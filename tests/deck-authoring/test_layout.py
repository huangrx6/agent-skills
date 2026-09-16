#!/usr/bin/env python3
"""layout/ 包：几何模型 + 安全盒碰撞政策。

一半在测「会报」：deny×deny 安全盒相交必须开口，且报告里带「需要 X 实际 Y」
（只说"撞了"的诊断没法修）。另一半在测「不许报」：同组、父子包含、
figure 内部（visual×caption）、跨页 —— 这四类是视觉整体，报了就是误伤，
误伤会把人练成忽略整个门。
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)),
                     "skills", os.path.basename(HERE))
FIXTURES_DIR = os.path.join(HERE, "fixtures")
os.environ.setdefault("DECK_STYLES", os.path.join(FIXTURES_DIR, "styles"))
os.environ.setdefault("DECK_BRANDS", os.path.join(FIXTURES_DIR, "brands"))

PKG = os.path.join(SKILL, "scripts", "layout", "__init__.py")


def _load_layout():
    spec = importlib.util.spec_from_file_location("_deck_test_layout", PKG)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 layout 包：{PKG}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_deck_test_layout"] = module
    spec.loader.exec_module(module)
    return module


layout = _load_layout()
model, collision = layout.model, layout.collision


def _load_render():
    spec = importlib.util.spec_from_file_location(
        "_deck_test_layout_render", os.path.join(SKILL, "scripts", "render.py"))
    if spec is None or spec.loader is None:
        raise RuntimeError("加载不了 render.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_deck_test_layout_render"] = module
    spec.loader.exec_module(module)
    return module


class TestModel(unittest.TestCase):
    def test_expand_rect(self) -> None:
        safe = model.expand_rect(
            model.Rect(84, 280, 600, 300),
            model.Insets(top=16, right=32, bottom=24, left=0))
        self.assertEqual((safe.x, safe.y, safe.width, safe.height),
                         (84, 264, 632, 340))

    def test_edge_touch_is_not_intersection(self) -> None:
        """净距恰好等于需要间距 = 合格（安全盒边贴边不算撞）。"""
        a = model.Rect(84, 200, 600, 100)
        b = model.Rect(84, 328, 600, 100)      # 净距 28
        self.assertFalse(model.intersects(a, b))

    def test_gap_between(self) -> None:
        a = model.Rect(0, 0, 100, 100)
        self.assertEqual(model.gap_between(a, model.Rect(0, 150, 100, 50)), 50)
        self.assertEqual(model.gap_between(a, model.Rect(130, 0, 50, 100)), 30)
        self.assertEqual(model.gap_between(a, model.Rect(50, 50, 100, 100)), 0)


class TestCollision(unittest.TestCase):
    @staticmethod
    def _el(eid: str, role: str, slide: int, x: float, y: float,
            w: float, h: float) -> dict:
        return {"id": eid, "role": role, "slide": slide,
                "x": x, "y": y, "w": w, "h": h}

    def _violations(self, els: list[dict], hero=frozenset()) -> list[dict]:
        return collision.violations(collision.build_boxes(els), hero)

    def test_deny_pair_too_close_is_reported_with_numbers(self) -> None:
        """标题底 → 条目顶：需要 48（28+20），只给 24 → 报，且带两个数。"""
        v = self._violations([
            self._el("s1.title", "title", 1, 84, 132, 700, 104),
            self._el("s1.bullet.0", "bullet", 1, 84, 260, 600, 40),
        ])
        self.assertEqual(len(v), 1)
        self.assertEqual(v[0]["required"], 48)
        self.assertEqual(v[0]["actual"], 24)

    def test_comfortable_gap_passes(self) -> None:
        self.assertEqual(self._violations([
            self._el("s1.title", "title", 1, 84, 132, 700, 104),
            self._el("s1.bullet.0", "bullet", 1, 84, 304, 600, 40),  # 净距 68
        ]), [])

    def test_same_group_exempt(self) -> None:
        """列表条目之间、标题与副标题之间是一个视觉整体 —— 不互判。"""
        self.assertEqual(self._violations([
            # 同组贴脸（净距 4）不报；跨组（subtitle→bullet）给足 48
            self._el("s1.bullet.0", "bullet", 1, 84, 324, 600, 40),
            self._el("s1.bullet.1", "bullet", 1, 84, 368, 600, 40),
            self._el("s1.title", "title", 1, 84, 132, 700, 104),
            self._el("s1.subtitle", "subtitle", 1, 84, 240, 700, 36),
        ]), [])

    def test_containment_exempt(self) -> None:
        """caption 在 figure 盒内部（父子 DOM）—— 组件内部不是页布局的事。"""
        self.assertEqual(self._violations([
            self._el("s1.image", "image", 1, 84, 300, 600, 400),
            self._el("s1.caption", "caption", 1, 84, 664, 560, 36),  # 盒内贴底
        ]), [])

    def test_visual_and_its_caption_exempt(self) -> None:
        """caption 属于 figure（图内间距由 figure 的 padding 管）—— 不互判。"""
        self.assertEqual(self._violations([
            self._el("s1.chart", "chart", 1, 84, 300, 1432, 378),
            self._el("s1.caption", "bullet", 1, 84, 702, 600, 36),  # 净距 24
        ]), [])

    def test_cross_slide_never_compares(self) -> None:
        self.assertEqual(self._violations([
            self._el("s1.title", "title", 1, 84, 132, 700, 104),
            self._el("s2.bullet.0", "bullet", 2, 84, 200, 600, 40),
        ]), [])

    def test_hero_title_over_image_is_intentional(self) -> None:
        """hero：实心反色标题条压图是设计本身 —— 豁免；非 hero 页同样的重叠照报。"""
        els = [
            self._el("s1.image", "image", 1, 0, 0, 1600, 900),
            self._el("s1.title", "title", 1, 84, 700, 1000, 80),
        ]
        self.assertEqual(self._violations(els, hero=frozenset({1})), [])
        self.assertEqual(len(self._violations(els)), 1)

    def test_caption_clearance_by_id_not_role(self) -> None:
        """图表页 caption 的登记角色是 bullet；安全距离按真实身份取（12 不是 20）。"""
        boxes = collision.build_boxes(
            [self._el("s1.caption", "bullet", 1, 84, 300, 600, 36)])
        self.assertEqual(boxes[0].clearance.top, 12)

    def test_malformed_elements_skipped(self) -> None:
        """缺几何 / 非数字的元素不参与（check 从不抛）。"""
        self.assertEqual(collision.build_boxes(
            [{"id": "s1.x", "role": "title", "slide": 1},
             {"id": "s1.y", "role": "title", "slide": 1,
              "x": "84", "y": 132, "w": 100, "h": 40}]), [])



class TestChartContract(unittest.TestCase):
    """图表进产物的两条契约：排印从 token 来；图注的身份是**图注**。

    两条都是实测踩出来的：
    - 排印：G2 主题的默认字体/字号不跟 deck 走（深底风格里默认轴文字看不见），
      必须由 `chart_g2_spec` 显式注入。键名 `labelFontFamily` 在 G2 5.2.10 包里
      搜不到（运行期按「部件 + 通用样式属性」拼出来），但**实测有效** ——
      这条测试守住"注入了，而且值来自风格 token"。
    - 身份：图表图注曾被标成 role=bullet → 被字号体检当成正文计入中位数
      （一次 4 页图注把中位数从 24px 拽到 16px，报了"内页正文偏小"）。
    """

    def _render(self, spec, tmp):
        import subprocess
        scripts = os.path.join(SKILL, "scripts")
        spec_path = os.path.join(tmp, "chart.spec.json")
        with open(spec_path, "w", encoding="utf-8") as fh:
            json.dump(spec, fh, ensure_ascii=False)
        out = os.path.join(tmp, "out.html")
        proc = subprocess.run(
            ["python3", os.path.join(scripts, "render.py"), spec_path, "-o", out],
            capture_output=True, text=True, timeout=300, env=dict(os.environ))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return out

    def test_chart_typography_is_token_driven_and_caption_keeps_its_role(self):
        import base64  # noqa: F401  (惯例：产物里清单是 JSON，探针才用 base64)
        import re
        import tempfile

        style_path = os.path.join(FIXTURES_DIR, "styles", "swiss-grid", "style.json")
        with open(style_path, encoding="utf-8") as fh:
            style = json.load(fh)
        fonts_body = style["fonts"]["body"]
        tier = style["type"]
        color_set = sorted(style["colorSets"])[0]
        spec = {"deck": {
            "style": "swiss-grid", "colorSet": color_set, "seed": 3,
            "title": "图表契约",
            "slides": [{"type": "chart", "title": "等级分布",
                        "chart": "bar", "caption": "数据来源：运行台账",
                        "data": [{"label": "甲", "value": 3},
                                 {"label": "乙", "value": 7}]}]}}
        with tempfile.TemporaryDirectory() as tmp:
            out = self._render(spec, tmp)
            doc = open(out, encoding="utf-8").read()

        found = re.search(
            r'<script type="application/json" id="__deck_manifest">(.*?)</script>',
            doc, re.S)
        if found is None:
            self.fail("产物里没有语义清单")
        manifest = json.loads(found.group(1))
        cap = [e for e in manifest if e["id"].endswith(".caption")]
        self.assertEqual(len(cap), 1)
        self.assertEqual(cap[0]["role"], "caption",
                         "图注被当成正文，会污染字号体检的中位数")

        bar = re.search(r"data-g2='(.*?)'", doc)
        if bar is None:
            self.fail("产物里没有图表 spec")
        g2 = json.loads(bar.group(1).replace("&#39;", "'"))
        self.assertEqual(g2["axis"]["x"]["labelFontFamily"], fonts_body)
        self.assertEqual(g2["axis"]["x"]["labelFontSize"], tier["chartLabel"])
        self.assertEqual(g2["labels"][0]["style"]["fontFamily"], fonts_body)
        self.assertEqual(g2["labels"][0]["style"]["fontSize"], tier["chartValue"])
        self.assertNotIn("radius", g2.get("style", {}),
                         "柱形圆角在 G2 5.2.10 的 spec 路径下被忽略，写了就是骗自己")
        # 轴标题：不关就是数据集名（"label" / "value"）印在轴上 —— 实测截图里就是
        self.assertFalse(g2["axis"]["x"]["title"])
        self.assertFalse(g2["axis"]["y"]["title"])
        # tooltip：交互产物会落进截图/录屏/PDF（实测截图里飘着"重大 / value / 3"）
        self.assertFalse(g2["interaction"]["tooltip"])
        # 柱宽：基准实测 187px / 横向覆盖 82.9%（四根几乎连成一片）——
        # 用相对 band 的 padding（绝对像素在类目多时会把柱子挤成细线）
        self.assertEqual(g2["scale"]["x"]["padding"], 0.45)

    def test_size_gate_ignores_captions_when_measuring_body(self):
        """字号体检的"正文"= role=bullet；图注再小也不是正文。"""
        import importlib.util as ilu
        check_path = os.path.join(SKILL, "scripts", "check.py")
        found_spec = ilu.spec_from_file_location("_deck_test_check_gate", check_path)
        if found_spec is None or found_spec.loader is None:
            self.fail(f"加载不了 check.py：{check_path}")
        module = ilu.module_from_spec(found_spec)
        sys.modules["_deck_test_check_gate"] = module
        found_spec.loader.exec_module(module)
        deck = {"slides": [{"type": "chart"}, {"type": "content-text"}]}

        def measured(bullet_px):
            els = [{"slide": 2, "role": "bullet", "fontSize": bullet_px}
                   for _ in range(4)]
            els.append({"slide": 1, "role": "caption", "fontSize": 12})
            return {"elements": els}

        small = module._check_type_size(measured(16), deck, None)
        self.assertTrue(any("偏小" in n for n in small), small)
        ok = module._check_type_size(measured(24), deck, None)
        self.assertFalse(any("偏小" in n for n in ok),
                         f"图注（12px）不该把正文中位数拽低：{ok}")


if __name__ == "__main__":
    unittest.main()


class TestEdgeGates(unittest.TestCase):
    """右缘栅格 + 同级左缘一致（提示级，挂在网格对齐那组）。"""

    @staticmethod
    def _measured(els):
        return {"elements": els}

    @staticmethod
    def _notes(measured):
        check_spec = importlib.util.spec_from_file_location(
            "_deck_test_check_align", os.path.join(SKILL, "scripts", "check.py"))
        if check_spec is None or check_spec.loader is None:
            raise RuntimeError("加载不了 check.py")
        check = importlib.util.module_from_spec(check_spec)
        sys.modules["_deck_test_check_align"] = check
        check_spec.loader.exec_module(check)
        return check._check_grid_alignment(measured)

    def test_chart_box_wider_than_grid_fires_right_edge_note(self) -> None:
        """图表盒 1480 宽（右缘 1564）—— 左缘吸得完美也必须被看见。"""
        notes = self._notes(self._measured([
            {"id": "s1.chart", "role": "chart", "slide": 1,
             "x": 84, "y": 300, "w": 1480, "h": 378},
        ]))
        self.assertTrue(any("右缘不在栅格缘" in n for n in notes), notes)

    def test_chart_right_on_content_edge_passes(self) -> None:
        self.assertEqual(self._notes(self._measured([
            {"id": "s1.chart", "role": "chart", "slide": 1,
             "x": 84, "y": 300, "w": 1432, "h": 378},
        ])), [])

    def test_image_right_at_span_end_passes(self) -> None:
        """span5 的图（582.67 宽）右缘 = 列起点减一档 gutter —— 合法。"""
        self.assertEqual(self._notes(self._measured([
            {"id": "s1.image", "role": "image", "slide": 1,
             "x": 84, "y": 300, "w": 582.67, "h": 400},
        ])), [])

    def test_title_subtitle_left_mismatch_fires(self) -> None:
        """2px 漂移（标题块内缩 30、副标题用了 32 的档）—— 肉眼成品上才看得见。"""
        notes = self._notes(self._measured([
            {"id": "s1.title", "role": "title", "slide": 1,
             "x": 114, "y": 195, "w": 282, "h": 81},
            {"id": "s1.subtitle", "role": "subtitle", "slide": 1,
             "x": 116, "y": 300, "w": 1400, "h": 33},
        ]))
        self.assertTrue(any("左缘不一致" in n and "2px" in n for n in notes), notes)

    def test_aligned_pair_passes(self) -> None:
        # 取列起点 84：既过「同级左缘一致」，也过「左缘吸附」（x=114 会命中
        # 另一条门 —— 那条对 114 报警是对的，风格故意内缩要走它的豁免口径）
        self.assertEqual(self._notes(self._measured([
            {"id": "s1.title", "role": "title", "slide": 1,
             "x": 84, "y": 195, "w": 282, "h": 81},
            {"id": "s1.subtitle", "role": "subtitle", "slide": 1,
             "x": 84, "y": 300, "w": 1400, "h": 33},
        ])), [])


class TestRepairLadder(unittest.TestCase):
    """修复梯（layout/repair.py）：信号 → 计划 → 应用。

    一半在测「会修」：未声明的档位降一档、补丁可复现（写回 spec 字段）。
    另一半在测「不许修」：作者声明过的字段只出诊断；已到最小档就停 ——
    再装不下是内容问题，缩字号不是答案。
    """

    @staticmethod
    def _layout_pkg():
        return _load_layout()

    def _signals(self, bottoms, tops=None):
        """bottoms: {slide: 最后一行内容底（页内坐标）}。"""
        tops = tops or {s: s * 936 for s in bottoms}
        elements, slides = [], []
        for s in sorted(set(list(bottoms) + list(tops))):
            slides.append({"x": 0, "y": tops[s], "w": 1600, "h": 900})
        for s, b in bottoms.items():
            elements.append({"id": f"s{s}.bullet.0", "role": "bullet", "slide": s,
                             "x": 84, "y": tops[s] + b - 40, "w": 1432, "h": 40})
        return self._layout_pkg().repair.signals({"slides": slides,
                                                  "elements": elements})

    def test_v_overflow_detected(self) -> None:
        issues = self._signals({1: 900})          # 带底 824
        self.assertTrue(any(i["kind"] == "v_overflow" and i["slide"] == 1
                            for i in issues))

    def test_in_band_passes(self) -> None:
        self.assertEqual(self._signals({1: 820}), [])

    def test_foot_not_judged(self) -> None:
        pkg = self._layout_pkg()
        els = [{"id": "s1.foot", "role": "foot", "slide": 1,
                "x": 84, "y": 936 + 830, "w": 300, "h": 18}]
        self.assertEqual(pkg.repair.signals(
            {"slides": [{"x": 0, "y": 936, "w": 1600, "h": 900}],
             "elements": els}), [])

    def test_plan_patches_undeclared_tier(self) -> None:
        pkg = self._layout_pkg()
        spec = {"deck": {"slides": [
            {"type": "content-text", "title": "t", "bullets": ["a"] * 12}]}}
        resolved = {"slides": [{"bTier": "bullet"}]}
        actions, diags = pkg.repair.plan(spec, resolved, self._signals({1: 900}))
        self.assertEqual(actions, [{"slide": 1, "field": "bulletTier",
                                    "from": "bullet", "to": "bulletSmall",
                                    "why": "内容底超出正文带 76px"}])
        self.assertEqual(diags, [])

    def test_plan_respects_declared_tier(self) -> None:
        pkg = self._layout_pkg()
        spec = {"deck": {"slides": [
            {"type": "content-text", "title": "t", "bulletTier": "bulletLarge",
             "bullets": ["a"] * 12}]}}
        resolved = {"slides": [{"bTier": "bulletLarge"}]}
        actions, diags = pkg.repair.plan(spec, resolved, self._signals({1: 900}))
        self.assertEqual(actions, [])
        self.assertEqual(len(diags), 1)
        self.assertIn("不自动改", diags[0]["why"])

    def test_plan_stops_at_smallest_tier(self) -> None:
        pkg = self._layout_pkg()
        spec = {"deck": {"slides": [
            {"type": "content-text", "title": "t", "bullets": ["a"] * 20}]}}
        resolved = {"slides": [{"bTier": "bulletSmall"}]}
        actions, diags = pkg.repair.plan(spec, resolved, self._signals({1: 900}))
        self.assertEqual(actions, [])
        self.assertIn("内容问题", diags[0]["why"])

    def test_apply_writes_back(self) -> None:
        pkg = self._layout_pkg()
        spec = {"deck": {"slides": [
            {"type": "content-text", "title": "t", "bullets": ["a"]}]}}
        pkg.repair.apply(spec, [{"slide": 1, "field": "bulletTier",
                                 "from": "bullet", "to": "bulletSmall"}])
        self.assertEqual(spec["deck"]["slides"][0]["bulletTier"], "bulletSmall")


class TestRepairCLI(unittest.TestCase):
    """`render --repair` 的端到端契约（真渲真量，钉住 CLI 行为）。"""

    def test_repair_patches_undeclared_and_respects_declared(self) -> None:
        import subprocess
        import tempfile
        scripts = os.path.join(SKILL, "scripts")
        env = dict(os.environ)
        with tempfile.TemporaryDirectory() as tmp:
            spec = {"deck": {
                "style": "swiss-grid", "colorSet": "blue", "seed": 3,
                "title": "修复梯",
                "slides": [
                    {"type": "content-text", "title": "未声明档位",
                     "bullets": [f"第 {i} 条内容，长度足够参与换行与占位" for i in range(1, 12)]},
                    {"type": "content-text", "title": "声明过档位",
                     "bulletTier": "bulletLarge",
                     "bullets": [f"第 {i} 条内容，长度足够参与换行与占位" for i in range(1, 12)]},
                ]}}
            spec_path = os.path.join(tmp, "deck.spec.json")
            with open(spec_path, "w", encoding="utf-8") as fh:
                json.dump(spec, fh, ensure_ascii=False)
            out = os.path.join(tmp, "out.html")
            proc = subprocess.run(
                ["python3", os.path.join(scripts, "render.py"),
                 spec_path, "-o", out, "--repair"],
                capture_output=True, text=True, timeout=300, env=env)
            # 声明页修不了 → 退出码 1（这是契约：不能假装修好了）
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            report = json.load(open(out + ".repair.json", encoding="utf-8"))
            fields = {(p["slide"], p["field"], p["to"]) for p in report["patches"]}
            self.assertIn((1, "bulletTier", "bulletSmall"), fields)
            self.assertNotIn((2, "bulletTier", "bulletSmall"), fields,
                             "作者声明过的页不许被改")
            self.assertTrue(any(d["slide"] == 2 for d in report["diagnostics"]))
            repaired = json.load(
                open(out.replace(".html", ".repaired.spec.json"), encoding="utf-8"))
            self.assertEqual(repaired["deck"]["slides"][0]["bulletTier"],
                             "bulletSmall")
            # 声明页保持原样：repaired spec 里仍是作者声明的 bulletLarge
            self.assertEqual(repaired["deck"]["slides"][1]["bulletTier"],
                             "bulletLarge")


class TestApplyPicks(unittest.TestCase):
    """`--picks` 的回写：候选名写进 spec，null/“缺省”撤掉 layout，坏键不静默吞。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.render = _load_render()

    def _spec(self) -> dict:
        return {"deck": {"slides": [
            {"type": "content-image", "layout": "hero"},
            {"type": "two-column"},
            {"type": "content-text"}]}}

    def test_names_are_written_and_default_removes_layout(self) -> None:
        picked, applied, problems = self.render._apply_picks(
            self._spec(), {"1": "even", "2": "缺省", "3": None})
        self.assertEqual(problems, [])
        self.assertEqual(len(applied), 3)
        self.assertEqual(picked["deck"]["slides"][0]["layout"], "even")
        self.assertNotIn("layout", picked["deck"]["slides"][1])
        self.assertNotIn("layout", picked["deck"]["slides"][2])
        # 原 spec 不被就地改（回写是复制，不是污染输入）
        self.assertEqual(self._spec()["deck"]["slides"][0]["layout"], "hero")

    def test_bad_keys_and_values_are_reported(self) -> None:
        _picked, applied, problems = self.render._apply_picks(
            self._spec(), {"9": "even", "abc": "even", "1": 7})
        self.assertEqual(applied, [])
        self.assertEqual(len(problems), 3, problems)


