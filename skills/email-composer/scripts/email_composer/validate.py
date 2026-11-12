"""校验：阻断项必须清零才能交付；警告项逐条判断后交付。

报告固定为 JSON：ok / blocking / warnings / skipped / stats。
数字溯源以 Spec 的 facts 为唯一依据；生成的结构编号不参与校验。
"""

from __future__ import annotations

import html as html_lib
import json
import os
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from .htmltools import Tags
from .spec import iter_images, iter_paragraphs, iter_text_fields

__all__ = [
    "validate_spec",
    "extract_tokens",
    "report_to_json",
    "check_html_body",
    "text_warnings",
]

PLACEHOLDER_RE = re.compile(r"【待填[^】]*】")
VARIABLE_RE = re.compile(r"\{\{[^{}\n]+\}\}")
URL_RE = re.compile(r"(?:https?://|mailto:)[^\s<>\"')]+")
IMG_RE = re.compile(r"<img\b[^>]*>", re.I)
ALT_RE = re.compile(r'alt="([^"]*)"', re.I)
WIDTH_CSS_RE = re.compile(r"(?:^|[;\s])(?:max-)?width\s*:\s*(\d+)\s*px", re.I)
WIDTH_ATTR_RE = re.compile(r'\bwidth="(\d+)"', re.I)
EXCLAMATION_RE = re.compile(r"[!！]")
EMOJI_RE = re.compile(
    "[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF\U00002600-\U000027BF]"
)
FORBIDDEN = (
    (re.compile(r"display\s*:\s*(?:flex|grid)", re.I), "flex/grid 布局"),
    (re.compile(r"<script\b", re.I), "script"),
    (re.compile(r"<form\b", re.I), "form"),
    (re.compile(r"\bposition\s*:\s*", re.I), "position 定位"),
    (re.compile(r"javascript\s*:", re.I), "javascript: 链接"),
)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")

ACTION_CUES = (
    "请",
    "麻烦",
    "烦请",
    "回复",
    "审批",
    "确认",
    "反馈",
    "提供",
    "参加",
    "知悉",
    "跟进",
    "评审",
    "批准",
    "提交",
    "上传",
    "参会",
)
DEADLINE_CUES = (
    "前",
    "之前",
    "截止",
    "不晚于",
    "尽快",
    "本周",
    "下周",
    "今天",
    "明天",
    "今日",
    "明日",
)

TOKEN_RE = re.compile(
    r"""
    (?P<date>\d{4}\s*[-/年]\s*\d{1,2}\s*[-/月]\s*\d{1,2}(?:\s*日)?)
  | (?P<ym>\d{4}\s*[-/年]\s*\d{1,2}\s*月?)
  | (?P<md>\d{1,2}\s*月\s*\d{1,2}\s*日)
  | (?P<mdash>(?:0?[1-9]|1[0-2])-(?:0?[1-9]|[12]\d|3[01])(?!\d))
  | (?P<time>\d{1,2}:\d{2})
  | (?P<num>\d+(?:\.\d+)?)
    """,
    re.X,
)

DATE_KINDS = {"date", "ym", "md", "mdash"}


