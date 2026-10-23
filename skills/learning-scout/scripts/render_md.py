"""Markdown rendering for learning-scout notes.

Preferred engine: markdown-it-py + Pygments (installed in `.venv/`).
Fallback: a small built-in renderer, used when the optional packages are absent.

Public API:
    render(markdown_text) -> (html, toc)
    CODE_CSS -> CSS for highlighted code blocks
    ENGINE -> "markdown-it" or "fallback"
"""

from __future__ import annotations

import html
import re
from typing import Iterable

try:  # optional dependency, installed by scripts/setup.sh
    from markdown_it import MarkdownIt
    from mdit_py_plugins.container import container_plugin
    from pygments import highlight as _pygments_highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import get_lexer_by_name

    _HAS_MDIT = True
except Exception:  # pragma: no cover - exercised on machines without deps
    _HAS_MDIT = False

ALERT_RE = re.compile(r"^>\s*\[!(note|tip|warning|caution|important)\]\s*(.*)$", re.IGNORECASE)
CODE_STYLE = "github-dark"
CODE_CSS = (
    HtmlFormatter(style=CODE_STYLE, cssclass="hl").get_style_defs(".hl")
    if _HAS_MDIT
    else ""
)


# --------------------------------------------------------------------------- #
# shared helpers
# --------------------------------------------------------------------------- #


def strip_frontmatter(text: str) -> str:
    lines = text.replace("\r\n", "\n").split("\n")
    if lines and lines[0].strip() == "---":
        for index in range(1, min(len(lines), 60)):
            if lines[index].strip() == "---":
                return "\n".join(lines[index + 1 :])
    return text


