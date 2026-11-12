"""渲染：Spec + 样式令牌 → HTML / 纯文本 / Markdown / .eml。"""

from __future__ import annotations

import html as html_lib
import mimetypes
import os
import re
from datetime import date
from email import policy
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
from . import ASSETS, blocks
from .htmltools import Tags
from .spec import filename_base, type_label
from .styles import describe

__all__ = [
    "render_html",
    "render_text",
    "render_markdown",
    "render_eml",
    "build_eml",
    "embed_images",
    "build_outputs",
    "parse_formats",
    "ALL_FORMATS",
]

ALL_FORMATS = ("html", "text", "md", "eml")
_DEFAULT_BASE = None


def parse_formats(raw: str) -> tuple[str, ...]:
    if raw.strip() in ("all", "全部"):
        return ALL_FORMATS
    items = tuple(item.strip() for item in raw.split(",") if item.strip())
    unknown = [item for item in items if item not in ALL_FORMATS]
    if unknown:
        raise ValueError(f"未知格式：{', '.join(unknown)}；可用：{', '.join(ALL_FORMATS)}")
    if not items:
        raise ValueError("至少选择一种输出格式")
    return items


def _base_template() -> str:
    global _DEFAULT_BASE
    if _DEFAULT_BASE is None:
        with open(os.path.join(ASSETS, "base.html"), encoding="utf-8") as handle:
            _DEFAULT_BASE = handle.read()
    return _DEFAULT_BASE


def _title_html(subject: str, tokens: dict) -> str:
    color = tokens["color"]
    style = (
        f"margin:0 0 16px;font-family:{tokens['font']['family']};"
        f"font-size:{tokens['heading']['size']}px;line-height:1.4;font-weight:600;"
        f"color:{color['text']};"
    )
    if tokens["heading"]["bar"]:
        style += f"border-left:4px solid {color['accent']};padding-left:12px;"
    return f'<h1 style="{style}">{blocks.esc(subject)}</h1>'


def _band_html(spec: dict, tokens: dict) -> str:
    band = tokens["band"]
    if not band["enabled"]:
        return ""
    label = "紧急" if spec.get("urgent") else (type_label(spec) or "提醒")
    return (
        f'<tr><td style="background-color:{band["color"]};padding:10px 28px;'
        f'color:{band["text"]};font-family:{tokens["font"]["family"]};font-size:13px;'
        f'line-height:1.5;">{blocks.esc(label)}</td></tr>'
    )


def _container(spec: dict, tokens: dict, inner: str) -> str:
    color = tokens["color"]
    border = (
        f"border:1px solid {color['border']};" if tokens["frame"]["border"] else ""
    )
    return (
        f'<table role="presentation" width="{tokens["width"]}" cellpadding="0" '
        f'cellspacing="0" border="0" style="width:{tokens["width"]}px;'
        f'max-width:{tokens["width"]}px;background-color:{color["background"]};{border}'
        f'border-collapse:collapse;">{_band_html(spec, tokens)}'
        f'<tr><td style="padding:{tokens["spacing"]["content"]}px;">{inner}</td></tr>'
        f"</table>"
    )


def render_html(spec: dict, tokens: dict) -> str:
    """渲染完整 HTML。.eml 内嵌图片在整段 HTML 上替换。"""
    color = tokens["color"]
    parts = [_title_html(spec["subject"], tokens)]
    if spec.get("greeting"):
        parts.append(
            f'<p style="margin:0 0 12px;font-family:{tokens["font"]["family"]};'
            f'font-size:{tokens["font"]["size"]}px;line-height:'
            f'{tokens["font"]["line_height"]};color:{color["text"]};">'
            f"{blocks.esc(spec['greeting'])}</p>"
        )
    if spec.get("summary"):
        parts.append(blocks.html({"kind": "summary", "text": spec["summary"]}, tokens))
    for block in spec.get("blocks") or []:
        parts.append(blocks.html(block, tokens))
    inner = "".join(parts)
    page = _base_template()
    for token, value in (
        ("@@LANG@@", "zh-CN"),
        ("@@TITLE@@", blocks.esc(spec["subject"])),
        ("@@PAGE_BG@@", color["page"]),
        ("@@PAGE_PAD@@", str(tokens["spacing"]["page"])),
        ("@@BODY@@", _container(spec, tokens, inner)),
    ):
        page = page.replace(token, value)
    return page


def render_text(spec: dict) -> str:
    """渲染纯文本：标题用【】，表格转成「字段：值」列表，链接单独成行。"""
    parts = [f"【主题】{spec['subject']}"]
    if spec.get("greeting"):
        parts.append(spec["greeting"])
    if spec.get("summary"):
        parts.append(spec["summary"])
    for block in spec.get("blocks") or []:
        parts.append(blocks.text(block))
    body = "\n\n".join(part for part in parts if part != "")
    while "\n\n\n" in body:
        body = body.replace("\n\n\n", "\n\n")
    return body.strip() + "\n"


