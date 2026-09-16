"""品牌资产层 —— 一个组织的视觉身份，跨 deck 复用。

## 为什么是**第三层**

三层各管一件事，混在一起就必然互相打架：

| 层 | 在哪里 | 管什么 | 谁改 |
| --- | --- | --- | --- |
| 内容 | `*.spec.json` | 说什么（标题 / 条目 / 数据） | 每次做 deck 都改 |
| 风格 | deck 的 `styles/<name>/` | 怎么表达（构图 / 字号跨度 / 墨色 / 运动） | 换风格才改 |
| **品牌** | `brands/<name>/` | **是谁**（logo / 色号 / 字体） | 换个客户才改 |

品牌资产的特点就是**跨 deck 不变**：同一个公司的 logo 和主色，做十份 deck 都一样。
把它塞进 spec 就等于每次重填一遍，而且必然填歪（颜色手抄会抄错，字体名会抄成
系统里没有的那个）。塞进 style 则更糟 —— 那等于"这家公司"变成了"一种视觉语言"，
换个风格就把品牌丢了。

## 优先级（写死，不靠约定）

**品牌赢在"是谁"，风格赢在"怎么表达"：**

- 色板：品牌提供的色板**并入**风格的色板表；同名的以品牌为准（品牌色号是事实，
  不是审美偏好）。风格原有的色板一个不删 —— 没品牌色的 deck 照旧能跑。
- 字体：品牌提供则**整体替换**（display 与 body 一起换）。只换一半会得到
  "标题是品牌字体、正文不是"这种半吊子，比不换更难看。
- logo / 署名：品牌给了才出现，没给就没有这个元素（不会渲染空占位）。
- **版面位置不归品牌管，归风格管**：logo 放哪个角、多大，是构图问题 ——
  风格知道画面哪里是空的。品牌只决定"出现在哪些页"（`logoOn`）。

## 文件形状

```jsonc
// brands/acme/brand.json
{
  "version": 1,
  "label": "某某科技",
  "logo": "logo.png",              // 相对 brand 目录；建议 PNG（见下）
  "logoOn": "cover+end",           // cover | cover+end | all | none（缺省 cover+end）
  "footer": "© 2026 某某科技",      // 可选：页脚的署名
  "colorSets": {                   // 可选：并入风格的色板表，同名覆盖
    "brand": { "primary": "#0B5FFF", "secondary": "#101418",
               "background": "#FFFFFF", "text": "#101418" }
  },
  "fonts": { "display": "...", "body": "..." }   // 可选：整体替换
}
```

### logo 的格式

**HTML / PDF 什么格式都行**（SVG 最好，矢量，放大不糊）—— 因为 logo 是以 base64
内嵌进产物的，产物自己是完整的，挪到哪都不会裂图（这是 `image` 字段的已知毛病，
logo 不再犯）。

**原生 PPTX 只吃位图**：python-pptx 不支持 SVG。给了 SVG 就用 Chrome 当场栅格化
（Chrome 本来就是这条流水线的依赖）。栅格化不了会**明说跳过**，不会静默少一个 logo。
"""
from __future__ import annotations

import base64
import importlib.util
import json
import mimetypes
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
BRANDS_DIR = os.path.join(SKILL_DIR, "brands")

BRAND_FIELDS = {"version", "label", "logo", "logoInverse", "logoOn", "footer",
                "colorSets", "fonts", "note"}
LOGO_ON = ("cover", "cover+end", "all", "none")
RASTER_EXT = (".png", ".jpg", ".jpeg")