def slugify(value: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", value.strip().lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or "section"


def _slug_heading(text: str, used: dict[str, int]) -> str:
    base = slugify(re.sub(r"[`*_~]", "", text))
    count = used.get(base, 0) + 1
    used[base] = count
    return base if count == 1 else f"{base}-{count}"


def preprocess_alerts(text: str) -> str:
    """Turn GitHub-style alerts into container blocks understood by the renderer.

    > [!note] Title
    > body
    ->
    ::: callout-note
    **Title**

    body
    :::
    """
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        match = ALERT_RE.match(lines[i])
        if not match:
            out.append(lines[i])
            i += 1
            continue
        kind = match.group(1).lower()
        title = match.group(2).strip()
        out.append(f"::: callout-{kind}")
        if title:
            out.append(f"**{title}**")
            out.append("")
        i += 1
        while i < len(lines) and lines[i].lstrip().startswith(">"):
            out.append(re.sub(r"^\s*>\s?", "", lines[i]))
            i += 1
        out.append(":::")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# markdown-it engine
# --------------------------------------------------------------------------- #


def _build_engine() -> "MarkdownIt":
    def highlight(code: str, lang: str, attrs: str) -> str:
        language = (lang or "").strip() or "text"
        try:
            lexer = get_lexer_by_name(language)
            inner = _pygments_highlight(code, lexer, HtmlFormatter(nowrap=True, style=CODE_STYLE))
        except Exception:
            inner = html.escape(code)
        return f'<pre class="hl" data-lang="{html.escape(language, quote=True)}"><code>{inner}</code></pre>'

    md = MarkdownIt("commonmark", {"highlight": highlight, "html": False, "linkify": False})
    md.enable(["table", "strikethrough"])
    for name in ("callout-note", "callout-tip", "callout-warning", "callout-caution", "callout-important"):
        md.use(container_plugin, name=name)

    return md


_ENGINE = _build_engine() if _HAS_MDIT else None


def _decorate_links(tokens: Iterable) -> None:
    for token in tokens:
        if token.type != "inline" or not token.children:
            continue
        for child in token.children:
            if child.type == "link_open":
                href = child.attrGet("href") or ""
                if href.startswith(("http://", "https://")):
                    child.attrSet("rel", "noreferrer")
                    child.attrSet("target", "_blank")
            elif child.type == "image":
                child.attrSet("loading", "lazy")


def _collect_headings(tokens: Iterable) -> list[tuple[int, str, str]]:
    toc: list[tuple[int, str, str]] = []
    used: dict[str, int] = {}
    token_list = list(tokens)
    for index, token in enumerate(token_list):
        if token.type != "heading_open":
            continue
        level = int(token.tag[1])
        inline = token_list[index + 1] if index + 1 < len(token_list) else None
        text = (inline.content if inline is not None else "").strip()
        heading_id = _slug_heading(text, used)
        token.attrSet("id", heading_id)
        if 2 <= level <= 3 and text:
            toc.append((level, heading_id, re.sub(r"[`*_~]", "", text)))
    return toc


def _drop_h1(tokens: list) -> list:
    """The page header already renders the note title; drop level-1 headings."""
    kept: list = []
    skip = 0
    for token in tokens:
        if token.type == "heading_open" and token.tag == "h1":
            skip = 2  # inline + heading_close
            continue
        if skip:
            skip -= 1
            continue
        kept.append(token)
    return kept


def _render_mdit(text: str) -> tuple[str, list[tuple[int, str, str]]]:
    text = preprocess_alerts(strip_frontmatter(text))
    tokens = _drop_h1(_ENGINE.parse(text))
    _decorate_links(tokens)
    toc = _collect_headings(tokens)
    return _ENGINE.renderer.render(tokens, _ENGINE.options, {}), toc


# --------------------------------------------------------------------------- #
# fallback engine (no dependencies)
# --------------------------------------------------------------------------- #


def _inline(text: str) -> str:
    out = html.escape(text, quote=False)

    def code(match: re.Match[str]) -> str:
        return f"<code>{match.group(1)}</code>"

    out = re.sub(r"`([^`]+)`", code, out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", out)

    def image(match: re.Match[str]) -> str:
        alt, url = match.group(1), match.group(2)
        if not url.lower().startswith(("http://", "https://", "./", "../")):
            return match.group(0)
        return f'<img src="{url}" alt="{alt}" loading="lazy" />'

    def link(match: re.Match[str]) -> str:
        label, url = match.group(1), match.group(2)
        if not url.lower().startswith(("http://", "https://", "./", "#", "../")):
            return match.group(0)
        return f'<a href="{url}" rel="noreferrer">{label}</a>'

    out = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", image, out)
    out = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, out)
    return out


def _render_fallback(text: str) -> tuple[str, list[tuple[int, str, str]]]:
    lines = strip_frontmatter(text).replace("\r\n", "\n").split("\n")
    blocks: list[str] = []
    toc: list[tuple[int, str, str]] = []
    used: dict[str, int] = {}
    i = 0
    para: list[str] = []

    def flush() -> None:
        if para:
            blocks.append(f"<p>{_inline(' '.join(para))}</p>")
            para.clear()

    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            flush()
            lang = line[3:].strip() or "text"
            i += 1
            code: list[str] = []
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            blocks.append(f'<pre class="hl" data-lang="{html.escape(lang)}"><code>{html.escape(chr(10).join(code))}</code></pre>')
            continue
        if re.match(r"^#{1,6}\s", line):
            flush()
            level = len(line) - len(line.lstrip("#"))
            title = line[level:].strip()
            if level > 1:
                heading_id = _slug_heading(title, used)
                if level <= 3:
                    toc.append((level, heading_id, re.sub(r"[`*_~]", "", title)))
                blocks.append(f'<h{level} id="{heading_id}">{_inline(title)}</h{level}>')
            i += 1
            continue
        if line.startswith(">"):
            flush()
            quote: list[str] = []
            while i < len(lines) and lines[i].startswith(">"):
                quote.append(lines[i].lstrip(">").lstrip())
                i += 1
            blocks.append(f"<blockquote>{_render_fallback(chr(10).join(quote))[0]}</blockquote>")
            continue
        if re.match(r"^\s*\|.*\|\s*$", line):
            flush()
            rows: list[list[str]] = []
            while i < len(lines) and re.match(r"^\s*\|.*\|\s*$", lines[i]):
                rows.append([cell.strip() for cell in lines[i].strip().strip("|").split("|")])
                i += 1
            if rows:
                header, *body = rows
                if body and all(re.fullmatch(r":?-{2,}:?", cell.replace(" ", "")) for cell in body[0]):
                    body = body[1:]
                markup = ['<div class="table-wrap"><table><thead><tr>']
                markup += [f"<th>{_inline(cell)}</th>" for cell in header]
                markup.append("</tr></thead><tbody>")
                for row in body:
                    markup.append("<tr>" + "".join(f"<td>{_inline(cell)}</td>" for cell in row) + "</tr>")
                markup.append("</tbody></table></div>")
                blocks.append("".join(markup))
            continue
        if re.match(r"^\s*([-*+]|\d+\.)\s+", line):
            flush()
            ordered = bool(re.match(r"^\s*\d+\.\s+", line))
            items: list[str] = []
            while i < len(lines) and re.match(r"^\s*([-*+]|\d+\.)\s+", lines[i]):
                items.append(f"<li>{_inline(re.sub(r'^\\s*([-*+]|\\d+\\.)\\s+', '', lines[i]))}</li>")
                i += 1
            tag = "ol" if ordered else "ul"
            blocks.append(f"<{tag}>" + "".join(items) + f"</{tag}>")
            continue
        if not line.strip():
            flush()
            i += 1
            continue
        para.append(line.strip())
        i += 1
    flush()
    return "\n".join(blocks), toc


# --------------------------------------------------------------------------- #
# public
# --------------------------------------------------------------------------- #


def render(markdown_text: str) -> tuple[str, list[tuple[int, str, str]]]:
    if _ENGINE is not None:
        return _render_mdit(markdown_text)
    return _render_fallback(markdown_text)


ENGINE = "markdown-it" if _ENGINE is not None else "fallback"
