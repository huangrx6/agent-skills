#!/usr/bin/env python3
"""输出层：时间转换、紧凑字段白名单、表格渲染。

**默认紧凑**，`--full` 才出原始 JSON。理由：调用方要的是「够不够判断下一步」，不是完整
响应体 —— 一个工作项的原始 JSON 里有 url / entity_properties / avatar 这些噪声，而真正
要看的编号、标题、状态、负责人在里面只占几行。

字段名**从官方响应示例里抄**（`api_data.json` 的 `success.examples`），不靠猜。
"""

from __future__ import annotations

import datetime
import os
import sys
import unicodedata
from typing import Any

# kind → ((字段路径, 表头), ...)。字段路径支持点号取嵌套，如 state.name。
WORKITEM = (
    ("identifier", "编号"),
    ("title", "标题"),
    ("type", "类型"),
    ("state.name", "状态"),
    ("priority.name", "优先级"),
    ("assignee.display_name", "负责人"),
    ("sprint.name", "迭代"),
    ("project.name", "项目"),
    ("end_at", "截止"),
    ("html_url", "链接"),
)

# 状态字典：`type` 是语义值（pending/in_progress/completed），判断「完没完」靠它 ——
# 实测里「已修复 / 已发布」都叫 completed 语义，光看中文名看不出来。
STATE = (
    ("name", "状态"),
    ("type", "语义"),
    ("id", "ID"),
)

PROJECT = (
    ("identifier", "标识"),
    ("name", "名称"),
    ("type", "类型"),
    ("state.name", "状态"),
    ("assignee.display_name", "负责人"),
    ("start_at", "开始"),
    ("end_at", "结束"),
    ("id", "ID"),
)

SPRINT = (
    ("name", "迭代"),
    ("status", "状态"),
    ("start_at", "开始"),
    ("end_at", "结束"),
    ("id", "ID"),
)

USER = (
    ("display_name", "显示名"),
    ("name", "用户名"),
    ("email", "邮箱"),
    ("id", "ID"),
)

SIMPLE = (
    ("name", "名称"),
    ("id", "ID"),
)

SCHEMAS: dict[str, tuple[tuple[str, str], ...]] = {
    "workitem": WORKITEM,
    "project": PROJECT,
    "sprint": SPRINT,
    "user": USER,
    "state": STATE,
    "simple": SIMPLE,
}

# 系统类型的 id → 中文名（官方文档列的 9 种）。
TYPE_NAMES = {
    "epic": "史诗", "feature": "特性", "story": "用户故事", "stage": "阶段",
    "milestone": "里程碑", "requirement": "需求", "task": "任务", "bug": "缺陷", "issue": "事务",
}


class TimeParseError(Exception):
    """时间参数看不懂。"""


def _as_int(value: object, default: int = 0) -> int:
    """宽松取整：时间参数来自命令行，不能因为一个字段坏了就整个崩。"""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def parse_time(text: str) -> int:
    """把用户写的时间变成 10 位时间戳（官方全用秒级时间戳）。

    接受 `2026-09-20`、`2026-09-20 18:30`、`2026/09/20`，也接受已经是时间戳的数字。
    只写日期时按**当天 00:00（本地时区）**算 —— 不写 23:59，因为"截止到某天"的语义
    交给使用方决定，这里只做字面转换。
    """
    raw = str(text or "").strip()
    if not raw:
        raise TimeParseError("空的时间")
    if raw.isdigit() and len(raw) >= 9:
        return _as_int(raw)
    normalized = raw.replace("/", "-").replace("年", "-").replace("月", "-").replace("日", "")
    formats = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y-%m", "%m-%d")
    for fmt in formats:
        try:
            parsed = datetime.datetime.strptime(normalized.strip(), fmt)
        except ValueError:
            continue
        if fmt == "%m-%d":
            parsed = parsed.replace(year=datetime.date.today().year)
        return _as_int(parsed.timestamp())
    raise TimeParseError(
        f"看不懂的时间 {text!r}；可用 2026-09-20 / 2026-09-20 18:30 / 10 位时间戳"
    )