# 纸面暗于这个相对亮度就当“深底”，改走反白条 logo。
# 实测取值：本仓库的深底风格是 #000000（keynote-dark）与 #0A0A0A（billboard/ink），
# 亮度 0.000 / 0.003；浅底最低的是 #F4F4F4（0.905）。0.45 把它们干净分开。
DARK_PAPER_LUMINANCE = 0.45

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def _deckio():
    """同目录模块加载（仓库约定：importlib + sys.modules，不碰 sys.path）。"""
    if "deckio" in sys.modules:
        return sys.modules["deckio"]
    spec = importlib.util.spec_from_file_location("deckio", os.path.join(HERE, "deckio.py"))
    if spec is None or spec.loader is None:
        raise SystemExit("✗ 加载不了 deckio.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["deckio"] = module
    spec.loader.exec_module(module)
    return module


def _ink():
    if "ink" in sys.modules:
        return sys.modules["ink"]
    spec = importlib.util.spec_from_file_location("ink", os.path.join(HERE, "ink.py"))
    if spec is None or spec.loader is None:
        raise SystemExit("✗ 加载不了 ink.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["ink"] = module
    spec.loader.exec_module(module)
    return module


def is_dark_paper(hex_color: str) -> bool:
    """这张纸算不算“深底”。用 ink 的亮度函数 —— 只有一处定义，不重抄。"""
    try:
        return _ink().luminance(hex_color) < DARK_PAPER_LUMINANCE
    except SystemExit:
        return False


def available() -> list[str]:
    """有哪些品牌可用（列出候选，供报错时写清"可选项是什么"）。"""
    return _deckio().list_dirs(BRANDS_DIR)


def load(name: str) -> dict:
    """读一个品牌。读不到**直接失败**并列出可选项 —— 静默降级成"没品牌"会让
    用户以为品牌生效了（色号没变、logo 没出），然后去别处找原因。

    唯一的例外是 `name` 为空/缺省：那代表"这份 deck 不用品牌"，是合法状态。
    """
    if not name:
        return {}
    path = os.path.join(BRANDS_DIR, name, "brand.json")
    if not os.path.isfile(path):
        have = available()
        raise SystemExit(
            f"✗ 找不到品牌 {name!r}（找的是 {path}）\n"
            f"  现有品牌：{have or '（一个都没有）'}\n"
            f"  新建一个：brands/{name}/brand.json —— 字段见 references/brand-assets.md"
        )
    raw = _deckio().read_json(path)
    version = raw.get("version")
    if version != 1:
        raise SystemExit(f"✗ brands/{name}/brand.json 的 version 应为 1，实际是 {version!r}")
    unknown = sorted(set(raw) - BRAND_FIELDS)
    if unknown:
        raise SystemExit(
            f"✗ brands/{name}/brand.json 里有未知字段 {unknown}\n"
            f"  允许的：{sorted(BRAND_FIELDS)}（字段集封闭 —— 见 references/brand-assets.md）"
        )
    mode = raw.get("logoOn", "cover+end")
    if mode not in LOGO_ON:
        raise SystemExit(
            f"✗ brands/{name}/brand.json 的 logoOn={mode!r} 不认识\n"
            f"  只能是：{list(LOGO_ON)}")
    if raw.get("logo"):
        logo_path = os.path.join(BRANDS_DIR, name, str(raw["logo"]))
        if not os.path.isfile(logo_path):
            raise SystemExit(f"✗ brands/{name}/brand.json 指向的 logo 不存在：{logo_path}")
    if raw.get("logoInverse"):
        inv = os.path.join(BRANDS_DIR, name, str(raw["logoInverse"]))
        if not os.path.isfile(inv):
            raise SystemExit(f"✗ brands/{name}/brand.json 指向的 logoInverse 不存在：{inv}")
    raw["_name"] = name
    raw["_dir"] = os.path.join(BRANDS_DIR, name)
    return raw


def logo_file(brand: dict, paper: str) -> str:
    """选哪个 logo 文件：**深底上优先用反白版**。

    这不是锦上添花 —— 抽帧看图当场撞到的：keynote-dark（纯黑底）上，
    专为白底设计的 logo 里的深色块**直接消失**，只剩一个白三角和几个字母。
    真实品牌手册里的 logo 从来都是成对的（正版 / 反白版），所以这就是品牌层
    该有的东西，而不是“以后再说”的优化。

    只给了一个 logo 也能跑：那就四套风格都用它，由 `check.py` 报一条提示
    （“深底上可能看不见，建议补 logoInverse”）——**不静默**。
    """
    if not brand.get("logo"):
        return ""
    if brand.get("logoInverse") and is_dark_paper(paper):
        return str(brand["logoInverse"])
    return str(brand["logo"])


def shows_logo(brand: dict, slide_kind: str, slide_no: int, end_slide: int) -> bool:
    """这一页要不要上 logo。brand 决定"出现在哪些页"，风格决定"放哪里"。

    `end_slide` 是**尾页的页号**，由 render.py 算好传进来 —— 不是"数组最后一页"。
    两者在常见的 deck 里恰好重合，但不等价（附件页跟在谢谢页后面很常见）。
    第一版就是写的 `slide_no == total`，测试里那个"尾页不是 end 的 deck"
    当场就把它拆了：logo 跑到了附件页上，而谢谢页没有。
    """
    mode = brand.get("logoOn", "cover+end")
    if not brand.get("logo") or mode == "none":
        return False
    if mode == "all":
        return True
    if mode == "cover+end":
        return slide_kind == "title" or slide_no == end_slide
    return slide_kind == "title"          # mode == "cover"


def logo_path(brand: dict, file: str) -> str:
    return os.path.join(brand["_dir"], file) if file else ""


def logo_bytes(brand: dict, file: str) -> bytes:
    """logo 的原始字节（内嵌与导出都用这一份事实）。"""
    if not file:
        return b""
    return _deckio().read_bytes(logo_path(brand, file))


def logo_mime(file: str) -> str:
    ext = os.path.splitext(file)[1].lower()
    if ext == ".svg":
        return "image/svg+xml"
    return mimetypes.guess_type("x" + ext)[0] or "image/png"


def logo_data_uri(brand: dict, file: str) -> str:
    """内嵌用的 data URI。

    为什么内嵌而不是给个相对路径：`image` 字段那条老路是"产物挪个目录就全员裂图"
    （README 已列为已知限制）。logo 是**每页都出现**的品牌资产，裂了整份 deck 就废了 ——
    它必须跟着产物走。选 base64 还因为它**只含 ASCII** —— 内嵌载荷不与正文的
    中文编码纠缠，转存/重编码都不会被改坏。
    """
    payload = logo_bytes(brand, file)
    if not payload:
        return ""
    return f"data:{logo_mime(file)};base64," + base64.b64encode(payload).decode("ascii")


def logo_ref(brand: dict, file: str) -> str:
    """给语义清单用的**技能相对**路径（导出脚本据此找到原图）。

    不用绝对路径：产物是给别人传阅的，里面不该有机主的目录结构
    （实测过 `data-m="data-m="s1.title""` 那类污染 —— 这类东西一进产物就洗不掉）。
    """
    if not file:
        return ""
    return f"brands/{brand['_name']}/{file}"


def resolve_logo_ref(ref: str) -> str:
    """把 `logo_ref()` 的路径解析成本机绝对路径。"""
    return os.path.join(SKILL_DIR, ref)


def rasterize(logo_path: str, width_px: float, height_px: float) -> str:
    """SVG → PNG（按**面板上真实的盒子尺寸**，2 倍分辨率）。

    原生 PPTX 只吃位图，而 logo 恰恰最常用 SVG。两条路：
      1. 让用户自己转一张 PNG（把活推给人）
      2. 当场栅格化（Chrome 就在机器上）
    选 2。栅格化不了就**如实报**，让调用方决定是跳过还是失败 —— 不静默少一个 logo。

    ⚠️ 第一版直接用 `--window-size=W,W` 截 SVG 文件，结果是**正方形**：
      一是丢了宽高比（贴进 PPTX 变成一个方框，图被拉／留大片透明），
      二是 SVG 作为文档打开时按**自身尺寸**渲染（本仓库那个是 420×100），
      在 235 宽的窗口里右边直接**被截掉**。两个毛病都不会报错，只会默默地丑。
    所以改成先包一层 HTML、把图显成**目标的宽高**，再按 2 倍截。
    """
    if not os.path.isfile(CHROME):
        raise SystemExit(
            f"✗ logo 是矢量格式，原生 PPTX 需要位图，但找不到 Chrome 去栅格化：{CHROME}\n"
            f"  两条路：装 Chrome，或把 logo 换成 PNG（HTML / PDF 用 SVG 没问题）")
    # 走 deckio.as_number（数字解析的收口点）而不是裸 int()/round()：
    # 量不到尺寸时要**报出来**，不能悄悄拿一个默认值去栅格化（那会出来一张糊的或空的图）。
    w = _deckio().as_number(width_px, "logo 的渲染宽度")
    h = _deckio().as_number(height_px, "logo 的渲染高度")
    if w < 16 or h < 8:
        raise SystemExit(
            f"✗ logo 的渲染尺寸不合常理（{width_px!r}×{height_px!r}）—— "
            f"测量层没给出可用盒子，不给一个猜的尺寸")
    out_dir = tempfile.mkdtemp(prefix="deck-logo-")
    page = os.path.join(out_dir, "page.html")
    out_path = os.path.join(out_dir, "logo.png")
    uri = pathlib.Path(logo_path).resolve().as_uri()
    # 透明背景：logo 常常超出图形本身（外留白），透明才能让它不抳一个白底。
    _deckio().write_text(
        page,
        "<!doctype html><meta charset='utf-8'>"
        "<style>html,body{margin:0;background:transparent}"
        f"img{{display:block;width:{w:.0f}px;height:{h:.0f}px;object-fit:contain}}</style>"
        f"<img src='{uri}'>")
    subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
         "--force-device-scale-factor=2", "--default-background-color=00000000",
         f"--window-size={w:.0f},{h:.0f}", f"--screenshot={out_path}",
         pathlib.Path(page).as_uri()],
        capture_output=True, check=False, timeout=60)
    if not os.path.isfile(out_path) or os.path.getsize(out_path) < 32:
        raise SystemExit(f"✗ Chrome 没能把 {logo_path} 栅格化成 PNG")
    return out_path



