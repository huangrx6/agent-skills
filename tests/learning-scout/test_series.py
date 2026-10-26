"""learning-scout series builder: rendering, validation, build and quality gate.

Run from the repository root:
    python3 -m unittest discover -s tests/learning-scout -v
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parents[1] / "skills" / "learning-scout"
SCRIPTS = SKILL / "scripts"
# build_series 内部 `import render_md`，所以这两条路径仍要留在 sys.path 上。
sys.path.insert(0, str(SCRIPTS))


def _load(name: str, path: Path):
    """按路径加载脚本；scripts/ 不是包，静态 import 解析不到。"""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


render_md = _load("render_md_under_test", SCRIPTS / "render_md.py")
build_series = _load("build_series_under_test", SCRIPTS / "build_series.py")
check_notes = _load("check_notes_under_test", SCRIPTS / "check_notes.py")


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
            write_series(base)
            note = base / "notes" / "01-a.md"
            note.write_text(note.read_text() + "\n见第 2 篇。\n", encoding="utf-8")
            errors, _ = check_notes.check_note(note, "concept", strict=False)
            self.assertTrue(any("跨篇引用" in error for error in errors))

    def test_other_note_references_are_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_series(base)
            note = base / "notes" / "01-a.md"
            original = note.read_text()
            for phrase in ("见另一篇", "详见另一篇", "其他笔记"):
                note.write_text(original + f"\n{phrase}。\n", encoding="utf-8")
                errors, _ = check_notes.check_note(note, "concept", strict=False)
                self.assertTrue(any("跨篇引用" in error for error in errors), phrase)

    def test_personal_path_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_series(base)
            note = base / "notes" / "01-a.md"
            note.write_text(note.read_text() + "\n/Users/someone/project\n", encoding="utf-8")
            errors, _ = check_notes.check_note(note, "concept", strict=False)
            self.assertTrue(any("个人环境路径" in error for error in errors))


if __name__ == "__main__":
    unittest.main()


class HouseStyleCheckTests(unittest.TestCase):
    """成文风格里能机械查的部分：编号章节、参考资料节、开头禁语、核验落点。

    这些约定来自本机 53 篇已成稿笔记的实测（见 references/house-style.md），
    不是审美偏好；只有参考资料与核验落点会阻塞，其余先提示。
    """

    def note(self, tmp: str, body: str) -> Path:
        path = Path(tmp) / "01-style.md"
        path.write_text(body, encoding="utf-8")
        return path

    def style(self, body: str) -> tuple[list[str], list[str]]:
        with tempfile.TemporaryDirectory() as tmp:
            return check_notes.check_note(self.note(tmp, body), "concept", strict=False)

    def test_numbered_sections_and_refs_produce_no_style_warnings(self):
        body = ("# 标题\n\n一个具体场景。\n\n## 1. 问题\n\n正文。\n\n"
                "## 2. 参考资料\n\n- [文档](https://example.com)\n")
        errors, warnings = self.style(body)
        self.assertEqual([], errors)
        self.assertFalse([w for w in warnings if "参考资料" in w or "编号" in w], warnings)

    def test_missing_references_section_is_warning(self):
        _errors, warnings = self.style("# 标题\n\n场景。\n\n## 1. 问题\n\n正文。\n")
        self.assertTrue(any("参考资料" in w for w in warnings), warnings)

    def test_non_numbered_sections_are_warning(self):
        body = "# 标题\n\n场景。\n\n## 问题\n\n正文。\n\n## 参考资料\n\n- [文档](https://x.y)\n"
        _errors, warnings = self.style(body)
        self.assertTrue(any("编号" in w for w in warnings), warnings)

    def test_gapped_numbering_is_warning(self):
        body = ("# 标题\n\n场景。\n\n## 1. 甲\n\n正文。\n\n## 3. 乙\n\n正文。\n\n"
                "## 4. 参考资料\n\n- [文档](https://x.y)\n")
        _errors, warnings = self.style(body)
        self.assertTrue(any("不连续" in w for w in warnings), warnings)

    def test_opening_with_intro_cliche_is_warning(self):
        body = "# 标题\n\n本文将介绍上下文工程的基本概念。\n\n## 1. 问题\n\n正文。\n"
        _errors, warnings = self.style(body)
        self.assertTrue(any("本文介绍" in w for w in warnings), warnings)

    def test_refs_section_counts_as_verification_anchor(self):
        """53 篇里没有一篇写「核验」节：参考资料节本身就是核验落点。"""
        body = ("# 标题\n\n场景。\n\n## 1. 问题\n\n正文。\n\n"
                "## 2. 参考资料\n\n- [文档](https://example.com)\n")
        errors, _warnings = self.style(body)
        self.assertEqual([], errors)

    def test_no_anchor_at_all_is_error(self):
        errors, _warnings = self.style("# 标题\n\n场景。\n\n## 1. 问题\n\n正文。\n")
        self.assertTrue(any("核验落点" in e for e in errors), errors)


class BodySignalTests(unittest.TestCase):
    """边界与失败模式看正文有没有讲到，不要求专门开一节。

    真实文章常把边界放在段落里（「这个方案在 X 下不适用」），
    按标题查会把人逼出没人读的空节。
    """

    def style(self, body: str, kind: str = "concept") -> tuple[list[str], list[str]]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "01-body.md"
            path.write_text(body, encoding="utf-8")
            return check_notes.check_note(path, kind, strict=False)

    def test_boundary_in_paragraph_is_enough(self):
        body = ("# 标题\n\n场景。\n\n## 1. 机制\n\n这个方案在弱网下不适用，此时应先降级。\n\n"
                "## 2. 参考资料\n\n- [文档](https://example.com)\n")
        _errors, warnings = self.style(body)
        self.assertFalse([w for w in warnings if "没写边界" in w], warnings)

    def test_missing_boundary_everywhere_is_warning(self):
        body = ("# 标题\n\n场景。\n\n## 1. 机制\n\n照着做即可。\n\n"
                "## 2. 参考资料\n\n- [文档](https://example.com)\n")
        _errors, warnings = self.style(body)
        self.assertTrue(any("没写边界" in w for w in warnings), warnings)

    def test_failure_mode_in_paragraph_counts_for_mechanism(self):
        body = ("# 标题\n\n场景。\n\n## 1. 机制\n\n超时后先看症状：连接池耗尽，修法是加退避。\n"
                "这里不适合流式场景。\n\n## 2. 参考资料\n\n- [文档](https://example.com)\n")
        _errors, warnings = self.style(body, kind="mechanism")
        self.assertFalse([w for w in warnings if "失败情况" in w], warnings)

    def test_mechanism_without_failure_mode_is_warning(self):
        body = ("# 标题\n\n场景。\n\n## 1. 机制\n\n请求按顺序转发，边界是单机部署。\n\n"
                "## 2. 参考资料\n\n- [文档](https://example.com)\n")
        _errors, warnings = self.style(body, kind="mechanism")
        self.assertTrue(any("失败情况" in w for w in warnings), warnings)


class QuizWhyTests(unittest.TestCase):
    """自测的「选项级」理由：错选时告诉读者这个选项错在哪。

    只有整题的 explain 时，读者知道自己错了但不知道错在想岔在哪一步；
    逐选项理由来自评估设计里的干扰项分析，是主动回忆之外最便宜的一步。
    """

    def build(self, base: Path, quiz: list[dict]) -> str:
        (base / "notes").mkdir(parents=True, exist_ok=True)
        (base / "notes" / "01-a.md").write_text(
            "# 一\n\n## 1. 甲\n\n正文。\n\n## 2. 参考资料\n\n- [文档](https://example.com)\n",
            encoding="utf-8")
        plan = {
            "version": 2,
            "topic": "测验",
            "promise": "验证自测理由。",
            "notes": [
                {"id": "01", "title": "一", "goal": "目标", "kind": "concept",
                 "file": "notes/01-a.md", "quiz": quiz},
                {"id": "02", "title": "二", "goal": "目标二", "kind": "concept",
                 "file": "notes/02-b.md"},
            ],
            "sources": {"verified_at": "2026-10-23"},
        }
        (base / "notes" / "02-b.md").write_text(
            "# 二\n\n## 1. 乙\n\n正文。\n\n## 2. 参考资料\n\n- [文档](https://example.com)\n",
            encoding="utf-8")
        plan_path = base / "plan.json"
        plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        out = base / "dist"
        build_series.build(plan_path, str(out), check=False)
        # 产物名是 <id>-<标题 slug>.html，不沿用源 md 的文件名
        pages = sorted((out / "notes").glob("01-*.html"))
        return pages[0].read_text(encoding="utf-8")

    def test_why_is_rendered_for_each_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            html = self.build(Path(tmp), [{
                "q": "入队成功代表消息安全了吗？",
                "options": ["是", "还要看是否落盘"],
                "answer": 1,
                "why": ["入队只在内存里，重启就没了", ""],
                "explain": "入队只是进了内存队列。",
            }])
        self.assertIn("data-why=", html)
        self.assertIn("quiz-why", html)
        self.assertIn("入队只在内存里，重启就没了", html)

    def test_why_length_must_match_options(self):
        with tempfile.TemporaryDirectory() as tmp, \
                self.assertRaises(build_series.PlanError):
            self.build(Path(tmp), [{
                    "q": "?", "options": ["A", "B"], "answer": 0,
                    "why": ["只有一条理由"], "explain": "x",
                }])

    def test_why_must_be_string_list(self):
        with tempfile.TemporaryDirectory() as tmp, \
                self.assertRaises(build_series.PlanError):
            self.build(Path(tmp), [{
                    "q": "?", "options": ["A", "B"], "answer": 0,
                    "why": [1, 2], "explain": "x",
                }])

    def test_quiz_without_why_still_builds(self):
        with tempfile.TemporaryDirectory() as tmp:
            html = self.build(Path(tmp), [{
                "q": "?", "options": ["A", "B"], "answer": 0, "explain": "x",
            }])
        self.assertIn("quiz-option", html)
        self.assertNotIn("入队只在内存里", html)
