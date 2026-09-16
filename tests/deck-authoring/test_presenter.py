#!/usr/bin/env python3
"""演示台验证 —— 讲稿层是**运行时产品**，不是一段可选的装饰脚本。

## 为什么要单独测

讲稿层是三块拼起来的：壳开一个窄接口（`window.__deck_ui`）、渲染器发两份载荷
（`#__deck_notes` / `#__deck_outline`）、讲稿层按一串 id 找元素。**缺任何一块，
它都静默失效** —— 按 S 没反应、讲稿空白、下一页指错页，而这一切在
"HTML 生成成功"的视角里全绿。现场才发现是最坏的发现时机。

所以这里钉两件事：

| 钉什么 | 为什么 |
| --- | --- |
| 产物里的合同锚点（id / 载荷 / `data-slide` / 窄接口） | 缺一个 = 讲稿层当场变哑巴 |
| 检查器把缺锚点当**阻塞问题** | 否则它有缺陷也不会有人知道 |

跑法：
    python3 -m unittest discover -s tests/deck-authoring -p "test_presenter.py"
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills",
                     os.path.basename(HERE))
FIXTURES_DIR = os.path.join(HERE, "fixtures")
os.environ.setdefault("DECK_STYLES", os.path.join(FIXTURES_DIR, "styles"))
os.environ.setdefault("DECK_BRANDS", os.path.join(FIXTURES_DIR, "brands"))
SCRIPTS = os.path.join(SKILL, "scripts")
DEMO = os.path.join(FIXTURES_DIR, "demo.spec.json")


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _spec(notes: dict | None = None) -> dict:
    with open(DEMO, encoding="utf-8") as fh:
        deck_spec = json.load(fh)
    for i, text in (notes or {}).items():
        deck_spec["deck"]["slides"][i - 1]["notes"] = text
    return deck_spec


def _payload(page: str, tag_id: str):
    """取内嵌 JSON 载荷；取不到就是产物缺陷 —— 直接断言，别静默返回 None。"""
    hit = re.search(f'<script type="application/json" id="{tag_id}">'
                    f'(.*?)</script>', page, re.S)
    assert hit is not None, f"产物里没有 {tag_id} 载荷"
    return json.loads(hit.group(1))


class TestPresenterContract(unittest.TestCase):
    """渲染器与检查器对讲稿层的合同 —— 真渲一份产物来验（不靠字符串想象）。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.render = _load("deck_render_presenter",
                           os.path.join(SCRIPTS, "render.py"))
        cls.check = _load("deck_check_presenter", os.path.join(SCRIPTS, "check.py"))

    def test_notes_and_outline_ride_with_the_product(self) -> None:
        spec = _spec({1: "开场：先说结论。", 3: "第三页要讲三条依据。"})
        page = self.render.render(spec)
        notes = _payload(page, "__deck_notes")
        self.assertEqual(notes["1"], "开场：先说结论。")
        self.assertEqual(notes["3"], "第三页要讲三条依据。")
        self.assertNotIn("2", notes, "没写讲稿的页不该造一个空条目出来")
        outline = _payload(page, "__deck_outline")
        self.assertEqual(len(outline), len(spec["deck"]["slides"]))
        self.assertTrue(all("t" in row for row in outline))

    def test_every_anchor_the_console_looks_for_exists(self) -> None:
        page = self.render.render(_spec({1: "开场。"}))
        for anchor in self.check.PRESENTER_IDS:
            self.assertIn(f'id="{anchor}"', page, f"讲稿层要的 {anchor} 不在产物里")
        self.assertIn("window.__deck_ui", page, "壳没开窄接口，讲稿层拿不到当前页")
        self.assertIn('id="__deck_console" hidden', page,
                      "讲稿层必须默认收起（否则一打开 deck 就盖住半页）")

    def test_console_ships_no_measured_elements(self) -> None:
        """讲稿层不发 `data-m` —— 否则污染"清单条数 == 实测元素数"那条不变量。"""
        page = self.render.render(_spec({1: "开场。"}))
        start = page.index('<div id="__deck_blackout"')
        end = page.index("</aside>", start)
        self.assertNotIn("data-m", page[start:end])

    def test_contract_gate_passes_on_a_real_product(self) -> None:
        spec = _spec({1: "开场。", 2: "第二页。"})
        self.assertEqual(
            self.check._check_presenter_contract(self.render.render(spec),
                                                 spec["deck"]), [])

    def test_shell_keeps_no_second_counter_when_console_is_open(self) -> None:
        """讲稿层一开，壳自己的页码条退场 —— 一份屏上两个计数器是噪音。"""
        page = self.render.render(_spec({1: "开场。"}))
        self.assertIn("html[data-console] .hud", page)


# 合同门的四种缺法都得点名 —— 它是阻塞门，所以必须**不误伤也不漏**。
GOOD_PAGE = """<html><body>
<section class="slide" data-slide="1" data-idx="01"></section>
<section class="slide" data-slide="2" data-idx="02"></section>
<script type="application/json" id="__deck_notes">{"1": "a"}</script>
<script type="application/json" id="__deck_outline">[{"t": "A"}, {"t": "B"}]</script>
<div id="__deck_blackout"></div>
<aside id="__deck_console"><span id="__deck_console_clock"></span>
<span id="__deck_console_timer"></span><span id="__deck_console_step"></span>
<div id="__deck_console_notes"></div><div id="__deck_console_next"></div></aside>
<script>window.__deck_ui={};</script>
</body></html>"""

GOOD_DECK = {"slides": [{"type": "title", "notes": "a"}, {"type": "content-text"}]}


class TestPresenterGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.check = _load("deck_check_presenter_gate",
                          os.path.join(SCRIPTS, "check.py"))

    def test_complete_product_is_clean(self) -> None:
        self.assertEqual(self.check._check_presenter_contract(GOOD_PAGE, GOOD_DECK), [])

    def test_missing_anchor_is_named(self) -> None:
        page = GOOD_PAGE.replace('<span id="__deck_console_timer"></span>', "")
        problems = self.check._check_presenter_contract(page, GOOD_DECK)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("__deck_console_timer", problems[0])

    def test_missing_ui_interface_is_reported(self) -> None:
        page = GOOD_PAGE.replace("window.__deck_ui", "window.__something_else")
        joined = " ".join(self.check._check_presenter_contract(page, GOOD_DECK))
        self.assertIn("__deck_ui", joined)

    def test_slide_without_data_slide_breaks_positioning(self) -> None:
        page = GOOD_PAGE.replace('<section class="slide" data-slide="2" data-idx="02">',
                                 '<section class="slide" data-idx="02">')
        problems = self.check._check_presenter_contract(page, GOOD_DECK)
        self.assertTrue(any("data-slide" in p and "2" in p for p in problems),
                        problems)

    def test_declared_notes_missing_from_payload(self) -> None:
        deck = {"slides": [{"notes": "a"}, {"notes": "丢了"}]}
        problems = self.check._check_presenter_contract(GOOD_PAGE, deck)
        self.assertTrue(any("第 2 页写了 notes" in p for p in problems), problems)

    def test_broken_payload_and_page_count_mismatch(self) -> None:
        page = GOOD_PAGE.replace('{"1": "a"}', "{不是 JSON")
        page = page.replace('[{"t": "A"}, {"t": "B"}]', '[{"t": "A"}]')
        joined = " ".join(self.check._check_presenter_contract(page, GOOD_DECK))
        self.assertIn("不是合法 JSON", joined)
        self.assertIn("目录载荷 1 条", joined)


if __name__ == "__main__":
    unittest.main()
