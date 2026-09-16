#!/usr/bin/env python3
"""archify 模仿项的回归测试：showcase 档 / JSON 回执 / 可读性 / cards / sigil / guide。

## 这批用例守什么

本轮从 archify 吸收了六件东西，每件都要有钉子：

1. **showcase 档**（`Outcome.promote`）—— 升级必须发生在调参循环之外、
   返回拷贝不动原值；这几点拆开测，因为在别的实现里它们很容易被悄悄合并
   （比如在 `converged()` 里直接看 quality —— 那会让调参循环对软项失明）。
2. **JSON 回执**（`build_receipt`）—— 结构化诊断的形状：code/severity/
   subject/evidence/suggestedFixes；**回执里同样不许出现参数名**（硬规则不因
   输出格式而松绑）。
3. **可读性下限**（`check_readability`）—— 宽画布投影字号；不阻塞、不进调参。
4. **cards**（`layout.card_rows` + 两个后端）—— 封闭字段集放行、几何单一来源、
   元素带 groupIds（装饰不是节点）。
5. **内置 sigil**（`sigils.py`）—— 不碰素材库就能用；未知名不 fallback；
   宽度真的进了尺寸链（盒子变宽）。
6. **guide**（`scripts/guide.py`）—— 打分推荐稳定；平分不硬选。

跑法：
    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


C = _load("check_layout", os.path.join(SCRIPTS, "check_layout.py"))
L = C.L
V = _load("validate_spec", os.path.join(SCRIPTS, "validate_spec.py"))
SIG = _load("sigils", os.path.join(SCRIPTS, "sigils.py"))
E = _load("emit_excalidraw", os.path.join(SCRIPTS, "emit_excalidraw.py"))
G = _load("guide", os.path.join(SCRIPTS, "guide.py"))


def spec_of(nodes, edges, **extra):
    base = {"type": "architecture",
            "nodes": [{"id": n, "label": n, "kind": "service"} for n in nodes],
            "edges": [{"from": a, "to": b} for a, b in edges]}
    base.update(extra)
    return base


class _Placed:
    def __init__(self, x, y, w=100.0, h=40.0):
        self.x, self.y, self.width, self.height = x, y, w, h


class TestShowcasePromotion(unittest.TestCase):
    """#3 质量两档：升级发生在调参之后、返回拷贝。"""

    def test_promote_returns_copy_and_upgrades_softs(self):
        soft = C.Issue("crossing", False, "a✕b", "测试", advice="拆节点")
        outcome = C.Outcome(issues=[soft, C.Issue("text", True, "x", "脚本 bug")])
        promoted = outcome.promote("showcase")
        self.assertEqual(2, len(promoted.blocking))
        # 原件不动：那条软项在原 outcome 里必须仍是软的（调参循环还要用它判断可调）
        original_crossing = next(i for i in outcome.issues if i.check == "crossing")
        self.assertFalse(original_crossing.blocking,
                         "promote 必须返回拷贝 —— 原 outcome 的软项不能被就地升级")

    def test_standard_is_identity(self):
        outcome = C.Outcome(issues=[C.Issue("crossing", False, "a", "b")])
        self.assertIs(outcome, outcome.promote("standard"))

    def test_readability_and_icon_are_not_promoted(self):
        outcome = C.Outcome(issues=[
            C.Issue("readability", False, "整张图", "太宽"),
            C.Issue("icon", False, "n", "对比度"),
        ])
        self.assertFalse(outcome.promote("showcase").blocking,
                         "readability/icon 不在 showcase 硬集合里")

    def test_unknown_quality_rejected(self):
        outcome = C.Outcome()
        with self.assertRaises(ValueError):
            outcome.promote("ultra")

    def test_tuning_uses_raw_outcome(self):
        """showcase 升级不得进入调参循环 —— 软项仍然是可调的。"""
        spec = spec_of(["a", "b", "c"], [("a", "b"), ("b", "c")])
        boxes = L.boxes_from_spec(spec)
        _result, outcome, attempts = C.layout_with_retry(spec, boxes)
        self.assertIsInstance(outcome, C.Outcome)
        # layout_with_retry 的返回值必须是"未升级"的：软项在场时 converged 仍可能为真
        for issue in outcome.issues:
            if issue.check in C.SHOWCASE_HARD:
                self.assertFalse(issue.blocking or True and issue.blocking,
                                 "调参循环内部不应看到被升级的软项")


