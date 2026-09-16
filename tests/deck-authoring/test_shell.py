#!/usr/bin/env python3
"""deck 外壳的行为验证 —— 演示态是**运行时视图**，不是产物版式。

## 为什么外壳要单独测

外壳是纯 JS/CSS。它坏了不会让任何一条机械校验变红 —— 校查验的是内容与版面，
而外壳只决定"人能不能拿它讲"。一个讲不了的 deck，校验全绿也没用。

所以这里测**行为**（真开一次浏览器、真按键、真读页码），不是"HTML 里有没有这段
字符串"。字符串断言只留给那两条不需要浏览器就能判的不变量。

## 三条不变量

| 不变量 | 破了会怎样 |
| --- | --- |
| 壳不带 `data-m` | 污染"清单条数 == 实测元素数"，而那条撑着整条导出链 |
| 打印态不缩放 | 导出的 PDF 是缩小的（屏幕用的缩放渗进纸面） |
| 演示态只显示 1 页 | 那不是"演示"，是把滚动页套了个壳 |

## 关键设计（别改成"演示态即产物版式"）

产物文件**永远**是 1600×900、未缩放的竖向堆叠 —— `measure.py` 用
`getBoundingClientRect` 量真实像素，`shots.py` 按真实偏移滚屏，两者都吃这个几何。
演示态只额外叠一层**整体相似变换**：等比缩放不引入裁切，所以"量未缩放的原件"
依然成立。真把缩放写进产物版式，度量层当场失效。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/deck-authoring/test_shell.py
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
# 测试自有夹具（v4）：风格与内容样本都放在 tests/ 下，**不随 skill 发布** ——
# 可拷贝的模板必然变成默认答案（用户实测：每份 deck 长得一样）。
FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
# 夹具当"额外风格根"：v4 起工具链不内置任何风格（可拷贝的模板必然变成
# 默认答案）。脚本各持一份模块副本，所以走环境变量而不是改常量。
os.environ.setdefault("DECK_STYLES",
                      os.path.join(FIXTURES_DIR, "styles"))
os.environ.setdefault("DECK_BRANDS",
                      os.path.join(FIXTURES_DIR, "brands"))
SCRIPTS = os.path.join(SKILL, "scripts")
TOKENS = os.path.join(FIXTURES_DIR, "styles", "swiss-grid", "style.json")
DEMO = os.path.join(FIXTURES_DIR, "demo.spec.json")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# 探针在 load 后**同步**跑完并把结果塞进 <pre>。同步是重点：靠 rAF 会被
# --virtual-time-budget 的虚拟时间抢跑，同一份产物三次能测出两种结果（measure.py 踩过）。
PROBE = """
<pre id="__out"></pre>
<script>
function vis(){return [].slice.call(document.querySelectorAll('section.slide'))
  .filter(function(s){return getComputedStyle(s).display!=='none'}).length;}
