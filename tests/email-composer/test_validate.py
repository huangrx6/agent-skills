"""校验：每个阻断项都要能被一个针对性变异触发，警告项不能误报成阻断。"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parents[1] / "skills" / "email-composer"
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

from email_composer import render, styles  # noqa: E402
from email_composer.spec import load_spec, normalize  # noqa: E402
from email_composer.validate import report_to_json, validate_spec  # noqa: E402

EXAMPLE = SKILL / "examples" / "approval-release.yaml"


def example():
    return copy.deepcopy(load_spec(str(EXAMPLE)))


def block(spec, kind):
    return next(item for item in spec["blocks"] if item["kind"] == kind)


def run(spec, html=None, text=None, md="", base_dir=None, tokens=None):
    tokens = tokens or styles.resolve(spec)[0]
    html = render.render_html(spec, tokens) if html is None else html
    text = render.render_text(spec) if text is None else text
    return validate_spec(
        spec, tokens, html, text, md, base_dir or str(EXAMPLE.parent)
    )


def codes(report, bucket="blocking"):
    return {item["code"] for item in report[bucket]}


class TestCleanExample(unittest.TestCase):
    def test_example_has_no_blocking_or_warnings(self):
        report = run(example())
        self.assertTrue(report["ok"], report["blocking"])
        self.assertEqual(set(), codes(report))
        self.assertEqual(set(), codes(report, "warnings"))
        self.assertTrue(report["skipped"])

    def test_report_is_json_serializable(self):
        payload = json.loads(report_to_json(run(example())))
        self.assertTrue(payload["ok"])
        self.assertIn("stats", payload)

    def test_subject_length_is_not_body_length(self):
        spec = example()
        spec["subject"] = "标题" * 450
        report = run(spec)
        self.assertNotIn("body_long", codes(report, "warnings"))


class TestBlocking(unittest.TestCase):
    def test_missing_subject(self):
        spec = example()
        spec["subject"] = ""
        self.assertIn("subject_missing", codes(run(spec)))

    def test_recipient_placeholder(self):
        spec = example()
        spec["to"] = "【待填：收件人邮箱】"
        report = run(spec)
        self.assertIn("recipient_placeholder", codes(report))

    def test_body_placeholder(self):
        spec = example()
        block(spec, "paragraph")["text"] = "附件名： 【待填：附件名】"
        report = run(spec)
        self.assertIn("placeholder", codes(report))
        self.assertIn("【待填：附件名】", report["stats"]["placeholders"])

    def test_unfilled_template_variable(self):
        spec = example()
        block(spec, "paragraph")["text"] = "当前版本 {{version}}"
        self.assertIn("unfilled_variable", codes(run(spec)))

    def test_width_over_640(self):
        spec = example()
        tokens = copy.deepcopy(styles.resolve(spec)[0])
        tokens["width"] = 700
        report = run(spec, tokens=tokens)
        self.assertIn("html_width", codes(report))

    def test_forbidden_html_construct(self):
        spec = example()
        html = render.render_html(spec, styles.resolve(spec)[0]) + '<div style="display:flex">x</div>'
        self.assertIn("html_forbidden", codes(run(spec, html=html)))

    def test_missing_alt(self):
        spec = example()
        block(spec, "images")["items"][0]["alt"] = ""
        self.assertIn("image_alt", codes(run(spec)))

    def test_number_without_fact(self):
        spec = example()
        spec["facts"] = []
        report = run(spec)
        self.assertIn("number_provenance", codes(report))

    def test_html_text_mismatch(self):
        spec = example()
        text = render.render_text(spec) + "\n2026-12-31\n"
        report = run(spec, text=text)
        self.assertIn("html_text_mismatch", codes(report))


class TestWarnings(unittest.TestCase):
    def test_no_action_and_no_deadline(self):
        spec = normalize(
            {
                "type": "confirm",
                "subject": "系统维护安排",
                "greeting": "大家好",
                "summary": "系统维护安排如下。",
                "blocks": [],
                "facts": [],
            }
        )
        report = run(spec)
        self.assertTrue(report["ok"])
        self.assertIn("no_action", codes(report, "warnings"))
        self.assertIn("no_deadline", codes(report, "warnings"))

    def test_recipient_missing(self):
        spec = example()
        spec["to"] = ""
        self.assertIn("recipient_missing", codes(run(spec), "warnings"))

    def test_exclamation_and_emoji(self):
        spec = example()
        spec["greeting"] = "王总，您好！🎉"
        report = run(spec)
        self.assertIn("exclamation", codes(report, "warnings"))
        self.assertIn("emoji", codes(report, "warnings"))

    def test_todo_incomplete(self):
        spec = example()
        block(spec, "todo")["items"][0]["owner"] = ""
        self.assertIn("todo_incomplete", codes(run(spec), "warnings"))

    def test_long_paragraph(self):
        spec = example()
        spec["summary"] = "说明" * 250
        self.assertIn("long_paragraph", codes(run(spec), "warnings"))

    def test_body_too_long(self):
        spec = example()
        spec["summary"] = "说明" * 450
        self.assertIn("body_long", codes(run(spec), "warnings"))

    def test_declared_placeholders_warn(self):
        spec = example()
        spec["placeholders"] = ["附件名待补"]
        self.assertIn("declared_placeholders", codes(run(spec), "warnings"))

    def test_image_width_and_local_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "dot.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 16)
            spec = normalize(
                {
                    "type": "daily",
                    "subject": "图片",
                    "greeting": "大家好",
                    "summary": "见下图，请确认。",
                    "blocks": [
                        {
                            "kind": "images",
                            "items": [{"src": str(image), "alt": "点", "width": 1200}],
                        }
                    ],
                    "facts": [],
                }
            )
            report = run(spec, base_dir=tmp)
            self.assertIn("image_width", codes(report, "warnings"))
            self.assertIn("image_local_path", codes(report, "warnings"))

    def test_large_image_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "big.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * (1024 * 1024 + 10))
            spec = normalize(
                {
                    "type": "daily",
                    "subject": "大图",
                    "greeting": "大家好",
                    "summary": "见下图，请确认。",
                    "blocks": [
                        {"kind": "images", "items": [{"src": str(image), "alt": "大图"}]}
                    ],
                    "facts": [],
                }
            )
            self.assertIn("image_size", codes(run(spec, base_dir=tmp), "warnings"))

    def test_unreadable_local_image_warns(self):
        spec = example()
        block(spec, "images")["items"][0]["src"] = "./missing.png"
        report = run(spec)
        self.assertIn("image_unreadable", codes(report, "warnings"))


if __name__ == "__main__":
    unittest.main()
