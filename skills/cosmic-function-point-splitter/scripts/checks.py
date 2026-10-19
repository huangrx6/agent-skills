#!/usr/bin/env python3
"""结构检查（硬错误）与一致性提示（不阻塞）。

分界线：
  - **硬错误**：表内自相矛盾，生成或回读会失真（缺 E、缺 W/X、CFP 与行数不符、
    非法移动、过程区间不连续……）。
  - **提示**：可能是问题，也可能是有依据的偏离（op 与移动不一致、排序不符合
    送审惯例、旧模板句、英文残留、描述完全重复……）。提示不否认真实需求，
    也不自动改数据；`--strict` 时才当作失败。
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import operation_types as ops  # noqa: E402  # pyright: ignore[reportMissingImports]
import style  # noqa: E402  # pyright: ignore[reportMissingImports]
from builder import Row  # noqa: E402  # pyright: ignore[reportMissingImports]


def process_blocks(rows: list[Row]) -> list[list[Row]]:
    """按稳定过程编号（旧表退化到模块与过程名）切块，不能按 E 切块。"""
    blocks: list[list[Row]] = []
    previous = None
    for row in rows:
        key = row.process_id or (row.l2, row.l3, row.func)
        if not blocks or key != previous:
            blocks.append([])
        blocks[-1].append(row)
        previous = key
    return blocks


def structural_issues(rows: list[Row]) -> list[str]:
    issues: list[str] = []
    seen_ids = set()
    for block in process_blocks(rows):
        first = block[0]
        key = first.process_id or (first.l2, first.l3, first.func)
        if key in seen_ids:
            issues.append(f"功能过程区间不连续：{first.func}")
        seen_ids.add(key)
        moves = [r.move for r in block]
        if first.seq and moves != first.seq:
            issues.append(f"序列与规格不一致 {first.func}：{moves} != {first.seq}")
        if moves[0] != 'E':
            issues.append(f"子过程未以 E 起 {first.func}：{moves}")
        if not any(m in ('W', 'X') for m in moves):
            issues.append(f"功能过程缺少 W 或 X {first.func}")
        if len(block) < 2:
            issues.append(f"功能过程只有单个子过程 {first.func}")
        if len(block) != first.fp:
            issues.append(f"CFP 与行数不符 {first.func}：声明 {first.fp} 实际 {len(block)}")
        seen_movements = set()
        for row in block:
            issues.extend(row.read_issues)
            if ((row.func, row.l2, row.l3, row.user, row.event, row.status)
                    != (first.func, first.l2, first.l3, first.user, first.event, first.status)):
                issues.append(f"同一过程的名称、模块、功能用户、触发事件或核实状态不一致 第 {row.excel_row} 行：{first.func}")
            if row.move not in ('E', 'R', 'W', 'X'):
                issues.append(f"非法数据移动类型 第 {row.excel_row} 行 {row.func}：{row.move!r}")
            if not row.func or not row.desc or not row.group:
                issues.append(f"缺少功能过程、描述或数据组 第 {row.excel_row} 行")
            missing = [label for key, label in (('l2', '二级模块'), ('l3', '三级模块'),
                       ('user', '功能用户'), ('event', '触发事件'), ('object', '兴趣对象'))
                       if not getattr(row, key).strip()]
            if missing:
                issues.append(f"缺少核心字段 第 {row.excel_row} 行：{'、'.join(missing)}")
            fields = row.attrs.replace('，', ',').split(',')
            if any(not f.strip() for f in fields):
                issues.append(f"属性有空项 {row.func}/{row.move}")
            if len({f.strip() for f in fields}) != len(fields):
                issues.append(f"属性行内重复 {row.func}/{row.move}")
            # 同一兴趣对象同一类型的再次移动需要功能需求理由。
            if row.object:
                signature = (row.move, row.object)
                if signature in seen_movements and not row.repeat_reason:
                    issues.append(f"重复移动需需求依据 {row.func}/{row.move}/{row.object}：填写 repeat_reason")
                seen_movements.add(signature)
    return issues


def op_hints(rows: list[Row]) -> list[str]:
    """声明了 op 才对照词表；未声明时不猜。"""
    hints: list[str] = []
    for block in process_blocks(rows):
        first = block[0]
        if not first.op:
            continue
        if first.op not in ops.OPS:
            hints.append(f"未知操作标签 {first.op}：{first.func}，请核对操作词表")
            continue
        expected = ops.default_moves(first.op)
        actual = tuple(row.move for row in block)
        if expected and actual != expected and not first.op_note:
            hints.append(
                f"op={first.op} 的默认序列是 {'→'.join(expected)}，实际是 {'→'.join(actual)}；"
                f"有依据就在规格里写 op_note {first.func}")
        if ops.OPS[first.op].trigger == "timer" and "定时" not in first.user and "系统" not in first.user:
            hints.append(f"{first.op} 通常由定时任务触发，当前功能用户是「{first.user}」 {first.func}")
    return hints


def order_hints(rows: list[Row]) -> list[str]:
    """模块内按送审惯例检查类别顺序；同类内顺序不动。"""
    hints: list[str] = []
    for _start, _end in _module_ranges(rows):
        heads = [row for row in rows[_start:_end + 1] if row.is_process_head]
        keys = [(ops.order_key(ops.op_of({"name": row.func, "op": row.op})), row) for row in heads]
        for (left_key, left), (right_key, right) in zip(keys, keys[1:], strict=False):
            if left_key > right_key:
                hints.append(
                    f"模块「{left.l3}」的过程顺序不符合送审惯例：{left.func} 在 {right.func} 之前；"
                    "build --order crud 可重排（只移动整块，不改数据）")
                break
    return hints


def _module_ranges(rows: list[Row]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    start = 0
    for index in range(1, len(rows)):
        if (rows[index].l2, rows[index].l3) != (rows[start].l2, rows[start].l3):
            ranges.append((start, index - 1))
            start = index
    if rows:
        ranges.append((start, len(rows) - 1))
    return ranges


def hints(rows: list[Row], glossary: dict | None = None) -> list[str]:
    glossary = glossary or style.load_glossary()
    return op_hints(rows) + order_hints(rows) + style.naming_hints(rows, glossary)


def check(rows: list[Row]) -> list[str]:
    """结构性硬错误；空列表仅表示结构通过，不代表来源已核实。"""
    return structural_issues(rows)


def summary(rows: list[Row]) -> dict:
    """统计过程、移动与分别标记的规模。"""
    heads = [row for row in rows if row.is_process_head]
    return {
        "rows": len(rows),
        "processes": len(heads),
        "cfp": sum(len(b) for b in process_blocks(rows)),
        "confirmed_cfp": sum(len(b) for b in process_blocks(rows) if b[0].status == "confirmed"),
        "unverified_cfp": sum(len(b) for b in process_blocks(rows) if b[0].status != "confirmed"),
        "unverified_processes": sum(1 for row in heads if row.status != "confirmed"),
        "moves": dict(Counter(row.move for row in rows)),
    }
