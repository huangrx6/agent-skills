"""模块库：每个模块同时定义 HTML、纯文本、Markdown 三种渲染。

HTML 只使用表格布局与内联样式，不用 flex/grid/JS；文本与 Markdown 保留同一份内容，
不另造信息。模块结构由 spec.py 规范化，这里只负责呈现。
"""

from __future__ import annotations

import html as html_lib
from typing import Callable

__all__ = ["html", "text", "markdown"]

TONE_LABELS = {"info": "说明", "warn": "注意", "risk": "风险"}
TONE_COLORS = {
    "info": ("#F1F6FA", "#1F4E79"),
    "warn": ("#FFFAEB", "#B54708"),
    "risk": ("#FEF3F2", "#B42318"),
}


def esc(value: object) -> str:
    return html_lib.escape(str(value), quote=True)


def _br(value: str) -> str:
    return esc(value).replace("\n", "<br>")


def _font(tokens: dict) -> str:
    font = tokens["font"]
    return (
        f"font-family:{font['family']};font-size:{font['size']}px;"
        f"line-height:{font['line_height']};color:{tokens['color']['text']};"
    )


def _typography(tokens: dict) -> str:
    """字号与颜色另写时用的字体基础串。"""
    font = tokens["font"]
    return f"font-family:{font['family']};line-height:{font['line_height']};"


def _block_gap(tokens: dict) -> int:
    return int(tokens["spacing"]["block"])


def _content_width(tokens: dict) -> int:
    return int(tokens["width"]) - 2 * int(tokens["spacing"]["content"])


def _paragraph(text: str, tokens: dict, color: str | None = None) -> str:
    return (
        f'<p style="{_font(tokens)}margin:0 0 {_block_gap(tokens)}px;'
        f'{f"color:{color};" if color else ""}">{_br(text)}</p>'
    )


def _table_html(columns: list[str], rows: list[list[str]], tokens: dict) -> str:
    color = tokens["color"]
    table = tokens["table"]
    cell = (
        f"padding:8px 10px;border-bottom:1px solid {color['border']};"
        f"vertical-align:top;text-align:left;"
    )
    head_cells = "".join(
        f'<th align="left" style="background-color:{table["header_background"]};'
        f'color:{color["text"]};font-weight:600;{cell}">{esc(name)}</th>'
        for name in columns
    )
    body_rows = []
    for index, row in enumerate(rows):
        background = (
            f"background-color:{color['surface']};"
            if table["zebra"] and index % 2 == 1
            else ""
        )
        cells = "".join(f'<td style="{background}{cell}">{_br(item)}</td>' for item in row)
        body_rows.append(f"<tr>{cells}</tr>")
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" '
        f'border="0" style="border-collapse:collapse;width:100%;margin:0 0 '
        f'{_block_gap(tokens)}px;font-size:13px;line-height:1.6;">'
        f"<tr>{head_cells}</tr>{''.join(body_rows)}</table>"
    )


def _summary_html(block: dict, tokens: dict) -> str:
    color = tokens["color"]
    if not tokens["summary"]["card"]:
        return _paragraph(block["text"], tokens)
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="border-collapse:collapse;margin:0 0 {_block_gap(tokens)}px;">'
        f'<tr><td style="background-color:{color["surface"]};border-left:4px solid '
        f'{color["accent"]};padding:12px 16px;{_font(tokens)}font-size:15px;">'
        f'{_br(block["text"])}</td></tr></table>'
    )


def _heading_html(block: dict, tokens: dict) -> str:
    color = tokens["color"]
    return (
        f'<h2 style="{_typography(tokens)}font-size:{tokens["heading"]["section_size"]}px;'
        f'font-weight:600;margin:24px 0 8px;color:{color["accent"]};">'
        f'{esc(block["text"])}</h2>'
    )