class TestCandidateCLI(unittest.TestCase):
    """`--candidates` 的端到端契约：对比页 + 报告 + `--picks` 回写。

    钉的是“决定权在作者”这件事：产物里必须有一页对比页（同内容不同结构）
    和一份能被回写的 picks 通路 —— 而不是脚本自己悄悄选完了。
    """

    def test_compare_page_and_picks_writeback(self) -> None:
        import subprocess
        import tempfile
        scripts = os.path.join(SKILL, "scripts")
        with tempfile.TemporaryDirectory() as tmp:
            spec = {"deck": {
                "style": "swiss-grid", "colorSet": "blue", "seed": 11,
                "title": "候选",
                "slides": [
                    {"type": "content-image", "title": "图页",
                     "bullets": ["一", "二", "三"], "image": "x.png",
                     "visual": {"kind": "evidence_image"}},
                    {"type": "two-column", "title": "双栏",
                     "columns": [{"title": "左", "bullets": ["a", "b"]},
                                 {"title": "右", "bullets": ["c", "d"]}]},
                ]}}
            spec_path = os.path.join(tmp, "deck.spec.json")
            with open(spec_path, "w", encoding="utf-8") as fh:
                json.dump(spec, fh, ensure_ascii=False)
            out = os.path.join(tmp, "out.html")
            env = dict(os.environ)
            proc = subprocess.run(
                ["python3", os.path.join(scripts, "render.py"), spec_path,
                 "-o", out, "--candidates"],
                capture_output=True, text=True, timeout=600, env=env)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

            compare = os.path.join(tmp, "out.compare.html")
            self.assertTrue(os.path.exists(compare), proc.stdout)
            with open(compare, encoding="utf-8") as fh:
                html = fh.read()
            self.assertIn('id="cmp"', html, "对比页必须带选择面板")
            self.assertIn("var PLAN=", html)
            # 同一页的几种结构都要在对比页里出现：visual-right 是**默认路径**
            # （不发类名，逐字节不变），其它变体发 v-<名>。
            self.assertIn('class="two"', html)
            self.assertIn('class="two v-even"', html, "同一页的不同结构要都在对比页里")
            self.assertIn('class="two v-visual-wide"', html)

            report_path = os.path.join(tmp, "out.candidates.json")
            with open(report_path, encoding="utf-8") as fh:
                report = json.load(fh)
            self.assertEqual(set(report["assignments"]), {"1", "2"})
            self.assertTrue(report["assignments"]["2"],
                            "每页都必须给出候选（否则对比页是空的）")

            picks_path = os.path.join(tmp, "picks.json")
            with open(picks_path, "w", encoding="utf-8") as fh:
                json.dump({"1": "even", "2": None}, fh)
            proc2 = subprocess.run(
                ["python3", os.path.join(scripts, "render.py"), spec_path,
                 "-o", out, "--candidates", "--picks", picks_path],
                capture_output=True, text=True, timeout=600, env=env)
            self.assertEqual(proc2.returncode, 0, proc2.stdout + proc2.stderr)
            with open(os.path.join(tmp, "out.picked.spec.json"),
                      encoding="utf-8") as fh:
                picked = json.load(fh)
            self.assertEqual(picked["deck"]["slides"][0]["layout"], "even")
            self.assertNotIn("layout", picked["deck"]["slides"][1])


