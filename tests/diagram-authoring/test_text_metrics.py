#!/usr/bin/env python3
"""text_metrics.py 的回归测试。

为什么需要：这个模块守的是前作 `draw-excalidraw` 真正的病灶 —— 它**有正确的模型结构**
（宽度 = 每行 units × 字号，CJK 与拉丁分开计），却依然文字溢出，因为
**断行宽度与容器宽度没有耦合**：`wrapText(maxUnits = 22)` 里的 22 是写死的，
与容器尺寸档位无关。

（它的拉丁常数 0.56 后来被实测推翻：对 MQ / CPU / DB 这类大写缩写偏窄 15~30%，
已换成按字符查 Helvetica 实测表。见 `test_latin_advance_table_is_the_measured_one`。）

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
# 测试住在仓库顶层 `tests/<skill>/`（**刻意不在 skill 目录里**：AI 调用 skill 时读的是
# `skills/<skill>/` 那棵树，测试放在里面会被顺手读进去）。
# 所以从 `tests/<skill>/` 往上两级到仓库根，再进 `skills/<skill>/`。
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")
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

    # ── 防线 1:宽度权重（拉丁那半已按实测换掉） ──
    def test_wide_and_narrow_weights(self):
        self.assertEqual(self.m.weighted_units("中"), 1.00)
        self.assertEqual(self.m.char_weight("A"), 0.70)
        self.assertAlmostEqual(self.m.weighted_units("AB"), 1.40)
        # 全角标点、假名、谚文都按全角算
        for ch in ("，", "。", "ア", "한"):
            with self.subTest(ch=ch):
                self.assertEqual(self.m.char_weight(ch), 1.00)

    def test_latin_advance_table_is_the_measured_one(self):
        """锁住**实测数据本身**。

        表里的值是拿 PIL + Helvetica 逐个字符量出来、再向上取整到 0.05 的。
        没有 PIL 就没法在测试里重新量 —— 所以这里锁住数值：
        改这张表必须是刻意的，不能顺手调。
        """
        for ch, want in (("i", 0.25), ("l", 0.25), ("I", 0.30), (" ", 0.30),
                         ("a", 0.60), ("1", 0.60), ("A", 0.70), ("M", 0.85),
                         ("W", 0.95), ("@", 1.05)):
            with self.subTest(ch=ch):
                self.assertEqual(want, self.m.char_weight(ch))

    def test_unknown_characters_are_assumed_widest(self):
        """表里没有的字符按最宽估 —— 两边代价不对称：估宽只是多留白，估窄会毁掉布局。"""
        for ch in ("é", "Я", "🙂"):
            with self.subTest(ch=ch):
                self.assertEqual(1.00, self.m.char_weight(ch))

    def test_same_char_count_differs_between_cjk_and_latin(self):
        """这一条就是“字符数简单映射”为什么不行：同样 8 个字符，宽度差近一倍。"""
        zh_text, en_text = "中文字符宽度测试", "abcdefgh"
        self.assertEqual(len(zh_text), len(en_text), "样本长度要相等才有可比性")
        zh = self.m.weighted_units(zh_text)
        en = self.m.weighted_units(en_text)
        self.assertEqual(8.0, zh, "全角字符恰好 1.0 em")
        self.assertGreater(zh / en, 1.5, "中文应当明显更宽")
        self.assertLess(zh / en, 2.5)

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
        """容器不能比文字窄（前作的病灶就是这个耦合被破坏）。

        **每桶按自己的字号算**：标题 16px、说明 12px。拿标题的字号去量说明行是在算
        一个不存在的宽度 —— 那会把"说明列只有标题列的 75% 宽"这个 bug 当成正确的
        （2026-09-16 实测就是它把这次修改拦下来的）。
        """
        for s in SAMPLES:
            with self.subTest(sample=s):
                box = self.m.measure(s, "次要说明 secondary detail")
                budget = box.width - 2 * self.m.PADDING_X
                for line in box.lines:
                    self.assertLessEqual(
                        self.m.weighted_units(line) * self.m.FONT_NODE,
                        budget + 1e-6,
                        f"标题行比容器宽 —— 耦合被破坏了：{s!r}",
                    )
                for line in box.detail_lines:
                    self.assertLessEqual(
                        self.m.weighted_units(line) * self.m.FONT_DETAIL,
                        budget + 1e-6,
                        f"说明行比容器宽（说明是 12px，要用它自己的字号量）：{s!r}",
                    )

    def test_detail_uses_the_full_container_width(self):
        """说明行数必须**少于**按旧规矩断出来的行数。

        旧行为：说明按**标题的单位数**断行 → 12px 的列只有 16px 列宽度的 75%，
        于是框里出现一条窄列、一直换行，长标识符被拦腰截断。
        用户截图里的 `LUX_VLM_TASK_MAX_RETR…` 就是这样被切掉的。
        （不拿"最宽行是否顶满预算"当断言：贪心断行本来就不会顶满。）
        """
        label = "任务级 max_attempts"
        detail = ("确定性失败（插件未注册 / 节点不存在）直接终态；"
                  "LUX_VLM_TASK_MAX_RETRIES 关掉重试")
        box = self.m.measure(label, detail)
        # 旧规矩 = 档位只看标题，说明按标题的单位数断行（12px 只画出 16px 的 75%）
        old_cap = self.m.size_class_for(self.m.weighted_units(label))[1]
        old_lines, _ = self.m.wrap(detail, old_cap)
        self.assertLess(len(box.detail_lines), len(old_lines),
                        "说明没有利用上容器宽度（说明列又被字号比卡窄了）")
        self.assertTrue(
            any("LUX_VLM_TASK_MAX_RETRIES" in l for l in box.detail_lines),
            "长标识符不该被拦腰截断：断行宽度要么放得下它，要么在它前面断",
        )

    def test_a_long_detail_widens_the_box(self):
        """说明长得多的节点要被撑宽，而不是在窄条里一直断行。

        用户原话："如果一个框中文本较多，直接将框设置的稍微宽一些，
        不要一直换行换行的"。旧规矩只拿标题定档位，说明再长也不撑宽容器。
        """
        short = self.m.measure("订单服务", "可重试")
        long = self.m.measure("订单服务", "重试策略最多三次，超了进死信队列并通知值班，"
                                          "人工核对之后再重放，不允许自动重放")
        self.assertGreater(long.width, short.width,
                           "说明长了一倍，框却一样宽 —— 又回到「一直换行」那版了")
        self.assertLessEqual(len(long.detail_lines), 2,
                             "撑宽的目的就是让说明别断成好几行")

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
        """拉丁词只在空格处断，词内不断。

        max_units 取得比 "alpha beta" 窄、比 "alpha" 宽 —— **不靠浮点凑巧**。
        这条以前用的是 5.6，而 "alpha beta" 在旧权重下恰好是 5.6000000000000005，
        是靠浮点误差才断开的；换个权重就变成 "alpha beta" / "gamma"。
        """
        lines, forced = self.m.wrap("alpha beta gamma", 4.0)
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
