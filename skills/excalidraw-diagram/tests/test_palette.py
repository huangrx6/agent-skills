#!/usr/bin/env python3
"""palette.py 的回归测试 —— 视觉方向 × 自适应颜色系统。

## 这套测试守的是什么

不是"几个颜色彼此分得开"，而是**四条设计约束**：

| 约束 | 为什么 |
| --- | --- |
| 文字 vs 填充 ≥ 4.5、描边 vs 填充 / 画布 ≥ 1.5 | 读得清、边界看得见（硬约束） |
| 四档层级两两可分、accent 与 neutral 明显可分 | 层级要真的分得出来，否则白设 |
| **一张图里 accent ≤ 10%、critical ≤ 5%** | 颜色是稀缺资源 —— 主色是焦点，不是默认节点样式 |
| **没有方向的主色可以落在灰蓝企业风里** | 这是被明确否掉的结果，见 `FORBIDDEN_*` |

最后一条是这套测试里唯一一条**编码了审美判断**的：它把"禁止灰蓝成为默认答案"
写成了一个能算的判据。灰蓝的特征不是"蓝"，而是**低饱和的蓝** —— 所以判据是
"色相在蓝区 且 饱和度偏低"。

## 先证明尺子准

`TestRulers` 用已知值钉住对比度 / ΔE / 饱和度 / 色相的实现。尺子错的话，
上面所有断言都是假的 —— 这个项目里"尺子自己错"已经出现过好几次，
最近一次是把 HSV 写成 HSL。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/test_palette.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
SPECS = os.path.join(HERE, "fixtures", "specs")


def _load(name: str, filename: str):
    path = os.path.join(SCRIPTS, filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


P = _load("palette_under_test", "palette.py")

contrast = P.contrast
delta_e = P.delta_e
saturation = P.saturation

TEXT_MIN = 4.5
STROKE_MIN = 1.5
VISIBLE_DE = 5.0
TINT_STEP_DE = 3.0    # 最轻的一档差：在感知阈值之上，但明显克制
ACCENT_SHARE_MAX = 0.10      # §9：accent 0~10%
CRITICAL_SHARE_MAX = 0.05    # §9：critical 0~5%
CRITICAL_COUNT_MIN = 1       # 小图上按比例算等于"一个都不许有"，而一条异常路径本就该标出来

# §20「禁止灰蓝成为默认答案」。用户点名的那类：白底 + 灰字 + 灰蓝节点 + 蓝灰线。
# 灰蓝的特征不是"蓝"，是**低饱和的蓝** —— 所以两条一起判。
FORBIDDEN_HUE = (195.0, 220.0)
FORBIDDEN_SAT_MAX = 0.35


def _specs():
    for name in sorted(os.listdir(SPECS)):
        if name.endswith(".json"):
            with open(os.path.join(SPECS, name), encoding="utf-8") as fh:
                yield name, json.load(fh)


def _all_seeds():
    for direction, spec in P.VISUAL_DIRECTIONS.items():
        for seed in spec["seeds"]:
            yield direction, seed


class TestRulers(unittest.TestCase):
    """先证明尺子准 —— 尺子错的话，下面所有断言都是假的。"""

    def test_white_on_black_is_21(self):
        self.assertAlmostEqual(21.0, contrast("#000000", "#FFFFFF"), places=1)

    def test_same_colour_contrast_is_one(self):
        self.assertAlmostEqual(1.0, contrast("#7C93A6", "#7C93A6"), places=3)

    def test_identical_colour_has_zero_delta_e(self):
        self.assertAlmostEqual(0.0, delta_e("#7C93A6", "#7C93A6"), places=6)

    def test_black_white_delta_e_is_large(self):
        self.assertGreater(delta_e("#000000", "#FFFFFF"), 90)

    def test_saturation_is_hsv_not_hsl(self):
        """HSV 下 #C08080 是 0.333；HSL 下是 0.2。搬家那次真把它写成过 HSL。"""
        self.assertAlmostEqual(1.0, saturation("#FF0000"), places=3)
        self.assertAlmostEqual(0.0, saturation("#808080"), places=3)
        self.assertAlmostEqual(0.3333, saturation("#C08080"), places=3)

    def test_hue_is_meaningless_without_saturation(self):
        """近无彩色的色相是噪声 —— 拿它比"色相跨度"会得出荒谬结论（踩过）。"""
        self.assertLess(saturation("#FDFCFA"), 0.05)
        self.assertAlmostEqual(0.0, saturation("#FFFFFF"), places=6)

    def test_bad_hex_is_rejected(self):
        for bad in ("not-a-colour", "#12345", "#GGGGGG"):
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    P.hex_to_rgb(bad)