class TestContracts(unittest.TestCase):
    """页面契约（layout/contracts.py）：写前预算 —— 这一页能装多少。

    钉两件事：**结构真的影响预算**（宽栏能放更多字），以及**坏值不会把表变 NaN**
    （NaN 参与比较全假，预算等于静默失效）。
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.pkg = _load_layout()
        cls.c = cls.pkg.contracts
        cls.TIERS = {"type": {"compact": 96.0, "bullet": 32.0, "colTitle": 40.0,
                              "nodeLabel": 28.0, "nodeNote": 22.0,
                              "cover": 128.0, "end": 128.0}}

    def test_wider_text_region_holds_more_characters(self) -> None:
        tiers = self.TIERS["type"]
        wide = self.c.budgets("content-image", "visual-right", tiers)["bullets"]
        narrow = self.c.budgets("content-image", "visual-wide", tiers)["bullets"]
        self.assertGreater(wide["maxChars"], narrow["maxChars"],
                           "7 栅文字栏必须比 4 栅能放更多字")

    def test_hero_uses_its_own_title_size(self) -> None:
        tiers = self.TIERS["type"]
        hero = self.c.budgets("content-image", "hero", tiers)
        normal = self.c.budgets("content-image", "visual-right", tiers)
        self.assertGreater(hero["title"]["maxChars"], normal["title"]["maxChars"],
                           "满幅页的标题住在底部条里，字号小一档 → 能放更多字")

    def test_two_column_items_use_the_bullet_size_not_the_column_title(self) -> None:
        col = self.c.budgets("two-column", "even", self.TIERS["type"])["columns"]
        self.assertEqual(col["size"], 32.0, "栏内条目是条目字号，不是栏题字号")
        self.assertGreater(col["titleChars"], 0)

    def test_bad_tier_values_do_not_poison_the_table(self) -> None:
        bad = {"bullet": float("nan"), "colTitle": True, "compact": "96"}
        out = self.c.budgets("content-image", "even", bad)
        # 任何一项变成 NaN 都会让后面的比较静默失效 —— 逐项确认是正常数
        for key in ("title", "bullets"):
            for field, value in out[key].items():
                if isinstance(value, float):
                    self.assertEqual(value, value, f"{key}.{field} 是 NaN")
                    self.assertGreater(value, 0, f"{key}.{field}")
        self.assertGreater(out["bullets"]["maxChars"], 0, out)
        self.assertGreater(out["title"]["maxChars"], 0, out)

    def test_unknown_page_type_is_not_guessed(self) -> None:
        self.assertEqual(self.c.budgets(None, None, self.TIERS["type"]), {})
        self.assertEqual(self.c.budgets("", None, self.TIERS["type"]), {})
        # tiers 缺失（没有风格 token）走默认档，而不是变成空表或 NaN
        fallback = self.c.budgets("content-text", None, None)
        self.assertGreater(fallback["bullets"]["maxChars"], 0, fallback)

    def test_per_slide_rows_skip_broken_entries(self) -> None:
        rows = self.c.contract_for_slides(
            [{"type": "content-text"}, None, {"title": "缺 type"}],
            self.TIERS["type"])
        self.assertEqual([r["page"] for r in rows], [1])


class TestFingerprint(unittest.TestCase):
    """结构指纹（layout/fingerprint.py）：镜像不算新结构，跨度不同才算。

    为什么这条要单独测：页级要给 3 个候选，一旦把镜像（图左/图右）当成不同结构，
    三个候选就会摆出"同一个构图换三件衣服"—— 作者看着有得选，其实没得选。
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.c = _load_layout().fingerprint

    def test_mirrors_collapse_to_one_composition(self) -> None:
        self.assertEqual(self.c.composition("content-image", "visual-right"),
                         self.c.composition("content-image", "visual-left"))
        self.assertEqual(self.c.composition("two-column", "lean-left"),
                         self.c.composition("two-column", "lean-right"))

    def test_different_spans_or_family_are_different_structures(self) -> None:
        comps = {self.c.composition("content-image", n)
                 for n in ("visual-right", "even", "hero")}
        self.assertEqual(len(comps), 3, comps)

    def test_distinct_keeps_one_per_composition(self) -> None:
        self.assertEqual(
            self.c.distinct("content-image",
                            ["visual-right", "visual-left", "even", "visual-wide",
                             "hero"]),
            ["visual-right", "even", "visual-wide", "hero"])
        self.assertEqual(
            self.c.distinct("two-column",
                            ["even", "lean-left", "lean-right",
                             "lean-hard-left", "lean-hard-right"]),
            ["even", "lean-left", "lean-hard-left"])

    def test_vocabulary_is_wide_enough_for_candidate_search(self) -> None:
        """结构词表至少要有 3 个真构图 —— 否则"给三个候选"是句空话。

        实测踩过：content-image 只有 6+6 / 7+5 / 满幅三个构图，
        于是三个候选只能取全部 —— 联合择优根本没有自由度可选。
        """
        for page_type in ("content-image", "two-column"):
            comps = {self.c.composition(page_type, n)
                     for n in self.c.STRUCTURES[page_type]}
            self.assertGreaterEqual(len(comps), 3, f"{page_type} 真构图不足：{comps}")

    def test_unknown_names_are_kept_not_swallowed(self) -> None:
        """不认识的名字不静默吞掉：宁可多给一个候选，也别把真支持的东西藏了。"""
        self.assertIsNone(self.c.composition("content-image", "brand-new"))
        self.assertEqual(self.c.distinct("content-image", ["brand-new"]),
                         ["brand-new"])
        self.assertIsNone(self.c.fingerprint("content-text", "anything"))

    def test_mirror_lookup(self) -> None:
        self.assertEqual(self.c.mirror_of("content-image", "visual-right"),
                         "visual-left")
        self.assertIsNone(self.c.mirror_of("content-image", "hero"))

    def test_region_spans_are_exposed_for_budgets(self) -> None:
        keys = self.c.region_budget_key("content-image", "visual-right")
        self.assertEqual({k: v["span"] for k, v in keys.items()},
                         {"main": 7, "image": 5})

    def test_table_covers_exactly_the_renderer_vocabulary(self) -> None:
        """结构表 ↔ 渲染器能力清单不得漂移（两份词表写岔 = 静默不受支持）。"""
        render = _load_render()
        for page_type, vocab in (("content-image", render.IMAGE_LAYOUTS),
                                 ("two-column", render.TWO_COL_LAYOUTS)):
            self.assertEqual(set(self.c.STRUCTURES[page_type]), set(vocab),
                             f"{page_type} 的结构表与渲染器能力清单对不上")


