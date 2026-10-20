#!/usr/bin/env python3
"""核验制作链路有没有跳步：上一关没过，不许出现下一关的产物。

为什么要有它
------------
"先做样页再铺全套"写进文档后仍然会被跳过：铺 28 页比重做 3 页"看起来更有进度"。
光靠自觉时，最常见的三种实际形态是：样页没确认就铺开、图位还会变就把 brief 交给用户出图、
图没回填就导出。这三种都能从**目录产物**看出来，不需要猜作者的想法。

做法
----
读 `design.md` 的 `## 阶段闸门` 表（人写、可读），再核对每关的产物是否真的存在：

    | # | 闸门 | 状态 | 日期 | 证据 | 用户确认 |
    | G1 | 范围与内容 | 通过 | 2026-10-20 | design.md §1 | 本次评审会 |
    | G3 | 样页 | 进行中 | | preview/hero-v3 | 待确认 |

状态只认三种：`通过` / `进行中` / `未开始`（也接受 passed / in-progress / pending）。
脚本只核对，不改文件：闸门状态由作者写进设计记录，这样状态表和设计记录不会分家。

用法
----
    python3 scripts/gate_check.py /path/to/v2-2026-10-20-风格/
    python3 scripts/gate_check.py /path/to/v2-.../ --json checks/gates.json
    python3 scripts/gate_check.py /path/to/v2-.../ --next     # 只报下一关要交什么

退出码：0 一致；1 跳步或证据缺失；2 没有闸门表（还没开始按链路走）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

GATES = [
    ("G1", "范围与内容"),
    ("G2", "风格"),
    ("G3", "样页"),
    ("G4", "配图交接"),
    ("G5", "全套"),
    ("G6", "审稿与回填"),
    ("G7", "导出"),
]
PASS = {"通过", "passed", "pass", "done", "✓", "✅"}
DOING = {"进行中", "in-progress", "in progress", "wip", "doing"}
TODO = {"未开始", "pending", "todo", "waiting", ""}
ROW = re.compile(r"^\|\s*(G[1-7])\s*\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|\s*$")


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def section(text: str, heading: str) -> str:
    """取某个 `## ` 小节的正文；找不到返回空串。"""
    lines = text.splitlines()
    out, grab = [], False
    for line in lines:
        if line.startswith("## "):
            if grab:
                break
            grab = heading.strip("# ").strip() in line
            continue
        if grab:
            out.append(line)
    return "\n".join(out).strip()


def has_content(block: str) -> bool:
    body = re.sub(r"^[\s|>\-:]+", "", block.strip())
    return len(re.sub(r"[\s|\-:]", "", body)) >= 3


def slides(source: Path) -> int:
    return len(re.findall(r'class="[^"]*\bslide\b', read(source))) if source.exists() else 0


def evidence_problems(root: Path, gate: str) -> list[str]:
    """逐关核对产物；返回缺失项描述。"""
    md = read(root / "design.md")
    images_dir = root / "assets" / "images"
    checks = root / "checks"
    preview = root / "preview"
    plan = root / "image-plan.json"
    out: list[str] = []

    if gate == "G1":
        if not has_content(section(md, "视觉命题")):
            out.append("design.md 的「视觉命题」还没写（观众与场景、事实来源）")
        if not has_content(section(md, "视觉分镜")):
            out.append("design.md 的「视觉分镜」还没写（每页一个问题）")

    elif gate == "G2":
        if not has_content(section(md, "参考拆解")):
            out.append("design.md 的「参考拆解」还没写")
        if "用户依据" not in md:
            out.append("design.md 缺「用户依据」一行（用户看到的是哪张页面/哪种样张）")
        version = re.match(r"^v(\d+)-", root.name)
        if version and int(version.group(1)) >= 2 and not has_content(section(md, "与上一版的差异")):
            out.append("v2 起要先写「与上一版的差异」")
        refs = root / "refs"
        if not (refs.is_dir() and any(p.is_file() for p in refs.iterdir())):
            out.append("refs/ 没有参考截图；A 档证据需要同媒介页面截图，B 档需要样张截图")

    elif gate == "G3":
        shots = sorted(preview.glob("**/*.png")) if preview.is_dir() else []
        if len(shots) < 3:
            out.append(f"preview/ 只有 {len(shots)} 张实际渲染截图，样页至少 3 张")
        # 审稿记录本身以 `## YYYY-MM-DD · hero vN` 为小标题，所以按全文扫日期标题
        rounds = re.findall(r"^#{2,3}\s*\d{4}-\d{2}-\d{2}", md, re.M)
        if len(rounds) < 2:
            out.append(f"design.md 只有 {len(rounds)} 轮带日期的审稿记录，样页要两轮")

    elif gate == "G4":
        if not plan.exists():
            out.append("缺 image-plan.json（图位与提示词计划）")
        else:
            try:
                data = json.loads(plan.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                out.append(f"image-plan.json 解析失败：{exc}")
            else:
                items = data.get("images") or []
                for item in items:
                    px = item.get("target_px")
                    if not (isinstance(px, list) and len(px) == 2 and all(isinstance(v, int) and v > 0 for v in px)):
                        out.append(f"image-plan.json 的 {item.get('id')} 缺合法 target_px")
                    if not (item.get("prompt") or "").strip():
                        out.append(f"image-plan.json 的 {item.get('id')} 缺提示词")
        if not (root / "image-brief.md").exists():
            out.append("缺 image-brief.md（用户要按它生成）")

    elif gate == "G5":
        count = slides(root / "source.html")
        if count == 0:
            out.append("source.html 还没有页面")
        elif count < 8:
            out.append(f"source.html 只有 {count} 页，全套还没铺开")
        if not (checks.is_dir() and any(checks.glob("*.json"))):
            out.append("checks/ 还没有任何检查报告（rhythm / type / web_check 至少跑一次）")

    elif gate == "G6":
        plan_exists = plan.exists()
        filled = [p for p in images_dir.glob("*") if p.is_file()] if images_dir.is_dir() else []
        if plan_exists:
            try:
                items = json.loads(plan.read_text(encoding="utf-8")).get("images") or []
            except json.JSONDecodeError:
                items = []
            if items and not filled:
                out.append("assets/images/ 还是空的：图未回填，G6 不能过（用户确认不要图时另记）")
            elif items and len(filled) < len(items):
                out.append(f"assets/images/ 只有 {len(filled)}/{len(items)} 张图")
        if not (checks.is_dir() and any(checks.glob("*check*.json"))):
            out.append("checks/ 缺 web_check 报告，逐页几何还没验")

    elif gate == "G7":
        if not any((root / name).exists() for name in ("deck.pdf", "deck.pptx", "deck.mp4")):
            out.append("还没有导出文件（deck.pdf / deck.pptx / deck.mp4）")

    return out


def parse(md: str) -> dict[str, dict]:
    block = section(md, "阶段闸门")
    rows: dict[str, dict] = {}
    for line in block.splitlines():
        m = ROW.match(line)
        if not m:
            continue
        gid, name, status, date, evidence, confirm = (m.group(i).strip() for i in range(1, 7))
        rows[gid] = {"name": name, "status": status, "date": date,
                     "evidence": evidence, "confirm": confirm}
    return rows


def status_of(raw: str) -> str:
    key = (raw or "").strip().lower()
    if key in PASS or (raw or "").strip() in PASS:
        return "passed"
    if key in DOING or (raw or "").strip() in DOING:
        return "doing"
    return "todo"


def main() -> int:
    ap = argparse.ArgumentParser(description="核验制作链路有没有跳步")
    ap.add_argument("directory", help="版本目录（含 design.md）")
    ap.add_argument("--json", dest="json_path", help="把结果写到这个 JSON 文件")
    ap.add_argument("--next", action="store_true", help="只报下一关要交什么")
    args = ap.parse_args()

    root = Path(args.directory).resolve()
    if not (root / "design.md").exists():
        print(f"✗ {root.name}：没有 design.md，先按链路从 G1 开始")
        return 2
    rows = parse(read(root / "design.md"))
    if not rows:
        print(f"✗ {root.name}：design.md 里没有「## 阶段闸门」表")
        print("  六个状态列照抄：| # | 闸门 | 状态 | 日期 | 证据 | 用户确认 |")
        return 2

    statuses = {gid: status_of(rows.get(gid, {}).get("status", "")) for gid, _ in GATES}
    problems: list[str] = []

    # 顺序：出现第一个未通过，就不能有更靠后的"通过"或"进行中"
    first_open = next((gid for gid, _ in GATES if statuses[gid] != "passed"), None)
    if first_open:
        later = [gid for gid, _ in GATES if gid > first_open and statuses[gid] != "todo"]
        for gid in later:
            problems.append(f"{gid} 标成「{rows.get(gid, {}).get('status', '')}」，但 {first_open} 还没通过——跳步")

    # 证据：标了通过就核产物
    for gid, name in GATES:
        if statuses[gid] != "passed":
            continue
        for item in evidence_problems(root, gid):
            problems.append(f"{gid} {name} 标通过，但{item}")

    current = first_open or "G7"
    label = dict(GATES)[current]
    if args.next:
        print(f"{current} {label}")
        for item in evidence_problems(root, current):
            print(f"  缺：{item}")
        return 0 if not problems else 1

    print(f"阶段闸门：{current} {label}（{rows.get(current, {}).get('status', '未开始') or '未开始'}）")
    done = [f"{gid} {name}" for gid, name in GATES if statuses[gid] == "passed"]
    print("已通过：" + ("、".join(done) if done else "无"))
    if not problems:
        print("✓ 顺序与证据一致")
    else:
        print("✗ 有问题：")
        for item in problems:
            print(f"  · {item}")
    missing = evidence_problems(root, current)
    if missing:
        print(f"下一关（{current} {label}）还缺：")
        for item in missing:
            print(f"  - {item}")

    report = {"directory": str(root), "current": current, "currentName": label,
              "statuses": statuses, "problems": problems, "nextMissing": missing}
    if args.json_path:
        target = Path(args.json_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"报告：{target}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
