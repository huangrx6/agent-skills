"""渲染：四套预设、三种文本格式、.eml 结构与转义。"""

from __future__ import annotations

import email
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parents[1] / "skills" / "email-composer"
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

from email_composer import render, styles  # noqa: E402
from email_composer.spec import load_spec  # noqa: E402

EXAMPLE = SKILL / "examples" / "approval-release.yaml"


def example():
    return load_spec(str(EXAMPLE))


class TestHtml(unittest.TestCase):
    def setUp(self):
        self.spec = example()
        self.tokens, self.preset, _ = styles.resolve(self.spec)
        self.html = render.render_html(self.spec, self.tokens)

    def test_preset_is_business(self):
        self.assertEqual("business", self.preset)

    def test_layout_is_inline_and_table_based(self):
        self.assertIn('width="640"', self.html)
        self.assertIn('role="presentation"', self.html)
        self.assertNotIn("<style", self.html)
        self.assertNotIn("<script", self.html)
        for forbidden in ("display:flex", "display:grid", "display: flex", "<form", "position:"):
            self.assertNotIn(forbidden, self.html)
        self.assertIn("background-color:#FFFFFF", self.html)

    def test_images_have_alt_and_width(self):
        tags = [tag for tag in self.html.split("<img")[1:]]
        self.assertEqual(3, len(tags))
        for tag in tags:
            self.assertIn('alt="', tag)
            self.assertIn('width="584"', tag)
            self.assertNotIn('alt=""', tag)

    def test_table_and_todo_render(self):
        self.assertIn("工时（人天）", self.html)
        self.assertIn("负责人", self.html)
        self.assertIn("截止时间", self.html)

    def test_html_escapes_content(self):
        spec = example()
        spec["subject"] = "<script>alert(1)</script>"
        tokens, _, _ = styles.resolve(spec)
        html = render.render_html(spec, tokens)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)

    def test_width_override_is_taken_from_tokens(self):
        tokens = dict(self.tokens)
        tokens["width"] = 700
        html = render.render_html(self.spec, tokens)
        self.assertIn('width="700"', html)


class TestText(unittest.TestCase):
    def setUp(self):
        self.text = render.render_text(example())

    def test_subject_and_greeting(self):
        self.assertTrue(self.text.startswith("【主题】"))
        self.assertIn("王总，您好", self.text)

    def test_table_becomes_field_list(self):
        self.assertIn("工时（人天）：3.5", self.text)
        self.assertIn("截止时间：2026-11-18 18:00", self.text)

    def test_links_are_on_their_own_line(self):
        lines = self.text.split("\n")
        url_lines = [line for line in lines if line.startswith("https://")]
        self.assertEqual(3, len(url_lines))

    def test_no_html_tags(self):
        self.assertNotIn("<p", self.text)
        self.assertNotIn("<table", self.text)


class TestMarkdown(unittest.TestCase):
    def setUp(self):
        self.md = render.render_markdown(example())

    def test_structure(self):
        self.assertTrue(self.md.startswith("# 【申请】"))
        self.assertIn("## 发布范围", self.md)
        self.assertIn("| 项目 | 工时（人天） | 说明 |", self.md)
        self.assertIn("![改版后的首页](https://example.com/orbit/home.png)", self.md)


