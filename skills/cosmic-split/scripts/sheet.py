#!/usr/bin/env python3
"""送审表的布局探测与写出。

上一版把列布局写死在文档里（A=项目名称、B=一级模块留空……），原因只是"当时手上的表长这样"。
真实模板的差异比想象的大，实测遇到过的三种：

  12 列标准表   一级模块 / 二级模块 / 三级模块 / 功能用户 / 触发事件 / 功能过程 / 子过程描述 /
                数据移动类型 / 数据组 / 数据属性 / 复用度 / CFP，表头在第 1 行
  4 列极简表    二级模块 / 三级模块 / 功能过程 / 标识 —— 没有用户、数据组、CFP，
                移动类型列叫「标识」
  多 sheet 梳理表  前 3 行是标题与说明，表头在第 4 行；列名是「一级业务域 / 二级功能模块 /
                二级功能模块 / 子过程」；工作簿里还有 模块总览、功能过程清单 等辅助表

所以这里先探测：扫描前若干行找表头、按别名匹配列、再用数据值确认候选列（只对含糊的「标识」列校验样例值）。探测不到的必填字段在写出时追加到末尾并明确报告，不静默丢数据。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil
from pathlib import Path
from unicodedata import combining, east_asian_width

from builder import Row, module_blocks

# 逻辑字段 → 表头可能的写法。顺序即优先级，首次命中即停。
# 「一级业务域」「二级功能模块」这类是实测见过的真实写法，不是同义词堆砌。
HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "l1": ("一级模块", "一级业务域", "一级功能模块", "项目名称", "系统名称", "业务域"),
    "l2": ("二级模块", "二级功能模块", "二级业务域", "模块名称", "子系统", "功能模块"),
    "l3": ("三级模块", "三级功能模块", "功能模块"),
    "user": ("功能用户", "功能使用者", "发起者", "用户"),
    "event": ("触发事件", "发起事件", "触发动作", "事件"),
    "func": ("功能过程名", "功能过程", "功能项"),
    "desc": ("子过程描述", "子过程名称", "子过程", "数据移动描述"),
    "move": ("数据移动类型", "数据移动", "移动类型", "移动标识", "标识"),
    "group": ("数据组", "数据组名"),
    "attrs": ("数据属性", "数据属性名", "属性"),
    "reuse": ("复用度", "复用级别", "复用"),
    "cfp": ("功能点", "功能点数", "功能点计数", "CFP"),
}

TRACE_LABELS = {"process_id": "过程编号", "status": "核实状态", "source": "需求依据",
                "object": "兴趣对象", "repeat_reason": "重复移动理由",
                "op": "操作类型", "op_note": "操作依据", "evidence": "接口证据"}
HEADER_ALIASES.update({key: (label,) for key, label in TRACE_LABELS.items()})

HEADER_LABELS = {
    "l1": "一级模块", "l2": "二级模块", "l3": "三级模块", "user": "功能用户",
    "event": "触发事件", "func": "功能过程", "desc": "子过程描述",
    "move": "数据移动类型", "group": "数据组", "attrs": "数据属性",
    "reuse": "复用度", "cfp": "CFP",
}

HEADER_LABELS.update(TRACE_LABELS)

# 写出时必须有的字段：没有这些列就没地方放数据。
# 「复用度」不在内：它是一个恒为 1 的列，模板没有时不追加，少一列常量比多一列噪声好。
REQUIRED_FOR_WRITE = (
    "l1", "l2", "l3", "user", "event", "func", "desc", "move", "group", "attrs", "cfp",
)
OPTIONAL_FIELDS = ("reuse",)

# 必填字段的优先顺序，追加缺失列时按这个顺序排。
FIELD_ORDER = (
    "l1", "l2", "l3", "user", "event", "func", "desc", "move",
    "group", "attrs", "reuse", "cfp",
)

# 默认布局：12 列版本。
DEFAULT_LAYOUT: dict[str, int] = {
    "l1": 1, "l2": 2, "l3": 3, "user": 4, "event": 5, "func": 6,
    "desc": 7, "move": 8, "group": 9, "attrs": 10, "reuse": 11, "cfp": 12,
}

DEFAULT_WIDTHS = {
    "l1": 16.0, "l2": 24.0, "l3": 25.0, "user": 30.0, "event": 29.0, "func": 26.0,
    "desc": 40.0, "move": 14.0, "group": 38.0, "attrs": 80.0, "reuse": 8.0, "cfp": 6.0,
}

HEADER_FILL = "FFC4D79B"
DEFAULT_FONT = "宋体"
FONT_SIZE = 11
HEADER_SEARCH_ROWS = 8
MOVE_VALUES = ("E", "R", "W", "X")

# 合并策略：这些逻辑字段按什么区间合并。
MERGE_WHOLE_TABLE = ("l1",)
MERGE_BY_MODULE = ("l2", "l3")
MERGE_BY_PROCESS = ("event", "func", "reuse", "cfp", "op", "op_note", "evidence")


@dataclass
class Template:
    """目标表的布局与观感。source 为空表示用默认 12 列布局。"""

    source: Path | None = None
    source_width: int = 0
    sheet_name: str = "Sheet1"
    header_row: int = 1
    l1_value: str = ""
    layout: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_LAYOUT))
    widths: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WIDTHS))
    header_fill: str = HEADER_FILL
    font: str = DEFAULT_FONT
    font_size: int = FONT_SIZE
    cfp_on_first_row_only: bool = True
    merge_whole_table: tuple[str, ...] = MERGE_WHOLE_TABLE
    merge_by_module: tuple[str, ...] = MERGE_BY_MODULE
    merge_by_process: tuple[str, ...] = MERGE_BY_PROCESS
    appended: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def freeze(self) -> str:
        return f"A{self.header_row + 1}"


def _normalise(text: object) -> str:
    return "".join(str(text).split()).lower()


def _match_columns(headers: dict[int, object]) -> dict[str, int]:
    """把一行表头映射到逻辑字段。返回 列号 → 逻辑字段 的反向表由调用方整理。"""
    normalised = {column: _normalise(value) for column, value in headers.items()}
    layout: dict[str, int] = {}
    taken: set[int] = set()
    for logical, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            target = _normalise(alias)
            for column, header in sorted(normalised.items()):
                if column in taken or not header:
                    continue
                if header == target:
                    layout[logical] = column
                    taken.add(column)
                    break
            if logical in layout:
                break
        if logical in layout:
            continue
        for alias in aliases:
            target = _normalise(alias)
            for column, header in sorted(normalised.items()):
                if column in taken or not header:
                    continue
                if target in header:
                    layout[logical] = column
                    taken.add(column)
                    break
            if logical in layout:
                break
    return layout


def _looks_like_move_column(worksheet, column: int, header_row: int) -> bool:
    """含糊列名有数据时核对移动值；空模板不能因没有样例被拒绝。

    别名匹配可能撞上同名的无关列（「标识」这类词太通用），
    用数据值确认一次比加更多别名可靠。
    """
    seen = 0
    hits = 0
    for row in range(header_row + 1, min(worksheet.max_row, header_row + 60) + 1):
        value = worksheet.cell(row=row, column=column).value
        if value in (None, ""):
            continue
        seen += 1
        if str(value).strip().upper() in MOVE_VALUES:
            hits += 1
    return seen == 0 or hits >= max(1, seen * 0.6)


def _score_sheet(worksheet) -> tuple[int, int, dict[str, int]]:
    """给一个 sheet 打分：找到的表头行 + 匹配到的字段数。返回 (字段数, 表头行, 布局)。"""
    best = (0, 1, {})
    for header_row in range(1, min(HEADER_SEARCH_ROWS, worksheet.max_row) + 1):
        headers = {
            column: worksheet.cell(row=header_row, column=column).value
            for column in range(1, worksheet.max_column + 1)
        }
        layout = _match_columns(headers)
        move_column = layout.get("move")
        if (move_column and _normalise(headers[move_column]) == "标识"
                and not _looks_like_move_column(worksheet, move_column, header_row)):
            layout.pop("move")
        if len(layout) > best[0]:
            best = (len(layout), header_row, layout)
    return best


def inspect(path: str | Path, sheet: str | None = None) -> Template:
    """读模板，返回布局与观感描述。

    没指定 sheet 时按「匹配到的字段数」挑最像拆分表的那个 ——
    真实工作簿里常有 使用说明、模块总览 这类辅助表，第一个 sheet 未必是数据表。
    """
    openpyxl = _openpyxl()
    source = Path(path)
    if not source.is_file():
        raise SystemExit(f"读不到模板文件：{source}")
    try:
        workbook = openpyxl.load_workbook(source)
    except Exception as exc:  # 不是 xlsx、被占用、损坏
        raise SystemExit(f"{source} 不是可读的 xlsx：{exc}") from None

    candidates = [workbook[sheet]] if sheet else workbook.worksheets
    scored = [(worksheet, *_score_sheet(worksheet)) for worksheet in candidates]
    worksheet, matched, header_row, layout = max(scored, key=lambda item: item[1])

    template = Template(source=source, sheet_name=worksheet.title)
    template.header_row = header_row
    template.source_width = worksheet.max_column
    if layout:
        template.layout = layout
    if len(candidates) > 1 and not sheet:
        others = [ws.title for ws in workbook.worksheets if ws.title != worksheet.title]
        template.notes.append(
            f"工作簿有 {len(candidates)} 个工作表，自动选了「{worksheet.title}」"
            f"（匹配 {matched} 个字段）；其余：{'、'.join(others)}"
        )
    if header_row > 1:
        template.notes.append(
            f"表头在第 {header_row} 行（前 {header_row - 1} 行是标题或说明），写出时保持同样位置"
        )

    unknown = [logical for logical in HEADER_ALIASES if logical not in layout]
    if unknown:
        template.notes.append(
            "没认出来的字段：" + "、".join(HEADER_LABELS[name] for name in unknown)
        )

    data_rows = sum(
        1
        for row in worksheet.iter_rows(min_row=header_row + 1, values_only=True)
        if any(value is not None for value in row)
    )
    process_runs = _column_runs(worksheet, template.layout.get("func", 0), header_row, data_rows)
    module_runs = _column_runs(worksheet, template.layout.get("l3", 0), header_row, data_rows)
    cfp_column = template.layout.get("cfp")
    if cfp_column:
        granularity = _merge_granularity(
            worksheet, cfp_column, header_row, data_rows, process_runs, module_runs
        )
        template.cfp_on_first_row_only = granularity != "none"
        if granularity == "none":
            template.notes.append("模板的 CFP 列没有合并：本工具仍按「每个功能过程写一次」输出")
    else:
        template.notes.append("模板没有 CFP 列：写出时会追加一列")

    get_column_letter = _openpyxl_utils().get_column_letter
    for letter, dimension in worksheet.column_dimensions.items():
        if not dimension.width:
            continue
        for logical, column in template.layout.items():
            if get_column_letter(column) == letter:
                template.widths[logical] = dimension.width

    header_cell = worksheet.cell(row=header_row, column=1)
    fill = getattr(getattr(header_cell, "fill", None), "fgColor", None)
    if fill is not None and isinstance(getattr(fill, "rgb", None), str) and len(fill.rgb) == 8:
        template.header_fill = fill.rgb
    if header_cell.font and header_cell.font.name:
        template.font = header_cell.font.name
        template.font_size = int(header_cell.font.sz or FONT_SIZE)

    l1_column = template.layout.get("l1")
    if l1_column:
        for row in range(header_row + 1, min(worksheet.max_row, header_row + 5) + 1):
            value = worksheet.cell(row=row, column=l1_column).value
            if value:
                template.l1_value = str(value).strip()
                break
    return template


def reconcile(template: Template) -> Template:
    """补齐模板缺的必填列：追加到最右侧，并在 notes 里说清追加了什么。

    直接丢掉放不下的数据是不可接受的 —— 一张 4 列的旧表少了数据组和数据属性，
    静默写出会丢失核查依据。所以宁可多加几列，也要把字段留住。
    """
    width = max([template.source_width, *template.layout.values()])
    for logical in FIELD_ORDER:
        if logical in template.layout:
            continue
        if logical not in REQUIRED_FOR_WRITE:
            continue
        width += 1
        template.layout[logical] = width
        template.appended[logical] = width
        template.widths.setdefault(logical, DEFAULT_WIDTHS[logical])
    if template.appended:
        names = "、".join(f"{HEADER_LABELS[k]}({_letter(v)})" for k, v in template.appended.items())
        template.notes.append(f"模板缺少这些列，已追加到末尾：{names}")
    skipped = [name for name in OPTIONAL_FIELDS if name not in template.layout]
    if skipped:
        names = "、".join(HEADER_LABELS[name] for name in skipped)
        template.notes.append(
            f"模板没有这些列，未追加（缺的是常量列，不影响功能点数）：{names}"
        )
    return template


def _letter(column: int) -> str:
    return _openpyxl_utils().get_column_letter(column)


def _column_runs(worksheet, column: int, header_row: int, data_rows: int) -> int:
    """数一列里有值的行数，用来反推模板自己的模块数 / 功能过程数。"""
    if not column:
        return 0
    return sum(
        1
        for row in range(header_row + 1, header_row + 1 + data_rows)
        if worksheet.cell(row=row, column=column).value not in (None, "")
    )


def _merge_granularity(worksheet, column: int, header_row: int, data_rows: int,
                       process_runs: int, module_runs: int) -> str:
    """判断一列的合并粒度：whole / process / module / none。

    只比数量关系，不比绝对行号 —— 模板的行数和我们生成的行数并不相同。
    容差留 25%：模板里可能存在空行或跨模块合并的边界情况。
    """
    ranges = [rng for rng in worksheet.merged_cells.ranges if rng.min_col == column]
    if not ranges or not data_rows:
        return "none"
    if len(ranges) == 1 and (ranges[0].max_row - ranges[0].min_row + 1) >= data_rows * 0.8:
        return "whole"
    for name, expected in (("process", process_runs), ("module", module_runs)):
        if expected and abs(len(ranges) - expected) <= max(2, expected * 0.25):
            return name
    return "none"


def describe(template: Template) -> str:
    """给人看、也方便贴进核对记录的探测结果。"""
    lines = [
        f"数据源：{template.source.name if template.source else '（无，使用默认 12 列布局）'}",
        f"工作表：{template.sheet_name}　表头行：{template.header_row}　冻结：{template.freeze}",
        f"表头底纹：{template.header_fill}　字体：{template.font} {template.font_size}",
        f"一级模块取值：{template.l1_value or '（空，写出时用 --l1）'}",
        "",
        "| 逻辑字段 | 列 | 列宽 |",
        "| --- | --- | --- |",
    ]
    for logical in FIELD_ORDER:
        column = template.layout.get(logical)
        if column is None:
            lines.append(f"| {HEADER_LABELS[logical]} | （未识别） | |")
        else:
            lines.append(
                f"| {HEADER_LABELS[logical]} | {_letter(column)} | {template.widths.get(logical, '')} |"
            )
    lines += [
        "",
        (
            f"CFP 每个功能过程只写一次：{'是' if template.cfp_on_first_row_only else '否'}"
            if "cfp" in template.layout
            else "模板无 CFP 列：写出时追加一列，每个功能过程写一次"
        ),
        f"整表合并列：{'、'.join(HEADER_LABELS[n] for n in template.merge_whole_table)}",
        f"按模块合并列：{'、'.join(HEADER_LABELS[n] for n in template.merge_by_module)}",
        f"按功能过程合并列：{'、'.join(HEADER_LABELS[n] for n in template.merge_by_process)}",
    ]
    if template.notes:
        lines += ["", "备注："]
        lines += [f"- {note}" for note in template.notes]
    return "\n".join(lines)


USER_FORMATS = ("plain", "dual")


def user_text(row: Row, user_format: str) -> str:
    """项目送审表常见的双行功能用户写法；默认保留纯功能用户。"""
    if user_format == "dual":
        return f"发起者：{row.user}\n接收者：{row.l3}"
    return row.user


def _row_values(row: Row, template: Template, user_format: str = "plain") -> dict[str, object]:
    values = {key: getattr(row, key) for key in (
        "l2", "l3", "user", "event", "func", "desc", "move", "group", "attrs",
        *TRACE_LABELS,
    )}
    values["user"] = user_text(row, user_format)
    return {
        "l1": template.l1_value,
        **values,
        "reuse": 1,
        "cfp": row.fp if row.is_process_head else None,
    }


def _validate_export_text(rows: list[Row], template: Template, user_format: str = "plain") -> None:
    """在创建输出文件前拒绝 Excel 会截断或 XML 无法表示的文本。"""
    for row in rows:
        for logical, value in _row_values(row, template, user_format).items():
            if logical not in template.layout or not isinstance(value, str):
                continue
            location = f"功能过程 {row.process_id or row.func!r} 的 {HEADER_LABELS[logical]}（{logical}）"
            validate_cell_text(value, location)


def validate_cell_text(value: str, location: str) -> None:
    """生成与原表改写共用同一文本限制，失败时尚未改动输出。"""
    if len(value) > 32767:
        raise SystemExit(f"无法写出：{location}有 {len(value)} 个字符，超过 Excel 单元格 32767 字符上限；请缩短原文，不会自动截断")
    for char in value:
        code = ord(char)
        if ((code < 0x20 and char not in '\t\n\r')
                or 0xD800 <= code <= 0xDFFF or code in (0xFFFE, 0xFFFF)):
            raise SystemExit(f"无法写出：{location}含 Excel XML 不支持的字符 U+{code:04X}；请修正原文")


def _text_lines(text: str, width: float, font_size: float) -> int:
    """按列宽近似换行数；中文/全角双宽，组合字符不额外占宽。"""
    capacity = max(1, (width - 2) * FONT_SIZE / font_size)
    lines = 0
    for paragraph in text.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        units = sum(0 if combining(char) else 4 if char == '\t'
                    else 2 if east_asian_width(char) in ('W', 'F') else 1
                    for char in paragraph)
        wrapped = max(1, ceil(units / capacity))
        # Excel 会按词和标点提前换行；自动换行段落留一行余量。
        lines += wrapped + (1 if wrapped > 1 else 0)
    return lines


def _apply_row_heights(worksheet, template: Template, first_row: int, last_row: int) -> None:
    """根据内容估算行高；纵向合并单元格共享高度，最大不超过 Excel 的 409pt。"""
    if last_row < first_row:
        return
    heights = {row: 20.0 for row in range(first_row, last_row + 1)}
    anchors = {(area.min_row, area.min_col): area for area in worksheet.merged_cells.ranges}
    merged_requirements = []
    for cells in worksheet.iter_rows(min_row=first_row, max_row=last_row):
        for cell in cells:
            if cell.value in (None, ''):
                continue
            area = anchors.get((cell.row, cell.column))
            width = worksheet.column_dimensions[cell.column_letter].width
            required = max(20.0, _text_lines(str(cell.value), width, template.font_size)
                           * template.font_size * 1.35 + 4)
            if area and area.max_row > area.min_row:
                merged_requirements.append((area, required))
            else:
                heights[cell.row] = min(409.0, max(heights[cell.row], required))

    # 先满足较小的合并区域，再补大区域的剩余高度，避免反复撑高整表。
    for area, required in sorted(merged_requirements, key=lambda item: item[0].max_row - item[0].min_row):
        span = list(range(area.min_row, area.max_row + 1))
        deficit = required - sum(heights[row] for row in span)
        eligible = [row for row in span if heights[row] < 409.0]
        while deficit > 0.1 and eligible:
            extra = deficit / len(eligible)
            for row in eligible:
                added = min(extra, 409.0 - heights[row])
                heights[row] += added
                deficit -= added
            eligible = [row for row in eligible if heights[row] < 409.0]
    for row, height in heights.items():
        worksheet.row_dimensions[row].height = round(height, 2)


def write(rows: list[Row], destination: str | Path, template: Template | None = None,
          user_format: str = "plain", trace: bool = False) -> Path:
    """写出拆分表。

    默认只写模板/标准 12 列；追溯字段留在自检报告里。需要把过程编号、核实状态、
    需求依据、兴趣对象、重复移动理由、op/op_note、接口证据也写进表时，显式传
    `trace=True`（CLI 的 `--trace`）。模板本来就有这些列时照常复用，不主动删列。

    功能用户列按「连续取值相同」合并，不按模块合并：同一个三级模块里，
    报表查询是操作员、采集入库是定时任务，整块合并会把两种取值糊在一起。
    user_format=dual 时单元格写成「发起者：X」换行「接收者：<三级模块>」。
    """
    if user_format not in USER_FORMATS:
        raise SystemExit(f"未知的功能用户写法 {user_format!r}；允许 {USER_FORMATS}")
    openpyxl = _openpyxl()
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    template = reconcile(template or Template())
    if not template.l1_value:
        raise SystemExit("一级模块取值为空：用 --l1 指定，或让模板的数据行有内容")

    if not trace and not any(key in template.layout for key in TRACE_LABELS):
        template.notes.append("默认只写标准列；追溯字段在自检报告里，需要写进表时加 --trace")
    if trace:
        for key, label in TRACE_LABELS.items():
            if key not in template.layout:
                template.layout[key] = max([template.source_width, *template.layout.values()]) + 1
                template.notes.append(f"追加追溯列：{label}")
            template.widths.setdefault(key, 35)
    _validate_export_text(rows, template, user_format)
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    if worksheet is None:  # pragma: no cover - openpyxl 总会创建默认表
        raise SystemExit("无法创建工作表")
    worksheet.title = template.sheet_name

    cell_font = Font(name=template.font, size=template.font_size)
    header_fill = PatternFill("solid", fgColor=template.header_fill)
    thin = Side(style="thin")
    header_border = Border(left=thin, right=thin, top=thin, bottom=thin)
    centred = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for logical, label in HEADER_LABELS.items():
        column = template.layout.get(logical)
        if column is None:
            continue
        cell = worksheet.cell(row=template.header_row, column=column, value=label)
        cell.font = cell_font
        cell.fill = header_fill
        cell.border = header_border
        cell.alignment = centred

    first_row = template.header_row + 1
    for offset, row in enumerate(rows):
        excel_row = first_row + offset
        for logical, value in _row_values(row, template, user_format).items():
            column = template.layout.get(logical)
            if column is None or not isinstance(value, (str, int, float)):
                continue
            cell = worksheet.cell(row=excel_row, column=column, value=value)
            if isinstance(value, str):
                # openpyxl 默认把 = 开头和 #N/A 等文本解释成公式/错误。
                cell.data_type = "s"
            cell.font = cell_font
            cell.alignment = centred

    last_row = first_row + len(rows) - 1
    _apply_merges(worksheet, rows, template, first_row, last_row)

    get_column_letter = _openpyxl_utils().get_column_letter
    for logical, width in template.widths.items():
        column = template.layout.get(logical)
        if column:
            worksheet.column_dimensions[get_column_letter(column)].width = width
    worksheet.freeze_panes = template.freeze
    _apply_row_heights(worksheet, template, first_row, last_row)

    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output)
    return output


def _apply_merges(worksheet, rows: list[Row], template: Template,
                  first_row: int, last_row: int) -> None:
    def merge(column: int | None, blocks: list[tuple[int, int]]) -> None:
        if not column:
            return
        for start, end in blocks:
            if end > start:
                worksheet.merge_cells(
                    start_row=first_row + start, start_column=column,
                    end_row=first_row + end, end_column=column,
                )

    for logical in template.merge_whole_table:
        column = template.layout.get(logical)
        if column and last_row > first_row:
            worksheet.merge_cells(
                start_row=first_row, start_column=column, end_row=last_row, end_column=column
            )
    for logical in template.merge_by_module:
        merge(template.layout.get(logical), module_blocks(rows, lambda row: (row.l2, row.l3)))
    for logical in template.merge_by_process:
        merge(
            template.layout.get(logical),
            module_blocks(rows, lambda row: row.process_id or (row.l2, row.l3, row.func)),
        )
    merge(template.layout.get("user"), module_blocks(rows, lambda row: row.user))


def _openpyxl():
    try:
        import openpyxl
    except ImportError:
        raise SystemExit("本 skill 读写 xlsx 需要 openpyxl：pip install openpyxl") from None
    return openpyxl


def _openpyxl_utils():
    """`import openpyxl` 不保证 `openpyxl.utils` 已加载，所以在这里显式导入一次。"""
    _openpyxl()
    import openpyxl.utils as utils

    return utils
