#!/usr/bin/env python3
"""风格层工具（style.py）与风格契约的验证。

这一层解决的是一个**具体的历史问题**：加风格很便宜（拷一个目录），代价是契约隐式 ——
少一个字号档、少一个 motion 键、色板过不了门槛，渲染器都不会报错；
skin 里 `var(--t-missing)` 只会**静默退回默认字号**，那一页"就是有点怪"，查起来极贵。

所以这里钉两件事：

1. **现有风格全部过契约** —— 而且遍历的是**目录**，不是写死的名单
   （写死名单的代价实测过：加了四套新风格，它们全部逃过了三条检查，而测试是绿的）。
2. **契约检查本身有牙** —— 逐项造违规样例，确认它真的会报。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/deck-authoring/test_style.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")
STYLES = os.path.join(SKILL, "dev-tools", "style-fixture")
DEMO = os.path.join(SKILL, "dev-tools", "demo.spec.json")
STRESS = os.path.join(SKILL, "dev-tools", "stress.spec.json")


def _load(name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, f"{name}.py"))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


deckio = _load("deckio")
render = _load("render")
style = _load("style")

TEST_PREFIX = "zz_test_"


class TestEveryShippedStylePassesTheContract(unittest.TestCase):
    def test_all_styles_pass(self) -> None:
        """八套（或将来更多）全部过契约 —— 遍历目录，新增风格自动进覆盖。"""
        names = style.available()
        # styles/ 内置已删（用户要求）：可用面 = 用户自建 + 开发夹具（swiss-grid）。
        # 不变量是"遍历目录自动进覆盖"，不是具体套数。
        self.assertGreaterEqual(len(names), 1, "一套风格都没有 —— 夹具丢了？")
        for name in names:
            with self.subTest(style=name):
                self.assertEqual(style.audit(name), [], f"{name} 没过契约")

    def test_shipped_styles_are_not_test_fixtures(self) -> None:
        """出货的风格里不该混进测试夹具。"""
        self.assertEqual([n for n in style.available() if n.startswith(TEST_PREFIX)], [])

    def test_summary_renders_for_every_style(self) -> None:
        """摘要对每套都能跑（它读的键比 audit 多 —— 会暴露 audit 没覆盖的缺键）。"""
        for name in style.available():
            with self.subTest(style=name):
                text = style.summarize(name)
                self.assertIn(name, text)
                self.assertIn("色板", text)


class TestContractListStaysInSyncWithTheRenderer(unittest.TestCase):
    """元测试：`REQUIRED_TYPE_TIERS` 不能和渲染器实际用的档位脱钩。

    脱钩的样子：有人在 render.py 里新写一句 `tier["newTier"]`，但忘了加进名单 ——
    于是契约检查对"新风格缺这一档"闭口不言，而生产上它就是一个静默的默认字号。
    """

    def test_required_tiers_cover_what_render_actually_reads(self) -> None:
        used = self._tiers_the_renderer_reads()
        missing = sorted(used - render.REQUIRED_TYPE_TIERS)
        self.assertEqual(missing, [],
                         f"render.py 读这些档位但契约名单里没有：{missing}")

    def test_every_style_provides_the_required_tiers(self) -> None:
        for name in style.available():
            with self.subTest(style=name):
                raw = deckio.read_json(os.path.join(STYLES, name, "style.json"))
                self.assertEqual(sorted(render.REQUIRED_TYPE_TIERS - set(raw["type"])), [])

    @staticmethod
    def _tiers_the_renderer_reads() -> set[str]:
        """渲染器读一个字号档的**所有**途径 —— 漏一条途径，这条元测试就会说假话。

        实测踩过：第一版只数了 `tier["x"]`、TITLE_TIER 的取值、BULLET_TIERS 的取值，
        把 `DEFAULT_TITLE_TIER`（内容是 "small"，直接赋值不是取值）漏了 ——
        于是它把 "small" 报成"没人用"。
        """
        src = open(os.path.join(SCRIPTS, "render.py"), encoding="utf-8").read()
        used = set(re.findall(r'tier\["([a-zA-Z]+)"\]', src))
        used |= set(render.TITLE_TIER.values())          # title/content-text/end 的档
        used.add(render.DEFAULT_BULLET_TIER)             # 条目缺省档（v3：作者声明）
        # 其余条目档由**作者/风格声明**进来（slide.bulletTier / style.titleTiers）——
        # v3 没有按条数自动升降档，但声明值必须在这份契约里（否则 tier[...] KeyError）
        used |= {"bulletLarge", "bulletSmall"}
        used.add(render.DEFAULT_TITLE_TIER)              # 其余版式的档（直接赋值，不是取值）
        return used

    def test_required_tiers_are_not_wishful(self) -> None:
        """反过来：名单里的每一项都要真的被用到 —— 否则它只是把契约撑大了。"""
        # chartValue / chartLabel 由 skin 经 `--t-*` 取，渲染器不直接读 —— 这两个是例外
        skin_only = {"chartValue", "chartLabel"}
        extra = sorted(render.REQUIRED_TYPE_TIERS - self._tiers_the_renderer_reads() - skin_only)
        self.assertEqual(extra, [], f"契约名单里这些没人用：{extra}")


class TestContractCheckHasTeeth(unittest.TestCase):
    """逐项造违规样例 —— 一条不会报错的检查等于没写。"""

    def setUp(self) -> None:
        self.base = deckio.read_json(os.path.join(STYLES, "swiss-grid", "style.json"))

    def _make(self, name: str, mutate) -> str:
        raw = json.loads(json.dumps(self.base))
        mutate(raw)
        d = os.path.join(STYLES, TEST_PREFIX + name)
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d, exist_ok=True)
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        with open(os.path.join(d, "style.json"), "w", encoding="utf-8") as fh:
            json.dump(raw, fh, ensure_ascii=False)
        with open(os.path.join(d, "skin.css"), "w", encoding="utf-8") as fh:
            fh.write("/* 契约测试用的空皮肤 */\n")
        return TEST_PREFIX + name

    def test_missing_type_tier_is_reported(self) -> None:
        name = self._make("notier", lambda raw: raw["type"].pop("caption"))
        problems = style.audit(name)
        self.assertTrue(any("caption" in p for p in problems), problems)

    def test_missing_motion_key_is_reported(self) -> None:
        name = self._make("nomotion", lambda raw: raw["motion"].pop("holdMs"))
        self.assertTrue(any("holdMs" in p for p in style.audit(name)))

    def test_linear_easing_is_reported(self) -> None:
        """匀速缓动是 AI slop 的第一特征 —— 必须报。"""
        name = self._make("linear", lambda raw: raw["motion"].update({"cssEase": "linear"}))
        self.assertTrue(any("linear" in p for p in style.audit(name)))

    def test_unknown_easing_is_reported(self) -> None:
        name = self._make("badease", lambda raw: raw["motion"].update({"easing": "bounce"}))
        self.assertTrue(any("bounce" in p for p in style.audit(name)))

    def test_low_contrast_color_set_is_reported(self) -> None:
        """两墨都亮 → 文字色压不深。这条是色板门禁在风格层的同一条门槛。"""
        def mutate(raw: dict) -> None:
            raw["colorSets"]["bad"] = {"primary": "#FFEE88", "secondary": "#FFF3B0",
                                       "background": "#FFFDF0"}
        name = self._make("lowcontrast", mutate)
        self.assertTrue(any("对比度" in p for p in style.audit(name)))

    def test_missing_top_level_key_is_reported(self) -> None:
        name = self._make("nokey", lambda raw: raw.pop("viewerBackground"))
        self.assertTrue(any("viewerBackground" in p for p in style.audit(name)))

    def test_decor_without_zones_is_reported(self) -> None:
        """声明了装饰类型却没给落点 —— 装饰就没有地方放。"""
        name = self._make("decor", lambda raw: raw["decor"].update(
            {"types": ["halftone-circle"], "kind": "halftone-circle"}))
        self.assertTrue(any("zones" in p for p in style.audit(name)))

    def test_a_good_style_reports_nothing(self) -> None:
        """反面对照：把原样拷一份过去，必须**一条都不报** ——
        否则上面那些"有牙"的用例可能只是"永远会报"。"""
        name = self._make("clean", lambda raw: None)
        self.assertEqual(style.audit(name), [])

    def test_cli_exits_nonzero_when_a_style_is_broken(self) -> None:
        """命令行也要有牙：坏风格在场时退出码必须是 1。"""
        self._make("cli", lambda raw: raw["type"].pop("foot"))
        run = subprocess.run([sys.executable, os.path.join(SCRIPTS, "style.py"), "--check"],
                             capture_output=True, text=True, cwd=SKILL)
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertIn(TEST_PREFIX + "cli", run.stdout + run.stderr)

    def test_broken_style_is_caught_by_the_directory_scan(self) -> None:
        """坏风格不能只在显式点名时被发现 —— 默认列表扫描也要报它。"""
        self._make("scan", lambda raw: raw["type"].pop("subtitle"))
        run = subprocess.run([sys.executable, os.path.join(SCRIPTS, "style.py")],
                             capture_output=True, text=True, cwd=SKILL)
        self.assertEqual(run.returncode, 1)
        self.assertIn(TEST_PREFIX + "scan", run.stdout + run.stderr)


class TestContactSheet(unittest.TestCase):
    """联系表：所有风格 × 同一份 demo → 一张图。

    这是「先出三个方向让人选」那个流程的实物依据 —— 选风格要的是画面，不是对照表。
    只跑两套（每套要开一次 Chrome 截图，全跑一遍 36 秒，不该进测试套件的常规路径）。
    """

    def test_sheet_is_produced_with_a_label_per_style(self) -> None:
        from PIL import Image   # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "sheet.png")
            path = style.sheet(out, styles=["swiss-grid"])
            self.assertTrue(os.path.isfile(path))
            with Image.open(path) as im:
                # 两套 × 两页拼在一起 → 比单页明显宽、明显高
                self.assertGreater(im.width, render.SLIDE_W * 0.4)
                self.assertGreater(im.height, render.SLIDE_H * 0.4)

    def test_url_for_a_page_uses_the_style_color_set(self) -> None:
        """试排/联系表都要用该风格**自己的**第一个色板 —— 拿 swiss 的色板去渲
        billboard 会直接报 KeyError（这坑实测踩过）。"""
        for name in style.available():
            with self.subTest(style=name):
                raw = deckio.read_json(os.path.join(STYLES, name, "style.json"))
                spec = deckio.read_json(DEMO)
                spec["deck"]["style"] = name
                spec["deck"]["colorSet"] = next(iter(raw["colorSets"]))
                html = render.render(spec)          # 会 raise（色板名不认识）
                self.assertIn("</html>", html)

class TestEveryStyleSurvivesTheStressDeck(unittest.TestCase):
    """每套风格都要能在**真实形状**的 deck 上过 check —— 这才是"稳定"的实际含义。

    为什么值得这个代价：图表页那条**结构性溢出**（八套风格全部把图注压进页脚区、
    paper-ink 直接裁掉）就是压测找出来的 —— 而它在此之前躲过了所有测试，
    因为 `demo.spec.json` 里**根本没有图表页**。契约测试只验 token 齐不齐，
    渲染出来长什么样它不知道；而"换个风格就撞车"正是最该被自动拦住的事。

    代价控制：只取**每种版式一页**（8 页）而不是压测的 21 页 —— 这里要验的是
    版式 × 风格，不是内容量。测量开销随页数走，21 页 × 8 套会把套件拖到两分钟以上。

    图片自己造（`plate.sample()`）：`sample-treated.png` 是 gitignore 的产物，
    让测试依赖一个本地才有的文件，等于换台机器就红。
    """

    # 每种版式取一页，且刻意取**最险的形状**：7 条密页、5+5 两栏、6 节点时间线、
    # 6 根柱的图表、带图注的图文页、18 字长标题、收尾页。
    # ⚠️ 这串页号写错过一次：第 21 页是**附录**，第 20 页才是 `end` ——
    # 于是"收尾版式"根本没进压测。下面那条 `test_the_pick_really_covers_every_layout`
    # 就是为这个写的（它会去比 PICK 覆盖的版式集合）。
    PICK = (1, 3, 5, 8, 9, 12, 13, 20)

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        cls.spec = deckio.read_json(STRESS)
        # 造图（相对路径的产物要同目录交付，所以写进临时目录）
        plate = _load("plate")
        plate.sample((640, 400)).save(os.path.join(cls._tmp.name, "sample-treated.png"))

    def test_every_style_renders_cleanly(self) -> None:
        """一次测量两用（check 的毛病 + 图表页的余量）—— 每次测量都要开一次
        Chrome 并截图整份 deck，重复付这个钱不值。"""
        check_mod = _load("check")
        measure_mod = _load("measure")
        for name in style.available():
            with self.subTest(style=name):
                raw = deckio.read_json(os.path.join(STYLES, name, "style.json"))
                spec = json.loads(json.dumps(self.spec))
                spec["deck"]["style"] = name
                spec["deck"]["colorSet"] = next(iter(raw["colorSets"]))
                spec["deck"]["slides"] = [self.spec["deck"]["slides"][i - 1] for i in self.PICK]
                path = os.path.join(self._tmp.name, f"{name}.html")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(render.render(spec))
                measured = measure_mod.measure(path)
                problems = check_mod.check(spec, path, measured=measured)
                self.assertEqual(problems, [], f"{name} 在真实形状的 deck 上没过 check")

                # 图表页那条结构性溢出（图注压进页脚）单独钉死 —— 它是最贵的那次回归。
                # 判据用**内容带底**（页脚之上），不是页边界：压进页脚区就算坏，
                # 因为页脚那一行会被盖住（被裁是更晚的事）。
                chart_no = self.PICK.index(9) + 1        # 6 柱图表在 PICK 里的序号
                box = measure_mod.slide_content_span(measured, chart_no)
                self.assertIsNotNone(box, f"{name} 的图表页量不到内容")
                assert box is not None
                _top, bottom = box
                self.assertLessEqual(
                    bottom, render.CONTENT_BOTTOM,
                    f"{name} 的图表页内容底 {bottom:.0f}px 越过正文带底 "
                    f"{render.CONTENT_BOTTOM}px —— 图注压进页脚区了")

    def test_the_pick_really_covers_every_layout(self) -> None:
        """这条是给上面那条兜底的：`PICK` 要是漏了某种版式，
        上面那条测试会照样绿 —— 而它绿得毫无意义。"""
        kinds = {self.spec["deck"]["slides"][i - 1]["type"] for i in self.PICK}
        from_renderer = set(render.TITLE_TIER) | {"content-text", "content-image",
                                                  "two-column", "timeline", "chart"}
        self.assertEqual(sorted(from_renderer - kinds), [],
                         f"PICK 漏了这些版式，那它们就没被压测覆盖：{sorted(from_renderer - kinds)}")



if __name__ == "__main__":
    unittest.main()


class TestMinimalContract(unittest.TestCase):
    """四张可选 effect 键（Riso 降级）：缺 = 无该效果，不是"声明一堆零"。

    minimal-baseline 是最小契约的活参照 —— 只有核心键的普通风格（Swiss/Minimal/
    Glass…）不再需要"声明自己没有颗粒、没有错位"。
    """

    def test_new_style_scaffold_generates_contract_clean(self) -> None:
        """脚手架草稿当场过契约；写在 **cwd 的 styles/**（随 deck 项目）。

        v3：不再有方向预设 —— 方向由模型读规则后按题自造（预设 = 内置）。
        这里只保证起手就过契约。
        """
        import os as _os
        with tempfile.TemporaryDirectory() as tmp:
            cwd = _os.getcwd()
            try:
                _os.chdir(tmp)
                out = style.new_style("my-deck-style")
                self.assertTrue(_os.path.isfile(_os.path.join(out, "style.json")))
                self.assertTrue(_os.path.isfile(_os.path.join(out, "skin.css")))
                self.assertEqual(style.audit(out), [], "生成的风格没过契约")
                # 拒绝写 skill 自己的 styles/（变相内置，用户明令禁止）
                skill_styles = _os.path.join(SKILL, "styles")
                with self.assertRaises(SystemExit):
                    style.new_style("nope", skill_styles)
            finally:
                _os.chdir(cwd)

    def test_junk_directory_is_not_a_style(self) -> None:
        """styles/ 里没有 style.json 的文件夹不是风格 —— 不进任何列表（用户
        目录会攒草稿；一个手滑的探针文件夹不该把工具链拖红）。"""
        junk = os.path.join(STYLES, "zz_junk_dir")
        os.makedirs(junk, exist_ok=True)
        self.addCleanup(shutil.rmtree, junk, ignore_errors=True)
        with open(os.path.join(junk, "t.txt"), "w") as fh:
            fh.write("date 输出之类的草稿")
        self.assertNotIn("zz_junk_dir", style.available())

    def test_fixture_has_no_effect_keys_and_audits_clean(self) -> None:
        raw = deckio.read_json(os.path.join(STYLES, "minimal-baseline", "style.json"))
        for key in style.EFFECT_KEYS:
            self.assertNotIn(key, raw, f"{key} 应是可选 effect —— 基线风格不该有它")
        self.assertEqual(style.audit("minimal-baseline"), [],
                         "缺 effect 键的风格没过审计")

    def test_renders_without_grain_layer(self) -> None:
        """无 texture：不发 .grain DOM（不是隐形层），错位全零。"""
        spec = deckio.read_json(DEMO)
        spec["deck"]["style"] = "minimal-baseline"
        html = render.render(spec)
        self.assertNotIn('<div class="grain"></div>', html,
                         "没声明纸纹的风格还有 grain 层")
        self.assertEqual(html.count("--dx:0.0px"), html.count("--dx:"),
                         "没声明错位的风格 dx 不全零")

    def test_declared_texture_still_emits_grain(self) -> None:
        """声明了 texture 的风格（swiss-grid）照发纸纹层 —— 可选不是删除。"""
        html = render.render(deckio.read_json(DEMO))    # 默认 swiss-grid
        self.assertIn('<div class="grain"></div>', html)