function key(k){document.dispatchEvent(new KeyboardEvent('keydown',{key:k,bubbles:true}));}
window.addEventListener('load', function(){
  var r={};
  r.view0=document.documentElement.getAttribute('data-view');
  r.vis0=vis();
  r.hud0=document.getElementById('__deck_page').textContent;
  key('ArrowRight'); key('ArrowRight');
  r.hud2=document.getElementById('__deck_page').textContent;
  r.curIdx=[].slice.call(document.querySelectorAll('section.slide'))
    .indexOf(document.querySelector('section.slide.is-cur'));
  key('End'); r.hudEnd=document.getElementById('__deck_page').textContent;
  key('p');
  r.viewP=document.documentElement.getAttribute('data-view');
  r.visP=vis();
  r.kP=parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--k'));
  r.vw=window.innerWidth; r.vh=window.innerHeight;
  key('Escape');
  r.viewEsc=document.documentElement.getAttribute('data-view');
  r.visEsc=vis();
  document.getElementById('__out').textContent=
    btoa(unescape(encodeURIComponent(JSON.stringify(r))));
});
</script>
"""


def probe_browser(html: str, query: str = "", size: str = "1400,900") -> dict:
    """真开一次 Chrome，问外壳几个行为问题。"""
    if not os.path.isfile(CHROME):
        raise RuntimeError(f"找不到 Chrome：{CHROME}\n  外壳是 JS —— 不真跑一次就测不了它。")
    with tempfile.TemporaryDirectory() as td:
        page = os.path.join(td, "p.html")
        with open(page, "w", encoding="utf-8") as fh:
            fh.write(html.replace("</body>", PROBE + "</body>"))
        dom = subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
             f"--window-size={size}", "--virtual-time-budget=3000", "--dump-dom",
             f"file://{page}{query}"],
            capture_output=True, text=True, timeout=120).stdout
    m = re.search(r'id="__out">([A-Za-z0-9+/=]+)<', dom)
    if not m:
        raise AssertionError("探针没回话 —— 页面里的脚本大概抛异常了（外壳 JS 坏了？）")
    return json.loads(base64.b64decode(m.group(1)).decode("utf-8"))


class TestShell(unittest.TestCase):
    """一次 Chrome 启动约 2.5 秒（还是无头），所以探针结果在 `setUpClass` 里算一次共享。

    默认那一次探测就把滚动/翻页/P 切换/Esc 全跑完了，所以一个会话能喂饱好几条用例。
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.render = _load("deck_render_shell", os.path.join(SCRIPTS, "render.py"))
        with open(TOKENS, encoding="utf-8") as fh:
            cls.tokens = json.load(fh)
        with open(DEMO, encoding="utf-8") as fh:
            cls.spec = json.load(fh)
        cls.html = cls.render.render(cls.spec)
        cls.total = len(cls.spec["deck"]["slides"])
        cls.default = probe_browser(cls.html)                        # 不预设视图
        cls.present = probe_browser(cls.html, query="?present")      # 直接进演示态
        cls.extreme = {s: probe_browser(cls.html, query="?present", size=s)
                       for s in ("800,1400", "2400,700")}

    # ── 不需要浏览器就能判的两条 ─────────────────────────────────────────

    def test_shell_chrome_carries_no_identity(self) -> None:
        """壳（页码 / 快捷键提示）不能带 `data-m`。

        它们是壳不是内容。带了就会进"清单条数 == 实测元素数"那条不变量 ——
        那条一旦被壳污染，`measure.py` 和导出链会开始互相甩锅。
        """
        frags = re.findall(r'<div class="(?:hud|hint)"[^>]*>', self.html)
        self.assertEqual(len(frags), 2, f"壳元素应恰好 2 个（页码 + 提示），实际 {len(frags)}")
        for frag in frags:
            self.assertNotIn("data-m", frag, f"壳元素带了身份：{frag}")

    def test_print_view_is_unscaled_and_paged(self) -> None:
        """打印态必须把演示态的缩放**清掉**，并且一页一张。

        不写这两句，`--print-to-pdf` 出来就是缩小 + 只打第一页 ——
        屏幕上的壳不能渗进纸面。
        """
        m = re.search(r"@media print\s*\{(.*?)\n\}", self.html, re.S)
        assert m is not None, "产物里没有 @media print —— PDF 导出没有依托"
        block = m.group(1)
        self.assertIn("transform:none", block, "打印态没有清掉演示态的 scale")
        self.assertIn("break-after:page", block, "打印态没有分页，只会出第一页")
        self.assertIn(".hud", block, "打印态没有隐藏壳（页码会印到纸上）")

    # ── 真开浏览器测行为 ────────────────────────────────────────────────

    def test_scroll_view_shows_every_slide(self) -> None:
        """默认（滚动态）必须全显示 —— 度量层和截图层都吃这个几何。

        断言的是「不是演示态」而不是「没有 data-view 属性」：滚动态现在会**显式**
        写 `data-view="scroll"`（frame 态也是同一套机制的第三个值），
        “没这个属性”是实现细节，不是意图。
        """
        r = self.default
        self.assertIn(r["view0"], (None, "scroll"),
                      f"默认进了不该进的视图：{r['view0']}")
        self.assertEqual(r["vis0"], self.total, "默认态应显示全部页")
        self.assertEqual(r["hud0"], f"1 / {self.total}")

    def test_keyboard_navigation_moves_and_counts(self) -> None:
        """→ 翻页、页码跟着走、当前页标记落在正确的那一页。"""
        r = self.default
        self.assertEqual(r["hud2"], f"3 / {self.total}", "按两次 → 应到第 3 页")
        self.assertEqual(r["curIdx"], 2, ".is-cur 没落在第 3 页上")
        self.assertEqual(r["hudEnd"], f"{self.total} / {self.total}", "End 应跳末页")

    def test_p_key_enters_present_mode_fitted(self) -> None:
        """按 P 进演示态：只显示 1 页，且 --k 恰好是 min(视口宽/1600, 视口高/900)。"""
        r = self.default
        self.assertEqual(r["viewP"], "present")
        self.assertEqual(r["visP"], 1, "演示态显示了不止 1 页")
        want = min(r["vw"] / 1600, r["vh"] / 900)
        self.assertAlmostEqual(r["kP"], want, places=6,
                               msg=f"缩放比不对：{r['kP']} vs min({r['vw']}/1600, {r['vh']}/900)={want}")

    def test_escape_restores_scroll_view(self) -> None:
        """Esc 从演示态回滚动态，并且该显示的又都显示了。"""
        r = self.default
        self.assertEqual(r["viewEsc"], "scroll")
        self.assertEqual(r["visEsc"], self.total)

    def test_query_param_starts_in_present_mode(self) -> None:
        """`out.html?present` 直接进演示态 —— 讲的时候不用先按一下。"""
        r = self.present
        self.assertEqual(r["view0"], "present")
        self.assertEqual(r["vis0"], 1)
        self.assertGreater(r["kP"], 0, "演示态下 --k 没算出来 —— 缩放没生效")

    def test_fit_survives_extreme_viewports(self) -> None:
        """极窄 / 极高视口下缩放比仍要贴边不溢出（letterbox 的意义就在这）。"""
        for size, r in self.extreme.items():
            with self.subTest(size=size):
                self.assertLessEqual(r["kP"] * 1600, r["vw"] + 0.5, f"{size} 宽度溢出")
                self.assertLessEqual(r["kP"] * 900, r["vh"] + 0.5, f"{size} 高度溢出")
                self.assertAlmostEqual(r["kP"], min(r["vw"] / 1600, r["vh"] / 900), places=6)



