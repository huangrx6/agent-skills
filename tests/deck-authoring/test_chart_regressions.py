#!/usr/bin/env python3
"""Chart regressions: validate rendered marks, not merely the existence of a canvas."""
from __future__ import annotations

import copy
import html
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/deck-authoring/scripts/render.py"
module_spec = importlib.util.spec_from_file_location("_chart_regression_render", SCRIPT)
render = importlib.util.module_from_spec(module_spec)
sys.modules[module_spec.name] = render
module_spec.loader.exec_module(render)
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
COLORS = {"primary": "#0033CC", "secondary": "#0A0A0A",
          "background": "#FFFFFF", "text": "#0A0A0A"}
SERIES = [
    {"name": "A", "data": [{"label": "Q1", "value": 15},
                             {"label": "Q2", "value": 30},
                             {"label": "Q3", "value": 22}]},
    {"name": "B", "data": [{"label": "Q1", "value": 25},
                             {"label": "Q2", "value": 20},
                             {"label": "Q3", "value": 35}]},
]


def chart_slides():
    return [
        {"type": "chart", "title": "Dataset", "message": "Composition",
         "chart": "donut", "data": [{"label": "A", "value": 55},
                                      {"label": "B", "value": 30},
                                      {"label": "C", "value": 15}]},
        {"type": "chart", "title": "Line", "chart": "line", "series": SERIES},
        {"type": "chart", "title": "Area", "chart": "area", "series": SERIES},
        {"type": "chart", "title": "Scatter", "chart": "scatter",
         "data": [{"label": "A", "x": 1, "y": 20},
                  {"label": "B", "x": 5, "y": 10},
                  {"label": "C", "x": 9, "value": 30}]},
        {"type": "chart", "title": "Combo", "chart": "combo",
         "series": [dict(SERIES[0], mark="bar"), dict(SERIES[1], mark="line")]},
    ]


def page_for(slides):
    style = copy.deepcopy(render.load_style(str(
        ROOT / "tests/deck-authoring/fixtures/styles/minimal-baseline")))
    style["tokens"]["type"].update(small=48, caption=18)
    style["tokens"]["fonts"].update(display="Arial, sans-serif", body="Arial, sans-serif")
    spec = {"deck": {"style": "minimal-baseline", "colorSet": "blue", "seed": 17,
                     "title": "Regression", "slides": slides}}
    return render.render(spec, style)


def browser_probe(page, script, query=""):
    """Headless Chrome reads local HTML and emits JSON after the ready promise."""
    probe = ('<pre id="__chart_test" hidden></pre><script>'
             'window.__deck_charts_ready.then(async function(){try{'
             'var result=await (async function(){' + script + '})();'
             'document.getElementById("__chart_test").textContent=JSON.stringify(result);'
             '}catch(e){document.getElementById("__chart_test").textContent='
             'JSON.stringify({fatal:String(e)});}});</script>')
    with tempfile.TemporaryDirectory(prefix="deck-chart-test-") as td:
        path = Path(td) / "charts.html"
        path.write_text(page.replace("</body>", probe + "</body>"), encoding="utf-8")
        proc = subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
             "--virtual-time-budget=5000",
             "--dump-dom", path.as_uri() + query], capture_output=True, text=True, timeout=40)
        if proc.returncode:
            raise AssertionError(f"Chrome returned {proc.returncode}: {proc.stderr[-1000:]}")
        match = re.search(r'<pre id="__chart_test"[^>]*>(.*?)</pre>', proc.stdout, re.S)
        if not match or not match.group(1):
            raise AssertionError("Chart readiness promise did not settle")
        result = json.loads(html.unescape(match.group(1)))
        if isinstance(result, dict) and result.get("fatal"):
            raise AssertionError(result["fatal"])
        return result


