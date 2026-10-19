"""Free-composition HTML compiler and real-browser playback/export contracts."""
from __future__ import annotations

import importlib.util
import asyncio
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/deck-authoring/scripts"
spec = importlib.util.spec_from_file_location("_web_deck_test", SCRIPTS / "web_deck.py")
web_deck = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web_deck)
from test_chart_regressions import browser_probe, CHROME, ws_connect


def source(*, head="", attrs="", body=None):
    if body is None:
        body = ('<section data-slide="1" class="slide" data-title="第一张" data-enter=".8" ' + attrs + '>'
                '<h1 id="hero" data-reveal="rise" data-at=".1" data-duration=".6">Title</h1>'
                '<div id="mask" data-reveal="wipe" data-duration=".5">Detail</div>'
                '<input id="editor" value="editable">'
                '</section><section class="slide" data-slide="2" data-title="第二张">End</section>')
    return ('<!doctype html><html lang="zh"><head><meta charset="utf-8">'
            '<style>h1 { transform: rotate(-3deg); font-size: 72px; } section {background:#fff}</style>'
            + head + '</head><body>' + body + '</body></html>')


class TestWebCompiler(unittest.TestCase):
    def test_source_coverage_keeps_static_text_deck_valid_and_reports_zero_features(self):
        authored = source(body='<section class="slide" data-slide="1" data-title="Text">'
                               '<p>No illustration is needed here.</p></section>')
        coverage = web_deck.source_coverage(authored)
        self.assertEqual(coverage['totals'], {'images': 0, 'inlineSvg': 0, 'reveals': 0})
        # Injected player controls are not authored motion evidence.
        compiled = web_deck.compile_html(authored)
        self.assertIn('__deck_web_runtime', compiled)
        with self.assertRaises(web_deck.SourceError):
            web_deck.source_coverage(compiled)
        with tempfile.TemporaryDirectory() as folder:
            original, output = Path(folder) / 'source.html', Path(folder) / 'deck.html'
            original.write_text(authored)
            stdout = io.StringIO()
            with patch('sys.stdout', stdout):
                self.assertEqual(web_deck.main([str(original), '-o', str(output)]), 0)
            self.assertIn('0 img slots, 0 inline SVG, 0 reveal targets', stdout.getvalue())

    def test_source_coverage_tracks_authored_features_per_page_without_claiming_readiness(self):
        authored = source().replace('</h1>', '</h1><img src="missing.png"><svg><rect /></svg>')
        # Comments and strings are not rendered image or reveal elements.
        authored = authored.replace('</head>', '<!-- <img src="not-real.png"> --></head>')
        coverage = web_deck.source_coverage(authored)
        self.assertEqual(coverage['totals'], {'images': 1, 'inlineSvg': 1, 'reveals': 2})
        self.assertEqual(coverage['pages'][1]['reveals'], 0)
        self.assertNotIn('ready', coverage)

    def test_raster_only_rejects_svg_markup_without_removing_default_support(self):
        for markup in ('<svg viewBox="0 0 10 10"><rect width="10" height="10" /></svg>',
                       '<SVG><text>Legacy vector</text></SVG>'):
            authored = source().replace('>Title</h1>', '>Title</h1>' + markup)
            self.assertIn(markup, web_deck.compile_html(authored))
            with self.subTest(markup=markup), self.assertRaisesRegex(web_deck.SourceError, "inline SVG"):
                web_deck.compile_html(authored, raster_only=True)

    def test_raster_only_rejects_svg_media_paths_and_mime_types(self):
        variants = (
            '<img src="media/diagram.svg">',
            '<img src="media/diagram.SVG?version=2#details">',
            '<img src="media/diagram%2Esv%67">',
            '<img src="media/diagram%23name.svg">',
            '<picture><source srcset="cover.png 1x, diagram.svg?x=2 2x"><img src="cover.png"></picture>',
            '<img src="cover.png" srcset="diagram%2Esvg#part 2x">',
            '<object data="https://example.test/render.SvG?version=1"></object>',
            '<embed src="diagram.svg#part">',
            '<object type="IMAGE/SVG+XML" data="render?format=vector"></object>',
            '<picture><source type="image/svg+xml" srcset="render"><img src="cover.png"></picture>',
            '<link rel="preload" as="image" imagesrcset="cover.png 1x, diagram.svg 2x">',
            '<img src="data:image/svg+xml,%3Csvg%20xmlns=%22http://www.w3.org/2000/svg%22/%3E">',
            '<img src="data:IMAGE/SVG+XML;base64,PHN2Zy8+">',
            '<img src="data:image%2Fsvg%2Bxml;base64,PHN2Zy8+">',
        )
        for markup in variants:
            with self.subTest(markup=markup), self.assertRaisesRegex(web_deck.SourceError, "SVG"):
                web_deck.compile_html(source().replace('</h1>', '</h1>' + markup), raster_only=True)

    def test_raster_only_rejects_inline_css_svg_resources(self):
        variants = (
            'background-image:url("diagram.svg?version=2#layer")',
            "background-image:url('diagram%2Esvg')",
            'mask-image: url(data:image/svg+xml,%3Csvg/%3E)',
            'background-image:URL("data:IMAGE/SVG+XML;base64,PHN2Zy8+")',
            r'background-image:url(diagram.\73 vg)',
            'background-image:image-set("cover.png" 1x, "diagram.svg" 2x)',
        )
        for css in variants:
            with self.subTest(css=css), self.assertRaisesRegex(web_deck.SourceError, "SVG in CSS"):
                web_deck.compile_html(source(head=f'<style>.hero {{{css}}}</style>'), raster_only=True)
        with self.assertRaisesRegex(web_deck.SourceError, "SVG in CSS"):
            web_deck.compile_html(source().replace('<h1 ', '<h1 style="background:url(&quot;diagram.svg&quot;)" ', 1),
                                  raster_only=True)

    def test_raster_only_keeps_html_raster_images_and_relative_stylesheets(self):
        authored = source(head='''<link rel="stylesheet" href="theme.css">
          <style>.layout{display:grid;grid-template-columns:1fr 1fr;gap:64px}
          .photo{background:url("media/scene.webp")} .label::after{content:"SVG is unsupported"}</style>''')
        authored = authored.replace('</h1>', '''</h1><picture>
          <source type="image/webp" srcset="media/scene.webp 1x, media/scene@2x.webp 2x">
          <img src="media/scene.png?version=1#crop" alt="SVG is not used here"></picture>
          <img src="media/detail.JPG"><img src="data:image/png;base64,aGVsbG8=">''')
        rendered = web_deck.compile_html(authored, raster_only=True)
        self.assertIn('<meta name="deck-media-policy" content="generated-raster">', rendered)
        self.assertEqual(rendered.count('name="deck-media-policy"'), 1)
        self.assertIn('href="theme.css"', rendered)
        self.assertIn('grid-template-columns:1fr 1fr', rendered)
        self.assertIn('src="media/detail.JPG"', rendered)
        # Asset decoding and generated-image provenance are deliberately not
        # inferred here from MIME labels, filenames or a compiler flag.
        self.assertIn('data:image/png;base64,aGVsbG8=', rendered)
        self.assertNotIn('name="deck-media-policy"', web_deck.compile_html(source()))

    def test_raster_policy_meta_cannot_override_compiler_policy(self):
        with self.assertRaisesRegex(web_deck.SourceError, "compiler-owned"):
            web_deck.compile_html(source(head='<meta name="DECK-MEDIA-POLICY" content="any">'), raster_only=True)

    def test_compiler_embeds_namespaced_layout_assets(self):
        rendered = web_deck.compile_html(source())
        self.assertIn('<style id="__deck_web_layouts">', rendered)
        self.assertIn((web_deck.ASSETS / 'web-layouts.css').read_text(encoding='utf-8'), rendered)

    def test_raster_only_cli_marks_output_and_preserves_previous_output_on_rejection(self):
        with tempfile.TemporaryDirectory(prefix="deck-raster-cli-") as directory:
            folder = Path(directory)
            original, output = folder / "source.html", folder / "deck.html"
            original.write_text(source(), encoding="utf-8")
            with patch("sys.stdout"):
                self.assertEqual(web_deck.main([str(original), '-o', str(output), '--raster-only']), 0)
            previous = output.read_bytes()
            self.assertIn(b'content="generated-raster"', previous)
            original.write_text(source(head='<style>body{background:url(diagram.svg)}</style>'), encoding="utf-8")
            with patch("sys.stderr"), self.assertRaises(SystemExit) as exc:
                web_deck.main([str(original), '-o', str(output), '--raster-only'])
            self.assertEqual(exc.exception.code, 1)
            self.assertEqual(output.read_bytes(), previous)

    def test_check_report_aliases_cannot_overwrite_source_or_output_before_compilation(self):
        for alias in ("source-path", "source-hardlink", "output-hardlink",
                      "source-symlink", "output-symlink", "output-resolves-to-report"):
            with self.subTest(alias=alias), tempfile.TemporaryDirectory(prefix="deck-report-alias-") as directory:
                folder = Path(directory)
                report = folder / "deck.check.json"
                original = report if alias == "source-path" else folder / "source.html"
                original.write_text(source(), encoding="utf-8")
                output = folder / "deck.html"
                if alias == "output-resolves-to-report":
                    report.write_text("previous compiled artifact", encoding="utf-8")
                    output.symlink_to(report)
                else:
                    output.write_text("previous compiled artifact", encoding="utf-8")
                if alias.endswith("hardlink"):
                    report.hardlink_to(original if alias.startswith("source") else output)
                elif alias.endswith("symlink"):
                    report.symlink_to(original if alias.startswith("source") else output)
                before = {path: path.read_bytes() for path in (original, output, report)}
                with patch.object(web_deck, "compile_file") as compile_file, patch("sys.stderr"):
                    with self.assertRaises(SystemExit) as exc:
                        web_deck.main([str(original), "-o", str(output), "--check"])
                self.assertEqual(exc.exception.code, 1)
                compile_file.assert_not_called()
                self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_preserves_authored_layout_and_canonicalizes_page_count(self):
        result = web_deck.compile_html(source())
        timeline = json.JSONDecoder().raw_decode(result.split("window.__deck_timeline=", 1)[1])[0]
        self.assertEqual(timeline, [{"slide": 1, "start": 0, "enter": .8, "hold": 3},
                                    {"slide": 2, "start": 3.8, "enter": .9, "hold": 3}])
        self.assertEqual(len(re.findall('<section class="slide"', result)), 2)
        self.assertIn('transform: rotate(-3deg)', result)
        self.assertIn('data-title="第一张"', result)

    def test_rejects_nonconsecutive_or_nested_slides(self):
        for text in (source().replace('data-slide="2"', 'data-slide="3"'),
                     source().replace('<body>', '<body><main>').replace('</body>', '</main></body>'),
                     source().replace('class="slide"', 'class="slide hero"', 1)):
            with self.subTest(text=text[-180:]), self.assertRaises(web_deck.SourceError):
                web_deck.compile_html(text)

    def test_rejects_missing_title_duplicate_attributes_and_broken_html(self):
        for text in (source().replace('data-title="第一张"', 'data-title=" "'),
                     source().replace('data-slide="1"', 'data-slide="1" data-slide="1"'),
                     source().replace('</h1>', ''), source().replace('<head>', ''),
                     source().replace('>Title</h1>', '/>'),
                     source(body="<p>No slides</p>")):
            with self.subTest(text=text[-180:]), self.assertRaises(web_deck.SourceError):
                web_deck.compile_html(text)

    def test_rejects_invalid_timing_and_late_reveals(self):
        for attr in ('data-hold="nan"', 'data-hold="inf"', 'data-hold="0"', 'data-hold="-1"'):
            with self.subTest(attr=attr), self.assertRaises(web_deck.SourceError):
                web_deck.compile_html(source(attrs=attr))
        for old, new in [('data-enter=".8"', 'data-enter="1e308" data-hold="1e308"'),
                         ('data-duration=".6"', 'data-duration="1"'),
                         ('data-at=".1"', 'data-at="-.1"'),
                         ('data-reveal="rise"', 'data-reveal="loop"')]:
            with self.subTest(new=new), self.assertRaises(web_deck.SourceError):
                web_deck.compile_html(source().replace(old, new))

    def test_rejects_base_urls_and_recompilation(self):
        with self.assertRaisesRegex(web_deck.SourceError, "base"):
            web_deck.compile_html(source(head='<base href="https://example.test/">'))
        with self.assertRaisesRegex(web_deck.SourceError, "already compiled"):
            web_deck.compile_html(web_deck.compile_html(source()))

    def test_file_guard_preserves_source_and_relative_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            original = folder / "source.html"
            original.write_text(source(head='<link rel="stylesheet" href="theme.css">'))
            with self.assertRaisesRegex(web_deck.SourceError, "different files"):
                web_deck.compile_file(original, original)
            with self.assertRaisesRegex(web_deck.SourceError, "same directory"):
                web_deck.compile_file(original, folder / "nested" / "deck.html")
            output = folder / "deck.html"
            web_deck.compile_file(original, output)
            self.assertIn('href="theme.css"', output.read_text())
            self.assertNotIn('name="deck-web-runtime"', original.read_text())