class TestBulletMarkerOwnership(unittest.TestCase):
    """条目标记**归皮肤**：壳只做结构 reset，不发标记。

    壳原来在每条前发一个 `<i>■</i>`：皮肤再画自己的标记（`.bullets li::before`
    短横）时就成了**两个标记**，而且那个方块没有间距、直接贴住正文（实测截图：
    蓝短横 + 黑方块贴字）。装饰归风格是这条流水线的基本分工，所以壳不再发标记。
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.render = _load("deck_render_marker", os.path.join(SCRIPTS, "render.py"))
        with open(DEMO, encoding="utf-8") as fh:
            cls.html = cls.render.render(json.load(fh))

    def test_shell_emits_no_bullet_marker(self) -> None:
        self.assertNotIn("<i>■</i>", self.html,
                         "壳不该发条目标记 —— 那是皮肤的 ::before")
        for chunk in ("<li ",):
            self.assertIn(chunk, self.html, "条目本身还要在")

    def test_bullets_keep_a_structural_reset(self) -> None:
        self.assertIn(".bullets{list-style:none", self.html,
                      "壳要给条目列表一条结构 reset（无默认圆点、无浏览器缩进）")


class TestOrnamentNote(unittest.TestCase):
    """条目以装饰字符开头 → 提示（两个标记 + 贴字）。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.check = _load("deck_check_ornament", os.path.join(SCRIPTS, "check.py"))

    def test_ornament_leading_bullets_are_flagged(self) -> None:
        deck = {"slides": [{"type": "content-text", "title": "t",
                            "bullets": ["▦ backend/services：编排层", "普通条目"]}]}
        notes = self.check._ornament_notes(deck)
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("▦", notes[0])
        self.assertIn("第 1 页", notes[0])

    def test_numerals_and_plain_text_are_silent(self) -> None:
        deck = {"slides": [{"type": "content-text", "title": "t",
                            "bullets": ["① 量化评级", "② 归档", "普通条目"]}]}
        self.assertEqual(self.check._ornament_notes(deck), [],
                         "① 是数字（No），不是装饰字符")