def show_time(value: Any) -> str:
    """时间戳 → 本地时间字符串；空了给空串（不是 None）。"""
    if value in (None, "", 0):
        return ""
    stamp = _as_int(value, -1)
    if stamp < 0:
        return str(value)
    return datetime.datetime.fromtimestamp(stamp).strftime("%Y-%m-%d %H:%M")


def dig(obj: Any, path: str) -> Any:
    """按点号取嵌套值；中间断了返回 None。"""
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def type_label(value: Any) -> str:
    """工作项类型：系统类型翻成中文，自定义类型原样返回。"""
    if value in (None, ""):
        return ""
    raw = str(value)
    return f"{TYPE_NAMES.get(raw, raw)}" if raw in TYPE_NAMES else raw


def compact(kind: str, obj: dict[str, Any]) -> dict[str, Any]:
    """按白名单裁剪一条记录。"""
    schema = SCHEMAS.get(kind, SIMPLE)
    out: dict[str, Any] = {}
    for path, title in schema:
        value = dig(obj, path)
        if path in ("start_at", "end_at", "completed_at", "created_at"):
            value = show_time(value)
        elif path == "type":
            value = type_label(value)
        if value not in (None, "", [], {}):
            out[title] = value
    return out


def rows(kind: str, values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """批量裁剪，**列顺序按 schema 而不是「首次出现」**。

    实测撞到过：第一条记录恰好没有迭代时，「迭代」「负责人」两列会跑到表尾，
    与 schema 顺序不一致 —— 同一张表在不同数据下长得不一样，看着很难受。
    """
    schema = SCHEMAS.get(kind, SIMPLE)
    compacted = [compact(kind, value) for value in values]
    columns = [title for _path, title in schema
               if any(title in record for record in compacted)]
    # 每行都铺成**同一套列**（缺的填空串）：render 是按「首次出现」收集列的，
    # 只重排每行的键还不够 —— 第一行恰好缺迭代时，迭代还是会被挤到表尾。
    return [{column: record.get(column, "") for column in columns} for record in compacted]


def _width(text: str) -> int:
    """显示宽度：CJK 全角算 2，其他算 1。"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in str(text))


def _pad(text: str, width: int) -> str:
    return str(text) + " " * max(0, width - _width(text))


def render(records: list[dict[str, Any]], empty: str = "（没有匹配的条目）") -> str:
    """把一堆字典渲染成对齐的表格。列顺序取并集，按首次出现排。"""
    if not records:
        return empty
    columns: list[str] = []
    for record in records:
        for key in record:
            if key not in columns:
                columns.append(key)
    cells = [[str(r.get(c, "")) for c in columns] for r in records]
    widths = [_width(c) for c in columns]
    for row in cells:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], _width(cell))
    lines = ["  ".join(_pad(c, widths[i]) for i, c in enumerate(columns)).rstrip()]
    lines.append("  ".join("-" * widths[i] for i in range(len(columns))))
    for row in cells:
        lines.append("  ".join(_pad(cell, widths[i]) for i, cell in enumerate(row)).rstrip())
    return "\n".join(lines)


def print_records(records: list[dict[str, Any]], full: bool = False,
                  raw: list[dict[str, Any]] | None = None, kind: str = "simple") -> None:
    """统一的输出入口：默认表格，`full=True` 出原始 JSON。"""
    import json as _json
    if full:
        payload = raw if raw is not None else records
        print(_json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(render(records))


def echo_stderr(message: str) -> None:
    print(message, file=sys.stderr)


def terminal_width(default: int = 100) -> int:
    """终端宽度（拿不到就给默认值，不报错）。"""
    try:
        return os.get_terminal_size().columns
    except OSError:
        return default
