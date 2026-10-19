"""Free HTML layout gates use real text geometry, without a structural spec."""
from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[2] / "skills/deck-authoring/scripts"


def load(name):
    spec = importlib.util.spec_from_file_location("_test_" + name, SCRIPTS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = load("web_check")
compiler = load("web_deck")
try:
    checker._connect()
    HAS_BROWSER = Path(checker.CHROME).is_file()
except RuntimeError:
    HAS_BROWSER = False


def source(pages, head=""):
    slides = "".join(f'<section class="slide" data-slide="{i}" data-title="Anonymous example {i}" '
                     f'data-enter=".5" data-hold="1">{content}</section>' for i, content in enumerate(pages, 1))
    return ('<!doctype html><html><head><meta charset="utf-8"><style>'
            'p,h1{margin:0;font:32px/1.4 Arial,sans-serif}.slide{background:white;color:#111}'
            '</style>' + head + '</head><body>' + slides + '</body></html>')


CAPACITY_STYLE = """<style>
.deck-page{box-sizing:border-box;width:100%;height:100%;padding:56px 80px 40px;
  display:grid;grid-template-rows:auto minmax(0,1fr) auto;gap:32px}
.deck-header h1{font:56px/1.12 Arial,sans-serif;max-width:1100px}
.deck-body{position:relative;box-sizing:border-box;min-height:0;min-width:0;padding-bottom:32px;
  display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:32px;align-content:start}
.deck-block{min-width:0}.deck-caption,.deck-caption p,.deck-footer{font:16px/1.4 Arial,sans-serif}
</style>"""


def capacity_page(body, title="A focused conclusion", *, page_attrs="", body_attrs="", header_attrs=""):
    return (f'<div class="deck-page" {page_attrs}><header class="deck-header" {header_attrs}>'
            f'<h1>{title}</h1></header><main class="deck-body" {body_attrs}>{body}</main>'
            '<footer class="deck-footer">Source and page number</footer></div>')


class TestWebCheckPolicy(unittest.TestCase):
    def report(self, *findings):
        return checker.summarize({"pages": [], "issues": list(findings)})

    def test_review_is_not_a_success_exit_and_small_type_is_advisory(self):
        small = self.report({"severity": "warning", "code": "small-text"})
        self.assertEqual(small["summary"]["status"], "passed")
        self.assertEqual(checker.exit_code(small), 0)
        self.assertEqual(checker.exit_code(small, strict=True), 2)
        review = self.report({"severity": "warning", "code": "text-overlap", "requiresReview": True})
        self.assertEqual(review["summary"]["status"], "needs_review")
        self.assertEqual(checker.exit_code(review), 2)
        error = self.report({"severity": "error", "code": "text-clipped"})
        self.assertEqual(error["summary"]["status"], "failed")
        self.assertEqual(checker.exit_code(error), 1)

    def test_missing_file_does_not_launch_browser(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            checker.inspect("/no-such-deck-fixture.html")

    def test_report_cannot_overwrite_source_or_follow_symlink_before_browser_launch(self):
        with tempfile.TemporaryDirectory(prefix="web-check-target-test-") as folder:
            path = Path(folder) / "deck.html"
            path.write_text("original artifact", encoding="utf-8")
            link = Path(folder) / "report.json"
            link.symlink_to(path)
            for output in (path, link):
                with self.subTest(output=output), patch.object(checker, "inspect") as inspect:
                    with self.assertRaises(SystemExit) as exc, patch("sys.stderr"):
                        checker.main([str(path), "--json", str(output)])
                    self.assertEqual(exc.exception.code, 2)
                    inspect.assert_not_called()
                    self.assertEqual(path.read_text(), "original artifact")

    def test_cli_distinguishes_default_role_thresholds_from_an_explicit_global_floor(self):
        for argv, expected in ((["deck.html"], None), (["deck.html", "--min-font", "24"], 24)):
            with self.subTest(argv=argv), patch.object(checker, "inspect", return_value=self.report()) as inspect, patch("builtins.print"):
                self.assertEqual(checker.main(argv), 0)
                self.assertEqual(inspect.call_args.kwargs["min_font"], expected)


@unittest.skipUnless(HAS_BROWSER, "Chrome and websockets are required")
class TestWebCheckBrowser(unittest.TestCase):
    def inspect(self, pages, head="", **options):
        with tempfile.TemporaryDirectory(prefix="web-check-test-") as folder:
            path = Path(folder) / "deck.html"
            path.write_text(compiler.compile_html(source(pages, head)), encoding="utf-8")
            return checker.inspect(path, stability_ms=100, **options)

    def codes(self, report, page=0):
        return {issue["code"] for issue in report["pages"][page]["issues"]}

    def test_small_text_samples_include_explanation_after_many_short_labels(self):
        labels = ''.join(f'<p style="font-size:14px">Label {i}</p>' for i in range(12))
        explanation = "The actual processing explanation must remain visible in the small text report. " * 2
        content = ('<div style="padding:80px">' + labels
                   + f'<p style="font-size:18px;max-width:1000px">{explanation}</p>'
                   + '<p style="font-size:23px">A secondary explanation at a different size.</p></div>')
        report = self.inspect([content])
        issues = [i for i in report["pages"][0]["issues"] if i["code"] == "small-text"]
        self.assertEqual(len(issues), 1)
        issue = issues[0]
        self.assertEqual(issue["count"], 14)
        distribution = {item["fontSize"]: item for item in issue["fontSizeDistribution"]}
        self.assertEqual({size: item["count"] for size, item in distribution.items()}, {14: 12, 18: 1, 23: 1})
        self.assertEqual(distribution[18]["characters"], len(explanation.strip()))
        self.assertGreater(distribution[18]["characters"], 100)
        self.assertTrue(any(sample["text"].startswith("The actual processing") for sample in issue["samples"]))
        self.assertEqual({sample["fontSize"] for sample in issue["samples"]}, {14, 18, 23})
        self.assertLessEqual(len(issue["samples"]), 8)
        self.assertEqual(checker.exit_code(report), 0, "Reporting more evidence must not turn type advice into a gate")

    def test_report_identifies_the_inspected_bytes_and_utc_check_window(self):
        with tempfile.TemporaryDirectory(prefix="web-check-version-test-") as folder:
            path = Path(folder) / "deck.html"
            content = compiler.compile_html(source(['<p>Stable input</p>'])).encode("utf-8")
            path.write_bytes(content)
            before = datetime.now(timezone.utc)
            report = checker.inspect(path, stability_ms=100)
            after = datetime.now(timezone.utc)
            self.assertEqual(report["htmlSha256"], hashlib.sha256(content).hexdigest())
            self.assertEqual(checker.exit_code(report), 0)
            self.assertTrue(report["capturedAt"].endswith("Z"))
            self.assertTrue(report["checkedAt"].endswith("Z"))
            captured = datetime.fromisoformat(report["capturedAt"].replace("Z", "+00:00"))
            checked = datetime.fromisoformat(report["checkedAt"].replace("Z", "+00:00"))
            self.assertLessEqual(before, captured)
            self.assertLessEqual(captured, checked)
            self.assertLessEqual(checked, after)

    def test_browser_triggered_file_change_or_removal_invalidates_geometry_pass(self):
        # The already-loaded HTML asks this loopback fixture to mutate its file.
        # Awaiting the request via the real runtime readiness contract makes the
        # race deterministic, without replacing Chrome or the inspection code.
        for action in ("change", "remove"):
            with self.subTest(action=action), tempfile.TemporaryDirectory(prefix="web-check-race-test-") as folder:
                path = Path(folder) / "deck.html"
                mutated = threading.Event()

                class Handler(BaseHTTPRequestHandler):
                    def do_GET(self):
                        if action == "change":
                            path.write_bytes(path.read_bytes() + b"\n<!-- next revision -->\n")
                        else:
                            path.unlink()
                        mutated.set()
                        self.send_response(200)
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.end_headers()
                        self.wfile.write(b"done")

                    def log_message(self, *args):
                        pass

                with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
                    thread = threading.Thread(target=server.serve_forever, daemon=True)
                    thread.start()
                    head = ('<script>window.__deck_charts_ready=fetch('
                            f'"http://127.0.0.1:{server.server_port}/mutate").then(r=>r.text());</script>')
                    content = compiler.compile_html(source(['<p>Readable loaded page</p>'], head)).encode("utf-8")
                    path.write_bytes(content)
                    try:
                        report = checker.inspect(path, stability_ms=100)
                    finally:
                        server.shutdown()
                        thread.join(timeout=5)
                self.assertTrue(mutated.is_set(), "Chrome must trigger the actual file mutation")
                self.assertEqual(len(report["pages"]), 1)
                self.assertEqual(report["pages"][0]["issues"], [])
                self.assertEqual(report["htmlSha256"], hashlib.sha256(content).hexdigest())
                issues = [i for i in report["issues"] if i["code"] == "input-changed"]
                self.assertEqual(len(issues), 1)
                self.assertEqual(issues[0]["severity"], "error")
                self.assertEqual(report["summary"]["status"], "failed")
                self.assertEqual(checker.exit_code(report), 1)
                if action == "change":
                    self.assertEqual(issues[0]["observedHtmlSha256"], hashlib.sha256(path.read_bytes()).hexdigest())
                    self.assertNotEqual(issues[0]["observedHtmlSha256"], report["htmlSha256"])
                else:
                    self.assertFalse(path.exists())

    def test_measures_every_page_and_finds_canvas_and_svg_clipping(self):
        report = self.inspect([
            '<p style="position:absolute;left:1500px;top:100px;white-space:nowrap">A long line beyond the canvas edge</p>',
            '<div style="position:absolute;left:80px;top:100px;width:200px;height:36px;overflow:hidden"><p>A sentence that needs several lines in a narrow column.</p></div>',
            '<svg width="200" height="160" style="position:absolute;left:80px;top:100px"><text x="100" y="70" font-size="32">Long SVG label</text></svg>',
        ])
        self.assertEqual(len(report["pages"]), 3)
        self.assertIn("text-outside-slide", self.codes(report, 0))
        self.assertIn("text-clipped", self.codes(report, 1))
        self.assertIn("text-clipped", self.codes(report, 2))
        self.assertEqual(checker.exit_code(report), 1)

    def test_overlap_uses_line_boxes_and_does_not_flag_inline_emphasis_or_image_layers(self):
        report = self.inspect([
            '<h1 style="position:absolute;left:100px;top:100px">First line<br>Second line</h1>'
            '<p style="position:absolute;left:100px;top:156px">Independent subtitle</p>',
            '<div style="position:absolute;inset:80px;background:#eee"><p>Text with <b>inline emphasis</b> and a second phrase.</p></div>',
            '<p style="position:absolute;left:100px;top:100px">Separate</p><p style="position:absolute;left:100px;top:145px">Readable</p>',
        ])
        collision = next(i for i in report["pages"][0]["issues"] if i["code"] == "text-overlap")
        self.assertGreater(collision["intersection"]["area"], 100)
        self.assertTrue(collision["requiresReview"])
        self.assertNotIn("text-overlap", self.codes(report, 1))
        self.assertNotIn("text-overlap", self.codes(report, 2))
        self.assertEqual(checker.exit_code(report), 2)

    def test_reasoned_exception_is_local_and_recorded(self):
        report = self.inspect([
            '<h1 data-web-check-allow="text-overlap" data-web-check-reason="Deliberate typographic overprint" style="position:absolute;left:100px;top:100px">OVERPRINT</h1>'
            '<p style="position:absolute;left:100px;top:100px">Overprinted caption</p>',
            '<p data-web-check-allow="text-outside-slide" style="position:absolute;left:1590px;top:100px;white-space:nowrap">Not an exemption without a reason</p>',
            '<p data-web-check-allow="text-outside-slide" data-web-check-reason="Not a valid reason to lose text" style="position:absolute;left:1590px;top:100px;white-space:nowrap">A hard error must remain blocking</p>',
        ])
        self.assertNotIn("text-overlap", self.codes(report))
        self.assertEqual(report["pages"][0]["exemptions"][0]["code"], "text-overlap")
        self.assertIn("invalid-exemption", self.codes(report, 1))
        self.assertIn("text-outside-slide", self.codes(report, 1))
        self.assertIn("text-outside-slide", self.codes(report, 2))
        self.assertEqual(report["pages"][2]["exemptions"], [])

    def test_parent_text_and_child_block_overlap_is_not_skipped(self):
        report = self.inspect([
            '<div style="position:absolute;left:100px;top:100px;font:32px Arial">Parent text'
            '<p style="position:absolute;left:0;top:0">Child paragraph</p></div>'
        ])
        self.assertIn("text-overlap", self.codes(report))
        self.assertEqual(checker.exit_code(report), 2)

    def test_opaque_html_and_svg_foregrounds_require_visual_review(self):
        report = self.inspect([
            '<p style="position:absolute;left:100px;top:100px">Covered text</p>'
            '<div style="position:absolute;left:80px;top:80px;width:400px;height:120px;background:white"></div>',
            '<svg width="500" height="300"><text x="80" y="110" font-size="32">Covered label</text>'
            '<rect x="60" y="60" width="350" height="120" fill="white"></rect></svg>',
            '<svg width="500" height="300"><rect x="60" y="60" width="350" height="120" fill="white"></rect>'
            '<text x="80" y="110" font-size="32">Readable foreground label</text></svg>',
        ])
        self.assertIn("text-occluded", self.codes(report, 0))
        self.assertIn("text-occluded", self.codes(report, 1))
        self.assertNotIn("text-occluded", self.codes(report, 2))
        self.assertEqual(checker.exit_code(report), 2)

    def test_failed_image_still_reports_other_pages(self):
        report = self.inspect([
            '<img src="missing-art.png" width="400" height="300" alt="Missing artwork">',
            '<p style="position:absolute;left:1590px;white-space:nowrap">Overflow remains detectable</p>',
        ])
        self.assertIn("image-failed", self.codes(report))
        self.assertIn("text-outside-slide", self.codes(report, 1))
        self.assertIn("readiness-failed", {i["code"] for i in report["issues"]})

    def test_waits_for_real_readiness_and_detects_later_geometry_drift(self):
        report = self.inspect([
            '<p id="ready" style="position:absolute;left:100px;top:100px">Waiting</p>'
        ], head='''<script>
          window.__deck_charts_ready=new Promise(resolve=>setTimeout(()=>{
            document.getElementById('ready').textContent='Ready';
            const origin=performance.now();
            function move(){document.getElementById('ready').style.left=(100+(performance.now()-origin)/2)+'px';requestAnimationFrame(move);}
            requestAnimationFrame(move);resolve();
          },120));
        </script>''')
        self.assertIn("unstable-layout", self.codes(report))
        self.assertFalse(any(i["code"].startswith("readiness") for i in report["issues"]))
        movement = next(i for i in report["pages"][0]["issues"] if i["code"] == "unstable-layout")
        self.assertGreater(movement["movements"][0]["delta"], 1)

    def test_pending_readiness_is_a_timed_failure_not_false_success(self):
        report = self.inspect(['<p>Visible while waiting</p>'],
                              head='<script>window.__deck_charts_ready=new Promise(()=>{});</script>', timeout=2)
        self.assertIn("readiness-timeout", {i["code"] for i in report["issues"]})
        self.assertEqual(checker.exit_code(report), 1)

    def test_capacity_normal_flow_reserves_footer_with_multiline_heading_and_small_captions(self):
        report = self.inspect([capacity_page(
            '<article class="deck-block"><p>A readable primary point.</p>'
            '<p class="deck-caption">Auxiliary image caption, not the main explanation.</p></article>'
            '<article class="deck-block"><p>A second short explanation.</p></article>',
            title='First line of the conclusion<br>Second line stays in normal flow')], CAPACITY_STYLE)
        page = report["pages"][0]
        budget = page["layoutBudget"]
        self.assertEqual(checker.exit_code(report), 0)
        self.assertNotIn("body-min-font", self.codes(report))
        self.assertGreater(budget["header"]["h"], 80)
        self.assertEqual(budget["bottomReserve"], 48)
        self.assertEqual(budget["minBodyFont"], 32)
        self.assertEqual(budget["viewing"], "screen")
        self.assertEqual(budget["minBodyFontRecommended"], 24)
        self.assertEqual(budget["blockCount"], 2)
        self.assertEqual(budget["captionTextRuns"], 1)
        self.assertGreater(budget["availableHeight"], 400)
        self.assertLess(budget["body"]["y"] + budget["body"]["h"], budget["footer"]["y"])

    def test_capacity_only_an_explicit_block_budget_requires_review(self):
        four = ''.join(f'<article class="deck-block"><p>Point {i} with a brief explanation.</p></article>' for i in range(4))
        report = self.inspect([
            capacity_page(four, body_attrs='style="font-size:18px"'),
            capacity_page(four),
            capacity_page(four, body_attrs='data-max-blocks="3"'),
        ], CAPACITY_STYLE + '<style>.deck-body[style] p{font-size:18px}</style>')
        self.assertIn("body-min-font", self.codes(report, 0))
        self.assertNotIn("body-block-budget", self.codes(report, 0))
        self.assertNotIn("text-outside-slide", self.codes(report, 0))
        self.assertNotIn("body-block-budget", self.codes(report, 1))
        self.assertNotIn("body-min-font", self.codes(report, 1))
        findings = [issue for issue in report["pages"][2]["issues"] if issue["code"] == "body-block-budget"]
        self.assertEqual(len(findings), 1)
        self.assertTrue(findings[0]["requiresReview"])
        self.assertEqual(findings[0]["count"], 4)
        self.assertEqual(report["summary"]["errors"], 0)
        self.assertEqual(checker.exit_code(report), 2)
        self.assertIsNone(report["pages"][0]["layoutBudget"]["maxBlocks"])
        self.assertIsNone(report["pages"][1]["layoutBudget"]["maxBlocks"])
        self.assertEqual(report["pages"][2]["layoutBudget"]["maxBlocks"], 3)

    def test_capacity_primary_type_uses_the_declared_viewing_context(self):
        cases = ((24, "screen", False), (26, None, False), (22, "screen", True),
                 (24, "room", True), (26, "room", True), (28, "room", False))
        report = self.inspect([
            capacity_page(f'<p class="deck-block" style="font-size:{size}px">One concise explanation.</p>',
                          page_attrs=f'data-viewing="{viewing}"' if viewing else "")
            for size, viewing, _ in cases
        ], CAPACITY_STYLE)
        self.assertEqual(report["summary"]["errors"], 0)
        for index, (size, viewing, advisory) in enumerate(cases):
            with self.subTest(size=size, viewing=viewing):
                page = report["pages"][index]
                budget = page["layoutBudget"]
                self.assertEqual(budget["viewing"], viewing or "screen")
                self.assertEqual(budget["minBodyFontRecommended"], 28 if viewing == "room" else 24)
                self.assertEqual(budget["minBodyFont"], size)
                findings = [issue for issue in page["issues"] if issue["code"] == "body-min-font"]
                self.assertEqual(bool(findings), advisory)
                self.assertFalse(any(issue.get("requiresReview") for issue in page["issues"]))
                if findings:
                    self.assertEqual(findings[0]["threshold"], budget["minBodyFontRecommended"])
        self.assertEqual(checker.exit_code(report), 0)
        self.assertEqual(checker.exit_code(report, strict=True), 2)

    def test_capacity_unknown_viewing_context_is_an_invalid_contract(self):
        report = self.inspect([
            capacity_page('<p class="deck-block">One concise explanation.</p>',
                          page_attrs=f'data-viewing="{viewing}"')
            for viewing in ("print", "Screen", "")
        ], CAPACITY_STYLE)
        for index in range(3):
            self.assertIn("layout-contract-invalid", self.codes(report, index))
            self.assertIsNone(report["pages"][index]["layoutBudget"]["minBodyFontRecommended"])
        self.assertEqual(checker.exit_code(report), 1)

    def test_capacity_small_auxiliary_type_has_role_specific_advisories(self):
        content = ('<p class="deck-block">A concise main explanation.</p>'
                   '<p class="deck-caption" style="font-size:15px">Small auxiliary caption.</p>')
        report = self.inspect([
            capacity_page(content, page_attrs=f'data-viewing="{viewing}"').replace(
                '<footer class="deck-footer">', '<footer class="deck-footer" style="font-size:13px">')
            for viewing in ("screen", "room")
        ], CAPACITY_STYLE)
        self.assertEqual(report["summary"]["errors"], 0)
        for page in report["pages"]:
            small = {issue["role"]: issue for issue in page["issues"] if issue["code"] == "small-text"}
            self.assertEqual(set(small), {"caption", "footer"})
            for role, threshold in (("caption", 16), ("footer", 14)):
                self.assertEqual(small[role]["threshold"], threshold)
                self.assertTrue(all(sample["role"] == role and sample["threshold"] == threshold
                                    for sample in small[role]["samples"]))
        self.assertEqual(checker.exit_code(report), 0)
        self.assertEqual(checker.exit_code(report, strict=True), 2)

    def test_auxiliary_class_names_do_not_lower_advisory_thresholds_in_legacy_or_invalid_layouts(self):
        report = self.inspect([
            '<p class="deck-caption" style="font-size:18px">Legacy caption.</p>'
            '<footer class="deck-footer" style="font-size:16px">Legacy footer.</footer>',
            capacity_page('<p class="deck-block">A concise explanation.</p>'
                          '<p class="deck-caption" style="font-size:18px">Invalid contract caption.</p>',
                          page_attrs='data-viewing="unknown"'),
        ], CAPACITY_STYLE)
        for page in report["pages"]:
            small = [issue for issue in page["issues"] if issue["code"] == "small-text"]
            self.assertEqual(len(small), 1)
            self.assertEqual(small[0]["role"], "text")
            self.assertEqual(small[0]["threshold"], 24)
            self.assertGreaterEqual(small[0]["count"], 2)
        self.assertIn("layout-contract-invalid", self.codes(report, 1))

    def test_explicit_min_font_keeps_global_and_viewing_context_advisories(self):
        content = ('<p class="deck-block" style="font-size:22px">Primary explanation below the screen recommendation.</p>'
                   '<p class="deck-caption" style="font-size:18px">Normal caption.</p>')
        for threshold, expected_roles in ((24, {"text", "caption", "footer"}), (12, set())):
            with self.subTest(threshold=threshold):
                report = self.inspect([capacity_page(content)], CAPACITY_STYLE, min_font=threshold)
                small = [issue for issue in report["pages"][0]["issues"] if issue["code"] == "small-text"]
                self.assertEqual({issue["role"] for issue in small}, expected_roles)
                self.assertTrue(all(issue["threshold"] == threshold for issue in small))
                self.assertIn("body-min-font", self.codes(report))
                self.assertEqual(checker.exit_code(report), 0)
                self.assertEqual(checker.exit_code(report, strict=True), 2)

    def test_capacity_overview_has_no_default_count_limit_and_accepts_project_budgets_above_six(self):
        def points(count):
            return ''.join(f'<p class="deck-block">Short label {i}</p>' for i in range(count))
        report = self.inspect([
            capacity_page(points(8), page_attrs='data-max-blocks="8"'),
            capacity_page(points(8), body_attrs='data-max-blocks="12"'),
            capacity_page(points(8)),
        ], CAPACITY_STYLE)
        self.assertEqual(report["summary"]["errors"], 0)
        for index, max_blocks in ((0, 8), (1, 12), (2, None)):
            self.assertNotIn("body-block-budget", self.codes(report, index))
            budget = report["pages"][index]["layoutBudget"]
            self.assertEqual(budget["blockCount"], 8)
            self.assertEqual(budget["maxBlocks"], max_blocks)
        self.assertEqual(checker.exit_code(report), 0)
        self.assertEqual(checker.exit_code(report, strict=True), 0)

    def test_capacity_long_table_exceeds_body_before_it_exceeds_canvas(self):
        table = '<table class="deck-block" style="border-collapse:collapse;font:28px Arial">' + ''.join(
            f'<tr style="height:50px"><td>Row {i}</td><td>One more technical detail</td></tr>' for i in range(9)) + '</table>'
        report = self.inspect([capacity_page(table, header_attrs='style="height:300px"')], CAPACITY_STYLE)
        self.assertIn("body-text-outside", self.codes(report))
        self.assertIn("body-capacity-exceeded", self.codes(report))
        self.assertNotIn("text-outside-slide", self.codes(report))
        self.assertEqual(checker.exit_code(report), 1)

    def test_pending_image_does_not_skip_overflow_or_certify_the_draft(self):
        # A reserved slot with unavailable manual-generation artwork must still
        # expose a too-tall table plus its bottom condition. No fixture artwork
        # is substituted into the authored source to manufacture a pass.
        table = '<table class="deck-block" style="border-collapse:collapse;font:24px Arial">' + ''.join(
            f'<tr style="height:80px"><td>Layer {i}</td><td>Necessary component names</td></tr>'
            for i in range(6)) + '</table>'
        body = ('<div class="deck-block">' + table +
                '<p style="font-size:24px">A bottom condition must remain above the footer.</p></div>'
                '<figure class="deck-block" style="margin:0">'
                '<img src="assets/pending-explanation.png" width="480" height="300" alt="Pending explanation">'
                '<figcaption class="deck-caption">Caption belongs in the capacity budget.</figcaption></figure>')
        report = self.inspect([capacity_page(body, header_attrs='style="height:200px"')], CAPACITY_STYLE)
        self.assertEqual(len(report["pages"]), 1)
        self.assertIn("layoutBudget", report["pages"][0])
        self.assertIn("readiness-failed", {issue["code"] for issue in report["issues"]})
        self.assertIn("image-failed", self.codes(report))
        self.assertIn("body-capacity-exceeded", self.codes(report))
        self.assertIn("body-text-outside", self.codes(report))
        self.assertEqual(checker.exit_code(report), 1)

    def test_capacity_uses_authored_padding_without_imposing_a_minimum_reserve(self):
        def bottom_label(bottom):
            return f'<p class="deck-block" style="position:absolute;bottom:{bottom}px;left:0">A concise bottom-aligned label.</p>'
        report = self.inspect([
            capacity_page(bottom_label(0), body_attrs='style="padding-bottom:0"'),
            capacity_page(bottom_label(12), body_attrs='style="padding-bottom:12px"'),
            capacity_page(bottom_label(0), body_attrs='style="padding-bottom:12px"'),
        ], CAPACITY_STYLE)
        for index, reserve in ((0, 0), (1, 12), (2, 12)):
            self.assertEqual(report["pages"][index]["layoutBudget"]["bottomReserve"], reserve)
        for index in (0, 1):
            self.assertFalse(any(issue["severity"] == "error" for issue in report["pages"][index]["issues"]))
        self.assertIn("body-capacity-exceeded", self.codes(report, 2))
        self.assertEqual(checker.exit_code(report), 1)

    def test_capacity_image_gallery_with_only_captions_is_advisory(self):
        pixel = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII='
        gallery = ''.join(
            f'<figure class="deck-block" style="margin:0"><img src="{pixel}" width="320" height="160" alt="Geometry fixture">'
            f'<figcaption class="deck-caption">Image study {i}</figcaption></figure>'
            for i in range(2))
        report = self.inspect([capacity_page(gallery)], CAPACITY_STYLE)
        self.assertIn("body-caption-only", self.codes(report))
        self.assertEqual(report["summary"]["errors"], 0)
        self.assertEqual(report["summary"]["review"], 0)
        self.assertEqual(checker.exit_code(report), 0)
        self.assertEqual(checker.exit_code(report, strict=True), 2)

    def test_capacity_breathing_room_and_region_boundaries_cannot_be_exempted(self):
        report = self.inspect([
            capacity_page('<p class="deck-block" style="position:absolute;bottom:0;left:0">Text in the reserved gap</p>'),
            capacity_page('<article class="deck-block"><p>Shifted into the heading.</p></article>',
                          body_attrs='style="transform:translateY(-80px)"'),
            capacity_page('<article class="deck-block" data-web-check-allow="body-min-font" '
                          'data-web-check-reason="Do not silently remove the advisory"><p style="font-size:20px">Small body text</p></article>'),
        ], CAPACITY_STYLE)
        self.assertIn("body-capacity-exceeded", self.codes(report, 0))
        self.assertIn("body-region-overlap", self.codes(report, 1))
        self.assertIn("body-min-font", self.codes(report, 2))
        self.assertIn("invalid-exemption", self.codes(report, 2))
        self.assertEqual(report["pages"][2]["exemptions"], [])
        self.assertEqual(checker.exit_code(report), 1)

    def test_capacity_contract_rejects_invalid_region_and_block_budgets(self):
        report = self.inspect([
            '<div class="deck-page"><header class="deck-header"><h1>Missing body and footer</h1></header></div>',
            capacity_page('<article class="deck-block"><p>Readable</p></article>', body_attrs='data-max-blocks="0"'),
            capacity_page('<p class="deck-caption">This cannot stand in for all core body content.</p>'),
            '<p>A legacy page is not silently enrolled in a capacity contract.</p>',
        ], CAPACITY_STYLE)
        self.assertIn("layout-contract-invalid", self.codes(report, 0))
        self.assertIn("layout-contract-invalid", self.codes(report, 1))
        self.assertIn("body-caption-only", self.codes(report, 2))
        self.assertNotIn("layoutBudget", report["pages"][3])

    def test_capacity_authored_scaling_is_reviewed_without_counting_player_zoom(self):
        report = self.inspect([
            capacity_page('<div class="deck-block" style="transform:scale(.5);transform-origin:top left"><p>Small after transform</p></div>'),
            capacity_page('<div class="deck-block" style="scale:.5;transform-origin:top left"><p>Small after independent scale</p></div>'),
            capacity_page('<p class="deck-block">Normal authored size</p>'),
        ], CAPACITY_STYLE + '<style>.deck-web-canvas{transform:scale(.5)!important}</style>')
        for index in (0, 1):
            self.assertIn("body-text-scaled", self.codes(report, index))
            budget = report["pages"][index]["layoutBudget"]
            self.assertEqual(budget["minBodyFont"], 32)
            self.assertEqual(budget["minRenderedBodyFont"], 16)
            self.assertEqual(budget["transformedBodyText"][0]["scale"], .5)
        self.assertNotIn("body-text-scaled", self.codes(report, 2))
        self.assertEqual(report["pages"][2]["layoutBudget"]["minRenderedBodyFont"], 32)
        self.assertEqual(checker.exit_code(report), 0)
        self.assertEqual(checker.exit_code(report, strict=True), 2)

    def test_capacity_unmarked_body_copy_is_advisory_but_captions_do_not_trigger_it(self):
        report = self.inspect([
            capacity_page(''.join(f'<p style="margin:0">Independent point {i}</p>' for i in range(4))),
            capacity_page('<p class="deck-block">One properly assigned point</p><p class="deck-caption">Auxiliary caption</p>'),
        ], CAPACITY_STYLE)
        self.assertIn("body-unmarked-content", self.codes(report, 0))
        self.assertEqual(report["pages"][0]["layoutBudget"]["blockCount"], 0)
        self.assertNotIn("body-unmarked-content", self.codes(report, 1))
        self.assertEqual(report["summary"]["errors"], 0)
        self.assertEqual(checker.exit_code(report), 0)
        self.assertEqual(checker.exit_code(report, strict=True), 2)

    def test_capacity_header_and_footer_text_must_stay_in_their_regions(self):
        report = self.inspect([
            capacity_page('<p class="deck-block" style="margin-top:160px">Body begins later.</p>',
                          title='First line<br>Second line<br>Third line', header_attrs='style="height:20px"'),
            capacity_page('<p class="deck-block">A short explanation.</p>').replace(
                '<footer class="deck-footer">', '<footer class="deck-footer" style="height:10px">'),
        ], CAPACITY_STYLE)
        for index, region in ((0, "header"), (1, "footer")):
            violations = [issue for issue in report["pages"][index]["issues"] if issue["code"] == "region-text-outside"]
            self.assertTrue(any(issue["region"] == region for issue in violations))
        self.assertEqual(checker.exit_code(report), 1)

    def test_capacity_text_and_images_need_regions_and_images_cannot_exceed_boundaries(self):
        pixel = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII='
        image = f'<img src="{pixel}" alt="Fixture image" style="width:40px;height:20px">'
        good = capacity_page('<p class="deck-block">A short explanation.</p>').replace(
            '<h1>A focused conclusion</h1>', '<h1>A focused conclusion</h1>' + image).replace(
                'Source and page number</footer>', 'Source and page number' + image + '</footer>')
        unassigned = capacity_page('<p class="deck-block">Readable text</p>')[:-6] + (
            f'<img src="{pixel}" alt="Clipped image" style="position:absolute;left:1540px;top:300px;width:400px;height:200px"></div>')
        bad_footer = capacity_page('<p class="deck-block">Readable text</p>').replace(
            '<footer class="deck-footer">', '<footer class="deck-footer" style="height:30px">' + image.replace('height:20px', 'height:100px'))
        unassigned_text = capacity_page('<p class="deck-block">Readable text</p>')[:-6] + (
            '<p style="position:absolute;left:800px;top:500px;font-size:18px">Unassigned primary content</p></div>')
        report = self.inspect([good, unassigned, bad_footer, unassigned_text], CAPACITY_STYLE)
        self.assertNotIn("layout-image-unassigned", self.codes(report, 0))
        self.assertNotIn("layout-image-outside", self.codes(report, 0))
        self.assertIn("layout-image-unassigned", self.codes(report, 1))
        self.assertIn("layout-image-outside", self.codes(report, 1))
        self.assertIn("layout-image-outside", self.codes(report, 2))
        self.assertIn("layout-text-unassigned", self.codes(report, 3))
        self.assertNotIn("layout-text-unassigned", self.codes(report, 0))
        self.assertEqual(checker.exit_code(report), 1)

    def test_actual_layout_starter_passes_capacity_with_a_test_image(self):
        # This tiny decoded bitmap exists only to exercise geometry in a test;
        # it is not a generated illustration or a finished deck deliverable.
        pixel = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII='
        authored = (compiler.ASSETS / 'layout-starter.html').read_text(encoding='utf-8').replace('src="assets/chapter-focus.png"', f'src="{pixel}"')
        with tempfile.TemporaryDirectory(prefix="web-capacity-starter-") as folder:
            path = Path(folder) / 'deck.html'
            path.write_text(compiler.compile_html(authored), encoding='utf-8')
            report = checker.inspect(path, stability_ms=100)
        self.assertEqual(len(report["pages"]), 3)
        self.assertEqual(checker.exit_code(report), 0, report)
        self.assertEqual(checker.exit_code(report, strict=True), 0, report)
        for page in report["pages"]:
            self.assertIn("layoutBudget", page)
            self.assertGreater(page["layoutBudget"]["availableHeight"], 0)
            self.assertFalse(any(issue["code"] == "small-text" for issue in page["issues"]), page)

    def test_raster_policy_checks_script_inserted_svg_and_computed_css_resources(self):
        head = ('<meta name="deck-media-policy" content="generated-raster">'
                '<style>#art{width:100px;height:100px;background-image:url("data:image/svg+xml,%3Csvg%20xmlns=\'http://www.w3.org/2000/svg\'%20/%3E")}</style>'
                '<script>window.__deck_charts_ready=new Promise(resolve=>setTimeout(()=>{'
                'const svg=document.createElementNS("http://www.w3.org/2000/svg","svg");'
                'document.querySelector("section.slide").appendChild(svg);resolve();},30));</script>')
        report = self.inspect(['<div id="art"></div><p>Raster-only delivery</p>'], head)
        violations = [issue for issue in report["pages"][0]["issues"] if issue["code"] == "media-policy"]
        self.assertTrue(any(issue["source"] == "inline-svg" for issue in violations))
        self.assertTrue(any("backgroundImage" in issue["source"] for issue in violations))
        self.assertEqual(checker.exit_code(report), 1)

    def test_svg_fill_override_needs_review_and_static_content_is_stable(self):
        report = self.inspect([
            '<svg width="500" height="300"><rect width="500" height="300" fill="#223344"></rect>'
            '<text x="30" y="100" font-size="32" fill="white">A readable label</text></svg>'
        ], head='<style>svg text{fill:#112233}</style>')
        self.assertIn("svg-fill-overridden", self.codes(report))
        self.assertNotIn("unstable-layout", self.codes(report))
        self.assertGreater(report["pages"][0]["stability"]["samples"], 1)
        self.assertEqual(checker.exit_code(report), 2)


if __name__ == "__main__":
    unittest.main()
