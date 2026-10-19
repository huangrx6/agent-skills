#!/usr/bin/env python3
"""Report design signals that geometry checks do not measure.

This is a **review aid**, not a beauty score. It reads the completed frames of a
compiled web_deck.py artifact and reports observable proxies for a page that
reads as a document or a template: flat type scale, default display type, a
wide palette, an equal-card grid, a repeated page silhouette, loose alignment,
uniform gaps, long lines and similar tells. Every finding carries a concrete
lever; none of them proves the page is bad.

The measurements are intentionally style-agnostic. They do not prescribe a
palette, a typeface, a grid or a fixed number of type sizes. Use the report
beside a real screenshot review, never instead of it.

Usage:
    python3 scripts/design_signals.py deck.html
    python3 scripts/design_signals.py deck.html --json design-report.json
    python3 scripts/design_signals.py deck.html --strict   # exit 2 on review signals

A missing browser or a malformed artifact is a hard failure (exit 1). Ordinary
signals exit 0, and --strict turns review-level signals into exit 2.
"""
from __future__ import annotations

import argparse
import asyncio
import colorsys
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = Path(__file__).resolve().parent

_browser_spec = importlib.util.spec_from_file_location("_deck_browser_signals", HERE / "browser.py")
if _browser_spec is None or _browser_spec.loader is None:
    raise RuntimeError(f"Cannot load browser.py from {HERE}")
browser = importlib.util.module_from_spec(_browser_spec)
_browser_spec.loader.exec_module(browser)


def _connect():
    for name in ("websockets.asyncio.client", "websockets"):
        try:
            module = __import__(name, fromlist=["connect"])
        except ImportError:
            continue
        return module.connect
    raise RuntimeError("websockets is required; install requirements.txt")