def _bullets_html(block: dict, tokens: dict) -> str:
    items = "".join(
        f'<li style="{_font(tokens)}margin:0 0 6px;">{_br(item)}</li>'
        for item in block["items"]
    )
    return (
        f'<ul style="margin:0 0 {_block_gap(tokens)}px;padding-left:20px;">{items}</ul>'
    )


def _todo_html(block: dict, tokens: dict) -> str:
    rows = [
        [item["text"], item["owner"] or "—", item["due"] or "—"] for item in block["items"]
    ]
    return _table_html(["事项", "负责人", "截止时间"], rows, tokens)


def _images_html(block: dict, tokens: dict, image_src: Callable[[str], str]) -> str:
    color = tokens["color"]
    max_width = _content_width(tokens)
    parts = []
    for item in block["items"]:
        width = min(int(item.get("width") or max_width), max_width)
        caption = item["caption"]
        caption_html = (
            f'<div style="font-size:12px;line-height:1.6;color:{color["muted"]};'
            f'margin-top:6px;">{_br(caption)}</div>'
            if caption
            else ""
        )
        parts.append(
            f'<div style="margin:0 0 {_block_gap(tokens)}px;">'
            f'<img src="{esc(image_src(item["src"]))}" alt="{esc(item["alt"])}" '
            f'width="{width}" style="display:block;width:{width}px;max-width:100%;'
            f'height:auto;border:0;">{caption_html}</div>'
        )
    return "".join(parts)


def _steps_html(block: dict, tokens: dict) -> str:
    color = tokens["color"]
    rows = []
    for index, item in enumerate(block["items"], start=1):
        time_html = (
            f'<span style="color:{color["muted"]};font-size:13px;">'
            f'（{esc(item["time"])}）</span>'
            if item["time"]
            else ""
        )
        text_html = (
            f'<div style="margin-top:4px;color:{color["text"]};">{_br(item["text"])}</div>'
            if item["text"]
            else ""
        )
        rows.append(
            f'<tr><td width="28" valign="top" style="{_font(tokens)}font-weight:700;'
            f'color:{color["accent"]};padding:0 8px 10px 0;">{index}.</td>'
            f'<td valign="top" style="{_font(tokens)}padding:0 0 10px;">'
            f"<strong>{esc(item['title'])}</strong>{time_html}{text_html}</td></tr>"
        )
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'border="0" style="border-collapse:collapse;margin:0 0 {_block_gap(tokens)}px;">'
        f"{''.join(rows)}</table>"
    )


def _callout_html(block: dict, tokens: dict) -> str:
    color = tokens["color"]
    if block["tone"] == "info":
        background, accent = color["surface"], color["accent"]
    else:
        background, accent = TONE_COLORS[block["tone"]]
    title = block["title"]
    title_html = (
        f'<div style="font-weight:600;margin-bottom:4px;">{esc(title)}</div>' if title else ""
    )
    if tokens["callout"]["card"]:
        return (
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'border="0" style="border-collapse:collapse;margin:0 0 {_block_gap(tokens)}px;">'
            f'<tr><td style="background-color:{background};border-left:4px solid {accent};'
            f'padding:10px 14px;{_font(tokens)}font-size:13px;">{title_html}'
            f'{_br(block["text"])}</td></tr></table>'
        )
    return (
        f'<div style="border-left:3px solid {color["border"]};padding:2px 0 2px 12px;'
        f'margin:0 0 {_block_gap(tokens)}px;{_font(tokens)}font-size:13px;">'
        f'{title_html}{_br(block["text"])}</div>'
    )


def _attachments_html(block: dict, tokens: dict) -> str:
    color = tokens["color"]
    lines = []
    for item in block["items"]:
        note = (
            f'<span style="color:{color["muted"]};">（{esc(item["note"])}）</span>'
            if item["note"]
            else ""
        )
        lines.append(f'<div style="{_font(tokens)}margin:0 0 4px;">附件：{esc(item["name"])}{note}</div>')
    return f'<div style="margin:0 0 {_block_gap(tokens)}px;">{"".join(lines)}</div>'


