#!/usr/bin/env python3
"""审计一版 deck 的字族：除机器标识外，全文只应有一个字族。

为什么要有它
------------
SKILL.md 要求"一个字族承担全部文本"，但这条只靠自觉时，实际常见的是：
标题一套展示体、正文一套无衬线、数字再套一套等宽 —— 每一处单看都合理，
合起来字面高度、重心和字重对不齐，读者说不出哪里怪，只觉得"不像一个人做的"。
多族混排在中文里最先露馅，所以做成可量的检查。

做法
----
读 `source.html`（或版本目录）及其样式：外链 CSS、内联 `<style>`、行内 `style`，
外加 `font-family`、`font` 简写和 `--*font*` 自定义属性。按规则里的选择器判断
字族用在哪：

- 只用在与机器标识相关的选择器（`pre`、`code`、`.mono`、`.token` 等）上 → 允许；
- 出现在任何其它选择器上 → 算文本字族；文本字族超过 1 个就失败。

`@font-face` 只算声明，不算使用；声明了却没人用的字族会单独提醒。

只有用户或品牌明确要求双族时才用 `--allow "字族名" --reason "原话或规范出处"`
放行；放行也要在 `design.md` 记下来。

用法
----
    python3 scripts/type_audit.py /path/to/v2-.../
    python3 scripts/type_audit.py /path/to/source.html --json checks/type-audit.json
    python3 scripts/type_audit.py /path/to/v2-.../ --allow "Inter" --reason "品牌规范指定标题字"

退出码：0 通过（可含提醒）、1 有第二个文本字族、2 用法或输入问题。
这不是审美检查：它只证明字族没有散开，不证明选的字好看或适合这套内容。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_sibling(name: str):
    """动态加载同目录脚本（`scripts/` 不是包，同级 import 在静态层面无法解析）。"""
    path = HERE / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_deck_type_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了同目录模块：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


deckio = _load_sibling("deckio")

GENERIC_FAMILIES = {
    "serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui",
    "ui-sans-serif", "ui-serif", "ui-monospace", "inherit", "initial", "unset",
    "revert", "revert-layer", "math", "emoji", "fangsong",
}
FRAMEWORK_CSS = {"web-base.css", "web-layouts.css"}
SKIP_DIRS = {"refs", "preview", "checks", "_archive", "node_modules", "__pycache__"}

CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
DECLARATION = re.compile(r"([-\w]+)\s*:\s*([^;}]+)")
FONT_SHORTHAND = re.compile(r"\d[\d.]*(?:px|rem|em|pt|%)(?:/\S+)?\s+(.+)", re.I)
VAR_REF = re.compile(r"var\(\s*(--[\w-]+)[^)]*\)", re.I)
FONT_FACE = re.compile(r"@font-face\s*\{([^}]*)\}", re.I)
STYLE_BLOCK = re.compile(r"<style[^>]*>(.*?)</style>", re.S | re.I)
STYLE_ATTR = re.compile(r'\sstyle="([^"]*)"', re.I)
LINK_CSS = re.compile(r'<link\b[^>]*rel=["\']?stylesheet["\']?[^>]*>', re.I)
HREF = re.compile(r'href=["\']([^"\']+)["\']', re.I)

# 非文本用途：代码与机器标识可以用等宽，图标字体只能落在图标选择器上。
MACHINE_SELECTOR = re.compile(
    r"(?:^|[\s>+~,.#\[-])(?:code|pre|kbd|samp|var|mono|token|machine|cli|log|"
    r"snippet|path|endpoint|json|yaml|sql|id|hash|slug|icon|glyph|symbol|emoji|awesome)"
    r"(?=$|[\s>+~,.#:\[-])", re.I)
HEADING_SELECTOR = re.compile(r"(?:^|[\s>+~,.#])(?:h[1-6]|title|display|headline|heading)(?=$|[\s>+~,.#:\[-])", re.I)
CAPTION_SELECTOR = re.compile(r"(?:^|[\s>+~,.#])(?:caption|figcaption|note|foot|meta|label|kicker)(?=$|[\s>+~,.#:\[-])", re.I)
BODY_SELECTOR = re.compile(r"(?:^|[\s>+~,.])(?:body|html|p|li|td|th|blockquote|copy|body-copy|lead)(?=$|[\s>+~,.#:\[-])", re.I)

MAX_LISTED = 4


@dataclass
class Family:
    name: str
    sites: dict[str, int] = field(default_factory=dict)   # 选择器 -> 次数
    declared: bool = False

    @property
    def text_sites(self) -> dict[str, int]:
        return {site: count for site, count in self.sites.items() if not MACHINE_SELECTOR.search(site)}

    @property
    def is_text(self) -> bool:
        return bool(self.text_sites)


@dataclass
class Audit:
    html: Path
    families: dict[str, Family]
    unused_declared: list[str]
    source_count: int


def _read(path: Path) -> str:
    return deckio.read_text(str(path))


def _walk_css(root: Path) -> list[Path]:
    found = []
    for path in root.rglob("*.css"):
        if not path.is_file() or path.name in FRAMEWORK_CSS:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts[:-1]):
            continue
        found.append(path)
    return sorted(found)


def _first_html(path: Path) -> Path | None:
    if path.is_file() and path.suffix.lower() == ".html":
        return path
    for name in ("source.html", "deck.html"):
        candidate = path / name
        if candidate.is_file():
            return candidate
    pages = sorted(path.glob("*.html"))
    return pages[0] if pages else None


def _linked_css(html_path: Path, html: str) -> list[Path]:
    found: list[Path] = []
    for tag in LINK_CSS.findall(html):
        match = HREF.search(tag)
        if match is None:
            continue
        href = match.group(1).split("?")[0].split("#")[0]
        if re.match(r"[a-z]+:", href, re.I):
            continue
        candidate = (html_path.parent / href).resolve()
        if candidate.is_file() and candidate not in found:
            found.append(candidate)
    fallback = (html_path.parent / "assets" / "deck.css").resolve()
    if fallback.is_file() and fallback not in found:
        found.append(fallback)
    return found


def _sources(target: Path) -> tuple[Path, str, int]:
    html_path = _first_html(target)
    if html_path is None:
        raise SystemExit(f"✗ {target} 里没有 HTML，无法审计")
    html = _read(html_path)
    chunks = [_read(path) for path in _linked_css(html_path, html)]
    chunks.extend(STYLE_BLOCK.findall(html))
    return html_path, "\n".join(chunks), len(chunks)


def _families(value: str) -> list[str]:
    value = re.sub(r"var\([^)]*\)", "", value, flags=re.I)
    names = []
    for part in value.split(","):
        name = part.strip().strip("'\"")
        name = re.sub(r"\s+", " ", name).strip()
        if not name or name.lower() in GENERIC_FAMILIES or not re.search(r"[A-Za-z\u4e00-\u9fff]", name):
            continue
        names.append(name)
    return names


def _add(families: dict[str, Family], name: str, site: str) -> None:
    key = name.lower()
    entry = families.setdefault(key, Family(name=name))
    entry.sites[site] = entry.sites.get(site, 0) + 1


def _plan(css_text: str, html: str) -> tuple[dict[str, Family], list[str]]:
    css = CSS_COMMENT.sub(" ", css_text)
    families: dict[str, Family] = {}

    # 先收自定义属性：`--font-display: "X"` 在 font-family/font 里被 var() 引用时才算使用。
    var_map: dict[str, list[str]] = {}
    for prop, value in DECLARATION.findall(css):
        if prop.startswith("--") and "font" in prop.lower():
            names = _families(value)
            if names:
                var_map[prop.lower()] = names

    def resolve(value: str) -> str:
        def repl(match: re.Match[str]) -> str:
            names = var_map.get(match.group(1).lower(), [])
            return ", ".join(f'"{name}"' for name in names) if names else ""
        return VAR_REF.sub(repl, value)

    for match in RULE.finditer(css):
        prelude = match.group(1).strip()
        if prelude.startswith("@"):
            continue
        selectors = [re.sub(r"\s+", " ", item).strip() for item in prelude.split(",") if item.strip()]
        for prop, raw in DECLARATION.findall(match.group(2)):
            value = resolve(raw)
            if prop.lower() == "font-family":
                names = _families(value)
            elif prop.lower() == "font":
                shorthand = FONT_SHORTHAND.search(value)
                names = _families(shorthand.group(1)) if shorthand else []
            else:
                continue
            for name in names:
                for selector in selectors:
                    _add(families, name, selector)

    for value in STYLE_ATTR.findall(html):
        for prop, raw in DECLARATION.findall(value):
            if prop.lower() == "font-family":
                for name in _families(resolve(raw)):
                    _add(families, name, "行内 style")

    declared = []
    for match in FONT_FACE.findall(css):
        for prop, value in DECLARATION.findall(match):
            if prop.lower() == "font-family":
                declared.extend(_families(value))
    for name in declared:
        entry = families.get(name.lower())
        if entry is None:
            families[name.lower()] = Family(name=name, declared=True)
        else:
            entry.declared = True
    unused = sorted(entry.name for entry in families.values()
                    if entry.declared and not entry.sites)
    return families, unused


def _role(selector: str) -> str:
    if MACHINE_SELECTOR.search(selector):
        return "非文本用途"
    if HEADING_SELECTOR.search(selector):
        return "标题"
    if CAPTION_SELECTOR.search(selector):
        return "图注 / 辅助"
    if BODY_SELECTOR.search(selector):
        return "正文"
    return "其它"


def _site_summary(sites: dict[str, int]) -> str:
    ordered = sorted(sites.items(), key=lambda item: (-item[1], item[0]))
    shown = [f"`{site}`" for site, _ in ordered[:MAX_LISTED]]
    rest = len(ordered) - len(shown)
    return "、".join(shown) + (f" 等 {len(ordered)} 处" if rest > 0 else "")


def audit(target: Path, allowed: dict[str, str]) -> Audit:
    html_path, css_text, source_count = _sources(target)
    families, unused = _plan(css_text, html_path.read_text(encoding="utf-8"))
    return Audit(html=html_path, families=families, unused_declared=unused, source_count=source_count)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="审计字族：除机器标识外，全文只应有一个字族")
    ap.add_argument("target", type=Path, help="版本目录或 source.html")
    ap.add_argument("--allow", action="append", default=[], metavar="FAMILY",
                    help="用户或品牌明确要求的第二个字族，可重复；必须配 --reason")
    ap.add_argument("--reason", default="", help="--allow 的原话或规范出处")
    ap.add_argument("--json", type=Path, help="把结果写成 JSON")
    args = ap.parse_args(argv)

    if not args.target.exists():
        print(f"✗ 路径不存在：{args.target}", file=sys.stderr)
        return 2
    if args.allow and not args.reason.strip():
        print("✗ --allow 必须配 --reason（用户原话或品牌规范出处）", file=sys.stderr)
        return 2
    allowed = {name.strip().lower(): name.strip() for name in args.allow if name.strip()}

    try:
        result = audit(args.target, allowed)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 2

    text_families = [entry for entry in result.families.values()
                     if entry.is_text and entry.name.lower() not in allowed]
    authorized = [entry for entry in result.families.values()
                  if entry.is_text and entry.name.lower() in allowed]
    mono = [entry for entry in result.families.values() if entry.sites and not entry.is_text]

    print(f"字体审计：{result.html}")
    print(f"  样式来源 {result.source_count} 个，文本字族 {len(text_families) + len(authorized)} 个\n")
    multiple = len(text_families) > 1
    for entry in sorted(text_families + authorized, key=lambda item: (not item.is_text, item.name)):
        mark = "·" if multiple or entry.name.lower() in allowed else "✓"
        note = "（已授权沿用）" if entry.name.lower() in allowed else ""
        print(f"  {mark} “{entry.name}”{note}")
        for selector, _ in sorted(entry.text_sites.items(), key=lambda item: (-item[1], item[0]))[:MAX_LISTED]:
            print(f"      {_role(selector)} · `{selector}`")
    if mono:
        print("\n  非文本用途字族（允许）：")
        for entry in sorted(mono, key=lambda item: item.name):
            print(f"    · “{entry.name}” —— {_site_summary(entry.sites)}")
    if result.unused_declared:
        print("\n  · 声明但未使用的字族：" + "、".join(f"“{name}”" for name in result.unused_declared))

    verdict = "pass" if len(text_families) <= 1 else "fail"
    if args.json:
        payload = {
            "schemaVersion": 1,
            "html": str(result.html),
            "allowed": allowed,
            "reason": args.reason,
            "families": [
                {
                    "name": entry.name,
                    "text": entry.is_text,
                    "authorized": entry.name.lower() in allowed,
                    "sites": entry.sites,
                }
                for entry in result.families.values()
            ],
            "status": verdict,
        }
        try:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
        except OSError as exc:
            print(f"✗ 写不了 {args.json}：{exc}", file=sys.stderr)
            return 2

    if verdict == "fail":
        names = "、".join(f"“{entry.name}”" for entry in text_families)
        print(f"\n✗ 文本字族 {len(text_families)} 个：{names}（上限 1）")
        print("改法：把第二族的字形需求并回主字族，或按本版参考重选一个能同时承担标题与正文的族；"
              "等宽只留给代码与机器标识。只有用户或品牌明确要求双族时，才用 "
              "--allow \"字族名\" --reason \"原话\" 放行，并在 design.md 记下来。")
        return 1
    if not text_families:
        print("\n⚠ 没有解析到文本字族：确认字体声明写在承载文字的容器上，而不是只声明 @font-face。")
        return 0
    print("\n✓ 全文只有一个文本字族；等宽与图标字体只出现在非文本用途。")
    print("这只证明字族没有散开，不证明选的字好看或适合这套内容——标题、正文与数字仍要在样页里看。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
