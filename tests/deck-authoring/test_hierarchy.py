#!/usr/bin/env python3
"""信息层级的回归测试：文本预算、视觉焦点、密度。

这一层最容易出的两个错：

**一、尺子没有牙。** 提示级的检查如果永远不会响，等于没写。所以焦点与预算两条
都有**合成样例**的正面触发（`_el` 造 measured 字典），不依赖"某份 deck 恰好有问题"。

**二、量错了。** 文字元素的 `w` 是**整栏宽**（实测标题 1432px），拿它当权重会得出
"标题和一段正文一样重"。真凭据是 `textW`（离屏 span 量的墨迹宽）—— 所以有一条
用例专门钉这个。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/deck-authoring/test_hierarchy.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")


def _load(name: str):
    key = f"_deck_test_{name}"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, os.path.join(SCRIPTS, f"{name}.py"))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


hierarchy = _load("hierarchy")


def _el(role: str, w: float = 100.0, h: float = 40.0, text_w: float | None = None,
        slide: int = 1, size: float = 32.0) -> dict:
    el = {"role": role, "w": w, "h": h, "slide": slide, "fontSize": size}
    if text_w is not None:
        el["textW"] = text_w
    return el


def _measured(*els: dict) -> dict:
    return {"elements": list(els)}


class TestVisualLen(unittest.TestCase):
    """字数怎么数 —— 混排时按 `len()` 数会把英文标题当成三倍长。"""

    def test_cjk_counts_one_per_char(self) -> None:
        self.assertEqual(hierarchy.visual_len("模型调用量"), 5)

    def test_latin_counts_one_per_word(self) -> None:
        """`len("LLM")` 是 3，但它在版面上是一个词的宽度 —— 按字母数会误报。"""
        self.assertEqual(hierarchy.visual_len("LLM"), 1)
        self.assertEqual(hierarchy.visual_len("the quick brown fox"), 4)

    def test_mixed(self) -> None:
        # "模型" 2 + "3" 1 + "次" 1 + "call" 1 = 5
        self.assertEqual(hierarchy.visual_len("模型 3 次 call"), 5)

    def test_empty_and_punctuation(self) -> None:
        self.assertEqual(hierarchy.visual_len(""), 0)
        self.assertEqual(hierarchy.visual_len("，。！"), 0)


class TestBudget(unittest.TestCase):
    """文本预算（规范第 12 条）。"""

    def test_over_budget_cover_title_is_reported(self) -> None:
        deck = {"slides": [{"type": "title",
                            "title": "这是一个明显超过十二个字的封面主标题用来验证预算"}]}
        issues = hierarchy.budget_issues(deck)
        self.assertTrue(issues, "超预算却没报")
        self.assertIn("第 1 页", issues[0])
        self.assertIn("≤12", issues[0])

    def test_the_repair_order_is_in_the_message(self) -> None:
        """报错要带**怎么修**，而且要按规范的顺序 —— 报错是人一定会读的那段字。"""
        deck = {"slides": [{"type": "title", "title": "一" * 20}]}
        msg = hierarchy.budget_issues(deck)[0]
        for step in ("删掉非必要的字", "拆信息", "换版式", "拆成两页", "最后才允许缩小字号"):
            self.assertIn(step, msg)

    def test_font_shrinking_comes_last(self) -> None:
        """**规范第 12 条的核心**：绝对不要第一步缩字号。"""
        self.assertIn("最后才允许缩小字号", hierarchy.REPAIR_ORDER[-1])
        self.assertNotIn("缩小字号", hierarchy.REPAIR_ORDER[0])

    def test_within_budget_is_silent(self) -> None:
        deck = {"slides": [{"type": "title", "title": "十二个字以内的标题"},
                           {"type": "content-text", "title": "短标题",
                            "bullets": ["也很短"]}]}
        self.assertEqual(hierarchy.budget_issues(deck), [])

    def test_bullets_and_columns_are_checked_too(self) -> None:
        long_bullet = "这一条非常长" * 12
        deck = {"slides": [
            {"type": "content-text", "title": "T", "bullets": [long_bullet]},
            {"type": "two-column", "title": "T", "columns": [
                {"title": "甲", "bullets": ["短"]}, {"title": "乙", "bullets": ["短"]}]},
        ]}
        self.assertTrue(hierarchy.budget_issues(deck))

    def test_missing_fields_are_skipped(self) -> None:
        deck = {"slides": [{"type": "content-text", "title": "T"},
                           {"type": "chart", "title": "C", "data": [{"label": "A", "value": 1}]}]}
        self.assertEqual(hierarchy.budget_issues(deck), [])


class TestWeights(unittest.TestCase):
    """视觉权重：**必须用墨迹宽，不能用整栏宽**。"""

    def test_text_uses_ink_width_not_container_width(self) -> None:
        """**回归**：文字元素的 `w` 是整栏宽（实测标题 1432px），墨迹只占一小块。

        造两个同高同字号、但一个 textW 只有容器三分之一宽的标题：带 textW 的那个
        必须**明显更轻**。用 `w` 算的话两者会一样重 —— 那就等于没测。
        """
        wide = hierarchy.weights(_measured(_el("title", w=1400, h=180, text_w=1400)), 1)
        narrow = hierarchy.weights(_measured(_el("title", w=1400, h=180, text_w=466)), 1)
        self.assertEqual(len(wide), 1)
        self.assertEqual(len(narrow), 1)
        self.assertLess(narrow[0][1], wide[0][1] * 0.5,
                        f"墨迹窄的那条没更轻：{narrow[0][1]} vs {wide[0][1]}")

    def test_text_w_wider_than_container_is_clamped(self) -> None:
        """换行不止一行时 textW 会比容器宽 —— 取 min（那部分确实铺满容器）。"""
        clamped = hierarchy.weights(_measured(_el("bullet", w=800, h=120, text_w=3000)), 1)
        exact = hierarchy.weights(_measured(_el("bullet", w=800, h=120, text_w=800)), 1)
        self.assertAlmostEqual(clamped[0][1], exact[0][1], places=6)

    def test_non_text_uses_the_box(self) -> None:
        image = hierarchy.weights(_measured(_el("image", w=640, h=404)), 1)
        self.assertEqual(len(image), 1)
        self.assertGreater(image[0][1], 0)

    def test_bad_measurements_do_not_raise(self) -> None:
        for bad in ({"role": "title"}, {"role": "title", "w": None, "h": 10},
                    {"role": "title", "w": "a", "h": "b"},
                    {"role": "unknown", "w": 10, "h": 10}):
            with self.subTest(bad=bad):
                self.assertEqual(hierarchy.weights(_measured(bad), 1), [])

    def test_other_slides_are_excluded(self) -> None:
        measured = _measured(_el("title", slide=1), _el("title", slide=2))
        self.assertEqual(len(hierarchy.weights(measured, 1)), 1)

    def test_sorted_descending(self) -> None:
        measured = _measured(_el("title", w=600, h=100, text_w=600),
                             _el("foot", w=600, h=20, text_w=600))
        ws = [w for _r, w, _t in hierarchy.weights(measured, 1)]
        self.assertEqual(ws, sorted(ws, reverse=True))


class TestFocalIssues(unittest.TestCase):
    """视觉焦点（规范第 7 / 8 条）—— 尺子必须有牙。"""

    def _deck(self, pages: int = 1) -> dict:
        return {"slides": [{"type": "content-text", "title": "T", "bullets": ["b"]}] * pages}

    def test_a_clear_leader_passes(self) -> None:
        measured = _measured(_el("title", w=800, h=200, text_w=800),
                             _el("bullet", w=400, h=40, text_w=400))
        self.assertEqual(hierarchy.focal_issues(measured, self._deck()), [])

    def test_two_nearly_equal_elements_are_reported(self) -> None:
        """**牙**：两个同角色同尺寸的元素并排 —— 没有第一焦点。"""
        measured = _measured(_el("title", w=800, h=200, text_w=800),
                             _el("title", w=800, h=200, text_w=800))
        issues = hierarchy.focal_issues(measured, self._deck())
        self.assertTrue(issues, "两个一样重却没报")
        self.assertIn("没有明显的第一焦点", issues[0])

    def test_too_many_heavy_elements_are_reported(self) -> None:
        """规范第 8 条：一页最多 3 个重点（1 主 + 2 次）。"""
        measured = _measured(*[_el("image", w=600, h=400) for _ in range(4)])
        issues = hierarchy.focal_issues(measured, self._deck())
        self.assertTrue(any("重点" in i for i in issues), issues)

    def test_the_gap_is_relative_not_absolute(self) -> None:
        """阈值必须是**相对**的：实测权重在 3~6 量级，绝对阈值 0.25 永不触发。"""
        self.assertGreaterEqual(hierarchy.MIN_FOCAL_GAP, 0.2)
        self.assertLessEqual(hierarchy.MIN_FOCAL_GAP, 0.4)

    def test_almost_equal_weights_with_big_numbers_are_caught(self) -> None:
        """两个很大的权重但只差一点点 —— 相对判据必须能抓到这个。"""
        measured = _measured(_el("image", w=1200, h=800), _el("image", w=1190, h=800))
        self.assertTrue(hierarchy.focal_issues(measured, self._deck()))

    def test_end_pages_are_exempt(self) -> None:
        measured = _measured(_el("title", w=800, h=200, text_w=800),
                             _el("title", w=800, h=200, text_w=800))
        deck = {"slides": [{"type": "end", "title": "谢谢"}]}
        self.assertEqual(hierarchy.focal_issues(measured, deck), [])


class TestDensity(unittest.TestCase):
    """密度分档（规范第 11 条）—— 阈值是工程启发式，所以是提示。"""

    def test_bands_are_ordered_and_named(self) -> None:
        names = [b[2] for b in hierarchy.DENSITY_BANDS]
        self.assertEqual(names, ["Minimal", "Normal", "Information", "Dashboard"])
        for lo, hi, _n, _z in hierarchy.DENSITY_BANDS:
            self.assertLess(lo, hi)

    def _measured(self, top: float, bottom: float, slide: int = 1) -> dict:
        """造一个**真形状**的 measured：`slide_content_span` 读 slides[n-1]["y"]
        与元素的 y/h。第一版这里造错了形状（把 slides 写成 dict），于是用例
        连 KeyError 都盖过去了 —— 那种"只要不抛就算过"的断言等于没测。"""
        return {"slides": [{"y": 0}],
                "elements": [{"slide": slide, "role": "bullet",
                              "y": top, "h": bottom - top}]}

    def test_density_is_measured_from_the_content_span(self) -> None:
        band = hierarchy.render.CONTENT_BOTTOM - hierarchy.render.CONTENT_TOP
        # 铺满整条正文带 → 100%
        full = self._measured(hierarchy.render.CONTENT_TOP,
                              hierarchy.render.CONTENT_BOTTOM)
        self.assertAlmostEqual(hierarchy.density_share(full, 1), 1.0, places=2)
        # 只占一半
        half = self._measured(hierarchy.render.CONTENT_TOP,
                              hierarchy.render.CONTENT_TOP + band / 2)
        self.assertAlmostEqual(hierarchy.density_share(half, 1), 0.5, places=2)

    def test_out_of_band_is_reported(self) -> None:
        """**牙**：铺满正文带（100%）超出所有档位（最高 82%）—— 必须报。"""
        measured = self._measured(hierarchy.render.CONTENT_TOP,
                                  hierarchy.render.CONTENT_BOTTOM)
        deck = {"slides": [{"type": "content-text", "title": "T"}]}
        issues = hierarchy.density_issues(measured, deck)
        self.assertTrue(issues, "满到 100% 却没报")
        self.assertIn("四档之外", issues[0])

    def test_expected_band_mismatch_mentions_the_band(self) -> None:
        """指定期望档位后，偏离要报出来并说明该更满还是更空。"""
        band = hierarchy.render.CONTENT_BOTTOM - hierarchy.render.CONTENT_TOP
        measured = self._measured(hierarchy.render.CONTENT_TOP,
                                  hierarchy.render.CONTENT_TOP + band * 0.3)
        deck = {"slides": [{"type": "content-text", "title": "T"}]}
        issues = hierarchy.density_issues(measured, deck, band="Dashboard")
        self.assertTrue(issues)
        self.assertIn("Dashboard", issues[0])

    def test_cover_and_end_are_exempt(self) -> None:
        measured = self._measured(hierarchy.render.CONTENT_TOP,
                                  hierarchy.render.CONTENT_BOTTOM)
        deck = {"slides": [{"type": "title", "title": "T"},
                           {"type": "end", "title": "E"}]}
        self.assertEqual(hierarchy.density_issues(measured, deck), [])


class TestHardSoftSplit(unittest.TestCase):
    """硬约束与软约束必须分开（规范第 21 条）。"""

    def test_the_two_lists_are_disjoint(self) -> None:
        hard = set(hierarchy.HARD_CONSTRAINTS)
        soft = set(hierarchy.SOFT_CONSTRAINTS)
        self.assertEqual(hard & soft, set())

    def test_overflow_is_hard_and_aesthetics_is_soft(self) -> None:
        joined_hard = " ".join(hierarchy.HARD_CONSTRAINTS)
        for word in ("越界", "重叠", "溢出", "糊"):
            self.assertIn(word, joined_hard)
        self.assertNotIn("平衡", joined_hard)
        self.assertIn("平衡", " ".join(hierarchy.SOFT_CONSTRAINTS))

    def test_report_never_fails(self) -> None:
        """提示级的东西**永远退出 0** —— 否则第一份正常 deck 就被挡住。"""
        import inspect

        src = inspect.getsource(hierarchy.report)
        self.assertIn("return 0", src)


if __name__ == "__main__":
    unittest.main()