def _cta_html(block: dict, tokens: dict) -> str:
    color = tokens["color"]
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        f'style="border-collapse:collapse;margin:0 0 {_block_gap(tokens)}px;">'
        f'<tr><td style="background-color:{color["accent"]};border-radius:4px;">'
        f'<a href="{esc(block["url"])}" style="display:inline-block;padding:10px 18px;'
        f'color:#FFFFFF;font-size:14px;line-height:1.4;text-decoration:none;'
        f'font-family:{tokens["font"]["family"]};">{esc(block["text"])}</a></td></tr></table>'
        f'<div style="font-size:12px;line-height:1.6;color:{color["muted"]};'
        f'margin:-4px 0 {_block_gap(tokens)}px;word-break:break-all;">{esc(block["url"])}</div>'
    )


def _signature_html(block: dict, tokens: dict) -> str:
    color = tokens["color"]
    lines = [f'<div style="font-weight:600;">{esc(block["name"])}</div>']
    if block["title"]:
        lines.append(f"<div>{esc(block['title'])}</div>")
    for line in block["contact"]:
        lines.append(f"<div>{esc(line)}</div>")
    return (
        f'<div style="margin-top:20px;padding-top:12px;border-top:1px solid '
        f'{color["border"]};font-size:13px;line-height:1.7;color:{color["muted"]};">'
        f'{"".join(lines)}</div>'
    )


def _note_html(block: dict, tokens: dict) -> str:
    return (
        f'<p style="margin:0 0 {_block_gap(tokens)}px;font-size:12px;line-height:1.6;'
        f'color:{tokens["color"]["muted"]};">{_br(block["text"])}</p>'
    )


def html(block: dict, tokens: dict, image_src: Callable[[str], str] | None = None) -> str:
    """渲染单个模块的 HTML 片段。"""
    image_src = image_src or (lambda src: src)
    kind = block["kind"]
    if kind == "summary":
        return _summary_html(block, tokens)
    if kind == "paragraph":
        return _paragraph(block["text"], tokens)
    if kind == "heading":
        return _heading_html(block, tokens)
    if kind == "bullets":
        return _bullets_html(block, tokens)
    if kind == "table":
        return _table_html(block["columns"], block["rows"], tokens)
    if kind == "todo":
        return _todo_html(block, tokens)
    if kind == "images":
        return _images_html(block, tokens, image_src)
    if kind == "steps":
        return _steps_html(block, tokens)
    if kind == "callout":
        return _callout_html(block, tokens)
    if kind == "attachments":
        return _attachments_html(block, tokens)
    if kind == "cta":
        return _cta_html(block, tokens)
    if kind == "signature":
        return _signature_html(block, tokens)
    if kind == "note":
        return _note_html(block, tokens)
    raise ValueError(f"未知模块：{kind}")


# ── 纯文本 ────────────────────────────────────────────────────────────────
def _table_text(columns: list[str], rows: list[list[str]]) -> str:
    # 不生成行号：纯文本与 HTML 的关键数字要能逐项对上，行号会制造假差异。
    blocks_out = []
    for row in rows:
        lines = [row[0]]
        for name, cell in zip(columns[1:], row[1:]):
            lines.append(f"  {name}：{cell}")
        blocks_out.append("\n".join(lines))
    return "\n\n".join(blocks_out)


def _steps_text(items: list[dict]) -> str:
    lines = []
    for index, item in enumerate(items, start=1):
        time = f"（{item['time']}）" if item["time"] else ""
        lines.append(f"{index}. {item['title']}{time}")
        if item["text"]:
            lines.append(f"   {item['text']}")
    return "\n".join(lines)


def _callout_text(block: dict) -> str:
    label = block["title"] or TONE_LABELS[block["tone"]]
    return f"【{label}】{block['text']}"