class TestPresets(unittest.TestCase):
    def test_four_presets_have_expected_tokens(self):
        business = styles.load_preset("business")
        report = styles.load_preset("report")
        plain = styles.load_preset("plain")
        alert = styles.load_preset("alert")
        self.assertEqual("#1F4E79", business["color"]["accent"])
        self.assertTrue(business["heading"]["bar"])
        self.assertTrue(report["table"]["zebra"])
        self.assertFalse(report["heading"]["bar"])
        self.assertEqual(600, plain["width"])
        self.assertFalse(plain["summary"]["card"])
        self.assertTrue(alert["band"]["enabled"])

    def test_auto_selection(self):
        spec = example()
        self.assertEqual("business", styles.resolve(spec)[1])
        spec["type"] = "report"
        self.assertEqual("report", styles.resolve(spec)[1])
        spec["type"] = "coordination"
        self.assertEqual("alert", styles.resolve(spec)[1])
        spec["type"] = "daily"
        self.assertEqual("plain", styles.resolve(spec)[1])
        spec["type"] = "approval"
        spec["audience"] = "外部客户"
        self.assertEqual("plain", styles.resolve(spec)[1])
        spec["urgent"] = True
        self.assertEqual("alert", styles.resolve(spec)[1])

    def test_explicit_style_beats_type(self):
        spec = example()
        spec["style"] = "alert"
        self.assertEqual("alert", styles.resolve(spec)[1])

    def test_style_override_merges(self):
        spec = example()
        spec["style"] = {"preset": "business", "overrides": {"color": {"accent": "#0F5C4E"}}}
        tokens, name, _ = styles.resolve(spec)
        self.assertEqual("business", name)
        self.assertEqual("#0F5C4E", tokens["color"]["accent"])
        self.assertEqual(640, tokens["width"])


class TestEml(unittest.TestCase):
    def test_structure_and_headers(self):
        spec = example()
        tokens, _, _ = styles.resolve(spec)
        data, notes = render.render_eml(spec, tokens, str(EXAMPLE.parent))
        msg = email.message_from_bytes(data)
        self.assertEqual(str(email.header.make_header(email.header.decode_header(msg["Subject"]))), spec["subject"])
        self.assertIn("wang@example.com", msg["To"])
        self.assertEqual([], notes)
        types = [part.get_content_type() for part in msg.walk()]
        self.assertIn("multipart/alternative", types)
        self.assertIn("text/plain", types)
        self.assertIn("text/html", types)

    def test_local_image_is_embedded_with_cid(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "dot.png"
            image.write_bytes(
                bytes.fromhex(
                    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c63f8cf00000003000100ef3f9e00"
                    "00000049454e44ae426082"
                )
            )
            spec = {
                "type": "daily",
                "subject": "图片",
                "greeting": "大家好",
                "summary": "见下图。",
                "blocks": [
                    {"kind": "images", "items": [{"src": "./dot.png", "alt": "点", "caption": ""}]}
                ],
                "facts": [],
            }
            from email_composer.spec import normalize

            spec = normalize(spec)
            tokens, _, _ = styles.resolve(spec)
            data, notes = render.render_eml(spec, tokens, tmp)
            self.assertEqual([], notes)
            msg = email.message_from_bytes(data)
            self.assertEqual("multipart/related", msg.get_content_type())
            cids = [part.get("Content-ID") for part in msg.walk() if part.get("Content-ID")]
            self.assertEqual(["<img1@email-composer>"], cids)
            html = [
                part.get_payload(decode=True).decode("utf-8")
                for part in msg.walk()
                if part.get_content_type() == "text/html"
            ][0]
            self.assertIn("cid:img1@email-composer", html)


class TestFilenames(unittest.TestCase):
    def test_filename_uses_subject_and_date(self):
        spec = example()
        tokens, _, _ = styles.resolve(spec)
        outputs, _ = render.build_outputs(
            spec, tokens, str(EXAMPLE.parent), formats=("html",), day=date(2026, 11, 18)
        )
        name = outputs["html"][0]
        self.assertTrue(name.startswith("Orbit-工作台上线申请"))
        self.assertTrue(name.endswith("_2026-11-18.html"))
        self.assertNotIn("【", name)

    def test_explicit_name_wins(self):
        spec = example()
        tokens, _, _ = styles.resolve(spec)
        outputs, _ = render.build_outputs(
            spec, tokens, str(EXAMPLE.parent), formats=("text",), name="draft"
        )
        self.assertEqual("draft.txt", outputs["text"][0])

    def test_unknown_format_is_rejected(self):
        with self.assertRaises(ValueError):
            render.parse_formats("html,pdf")


if __name__ == "__main__":
    unittest.main()
