"""Behavioral regressions for declaration checks, HTML and delivery gates."""
import json
import subprocess
import sys
import tempfile
import unittest
from email import policy
from email.parser import BytesParser
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2] / "skills" / "email-composer"
sys.path.insert(0, str(SKILL / "scripts"))
from email_composer import render, styles, templates, rawhtml
from email_composer.spec import normalize, filename_base, SpecError
from email_composer.validate import validate_spec, check_html_body


def report(**values):
    spec = normalize({"type": "confirm", "subject": "确认", **values})
    tokens = styles.resolve(spec)[0]
    return validate_spec(spec, tokens, render.render_html(spec, tokens),
                         render.render_text(spec), render.render_markdown(spec))


def codes(result):
    return {item["code"] for item in result["blocking"]}


class Declarations(unittest.TestCase):
    def test_date_and_time_cannot_justify_cost(self):
        for fact in ("2026-11-20", "20:00"):
            with self.subTest(fact=fact):
                self.assertIn("number_provenance", codes(report(summary="费用 20 万元", facts=[fact])))

    def test_units_and_magnitude_must_match(self):
        for actual, fact in (("5 万元", "5 元"), ("5 小时", "5 人天"), ("5%", "5 元"), ("5 万元", "5")):
            with self.subTest(actual=actual, fact=fact):
                self.assertIn("quantity_mismatch", codes(report(summary=actual, facts=[fact])))

    def test_matching_quantity_passes(self):
        self.assertTrue(report(summary="请确认 5 万元", facts=["费用 5 万元"])["ok"])

    def test_table_inherits_unit(self):
        blocks = [{"kind": "table", "columns": ["项目", "工时（人天）"], "rows": [["开发", "5"]]}]
        self.assertIn("quantity_mismatch", codes(report(blocks=blocks, facts=["5 小时"])))
        self.assertTrue(report(blocks=blocks, facts=["5 人天"])["ok"])

    def test_unfilled_delivery_fields_block(self):
        for field in ({"to": "{{recipient}}"}, {"cc": ["{{copy}}"]},
                      {"blocks": [{"kind": "cta", "text": "查看", "url": "https://example.com/{{ticket}}"}]},
                      {"blocks": [{"kind": "images", "items": [{"src": "{{path}}", "alt": "{{label}}"}]}]}):
            with self.subTest(field=field):
                self.assertIn("unfilled_variable", codes(report(**field)))

    def test_final_output_is_scanned(self):
        spec = normalize({"type": "daily", "subject": "感谢"})
        result = validate_spec(spec, styles.resolve(spec)[0], "<p>{{leftover}}</p>", "感谢")
        self.assertIn("unfilled_variable", codes(result))

    def test_daily_and_information_only_do_not_require_deadline(self):
        for kind in ("daily", "notice", "report"):
            warnings = report(type=kind, summary="感谢支持。")['warnings']
            self.assertFalse({"no_action", "no_deadline"} & {w["code"] for w in warnings})

    def test_confirm_still_requires_action_and_deadline(self):
        warnings = report(summary="事项如下。")['warnings']
        self.assertTrue({"no_action", "no_deadline"} <= {w["code"] for w in warnings})


