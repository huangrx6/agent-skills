"""learning-scout series builder: rendering, validation, build and quality gate.

Run from the repository root:
    python3 -m unittest discover -s tests/learning-scout -v
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parents[1] / "skills" / "learning-scout"
sys.path.insert(0, str(SKILL / "scripts"))

import build_series  # noqa: E402
import check_notes  # noqa: E402
import render_md  # noqa: E402


def write_series(base: Path, *, with_image: bool = False) -> Path:
    notes = base / "notes"
    notes.mkdir(parents=True, exist_ok=True)
    (notes / "01-a.md").write_text(
        "# 第一篇\n\n开场故障。\n\n## 一节\n\n- 一级\n  - 二级\n\n## 核验\n\n示例。\n",
        encoding="utf-8",
    )
    body = "# 第二篇\n\n## 一节\n\n正文。\n\n## 核验\n\n示例。\n"
    if with_image:
        (notes / "images").mkdir(exist_ok=True)
        (notes / "images" / "dot.bin").write_bytes(b"\x00\x01")
        body = "![图](images/dot.bin)\n\n" + body
    (notes / "02-b.md").write_text(body, encoding="utf-8")
    plan = {
        "version": 2,
        "topic": "测试系列",
        "promise": "验证构建链路。",
        "notes": [
            {"id": "01", "title": "第一篇", "goal": "目标一", "kind": "concept", "file": "notes/01-a.md"},
            {"id": "02", "title": "第二篇", "goal": "目标二", "kind": "practice", "file": "notes/02-b.md"},
        ],
        "sources": {"verified_at": "2026-10-23"},
    }
    plan_path = base / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    return plan_path


class RenderTests(unittest.TestCase):
    def test_alert_preprocessing(self):
        text = "> [!note] 标题\n> 正文\n"
        out = render_md.preprocess_alerts(text)
        self.assertIn("::: callout-note", out)
        self.assertIn("**标题**", out)
        self.assertIn("正文", out)

    def test_nested_lists_when_engine_available(self):
        if render_md.ENGINE != "markdown-it":
            self.skipTest("optional renderer not installed")
        html, _ = render_md.render("- 一级\n  - 二级\n")
        self.assertGreaterEqual(html.count("<ul>"), 2)

    def test_table_alignment(self):
        if render_md.ENGINE != "markdown-it":
            self.skipTest("optional renderer not installed")
        html, _ = render_md.render("| a | b |\n|:--|--:|\n| 1 | 2 |\n")
        self.assertIn('style="text-align:left"', html)
        self.assertIn('style="text-align:right"', html)

    def test_heading_ids_and_toc(self):
        html, toc = render_md.render("# T\n\n## 一节\n\n## 二节\n")
        self.assertNotIn("<h1", html)  # page header renders the title
        self.assertEqual([entry[1] for entry in toc], ["一节", "二节"])
        self.assertIn('id="一节"', html)


class VideoTests(unittest.TestCase):
    def test_youtube(self):
        self.assertEqual(
            build_series.embed_url("https://www.youtube.com/watch?v=abc123"),
            "https://www.youtube-nocookie.com/embed/abc123",
        )
        self.assertEqual(
            build_series.embed_url("https://youtu.be/abc123"),
            "https://www.youtube-nocookie.com/embed/abc123",
        )

    def test_bilibili_and_vimeo(self):
        self.assertIn("bvid=BV1xx411c7mD", build_series.embed_url("https://www.bilibili.com/video/BV1xx411c7mD"))
        self.assertEqual(build_series.embed_url("https://vimeo.com/123456"), "https://player.vimeo.com/video/123456")

    def test_unknown_platform(self):
        self.assertIsNone(build_series.embed_url("https://example.com/video/1"))


class ValidationTests(unittest.TestCase):
    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = write_series(Path(tmp))
            plan = json.loads(plan_path.read_text())
            plan["notes"][0]["file"] = "notes/missing.md"
            errors, _ = build_series.validate_plan(plan, plan_path.parent)
            self.assertTrue(any("不存在" in error for error in errors))

    def test_bad_quiz_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = write_series(Path(tmp))
            plan = json.loads(plan_path.read_text())
            plan["notes"][0]["quiz"] = [{"q": "x", "options": ["a"], "answer": 3}]
            errors, _ = build_series.validate_plan(plan, plan_path.parent)
            self.assertTrue(any("quiz" in error for error in errors))

    def test_version_must_be_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = write_series(Path(tmp))
            plan = json.loads(plan_path.read_text())
            plan["version"] = 1
            errors, _ = build_series.validate_plan(plan, plan_path.parent)
            self.assertTrue(any("version" in error for error in errors))


class BuildTests(unittest.TestCase):
    def test_build_outputs_and_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            plan_path = write_series(base)
            out = base / "dist"
            build_series.build(plan_path, str(out), check=False)
            index = (out / "index.html").read_text(encoding="utf-8")
            self.assertIn("测试系列", index)
            self.assertEqual(len(list((out / "notes").glob("*.html"))), 2)
            self.assertEqual(len(list((out / "notes").glob("*.md"))), 2)
            self.assertTrue((out / "plan.json").exists())
            self.assertTrue((out / "print.html").exists())
            print_html = (out / "print.html").read_text(encoding="utf-8")
            self.assertIn("第一篇", print_html)
            self.assertIn("第二篇", print_html)
            for href in re.findall(r'href="([^"#]+)"', index):
                if href.startswith(("http", "mailto")):
                    continue
                self.assertTrue((out / href).exists(), href)

    def test_image_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            plan_path = write_series(base, with_image=True)
            out = base / "dist"
            build_series.build(plan_path, str(out), check=False)
            self.assertTrue((out / "notes" / "images" / "dot.bin").exists())

    def test_refuses_existing_dir_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            plan_path = write_series(base)
            out = base / "dist"
            out.mkdir()
            (out / "keep.txt").write_text("x")
            with self.assertRaises(build_series.PlanError):
                build_series.build(plan_path, str(out), check=False)
            build_series.build(plan_path, str(out), force=True, check=False)


class CheckTests(unittest.TestCase):
    def test_short_note_is_warning_not_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            plan_path = write_series(base)
            # 47 行，远低于 concept 参考下限；只应警告，不应阻止构建
            out = build_series.build(plan_path, str(base / "dist"))
            self.assertTrue((out / "index.html").exists())

    def test_build_rejects_note_without_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            plan_path = write_series(base)
            (base / "notes" / "01-a.md").write_text("# 第一篇\n\n没有核验节。\n", encoding="utf-8")
            with self.assertRaises(build_series.PlanError):
                build_series.build(plan_path, str(base / "dist"))


class CheckerTests(unittest.TestCase):
    def test_cross_reference_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            plan_path = write_series(base)
            note = base / "notes" / "01-a.md"
            note.write_text(note.read_text() + "\n见第 2 篇。\n", encoding="utf-8")
            errors, _ = check_notes.check_note(note, "concept", strict=False)
            self.assertTrue(any("跨篇引用" in error for error in errors))

    def test_other_note_references_are_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            plan_path = write_series(base)
            note = base / "notes" / "01-a.md"
            original = note.read_text()
            for phrase in ("见另一篇", "详见另一篇", "其他笔记"):
                note.write_text(original + f"\n{phrase}。\n", encoding="utf-8")
                errors, _ = check_notes.check_note(note, "concept", strict=False)
                self.assertTrue(any("跨篇引用" in error for error in errors), phrase)

    def test_personal_path_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            plan_path = write_series(base)
            note = base / "notes" / "01-a.md"
            note.write_text(note.read_text() + "\n/Users/someone/project\n", encoding="utf-8")
            errors, _ = check_notes.check_note(note, "concept", strict=False)
            self.assertTrue(any("个人环境路径" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