COLLECT_JS = r"""
window.__designSignalsCollect = function(slide) {
  const round = n => Math.round(n * 100) / 100;
  const bounds = slide.getBoundingClientRect();
  const scale = bounds.width > 0 ? bounds.width / 1600 : 1;
  const norm = r => ({
    x: round((r.left - bounds.left) / scale), y: round((r.top - bounds.top) / scale),
    w: round(r.width / scale), h: round(r.height / scale),
    right: round((r.right - bounds.left) / scale), bottom: round((r.bottom - bounds.top) / scale)
  });
  const text = value => String(value || '').replace(/\s+/g, ' ').trim();
  const className = el => String((el.className && el.className.baseVal !== undefined)
    ? el.className.baseVal : (el.className || ''));
  const visible = el => {
    for (let cur = el; cur; cur = cur.parentElement) {
      const cs = getComputedStyle(cur);
      if (cs.display === 'none' || cs.visibility === 'hidden' || cs.visibility === 'collapse' || Number(cs.opacity) === 0) return false;
      if (cur === slide) break;
    }
    return true;
  };
  const firstFamily = value => {
    const first = String(value || '').split(',')[0].trim().replace(/^["']|["']$/g, '');
    return first || 'unknown';
  };
  const painted = value => value && !/^rgba?\(\s*0\s*,\s*0\s*,\s*0\s*,\s*0\s*\)$/.test(value);
  // 背景可能是同级层（.bg / .backdrop）而不是祖先，先按面积找覆盖整页的那一层
  const pageBackdrop = () => {
    const area = bounds.width * bounds.height;
    let best = null, bestArea = 0;
    for (const el of slide.querySelectorAll('*')) {
      const r = el.getBoundingClientRect();
      if ((r.width * r.height) < area * 0.6) continue;
      const bg = getComputedStyle(el).backgroundColor;
      if (!painted(bg)) continue;
      if (r.width * r.height > bestArea) { best = bg; bestArea = r.width * r.height; }
    }
    return best;
  };
  const bgOf = el => {
    for (let cur = el; cur; cur = cur.parentElement) {
      const bg = getComputedStyle(cur).backgroundColor;
      if (painted(bg)) return bg;
      if (cur === slide) break;
    }
    return pageBackdrop() || 'rgb(255, 255, 255)';
  };
  const blockSelector = 'h1,h2,h3,h4,h5,h6,p,li,figure,blockquote,img,svg,.deck-block,.deck-card,[class*="card"],[class*="column"],[class*="col"]';
  const blockOf = el => el.closest('li') || el.closest(blockSelector) || el;
  const blocks = new Map();

  function ensureBlock(el, kind) {
    let item = blocks.get(el);
    if (!item) {
      const r = el.getBoundingClientRect();
      if (r.width < 2 || r.height < 2 || !visible(el)) return null;
      const cs = getComputedStyle(el);
      item = {
        tag: el.tagName.toLowerCase(), cls: className(el).slice(0, 120),
        ...norm(r), align: cs.textAlign, fontSize: parseFloat(cs.fontSize) || 0,
        family: firstFamily(cs.fontFamily), weight: cs.fontWeight,
        color: cs.color, background: cs.backgroundColor,
        radius: parseFloat(cs.borderTopLeftRadius) || 0,
        shadow: cs.boxShadow !== 'none',
        gradient: /gradient/i.test(cs.backgroundImage || '')
      };
      blocks.set(el, item);
    }
    if (kind) item[kind] = true;
    return item;
  }

  const runs = [];
  const headings = [];
  const walker = document.createTreeWalker(slide, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    const el = node.parentElement;
    const value = text(node.nodeValue);
    if (!value || !el || el.closest('script,style,defs,title,desc') || !visible(el)) continue;
    const range = document.createRange();
    range.selectNodeContents(node);
    const rects = Array.from(range.getClientRects())
      .filter(r => r.width > .1 && r.height > .1).map(norm);
    if (!rects.length) continue;
    const cs = getComputedStyle(el);
    const tag = el.tagName.toLowerCase();
    const inFooter = !!el.closest('.deck-footer, footer');
    const inCaption = !!el.closest('.deck-caption, figcaption, .deck-kicker');
    let inHeading = /^h[1-6]$/.test(tag) || !!el.closest('h1,h2,h3,h4,h5,h6');
    if (!inHeading) {
      for (let cur = el; cur && cur !== slide; cur = cur.parentElement) {
        if (/(title|heading|headline|display)/i.test(className(cur))) { inHeading = true; break; }
      }
    }
    if (inFooter || inCaption) inHeading = false;
    const inBody = !inHeading && !inFooter && !inCaption &&
      (['p', 'li', 'dd', 'dt', 'blockquote'].includes(tag) || !!el.closest('.deck-copy, .deck-body'));
    const block = blockOf(el);
    const blockItem = ensureBlock(block, inHeading ? 'headingBlock' : inBody ? 'bodyBlock' : null);
    const xs = rects.map(r => r.x), ys = rects.map(r => r.y);
    const bbox = {
      x: Math.min(...xs), y: Math.min(...ys),
      right: Math.max(...rects.map(r => r.right)),
      bottom: Math.max(...rects.map(r => r.bottom))
    };
    bbox.w = round(bbox.right - bbox.x); bbox.h = round(bbox.bottom - bbox.y);
    const run = {
      text: value.length > 220 ? value.slice(0, 220) + '…' : value,
      tag, chars: Array.from(value).length, lineCount: rects.length, ...bbox,
      fontSize: round(parseFloat(cs.fontSize) || 0), family: firstFamily(cs.fontFamily),
      weight: cs.fontWeight, color: cs.color, align: cs.textAlign,
      letterSpacing: cs.letterSpacing, lineHeight: cs.lineHeight,
      letterSpacingPx: Number.isFinite(parseFloat(cs.letterSpacing)) ? parseFloat(cs.letterSpacing) : 0,
      cjk: /[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/.test(value),
      bg: bgOf(el), familyStack: cs.fontFamily,
      heading: inHeading, body: inBody, caption: inCaption, footer: inFooter,
      blockX: blockItem ? blockItem.x : bbox.x, blockW: blockItem ? blockItem.w : bbox.w
    };
    runs.push(run);
    if (inHeading) headings.push({x: run.x, y: run.y, w: run.w, h: run.h, align: run.align, size: run.fontSize, text: run.text});
  }

  const effects = {gradients: 0, shadows: 0, rounded: 0, glass: 0};
  let backgroundImages = 0;
  const backgrounds = new Map();
  for (const el of slide.querySelectorAll('*')) {
    if (!visible(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    const cs = getComputedStyle(el);
    if (/gradient/i.test(cs.backgroundImage || '')) effects.gradients++;
    if (/url\(/i.test(cs.backgroundImage || '') && (r.width / scale) * (r.height / scale) > 20000) backgroundImages++;
    if (cs.boxShadow !== 'none') effects.shadows++;
    if ((parseFloat(cs.borderTopLeftRadius) || 0) >= 6) effects.rounded++;
    if (cs.backdropFilter && cs.backdropFilter !== 'none') effects.glass++;
    const bg = cs.backgroundColor;
    if (bg && !/^rgba?\(\s*0\s*,\s*0\s*,\s*0\s*,\s*0\s*\)$/.test(bg)) {
      const area = (r.width / scale) * (r.height / scale);
      const previous = backgrounds.get(bg) || {color: bg, area: 0, count: 0};
      previous.area += area; previous.count++;
      backgrounds.set(bg, previous);
    }
  }

  const images = [];
  for (const el of slide.querySelectorAll('img, svg')) {
    if (!visible(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 80 || r.height < 80) continue;
    const cs = getComputedStyle(el);
    images.push({
      kind: el.tagName.toLowerCase(), ...norm(r),
      fit: cs.objectFit || null,
      naturalWidth: el.naturalWidth || null, naturalHeight: el.naturalHeight || null,
      aspect: round(r.width / Math.max(1, r.height))
    });
  }

  const cardGroups = [];
  const gaps = [];
  for (const parent of slide.querySelectorAll('*')) {
    const kids = Array.from(parent.children).filter(el => {
      const tag = el.tagName;
      return !/^(SCRIPT|STYLE|LINK|META)$/.test(tag) && visible(el) &&
        el.getBoundingClientRect().width > 20 && el.getBoundingClientRect().height > 20;
    });
    if (kids.length >= 2) {
      const rects = kids.map(el => el.getBoundingClientRect()).sort((a, b) => a.top - b.top || a.left - b.left);
      for (let i = 1; i < rects.length; i++) {
        const gap = (rects[i].top - rects[i - 1].bottom) / scale;
        if (gap > 2 && gap < 300) gaps.push(round(gap));
      }
    }
    if (kids.length < 3) continue;
    const rects = kids.map(el => el.getBoundingClientRect());
    const top = rects[0].top;
    if (!rects.every(r => Math.abs(r.top - top) < 2)) continue;
    const widths = rects.map(r => r.width / scale), heights = rects.map(r => r.height / scale);
    if (Math.max(...widths) - Math.min(...widths) > 3) continue;
    if (Math.max(...heights) - Math.min(...heights) > 3) continue;
    const sorted = rects.slice().sort((a, b) => a.left - b.left);
    const horizontal = [];
    for (let i = 1; i < sorted.length; i++) horizontal.push((sorted[i].left - sorted[i - 1].right) / scale);
    if (horizontal.length && Math.max(...horizontal) - Math.min(...horizontal) > 4) continue;
    const total = widths.reduce((a, b) => a + b, 0) + horizontal.reduce((a, b) => a + b, 0);
    if (total < bounds.width / scale * 0.35) continue;
    const surfaced = kids.some(el => {
      const cs = getComputedStyle(el);
      const bg = cs.backgroundColor;
      const painted = bg && !/^rgba?\(\s*0\s*,\s*0\s*,\s*0\s*,\s*0\s*\)$/.test(bg);
      const framed = ['Top', 'Right', 'Bottom', 'Left']
        .filter(side => parseFloat(cs['border' + side + 'Width']) > 0).length >= 2;
      return painted || cs.boxShadow !== 'none'
        || framed || parseFloat(cs.borderTopLeftRadius) >= 4;
    });
    cardGroups.push({
      count: kids.length, width: round(widths[0]), height: round(heights[0]),
      gap: round(horizontal[0] || 0), top: round((top - bounds.top) / scale),
      surfaced
    });
  }

  const uniqueCards = Array.from(new Map(cardGroups.map(g =>
    [g.count + ':' + g.width + ':' + g.height + ':' + g.gap + ':' + g.top, g])).values()).slice(0, 4);
  const headingSizes = headings.map(h => h.size);
  const bodySizes = runs.filter(r => r.body).map(r => r.fontSize);
  const allSizes = runs.map(r => r.fontSize);
  const families = runs.map(r => r.family);
  const weights = runs.map(r => r.weight);
  const charCount = runs.reduce((sum, r) => sum + r.chars, 0);
  const emojiCount = runs.reduce((sum, r) =>
    sum + ((r.text.match(/\p{Extended_Pictographic}/gu) || []).length), 0);
  const blocksOut = Array.from(blocks.values()).map(item => ({...item}));
  const textBlocks = blocksOut.filter(b => b.headingBlock || b.bodyBlock);
  // 满版背景图不算内容块：否则 margins 恒为 0，bottom-empty / 顶部过挤永远测不出来
  const foregroundImages = images.filter(i => (i.w || 0) < bounds.width / scale * 0.92
    || (i.h || 0) < bounds.height / scale * 0.92);
  const contentBlocks = textBlocks.concat(foregroundImages.map(i => ({...i, textBlock: false})));
  const margins = contentBlocks.length ? {
    left: round(Math.min(...contentBlocks.map(b => b.x))),
    top: round(Math.min(...contentBlocks.map(b => b.y))),
    right: round(1600 - Math.max(...contentBlocks.map(b => b.right))),
    bottom: round(900 - Math.max(...contentBlocks.map(b => b.bottom)))
  } : null;
  const header = slide.querySelector('.deck-header');
  const body = slide.querySelector('.deck-body');
  const footer = slide.querySelector('.deck-footer');
  const region = el => el ? norm(el.getBoundingClientRect()) : null;
  const pageRoot = slide.querySelector('.deck-page');

  return {
    slide: Number(slide.dataset.slide), title: slide.dataset.title || '',
    bounds: norm(bounds), scale: round(scale),
    viewing: pageRoot ? (pageRoot.getAttribute('data-viewing') || 'screen') : null,
    layout: pageRoot ? (pageRoot.getAttribute('data-layout') || '') : '',
    regions: {header: region(header), body: region(body), footer: region(footer)},
    declaredFamilies: Array.from(new Set(Array.from(document.fonts || []).map(f => f.family))),
    runs: runs.slice(0, 500),
    headings: headings.slice(0, 80),
    blocks: blocksOut.slice(0, 250),
    type: {
      sizes: allSizes, headingSizes, bodySizes, families, weights
    },
    colors: {
      text: runs.map(r => r.color),
      backgrounds: Array.from(backgrounds.values()).sort((a, b) => b.area - a.area).slice(0, 12)
    },
    effects, backgroundImages,
    images,
    cardGroups: uniqueCards,
    gaps: gaps.slice(0, 80),
    charCount,
    emojiCount,
    textBlocks: blocksOut.filter(b => b.headingBlock || b.bodyBlock).length,
    margins,
    centeredHeadings: headings.filter(h => h.align === 'center').length,
    headingCount: headings.length
  };
};
"""