def _digits(raw: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", raw))


def extract_tokens(text: str) -> list[tuple[str, Any, str]]:
    """提取日期、时间与数字。返回 (kind, 归一化值, 原文)。"""
    tokens: list[tuple[str, Any, str]] = []
    for match in TOKEN_RE.finditer(text or ""):
        kind = match.lastgroup or ""
        raw = match.group(0)
        if kind in DATE_KINDS:
            tokens.append((kind, _digits(raw), raw))
        elif kind == "time":
            hour, minute = raw.split(":")
            tokens.append(("time", (int(hour), int(minute)), raw))
        elif kind == "num":
            try:
                tokens.append(("num", Decimal(raw), raw))
            except InvalidOperation:
                continue
    return tokens


def _is_subsequence(needle: tuple, haystack: tuple) -> bool:
    if not needle or len(needle) > len(haystack):
        return False
    for start in range(len(haystack) - len(needle) + 1):
        if haystack[start : start + len(needle)] == needle:
            return True
    return False


def _number_matches(value: Decimal, fact_tokens: list[tuple[str, Any, str]]) -> bool:
    for kind, fact_value, _ in fact_tokens:
        if kind == "num" and fact_value == value:
            return True
    return False


def _token_matches(token: tuple[str, Any, str], fact_tokens: list[tuple[str, Any, str]]) -> bool:
    kind, value, _ = token
    if kind == "num":
        return _number_matches(value, fact_tokens)
    if kind == "time":
        return any(fact_kind == "time" and fact_value == value for fact_kind, fact_value, _ in fact_tokens)
    return any(
        fact_kind in DATE_KINDS and _is_subsequence(value, fact_value)
        for fact_kind, fact_value, _ in fact_tokens
    )


def _html_text(source: str) -> str:
    source = re.sub(r"<(script|style)\b.*?</\1>", " ", source, flags=re.S | re.I)
    source = re.sub(r"<[^>]+>", " ", source)
    return html_lib.unescape(source)


def _strip_urls(text: str) -> str:
    return URL_RE.sub(" ", text)


def _item(code: str, message: str, where: str = "") -> dict:
    return {"code": code, "message": message, "where": where}


def _add_unique(items: list[dict], entry: dict) -> None:
    for existing in items:
        if existing["code"] == entry["code"] and existing["message"] == entry["message"]:
            return
    items.append(entry)


def _estimate_lines(text: str) -> int:
    """按 14px/600px 版心估算行数：全角 1 字，半角 0.5 字，每行约 42 个全角字。"""
    lines = 0
    for part in (text or "").split("\n"):
        width = sum(1.0 if ord(ch) > 127 else 0.5 for ch in part)
        lines += max(1, int((width + 41) // 42))
    return lines


def _scan_source_strings(spec: dict) -> list[tuple[str, str]]:
    """Scan content and delivery fields; facts/style/metadata are not output."""
    fields = []
    def walk(value, path):
        if isinstance(value, str):
            fields.append((path, value))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")
        elif isinstance(value, dict):
            for key, item in value.items():
                walk(item, f"{path}.{key}")
    for key in ("subject", "greeting", "summary", "to", "cc", "blocks"):
        walk(spec.get(key), key)
    return fields


def check_html_body(html_body: str) -> list[dict]:
    """Inspect parsed attributes and CSS; never treat visible prose as markup."""
    blocking = []
    def add(code, message, where=""):
        _add_unique(blocking, _item(code, message, where))
    def css(source):
        source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
        # CSS escapes can hide disallowed declarations; unsupported in mail styles.
        if "\\" in source:
            add("html_forbidden", "CSS 含不支持的转义", "style")
        for pattern, label in FORBIDDEN:
            if pattern.search(source):
                add("html_forbidden", f"HTML 含禁用构造：{label}", "style")
        if re.search(r"(?:expression\s*\(|@import|url\s*\()", source, re.I):
            add("html_forbidden", "CSS 含动态表达式或外部资源", "style")
        for value, unit in re.findall(r"(?:^|[;{\s])(?:min-|max-)?width\s*:\s*([0-9.]+)\s*(px|pt)?", source, re.I):
            width = float(value) * (4 / 3 if unit.lower() == "pt" else 1)
            if width > 640:
                add("html_width", f"HTML 宽度超过 640：{width:g}px")
    for tag, attrs, raw, _ in Tags(html_body or "").tags:
        if tag in {"script", "form", "iframe", "object", "embed", "svg", "math", "base", "link"}:
            add("html_forbidden", f"HTML 含禁用构造：{tag}", tag)
        values = dict(attrs)
        if tag == "meta" and values.get("http-equiv", "").lower() == "refresh":
            add("html_forbidden", "HTML 含跳转 meta", tag)
        for key, value in attrs:
            value = value or ""
            if key.startswith("on") or key in {"srcdoc", "srcset"}:
                add("html_forbidden", f"HTML 含禁用属性：{key}", tag)
            if key in {"href", "src", "background", "action", "xlink:href"}:
                compact = re.sub(r"[\x00-\x20]+", "", value).lower()
                if compact.startswith(("javascript:", "vbscript:", "data:text/html", "data:image/svg")):
                    add("html_forbidden", "HTML 含不安全的 URL", tag)
            if key == "style":
                css(value)
            if key == "width" and re.fullmatch(r"[0-9.]+(?:px)?", value.strip(), re.I):
                if float(re.sub("px$", "", value.strip(), flags=re.I)) > 640:
                    add("html_width", f"HTML 宽度超过 640：{value}")
        if tag == "img" and not (values.get("alt") or "").strip():
            add("image_alt", "图片缺少 alt", raw[:80])
    for style in re.findall(r"<style\b[^>]*>(.*?)</style\s*>", html_body or "", re.S | re.I):
        css(style)
    return blocking


UNIT_PATTERN = r"亿元|万元|人民币|美元|欧元|港元|元|人天|人日|人时|小时|分钟|秒|天|%|％|个百分点|人|个|次|张|件"
QUANTITY_RE = re.compile(r"(?<![\d.])([+-]?\d+(?:\.\d+)?)\s*(" + UNIT_PATTERN + r")")


def quantities(text):
    # Keep magnitude and unit exact: conversions require an explicit fact.
    return {(Decimal(m.group(1)), m.group(2).replace("％", "%").replace("人日", "人天"))
            for m in QUANTITY_RE.finditer(text)}


def check_quantities(spec):
    known = set().union(*(quantities(fact) for fact in spec.get("facts") or []))
    fields = list(iter_text_fields(spec))
    for i, block in enumerate(spec.get("blocks") or []):
        if block["kind"] != "table":
            continue
        for j, heading in enumerate(block["columns"]):
            unit = re.search(r"[（(]\s*(" + UNIT_PATTERN + r")\s*[）)]", heading)
            if unit:
                for row in block["rows"]:
                    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", row[j].strip()):
                        fields.append((f"blocks[{i}].rows", row[j] + unit.group(1)))
    hits = []
    for where, value in fields:
        for number, unit in quantities(value) - known:
            _add_unique(hits, _item("quantity_mismatch", f"数值与单位未在 facts 声明：{number} {unit}", where))
    return hits


def text_warnings(text_body: str, exclude_subject_line: bool = False, kind: str = "") -> tuple[list[dict], int]:
    """纯文本的通用警告：长度、期望动作、时限、感叹号与 emoji。"""
    warnings: list[dict] = []
    lines = (text_body or "").split("\n")
    if exclude_subject_line and lines and lines[0].startswith("【主题】"):
        lines = lines[1:]
    body_chars = len(re.sub(r"\s", "", _strip_urls("\n".join(lines))))
    if body_chars > 800:
        warnings.append(_item("body_long", f"正文约 {body_chars} 字，超过 800 字建议", "body"))
    content = "\n".join(lines)
    has_action = any(cue in content for cue in ACTION_CUES)
    has_deadline = any(cue in content for cue in DEADLINE_CUES) or any(
        kind in DATE_KINDS or kind == "time"
        for kind, _, _ in extract_tokens(content)
    )
    requires_action = kind in {"approval", "confirm", "coordination", "business", "followup", "invitation", "handover"}
    if requires_action and not has_action:
        warnings.append(_item("no_action", "没有识别到明确的期望动作", "body"))
    if requires_action and not has_deadline:
        warnings.append(_item("no_deadline", "没有识别到回复或完成时限", "body"))
    if EXCLAMATION_RE.search(text_body or ""):
        warnings.append(_item("exclamation", "出现感叹号", "body"))
    emoji = EMOJI_RE.search(text_body or "")
    if emoji:
        warnings.append(_item("emoji", f"出现 emoji：{emoji.group(0)}", "body"))
    return warnings, body_chars


def validate_spec(
    spec: dict,
    tokens: dict,
    html_body: str,
    text_body: str,
    md_body: str = "",
    base_dir: str | None = None,
) -> dict:
    blocking: list[dict] = []
    warnings: list[dict] = []
    skipped: list[str] = ["仅校验 Spec 内声明的一致性；未核验用户原始材料或事实真实性"]
    base_dir = base_dir or os.getcwd()

    # ── 阻断项 ──
    if not (spec.get("subject") or "").strip():
        blocking.append(_item("subject_missing", "主题行缺失", "subject"))
    if "【待填" in (spec.get("to") or ""):
        blocking.append(_item("recipient_placeholder", "收件人仍是占位，未处理", "to"))

    if not spec.get("type"):
        warnings.append(_item("type_missing", "没有声明邮件类型，预设有按默认值处理的风险", "type"))

    placeholders: list[str] = []
    for where, value in _scan_source_strings(spec):
        for match in PLACEHOLDER_RE.finditer(value):
            if match.group(0) not in placeholders:
                placeholders.append(match.group(0))
            _add_unique(blocking, _item("placeholder", f"正文仍有占位：{match.group(0)}", where))
    for label, body in (("html", html_body), ("text", text_body), ("md", md_body)):
        match = PLACEHOLDER_RE.search(body)
        if match:
            _add_unique(
                blocking,
                _item("placeholder", f"输出里仍有占位：{match.group(0)}", label),
            )

    for where, value in _scan_source_strings(spec):
        match = VARIABLE_RE.search(value)
        if match:
            _add_unique(
                blocking,
                _item("unfilled_variable", f"变量未填：{match.group(0)}", where),
            )
            break

    for label, body in (("html", html_body), ("text", text_body), ("md", md_body)):
        for match in VARIABLE_RE.finditer(body):
            _add_unique(blocking, _item("unfilled_variable", f"变量未填：{match.group(0)}", label))
    blocking.extend(check_html_body(html_body))
    blocking.extend(check_quantities(spec))

    fact_tokens: list[tuple[str, Any, str]] = []
    for fact in spec.get("facts") or []:
        fact_tokens.extend(extract_tokens(fact))
    provenance_hits: list[str] = []
    for where, value in iter_text_fields(spec):
        for token in extract_tokens(value):
            if not _token_matches(token, fact_tokens):
                message = f"数字/日期无法溯源：{token[2]}"
                if message not in provenance_hits and len(provenance_hits) < 20:
                    provenance_hits.append(message)
                    blocking.append(_item("number_provenance", message, where))
    if len(provenance_hits) == 20:
        blocking.append(
            _item("number_provenance", "还有更多未溯源数字，已省略", "facts")
        )

    if html_body and text_body:
        html_tokens = {
            (kind, value)
            for kind, value, _ in extract_tokens(_strip_urls(_html_text(html_body)))
        }
        text_tokens = {
            (kind, value) for kind, value, _ in extract_tokens(_strip_urls(text_body))
        }
        only_html = sorted(html_tokens - text_tokens, key=str)
        only_text = sorted(text_tokens - html_tokens, key=str)
        if only_html or only_text:
            detail = []
            if only_html:
                detail.append(f"仅 HTML 有 {only_html[:3]}")
            if only_text:
                detail.append(f"仅纯文本有 {only_text[:3]}")
            blocking.append(
                _item("html_text_mismatch", "HTML 与纯文本的关键数字/日期不一致：" + "；".join(detail))
            )

    # ── 警告项 ──
    text_hits, body_chars = text_warnings(text_body, exclude_subject_line=True, kind=spec.get("type", ""))
    warnings.extend(text_hits)

    if not (spec.get("to") or "").strip():
        warnings.append(_item("recipient_missing", "未提供收件人，交付时给出建议", "to"))

    for where, value in iter_paragraphs(spec):
        lines = _estimate_lines(value)
        if lines > 4:
            warnings.append(
                _item("long_paragraph", f"段落约 {lines} 行，超过 4 行建议拆分", where)
            )

    for index, block in enumerate(spec.get("blocks") or [], start=1):
        if block["kind"] != "todo":
            continue
        for pos, item in enumerate(block.get("items") or [], start=1):
            if not item.get("owner") or not item.get("due"):
                warnings.append(
                    _item(
                        "todo_incomplete",
                        "待办缺少负责人或截止时间",
                        f"blocks[{index}].items[{pos}]",
                    )
                )

    total_bytes = 0
    for item in iter_images(spec):
        src = item["src"]
        if src.startswith(("http://", "https://", "data:")):
            continue
        path = src
        if src.startswith("file://"):
            from urllib.request import url2pathname

            path = url2pathname(src[len("file://") :])
        elif not os.path.isabs(path):
            path = os.path.join(base_dir, path)
        try:
            total_bytes += os.path.getsize(path)
        except OSError:
            warnings.append(_item("image_unreadable", f"本地图片不可读：{src}", src))
        warnings.append(
            _item(
                "image_local_path",
                "本地图片在 HTML 里按路径引用；发送前需上传，或改用 .eml 内嵌",
                src,
            )
        )
        content_width = int(tokens["width"]) - 2 * int(tokens["spacing"]["content"])
        if item.get("width") and item["width"] > content_width:
            warnings.append(
                _item("image_width", f"图片宽度 {item['width']}px 超过版心，已按版心输出", src)
            )
    if total_bytes > 1024 * 1024:
        warnings.append(
            _item("image_size", f"本地图片合计 {total_bytes / 1048576:.1f} MB，超过 1 MB", "images")
        )
    remote_images = [
        item["src"]
        for item in iter_images(spec)
        if item["src"].startswith(("http://", "https://"))
    ]
    if remote_images:
        skipped.append(f"{len(remote_images)} 张远程图片的大小未测量（无法访问）")

    if spec.get("placeholders"):
        warnings.append(
            _item(
                "declared_placeholders",
                f"Spec 声明了 {len(spec['placeholders'])} 项待补信息，交付清单需列出",
                "placeholders",
            )
        )

    report: dict[str, Any] = {
        "ok": not blocking,
        "blocking": blocking,
        "warnings": warnings,
        "skipped": skipped,
        "stats": {
            "chars": body_chars,
            "images": len(list(iter_images(spec))),
            "placeholders": placeholders,
            "facts": len(spec.get("facts") or []),
            "width": tokens["width"],
            "preset": tokens["name"],
        },
    }
    return report


def report_to_json(report: dict) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2)
