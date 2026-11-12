"""内容 Spec 的载入、规范化与类型/样式判定。

Spec 是唯一数据源：HTML、纯文本、Markdown、.eml 都从这里渲染。
规范化只做结构检查与类型收敛，不补造内容；缺字段留给 validate.py 报阻断项。
"""

from __future__ import annotations

import json
import os
import re
from datetime import date
from typing import Any, Iterator

from . import yamlish

__all__ = [
    "SpecError",
    "load_spec",
    "normalize",
    "choose_preset",
    "type_label",
    "iter_text_fields",
    "iter_paragraphs",
    "slugify",
    "filename_base",
    "FORMAT_EXT",
]


class SpecError(ValueError):
    """Spec 结构错误，无法继续渲染。"""


TYPE_LABELS = {
    "notice": "通知",
    "approval": "申请/审批",
    "confirm": "确认",
    "report": "汇报",
    "handover": "交付/验收",
    "coordination": "协调/故障",
    "business": "商务",
    "followup": "跟进",
    "invitation": "邀请",
    "daily": "日常",
}

TYPE_ALIASES = {
    "通知": "notice",
    "告知": "notice",
    "申请": "approval",
    "审批": "approval",
    "确认": "confirm",
    "汇报": "report",
    "周报": "report",
    "交付": "handover",
    "验收": "handover",
    "协调": "coordination",
    "故障": "coordination",
    "商务": "business",
    "报价": "business",
    "跟进": "followup",
    "邀请": "invitation",
    "日常": "daily",
}

BLOCK_KINDS = {
    "summary",
    "paragraph",
    "heading",
    "bullets",
    "table",
    "todo",
    "images",
    "steps",
    "callout",
    "attachments",
    "cta",
    "signature",
    "note",
}

CALLOUT_TONES = {"info", "warn", "risk"}

FORMAT_EXT = {"html": ".html", "text": ".txt", "md": ".md", "eml": ".eml"}


def _text(value: Any, where: str) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        raise SpecError(f"{where} 需要文本，实际是 {type(value).__name__}")
    return str(value)


def _list(value: Any, where: str) -> list:
    if value is None:
        return []
    if not isinstance(value, list):
        raise SpecError(f"{where} 需要列表，实际是 {type(value).__name__}")
    return value


def _string_list(value: Any, where: str) -> list[str]:
    out: list[str] = []
    for index, item in enumerate(_list(value, where), start=1):
        if isinstance(item, (dict, list)):
            raise SpecError(f"{where}[{index}] 需要文本，实际是 {type(item).__name__}")
        out.append(str(item))
    return out


def _type_key(value: Any) -> str:
    key = str(value or "").strip()
    if not key:
        return ""
    if key in TYPE_LABELS:
        return key
    return TYPE_ALIASES.get(key, key)


