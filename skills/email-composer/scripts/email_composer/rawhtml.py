"""原始 HTML 模板：提取标题与纯文本、校验兼容性。

这是模板库的扩展类型：用户把现成 HTML 放进 `templates/html/`，用 `{{name}}` 标记变量。
它不经过内容 Spec，因此不做数字溯源，也不输出 Markdown；其余兼容规则与 Spec 模板一致。
"""

from __future__ import annotations

import html as html_lib
import re
from html.parser import HTMLParser

from . import validate

__all__ = ["auto_vars", "extract_title", "html_to_text", "validate_html_template"]

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "table", "ul", "ol", "blockquote"}
RAW_VAR_RE = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}")
BRACKET_RE = re.compile(r"【[^】]+】")


class _TextExtractor(HTMLParser):
    """把邮件 HTML 转成可读纯文本：保留段落、列表、表格单元与图片说明。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0
        self.cells = 0
        self.href: str | None = None

    def _newline(self, count: int = 1) -> None:
        if not self.parts:
            return
        if self.parts[-1].endswith("\n" * count):
            return
        self.parts.append("\n" * count)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in ("head", "style", "script", "title"):
            self.skip += 1
            return
        if self.skip:
            return
        values = dict(attrs)
        if tag in _BLOCK_TAGS:
            self._newline(2)
        elif tag == "tr":
            self._newline(1)
            self.cells = 0
        elif tag in ("td", "th"):
            if self.cells:
                self.parts.append(" | ")
            self.cells += 1
        elif tag == "li":
            self._newline(1)
            self.parts.append("- ")
        elif tag == "br":
            self._newline(1)
        elif tag == "img":
            alt = (values.get("alt") or "").strip()
            src = (values.get("src") or "").strip()
            self._newline(1)
            self.parts.append(f"[图片] {alt}".rstrip())
            if src:
                self._newline(1)
                self.parts.append(src)
            self._newline(1)
        elif tag == "a":
            self.href = values.get("href")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in ("head", "style", "script", "title"):
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in _BLOCK_TAGS:
            self._newline(2)
        elif tag == "tr":
            self._newline(1)
        elif tag == "li":
            self._newline(1)
        elif tag == "a" and self.href:
            self.parts.append(f"（{self.href}）")
            self.href = None

    def handle_data(self, data: str) -> None:
        if self.skip:
            return
        # 源码里的换行与缩进不是内容；块级换行由标签决定。
        text = re.sub(r"\s+", " ", data)
        if not text:
            return
        if text.strip() == "" and self.parts and self.parts[-1].endswith("\n"):
            return
        self.parts.append(text)


def extract_title(html_body: str) -> str:
    match = _TITLE_RE.search(html_body or "")
    if not match:
        return ""
    return html_lib.unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip()


def html_to_text(html_body: str) -> str:
    parser = _TextExtractor()
    parser.feed(html_body or "")
    parser.close()
    text = "".join(parser.parts).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def auto_vars(html_body: str) -> dict:
    """按 {{name}} 占位符自动声明变量；没有示例与说明。"""
    names = sorted(set(RAW_VAR_RE.findall(html_body or "")))
    return {
        name: {"required": True, "description": "", "example": ""}
        for name in names
    }


def validate_html_template(
    html_body: str, text_body: str, subject: str, to: str | None = None, cc: list[str] | None = None, kind: str = ""
) -> dict:
    """原始 HTML 模板的校验报告。结构与 Spec 校验保持一致。"""
    blocking = validate.check_html_body(html_body)
    if not (subject or "").strip():
        blocking.append(
            {"code": "subject_missing", "message": "主题行缺失（HTML <title> 为空）", "where": "title"}
        )
    placeholders: list[str] = []
    for match in validate.PLACEHOLDER_RE.finditer(html_body or ""):
        if match.group(0) not in placeholders:
            placeholders.append(match.group(0))
        blocking.append(
            {
                "code": "placeholder",
                "message": f"正文仍有占位：{match.group(0)}",
                "where": "html",
            }
        )
    variables = sorted(set(validate.VARIABLE_RE.findall(html_body or "")))
    for name in variables:
        blocking.append(
            {"code": "unfilled_variable", "message": "变量未填：" + name, "where": "html"}
        )
    for where, value in [("subject", subject), ("to", to or "")] + [("cc", v) for v in cc or []]:
        for pattern, code in ((validate.PLACEHOLDER_RE, "placeholder"), (validate.VARIABLE_RE, "unfilled_variable")):
            if pattern.search(value):
                blocking.append({"code": code, "message": f"{where} 仍有未填内容", "where": where})
    warnings, chars = validate.text_warnings(text_body, kind=kind)
    brackets = sorted(set(BRACKET_RE.findall(html_body or "")))
    if brackets:
        warnings.append(
            {
                "code": "bracket_placeholder",
                "message": "仍有【...】占位，可能是未转换的模板字段：" + "、".join(brackets[:5]),
                "where": "html",
            }
        )
    if not (to or "").strip():
        warnings.append(
            {"code": "recipient_missing", "message": "未提供收件人，交付时给出建议", "where": "to"}
        )
    images = validate.IMG_RE.findall(html_body or "")
    remote = [
        match
        for match in re.findall(r'<img\b[^>]*\bsrc="([^"]+)"', html_body or "", re.I)
        if match.startswith(("http://", "https://"))
    ]
    skipped = ["原始 HTML 模板不做数字溯源"]
    if remote:
        skipped.append(f"{len(remote)} 张远程图片的大小未测量（无法访问）")
    return {
        "ok": not blocking,
        "blocking": blocking,
        "warnings": warnings,
        "skipped": skipped,
        "stats": {
            "chars": chars,
            "images": len(images),
            "placeholders": placeholders,
            "facts": 0,
            "kind": "html",
        },
    }