class TestInlineText(unittest.TestCase):
    """文本的两条硬约定：Markdown 星号要变成加粗；图注要有缺省样式。

    实测踩过两件：第 3 页条目把 `**6 因素**` 原样显示（屏幕上就是星号）；
    用户的皮肤没写 `.chartcap` 时，图注直接贴住图、而且用正文的黑 —— 两条都得由壳兜住。
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.render = _load("deck_render_inline", os.path.join(SCRIPTS, "render.py"))
        with open(DEMO, encoding="utf-8") as fh:
            cls.html = cls.render.render(json.load(fh))

    def test_markdown_bold_becomes_em_span(self) -> None:
        self.assertEqual(self.render.rich("**6 因素** 硬尺标统一口径"),
                         '<span class="em">6 因素</span> 硬尺标统一口径')

    def test_rich_still_escapes(self) -> None:
        self.assertEqual(self.render.rich('<script>&"x"'),
                         '&lt;script&gt;&amp;&quot;x&quot;')
        self.assertNotIn("<script>", self.render.rich("<script>alert(1)</script>"))

    def test_shell_gives_captions_a_default_gap_and_muted_color(self) -> None:
        self.assertIn(".chartcap{margin-top:var(--sp-inner)", self.html,
                      "图注的间距/颜色不能只靠皮肤 —— 皮肤没写就贴住图")
        self.assertIn("opacity:.62", self.html)
        self.assertIn(".em{font-weight:700}", self.html,
                      "行内强调要有样式，否则 span 是隐形的")


class TestMarkdownNote(unittest.TestCase):
    """文本里出现 Markdown 标记 → 提示（格式归版式）。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.check = _load("deck_check_markdown", os.path.join(SCRIPTS, "check.py"))

    def test_markdown_in_content_is_flagged(self) -> None:
        deck = {"slides": [{"type": "content-text", "title": "t",
                            "bullets": ["**6 因素** 硬尺标统一口径", "普通条目"]}]}
        notes = self.check._markdown_notes(deck)
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("第 1 页", notes[0])

    def test_plain_content_is_silent(self) -> None:
        deck = {"slides": [{"type": "content-text", "title": "t",
                            "bullets": ["6 因素 硬尺标统一口径"]}]}
        self.assertEqual(self.check._markdown_notes(deck), [])



class TestImageSlotRatio(unittest.TestCase):
    """**槽位定比例**，图片自身比例只管裁切/留边。

    实测背景：生图工具出成 1:1 / 4:3 / 2:1 是常态（提示词按不住比例）。以前壳只写
    `width:100%`，高度跟着图片走 —— 1:1 撑出页底（实测溢出 109px）、2:1 留空洞，
    于是人被逼着重出图。现在高度由槽位比例定，多出来的按 `visual.kind` 处理。
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.render = _load("deck_render_ratio", os.path.join(SCRIPTS, "render.py"))
        with open(TOKENS, encoding="utf-8") as fh:
            cls.tokens = json.load(fh)

    def _page(self, kind: str) -> str:
        spec = {"deck": {"style": "swiss-grid", "colorSet": "blue", "seed": 1,
                         "title": "t", "slides": [
                             {"type": "content-image", "title": "图页",
                              "image": "x.png", "bullets": ["一条"],
                              "visual": {"kind": kind}}]}}
        return self.render.render(spec)

    def test_slot_owns_the_display_ratio(self) -> None:
        html = self._page("evidence_image")
        self.assertIn("aspect-ratio:var(--img-ratio,3/2)", html,
                      "高度必须由槽位定（缺省 3:2，可由 visual.ratio 覆盖）")
        self.assertIn("object-fit:cover", html, "照片：按中心裁切")

    def test_diagram_is_letterboxed_not_cropped(self) -> None:
        fig = re.search(r'<figure class="imgwrap"[^>]*>', self._page("diagram"))
        assert fig is not None
        self.assertIn('data-fit="contain"', fig.group(0),
                      "结构图不能裁 —— 图里每一笔都是信息")
        fig2 = re.search(r'<figure class="imgwrap"[^>]*>', self._page("evidence_image"))
        assert fig2 is not None
        self.assertNotIn("data-fit", fig2.group(0))



class TestColumnHooks(unittest.TestCase):
    """卡片（two-column）要发跟顶层一样的东西：钩子类 + 阶梯变量。

    实测缺陷：卡片的 `<h3>` 没类（皮肤写 `.colTitle` 从不命中 → 渲染成 UA 的
    `<h3>`：18.7px/700/系统默认族，而阶梯里是 26px 展示衬线）；卡片的 `<ul>` 漏发
    `--s-bullet`（皮肤那条 `font: 400 var(--s-bullet)/…` 因变量不存在**整条失效**，
    连字体族一起丢）。同一个角色，壳发的东西必须一致 —— 否则“字号/字重/字体族”
    三样会一起静默跑偏，而门只能看见“字体族丢了”这一面。
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.render = _load("deck_render_colhooks", os.path.join(SCRIPTS, "render.py"))

    def _page(self) -> str:
        spec = {"deck": {"style": "swiss-grid", "colorSet": "blue", "seed": 1,
                         "title": "t", "slides": [
                             {"type": "two-column", "title": "双栏",
                              "columns": [{"title": "左", "bullets": ["a", "b"]},
                                          {"title": "右", "bullets": ["c", "d"]}]}]}}
        return self.render.render(spec)

    def test_slide_box_keeps_its_size(self) -> None:
        """皮肤给 `.slide` 加边框不能把页盒掉大（实测 1px 就把 PDF 变成两倍页数）。"""
        html = self._page()
        m = re.search(r"\.slide\{[^}]*\}", html)
        assert m is not None
        self.assertIn("box-sizing:border-box", m.group(0))

    def test_column_title_carries_the_hook_class(self) -> None:
        self.assertIn('<h3 class="colTitle"', self._page())

    def test_column_list_carries_the_tier_variable(self) -> None:
        html = self._page()
        m = re.search(r'<ul class="bullets small"[^>]*>', html)
        assert m is not None, "卡片的列表没渲出来"
        self.assertIn("--s-bullet:", m.group(0))