class TestChartInputAndTitles(unittest.TestCase):
    def test_chart_headline_is_real_html_and_manifest_tracks_message(self):
        page = page_for(chart_slides()[:2])
        self.assertIn('data-m="s1.title" data-text="Composition">Composition</h1>', page)
        self.assertIn('data-m="s2.title" data-text="Line">Line</h1>', page)
        self.assertNotIn("&lt;h1", page)
        manifest = json.loads(re.search(
            r'id="__deck_manifest">(.*?)</script>', page, re.S).group(1))
        entries = {entry["id"]: entry for entry in manifest}
        self.assertEqual(entries["s1.title"]["text"], "Composition")
        self.assertEqual(entries["s1.chartSource"]["text"], "Dataset")
        self.assertEqual(entries["s1.chartSource"]["role"], "caption")

    def test_unit_is_visible_with_or_without_message_and_keeps_data_scale(self):
        slides = [dict(chart_slides()[0], unit="%"), dict(chart_slides()[1], unit="万元")]
        page = page_for(slides)
        visible_sources = re.findall(r'<div class="chartsrc"[^>]*>(.*?)</div>', page)
        self.assertEqual(visible_sources, ["Dataset · 单位：%", "单位：万元"])
        manifest = json.loads(re.search(
            r'id="__deck_manifest">(.*?)</script>', page, re.S).group(1))
        sources = [entry for entry in manifest if entry["id"].endswith(".chartSource")]
        self.assertEqual([entry["text"] for entry in sources], visible_sources)
        self.assertTrue(all(entry["role"] == "caption" for entry in sources))
        g2_specs = [json.loads(html.unescape(raw)) for raw in re.findall(r"data-g2='(.*?)'", page)]
        self.assertEqual([d["value"] for d in g2_specs[0]["data"]], [55, 30, 15])
        self.assertEqual([d["value"] for d in g2_specs[1]["data"]], [15, 30, 22, 25, 20, 35])

    def test_combo_requires_declared_marks(self):
        with self.assertRaisesRegex(SystemExit, "mark=bar"):
            render.chart_g2_spec({"chart": "combo", "series": SERIES}, COLORS)

    def test_chart_text_uses_full_opacity(self):
        spec = render.chart_g2_spec(chart_slides()[1], COLORS)
        for axis in spec["axis"].values():
            self.assertEqual(axis["labelOpacity"], 1)
            self.assertEqual(axis["titleOpacity"], 1)
        self.assertTrue(all(label["style"]["opacity"] == 1 for label in spec["labels"]))

    def test_unsupported_multi_series_is_not_silently_truncated(self):
        for kind in ("bar", "bar-horizontal", "donut", "scatter"):
            with self.subTest(kind=kind), self.assertRaisesRegex(SystemExit, "多 series"):
                render.chart_g2_spec({"chart": kind, "series": SERIES}, COLORS)

    def test_scatter_requires_numeric_x(self):
        with self.assertRaisesRegex(SystemExit, "数值 x"):
            render.chart_g2_spec({"chart": "scatter", "data": [{"label": "A", "value": 4}]}, COLORS)

    def test_compile_then_render_rejects_third_column(self):
        slide = {"type": "two-column", "title": "Too many columns",
                 "columns": [{"title": str(i), "bullets": ["Content"]} for i in range(3)]}
        with self.assertRaisesRegex(ValueError, "最多支持 2 栏"):
            page_for([slide])

    def test_compile_then_render_rejects_unimplemented_annotations(self):
        slide = dict(chart_slides()[0], annotations=[{"type": "reference", "value": 20}])
        with self.assertRaisesRegex(ValueError, "annotations 尚未实现"):
            page_for([slide])
        with self.assertRaisesRegex(ValueError, "annotations 尚未实现"):
            render.chart_g2_spec(slide, COLORS)

    def test_direct_resolved_render_has_the_same_guards(self):
        style = render.load_style(str(ROOT / "tests/deck-authoring/fixtures/styles/minimal-baseline"))
        spec = {"deck": {"style": "minimal-baseline", "colorSet": "blue", "seed": 17,
                         "slides": chart_slides()[:1]}}
        resolved = render.deck_mod.compile_spec(spec, style)
        resolved["deck"]["slides"][0]["annotations"] = [{"type": "reference", "value": 20}]
        with self.assertRaisesRegex(ValueError, "annotations 尚未实现"):
            render.render_resolved(resolved)
        slide = resolved["deck"]["slides"][0]
        slide.pop("annotations")
        slide.update(type="two-column", columns=[{}, {}, {}])
        with self.assertRaisesRegex(ValueError, "最多支持 2 栏"):
            render.render_resolved(resolved)