def _block(raw: Any, index: int) -> dict:
    where = f"blocks[{index}]"
    if not isinstance(raw, dict):
        raise SpecError(f"{where} 需要对象，实际是 {type(raw).__name__}")
    kind = str(raw.get("kind") or "").strip()
    if kind not in BLOCK_KINDS:
        raise SpecError(
            f"{where}.kind 不支持 {kind!r}；可用：{', '.join(sorted(BLOCK_KINDS))}"
        )
    block: dict[str, Any] = {"kind": kind}

    if kind in ("summary", "paragraph", "heading", "note"):
        block["text"] = _text(raw.get("text"), f"{where}.text")
        if not block["text"].strip():
            raise SpecError(f"{where}.text 不能为空")
    elif kind == "bullets":
        items = []
        for pos, item in enumerate(_list(raw.get("items"), f"{where}.items"), start=1):
            if isinstance(item, dict):
                item = item.get("text")
            items.append(_text(item, f"{where}.items[{pos}]"))
        if not items:
            raise SpecError(f"{where}.items 不能为空")
        block["items"] = items
    elif kind == "table":
        columns = _string_list(raw.get("columns"), f"{where}.columns")
        if not columns:
            raise SpecError(f"{where}.columns 不能为空")
        rows: list[list[str]] = []
        for pos, row in enumerate(_list(raw.get("rows"), f"{where}.rows"), start=1):
            if not isinstance(row, list):
                raise SpecError(f"{where}.rows[{pos}] 需要列表")
            cells = [_text(cell, f"{where}.rows[{pos}]") for cell in row]
            if len(cells) != len(columns):
                raise SpecError(
                    f"{where}.rows[{pos}] 有 {len(cells)} 列，表头是 {len(columns)} 列"
                )
            rows.append(cells)
        if not rows:
            raise SpecError(f"{where}.rows 不能为空")
        block["columns"] = columns
        block["rows"] = rows
    elif kind == "todo":
        items = []
        for pos, item in enumerate(_list(raw.get("items"), f"{where}.items"), start=1):
            if not isinstance(item, dict):
                raise SpecError(f"{where}.items[{pos}] 需要对象")
            text = _text(item.get("text"), f"{where}.items[{pos}].text")
            if not text.strip():
                raise SpecError(f"{where}.items[{pos}].text 不能为空")
            items.append(
                {
                    "text": text,
                    "owner": _text(item.get("owner"), f"{where}.items[{pos}].owner"),
                    "due": _text(item.get("due"), f"{where}.items[{pos}].due"),
                }
            )
        if not items:
            raise SpecError(f"{where}.items 不能为空")
        block["items"] = items
    elif kind == "images":
        items = []
        for pos, item in enumerate(_list(raw.get("items"), f"{where}.items"), start=1):
            if not isinstance(item, dict):
                raise SpecError(f"{where}.items[{pos}] 需要对象")
            src = _text(item.get("src"), f"{where}.items[{pos}].src").strip()
            if not src:
                raise SpecError(f"{where}.items[{pos}].src 不能为空")
            width = item.get("width")
            if width is not None:
                try:
                    width = int(width)
                except (TypeError, ValueError) as exc:
                    raise SpecError(f"{where}.items[{pos}].width 需要整数") from exc
            entry = {
                "src": src,
                "alt": _text(item.get("alt"), f"{where}.items[{pos}].alt"),
                "caption": _text(item.get("caption"), f"{where}.items[{pos}].caption"),
            }
            if width is not None:
                entry["width"] = width
            items.append(entry)
        if not items:
            raise SpecError(f"{where}.items 不能为空")
        block["items"] = items
    elif kind == "steps":
        items = []
        for pos, item in enumerate(_list(raw.get("items"), f"{where}.items"), start=1):
            if not isinstance(item, dict):
                raise SpecError(f"{where}.items[{pos}] 需要对象")
            title = _text(item.get("title"), f"{where}.items[{pos}].title")
            if not title.strip():
                raise SpecError(f"{where}.items[{pos}].title 不能为空")
            items.append(
                {
                    "title": title,
                    "time": _text(item.get("time"), f"{where}.items[{pos}].time"),
                    "text": _text(item.get("text"), f"{where}.items[{pos}].text"),
                }
            )
        if not items:
            raise SpecError(f"{where}.items 不能为空")
        block["items"] = items
    elif kind == "callout":
        tone = str(raw.get("tone") or "info").strip().lower()
        if tone not in CALLOUT_TONES:
            raise SpecError(f"{where}.tone 只支持 {', '.join(sorted(CALLOUT_TONES))}")
        block["tone"] = tone
        block["title"] = _text(raw.get("title"), f"{where}.title")
        block["text"] = _text(raw.get("text"), f"{where}.text")
        if not block["text"].strip():
            raise SpecError(f"{where}.text 不能为空")
    elif kind == "attachments":
        items = []
        for pos, item in enumerate(_list(raw.get("items"), f"{where}.items"), start=1):
            if not isinstance(item, dict):
                raise SpecError(f"{where}.items[{pos}] 需要对象")
            name = _text(item.get("name"), f"{where}.items[{pos}].name").strip()
            if not name:
                raise SpecError(f"{where}.items[{pos}].name 不能为空")
            items.append(
                {"name": name, "note": _text(item.get("note"), f"{where}.items[{pos}].note")}
            )
        if not items:
            raise SpecError(f"{where}.items 不能为空")
        block["items"] = items
    elif kind == "cta":
        block["text"] = _text(raw.get("text"), f"{where}.text")
        block["url"] = _text(raw.get("url"), f"{where}.url")
        if not block["text"].strip() or not block["url"].strip():
            raise SpecError(f"{where} 需要 text 与 url")
    elif kind == "signature":
        name = _text(raw.get("name"), f"{where}.name")
        if not name.strip():
            raise SpecError(f"{where}.name 不能为空")
        contact = raw.get("contact")
        block["name"] = name
        block["title"] = _text(raw.get("title"), f"{where}.title")
        block["contact"] = _string_list(contact, f"{where}.contact") if contact else []
    return block


