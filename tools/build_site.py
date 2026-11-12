#!/usr/bin/env python3
"""生成 Agent Skills 项目子站：项目首页 + docs 页面。

站点输出是一个自包含的静态目录，部署在 https://huangrx6.github.io/agent-skills/。
页面链接全部使用相对路径，因此同一份产物也能用本地 HTTP 服务预览。

用法：
    python3 tools/build_site.py --out <目录>
    python3 tools/build_site.py --out /tmp/site --check

依赖 markdown-it-py（见 tools/site/requirements.txt）。没有它时明确报错，不生成半个站点。
"""

from __future__ import annotations

import argparse
import html
import posixpath
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import quote

try:
    from markdown_it import MarkdownIt
except ImportError:  # pragma: no cover - 环境缺依赖时给出可执行的提示
    print(
        "错误：需要 markdown-it-py。\n"
        "  python3 -m pip install -r tools/site/requirements.txt",
        file=sys.stderr,
    )
    raise SystemExit(2)

ROOT = Path(__file__).resolve().parents[1]
SITE_DIR = ROOT / "tools" / "site"
TEMPLATES = SITE_DIR / "templates"
ASSETS = SITE_DIR / "assets"

REPO = "https://github.com/huangrx6/agent-skills"
RAW = "https://raw.githubusercontent.com/huangrx6/agent-skills/main"
BLOB = f"{REPO}/blob/main"
SITE_URL = "https://huangrx6.github.io/agent-skills/"
SITE_NAME = "Agent Skills"
SITE_DESC = (
    "10 个可独立安装的 Agent skill：演示文稿、技术图、COSMIC、Obsidian、Git、"
    "PingCode、学习路线与邮件。每个 skill 都带入口说明、可执行脚本和回归测试。"
)

SKILL_ROW_RE = re.compile(
    r"^\|\s*\[\*\*(?P<name>[^*]+)\*\*\]"
    r"\(skills/(?P<slug>[^/]+)/README\.md\)\s*\|\s*(?P<what>.+?)\s*\|\s*(?P<output>.+?)\s*\|\s*$"
)
HEADING_RE = re.compile(r"<h([1-6])>(.*?)</h\1>", re.S)
ATTR_RE = re.compile(r'(?P<attr>href|src)=(?P<q>["\'])(?P<url>.*?)(?P=q)', re.S)
LEFTOVER_TOKEN_RE = re.compile(r"@@[A-Z_]+@@")


class SiteError(ValueError):
    """内容或模板不满足生成条件。"""


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def join_cjk(text: str) -> str:
    text = re.sub(r"\s*\n\s*", " ", text)
    text = re.sub(r"(?<=[\u4e00-\u9fff。；，、！？：])\s+(?=[\u4e00-\u9fff])", "", text)
    text = re.sub(r"\s+([，。；：！？、])", r"\1", text)
    return text.strip()