def need_raster(file: str) -> bool:
    ext = os.path.splitext(file)[1].lower()
    return bool(file) and ext not in RASTER_EXT


def merge_fonts(style_fonts: dict, brand: dict) -> dict:
    """品牌字体**整体替换**（只换一半会得到半吊子，比不换更难看）。"""
    bf = brand.get("fonts")
    if not isinstance(bf, dict) or not bf.get("display") or not bf.get("body"):
        return style_fonts
    merged = dict(style_fonts)
    merged["display"] = str(bf["display"])
    merged["body"] = str(bf["body"])
    merged["note"] = f"字体来自品牌 {brand.get('label', brand.get('_name'))}（覆盖风格的字体）"
    return merged


def merge_color_sets(style_sets: dict, brand: dict) -> dict:
    """品牌色板**并入**风格的色板表；同名以品牌为准。风格原有色板一个不删 ——
    没定义品牌色的 deck 照旧能跑。"""
    bcs = brand.get("colorSets")
    if not isinstance(bcs, dict) or not bcs:
        return style_sets
    merged = {name: dict(cs) for name, cs in style_sets.items()}
    for name, cs in bcs.items():
        if not isinstance(cs, dict):
            raise SystemExit(f"✗ 品牌 {brand.get('_name')} 的 colorSets.{name} 应是对象")
        merged[name] = dict(cs)
    return merged