def render_markdown(spec: dict) -> str:
    """渲染 Markdown 源稿，保留结构便于二次编辑。"""
    parts = [f"# {spec['subject']}"]
    if spec.get("greeting"):
        parts.append(spec["greeting"])
    if spec.get("summary"):
        parts.append(blocks.markdown({"kind": "summary", "text": spec["summary"]}))
    for block in spec.get("blocks") or []:
        parts.append(blocks.markdown(block))
    body = "\n\n".join(part for part in parts if part != "")
    while "\n\n\n" in body:
        body = body.replace("\n\n\n", "\n\n")
    return body.strip() + "\n"


def _is_remote(src: str) -> bool:
    return src.startswith(("http://", "https://", "data:", "cid:"))


def _local_path(src: str, base_dir: str) -> str:
    if src.startswith("file://"):
        from urllib.request import url2pathname

        return url2pathname(src[len("file://") :])
    if os.path.isabs(src):
        return src
    return os.path.join(base_dir, src)


def embed_images(html_body: str, base_dir: str) -> tuple[str, list[dict], list[str]]:
    """Resolve local image sources regardless of HTML attribute quoting."""
    attachments, notes, changes = [], [], []
    seen = {}
    for tag, attrs, raw, start in Tags(html_body).tags:
        src = dict(attrs).get("src")
        if tag != "img" or not src or _is_remote(src):
            continue
        if src not in seen:
            path = _local_path(src, base_dir)
            try:
                with open(path, "rb") as handle:
                    data = handle.read()
            except OSError:
                notes.append(f"图片无法读取，.eml 中保留原地址：{src}")
                continue
            cid = f"img{len(attachments) + 1}@email-composer"
            seen[src] = f"cid:{cid}"
            attachments.append({"cid": cid, "data": data, "path": path})
        values = [(key, seen[src] if key == "src" else value) for key, value in attrs]
        replacement = "<img " + " ".join(key if value is None else
            f'{key}="{html_lib.escape(value, quote=True)}"' for key, value in values) + ">"
        changes.append((start, start + len(raw), replacement))
    for start, end, replacement in reversed(changes):
        html_body = html_body[:start] + replacement + html_body[end:]
    return html_body, attachments, notes


def build_eml(
    subject: str,
    html_body: str,
    text_body: str,
    base_dir: str,
    to: str | None = None,
    cc: list[str] | None = None,
) -> tuple[bytes, list[str]]:
    """生成可直接用 Outlook / Foxmail 打开的 .eml；本地图片以 cid 内嵌。"""
    html_body, attachments, notes = embed_images(html_body, base_dir)
    alternative = MIMEMultipart("alternative")
    alternative.attach(MIMEText(text_body, "plain", "utf-8"))
    alternative.attach(MIMEText(html_body, "html", "utf-8"))
    if attachments:
        root = MIMEMultipart("related")
        root.attach(alternative)
    else:
        root = alternative
    root["Subject"] = subject
    if to:
        root["To"] = to
    if cc:
        root["Cc"] = ", ".join(cc)
    root["Date"] = formatdate(localtime=True)
    for item in attachments:
        mime, _ = mimetypes.guess_type(item["path"])
        subtype = mime.split("/")[-1] if mime and mime.startswith("image/") else "png"
        part = MIMEImage(item["data"], _subtype=subtype)
        part.add_header("Content-ID", f"<{item['cid']}>")
        part.add_header(
            "Content-Disposition", "inline", filename=os.path.basename(item["path"])
        )
        root.attach(part)
    return root.as_bytes(policy=policy.SMTP), notes


def render_eml(spec: dict, tokens: dict, base_dir: str) -> tuple[bytes, list[str]]:
    """Spec 模板的 .eml。"""
    return build_eml(
        spec["subject"],
        render_html(spec, tokens),
        render_text(spec),
        base_dir,
        spec.get("to"),
        spec.get("cc"),
    )


def build_outputs(
    spec: dict,
    tokens: dict,
    base_dir: str,
    formats: tuple[str, ...] = ("html", "text", "md"),
    day: date | None = None,
    name: str | None = None,
) -> tuple[dict[str, tuple[str, str | bytes]], list[str]]:
    """生成所有选定格式，返回 {格式: (文件名, 内容)} 与提示。"""
    unknown = [item for item in formats if item not in ALL_FORMATS]
    if unknown:
        raise ValueError(f"未知格式：{', '.join(unknown)}；可用：{', '.join(ALL_FORMATS)}")
    base = filename_base(spec["subject"], day=day, name=name)
    outputs: dict[str, tuple[str, str | bytes]] = {}
    notes: list[str] = []
    if "html" in formats:
        outputs["html"] = (f"{base}.html", render_html(spec, tokens))
    if "text" in formats:
        outputs["text"] = (f"{base}.txt", render_text(spec))
    if "md" in formats:
        outputs["md"] = (f"{base}.md", render_markdown(spec))
    if "eml" in formats:
        content, eml_notes = render_eml(spec, tokens, base_dir)
        outputs["eml"] = (f"{base}.eml", content)
        notes.extend(eml_notes)
    return outputs, notes


def style_summary(tokens: dict) -> str:
    """给 CLI / C2 用的一句话说明。"""
    return describe(tokens)
