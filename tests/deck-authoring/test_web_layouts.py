"""Real browser checks for the reusable normal-flow regions, not a style score."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image
from test_chart_regressions import browser_probe, CHROME, ws_connect

ASSETS = Path(__file__).resolve().parents[2] / "skills/deck-authoring/assets"


def page(*, layout="image-right", title="A clear starting point", body=None, project_css=""):
    if body is None:
        body = ('<div class="deck-copy"><p class="deck-block" id="copy">One idea with enough room to read.</p></div>'
                '<figure class="deck-media">'
                '<img id="art" width="1600" height="1200" alt="Pending neutral test fixture">'
                '<figcaption class="deck-caption">Supporting caption</figcaption></figure>')
    return ('<!doctype html><html><head><meta charset="utf-8"><style>body{margin:0}' + project_css
            + '</style><style id="layout-test-styles">'
            + ASSETS.joinpath("web-layouts.css").read_text(encoding="utf-8")
            + '</style><script>window.__deck_charts_ready=Promise.resolve();</script></head><body>'
            f'<div class="deck-page" data-layout="{layout}"><header class="deck-header">'
            f'<h1 id="title">{title}</h1></header><main class="deck-body">{body}</main>'
            '<footer class="deck-footer"><span>Neutral layout fixture</span><span>01</span></footer>'
            '</div></body></html>')


GEOMETRY = """
function box(selector) {
  const r=document.querySelector(selector).getBoundingClientRect();
  return {x:r.x,y:r.y,width:r.width,height:r.height,bottom:r.bottom,right:r.right};
}
function regions() {
  return {header:box('.deck-header'),body:box('.deck-body'),footer:box('.deck-footer'),
    copy:box('.deck-copy'),caption:box('.deck-caption'),slot:box('.deck-media > img'),image:box('#art')};
}
"""


@unittest.skipUnless(Path(CHROME).exists() and ws_connect, "Chrome and websockets are required")
class TestWebLayouts(unittest.TestCase):
    def test_injected_layout_does_not_style_legacy_class_names_outside_page(self):
        legacy = ('<div id="legacy"><header class="deck-header"><h1>Previous design</h1></header>'
                  '<div class="deck-body"><div class="deck-copy"><p class="deck-block">Existing copy</p></div>'
                  '<figure class="deck-media"><img alt="Legacy"><figcaption class="deck-caption">Caption</figcaption>'
                  '</figure></div><footer class="deck-footer">Existing footer</footer></div>')
        result = browser_probe(page().replace('</body>', legacy + '</body>'), """
          const properties=['display','fontSize','minWidth','minHeight','margin','padding','gap','width','height'];
          function legacyStyles() {return Array.from(document.querySelectorAll('#legacy *')).map(el=>{
            const style=getComputedStyle(el);return properties.map(property=>style[property]);});}
          const before=legacyStyles();
          document.querySelector('#layout-test-styles').disabled=true;
          return {before,after:legacyStyles()};
        """)
        self.assertEqual(result['before'], result['after'])

    def test_project_tokens_survive_later_layout_injection(self):
        result = browser_probe(page(project_css=':root{--deck-body-size:36px}.deck-page{--deck-title-size:60px}'), """
          return {body:getComputedStyle(document.querySelector('#copy')).fontSize,
            title:getComputedStyle(document.querySelector('#title')).fontSize};
        """)
        self.assertEqual(result, {"body": "36px", "title": "60px"})

    def test_long_title_reflows_body_without_moving_footer_or_shrinking_type(self):
        result = browser_probe(page(), GEOMETRY + """
          const before=regions();
          document.querySelector('#title').innerHTML='A clear starting point<br>With a second line';
          await new Promise(requestAnimationFrame);
          const after=regions();
          return {before,after,titleSize:getComputedStyle(document.querySelector('#title')).fontSize,
            bodySize:getComputedStyle(document.querySelector('#copy')).fontSize,
            copyPosition:getComputedStyle(document.querySelector('.deck-copy')).position,
            footerPosition:getComputedStyle(document.querySelector('.deck-footer')).position};
        """)
        before, after = result["before"], result["after"]
        growth = after["header"]["height"] - before["header"]["height"]
        self.assertGreater(growth, 0)
        self.assertAlmostEqual(after["body"]["y"] - before["body"]["y"], growth)
        self.assertAlmostEqual(before["body"]["height"] - after["body"]["height"], growth)
        self.assertEqual(before["footer"], after["footer"])
        self.assertLessEqual(after["copy"]["bottom"], after["body"]["bottom"] - 32)
        self.assertAlmostEqual(after["footer"]["y"] - after["body"]["bottom"], 48)
        # Presentation-scale baseline: 64 / 26, not the old 40 / 24 document scale.
        self.assertEqual(result["titleSize"], "64px")
        self.assertEqual(result["bodySize"], "26px")
        self.assertEqual(result["copyPosition"], "static")
        self.assertEqual(result["footerPosition"], "static")

    def test_image_decode_preserves_reserved_geometry_in_both_directions(self):
        with tempfile.TemporaryDirectory(prefix="deck-layout-raster-") as directory:
            image = Path(directory) / "neutral-fixture.png"
            # Mechanical load fixture only; never shipped or represented as artwork.
            Image.new("RGB", (1600, 1200), "#e8e4da").save(image)
            for layout in ("image-right", "image-left"):
                with self.subTest(layout=layout):
                    result = browser_probe(page(layout=layout), GEOMETRY + f"""
                      const before=regions(), art=document.querySelector('#art');
                      art.src={json.dumps(image.as_uri())};
                      await art.decode();
                      await new Promise(requestAnimationFrame);
                      return {{before,after:regions(),width:art.naturalWidth,
                        svgCount:document.querySelectorAll('svg').length,
                        fit:getComputedStyle(art).objectFit}};
                    """)
                    self.assertEqual(result["before"], result["after"])
                    self.assertEqual(result["width"], 1600)
                    self.assertEqual(result["svgCount"], 0)
                    self.assertEqual(result["fit"], "contain")
                    geometry = result["after"]
                    if layout == "image-right":
                        self.assertLess(geometry["copy"]["right"], geometry["slot"]["x"])
                    else:
                        self.assertLess(geometry["slot"]["right"], geometry["copy"]["x"])

    def test_overcapacity_stays_detectable_instead_of_shrinking_or_clipping(self):
        result = browser_probe(page(layout="statement", body='<div class="deck-copy"><p class="deck-block" id="copy">Short claim.</p></div>'), """
          const copy=document.querySelector('#copy'), body=document.querySelector('.deck-body');
          const before=getComputedStyle(copy).fontSize;
          copy.innerHTML=Array(30).fill('An independent idea belongs on another page.').join('<br>');
          await new Promise(requestAnimationFrame);
          return {before,after:getComputedStyle(copy).fontSize,
            exceeds:body.scrollHeight>body.clientHeight,
            overflow:getComputedStyle(body).overflow,
            footerY:document.querySelector('.deck-footer').getBoundingClientRect().y,
            pageHeight:document.querySelector('.deck-page').getBoundingClientRect().height};
        """)
        self.assertTrue(result["exceeds"], "The checker must be able to reject an overfull page")
        self.assertEqual(result["before"], result["after"])
        self.assertEqual(result["overflow"], "visible")
        self.assertLess(result["footerY"], 900)
        self.assertEqual(result["pageHeight"], 900)

    def test_reading_width_and_auxiliary_roles_remain_separate(self):
        result = browser_probe(page(project_css='.deck-page{--deck-caption-size:20px}'), """
          return {body: getComputedStyle(document.querySelector('#copy')).fontSize,
            caption: getComputedStyle(document.querySelector('.deck-caption')).fontSize,
            footer: getComputedStyle(document.querySelector('.deck-footer')).fontSize,
            readingLimit: getComputedStyle(document.querySelector('.deck-copy')).maxWidth};
        """)
        self.assertEqual(result, {'body': '26px', 'caption': '20px', 'footer': '16px', 'readingLimit': '820px'})


if __name__ == "__main__":
    unittest.main()