class TestJsonReceipt(unittest.TestCase):
    """#1 JSON 诊断回执的形状与措辞。"""

    def _receipt(self, issues):
        outcome = C.Outcome(issues=issues)
        result = type("R", (), {"real_nodes": lambda s: {}, "edges": [],
                                "crossings": 0})()
        attempt = C.Attempt(round_no=0, params=dict(L.DEFAULT_PARAMS), outcome=outcome)
        return C.build_receipt({}, result, [attempt], outcome, "showcase")

    def test_shape(self):
        r = self._receipt([C.Issue("gap", True, "a ↔ b", "间隙 4px", advice="拆节点",
                                   evidence={"gapPx": 4})])
        self.assertFalse(r["ok"])
        self.assertEqual("showcase", r["quality"])
        d = r["diagnostics"][0]
        self.assertEqual("layout/gap", d["code"])
        self.assertEqual("error", d["severity"])
        self.assertEqual({"gapPx": 4}, d["evidence"])
        self.assertEqual(["拆节点"], d["suggestedFixes"])
        self.assertIn({"name": "gap", "ok": False}, r["checks"])
        self.assertIn({"name": "crossing", "ok": True}, r["checks"])

    def test_soft_issue_is_warning_severity(self):
        r = self._receipt([C.Issue("bend", False, "a→b", "5 个折点")])
        self.assertEqual("warning", r["diagnostics"][0]["severity"])
        self.assertEqual([], r["diagnostics"][0]["suggestedFixes"])

    def test_no_param_names_in_receipt(self):
        """回执与人读报告同一条规矩：参数名不出现。"""
        r = self._receipt([C.Issue("gap", True, "a ↔ b", "间隙 4px", advice="拆节点",
                                   evidence={"gapPx": 4})])
        text = json.dumps(r, ensure_ascii=False)
        for name in C.PARAM_SPOKEN:
            self.assertNotIn(name, text)


class TestReadability(unittest.TestCase):
    """#5 桌面可读性：宽画布投影字号。"""

    def test_narrow_canvas_is_quiet(self):
        placed = {"a": _Placed(0, 0), "b": _Placed(700, 0)}
        result = type("R", (), {"real_nodes": lambda s: placed, "edges": [],
                                "crossings": 0})()
        self.assertEqual([], C.check_readability({}, result))

    def test_wide_canvas_reports_without_blocking(self):
        placed = {"a": _Placed(0, 0), "b": _Placed(2400, 0)}
        result = type("R", (), {"real_nodes": lambda s: placed, "edges": [],
                                "crossings": 0})()
        issues = C.check_readability({}, result)
        self.assertEqual(1, len(issues))
        self.assertFalse(issues[0].blocking)
        self.assertNotIn(issues[0].check, C.STEPPABLE,
                         "可读性不进调参：加大间距只会让画布更宽")

    def test_threshold_boundary(self):
        # 12px × 960/1920 = 6px —— 恰好在下限上，不该报
        placed = {"a": _Placed(0, 0), "b": _Placed(1820, 0, 100, 40)}
        result = type("R", (), {"real_nodes": lambda s: placed, "edges": [],
                                "crossings": 0})()
        self.assertEqual([], C.check_readability({}, result))