def normalize(data: Any, source: str = "<spec>") -> dict:
    """把解析后的对象收敛成渲染器使用的 Spec。结构错误直接抛 SpecError。"""
    if not isinstance(data, dict):
        raise SpecError(f"{source} 顶层需要对象，实际是 {type(data).__name__}")
    spec: dict[str, Any] = {}
    spec["source"] = source
    spec["type"] = _type_key(data.get("type"))
    spec["secondary"] = [
        key for key in (_type_key(item) for item in _list(data.get("secondary"), "secondary")) if key
    ]
    spec["audience"] = _text(data.get("audience"), "audience")
    spec["tone"] = _text(data.get("tone"), "tone")
    spec["to"] = _text(data.get("to"), "to")
    spec["cc"] = _string_list(data.get("cc"), "cc")
    spec["subject"] = _text(data.get("subject"), "subject")
    spec["greeting"] = _text(data.get("greeting"), "greeting")
    spec["summary"] = _text(data.get("summary"), "summary")
    spec["urgent"] = (
        data.get("urgent") is True
        or str(data.get("urgent") or "").strip().lower() in ("true", "yes", "1")
    )
    style = data.get("style")
    if style is not None and not isinstance(style, (str, dict)):
        raise SpecError("style 需要预设名或对象")
    spec["style"] = style or ""
    spec["blocks"] = [
        _block(raw, index) for index, raw in enumerate(_list(data.get("blocks"), "blocks"), 1)
    ]
    spec["facts"] = _string_list(data.get("facts"), "facts")
    spec["placeholders"] = _string_list(data.get("placeholders"), "placeholders")
    return spec


def choose_preset(spec: dict) -> tuple[str, str]:
    """按方案第四节选择预设，返回 (预设名, 依据)。"""
    style = spec.get("style")
    if isinstance(style, str) and style.strip():
        return style.strip(), "Spec 指定"
    if isinstance(style, dict) and str(style.get("preset") or "").strip():
        return str(style["preset"]).strip(), "Spec 指定"

    kind = spec.get("type")
    audience = spec.get("audience") or ""
    external = any(word in audience for word in ("外部", "客户", "甲方", "供应商"))
    blocks = spec.get("blocks") or []
    table_rows = sum(len(block.get("rows", [])) for block in blocks if block["kind"] == "table")
    images = sum(len(block.get("items", [])) for block in blocks if block["kind"] == "images")

    if spec.get("urgent"):
        return "alert", "标记为紧急"
    if kind == "coordination":
        return "alert", "协调/故障类型"
    if kind == "daily" or external:
        return "plain", "日常或对外"
    if kind in ("report", "handover"):
        return "report", "汇报/交付类型"
    if kind in ("approval", "confirm", "invitation", "notice", "business", "followup"):
        return "business", "对内正式类型"
    if table_rows >= 3 or images >= 2:
        return "report", "表格或图片较多"
    return "business", "默认预设"


def type_label(spec: dict) -> str:
    labels = [TYPE_LABELS.get(spec.get("type", ""), spec.get("type", ""))]
    labels.extend(TYPE_LABELS.get(item, item) for item in spec.get("secondary") or [])
    return " + ".join(label for label in labels if label)


