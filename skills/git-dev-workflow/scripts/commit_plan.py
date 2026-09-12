#!/usr/bin/env python3
"""把工作区的改动分成「候选提交」，**只出计划，不执行**。

## 为什么只出计划

分组是判断，不是计算。同一堆文件，按"一个功能"分还是按"一次重构"分，取决于你知道
而机器不知道的东西。所以这个脚本给的是**一份待确认的清单**：你能一眼看出它猜得对不对，
然后自己 `git add` 那几行。它不会替你 `add`、更不会替你 `commit`。

## 分组按「区域」，不按「增/改/删」

按区域（顶层目录，必要时下沉一层）分组，是因为**同一件事通常落在同一个区域里**；
增/改/删只是那件事的形状，把它也当切分轴，一个功能的"新增文件 + 改另一个文件"就会被
拆成两组 —— 那不是帮忙。

形状仍然有用：它决定**候选前缀**（只有删除 → `chore`/`refactor`；只碰测试 → `test`）。

## 两条硬规矩

1. **疑似凭据单独成组**，并且**不会出现在任何别的组里** —— 它是你提交前最该看一眼的东西。
2. **只有源码改动时，前缀写"需要你定"** —— `feat` / `fix` / `refactor` / `perf` 之间
   的差别是语义判断，机器只看得见扩展名。猜一个反倒像给了依据。

## 用法

    python3 scripts/commit_plan.py
    python3 scripts/commit_plan.py --json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys

# 文件名的形状 → 候选前缀。
#
# 写成顺序判断而不是「带 None 占位的表」：那种表逼着读取方处理 None，
# 而 None 在这里没有任何含义（它只是「这条规则用不到目录名」）。
TEST_DIRS = ("test", "tests", "spec", "specs", "__tests__", "e2e")
CI_NAMES = ("gitlab-ci.yml", "jenkinsfile", "azure-pipelines.yml", "cloudbuild.yaml")
CI_DIRS = (".github/workflows", ".circleci", ".buildkite")
BUILD_NAMES = ("Dockerfile", "Makefile", "pyproject.toml", "package.json", "setup.py",
               "setup.cfg", "go.mod", "go.sum", "Cargo.toml", "pom.xml", "build.gradle",
               "CMakeLists.txt", "docker-compose.yml")
BUILD_PREFIXES = ("requirements", "poetry.lock", "package-lock.json", "yarn.lock",
                  "pnpm-lock.yaml", "Gemfile.lock", "uv.lock")
SOURCE_HINT = "需要你定（feat / fix / refactor / perf 都可能）"


def _load_sibling(name: str):
    """按显式文件路径加载同目录模块（先注册 sys.modules 再 exec）。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"_gitdev_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了同目录模块：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


S = _load_sibling("git_state")

UNTRACKED_LINE_CAP = 10000          # 新文件超过这么多行就只报"≥ N 行"，不读下去
UNTRACKED_SIZE_CAP = 2 * 1024 * 1024


def area_of(path: str, first_components: set) -> str:
    """这个文件属于哪个区域。

    默认取第一段路径；如果**所有**改动都落在同一个第一段下（比如全在 `src/`），
    就下沉一层 —— 否则整份计划只有一个组，等于没分组。只下沉一次，不下沉到底：
    再往下就变成"每个文件一组"了。
    """
    parts = path.split("/")
    if len(parts) == 1:
        return "(仓库根)"
    if len(first_components) == 1 and len(parts) > 2:
        return "/".join(parts[:2])
    return parts[0]


def candidate_prefix(paths: list[str], kinds: set[str]) -> tuple[str, str]:
    """给一组文件猜一个候选前缀，并说明依据。猜不出来就说不出来。

    **每条规则都用 `all`，不用 `any`**：候选前缀是给**整组**用的，
    只要有一个路径像测试就报 test，那一组里真正的源码改动就被盖住了 ——
    而"你能一眼反驳它"正是这个字段存在的理由。（第一版用 any，真实输出里
    一组 mixed 的 scripts+tests 被报成 test，被自己的眼睛抓出来。）

    顺序有意义：先问"它是不是测试"，再问文档、CI、构建。每条都把依据写出来。
    """
    def is_test(path: str) -> bool:
        return any(part in TEST_DIRS for part in path.split("/"))

    def is_ci(path: str) -> bool:
        return (any(path.startswith(prefix) for prefix in CI_DIRS)
                or os.path.basename(path).lower() in CI_NAMES)

    def is_build(path: str) -> bool:
        base = os.path.basename(path)
        return base in BUILD_NAMES or base.startswith(BUILD_PREFIXES)

    def is_docs(path: str) -> bool:
        return os.path.splitext(path)[1].lower() in S.DOC_SUFFIXES

    if paths and all(is_test(path) for path in paths):
        return "test", "整组都是测试"
    if paths and all(is_docs(path) for path in paths):
        return "docs", "整组都是文档"
    if paths and all(is_ci(path) for path in paths):
        return "ci", "整组都是 CI 配置"
    if paths and all(is_build(path) for path in paths):
        return "build", "整组都是依赖清单 / 构建文件"
    if kinds and kinds <= {"D"}:
        return "chore", "整组只有删除（如果是在去掉某个功能，refactor 也行）"
    note = "；这组里含测试文件" if any(is_test(path) for path in paths) else ""
    return "", SOURCE_HINT + note