class TestContrast(unittest.TestCase):
    """硬约束，对**每一个方向 × 每一个 seed** 都要成立。"""

    def test_theme_tables_are_complete(self):
        for direction, seed in _all_seeds():
            with P.direction_context(direction, seed):
                with self.subTest(direction=direction, seed=seed):
                    self.assertEqual(set(P.LEVELS), set(P.VISUAL_LEVELS))
                    for level, entry in P.LEVELS.items():
                        self.assertEqual({"stroke", "fill"}, set(entry), level)

    def test_text_readable_on_every_level_fill(self):
        for direction, seed in _all_seeds():
            with P.direction_context(direction, seed):
                for level, entry in P.LEVELS.items():
                    with self.subTest(direction=direction, seed=seed, level=level):
                        got = contrast(P.CANVAS["text"], entry["fill"])
                        self.assertGreaterEqual(got, TEXT_MIN, f"文字对比度 {got:.2f}")

    def test_strokes_visible(self):
        for direction, seed in _all_seeds():
            with P.direction_context(direction, seed):
                for level, entry in P.LEVELS.items():
                    with self.subTest(direction=direction, seed=seed, level=level):
                        own = contrast(entry["stroke"], entry["fill"])
                        canvas = contrast(entry["stroke"], P.CANVAS["background"])
                        self.assertGreaterEqual(min(own, canvas), STROKE_MIN)

    def test_edge_colours_visible(self):
        for direction, seed in _all_seeds():
            with P.direction_context(direction, seed):
                for kind, entry in P.EDGE_KINDS.items():
                    with self.subTest(direction=direction, seed=seed, edge=kind):
                        got = contrast(entry["stroke"], P.CANVAS["background"])
                        self.assertGreaterEqual(got, STROKE_MIN)


class TestLevelsAreDistinguishable(unittest.TestCase):

    def test_four_levels_are_pairwise_distinct(self):
        for direction, seed in _all_seeds():
            with P.direction_context(direction, seed):
                names = list(P.VISUAL_LEVELS)
                for i, a in enumerate(names):
                    for b in names[i + 1:]:
                        with self.subTest(direction=direction, seed=seed, pair=(a, b)):
                            key = "stroke" if "critical" in (a, b) else "fill"
                            got = delta_e(P.LEVELS[a][key], P.LEVELS[b][key])
                            # neutral ↔ tint 是**刻意最轻**的一档差（§5：tint 与画布的差
                            # 要非常克制）。用 5.0 卡它就等于要求 tint 去抢注意力 ——
                            # 那正是要避免的。它只要在感知阈值（≈2.3）之上分得出来就够了。
                            floor = TINT_STEP_DE if {a, b} == {"neutral", "tint"} else VISIBLE_DE
                            self.assertGreaterEqual(got, floor,
                                                    f"{a}/{b} 的{key} ΔE {got:.1f}")

    def test_accent_is_clearly_not_neutral(self):
        """accent 是"真正重要的东西"，必须从大量中性节点里跳出来。"""
        for direction, seed in _all_seeds():
            with P.direction_context(direction, seed):
                with self.subTest(direction=direction, seed=seed):
                    got = delta_e(P.LEVELS["accent"]["fill"],
                                  P.LEVELS["neutral"]["fill"])
                    self.assertGreaterEqual(got, VISIBLE_DE)

    def test_tint_stays_close_to_canvas(self):
        """§5：tint 与画布的差**非常克制** —— 它不是"比 neutral 深一点的灰色"。

        所以这里断言的是**上界**：差得太大就说明 tint 又在抢注意力了。
        """
        for direction, seed in _all_seeds():
            with P.direction_context(direction, seed):
                with self.subTest(direction=direction, seed=seed):
                    got = delta_e(P.LEVELS["tint"]["fill"],
                                  P.CANVAS["background"])
                    self.assertLess(got, 12.0, f"tint 与画布差得太多（ΔE {got:.1f}）")