class TestAllocation(unittest.TestCase):
    """deck 级**联合**择优（layout/allocation.py）。

    测的是一件事：逐页各挑各的最优会得到"每页都还行、整份却一个版式用五遍"，
    联合择优必须在多页之间把候选散开，而且**同 seed 必得同结果**。
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.pkg = _load_layout()
        cls.a, cls.fp = cls.pkg.allocation, cls.pkg.fingerprint

    def _page(self, key, fits: dict, page_type="content-image"):
        return {"key": key, "pageType": page_type,
                "candidates": [{"layout": n, "fit": f,
                                "fingerprint": self.fp.fingerprint(page_type, n)}
                               for n, f in fits.items()]}

    def test_same_seed_same_result(self) -> None:
        pages = [self._page(i, {"visual-right": 0.8, "even": 0.79, "hero": 0.78})
                 for i in range(1, 7)]
        first = self.a.allocate(pages, seed="deck-a")["assignments"]
        second = self.a.allocate(pages, seed="deck-a")["assignments"]
        third = self.a.allocate(pages, seed="deck-b")["assignments"]
        self.assertEqual(first, second, "同 seed 同输入必须同结果")
        self.assertEqual(set(first), set(third), "两个 seed 都该给出全部页")

    def test_repetition_is_spread_across_pages(self) -> None:
        """同分页多于一页时，选出来的三条候选不该每页都是同一组。"""
        fits = {"visual-right": 0.80, "even": 0.80, "visual-wide": 0.80,
                "hero": 0.80, "visual-left": 0.80}      # 5 个名字 → 4 个真构图
        pages = [self._page(i, fits) for i in range(1, 7)]
        out = self.a.allocate(pages, seed="deck-spread")
        combos = {tuple(sorted(v)) for v in out["assignments"].values()}
        self.assertGreaterEqual(len(combos), 3, f"候选组合没散开：{combos}")
        # visual-left 与 visual-right 同构图（镜像）→ 同一页不会同时出现
        for key, names in out["assignments"].items():
            comps = [self.fp.composition("content-image", n) for n in names]
            self.assertEqual(len(comps), len(set(comps)), f"第 {key} 页给了同构图候选")

    def test_far_worse_candidate_is_dropped(self) -> None:
        """一个明显更差的候选不该占位置（拟合带内才留）。"""
        out = self.a.allocate(
            [self._page(1, {"visual-right": 0.90, "even": 0.85, "hero": 0.80,
                            "visual-left": 0.20})], seed="deck-band")
        self.assertEqual(out["assignments"][1],
                         ["visual-right", "even", "hero"])

    def test_insufficient_candidates_are_reported_not_faked(self) -> None:
        """two-column 只有 3 个真构图（lean 两向是镜像）——给 3 个，不凑数。"""
        out = self.a.allocate(
            [self._page(1, {"even": 0.8, "lean-left": 0.75, "lean-right": 0.70},
                        page_type="two-column")], seed="deck-two")
        self.assertEqual(len(out["assignments"][1]), 2,
                         "默认给三条；只有两个真构图时才给两条")
        self.assertTrue(any("只有 2 个结构不同" in d for d in out["diagnostics"]),
                        out["diagnostics"])

    def test_pages_without_candidates_stay_out(self) -> None:
        out = self.a.allocate([{"key": 3, "pageType": "content-text",
                                "candidates": []}], seed="deck-empty")
        self.assertEqual(out["assignments"], {})
        self.assertTrue(any("没有可用候选" in d for d in out["diagnostics"]))

    def test_bad_fit_values_do_not_poison_the_page(self) -> None:
        """NaN / bool / 字符串不是分数：混进 max() 会把基准变成 NaN（静默挑错）。"""
        page = {"key": 1, "pageType": "content-image", "candidates": [
            {"layout": "even", "fit": float("nan")},
            {"layout": "hero", "fit": True},
            {"layout": "visual-right", "fit": "0.9"},
            {"layout": "visual-left", "fit": 0.7,
             "fingerprint": self.fp.fingerprint("content-image", "visual-left")},
        ]}
        out = self.a.allocate([page], seed="deck-nan")
        self.assertEqual(out["assignments"][1], ["visual-left"])

    def test_repeat_counts_only_reports_actual_repeats(self) -> None:
        self.assertEqual(self.a.repeat_counts(["a", "a", "b"]), {"a": 2})
        self.assertEqual(self.a.repeat_counts([]), {})


class TestCandidates(unittest.TestCase):
    """候选搜索（layout/candidates.py）：搜什么、怎么打分、什么作废。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.pkg = _load_layout()
        cls.c = cls.pkg.candidates

    def test_searchable_pages(self) -> None:
        img, two = ("visual-right", "visual-left", "even", "hero"), ("even", "lean-left", "lean-right")
        self.assertEqual(self.c.searchable({"type": "content-image"}, img, two),
                         list(img))
        self.assertEqual(self.c.searchable({"type": "two-column"}, img, two),
                         list(two))
        # 声明过 = 钉死（主权）；无结构布局的页型 = 没得搜
        self.assertEqual(self.c.searchable(
            {"type": "content-image", "layout": "even"}, img, two), [])
        self.assertEqual(self.c.searchable({"type": "content-text"}, img, two), [])

    @staticmethod
    def _page(els, top=0.0):
        return els, top

    def _els(self, bottom, image=None, bullets=1):
        top = 0.0
        els = [{"id": "s1.title", "role": "title", "x": 84, "y": top + 140,
                "w": 600, "h": 48, "fontSize": 42,
                "scrollW": 600, "clientW": 600}]
        y = top + 300
        for i in range(bullets):
            els.append({"id": f"s1.bullet.{i}", "role": "bullet", "x": 84,
                        "y": y, "w": 825, "h": 40, "fontSize": 26,
                        "scrollW": 825, "clientW": 825})
            y += 52
        if image is not None:
            w, h = image
            els.append({"id": "s1.image", "role": "image", "x": 933,
                        "y": top + 300, "w": w, "h": h})
        return els, top

    def test_overflow_candidate_is_invalid(self) -> None:
        els, top = self._els(bottom=None, image=None, bullets=1)
        els[1]["y"] = 900                    # 内容底 940 > 带底 824
        r = self.c.score_page("content-text", els, top)
        self.assertFalse(r["valid"])
        self.assertTrue(any(i.startswith("v_overflow") for i in r["invalid_reason"]))

    def test_raw_density_and_scores_are_separate(self) -> None:
        """占带 53% 是原始值；区间得分 1.0 是另一回事 —— 混读会当成「塞满」。"""
        els, top = self._els(None, image=(583, 200), bullets=2)   # 图底 500 最深
        r = self.c.score_page("content-image", els, top)
        self.assertTrue(r["valid"])
        self.assertAlmostEqual(r["density"], (500 - 132) / 692, places=2)
        self.assertEqual(r["scores"]["density"], 1.0)

    def test_overfull_scores_lower_not_higher(self) -> None:
        """反「最满优先」：占带超出区间上沿（仍不溢出），密度分必须往下走。"""
        mid, top = self._els(None, image=(583, 200), bullets=2)          # 53%
        full = [dict(e) for e in mid]
        full[1]["y"] = 700                     # bullet.0 → 底 740
        full[2]["y"] = 752                     # bullet.1 → 底 792（≤824 不溢出）
        full[3]["h"] = 492                     # 图底 792
        r_mid = self.c.score_page("content-image", mid, top)
        r_full = self.c.score_page("content-image", full, top)
        self.assertTrue(r_full["valid"], r_full["invalid_reason"])
        # 原始占带确实更满（0.95 vs 0.53）—— 但**得分**更低：满不是优点
        self.assertGreater(r_full["density"], r_mid["density"])
        self.assertLess(r_full["scores"]["density"], r_mid["scores"]["density"])

    def test_hero_trial_gets_intentional_exemption(self) -> None:
        """试 hero = 试用即声明：条上文字压图按 intentional 豁免；非 hero 同样布局作废。"""
        els = [
            {"id": "s1.image", "role": "image", "x": 84, "y": 200,
             "w": 1432, "h": 560},
            {"id": "s1.title", "role": "title", "x": 114, "y": 640,
             "w": 900, "h": 60, "fontSize": 42, "scrollW": 900, "clientW": 900},
            {"id": "s1.bullet.0", "role": "bullet", "x": 114, "y": 710,
             "w": 900, "h": 36, "fontSize": 26, "scrollW": 900, "clientW": 900},
        ]
        hero = self.c.score_page("content-image", els, 0.0, layout_name="hero")
        plain = self.c.score_page("content-image", els, 0.0, layout_name="even")
        self.assertTrue(hero["valid"], hero["invalid_reason"])
        self.assertFalse(plain["valid"])

    def test_hero_not_rewarded_by_focal(self) -> None:
        """满幅图的视觉占比 1.0 在 [0.35, 0.60] 区间外 → 视觉分 0（声明设计不自动加分）。"""
        els, top = self._els(None, image=(1432, 460), bullets=1)   # 图底 760 ≤824
        r = self.c.score_page("content-image", els, top, layout_name="hero")
        self.assertTrue(r["valid"], r["invalid_reason"])
        self.assertEqual(r["scores"]["focal"], 0.0)
