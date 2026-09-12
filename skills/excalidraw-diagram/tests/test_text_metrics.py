#!/usr/bin/env python3
"""text_metrics.py 的回归测试。

为什么需要：这个模块守的是前作 `draw-excalidraw` 真正的病灶 —— 它**有正确的宽度模型**
（1.00 / 0.56，与本模块一致），却依然文字溢出，因为**断行宽度与容器宽度没有耦合**：
`wrapText(maxUnits = 22)` 里的 22 是写死的，与容器尺寸档位无关。

所以本模块最要紧的一条是**耦合不变量**：

    容器宽度 × （减去内边距） ≥ 实际每一行的文字宽度 × 字号

按构造它恒成立。测试要守住的就是"它恒成立"，而不是某一个具体数字。
一旦它被破坏（有人把容器宽度改回按档位查表、或把断行宽度改成别的值），
下面的 `test_container_never_narrower_than_text` 会失败。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/test_text_metrics.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
TEXT_METRICS = os.path.join(SCRIPTS, "text_metrics.py")


def _load():
    spec = importlib.util.spec_from_file_location("text_metrics_under_test", TEXT_METRICS)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {TEXT_METRICS}")
    module = importlib.util.module_from_spec(spec)
    # 必须先注册进 sys.modules:不注册的话 @dataclass 会炸——
    # dataclasses._is_type 会去查 sys.modules.get(cls.__module__) 并拿到 None。
    # 这是用 importlib 加载模块的正确做法,不是绕过。
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# 覆盖各字符类、长度、空白形态的样本
SAMPLES = [
    "鉴权",
    "鉴权服务",
    "Auth Service",
    "鉴权服务 Auth",
    "这是一个相当长的中文节点标题用来触发断行行为",
    "A very long English node label that definitely needs wrapping",
    "混合 CJK 与 Latin 的 node label 会怎样断行",
    "短",
    "x",
    "Redis",
    "数据库 / 持久化存储",
    "用户 -> 网关 -> 服务 -> 数据库 的一条长链路",
    "https://example.com/a/very/long/unbreakable/url/segment",
    "onelinewithoutanyspacesatallbutveryverylongtoken",
]


class TextMetricsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    # ── 防线 1:宽度权重（数值取自前作,没被推翻） ──
    def test_wide_and_narrow_weights(self):
        self.assertEqual(self.m.weighted_units("中"), 1.00)
        self.assertEqual(self.m.char_weight("A"), 0.56)
        self.assertAlmostEqual(self.m.weighted_units("AB"), 1.12)
        # 全角标点、假名、谚文都按全角算
        for ch in ("，", "。", "ア", "한"):
            with self.subTest(ch=ch):
                self.assertEqual(self.m.char_weight(ch), 1.00)

    def test_same_char_count_differs_between_cjk_and_latin(self):
        # 这一条就是"字符数简单映射"为什么不行：同样 10 个字符，宽度差近一倍
        zh_text, en_text = "中文字符宽度测试", "abcdefgh"
        self.assertEqual(len(zh_text), len(en_text), "样本长度要相等才有可比性")
        zh = self.m.weighted_units(zh_text)
        en = self.m.weighted_units(en_text)
        self.assertAlmostEqual(zh / en, 1.00 / 0.56, places=2)

    # ── 防线 2:档位边界 ──
    def test_size_class_boundaries(self):
        cases = [(5.0, "S"), (10.0, "S"), (10.1, "M"), (16.0, "M"), (16.1, "L"), (24.0, "L")]
        for units, want in cases:
            with self.subTest(units=units):
                self.assertEqual(self.m.size_class_for(units)[0], want)

    def test_over_largest_class_is_reported_as_content_problem(self):
        self.assertFalse(self.m.too_long_for_largest("短标题"))
        self.assertTrue(self.m.too_long_for_largest("很长" * 20))

    # ── 防线 3:耦合不变量（前作真正栽的地方） ──
    def test_container_never_narrower_than_text(self):
        for s in SAMPLES:
            with self.subTest(sample=s):
                box = self.m.measure(s, "次要说明 secondary detail")
                budget = box.width - 2 * self.m.PADDING_X
                for line in box.lines + box.detail_lines:
                    self.assertLessEqual(
                        self.m.weighted_units(line) * self.m.FONT_NODE,
                        budget + 1e-6,
                        f"容器比文字窄 —— 耦合被破坏了（前作的病灶）：{s!r}",
                    )

    def test_overflow_flag_is_always_false(self):
        # 按构造永远为 False；它为 True 只可能是 measure 被改坏了
        for s in SAMPLES:
            with self.subTest(sample=s):
                self.assertFalse(self.m.measure(s, "d").overflowed)

    def test_break_width_is_what_container_uses(self):
        # 反过来说明耦合方向：容器宽度由断行宽度算出，不是按档位查表
        box = self.m.measure("Auth Service")
        self.assertAlmostEqual(box.width, box.break_units * self.m.FONT_NODE
                               + 2 * self.m.PADDING_X)

    # ── 防线 4:断行行为 ──
    def test_cjk_breaks_anywhere(self):
        lines, forced = self.m.wrap("中文可以逐字断开这是设计意图", 5.0)
        self.assertTrue(len(lines) > 1)
        self.assertEqual(forced, [])
        for l in lines:
            self.assertLessEqual(self.m.weighted_units(l), 5.0 + 1e-6)

    def test_latin_breaks_at_spaces_only(self):
        lines, forced = self.m.wrap("alpha beta gamma", 5.6)
        self.assertEqual(lines, ["alpha", "beta", "gamma"])
        self.assertEqual(forced, [], "拉丁词不该被强行切开")

    def test_explicit_newline_is_respected(self):
        lines, _ = self.m.wrap("第一行\n第二行", 24.0)
        self.assertEqual(lines, ["第一行", "第二行"])

    def test_unbreakable_token_is_force_broken_and_recorded(self):
        long_url = "https://example.com/" + "a" * 60
        lines, forced = self.m.wrap(long_url, 10.0)
        self.assertTrue(forced, "超长不可断词应当被记录,否则报告里提不出来")
        for l in lines:
            self.assertLessEqual(self.m.weighted_units(l), 10.0 + 1e-6)

    def test_empty_input(self):
        lines, forced = self.m.wrap("", 10.0)
        self.assertEqual(lines, [""])
        self.assertEqual(forced, [])

    # ── 防线 5:字号固定 3 档（不给区间） ──
    def test_font_sizes_are_fixed_values_not_ranges(self):
        for attr in ("FONT_TITLE", "FONT_NODE", "FONT_DETAIL"):
            with self.subTest(attr=attr):
                self.assertIsInstance(getattr(self.m, attr), float)

    def test_size_classes_are_ordered(self):
        caps = [c for _, c in self.m.SIZE_CLASSES]
        self.assertEqual(caps, sorted(caps), "档位必须递增")
        self.assertEqual(len(caps), 3, "档位固定 3 档")


if __name__ == "__main__":
    unittest.main(verbosity=2)
