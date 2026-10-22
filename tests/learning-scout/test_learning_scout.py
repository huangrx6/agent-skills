"""learning-scout: JSON contract, safe rendering, themes and CLI."""

from __future__ import annotations

import copy
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SKILL = HERE.parents[1] / "skills" / "learning-scout"
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location("learning_scout_under_test", SCRIPTS / "learning_scout.py")
if spec is None or spec.loader is None:
    raise RuntimeError("加载不了 learning_scout.py")
CLI = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = CLI
spec.loader.exec_module(CLI)

EXAMPLE = json.loads((SKILL / "examples" / "rag.plan.json").read_text(encoding="utf-8"))
NOTES = json.loads((SKILL / "examples" / "langchain-notes.plan.json").read_text(encoding="utf-8"))


def _plan() -> dict:
    return copy.deepcopy(EXAMPLE)


def _errors(plan: dict) -> list[str]:
    errors, _warnings = CLI.validate_plan(plan)
    return errors


def _render(plan: dict, layout: str | None = None, **theme_args) -> str:
    theme = CLI._theme_config(plan, **theme_args)
    return CLI.render_html(plan, theme, layout)


class TestValidation(unittest.TestCase):
    def test_example_is_valid(self):
        errors, warnings = CLI.validate_plan(_plan())
        self.assertEqual([], errors)
        self.assertEqual([], warnings)

    def test_stage_can_have_only_a_practice(self):
        plan = _plan()
        plan["stages"] = [{
            "id": "only-practice",
            "title": "先做一次最小实验",
            "practice": {"title": "跑通一条链路"},
        }]
        plan["interludes"] = []
        self.assertEqual([], _errors(plan))

    def test_stage_without_any_content_is_rejected(self):
        plan = _plan()
        plan["stages"] = [{"id": "empty", "title": "只有一个标题"}]
        self.assertTrue(any("至少要有资源、练习或检查点" in item for item in _errors(plan)))

    def test_duplicate_resource_url_is_rejected(self):
        plan = _plan()
        plan["stages"][0]["resources"].append(copy.deepcopy(plan["stages"][0]["resources"][0]))
        self.assertTrue(any("重复" in item for item in _errors(plan)))

    def test_stage_title_lines_must_be_non_empty_strings(self):
        plan = _plan()
        plan["stages"][0]["title_lines"] = ["", "second"]
        self.assertTrue(any("title_lines" in item for item in _errors(plan)))

    def test_duplicate_stage_id_is_rejected(self):
        plan = _plan()
        plan["stages"][1]["id"] = plan["stages"][0]["id"]
        self.assertTrue(any("id 重复" in item for item in _errors(plan)))

    def test_bad_layout_is_rejected(self):
        plan = _plan()
        plan["layout"] = "kanban"
        self.assertTrue(any("layout" in item for item in _errors(plan)))

    def test_bad_theme_and_date_are_rejected(self):
        plan = _plan()
        plan["theme"]["name"] = "neon"
        plan["sources"]["verified_at"] = "2026/10/22"
        errors = _errors(plan)
        self.assertTrue(any("theme.name" in item for item in errors))
        self.assertTrue(any("verified_at" in item for item in errors))

    def test_javascript_url_is_rejected(self):
        plan = _plan()
        plan["stages"][0]["resources"][0]["url"] = "javascript:alert(1)"
        self.assertTrue(any("http(s)" in item for item in _errors(plan)))

    def test_title_lines_must_be_non_empty_strings(self):
        plan = _plan()
        plan["title_lines"] = ["", "second"]
        self.assertTrue(any("title_lines" in item for item in _errors(plan)))

    def test_missing_verified_date_is_rejected(self):
        plan = _plan()
        del plan["sources"]["verified_at"]
        self.assertTrue(any("verified_at" in item for item in _errors(plan)))

    def test_interlude_after_unknown_stage_is_rejected(self):
        plan = _plan()
        plan["interludes"][0]["after"] = "s99"
        self.assertTrue(any("after" in item for item in _errors(plan)))

    def test_no_practice_is_a_warning_not_an_error(self):
        plan = _plan()
        for stage in plan["stages"]:
            stage.pop("practice", None)
        errors, warnings = CLI.validate_plan(plan)
        self.assertEqual([], errors)
        self.assertTrue(any("动手任务" in item for item in warnings))