RGB_RE = re.compile(r"^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)(?:\s*,\s*([\d.]+))?\s*\)$", re.I)
HEX_RE = re.compile(r"^#([0-9a-f]{3,8})$", re.I)
DEFAULT_FONTS = {
    "system-ui", "-apple-system", "blinkmacsystemfont", "inter", "roboto", "arial",
    "helvetica", "helvetica neue", "segoe ui", "noto sans", "sans-serif", "sans",
}


def _rgb(value: str) -> tuple[float, float, float, float] | None:
    value = str(value or "").strip()
    hit = RGB_RE.match(value)
    if hit:
        return tuple(_num(part, 1.0) for part in hit.groups(default="1"))  # type: ignore[return-value]
    hit = HEX_RE.match(value)
    if hit:
        raw = hit.group(1)
        if len(raw) in (3, 4):
            raw = "".join(ch * 2 for ch in raw)
        if len(raw) not in (6, 8):
            return None
        return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16),
                int(raw[6:8], 16) / 255 if len(raw) == 8 else 1.0)
    return None


def _contrast_ratio(foreground: str, background: str) -> float | None:
    """WCAG 2.1 contrast for a text run against its effective background."""
    front, back = _rgb(foreground), _rgb(background)
    if not front or not back:
        return None
    if front[3] < 0.95:
        return None

    def channel(value: float) -> float:
        value = value / 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    def luminance(rgb):
        red, green, blue = (channel(part) for part in rgb[:3])
        return 0.2126 * red + 0.7152 * green + 0.0722 * blue

    first, second = luminance(front), luminance(back)
    high, low = max(first, second), min(first, second)
    return round((high + 0.05) / (low + 0.05), 2)


def _hsl(value: str) -> tuple[float, float, float] | None:
    parsed = _rgb(value)
    if not parsed:
        return None
    red, green, blue, alpha = parsed
    if alpha < 0.5:
        return None
    hue, lightness, saturation = colorsys.rgb_to_hls(red / 255, green / 255, blue / 255)
    return hue * 360, saturation, lightness


def _chromatic(value: str) -> bool:
    parsed = _hsl(value)
    if not parsed:
        return False
    _, saturation, lightness = parsed
    return saturation >= 0.18 and 0.08 <= lightness <= 0.95


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 2) if values else None


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return round(ordered[index], 2)


