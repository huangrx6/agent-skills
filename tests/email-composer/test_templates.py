"""模板库：变量、入库门槛、版本、归档与删除。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parents[1] / "skills" / "email-composer"
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

from email_composer import templates  # noqa: E402
from email_composer.spec import load_spec  # noqa: E402

EXAMPLE = SKILL / "examples" / "approval-release.yaml"
VARIABLES = {
    "Orbit": "project",
    "2026-11-20 20:00": "release_time",
    "2026-11-18 18:00": "confirm_deadline",
    "2026-11-19 12:00": "notify_deadline",
    "20:00": "freeze_time",
    "20:30": "gray_time",
    "22:00": "full_time",
}
VALUES = {
    "project": "Nova",
    "release_time": "2026-12-01 21:00",
    "confirm_deadline": "2026-11-28 18:00",
    "notify_deadline": "2026-11-29 12:00",
    "freeze_time": "21:00",
    "gray_time": "21:30",
    "full_time": "23:00",
}


def save(root: Path, **overrides):
    params = dict(
        spec_path=str(EXAMPLE),
        root=root,
        tid="approval-release",
        name="上线申请",
        scene="release",
        description="版本上线审批",
        required=VARIABLES,
        optional={},
        descriptions={"project": "项目名", "release_time": "发布窗口"},
        note="从规格生成",
        today="2026-11-18",
    )
    params.update(overrides)
    return templates.save(**params)


def write_spec(tmp: Path, body: str) -> str:
    path = tmp / "spec.yaml"
    path.write_text(body, encoding="utf-8")
    return str(path)


class TestSaveAndApply(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "email-templates"
        self.result = save(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_creates_version_files(self):
        version = self.root / "approval-release" / "v1"
        for name in ("template.yaml", "vars.json", "style.json", "sample.html", "README.md"):
            self.assertTrue((version / name).is_file(), name)
        self.assertEqual("v1", self.result["version"])
        self.assertEqual("business", json.loads((version / "style.json").read_text())["preset"])

    def test_recipient_is_not_stored(self):
        text = (self.root / "approval-release" / "v1" / "template.yaml").read_text()
        self.assertNotIn("wang@example.com", text)
        self.assertIn("{{project}}", text)

    def test_vars_json_shape(self):
        data = json.loads((self.root / "approval-release" / "v1" / "vars.json").read_text())
        self.assertEqual(1, data["version"])
        self.assertTrue(data["vars"]["project"]["required"])
        self.assertEqual("Orbit", data["vars"]["project"]["example"])

    def test_list_and_show(self):
        rows = templates.list_templates(self.root)
        self.assertEqual(["approval-release"], [row["id"] for row in rows])
        detail = templates.show(self.root, "approval-release")
        self.assertIn("project", detail["vars"])
        self.assertIn("vars.json", detail["files"])

    def test_apply_renders_files_and_report(self):
        outdir = Path(self.tmp.name) / "out"
        result = templates.apply(
            self.root, "approval-release", None, [f"{k}={v}" for k, v in VALUES.items()], str(outdir)
        )
        self.assertTrue(result["ok"], result.get("report"))
        self.assertEqual(3, len(result["files"]))
        html = Path(result["files"]["html"]).read_text()
        self.assertIn("Nova", html)
        self.assertNotIn("Orbit", html)
        self.assertEqual(640, result["report"]["stats"]["width"])

    def test_apply_with_vars_file(self):
        vars_path = Path(self.tmp.name) / "vars.json"
        vars_path.write_text(json.dumps({"vars": VALUES}, ensure_ascii=False), encoding="utf-8")
        outdir = Path(self.tmp.name) / "out"
        result = templates.apply(self.root, "approval-release", str(vars_path), None, str(outdir))
        self.assertTrue(result["ok"])

    def test_apply_missing_vars(self):
        with self.assertRaises(templates.MissingVars) as caught:
            templates.apply(self.root, "approval-release", None, ["project=Nova"], "out")
        self.assertIn("release_time", caught.exception.names)

    def test_apply_unknown_var(self):
        values = dict(VALUES, extra="x")
        with self.assertRaises(templates.TemplateError):
            templates.apply(self.root, "approval-release", None, [f"{k}={v}" for k, v in values.items()], "out")

    def test_apply_blocked_does_not_write_files(self):
        # 正常入库后手工改坏模板：新增一个 facts 里没有的数字，套用时必须被拦住。
        template = self.root / "approval-release" / "v1" / "template.yaml"
        text = template.read_text(encoding="utf-8")
        template.write_text(
            text.replace("回滚演练已经完成。", "回滚演练已经完成。预算 999 元。"), encoding="utf-8"
        )
        outdir = Path(self.tmp.name) / "blocked"
        result = templates.apply(
            self.root, "approval-release", None,
            [f"{k}={v}" for k, v in VALUES.items()], str(outdir)
        )
        self.assertFalse(result["ok"])
        self.assertIn(
            "number_provenance", {item["code"] for item in result["report"]["blocking"]}
        )
        self.assertFalse(outdir.exists() and any(outdir.iterdir()))


class TestGates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.root = self.dir / "email-templates"

    def tearDown(self):
        self.tmp.cleanup()

    def test_date_gate(self):
        spec = write_spec(
            self.dir,
            "type: daily\nsubject: 培训\nsummary: 培训在 2026-11-20 举行。\nfacts: [2026-11-20]\n",
        )
        with self.assertRaises(templates.TemplateError) as caught:
            save(self.root, spec_path=spec, required={})
        self.assertIn("日期", str(caught.exception))

    def test_sensitive_gate(self):
        spec = write_spec(
            self.dir,
            "type: daily\nsubject: 联系\nsummary: 请联系 wang@example.com 确认。\nfacts: []\n",
        )
        with self.assertRaises(templates.TemplateError) as caught:
            save(self.root, spec_path=spec, required={})
        self.assertIn("邮箱", str(caught.exception))

    def test_literal_not_found(self):
        with self.assertRaises(templates.TemplateError) as caught:
            save(self.root, required={"不存在的值": "x"})
        self.assertIn("没有出现", str(caught.exception))

    def test_blocking_sample_is_rejected(self):
        spec = write_spec(
            self.dir,
            "type: daily\nsubject: 预算\nsummary: 预算 999 元，请确认。\nfacts: []\n",
        )
        with self.assertRaises(templates.TemplateError) as caught:
            save(self.root, spec_path=spec, required={})
        self.assertIn("样例校验未通过", str(caught.exception))

    def test_same_id_cannot_be_saved_twice(self):
        save(self.root)
        with self.assertRaises(templates.TemplateError):
            save(self.root)


class TestVersioning(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "email-templates"
        save(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_update_creates_next_version_and_keeps_v1(self):
        result = templates.update(
            str(EXAMPLE),
            self.root,
            "approval-release",
            required=VARIABLES,
            note="补充发布步骤",
            today="2026-11-19",
        )
        self.assertEqual("v2", result["version"])
        self.assertTrue((self.root / "approval-release" / "v1").is_dir())
        self.assertTrue((self.root / "approval-release" / "v2").is_dir())
        index = templates.load_index(self.root)
        entry = index["templates"]["approval-release"]
        self.assertEqual("v2", entry["current"])
        self.assertEqual(["v1", "v2"], entry["versions"])
        self.assertEqual(2, len(entry["history"]))

    def test_update_keeps_previous_descriptions(self):
        templates.update(str(EXAMPLE), self.root, "approval-release", required=VARIABLES)
        data = json.loads((self.root / "approval-release" / "v2" / "vars.json").read_text())
        self.assertEqual("项目名", data["vars"]["project"]["description"])

    def test_archive_hide_and_restore(self):
        templates.archive(self.root, "approval-release")
        self.assertEqual([], templates.list_templates(self.root))
        self.assertEqual(1, len(templates.list_templates(self.root, include_archived=True)))
        templates.restore(self.root, "approval-release")
        self.assertEqual(1, len(templates.list_templates(self.root)))

    def test_remove(self):
        templates.remove(self.root, "approval-release")
        self.assertFalse((self.root / "approval-release").exists())
        self.assertEqual({}, templates.load_index(self.root)["templates"])


class TestVariables(unittest.TestCase):
    def test_typed_rows_are_expanded(self):
        data = {"rows": ["{{rows}}"], "name": "{{name}}"}
        defs = {"rows": {"required": True}, "name": {"required": True}}
        result = templates.apply_vars(
            data, {"rows": [["a", "b"], ["c", "d"]], "name": "x"}, defs
        )
        self.assertEqual([["a", "b"], ["c", "d"]], result["rows"])

    def test_optional_variable_uses_default(self):
        result = templates.apply_vars(
            {"a": "{{x}}"}, {}, {"x": {"required": False, "default": "d"}}
        )
        self.assertEqual("d", result["a"])

    def test_required_variable_cannot_be_empty(self):
        with self.assertRaises(templates.MissingVars):
            templates.apply_vars({"a": "{{x}}"}, {"x": ""}, {"x": {"required": True}})

    def test_list_cannot_be_embedded_in_a_string(self):
        with self.assertRaises(templates.TemplateError):
            templates.apply_vars(
                {"a": "前缀 {{x}}"}, {"x": ["a"]}, {"x": {"required": True}}
            )

    def test_parse_assignments_accepts_braces(self):
        self.assertEqual({"a": "x"}, templates.parse_assignments(["a={{x}}"], "--var"))

    def test_candidates_include_datetime_and_greeting(self):
        rows = templates.candidates(load_spec(str(EXAMPLE)))
        kinds = {row["kind"] for row in rows}
        self.assertIn("datetime", kinds)
        self.assertIn("greeting", kinds)
        self.assertIn("person", kinds)


HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><title>排班通知｜{{name}}</title></head>
<body><table role="presentation" width="600"><tr><td>
<h1>排班通知</h1><p>负责人：{{name}}</p>
<img src="https://example.com/a.png" alt="排班表" width="600">
</td></tr></table></body></html>
"""


