#!/usr/bin/env python3
"""Design signals are advisories, not scores: pin the observable rules."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[2] / "skills/deck-authoring/scripts"


def load(name):
    spec = importlib.util.spec_from_file_location("_test_" + name, SCRIPTS / (name + ".py"))
    if spec is None or spec.loader is None:
        raise RuntimeError(name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


signals = load("design_signals")
compiler = load("web_deck")
try:
    signals._connect()
    HAS_BROWSER = True
except RuntimeError:
    HAS_BROWSER = False


def analyzed_page(*, heading=64, body=26, family="Source Han Serif", chars=240,
                  card_groups=None, gaps=None, centered=0, headings=1,
                  images=None, blocks=None, margins=None, effects=None,
                  heading_text="A page with a real focal point"):
    run = {"text": "这是一段用于检查行长和图注关系的正文。" * 8, "body": True,
           "chars": chars, "lineCount": max(1, chars // 40), "fontSize": body,
           "family": family, "x": 112, "y": 260, "w": 760, "h": 80}
    heading_run = {"text": heading_text, "heading": True, "chars": len(heading_text),
                   "lineCount": 1, "fontSize": heading, "family": family,
                   "x": 112, "y": 100, "w": 900, "h": heading, "align": "center" if centered else "left"}
    return {
        "slide": 1, "title": "Test", "runs": [heading_run, run],
        "headings": [heading_run] * max(1, headings),
        "type": {"sizes": [18, body, heading], "headingSizes": [heading] * max(1, headings),
                 "bodySizes": [body], "families": [family], "weights": ["400", "500"]},
        "colors": {"text": ["rgb(34,34,34)"], "backgrounds": []},
        "blocks": blocks or [
            {"x": 112, "right": 872, "y": 100, "w": 760, "h": 40},
            {"x": 112, "right": 872, "y": 260, "w": 760, "h": 80},
        ],
        "gaps": gaps or [], "images": images or [], "cardGroups": card_groups or [],
        "effects": effects or {}, "charCount": chars, "margins": margins or
        {"left": 112, "top": 100, "right": 112, "bottom": 120},
        "centeredHeadings": centered, "headingCount": headings,
        "regions": {"header": {"h": 120}, "body": {"y": 240}},
        "viewing": "screen", "layout": "image-right",
    }


def codes(page):
    return {signal["code"] for signal in signals.analyze_page(page)["signals"]}


class TestPageSignals(unittest.TestCase):
    def test_flat_scale_and_default_display_type(self):
        page = analyzed_page(heading=40, body=24, family="Arial")
        found = codes(page)
        self.assertIn("flat-type-scale", found)
        self.assertIn("default-display-type", found)

    def test_strong_scale_with_a_real_typeface_is_not_flagged(self):
        found = codes(analyzed_page(heading=96, body=28, family="Source Han Serif"))
        self.assertNotIn("flat-type-scale", found)
        self.assertNotIn("default-display-type", found)

    def test_equal_card_grid_and_shadow_stack(self):
        page = analyzed_page(card_groups=[{"count": 3, "width": 300, "height": 200,
                                           "gap": 24, "top": 300}],
                             effects={"shadows": 3, "rounded": 4, "gradients": 0})
        found = codes(page)
        self.assertIn("equal-card-grid", found)
        self.assertIn("shadow-card-stack", found)

    def test_uniform_gaps_are_flagged_only_on_low_text_pages(self):
        found = codes(analyzed_page(chars=400, gaps=[24] * 8))
        self.assertIn("uniform-gap", found)
        dense = codes(analyzed_page(chars=1200, gaps=[24] * 8))
        self.assertNotIn("uniform-gap", dense)

    def test_centered_headings_and_loose_alignment(self):
        page = analyzed_page(headings=3, centered=3, chars=300,
                             blocks=[{"x": 100 + i * 37, "right": 300 + i * 37,
                                      "y": 100 + i * 90, "w": 120, "h": 30}
                                     for i in range(9)])
        found = codes(page)
        self.assertIn("centered-everything", found)
        self.assertIn("loose-alignment", found)

    def test_no_signals_for_a_quiet_single_text_page(self):
        found = codes(analyzed_page(chars=80, gaps=[], blocks=[
            {"x": 112, "right": 872, "y": 100, "w": 760, "h": 40}]))
        self.assertEqual(found, set())

    def test_deck_flags_a_repeated_silhouette_and_missing_hero(self):
        page = signals.analyze_page(analyzed_page(heading=40, body=24, family="Arial"))
        raw = analyzed_page(heading=40, body=24, family="Arial")
        pages = [{**page, "slide": index, "title": f"P{index}"} for index in range(1, 5)]
        raws = [{**raw, "slide": index} for index in range(1, 5)]
        deck = signals.analyze_deck(pages, raws)
        found = {signal["code"] for signal in deck["signals"]}
        self.assertIn("repeated-silhouette", found)
        self.assertIn("no-hero-page", found)

    def test_report_exit_codes_are_advisory_by_default(self):
        report = signals.summarize({"pages": [], "issues": []})
        self.assertEqual(signals.exit_code(report), 0)
        report["summary"]["review"] = 1
        self.assertEqual(signals.exit_code(report), 0)
        self.assertEqual(signals.exit_code(report, strict=True), 2)
        report["summary"]["errors"] = 1
        self.assertEqual(signals.exit_code(report), 1)

    def test_missing_file_does_not_launch_browser(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            signals.inspect("/no-such-design-signals-fixture.html")

    def test_cli_rejects_report_that_overwrites_input(self):
        with tempfile.TemporaryDirectory(prefix="design-signals-target-") as folder:
            path = Path(folder) / "deck.html"
            path.write_text("original artifact", encoding="utf-8")
            with patch.object(signals, "inspect") as inspect, \
                    patch("sys.stderr"), self.assertRaises(SystemExit) as exc:
                signals.main([str(path), "--json", str(path)])
            self.assertEqual(exc.exception.code, 2)
            inspect.assert_not_called()
            self.assertEqual(path.read_text(), "original artifact")


@unittest.skipUnless(HAS_BROWSER, "Chrome and websockets are required")
class TestDesignSignalsBrowser(unittest.TestCase):
    def inspect(self, pages, css=""):
        slides = "".join(
            f'<section class="slide" data-slide="{index}" data-title="Fixture {index}" '
            f'data-enter=".4" data-hold="1">{body}</section>'
            for index, body in enumerate(pages, 1))
        source = ('<!doctype html><html><head><meta charset="utf-8"><style>'
                  'body{margin:0}' + css + '</style></head><body>' + slides + '</body></html>')
        with tempfile.TemporaryDirectory(prefix="design-signals-test-") as folder:
            path = Path(folder) / "deck.html"
            path.write_text(compiler.compile_html(source), encoding="utf-8")
            return signals.inspect(path, timeout=30)

    def test_bland_page_reports_flat_scale_and_default_type(self):
        css = ('.deck-page{--deck-title-size:40px;--deck-body-size:24px;'
               '--deck-display-font:system-ui, sans-serif}')
        report = self.inspect([(
            '<div class="deck-page" data-layout="image-right"><header class="deck-header">'
            '<h1>A generic title that reads like a document</h1></header><main class="deck-body">'
            '<div class="deck-copy"><p class="deck-block">'
            + "This paragraph has enough body text to evaluate the type scale and line length. " * 4
            + '</p></div></main><footer class="deck-footer"><span>01</span></footer></div>')], css)
        found = {signal["code"] for page in report["pages"] for signal in page["signals"]}
        self.assertIn("flat-type-scale", found)
        self.assertIn("default-display-type", found)
        self.assertEqual(report["summary"]["errors"], 0)

    def test_crafted_page_clears_the_same_signals(self):
        css = ('.deck-page{--deck-title-size:96px;--deck-body-size:28px;'
               '--deck-display-font:Georgia, serif}')
        report = self.inspect([(
            '<div class="deck-page" data-layout="image-right"><header class="deck-header">'
            '<h1>A specific claim with a real scale jump</h1></header><main class="deck-body">'
            '<div class="deck-copy"><p class="deck-block">'
            + "This paragraph has enough body text to evaluate the type scale and line length. " * 4
            + '</p></div></main><footer class="deck-footer"><span>01</span></footer></div>')], css)
        found = {signal["code"] for page in report["pages"] for signal in page["signals"]}
        self.assertNotIn("flat-type-scale", found)
        self.assertNotIn("default-display-type", found)


if __name__ == "__main__":
    unittest.main()
