#!/usr/bin/env python3
"""从**官方素材库目录**里找图标并下载到本地缓存。

## 为什么要这个工具

内置 sigil 只有十来个图形，而架构图/流程图需要的语义图形远不止这些。
Excalidraw 官方维护着一个社区素材库目录 —— `libraries.excalidraw.com`，
里面有 200+ 个库、几千个图形（通用图标、云厂商、K8s、BPMN、网络拓扑……）。
这个工具把那个目录变成可以**搜、可以取**的东西：

    python3 scripts/icons_fetch.py --list                    # 列出全部官方库
    python3 scripts/icons_fetch.py --list 数据库              # 按库名/图形名过滤
    python3 scripts/icons_fetch.py --search 数据库            # 在图形名里搜，告诉你哪个库里有
    python3 scripts/icons_fetch.py --get "IT icons"          # 下载到本地缓存

下载后 `--library <缓存里的名字>` 或直接 `--library <路径>` 就能用，
见 `references/icons.md`。

## 为什么不把库放进仓库

素材库是第三方作品（几十 KB 到几 MB，授权各不相同）。入库既有体积问题也有许可问题，
所以**只下载到本地缓存**（默认 `~/.cache/diagram-authoring/libraries/`），
并把出处（作者 / 官方来源 / 官方页面）写在 `.meta.json` 旁边 —— 谁的作品一目了然。

## 联网说明

本工具需要网络（首次取索引、下载库）。**它是可选的**：核心出图链路零依赖，
不联网也能用内置 sigil 或本地已有的库。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Sequence

INDEX_URL = "https://libraries.excalidraw.com/libraries.json"
LIBRARY_PAGE = "https://libraries.excalidraw.com/"
RAW_BASE = ("https://raw.githubusercontent.com/excalidraw/"
            "excalidraw-libraries/master/libraries/")
INDEX_TTL_S = 24 * 3600          # 索引缓存 24 小时，避免每次联网
TIMEOUT_S = 90


def _icons_module():
    """加载同目录的 icons.py（缓存目录与"库名解析"都归它管，只留一份真话）。"""
    import importlib.util as _ilu
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons.py")
    spec = _ilu.spec_from_file_location("_diagram_icons_for_fetch", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = _ilu.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def cache_dir(explicit: str | None = None) -> str:
    """缓存目录：命令行 > 环境变量 > 默认（规则住在 icons.py，这里只转一手）。"""
    return _icons_module().cache_dir(explicit)


def slug(text: str) -> str:
    """库名 → 文件名（稳定、可读、无空格）。"""
    got = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return got or "library"


def _get(url: str, timeout: int = TIMEOUT_S) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "diagram-authoring/1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_index(cache: str, refresh: bool = False) -> list[dict]:
    """取官方库索引（含 `itemNames`，所以搜索不用下载任何库）。带本地缓存。"""
    path = os.path.join(cache, "libraries.json")
    fresh = (os.path.isfile(path)
             and time.time() - os.path.getmtime(path) < INDEX_TTL_S)
    if fresh and not refresh:
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            pass                                    # 缓存坏了就重取，不用报错
    raw = _get(INDEX_URL)
    try:
        os.makedirs(cache, exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(raw)
    except OSError:
        pass                    # 缓存写不了不影响这次搜索（下次再取一遍而已）
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"官方索引不是合法 JSON：{exc}") from None


def entry_names(entry: dict) -> list[str]:
    return [str(n) for n in (entry.get("itemNames") or [])]


def entry_url(entry: dict) -> str:
    """库文件的下载地址。官方索引给的是 `作者/文件名` 相对路径。"""
    return RAW_BASE + str(entry.get("source", "")).lstrip("/")


def find_library(index: list[dict], wanted: str) -> dict | None:
    """按名字或 slug 找库（精确优先，其次唯一前缀）。**找不到就返回 None**。"""
    key = slug(wanted)
    for entry in index:
        if str(entry.get("name", "")).strip() == wanted.strip():
            return entry
    for entry in index:
        if slug(str(entry.get("name", ""))) == key:
            return entry
    prefix = [e for e in index if slug(str(e.get("name", ""))).startswith(key)]
    return prefix[0] if len(prefix) == 1 else None


def search(index: list[dict], keyword: str, limit: int = 40) -> list[tuple[dict, list[str]]]:
    """在**图形名**与库名里搜关键词（支持中文 → 英文的常见说法），返回 `[(库, 命中的图形名)]`。"""
    for term in _terms(keyword):
        hits = _search_one(index, term, limit)
        if hits:
            return hits
    return []


def _search_one(index: list[dict], keyword: str, limit: int) -> list[tuple[dict, list[str]]]:
    hits: list[tuple[dict, list[str]]] = []
    low = keyword.strip().lower()
    for entry in index:
        names = entry_names(entry)
        matched = [n for n in names if low in n.lower()]
        if low in str(entry.get("name", "")).lower():
            matched = names[:6] or matched
        if matched:
            hits.append((entry, matched))
    hits.sort(key=lambda item: (-len(item[1]), str(item[0].get("name", ""))))
    return hits[:limit]


# 中文关键词 → 英文常见说法。官方库里项名全是英文（Database / Firewall / …），
# 没有这层的话，模型用中文搜就什么都搜不到。一个词可以对应多个说法，按顺序试。
_ALIASES: dict[str, tuple[str, ...]] = {
    "数据库": ("database", "db"), "库": ("database", "library"),
    "缓存": ("cache", "memory"), "队列": ("queue", "message", "kafka"),
    "消息": ("message", "event"), "服务器": ("server", "host"),
    "主机": ("host", "server"), "容器": ("container", "docker", "pod"),
    "云": ("cloud",), "网络": ("network", "internet"),
    "防火墙": ("firewall", "security"), "安全": ("security", "firewall", "key", "lock"),
    "密钥": ("key", "lock", "password"), "用户": ("user", "person"),
    "人": ("user", "person"), "设备": ("device", "printer"),
    "文档": ("document", "file", "paper"), "文件": ("file", "document", "folder"),
    "文件夹": ("folder", "document"), "图片": ("image", "picture"),
    "邮件": ("email", "message"), "监控": ("monitor", "graph", "signal"),
    "告警": ("warn", "alert", "error"), "日志": ("log", "comment", "notice"),
    "图表": ("graph", "chart", "bar graph", "pie chart"), "指标": ("graph", "signal", "bar chart"),
    "定时": ("timer", "clock", "event"), "计时器": ("timer", "clock"),
    "网关": ("gateway",), "进程": ("process", "model"),
    "模型": ("model",), "搜索": ("search", "magic wand"),
    "索引": ("search", "table", "collection"), "表": ("table", "grid"),
    "链接": ("link",), "关系": ("relationship", "link"),
    "错误": ("error", "warn"), "重试": ("compensation", "escalation", "cancel"),
    "条件": ("conditional", "gateway"), "分支": ("conditional", "exclusive gateway"),
    "并行": ("parallel", "multiple parallel"), "泳道": ("pool", "lifeline"),
    "流程": ("gateway", "event", "block"), "存储": ("drive", "database", "disk"),
    "磁盘": ("drive", "disk", "device"), "服务": ("server", "model", "host"),
    "接口": ("link", "network", "signal"), "认证": ("key", "password", "security"),
}


def _terms(keyword: str) -> list[str]:
    """把关键词展开成"先原文、再英文说法"的候选列表（中文搜不到就换英文）。"""
    got = [keyword]
    low = keyword.strip().lower()
    for zh, en in _ALIASES.items():
        if zh in keyword or low == zh:
            got.extend(en)
    seen: list[str] = []
    for term in got:
        if term and term not in seen:
            seen.append(term)
    return seen


def _write_meta(meta_path: str, entry: dict, url: str) -> bool:
    """把出处写在库文件旁边：第三方作品必须能追到作者与官方来源。

    写不了**不抛**：出处是旁挂信息，不该把已经成功的下载判成失败 ——
    但要如实回报（回执里的 `provenance_written`），不静默。
    """
    try:
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump({"name": entry.get("name"), "authors": entry.get("authors"),
                       "source": entry.get("source"), "url": url,
                       "page": LIBRARY_PAGE,
                       "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S")},
                      fh, ensure_ascii=False, indent=1)
    except OSError:
        return False
    return True


def _cached_item_names(path: str) -> list[str]:
    """已缓存库里的图形名（不重复下载也要能列出内容）。"""
    try:
        with open(path, encoding="utf-8") as fh:
            parsed = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    return [str(i.get("name")) for i in parsed.get("libraryItems", [])
            if isinstance(i, dict) and i.get("name")]


def describe(entry: dict) -> str:
    authors = "、".join(a.get("name", "?") for a in (entry.get("authors") or [])) or "?"
    return f"{entry.get('name')} —— {len(entry_names(entry))} 项 · 作者 {authors}"


def download(entry: dict, cache: str, force: bool = False) -> dict:
    """下载一个库到缓存，并写下出处。返回回执。"""
    name = str(entry.get("name", "")).strip()
    path = os.path.join(cache, slug(name) + ".excalidrawlib")
    meta_path = os.path.join(cache, slug(name) + ".meta.json")
    if os.path.isfile(path) and not force:
        # 出处也要保证在：缓存里的库同样不能"来路不明"（早期版本没写 meta 的也补上）。
        # `wrote` 先按"出处已在"起手 —— 否则 meta 已存在时它会未绑定（真踩过）。
        wrote = True
        if not os.path.isfile(meta_path):
            wrote = _write_meta(meta_path, entry, entry_url(entry))
        return {"ok": True, "stage": "cache", "path": path, "cached": True,
                "items": _cached_item_names(path), "provenance_written": wrote,
                "message": f"缓存里已有 {name}（{os.path.getsize(path) // 1024} KB）"}
    url = entry_url(entry)
    try:
        raw = _get(url)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"ok": False, "stage": "download", "url": url,
                "message": f"下载失败：{exc}"}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {"ok": False, "stage": "download", "url": url,
                "message": f"下载到的不是合法 JSON：{exc}"}
    if parsed.get("type") != "excalidrawlib":
        return {"ok": False, "stage": "download", "url": url,
                "message": "下载到的文件不是 Excalidraw 素材库"}
    try:
        os.makedirs(cache, exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(raw)
        wrote = _write_meta(meta_path, entry, url)
    except OSError as exc:
        return {"ok": False, "stage": "output", "message": f"写不了缓存：{exc}"}
    return {"ok": True, "stage": "download", "path": path, "bytes": len(raw),
            "provenance_written": wrote,
            "items": [i.get("name") for i in parsed.get("libraryItems", [])
                      if isinstance(i, dict)],
            "authors": entry.get("authors"), "url": url, "page": LIBRARY_PAGE}


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="从官方素材库目录里搜/取图标（下载到本地缓存，不入仓库）")
    ap.add_argument("--list", nargs="?", const="", metavar="关键词",
                    help="列出官方库（可选关键词过滤库名或图形名）")
    ap.add_argument("--search", metavar="关键词", help="在图形名里搜，告诉你哪个库里有")
    ap.add_argument("--get", metavar="库名", help="下载某个库到本地缓存")
    ap.add_argument("--url", help="直接按 URL 下载一个 .excalidrawlib（索引里没有的库）")
    ap.add_argument("--dir", help="缓存目录（默认 ~/.cache/diagram-authoring/libraries）")
    ap.add_argument("--refresh", action="store_true", help="强制刷新官方索引缓存")
    ap.add_argument("--force", action="store_true", help="重下已缓存的库")
    ap.add_argument("--json", action="store_true", help="输出机器可读回执")
    args = ap.parse_args(argv)

    if not (args.list is not None or args.search or args.get or args.url):
        ap.print_help()
        return 2

    cache = cache_dir(args.dir)
    try:
        index = fetch_index(cache, refresh=args.refresh)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"✗ 取不到官方索引（{INDEX_URL}）：{exc}", file=sys.stderr)
        print("  这个工具需要联网；离线时可以用内置 sigil（scripts/sigils.py 可列）"
              "或本地已有的 .excalidrawlib。", file=sys.stderr)
        return 2

    if args.search:
        hits = search(index, args.search)
        if not hits:
            print(f"没搜到 {args.search!r}（在 {len(index)} 个官方库里搜库名与图形名）")
            return 1
        print(f"搜到 {len(hits)} 个库含 {args.search!r}：")
        for entry, names in hits:
            print(f"  {describe(entry)}")
            print(f"    命中：{'、'.join(names[:8])}"
                  f"{' …' if len(names) > 8 else ''}")
        print("\n取用：python3 scripts/icons_fetch.py --get \"<库名>\"，"
              "然后 emit 时 --library <库名或缓存路径>")
        return 0

    if args.list is not None:
        key = args.list.strip().lower()
        rows = index
        if key:
            rows = [e for e in index
                    if key in str(e.get("name", "")).lower()
                    or any(key in n.lower() for n in entry_names(e))]
        print(f"官方素材库共 {len(index)} 个，"
              f"{'匹配 ' + repr(args.list) + ' 的 ' if key else ''}{len(rows)} 个：")
        for entry in rows:
            print(f"  {describe(entry)}")
        print(f"\n共 {sum(len(entry_names(e)) for e in rows)} 个图形。"
              f"缓存目录：{cache}")
        return 0

    if args.url:
        entry = {"name": os.path.basename(args.url), "source": "", "authors": []}
        entry["source"] = args.url.replace(RAW_BASE, "")
        got = download(entry, cache, force=True)
    else:
        entry = find_library(index, args.get)
        if entry is None:
            close = [str(e.get("name")) for e in index
                     if e.get("name")
                     and slug(str(e["name"])).startswith(slug(args.get)[:4])][:6]
            print(f"✗ 官方目录里没有 {args.get!r}"
                  + (f"；名字相近的有：{'、'.join(close)}" if close else ""),
                  file=sys.stderr)
            print("  用 --list <关键词> 或 --search <关键词> 找找。", file=sys.stderr)
            return 1
        got = download(entry, cache, force=args.force)

    if args.json:
        print(json.dumps(got, ensure_ascii=False, indent=2))
    if not got["ok"]:
        print(f"✗ 取库失败（{got['stage']}）：{got['message']}", file=sys.stderr)
        return 1 if got["stage"] != "output" else 2
    items = got.get("items") or []
    print(f"✓ {got['message'] if got.get('cached') else '已下载'}：{got['path']}")
    if items:
        print(f"  {len(items)} 个图形：{'、'.join(items[:12])}"
              f"{' …' if len(items) > 12 else ''}")
    if got.get("url"):
        print(f"  出处：{got['url']}（官方目录 {LIBRARY_PAGE}）")
    print(f"  用起来：--library \"{os.path.basename(got['path'])[:-len('.excalidrawlib')]}\""
          f" 或 --library {got['path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