class TestHtmlTemplates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.root = self.dir / "templates"
        self.source = self.dir / "support-plan.html"
        self.source.write_text(HTML_TEMPLATE, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, **kwargs):
        return templates.add_html(self.root, str(self.source), "support-plan", **kwargs)

    def test_add_creates_sidecar_and_lists(self):
        result = self.add()
        self.assertEqual("html/support-plan", result["id"])
        self.assertTrue((self.root / "html" / "support-plan.html").is_file())
        sidecar = self.root / "html" / "support-plan.vars.json"
        self.assertTrue(sidecar.is_file())
        data = json.loads(sidecar.read_text())
        self.assertIn("name", data["vars"])
        rows = templates.list_templates(self.root)
        self.assertEqual(["html/support-plan"], [row["id"] for row in rows])
        self.assertEqual("html", rows[0]["kind"])

    def test_show_and_apply(self):
        self.add()
        detail = templates.show(self.root, "html/support-plan")
        self.assertIn("name", detail["vars"])
        outdir = self.dir / "out"
        result = templates.apply(
            self.root, "html/support-plan", None, ["name=客服"], str(outdir)
        )
        self.assertTrue(result["ok"], result.get("report"))
        self.assertEqual("排班通知｜客服", result["subject"])
        text = Path(result["files"]["text"]).read_text()
        self.assertIn("负责人：客服", text)
        self.assertEqual({"html", "text"}, set(result["files"]))

    def test_values_are_html_escaped(self):
        self.add()
        outdir = self.dir / "out"
        result = templates.apply(
            self.root, "html/support-plan", None, ["name=<b>客服</b>"], str(outdir)
        )
        self.assertTrue(result["ok"])
        html = Path(result["files"]["html"]).read_text()
        self.assertIn("&lt;b&gt;客服&lt;/b&gt;", html)
        self.assertNotIn("<b>客服</b>", html)

    def test_missing_and_unknown_variables(self):
        self.add()
        with self.assertRaises(templates.MissingVars):
            templates.apply(self.root, "html/support-plan", None, [], "out")
        with self.assertRaises(templates.TemplateError):
            templates.apply(self.root, "html/support-plan", None, ["other=x"], "out")

    def test_markdown_is_not_supported(self):
        self.add()
        with self.assertRaises(templates.TemplateError):
            templates.apply(
                self.root, "html/support-plan", None, ["name=客服"], "out", ("html", "md")
            )

    def test_width_block_prevents_files(self):
        wide = self.dir / "wide.html"
        wide.write_text(
            HTML_TEMPLATE.replace('width="600"', 'width="700"'), encoding="utf-8"
        )
        templates.add_html(self.root, str(wide), "wide")
        outdir = self.dir / "blocked"
        result = templates.apply(self.root, "html/wide", None, ["name=客服"], str(outdir))
        self.assertFalse(result["ok"])
        self.assertIn("html_width", {item["code"] for item in result["report"]["blocking"]})
        self.assertFalse(outdir.exists() and any(outdir.iterdir()))

    def test_add_refuses_overwrite_without_force(self):
        self.add()
        with self.assertRaises(templates.TemplateError):
            self.add()
        self.add(force=True)

    def test_placeholders_are_reported(self):
        self.source.write_text(HTML_TEMPLATE + "<p>【项目名】【待填：附件名】</p>", encoding="utf-8")
        result = self.add()
        self.assertIn("【项目名】", result["placeholders"])
        self.assertIn("【待填：附件名】", result["placeholders"])

    def test_archive_is_rejected_and_remove_deletes(self):
        self.add()
        with self.assertRaises(templates.TemplateError):
            templates.archive(self.root, "html/support-plan")
        templates.remove(self.root, "html/support-plan")
        self.assertFalse((self.root / "html" / "support-plan.html").exists())
        self.assertFalse((self.root / "html" / "support-plan.vars.json").exists())
        self.assertEqual([], templates.list_templates(self.root))


if __name__ == "__main__":
    unittest.main()
