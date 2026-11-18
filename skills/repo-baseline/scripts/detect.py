#!/usr/bin/env python3
"""repo-baseline 检测脚本。只读，不写任何文件。

  detect.py --root DIR          输出完整 JSON 报告
  detect.py --root DIR --quick  基线不完整时输出一行提示，完整时无输出（供 SessionStart 钩子使用）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

WALK_SKIP = {
    ".git", "node_modules", ".venv", "venv", "dist", "build", "target", ".next",
    "__pycache__", "backups", "release", "generated_images", ".idea", ".vscode",
}
MAX_DEPTH = 3
LARGE_BYTES = 1024 * 1024

BASE_FILES = [".editorconfig", ".gitignore", ".pre-commit-config.yaml", "Makefile", "AGENTS.md", "CLAUDE.md"]

GITIGNORE_LINES = [
    "backups/", "dist/", "release/", "node_modules/", "*.dump", "*.tar.gz", "*.tsbuildinfo",
    ".env", "*.pem", "*.p12", ".venv/", "__pycache__/", ".DS_Store", ".claude/settings.local.json",
]

# 有这些文件说明目录里已经有源码，即使缺依赖清单也不能当成「空目录」。
SOURCE_SUFFIXES = (
    ".py", ".pyi", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue", ".svelte",
    ".go", ".rs", ".java", ".kt", ".rb", ".php", ".cs", ".swift", ".c", ".cc", ".cpp", ".h", ".hpp",
)

ESLINT_FILES = [
    ".eslintrc", ".eslintrc.js", ".eslintrc.cjs", ".eslintrc.json", ".eslintrc.yml",
    "eslint.config.js", "eslint.config.mjs", "eslint.config.cjs", "eslint.config.ts",
]
PRETTIER_FILES = [
    ".prettierrc", ".prettierrc.json", ".prettierrc.js", ".prettierrc.cjs",
    ".prettierrc.yaml", ".prettierrc.yml", "prettier.config.js", "prettier.config.cjs",
    "prettier.config.mjs",
]
STYLELINT_FILES = [
    ".stylelintrc", ".stylelintrc.json", ".stylelintrc.js", ".stylelintrc.cjs",
    ".stylelintrc.yml", "stylelint.config.js", "stylelint.config.cjs", "stylelint.config.mjs",
]

RISK_RULES = [
    (re.compile(r"(^|/)\.env$"), "密钥文件 .env 被提交"),
    (re.compile(r"\.(dump|bak)$|\.sql\.gz$"), "数据库备份被提交"),
    (re.compile(r"\.(tar\.gz|tgz|zip)$"), "压缩包被提交"),
    (re.compile(r"\.(pem|key|p12)$"), "私钥或证书被提交"),
    (re.compile(r"^(backups|dist|release|node_modules)/"), "构建产物或备份目录被跟踪"),
]


# ---------- 基础工具 ----------

def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def git(root: Path, *args: str) -> str | None:
    if not shutil.which("git"):
        return None
    try:
        r = subprocess.run(["git", "-C", str(root), *args],
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def walk(root: Path) -> list[tuple[Path, list[str]]]:
    """遍历目录，跳过无关目录，深度不超过 MAX_DEPTH。"""
    base = len(root.parts)
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        depth = len(Path(dirpath).parts) - base
        dirnames[:] = [d for d in dirnames if d not in WALK_SKIP] if depth < MAX_DEPTH else []
        out.append((Path(dirpath), filenames))
    return out


def rel(root: Path, p: Path) -> str:
    return os.path.relpath(p, root).replace(os.sep, "/")


def sort_key(d: str) -> tuple[int, str]:
    return (0 if d == "." else d.count("/") + 1, d)


def existing(p: Path, names: list[str]) -> list[str]:
    return [n for n in names if (p / n).exists()]


def has_suffix(root: Path, suffixes: tuple[str, ...]) -> bool:
    return any(f.endswith(suffixes) for _, files in walk(root) for f in files)


def has_dep(text: str, lock: str, name: str) -> bool:
    """依赖是否真的声明了。必须按完整包名匹配：`"pytest` 会命中 `"pytest-cov`。"""
    pattern = rf'["\']{re.escape(name)}\s*(?:[<>=!~;\[]|["\'])'
    return bool(re.search(pattern, text)) or f'name = "{name}"' in lock


def make_targets(path: Path) -> list[str]:
    """Makefile 里的目标名。过滤点开头的特殊目标与 URL，避免 drift 判断被噪声带偏。"""
    found = re.findall(r"^([A-Za-z0-9_.-]+)\s*:(?!=)(?!//)", read_text(path), re.M)
    return sorted({t for t in found if not t.startswith(".")})


def in_dir(d: str, cmd: str) -> str:
    """在项目子目录执行命令；项目在根目录时不加 `cd .`。"""
    return cmd if d in ("", ".") else f"cd {d} && {cmd}"


def pnpm(d: str, args: str) -> str:
    """调用 pnpm；项目在根目录时不加 `-C .`。"""
    return f"pnpm {args}" if d in ("", ".") else f"pnpm -C {d} {args}"


def label(d: str) -> str:
    """报告里的项目名：根目录不要写成 `.`。"""
    return "根目录" if d in ("", ".") else d


# ---------- 分项分析 ----------

def analyze_python(root: Path, d: str) -> dict:
    p = root / d
    text = read_text(p / "pyproject.toml")
    lock = read_text(p / "uv.lock")
    m = re.search(r'requires-python\s*=\s*"[^\d"]*(\d+)\.(\d+)', text)
    if not m:
        m = re.match(r"(\d+)\.(\d+)", read_text(p / ".python-version").strip())
    return {
        "dir": d,
        "uv": (p / "uv.lock").exists(),
        "target": f"py{m.group(1)}{m.group(2)}" if m else None,
        "ruff_config": "[tool.ruff" in text or (p / "ruff.toml").exists() or (p / ".ruff.toml").exists(),
        "ruff_dep": has_dep(text, lock, "ruff"),
        "pyright_config": (p / "pyrightconfig.json").exists() or "[tool.pyright]" in text,
        "pyright_dep": has_dep(text, lock, "pyright"),
        "pytest_dep": has_dep(text, lock, "pytest"),
        "tests": (p / "tests").is_dir(),
        "migrations": (p / "migrations").is_dir(),
    }


def analyze_frontend(root: Path, d: str) -> dict:
    p = root / d
    try:
        pkg = json.loads(read_text(p / "package.json") or "{}")
    except json.JSONDecodeError:
        pkg = {}
    deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
    scripts = pkg.get("scripts") or {}
    if (root / "pnpm-lock.yaml").exists() or (p / "pnpm-lock.yaml").exists():
        pm = "pnpm"
    elif (p / "package-lock.json").exists():
        pm = "npm"
    elif (p / "yarn.lock").exists():
        pm = "yarn"
    else:
        pm = None
    return {
        "dir": d,
        "package_manager": pm,
        "package_manager_field": pkg.get("packageManager"),
        "frameworks": [n for n in ("vue", "react", "next", "vite") if n in deps],
        "typescript": "typescript" in deps or (p / "tsconfig.json").exists(),
        "vue_tsc": "vue-tsc" in deps,
        "eslint_configs": existing(p, ESLINT_FILES),
        "eslint_dep": "eslint" in deps,
        "prettier_configs": existing(p, PRETTIER_FILES),
        "prettier_dep": "prettier" in deps,
        "stylelint_configs": existing(p, STYLELINT_FILES),
        "stylelint_dep": "stylelint" in deps,
        "biome": (p / "biome.json").exists() or "@biomejs/biome" in deps,
        "css": has_suffix(p, (".css",)),
        "scss": has_suffix(p, (".scss", ".sass")),
        "scripts": {k: k in scripts for k in ("lint", "test", "typecheck")},
        "lint_cmd": str(scripts.get("lint") or ""),
    }


def analyze_git(root: Path) -> dict:
    top = git(root, "rev-parse", "--show-toplevel")
    if top is None:
        return {"is_repo": False, "is_root": False, "github": False, "branch": None,
                "hooks_path": None, "risks": [], "risk_count": 0, "tracked_count": 0}
    remotes = git(root, "remote", "-v") or ""
    branch = (git(root, "branch", "--show-current") or "").strip() or None
    hooks_path = (git(root, "config", "--get", "core.hooksPath") or "").strip() or None
    tracked = [t for t in (git(root, "ls-files", "-z") or "").split("\0") if t]
    risks: list[str] = []
    for t in tracked:
        msg = next((m for rx, m in RISK_RULES if rx.search(t)), None)
        if msg:
            risks.append(f"{msg}：{t}")
            continue
        try:
            if (root / t).is_file() and (root / t).stat().st_size > LARGE_BYTES:
                risks.append(f"大于 1MB 的文件：{t}")
        except OSError:
            pass
    return {
        "is_repo": True,
        "is_root": Path(top.strip()).resolve() == root.resolve(),
        "github": "github.com" in remotes,
        "branch": branch,
        "hooks_path": hooks_path,
        "risks": risks[:50],
        "risk_count": len(risks),
        "tracked_count": len(tracked),
    }


def analyze_hooks(root: Path) -> dict:
    """钩子位置用 git 自己解析：子目录仓库与 worktree 的 hooks 都不在 <root>/.git/hooks。"""
    declared = git(root, "rev-parse", "--git-path", "hooks")
    if declared:
        hooks_dir = root / declared.strip()
    else:
        hooks_dir = root / ".git" / "hooks"
    hook = hooks_dir / "pre-commit"
    return {
        "pre_commit_on_path": shutil.which("pre-commit") is not None,
        "git_hook_installed": hook.is_file() and "pre-commit" in read_text(hook)[:4000],
        "claude_hook": "repo-baseline" in read_text(root / ".claude" / "settings.local.json"),
    }


# ---------- 总分析 ----------

def analyze(root: Path) -> dict:
    root = root.resolve()
    py_dirs, fe_dirs, jv_dirs = [], [], []
    for d, names in walk(root):
        r = rel(root, d)
        s = set(names)
        if s & {"pyproject.toml", "uv.lock"}:
            py_dirs.append(r)
        if "package.json" in s:
            fe_dirs.append(r)
        if "pom.xml" in s or any(n.startswith("build.gradle") for n in s):
            jv_dirs.append(r)

    pythons = [analyze_python(root, d) for d in sorted(py_dirs, key=sort_key)]
    frontends = [analyze_frontend(root, d) for d in sorted(fe_dirs, key=sort_key)]
    javas = [{"dir": d, "build": "maven" if (root / d / "pom.xml").exists() else "gradle"}
             for d in sorted(jv_dirs, key=sort_key)]
    git_info = analyze_git(root)
    hooks = analyze_hooks(root)

    files = {f: (root / f).exists() for f in BASE_FILES}
    wf = root / ".github" / "workflows"
    ci = wf.is_dir() and any(wf.glob("*.y*ml"))
    dependabot = any((root / ".github" / n).exists() for n in ("dependabot.yml", "dependabot.yaml"))
    pc = read_text(root / ".pre-commit-config.yaml")
    existing_gi = {ln.strip() for ln in read_text(root / ".gitignore").splitlines()}
    gi_missing = [ln for ln in GITIGNORE_LINES if ln not in existing_gi]
    claude_text = read_text(root / "CLAUDE.md")
    claude_refs = "@AGENTS.md" in claude_text
    claude_custom = bool(claude_text.strip()) and not claude_refs
    targets = make_targets(root / "Makefile")
    is_repo = git_info["is_repo"]

    conflicts: list[str] = []
    missing: list[str] = []
    suggestions: list[str] = []
    drift: list[str] = []
    stacks_found = bool(pythons or frontends or javas)
    base_any = any(files.values())

    # 冲突：必须先问用户
    if is_repo and not git_info["is_root"]:
        conflicts.append("当前目录不是 git 仓库根目录")
    blocking: list[str] = []  # 会阻断写入的冲突，除非用户明确接受
    if git_info["hooks_path"] or (root / ".husky").is_dir():
        msg = "检测到 husky 或 core.hooksPath，与 pre-commit 冲突，需先确认迁移或保留"
        conflicts.append(msg)
        blocking.append(msg)
    if claude_custom and not files["AGENTS.md"]:
        conflicts.append("CLAUDE.md 已有自定义内容且 AGENTS.md 不存在，需确认是否迁入 AGENTS.md")
    if len(pythons) > 1:
        conflicts.append("多个 Python 项目目录：" + "、".join(p["dir"] for p in pythons) + "，默认使用第一个")
    if len(frontends) > 1:
        conflicts.append("多个前端项目目录：" + "、".join(f["dir"] for f in frontends) + "，默认使用第一个")

    # 缺失：基线必需项
    if not is_repo:
        missing.append("git 仓库（需先 git init，需确认）")
    for name in (".editorconfig", ".gitignore", ".pre-commit-config.yaml", "Makefile"):
        if not files[name]:
            missing.append(name)
    if files[".gitignore"] and gi_missing:
        missing.append(f".gitignore 缺 {len(gi_missing)} 行")
    if files[".pre-commit-config.yaml"] and "<latest>" in pc:
        missing.append("pre-commit 配置未 autoupdate（rev 为占位符）")
    if not files["AGENTS.md"] and not claude_custom:
        missing.append("AGENTS.md")
    if not files["CLAUDE.md"]:
        missing.append("CLAUDE.md")
    if is_repo and not hooks["git_hook_installed"]:
        missing.append("pre-commit 的 git 钩子未安装")
    if files["Makefile"] and "check" not in targets:
        missing.append("Makefile 缺少 check 目标")
    if git_info["github"]:
        if not ci:
            missing.append("CI 工作流（.github/workflows）")
        if not dependabot:
            missing.append("dependabot.yml")

    for p in pythons:
        if not p["ruff_config"]:
            missing.append(f"{label(p['dir'])}：缺 ruff 配置")
        if not p["ruff_dep"]:
            suggestions.append(f"{label(p['dir'])}：ruff 未声明为依赖，检查命令将用 uvx；建议 uv add --dev ruff")
        if not p["pyright_config"]:
            suggestions.append(f"{label(p['dir'])}：未配置 pyright（可选）")
        if p["tests"] and not p["pytest_dep"]:
            suggestions.append(f"{label(p['dir'])}：有 tests/ 但未声明 pytest 依赖")
        if p["migrations"]:
            suggestions.append(f"{label(p['dir'])}/migrations 存在：建议 CI 增加空库迁移检查")

    for f in frontends:
        d = f["dir"]
        if f["package_manager"] not in (None, "pnpm"):
            conflicts.append(f"{label(d)}：包管理器为 {f['package_manager']}，模板按 pnpm 生成")
        if f["biome"]:
            conflicts.append(f"{label(d)}：检测到 biome，与 prettier、eslint 可能重复")
        legacy = [c for c in f["eslint_configs"] if c.startswith(".eslintrc")]
        flat = [c for c in f["eslint_configs"] if c.startswith("eslint.config")]
        if legacy and flat:
            conflicts.append(f"{label(d)}：新旧 eslint 配置并存（{', '.join(legacy + flat)}）")
        if not f["eslint_configs"]:
            missing.append(f"{label(d)}：缺 eslint 配置（需安装依赖，需确认）")
        if not f["prettier_dep"]:
            missing.append(f"{label(d)}：缺 prettier（需安装依赖，需确认）")
        if not f["scripts"]["lint"]:
            missing.append(f"{label(d)}：package.json 缺 lint 脚本")
        elif "eslint" in f["lint_cmd"] and not f["eslint_dep"]:
            suggestions.append(f"{label(d)}：lint 脚本调用 eslint，但 eslint 未声明为依赖，make check 会失败")
        if (f["css"] or f["scss"]) and not (f["stylelint_dep"] or f["stylelint_configs"]):
            suggestions.append(f"{label(d)}：有 css 或 scss，但既无 stylelint 配置也无依赖")
        if not f["typescript"]:
            suggestions.append(f"{label(d)}：未使用 TypeScript，不生成类型检查")
        elif "vue" in f["frameworks"] and not f["vue_tsc"]:
            suggestions.append(f"{label(d)}：Vue 项目建议安装 vue-tsc")

    # 漂移：工具已经存在，但 Makefile 没有调用（Makefile 不会被覆盖，只报告）
    makefile_text = read_text(root / "Makefile")
    if makefile_text:
        for p in pythons:
            if p["ruff_config"] and "ruff" not in makefile_text:
                drift.append(f"Makefile 未调用 {label(p['dir'])} 的 ruff")
        for f in frontends:
            d = f["dir"]
            if f["scripts"]["lint"] and pnpm(d, "run lint") not in makefile_text:
                drift.append(f"package.json 有 lint 脚本，但 Makefile 未调用（{d}）")
            if f["prettier_dep"] and "prettier --check" not in makefile_text:
                drift.append(f"已安装 prettier，但 Makefile 未检查格式（{d}）")

    if javas:
        suggestions.append(
            "Java（" + "、".join(j["dir"] for j in javas) + "）：推荐 Spotless 管格式，"
            "Checkstyle 或 P3C 二选一管规范，SpotBugs 加 find-sec-bugs 查安全，JaCoCo 管覆盖率。"
            "只给建议，不改构建文件。")
    if not is_repo and stacks_found:
        suggestions.append("不是 git 仓库，无法检查提交风险")

    # 「空」不能只看依赖清单：只有源码、还没建清单的目录也是项目，建不了基线要如实说。
    has_source = has_suffix(root, SOURCE_SUFFIXES)
    if not stacks_found and not base_any and not has_source:
        state = "empty"
    elif missing:
        state = "partial"
    else:
        state = "complete"

    return {
        "root": str(root),
        "state": state,
        "git": git_info,
        "hooks": hooks,
        "stacks": {"python": pythons, "frontend": frontends, "java": javas},
        "files": files,
        "ci": ci,
        "dependabot": dependabot,
        "makefile_targets": targets,
        "gitignore_missing": gi_missing,
        "claude_custom": claude_custom,
        "conflicts": conflicts,
        "blocking": blocking,
        "missing": missing,
        "drift": drift,
        "suggestions": suggestions,
        "risks": git_info["risks"],
    }


def quick_message(rep: dict) -> str:
    if rep["state"] == "complete":
        return ""
    if rep["state"] == "empty":
        return "[repo-baseline] 这个目录还没有可识别的项目（没有依赖清单，也没有源码）。要先搭建项目吗？"
    head = "；".join(rep["missing"][:3])
    more = f" 等 {len(rep['missing'])} 项" if len(rep["missing"]) > 3 else ""
    return f"[repo-baseline] 工程基线未完整，缺：{head}{more}。要补全吗？"


def main() -> int:
    ap = argparse.ArgumentParser(description="repo-baseline 只读检测")
    ap.add_argument("--root", default=".", help="项目根目录")
    ap.add_argument("--quick", action="store_true", help="只输出一行提示，供 SessionStart 钩子使用")
    args = ap.parse_args()
    root = Path(args.root)
    if args.quick:
        try:
            msg = quick_message(analyze(root))
        except Exception:  # 钩子不能因为检测出错而影响会话启动
            return 0
        if msg:
            print(msg)
        return 0
    if not root.is_dir():
        print(f"目录不存在：{root}", file=sys.stderr)
        return 2
    print(json.dumps(analyze(root), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