class TestRendering(unittest.TestCase):
    def test_renders_self_contained_page(self):
        html = _render(_plan())
        self.assertIn("<!doctype html>", html.lower())
        self.assertIn("RAG 实战", html)
        self.assertIn("从开卷考试", html)
        self.assertIn("data-theme=\"deep-field\"", html)
        self.assertIn("--accent: #c8ff4d", html)
        self.assertIn("<style>", html)
        self.assertIn("<script>", html)
        self.assertIn("0 / 16", html)
        self.assertIn("id=\"shelf\"", html)

    def test_title_lines_render_as_separate_spans(self):
        html = _render(_plan())
        self.assertIn("<em><span>从开卷考试</span><span>到可评估系统</span></em>", html)

    def test_stage_title_lines_render_as_spans(self):
        plan = _plan()
        plan["stages"][0]["title_lines"] = ["先拆开这台机器", "再决定怎么用"]
        html = _render(plan)
        self.assertIn("<h2><span>先拆开这台机器</span><span>再决定怎么用</span></h2>", html)

    def test_flexible_stage_hides_absent_sections(self):
        plan = _plan()
        plan["stages"] = [{
            "id": "minimal",
            "title": "只做一次练习",
            "practice": {"title": "写下你的问题"},
        }]
        plan["interludes"] = []
        plan["not_now"] = []
        plan["rabbit_holes"] = []
        plan["start"] = {}
        html = _render(plan)
        self.assertIn("只做一次练习", html)
        self.assertIn("FIELD MISSION", html)
        self.assertNotIn("THE LIBRARY", html)
        self.assertNotIn("CHECKPOINT", html)
        self.assertNotIn("NOT NOW", html)

    def test_text_and_attributes_are_escaped(self):
        plan = _plan()
        plan["title"] = "<script>alert(1)</script>"
        plan.pop("title_lines", None)
        plan["stages"][0]["title"] = "<b>danger</b>"
        plan["stages"][0]["resources"][0]["title"] = "<img src=x onerror=alert(1)>"
        plan["stages"][0]["resources"][0]["url"] = "https://example.com/?q=\"x\"&b=2"
        html = _render(plan)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertNotIn("<b>danger</b>", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertIn("&quot;x&quot;", html)

    def test_layouts_render_distinct_heroes(self):
        journey = _render(_plan())
        atlas = _render(_plan(), layout="atlas")
        studio = _render(_plan(), layout="studio")
        self.assertIn('data-layout="journey"', journey)
        self.assertIn('class="hero-board', journey)
        self.assertIn('data-layout="atlas"', atlas)
        self.assertIn('class="hero hero--atlas"', atlas)
        self.assertIn('class="atlas-panel', atlas)
        self.assertNotIn('class="hero-board', atlas)
        self.assertIn('data-layout="studio"', studio)
        self.assertIn('class="hero hero--studio"', studio)
        self.assertIn('class="studio-poster', studio)
        self.assertIn('class="studio-ticker', studio)
        self.assertNotIn('class="hero-board', studio)

    def test_theme_can_be_overridden(self):
        html = _render(_plan(), override_name="paper-trail", override_accent="#123456", override_motif="grid")
        self.assertIn('data-theme="paper-trail"', html)
        self.assertIn("--accent: #123456", html)
        self.assertIn('data-motif="grid"', html)

    def test_switching_theme_uses_its_own_accent_and_motif(self):
        html = _render(_plan(), override_name="paper-trail")
        self.assertIn('data-theme="paper-trail"', html)
        self.assertIn("--accent: #d64b2a", html)
        self.assertIn('data-motif="grid"', html)
        self.assertIn("由命令行主题覆盖", html)

    def test_auto_theme_uses_topic_hints(self):
        plan = _plan()
        plan["topic"] = "Kubernetes 集群"
        plan["theme"] = {"name": "auto"}
        self.assertEqual("blueprint", CLI._pick_theme(plan))
        plan["topic"] = "技术写作"
        self.assertEqual("paper-trail", CLI._pick_theme(plan))

    def test_output_path_uses_topic_and_verified_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = CLI._output_path(_plan(), None, tmp)
            self.assertEqual("rag-实战-2026-10-22", path.parent.name)
            self.assertEqual("index.html", path.name)

    def test_cli_render_writes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "nested" / "plan.html"
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = CLI.main(["render", "--input", str(SKILL / "examples" / "rag.plan.json"),
                                 "--out", str(out)])
            self.assertEqual(0, code)
            self.assertTrue(out.exists())
            self.assertIn("RAG 实战", out.read_text(encoding="utf-8"))
            self.assertIn("HTML:", buf.getvalue())

    def test_cli_layout_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "atlas.html"
            with redirect_stdout(io.StringIO()):
                code = CLI.main(["render", "--input", str(SKILL / "examples" / "rag.plan.json"),
                                 "--layout", "atlas", "--out", str(out)])
            self.assertEqual(0, code)
            self.assertIn('data-layout="atlas"', out.read_text(encoding="utf-8"))

    def test_cli_validate_reports_topic(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = CLI.main(["validate", "--input", str(SKILL / "examples" / "rag.plan.json")])
        self.assertEqual(0, code)
        self.assertIn("RAG 实战", buf.getvalue())
        self.assertIn("5 个阶段", buf.getvalue())

    def test_stdout_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict("os.environ", {"LEARNING_SCOUT_OUTPUT_DIR": tmp}):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = CLI.main(["render", "--input", str(SKILL / "examples" / "rag.plan.json"), "--stdout"])
            self.assertEqual(0, code)
            self.assertIn("<!doctype html>", buf.getvalue())
            self.assertEqual([], list(Path(tmp).iterdir()))


class TestPagedNotes(unittest.TestCase):
    def test_langchain_notes_example_is_valid(self):
        errors, warnings = CLI.validate_plan(copy.deepcopy(NOTES))
        self.assertEqual([], errors)
        self.assertEqual([], warnings)

    def test_paged_requires_sections(self):
        plan = _plan()
        plan["layout"] = "paged"
        errors = _errors(plan)
        self.assertTrue(any("sections" in item for item in errors))

    def test_paged_page_loop_has_notes_quiz_and_review(self):
        html = _render(copy.deepcopy(NOTES))
        self.assertIn('data-layout="paged"', html)
        self.assertIn("scroll-snap-type: y mandatory", html)
        self.assertEqual(15, html.count('class="page page--note"'))
        self.assertEqual(7, html.count('class="page page--work"'))
        self.assertEqual(1, html.count('class="page page--review"'))
        self.assertEqual(1, html.count('class="page page--orientation"'))
        self.assertIn('data-complete-stage="d1"', html)
        self.assertIn('class="quiz-item"', html)
        self.assertIn('class="review-card"', html)
        self.assertIn('class="source-chip"', html)
        self.assertIn("你的起点", html)
        self.assertIn("create_agent", html)
        self.assertIn("33 / 34", html)
        self.assertIn("先知道这些词", html)
        self.assertIn("Agent loop", html)
        self.assertIn("Python 类型注解", html)
        self.assertIn("学完自测", html)
        self.assertIn("工具描述只是给开发者看的注释", html)
        self.assertNotIn(">wrong<", html)
        self.assertNotIn(">right<", html)
        self.assertIn("structured_response", html)
        self.assertIn("ProviderStrategy", html)
        self.assertIn("示例代码", html)
        self.assertIn("伪代码", html)

    def test_paged_escapes_quiz_and_section_titles(self):
        plan = copy.deepcopy(NOTES)
        plan["stages"][0]["sections"][0]["title"] = "<b>bad</b>"
        plan["stages"][0]["quiz"][0]["options"][0] = "<img src=x>"
        html = _render(plan)
        self.assertNotIn("<b>bad</b>", html)
        self.assertNotIn("<img src=x>", html)
        self.assertIn("&lt;b&gt;bad&lt;/b&gt;", html)

    def test_quiz_answer_must_be_in_range(self):
        plan = copy.deepcopy(NOTES)
        plan["stages"][0]["quiz"][0]["answer"] = 99
        self.assertTrue(any("answer 越界" in item for item in _errors(plan)))

    def test_review_stage_must_exist(self):
        plan = copy.deepcopy(NOTES)
        plan["review"][0]["stage"] = "missing"
        self.assertTrue(any("review[0].stage" in item for item in _errors(plan)))

    def test_glossary_requires_unique_terms_and_definitions(self):
        plan = copy.deepcopy(NOTES)
        plan["glossary"].append({"term": plan["glossary"][0]["term"], "definition": "重复"})
        plan["glossary"].append({"term": "空定义", "definition": ""})
        errors = _errors(plan)
        self.assertTrue(any("term 重复" in item for item in errors))
        self.assertTrue(any("definition 不能为空" in item for item in errors))

    def test_misconceptions_and_teach_back_are_validated(self):
        plan = copy.deepcopy(NOTES)
        plan["stages"][0]["misconceptions"] = [{"wrong": "只有错误"}]
        plan["stages"][0]["teach_back"] = 123
        errors = _errors(plan)
        self.assertTrue(any("right 不能为空" in item for item in errors))
        self.assertTrue(any("teach_back 必须是字符串" in item for item in errors))

    def test_code_status_must_be_known(self):
        plan = copy.deepcopy(NOTES)
        plan["stages"][0]["sections"][0]["code"]["status"] = "trust-me"
        self.assertTrue(any("code.status" in item for item in _errors(plan)))

    def test_learner_must_be_an_object(self):
        plan = copy.deepcopy(NOTES)
        plan["learner"] = "beginner"
        self.assertTrue(any("learner 必须是对象" in item for item in _errors(plan)))


if __name__ == "__main__":
    unittest.main()
