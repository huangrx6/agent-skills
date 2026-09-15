#!/usr/bin/env python3
"""内容设计层的验证：试排（fit.py）与 deck 级检查。

这一层最容易出的错不是"算错"，是**把两件事混成一件**。最典型的一次就发生在这里：

    第一版把"半页空"和"装不下"合成一个 mark，于是"2 条内容、占了正文带 46%"
    被判成"装不下"，输出"建议拆页 —— 拆成 1 页"这种废话。**数字全对，意思错了。**

所以下面第一个用例专盯这件事。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/deck-authoring/test_fit.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")
DEMO = os.path.join(SKILL, "dev-tools", "demo.spec.json")


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
fit = _load("fit")
check_mod = _load("check")


def _fake_measured(rows: list[tuple[int, float, float]], slides: int | None = None,
                   roles: tuple[str, ...] = ("title", "bullet")) -> dict:
    """造一份最小可用的测量结果。

    每个 `[data-m]` 元素的 y 是**文档坐标**（产物纵向堆叠），所以要加上每页的偏移 ——
    与真浏览器给的一致。这是刻意的：`slide_content_span` 的口径就是在这上面归一化的，
    喂一个"已经把偏移减掉"的假数据等于绕过了它要测的那段。
    """
    n = slides if slides is not None else (max(r[0] for r in rows) if rows else 1)
    out: dict = {"slides": [], "elements": []}
    for i in range(1, n + 1):
        out["slides"].append({"x": 0, "y": (i - 1) * (900 + 36), "w": 1600, "h": 900})
    for slide_no, top, bottom in rows:
        base = out["slides"][slide_no - 1]["y"]
        out["elements"].append({"id": f"s{slide_no}.title", "slide": slide_no, "role": roles[0],
                                "x": 84, "y": base + top, "w": 800, "h": 40,
                                "intendedText": "t", "fontSize": 84})
        out["elements"].append({"id": f"s{slide_no}.bullet.0", "slide": slide_no, "role": roles[-1],
                                "x": 84, "y": base + bottom - 30, "w": 800, "h": 30,
                                "intendedText": "b", "fontSize": 32})
        # 页脚固定在底部：它**不该**被算进内容占位（算进去每页都显得装满）
        out["elements"].append({"id": f"s{slide_no}.foot", "slide": slide_no, "role": "foot",
                                "x": 84, "y": base + 828, "w": 200, "h": 20,
                                "intendedText": "f", "fontSize": 20})
    return out


class TestOverflowAndSparsenessAreDifferentThings(unittest.TestCase):
    """回归：`fits`（硬对错）与 `density`（质量信号）必须是**两个**判据。"""

    def _analyze(self, rows, slides=None) -> dict:
        return fit.analyze(_fake_measured(rows, slides), {1: {"kind": "content-text", "count": None}},
                           {"title": "t"})

    def test_sparse_page_still_counts_as_fitting(self) -> None:
        """占了 30% 的页是**装得下**的 —— 它只是稀疏。第一版在这里判成"装不下"。"""
        row = self._analyze([(1, fit.BAND_TOP, fit.BAND_TOP + 200)])["candidates"][0]
        self.assertTrue(row["fits"], "稀疏的页被当成了装不下（这正是那个真 bug）")
        self.assertEqual(row["overflow"], 0, "装得下时 overflow 不该是个负数")
        self.assertLess(row["density"], fit.DEAD_SPACE, "密度应该报出“偏稀”")

    def test_overflow_page_does_not_fit_and_reports_the_excess(self) -> None:
        over = 150
        row = self._analyze([(1, fit.BAND_TOP, fit.BAND_BOTTOM + over)])["candidates"][0]
        self.assertFalse(row["fits"])
        self.assertAlmostEqual(row["overflow"], over, places=1)

    def test_the_footer_is_not_content(self) -> None:
        """内容只到 300px 时，密度要按内容算 —— 页脚在 828 不许把它撑满。"""
        row = self._analyze([(1, fit.BAND_TOP, fit.BAND_TOP + 168)])["candidates"][0]
        self.assertLess(row["density"], 0.3, "页脚被算进内容占位了")

    def test_slide_offset_is_normalized(self) -> None:
        """第 2 页的坐标带整页偏移 —— 归一化错了它就会被判成"越出下缘"。"""
        rows = [(1, fit.BAND_TOP, fit.BAND_TOP + 600)]
        result = fit.analyze(_fake_measured(rows, slides=1), {1: {"kind": "content-text",
                                                                "count": None}},
                             {"title": "t"})
        first = result["candidates"][0]
        rows2 = [(1, fit.BAND_TOP, fit.BAND_TOP + 600), (2, fit.BAND_TOP, fit.BAND_TOP + 600)]
        result2 = fit.analyze(_fake_measured(rows2, slides=2),
                              {1: {"kind": "content-text", "count": None},
                               2: {"kind": "content-text", "count": None}}, {"title": "t"})
        self.assertEqual([c["density"] for c in result["candidates"]],
                         [c["density"] for c in result2["candidates"]][:1])
        for row in result2["candidates"]:
            self.assertTrue(row["fits"], f"第 {row['kind']} 页因偏移被判成不通过")


class TestSplitEven(unittest.TestCase):
    def test_remainder_goes_to_the_first_columns(self) -> None:
        self.assertEqual(fit._split_even([1, 2, 3, 4, 5], 2), [[1, 2, 3], [4, 5]])

    def test_everything_lands_somewhere(self) -> None:
        for n in range(2, 13):
            parts = fit._split_even(list(range(n)), 2)
            self.assertEqual(sum(len(p) for p in parts), n)
            self.assertLessEqual(abs(len(parts[0]) - len(parts[1])), 1)


class TestFitEndToEnd(unittest.TestCase):
    """真渲真量跑一次，多个断言 —— 每次试排都要开一次 Chrome，别让测试重复付这个钱。

    这一份内容（16 条）正好同时覆盖两种判定：`content-text` 溢出、`two-column` 装得下。
    """

    CONTENT = {"title": "年度复盘", "bullets": [
        f"第 {i} 条：这一年的判断" for i in range(1, 17)]}

    @classmethod
    def setUpClass(cls) -> None:
        deck, labels = fit.build_probe_deck(cls.CONTENT)
        deck["deck"].update({"style": render.DEFAULT_STYLE, "colorSet": "blue", "seed": 1})
        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        path = os.path.join(cls._tmp.name, "fit.html")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(render.render(deck))
        cls.measured = _load("measure").measure(path)
        cls.result = fit.analyze(cls.measured, labels, cls.CONTENT)

    def _row(self, kind: str) -> dict:
        for c in self.result["candidates"]:
            if c["kind"] == kind:
                return c
        raise AssertionError(f"候选里没有 {kind}：{[c['kind'] for c in self.result['candidates']]}")

    def test_dense_content_overflows_one_layout_and_fits_another(self) -> None:
        """16 条短条目：这正是试排存在的意义 —— 一种装不下，另一种装得下。

        ⚠️ 这个夹具是**量过的**，不是拍脑袋的：第一版我用的是 27 字的条目，
        想当然以为 `two-column` 能装下，结果它一起溢出了 —— 于是“一种装不下、
        另一种装得下”这个卖点根本没被验到。试排工具的第一条用法就是先用它试
        自己的夹具（`_row` 报出来的数字就是实测值）。
        """
        self.assertFalse(self._row("content-text")["fits"], "16 条居然在 content-text 里装下了")
        self.assertTrue(self._row("two-column")["fits"], "two-column 也没装下 —— 夹具前提变了")

    def test_measurement_is_real_not_estimated(self) -> None:
        """量出来的内容底要**真的**超过正文带底 —— 与它报的溢出量对得上。"""
        row = self._row("content-text")
        self.assertGreater(row["bottom"], fit.BAND_BOTTOM)
        self.assertAlmostEqual(row["overflow"], row["bottom"] - fit.BAND_BOTTOM, places=1)

    def test_item_ceiling_is_a_measured_number(self) -> None:
        """条目数上限要是实测出来的，且小于给的总数（否则它只是个扫描边界）。"""
        self.assertIn("content-text", self.result["max_items"])
        cap = self.result["max_items"]["content-text"]
        self.assertGreater(cap, 0)
        self.assertLess(cap, len(self.CONTENT["bullets"]),
                        "上限等于总条数 —— 那说明溢出的是夹具，不是版式")
        self.assertNotIn("content-text", self.result["capped"],
                         "content-text 报到了扫描上限 —— 那个数字就不再是上限了")

    def test_report_ranks_by_score_not_fullness(self) -> None:
        """建议按**多目标评分**给 —— 密度只是留白维度的输入，不是优化目标。

        反面钉住旧病：不再出现"把正文带用得最满"这种奖励拥挤的措辞，
        也不再给"两页合一 / 写长一点"这种消灭留白的建议。
        """
        text = fit.report(self.result, self.CONTENT, render.DEFAULT_STYLE, None)
        fitting = [c for c in self.result["candidates"] if c["fits"]]
        self.assertTrue(fitting)
        self.assertIn("candidate score", text)
        self.assertNotIn("用得最满", text, "还在按密度最大化建议 —— 旧目标函数没死透")
        self.assertNotIn("拆页", text, "有装得下的版式却建议拆页")

    def test_crowded_candidate_loses_to_comfort_band(self) -> None:
        """占带 >85% 的拥挤候选要输给舒适带候选 —— 惩罚真实生效。"""
        result = {"candidates": [
            {"kind": "content-text", "bottom": 820.0, "fits": True,
             "overflow": 0.0, "density": 0.94},
            {"kind": "two-column", "bottom": 640.0, "fits": True,
             "overflow": 0.0, "density": 0.62}],
            "max_items": {}, "capped": []}
        content = {"title": "T", "bullets": [f"条目{i}" for i in range(7)]}
        text = fit.report(result, content, render.DEFAULT_STYLE, None)
        self.assertIn("two-column", text.split("建议")[1],
                      "拥挤候选（94%）赢了舒适带候选（62%）—— 惩罚没生效")
        self.assertIn("拥挤", text)

    def test_whitespace_score_peaks_in_comfort_band(self) -> None:
        """留白分：舒适带 45-75% 满分；稀按比例衰减；挤到 100% 归零。"""
        self.assertEqual(fit._whitespace_score(0.60), 1.0)
        self.assertLess(fit._whitespace_score(0.30), 0.7)
        self.assertEqual(fit._whitespace_score(1.0), 0.0)

    def test_sparse_advice_never_says_fill_the_page(self) -> None:
        """全偏稀时的建议：不许出现"填满/写长/合成一页"这类消灭留白的话。"""
        result = {"candidates": [
            {"kind": "content-text", "bottom": 400.0, "fits": True,
             "overflow": 0.0, "density": 0.40}],
            "max_items": {}, "capped": []}
        text = fit.report(result, {"title": "T", "bullets": ["a", "b"]},
                          render.DEFAULT_STYLE, None)
        self.assertIn("不要为填满页面加内容", text)
        self.assertNotIn("写长", text)
        self.assertNotIn("合成一页", text)

    def test_report_says_split_when_nothing_fits(self) -> None:
        """全都装不下时才说拆页，且要带“单页最多几条”。

        这条走**纯函数**（喂一个 analyze 形状的结果）而不是再开一次浏览器：
        要断言的是 report 的分支，不是测量 —— 而测量贵。端到端那条已经盖住了。
        """
        result = {"candidates": [
            {"kind": "content-text", "bottom": 1600.0, "fits": False,
             "overflow": 776.0, "density": 2.12},
            {"kind": "two-column", "bottom": 1700.0, "fits": False,
             "overflow": 876.0, "density": 2.27}],
            "max_items": {"content-text": 12}, "capped": []}
        text = fit.report(result, {"title": "T", "bullets": ["x"] * 30},
                          "swiss-grid", None)
        self.assertIn("拆页", text)
        self.assertIn("12 条", text)
        self.assertIn("3 页", text, "30 条 / 单页 12 条 = 3 页")

    def test_verdicts_never_invent_a_layout(self) -> None:
        """报的版式必须是真渲过的那些，不能出现没试过的版式名。

        "content-image:even" 这类是**家族变体**（探针真渲过），拆前缀对家族名。
        """
        for c in self.result["candidates"]:
            self.assertIn(c["kind"].split(":")[0], fit.CANDIDATES)

    def test_probe_deck_includes_image_variants(self) -> None:
        """content-image 是家族不是单一版式：探针把 visual-left / even 摆进同一份
        产物 —— CandidateScore 有真候选可比，compile 的自动选变体从这里取数。"""
        _deck, labels = fit.build_probe_deck(
            {"title": "T", "bullets": ["a", "b", "c"], "image": "x.png"})
        kinds = [v["kind"] for v in labels.values()]
        self.assertIn("content-image:visual-left", kinds)
        self.assertIn("content-image:even", kinds)
        self.assertIn("content-image:hero", kinds)


class TestFitCli(unittest.TestCase):
    def test_exit_code_reflects_whether_anything_fits(self) -> None:
        ok = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "fit.py"), "--title", "T",
             "--bullet", "一二三四五六", "--style", "swiss-grid"],
            capture_output=True, text=True, cwd=SKILL)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)

    def test_missing_source_slide_is_reported_not_crashed(self) -> None:
        bad = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "fit.py"),
             "--from-spec", DEMO, "--slide", "999"],
            capture_output=True, text=True, cwd=SKILL)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("越界", bad.stdout + bad.stderr)

    def test_from_spec_carries_the_color_set(self) -> None:
        """回归：第一版没把 spec 的 colorSet 带过去，壳直接报“colorSet=None”。

        这条用真实 spec 跑 —— 假夹具不会暴露"少带了一个字段"。
        """
        run = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "fit.py"),
             "--from-spec", DEMO, "--slide", "2"],
            capture_output=True, text=True, cwd=SKILL)
        self.assertNotIn("colorSet", run.stdout + run.stderr,
                         "试排把 colorSet 丢了")
        self.assertIn("版式候选", run.stdout)


class TestDeckShapeChecks(unittest.TestCase):
    """deck 级检查：空内容**阻塞**，形状问题**提示**。"""

    @classmethod
    def setUpClass(cls) -> None:
        with open(DEMO, encoding="utf-8") as fh:
            cls.spec = json.load(fh)

    def _deck(self, slides) -> dict:
        deck = json.loads(json.dumps(self.spec["deck"]))
        deck["slides"] = slides
        return deck

    def test_empty_bullet_blocks(self) -> None:
        deck = self._deck([{"type": "title", "title": "封面"},
                           {"type": "content-text", "title": "T", "bullets": ["a", "", "  "]}])
        problems = check_mod._check_empty_content(deck)
        self.assertEqual(len(problems), 2)                     # 空串与纯空白都算
        self.assertTrue(all("第 2 页" in p for p in problems))

    def test_empty_title_blocks(self) -> None:
        deck = self._deck([{"type": "title", "title": ""},
                           {"type": "content-text", "title": "T", "bullets": ["a"]}])
        problems = check_mod._check_empty_content(deck)
        self.assertTrue(any("第 1 页标题是空的" in p for p in problems), problems)

    def test_empty_nested_items_block(self) -> None:
        deck = self._deck([
            {"type": "title", "title": "封面"},
            {"type": "two-column", "title": "T", "columns": [
                {"title": "a", "bullets": ["x"]}, {"title": "b", "bullets": [""]}]},
            {"type": "timeline", "title": "T", "nodes": [{"label": "", "note": "n"}]},
            {"type": "chart", "title": "T", "data": [{"label": " ", "value": 1}]},
        ])
        problems = check_mod._check_empty_content(deck)
        self.assertEqual(len(problems), 3, problems)

    def test_clean_deck_reports_nothing(self) -> None:
        """反面对照：正常内容不许报 —— 否则上面几条可能只是"永远会报"。"""
        deck = self._deck([{"type": "title", "title": "封面"},
                           {"type": "content-text", "title": "T", "bullets": ["a"]}])
        self.assertEqual(check_mod._check_empty_content(deck), [])

    def test_missing_cover_is_noted(self) -> None:
        deck = self._deck([{"type": "content-text", "title": "T", "bullets": ["a"]},
                           {"type": "end", "title": "谢谢"}])
        _, notes = check_mod._check_deck_shape({"slides": [], "elements": []}, deck)
        self.assertTrue(any("没有封面" in n for n in notes), notes)

    def test_single_layout_is_noted(self) -> None:
        deck = self._deck([{"type": "title", "title": "封面"}]
                          + [{"type": "content-text", "title": f"T{i}", "bullets": ["a"]}
                             for i in range(4)])
        _, notes = check_mod._check_deck_shape({"slides": [], "elements": []}, deck)
        self.assertTrue(any("构图没有变化" in n for n in notes), notes)

    def test_varied_layouts_are_not_noted(self) -> None:
        deck = self._deck([{"type": "title", "title": "封面"},
                           {"type": "content-text", "title": "a", "bullets": ["x"]},
                           {"type": "two-column", "title": "b", "columns": [
                               {"title": "c", "bullets": ["x"]}, {"title": "d", "bullets": ["y"]}]},
                           {"type": "end", "title": "谢谢"}])
        _, notes = check_mod._check_deck_shape({"slides": [], "elements": []}, deck)
        self.assertEqual([n for n in notes if "构图没有变化" in n], [])


class TestPlateSampleHasNoHardcodedColorSet(unittest.TestCase):
    """回归：`plate.py --sample` 曾经因为写死 `--color-set vivid` 而崩。

    risograph 风格连同它的 `vivid` 色板被删掉之后，那条默认值还在 ——
    README 跑法第 3 步直接 KeyError，而测试全绿（测试都自己传 --color-set）。
    """

    def test_sample_runs_without_a_color_set_argument(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "s.png")
            run = subprocess.run(
                [sys.executable, os.path.join(SCRIPTS, "plate.py"), "--sample", "-o", out],
                capture_output=True, text=True, cwd=SKILL)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("已写出", run.stdout)

    def test_unknown_color_set_is_reported(self) -> None:
        run = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "plate.py"), "--sample",
             "-o", os.path.join(tempfile.gettempdir(), "x.png"), "--color-set", "vivid"],
            capture_output=True, text=True, cwd=SKILL)
        self.assertEqual(run.returncode, 1)
        self.assertIn("vivid", run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()


class TestRecommend(unittest.TestCase):
    """fit.recommend：变体实测推荐 —— compile auto 的数据源（§22 候选测量的第一片）。

    图的高宽比是变体选择的真实输入，所以探针必须带**真图**：
    demo 引用的 sample-treated.png 不在仓库里，这里手写一张最小 PNG
    （800×600，stdlib zlib —— 渲染器要的是能解码的图，不是好看的图）。
    """

    @classmethod
    def setUpClass(cls) -> None:
        import tempfile
        import zlib
        cls.tmp = tempfile.mkdtemp(prefix="deck-rec-")
        w, h = 800, 600
        raw = b"".join(b"\x00" + bytes((200, 80, 60)) * w for _ in range(h))

        def chunk(tag: bytes, data: bytes) -> bytes:
            head = tag + data
            return (len(data).to_bytes(4, "big") + head
                    + (zlib.crc32(head) & 0xFFFFFFFF).to_bytes(4, "big"))

        png = (b"\x89PNG\r\n\x1a\n"
               + chunk(b"IHDR", w.to_bytes(4, "big") + h.to_bytes(4, "big")
                       + b"\x08\x02\x00\x00\x00")
               + chunk(b"IDAT", zlib.compress(raw))
               + chunk(b"IEND", b""))
        with open(os.path.join(cls.tmp, "img.png"), "wb") as fh:
            fh.write(png)

    def test_probe_resolves_image_to_absolute(self) -> None:
        """相对路径必须解析成绝对：探针 HTML 在临时目录，裂图量出来是错的。"""
        spec = {"deck": {"slides": [{"type": "content-image", "title": "t",
                                     "bullets": ["a"], "image": "img.png"}]}}
        probe, labels = fit.build_variant_probe(spec, self.tmp)
        self.assertEqual(len(probe["deck"]["slides"]), 4)   # 三分栏变体 + hero
        self.assertEqual(probe["deck"]["slides"][0]["image"],
                         os.path.join(self.tmp, "img.png"))
        kinds = [m["kind"] for m in labels.values()]
        self.assertIn("content-image:even", kinds)
        self.assertIn("content-image:visual-left", kinds)
        self.assertIn("content-image:hero", kinds)

    def test_probe_empty_without_image_pages(self) -> None:
        probe, _labels = fit.build_variant_probe(
            {"deck": {"slides": [{"type": "content-text", "title": "t",
                                 "bullets": ["a"]}]}}, self.tmp)
        self.assertEqual(probe["deck"]["slides"], [])

    def test_recommend_picks_and_is_deterministic(self) -> None:
        """浏览器实测：结构正确（最佳+两个对手+分数不劣于对手）、同输入恒等。"""
        spec = {"deck": {"title": "变体", "seed": 3, "slides": [
            {"type": "content-image", "title": "图页",
             "bullets": ["要点一", "要点二", "要点三"],
             "image": "img.png", "variant": "auto"}]}}
        probe, labels = fit.build_variant_probe(spec, self.tmp)
        html_path = os.path.join(self.tmp, "probe.html")
        fit.deckio.write_text(html_path, fit.render.render(probe))
        recs = fit.recommend(fit.measure_mod.measure(html_path), labels, spec)
        self.assertEqual(len(recs), 1)
        rec = recs[0]
        self.assertEqual(rec["page"], 1)
        self.assertIn(rec["variant"], fit.render.IMAGE_VARIANTS)
        self.assertEqual(len(rec["alternatives"]), 3)   # 四变体：最佳 + 三个对手
        for alt in rec["alternatives"]:
            self.assertGreaterEqual(rec["score"], alt["score"],
                                    "最佳变体分数反而落后 —— 排序坏了")
        # 纯函数：同一份测量再算一遍必须恒等；重测一次也恒等（确定性链路）
        again = fit.recommend(fit.measure_mod.measure(html_path), labels, spec)
        self.assertEqual(recs, again)


class TestHeroScoring(unittest.TestCase):
    """hero 的评分维度：满图是特性不是拥挤 —— 与文字主导页用不同的留白尺子。"""

    def test_hero_whitespace_peaks_when_full(self) -> None:
        self.assertEqual(fit._hero_whitespace(0.94), 1.0)
        self.assertEqual(fit._hero_whitespace(1.0), 1.0)
        self.assertLess(fit._hero_whitespace(0.4), 0.6)

    def test_hero_scores_fullness_as_feature(self) -> None:
        """占带 93% 的 hero：留白满分、不吃拥挤惩罚（同数字的文字页会吃）。"""
        score, parts, pens = fit.score_candidate(
            {"kind": "content-image:hero", "fits": True, "density": 0.93},
            {"title": "t", "bullets": ["a"], "image": "x.png"})
        self.assertEqual(parts["whitespace"], 1.0)
        self.assertEqual(pens, [])

    def test_hero_semantic_wants_few_bullets(self) -> None:
        """图即陈述：≤2 条满分，≥3 条降分（该用带正文的变体）。"""
        two = fit._semantic_score("content-image:hero",
                                  {"bullets": ["a", "b"], "image": "x"})
        many = fit._semantic_score("content-image:hero",
                                   {"bullets": ["a", "b", "c"], "image": "x"})
        self.assertEqual(two, 1.0)
        self.assertEqual(many, 0.2)

    def test_text_page_still_gets_crowding_penalty(self) -> None:
        """同一数字 93%：文字主导页照吃拥挤惩罚 —— role-aware 不是放水。"""
        _s, _p, pens = fit.score_candidate(
            {"kind": "content-text", "fits": True, "density": 0.93},
            {"title": "t", "bullets": ["a"]})
        self.assertTrue(any("拥挤" in p for p in pens))
