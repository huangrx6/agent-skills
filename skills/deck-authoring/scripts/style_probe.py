#!/usr/bin/env python3
"""跨站取样：从模板站取回真实的风格候选，而不是由作者凭感觉命名。

为什么要有它
------------
"给我几个风格选项"最容易变成作者编名字：极简、科技、高级、3D 动画——
用户看到的是词，拿到的是另一回事。模板站其实已经把风格编码好了：Canva 把颜色+风格+行业
写进模板标题，Miricanvas 有 Style / Color 筛选器，Oh My PPT 直接用中文风格名，
PPT-Design 用中文题材分类，Dribbble 用视觉风格 tag。**取这些真实字段，比自造风格名可靠。**

站点清单在 `assets/style-sources.json`（一份注册表，文档与脚本共用）。新增站点只改那张表。

取数分四级，拿不到就如实降级，不编内容：

    L1  结构化接口   Miricanvas
    L2  渲染后 DOM   Canva / Dribbble / Oh My PPT（无头 Chrome）
    L3  静态页面     Slidesgo / PresentationGO / PPT-Design
    L0  只给入口     Pitch、以及被 consent 挡住的 Envato

用法
----
    python3 scripts/style_probe.py --list-sites
    python3 scripts/style_probe.py --terms
    python3 scripts/style_probe.py --probe "极简 商务" --limit 4
    python3 scripts/style_probe.py --probe "3d 动画" --sites canva,dribbble,ohmyppt
    python3 scripts/style_probe.py --probe "国风" --sites ohmyppt,ppt-design
    python3 scripts/style_probe.py --probe "gradient" --json checks/style-probe.json

输出是一张候选表：站点 / 类型 / 标题 / 抽出的风格词·颜色词·用途词 / 链接 / 缩略图。
作者再按 `references/style-sources.md` 的格式挑 3–5 个候选交给用户选择。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
REGISTRY = Path(__file__).resolve().parent.parent / "assets" / "style-sources.json"
DEFAULT_SITES = "canva,miri,slidesgo,presentationgo,ppt-design,ohmyppt,dribbble,envato"

# 意图 → 检索词（中文意图先落到站点能搜的词）
INTENT = {
    "3d": "3d", "立体": "3d", "动画": "animated", "动效": "animated",
    "极简": "minimal", "简约": "simple", "简单": "simple", "留白": "minimal",
    "商务": "business", "企业": "corporate", "汇报": "business",
    "科技": "technology", "技术": "tech", "数据": "visual charts", "图表": "infographic",
    "路演": "pitch deck", "融资": "pitch deck", "发布": "product launch",
    "教育": "education", "培训": "education", "医疗": "medical", "金融": "finance",
    "渐变": "gradient", "暗色": "dark", "深色": "dark", "霓虹": "neon",
    "插画": "illustrated", "手绘": "watercolor", "水彩": "watercolor",
    "复古": "vintage", "怀旧": "retro", "拼贴": "scrapbook", "剪贴": "scrapbook",
    "可爱": "cute", "活泼": "playful", "糖果": "pastel", "柔和": "pastel",
    "高级": "elegant", "优雅": "elegant", "编辑": "editorial", "杂志": "magazine",
    "排版": "typographic", "大字": "typographic", "等距": "isometric",
    "玻璃": "glassmorphism", "黏土": "claymorphism", "扁平": "flat",
    "摄影": "photography", "黑白": "black and white", "单色": "monochrome",
    "国风": "国风", "治愈": "治愈", "山水": "山水", "手账": "手账",
}

COLORS = ["black", "white", "beige", "cream", "brown", "red", "pink", "orange", "yellow",
          "green", "blue", "navy", "purple", "gray", "grey", "gold", "dark", "light",
          "pastel", "colorful", "紫", "蓝", "橙", "绿", "红", "米", "黑", "白", "金"]
STYLES = ["minimalist", "minimal", "simple", "modern", "bold", "creative", "elegant",
          "aesthetic", "vintage", "retro", "watercolor", "grunge", "scrapbook", "pastel",
          "cute", "playful", "fun", "abstract", "typographic", "monochrome", "gradient",
          "illustrated", "professional", "traditional", "sentimental", "3d", "isometric",
          "glassmorphism", "neon", "animated", "cool", "collage", "editorial", "flat",
          "国风", "手账", "治愈", "水彩", "复古", "极简", "杂志"]
INDUSTRY = ["business", "education", "marketing", "technology", "tech", "medical",
            "healthcare", "pitch", "deck", "travel", "portfolio", "startup", "sales",
            "finance", "company", "conference", "product", "skincare", "bakery", "gym",
            "project", "brainstorm", "planner", "kids", "game", "nature", "autumn",
            "proposal", "profile", "brief", "report", "webinar", "keynote",
            "商务", "营销", "创业", "金融", "教育", "医疗", "路演", "汇报"]

# 意图 → 站点自己的分类 slug（分类名取自各站导航，不自造）
CANVA_CAT = {"animated": "animated", "动画": "animated", "动效": "animated",
             "simple": "simple", "极简": "simple", "简约": "simple",
             "creative": "creative", "创意": "creative", "cool": "cool",
             "business": "business", "商务": "business", "企业": "business",
             "visual charts": "visual-charts", "图表": "visual-charts", "数据": "visual-charts",
             "pitch deck": "pitch-deck", "路演": "pitch-deck", "融资": "pitch-deck",
             "startup": "startup", "创业": "startup", "sales": "sales", "销售": "sales",
             "finance": "finance", "金融": "finance", "education": "education", "教育": "education",
             "marketing": "marketing", "营销": "marketing", "company": "company",
             "scrapbook": "scrapbook", "拼贴": "scrapbook", "brand guidelines": "brand-guidelines"}
ENVATO_CAT = {"business": "business", "商务": "business", "technology": "technology",
              "科技": "technology", "tech": "technology", "pitch": "pitch+deck",
              "路演": "pitch+deck", "education": "education", "教育": "education",
              "marketing": "marketing", "营销": "marketing", "medical": "medical",
              "医疗": "medical", "infographic": "infographic", "图表": "infographic",
              "portfolio": "portfolio", "corporate": "corporate"}


# ── 基础设施 ────────────────────────────────────────────────────────────────
def load_registry() -> tuple[dict, list]:
    try:
        data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"读不到站点注册表 {REGISTRY}：{exc}")
    return {site["id"]: site for site in data.get("sites", [])}, data.get("groups", [])


def chrome_bin() -> str | None:
    for path in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                 "/Applications/Chromium.app/Contents/MacOS/Chromium"):
        if Path(path).is_file():
            return path
    for name in ("google-chrome", "chromium", "chromium-browser"):
        found = subprocess.run(["which", name], capture_output=True, text=True)
        if found.returncode == 0:
            return found.stdout.strip()
    return None


def render(url: str, budget: int = 9000) -> str:
    chrome = chrome_bin()
    if not chrome:
        return ""
    try:
        out = subprocess.run(
            [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
             f"--virtual-time-budget={budget}", "--window-size=1440,1100",
             f"--user-agent={UA}", "--dump-dom", url],
            capture_output=True, text=True, timeout=90)
        return out.stdout or ""
    except (subprocess.SubprocessError, OSError):
        return ""


def fetch(url: str, budget: int = 0) -> str:
    """budget=0 走静态抓取；否则用无头浏览器渲染。"""
    if budget:
        return render(url, budget)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25) as resp:
            return resp.read().decode("utf-8", "ignore")
    except (urllib.error.URLError, OSError):
        return ""


def get_json(url: str, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json",
                                               **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def classify(text: str) -> dict:
    low = f" {text.lower()} "
    def hit(words: list[str]) -> list[str]:
        found = []
        for w in words:
            if w[0] > "\u4e00":
                if w in text:
                    found.append(w)
            elif re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", low):
                found.append(w)
        return found
    return {"colors": hit(COLORS), "styles": hit(STYLES), "industries": hit(INDUSTRY)}


def slug_title(slug: str) -> str:
    words = [w for w in re.split(r"[-_+]", slug) if w]
    drop = {"template", "powerpoint", "ppt", "presentation", "slides", "google"}
    kept = [w for w in words if w.lower() not in drop] or words
    return " ".join(w.capitalize() if w.islower() else w for w in kept)


def row(site: str, title: str, url: str, kind: str = "模板",
        thumb: str = "", meta: str = "") -> dict:
    return {"site": site, "kind": kind, "title": title, "url": url, "thumb": thumb,
            "meta": meta, **classify(title)}


def matches(text: str, query: str) -> bool:
    if not query:
        return True
    low = text.lower()
    return any(word.lower() in low for word in query.split() if word)


# ── 各站解析 ────────────────────────────────────────────────────────────────
def probe_canva(site: dict, query: str, raw: str, limit: int) -> list[dict]:
    cat = next((CANVA_CAT[w] for w in ([raw] + query.split()) if w in CANVA_CAT), "")
    page = site["category"].format(slug=cat) if cat else site["entry"]
    html = fetch(page, 9000)
    rows, seen = [], set()
    for m in re.finditer(r'<a[^>]+href="/templates/([A-Za-z0-9-]+)/"[^>]*>(.*?)</a>', html, re.S):
        slug = m.group(1)
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(2))).strip()
        if len(title) < 8 or not title[:1].isupper() or slug in seen:
            continue
        if not cat and not matches(title + " " + slug, query):
            continue
        seen.add(slug)
        ident = slug.split("-")[0]
        sizes = re.findall(rf'template\.canva\.com/{ident}/\d+/\d+/(\d+)w-[A-Za-z0-9_-]+\.jpg', html)
        thumb = ""
        if sizes:
            best = max(sizes, key=int)
            found = re.search(rf'(template\.canva\.com/{ident}/\d+/\d+/{best}w-[A-Za-z0-9_-]+\.jpg)', html)
            thumb = "https://" + found.group(1) if found else ""
        rows.append(row("canva", title, f"https://www.canva.com/templates/{slug}/", "模板",
                        thumb, f"canva 分类: {cat}" if cat else ""))
        if len(rows) >= limit:
            break
    return rows


def probe_miri(site: dict, query: str, raw: str, limit: int) -> list[dict]:
    url = site["api"].format(q=urllib.parse.quote(query), n=limit)
    data = get_json(url, {"Referer": "https://www.miricanvas.com/"})
    rows = []
    for item in (data.get("data", {}).get("list") or []):
        title = (item.get("title") or "").strip()
        rows.append(row("miri", title,
                        "https://www.miricanvas.com/en/template/all-types?keyword=" + urllib.parse.quote(title),
                        "模板", item.get("thumb800Url") or item.get("thumbUrl") or "",
                        f"{(item.get('pageCount') or '?')} 页 · {(item.get('tier') or '').lower()}"))
    return rows


def probe_slidesgo(site: dict, query: str, raw: str, limit: int) -> list[dict]:
    html = fetch(site["entry"])
    rows, seen = [], set()
    for slug in re.findall(r'slidesgo\.com/theme/([a-z0-9-]{4,})', html):
        if slug in seen:
            continue
        title = slug_title(slug)
        if not matches(title + " " + slug, query):
            continue
        seen.add(slug)
        rows.append(row("slidesgo", title, site["link"].format(slug=slug), "主题"))
        if len(rows) >= limit:
            break
    return rows


def probe_presentationgo(site: dict, query: str, raw: str, limit: int) -> list[dict]:
    html = fetch(site["entry"])
    rows, seen = [], set()
    for slug in re.findall(r'presentationgo\.com/presentation/([a-z0-9-]{4,})/?["/]', html):
        if slug in seen:
            continue
        title = slug_title(slug)
        if not matches(title + " " + slug, query):
            continue
        seen.add(slug)
        rows.append(row("presentationgo", title, site["link"].format(slug=slug), "图解"))
        if len(rows) >= limit:
            break
    return rows


def probe_pptdesign(site: dict, query: str, raw: str, limit: int) -> list[dict]:
    html = fetch(site["entry"])
    rows, seen = [], set()
    for m in re.finditer(r'href="(https://ppt-design\.com/zh/themes/([a-z0-9-]+))"[^>]*>([\s\S]{0,160}?)</a>', html):
        url, slug, inner = m.group(1), m.group(2), m.group(3)
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", inner)).strip()
        title = re.sub(r"\s*\d+\s*$", "", title)
        if slug in ("business", "marketing", "startup", "finance", "free"):
            title = f"{title}（分类）"
        if not title or len(title) > 24 or slug in seen:
            continue
        if not matches(title + " " + slug, query):
            continue
        seen.add(slug)
        rows.append(row("ppt-design", title, url, "主题", "", f"slug: {slug}"))
        if len(rows) >= limit:
            break
    return rows


def probe_ohmyppt(site: dict, query: str, raw: str, limit: int) -> list[dict]:
    html = fetch(site["entry"], 12000)
    rows, seen = [], set()
    for m in re.finditer(r'alt="([^"]{4,40})"', html):
        title = m.group(1).strip()
        if title.lower() in ("oh my ppt", "close", "logo") or title in seen:
            continue
        if not matches(title, query):
            continue
        seen.add(title)
        rows.append(row("ohmyppt", title, site["entry"], "风格", "", "中文风格名"))
        if len(rows) >= limit:
            break
    return rows


def probe_dribbble(site: dict, query: str, raw: str, limit: int) -> list[dict]:
    style = next((w for w in query.split() if w.lower() in STYLES), "")
    tag = style.lower() if style else "presentation"
    html = fetch(site["tag"].format(slug=tag), 10000)
    rows = [row("dribbble", f"#{tag} 视觉参照", site["tag"].format(slug=tag), "分类", "",
                "看画风，不含成品模板")]
    marks = ("presentation", "deck", "slide", "keynote", "template")
    seen = set()
    for m in re.finditer(r'alt="([^"]{8,90})"', html):
        title = m.group(1).strip()
        low = title.lower()
        if low in seen or len(title.split()) < 2 or not any(w in low for w in marks):
            continue
        seen.add(low)
        rows.append(row("dribbble", title, site["tag"].format(slug=tag), "作品", "", f"tag: {tag}"))
        if len(rows) >= limit:
            break
    return rows


def probe_envato(site: dict, query: str, raw: str, limit: int) -> list[dict]:
    slug = next((ENVATO_CAT[w] for w in ([raw] + query.split()) if w in ENVATO_CAT), "")
    note = "分类页" if slug else "没有对应的风格分类，给用途最近的"
    slug = slug or "pitch+deck"
    return [row("envato", f"{slug.replace('+', ' ')} 分类", site["category"].format(slug=slug),
                "分类", "", note)]


def probe_entry(site: dict, query: str, raw: str, limit: int) -> list[dict]:
    return [row(site["id"], site["name"], site["entry"], "入口", "", site["note"][:40])]


PARSERS = {"canva": probe_canva, "miri": probe_miri, "slidesgo": probe_slidesgo,
           "presentationgo": probe_presentationgo, "pptdesign": probe_pptdesign,
           "ohmyppt": probe_ohmyppt, "dribbble": probe_dribbble, "envato": probe_envato,
           "entry": probe_entry}


# ── 输出 ────────────────────────────────────────────────────────────────────
def keywords(intent: str) -> list[str]:
    words = [w.strip() for w in re.split(r"[\s,，、/]+", intent) if w.strip()]
    return list(dict.fromkeys(INTENT.get(w, w) for w in words))


def print_sites(sites: dict, groups: list[dict]) -> None:
    for group in groups:
        members = [s for s in sites.values() if s["group"] == group["id"]]
        if not members:
            continue
        print(f"\n【{group['name']}】{group['what']}")
        for site in members:
            print(f"  {site['id']:15s} {site['name']}")
            print(f"  {'':15s} 入口：{site['entry']}")
            print(f"  {'':15s} 取数：{site['access']}（parse={site['parse']}）· 轴：{site['axes']}")
            if site["categories"]:
                print(f"  {'':15s} 分类：{'、'.join(site['categories'][:8])}")
            print(f"  {'':15s} 说明：{site['note']}")


def print_terms() -> None:
    print("归一化词表（风格词必须来自站点，不从这张表里自造）：\n")
    for name, words in (("颜色", COLORS), ("视觉风格", STYLES), ("用途 / 行业", INDUSTRY)):
        print(f"  {name}：{'、'.join(words)}")
    print("\n中文意图 → 检索词：")
    print("  " + "；".join(f"{zh}→{en}" for zh, en in list(INTENT.items())[:26]) + " …")
    print("\n站点原词（不要改写成同义词）：Miricanvas Style = Cute / Sentimental / Professional / "
          "Traditional / Fun；Oh My PPT 用中文风格名；PPT-Design 用中文题材；Dribbble 用 tag")


def main() -> int:
    sites, groups = load_registry()
    ap = argparse.ArgumentParser(description="跨站取样真实风格候选")
    ap.add_argument("--list-sites", action="store_true", help="列出站点注册表")
    ap.add_argument("--terms", action="store_true", help="列出归一化词表")
    ap.add_argument("--probe", help="检索词或中文意图，如「极简 商务」「3d 动画」")
    ap.add_argument("--sites", dest="site_list", help=f"逗号分隔，默认 {DEFAULT_SITES}")
    ap.add_argument("--limit", type=int, default=4, help="每站候选数（默认 4）")
    ap.add_argument("--json", dest="json_path", help="同时写出候选 JSON")
    args = ap.parse_args()

    if args.list_sites:
        print_sites(sites, groups)
        return 0
    if args.terms:
        print_terms()
        return 0
    if not args.probe:
        ap.print_help()
        return 0

    wanted = [k.strip() for k in (args.site_list or DEFAULT_SITES).split(",") if k.strip()]
    unknown = [k for k in wanted if k not in sites]
    if unknown:
        print(f"未知站点：{', '.join(unknown)}；可用：{', '.join(sites)}", file=sys.stderr)
        return 2

    queries = keywords(args.probe)
    query = " ".join(queries)
    print(f"检索：{args.probe} → {queries}\n")
    rows, notes = [], []
    for key in wanted:
        site = sites[key]
        parser = PARSERS.get(site.get("parse", "entry"), probe_entry)
        try:
            got = parser(site, query, args.probe, args.limit)
            err = ""
        except Exception as exc:                   # 网络/解析变化都降级，不中断
            got, err = [], f"{type(exc).__name__}: {exc}"
        if got:
            rows.extend(got)
            print(f"✓ {site['name']}：{len(got)} 条（{site['access']}）")
        else:
            notes.append(f"{site['name']}：本轮检索词没命中" + (f"（{err}）" if err else "")
                         + f"，入口 {site['entry']}")
            print(f"· {site['name']}：本轮没命中（站点有内容，换词或直接打开入口）")

    if rows:
        print("\n| # | 站点 | 类型 | 候选 | 风格词 | 颜色词 | 用途词 | 元信息 | 链接 |")
        print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for i, r in enumerate(rows, 1):
            print(f"| {i} | {r['site']} | {r['kind']} | {r['title'][:46]} "
                  f"| {'、'.join(r['styles']) or '—'} | {'、'.join(r['colors']) or '—'} "
                  f"| {'、'.join(r['industries']) or '—'} | {r['meta'] or '—'} | [打开]({r['url']}) |")
        thumbs = [r for r in rows if r["thumb"]]
        if thumbs:
            print("\n缩略图（只记 URL，不下载）：")
            for r in thumbs:
                print(f"  - {r['site']} · {r['title'][:36]}：{r['thumb']}")

        wanted_words = {w.lower() for w in queries + [args.probe] if len(w) > 1}

        def relevant(r: dict) -> bool:
            text = " ".join([r["title"], r.get("meta", ""), *r["styles"], *r["industries"]]).lower()
            return any(w in text for w in wanted_words)

        if len([r for r in rows if relevant(r)]) < 2:
            print("\n⚠ 覆盖度不足：注册表里匹配的风格条目少于 2 条。这通常说明**这个方向不是模板站的常见风格**"
                  "（例如 3D 动画电影、手绘绘本），不要硬套模板——按 style-evidence.md 走 B 档可比拟样张，"
                  "并把 Dribbble / 影片 / 摄影当画风来源。")
        print("\n下一步：挑 3–5 个**来自至少两个分组**的候选交给用户，每个写清「这套像什么、适合什么、"
              "不适合什么」，并让用户能点开看整页。")

    if notes:
        print("\n降级说明：")
        for note in notes:
            print(f"  - {note}")

    payload = {"query": args.probe, "keywords": queries,
               "fetchedAt": time.strftime("%Y-%m-%d %H:%M"), "rows": rows, "degraded": notes}
    if args.json_path:
        target = Path(args.json_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\nJSON：{target}")
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
