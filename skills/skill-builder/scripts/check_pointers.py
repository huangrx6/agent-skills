#!/usr/bin/env python3
"""把仓库里的"指针语句"找出来，供人做逐词核对。

## 为什么只做"找出来"，不做"判断"

2026-09-12 的失败：把图片风格规格从 PKB 的 `resource-notes.md` 改成指向
`excalidraw-diagram`（现名 `diagram-authoring`）的指针 —— **但没把那些条款真的写进目标文件**。
"指针写对了"和"内容搬过去了"是两件事，只检查前者看起来任务已经完成。

**我试过把它做成自动判定器**：把指针动词之前那一段拆成词条，逐个在目标文件里
数出现次数。在真实仓库上跑出 12 条指针，几乎全是噪音：

| 噪音 | 例子 |
| --- | --- |
| 指针动词之前那一大段不是"主语列表"，是整句散文 | `所以本 skill 的做法是把旋钮从规格里拿走，放进脚本` 被当成一个词条 |
| 文件名通配被当成路径 | `*.diagram.json` → 假报"目标不存在" |
| 跨 skill 的相对路径解析不到 | `resource-notes.md` → 假报"目标不存在" |
| 中文字面 ≠ 语义 | 指针写"视觉排除项"，目标文件写"明确排除" |

**一个全是噪音的检查比没有检查更糟** —— 它会被忽略，然后连它能做对的那部分
也一起被忽略。所以这个脚本只做**可靠的那一半**：

1. 找出指针语句（哪些文件在说"这事定义在别处"）
2. 确认目标文件存在

**语义那一半（目标里到底有没有那些条款）留给人** —— 见 `SKILL.md` 的检查项
「改成指针时，逐词核对目标里真的接住了内容」。

用法：
    python3 check_pointers.py                # 扫 skills/
    python3 check_pointers.py PATH...
    python3 check_pointers.py --json

退出码：0 = 所有指针的目标都存在；1 = 有目标找不到；2 = 路径无效。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

POINTER_VERBS = r"(?:由|见|参见|详见|定义在|收拢到|不在这里定义)"
# 只认**像路径**的反引号内容：必须带扩展名，且不含通配符
PATH_IN_TICK = re.compile(r"`([^`*?\s]*\.(?:md|py|json|yaml|yml))`")

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv"}


def iter_docs(targets: list[str]):
    for t in targets:
        if os.path.isfile(t):
            yield t
            continue
        for root, dirs, files in os.walk(t):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            for name in sorted(files):
                if name.endswith(".md"):
                    yield os.path.join(root, name)


def _build_basename_index(root: str) -> dict[str, str]:
    """按文件名建索引 —— 跨 skill 的引用（`resource-notes.md`）只写文件名，
    这类解析靠 basename 最可靠。"""
    index: dict[str, str] = {}
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for name in files:
            if name.endswith((".md", ".py", ".json", ".yaml", ".yml")):
                index.setdefault(name, os.path.join(dirpath, name))
    return index


def find_pointers(path: str) -> list[dict]:
    found: list[dict] = []
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            text = fh.read()
    except OSError:
        return found

    in_fence = False
    for lineno, line in enumerate(text.split("\n"), 1):
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        # 以点开头的不是路径而是扩展名（`.excalidraw.md`），排除掉避免误报
        targets = [t for t in PATH_IN_TICK.findall(line) if not t.startswith(".")]
        if not targets:
            continue
        # `pointer` 区分“这句话在指路”与“只是提到了一个文件名”。
        #
        # 为什么两者都要收：以前只收含“见 / 参见”这类动词的行，于是
        # 「图标（`references/icons.md`）**遵循**同一条纪律」这种句子被整行跳过 ——
        # 而那个文件根本不存在。**假阴性**比误报危险：误报会被人忽略，假阴性没人看得见。
        is_pointer = bool(re.search(POINTER_VERBS, line))
        for target in targets:
            found.append({"file": path, "line": lineno, "target": target,
                          "pointer": is_pointer, "sentence": line.strip()})
    return found


def _resolve(target: str, doc: str, root: str, basename_index: dict[str, str]) -> str | None:
    for cand in (os.path.join(root, target),
                 os.path.join(os.path.dirname(doc), target)):
        if os.path.isfile(cand):
            return os.path.relpath(cand, root)
    return basename_index.get(os.path.basename(target))


def run(docs: list[str], root: str) -> list[dict]:
    basename_index = _build_basename_index(root)
    out = []
    for doc in docs:
        for ptr in find_pointers(doc):
            resolved = _resolve(ptr["target"], doc, root, basename_index)
            out.append({**ptr,
                        "target_exists": resolved is not None,
                        "resolved": resolved})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="列出指针语句供逐词核对（只找与解析，不下语义判断）")
    ap.add_argument("targets", nargs="*", default=["skills"], help="要扫的路径")
    ap.add_argument("--root", default=".", help="解析目标路径的基准目录")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    targets = args.targets or ["skills"]
    if not any(os.path.exists(t) for t in targets):
        print(f"路径无效：{targets}", file=sys.stderr)
        return 2

    ptrs = run(list(iter_docs(targets)), args.root)
    # 分两级，因为这两类**确定性不同**：
    #   broken   —— 含"见 / 参见"这类动词，解析不到：这句话在明确指路，路是断的。**阻塞。**
    #   suspect  —— 只是提到一个长得像路径的词，解析不到：可能只是举了个例子（"假如有
    #               决策树图就放 references/decision-tree.md"），也可能指向仓库外的东西
    #               （vault 里的 `better-export-pdf/data.json`）。**列出但不阻塞。**
    # 全都不阻塞会让真正的悬空引用被淹掉；全都阻塞会制造误报，而误报会训练人忽略整个检查
    # （前作 lint 全 warn 没人看就是这个失败模式）。
    broken = [p for p in ptrs if not p["target_exists"] and p.get("pointer")]
    suspect = [p for p in ptrs if not p["target_exists"] and not p.get("pointer")]

    if args.json:
        print(json.dumps({"pointer_count": len(ptrs), "broken_count": len(broken),
                          "suspect_count": len(suspect), "pointers": ptrs},
                         ensure_ascii=False, indent=2))
        return 1 if broken else 0

    if not ptrs:
        print("✓ 没有找到指针语句")
        return 0

    for p in broken:
        print(f"  ✗ {p['file']}:{p['line']} → {p['target']} 不存在")
    if broken:
        print(f"\n  ✗ {len(broken)} 处悬空引用（这句话在指路，但路是断的）")

    if suspect:
        print(f"\n  ⚠ 另有 {len(suspect)} 处「看起来像路径但解析不到」，不阻塞。逐条看是不是真悬空：")
        for p in suspect:
            print(f"      {p['file']}:{p['line']} → {p['target']}")

    print(f"指针语句（{len(ptrs)} 条）—— 目标是“哪些文件在说这事定义在别处”\n")
    for p in ptrs:
        if not p.get("pointer"):
            continue          # 只在提到文件名、没在指路的行不列进来（上面已单独报过）
        rel = os.path.relpath(p["file"], args.root)
        mark = "✓" if p["target_exists"] else "✗ 目标找不到"
        loc = p.get("resolved") or p["target"]
        print(f"  {rel}:{p['line']}")
        print(f"      → {loc}   {mark}")

    if broken:
        return 1

    print("\n✓ 所有指针的目标都存在")
    print("  ⚠ 目标存在 **不等于** 内容搬过去了 —— 改动指针时请逐词核对目标里")
    print("    真的接住了那些条款（这条留给人和 skill-builder 的检查项）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