@unittest.skipUnless(os.path.isfile(CHROME), "Local Chrome is required for scene-graph verification")
class TestChartBrowser(unittest.TestCase):
    def test_present_and_cross_page_frames_keep_real_plot_width(self):
        page = page_for(chart_slides()[1:3]).replace(
            "await chart.render();", "await chart.render(); n.__test_chart=chart;")
        result = browser_probe(page, """
          var initialView=document.documentElement.getAttribute('data-view');
          var rows=[];
          function pause(){return new Promise(function(resolve){setTimeout(resolve,350);});}
          for(var i of [0,1,0,1]){
            var span=window.__deck_timeline[i];
            window.__deck.seek(span.start+span.enter+span.hold*0.5);
            await pause();
            var n=document.querySelectorAll('.g2')[i];
            var doc=n.__test_chart.getContext().canvas.document;
            var widths=Array.from(doc.querySelectorAll('.element')).map(function(e){
              return e.getBounds().halfExtents[0]*2;
            });
            rows.push({slide:i,canvasWidth:parseFloat(getComputedStyle(n.querySelector('canvas')).width),
              plotWidth:Math.max.apply(Math,widths),ready:n.getAttribute('data-chart-ready')});
          }
          return {initialView:initialView,rows:rows};
        """, query="?present")
        self.assertEqual(result["initialView"], "present")
        self.assertEqual(len(result["rows"]), 4)
        for row in result["rows"]:
            with self.subTest(row=row):
                self.assertEqual(row["ready"], "1")
                self.assertGreater(row["canvasWidth"], 1000)
                self.assertGreater(row["plotWidth"], 600)

    def test_all_chart_marks_render_with_their_data(self):
        page = page_for(chart_slides()).replace(
            "await chart.render();", "await chart.render(); n.__test_chart=chart;")
        rows = browser_probe(page, """
          return Array.from(document.querySelectorAll('.g2')).map(function(n){
            var doc=n.__test_chart.getContext().canvas.document;
            return {ready:n.getAttribute('data-chart-ready'), error:n.getAttribute('data-chart-error'),
              shapes:Array.from(doc.querySelectorAll('.element')).map(function(e){
                return {name:e.nodeName, fill:e.attributes.fill, stroke:e.attributes.stroke,
                  path:e.attributes.d, origin:e.attributes.transformOrigin};
              }), labels:doc.querySelectorAll('.label').length};
          });
        """)
        self.assertEqual([row["ready"] for row in rows], ["1"] * 5)
        self.assertTrue(all(row["error"] is None for row in rows))
        self.assertEqual([len(row["shapes"]) for row in rows], [3, 2, 2, 3, 4])
        donut, line, area, scatter, combo = rows
        self.assertEqual(len({s["fill"] for s in donut["shapes"]}), 3)
        self.assertTrue(all("A" in s["path"] for s in donut["shapes"]))
        self.assertEqual(len({s["stroke"] for s in line["shapes"]}), 2)
        self.assertEqual(len({s["fill"] for s in area["shapes"]}), 2)
        points = [tuple(map(float, s["origin"].split())) for s in scatter["shapes"]]
        self.assertLess(points[0][0], points[1][0])
        self.assertLess(points[1][0], points[2][0])
        self.assertGreater(points[1][1], points[0][1])  # y=10 lies below y=20
        self.assertLess(points[2][1], points[0][1])     # value=30 aliases y=30
        self.assertEqual([s["name"] for s in combo["shapes"]].count("rect"), 3)
        self.assertEqual([s["name"] for s in combo["shapes"]].count("path"), 1)

    def test_async_render_failure_is_reported_without_ready(self):
        page = page_for(chart_slides()[:1]).replace(
            render.G2_INIT_JS,
            'window.G2={Chart:function(){this.options=function(){};this.render=function(){'
            'return Promise.reject(new Error("deliberate async failure"));};}};\n'
            + render.G2_INIT_JS)
        row = browser_probe(page, """
          var n=document.querySelector('.g2');
          return {ready:n.getAttribute('data-chart-ready'),error:n.getAttribute('data-chart-error')};
        """)
        self.assertIsNone(row["ready"])
        self.assertEqual(row["error"], "deliberate async failure")


if __name__ == "__main__":
    unittest.main()
