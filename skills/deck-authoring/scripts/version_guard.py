#!/usr/bin/env python3
"""比对相邻版本，拦住"新版本照着上一版改"。

为什么要有它
------------
SKILL.md 写了"新版本 = 新风格"，但这条规则靠自觉时，实际交付里最常见的是：
v2 复制 v1 的 deck.css 改几个字；沿用同一套类名、同一族字、同一组渐变，再换个
封面 —— 说是"重做"，缩略图几乎一样。作者自述"我没有参考上一版"无法验证，
相似度可以量。

做法
----
只读两版的源文件（source.html / 项目 CSS / design.md / image-plan.json），按
**视觉决定**分维比对：CSS 文件、组件类名、字族、彩色色板、背景与图案声明、
内联图形、页面骨架顺序、图片文件，以及"版本差异记录"是否写了。

报告只给"哪一维重合、重合多少"，**不打印上一版的具体值**：把旧色号、旧字体
重新塞回上下文，等于帮它接着抄。要改哪一维，回本版参考重新选。

用法
----
    python3 scripts/version_guard.py /path/to/v2-2026-10-19-深色工程/
    python3 scripts/version_guard.py /path/to/v2-.../ --against /path/to/v1-.../
    python3 scripts/version_guard.py /path/to/v2-.../ --json checks/version-guard.json
    python3 scripts/version_guard.py /path/to/v2-.../ --allow fonts --reason "用户指定沿用品牌字体"

`--against` 省略时，自动取同级目录里编号更小的 vN 版本。只有用户明确说"沿用
上一版的某一维"才用 `--allow`，且必须给 `--reason`（写用户原话），同时记进
design.md 的版本差异一节。

退出码：0 通过（可含提醒）、1 有硬失败、2 用法或输入问题。`--strict` 把提醒
也变成 2，与 design_signals.py 一致。这不是审美检查：它只证明没抄上一版，
不证明这一版好看。
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_sibling(name: str):
    """动态加载同目录脚本（`scripts/` 不是包，同级 import 在静态层面无法解析）。"""
    path = HERE / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_deck_guard_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了同目录模块：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


deckio = _load_sibling("deckio")
rhythm = _load_sibling("rhythm_check")   # 复用页面骨架签名，避免两套判定

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".avif"}
SKIP_DIRS = {"refs", "preview", "checks", "_archive", "node_modules", "__pycache__"}
FRAMEWORK_CSS = {"web-base.css", "web-layouts.css"}

# 框架与播放器自带的类名不是作者的视觉决定，不能算"搬用"。
FRAMEWORK_PREFIXES = ("deck-", "__deck", "is-", "js-")
FRAMEWORK_CLASSES = {"slide", "slides", "active", "reveal", "visible", "hidden", "print", "page"}
GENERIC_FAMILIES = {
    "serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui",
    "ui-sans-serif", "ui-serif", "ui-monospace", "inherit", "initial", "unset", "revert",
}

CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
URL_VALUE = re.compile(r"url\([^)]*\)", re.I)
RULE_PRELUDE = re.compile(r"([^{}]+)\{")
CLASS_TOKEN = re.compile(r"\.(-?[_a-zA-Z][\w-]*)")
FONT_FAMILY = re.compile(r"font-family\s*:\s*([^;}]+)", re.I)
FONT_PROPERTY = re.compile(r"--[-\w]*font[-\w]*\s*:\s*([^;}]+)", re.I)
HEX = re.compile(r"#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b")
RGB = re.compile(r"rgba?\(\s*(\d+)\s*[,\s]\s*(\d+)\s*[,\s]\s*(\d+)", re.I)
DECLARATION = re.compile(r"(?:(?<=[;{])|\A)\s*([-\w]+)\s*:\s*([^;}]+)")
SVG_PATH = re.compile(r'\sd="([^"]{24,})"')
ASSET_REF = re.compile(r'(?:src|href)="([^"]+)"|url\(([^)]*)\)', re.I)
VERSION_REF = re.compile(r"(?:^|/)v\d+[^/]*/")
STYLE_BLOCK = re.compile(r"<style[^>]*>(.*?)</style>", re.S | re.I)
STYLE_ATTR = re.compile(r'\sstyle="([^"]*)"', re.I)
CLASS_ATTR = re.compile(r'class="([^"]*)"')
DIFF_HEADING = re.compile(r"^#{2,4}[^\n]*(?:上一版|版本差异|版本对比)[^\n]*$", re.M)
HEADING = re.compile(r"^#{1,4}\s", re.M)

# 阈值：硬失败抓"同源"，提醒抓"疑似"。数字是相对重合度，不是审美评分。
CLASS_WARN, CLASS_FAIL = 0.25, 0.40
FONT_WARN, FONT_FAIL = 0.50, 1.00
PALETTE_WARN, PALETTE_FAIL = 0.35, 0.60
SURFACE_WARN, SURFACE_FAIL = 1, 3
SVG_WARN, SVG_FAIL = 1, 2
RHYTHM_WARN, RHYTHM_FAIL = 0.62, 0.80
MIN_PAGES_FOR_RHYTHM = 6
MIN_DIFF_LINES = 3

DIMENSIONS = (
    ("css", "项目 CSS"),
    ("classes", "组件类名"),
    ("fonts", "字族"),
    ("palette", "彩色色板"),
    ("surfaces", "背景 / 图案"),
    ("svg", "内联图形"),
    ("rhythm", "页面骨架顺序"),
    ("images", "图片 / 素材"),
    ("record", "版本差异记录"),
)
LABELS = dict(DIMENSIONS)
HINTS = {
    "css": "整份 CSS 相同说明这一版只换了文字；按本版参考重写样式表，别在旧文件上改。",
    "classes": "类名重合说明组件是搬过来的；按本版页面任务重新命名、拆分组件，不要沿用旧骨架。",
    "fonts": "字族相同，排印气质就没变；按本版参考重新选字。品牌强制时用 --allow fonts 并写明理由。",
    "palette": "色板重合说明颜色没有重选；从新参考重新建立色彩角色，不要微调旧色号。",
    "surfaces": "背景、渐变或纹理声明与上一版逐字相同；重做底纹与材质，别换张图盖住旧图案。",
    "svg": "内联图形路径相同，说明图案或图标是复制的；按本版图解语法重画。",
    "rhythm": "页序与骨架顺序接近上一版；按本轮问题重新拆页，不要沿用旧页序填空。",
    "images": "图片与上一版相同，或引用了别的版本目录；重新规划配图。确需复用要在 image-plan.json 写 source: provided 与理由。",
    "record": "design.md 缺「与上一版的差异」；先写清本版参考、字体、配色、构图、图案与封面尾页，再写页面。",
}
LEVEL_ORDER = {"skip": 0, "ok": 1, "authorized": 2, "warn": 3, "fail": 4}
SKIP_VALUE = "未测"


class GuardError(Exception):
    """输入不成立（缺产物、缺目录）—— 用法问题，不是"版本不合格"。"""


@dataclass
class Snapshot:
    root: Path
    pages: int
    classes: frozenset[str]
    fonts: frozenset[str]
    palette: frozenset[tuple[int, int, int]]
    surfaces: frozenset[str]
    paths: frozenset[str]
    signatures: tuple[str, ...]
    images: dict[str, str]          # sha256 -> 版本内相对路径
    cross_refs: frozenset[str]      # 指向其他版本目录的素材路径
    css_digest: str
    diff_lines: int


def _walk_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts[:-1]):
            continue
        found.append(path)
    return sorted(found)


def _project_css(root: Path, html: str) -> str:
    chunks = []
    for path in _walk_files(root):
        if path.suffix.lower() != ".css" or path.name in FRAMEWORK_CSS:
            continue
        chunks.append(deckio.read_text(str(path)))
    # 只有 deck.html 时样式被编进页面里；内联 <style> 同样属于本版视觉决定。
    chunks.extend(STYLE_BLOCK.findall(html))
    return "\n".join(chunks)


def _strip(css: str) -> str:
    return URL_VALUE.sub("url()", CSS_COMMENT.sub(" ", css))


def _classes(css: str, html: str) -> frozenset[str]:
    names: set[str] = set()
    for prelude in RULE_PRELUDE.findall(_strip(css)):
        names.update(CLASS_TOKEN.findall(prelude))
    for attr in CLASS_ATTR.findall(html):
        names.update(attr.split())
    return frozenset(
        name for name in names
        if len(name) >= 3
        and name.lower() not in FRAMEWORK_CLASSES
        and not name.startswith(FRAMEWORK_PREFIXES)
        and not name.isdigit()
    )


def _fonts(css: str) -> frozenset[str]:
    families: set[str] = set()
    for value in FONT_FAMILY.findall(_strip(css)) + FONT_PROPERTY.findall(_strip(css)):
        # var() 里可能带逗号（回退栈），先整段去掉再按逗号拆，避免拆出 "sans-serif)"。
        value = re.sub(r"var\([^)]*\)", "", value, flags=re.I)
        for part in value.split(","):
            name = part.strip().strip("'\"").strip().lower()
            name = re.sub(r"\s+", " ", name)
            if not name or name in GENERIC_FAMILIES:
                continue
            families.add(name)
    return frozenset(families)


def _rgb(hex_text: str) -> tuple[int, int, int]:
    raw = hex_text.lower()
    if len(raw) >= 6:
        return int(raw[:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
    doubled = "".join(ch * 2 for ch in raw[:3])
    return int(doubled[:2], 16), int(doubled[2:4], 16), int(doubled[4:6], 16)


def _chromatic(rgb: tuple[int, int, int]) -> bool:
    """只留彩色：黑白灰在任何一套设计里都会出现，重合不说明问题。"""
    top, low = max(rgb), min(rgb)
    return top - low >= 24 and top >= 40


def _palette(css: str, html: str) -> frozenset[tuple[int, int, int]]:
    text = _strip(css) + "\n" + " ".join(STYLE_ATTR.findall(html))
    colors = {_rgb(match) for match in HEX.findall(text)}
    colors.update(tuple(int(n) for n in match) for match in RGB.findall(text))
    return frozenset(color for color in colors if _chromatic(color))


def _surfaces(css: str, html: str) -> frozenset[str]:
    """渐变、纹理、内联 SVG data URI —— 换版重做时最常见的"图案照搬"。

    只收带图案语义的值：纯 url() 归图片比对，纯色归色板比对。
    """
    text = _strip(css) + "\n" + " ".join(STYLE_ATTR.findall(html))
    values: set[str] = set()
    for prop, value in DECLARATION.findall(text):
        if prop.startswith("--") or "background" in prop or "border-image" in prop or "mask" in prop:
            lowered = value.lower()
            if any(key in lowered for key in ("gradient(", "repeating-", "data:image")):
                values.add(re.sub(r"\s+", " ", lowered).strip())
    return frozenset(values)


def _paths(html: str) -> frozenset[str]:
    return frozenset(re.sub(r"\s+", " ", match) for match in SVG_PATH.findall(html))


def _signatures(html: str) -> tuple[str, ...]:
    return tuple(rhythm.signature(section) for section in rhythm.SECTION.findall(html))


def _cross_refs(html: str, css: str) -> frozenset[str]:
    """抓指向别的版本目录的素材引用（`../v1-.../assets/...`）。

    版本目录要能单独拷走；跨版本引用即使没复制文件，也把两版绑在了一起。
    """
    refs: set[str] = set()
    for match in ASSET_REF.finditer(html + "\n" + css):
        value = (match.group(1) or match.group(2) or "").strip().strip("'\"")
        if value and not value.startswith("data:") and VERSION_REF.search(value):
            refs.add(value)
    return frozenset(refs)


def _images(root: Path) -> dict[str, str]:
    """版本里实际使用的图片，按内容哈希查重。

    `brands/` 与 `assets/brand*/` 下的组织标识（logo、品牌图）本来就应该逐版一致，
    不计入"搬用"；它们承担的是身份，不是这一版的视觉决定。
    """
    hashes: dict[str, str] = {}
    for path in _walk_files(root):
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        if any(part.lower().startswith("brand") for part in path.relative_to(root).parts[:-1]):
            continue
        digest = hashlib.sha256(deckio.read_bytes(str(path))).hexdigest()
        hashes.setdefault(digest, str(path.relative_to(root)))
    return hashes


def _diff_lines(text: str) -> int:
    match = DIFF_HEADING.search(text)
    if match is None:
        return 0
    rest = text[match.end():]
    stop = HEADING.search(rest)
    body = rest[:stop.start()] if stop else rest
    return sum(1 for line in body.splitlines()
               if line.strip() and not line.strip().startswith("<!--"))


def _first_html(root: Path) -> Path | None:
    for name in ("source.html", "deck.html"):
        candidate = root / name
        if candidate.is_file():
            return candidate
    html = [path for path in _walk_files(root) if path.suffix.lower() == ".html"]
    return html[0] if html else None


def snapshot(root: Path) -> Snapshot:
    html_path = _first_html(root)
    if html_path is None:
        raise GuardError(f"{root} 里没有 source.html / deck.html，无法比对")
    html = deckio.read_text(str(html_path))
    css = _project_css(root, html)
    design = root / "design.md"
    diff_lines = _diff_lines(deckio.read_text(str(design))) if design.is_file() else 0
    return Snapshot(
        root=root,
        pages=len(rhythm.SECTION.findall(html)),
        classes=_classes(css, html),
        fonts=_fonts(css),
        palette=_palette(css, html),
        surfaces=_surfaces(css, html),
        paths=_paths(html),
        signatures=_signatures(html),
        images=_images(root),
        cross_refs=_cross_refs(html, css),
        css_digest=hashlib.sha256(css.strip().encode("utf-8")).hexdigest() if css.strip() else "",
        diff_lines=diff_lines,
    )


def _ratio(shared: int, union: int) -> float:
    return shared / union if union else 0.0


def _compare(new: Snapshot, old: Snapshot, provided: set[str]) -> dict[str, tuple[str, str, str]]:
    """返回 key → (level, 显示值, 细节)。只算重合，不回显旧值。"""
    out: dict[str, tuple[str, str, str]] = {}

    if not new.css_digest:
        out["css"] = ("skip", SKIP_VALUE, "没有项目 CSS，无法比对")
    elif new.css_digest == old.css_digest:
        out["css"] = ("fail", "100%", "整份项目 CSS 与上一版逐字节相同")
    else:
        out["css"] = ("ok", "不同", "")

    union = len(new.classes | old.classes)
    if union < 6:
        out["classes"] = ("skip", SKIP_VALUE, "自定义类名太少，比例没有意义")
    else:
        ratio = _ratio(len(new.classes & old.classes), union)
        if ratio >= CLASS_FAIL:
            out["classes"] = ("fail", f"重合 {ratio:.0%}", f"超过 {CLASS_FAIL:.0%} 上限")
        elif ratio >= CLASS_WARN:
            out["classes"] = ("warn", f"重合 {ratio:.0%}", f"超过提醒线 {CLASS_WARN:.0%}")
        else:
            out["classes"] = ("ok", f"重合 {ratio:.0%}", "")

    if not new.fonts or not old.fonts:
        out["fonts"] = ("skip", SKIP_VALUE, "没有声明字族，无法比对")
    else:
        ratio = _ratio(len(new.fonts & old.fonts), len(new.fonts | old.fonts))
        if ratio >= FONT_FAIL:
            out["fonts"] = ("fail", f"重合 {ratio:.0%}", "字族与上一版完全相同")
        elif ratio >= FONT_WARN:
            out["fonts"] = ("warn", f"重合 {ratio:.0%}", f"超过提醒线 {FONT_WARN:.0%}")
        else:
            out["fonts"] = ("ok", f"重合 {ratio:.0%}", "")

    if len(new.palette) < 2 or len(old.palette) < 2:
        out["palette"] = ("skip", SKIP_VALUE, "彩色太少，无法比对")
    else:
        ratio = _ratio(len(new.palette & old.palette), len(new.palette | old.palette))
        if ratio >= PALETTE_FAIL:
            out["palette"] = ("fail", f"重合 {ratio:.0%}", f"超过 {PALETTE_FAIL:.0%} 上限")
        elif ratio >= PALETTE_WARN:
            out["palette"] = ("warn", f"重合 {ratio:.0%}", f"超过提醒线 {PALETTE_WARN:.0%}")
        else:
            out["palette"] = ("ok", f"重合 {ratio:.0%}", "")

    shared = len(new.surfaces & old.surfaces)
    if shared >= SURFACE_FAIL:
        out["surfaces"] = ("fail", f"{shared} 处相同", "渐变/纹理声明逐字复用")
    elif shared >= SURFACE_WARN:
        out["surfaces"] = ("warn", f"{shared} 处相同", "有图案声明与上一版一致")
    else:
        out["surfaces"] = ("ok", "0 处相同", "")

    shared = len(new.paths & old.paths)
    if shared >= SVG_FAIL:
        out["svg"] = ("fail", f"{shared} 条相同", "内联图形路径逐字复用")
    elif shared >= SVG_WARN:
        out["svg"] = ("warn", f"{shared} 条相同", "有图形路径与上一版一致")
    else:
        out["svg"] = ("ok", "0 条相同", "")

    if len(new.signatures) < MIN_PAGES_FOR_RHYTHM or len(old.signatures) < MIN_PAGES_FOR_RHYTHM:
        out["rhythm"] = ("skip", SKIP_VALUE, f"少于 {MIN_PAGES_FOR_RHYTHM} 页，无法比对页序")
    else:
        ratio = SequenceMatcher(None, list(new.signatures), list(old.signatures)).ratio()
        if ratio >= RHYTHM_FAIL:
            out["rhythm"] = ("fail", f"相似 {ratio:.0%}", f"超过 {RHYTHM_FAIL:.0%} 上限")
        elif ratio >= RHYTHM_WARN:
            out["rhythm"] = ("warn", f"相似 {ratio:.0%}", f"超过提醒线 {RHYTHM_WARN:.0%}")
        else:
            out["rhythm"] = ("ok", f"相似 {ratio:.0%}", "")

    shared_images = [path for digest, path in new.images.items() if digest in old.images]
    if new.cross_refs:
        out["images"] = ("fail", f"{len(new.cross_refs)} 处越界引用",
                         "引用了其他版本目录的素材，版本目录无法单独拷走")
    elif not shared_images:
        out["images"] = ("ok", "0 个相同", "")
    else:
        unlisted = [path for path in shared_images if os.path.basename(path) not in provided]
        if unlisted:
            out["images"] = ("fail", f"{len(unlisted)} 个相同", "图片文件与上一版重复")
        else:
            out["images"] = ("authorized", f"{len(shared_images)} 个相同",
                             "已在 image-plan.json 登记为 provided")

    if new.diff_lines >= MIN_DIFF_LINES:
        out["record"] = ("ok", "已写", "")
    else:
        out["record"] = ("fail", "缺失" if not new.diff_lines else "太短",
                         f"design.md 的版本差异至少 {MIN_DIFF_LINES} 行有效内容")
    return out


def _provided_images(root: Path) -> set[str]:
    plan = root / "image-plan.json"
    if not plan.is_file():
        return set()
    try:
        data = json.loads(deckio.read_text(str(plan)))
    except json.JSONDecodeError:
        return set()
    allowed: set[str] = set()
    for item in data.get("images") or []:
        if not isinstance(item, dict):
            continue
        note = str(item.get("source_note") or "").strip()
        if item.get("source") == "provided" and note:
            allowed.add(os.path.basename(str(item.get("file") or "")))
    return allowed


def _previous_versions(current: Path) -> list[Path]:
    """同级与 `_archive/` 里的更早 vN —— 归档不等于从历史里消失。

    只比编号更小的版本；空占位目录（只有 README）跳过，不算"历史"。
    """
    own = re.match(r"v(\d+)", current.name)
    limit = int(own.group(1)) if own else None
    found = []
    for folder in (current.parent, current.parent / "_archive"):
        if not folder.is_dir():
            continue
        for path in folder.iterdir():
            if not path.is_dir() or path.resolve() == current.resolve():
                continue
            match = re.match(r"v(\d+)", path.name)
            if not match or _first_html(path) is None:
                continue
            if limit is not None and int(match.group(1)) >= limit:
                continue
            found.append((int(match.group(1)), path))
    return [path for _, path in sorted(found)]


def _merge(results: list[dict[str, tuple[str, str, str]]],
           previous: list[Path]) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    for key, label in DIMENSIONS:
        hits = [(previous[index].name, result[key])
                for index, result in enumerate(results) if key in result]
        if not hits:
            merged.append({"key": key, "label": label, "level": "skip",
                           "value": SKIP_VALUE, "detail": "", "versions": ""})
            continue
        worst_level = max(LEVEL_ORDER[item[0]] for _, item in hits)
        worst = next(item for _, item in hits if LEVEL_ORDER[item[0]] == worst_level)
        names = [name for name, item in hits if LEVEL_ORDER[item[0]] == worst_level]
        merged.append({"key": key, "label": label, "level": worst[0], "value": worst[1],
                       "detail": worst[2], "versions": "、".join(names)})
    return merged


def _render(findings: list[dict[str, str]], current: Path, previous: list[Path],
            allowed: dict[str, str], strict: bool) -> int:
    marks = {"fail": "✗", "warn": "⚠", "authorized": "·", "ok": "✓", "skip": "·"}
    print(f"比对：{current.name}")
    print(f"历史：{'、'.join(path.name for path in previous)}（{len(previous)} 个）\n")
    for finding in findings:
        mark = marks[finding["level"]]
        if finding["level"] == "skip":
            print(f"  {mark} {finding['label']}：{finding['detail'] or SKIP_VALUE}")
            continue
        if finding["level"] == "ok":
            print(f"  {mark} {finding['label']}：{finding['value']}")
            continue
        print(f"  {mark} {finding['label']}：{finding['value']} —— {finding['detail']}")
        if finding["key"] in allowed:
            print(f"     已授权沿用：{allowed[finding['key']]}")
        elif finding["level"] in ("fail", "warn"):
            print(f"     {HINTS[finding['key']]}")
    print()
    fails = [item for item in findings if item["level"] == "fail"]
    warns = [item for item in findings if item["level"] == "warn"]
    if fails:
        print(f"✗ {len(fails)} 项硬失败。回本版参考重写这些维度——"
              "对着上一版改色号、换配图，仍然只是同一套设计。")
        return 1
    if warns and strict:
        print(f"⚠ {len(warns)} 项提醒（--strict 视为失败）。先确认它们不是上一版漏下来的。")
        return 2
    if warns:
        print(f"⚠ {len(warns)} 项提醒。逐项确认不是上一版漏下来的；"
              "确认后仍要能说出它来自本版哪条参考。")
    else:
        print("✓ 没有发现跨版本搬用。")
    print("这只证明没抄上一版，不证明这一版好看——审美仍按 design-review.md 看。")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="比对相邻版本，检查新版本是否沿用了上一版的视觉决定")
    ap.add_argument("version", type=Path, help="当前版本目录（vN-...）")
    ap.add_argument("--against", type=Path, action="append",
                    help="指定历史版本目录，可重复；省略时自动取同级更小的 vN")
    ap.add_argument("--allow", default="", help="用户明确要求沿用的维度，逗号分隔：" + ", ".join(LABELS))
    ap.add_argument("--reason", default="", help="--allow 的用户原话；交付说明里能查到")
    ap.add_argument("--json", type=Path, help="把结果写成 JSON")
    ap.add_argument("--strict", action="store_true", help="把提醒也当作失败（退出 2）")
    args = ap.parse_args(argv)

    current = args.version.resolve()
    if not current.is_dir():
        print(f"✗ 不是目录：{current}", file=sys.stderr)
        return 2

    allowed: dict[str, str] = {}
    for key in (item.strip() for item in args.allow.split(",") if item.strip()):
        if key not in LABELS:
            print(f"✗ 未知的 --allow 维度：{key}（可用：{', '.join(LABELS)}）", file=sys.stderr)
            return 2
        allowed[key] = args.reason.strip()
    if allowed and not args.reason.strip():
        print("✗ --allow 必须配 --reason（写用户原话），不能无理由沿用上一版", file=sys.stderr)
        return 2

    previous = [path.resolve() for path in (args.against or _previous_versions(current))]
    unique: list[Path] = []
    for path in previous:
        if path not in unique:
            unique.append(path)
    previous = unique
    if not previous:
        print(f"{current.name} 没有可比的上一版，跳过跨版本检查。")
        return 0
    if current in previous:
        print("✗ --against 不能包含当前版本自己", file=sys.stderr)
        return 2

    try:
        new = snapshot(current)
        results = [_compare(new, snapshot(path), _provided_images(current)) for path in previous]
    except GuardError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2
    findings = _merge(results, previous)
    for finding in findings:
        if finding["key"] in allowed and finding["level"] in ("fail", "warn"):
            finding["level"] = "authorized"

    status = "fail" if any(item["level"] == "fail" for item in findings) else "pass"
    if args.json:
        payload = {
            "schemaVersion": 1,
            "current": str(current),
            "previous": [str(path) for path in previous],
            "allowed": allowed,
            "findings": findings,
            "status": status,
        }
        try:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
        except OSError as exc:
            print(f"✗ 写不了 {args.json}：{exc}", file=sys.stderr)
            return 2
    return _render(findings, current, previous, allowed, args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
