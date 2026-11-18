#!/usr/bin/env python3
"""repo-baseline 写入脚本。只创建缺失文件、只向 .gitignore 追加缺失行，从不覆盖已有文件。

  apply.py --root DIR                    计划模式（默认）：列出将要做的事，不写文件
  apply.py --root DIR --write [选项]     执行写入。每个选项都必须先经用户确认

选项：
  --with-ci     新增 GitHub Actions 工作流与 dependabot.yml（仅 GitHub 仓库，且缺失时）
  --autoupdate  执行 pre-commit autoupdate，把 rev 占位符换成真实版本（需要联网）
  --install     安装 pre-commit（uv tool install）、安装 git 钩子；隐含 --autoupdate
  --accept-conflicts  用户已确认阻断性冲突（如 husky）后，允许继续写入
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from detect import GITIGNORE_LINES, analyze, in_dir, label, pnpm, read_text  # noqa: E402

EDITORCONFIG = """root = true

[*]
indent_style = space
indent_size = 2
end_of_line = lf
charset = utf-8
trim_trailing_whitespace = true
insert_final_newline = true

[*.py]
indent_size = 4

[Makefile]
indent_style = tab
"""

PRECOMMIT_BASE = """repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: <latest>
    hooks:
      - id: check-added-large-files
        args: [--maxkb=1024]
      - id: detect-private-key
      - id: check-merge-conflict
      - id: trailing-whitespace
      - id: end-of-file-fixer
  - repo: https://github.com/gitleaks/gitleaks
    rev: <latest>
    hooks:
      - id: gitleaks
  - repo: https://github.com/commitizen-tools/commitizen
    rev: <latest>
    hooks:
      - id: commitizen
        stages: [commit-msg]