class TestNoGreyBlueDefault(unittest.TestCase):
    """§20 —— 把"禁止灰蓝成为默认答案"写成能算的判据。

    否掉的那一套是：白底 + 灰字 + **灰蓝**节点 + 蓝灰线。灰蓝的特征不是"蓝"，
    是**低饱和的蓝** —— 所以两条一起判：色相落在蓝区，且饱和度偏低。
    用户点名的是 `#6E879B` / `#7F96A5` / `#AAB8C0` 这一路。
    """

    def test_no_direction_accent_is_greyblue(self):
        offenders = []
        for direction, seed in _all_seeds():
            with P.direction_context(direction, seed):
                accent = P.ROLES["accent"]
                h, s = P.hue(accent), saturation(accent)
                if FORBIDDEN_HUE[0] <= h <= FORBIDDEN_HUE[1] and s < FORBIDDEN_SAT_MAX:
                    offenders.append(f"{direction}/{seed}: {accent} 色相 {h:.0f}° 饱和 {s:.2f}")
        self.assertEqual([], offenders,
                         "这些主色的色相落在蓝区且饱和偏低：" + "；".join(offenders))

    def test_the_ruler_actually_catches_the_named_colours(self):
        """先证明这条判据真的能抓住用户点名的那几个色值，否则它是空话。"""
        for colour in ("#6E879B", "#7F96A5", "#AAB8C0"):
            with self.subTest(colour=colour):
                h, s = P.hue(colour), saturation(colour)
                self.assertGreaterEqual(s, 0.0)
                self.assertLess(s, FORBIDDEN_SAT_MAX, f"{colour} 饱和 {s:.2f} 应被判为灰蓝")
                self.assertTrue(FORBIDDEN_HUE[0] <= h <= FORBIDDEN_HUE[1],
                                f"{colour} 色相 {h:.0f}° 应落在蓝区")


class TestKindDoesNotDecideColour(unittest.TestCase):
    """§7：Kind 与颜色彻底解耦。**没有角色默认拿到 accent。**"""

    def test_no_kind_defaults_to_accent(self):
        hot = {k for k, level in P.KINDS.items() if level != "neutral"}
        self.assertEqual(set(), hot, f"这些角色默认不是中性：{sorted(hot)}")

    def test_accent_only_arrives_through_emphasis(self):
        for kind in P.KINDS:
            with self.subTest(kind=kind):
                self.assertEqual("neutral", P.level_for(kind, "normal"))
                self.assertEqual("neutral", P.level_for(kind, "muted"))
                self.assertEqual("accent", P.level_for(kind, "primary"))
                self.assertEqual("critical", P.level_for(kind, "critical"))

    def test_unknown_kind_raises_never_falls_back(self):
        for bad in ("queue", "", "Service"):
            with self.subTest(kind=bad):
                with self.assertRaises(KeyError):
                    P.fill_for(bad)

    def test_unknown_emphasis_raises_never_falls_back(self):
        for bad in ("important", "", "PRIMARY"):
            with self.subTest(emphasis=bad):
                with self.assertRaises(KeyError):
                    P.fill_for("service", bad)

    def test_emphasis_strength_is_ordered(self):
        widths = [P.emphasis_stroke_width(e) for e in ("muted", "normal", "primary")]
        self.assertEqual(sorted(widths), widths, "描边粗细顺序反了")
        scales = [P.emphasis_scale(e) for e in ("muted", "normal", "primary")]
        self.assertEqual(sorted(scales), scales, "尺寸倍数顺序反了")

    def test_size_hierarchy_is_subtle(self):
        """§13：要的是层次，不是海报式跳跃。"""
        for emphasis, entry in P.EMPHASIS.items():
            with self.subTest(emphasis=emphasis):
                self.assertGreaterEqual(entry["scale"], 0.90)
                self.assertLessEqual(entry["scale"], 1.10)


