#!/usr/bin/env python3
"""字体库：清单 + 取字体 + 映射表 + 内嵌。

## 三条实测结论决定了这个模块的形状（都是验过的，不是推断）

1. **字体文件不进仓库**：单款 CJK 字体 5–28MB，126 款就是 1–2GB。仓库只存**清单**
   （`fonts/catalog.json`，纯文本），字体文件落在 `fonts/ttf/` 且**被 .gitignore 挡掉**。
   换台机器跑一次 `fonts.py --fetch` 就有了 —— 与 `h264_encode.swift` 首次编译成
   缓存是同一个模式。

2. **渲染走 `@font-face` 指本地文件，不靠系统装字体**。实测：把字体 cp 进
   `~/Library/Fonts`、字体名也写对，Chrome 仍然回退到 `STSongti-SC-Regular` ——
   macOS 的字体缓存不会因为复制文件就刷新。而 `@font-face` 指本地路径立刻生效，
   且**顺带解决了 PDF 内嵌**（见下）。

3. **PDF 会子集内嵌字体**：实测一份 25MB 的霞鹜文楷，出的 PDF 总共 **62KB**，
   里面是 `AAAAAA+SmileySans-Oblique` 这样的**子集**（只含用到的字形）。
   所以 **PDF 交付对方不需要装任何字体**。而 **PPTX 只存字体名**，对方没装就由宿主
   替换 —— 这就是"分享出去会不会出事"的分水岭。逐格式结论见 `references/fonts.md`。

跑法：
    python3 scripts/fonts.py --list                 # 清单（126 款）
    python3 scripts/fonts.py --list --urls          # 带上来源页地址
    python3 scripts/fonts.py --installed            # 本地已取到哪些
    python3 scripts/fonts.py --fetch --tier A       # 取能直接下的那批
    python3 scripts/fonts.py --map                  # 字体 ↔ 风格映射表
    python3 scripts/fonts.py --embed out.html -o portable.html
"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import os
import re
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
CATALOG = os.path.join(SKILL, "fonts", "catalog.json")
MAPPING = os.path.join(SKILL, "fonts", "mapping.json")
# 字体文件**不落在 skill 目录里**。三个候选位置，按需选：
#   · `$DECK_FONT_DIR`           —— 显式指定（CI / 一次性用临时目录就靠它）
#   · `~/.config/deck-authoring/fonts` —— 默认。**持久**：单款 CJK 5–28MB，
#     每次重下太浪费；换台机器也就下一次。
#   · `tempfile.gettempdir()/...` —— 给 `--temp` 用：不在这台机器上留东西。
#
# 为什么不在 skill 目录：skill 目录是**可分发的代码**，不该长出自下载的二进制。
# 仓库里 h264 编码器早就是这个规矩（编译进 tempdir 按源码哈希命名），字体照同一个
# 思路。旧的 `fonts/ttf/` 仍然**会被读**（已经下了的人不用重下），但**不再往里写**。
LEGACY_DIR = os.path.join(SKILL, "fonts", "ttf")
CACHE_DIRNAME = "deck-authoring"

FONT_SUFFIXES = (".ttf", ".otf", ".ttc", ".woff2")

# 认字体时要求记号至少这么长。理由见 `installed_names()`：`ar` / `sans` / `kai`
# 这种短记号在长文件名里到处都是，做子串匹配必然误报。
MIN_TOKEN = 5

# ═══════════════════════════════════════════════════════════════════════════
# **严格 A** —— "没有 license 也能用"的那一档
#
# 判据是 license **恰好等于** "A"，不是 `startswith("A")`。`"A/B"` 不算：
# 它意味着某个来源标了 A、另一个标了 B，而 B 有署名 / 地区 / 禁商标 / **禁嵌入**
# 等限制。把字体嵌进交付物属于**再分发**，比"自己用"敏感 —— 对没有 license 的人
# 来说，含糊等于不能用。
#
# 所以 `--fetch` 与 `--list --license A` 都按**严格相等**比较；`--map --a-only`
# 给出一整套纯 A 的字体方案（`mapping.json` 的 `a_only`）。
# ═══════════════════════════════════════════════════════════════════════════
FREE_LICENSE = "A"

# 取字体时默认只取这一档。想连 B/C 一起看要显式给 `--tier all`。
DEFAULT_TIER = FREE_LICENSE

# 同一个字族有多个格式时，按这个顺序挑。**实测排出来的，不是偏好**：
# 同一个得意黑，`.otf` 那份 Chrome **完全不嵌**（`@font-face` 指它，出 PDF 零字体、
# 文件 40KB），`.ttf` 那份就正常嵌成 `AAAAAA+SmileySans-Oblique`（45KB）。
# 所以 `.ttf` 优先；`.otf` 只在没有 `.ttf` 时用。
FORMAT_PREFERENCE = (".ttf", ".otf", ".ttc", ".woff2")


def _load_sibling(name: str):
    """动态加载同目录脚本（`scripts/` 不是包，同级 import 在静态层面无法解析）。"""
    key = f"_deck_{name}"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, os.path.join(HERE, f"{name}.py"))
    if spec is None or spec.loader is None:
        raise SystemExit(f"✗ 加载不了 scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


deckio = _load_sibling("deckio")

# ═══════════════════════════════════════════════════════════════════════════
# 能直接下载的那一批（**只收录验证过的仓库**，不凭印象填 URL）
#
# 为什么这么少：126 款里绝大多数只在字体站上分发，下载要走页面（有的还要登录 /
# 领授权）。凡是没能验证直链的，`--fetch` 就**如实说"去来源页拿"**，而不是编一个
# URL 让命令静默失败。
#
# 版本号不写死：运行时问 GitHub API 要 latest release 的资产名 —— 硬编码
# `v2.0.1.zip` 这种会在作者发新版那天静默 404。
# ═══════════════════════════════════════════════════════════════════════════
FETCHABLE = [
    # (catalog 名, owner/repo, 资产名匹配, 授权)
    ("得意黑 Smiley Sans", "atelier-anchor/smiley-sans", r"smiley-sans.*\.zip$", "OFL-1.1"),
    ("霞鹜文楷", "lxgw/LxgwWenKai", r"LXGWWenKai-Regular\.ttf$", "OFL-1.1"),
    # Mono 变体是 terminal 那套的中文等宽来源（中文名「霞鹜文楷等宽」）。
    # 它是同一个 catalog 条目的变体，所以这里另起一行 —— 名字用真实字族名，
    # 否则 _local_path_for 找不到它。
    ("LXGW WenKai Mono", "lxgw/LxgwWenKai", r"LXGWWenKaiMono-Regular\.ttf$", "OFL-1.1"),
    ("霞鹜文楷 TC", "lxgw/LxgwWenKaiTC", r"LXGWWenKaiTC-Regular\.ttf$", "OFL-1.1"),
    ("清松手写体 1", "jasonhandwriting/JasonHandwriting", r"[Jj]asonHandwriting1.*\.(ttf|otf|zip)$", "OFL-1.1"),
    # 资产名有 66 个变体：bdf / dfont / otb / pcf / woff / woff2 / ms.bitmap.ttf
    # 都不是能直接用的字体。第一版用了宽松的 `.*(12px|font).*\.zip$`，
    # 结果抓到一个 16MB 的 **BDF 点阵**包（不能用，也没解出任何字体）——
    # 所以要**钉住 -(proportional|monospaced)-ttf-v** 这一段。
    ("Fusion Pixel Font", "TakWolf/fusion-pixel-font",
     r"fusion-pixel-font-12px-proportional-ttf-v.*\.zip$", "MIT"),
]

GITHUB_API = "https://api.github.com/repos/{repo}/releases/latest"
UA = {"User-Agent": "deck-authoring-fonts"}
TIMEOUT = 300


def tier_matches(license_code: str, tier: str | None) -> bool:
    """某个授权级算不算落在要取的这一档里。

    **严格相等**，不是 `startswith` —— 见 `FREE_LICENSE` 那段：`"A/B"` 在
    选 A 的时候**不算通过**。这条抽成函数是为了能测：写在内联判断里的话，
    "A/B 被当成 A 放过去"这种错只能靠人盯。
    """
    if not tier or tier == "all":
        return True
    return license_code == tier


def catalog() -> list[dict]:
    return deckio.read_json(CATALOG).get("fonts", [])


def by_name(name: str) -> dict | None:
    for f in catalog():
        if f["name"] == name:
            return f
    return None


def owner_of(name: str) -> dict | None:
    """这个名字归**清单里的哪个条目** —— 认不出就 None。

    一个条目可能被叫三种名字：清单名（`霞鹜文楷`）、字体真名（`LXGW WenKai`）、
    变体名（`LXGW WenKai Mono`）。三者在映射表、样式栈、测试里都会出现，
    所以"谁是谁"必须只有一处定义 —— 之前把它抄进测试里，抄错了一次
    （合成了个缺 `match` 字段的 dict，于是带 `match` 的条目全部认不出来）。
    """
    exact = by_name(name)
    if exact is not None:
        return exact
    low = _norm(name)
    for entry in catalog():
        # 拉丁记号（"lxgwwenkai" 认得 "LXGW WenKai Mono"）
        if low and any(tok and tok in low for tok in _file_tokens(entry)):
            return entry
        # **中文名**：`_norm` 只留 [a-z0-9]，中文全被抹掉 —— 所以中文必须另走一路。
        # 实测踩过：映射表写"汇文明朝体"（清单里是"汇文明朝体（修正版）"），
        # 只认拉丁记号时认不出来，而那一款明明是纯 A。
        cjk_low = _norm_cjk(name)
        if len(cjk_low) >= CJK_MIN:
            cjk_entry = _norm_cjk(entry["name"])
            if cjk_low in cjk_entry or cjk_entry in cjk_low:
                return entry
    return None


def cache_dir(temp: bool = False) -> str:
    """字体文件该放（该找）哪个目录。

    优先级：`$DECK_FONT_DIR` > `~/.config/deck-authoring/fonts` > 临时目录。
    环境变量排第一，是为了让"下载到哪"这件事**可被调用方决定** —— 做 PPT 的 AI
    可以按实际情况选持久目录或临时目录，不用改代码。
    """
    env = os.environ.get("DECK_FONT_DIR")
    if env:
        return os.path.abspath(env)
    if temp:
        import tempfile   # noqa: PLC0415

        return os.path.join(tempfile.gettempdir(), CACHE_DIRNAME, "fonts")
    return os.path.join(os.path.expanduser("~"), ".config", CACHE_DIRNAME, "fonts")


def search_dirs(temp: bool = False) -> list[str]:
    """按顺序找字体的所有目录（缓存在前，旧的 skill 目录兜底只读）。"""
    return [cache_dir(temp), LEGACY_DIR]


def local_files(temp: bool = False) -> list[str]:
    """本地已有哪些字体文件（已排序，按文件名去重）。

    **这是"能不能渲染"的真凭据** —— 不是"系统里装没装"。因为渲染走 `@font-face`
    指本地文件，系统装没装其实无关。

    同时扫缓存目录与旧的 skill 目录：已经下过的人不用重下，而新下载只进缓存。
    """
    out: list[str] = []
    seen: dict[str, str] = {}
    for d in search_dirs(temp):
        for suffix in FONT_SUFFIXES:
            for fn in deckio.list_files(d, suffix):
                if fn not in seen:
                    seen[fn] = os.path.join(d, fn)
    for fn in sorted(seen):
        out.append(seen[fn])
    return out


def local_paths() -> dict[str, str]:
    """文件名 → 完整路径（给需要按名字找文件的地方用）。"""
    return {os.path.basename(p): p for p in local_files()}


def local_families() -> dict[str, str]:
    """读本地每个字体文件**自己声明的**字族名 → 文件路径。

    为什么不按文件名猜：catalog 里的"得意黑 Smiley Sans"和字体内部的 family
    （实测是 `Smiley Sans Oblique`）本来就不是同一个字符串。字形文件自己写着
    真名，读它比猜它可靠 —— 我之前手写字体探测翻过车，就是栽在猜名字上。
    """
    families: dict[str, str] = {}
    for path in local_files():          # local_files() 给的是完整路径
        for fam in _font_families(path):
            families.setdefault(fam, path)
    return families


def _font_families(path: str) -> list[str]:
    """解析 TTF/OTF 的 name 表（nameID 1 / 16），拿字族名。解析不了就返回空。

    只读需要的两处，不引第三方库 —— 装 fontTools 只为一件事不值。
    """
    import struct   # noqa: PLC0415

    try:
        data = deckio.read_bytes(path)
    except SystemExit:
        return []
    if len(data) < 12 or data[:4] not in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
        return []
    try:
        n_tables = struct.unpack(">H", data[4:6])[0]
        tables: dict[str, tuple[int, int]] = {}
        off = 12
        for _ in range(n_tables):
            tag = data[off:off + 4].decode("latin-1")
            o, ln = struct.unpack(">II", data[off + 8:off + 16])
            tables[tag] = (o, ln)
            off += 16
        if "name" not in tables:
            return []
        base = tables["name"][0]
        _fmt, count, str_off = struct.unpack(">HHH", data[base:base + 6])
        out: list[str] = []
        for i in range(count):
            rec = base + 6 + i * 12
            pid, eid, _lid, nid, ln, so = struct.unpack(">HHHHHH", data[rec:rec + 12])
            if nid not in (1, 16):
                continue
            raw = data[base + str_off + so:base + str_off + so + ln]
            try:
                text = raw.decode("utf-16-be") if (pid == 3 or eid == 1) else raw.decode("latin-1")
            except (UnicodeDecodeError, LookupError):
                continue
            if text and text not in out:
                out.append(text)
        return out
    except (struct.error, IndexError, ValueError):
        return []


def installed_names() -> set[str]:
    """catalog 里哪些字体在本地已经就位。

    判据是"本地真有一个字族名 / 文件名配得上它"，两边都**归一化后**比。

    **宁漏不错**：报"已就位"但其实是回退，会静默渲出一份字体不对的 deck；而漏报
    只是让人多看一眼 `--installed`。第一版就是错的 —— 用短记号做子串匹配，
    `AR PL UKai` 的 `ar` 撞上 `Regul**ar**`、`OPPO **Sans**` 撞上 `Smiley**Sans**`，
    只下了 4 款却报"已就位 8 款"。所以现在要求记号 **≥5 个字符**，
    且比对对象是字体**自己声明的**字族名 + 文件名（都去掉非字母数字、转小写）。
    """
    haystacks = [_norm(f) for f in local_families()]
    haystacks += [_norm(f) for f in local_files()]
    have = [h for h in haystacks if h]
    out = set()
    for f in catalog():
        for tok in _file_tokens(f):
            if any(tok in h for h in have):
                out.add(f["name"])
                break
    return out


def _norm(text: str) -> str:
    """归一化：只留字母数字、转小写。比较前两边都要过这一步。

    **中文会被整个抹掉** → 需要认中文名的地方要用 `_norm_cjk`。
    """
    return re.sub(r"[^a-z0-9]", "", text.lower())


# 中文名匹配要求至少这么多个字。太短的中文（"站酷"）会在别的名字里到处出现。
CJK_MIN = 4


def _norm_cjk(text: str) -> str:
    """归一化，但**保留汉字**：只留汉字、字母、数字。

    为什么需要它：`_norm` 把中文全抹了，于是"汇文明朝体"归一化后是空串，
    **永远匹配不上**任何东西（实测：映射表里那一款因此认不出来）。
    """
    return re.sub(r"[^\u4e00-\u9fffa-z0-9]", "", text.lower())


def _file_tokens(entry: dict) -> list[str]:
    """这个清单条目可以用哪些记号去认它。**返回的都是可用的**（长度已过滤）。

    优先用 catalog 里显式验证过的 `match`（纯中文名的款只能靠它 ——
    "霞鹜文楷"这个名字里没有任何能和 `LXGWWenKai` 对上的拉丁记号）；
    否则退回名字里的拉丁词。

    **短记号在这里就滤掉**，不留给调用方：`AR PL UKai` 会产出 `ar`、`pl`、`ukai`，
    `OPPO Sans 4.0` 会产出 `sans` —— 这些在长文件名里到处都是（`Regul**ar**`、
    `Smiley**Sans**`）。过滤散在三个调用点上，漏一处就又是那次的假阳性
    （只下了 4 款却报"已就位 8 款"）。**返回空表 = 这款字认不出来**，
    那只是漏报（人工放进 fonts/ttf/ 即可），比误报安全得多。
    """
    if entry.get("match"):
        toks = [_norm(entry["match"])]
    else:
        toks = [_norm(t) for t in re.findall(r"[A-Za-z][A-Za-z0-9]+", entry["name"])]
    return [t for t in toks if len(t) >= MIN_TOKEN]


def _github_assets(repo: str) -> list[tuple[str, str]]:
    """问 GitHub 要 latest release 的资产（名称 + 下载地址）。拿不到就抛 SystemExit。"""
    try:
        req = urllib.request.Request(GITHUB_API.format(repo=repo), headers=UA)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            rel = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            OSError, ValueError) as exc:
        raise SystemExit(f"✗ 拿不到 {repo} 的 release：{type(exc).__name__}") from exc
    return [(a.get("name", ""), a.get("browser_download_url", ""))
            for a in rel.get("assets", [])]


def _download(url: str) -> bytes:
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        raise SystemExit(f"✗ 下载失败：{type(exc).__name__}") from exc


def fetch(only: list[str] | None = None, tier: str | None = None,
          quiet: bool = False, temp: bool = False) -> tuple[int, list[str]]:
    """取能直接下的那批。返回 (成功数, 消息)。取不下来的如实说去哪儿拿。"""
    target_dir = cache_dir(temp)
    deckio.ensure_dir(target_dir)
    if not quiet:
        print(f"字体目录：{target_dir}"
              + ("（临时；用 $DECK_FONT_DIR 可指定别处）" if temp else ""))
        legacy = deckio.list_files(LEGACY_DIR, ".ttf") + deckio.list_files(LEGACY_DIR, ".otf")
        if legacy:
            print(f"  ⚠️ 旧的 skill 目录里还留着 {len(legacy)} 个字体文件"
                  f"（会被读取，但新下载不再往里写）—— 想清掉：rm -rf fonts/ttf")
    cats = deckio.read_json(CATALOG)
    srcs = cats.get("sources", {})
    ok = 0
    msgs: list[str] = []
    for name, repo, asset_pat, lic in FETCHABLE:
        entry = owner_of(name)
        if entry is None:
            msgs.append(f"⚠️ 清单里没有 {name!r} —— 清单与下载表脱节了")
            continue
        if only and name not in only:
            continue
        if not tier_matches(entry["license"], tier):
            continue
        if name in installed_names():
            msgs.append(f"✓ 已有 {name}")
            ok += 1
            continue
        url = srcs.get(entry["source"], {}).get("url", "?")
        try:
            assets = _github_assets(repo)
        except SystemExit as exc:
            msgs.append(f"✗ {name}：{exc} —— 去来源页拿：{url}")
            continue
        want = [a for a in assets if re.search(asset_pat, a[0], re.IGNORECASE)]
        if not want:
            names = ", ".join(a[0] for a in assets[:6]) or "（这个 release 没有资产）"
            msgs.append(f"✗ {name}：release 里没有匹配 {asset_pat!r} 的资产（现有：{names}）")
            continue
        aname, aurl = want[0]
        try:
            blob = _download(aurl)
        except SystemExit as exc:
            msgs.append(f"✗ {name}：{exc}")
            continue
        dest = os.path.join(target_dir, aname)
        deckio.write_bytes(dest, blob)
        msg = f"✓ {name} ← {aname}（{len(blob) / 1e6:.1f}MB，{lic}）"
        unpacked = _unpack(dest)
        if unpacked:
            msg += f" → 解出 {len(unpacked)} 个字体文件"
        msgs.append(msg)
        ok += 1
    if not quiet:
        for m in msgs:
            print(m)
    return ok, msgs


def _unpack(path: str) -> list[str]:
    """zip 里全是字体就解开（得意黑那种一个 zip 一个字体）。

    解到**这个 zip 所在目录**，不是写死的某个常量 —— 字体可能来自 `DECK_FONT_DIR`
    指定的任意位置。
    """
    import zipfile   # noqa: PLC0415

    if not path.lower().endswith(".zip"):
        return []
    out: list[str] = []
    target_dir = os.path.dirname(os.path.abspath(path))
    try:
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                if not n.lower().endswith((".ttf", ".otf")):
                    continue
                target = os.path.join(target_dir, os.path.basename(n))
                deckio.write_bytes(target, z.read(n))
                out.append(target)
    except (zipfile.BadZipFile, OSError):
        return []
    if out:
        deckio.remove(path)          # 保留解出来的字体，去掉压缩包
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 内嵌：把字体做成 base64 的 @font-face
# ═══════════════════════════════════════════════════════════════════════════

# 单款 CJK 字体 5–28MB，base64 之后还要 ×1.33 —— 一个 deck 内嵌两三款就是 100MB+
# 的 HTML。而 **Chrome 出 PDF 时已经自动做子集了**，所以这里不去自己做子集
# （那要解析字形表），而是：超上限就**如实拒绝并指出走 PDF**。
EMBED_LIMIT_MB = 40


def embed(html_path: str, out_path: str) -> str:
    """把 `@font-face` 内联进 HTML（base64），让 HTML 单文件也能带字体。

    实测过的必要性：`@font-face` 指本地文件在**本机**渲染没问题、PDF 也会内嵌，
    但 HTML 换个目录 / 换台机器就断（和 `image` 字段的相对路径是同一个坑）。
    """
    src = deckio.read_text(html_path)
    picks = _families_from_css(src)
    if not picks:
        raise SystemExit("✗ 这份 HTML 里没有可内嵌的 `@font-face`（带本地文件的那些）")
    total = 0.0
    blocks = []
    for fam, path in picks.items():
        if not os.path.isfile(path):
            raise SystemExit(f"✗ 内嵌 {fam!r} 失败：找不到字体文件 {path}")
        size_mb = os.path.getsize(path) / 1e6
        total += size_mb
        if total > EMBED_LIMIT_MB:
            raise SystemExit(
                f"✗ 内嵌后 HTML 会超过 {EMBED_LIMIT_MB}MB（{fam} 一档就 {size_mb:.1f}MB）"
                f"—— CJK 字体整款内嵌不划算。要单文件交付就**导出 PDF**："
                f"Chrome 只嵌用到的字形，实测 25MB 的霞鹜文楷进 PDF 总共 62KB")
        b64 = base64.b64encode(deckio.read_bytes(path)).decode("ascii")
        fmt = css_format(path)
        blocks.append(f'@font-face{{font-family:"{fam}";'
                      f'src:url(data:font/{fmt};base64,{b64}) format("{fmt}")}}')
    injected = "<style>" + "".join(blocks) + "</style>"
    marker = "</style>"
    src = (src.replace(marker, injected + marker, 1) if marker in src
           else injected + src)
    deckio.write_text(out_path, src)
    return f"{out_path}（内嵌 {len(picks)} 款，约 {total:.1f}MB）"


def _families_from_css(html: str) -> dict[str, str]:
    """从 HTML 里找 `@font-face` 的 family → 本地文件路径。"""
    out: dict[str, str] = {}
    for m in re.finditer(r"@font-face\s*\{([^}]*)\}", html):
        body = m.group(1)
        fam = re.search(r"font-family\s*:\s*[\"']([^\"']+)[\"']", body)
        url = re.search(r"url\(\s*[\"']?([^\"')]+)", body)
        if fam and url and not url.group(1).startswith("data:"):
            out[fam.group(1)] = url.group(1)
    return out


def face_css(font_stacks: list[str]) -> str:
    """给这些字体栈生成 `@font-face` 规则 —— **只对本地真有文件的字体**。

    契约：样式栈里写**字体名**（清单名 `霞鹜文楷`、真名 `LXGW WenKai`、或变体名
    `LXGW WenKai Mono` 都行），渲染时自动注入对应的 `@font-face`。这样：
      · 装上就能用，不需要"把字体装进系统"（实测 macOS 缓存不刷新，装对了也回退）；
      · Chrome 出 PDF 时会把用到的字形**子集内嵌**（实测 25MB 字体 → PDF 62KB），
        读者那边不需要有这款字；
      · 本地没取的字体**静默跳过** —— 栈里还有回退项，不会画出裂图，
        具体谁顶上由 `check.py` 的字体回退提示说清楚。

    **按本地文件走，不按清单条目走** —— 这是一个改对了的地方：原先每个清单条目只挑
    一个文件（`_local_path_for` 按格式优先级选一个），于是"霞鹜文楷的等宽变体"
    永远选不中，`terminal` 那套写 `LXGW WenKai Mono` 时**一条 @font-face 都没注入**，
    浏览器静默回退（实测）。改成遍历本地文件、按它**自己声明的**每个字族名注入，
    三种写法就都能对上了。

    用**绝对路径**：产物与字体不在同一个目录，相对路径会随产物移动而断。
    要单文件 HTML 就再跑 `fonts.py --embed`。
    """
    stacks = " ".join(font_stacks or [])
    if not stacks:
        return ""
    norm = _norm(stacks)
    # family → 候选文件。**按家族先去重再挑文件**：同一个字族常有 .otf 与 .ttf 两份，
    # 各注一条的话浏览器会拿到两个同族 @font-face，谁生效取决于顺序 —— 而实测
    # `.otf` 那份 Chrome 根本不用（见 FORMAT_PREFERENCE）。所以一个家族只留一条。
    wanted: dict[str, list[str]] = {}
    for path in local_files():
        for fam in _injectable_names(path):
            # 两种都认：· 归一化后是子串（拉丁名，"LXGW WenKai Mono"）
            #          · 字面出现（中文名，"霞鹜文楷等宽" —— `_norm` 只留 [a-z0-9]，
            #            中文名归一化后是空串，光靠归一化永远匹配不上）
            if (len(_norm(fam)) >= MIN_TOKEN and _norm(fam) in norm) or fam in stacks:
                wanted.setdefault(fam, []).append(path)
        # 栈里写**清单名**的写法：清单名和字体真名不是一回事，得单独认
        for name in _catalog_names_for(path):
            if name in stacks:
                wanted.setdefault(name, []).append(path)
    rules = []
    for fam, paths in wanted.items():
        path = _preferred(paths)
        if not path:
            continue
        url = "file://" + os.path.abspath(path)
        rules.append(f'@font-face{{font-family:"{fam}";'
                     f'src:url("{url}") format("{css_format(path)}")}}')
    return "\n".join(rules)


def _injectable_names(path: str) -> dict[str, str]:
    """这份字体文件可以用来注入哪些 family 名（都是它**自己声明的**）。"""
    return {fam: path for fam in _font_families(path)}


def _catalog_names_for(path: str) -> list[str]:
    """这份文件对应清单里的哪个条目名（认不出就空）。

    三种都对：· 文件路径就是该条目挑中的那个；· 文件名里带该条目的记号；
    · 文件声明的字族名里带该条目的记号（Mono 变体就靠这条归属到"霞鹜文楷"）。
    """
    out: list[str] = []
    base = _norm(os.path.basename(path))
    fams = [_norm(f) for f in _font_families(path)]
    for entry in catalog():
        if _local_path_for(entry) == path:
            out.append(entry["name"])
            continue
        for tok in _file_tokens(entry):
            if tok and (tok in base or any(tok in f for f in fams)):
                out.append(entry["name"])
                break
    return out


def css_format(path: str) -> str:
    """文件后缀 → CSS `format()` 关键字。

    **不能一律写 `truetype`**：实测一款 `.otf`（得意黑的 `SmileySans-Oblique.otf`）
    带上 `format("truetype")` 之后 Chrome **直接不用它**，静默回退 —— 而字体明明
    装着、名字也对。产物里看着一切正常，只有 PDF 里少一款字才露出来。
    """
    low = path.lower()
    if low.endswith(".woff2"):
        return "woff2"
    if low.endswith((".otf", ".ttc")):
        return "opentype"
    return "truetype"


def _names_font(entry: dict, raw_stacks: str, norm: str) -> bool:
    """这个字体栈有没有点名这款字体。

    **两条都可能**，所以都要查：
      · 写**清单名**（`霞鹜文楷`、`得意黑 Smiley Sans`）—— 这是本 skill 的契约写法；
      · 写字体**自己的字族名**（`LXGW WenKai`、`Smiley Sans Oblique`）—— 手写
        style.json 的人很自然会这么写。

    第一版只查了拉丁记号，于是中文名的写法全落空 —— 而且 `_norm` 会把中文整个
    抹掉（只留 `[a-z0-9]`），所以"霞鹜文楷"归一化之后是空串，**永远不可能匹配**。
    实测：一个 display 用得意黑、body 用霞鹜文楷的风格，只注入了前者。
    """
    if entry["name"] in raw_stacks:
        return True
    return any(tok and tok in norm for tok in _file_tokens(entry))


def _local_path_for(entry: dict) -> str | None:
    """这个清单条目对应本地哪个字体文件（没有就 None）。

    同一个字族有多个格式时按 `FORMAT_PREFERENCE` 挑 —— 见那里的实测理由
    （`.otf` 那份 Chrome 不用）。
    """
    for tok in _file_tokens(entry):
        cands = [p for fam, p in local_families().items() if tok in _norm(fam)]
        cands += [p for p in local_files() if tok in _norm(os.path.basename(p))]
        best = _preferred(cands)
        if best:
            return best
    return None


def _preferred(paths: list[str]) -> str | None:
    """按格式优先级在这些候选里挑一个。"""
    for suffix in FORMAT_PREFERENCE:
        for p in sorted(set(paths)):
            if p.lower().endswith(suffix):
                return p
    return None


def mapping() -> dict:
    return deckio.read_json(MAPPING)


def print_map(as_md: bool = False, a_only: bool = False) -> None:
    """字体 ↔ 风格映射表。

    `a_only=True` 时只打**严格 A** 那一套 —— 给"没有 license"的人用，
    里面每一款都能下载、安装、嵌进交付物。
    """
    mp = mapping()
    if a_only:
        print("字体 ↔ 风格映射（**纯 A 档**：每一款都能免费商用、可嵌入交付物）\n")
        for style, roles in mp["a_only"]["styles"].items():
            label = mp["styles"].get(style, {}).get("label", style)
            print(f"── {style}（{label}）")
            for role, pick in roles.items():
                print(f"     {role:14} {pick}")
        print()
        print(mp["a_only"]["why"])
        return
    if as_md:
        print("# 字体 ↔ 风格映射\n")
        for style, row in mp["styles"].items():
            print(f"## {style}（{row['label']}）\n")
            print(f"- 温度：{row['temperature']}")
            for role, pick in row["roles"].items():
                print(f"- **{role}**：{pick}")
            print()
        return
    for style, row in mp["styles"].items():
        print(f"── {style}（{row['label']} / {row['temperature']}）")
        for role, pick in row["roles"].items():
            print(f"     {role:14} {pick}")
    print()
    print("── 六类艺术字各适合什么用途（更细的一层，来自清单的 for 字段）")
    for row in mp["categories"].values():
        print(f"     {row['label']}")
        print(f"         {row['use']}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="字体库：清单 / 取字体 / 映射 / 内嵌")
    ap.add_argument("--list", action="store_true", help="列出清单")
    ap.add_argument("--installed", action="store_true", help="列出本地已就位哪些")
    ap.add_argument("--fetch", action="store_true", help="取能直接下载的那批")
    ap.add_argument("--only", default=None, help="只取这些（逗号分隔的名字）")
    ap.add_argument("--tier", default=None,
                    help="只取这个授权级（默认 A = 严格免费可嵌；要 B/C 用 --tier all）")
    ap.add_argument("--map", action="store_true", help="打印字体 ↔ 风格映射表")
    ap.add_argument("--md", action="store_true", help="--map 输出 markdown")
    ap.add_argument("--a-only", action="store_true",
                    help="--map 只打**纯 A** 那一套（没有 license 也能用、可嵌交付物）")
    ap.add_argument("--embed", default=None, metavar="HTML", help="把字体内联进这份 HTML")
    ap.add_argument("-o", "--out", default=None, help="--embed 的输出")
    ap.add_argument("--category", default=None, help="--list 只列这一类")
    ap.add_argument("--license", default=None, help="--list 只列这个授权级")
    ap.add_argument("--urls", action="store_true", help="--list 时带上来源页地址")
    ap.add_argument("--temp", action="store_true",
                    help="字体放临时目录（不在这台机器上留东西），而不是 ~/.config")
    ap.add_argument("--where", action="store_true", help="打印字体该放哪儿（含解析顺序）")
    args = ap.parse_args(argv[1:])

    if args.where:
        print(f"当前会用的目录：{cache_dir(args.temp)}")
        print(f"  解析顺序：$DECK_FONT_DIR"
              f"{' > 临时目录（--temp）' if args.temp else ''} "
              f"> ~/.config/{CACHE_DIRNAME}/fonts")
        print(f"  旧的 skill 目录（只读兜底）：{LEGACY_DIR}")
        files = local_files(args.temp)
        print(f"  这里找到 {len(files)} 个字体文件")
        for p in files[:8]:
            print(f"     {p}")
        return 0

    if args.embed:
        out = args.out or os.path.splitext(args.embed)[0] + ".portable.html"
        print("✓", embed(args.embed, out))
        return 0

    if args.fetch:
        only = [s.strip() for s in args.only.split(",")] if args.only else None
        # 默认只取严格 A —— "我只需要免费的字体，我没有什么 license"。
        # 要看 B/C 得显式 --tier all。
        ok, _msgs = fetch(only=only, tier=args.tier or DEFAULT_TIER, temp=args.temp)
        have = installed_names()
        print(f"\n本地已有 {len(have)} 款 / 清单 {len(catalog())} 款")
        if len(have) < len(catalog()):
            print("  其余的去来源页拿（--list --urls 看地址）；清单里多数是站上分发，"
                  "没有可验证的直链")
        return 0 if ok else 1

    if args.map:
        print_map(as_md=args.md, a_only=args.a_only)
        return 0

    fonts = catalog()
    srcs = deckio.read_json(CATALOG).get("sources", {})
    if args.category:
        fonts = [f for f in fonts if f["category"] == args.category]
    if args.license:
        fonts = [f for f in fonts if tier_matches(f["license"], args.license)]
    if args.installed:
        have = installed_names()
        fonts = [f for f in fonts if f["name"] in have]
        print(f"本地已就位 {len(fonts)} 款（判据：字体目录里真有对应文件，"
              f"见 --where）\n")
    for f in fonts:
        line = f"  {f['i']:3}  {f['name']:28} [{f['license']:3}] {f['for']}"
        if args.urls:
            s = srcs.get(f["source"], {})
            line += f"\n       {f['source']} {s.get('url', '?')}"
        print(line)
    if not args.installed:
        print(f"\n共 {len(fonts)} 款。取字体：--fetch --tier A；映射表：--map")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