class TestStructureVariants(unittest.TestCase):
    """结构变体真的渲得出来（词表里的名字 ↔ CSS 里的类名 ↔ DOM 上的类，三处必须对上）。

    实测踩过：候选搜索里一个词表名字，如果渲染器没实现对应 CSS，
    三个"结构不同"的候选会渲成同一个样子 —— 比不给候选更差（给了假选择）。
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.render = _load("deck_render_variants", os.path.join(SCRIPTS, "render.py"))

    def _render(self, slide: dict) -> str:
        spec = {"deck": {"style": "swiss-grid", "colorSet": "blue", "seed": 1,
                         "title": "t", "slides": [
                             {"title": "页", "bullets": ["一条", "两条"],
                              "image": "x.png",
                              "visual": {"kind": "evidence_image"}, **slide}]}}
        return self.render.render(spec)

    def test_visual_wide_gets_its_own_grid(self) -> None:
        html = self._render({"type": "content-image", "layout": "visual-wide"})
        self.assertIn('class="two v-visual-wide"', html)
        self.assertIn(".two.v-visual-wide .main{width:461.33px}", html)
        self.assertIn(".two.v-visual-wide .imgwrap{width:946.67px}", html)

    def test_hard_lean_columns_get_their_own_grid(self) -> None:
        html = self._render({"type": "two-column", "layout": "lean-hard-left",
                             "columns": [{"title": "左", "bullets": ["a"]},
                                         {"title": "右", "bullets": ["b"]}]})
        self.assertIn('class="cols v-lean-hard-left"', html)
        self.assertIn(".cols.v-lean-hard-left .col:first-child", html)

    def test_every_vocab_name_has_a_renderer_branch(self) -> None:
        """词表里的每个名字都要能在产物里出现**同名**类名（否则就是承诺了却没实现）。

        类名 = layout 名是契约：皮肤作者按名字就能选到，不用猜。历史上 visual-left
        渲的是 `v-left`，那种"名字对不上"最难查（皮肤里那条规则永远不生效）。
        """
        for name in self.render.IMAGE_LAYOUTS:
            html = self._render({"type": "content-image", "layout": name})
            marker = ("herofig" if name == "hero"
                      else 'class="two' + ("" if name == "visual-right" else f" v-{name}"))
            self.assertIn(marker, html, f"content-image 的 {name} 没有渲出来")
        for name in self.render.TWO_COL_LAYOUTS:
            html = self._render({"type": "two-column", "layout": name,
                                 "columns": [{"title": "左", "bullets": ["a"]},
                                             {"title": "右", "bullets": ["b"]}]})
            marker = ('class="cols"' if name == "even" else f'class="cols v-{name}"')
            self.assertIn(marker, html, f"two-column 的 {name} 没有渲出来")

    def test_legacy_visual_left_class_is_kept(self) -> None:
        """历史短名 `v-left` 不能因为改名默默失效（已在皮肤里的选择器还要能用）。"""
        html = self._render({"type": "content-image", "layout": "visual-left"})
        self.assertIn('class="two v-visual-left v-left"', html)


class TestStyleLocationNote(unittest.TestCase):
    """风格的位置要开口说：**风格随 deck 项目交付**。

    实测事故：一份 17 页 deck 的风格目录放在 /tmp，被清掉后 spec 里的 deck.style
    成了死链，整套版式再也复现不出来。这条提示就是那次事故的产物。
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.render = _load("deck_render_styleloc", os.path.join(SCRIPTS, "render.py"))

    def test_temp_style_is_flagged(self) -> None:
        note = self.render.style_location_note("/tmp/some-style", "/tmp/deck.spec.json")
        self.assertIsNotNone(note)
        self.assertIn("临时目录", note or "")
        self.assertIn("项目目录", note or "")

    def test_spec_in_temp_but_style_in_project_names_the_spec(self) -> None:
        """要挪的东西不同，说法就不同：spec 在 /tmp 时不能劝"把风格挪到 spec 旁边"。"""
        D = os.path.dirname(SCRIPTS)          # 非临时目录
        note = self.render.style_location_note(
            os.path.join(D, "styles"), "/tmp/some/deck.spec.json")
        self.assertIn("spec 在临时目录", note or "")

    def test_style_outside_the_deck_project_is_flagged(self) -> None:
        # 两边都得在**非临时目录**里，才能测到"项目之外"那一条：
        # 夹具目录当 deck 项目，skill 目录当"项目之外"的风格根。
        spec = os.path.join(FIXTURES_DIR, "demo.spec.json")
        skill_dir = os.path.dirname(SCRIPTS)
        outside = self.render.style_location_note(skill_dir, spec)
        self.assertIn("项目之外", outside or "")
        inside = self.render.style_location_note(
            os.path.join(FIXTURES_DIR, "styles", "swiss-grid"), spec)
        self.assertIsNone(inside, "风格在 deck 项目里就不该念")