def strip_inline_md(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text


def slugify(text: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text.strip().lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or "section"


def paths(kind: str) -> dict:
    """相对前缀。kind: landing / docs / skills。"""
    if kind == "landing":
        return {"assets": "assets/", "docs": "docs/", "project": "", "home": "../"}
    if kind == "docs":
        return {"assets": "../assets/", "docs": "", "project": "../", "home": "../../"}
    return {"assets": "../../assets/", "docs": "../", "project": "../../", "home": "../../../"}


def fill(template: str, tokens: dict) -> str:
    for key, value in tokens.items():
        template = template.replace(f"@@{key}@@", str(value))
    return template


def build_markdown() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": True, "linkify": False, "typographer": False})
    md.enable("table")
    md.enable("strikethrough")
    md.renderer.rules["table_open"] = lambda *args: '<div class="table-wrap"><table>'
    md.renderer.rules["table_close"] = lambda *args: "</table></div>"
    return md


MD = build_markdown()


def split_h1(text: str) -> tuple[str, str]:
    match = re.search(r"^#\s+(.+)$", text, re.M)
    if not match:
        raise SiteError("Markdown 缺少一级标题")
    title = match.group(1).strip()
    body = text[: match.start()] + text[match.end() :]
    return title, body


def take_blockquote(body: str) -> tuple[str, str]:
    lines = body.lstrip("\n").split("\n")
    if not lines or not lines[0].startswith(">"):
        return "", body
    quote: list[str] = []
    index = 0
    while index < len(lines) and lines[index].startswith(">"):
        quote.append(lines[index].lstrip(">").strip())
        index += 1
    while index < len(lines) and not lines[index].strip():
        index += 1
    return join_cjk(strip_inline_md("\n".join(quote))), "\n".join(lines[index:])


def take_first_paragraph(body: str) -> tuple[str, str]:
    lines = body.lstrip("\n").split("\n")
    if not lines or not lines[0].strip():
        return "", body
    first = lines[0].lstrip()
    if first.startswith(("#", "-", "*", "|", "<", ">", "`")) or re.match(r"^\d+\.\s", first):
        return "", body
    paragraph: list[str] = []
    index = 0
    while index < len(lines) and lines[index].strip() and not lines[index].startswith(("#", "```")):
        paragraph.append(lines[index].strip())
        index += 1
    while index < len(lines) and not lines[index].strip():
        index += 1
    return join_cjk(strip_inline_md("\n".join(paragraph))), "\n".join(lines[index:])


def strip_toc_details(body: str) -> str:
    return re.sub(
        r"<details>\s*<summary><strong>目录</strong></summary>.*?</details>\s*",
        "",
        body,
        flags=re.S,
    )


def parse_skills(root_readme: str) -> list[dict]:
    categories: list[dict] = []
    current: dict | None = None
    in_skills = False
    for line in root_readme.split("\n"):
        if line.startswith("## "):
            in_skills = line.strip() == "## Skills"
            continue
        if not in_skills:
            continue
        if line.startswith("### "):
            current = {"name": line[4:].strip(), "skills": []}
            categories.append(current)
            continue
        match = SKILL_ROW_RE.match(line.strip())
        if match and current is not None:
            current["skills"].append(
                {
                    "name": match.group("slug").strip(),
                    "what": match.group("what").strip(),
                    "output": match.group("output").strip(),
                }
            )
    if not categories:
        raise SiteError("根 README 里没有找到 Skill 分类表")
    return categories


def load_skills() -> tuple[str, list[dict]]:
    root_readme = read(ROOT / "README.md")
    categories = parse_skills(root_readme)
    for category in categories:
        for item in category["skills"]:
            readme_path = ROOT / "skills" / item["name"] / "README.md"
            if not readme_path.is_file():
                raise SiteError(f"skill 缺少 README：{readme_path}")
            title, body = split_h1(read(readme_path))
            lead, body = take_blockquote(body)
            body = strip_toc_details(body)
            subtitle = title.split("·", 1)[1].strip() if "·" in title else ""
            item.update(
                {
                    "title": title,
                    "subtitle": subtitle,
                    "lead": lead or item["what"],
                    "body": body,
                    "category": category["name"],
                }
            )
    return root_readme, categories


def github_blob(path: str) -> str:
    return f"{BLOB}/{quote(path, safe='/')}"


def rewrite_links(html_text: str, base_path: str, link_mode: str) -> str:
    def replace(match: re.Match) -> str:
        attr = match.group("attr")
        quote_char = match.group("q")
        url = html.unescape(match.group("url")).strip()
        if not url or url.startswith(
            ("#", "/", "http://", "https://", "mailto:", "tel:", "data:", "//")
        ):
            return match.group(0)
        raw_path, sep, fragment = url.partition("#")
        if not raw_path:
            return match.group(0)
        resolved = posixpath.normpath(
            posixpath.join(base_path, raw_path) if base_path else raw_path
        )
        if resolved.startswith(".."):
            new = REPO
        elif attr == "src":
            new = f"{RAW}/{quote(resolved, safe='/')}"
        elif link_mode == "root":
            skill_match = re.fullmatch(r"skills/([^/]+)/README\.md", resolved)
            if skill_match:
                new = f"skills/{skill_match.group(1)}.html"
            elif resolved == "ROADMAP.md":
                new = "roadmap.html"
            elif resolved == "README.md":
                new = "../index.html"
            else:
                new = github_blob(resolved)
        else:
            new = github_blob(resolved)
        if sep and attr == "href":
            new = f"{new}#{fragment}"
        return f"{attr}={quote_char}{html.escape(new, quote=True)}{quote_char}"

    return ATTR_RE.sub(replace, html_text)


def add_heading_ids(html_text: str) -> tuple[str, list[tuple[int, str, str]]]:
    used: dict[str, int] = {}
    toc: list[tuple[int, str, str]] = []

    def replace(match: re.Match) -> str:
        level = int(match.group(1))
        inner = match.group(2)
        text = html.unescape(re.sub(r"<[^>]+>", "", inner)).strip()
        base = slugify(text)
        count = used.get(base, 0) + 1
        used[base] = count
        heading_id = base if count == 1 else f"{base}-{count}"
        if level in (2, 3):
            toc.append((level, heading_id, text))
        return f'<h{level} id="{heading_id}">{inner}</h{level}>'

    return HEADING_RE.sub(replace, html_text), toc


def preprocess_alerts(text: str) -> str:
    """把 GitHub 的 > [!NOTE] 转成带中文标签的引用块。"""
    labels = {
        "NOTE": "注意",
        "TIP": "提示",
        "WARNING": "注意",
        "CAUTION": "谨慎",
        "IMPORTANT": "重要",
    }
    pattern = re.compile(r"^>\s*\[!(NOTE|TIP|WARNING|CAUTION|IMPORTANT)\]\s*$", re.I)
    lines = text.split("\n")
    out: list[str] = []
    index = 0
    while index < len(lines):
        match = pattern.match(lines[index])
        if not match:
            out.append(lines[index])
            index += 1
            continue
        out.append(f"> **{labels[match.group(1).upper()]}**")
        out.append(">")
        index += 1
        while index < len(lines) and lines[index].startswith(">"):
            out.append(lines[index])
            index += 1
    return "\n".join(out)


def render_markdown(
    text: str, base_path: str, link_mode: str
) -> tuple[str, list[tuple[int, str, str]]]:
    rendered = MD.render(preprocess_alerts(text))
    rendered = rewrite_links(rendered, base_path, link_mode)
    return add_heading_ids(rendered)


def extract_section(markdown: str, name: str) -> str:
    match = re.search(rf"^##\s+{re.escape(name)}\s*$", markdown, re.M)
    if not match:
        raise SiteError(f"根 README 缺少章节：## {name}")
    rest = markdown[match.end() :]
    next_match = re.search(r"^##\s+", rest, re.M)
    end = match.end() + next_match.start() if next_match else len(markdown)
    return markdown[match.start() : end].strip() + "\n"


def header(kind: str, active: str) -> str:
    prefix = paths(kind)
    brand_href = f"{prefix['project']}index.html"
    links = [
        ("docs", f"{prefix['docs']}index.html", "文档"),
        ("skills", f"{prefix['docs']}skills/index.html", "Skills"),
        ("guide", f"{prefix['docs']}guide.html", "编写 Skill"),
    ]
    nav = []
    for key, href, label in links:
        current = ' aria-current="page"' if active == key else ""
        nav.append(f'<a href="{href}"{current}>{label}</a>')
    external = (
        f'<a class="nav-github" href="{REPO}" target="_blank" rel="noreferrer">'
        "GitHub"
        '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 17 17 7M9 7h8v8" '
        'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
        'stroke-linejoin="round"/></svg></a>'
    )
    theme = (
        '<button class="theme-toggle" type="button" data-theme-toggle '
        'aria-label="切换白天/夜间模式" title="切换白天/夜间">'
        '<span class="when-light">'
        '<svg viewBox="0 0 24 24" aria-hidden="true">'
        '<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a7 7 0 1 0 10.5 10.5Z" '
        'fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>'
        "</svg>夜间</span>"
        '<span class="when-dark">'
        '<svg viewBox="0 0 24 24" aria-hidden="true">'
        '<circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" stroke-width="1.7"/>'
        '<path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4'
        'M17.3 17.3l1.4 1.4M18.7 5.3l-1.4 1.4M6.7 17.3l-1.4 1.4" '
        'fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>'
        "</svg>白天</span>"
        "</button>"
    )
    return f"""<header class="site-header">
  <div class="wrap header-inner">
    <a class="brand" href="{brand_href}">
      <svg class="brand-mark" viewBox="0 0 24 24" aria-hidden="true">
        <rect x="2" y="2" width="8" height="8" rx="2" fill="currentColor"/>
        <rect x="14" y="2" width="8" height="8" rx="2" fill="currentColor"/>
        <rect x="2" y="14" width="8" height="8" rx="2" fill="currentColor"/>
        <rect x="14" y="14" width="8" height="8" rx="2" fill="currentColor" opacity=".45"/>
      </svg>
      <span>Agent Skills</span>
    </a>
    <div class="header-tools">
      <nav class="site-nav" id="site-nav" aria-label="主导航">
        {"".join(nav)}
        {external}
      </nav>
      {theme}
      <button class="nav-toggle" type="button" aria-expanded="false" aria-controls="site-nav" aria-label="打开导航">
        <span></span><span></span>
      </button>
    </div>
  </div>
</header>"""


def footer(kind: str, count: int) -> str:
    prefix = paths(kind)
    return f"""<footer class="site-footer">
  <div class="wrap footer-inner">
    <p>Agent Skills · {count} 个可独立安装的 skill</p>
    <nav aria-label="页脚">
      <a href="{prefix['docs']}index.html">文档</a>
      <a href="{REPO}" target="_blank" rel="noreferrer">GitHub</a>
      <a href="{prefix['home']}">huangrx6.github.io</a>
    </nav>
  </div>
</footer>"""


def sidebar(active: str, categories: list[dict], kind: str) -> str:
    prefix = paths(kind)
    docs_links = [
        ("docs-index", "index.html", "文档首页"),
        ("getting-started", "getting-started.html", "开始使用"),
        ("skills", "skills/index.html", "Skill 目录"),
        ("guide", "guide.html", "编写 Skill"),
        ("maintenance", "maintenance.html", "维护与验证"),
        ("roadmap", "roadmap.html", "路线图"),
    ]
    rows = [
        '<aside class="docs-sidebar" id="docs-sidebar">',
        '<nav aria-label="文档导航">',
        '<p class="side-label">文档</p>',
    ]
    for key, href, label in docs_links:
        current = ' class="is-active" aria-current="page"' if active == key else ""
        rows.append(f'<a href="{prefix["docs"]}{href}"{current}>{label}</a>')
    rows.append('<p class="side-label">Skills</p>')
    for category in categories:
        rows.append(f'<p class="side-cat">{esc(category["name"])}</p>')
        for item in category["skills"]:
            key = f"skill:{item['name']}"
            current = ' class="is-active" aria-current="page"' if active == key else ""
            rows.append(
                f'<a href="{prefix["docs"]}skills/{item["name"]}.html"{current}>'
                f"{esc(item['name'])}</a>"
            )
    rows.extend(["</nav>", "</aside>"])
    return "\n".join(rows)


def crumbs(items: list[tuple[str, str | None]]) -> str:
    parts = ['<nav class="crumbs" aria-label="面包屑">']
    for index, (label, href) in enumerate(items):
        if index:
            parts.append('<span aria-hidden="true">/</span>')
        if href:
            parts.append(f'<a href="{href}">{esc(label)}</a>')
        else:
            parts.append(f'<span aria-current="page">{esc(label)}</span>')
    parts.append("</nav>")
    return "".join(parts)


def toc_html(toc: list[tuple[int, str, str]]) -> str:
    if len(toc) < 2:
        return ""
    items = "".join(
        f'<li class="toc-{level}"><a href="#{heading_id}">{esc(text)}</a></li>'
        for level, heading_id, text in toc
    )
    return (
        '<aside class="docs-toc" aria-label="本页目录">'
        '<p class="side-label">本页目录</p>'
        f"<ul>{items}</ul></aside>"
    )


def page_nav(prev: dict | None, next_page: dict | None, kind: str) -> str:
    prefix = paths(kind)

    def link(item: dict | None, direction: str, label: str) -> str:
        if not item:
            return '<span class="placeholder"></span>'
        href = f"{prefix['docs']}{item['href']}"
        cls = "page-nav-link next" if direction == "next" else "page-nav-link"
        return (
            f'<a class="{cls}" href="{href}"><span>{label}</span>'
            f"<strong>{esc(item['label'])}</strong></a>"
        )

    return (
        '<nav class="page-nav" aria-label="上一篇与下一篇">'
        f"{link(prev, 'prev', '上一篇')}{link(next_page, 'next', '下一篇')}"
        "</nav>"
    )


def layout(
    *,
    title: str,
    description: str,
    canonical: str,
    body_class: str,
    header_html: str,
    body: str,
    footer_html: str,
    assets_prefix: str,
) -> str:
    template = read(TEMPLATES / "layout.html")
    return fill(
        template,
        {
            "TITLE": esc(title),
            "DESCRIPTION": esc(description),
            "CANONICAL": esc(canonical),
            "BODY_CLASS": body_class,
            "BASE": assets_prefix,
            "HEADER": header_html,
            "BODY": body,
            "FOOTER": footer_html,
        },
    )


def docs_page(
    *,
    title: str,
    lead: str,
    content_html: str,
    toc: list[tuple[int, str, str]],
    canonical: str,
    active: str,
    header_active: str,
    categories: list[dict],
    kind: str,
    crumb_items: list[tuple[str, str | None]],
    meta_html: str,
    nav_html: str,
    count: int,
    eyebrow: str = "文档",
) -> str:
    toc_markup = toc_html(toc)
    shell_class = "has-toc" if toc_markup else ""
    docs_template = read(TEMPLATES / "docs.html")
    body = fill(
        docs_template,
        {
            "SHELL_CLASS": shell_class,
            "SIDEBAR": sidebar(active, categories, kind),
            "CRUMBS": crumbs(crumb_items),
            "EYEBROW": eyebrow,
            "PAGE_TITLE": esc(title),
            "LEAD": f'<p class="page-lede">{esc(lead)}</p>' if lead else "",
            "META": meta_html,
            "CONTENT": content_html,
            "TOC": toc_markup,
            "PAGE_NAV": nav_html,
        },
    )
    return layout(
        title=f"{title} · {SITE_NAME}",
        description=lead or SITE_DESC,
        canonical=canonical,
        body_class="docs",
        header_html=header(kind, header_active),
        body=body,
        footer_html=footer(kind, count),
        assets_prefix=paths(kind)["assets"],
    )


def meta_links(items: list[tuple[str, str]]) -> str:
    parts = []
    for label, href in items:
        parts.append(f'<a href="{href}" target="_blank" rel="noreferrer">{label}</a>')
    return '<div class="page-meta">' + '<span aria-hidden="true">·</span>'.join(parts) + "</div>"


def skill_groups(
    categories: list[dict], href_prefix: str, level: int
) -> str:
    tag = f"h{level}"
    groups = []
    for category in categories:
        cards = "".join(
            f"""<a class="skill-card" href="{href_prefix}{item["name"]}.html">
  <div class="skill-card-head">
    <span class="skill-id">{esc(item["name"] if item["subtitle"] else "")}</span>
    <span class="skill-arrow" aria-hidden="true">→</span>
  </div>
  <h4>{esc(item["subtitle"] or item["name"])}</h4>
  <p>{esc(item["what"])}</p>
  <span class="skill-output">{esc(item["output"])}</span>
</a>"""
            for item in category["skills"]
        )
        groups.append(
            f'<div class="skill-group"><div class="group-head"><{tag}>{esc(category["name"])}</{tag}>'
            f"<span>{len(category['skills'])}</span></div>"
            f'<div class="skill-grid">{cards}</div></div>'
        )
    return "\n".join(groups)


def build_landing(categories: list[dict], count: int) -> str:
    template = read(TEMPLATES / "home.html")
    body = fill(
        template,
        {
            "SKILL_COUNT": count,
            "SKILL_GROUPS": skill_groups(categories, "docs/skills/", 3),
        },
    )
    return layout(
        title="Agent Skills — 可执行、可验证的 Agent skill",
        description=SITE_DESC,
        canonical=SITE_URL,
        body_class="home",
        header_html=header("landing", ""),
        body=body,
        footer_html=footer("landing", count),
        assets_prefix=paths("landing")["assets"],
    )


def build_docs_index(categories: list[dict], count: int) -> str:
    cards = [
        ("01", "开始使用", "getting-started.html", "安装到 agent 的发现目录，确认配置，然后从一条真实需求开始。"),
        ("02", "Skill 目录", "skills/index.html", "按场景浏览 10 个 skill，查看各自的输入、产物与边界。"),
        ("03", "编写 Skill", "guide.html", "从触发描述、最小流程到验证与交付，写一个能执行的 skill。"),
        ("04", "维护与验证", "maintenance.html", "结构检查、回归测试、锁文件与站点构建各自证明什么。"),
        ("05", "路线图", "roadmap.html", "当前优先解决的问题与后续扩展方向。"),
    ]
    content = '<div class="doc-cards">' + "".join(
        f'<a class="doc-card" href="{href}"><div class="doc-card-head"><span>{num}</span>'
        f'<span class="arrow" aria-hidden="true">→</span></div><h2>{esc(title)}</h2>'
        f'<p>{esc(desc)}</p></a>'
        for num, title, href, desc in cards
    ) + "</div>"
    getting_started = {"href": "getting-started.html", "label": "开始使用"}
    return docs_page(
        title="文档",
        lead="从安装到编写 skill，再到维护与验证。",
        content_html=content,
        toc=[],
        canonical=SITE_URL + "docs/",
        active="docs-index",
        header_active="docs",
        categories=categories,
        kind="docs",
        crumb_items=[("Agent Skills", "../index.html"), ("文档", None)],
        meta_html=meta_links([("README.md", github_blob("README.md"))]),
        nav_html=page_nav(None, getting_started, "docs"),
        count=count,
    )


def build_skills_index(categories: list[dict], count: int) -> str:
    content = '<div class="skill-index">' + skill_groups(categories, "", 2) + "</div>"
    prev_page = {"href": "getting-started.html", "label": "开始使用"}
    next_page = {"href": "guide.html", "label": "编写 Skill"}
    return docs_page(
        title="Skill 目录",
        lead=f"{count} 个 skill，按使用场景分组。每个都能独立安装，也可以组合。",
        content_html=content,
        toc=[],
        canonical=SITE_URL + "docs/skills/",
        active="skills",
        header_active="skills",
        categories=categories,
        kind="skills",
        crumb_items=[
            ("Agent Skills", "../../index.html"),
            ("文档", "../index.html"),
            ("Skill 目录", None),
        ],
        meta_html=meta_links([("README.md", github_blob("README.md"))]),
        nav_html=page_nav(prev_page, next_page, "skills"),
        count=count,
    )


def build_getting_started(root_readme: str, categories: list[dict], count: int) -> str:
    custom = """## 第一次调用

在 agent 里直接描述任务，或显式点名 skill：

> 使用 `$deck-authoring` 把这份材料做成演示文稿。
>
> 使用 `$email-composer` 写一封上线申请邮件。

是否自动发现、如何显式调用，取决于使用的 Agent。
"""
    markdown = (
        extract_section(root_readme, "安装")
        + "\n"
        + extract_section(root_readme, "配置")
        + "\n"
        + custom
    )
    content, toc = render_markdown(markdown, "", "root")
    prev_page = {"href": "index.html", "label": "文档"}
    next_page = {"href": "skills/index.html", "label": "Skill 目录"}
    return docs_page(
        title="开始使用",
        lead="安装到 agent 的发现目录，确认配置，然后从一条真实需求开始。",
        content_html=content,
        toc=toc,
        canonical=SITE_URL + "docs/getting-started.html",
        active="getting-started",
        header_active="docs",
        categories=categories,
        kind="docs",
        crumb_items=[
            ("Agent Skills", "../index.html"),
            ("文档", "index.html"),
            ("开始使用", None),
        ],
        meta_html=meta_links([("README.md", github_blob("README.md"))]),
        nav_html=page_nav(prev_page, next_page, "docs"),
        count=count,
    )


def build_guide(categories: list[dict], count: int) -> str:
    title, body = split_h1(read(ROOT / "tools" / "skill-builder" / "GUIDE.md"))
    lead, body = take_first_paragraph(body)
    content, toc = render_markdown(body, "tools/skill-builder", "tool")
    prev_page = {"href": "skills/index.html", "label": "Skill 目录"}
    next_page = {"href": "maintenance.html", "label": "维护与验证"}
    return docs_page(
        title="编写 Skill",
        lead=lead or "把可复用的工作方法写成容易触发、能执行、能核验的 skill。",
        content_html=content,
        toc=toc,
        canonical=SITE_URL + "docs/guide.html",
        active="guide",
        header_active="guide",
        categories=categories,
        kind="docs",
        crumb_items=[
            ("Agent Skills", "../index.html"),
            ("文档", "index.html"),
            ("编写 Skill", None),
        ],
        meta_html=meta_links([("GUIDE.md", github_blob("tools/skill-builder/GUIDE.md"))]),
        nav_html=page_nav(prev_page, next_page, "docs"),
        count=count,
    )


def build_maintenance(root_readme: str, categories: list[dict], count: int) -> str:
    markdown = (
        extract_section(root_readme, "维护工具")
        + "\n"
        + extract_section(root_readme, "开发与验证")
        + "\n"
        + extract_section(root_readme, "仓库结构")
    )
    content, toc = render_markdown(markdown, "", "root")
    callout = (
        '<div class="callout">结构检查、回归测试与产物质量是三件事。'
        "检查通过只说明对应范围，不代表视觉、导出或外部服务已经验收。</div>"
    )
    prev_page = {"href": "guide.html", "label": "编写 Skill"}
    next_page = {"href": "roadmap.html", "label": "路线图"}
    return docs_page(
        title="维护与验证",
        lead="结构检查、回归测试、锁文件与站点构建，各自证明不同的事情。",
        content_html=callout + content,
        toc=toc,
        canonical=SITE_URL + "docs/maintenance.html",
        active="maintenance",
        header_active="docs",
        categories=categories,
        kind="docs",
        crumb_items=[
            ("Agent Skills", "../index.html"),
            ("文档", "index.html"),
            ("维护与验证", None),
        ],
        meta_html=meta_links([("README.md", github_blob("README.md"))]),
        nav_html=page_nav(prev_page, next_page, "docs"),
        count=count,
    )


def build_roadmap(categories: list[dict], count: int) -> str:
    title, body = split_h1(read(ROOT / "ROADMAP.md"))
    lead, body = take_first_paragraph(body)
    content, toc = render_markdown(body, "", "tool")
    prev_page = {"href": "maintenance.html", "label": "维护与验证"}
    return docs_page(
        title="路线图",
        lead=lead or "当前优先解决的问题与后续扩展方向。",
        content_html=content,
        toc=toc,
        canonical=SITE_URL + "docs/roadmap.html",
        active="roadmap",
        header_active="docs",
        categories=categories,
        kind="docs",
        crumb_items=[
            ("Agent Skills", "../index.html"),
            ("文档", "index.html"),
            ("路线图", None),
        ],
        meta_html=meta_links([("ROADMAP.md", github_blob("ROADMAP.md"))]),
        nav_html=page_nav(prev_page, None, "docs"),
        count=count,
    )


def build_skill_pages(categories: list[dict], count: int) -> dict[str, str]:
    flat: list[dict] = []
    for category in categories:
        for item in category["skills"]:
            flat.append(item)
    pages: dict[str, str] = {}
    for index, item in enumerate(flat):
        content, toc = render_markdown(
            item["body"], f"skills/{item['name']}", "skill"
        )
        prev_item = flat[index - 1] if index > 0 else None
        next_item = flat[index + 1] if index + 1 < len(flat) else None
        prev_page = (
            {"href": f"skills/{prev_item['name']}.html", "label": prev_item["subtitle"] or prev_item["name"]}
            if prev_item
            else {"href": "skills/index.html", "label": "Skill 目录"}
        )
        next_page = (
            {"href": f"skills/{next_item['name']}.html", "label": next_item["subtitle"] or next_item["name"]}
            if next_item
            else {"href": "guide.html", "label": "编写 Skill"}
        )
        meta = meta_links(
            [
                ("SKILL.md", github_blob(f"skills/{item['name']}/SKILL.md")),
                ("README.md", github_blob(f"skills/{item['name']}/README.md")),
            ]
        )
        pages[f"docs/skills/{item['name']}.html"] = docs_page(
            title=item["title"],
            lead=item["lead"],
            content_html=content,
            toc=toc,
            canonical=SITE_URL + f"docs/skills/{item['name']}.html",
            active=f"skill:{item['name']}",
            header_active="skills",
            categories=categories,
            kind="skills",
            crumb_items=[
                ("Agent Skills", "../../index.html"),
                ("文档", "../index.html"),
                ("Skill 目录", "../skills/index.html"),
                (item["name"], None),
            ],
            meta_html=meta,
            nav_html=page_nav(prev_page, next_page, "skills"),
            count=count,
            eyebrow=item["category"],
        )
    return pages


def build_404(categories: list[dict], count: int) -> str:
    body = """<main id="main" class="not-found">
  <p class="eyebrow">404</p>
  <h1>这个地址没有页面。</h1>
  <p>可能是链接过期，或文档还在整理。</p>
  <div class="hero-actions">
    <a class="btn btn-primary" href="./">回到 Agent Skills</a>
    <a class="btn btn-ghost" href="docs/">查看文档</a>
  </div>
</main>"""
    return layout(
        title=f"页面不存在 · {SITE_NAME}",
        description="这个地址没有对应的页面。",
        canonical=SITE_URL + "404.html",
        body_class="home",
        header_html=header("landing", ""),
        body=body,
        footer_html=footer("landing", count),
        assets_prefix=paths("landing")["assets"],
    )


def clean_output(out: Path) -> None:
    for name in ("assets", "docs"):
        shutil.rmtree(out / name, ignore_errors=True)
    for name in ("index.html", "404.html", ".nojekyll"):
        (out / name).unlink(missing_ok=True)


def copy_assets(out: Path) -> None:
    target = out / "assets"
    target.mkdir(parents=True, exist_ok=True)
    for source in ASSETS.iterdir():
        if source.is_file():
            shutil.copy2(source, target / source.name)


def write_page(out: Path, relative: str, content: str) -> None:
    path = out / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def check_output(out: Path, categories: list[dict]) -> list[str]:
    problems: list[str] = []
    expected = [
        "index.html",
        "404.html",
        "docs/index.html",
        "docs/getting-started.html",
        "docs/skills/index.html",
        "docs/guide.html",
        "docs/maintenance.html",
        "docs/roadmap.html",
        "assets/site.css",
        "assets/site.js",
        "assets/favicon.svg",
        ".nojekyll",
    ]
    for category in categories:
        for item in category["skills"]:
            expected.append(f"docs/skills/{item['name']}.html")
    for relative in expected:
        if not (out / relative).is_file():
            problems.append(f"缺少文件：{relative}")

    root = out.resolve()
    for path in out.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        leftover = LEFTOVER_TOKEN_RE.search(text)
        if leftover:
            problems.append(f"{path.relative_to(out)} 残留模板标记：{leftover.group(0)}")
        if "<title>" not in text:
            problems.append(f"{path.relative_to(out)} 缺少 <title>")
        for match in ATTR_RE.finditer(text):
            url = html.unescape(match.group("url")).strip()
            if not url or url.startswith(
                ("#", "/", "http://", "https://", "mailto:", "tel:", "data:", "//")
            ):
                continue
            raw_path = url.partition("#")[0]
            if not raw_path:
                continue
            target = (path.parent / raw_path).resolve()
            if target != root and root not in target.parents:
                continue
            if target.is_dir():
                target = target / "index.html"
            if not target.is_file():
                problems.append(f"{path.relative_to(out)} 链接目标不存在：{url}")
    return problems


def build(out: Path) -> int:
    root_readme, categories = load_skills()
    count = sum(len(category["skills"]) for category in categories)
    out.mkdir(parents=True, exist_ok=True)
    clean_output(out)

    pages = {
        "index.html": build_landing(categories, count),
        "404.html": build_404(categories, count),
        "docs/index.html": build_docs_index(categories, count),
        "docs/getting-started.html": build_getting_started(root_readme, categories, count),
        "docs/skills/index.html": build_skills_index(categories, count),
        "docs/guide.html": build_guide(categories, count),
        "docs/maintenance.html": build_maintenance(root_readme, categories, count),
        "docs/roadmap.html": build_roadmap(categories, count),
    }
    pages.update(build_skill_pages(categories, count))
    for relative, content in pages.items():
        write_page(out, relative, content)
    copy_assets(out)
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return len(pages)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="build_site.py", description="生成 Agent Skills 项目子站（首页 + docs）"
    )
    parser.add_argument("--out", default="_site", help="输出目录（默认 ./_site）")
    parser.add_argument(
        "--check", action="store_true", help="生成后检查内部链接、必备文件与模板残留"
    )
    args = parser.parse_args(argv)

    out = Path(args.out).expanduser().resolve()
    try:
        pages = build(out)
        problems = check_output(out, load_skills()[1]) if args.check else []
    except SiteError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2

    print(f"已生成 {pages} 个页面：{out}")
    if problems:
        print(f"检查发现 {len(problems)} 个问题：", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    if args.check:
        print("链接、必备文件与模板残留检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
