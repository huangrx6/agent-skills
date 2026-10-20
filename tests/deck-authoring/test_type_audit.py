"""字族审计：一版 deck 除机器标识外只应有一个文本字族。

合成 deck 只保留与判定相关的形状：选择器、字族声明、变量与简写。
真正的判断发生在真实字体与真实页面上，这里测的是"第二族会不会被放过"。
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/deck-authoring/scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(f"_type_audit_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


audit = load("type_audit")

HTML = """<!doctype html><html><head><link rel="stylesheet" href="assets/deck.css"></head><body>
<section class="slide"><h1 class="title">标题</h1><p class="lead">正文</p>
<pre class="code-block">npm run build</pre><figcaption>图注</figcaption></section>
</body></html>"""

ONE_FAMILY = """
:root { --font-body: "Source Serif 4"; }
body { font-family: var(--font-body), serif; }
h1, h2, .title { font-family: "Source Serif 4", serif; }
figcaption { font-family: "Source Serif 4"; }
pre, code, .code-block { font-family: "JetBrains Mono", monospace; }
"""

TWO_FAMILIES = """
body { font-family: "Source Serif 4", serif; }
h1, h2, .title { font-family: "Fraunces", serif; }
pre, code { font-family: "JetBrains Mono", monospace; }
"""


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = audit.main([str(arg) for arg in argv])
    return code, out.getvalue(), err.getvalue()


class TestTypeAudit(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "v2-2026-10-19-深色"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, css: str, html: str = HTML) -> Path:
        (self.root / "assets").mkdir(parents=True, exist_ok=True)
        (self.root / "source.html").write_text(html, encoding="utf-8")
        (self.root / "assets" / "deck.css").write_text(css, encoding="utf-8")
        return self.root

    def test_one_text_family_passes_with_mono_left_to_code(self) -> None:
        code, out, _ = run(self.write(ONE_FAMILY))
        self.assertEqual(code, 0, out)
        self.assertIn("全文只有一个文本字族", out)
        self.assertIn("非文本用途字族", out)

    def test_icon_font_is_not_a_second_text_family(self) -> None:
        css = ONE_FAMILY + '\n.icon, .icon::before { font-family: "Font Awesome 6 Free"; }\n'
        code, out, _ = run(self.write(css))
        self.assertEqual(code, 0, out)
        self.assertIn("非文本用途字族", out)

    def test_a_second_text_family_fails(self) -> None:
        code, out, _ = run(self.write(TWO_FAMILIES))
        self.assertEqual(code, 1, out)
        self.assertIn("文本字族 2 个", out)
        self.assertIn("Fraunces", out)
        self.assertIn("Source Serif 4", out)

    def test_mono_used_for_numbers_counts_as_text(self) -> None:
        css = TWO_FAMILIES.replace(
            'h1, h2, .title { font-family: "Fraunces", serif; }',
            'h1, h2, .title { font-family: "Source Serif 4"; }\n'
            '.stat-number { font-family: "JetBrains Mono", monospace; }')
        code, out, _ = run(self.write(css))
        self.assertEqual(code, 1, out)
        self.assertIn("JetBrains Mono", out)

    def test_font_shorthand_and_variables_are_resolved(self) -> None:
        css = """
:root { --font-display: "Fraunces"; }
h1 { font: 600 64px/1.1 var(--font-display), serif; }
body { font-family: "Source Serif 4", serif; }
"""
        code, out, _ = run(self.write(css))
        self.assertEqual(code, 1, out)
        self.assertIn("“Fraunces”", out)
        self.assertNotIn("Fraunces\")", out)

    def test_unused_font_face_is_reported_without_failing(self) -> None:
        css = ONE_FAMILY + '\n@font-face { font-family: "Unused Extra"; src: url(x.woff2); }\n'
        code, out, _ = run(self.write(css))
        self.assertEqual(code, 0, out)
        self.assertIn("声明但未使用的字族", out)
        self.assertIn("Unused Extra", out)

    def test_second_family_needs_an_explicit_allowance(self) -> None:
        target = self.write(TWO_FAMILIES)
        code, _, _ = run(target, "--allow", "Fraunces")
        self.assertEqual(code, 2, "无理由的 --allow 应被拒")

        code, out, _ = run(target, "--allow", "Fraunces", "--reason", "用户指定标题展示体")
        self.assertEqual(code, 0, out)
        self.assertIn("已授权沿用", out)

    def test_json_report_records_families_and_status(self) -> None:
        target = self.write(TWO_FAMILIES)
        report = target / "checks" / "type-audit.json"
        code, _, _ = run(target, "--json", report)
        self.assertEqual(code, 1)
        payload = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "fail")
        names = {entry["name"] for entry in payload["families"]}
        self.assertIn("Fraunces", names)
        self.assertIn("Source Serif 4", names)


if __name__ == "__main__":
    unittest.main()