class TestCards(unittest.TestCase):
    """#8 cards：规格契约 + 几何单一来源 + 元素形态。"""

    def test_valid_cards_pass_validation(self):
        spec = spec_of(["a", "b"], [("a", "b")],
                       cards=[{"title": "说明", "items": ["一条", "两条"]}])
        self.assertEqual([], V.validate(spec).errors)

    def test_unknown_card_field_fails(self):
        spec = spec_of(["a", "b"], [("a", "b")],
                       cards=[{"title": "t", "items": ["x"], "color": "#fff"}])
        errors = V.validate(spec).errors
        self.assertTrue(any(e["code"] == "UNKNOWN_FIELD" for e in errors),
                        "cards 也是封闭字段集")

    def test_empty_items_fail(self):
        spec = spec_of(["a", "b"], [("a", "b")], cards=[{"title": "t", "items": []}])
        self.assertTrue(any(e["code"] == "MISSING_CARD_ITEMS" for e in V.validate(spec).errors))

    def test_card_rows_lays_out_below_content(self):
        spec = spec_of(["a", "b"], [("a", "b")],
                       cards=[{"title": "一", "items": ["甲"]},
                              {"title": "二", "items": ["乙"]}])
        rows = L.card_rows(spec, 0.0, 900.0, 200.0)
        self.assertEqual(2, len(rows))
        self.assertGreaterEqual(rows[0]["y"], 200.0 + L.CARD_GAP_BELOW)
        # 同行两张卡不重叠
        first, second = sorted(rows, key=lambda c: c["x"])
        self.assertLessEqual(first["x"] + first["width"] + L.CARD_GAP_BETWEEN,
                             second["x"])

    def test_scene_contains_card_elements_with_group_ids(self):
        spec = spec_of(["a", "b"], [("a", "b")],
                       cards=[{"title": "说明", "items": ["一条"]}])
        scene, _result, outcome, _attempts = E.emit(spec)
        self.assertFalse(outcome.blocking)
        cards = [e for e in scene["elements"] if str(e["id"]).startswith("card-")]
        self.assertTrue(cards, "场景里应有卡片元素")
        for el in cards:
            self.assertTrue(el.get("groupIds"), "卡片是装饰，必须挂 groupIds")

    def test_no_cards_means_no_card_elements(self):
        scene, _r, _o, _a = E.emit(spec_of(["a", "b"], [("a", "b")]))
        self.assertEqual([], [e for e in scene["elements"]
                              if str(e["id"]).startswith("card-")])


class TestBuiltinSigils(unittest.TestCase):
    """#9 内置 sigil：不碰素材库、未知名不 fallback、宽度进尺寸链。"""

    def test_catalog_and_aliases(self):
        for name in ("user", "database", "queue", "shield", "api"):
            self.assertTrue(SIG.is_builtin(name))
        self.assertTrue(SIG.is_builtin("client"))       # 别名
        self.assertFalse(SIG.is_builtin("不存在的名字"))

    def test_glyph_unknown_raises(self):
        with self.assertRaises(KeyError):
            SIG.glyph("不存在的名字", "#000000")

    def test_all_glyphs_have_geometry(self):
        for name in sorted(SIG.NAMES):
            els = SIG.glyph(name, "#000000")
            self.assertTrue(els)
            for el in els:
                self.assertIn(el["type"], ("line", "ellipse", "rectangle"))

    def test_builtin_icon_needs_no_library(self):
        """全部图标都是内置名时，load_icons 完全不接触素材库路径。"""
        spec = spec_of(["a", "b"], [("a", "b")])
        spec["nodes"][0]["icon"] = "database"
        spec["nodes"][1]["icon"] = "api"
        # library 参数不传、且把环境变量清掉 —— 能过就说明没走库
        old = os.environ.pop("EXCALIDRAW_LIBRARY", None)
        try:
            lookup, sizes, _heights = E.load_icons(spec)
            self.assertIsNotNone(lookup)
            self.assertIn("database", lookup)
            self.assertIn("a", sizes, "内置图标也要进尺寸链（盒子加宽）")
        finally:
            if old is not None:
                os.environ["EXCALIDRAW_LIBRARY"] = old

    def test_sigil_widens_the_node_box(self):
        plain = L.boxes_from_spec(spec_of(["a"], []))["a"]
        with_icon = dict(spec_of(["a"], []))
        with_icon["nodes"][0]["icon"] = "database"
        got = L.boxes_from_spec(with_icon, {"a": (24.0, 24.0)})["a"]
        self.assertGreater(got.width, plain.width,
                           "图标（含内置 sigil）是外部尺寸来源，必须加宽盒子")


class TestGuide(unittest.TestCase):
    """#10 场景路由：打分稳定、平分不硬选。"""

    def test_flow_wins_for_workflow_text(self):
        rec = G.recommend("审批通过后部署，失败则回滚重试")
        self.assertEqual("flow", rec["recommended"])
        self.assertEqual("TB", rec["direction"])

    def test_dependency_wins_for_import_text(self):
        self.assertEqual("dependency", G.recommend("模块之间的 import 依赖关系")["recommended"])

    def test_state_wins_for_lifecycle_text(self):
        self.assertEqual("state", G.recommend("订单生命周期里的状态转移与终态")["recommended"])

    def test_no_signal_recommends_nothing(self):
        rec = G.recommend("zzz qqq")
        self.assertIsNone(rec["recommended"])

    def test_scoring_is_deterministic(self):
        self.assertEqual(G.score("画个状态机"), G.score("画个状态机"))


if __name__ == "__main__":
    unittest.main()
