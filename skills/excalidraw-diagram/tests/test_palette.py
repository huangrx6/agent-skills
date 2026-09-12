#!/usr/bin/env python3
"""palette.py 的回归测试。

## 这套测试守的是什么

**不是"六个颜色彼此分得开"** —— 那正是被换掉的旧模型。旧模型逼着色板制造六种颜色，
实测六种填充色相跨度 310°（占整个色环 86%），一张 14 节点的架构图出现 9 种颜色。
工程上干净，视觉上一定丑。

现在守的是**视觉负担**：

| 约束 | 为什么 |
| --- | --- |
| 文字 vs 自己的填充 ≥ 4.5 | 读得清（WCAG AA） |
| 描边 vs 填充 / 画布 ≥ 1.5 | 边界看得见 |
| neutral / tint / accent / secondary / critical **五档互不相同** | 层级要真的分得出来，否则这一层白设 |
| accent vs neutral、critical vs accent 明显可分 | 这两对是"有信息量"的对比 |
| **一张图里 accent 及以上的节点 ≤ 一半** | 颜色多了就没有信息量 —— 这条才是"好看"的机械代理 |

最后一条是这套测试里唯一一条**关于图、而不是关于色板**的约束。它的存在理由：
色板好看不等于图好看 —— 一张每个框都是主色的图，再好的色板也救不回来。

## 先证明尺子准

`TestRulers` 用已知值钉住对比度 / ΔE 的实现（白对黑 = 21、同色 = 0、同明度不同色相
ΔE 要够大）。尺子本身错的话，上面所有断言都是假的 —— 这个项目里"尺子自己错了"
已经出现过好几次，最近一次是把 HSV 写成 HSL。

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

TEXT_MIN = 4.5              # 正文对比度（WCAG AA）
STROKE_MIN = 1.5            # 描边只要"看得见边界"，不要求它自己成为焦点
VISIBLE_DE = 5.0            # 感知可辨阈值 ΔE≈2.3，这里留两倍余量
# 颜色是**稀缺资源**：主色是视觉焦点，不是默认节点样式。
# 50% 太宽 —— 一半节点带主色，整张图依然会花。这两个数不是设计铁律，
# 是"多到什么时候就没有信息量了"的经验线；真要动它，得先有一张被它误伤的图。
ACCENT_SHARE_MAX = 0.30     # accent + secondary 的占比上限
CRITICAL_SHARE_MAX = 0.05   # critical 的占比上限（警示色一旦常见就不再是警示）
# 但小图上这个比例没有意义：8 个节点的 5% 等于"一个都不许有"，而"一条异常路径"
# 本来就该被标出来。所以按**绝对数量**兜底：至少允许一处。
# 这不是放宽，是比例在样本很小时会失效 —— 图大起来仍然按 5% 收紧。
CRITICAL_COUNT_MIN = 1


def _luminance(colour: str) -> float:
    return P.relative_luminance(colour)


def _specs():
    for name in sorted(os.listdir(SPECS)):
        if name.endswith(".json"):
            with open(os.path.join(SPECS, name), encoding="utf-8") as fh:
                yield name, json.load(fh)


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

    def test_delta_e_separates_same_lightness_different_hue(self):
        self.assertGreater(delta_e("#D8E6F2", "#F2DFD8"), VISIBLE_DE)

    def test_saturation_is_hsv_not_hsl(self):
        """HSV 下纯红的饱和度是 1.0；HSL 下也是 1.0，但中间值会不同。

        这条是防止"顺手改成 HSL" —— 搬家的那次真发生过，三个用例变红才挡住。
        """
        self.assertAlmostEqual(1.0, saturation("#FF0000"), places=3)
        # #808080 无彩：两种模型都给 0
        self.assertAlmostEqual(0.0, saturation("#808080"), places=3)
        # #C08080：HSV = (192-128)/192 ≈ 0.333；HSL = (192-128)/(192+128) = 0.2
        self.assertAlmostEqual(0.3333, saturation("#C08080"), places=3)

    def test_bad_hex_is_rejected(self):
        with self.assertRaises(ValueError):
            P.hex_to_rgb("not-a-colour")


class TestContrast(unittest.TestCase):
    """硬约束：读得清、边界看得见。遍历**层级**，不是语义角色 —— 颜色住在层级里。"""

    def test_level_table_is_complete(self):
        self.assertEqual(set(P.LEVELS), set(P.VISUAL_LEVELS))
        for name, entry in P.LEVELS.items():
            self.assertEqual({"stroke", "fill"}, set(entry), f"{name} 字段不对")

    def test_text_on_every_level_fill(self):
        for level, entry in P.LEVELS.items():
            with self.subTest(level=level):
                ratio = contrast(P.CANVAS["text"], entry["fill"])
                self.assertGreaterEqual(ratio, TEXT_MIN,
                                        f"{level} 上文字对比度只有 {ratio:.2f}")

    def test_text_on_canvas(self):
        ratio = contrast(P.CANVAS["text"], P.CANVAS["background"])
        self.assertGreaterEqual(ratio, TEXT_MIN)

    def test_stroke_against_its_own_fill(self):
        for level, entry in P.LEVELS.items():
            with self.subTest(level=level):
                ratio = contrast(entry["stroke"], entry["fill"])
                self.assertGreaterEqual(ratio, STROKE_MIN,
                                        f"{level} 的描边与自己的填充只有 {ratio:.2f}")

    def test_stroke_against_canvas(self):
        for level, entry in P.LEVELS.items():
            with self.subTest(level=level):
                ratio = contrast(entry["stroke"], P.CANVAS["background"])
                self.assertGreaterEqual(ratio, STROKE_MIN)

    def test_edge_colours_against_canvas(self):
        for kind, entry in P.EDGE_KINDS.items():
            with self.subTest(edge=kind):
                ratio = contrast(entry["stroke"], P.CANVAS["background"])
                self.assertGreaterEqual(ratio, STROKE_MIN)

    def test_level_fills_stand_out_from_canvas(self):
        """**accent 及以上**要真的成块。

        neutral / tint 刻意接近画布 —— 它们是"背景里的普通节点"，不要求跳出来。
        第一版这里把 tint 也要求了，是我写错：tint 的定义就是"非常轻微的色彩倾向"。
        """
        for level, entry in P.LEVELS.items():
            if level in ("neutral", "tint"):
                continue
            with self.subTest(level=level):
                d = delta_e(entry["fill"], P.CANVAS["background"])
                self.assertGreaterEqual(d, VISIBLE_DE, f"{level} 与画布 ΔE 只有 {d:.1f}")


class TestVisualBurden(unittest.TestCase):
    """这一组守的是**视觉负担**，不是色彩数量。

    旧模型要求"六个语义色的填充两两 ΔE ≥ 5" —— 那条约束会**逼着**色板制造六种颜色，
    和"舒服、大气"直接冲突。"六种颜色必须能区分" ≠ "六种颜色都应该被用户看到"。
    """

    def test_levels_are_distinguishable_from_each_other(self):
        """五档层级必须真的分得出来 —— 这是新的可区分性要求，对象是层级不是语义。"""
        names = list(P.VISUAL_LEVELS)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                with self.subTest(pair=(a, b)):
                    # critical 看描边（它的填充刻意很淡，是洗染不是色块）
                    key = "stroke" if "critical" in (a, b) else "fill"
                    d = delta_e(P.LEVELS[a][key], P.LEVELS[b][key])
                    self.assertGreaterEqual(d, VISIBLE_DE,
                                            f"{a} 与 {b} 的{key} ΔE 只有 {d:.1f}")

    def test_accent_stands_out_from_neutral(self):
        """accent 是"重要的东西"，它必须从大量中性节点里跳出来。"""
        for a, b in (("accent", "neutral"), ("accent", "tint"), ("critical", "accent")):
            with self.subTest(pair=(a, b)):
                d = delta_e(P.LEVELS[a]["fill"], P.LEVELS[b]["fill"])
                self.assertGreaterEqual(d, VISIBLE_DE)

    def test_accent_and_critical_strokes_differ(self):
        """警示色不能和主色撞 —— 撞了就分不出"重点"和"异常"。"""
        d = delta_e(P.LEVELS["critical"]["stroke"], P.LEVELS["accent"]["stroke"])
        self.assertGreaterEqual(d, VISIBLE_DE)

    def test_critical_is_visible_against_the_quiet_levels(self):
        """critical 靠**描边**从普通节点里跳出来。

        为什么不对填充提同样要求：浅色主题下 critical 的填充本来就只是一层极浅的
        洗染（和 tint 的填充很近），这是有意的 —— 一整块大色块正是要避免的东西。
        真正"看得见它"的是描边色加上更粗的线宽。
        """
        for quiet in ("neutral", "tint"):
            with self.subTest(against=quiet):
                d = delta_e(P.LEVELS["critical"]["stroke"], P.LEVELS[quiet]["stroke"])
                self.assertGreaterEqual(d, VISIBLE_DE, f"与 {quiet} 的描边 ΔE 只有 {d:.1f}")

    def test_most_nodes_are_not_accented(self):
        """**关于图、而不是关于色板的那条约束**：一张图里 accent 及以上的节点 ≤ 一半。

        色板好看不等于图好看。一张每个框都是主色的图，再好的色板也救不回来 ——
        而这条只有量实际规格才能发现。
        """
        offenders = []
        for name, spec in _specs():
            nodes = spec.get("nodes", [])
            if not nodes:
                continue
            hot = crit = 0
            for node in nodes:
                level = P.level_for(node["kind"], node.get("emphasis", P.DEFAULT_EMPHASIS))
                hot += P.VISUAL_LEVELS.index(level) >= P.VISUAL_LEVELS.index("accent")
                crit += level == "critical"
            if hot / len(nodes) > ACCENT_SHARE_MAX:
                offenders.append(f"{name}: 主色 {hot}/{len(nodes)} = {hot/len(nodes):.0%}")
            allowed_crit = max(CRITICAL_COUNT_MIN, CRITICAL_SHARE_MAX * len(nodes))
            if crit > allowed_crit:
                offenders.append(f"{name}: 警示 {crit}/{len(nodes)} = {crit/len(nodes):.0%}"
                                 f"（上限 {allowed_crit:.0f} 处）")
        self.assertEqual(
            [], offenders,
            "这些图的强调色占比超过一半，颜色就没有信息量了：" + "；".join(offenders))


class TestLevelDerivation(unittest.TestCase):
    """kind → 层级 → 颜色 这条派生链。语义不直接决定颜色。"""

    def test_kind_maps_to_a_level_not_a_colour(self):
        for kind, level in P.KINDS.items():
            with self.subTest(kind=kind):
                self.assertIn(level, P.VISUAL_LEVELS, f"{kind} 指向未知层级 {level!r}")

    def test_level_count_is_capped(self):
        """真正要封顶的是**层级数**（颜色数），不是角色数 —— 颜色数量 ≠ 语义数量。"""
        self.assertLessEqual(len(P.VISUAL_LEVELS), 5)

    def test_most_kinds_are_not_accented(self):
        """色板的默认值本身就不能"六种颜色" —— 大多数角色落在 neutral / tint。"""
        hot = {k for k, level in P.KINDS.items()
               if P.VISUAL_LEVELS.index(level) >= P.VISUAL_LEVELS.index("accent")}
        self.assertLessEqual(len(hot), 2, f"默认就带强调色的角色太多了：{sorted(hot)}")

    def test_default_emphasis_is_the_level_itself(self):
        for kind in P.KINDS:
            with self.subTest(kind=kind):
                self.assertEqual(P.LEVELS[P.KINDS[kind]]["fill"], P.fill_for(kind))

    def test_primary_promotes_and_muted_demotes(self):
        promoted = P.level_for("client", "primary")      # tint → accent
        demoted = P.level_for("service", "muted")        # accent → tint
        self.assertEqual("accent", promoted)
        self.assertEqual("tint", demoted)

    def test_promotion_never_reaches_critical(self):
        """普通节点被"强调"不该变成警示色 —— critical 只能显式指定。"""
        for kind in P.KINDS:
            for emphasis in ("primary", "normal", "muted"):
                with self.subTest(kind=kind, emphasis=emphasis):
                    self.assertNotEqual("critical", P.level_for(kind, emphasis))

    def test_critical_is_reachable_only_by_asking_for_it(self):
        self.assertEqual("critical", P.level_for("service", "critical"))
        self.assertEqual("critical", P.level_for("external", "critical"))

    def test_promotion_is_capped_at_secondary(self):
        """顶到头也不会溢出枚举 —— 提级要 clamp，不是 IndexError。"""
        for kind in P.KINDS:
            with self.subTest(kind=kind):
                self.assertIn(P.level_for(kind, "primary"), P.VISUAL_LEVELS)

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
                with self.assertRaises(KeyError):
                    P.emphasis_stroke_width(bad)

    def test_emphasis_strength_is_ordered(self):
        widths = [P.emphasis_stroke_width(e) for e in ("muted", "normal", "primary")]
        self.assertEqual(sorted(widths), widths, "描边粗细的顺序反了（muted 应最细）")


class TestThemes(unittest.TestCase):
    """每个主题都要独立满足上面的硬约束，而且要真的互不相同。"""

    def test_every_theme_keeps_text_readable(self):
        for theme in P.available_themes():
            with P.theme_context(theme):
                for level, entry in P.LEVELS.items():
                    with self.subTest(theme=theme, level=level):
                        got = contrast(P.CANVAS["text"], entry["fill"])
                        self.assertGreaterEqual(got, TEXT_MIN)

    def test_every_theme_keeps_strokes_visible(self):
        for theme in P.available_themes():
            with P.theme_context(theme):
                for level, entry in P.LEVELS.items():
                    with self.subTest(theme=theme, level=level):
                        own = contrast(entry["stroke"], entry["fill"])
                        canvas = contrast(entry["stroke"], P.CANVAS["background"])
                        self.assertGreaterEqual(min(own, canvas), STROKE_MIN)

    def test_every_theme_has_distinguishable_levels(self):
        """深色主题翻过车：第一版五档挤在窄明度带里，看着就是几块差不多的深灰。"""
        for theme in P.available_themes():
            with P.theme_context(theme):
                names = list(P.VISUAL_LEVELS)
                for i, a in enumerate(names):
                    for b in names[i + 1:]:
                        with self.subTest(theme=theme, pair=(a, b)):
                            d = delta_e(P.LEVELS[a]["fill"], P.LEVELS[b]["fill"])
                            self.assertGreaterEqual(d, VISIBLE_DE)

    def test_unknown_theme_raises_and_lists_options(self):
        with self.assertRaises(KeyError) as ctx:
            P.use_theme("不存在的主题")
        self.assertIn("soft-light", str(ctx.exception))

    def test_theme_context_restores_the_previous_one(self):
        before = P.active_theme()
        with P.theme_context("dark"):
            self.assertEqual("dark", P.active_theme())
        self.assertEqual(before, P.active_theme())

    def test_suggestion_table_only_names_real_diagram_types(self):
        """这张表曾经把图类型全抄了一遍 —— 于是同一个漂移又发生一次：
        `component` / `sequence` 早就不是合法类型了，表里还留着。

        类型清单的唯一来源是 `layout.DIRECTION_FOR_TYPE`。
        """
        layout = _load("layout_for_palette_test", "layout.py")
        for name in P.THEME_SUGGESTION:
            with self.subTest(diagram_type=name):
                self.assertIn(name, layout.DIRECTION_FOR_TYPE)

    def test_themes_are_actually_different_from_each_other(self):
        seen = {}
        for theme in P.available_themes():
            with P.theme_context(theme):
                seen[theme] = tuple(sorted(e["fill"] for e in P.LEVELS.values()))
        self.assertEqual(len(seen), len(set(seen.values())), "有两个主题的层级色完全一样")


if __name__ == "__main__":
    unittest.main()

class TestDocsDoNotRestateColours(unittest.TestCase):
    """文档里**一个十六进制色值都不许出现**。

    颜色只有一处定义（`THEMES`），复述一次就会漂移一次 —— 这不是假设，是发生过的：
    换掉六色硬编码模型之后，`diagram-spec.md` 里那张 kind→HEX 的表还留了两个版本，
    直到有人 grep 才被发现。而且**只 grep 旧名字是不够的**：那一整节描述的是旧模型，
    却一次都没提"莫兰迪"三个字。

    所以这里用**机械**的方式守住：文档只管讲原则，具体色值去代码里读。
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
                         "文档里出现了写死的色值，颜色只有一处定义：" + "；".join(offenders))

