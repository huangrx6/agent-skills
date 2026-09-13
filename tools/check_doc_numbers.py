#!/usr/bin/env python3
"""检查文档里写的测试条数是不是**真的**。

为什么有这个
------------
这一类错在本仓库已经出现过四次：

- `pingcode` 的 README 写着「120 条」和「134 条」，实际已经 139/166（改了两次才发现）
- WLRR 的 README 写着「0 脚本 0 测试」，补上脚本后那句话还在
- `git-dev-workflow` 的 README 初稿把仓库**实时状态**（未提交 13 项）抄进了文档

共同点：**数字是手写的，而它对应的事实会变**。人眼读文档时看不出哪个数字过期了 ——
而一个对不上的数字会让人开始怀疑整份文档。

做法
----
pre-commit hook 本来就会为每个 skill 跑一次测试，`Ran N tests` 就在它手上。
所以这里不要额外开销：把**刚测出来的真实条数**传进来，跟文档里写的比。

只认**紧跟在测试命令那一行**的数字（行内含 `unittest`），例如：

    python3 -m unittest discover -s tests -v     # 166 条：全绿

不认别处的 `N 条` —— 那些可能是「470 条接口」「8 条 eval」「9 条问题清单」，
不是同一个东西，硬比就是制造误报。

用法
----
    python3 tools/check_doc_numbers.py <文档目录> --actual 166
    python3 tools/check_doc_numbers.py <文档目录> --list      # 只看文档里声称了多少

退出码：0 对得上（或没有声称）/ 1 对不上 / 2 用法
"""

from __future__ import annotations

import argparse
import os
import re
import sys

# 只看「跑测试命令」那一行上的数字。行内含 unittest 才算 —— 这是唯一无歧义的位置。
COMMAND_LINE = re.compile(r"unittest", re.IGNORECASE)
CLAIM = re.compile(r"(\d+)\s*条")
DOC_NAMES = ("README.md", "SKILL.md")


def read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _as_int(value: object, default: int = -1) -> int:
    """宽松取整：文档内容是外部输入，读到怪东西不该让检查整体失败。"""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def claims(doc_dir: str) -> list[tuple[str, int, str]]:
    """返回 [(文件, 行号, 声称的条数)]，只取测试命令那一行上的。"""
    found: list[tuple[str, int, str]] = []
    for name in DOC_NAMES:
        path = os.path.join(doc_dir, name)
        if not os.path.isfile(path):
            continue
        for number, line in enumerate(read_text(path).splitlines(), start=1):
            if not COMMAND_LINE.search(line):
                continue
            for match in CLAIM.finditer(line):
                found.append((name, number, match.group(1)))
    return found


def check(doc_dir: str, actual: int) -> list[tuple[str, int, str, int]]:
    """返回对不上的 [(文件, 行号, 声称值, 实际值)]。"""
    return [(name, line, value, actual)
            for name, line, value in claims(doc_dir)
            if _as_int(value) != actual]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="检查文档里写的测试条数与实际是否一致")
    parser.add_argument("doc_dir", help="放着 README.md / SKILL.md 的目录")
    parser.add_argument("--actual", type=int, help="刚跑出来的真实条数")
    parser.add_argument("--list", action="store_true", help="只列出文档里声称的条数")
    args = parser.parse_args(argv)

    doc_dir = os.path.abspath(os.path.expanduser(args.doc_dir))
    if not os.path.isdir(doc_dir):
        print(f"读不到目录：{doc_dir}", file=sys.stderr)
        return 2

    found = claims(doc_dir)
    if args.list:
        if not found:
            print(f"{doc_dir}：文档里没有声称测试条数")
            return 0
        for name, line, value in found:
            print(f"{name}:{line}  声称 {value} 条")
        return 0

    if args.actual is None:
        parser.print_help()
        return 2

    bad = check(doc_dir, args.actual)
    if not bad:
        if found:
            print(f"✓ 文档里的测试条数与实际一致（{args.actual} 条）")
        return 0
    for name, line, value, actual in bad:
        print(f"✗ {name}:{line} 写着 {value} 条，实际是 {actual} 条"
              f"（跑一次上面那条命令就能确认）", file=sys.stderr)
    print("  改法：把那个数字改成实际值，或干脆不写数字（只写「全绿」）。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
