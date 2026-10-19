#!/usr/bin/env python3
"""按模块和规格声明顺序展开数据移动，保留原始字段与过程边界。

描述缺省时才按 op 与移动类型推导；已有 description 一律原样使用。
`--order crud` 只在模块内按送审表的增删改查惯例排过程顺序，移动与 CFP 不变。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import operation_types as ops  # noqa: E402  # pyright: ignore[reportMissingImports]
import spec as spec_module  # noqa: E402  # pyright: ignore[reportMissingImports]
import style  # noqa: E402  # pyright: ignore[reportMissingImports]


@dataclass
class Row:
    l2: str
    l3: str
    user: str
    event: str
    func: str
    desc: str
    move: str
    group: str
    attrs: str
    seq: list[str] = field(default_factory=list)
    seq_index: int = 0
    fp: int = 0

    process_id: str = ""
    status: str = "unverified"
    source: str = ""
    object: str = ""
    repeat_reason: str = ""
    op: str = ""
    op_note: str = ""
    evidence: str = ""
    read_issues: list[str] = field(default_factory=list)
    excel_row: int = 0
    declared_cfp: object = None

    @property
    def is_process_head(self) -> bool:
        return self.seq_index == 0


@dataclass
class BuildResult:
    rows: list[Row]

    @property
    def total_cfp(self) -> int:
        return sum(row.fp for row in self.rows if row.is_process_head)

    @property
    def process_count(self) -> int:
        return sum(1 for row in self.rows if row.is_process_head)


def ordered(processes: list[dict], order: str) -> list[dict]:
    if order == "spec":
        return processes
    return sorted(processes, key=lambda process: ops.order_key(ops.op_of(process)))


def build(spec: dict, order: str = "spec") -> BuildResult:
    rows: list[Row] = []
    for l2, l3, procs in spec_module.group_by_module(spec):
        for proc in ordered(procs, order):
            moves = spec_module.moves_for(proc)
            op = proc.get("op", "")
            for index, movement in enumerate(proc['movements']):
                rows.append(Row(
                    l2=l2, l3=l3, user=proc['user'], event=proc['trigger'], func=proc['name'],
                    desc=movement.get('description') or style.describe(movement['type'], movement['object'], op),
                    move=movement['type'], group=movement['group'],
                    attrs=','.join(movement['attributes']), seq=moves, seq_index=index,
                    fp=len(moves) if index == 0 else 0, process_id=proc['id'], status=proc['status'],
                    source=movement.get('source') or proc.get('source', ''),
                    object=movement['object'], repeat_reason=movement.get('repeat_reason', ''),
                    op=op, op_note=proc.get('op_note', ''),
                    evidence=','.join(proc.get('evidence', [])),
                ))
    return BuildResult(rows=rows)


def module_blocks(rows: list[Row], key) -> list[tuple[int, int]]:
    """把行按 key 切连续区间，返回 0 基的 [起, 止] 闭区间。

    合并单元格和连续性检查都用这个 —— 同一 key 必须连续出现，否则渲染出来
    会看到同一个模块的表头散在表格两头。
    """
    if not rows:
        return []
    blocks: list[tuple[int, int]] = []
    start = 0
    previous = key(rows[0])
    for index in range(1, len(rows)):
        current = key(rows[index])
        if current != previous:
            blocks.append((start, index - 1))
            start = index
            previous = current
    blocks.append((start, len(rows) - 1))
    return blocks