"""

RUFF_TOML_HEAD = "# 由 repo-baseline 生成。pyproject.toml 已有 [tool.ruff] 时不会创建本文件。\nline-length = 100\n"

RUFF_SELECT = '\n[lint]\nselect = ["E", "F", "I", "B", "UP", "SIM"]\n'

DEPENDABOT = """version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
"""


# ---------- 小工具 ----------

def jp(d: str, name: str) -> str:
    """拼接相对路径，项目在根目录时不加前缀。"""
    return name if d in ("", ".") else f"{d}/{name}"


def dir_prefix(d: str) -> str:
    return "/" if d in ("", ".") else f"/{d}"


def ruff_cmd(py: dict) -> str:
    return "uv run ruff" if py["ruff_dep"] else "uvx ruff"


def run(cmd: list[str], cwd: Path) -> dict:
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=900)
        return {"cmd": " ".join(cmd), "ok": r.returncode == 0, "tail": (r.stdout + r.stderr)[-400:]}
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"cmd": " ".join(cmd), "ok": False, "tail": str(e)}


# ---------- 模板渲染 ----------

def render_precommit(pys: list[dict], fes: list[dict]) -> str:
    parts = [PRECOMMIT_BASE]
    for p in pys[:1]:
        files = "" if p["dir"] == "." else f"        files: ^{re.escape(p['dir'])}/\n"
        parts.append(
            "  - repo: https://github.com/astral-sh/ruff-pre-commit\n"
            "    rev: <latest>\n"
            "    hooks:\n"
            "      - id: ruff\n"
            "        args: [--fix]\n" + files +
            "      - id: ruff-format\n" + files)
    for f in fes[:1]:
        d = f["dir"]
        files = "" if d == "." else f"        files: ^{re.escape(d)}/\n"
        parts.append(
            "  - repo: local\n"
            "    hooks:\n"
            "      - id: prettier\n"
            "        name: prettier\n"
            f"        entry: {jp(d, 'node_modules/.bin/prettier')} --write --ignore-unknown\n"
            "        language: system\n" + files +
            "        exclude: '(pnpm-lock\\.yaml|package-lock\\.json|yarn\\.lock)$'\n")
    return "".join(parts)


def _block(name: str, lines: list[str]) -> list[str]:
    return [f"{name}:"] + [f"\t{ln}" for ln in lines] + [""]


def render_makefile(pys: list[dict], fes: list[dict]) -> str:
    setup = [
        "@command -v pre-commit >/dev/null 2>&1 || uv tool install pre-commit",
        "pre-commit install",
        "pre-commit install --hook-type commit-msg",
    ]
    lint: list[str] = []
    test: list[str] = []
    no_test = "没有可执行的测试"
    for p in pys[:1]:
        d, r = p["dir"], ruff_cmd(p)
        setup.append(in_dir(d, "uv sync"))
        lint += [in_dir(d, f"{r} check ."), in_dir(d, f"{r} format --check .")]
        if p["pyright_config"] and p["pyright_dep"]:
            lint.append(in_dir(d, "uv run pyright"))
        if p["tests"] and p["pytest_dep"]:
            test.append(in_dir(d, "uv run pytest"))
        elif p["tests"]:
            no_test = "tests/ 存在，但未声明 pytest，未生成测试命令（见 detect 报告）"
    for f in fes[:1]:
        d = f["dir"]
        setup.append(pnpm(d, "install"))
        if f["scripts"]["lint"]:
            lint.append(pnpm(d, "run lint"))
        if f["prettier_dep"]:
            # 锁文件不参与格式检查：prettier 会重写它们，和 pnpm 自己维护的格式打架。
            lint.append(pnpm(d, 'exec prettier --check . "!pnpm-lock.yaml" "!package-lock.json" "!yarn.lock"'))
        if f["typescript"]:
            tc = "vue-tsc" if f["vue_tsc"] else "tsc"
            lint.append(pnpm(d, f"exec {tc} --noEmit"))
        if f["scripts"]["test"]:
            test.append(pnpm(d, "run test"))

    out = [".PHONY: setup lint test fmt check", ""]
    out += _block("setup", setup)
    out += _block("lint", lint or ['@echo "没有可执行的检查项，请先补全工具配置"'])
    out += _block("test", test or [f'@echo "{no_test}"'])
    out += _block("fmt", ["pre-commit run --all-files"])
    out += ["check: lint test", ""]
    return "\n".join(out)


def render_agents(rep: dict) -> str:
    pys, fes = rep["stacks"]["python"], rep["stacks"]["frontend"]
    lines = [
        "# 工作说明", "", "## 常用命令", "",
        "- 首次准备：`make setup`",
        "- 提交前检查（不修改文件）：`make check`",
        "- 自动格式化（会改文件）：`make fmt`",
        "", "## 结构", "",
    ]
    for p in pys[:1]:
        where = "仓库根目录" if p["dir"] in ("", ".") else f"`{p['dir']}/`"
        lines.append(f"- 后端：{where}，Python，依赖由 uv 管理")
        if p["migrations"]:
            lines.append(f"- 数据库结构只改 `{jp(p['dir'], 'migrations/')}`，不要手改其他 schema 文件")
    for f in fes[:1]:
        fw = "、".join(f["frameworks"]) or "Node"
        where = "仓库根目录" if f["dir"] in ("", ".") else f"`{f['dir']}/`"
        lines.append(f"- 前端：{where}，{fw}，依赖由 {f['package_manager'] or 'pnpm'} 管理")
    lines += ["", "## 工具检查不到的约定", "",
              "<!-- 同一类错误犯了两次再补一行；没有就删掉本节 -->", ""]
    return "\n".join(lines)


def render_ruff(py: dict) -> str:
    head = RUFF_TOML_HEAD
    if py["target"]:
        head += f'target-version = "{py["target"]}"\n'
    return head + RUFF_SELECT


def render_ci(rep: dict) -> str:
    pys, fes = rep["stacks"]["python"], rep["stacks"]["frontend"]
    branches = ["main"]
    cur = rep["git"].get("branch")
    if cur and cur not in branches:
        branches.append(cur)
    steps = ["      - uses: actions/checkout@v4"]
    if pys:
        # 没有 uv.lock 时 --frozen 会直接失败。
        frozen = " --frozen" if pys[0]["uv"] else ""
        steps += ["      - uses: astral-sh/setup-uv@v5",
                  f"      - run: {in_dir(pys[0]['dir'], f'uv sync{frozen}')}"]
    if fes:
        d = fes[0]["dir"]
        # pnpm/action-setup 必须知道版本：优先 package.json 的 packageManager，否则钉一个主版本。
        field = str(fes[0].get("package_manager_field") or "")
        version = field.split("@", 1)[1] if field.startswith("pnpm@") else "9"
        has_lock = fes[0]["package_manager"] == "pnpm"
        steps += [
            "      - uses: pnpm/action-setup@v4",
            "        with:",
            f'          version: "{version}"',
            "      - uses: actions/setup-node@v4",
            "        with:",
            '          node-version: "22"',
        ]
        if has_lock:
            # 没有 pnpm-lock.yaml 时 setup-node 的 cache 会直接失败。
            steps += ["          cache: pnpm",
                      f"          cache-dependency-path: {jp(d, 'pnpm-lock.yaml')}"]
        steps.append(f"      - run: {pnpm(d, 'install' + (' --frozen-lockfile' if has_lock else ''))}")
    steps.append("      - run: make check")
    return "\n".join([
        "name: ci",
        "on:",
        "  pull_request:",
        "  push:",
        f"    branches: [{', '.join(branches)}]",
        "permissions:",
        "  contents: read",
        "jobs:",
        "  check:",
        "    runs-on: ubuntu-latest",
        "    steps:",
    ] + steps) + "\n"


def render_dependabot(rep: dict) -> str:
    text = DEPENDABOT
    for f in rep["stacks"]["frontend"][:1]:
        text += (
            '  - package-ecosystem: "npm"\n'
            f'    directory: "{dir_prefix(f["dir"])}"\n'
            "    schedule:\n"
            '      interval: "weekly"\n'
        )
    return text


# ---------- 计划与执行 ----------

def act(kind: str, path: str, content: str = "", reason: str = "") -> dict:
    return {"kind": kind, "path": path, "content": content, "reason": reason}


def build_actions(rep: dict, opts: argparse.Namespace) -> tuple[list[dict], list[str]]:
    acts: list[dict] = []
    confirm: list[str] = []
    pys, fes = rep["stacks"]["python"], rep["stacks"]["frontend"]
    f = rep["files"]
    gh = rep["git"]["github"]
    placeholder = "<latest>" in read_text(Path(rep["root"]) / ".pre-commit-config.yaml")

    if not f[".editorconfig"]:
        acts.append(act("create", ".editorconfig", EDITORCONFIG))
    if not f[".gitignore"]:
        acts.append(act("create", ".gitignore", "\n".join(GITIGNORE_LINES) + "\n"))
    elif rep["gitignore_missing"]:
        acts.append(act("append", ".gitignore", "\n".join(rep["gitignore_missing"]) + "\n"))
    if not f[".pre-commit-config.yaml"]:
        acts.append(act("create", ".pre-commit-config.yaml", render_precommit(pys, fes)))
        placeholder = True
    if not f["Makefile"]:
        acts.append(act("create", "Makefile", render_makefile(pys, fes)))
    if not f["AGENTS.md"]:
        if rep["claude_custom"]:
            acts.append(act("skip", "AGENTS.md", reason="CLAUDE.md 已有自定义内容，需先确认迁移方式"))
        else:
            acts.append(act("create", "AGENTS.md", render_agents(rep)))
    if not f["CLAUDE.md"] and not rep["claude_custom"]:
        acts.append(act("create", "CLAUDE.md", "@AGENTS.md\n"))
    for p in pys[:1]:
        if not p["ruff_config"]:
            acts.append(act("create", jp(p["dir"], "ruff.toml"), render_ruff(p)))

    if gh:
        if not rep["ci"]:
            if opts.ci:
                acts.append(act("create", ".github/workflows/ci.yml", render_ci(rep)))
            else:
                confirm.append("GitHub Actions CI（加 --with-ci）")
        if not rep["dependabot"]:
            if opts.ci:
                acts.append(act("create", ".github/dependabot.yml", render_dependabot(rep)))
            else:
                confirm.append("dependabot.yml（加 --with-ci）")

    if not rep["git"]["is_repo"]:
        confirm.append("git init（需确认，脚本不会自动执行）")
    elif not rep["hooks"]["git_hook_installed"] and not opts.install:
        confirm.append("安装 pre-commit 与 git 钩子（加 --install）")
    if placeholder and not (opts.install or opts.autoupdate):
        confirm.append("pre-commit autoupdate（联网，必需；加 --autoupdate 或 --install）")
    if fes and not (fes[0]["eslint_configs"] and fes[0]["prettier_dep"]):
        confirm.append("前端 eslint、prettier 依赖安装（需确认，脚本不会自动安装）")
    if not rep["hooks"]["claude_hook"]:
        confirm.append("SessionStart 提醒钩子（确认后运行 hook.py install）")
    return acts, confirm


def execute(root: Path, rep: dict, acts: list[dict], opts: argparse.Namespace) -> tuple[list[dict], list[dict]]:
    results: list[dict] = []
    steps: list[dict] = []
    for a in acts:
        p = root / a["path"]
        if a["kind"] == "create":
            if p.exists():
                results.append({"path": a["path"], "result": "跳过（已存在）"})
                continue
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(a["content"], encoding="utf-8")
            results.append({"path": a["path"], "result": "已创建"})
        elif a["kind"] == "append":
            old = read_text(p)
            prefix = "" if (not old or old.endswith("\n")) else "\n"
            p.write_text(old + prefix + "# repo-baseline 追加\n" + a["content"], encoding="utf-8")
            results.append({"path": a["path"], "result": "已追加缺失行"})
        else:
            results.append({"path": a["path"], "result": f"跳过（{a['reason']}）"})

    if opts.install or opts.autoupdate:
        pc = root / ".pre-commit-config.yaml"
        if not shutil.which("pre-commit") and opts.install and shutil.which("uv"):
            steps.append(run(["uv", "tool", "install", "pre-commit"], root))
        exe = shutil.which("pre-commit")
        if not exe:
            steps.append({"cmd": "pre-commit", "ok": False,
                          "tail": "找不到 pre-commit。确认 ~/.local/bin 在 PATH 中后重试"})
        else:
            steps.append(run([exe, "autoupdate"], root))
            still = "<latest>" in read_text(pc)
            if opts.install:
                if not rep["git"]["is_repo"]:
                    steps.append({"cmd": "pre-commit install", "ok": False,
                                  "tail": "不是 git 仓库，未安装钩子（需先 git init）"})
                elif still:
                    steps.append({"cmd": "pre-commit install", "ok": False,
                                  "tail": "autoupdate 失败，rev 仍为占位符，未安装钩子"})
                else:
                    steps.append(run([exe, "install"], root))
                    steps.append(run([exe, "install", "--hook-type", "commit-msg"], root))
    return results, steps


def main() -> int:
    ap = argparse.ArgumentParser(description="repo-baseline 写入（默认计划模式）")
    ap.add_argument("--root", default=".", help="项目根目录")
    ap.add_argument("--write", action="store_true", help="真正写入（默认只列出计划）")
    ap.add_argument("--with-ci", dest="ci", action="store_true")
    ap.add_argument("--autoupdate", action="store_true")
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--accept-conflicts", action="store_true",
                    help="用户已确认阻断性冲突（如 husky）可以继续写入")
    opts = ap.parse_args()

    root = Path(opts.root).resolve()
    if not root.is_dir():
        print(json.dumps({"error": f"目录不存在：{root}"}, ensure_ascii=False))
        return 2
    rep = analyze(root)
    if rep["state"] == "empty":
        print(json.dumps({"state": "empty", "message": "目录为空，请先确认是否搭建项目"},
                         ensure_ascii=False, indent=2))
        return 0
    if rep["state"] == "complete":
        print(json.dumps({"state": "complete", "message": "基线已完整，无需写入"},
                         ensure_ascii=False, indent=2))
        return 0
    if rep["blocking"] and opts.write and not opts.accept_conflicts:
        print(json.dumps({"state": rep["state"], "mode": "refused", "blocking": rep["blocking"],
                          "message": "存在阻断性冲突，已拒绝写入。先与用户确认，再加 --accept-conflicts 重试"},
                         ensure_ascii=False, indent=2))
        return 3

    acts, confirm = build_actions(rep, opts)
    out: dict = {
        "state": rep["state"],
        "blocking": rep["blocking"],
        "mode": "write" if opts.write else "plan",
        "actions": [
            {"kind": a["kind"], "path": a["path"], "reason": a["reason"],
             **({} if opts.write or a["kind"] != "create"
                else {"preview": a["content"].splitlines()[:15]})}
            for a in acts
        ],
        "needs_confirm": confirm,
    }
    if opts.write:
        results, steps = execute(root, rep, acts, opts)
        out["results"] = results
        out["steps"] = steps
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
