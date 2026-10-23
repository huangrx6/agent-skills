#!/usr/bin/env python3
"""Query open font repositories, then download the file you pick.

Built for agents: one index pass, then keyword search, then a single download
command. Nothing here judges type quality; it only finds files and their URLs.

  python3 scripts/font_repos.py --index
  python3 scripts/font_repos.py --search 思源 --cjk
  python3 scripts/font_repos.py --search "Alibaba" --repo zispace/hanzi-fonts
  python3 scripts/font_repos.py --get "zispace/hanzi-fonts:*更多字体/AlibabaPuHuiTi-3-55-Regular.ttf" -o fonts/
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import html
import re
import urllib.parse
import urllib.request
from pathlib import Path

REPOS = {
    "jaywcjlove/free-font": {
        "branch": "main",
        "note": "按厂商/风格分目录，收录带来源与授权说明，适合按风格挑中文艺术字",
    },
    "dengcao/free-fonts": {
        "branch": "main",
        "note": "数量最多（中文约 348 款），适合一次铺开挑选；个别字体有平台或授权限制",
    },
    "zispace/hanzi-fonts": {
        "branch": "main",
        "note": "常用汉字与特色字形，另有 Alibaba PuHuiTi / HarmonyOS Sans / 荣耀等完整中文字库",
    },
}
EXT = (".ttf", ".otf", ".ttc", ".woff2", ".woff")
def _index_path() -> Path:
    explicit = os.environ.get("DECK_FONT_INDEX", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    home = Path(os.environ.get("AGENT_SKILLS_HOME", "~/.agent-skills")).expanduser()
    data = Path(os.environ.get("AGENT_SKILLS_DATA_DIR", home / "data")).expanduser()
    new = data / "deck-authoring" / "font-index.json"
    legacy = Path.home() / ".config" / "deck-authoring" / "font-index.json"
    return legacy if not new.exists() and legacy.exists() else new


INDEX_PATH = _index_path()
# 语言只用来"标注"和"按需筛选"，不是默认限制：拉丁字体同样经常需要
ZH_HINTS = ("中文", "chinese", "han", "cjk", "思源", "黑体", "宋", "楷", "明", "圓", "圆", "漢", "汉", "繁", "简")
EN_HINTS = ("英文", "english", "latin", "serif", "display", "handwriting", "script")


def detect_lang(path: str) -> str:
    """Guess the script a font file targets, from its path only. Never filters by itself."""
    lowered = path.lower()
    cjk_chars = sum(1 for ch in path if "\u3400" <= ch <= "\u9fff")
    if any(hint in lowered for hint in EN_HINTS):
        return "en"
    if any(hint in lowered for hint in ZH_HINTS) or cjk_chars >= 2:
        return "zh"
    return "?"


def _get(url: str, timeout: float = 60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "deck-authoring-font-repos"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _tree(repo: str, branch: str) -> list[dict]:
    url = f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
    try:
        payload = json.loads(_get(url))
    except Exception as exc:  # noqa: BLE001 - network and API errors share one message
        raise SystemExit(f"取不到 {repo} 的文件树：{exc}") from exc
    if "tree" not in payload:
        raise SystemExit(f"{repo} 返回异常：{str(payload)[:160]}")
    if payload.get("truncated"):
        print(f"⚠️ {repo} 的文件树被截断，索引不完整", file=sys.stderr)
    return payload["tree"]


def build_index(repos: list[str], *, quiet: bool = False) -> dict:
    index: dict[str, list[dict]] = {}
    for repo, meta in REPOS.items():
        if repos and repo not in repos:
            continue
        files = [
            {"path": item["path"], "size": item.get("size") or 0}
            for item in _tree(repo, meta["branch"])
            if item["path"].lower().endswith(EXT)
        ]
        index[repo] = files
        if not quiet:
            print(f"{repo}: {len(files)} 个字体文件")
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {"builtAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "repos": REPOS, "index": index}
    INDEX_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    if not quiet:
        print(f"索引已保存：{INDEX_PATH}")
    return index


def load_index(auto: bool = True) -> dict:
    if INDEX_PATH.exists():
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    if not auto:
        raise SystemExit("还没有索引，先运行 --index")
    print("索引不存在，先抓一次……", file=sys.stderr)
    build_index([])
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


def search(keyword: str, *, repo: str | None = None, lang: str | None = None, limit: int = 20) -> int:
    data = load_index()
    hits = []
    lowered = keyword.lower()
    for name, files in data["index"].items():
        if repo and name != repo:
            continue
        for item in files:
            path = item["path"]
            if lowered not in path.lower():
                continue
            guessed = detect_lang(path)
            if lang and guessed != lang:
                continue
            hits.append({"repo": name, "path": path, "size": item["size"], "lang": guessed})
    hits.sort(key=lambda hit: hit["size"])
    if not hits:
        print(f"没有匹配「{keyword}」的字体。换个关键词，或先 --index 更新索引。")
        return 1
    print(f"命中 {len(hits)} 个（按体积从小到大，体积小的多半是子集或单字重）：\n")
    for hit in hits[:limit]:
        mb = hit["size"] / 1024 / 1024
        print(f"  [{hit['lang']}] {mb:6.1f}MB  {hit['repo']}")
        print(f"          {hit['path']}")
        print(f"          取用：python3 scripts/font_repos.py --get \"{hit['repo']}:{hit['path']}\" -o assets/fonts/")
    if len(hits) > limit:
        print(f"\n……另有 {len(hits) - limit} 个未列出，用 --limit 调整。")
    print("\n授权需自行核对：仓库只做了收集与分类，不构成授权判断。")
    return 0


def download(spec: str, out: Path, name: str | None = None) -> int:
    if ":" not in spec:
        raise SystemExit('--get 需要写成 "owner/repo:文件路径"')
    repo, path = spec.split(":", 1)
    if repo not in REPOS:
        raise SystemExit(f"未知仓库 {repo}；可用：" + "、".join(REPOS))
    target = out / (name or Path(path).name)
    quoted = urllib.parse.quote(path)
    urls = [
        f"https://cdn.jsdelivr.net/gh/{repo}@{REPOS[repo]['branch']}/{quoted}",
        f"https://raw.githubusercontent.com/{repo}/{REPOS[repo]['branch']}/{quoted}",
    ]
    target.parent.mkdir(parents=True, exist_ok=True)
    for url in urls:
        try:
            payload = _get(url, timeout=180)
        except Exception as exc:  # noqa: BLE001
            print(f"  失败 {url.split('/')[2]}：{exc}", file=sys.stderr)
            continue
        if len(payload) < 1024:
            continue
        target.write_bytes(payload)
        print(f"✓ {target}  ({len(payload)/1024/1024:.1f}MB, 来自 {url.split('/')[2]})")
        return 0
    raise SystemExit(f"下载失败：{spec}")


def coverage(font_path: Path, source: Path) -> int:
    """检查字体对这份稿子的字符覆盖——缺字会变成方框或回落成别的字体。"""
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        raise SystemExit("需要 fontTools：pip install fonttools brotli")
    if not font_path.exists():
        raise SystemExit(f"字体不存在：{font_path}")
    if not source.exists():
        raise SystemExit(f"要检查的源文件不存在：{source}")
    raw = source.read_text(encoding="utf-8", errors="ignore")
    raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    chars = {c for c in raw if not c.isspace() and ord(c) > 0x1F}
    try:
        cmap = set(TTFont(str(font_path)).getBestCmap().keys())
    except Exception as exc:  # noqa: BLE001 - woff2 需要 brotli 等
        raise SystemExit(f"读不了字体（可能是 woff2 缺 brotli）：{exc}")
    missing = sorted(c for c in chars if ord(c) not in cmap)
    total = len(chars)
    print(f"{font_path.name}: 稿子用字 {total} 个，缺 {len(missing)} 个")
    if missing:
        print("缺字：" + "".join(missing[:80]) + ("…" if len(missing) > 80 else ""))
        print("这些字会回落成别族或显示为方框；换字体、补字，或把它们改成 ASCII/SVG。")
        return 1
    print("覆盖完整，可以放心用作标题/正文字体。")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--index", action="store_true", help="抓取三个仓库的文件树并写入本地索引")
    parser.add_argument("--repos", nargs="*", default=[], help="与 --index 连用，只索引指定仓库")
    parser.add_argument("--list-repos", action="store_true", help="列出内置仓库与用途")
    parser.add_argument("--search", metavar="KEYWORD", help="在索引里按路径关键词查找字体")
    parser.add_argument("--repo", help="限定一个仓库")
    parser.add_argument("--lang", choices=("zh", "en", "?"),
                        help="按脚本筛选（zh 中文 / en 拉丁）；不加则不筛选，结果里会标注 [zh]/[en]")
    parser.add_argument("--cjk", action="store_true", help="等同 --lang zh（保留旧用法）")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--coverage", type=Path, metavar="FONT", help="检查字体对源文件的字符覆盖")
    parser.add_argument("--html", type=Path, help="与 --coverage 连用：要检查的 HTML 源")
    parser.add_argument("--get", metavar="REPO:PATH", help="下载指定字体文件")
    parser.add_argument("-o", "--out", type=Path, default=Path("assets/fonts"))
    parser.add_argument("--name", help="下载后的文件名")
    args = parser.parse_args(argv)

    if args.list_repos or not any([args.index, args.search, args.get, args.coverage]):
        print("可查询的字体仓库：\n")
        for name, meta in REPOS.items():
            print(f"  {name}  ({meta['branch']})")
            print(f"    {meta['note']}")
        print("\n典型流程：--index 一次 → --search 关键词（可加 --lang zh/en）→ --get 落盘 → 在项目 CSS 里声明 @font-face")
        print("提示：不传 --lang 时中英文一起返回，每条结果前标 [zh]/[en]。")
        return 0
    if args.index:
        build_index(args.repos)
        return 0
    if args.coverage:
        if not args.html:
            raise SystemExit("--coverage 需要 --html 指定要检查的源文件")
        return coverage(args.coverage, args.html)
    if args.search:
        lang = "zh" if args.cjk else args.lang
        return search(args.search, repo=args.repo, lang=lang, limit=args.limit)
    return download(args.get, args.out, args.name)


if __name__ == "__main__":
    raise SystemExit(main())