def text(block: dict) -> str:
    """渲染单个模块的纯文本片段。"""
    kind = block["kind"]
    if kind in ("summary", "paragraph", "heading"):
        return block["text"]
    if kind == "bullets":
        return "\n".join(f"- {item}" for item in block["items"])
    if kind == "table":
        return _table_text(block["columns"], block["rows"])
    if kind == "todo":
        blocks_out = ["【待办】"]
        for item in block["items"]:
            lines = [item["text"]]
            if item["owner"]:
                lines.append(f"  负责人：{item['owner']}")
            if item["due"]:
                lines.append(f"  截止时间：{item['due']}")
            blocks_out.append("\n".join(lines))
        return "\n\n".join(blocks_out)
    if kind == "images":
        lines = []
        for item in block["items"]:
            lines.append(f"[图片] {item['caption']}".rstrip())
            lines.append(item["src"])
        return "\n".join(lines)
    if kind == "steps":
        return _steps_text(block["items"])
    if kind == "callout":
        return _callout_text(block)
    if kind == "attachments":
        return "\n".join(
            f"附件：{item['name']}" + (f"（{item['note']}）" if item["note"] else "")
            for item in block["items"]
        )
    if kind == "cta":
        return f"{block['text']}\n{block['url']}"
    if kind == "signature":
        return "\n".join([block["name"], *([block["title"]] if block["title"] else []), *block["contact"]])
    if kind == "note":
        return block["text"]
    raise ValueError(f"未知模块：{kind}")


# ── Markdown ──────────────────────────────────────────────────────────────
def _md_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


def _md_table(columns: list[str], rows: list[list[str]]) -> str:
    head = "| " + " | ".join(_md_cell(name) for name in columns) + " |"
    rule = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| " + " | ".join(_md_cell(cell) for cell in row) + " |" for row in rows
    ]
    return "\n".join([head, rule, *body])


def markdown(block: dict) -> str:
    """渲染单个模块的 Markdown 片段，保留结构便于二次编辑。"""
    kind = block["kind"]
    if kind == "summary":
        return "\n".join(f"> {line}" for line in block["text"].split("\n"))
    if kind == "paragraph":
        return block["text"]
    if kind == "heading":
        return f"## {block['text']}"
    if kind == "bullets":
        return "\n".join(f"- {item}" for item in block["items"])
    if kind == "table":
        return _md_table(block["columns"], block["rows"])
    if kind == "todo":
        return _md_table(
            ["事项", "负责人", "截止时间"],
            [[item["text"], item["owner"] or "—", item["due"] or "—"] for item in block["items"]],
        )
    if kind == "images":
        lines = []
        for item in block["items"]:
            alt = item["alt"] or "图片"
            lines.append(f"![{alt}]({item['src']})")
            if item["caption"]:
                lines.append(f"*{item['caption']}*")
        return "\n\n".join(lines)
    if kind == "steps":
        lines = []
        for index, item in enumerate(block["items"], start=1):
            time = f"（{item['time']}）" if item["time"] else ""
            lines.append(f"{index}. **{item['title']}**{time}")
            if item["text"]:
                lines.append(f"   {item['text']}")
        return "\n".join(lines)
    if kind == "callout":
        label = block["title"] or TONE_LABELS[block["tone"]]
        return "\n".join(f"> **{label}**：{line}" for line in block["text"].split("\n"))
    if kind == "attachments":
        return "\n".join(
            f"- 附件：{item['name']}" + (f"（{item['note']}）" if item["note"] else "")
            for item in block["items"]
        )
    if kind == "cta":
        return f"[{block['text']}]({block['url']})"
    if kind == "signature":
        lines = ["--", "", f"**{block['name']}**"]
        if block["title"]:
            lines.append(block["title"])
        lines.extend(block["contact"])
        return "  \n".join(lines)
    if kind == "note":
        return f"*{block['text']}*"
    raise ValueError(f"未知模块：{kind}")
