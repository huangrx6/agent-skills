"""Content visibility and painted contrast, using actual browser probes."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/deck-authoring/scripts"
FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    spec = importlib.util.spec_from_file_location(f"_quality_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


check, measure = load("check"), load("measure")
collision = check.layout_mod.collision


class TestQualityContracts(unittest.TestCase):
    def test_chart_source_is_caption_with_spacing_but_not_overlap_exemption(self):
        source = {"id": "s1.chartSource", "role": "caption", "slide": 1,
                  "x": 84, "y": 240, "w": 300, "h": 24}
        chart = {"id": "s1.chart", "role": "chart", "slide": 1,
                 "x": 84, "y": 288, "w": 900, "h": 350}
        self.assertEqual(collision.group_of(source), "caption")
        self.assertEqual(collision.group_of({"id": "s1.custom-source", "role": "caption"}), "caption")
        self.assertEqual(collision.violations(collision.build_boxes([source, chart]), frozenset()), [])
        other_text = {**source, "id": "s1.caption", "y": 250}
        result = collision.violations(collision.build_boxes([source, other_text]), frozenset())
        self.assertEqual(result[0]["kind"], "text-overlap")

    def test_live_body_does_not_receive_desktop_shrink_advice(self):
        measured = {"elements": [{"id": f"s1.bullet.{i}", "role": "bullet",
                                   "slide": 1, "fontSize": 32} for i in range(4)]}
        deck = {"delivery": "live", "slides": [{"type": "content-text"}]}
        self.assertEqual(check._check_type_size(measured, deck, {}), [])
        self.assertEqual(check._delivery_type_notes(measured, deck, {}), [])
        near = check._check_type_size(measured, {**deck, "delivery": "async"}, {})
        self.assertTrue(any("宣言档" in note for note in near), near)
        self.assertTrue(any("整体偏大" in note for note in near), near)

    def test_chart_data_gate_matches_scatter_and_series_input_contract(self):
        for row in ({"label": "A", "x": 1, "y": 2},
                    {"label": "A", "x": 1, "value": 2},
                    {"label": "A", "x": 1, "y": 2, "value": 999}):
            for payload in ({"data": [row]}, {"series": [{"name": "S", "data": [row]}]}):
                slide = {"type": "chart", "title": "T", "chart": "scatter", **payload}
                self.assertEqual(check._check_chart_data({"slides": [slide]}), [])
        for value in (None, True, float("nan"), float("inf"), "2"):
            row = {"label": "A", "x": 1, "y": value}
            slide = {"type": "chart", "title": "T", "chart": "scatter",
                     "series": [{"name": "S", "data": [row]}]}
            problems = check._check_chart_data({"slides": [slide]})
            self.assertTrue(any("series[0].data[0].y" in p for p in problems), problems)

    def test_chart_data_gate_rejects_missing_ambiguous_and_bad_series(self):
        base = {"type": "chart", "title": "T", "chart": "line"}
        rows = [{"label": "A", "value": 1}]
        for payload in ({}, {"data": rows, "series": [{"name": "S", "data": rows}]},
                        {"series": [{"name": "S", "data": [{"label": "A", "value": False}]}]},
                        {"series": [{"name": "S", "data": [{"label": "", "value": 1}]}]}):
            self.assertTrue(check._check_chart_data({"slides": [{**base, **payload}]}), payload)

    def test_delivery_advice_uses_measured_size_not_declared_tier(self):
        measured = {"elements": [
            {"id": "s1.bullet.0", "role": "bullet", "slide": 1, "fontSize": 24},
            {"id": "s1.caption", "role": "bullet", "slide": 1, "fontSize": 12},
            {"id": "s2.chart", "role": "chart", "slide": 2,
             "textRuns": [{"fontSize": 16}]}]}
        deck = {"delivery": "live", "slides": [{"type": "content-text"}, {"type": "chart"}]}
        notes = check._delivery_type_notes(measured, deck, {"type": {"bullet": 40, "chartLabel": 40}})
        self.assertEqual(len(notes), 2)
        self.assertIn("24px", notes[0])
        self.assertIn("16px", notes[1])
        self.assertEqual(check._delivery_type_notes(measured, {**deck, "delivery": "async"}, {}), [])
        self.assertEqual(check._delivery_type_notes(measured, {"slides": deck["slides"]}, {}), [])

    def test_brand_override_and_added_palette_are_shared_with_compile(self):
        with tempfile.TemporaryDirectory() as tmp:
            brand = Path(tmp) / "brands/acme"
            brand.mkdir(parents=True)
            colors = {"primary": "#EEEEEE", "secondary": "#EEEEEE",
                      "background": "#FFFFFF", "text": "#EEEEEE"}
            (brand / "brand.json").write_text(json.dumps({
                "version": 1, "colorSets": {"blue": colors, "brand-only": colors}}))
            spec = {"deck": {"style": str(FIXTURES / "styles/swiss-grid"), "brand": "acme",
                             "colorSet": "brand-only", "slides": [{"type": "title", "title": "T"}]}}
            tokens = check.style_tokens(spec, project_dir=tmp)
            resolved = check.render_mod.deck_mod.compile_spec(spec, project_dir=tmp)
            self.assertEqual(tokens["colorSets"], resolved["style"]["tokens"]["colorSets"])
            self.assertEqual(tokens["colorSets"]["blue"], colors)

    def test_pending_missing_and_error_charts_are_blocked(self):
        deck = {"slides": [{"type": "chart"}]}
        for state in (None, "pending", "error:bad"):
            measured = {"elements": [{"id": "s1.chart", "chartReady": state}]}
            self.assertTrue(check._check_chart_readiness(measured, deck), state)
        self.assertEqual(check._check_chart_readiness(
            {"elements": [{"id": "s1.chart", "chartReady": "ready"}]}, deck), [])

    def test_same_group_waives_spacing_but_not_text_overlap(self):
        els = [{"id": f"s1.bullet.{i}", "role": "bullet", "slide": 1,
                "x": 10, "y": y, "w": 100, "h": 30} for i, y in enumerate((10, 25))]
        result = collision.violations(collision.build_boxes(els), frozenset())
        self.assertEqual(result[0]["kind"], "text-overlap")
        els[1]["y"] = 42
        self.assertEqual(collision.violations(collision.build_boxes(els), frozenset()), [])

    def test_hero_never_waives_text_overlap(self):
        els = [{"id": f"s1.{role}", "role": role, "slide": 1,
                "x": 10, "y": 10, "w": 100, "h": 30} for role in ("title", "bullet")]
        self.assertEqual(collision.violations(collision.build_boxes(els), frozenset({1}))[0]["kind"],
                         "text-overlap")

    def test_range_rectangles_avoid_wide_container_false_positive(self):
        els = [{"id": f"s1.bullet.{i}", "role": "bullet", "slide": 1,
                "x": 0, "y": 0, "w": 600, "h": 60,
                "textRects": [{"x": x, "y": 10, "w": 80, "h": 20}]}
               for i, x in enumerate((10, 200))]
        self.assertEqual(collision.violations(collision.build_boxes(els), frozenset()), [])


@unittest.skipUnless(os.path.isfile(measure.CHROME), "Chrome is required")
class TestBrowserQuality(unittest.TestCase):
    def probe(self, markup, css="", script="", ids=("s1.title",)):
        manifest = [{"id": eid, "slide": 1, "role": "title", "text": "Text"} for eid in ids]
        html = ('<!doctype html><html><head><style>'
                'body{margin:0;background:white;color:black} '
                '.slide{width:1600px;height:900px;overflow:hidden;background:white} '
                'h1{margin:0;font:32px/1.2 Arial} ' + css + '</style></head><body>'
                '<section class="slide">' + markup + '</section>'
                '<script type="application/json" id="__deck_manifest">' + json.dumps(manifest) +
                '</script><script>' + script + '</script></body></html>')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.html"
            path.write_text(html)
            return measure.measure(str(path))

    def test_css_foreground_override_is_measured(self):
        data = self.probe('<h1 data-m="s1.title">Text</h1>', 'h1{color:#eee}')
        self.assertTrue(check._check_rendered_contrast(data, {}))

    def test_ancestor_opacity_is_composited(self):
        data = self.probe('<div style="opacity:.2"><h1 data-m="s1.title">Text</h1></div>')
        self.assertAlmostEqual(data["elements"][0]["opacity"], .2)
        self.assertTrue(check._check_rendered_contrast(data, {}))

    def test_reverse_text_uses_its_actual_background(self):
        data = self.probe('<div style="background:black"><h1 data-m="s1.title">Text</h1></div>',
                          'h1{color:white}')
        self.assertEqual(check._check_rendered_contrast(data, {}), [])

    def test_hidden_ancestor_blocks_delivery(self):
        data = self.probe('<div style="display:none"><h1 data-m="s1.title">Text</h1></div>')
        self.assertFalse(data["elements"][0]["visible"])
        self.assertTrue(any("不可见" in p for p in check._check_measured_health(data)))

    def test_hidden_child_text_cannot_hide_in_a_visible_fixed_box(self):
        data = self.probe('<h1 data-m="s1.title" style="height:50px">'
                          '<span style="display:none">Text</span></h1>')
        self.assertTrue(data["elements"][0]["visible"])
        self.assertTrue(any("文字不可见" in p for p in check._check_measured_health(data)))

    def test_ancestor_clip_blocks_delivery(self):
        data = self.probe('<div style="height:12px;overflow:hidden">'
                          '<h1 data-m="s1.title">Text</h1></div>')
        self.assertTrue(any("祖先容器裁切" in p for p in check._check_measured_health(data)))

    def test_missing_manifest_element_blocks_delivery(self):
        data = self.probe('<h1>Text</h1>')
        self.assertEqual(data["missing_elements"][0]["id"], "s1.title")
        self.assertTrue(any("元素缺失" in p for p in check._check_measured_health(data)))

    def test_empty_svg_is_not_ready_and_promise_completion_is_measured(self):
        markup = '<div data-m="s1.chart"><div class="g2" data-g2="x"><svg></svg></div></div>'
        data = self.probe(markup, ids=("s1.chart",))
        self.assertEqual(data["elements"][0]["chartReady"], "pending")
        script = ('window.__deck_charts_ready=new Promise(function(resolve){setTimeout(function(){'
                  'document.querySelector(".g2").setAttribute("data-chart-ready","1");resolve();},50)});')
        ready = self.probe(markup, script=script, ids=("s1.chart",))
        self.assertEqual(ready["elements"][0]["chartReady"], "ready")

    def test_export_typography_and_image_fit_are_measured(self):
        data = self.probe('<h1 data-m="s1.title">Text</h1>',
                          'h1{text-align:center;letter-spacing:2px;line-height:48px}')
        el = data["elements"][0]
        self.assertEqual((el["textAlign"], el["letterSpacing"], el["lineHeight"]),
                         ("center", "2px", "48px"))
        image = self.probe('<figure data-m="s1.image"><img style="object-fit:cover;'
                           'object-position:25% 40%;width:100px;height:100px" '
                           'src="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 '
                           'width=%221%22 height=%221%22/%3E"></figure>', ids=("s1.image",))
        self.assertEqual((image["elements"][0]["objectFit"], image["elements"][0]["objectPosition"]),
                         ("cover", "25% 40%"))


if __name__ == "__main__":
    unittest.main()