def _cv(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = statistics.fmean(values)
    return round(statistics.pstdev(values) / mean, 3) if mean else None


def _num(value, default: float = 0.0) -> float:
    """Raw metrics come from JavaScript; never let one bad value abort a report."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _int(value, default: int = 0) -> int:
    try:
        return int(_num(value, default))
    except (TypeError, ValueError, OverflowError):
        return default


def _signal(code: str, severity: str, message: str, lever: str, **evidence) -> dict:
    return {"code": code, "severity": severity, "message": message,
            "lever": lever, "evidence": evidence}


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def analyze_page(page: dict) -> dict:
    """Turn one page's raw measurements into review signals.

    Kept free of browser calls so the rules can be tested and tuned without a
    display. The rules describe *observable* properties, not a house style.
    """
    runs = page.get("runs") or []
    headings = page.get("headings") or []
    type_data = page.get("type") or {}
    sizes = [round(_num(value) * 2) / 2 for value in type_data.get("sizes", []) if _num(value) > 0]
    heading_sizes = [_num(value) for value in type_data.get("headingSizes", []) if _num(value) > 0]
    body_sizes = [_num(value) for value in type_data.get("bodySizes", []) if _num(value) > 0]
    families = [str(value) for value in type_data.get("families", []) if value]
    weights = [str(value) for value in type_data.get("weights", []) if value]
    body_text = [run for run in runs if run.get("body")]
    char_count = _int(page.get("charCount"))
    body_chars = sum(_int(run.get("chars")) for run in body_text)

    heading_size = max(heading_sizes) if heading_sizes else (max(sizes) if sizes else None)
    body_size = _median(body_sizes) or _median(sizes)
    scale_ratio = round(heading_size / body_size, 2) if heading_size and body_size else None
    distinct_sizes = sorted(set(sizes))
    content_sizes = sorted({round(_num(value) * 2) / 2 for value in heading_sizes + body_sizes})
    heading_families = _unique([str(h.get("family")) for h in headings if h.get("family")])
    display_family = heading_families[0] if heading_families else (families[0] if families else None)
    colors = page.get("colors") or {}
    chromatic = _unique([value for value in (colors.get("text") or []) if _chromatic(value)])
    chromatic += _unique([item.get("color", "") for item in (colors.get("backgrounds") or [])
                          if _chromatic(item.get("color", ""))])
    chromatic = _unique(chromatic)
    blocks = page.get("blocks") or []
    block_boxes = [b for b in blocks if _num(b.get("w")) >= 20 and _num(b.get("h")) >= 10]
    axes = [round(_num(b.get("x"))) for b in block_boxes]
    axes += [round(_num(b.get("right"))) for b in block_boxes]
    axis_counts: dict[int, int] = {}
    for axis in axes:
        axis_counts[axis] = axis_counts.get(axis, 0) + 1
    shared_axes = sum(1 for count in axis_counts.values() if count >= 2)
    gaps = [_num(value) for value in (page.get("gaps") or []) if _num(value) > 0]
    gap_cv = _cv(gaps)
    gap_modes = len({round(value) for value in gaps})
    images = page.get("images") or []
    image_area = sum(_num(item.get("w")) * _num(item.get("h")) for item in images)
    image_ratio = min(1.0, round(image_area / (1600 * 900), 3))
    edge_bleed = any(
        _num(item.get("x")) <= 2 or _num(item.get("y")) <= 2
        or _num(item.get("right")) >= 1598 or _num(item.get("bottom")) >= 898
        for item in images)
    aspects = [_num(item.get("aspect")) for item in images if _num(item.get("aspect")) > 0]
    line_chars = [_num(run.get("chars")) / max(1.0, _num(run.get("lineCount"), 1))
                  for run in body_text
                  if _num(run.get("lineCount")) and _num(run.get("chars")) >= 30]
    cjk_chars = sum(len(re.findall(r"[\u3400-\u9fff]", run.get("text", ""))) for run in body_text)
    cjk_ratio = cjk_chars / max(1, body_chars)
    margins = page.get("margins") or {}
    effects = page.get("effects") or {}
    card_groups = page.get("cardGroups") or []
    heading_count = _int(page.get("headingCount"))
    centered = _int(page.get("centeredHeadings"))
    signals: list[dict] = []

    if (scale_ratio is not None and body_chars >= 120 and content_sizes
            and scale_ratio < 2.2 and len(content_sizes) <= 3):
        signals.append(_signal(
            "flat-type-scale", "review",
            f"标题/正文尺度比约 {scale_ratio}×，层级接近文档而不是演示。",
            "先把标题提高一档到正文的 2.4–3.5×，或把正文降一档；只改一层后复看。",
            headingSize=heading_size, bodySize=body_size, ratio=scale_ratio,
            distinctSizes=content_sizes))

    if len(distinct_sizes) > 7:
        signals.append(_signal(
            "many-type-sizes", "info",
            f"一页出现 {len(distinct_sizes)} 档字号，层级可能互相抵消。",
            "合并到 3–5 档：展示、标题、正文、辅助；把只差 1–2px 的档并掉。",
            distinctSizes=distinct_sizes))

    if display_family and display_family.strip().lower() in DEFAULT_FONTS and heading_count:
        signals.append(_signal(
            "default-display-type", "review",
            f"展示字使用默认系统字族 {display_family!r}；若这是有意的排印选择，记录它如何服务尺度或材质，否则页面容易读成未设计的文档。",
            "为标题选择一个有明确字形态度的展示字，或让排印由尺度、字重和位置承担；不要只换一个默认无衬线。",
            family=display_family, headingCount=heading_count))

    if len(_unique(families)) > 3:
        signals.append(_signal(
            "font-family-mix", "info",
            f"一页出现 {len(_unique(families))} 个字族，视觉声音容易散。",
            "收敛到展示字 + 正文字两族；第三族只用于数据或代码，并检查它是否真的必要。",
            families=_unique(families)))

    if len(chromatic) > 6:
        signals.append(_signal(
            "wide-palette", "review",
            f"检测到 {len(chromatic)} 个高饱和色，强调色可能失去焦点。",
            "保留一个主强调色和一个信号色；其余降低饱和度或改成中性色，按面积而不是按数量检查。",
            chromatic=chromatic[:10]))

    if _int(effects.get("shadows")) >= 3 and _int(effects.get("rounded")) >= 3:
        signals.append(_signal(
            "shadow-card-stack", "review",
            f"检测到 {effects.get('shadows')} 处阴影、{effects.get('rounded')} 处圆角，接近通用卡片模板。",
            "先判断这些卡片是否必须存在；需要分组时用对齐、留白、细线或色块，只有真实层级才用阴影。",
            shadows=effects.get("shadows"), rounded=effects.get("rounded")))

    if _int(effects.get("rounded")) >= 8 and _int(effects.get("shadows")) == 0:
        signals.append(_signal(
            "rounded-everything", "info",
            f"检测到 {effects.get('rounded')} 个圆角元素，形状语言可能过于统一。",
            "让圆角表达真实含义（按钮、标签、容器），其余元素用直角或与网格一致的小圆角。",
            rounded=effects.get("rounded")))

    if _int(effects.get("gradients")) >= 2:
        signals.append(_signal(
            "gradient-layers", "info",
            f"检测到 {effects.get('gradients')} 处渐变背景。",
            "渐变应服务光感、深度或品牌，不要用紫色/蓝色渐变当默认装饰；先看它是否承担了画面关系。",
            gradients=effects.get("gradients")))

    if heading_count >= 3 and centered / max(1, heading_count) >= 0.8:
        signals.append(_signal(
            "centered-everything", "review",
            f"{centered}/{heading_count} 个标题居中，页面缺少方向性对齐。",
            "至少让一组内容采用边对齐或非对称构图；居中只留给真正需要对称的页。",
            centered=centered, headings=heading_count))

    surfaced_cards = [group for group in card_groups if group.get("surfaced")]
    if surfaced_cards:
        first = surfaced_cards[0]
        signals.append(_signal(
            "equal-card-grid", "review",
            f"检测到 {first.get('count')} 个等宽等高、带底/框的卡片，像通用组件阵列。",
            "先问这些卡片是否等权；需要比较时保留同尺度，其余改成不同列宽、不同高度或连续排印。"
            "纯文字分栏不算卡片，不需要为了消掉提示去加底色。",
            groups=surfaced_cards[:3]))

    if len(gaps) >= 6 and gap_cv is not None and gap_cv < 0.08 and gap_modes <= 2 and char_count < 900:
        signals.append(_signal(
            "uniform-gap", "review",
            f"{len(gaps)} 个组间/条间距几乎相同（CV {gap_cv}），缺少组间层级。",
            "让组间距至少是条间距的 1.5–2×；先建立 3 种关系（同组、跨组、章节），不要所有间距一个值。",
            gapCount=len(gaps), cv=gap_cv, modes=gap_modes))

    if margins and char_count > 200 and not edge_bleed:
        tight = [name for name in ("left", "top", "right", "bottom") if _num(margins.get(name), 999) < 40]
        if tight:
            signals.append(_signal(
                "tight-margins", "info",
                f"{'/'.join(tight)} 边距小于 40px，画面容易被边缘压住。",
                "把边距当作构图的一部分；先统一左/上轴，再决定是否让一张图或色块故意出血。",
                margins=margins))

    if (margins and char_count > 250 and _num(margins.get("bottom")) > 280
            and _num(margins.get("top"), 999) < 180 and len(images) <= 1):
        signals.append(_signal(
            "bottom-empty", "info",
            f"底部空出约 {margins.get('bottom')}px，内容集中在页面上半部。",
            "把空间放到组间或焦点周围，或让一个元素（图、数字、色块）承担下半部；不要用拉高容器填满。",
            margins=margins, charCount=char_count))

    if char_count > 1600:
        signals.append(_signal(
            "text-wall", "review",
            f"本页约 {char_count} 字符，阅读负担接近文档页。",
            "先按问题拆页或把细节下沉到图注/附录；不要靠缩字或缩小行距解决。",
            charCount=char_count))

    if line_chars and body_chars >= 200:
        p90 = _percentile(line_chars, 0.9)
        limit = 55 if cjk_ratio >= 0.3 else 100
        if p90 and p90 > limit:
            signals.append(_signal(
                "long-lines", "review",
                f"正文行长 P90 约 {p90} 字符（建议 ≤ {limit}），阅读路径偏长。",
                "缩短正文列宽、增加分栏或改成分组短段；不要把字号缩小来塞进原宽度。",
                p90=p90, limit=limit, cjkRatio=round(cjk_ratio, 2)))

    if len(block_boxes) >= 8 and shared_axes < 3:
        signals.append(_signal(
            "loose-alignment", "review",
            f"{len(block_boxes)} 个内容块只共享 {shared_axes} 条对齐轴，画面容易漂浮。",
            "先找回 2–4 条共同轴（左缘、图注基线、右缘），再保留有理由的错位；偏心需要秩序支撑。",
            blocks=len(block_boxes), sharedAxes=shared_axes))

    if shared_axes > 10:
        signals.append(_signal(
            "many-alignment-axes", "info",
            f"检测到 {shared_axes} 条共享对齐轴，可能削弱主次。",
            "保留主网格轴，其余错位只服务一个明确的目的（出血、标注、节奏）。",
            sharedAxes=shared_axes))

    if len(aspects) >= 3 and statistics.pstdev(aspects) < 0.02:
        signals.append(_signal(
            "uniform-image-ratio", "info",
            f"{len(aspects)} 张图的宽高比几乎相同，图片可能只是等尺寸填充。",
            "让图像比例跟随内容：证据图保全比例，氛围图可裁切，特写可局部放大；不要统一成同一张卡。",
            aspects=aspects))

    has_visual = bool(images) or _int(page.get("backgroundImages")) > 0
    if not has_visual and char_count > 450:
        signals.append(_signal(
            "no-image", "info",
            "本页文字较多但没有图像或图形承担解释。",
            "确认这是有意的纯文字页；若图能减少解释负担，安排功能图或把关系画出来。",
            charCount=char_count))

    if images and image_ratio < 0.08 and char_count > 450:
        signals.append(_signal(
            "small-image-area", "info",
            f"图片只占画面 {round(image_ratio * 100, 1)}%，更像装饰而不是证据。",
            "决定图是主角、证据还是背景；若是证据，放大到能读出关键关系，或局部放大后拆页。",
            imageRatio=image_ratio, imageCount=len(images)))

    if _int(page.get("emojiCount")) >= 2:
        signals.append(_signal(
            "emoji-icons", "info",
            f"检测到 {page.get('emojiCount')} 个 emoji。",
            "emoji 不能替代图标系统或证据；需要图标时用项目自己的形状语言，并检查它在投影尺寸下的辨识度。",
            emojiCount=page.get("emojiCount")))

    # 中文字距：中文从 0 开始；大 tracking 只给全大写拉丁与短标签
    tracked_cjk = [
        run for run in runs
        if run.get("cjk") and _num(run.get("letterSpacingPx")) > max(0.6, 0.03 * _num(run.get("fontSize"), 16))
    ]
    if tracked_cjk:
        sample = tracked_cjk[0]
        signals.append(_signal(
            "cjk-tracking", "review",
            f"{len(tracked_cjk)} 段中文被加了字距（示例 {sample.get('letterSpacing')} @ {sample.get('fontSize')}px）。",
            "中文从 letter-spacing: 0 开始；0.1em 以上的字距只给全大写拉丁和短标签，句子保持 0。",
            count=len(tracked_cjk), sample=str(sample.get("text", ""))[:40],
            letterSpacing=sample.get("letterSpacing")))

    # 文字对比度：正文 4.5:1、大字 3:1
    low_contrast = []
    for run in runs:
        size = _num(run.get("fontSize"), 0)
        if size <= 0:
            continue
        weight = _num(str(run.get("weight") or "400").replace("bold", "700"), 400)
        large = size >= 24 or (size >= 18.66 and weight >= 700)
        ratio = _contrast_ratio(str(run.get("color") or ""), str(run.get("bg") or ""))
        if ratio is None:
            continue
        floor = 3.0 if large else 4.5
        if ratio < floor:
            low_contrast.append({"ratio": ratio, "floor": floor, "size": size,
                                 "color": run.get("color"), "bg": run.get("bg"),
                                 "text": str(run.get("text", ""))[:40]})
    if low_contrast:
        worst = min(low_contrast, key=lambda item: item["ratio"])
        signals.append(_signal(
            "low-contrast", "review",
            f"{len(low_contrast)} 段文字的对比度低于 WCAG 门槛（最低 {worst['ratio']}:1，要求 {worst['floor']}:1，{worst['size']}px）。",
            "提高该灰阶的明度差或加大字号/字重；浅灰小字在投影和打印上最先消失。",
            count=len(low_contrast), worst=worst))

    # 字体栈：栈里没有任何声明字族的文字，会落到系统字
    declared = {str(name).strip().strip('"').strip("'").lower()
                for name in (page.get("declaredFamilies") or []) if str(name).strip()}
    if declared:
        system_runs = []
        for run in runs:
            stack = {part.strip().strip('"').strip("'").lower()
                     for part in str(run.get("familyStack") or "").split(",") if part.strip()}
            if stack and not (stack & declared):
                system_runs.append(run)
        if system_runs:
            sample = system_runs[0]
            signals.append(_signal(
                "system-font-fallback", "review",
                f"{len(system_runs)} 段文字的字体栈不含任何已加载字族，实际会用系统字（示例：{sample.get('familyStack')}）。",
                "把项目字体栈设在整张 slide（而不只是内容容器）上；容器外的边注、页码、单位最容易漏，导出 PDF 时还会嵌入系统字体。",
                count=len(system_runs), sample=str(sample.get("text", ""))[:40],
                stack=str(sample.get("familyStack"))[:120]))

    # 声明了字体却整页没用到：字体没生效、或标题走了别的字族
    if declared:
        used = set()
        for run in runs:
            for part in str(run.get("familyStack") or "").split(","):
                name = part.strip().strip('"').strip("'").lower()
                if name:
                    used.add(name)
        unused = sorted(declared - used)
        if unused and (headings or runs):
            signals.append(_signal(
                "declared-font-unused", "review",
                f"本页声明了 {len(unused)} 个字体但一个字都没用上（{', '.join(unused[:3])}）。",
                "确认字体文件真的加载、font-family 写在承载文字的容器上；标题与正文分别检查，别只看 body。",
                unused=unused[:6], declared=sorted(declared)[:6]))

    # 正文字族过多：一个字族承担全部文本，等宽只给机器标识
    prose_families = set()
    for run in runs:
        stack = [part.strip().strip('"').strip("'") for part in str(run.get("familyStack") or "").split(",")]
        first = next((name for name in stack if name and name.lower() not in ("monospace", "sans-serif", "serif")), "")
        if not first:
            continue
        if "mono" in first.lower():
            continue
        prose_families.add(first.lower())
    if len(prose_families) > 2:
        signals.append(_signal(
            "too-many-prose-families", "review",
            f"本页正文用了 {len(prose_families)} 个字族：{', '.join(sorted(prose_families)[:4])}。",
            "选定一个字族承担标题与正文；确需双族时只允许标题使用，并在 design.md 写明例外。",
            families=sorted(prose_families)[:6]))

    metrics = {
        "typeSizes": distinct_sizes,
        "headingSize": heading_size,
        "maxTypeSize": max(sizes) if sizes else None,
        "bodySize": body_size,
        "scaleRatio": scale_ratio,
        "displayFamily": display_family,
        "fontFamilies": _unique(families),
        "weights": _unique(weights),
        "chromaticColors": chromatic[:12],
        "blockCount": len(block_boxes),
        "sharedAxes": shared_axes,
        "margins": margins,
        "gapCount": len(gaps),
        "gapCv": gap_cv,
        "imageCount": len(images),
        "imageAreaRatio": image_ratio,
        "cardGroups": card_groups[:3],
        "charCount": char_count,
        "bodyChars": body_chars,
        "lineCharsP90": _percentile(line_chars, 0.9),
        "effects": effects,
        "centeredHeadingRatio": round(centered / heading_count, 2) if heading_count else None,
        "viewing": page.get("viewing"),
        "layout": page.get("layout"),
        "cjkTrackedRuns": len(tracked_cjk),
        "lowContrastRuns": len(low_contrast),
        "minContrast": min((item["ratio"] for item in low_contrast), default=None),
        "systemFontRuns": len(system_runs) if declared else None,
    }
    return {"slide": page.get("slide"), "title": page.get("title"), "metrics": metrics, "signals": signals}


def _signature(page: dict) -> tuple:
    metrics = page.get("metrics", {})
    regions = page.get("regions") or {}
    header = regions.get("header") or {}
    body = regions.get("body") or {}
    heading = page.get("headings") or [{}]
    title_y = heading[0].get("y", 0) if heading else 0
    return (
        round((header.get("h") or 0) / 8),
        round(title_y / 8),
        round((metrics.get("headingSize") or 0) / 8),
        round((body.get("y") or 0) / 16),
        round((metrics.get("imageAreaRatio") or 0) * 10),
    )


def analyze_deck(pages: list[dict], raw_pages: list[dict]) -> dict:
    """Deck-level repetition and range. Page indices are 1-based in the report."""
    signals: list[dict] = []
    signatures = [_signature({**raw, **page, "regions": raw.get("regions") or {}})
                  for page, raw in zip(pages, raw_pages, strict=True)]
    run_start = 0
    for index in range(1, len(signatures) + 1):
        if index == len(signatures) or signatures[index] != signatures[run_start]:
            length = index - run_start
            if length >= 4:
                signals.append(_signal(
                    "repeated-silhouette", "review",
                    f"第 {run_start + 1}–{index} 页的页头高度、标题位置、图片面积和文字密度几乎相同。",
                    "如果这些页不是同构比较，改变主角、尺度或阅读路径：移动标题、放大证据、拆段或换主视觉；不要只换背景色。",
                    pages=list(range(run_start + 1, index + 1)), signature=signatures[run_start]))
            run_start = index
    counts: list[float] = [_num(page["metrics"].get("charCount")) for page in pages]
    counts = [value for value in counts if value > 0]
    density_cv = _cv(counts)
    if len(counts) >= 5 and density_cv is not None and density_cv < 0.18:
        signals.append(_signal(
            "flat-density", "info",
            f"{len(counts)} 页的文字量几乎相同（CV {density_cv}），缺少疏密节奏。",
            "安排一张安静页或一张高密度证据页；让章节、主张、证据各有不同的呼吸，不要每页同样满。",
            cv=density_cv, counts=counts))
    title_ys = [(page.get("headings") or [{}])[0].get("y", 0) for page in raw_pages if page.get("headings")]
    if len(title_ys) >= 5 and statistics.pstdev(title_ys) < 2:
        signals.append(_signal(
            "fixed-title-position", "info",
            "标题几乎每页都在同一高度，页头容易变成模板条。",
            "让标题按页面任务移动：封面、章节、图像主角页可以不同；只保留必要的共同阅读坐标。",
            titleY=round(statistics.fmean(title_ys), 1)))
    families = _unique([family for page in pages for family in page["metrics"].get("fontFamilies", [])])
    if len(families) > 3:
        signals.append(_signal(
            "deck-font-mix", "info",
            f"整套出现 {len(families)} 个字族，跨页亲缘可能变弱。",
            "把字族收敛到展示 + 正文两族；第三族只在数据/代码页出现并说明理由。",
            families=families))
    chromatic = _unique([color for page in pages for color in page["metrics"].get("chromaticColors", [])])
    if len(chromatic) > 10:
        signals.append(_signal(
            "deck-palette-wide", "info",
            f"整套出现 {len(chromatic)} 个高饱和色，强调可能被稀释。",
            "按角色而不是按页面分色：中性主族、一个强调色、一个信号色；其余颜色只服务图像。",
            colors=chromatic[:16]))
    max_image = max([page["metrics"].get("imageAreaRatio") or 0 for page in pages] or [0])
    max_ratio = max([page["metrics"].get("scaleRatio") or 0 for page in pages] or [0])
    max_type = max([page["metrics"].get("maxTypeSize") or 0 for page in pages] or [0])
    if len(pages) >= 3 and max_image < 0.12 and max_ratio < 2.8 and max_type < 72:
        signals.append(_signal(
            "no-hero-page", "review",
            "整套没有一页由大图、大数字或大字承担主视觉，容易全部读成同一强度。",
            "至少设计一页“设计对象”：全出血图、排印海报、单数字数据故事或图作为主角；不是给封面加装饰。",
            maxImageArea=max_image, maxScaleRatio=max_ratio, maxTypeSize=max_type))
    return {"signals": signals, "metrics": {
        "pages": len(pages), "titleY": round(statistics.fmean(title_ys), 1) if title_ys else None,
        "fontFamilies": families, "chromaticColors": chromatic[:16],
        "maxImageAreaRatio": max_image, "maxScaleRatio": max_ratio, "maxTypeSize": max_type,
    }}


async def _inspect(path: Path, *, chrome: str, timeout: float) -> dict:
    connect = _connect()
    report = {"file": str(path), "coordinateSpace": "CSS pixels at 1600×900",
              "scope": "Advisory design signals on completed frames; not a beauty score and not a "
                       "replacement for screenshot review.", "pages": [], "issues": []}
    with tempfile.TemporaryDirectory(prefix="deck-design-signals-") as folder:
        profile = Path(folder) / "profile"
        proc = subprocess.Popen(
            [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
             "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
             "--remote-debugging-port=0", "--remote-debugging-address=127.0.0.1",
             f"--user-data-dir={profile}", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            target = None
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise RuntimeError(f"Chrome exited with status {proc.returncode}")
                try:
                    port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=1) as response:
                        targets = json.load(response)
                    target = next((item["webSocketDebuggerUrl"] for item in targets
                                   if item.get("type") == "page"), None)
                    if target:
                        break
                except (OSError, ValueError, IndexError):
                    pass
                await asyncio.sleep(.05)
            if not target:
                raise RuntimeError("Chrome CDP startup timed out")
            async with connect(target, max_size=None, open_timeout=timeout) as ws:
                sequence = 0

                async def command(method, params=None):
                    nonlocal sequence
                    sequence += 1
                    own_id = sequence
                    await ws.send(json.dumps({"id": own_id, "method": method, "params": params or {}}))
                    while True:
                        message = json.loads(await ws.recv())
                        if message.get("method") == "Runtime.exceptionThrown":
                            details = message.get("params", {}).get("exceptionDetails", {})
                            report["issues"].append({
                                "code": "script-error", "severity": "error",
                                "message": details.get("exception", {}).get("description", details.get("text"))})
                        if message.get("id") == own_id:
                            if "error" in message:
                                raise RuntimeError(f"CDP {method}: {message['error']}")
                            return message.get("result", {})

                async def evaluate(expression):
                    result = await command("Runtime.evaluate", {
                        "expression": expression, "awaitPromise": True, "returnByValue": True})
                    if result.get("exceptionDetails"):
                        details = result["exceptionDetails"]
                        raise RuntimeError(details.get("exception", {}).get(
                            "description", details.get("text", "JavaScript evaluation failed")))
                    return result.get("result", {}).get("value")

                for method in ("Page.enable", "Runtime.enable"):
                    await command(method)
                await command("Emulation.setDeviceMetricsOverride", {
                    "width": 1600, "height": 900, "deviceScaleFactor": 1, "mobile": False})
                await command("Page.addScriptToEvaluateOnNewDocument",
                              {"source": "window.__recording=true;"})
                await command("Page.navigate", {"url": path.as_uri()})
                deadline = time.monotonic() + timeout
                while not await evaluate("document.readyState==='complete'"):
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Document load timed out")
                    await asyncio.sleep(.05)
                contract = await evaluate(
                    "!!(document.querySelector('meta[name=\"deck-web-runtime\"]') && "
                    "window.__deck && typeof __deck.seek==='function' && "
                    "Array.isArray(window.__deck_timeline))")
                if not contract:
                    raise RuntimeError("Expected a compiled web_deck.py artifact with its runtime and timeline")
                readiness = await evaluate("""(async()=>{
                  if(document.fonts) await document.fonts.ready;
                  const images=[];
                  for(const im of Array.from(document.images)){
                    im.loading='eager';
                    try{ if(im.decode) await im.decode(); }catch(e){ images.push(String(im.src)); }
                    if(!im.complete||!im.naturalWidth) images.push(String(im.src));
                  }
                  return {images:[...new Set(images)],
                    fonts:document.fonts?Array.from(document.fonts).filter(f=>f.status==='error').map(f=>f.family):[]};
                })()""")
                if readiness.get("images") or readiness.get("fonts"):
                    report["issues"].append({
                        "code": "readiness-failed", "severity": "warning",
                        "message": "Some fonts or images were not ready; signals still reflect the rendered DOM.",
                        "details": readiness})
                await evaluate(COLLECT_JS)
                timeline = await evaluate("window.__deck_timeline")
                if not isinstance(timeline, list) or not timeline:
                    raise RuntimeError("The compiled artifact has no timeline")
                for index, step in enumerate(timeline):
                    when = step["start"] + step["enter"] + min(.001, step["hold"] / 2)
                    expression = """(async()=>{
                      window.__deck.seek(TIME);
                      await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
                      const slide=document.querySelectorAll('section.slide')[INDEX];
                      if(!slide) throw new Error('Missing slide at index INDEX');
                      return window.__designSignalsCollect(slide);
                    })()""".replace("TIME", json.dumps(when)).replace("INDEX", str(index))
                    report["pages"].append(await evaluate(expression))
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
    return report


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def summarize(raw: dict) -> dict:
    pages = [analyze_page(page) for page in raw.get("pages", [])]
    raw_pages = raw.get("pages", [])
    deck = analyze_deck(pages, raw_pages)
    findings = (raw.get("issues", []) + [signal for page in pages for signal in page["signals"]]
                + deck["signals"])
    errors = sum(item.get("severity") == "error" for item in findings)
    review = sum(item.get("severity") == "review" for item in findings)
    info = sum(item.get("severity") == "info" for item in findings)
    raw["pages"] = pages
    raw["deck"] = deck
    raw["summary"] = {"pages": len(pages), "review": review, "info": info, "errors": errors,
                      "status": "failed" if errors else "signals" if review or info else "clear"}
    return raw


def exit_code(report: dict, strict: bool = False) -> int:
    if report["summary"]["errors"]:
        return 1
    return 2 if strict and report["summary"]["review"] else 0


def inspect(html: str | Path, *, chrome: str | None = None, timeout: float = 30) -> dict:
    path = Path(html).resolve()
    if not path.is_file():
        raise ValueError(f"HTML file does not exist: {path}")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be positive")
    initial = path.read_bytes()
    initial_sha = hashlib.sha256(initial).hexdigest()
    captured_at = _utc_now()
    try:
        binary = browser.find_chrome(chrome)
        raw = asyncio.run(_inspect(path, chrome=binary, timeout=timeout))
    except (RuntimeError, ValueError, OSError, TimeoutError, asyncio.TimeoutError) as exc:
        raw = {"file": str(path), "pages": [], "issues": [{
            "code": "inspection-failed", "severity": "error", "message": str(exc)}]}
    try:
        final = path.read_bytes()
    except OSError as exc:
        raw["issues"].append({"code": "input-changed", "severity": "error",
                              "message": f"Input became unreadable during inspection: {exc}"})
    else:
        if final != initial:
            raw["issues"].append({"code": "input-changed", "severity": "error",
                                  "message": "Input HTML changed during inspection; rerun against a stable artifact",
                                  "observedHtmlSha256": hashlib.sha256(final).hexdigest()})
    raw.update(capturedAt=captured_at, checkedAt=_utc_now(), htmlSha256=initial_sha)
    return summarize(raw)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html", type=Path)
    parser.add_argument("--json", type=Path, help="Write the complete machine-readable report")
    parser.add_argument("--chrome")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--strict", action="store_true",
                        help="Exit 2 when review-level signals are present (signals never block by default)")
    args = parser.parse_args(argv)
    if args.json:
        if args.json.is_symlink():
            parser.error("Report target must not be a symlink")
        if args.json.resolve() == args.html.resolve() or (
                args.json.exists() and args.html.exists() and args.json.samefile(args.html)):
            parser.error("Report target must not overwrite the input HTML")
        if not args.json.parent.is_dir() or (args.json.exists() and not args.json.is_file()):
            parser.error("Report target needs an existing directory and must be a regular file")
    try:
        report = inspect(args.html, chrome=args.chrome, timeout=args.timeout)
    except (RuntimeError, ValueError, OSError, TimeoutError, asyncio.TimeoutError) as exc:
        report = summarize({"file": str(args.html.resolve()), "pages": [],
                            "issues": [{"code": "inspection-failed", "severity": "error",
                                        "message": str(exc)}]})
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = report["summary"]
    print(f"DESIGN SIGNALS: {summary['pages']} pages · {summary['review']} review · "
          f"{summary['info']} info · {summary['errors']} errors")
    for page in [{"slide": "—", "issues": [item for item in report.get("issues", [])
                                            if item.get("severity") == "error"]}] + report["pages"]:
        for signal in page.get("signals", []) if page.get("slide") != "—" else page["issues"]:
            print(f"  [{signal['severity']}] page {page['slide']} {signal['code']}: {signal['message']}")
            print(f"      → {signal['lever']}")
    deck = report.get("deck", {})
    for signal in deck.get("signals", []):
        print(f"  [{signal['severity']}] deck {signal['code']}: {signal['message']}")
        print(f"      → {signal['lever']}")
    if not summary["review"] and not summary["info"] and not summary["errors"]:
        print("  No signals. This does not prove the design is good; look at the pages.")
    print("Advisory only: signals describe observable tells, not a beauty score. "
          "Review screenshots at the intended viewing size before delivery.")
    return exit_code(report, args.strict)


if __name__ == "__main__":
    sys.exit(main())