class TestDirectionsComeFromOnePlace(unittest.TestCase):

    def test_direction_names_are_the_documented_five(self):
        self.assertEqual(
            ["botanical", "coastal", "editorial", "fresh", "night"],
            P.available_directions())

    def test_each_direction_has_character_and_seeds(self):
        for direction, spec in P.VISUAL_DIRECTIONS.items():
            with self.subTest(direction=direction):
                self.assertIn("zh", spec)
                self.assertIn("character", spec)
                self.assertTrue(spec["seeds"], f"{direction} 没有 seed")
                for name, seed in spec["seeds"].items():
                    self.assertEqual({"canvas", "ink", "accent", "critical"},
                                     set(seed), f"{direction}/{name} 字段不对")

    def test_character_words_are_from_a_closed_set(self):
        """Character 是**给模型读的** —— 它得能照着判断选哪个方向。
        所以取值要收敛，不能变成自由文本。"""
        allowed = {
            "temperature": {"warm", "neutral-warm", "bright", "cool", "warm-dark"},
            "density": {"sparse", "medium", "dense"},
            "contrast": {"moderate", "high"},
        }
        for direction, spec in P.VISUAL_DIRECTIONS.items():
            for key, options in allowed.items():
                with self.subTest(direction=direction, key=key):
                    self.assertIn(spec["character"][key], options)

    def test_old_theme_names_are_rejected_not_remapped(self):
        """旧名判失败，**不做静默映射** —— 那些名字代表的是被否掉的灰蓝风，
        映射过来只会让人以为改动没生效。"""
        for old in ("soft-light", "clean-light", "dark", "morandi", "bright-clean"):
            with self.subTest(old=old):
                with self.assertRaises(KeyError) as ctx:
                    P.use_direction(old)
                self.assertIn("未知视觉方向", str(ctx.exception))

    def test_unknown_direction_lists_options(self):
        with self.assertRaises(KeyError) as ctx:
            P.use_direction("不存在的方向")
        self.assertIn("botanical", str(ctx.exception))

    def test_direction_context_restores_the_previous_one(self):
        before = P.active_direction()
        with P.direction_context("night"):
            self.assertEqual("night", P.active_direction())
        self.assertEqual(before, P.active_direction())

    def test_auto_resolves_by_type(self):
        for diagram_type, expected in (("flow", "fresh"), ("network", "coastal"),
                                       ("architecture", "botanical"),
                                       ("mindmap", "botanical")):
            with self.subTest(diagram_type=diagram_type):
                self.assertEqual(expected, P.resolve_direction("auto", diagram_type))

    def test_user_mood_beats_diagram_type(self):
        """§19：用户说了风格意图，就不该被图类型压过去。"""
        self.assertEqual("fresh", P.resolve_direction("auto", "architecture", "画得有点春天的气息"))
        self.assertEqual("night", P.resolve_direction("auto", "flow", "深色一点的"))


class TestVisualBurden(unittest.TestCase):
    """颜色是**稀缺资源**（§9）。这一组是唯一一类**关于图、而不是关于色板**的约束。"""

    def test_colour_budget_per_level(self):
        """§9 的 band 是**每一档各自**的：accent 0~10%、critical 0~5%，
        而 tint 5~20% 是另一档（它不属于强调预算）。

        §9 自己也说了这是软约束。所以只卡有意义的两条：强调色和警示色的上限，
        并且对小图按绝对数量兜底 —— 14 个节点的 10% 是 1.4，8 个节点的 5% 是 0.4，
        按纯比例算等于"一个都不许有"，而枢纽和异常路径本来就该被标出来。
        """
        offenders = []
        for name, spec in _specs():
            nodes = spec.get("nodes", [])
            if not nodes:
                continue
            tally = {}
            for node in nodes:
                level = P.level_for(node["kind"], node.get("emphasis", P.DEFAULT_EMPHASIS))
                tally[level] = tally.get(level, 0) + 1
            total = len(nodes)
            accents = tally.get("accent", 0)
            critical = tally.get("critical", 0)
            if accents > max(1, ACCENT_SHARE_MAX * total):
                offenders.append(f"{name}: accent {accents}/{total} = {accents/total:.0%}")
            if critical > max(CRITICAL_COUNT_MIN, CRITICAL_SHARE_MAX * total):
                offenders.append(f"{name}: critical {critical}/{total}")
        self.assertEqual([], offenders, "颜色密度超标：" + "；".join(offenders))

    def test_edges_do_not_compete_with_nodes(self):
        """§10：边退出颜色竞争 —— 它们只能用 edge / edge-muted / accent 三种角色。"""
        for kind, entry in P.EDGE_KINDS.items():
            with self.subTest(edge=kind):
                self.assertIn(entry["stroke"], P.ROLES.values())


class TestDocsDoNotRestateColours(unittest.TestCase):
    """文档里**一个十六进制色值都不许出现**。

    颜色只有一处定义，复述一次就会漂移一次 —— 这不是假设：换掉六色硬编码之后，
    `diagram-spec.md` 里那张 kind→HEX 的表还留了两个版本，而且那一整节描述的是旧模型，
    却一次都没提"莫兰迪"三个字 —— **只 grep 旧名字是查不出来的**。
    """

    def test_no_hex_colours_in_docs(self):
        root = os.path.dirname(HERE)
        offenders = []
        pattern = re.compile(r"#[0-9A-Fa-f]{6}\b")
        for base in (os.path.join(root, "references"), root):
            for name in sorted(os.listdir(base)):
                if not name.endswith(".md"):
                    continue
                path = os.path.join(base, name)
                for number, line in enumerate(
                        open(path, encoding="utf-8").read().split("\n"), 1):
                    for match in pattern.findall(line):
                        offenders.append(f"{name}:{number} {match}")
        self.assertEqual([], offenders,
                         "文档里出现了写死的色值：" + "；".join(offenders))


if __name__ == "__main__":
    unittest.main()
