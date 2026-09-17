#!/usr/bin/env python3
"""HTML / 每页 PNG → PPTX。两条路都在这一个脚本里：

| 模式 | 怎么跑 | 每页内容 | 改字 | 观感 |
| --- | --- | --- | --- | --- |
| 贴图 | `--png-dir pages/` | 一张 2x 截图 | 改不了（回改 spec 重出） | 100%（错位 / 颗粒 / 网点全在） |
| 原生 | `out.html`（或 `--resolved`） | 原生文本框 / 形状 / 图表 | **能改** | 打折（见下） |

两条路**不能兼得** —— 这是「观感 100%」的本质代价，不是偷懒。要改字就接受外观打折，
要外观就接受改不了字。要"外观对且不能改"还有 PDF（矢量，0.65MB）。

## 为什么这个 skill 能出原生 shapes（而通用 HTML→PPTX 工具很勉强）

**因为渲染器是自己的。** `render.py` 在产物里留下了两样东西：

- **语义清单**（`<script id="__deck_manifest">`）：每个元素是什么、写了什么字、
  设计意图用多大字号
- **真实几何**：由 `measure.py` 从真浏览器量出来的盒子

通用工具只能从 DOM 反推这两样（huashu-design 为此写了 46KB 的 `html2pptx.js`，
还得给用户加 4 条 HTML 约束）。我们不用猜。

## 有意打折的地方（写清楚，别当成 bug）

- **不做双墨错位**：标题只有一层，用叠印色。错位是屏幕/印刷效果，
  在 PPT 里要么做两个文本框（编辑体验毁掉），要么不做。选了后者。
- **不做颗粒**：`feTurbulence` 在 PPT 里没有对应物。
- **网点变 PowerPoint 内置图案填充**（`pct25`）：观感接近，可编辑。
- **几何是"种子"不是"复制"**：位置与字号来自真实测量，但 PowerPoint 的文本排版
  引擎与浏览器不同，边界会有几个像素的出入。
- **图表是 PowerPoint 原生图表**：数据可改（这是重点），但长相是 PowerPoint 的。

跑法（两条路，同一构建核）：
    python3 pptx_native.py out.html -o deck-editable.pptx            # HTML 模式（当场实测）
    python3 pptx_native.py --resolved resolved.deck.json -o deck.pptx  # 契约模式（渲染时几何）
    python3 pptx_native.py --png-dir pages/ -o deck.pptx               # 贴图模式

契约模式吃 `render.py --resolved` 出的**完整契约**（语义 manifest + 实测几何 +
颜色变量 + 资产基准目录）：几何只在渲染时量一次，导出不再自己跑测量 ——
HTML 与 PPTX 同源，两次测量之间的字体/机器差异不再进入产物。
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys

from pptx import Presentation
from pptx.chart.data import CategoryChartData, XyChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.enum.dml import MSO_PATTERN
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_sibling(name: str):
    """动态加载同目录脚本（`scripts/` 不是包，同级 import 在静态层面无法解析）。

    写法和本目录其他脚本一致。
    """
    path = os.path.join(HERE, f"{name}.py")
    mod_spec = importlib.util.spec_from_file_location(f"_deck_{name}", path)
    if mod_spec is None or mod_spec.loader is None:
        raise RuntimeError(f"加载不了同目录模块：{path}")
    module = importlib.util.module_from_spec(mod_spec)
    sys.modules[mod_spec.name] = module
    mod_spec.loader.exec_module(module)
    return module


deckio = _load_sibling("deckio")
measure_mod = _load_sibling("measure")
deck_mod = _load_sibling("deck")       # 品牌 logo：路径解析 + 矢量栅格化

# 1 CSS px = 0.75pt = 9525 EMU。版面 1600×900px → 1200×675pt。
EMU_PER_PX = 9525
PX_TO_PT = 0.75

# 能导出成原生形状的装饰类型。**加新装饰时这里与 add_decor 必须同时长** ——
# 只长一边的话，导出会静默少一个元素（文件照生成、页数照样对，就是缺东西）。
# test_pptx_native 里有一条用例拿所有风格声明的 kind 来对这里。
DECOR_SHAPES = {"accent-block", "halftone-circle"}

# 角色 → 用哪套字。字体族本身从产物里的 --display / --body 取。
SERIF_ROLES = {"title"}
MONO_ROLES = {"subtitle", "bullet", "foot", "caption"}
# 量不到字重时的兜底（老产物没有 fontWeight 字段）。
# **正常路径不看它** —— 字重由实测决定，见 add_text：有的风格标题是 400 字重，
# 写死 bold 就直接和设计相反了。
BOLD_ROLES_FALLBACK = {"title"}
BOLD_WEIGHT = 600

# 在浏览器里就是**单行不折**的（`.riso b{white-space:nowrap}`；`.foot` 是一行页码）。
# PPT 里必须同样 nowrap：对方机器没有声明的字时会被替换，**替换字体一旦变宽就折行**，
# 把下面的元素整片压掉（实渲出来就是这个样子 ✗）。浏览器里溢出而不是折行，这里也溢出。
NOWRAP_ROLES = {"title", "foot"}

# 文字元素之外的角色（有几何但不出文本框）
NON_TEXT_ROLES = {"image", "chart", "logo"}
# 位图角色：有真图就摆图（logo 与内容图的区别在 **base** —— 见 build() 里的 src_base）
PICTURE_ROLES = {"image", "logo"}


def parse_root_vars(html: str) -> dict[str, str]:
    """从产物里读 `:root{--paper:…;--accent:…}`。

    为什么不读 `style.json`：产物**已经**把 token 解析成 CSS 变量写进页面了。
    以产物为唯一事实来源，就不会出现"改了 token 但产物是旧的"这种错配 ——
    也自然支持多风格（不管哪个 skin，契约变量名是同一组）。
    """
    m = re.search(r":root\s*\{(.*?)\}", html, re.S)
    if m is None:
        raise SystemExit("✗ 产物里找不到 :root 变量块 —— 这不是 render.py 出的产物？")
    out = {}
    for decl in m.group(1).split(";"):
        if ":" in decl:
            key, _, val = decl.partition(":")
            out[key.strip()] = val.strip()
    return out


def css_color(value: str) -> RGBColor:
    """`#RRGGBB` / `rgb(r, g, b)` → RGBColor。

    数值解析走 `deckio.as_number`（本 skill 的数值收口）—— 转不了就报清楚的话，
    不甩 traceback。十六进制那支走 `bytes.fromhex`，一次拿到三个字节。
    """
    value = value.strip()
    m = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", value)
    if m:
        r, g, b = (round(deckio.as_number(x, f"颜色分量 {value!r}")) for x in m.groups())
        return RGBColor(r, g, b)
    m = re.match(r"#([0-9a-fA-F]{6})", value)
    if m:
        r, g, b = bytes.fromhex(m.group(1))
        return RGBColor(r, g, b)
    raise SystemExit(f"✗ 认不出的颜色值：{value!r}")


def first_family(stack: str) -> str:
    """从 CSS 字体栈里取第一个具体族名。

    PPT 只吃单个族名。栈里第一项是设计意图首选 —— 本机没有它会回退到后面的族，
    但那是**对方打开时**的事，写进去的应该是意图。
    """
    first = stack.split(",")[0].strip().strip("\"'")
    return first or "sans-serif"


def slide_boxes(measured: dict) -> list[dict]:
    return measured.get("slides") or []


def rel_box(el: dict, slides: list[dict]) -> tuple[float, float, float, float]:
    """把元素盒子换算成**相对它所在那一页**的坐标（像素）。

    产物是竖向堆叠的多页，第 N 页的元素 y 本来就在 (N-1)×900 以下 ——
    不减页原点，摆到 PPT 里会整片飞出画布。
    """
    idx = el.get("slide")
    sx, sy = 0.0, 0.0
    if isinstance(idx, int) and 1 <= idx <= len(slides):
        sx, sy = slides[idx - 1]["x"], slides[idx - 1]["y"]
    return el["x"] - sx, el["y"] - sy, el["w"], el["h"]


# 我们出货的风格里出现过的 CJK 族。加新风格时如果用了新的中文字体，**这里要补**
# （不补的话 ea 不会被写进去，中文就退回宿主自选 —— 不会报错，只会悄悄换字体）。
CJK_FAMILIES = ("Hiragino Sans GB", "Songti SC", "Heiti SC", "PingFang SC",
                "Microsoft YaHei", "Noto Sans SC", "Source Han Sans SC",
                "Source Han Serif SC")


def east_asian_family(stack: str) -> str | None:
    """从 CSS 字体栈里挑第一个**能画汉字**的族（给 `<a:ea>` 用）。挑不到返回 None。"""
    for raw in stack.split(","):
        fam = raw.strip().strip('"').strip("'")
        if fam in CJK_FAMILIES:
            return fam
    return None


def set_east_asian_font(run, typeface: str) -> None:
    """把**东亚字体**写进 `<a:ea>`（`font.name` 只写 `<a:latin>`）。

    为什么这条对中文 deck 是要害：一份中文 deck 的字**绝大多数是 CJK**，
    而宿主软件（PowerPoint / WPS / LibreOffice）对 CJK 用的是 `<a:ea>` 指定的族；
    没写就由它自己挑 —— 实测：LibreOffice 渲出来是一个加粗的黑体，
    而有的风格指定的是宋体，等于导出把整个风格换掉了。

    OOXML 的 schema 规定 `<a:latin>` → `<a:ea>` → `<a:cs>` 的顺序，
    所以插在 latin 之后，不是直接 append（顺序错了 PowerPoint 会拒绝整个文件）。
    """
    rPr = run._r.get_or_add_rPr()          # noqa: SLF001 —— python-pptx 没有公开的 ea 接口
    ea = rPr.makeelement(qn("a:ea"), {"typeface": typeface})
    latin = rPr.find(qn("a:latin"))
    if latin is not None:
        latin.addnext(ea)
    else:
        rPr.append(ea)


def add_text(slide, el: dict, box: tuple[float, float, float, float],
             vars_: dict[str, str]) -> None:
    """一个元素 → 一个文本框。**一个元素一个框**是可编辑性的底线。"""
    x, y, w, h = box
    tx = slide.shapes.add_textbox(Emu(round(x * EMU_PER_PX)), Emu(round(y * EMU_PER_PX)),
                                  Emu(round(w * EMU_PER_PX)), Emu(round(h * EMU_PER_PX)))
    tf = tx.text_frame
    role = el.get("role", "")
    tf.word_wrap = role not in NOWRAP_ROLES
    tf.auto_size = MSO_AUTO_SIZE.NONE        # 绝不自动缩放字号：那会让 PPT 与设计脱钩
    tf.vertical_anchor = MSO_ANCHOR.TOP
    # 内边距清零：默认 0.1in 会把文字挤到框内偏移，位置就不来自测量了
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    run = p.add_run()
    run.text = el.get("text", "")

    fam = first_family(vars_.get("--display", "") if role in SERIF_ROLES
                       else vars_.get("--body", ""))
    run.font.name = fam
    # 中文靠 `<a:ea>`；**但不能拿栈首那个族给它** —— 栈首往往是拉丁族
    # （Georgia / Helvetica Neue / Menlo），对汉字没有字形，宿主照样自己去挑，
    # 等于没写（实测：ea 写成 Georgia 之后，LibreOffice 渲出来的中文还是个加粗黑体）。
    # 所以从栈里挑一个**声明过的 CJK 族**；挑不到就不写 ea（让宿主决定，
    # 比写一个错的强 —— 错的会让人以为我们指定了）。
    ea_fam = east_asian_family(vars_.get("--display", "") if role in SERIF_ROLES
                               else vars_.get("--body", ""))
    if ea_fam:
        set_east_asian_font(run, ea_fam)
    run.font.size = Pt(round((el.get("fontSize") or 24) * PX_TO_PT, 1))
    # 字重**跟着实测走**，不按角色写死：有的风格标题是 400 字重，
    # 统一 bold 就等于把这两套风格的标题设计抹掉了（XML 里读出来是 b="1" ✗）。
    weight = el.get("fontWeight")
    run.font.bold = ((weight >= BOLD_WEIGHT) if isinstance(weight, (int, float))
                     else role in BOLD_ROLES_FALLBACK)
    # 标题取叠印色（单层替代双墨错位）；其余用**实测到的**计算色 —— 又是"量不是猜"
    color = vars_["--text"] if role in SERIF_ROLES else (el.get("measuredColor")
                                                         or vars_["--text"])
    run.font.color.rgb = css_color(color)


def add_decor(slide, d: dict, slides: list[dict], vars_: dict[str, str]) -> None:
    """装饰墨块 → 原生形状。**按 kind 分派**（不是写死一种）：

      accent-block     实心矩形色场
      halftone-circle  带 `pct25` 图案填充的椭圆（网点圆的近似）

    加新装饰类型时这里必须同步加一分支，否则导出会**静默少一个元素**。
    `test_pptx_native` 里有一条「每种风格的 decor.kind 都有映射」看着它。
    """
    x, y, w, h = rel_box(d, slides)
    kind = d.get("kind") or "halftone-circle"
    geom = (Emu(round(x * EMU_PER_PX)), Emu(round(y * EMU_PER_PX)),
            Emu(round(w * EMU_PER_PX)), Emu(round(h * EMU_PER_PX)))
    if kind not in DECOR_SHAPES:
        raise SystemExit(f"✗ pptx 导出认不出的装饰 kind={kind!r}"
                         f"（可选：{sorted(DECOR_SHAPES)} —— add_decor 缺分支？）")
    if kind == "accent-block":
        shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, *geom)
        shape.line.fill.background()
        shape.shadow.inherit = False
        shape.fill.solid()
        shape.fill.fore_color.rgb = css_color(vars_["--accent"])
        return
    if kind != "halftone-circle":
        raise SystemExit(f"✗ pptx 导出认不出的装饰 kind={kind!r}（add_decor 缺分支）")
    shape = slide.shapes.add_shape(MSO_SHAPE.OVAL, *geom)
    shape.line.fill.background()
    shape.shadow.inherit = False             # add_shape 会带一套主题效果（阴影），清掉
    shape.fill.patterned()
    # ⚠️ 属性名是 `pattern`，不是 `pattern_type` —— 写错了不会报错，会被当成普通属性
    # 默默吞掉，XML 里的 `<a:pattFill>` 就光秃秃没有 prst（渲染出来是个空圈）。
    shape.fill.pattern = MSO_PATTERN.PERCENT_25
    shape.fill.fore_color.rgb = css_color(vars_["--accent"])
    shape.fill.back_color.rgb = css_color(vars_["--paper"])


def _mix(a: str, b: str, t: float) -> str:
    """两个 CSS 颜色的线性混合（t=0 是 a，t=1 是 b）。系列深浅阶用。"""
    def chan(c: str) -> tuple[int, int, int]:
        c = c.lstrip("#")
        return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))
    ea, eb = chan(a), chan(b)
    return "#" + "".join(f"{round(x + (y - x) * t):02X}"
                   for x, y in zip(ea, eb, strict=True))


def _style_labels(labels, vars_: dict[str, str]) -> None:
    """数值标签的字体与单位 —— 字号 20px 换算、颜色跟 --text、单位跟数值走。"""
    labels.font.size = Pt(round(20 * PX_TO_PT, 1))
    labels.font.color.rgb = css_color(vars_["--text"])


# DSL 的 chart 类型 → PowerPoint 原生图表类型。combo 在原生层退化成柱
# （python-pptx 一个图表对象只能一个 plot；组合图是第二阶段的事，先如实降级）。
_XL_KIND = {
    "bar": XL_CHART_TYPE.COLUMN_CLUSTERED,
    "bar-horizontal": XL_CHART_TYPE.BAR_CLUSTERED,
    "line": XL_CHART_TYPE.LINE_MARKERS,
    "area": XL_CHART_TYPE.AREA,
    "bar-stacked": XL_CHART_TYPE.COLUMN_STACKED,
    "donut": XL_CHART_TYPE.DOUGHNUT,
    "scatter": XL_CHART_TYPE.XY_SCATTER,
    "combo": XL_CHART_TYPE.COLUMN_CLUSTERED,
}


def add_chart(slide, el: dict, box: tuple[float, float, float, float],
              vars_: dict[str, str]) -> None:
    """图表 → **PowerPoint 原生图表**：数据可改才是重点。"""
    data = el.get("data") or []
    series = el.get("series") or []
    if not data and not series:
        return
    kind = el.get("chart") or ""
    x, y, w, h = box
    if kind == "scatter":
        # 散点要两个连续量：XyChartData，不是 CategoryChartData（类别轴画不了它）
        chart_data = XyChartData()
        for d in data:
            chart_data.add_series(str(d.get("label", ""))).add_data_point(
                d.get("x", 0), d.get("value", d.get("y", 0)))
    else:
        chart_data = CategoryChartData()
        if series:
            chart_data.categories = [str(d.get("label", ""))
                                     for d in series[0].get("data", [])]
            for s in series:
                chart_data.add_series(str(s.get("name", "")) or "值",
                                      [d.get("value", 0) for d in s.get("data", [])])
        else:
            chart_data.categories = [str(d.get("label", "")) for d in data]
            chart_data.add_series(el.get("unit", "") or "值",
                                  [d.get("value", 0) for d in data])
    frame = slide.shapes.add_chart(
        _XL_KIND.get(el.get("chart") or "", XL_CHART_TYPE.COLUMN_CLUSTERED),
        Emu(round(x * EMU_PER_PX)), Emu(round(y * EMU_PER_PX)),
        Emu(round(w * EMU_PER_PX)), Emu(round(h * EMU_PER_PX)), chart_data)
    chart = frame.chart
    # 图例：**只在多系列时画**（不画分不开系列；单系列坚决不画 —— 那是噪音）。
    # 这与 SVG 层"名字标在线尾"不同：原生层没有线尾可标。
    chart.has_legend = len(series) > 1
    if chart.has_legend:
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
    chart.has_title = False
    # 图标外观要**跟着我们的设计**，不是跟着宿主软件的默认模板。
    # 实测：不设这两项时 LibreOffice/PowerPoint 会画上网格线与左侧坐标轴数字，
    # 而柱子上**没有数值** —— 和我们设计的柱状图正好相反（我们的设计里数值在柱顶、
    # 只有一条基线）。
    # 环图没有 value_axis（访问就抛）；散点的两轴我们同样不画数字
    if kind not in ("donut", "scatter"):
        chart.value_axis.has_major_gridlines = False
        chart.value_axis.visible = False          # 坐标轴数字是我们不画的
    plot = chart.plots[0]
    if kind != "scatter":                        # 散点标数值会糊成一片
        plot.gap_width = 60
        plot.has_data_labels = True
        labels = plot.data_labels
        labels.show_value = True
        labels.show_category_name = False
        labels.show_series_name = False
        # OUTSIDE_END 对环图非法（python-pptx 直接抛）—— 环图用 CENTER
        labels.position = (XL_LABEL_POSITION.CENTER if kind == "donut"
                           else XL_LABEL_POSITION.OUTSIDE_END)
        _style_labels(labels, vars_)
        unit = str(el.get("unit", "") or "")
        if unit:
            labels.number_format = f'0"{unit}"'
            labels.number_format_is_linked = False
    # 单位跟着数值走的理由见上面分支里的注释（number_format_is_linked=False
    # 是关键：不设的话 PowerPoint 打开时会重新套默认格式，单位就没了）。
    #
    # 系列上色：**多系列不许同色**（分不开），也不许彩虹 —— 用 accent 向纸色
    # 分档褪色，与 SVG 层 series_colors 同一条规则。这里曾用 `for series in …`
    # 直接把外层的 `series`（数据系列表）遮蔽掉，多系列全被涂成同一种颜色。
    n_series = max(1, len(series))
    for si, s in enumerate(plot.series):
        s.format.fill.solid()
        s.format.fill.fore_color.rgb = css_color(
            _mix(vars_["--accent"], vars_["--paper"], 0.62 * si / max(1, n_series - 1))
            if n_series > 1 else vars_["--accent"])


def build(html_path: str, out_path: str) -> dict:
    """产物 HTML → 可编辑 PPTX（几何=当场实测）。"""
    html = deckio.read_text(html_path)
    return _build(parse_root_vars(html), measure_mod.measure(html_path),
                  measure_mod.read_manifest(html),
                  os.path.dirname(os.path.abspath(html_path)), out_path)


def build_resolved(resolved_path: str, out_path: str) -> dict:
    """resolved.deck.json → 可编辑 PPTX（几何=渲染时定好的那份，不再实测）。

    与 HTML 模式**同一个构建核**：HTML/PPTX 同源 —— 几何只在渲染时量一次，
    导出不再自己跑测量（两次测量之间换字体/换机器就是漂移的来源）。
    """
    r = deckio.read_json(resolved_path)
    missing = [k for k in ("vars", "geometry", "manifest", "baseDir") if k not in r]
    if missing:
        raise SystemExit(f"✗ {resolved_path} 不是完整契约（缺 {missing}）—— "
                          f"用 `render.py … --resolved` 重新生成")
    return _build(r["vars"],
                  {"slides": r["geometry"].get("slides") or [],
                   "elements": r["geometry"].get("elements") or [],
                   "decor": r["geometry"].get("decor") or []},
                  r["manifest"], r["baseDir"], out_path)


def _build(vars_: dict, measured: dict, manifest: list, base_dir: str,
           out_path: str) -> dict:
    """四源（变量 / 实测几何 / 语义清单 / 资产基准目录）→ PPTX。"""
    slides_geo = slide_boxes(measured)
    if not slides_geo:
        raise SystemExit("✗ 测量结果里没有页盒子 —— 产物里没有 section.slide？")

    boxes = {e["id"]: e for e in measured.get("elements", [])}
    # 导出要用的**实测**字段显式并进清单条目（比从 token 猜准 —— 又是"量不是猜"）。
    #
    # 显式列出而不是整包 update：整包会把 x/y/w/h 也塞进清单条目，之后再用
    # `rel_box()` 算相对坐标时，读的人分不清手上那个是文档坐标还是页内坐标。
    # 但**漏一个字段就是静默走兜底值** —— 实测就漏过 `fontWeight`：
    # 于是那些 400 字重的标题在 PPTX 里被强制加粗，
    # 而文件照生成、页数照样对，只有把 PPTX 打开看才发现。
    MERGE_MEASURED = {"color": "measuredColor", "fontWeight": "fontWeight"}
    for entry in manifest:
        m = boxes.get(entry["id"])
        if not m:
            continue
        for src_key, dst_key in MERGE_MEASURED.items():
            if m.get(src_key) is not None:
                entry[dst_key] = m[src_key]

    prs = Presentation()
    prs.slide_width = Emu(1600 * EMU_PER_PX)
    prs.slide_height = Emu(900 * EMU_PER_PX)
    blank = prs.slide_layouts[6]

    counts: dict[str, int] = {"text": 0, "decor": 0, "chart": 0, "image": 0,
                              "logo": 0, "skipped": 0}
    # 跳过的原因单独一个表：counts 是**计数**，混进字符串会让它不能再求和。
    notes: list[str] = []
    by_slide: dict[int, list[dict]] = {}
    for entry in manifest:
        by_slide.setdefault(entry["slide"], []).append(entry)
    decor_by_slide: dict[int, list[dict]] = {}
    for d in measured.get("decor", []):
        decor_by_slide.setdefault(d.get("slide", 0), []).append(d)

    total = max(len(slides_geo), max(by_slide, default=0))
    for n in range(1, total + 1):
        slide = prs.slides.add_slide(blank)
        bg = slide.background.fill
        bg.solid()
        bg.fore_color.rgb = css_color(vars_["--paper"])
        for d in decor_by_slide.get(n, []):
            add_decor(slide, d, slides_geo, vars_)
            counts["decor"] += 1
        for entry in by_slide.get(n, []):
            geo = boxes.get(entry["id"])
            if geo is None:
                counts["skipped"] += 1          # 量不到就不摆 —— 不猜一个位置
                continue
            box = rel_box(geo, slides_geo)
            role = entry.get("role", "")
            if role == "chart":
                add_chart(slide, entry, box, vars_)
                counts["chart"] += 1
            elif role in PICTURE_ROLES:
                src = entry.get("text", "")
                # base=skill：品牌 logo 走的是**技能相对**路径（brands/<name>/logo.svg）。
                # 内容图（image 字段）则是相对 HTML 的 —— 两种基准不能混。
                if entry.get("src_base") == "skill":
                    path = deck_mod.resolve_logo_ref(src)
                else:
                    path = os.path.join(base_dir, src)
                if not os.path.isfile(path):
                    counts["skipped"] += 1      # 图不在旁边：跳过并计数，不假装成功
                    continue
                # 原生 PPTX 只吃位图：矢量 logo 当场用 Chrome 栅格化。
                # 栅格化不了会**明说**（异常带原因），不静默少一个 logo。
                if role == "logo" and deck_mod.need_raster(src):
                    try:
                        # 传**实测的盒子尺寸**：栅格化要保住宽高比（传标量会得到
                        # 正方形，图要么被拉、要么一片透明）。
                        path = deck_mod.rasterize(path, box[2], box[3])
                    except SystemExit as exc:
                        counts["skipped"] += 1
                        notes.append(str(exc))
                        continue
                slide.shapes.add_picture(path, Emu(round(box[0] * EMU_PER_PX)),
                                         Emu(round(box[1] * EMU_PER_PX)),
                                         width=Emu(round(box[2] * EMU_PER_PX)))
                counts["logo" if role == "logo" else "image"] += 1
            elif role in NON_TEXT_ROLES:
                counts["skipped"] += 1
            elif entry.get("text"):
                add_text(slide, entry, box, vars_)
                counts["text"] += 1
    prs.save(out_path)
    counts["bytes"] = os.path.getsize(out_path)
    counts["slides"] = len(prs.slides._sldIdLst)      # noqa: SLF001 —— 没有公开的页数接口
    for n in notes:
        print("  ·", n)
    return counts


# ═══════════════════════════════════════════════════════════════════════════
# 贴图模式（`--png-dir`）：每页截图 → 16:9 pptx，一页一张满版图。
#
# 为什么还留它：浏览器渲染是**唯一**能 100% 还原风格效果（错位/颗粒/网点/G2 图表）
# 的路径。代价是每页一张图、**改不了字** —— 要改字回改 spec 再重出，或者用同文件
# 的原生 shapes 模式（`pptx_native.py out.html`）。两条不能兼得，按要"像"还是要"改"选。
# ═══════════════════════════════════════════════════════════════════════════
def build_from_pngs(png_paths: list[str], out: str, width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise SystemExit(f"✗ 版心必须是正数，收到 {width}x{height}")
    prs = Presentation()
    # 用整数运算算高度：`Emu(int(slide_width / ratio))` 先转 float 再取整，是多余的
    # 精度往返，且 height=0 时会 ZeroDivisionError（前面已拦住）。
    # `slide_width * height // width` 结果一样、全整数 —— 与 layout.py 同一手法：
    # 遇到不需要转换的地方就换个写法，而不是加一个永远不会触发的 try。
    slide_width = Inches(13.333)
    slide_height = Emu(slide_width * height // width)
    prs.slide_width = slide_width
    prs.slide_height = slide_height
    blank = prs.slide_layouts[6]                       # 空白版式，不放任何占位符
    for path in png_paths:
        slide = prs.slides.add_slide(blank)
        slide.shapes.add_picture(path, Emu(0), Emu(0), width=slide_width, height=slide_height)
    prs.save(out)



def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="PPTX：out.html → 可编辑（原生 shapes）；或 --png-dir 贴图模式")
    ap.add_argument("html", nargs="?", help="原生模式：产出的 out.html")
    ap.add_argument("--resolved", default=None, metavar="PATH",
                    help="resolved 模式：render --resolved 出的完整契约"
                         "（几何=渲染时定好的，不再实测；与 HTML 模式同一构建核）")
    ap.add_argument("--png-dir", default=None,
                    help="贴图模式：shots.py 出的 page-*.png 目录（一页一张满版图）")
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args(argv[1:])
    if args.png_dir:
        import glob as _glob
        pages = sorted(_glob.glob(os.path.join(args.png_dir, "page-*.png")))
        if not pages:
            raise SystemExit(f"✗ {args.png_dir} 里没有 page-*.png")
        build_from_pngs(pages, args.out, args.width, args.height)
        print(f"✓ 已写出 {args.out}（{len(pages)} 页贴图 / "
              f"{os.path.getsize(args.out)} 字节）")
        print("  · 每页是一张满版图：改不了字；要改字回改 spec 再重出")
        return 0
    if args.resolved:
        counts = build_resolved(args.resolved, args.out)
    elif args.html:
        counts = build(args.html, args.out)
    else:
        raise SystemExit("✗ 三选一：out.html（原生）/ --resolved 契约 / --png-dir 贴图")
    print(f"✓ 已写出 {args.out}")
    print(f"  {counts['slides']} 页 / {counts['bytes'] / 1048576:.2f}MB / "
          f"文本 {counts['text']} / 装饰 {counts['decor']} / 图表 {counts['chart']} / "
          f"图 {counts['image']} / logo {counts['logo']}")
    if counts["skipped"]:
        print(f"  · 跳过 {counts['skipped']} 个（量不到几何、或图不在产物旁边）—— 不猜位置")
    print("  · 字是真字，可直接改；错位与颗粒是屏幕/印刷效果，这里有意不做")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
