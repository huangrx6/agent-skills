"""节奏检查：可以成对同构，连续三页同构才是版面偷懒。"""
from __future__ import annotations

import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/deck-authoring/scripts/rhythm_check.py"

TEXT = '<section class="slide"><p>x</p></section>'
IMG = '<section class="slide"><img src="a.png"></section>'
STAT = '<section class="slide"><div class="stat">42%</div></section>'
Q = '<section class="slide"><blockquote>q</blockquote></section>'
SVG = '<section class="slide"><svg class="dgm"><path d="M0 0"/></svg></section>'
TABLE = '<section class="slide"><table><tr><td>x</td></tr></table></section>'


def load():
    spec = importlib.util.spec_from_file_location("_rhythm_check_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


rhythm = load()


def run(slides: list[str]) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "source.html"
        path.write_text("<html><body>" + "".join(slides) + "</body></html>", encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = rhythm.main([str(path)])
    return code, out.getvalue()


class TestRhythmCheck(unittest.TestCase):
    def test_a_pair_of_image_pages_is_allowed(self) -> None:
        code, out = run([TEXT, IMG, IMG, STAT, TABLE, Q, SVG, TEXT])
        self.assertEqual(code, 0, out)

    def test_a_photo_essay_is_not_failed(self) -> None:
        code, out = run([IMG] * 8)
        self.assertEqual(code, 0, out)
        self.assertIn("图像主导", out)
        self.assertIn("不设上限", out)

    def test_three_image_pages_in_a_row_is_a_note_not_a_failure(self) -> None:
        code, out = run([TEXT, IMG, IMG, IMG, STAT, TABLE, Q, SVG])
        self.assertEqual(code, 0, out)
        self.assertIn("构图", out)

    def test_three_text_pages_in_a_row_fails(self) -> None:
        code, out = run([TEXT, TEXT, TEXT, IMG, STAT, TABLE, Q, SVG])
        self.assertEqual(code, 1, out)
        self.assertIn("连续三页以上非图像主角", out)

    def test_one_text_lead_over_share_still_fails(self) -> None:
        code, out = run([TEXT] * 5 + [IMG, STAT, TABLE, Q, SVG])
        self.assertEqual(code, 1, out)
        self.assertIn("超过 45%", out)

    def test_no_slides_is_an_input_error(self) -> None:
        code, _ = run([])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