def count_lines(full: str) -> str:
    """数一个未跟踪文件有多少行。二进制/太大就说不数了 —— 不猜。"""
    try:
        if os.path.getsize(full) > UNTRACKED_SIZE_CAP:
            return "（文件太大，没数）"
        with open(full, "rb") as handle:
            head = handle.read(8192)
            if b"\0" in head:
                return "（二进制）"
            handle.seek(0)
            total = 0
            for total, _ in enumerate(handle, start=1):
                if total >= UNTRACKED_LINE_CAP:
                    return f"≥{UNTRACKED_LINE_CAP} 行"
    except OSError:
        return "（读不了）"
    return f"{total} 行"


def numstat(repo: str) -> dict[str, tuple[int, int]]:
    """相对 HEAD 的增删行数（含已暂存与未暂存）。"""
    out: dict[str, tuple[int, int]] = {}
    for line in S.git_lines(repo, "diff", "--numstat", "HEAD"):
        parts = line.split("\t")
        if len(parts) >= 3:
            added, deleted, path = parts[0], parts[1], parts[2]
            out[path] = (S.as_int(added), S.as_int(deleted))
    return out


def plan(state: dict) -> dict:
    repo = state["root"]
    entries = [e for e in state["dirty"]["files"] if e["code"] != "!!"]
    stats = numstat(repo)
    submodule_paths = {item["path"] for item in state["submodules"]["items"]}

    groups: dict[tuple[str, str], list[dict]] = {}
    for entry in entries:
        path = entry["path"]
        if entry["kind"] == "secret":
            key = ("⚠ 疑似凭据", "secret")
        elif any(path == sub or path.startswith(sub + "/") for sub in submodule_paths):
            key = ("子模块 / 路径指针", "submodule")
        else:
            key = (area_of(path, {"x"}), "normal")
        groups.setdefault(key, []).append(entry)

    # area 只下沉一次：先按第一段算，若整份改动只有一个第一段，再重算
    firsts = {e["path"].split("/")[0] for e in entries if "/" in e["path"]}
    if len(firsts) == 1:
        regroups: dict[tuple[str, str], list[dict]] = {}
        for (label, kind), items in groups.items():
            if kind != "normal":
                regroups[(label, kind)] = items
                continue
            for entry in items:
                regroups.setdefault((area_of(entry["path"], firsts), kind), []).append(entry)
        groups = regroups

    out_groups = []
    for (label, kind), items in sorted(groups.items()):
        paths = [e["path"] for e in items]
        kinds = {e["code"][0].replace("?", "A").replace(" ", "M") for e in items}
        prefix, reason = candidate_prefix(paths, kinds)
        added = sum(stats.get(path, (0, 0))[0] for path in paths)
        deleted = sum(stats.get(path, (0, 0))[1] for path in paths)
        untracked = [e for e in items if e["code"] == "??"]
        out_groups.append({
            "label": label,
            "kind": kind,
            "files": paths,
            "change_kinds": sorted(kinds),
            "added": added,
            "deleted": deleted,
            "untracked_lines": {e["path"]: count_lines(os.path.join(repo, e["path"]))
                                for e in untracked[:20]},
            "prefix": prefix,
            "prefix_reason": reason,
            "add_command": "git add -- " + " ".join(
                _quote(path) for path in paths[:40])
            + (" …（文件多，见 --json）" if len(paths) > 40 else ""),
        })
    return {"root": repo, "total_files": len(entries), "groups": out_groups}


def _quote(path: str) -> str:
    return f"'{path}'" if " " in path or "'" in path else path


def render(result: dict) -> str:
    lines = [f"仓库 {result['root']}",
             f"待整理 {result['total_files']} 个文件，分成 {len(result['groups'])} 组：",
             "",
             "（**不会自动 add、不会自动 commit** —— 下面是给你的清单和命令，你自己决定）"]
    for index, group in enumerate(result["groups"], start=1):
        head = f"{index}. {group['label']}   （改动形状：{'/'.join(group['change_kinds'])}）"
        if group["kind"] == "secret":
            head = f"{index}. ⚠ {group['label']} —— 提交前先确认这些是不是该进版本库"
        if group["kind"] == "submodule":
            head = f"{index}. {group['label']} —— 指针 bump 通常单独一条"
        lines.append("")
        lines.append(head)
        lines.append(f"   +{group['added']} / -{group['deleted']}")
        for path in group["files"][:12]:
            extra = group["untracked_lines"].get(path)
            lines.append(f"   {path}" + (f"   （新文件，{extra}）" if extra else ""))
        if len(group["files"]) > 12:
            lines.append(f"   …（还有 {len(group['files']) - 12} 个，见 --json）")
        if group["prefix"]:
            lines.append(f"   候选前缀：{group['prefix']}  —— 依据：{group['prefix_reason']}")
        else:
            lines.append(f"   候选前缀：{group['prefix_reason']}")
        lines.append(f"   git add -- {group['add_command'][len('git add -- '):]}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把改动分成候选提交（只出计划）")
    parser.add_argument("--repo", default=".", help="仓库路径（默认当前目录）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    state = S.snapshot(args.repo)
    if not state.get("is_repo"):
        print(f"不是一个 git 仓库：{os.path.abspath(args.repo)}", file=sys.stderr)
        return 1

    result = plan(state)
    if not result["groups"]:
        print("工作区是干净的，没有要分组的。")
        return 0
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json
          else render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
