"""跨版本检查：新版本不能靠改上一版交差。

这些用例故意用**极小的合成 deck**：形状是假的，但"抄"与"重做"在可测的维度上
是不同的（同一份 CSS / 同一族字 / 同一组渐变 / 同一批图片 / 同一条页序）。
失败信息里也断言不回显上一版的具体色号与字族 —— 把旧值打印出来，等于给模型
递回去接着抄。
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/deck-authoring/scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(f"_version_guard_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = load("version_guard")

OLD_HTML = """<!doctype html><html><head><link rel="stylesheet" href="assets/deck.css"></head><body>
<section class="slide"><div class="hero-split"><h1>开场</h1></div></section>
<section class="slide"><div class="stat-band"><span class="stat-num">42%</span></div></section>
<section class="slide"><div class="split-notes"><p class="note">注</p></div></section>
<section class="slide"><svg class="dgm"><path d="M10 10 L200 20 L200 120 Z"/></svg></section>
<section class="slide"><div class="quote-block"><blockquote>引用</blockquote></div></section>
<section class="slide"><img src="assets/images/hero.png"></section>
<section class="slide"><table><tr><td>a</td></tr></table></section>
<section class="slide"><div class="end-mark">完</div></section>
</body></html>"""

OLD_CSS = """
:root { --ink:#1c2a3a; --paper:#f2ede4; --accent:#c2410c; --rule:#2f6f6a; }
body { font-family: "Source Serif 4", serif; color: var(--ink); background: var(--paper); }
.hero-split { display:grid; grid-template-columns: 7fr 5fr; gap:40px;
  background: linear-gradient(180deg, #f2ede4 0%, #e7dfd0 100%); }
.lede { font-size: 30px; color: #c2410c; }
.stat-band { border-top: 6px solid #2f6f6a; }
.stat-num { font-size: 120px; }
.split-notes { background: repeating-linear-gradient(90deg, #1c2a3a 0 2px, transparent 2px 12px); }
.note { color: #2f6f6a; }
.quote-block { background: linear-gradient(135deg, #c2410c 0%, #7c2d12 100%); }
.end-mark { color: #f2ede4; background:#1c2a3a; }
"""

NEW_HTML = """<!doctype html><html><head><link rel="stylesheet" href="assets/deck.css"></head><body>
<section class="slide"><div class="stage"><h1>另一种开场</h1></div></section>
<section class="slide"><div class="full-bleed plate"><h2>整幅</h2></div></section>
<section class="slide"><div class="stat datum"><span class="datum-figure">7</span></div></section>
<section class="slide"><table class="matrix"><tr><td>x</td></tr></table></section>
<section class="slide"><img src="assets/images/field.jpg"></section>
<section class="slide"><div class="citation"><blockquote>另一句</blockquote></div></section>
<section class="slide"><svg><path d="M0 90 Q 300 20 600 90 T 900 30"/></svg></section>
<section class="slide"><div class="ed margin-column"><p>边注</p></div></section>
<section class="slide"><div class="closing-rule"><p>收束</p></div></section>
</body></html>"""

NEW_CSS = """
:root { --graphite:#22303f; --teal:#1f7a5c; --lime:#d7f26b; }
body { font-family: "Fraunces", "Noto Sans SC", sans-serif; background: #f4f1e8; color: #22303f; }
.stage { display:flex; align-items:flex-end; padding: 96px;
  background: radial-gradient(circle at 80% 20%, #d7f26b 0 18%, transparent 19%); }
.full-bleed { position:absolute; inset:0;
  background: linear-gradient(90deg, #22303f 0 38%, #1f7a5c 38% 100%); }
.datum-figure { font-size: 200px; color: #d64545; letter-spacing:-.04em; }
.matrix { border-collapse: collapse; border-top: 2px solid #1f7a5c; }
.margin-column { background: repeating-linear-gradient(0deg, #22303f 0 1px, transparent 1px 24px); }
.citation { padding: 120px 80px; background:#d7f26b; }
.closing-rule { border-bottom: 12px solid #1f7a5c; }
"""

DIFF = """# 设计记录

## 与上一版的差异

- 参考：另找的编辑设计，与上一版无亲缘关系
- 字体：换成本版字族
- 配色：重新选色
- 构图：按本轮问题重排
"""


def write_version(root: Path, name: str, html: str = OLD_HTML, css: str = OLD_CSS,
                  design: str | None = DIFF, image: bytes | None = b"hero",
                  image_name: str = "hero.png", plan: dict | None = None) -> Path:
    target = root / name
    (target / "assets" / "images").mkdir(parents=True)
    (target / "source.html").write_text(html, encoding="utf-8")
    (target / "assets" / "deck.css").write_text(css, encoding="utf-8")
    if design is not None:
        (target / "design.md").write_text(design, encoding="utf-8")
    if image is not None:
        (target / "assets" / "images" / image_name).write_bytes(image)
    if plan is not None:
        (target / "image-plan.json").write_text(json.dumps(plan), encoding="utf-8")
    return target


def run(*argv: str) -> tuple[int, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(io.StringIO()):
        code = guard.main([str(arg) for arg in argv])
    return code, buffer.getvalue()


class TestVersionGuard(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "deck-topic"
        self.root.mkdir()
        self.v1 = write_version(self.root, "v1-2026-10-01-纸面")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def redesign(self, name: str = "v2-2026-10-19-深色", **overrides) -> Path:
        values = {"html": NEW_HTML, "css": NEW_CSS, "image": b"other image",
                  "image_name": "field.jpg"}
        values.update(overrides)
        return write_version(self.root, name, **values)

    def test_a_copy_fails_and_does_not_echo_the_old_values(self) -> None:
        v2 = self.root / "v2-2026-10-19-深色"
        shutil.copytree(self.v1, v2)
        code, out = run(v2)
        self.assertEqual(code, 1, out)
        for dimension in ("项目 CSS", "组件类名", "字族", "彩色色板", "图片 / 素材"):
            self.assertIn(f"✗ {dimension}", out, out)
        self.assertNotIn("Source Serif 4", out, "报告回显了上一版的字族，等于递回去接着抄")
        self.assertNotIn("#c2410c", out, "报告回显了上一版的色值，等于递回去接着抄")

    def test_a_real_redesign_passes(self) -> None:
        code, out = run(self.redesign(), "--against", self.v1)
        self.assertEqual(code, 0, out)
        self.assertIn("没有发现跨版本搬用", out)

    def test_one_shared_font_needs_an_explicit_user_allowance(self) -> None:
        v2 = self.redesign(css=NEW_CSS.replace('"Fraunces", "Noto Sans SC", sans-serif',
                                               '"Source Serif 4", serif'))
        code, out = run(v2, "--against", self.v1)
        self.assertEqual(code, 1, out)
        self.assertIn("✗ 字族", out)
        self.assertNotIn("✗ 组件类名", out, "除字族外的维度不该被一起判失败")

        code, out = run(v2, "--against", self.v1, "--allow", "fonts",
                        "--reason", "用户说品牌字体必须保留")
        self.assertEqual(code, 0, out)
        self.assertIn("已授权沿用：用户说品牌字体必须保留", out)

    def test_allow_without_a_reason_is_rejected(self) -> None:
        v2 = self.root / "v2-2026-10-19-深色"
        shutil.copytree(self.v1, v2)
        code, _ = run(v2, "--allow", "fonts")
        self.assertEqual(code, 2)

    def test_reused_image_is_allowed_only_when_registered_as_provided(self) -> None:
        v2 = self.redesign(html=NEW_HTML.replace("field.jpg", "hero.png"),
                          image=b"hero", image_name="hero.png")
        code, out = run(v2, "--against", self.v1)
        self.assertEqual(code, 1, out)
        self.assertIn("✗ 图片 / 素材", out)

        v3 = self.redesign(name="v3-2026-10-19-深色",
                          html=NEW_HTML.replace("field.jpg", "hero.png"),
                          image=b"hero", image_name="hero.png", plan={
            "schemaVersion": 1, "images": [{
                "id": "hero", "file": "assets/images/hero.png", "source": "provided",
                "source_note": "用户提供的真实场地照片，本版仍按抬头裁切",
            }]})
        code, out = run(v3, "--against", self.v1)
        self.assertNotIn("✗ 图片 / 素材", out)
        self.assertIn("登记为 provided", out)

    def test_cross_version_asset_reference_fails(self) -> None:
        v2 = self.redesign(html=NEW_HTML.replace(
            'src="assets/images/field.jpg"',
            'src="../v1-2026-10-01-纸面/assets/images/hero.png"'))
        code, out = run(v2, "--against", self.v1)
        self.assertEqual(code, 1, out)
        self.assertIn("越界引用", out)

    def test_missing_version_diff_record_fails(self) -> None:
        v2 = self.redesign(design="# 设计记录\n\n只有一句话。\n")
        code, out = run(v2, "--against", self.v1)
        self.assertEqual(code, 1, out)
        self.assertIn("✗ 版本差异记录", out)

    def test_previous_versions_are_discovered_by_number(self) -> None:
        code, out = run(self.redesign())
        self.assertEqual(code, 0, out)
        self.assertIn("历史：v1-2026-10-01-纸面（1 个）", out)

    def test_later_versions_and_empty_placeholders_are_not_compared(self) -> None:
        v2 = self.redesign()
        self.redesign(name="v9-2026-11-01-后续")
        (self.root / "v10-2026-11-02-空位").mkdir()
        (self.root / "v10-2026-11-02-空位" / "README.md").write_text("空位", encoding="utf-8")
        code, out = run(v2)
        self.assertEqual(code, 0, out)
        self.assertNotIn("v9-", out, "检查了比当前更新的版本")
        self.assertNotIn("v10-", out, "把空占位目录当成了历史版本")

    def test_json_report_records_dimensions_and_status(self) -> None:
        v2 = self.root / "v2-2026-10-19-深色"
        shutil.copytree(self.v1, v2)
        report = v2 / "checks" / "version-guard.json"
        code, _ = run(v2, "--json", report)
        self.assertEqual(code, 1)
        payload = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "fail")
        keys = {finding["key"]: finding["level"] for finding in payload["findings"]}
        self.assertEqual(keys["fonts"], "fail")
        self.assertEqual(keys["record"], "ok")


if __name__ == "__main__":
    unittest.main()
