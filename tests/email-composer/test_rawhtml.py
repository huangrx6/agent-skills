"""原始 HTML 模板：标题、纯文本提取与兼容性校验。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parents[1] / "skills" / "email-composer" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from email_composer import rawhtml  # noqa: E402

HTML = """<!DOCTYPE html>
<html><head><title>排班通知｜{{name}}</title></head>
<body>
<h1>排班通知</h1>
<p>负责人：<strong>{{name}}</strong></p>
<ul><li>时段一</li><li>时段二</li></ul>
<table><tr><td>时段</td><td>人员</td></tr><tr><td>20:00</td><td>张工</td></tr></table>
<img src="https://example.com/a.png" alt="排班表" width="600">
<a href="https://example.com/x">详情</a>
</body></html>
"""


class TestExtraction(unittest.TestCase):
    def test_title(self):
        self.assertEqual("排班通知｜{{name}}", rawhtml.extract_title(HTML))
        self.assertEqual("A & B", rawhtml.extract_title("<title>A &amp; B</title>"))

    def test_text_keeps_structure_and_skips_head(self):
        text = rawhtml.html_to_text(HTML)
        self.assertNotIn("DOCTYPE", text)
        self.assertNotIn("排班通知｜{{name}}", text)
        self.assertIn("负责人：{{name}}", text)
        self.assertIn("- 时段一", text)
        self.assertIn("时段 | 人员", text)
        self.assertIn("20:00 | 张工", text)
        self.assertIn("[图片] 排班表", text)
        self.assertIn("详情（https://example.com/x）", text)

    def test_auto_vars(self):
        self.assertEqual(
            {"name": {"required": True, "description": "", "example": ""}},
            rawhtml.auto_vars(HTML),
        )


class TestValidation(unittest.TestCase):
    def report(self, html=HTML, subject="排班通知", to="a@example.com"):
        text = rawhtml.html_to_text(html)
        return rawhtml.validate_html_template(html, text, subject, to)

    def test_clean(self):
        report = self.report(HTML.replace("{{name}}", "客服"))
        self.assertTrue(report["ok"], report["blocking"])
        self.assertEqual([], report["blocking"])
        self.assertEqual("html", report["stats"]["kind"])

    def test_unfilled_variable_blocks(self):
        self.assertIn(
            "unfilled_variable", {item["code"] for item in self.report()["blocking"]}
        )

    def test_width_and_alt(self):
        html = HTML.replace('width="600"', 'width="700"').replace('alt="排班表"', "")
        report = self.report(html)
        codes = {item["code"] for item in report["blocking"]}
        self.assertIn("html_width", codes)
        self.assertIn("image_alt", codes)

    def test_placeholder_and_subject(self):
        report = self.report(HTML + "<p>【待填：附件名】</p>", subject="")
        codes = {item["code"] for item in report["blocking"]}
        self.assertIn("placeholder", codes)
        self.assertIn("subject_missing", codes)

    def test_forbidden_construct(self):
        report = self.report(HTML + '<div style="display:flex">x</div>')
        self.assertIn("html_forbidden", {item["code"] for item in report["blocking"]})

    def test_exclamation_warning(self):
        report = self.report(HTML.replace("排班通知", "排班通知！"))
        self.assertIn("exclamation", {item["code"] for item in report["warnings"]})


if __name__ == "__main__":
    unittest.main()