@unittest.skipUnless(Path(CHROME).exists() and ws_connect, "Chrome and websockets are required")
class TestWebBrowser(unittest.TestCase):
    def test_layout_assets_do_not_style_legacy_elements_outside_deck_page(self):
        authored = source(body='''<section class="slide" data-slide="1" data-title="Legacy composition">
          <div class="deck-header"><h1>Legacy heading</h1></div>
          <div class="deck-body"><div class="deck-block"><h2>Legacy subheading</h2>
          <p>Legacy body</p></div><figure class="deck-visual"><figcaption class="deck-caption">Legacy caption</figcaption></figure></div>
          <footer class="deck-footer"><p>Legacy footer</p></footer></section>''')
        result = browser_probe(web_deck.compile_html(authored), """
          const sheet=document.getElementById('__deck_web_layouts').sheet;
          const nodes=Array.from(document.querySelector('section.slide').querySelectorAll('*'));
          const properties=['display','fontSize','lineHeight','marginTop','marginBottom',
            'paddingBottom','minWidth','minHeight','gap','color','overflowWrap'];
          function snapshot(){return nodes.map(node=>{
            const style=getComputedStyle(node);return properties.map(key=>style[key]);
          });}
          sheet.disabled=true;const before=snapshot();sheet.disabled=false;
          return {before,after:snapshot()};
        """)
        self.assertEqual(result['before'], result['after'])

    def test_check_cli_writes_report_and_preserves_reviewable_html(self):
        for overlapping in (False, True):
            with self.subTest(overlapping=overlapping), tempfile.TemporaryDirectory(prefix="deck-check-cli-") as directory:
                folder = Path(directory)
                original, output = folder / "source.html", folder / "deck.html"
                top = 108 if overlapping else 210
                authored = source(
                    head='<style>p{margin:0;font:32px/1.4 Arial,sans-serif;color:#111}</style>',
                    body='<section class="slide" data-slide="1" data-title="Anonymous layout fixture">'
                         '<p style="position:absolute;left:100px;top:100px">Primary statement</p>'
                         f'<p style="position:absolute;left:100px;top:{top}px">Supporting statement</p>'
                         '</section>')
                original.write_text(authored, encoding="utf-8")
                process = subprocess.run([sys.executable, str(SCRIPTS / "web_deck.py"),
                                          str(original), "-o", str(output), "--check"],
                                         capture_output=True, text=True, timeout=60)
                self.assertEqual(process.returncode, 2 if overlapping else 0, process.stdout + process.stderr)
                self.assertEqual(original.read_text(encoding="utf-8"), authored)
                self.assertIn('name="deck-web-runtime"', output.read_text(encoding="utf-8"))
                self.assertIn("Supporting statement", output.read_text(encoding="utf-8"))
                report = json.loads(output.with_suffix(".check.json").read_text(encoding="utf-8"))
                self.assertEqual(report["summary"]["status"], "needs_review" if overlapping else "passed")
                self.assertEqual(report["summary"]["errors"], 0)
                self.assertEqual(report["summary"]["pages"], 1)
                self.assertEqual(report["file"], str(output.resolve()))
                if overlapping:
                    self.assertTrue(any(issue["code"] == "text-overlap" for issue in report["pages"][0]["issues"]))

    def test_seek_is_reversible_and_preserves_authored_transform(self):
        page = web_deck.compile_html(source(head='<script>window.__recording=true;</script>'))
        result = browser_probe(page, """
          var node=document.getElementById('hero');
          function snapshot(t){window.__deck.seek(t);var s=getComputedStyle(node);
            return [s.opacity,s.translate,s.transform,document.documentElement.dataset.deckMode];}
          var beginning=snapshot(0), middle=snapshot(.35), final=snapshot(.8);
          window.__deck.seek(4);var restored=snapshot(.35);
          return {beginning,middle,final,restored,active:window.__deck_ui.cur(),
            mask:getComputedStyle(document.getElementById('mask')).clipPath,
            width:document.querySelector('section').getBoundingClientRect().width};
        """)
        self.assertEqual(result["beginning"][0], "0")
        self.assertGreater(float(result["middle"][0]), 0)
        self.assertLess(float(result["middle"][0]), 1)
        self.assertEqual(result["middle"], result["restored"])
        self.assertEqual(result["final"][0], "1")
        self.assertEqual(result["final"][1], "none")
        self.assertEqual(result["final"][2], result["middle"][2])
        self.assertEqual(result["active"], 0)
        self.assertEqual(result["width"], 1600)

    def test_play_stops_resize_does_not_replay_and_editors_keep_keys(self):
        result = browser_probe(web_deck.compile_html(source()), """
          await new Promise(r=>setTimeout(r,1000));
          var node=document.getElementById('hero'), before=getComputedStyle(node).opacity;
          window.dispatchEvent(new Event('resize'));
          var after=getComputedStyle(node).opacity, playing=window.__deck_ui.isPlaying();
          var input=document.getElementById('editor');input.focus();
          input.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));
          var editingIndex=window.__deck_ui.cur();input.blur();
          document.body.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));
          var next=window.__deck_ui.cur();window.__deck_ui.go(0);
          return {before,after,playing,editingIndex,next,
            replay:getComputedStyle(node).opacity,
            buttons:Array.from(document.querySelectorAll('nav button')).map(b=>b.type)};
        """)
        self.assertEqual(result["before"], "1")
        self.assertEqual(result["after"], "1")
        self.assertFalse(result["playing"])
        self.assertEqual(result["editingIndex"], 0)
        self.assertEqual(result["next"], 1)
        self.assertEqual(result["replay"], "0")
        self.assertEqual(result["buttons"], [])

    def test_author_translate_and_clip_keep_geometry_through_settling(self):
        page = web_deck.compile_html(source(head='''<script>window.__recording=true;</script>
          <style>#hero{position:absolute;left:50%;top:200px;translate:-50% 16px}
          #mask{clip-path:inset(4px 8px 12px 16px)}</style>'''))
        result = browser_probe(page, """
          var node=document.getElementById('hero'), mask=document.getElementById('mask');
          function snapshot(t){window.__deck.seek(t);var r=node.getBoundingClientRect();
            return {x:r.x,y:r.y,translate:getComputedStyle(node).translate,
              clip:getComputedStyle(mask).clipPath,opacity:getComputedStyle(node).opacity};}
          return [.1,.35,.699,.7,.8].map(snapshot);
        """)
        final = result[-1]
        self.assertEqual(final["translate"], "-50% 16px")
        self.assertEqual(final["clip"], "inset(4px 8px 12px 16px)")
        for snapshot in result:
            self.assertEqual(snapshot["x"], final["x"])
            self.assertEqual(snapshot["y"], final["y"])
            self.assertEqual(snapshot["translate"], final["translate"])
            self.assertEqual(snapshot["clip"], final["clip"])
        self.assertEqual(result[0]["opacity"], "0")
        self.assertGreater(float(result[1]["opacity"]), 0)
        self.assertEqual(final["opacity"], "1")

    def test_present_canvas_uses_viewport_without_visible_controls(self):
        result = browser_probe(web_deck.compile_html(source()), """
          var frame=document.querySelector('.deck-web-frame[data-active]').getBoundingClientRect();
          document.body.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));
          var status=document.querySelector('[role=status]');
          return {frameTop:frame.top,frameBottom:frame.bottom,frameWidth:frame.width,
            viewport:innerHeight,viewportWidth:innerWidth,
            controls:document.querySelector('nav.__deck_web_controls') !== null,
            status:status.textContent,statusWidth:status.getBoundingClientRect().width,
            clipped:getComputedStyle(status).clipPath,
            hiddenPageInert:document.querySelector('.deck-web-frame').inert};
        """)
        self.assertEqual(result["frameTop"], 0)
        self.assertEqual(result["frameBottom"], result["viewport"])
        self.assertEqual(result["frameWidth"], result["viewportWidth"])
        self.assertFalse(result["controls"])
        self.assertEqual(result["status"], "2 / 2 · 第二张")
        self.assertEqual(result["statusWidth"], 1)
        self.assertEqual(result["clipped"], "inset(50%)")
        self.assertTrue(result["hiddenPageInert"])

    def test_reduced_motion_and_scroll_are_complete_without_animation(self):
        reduced = '<script>window.matchMedia=function(){return {matches:true,addEventListener:function(){}}};</script>'
        for query, head in [("?scroll", ""), ("", reduced)]:
            with self.subTest(query=query):
                result = browser_probe(web_deck.compile_html(source(head=head)), """
                  window.__deck_ui.replay();
                  return {opacity:getComputedStyle(document.getElementById('hero')).opacity,
                    playing:window.__deck_ui.isPlaying(),
                    visible:Array.from(document.querySelectorAll('.deck-web-frame')).filter(f=>getComputedStyle(f).display!=='none').length};
                """, query=query)
                self.assertEqual(result["opacity"], "1")
                self.assertFalse(result["playing"])
                self.assertEqual(result["visible"], 2 if query else 1)

    def test_print_settles_every_page_and_defines_fixed_page_box(self):
        result = browser_probe(web_deck.compile_html(source()), """
          window.__deck_ui.replay();window.dispatchEvent(new Event('beforeprint'));
          var css=document.getElementById('__deck_web_base').textContent;
          return {opacity:getComputedStyle(document.getElementById('hero')).opacity,
            clip:getComputedStyle(document.getElementById('mask')).clipPath,
            playing:window.__deck_ui.isPlaying(),
            pageBox:css.includes('size: 1600px 900px'),
            inert:Array.from(document.querySelectorAll('.deck-web-frame')).some(f=>f.inert)};
        """)
        self.assertEqual(result, {"opacity": "1", "clip": "none", "playing": False,
                                  "pageBox": True, "inert": False})

    def test_existing_capture_produces_identical_pixels_after_backward_seek(self):
        capture_spec = importlib.util.spec_from_file_location("_web_deck_capture_test", SCRIPTS / "animate.py")
        capture = importlib.util.module_from_spec(capture_spec)
        capture_spec.loader.exec_module(capture)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            html = folder / "deck.html"
            html.write_text(web_deck.compile_html(source()), encoding="utf-8")
            frames = asyncio.run(capture._capture_async(str(html), directory, [.35, .8, 4, .35], 1))
            digests = [hashlib.sha256(Path(frame).read_bytes()).hexdigest() for frame in frames]
            self.assertEqual(digests[0], digests[3])
            self.assertNotEqual(digests[0], digests[1])
            self.assertNotEqual(digests[1], digests[2])

    @unittest.skipUnless(shutil.which("pdfinfo"), "Poppler is required for page box validation")
    def test_existing_pdf_export_has_two_correctly_sized_pages(self):
        pdf_spec = importlib.util.spec_from_file_location("_web_deck_pdf_test", SCRIPTS / "pdf.py")
        pdf = importlib.util.module_from_spec(pdf_spec)
        pdf_spec.loader.exec_module(pdf)
        with tempfile.TemporaryDirectory() as directory:
            html = Path(directory) / "deck.html"
            html.write_text(web_deck.compile_html(source()), encoding="utf-8")
            result = pdf.export(str(html), str(Path(directory) / "deck.pdf"))
            self.assertEqual(result["expected_pages"], 2)
            self.assertEqual(result["pages"], 2)
            self.assertEqual(len(result["mediaboxes"]), 2)
            for box in result["mediaboxes"]:
                width, height = pdf._box_size(box)
                self.assertAlmostEqual(width, 1200, delta=1)
                self.assertAlmostEqual(height, 675, delta=1)


if __name__ == "__main__":
    unittest.main()