def iter_text_fields(spec: dict) -> Iterator[tuple[str, str]]:
    """产出所有会出现在正文里的文本字段，供数字溯源与长度检查。"""
    for key in ("subject", "greeting", "summary"):
        value = spec.get(key) or ""
        if value:
            yield key, value
    for index, block in enumerate(spec.get("blocks") or [], start=1):
        kind = block["kind"]
        base = f"blocks[{index}].{kind}"
        if kind in ("summary", "paragraph", "heading", "note"):
            yield f"{base}.text", block.get("text", "")
        elif kind == "bullets":
            for pos, item in enumerate(block.get("items") or [], start=1):
                yield f"{base}.items[{pos}]", item
        elif kind == "table":
            for pos, name in enumerate(block.get("columns") or [], start=1):
                yield f"{base}.columns[{pos}]", name
            for row_pos, row in enumerate(block.get("rows") or [], start=1):
                for cell_pos, cell in enumerate(row, start=1):
                    yield f"{base}.rows[{row_pos}][{cell_pos}]", cell
        elif kind == "todo":
            for pos, item in enumerate(block.get("items") or [], start=1):
                yield f"{base}.items[{pos}].text", item.get("text", "")
                yield f"{base}.items[{pos}].owner", item.get("owner", "")
                yield f"{base}.items[{pos}].due", item.get("due", "")
        elif kind == "images":
            for pos, item in enumerate(block.get("items") or [], start=1):
                yield f"{base}.items[{pos}].caption", item.get("caption", "")
        elif kind == "steps":
            for pos, item in enumerate(block.get("items") or [], start=1):
                yield f"{base}.items[{pos}].title", item.get("title", "")
                yield f"{base}.items[{pos}].time", item.get("time", "")
                yield f"{base}.items[{pos}].text", item.get("text", "")
        elif kind == "callout":
            yield f"{base}.title", block.get("title", "")
            yield f"{base}.text", block.get("text", "")
        elif kind == "attachments":
            for pos, item in enumerate(block.get("items") or [], start=1):
                yield f"{base}.items[{pos}].name", item.get("name", "")
                yield f"{base}.items[{pos}].note", item.get("note", "")
        elif kind == "cta":
            yield f"{base}.text", block.get("text", "")
        elif kind == "signature":
            yield f"{base}.name", block.get("name", "")
            yield f"{base}.title", block.get("title", "")
            for pos, line in enumerate(block.get("contact") or [], start=1):
                yield f"{base}.contact[{pos}]", line


def iter_paragraphs(spec: dict) -> Iterator[tuple[str, str]]:
    """会形成连续段落的文本，用于估算行数。"""
    for key in ("summary",):
        value = spec.get(key) or ""
        if value:
            yield key, value
    for index, block in enumerate(spec.get("blocks") or [], start=1):
        if block["kind"] in ("summary", "paragraph", "callout", "note"):
            yield f"blocks[{index}].{block['kind']}.text", block.get("text", "")


def iter_images(spec: dict) -> Iterator[dict]:
    for block in spec.get("blocks") or []:
        if block["kind"] == "images":
            yield from block.get("items") or []


def load_spec(path: str) -> dict:
    """读取 .yaml / .json 规格。JSON 也可以写成 .yaml（首字符为 `{` 时按 JSON 解析）。"""
    if not os.path.isfile(path):
        raise SpecError(f"找不到规格文件：{path}")
    with open(path, encoding="utf-8-sig") as handle:
        text = handle.read()
    try:
        if path.endswith(".json"):
            data = json.loads(text)
        elif text.lstrip().startswith("{"):
            try:
                data = json.loads(text)
            except ValueError:
                data = yamlish.loads(text)
        else:
            data = yamlish.loads(text)
    except (ValueError, yamlish.YamlError) as exc:
        raise SpecError(f"{path} 解析失败：{exc}") from exc
    return normalize(data, source=path)


_UNSAFE_FILENAME = re.compile(r'[\\/:*?"<>|\r\n\t]')
_TAG = re.compile(r"【[^】]*】")


def slugify(subject: str, limit: int = 40) -> str:
    text = _TAG.sub("", subject or "")
    text = _UNSAFE_FILENAME.sub("-", text)
    text = re.sub(r"\s+", "-", text.strip())
    text = re.sub(r"-{2,}", "-", text).strip("-.")
    return text[:limit].strip("-.") or "email"


def filename_base(subject: str, day: date | None = None, name: str | None = None) -> str:
    if name:
        if name in {".", ".."} or _UNSAFE_FILENAME.search(name):
            raise SpecError("--name 必须是文件名主干，不能包含路径或控制字符")
        return name
    return f"{slugify(subject)}_{(day or date.today()).isoformat()}"