class TestHeroHeight(unittest.TestCase):
    """hero 的图高**按这一页要装什么算** —— 不是一个固定值。

    旧写法按"有没有条目"在两个固定值（520/648）里挑，实测后果：条目到 6 条时
    正文带溢出 81px、caption 顶到页脚上（`check` 报三处越界 + 三处"太近"），
    而图还占着 520px 不让。这条测试钉住"条目越多、图越矮"这个方向。
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.render = _load("deck_render_heroh", os.path.join(SCRIPTS, "render.py"))

    def _hero(self, bullets: list, caption: bool = False) -> str:
        slide = {"type": "content-image", "layout": "hero", "title": "页",
                 "image": "x.png", "bullets": bullets,
                 "visual": {"kind": "diagram"}}
        if caption:
            slide["caption"] = "图注"
        spec = {"deck": {"style": "swiss-grid", "colorSet": "blue", "seed": 1,
                         "title": "t", "slides": [slide]}}
        return self.render.render(spec)

    @staticmethod
    def _height(html: str) -> int:
        # 只认那条标签（`class="herofig" … style="height:Npx"`）—— 放宽会把
        # 壳 CSS 里的 `height:…` 也匹配进来（实测匹配到 56，然后断言全错）
        hit = re.search(r'class="herofig"[^>]*style="height:(\d+)px', html)
        assert hit is not None, "hero 页没有渲染出图高"
        return int(hit.group(1))

    def test_more_items_means_shorter_figure(self) -> None:
        few = self._height(self._hero(["一", "二"]))
        many = self._height(self._hero(["一"] * 6))
        self.assertGreater(few, many, "条目多了图就该让位")
        self.assertGreaterEqual(many, self.render.HERO_MIN_H,
                                "图矮到下限就不再让（该换版式/拆页，由 check 说）")
        self.assertLessEqual(few, self.render.HERO_MAX_H)

    def test_no_items_takes_the_max(self) -> None:
        self.assertEqual(self._height(self._hero([])), self.render.HERO_MAX_H)

    def test_caption_is_reserved_in_the_height(self) -> None:
        """有图注要再让出一块 —— 图注是普通流，不像 hero 标题那样住图里。"""
        self.assertLess(self._height(self._hero(["一"], caption=True)),
                        self._height(self._hero(["一"])))

    def test_hero_caption_gets_the_clearance_token(self) -> None:
        """hero 流里的图注是顶层元素（拿不到 figure 成员豁免），必须用够的 token。

        --sp-inner(16) < 安全盒要求的 28（body 下 16 + caption 上 12）——
        以前就是它导致每张 hero 页都报"太近"。
        """
        html = self._hero(["一"], caption=True)
        self.assertIn(".herofig + .chartcap, .hero-bullets + .chartcap", html)
        self.assertIn("--sp-block", html)


if __name__ == "__main__":
    unittest.main()