class HtmlParsing(unittest.TestCase):
    def test_quotes_and_widths(self):
        for width in ("'900'", '"900"', "900"):
            self.assertIn("html_width", {h["code"] for h in check_html_body(f"<table width={width}></table>")})
        self.assertEqual([], check_html_body("<img src='photo.png' alt='效果图'>"))
        self.assertEqual([], check_html_body("<img src=photo.png alt=效果图>"))

    def test_css_widths(self):
        for html in ("<div style='width:900.5px'>x</div>", "<style>table {width:600pt}</style>"):
            self.assertIn("html_width", {h["code"] for h in check_html_body(html)})

    def test_active_content_is_rejected(self):
        for html in ('<img src="x" alt="图" onerror="alert(1)">',
                     '<a href="java&#x73;cript:alert(1)">x</a>',
                     '<iframe srcdoc="hello"></iframe>',
                     '<div style="display:/* comment */grid">x</div>'):
            with self.subTest(html=html):
                self.assertIn("html_forbidden", {h["code"] for h in check_html_body(html)})

    def test_visible_code_is_not_mistaken_for_html(self):
        self.assertEqual([], check_html_body("<p>说明 display:flex 和 &lt;script&gt; 的限制</p>"))

    def test_raw_headers_are_checked(self):
        for values in ({"to": "【待填：邮箱】"}, {"cc": ["{{copy}}"]}, {"subject": "{{title}}"}):
            args = {"subject": "确认", **values}
            self.assertFalse(rawhtml.validate_html_template("<p>确认</p>", "确认", **args)["ok"])

    def test_single_quote_images_embed_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "photo.png").write_bytes(b"image")
            body, attachments, notes = render.embed_images("<img src='photo.png' alt='图'><img src=photo.png alt=图>", tmp)
            self.assertEqual(1, len(attachments))
            self.assertEqual(2, body.count("cid:img1@email-composer"))
            self.assertEqual([], notes)

    def test_mime_headers_are_unique_per_part(self):
        data, _ = render.build_eml("确认", "<p>确认</p>", "确认", ".")
        message = BytesParser(policy=policy.default).parsebytes(data)
        for part in message.walk():
            self.assertEqual(1, len(part.get_all("MIME-Version", [])))


class Delivery(unittest.TestCase):
    def invoke(self, tmp, *args, summary="金额【待填：金额】", blocks=None):
        path = Path(tmp, "spec.json")
        path.write_text(json.dumps({"type": "confirm", "subject": "确认", "summary": summary, "blocks": blocks or []}))
        return subprocess.run([sys.executable, str(SKILL / "scripts/render.py"), str(path),
                               "--outdir", str(Path(tmp, "out")), "--json", *args],
                              text=True, capture_output=True, timeout=30)

    def test_render_blocks_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.invoke(tmp)
            self.assertEqual(1, result.returncode, result.stderr)
            self.assertFalse(Path(tmp, "out").exists())
            self.assertFalse(json.loads(result.stdout)["ok"])

    def test_explicit_draft_retains_failure_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.invoke(tmp, "--draft")
            self.assertEqual(1, result.returncode, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["draft"])
            self.assertFalse(payload["ok"])
            self.assertTrue(payload["report"]["blocking"])
            self.assertTrue(all(Path(p).name.startswith("DRAFT_") for p in payload["files"].values()))

    def test_draft_cannot_bypass_active_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.invoke(tmp, "--draft", blocks=[{"kind": "cta", "text": "查看", "url": "javascript:alert(1)"}])
            self.assertEqual(1, result.returncode)
            self.assertFalse(Path(tmp, "out").exists())

    def test_name_cannot_escape_output_directory(self):
        for name in ("../escape", "/tmp/escape", ".."):
            with self.assertRaises(SpecError):
                filename_base("确认", name=name)

    def test_html_import_rejects_unparameterized_values_before_writing(self):
        for value in ("test@example.com", "13800138000", "2026-11-20", "20:00"):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp, "source.html")
                source.write_text(f"<title>确认</title><p>{value}</p>")
                root = Path(tmp, "templates")
                with self.assertRaises(templates.TemplateError):
                    templates.add_html(root, str(source), "sample")
                self.assertFalse(root.exists())

    def test_manually_copied_template_cannot_bypass_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp, "templates")
            (root / "html").mkdir(parents=True)
            (root / "html/sample.html").write_text("<title>确认</title><p>test@example.com</p>")
            with self.assertRaises(templates.TemplateError):
                templates.apply(root, "html/sample", outdir=str(Path(tmp, "out")))
            self.assertFalse(Path(tmp, "out").exists())

    def test_cli_preset_wins_but_keeps_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "style.json")
            path.write_text(json.dumps({"preset": "alert", "overrides": {"width": 600}}))
            spec = normalize({"subject": "确认", "style": {"preset": "business", "overrides": {"color": {"accent": "#123456"}}}})
            tokens, name, _ = styles.resolve(spec, "plain", str(path))
            self.assertEqual("plain", name)
            self.assertEqual(600, tokens["width"])
            self.assertEqual("#123456", tokens["color"]["accent"])


if __name__ == "__main__":
    unittest.main()
