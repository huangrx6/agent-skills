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
SCRIPTS = os.path.join(SKILL, "scripts")
TOKENS = os.path.join(SKILL, "dev-tools", "style-fixture", "swiss-grid", "style.json")
DEMO = os.path.join(SKILL, "dev-tools", "demo.spec.json")
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


if __name__ == "__main__":
    unittest.main()
