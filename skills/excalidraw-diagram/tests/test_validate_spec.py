#!/usr/bin/env python3
"""validate_spec.py 的回归测试。

为什么需要：这个校验器守的是**内容层**，而内容层最危险的失败是"字段悄悄多出来"。

前作 `draw-excalidraw` 的 schema 里有 `nodes[].x` / `y` / `width` / `height`，
并且 `layout.engine: "manual"` 会**直接用填的坐标**。所以本 skill 把字段集写成封闭的，
未知字段判失败而不是忽略 —— 否则有人"顺手加个可选 x/y"就能让病根原样复发，
而且不会有人发现，因为加字段的人会觉得自己只是加了可选功能。

下面的 `test_coordinate_field_is_rejected` 和 `test_layout_param_is_rejected` 是这一层的核心防线。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/test_validate_spec.py
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
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
VALIDATE_SPEC = os.path.join(SCRIPTS, "validate_spec.py")
PALETTE = os.path.join(SCRIPTS, "palette.py")


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    # 先注册再 exec —— 不注册的话被加载模块里的 @dataclass 会炸
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def valid_spec() -> dict:
    return {
        "type": "architecture",
        "title": "鉴权链路",
        "direction": "LR",
        "detail": "standard",
        "groups": [{"id": "edge", "label": "接入层"}],
        "nodes": [
            {"id": "user", "label": "用户", "kind": "client"},
            {"id": "auth", "label": "鉴权服务", "kind": "security", "group": "edge"},
            {"id": "db", "label": "iam_db", "kind": "data", "detail": "users / roles"},
        ],
        "edges": [
            {"from": "user", "to": "auth", "label": "POST /login", "kind": "sync"},
            {"from": "auth", "to": "db", "kind": "data"},
        ],
    }


class ValidateSpecTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load("validate_spec_under_test", VALIDATE_SPEC)
        cls.palette = _load("palette_under_test", PALETTE)

    def codes(self, spec: dict) -> set[str]:
        return {i["code"] for i in self.mod.validate(spec).errors}

    def assert_error(self, spec: dict, code: str, why: str = "") -> None:
        got = self.codes(spec)
        self.assertIn(code, got, f"{why}（实际 errors: {sorted(got)}）")

    # ── 基线 ──
    def test_valid_spec_passes(self):
        self.assertEqual(self.codes(valid_spec()), set())

    # ── 防线 1:坐标字段必须被拒（前作的病根） ──
    def test_coordinate_field_is_rejected(self):
        for field in ("x", "y", "width", "height"):
            with self.subTest(field=field):
                s = valid_spec()
                s["nodes"][1][field] = 120
                self.assert_error(s, "COORD_FIELD",
                                  f"nodes[].{field} 被接受了 —— 一旦能填坐标，模型就会填")

    def test_coordinate_rejection_explains_why(self):
        s = valid_spec()
        s["nodes"][0]["x"] = 10
        msg = " ".join(i["message"] for i in self.mod.validate(s).errors)
        self.assertIn("rank", msg, "报错应指出替代方案（rank / pin），而不是只说未知字段")

    # ── 防线 2:布局参数必须被拒 ──
    def test_layout_param_is_rejected(self):
        s = valid_spec()
        s["layout"] = {"engine": "dagre", "nodeSeparation": 90}
        self.assert_error(s, "LAYOUT_FIELD",
                          "布局参数出现在规格里被接受了 —— 参数只属于脚本")

    def test_top_level_layout_params_rejected(self):
        s = valid_spec()
        s["nodeSeparation"] = 90
        self.assert_error(s, "LAYOUT_FIELD")

    # ── 防线 3:字段集封闭 ──
    def test_unknown_field_is_rejected_not_ignored(self):
        s = valid_spec()
        s["nodes"][0]["colour"] = "#ff0000"
        self.assert_error(s, "UNKNOWN_FIELD", "未知字段被静默忽略了")

    def test_unknown_top_and_edge_fields_rejected(self):
        s = valid_spec()
        s["theme"] = "dark"
        s["edges"][0]["arrowhead"] = "dot"
        got = self.codes(s)
        self.assertIn("UNKNOWN_FIELD", got)

    # ── 防线 4:kind 封闭枚举,未知判失败不 fallback ──
    def test_unknown_kind_is_rejected(self):
        s = valid_spec()
        s["nodes"][1]["kind"] = "queue"          # 模型很容易自己发明
        self.assert_error(s, "UNKNOWN_KIND",
                          "未知 kind 被接受了 —— 这正是 fallback 会悄悄绕过色板校验的场景")

    def test_all_palette_kinds_are_accepted(self):
        for kind in self.palette.KINDS:
            with self.subTest(kind=kind):
                s = valid_spec()
                s["nodes"][1]["kind"] = kind
                self.assertNotIn("UNKNOWN_KIND", self.codes(s))

    def test_kind_error_lists_allowed_values(self):
        s = valid_spec()
        s["nodes"][0]["kind"] = "nope"
        msgs = [i["message"] for i in self.mod.validate(s).errors if i["code"] == "UNKNOWN_KIND"]
        for allowed in self.palette.KINDS:
            self.assertIn(allowed, msgs[0], "报错应列出允许的取值,否则模型只能猜")

    def test_missing_kind_is_rejected(self):
        s = valid_spec()
        del s["nodes"][0]["kind"]
        self.assert_error(s, "MISSING_KIND")

    def test_unknown_edge_kind_rejected(self):
        s = valid_spec()
        s["edges"][0]["kind"] = "telepathy"
        self.assert_error(s, "UNKNOWN_EDGE_KIND")

    # ── 防线 5:引用完整性 ──
    def test_dangling_group_reference(self):
        s = valid_spec()
        s["nodes"][1]["group"] = "nope"
        self.assert_error(s, "UNKNOWN_GROUP")

    def test_dangling_edge_reference(self):
        s = valid_spec()
        s["edges"][0]["to"] = "ghost"
        self.assert_error(s, "DANGLING_EDGE")

    def test_duplicate_node_id(self):
        s = valid_spec()
        s["nodes"][1]["id"] = "user"
        self.assert_error(s, "DUPLICATE_NODE_ID")

    def test_self_loop_rejected(self):
        s = valid_spec()
        s["edges"].append({"from": "auth", "to": "auth"})
        self.assert_error(s, "SELF_LOOP")

    # ── 防线 6:必填与取值域 ──
    def test_missing_required_fields(self):
        for mutate, code in [
            (lambda s: s.pop("type"), "MISSING_TYPE"),
            (lambda s: s.pop("nodes"), "MISSING_NODES"),
            (lambda s: s["nodes"][0].pop("label"), "MISSING_LABEL"),
        ]:
            with self.subTest(code=code):
                s = valid_spec()
                mutate(s)
                self.assert_error(s, code)

    def test_bad_enum_values(self):
        for field, bad, code in [
            ("type", "hologram", "BAD_TYPE"),
            ("direction", "RL", "BAD_DIRECTION"),
            ("detail", "god-tier", "BAD_DETAIL"),
        ]:
            with self.subTest(field=field):
                s = valid_spec()
                s[field] = bad
                self.assert_error(s, code)

    def test_bad_pin_and_rank(self):
        s = valid_spec()
        s["nodes"][0]["pin"] = "center"
        s["nodes"][1]["rank"] = -1
        got = self.codes(s)
        self.assertIn("BAD_PIN", got)
        self.assertIn("BAD_RANK", got)

    def test_rank_and_pin_are_accepted(self):
        s = valid_spec()
        s["nodes"][0]["rank"] = 0
        s["nodes"][1]["pin"] = "left"
        self.assertEqual(self.codes(s), set(), "rank / pin 是允许的方向约束,不该被拒")

    # ── CLI 契约 ──
    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            good = os.path.join(d, "good.json")
            bad = os.path.join(d, "bad.json")
            broken = os.path.join(d, "broken.json")
            with open(good, "w", encoding="utf-8") as fh:
                json.dump(valid_spec(), fh, ensure_ascii=False)
            s = valid_spec()
            s["nodes"][0]["x"] = 1
            with open(bad, "w", encoding="utf-8") as fh:
                json.dump(s, fh, ensure_ascii=False)
            with open(broken, "w", encoding="utf-8") as fh:
                fh.write("{ not json")

            for path, want, why in [
                (good, 0, "合法规格应返回 0"),
                (bad, 1, "有 error 应返回 1"),
                (broken, 2, "非法 JSON 应返回 2"),
                (os.path.join(d, "missing.json"), 2, "文件不存在应返回 2"),
            ]:
                with self.subTest(path=os.path.basename(path)):
                    proc = subprocess.run([sys.executable, VALIDATE_SPEC, path],
                                          capture_output=True, text=True)
                    self.assertEqual(proc.returncode, want, why)


if __name__ == "__main__":
    unittest.main(verbosity=2)

class TestTypeEnumHasOneSource(unittest.TestCase):
    """图类型这个枚举只能有一份 —— 两份必然漂移，而且已经漂移过一次。"""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load("validate_spec_under_test", VALIDATE_SPEC)

    def test_whitelist_comes_from_the_layout_module(self):
        layout = self.mod._load_sibling("layout")
        self.assertEqual(set(self.mod.DIAGRAM_TYPES), set(layout.DIRECTION_FOR_TYPE))

    def test_every_accepted_type_has_a_direction(self):
        for name in sorted(self.mod.DIAGRAM_TYPES):
            spec = {"type": name, "nodes": [], "edges": []}
            codes = {i["code"] for i in self.mod.validate(spec).errors}
            self.assertNotIn("BAD_TYPE", codes, f"{name} 被白名单接受但校验报 BAD_TYPE")
