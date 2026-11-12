"""YAML 子集解析与写出：只测本 skill 规格实际用到的写法。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parents[1] / "skills" / "email-composer" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from email_composer import yamlish  # noqa: E402


class TestLoads(unittest.TestCase):
    def test_nested_map_and_list(self):
        data = yamlish.loads(
            "type: approval\n"
            "secondary: [handover, confirm]\n"
            "blocks:\n"
            "  - kind: paragraph\n"
            "    text: 第一段\n"
            "  - kind: table\n"
            "    columns: [项目, 工时]\n"
            "    rows:\n"
            "      - [发布, \"3.5\"]\n"
        )
        self.assertEqual("approval", data["type"])
        self.assertEqual(["handover", "confirm"], data["secondary"])
        self.assertEqual("paragraph", data["blocks"][0]["kind"])
        self.assertEqual(["发布", "3.5"], data["blocks"][1]["rows"][0])

    def test_plain_scalar_keeps_colon_in_time(self):
        data = yamlish.loads("subject: 上线（2026-11-20 20:00）\n")
        self.assertEqual("上线（2026-11-20 20:00）", data["subject"])

    def test_comment_is_stripped_but_not_inside_quotes(self):
        data = yamlish.loads('subject: 发布 # 备注\ntext: "a # b"\n')
        self.assertEqual("发布", data["subject"])
        self.assertEqual("a # b", data["text"])

    def test_block_scalars(self):
        data = yamlish.loads("a: |\n  第一行\n  第二行\nb: >-\n  hello\n  world\n")
        self.assertEqual("第一行\n第二行", data["a"])
        self.assertEqual("hello world", data["b"])

    def test_cjk_folding_does_not_add_space(self):
        data = yamlish.loads("a: >-\n  中文前半，\n  中文后半。\n")
        self.assertEqual("中文前半，中文后半。", data["a"])

    def test_quotes_and_booleans(self):
        data = yamlish.loads("a: 'it''s'\nb: \"x\\ny\"\nc: true\nd: null\ne: 3\n")
        self.assertEqual("it's", data["a"])
        self.assertEqual("x\ny", data["b"])
        self.assertIs(True, data["c"])
        self.assertIsNone(data["d"])
        self.assertEqual(3, data["e"])

    def test_leading_zero_is_a_string(self):
        self.assertEqual("007", yamlish.loads("code: 007\n")["code"])

    def test_tab_indent_is_rejected(self):
        with self.assertRaises(yamlish.YamlError):
            yamlish.loads("a:\n\tb: 1\n")

    def test_anchor_is_rejected(self):
        with self.assertRaises(yamlish.YamlError):
            yamlish.loads("a: &x 1\n")

    def test_unparsed_tail_is_reported(self):
        with self.assertRaises(yamlish.YamlError):
            yamlish.loads("a: 1\n  b: 2\n")


class TestDumps(unittest.TestCase):
    def test_round_trip(self):
        data = {
            "type": "approval",
            "subject": "【申请】上线（2026-11-20 20:00）",
            "blocks": [
                {"kind": "paragraph", "text": "第一段"},
                {"kind": "table", "columns": ["项目", "工时"], "rows": [["发布", "3.5"]]},
            ],
            "facts": ["2026-11-20 20:00", "3.5"],
            "empty": [],
        }
        dumped = yamlish.dumps(data)
        self.assertEqual(data, yamlish.loads(dumped))

    def test_multiline_string_and_numeric_looking_string(self):
        data = {"summary": "第一行\n第二行", "code": "123", "flag": "true"}
        dumped = yamlish.dumps(data)
        self.assertIn("|-", dumped)
        self.assertIn('"123"', dumped)
        self.assertIn('"true"', dumped)
        self.assertEqual(data, yamlish.loads(dumped))


if __name__ == "__main__":
    unittest.main()
