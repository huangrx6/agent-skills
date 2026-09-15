#!/usr/bin/env python3
"""validate_spec.py 的回归测试：字段集必须**真的**封闭。

## 为什么这条要单独测

`check.py` 只主动拦 `color` 一个字段，其余未知键是**静默忽略**的（这一点我实测过：
塞 `fontSize` / `x` / `y` / `bogusTop` 进去，产物毫无变化、也不报错）。
于是"字段集封闭"这件事只由 `validate_spec.py` 兜着 —— 一个只会说 ✓ 的校验器和
没有校验器在结果上一样，所以下面每条都是**造一个越界样例**，断言它被指名报出来。

反向也测：合法的 spec（demo + 七种版式各一页）必须过 —— 校验器不能对什么都说违规。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/deck-authoring/test_validate_spec.py
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")
TOKENS = os.path.join(SKILL, "styles", "swiss-grid", "style.json")
DEMO = os.path.join(SKILL, "dev-tools", "demo.spec.json")


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


vs = _load("_deck_test_validate_spec", os.path.join(SCRIPTS, "validate_spec.py"))

VALID_SLIDES = [
    {"type": "title", "title": "T", "subtitle": "s"},
    {"type": "content-text", "title": "C", "bullets": ["a"]},
    {"type": "content-image", "title": "I", "bullets": ["a"], "image": "x.png"},
    {"type": "two-column", "title": "W",
     "columns": [{"title": "A", "bullets": ["a"]}, {"title": "B", "bullets": ["b"]}]},
    {"type": "timeline", "title": "L", "nodes": [{"label": "Q1", "note": "n"}]},
    {"type": "chart", "title": "G", "data": [{"label": "A", "value": 10}], "unit": "%"},
    {"type": "end", "title": "E"},
]


def _spec(slides=None) -> dict:
    # 色板名**不写死**：从真实的风格 token 里取。写死过 "vivid"，孔版那套一删
    # 这里就开始报 BAD_COLOR_SET —— 于是“合法 spec 必须全过”这条用例变成在报
    # 一个与本意无关的错。
    with open(TOKENS, encoding="utf-8") as fh:
        color_set = next(iter(json.load(fh)["colorSets"]))
    return {"deck": {"colorSet": color_set, "seed": 7, "title": "t",
                     "slides": copy.deepcopy(slides or VALID_SLIDES)}}


class TestValidateSpec(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with open(TOKENS, encoding="utf-8") as fh:
            cls.color_sets = set(json.load(fh)["colorSets"])

    def _codes(self, spec: dict) -> set[str]:
        """跑校验，返回所有 error 的 code。"""
        return {i["code"] for i in vs.validate(spec, self.color_sets).errors}

    def _messages(self, spec: dict) -> str:
        return " ".join(i["message"] for i in vs.validate(spec, self.color_sets).items)

    # ── 正向：合法的必须过 ────────────────────────────────────────────────

    def test_demo_spec_passes(self) -> None:
        with open(DEMO, encoding="utf-8") as fh:
            demo = json.load(fh)
        self.assertEqual(vs.validate(demo, self.color_sets).errors, [],
                         "仓库自带的 demo spec 本应通过")

    def test_all_documented_slide_types_pass(self) -> None:
        """七种版式各来一页，必须全过 —— 校验器不能对合法输入也报。"""
        self.assertEqual(self._codes(_spec()), set(),
                         f"合法 spec 被判违规：{self._messages(_spec())}")

    # ── 反向：越界必须被指名报出 ──────────────────────────────────────────

    def test_unknown_deck_field_is_rejected(self) -> None:
        bad = _spec()
        bad["deck"]["bogusTop"] = 123
        self.assertIn("UNKNOWN_FIELD", self._codes(bad))

    def test_unknown_slide_field_is_rejected(self) -> None:
        bad = _spec()
        bad["deck"]["slides"][0]["whatever"] = 1
        self.assertIn("UNKNOWN_FIELD", self._codes(bad))

    def test_coordinate_fields_get_targeted_error(self) -> None:
        """坐标要报成 COORD_FIELD（专门说明），不是笼统的 UNKNOWN_FIELD。"""
        for key in ("x", "y", "dx", "rotation", "width"):
            with self.subTest(field=key):
                bad = _spec()
                bad["deck"]["slides"][0][key] = 1
                self.assertIn("COORD_FIELD", self._codes(bad),
                              f"{key} 应被当作坐标字段报出来")

    def test_size_fields_get_targeted_error(self) -> None:
        for key in ("fontSize", "size", "font"):
            with self.subTest(field=key):
                bad = _spec()
                bad["deck"]["slides"][0][key] = 1
                self.assertIn("SIZE_FIELD", self._codes(bad),
                              f"{key} 应被当作字号字段报出来")

    def test_color_value_fields_get_targeted_error(self) -> None:
        """主/副色 / 叠印墨这些**名字**也不能出现在 spec 里。"""
        for key in ("primary", "secondary", "background", "ink", "inkText"):
            with self.subTest(field=key):
                bad = _spec()
                bad["deck"]["slides"][0][key] = "#FF0000"
                self.assertIn("COLOR_FIELD", self._codes(bad),
                              f"{key} 应被当作色值字段报出来")

    def test_color_must_be_overprint(self) -> None:
        """`color` 是唯一允许的"样式"字段，且只接受 "overprint"。"""
        ok = _spec()
        ok["deck"]["slides"][0]["color"] = "overprint"
        self.assertEqual(self._codes(ok), set(), "color='overprint' 应当合法")

        bad = _spec()
        bad["deck"]["slides"][0]["color"] = "#FF0000"
        self.assertIn("BAD_COLOR", self._codes(bad))

    def test_unknown_slide_type_is_rejected(self) -> None:
        bad = _spec()
        bad["deck"]["slides"][0]["type"] = "not-a-real-type"
        self.assertIn("BAD_TYPE", self._codes(bad))

    def test_unknown_color_set_is_rejected(self) -> None:
        bad = _spec()
        bad["deck"]["colorSet"] = "no-such-palette"
        self.assertIn("BAD_COLOR_SET", self._codes(bad))

    def test_nested_item_unknown_field_is_rejected(self) -> None:
        """嵌套列表也要管：columns / nodes / data 的元素字段同样是封闭的。"""
        cases = [
            ("columns", 3, "extra"),   # index 3 是 two-column 页
            ("nodes", 4, "extra"),     # index 4 是 timeline 页
            ("data", 5, "extra"),      # index 5 是 chart 页
        ]
        for key, index, field in cases:
            with self.subTest(list_key=key):
                bad = _spec()
                bad["deck"]["slides"][index][key][0][field] = 1
                self.assertIn("UNKNOWN_FIELD", self._codes(bad),
                              f"{key}[0].{field} 没有被报出来")

    def test_missing_tokens_skips_colorset_check_not_whole_validation(self) -> None:
        """读不到 token 时只跳过 colorSet 那一条，其余照样验 —— 别整份放行。"""
        bad = _spec()
        bad["deck"]["slides"][0]["fontSize"] = 120
        codes = {i["code"] for i in vs.validate(bad, None).errors}
        self.assertIn("SIZE_FIELD", codes, "color_sets=None 时不该把整份 spec 放过去")
        self.assertNotIn("BAD_COLOR_SET", codes)


if __name__ == "__main__":
    unittest.main()