def describe(brand: dict) -> str:
    """一行摘要，给渲染日志用（"品牌生效了没有"要能一眼看到）。"""
    if not brand:
        return "（无品牌）"
    bits = [f"品牌 {brand.get('label', brand['_name'])}"]
    if brand.get("logo"):
        pair = "+反白版" if brand.get("logoInverse") else ""
        bits.append(f"logo={brand['logo']}{pair}（{brand.get('logoOn', 'cover+end')}）")
    if brand.get("colorSets"):
        bits.append(f"色板 +{sorted(brand['colorSets'])}")
    if brand.get("fonts"):
        bits.append("字体覆盖")
    if brand.get("footer"):
        bits.append("署名")
    return "·".join(bits)


def main(argv: list[str]) -> int:
    """`python3 scripts/brand.py` 列出现有品牌；`brand.py <name>` 显示它的摘要。"""
    if len(argv) > 1:
        b = load(argv[1])
        print(describe(b))
        print(f"  目录：{b.get('_dir')}")
        return 0
    names = available()
    if not names:
        print(f"还没有品牌。新建 brands/<name>/brand.json —— 见 references/brand-assets.md")
        print(f"（目录：{BRANDS_DIR}）")
        return 0
    for n in names:
        try:
            print(f"  {n:16s} {describe(load(n))}")
        except SystemExit as exc:
            print(f"  {n:16s} ✗ {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
