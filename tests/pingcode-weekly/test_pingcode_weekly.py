"""PingCode-only 周报：窗口、采集、数据合同、模板与 CLI 回归。"""

from __future__ import annotations

import argparse
import importlib.util
import io
import os
import re
import sys
import tempfile
import tomllib
import unittest
from datetime import datetime, timezone
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SKILL = HERE.parents[1] / "skills" / "pingcode-weekly"
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


COLLECT = _load("delivery_collect_under_test", SCRIPTS / "collect.py")
WEEKLY = _load("delivery_weekly_under_test", SCRIPTS / "weekly.py")
READ = _load("delivery_pingcode_read_under_test", SCRIPTS / "pingcode_read.py")
OUTPUT = _load("weekly_output_under_test", SCRIPTS / "output_paths.py")
CLI = _load("weekly_cli_under_test", SCRIPTS / "pingcode_weekly.py")

NOW = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)
SINCE = datetime(2026, 10, 19, tzinfo=timezone.utc)
UNTIL = datetime(2026, 10, 25, 23, 59, 59, tzinfo=timezone.utc)


def _epoch(value: datetime) -> int:
    return int(value.timestamp())


def _item(number: int, title: str, *, kind: str = "requirement",
          state: str = "处理中", state_type: str = "in_progress",
          assignee: str | None = "张三", updated: datetime | None = None,
          created: datetime | None = None,
          completed: datetime | None = None, sprint: str = "s1",
          severity: str | None = None, description: str = "") -> dict:
    type_id = "t-story" if kind == "requirement" else "t-bug"
    type_name = "用户故事" if kind == "requirement" else "缺陷"
    return {
        "id": f"w{number}",
        "identifier": number,
        "whole_identifier": f"DOC-{number}",
        "title": title,
        "type": {"id": type_id, "name": type_name,
                 "group": "requirement" if kind == "requirement" else "bug"},
        "state": {"name": state, "type": state_type},
        "assignee": ({"id": f"u-{assignee}", "display_name": assignee}
                     if assignee else None),
        "priority": {"name": "普通"},
        "properties": {"severity": severity} if severity else {},
        "description": description,
        "created_at": _epoch(created or SINCE),
        "updated_at": _epoch(updated or NOW),
        "completed_at": _epoch(completed) if completed else None,
        "sprint": {"id": sprint, "name": sprint},
        "parent": {"whole_identifier": "DOC-1"},
        "project": {"identifier": "DOC"},
        "html_url": f"https://example.test/DOC-{number}",
        "tags": [],
    }


class FakeApi:
    def __init__(self, items: list[dict], *, history_rows: dict[str, list[dict]] | None = None):
        self.items = items
        self.history_rows = history_rows or {}

    def paginate(self, path: str, page_size: int = 100, max_items: int = 500, **params):
        values = self._values(path, params)
        return values[:max_items]

    def get(self, path: str, **params):
        return type("Result", (), {"data": {}})()

    def _values(self, path: str, params: dict) -> list[dict]:
        if path.endswith("/projects"):
            return [{"id": "p1", "identifier": "DOC", "name": "文档平台"}]
        if path.endswith("/workitem_types"):
            return [{"id": "t-story", "name": "用户故事", "group": "requirement"},
                    {"id": "t-bug", "name": "缺陷", "group": "bug"}]
        if path.endswith("/workitem_states"):
            return [{"name": "处理中", "type": "in_progress"},
                    {"name": "已完成", "type": "completed"},
                    {"name": "打开", "type": "pending"}]
        if path.endswith("/sprints"):
            return [
                {"id": "s1", "name": "W43", "status": "in_progress",
                 "start": {"date": _epoch(SINCE)}, "due": {"date": _epoch(UNTIL)}},
                {"id": "s2", "name": "W44", "status": "pending",
                 "start": {"date": _epoch(datetime(2026, 10, 26, tzinfo=timezone.utc))},
                 "due": {"date": _epoch(datetime(2026, 11, 1, tzinfo=timezone.utc))}},
            ]
        if "/transition_histories" in path:
            item_id = path.split("/")[-2]
            return self.history_rows.get(item_id, [])
        if path.endswith("/workitems"):
            rows = list(self.items)
            project_id = params.get("project_id")
            if project_id and project_id != "p1":
                return []
            type_id = params.get("type_id")
            if type_id:
                rows = [row for row in rows if row["type"]["id"] == type_id]
            sprint_id = params.get("sprint_id")
            if sprint_id:
                rows = [row for row in rows if row["sprint"]["id"] == sprint_id]
            updated = params.get("updated_between")
            if updated:
                start, end = (int(part) for part in updated.split(","))
                rows = [row for row in rows if start <= int(row["updated_at"]) <= end]
            return rows
        raise AssertionError(f"unexpected path {path}")


def _payload(items=None, history_rows=None, **kwargs) -> dict:
    api = FakeApi(items or [], history_rows=history_rows)
    return COLLECT.collect_project(
        api, "DOC", since=SINCE, until=UNTIL,
        requirement_types=["用户故事"], defect_types=["缺陷"],
        summary_field="周报摘要", limit=100, **kwargs,
    )


class TestWindow(unittest.TestCase):
    def test_iso_week_is_monday_to_sunday(self):
        start, end = COLLECT.parse_window(week="2026-W43", now=NOW)
        self.assertEqual(start.date().isoformat(), "2026-10-19")
        self.assertEqual(end.date().isoformat(), "2026-10-25")
        self.assertEqual(end.hour, 23)
        self.assertEqual(end.minute, 59)

    def test_month_window(self):
        start, end = COLLECT.parse_window(month="2026-02", now=NOW)
        self.assertEqual(start.date().isoformat(), "2026-02-01")
        self.assertEqual(end.date().isoformat(), "2026-02-28")
        self.assertEqual(end.hour, 23)

    def test_month_and_week_cannot_combine(self):
        with self.assertRaises(COLLECT.CollectError):
            COLLECT.parse_window(week="2026-W43", month="2026-10", now=NOW)

    def test_reverse_window_rejected(self):
        with self.assertRaises(COLLECT.CollectError):
            COLLECT.parse_window(since="2026-10-25", until="2026-10-19", now=NOW)


class TestCollect(unittest.TestCase):
    def test_requirements_bugs_and_planned_items(self):
        items = [
            _item(1, "完成多格式解析", state="已完成", state_type="completed",
                  completed=datetime(2026, 10, 21, tzinfo=timezone.utc),
                  description="新增 HTML 与 Markdown。\n\n补充说明"),
            _item(2, "补格式兼容", state="处理中", state_type="in_progress",
                  assignee=None),
            _item(3, "下周做 MCP", state="打开", state_type="pending", sprint="s2"),
            _item(4, "缺陷：表格丢字段", kind="bug", state="打开", state_type="pending",
                  assignee=None),
            _item(5, "缺陷：旧版 Office", kind="bug", state="已完成",
                  state_type="completed", completed=datetime(2026, 10, 20, tzinfo=timezone.utc),
                  severity="P2"),
            _item(6, "缺陷：下周修复", kind="bug", state="打开", state_type="pending",
                  sprint="s2", severity="P0"),
        ]
        project = _payload(items)
        self.assertEqual(project["identifier"], "DOC")
        self.assertEqual(len(project["requirements"]), 3)
        self.assertEqual(len(project["bugs"]), 3)
        self.assertEqual(project["quality"]["completed_requirements"], 1)
        self.assertEqual(project["quality"]["completed_bugs"], 1)
        self.assertEqual(project["quality"]["open_bugs"], 2)
        self.assertEqual(project["quality"]["planned_requirements"], 1)
        self.assertEqual(project["quality"]["planned_bugs"], 1)
        self.assertIn("DOC-2", project["quality"]["missing_assignee"])
        self.assertIn("DOC-4", project["quality"]["missing_severity"])
        self.assertFalse(project["quality"]["missing_next_week"])

    def test_missing_assignee_covers_completed_in_window(self):
        item = _item(11, "完成但无负责人", state="已完成", state_type="completed",
                     assignee=None, completed=datetime(2026, 10, 21, tzinfo=timezone.utc))
        project = _payload([item])
        self.assertIn("DOC-11", project["quality"]["missing_assignee"])

    def test_missing_assignee_ignores_items_outside_report_scope(self):
        item = _item(12, "很久以前完成", state="已完成", state_type="completed",
                     assignee=None, created=datetime(2026, 9, 1, tzinfo=timezone.utc),
                     updated=datetime(2026, 9, 2, tzinfo=timezone.utc),
                     completed=datetime(2026, 9, 3, tzinfo=timezone.utc))
        project = _payload([item])
        self.assertNotIn("DOC-12", project["quality"]["missing_assignee"])

    def test_completion_time_can_come_from_history(self):
        item = _item(7, "历史完成", state="已完成", state_type="completed")
        history = {"w7": [{"to_state": {"name": "已完成", "type": "completed"},
                           "created_at": _epoch(datetime(2026, 10, 22, tzinfo=timezone.utc))}]}
        project = _payload([item], history_rows=history)
        req = next(row for row in project["requirements"] if row["id"] == "DOC-7")
        self.assertTrue(req["completed_in_window"])
        self.assertIsNotNone(req["completed_at"])

    def test_empty_project_is_explicit(self):
        project = _payload([])
        self.assertTrue(project["quality"]["empty"])
        self.assertEqual(project["quality"]["requirements_total"], 0)
        ok, lines = COLLECT.build_check({"projects": [project]})
        self.assertFalse(ok)
        self.assertTrue(any("没有 PingCode" in line for line in lines))

    def test_closed_can_be_configured_as_done(self):
        item = _item(9, "关闭即完成", state="关闭", state_type="closed",
                     completed=datetime(2026, 10, 21, tzinfo=timezone.utc))
        default = _payload([item])
        self.assertEqual(default["quality"]["completed_requirements"], 0)
        configured = _payload([item], done_state_types=["completed", "closed"])
        self.assertEqual(configured["quality"]["completed_requirements"], 1)
        self.assertTrue(configured["requirements"][0]["open"] is False)

    def test_filter_by_assignee_recomputes_quality(self):
        items = [
            _item(1, "张三的完成项", state="已完成", state_type="completed",
                  completed=datetime(2026, 10, 21, tzinfo=timezone.utc)),
            _item(2, "李四的进行中项", assignee="李四"),
        ]
        payload = {"version": 1, "projects": [_payload(items)], "quality": {}}
        filtered = COLLECT.filter_payload(payload, ["张三"])
        project = filtered["projects"][0]
        self.assertEqual(1, project["quality"]["requirements_total"])
        self.assertEqual(1, project["quality"]["completed_requirements"])
        self.assertEqual("张三", project["requirements"][0]["assignee"])
        self.assertEqual(["张三", "李四"], COLLECT.assignee_names(payload))

    def test_filter_records_excluded_unassigned_items(self):
        items = [
            _item(1, "张三的完成项", state="已完成", state_type="completed",
                  completed=datetime(2026, 10, 21, tzinfo=timezone.utc)),
            _item(3, "没人负责的完成项", state="已完成", state_type="completed",
                  assignee=None, completed=datetime(2026, 10, 22, tzinfo=timezone.utc)),
            _item(4, "李四的进行中项", assignee="李四"),
        ]
        payload = {"version": 1, "projects": [_payload(items)], "quality": {}}
        filtered = COLLECT.filter_payload(payload, ["张三"])
        project = filtered["projects"][0]
        scope = project["scope"]
        self.assertEqual(1, scope["matched"])
        self.assertIn("DOC-3", scope["excluded_unassigned"])
        self.assertEqual(1, scope["excluded_other"])
        self.assertTrue(any("按负责人过滤" in warning
                            for warning in project["quality"]["warnings"]))
        text = WEEKLY.render_weekly(filtered)
        self.assertIn("按负责人过滤", text)
        self.assertIn("DOC-3", text)

    def test_check_surfaces_scope_and_filter_warning(self):
        items = [
            _item(1, "张三的完成项", state="已完成", state_type="completed",
                  completed=datetime(2026, 10, 21, tzinfo=timezone.utc)),
            _item(3, "没人负责的完成项", state="已完成", state_type="completed",
                  assignee=None, completed=datetime(2026, 10, 22, tzinfo=timezone.utc)),
        ]
        payload = {"version": 1, "projects": [_payload(items)], "quality": {}}
        filtered = COLLECT.filter_payload(payload, ["张三"])
        ok, lines = COLLECT.build_check(filtered)
        self.assertTrue(ok)
        self.assertTrue(any("按人过滤" in line and "张三" in line for line in lines))
        self.assertTrue(any("未分配被排除 1 条" in line for line in lines))
        self.assertTrue(any("按负责人过滤" in line for line in lines))

    def test_assignee_id_is_part_of_filter_key(self):
        item = _item(3, "按 id 匹配", assignee="王五")
        item["assignee"]["id"] = "u-123"
        filtered = COLLECT.filter_payload({"projects": [_payload([item])]}, ["u-123"])
        self.assertEqual(1, filtered["projects"][0]["quality"]["requirements_total"])

    def test_summary_can_be_truncated(self):
        item = _item(10, "长摘要", description="很长的描述。" * 40)
        project = _payload([item], summary_max_chars=20)
        summary = project["requirements"][0]["summary"]
        self.assertLessEqual(len(summary), 21)
        self.assertTrue(summary.endswith("…"))

    def test_summary_prefers_custom_property_then_description(self):
        item = _item(8, "标题", description="描述第一段。\n\n第二段")
        item["properties"]["周报摘要"] = "自定义摘要"
        project = _payload([item])
        req = next(row for row in project["requirements"] if row["id"] == "DOC-8")
        self.assertEqual(req["summary"], "自定义摘要")
        self.assertEqual(req["summary_source"], "custom")


class TestWeekly(unittest.TestCase):
    def _project(self):
        return _payload([
            _item(1, "完成多格式解析", state="已完成", state_type="completed",
                  completed=datetime(2026, 10, 21, tzinfo=timezone.utc),
                  description="新增 HTML 与 Markdown。"),
            _item(4, "缺陷：表格丢字段", kind="bug", state="打开", state_type="pending",
                  severity="P1", assignee=None),
            _item(3, "下周做 MCP", state="打开", state_type="pending", sprint="s2"),
            _item(5, "新需求待开始", state="打开", state_type="pending", sprint="s1"),
        ])

    def _payload(self):
        return {
            "version": 1,
            "generated_at": "2026-10-23T12:00:00+08:00",
            "window": {"since": "2026-10-19T00:00:00+08:00",
                       "until": "2026-10-25T23:59:59+08:00"},
            "projects": [self._project()],
            "quality": {},
        }

    def test_default_template_has_requirements_bugs_and_next_week(self):
        text = WEEKLY.render_weekly(self._payload())
        self.assertIn("本周任务", text)
        self.assertIn("本周新增缺陷", text)
        self.assertIn("缺陷清单", text)
        self.assertIn("下周计划", text)
        self.assertIn("DOC-1", text)
        self.assertIn("DOC-4", text)
        self.assertIn("P1", text)
        self.assertIn("DOC-3", text)
        self.assertIn("本周新增/待开始", text)
        self.assertIn("DOC-5", text)
        self.assertIn("文档平台", text)

    def test_closed_new_bug_still_appears(self):
        project = _payload([_item(9, "误报：旧格式", kind="bug", state="已拒绝",
                                  state_type="closed")])
        payload = self._payload()
        payload["projects"] = [project]
        text = WEEKLY.render_weekly(payload)
        self.assertIn("本周新增缺陷", text)
        self.assertIn("DOC-9", text)

    def test_custom_template_layout_and_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "weekly.toml"
            path.write_text(
                '[layout]\nbody = """# {week_start}\n{requirements}\n{bugs}"""\n'
                '[format]\nproject = "## {name}"\nrequirement = "* {summary} ({id})"\n'
                'open_bug = "- {severity} {summary}"\n',
                encoding="utf-8",
            )
            text = WEEKLY.render_weekly(self._payload(), path)
        self.assertIn("# 2026-10-19", text)
        self.assertIn("## 文档平台", text)
        self.assertIn("* 新增 HTML 与 Markdown。 (DOC-1)", text)
        self.assertIn("- P1 缺陷：表格丢字段", text)

    def test_unknown_template_field_is_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.toml"
            path.write_text('[layout]\nbody = "{missing}"\n', encoding="utf-8")
            with self.assertRaises(WEEKLY.TemplateError):
                WEEKLY.render_weekly(self._payload(), path)

    def test_empty_report_can_render(self):
        payload = self._payload()
        payload["projects"][0]["requirements"] = []
        payload["projects"][0]["bugs"] = []
        text = WEEKLY.render_weekly(payload)
        self.assertIn("本周没有已完成或进行中的", text)
        self.assertIn("无未关闭缺陷", text)


class TestOutput(unittest.TestCase):
    def test_env_override(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            os.environ, {OUTPUT.OUTPUT_ENV: tmp}
        ):
            self.assertEqual(OUTPUT.default_output_dir(), Path(tmp))

    def test_filename_is_safe(self):
        name = OUTPUT.build_filename("项目 A/周报", "2026-W43", "weekly.md")
        self.assertEqual(name, "项目-A-周报-2026-W43-weekly.md")

    def test_month_window_filename(self):
        since = datetime(2026, 10, 1, tzinfo=timezone.utc)
        until = datetime(2026, 10, 31, 23, 59, 59, tzinfo=timezone.utc)
        self.assertEqual("2026-10", OUTPUT.window_slug(since, until, month="2026-10"))

    def test_render_filename_avoids_overwriting_weekly(self):
        self.assertEqual(
            OUTPUT.render_filename("DOCFLUX-2026-W43-evidence"),
            "DOCFLUX-2026-W43-rendered-weekly.md",
        )

    def test_atomic_write_replaces_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "weekly.md"
            target.write_text("old", encoding="utf-8")
            OUTPUT.atomic_write_text(target, "new")
            self.assertEqual(target.read_text(encoding="utf-8"), "new")

    def test_atomic_write_failure_keeps_old_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "weekly.md"
            target.write_text("old", encoding="utf-8")
            with mock.patch.object(OUTPUT.os, "replace", side_effect=OSError("boom")), \
                    self.assertRaises(OSError):
                OUTPUT.atomic_write_text(target, "new")
            self.assertEqual(target.read_text(encoding="utf-8"), "old")
            self.assertEqual(list(Path(tmp).glob(".weekly.md.*.tmp")), [])


class TestWorkspaceConfig(unittest.TestCase):
    def _write(self, tmp: str, text: str) -> Path:
        path = Path(tmp) / "weekly.toml"
        path.write_text(text, encoding="utf-8")
        return path

    def test_unknown_workspace_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, '[workspace]\ntimezone = "Asia/Shanghai"\n'
                                   '[[projects]]\nname = "A"\n')
            with self.assertRaises(COLLECT.CollectError):
                COLLECT.load_workspace(path)

    def test_bad_summary_max_chars_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, '[[projects]]\nname = "A"\nsummary_max_chars = "abc"\n')
            with self.assertRaises(COLLECT.CollectError):
                COLLECT.load_workspace(path)

    def test_output_dir_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, '[workspace]\noutput_dir = "~/Downloads/pingcode-weekly"\n'
                                   '[[projects]]\nname = "A"\n')
            data = COLLECT.load_workspace(path)
            self.assertEqual(data["workspace"]["output_dir"],
                             "~/Downloads/pingcode-weekly")


class TestDocumentedWorkspaceExamples(unittest.TestCase):
    """文档里的工作区示例要能被真实解析器读取；写了 template 就必须指向存在的文件。

    模板路径相对**工作区文件所在目录**解析，读者照抄时最容易在这里出错。
    """

    def test_examples_resolve_template_to_existing_file(self):
        blocks = []
        for doc in (SKILL / "SKILL.md", SKILL / "README.md"):
            text = doc.read_text(encoding="utf-8")
            blocks += [m.group(1) for m in re.finditer(r"```toml\n(.*?)```", text, re.S)
                       if "[[projects]]" in m.group(1)]
        self.assertTrue(blocks, "文档里应有多项目工作区示例")
        for block in blocks:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "weekly.toml"
                path.write_text(block, encoding="utf-8")
                workspace = COLLECT.load_workspace(path)
                args = argparse.Namespace(template=None, workspace=str(path))
                template = CLI._template(args, workspace)
                if template is not None:
                    self.assertTrue(Path(template).is_file(),
                                    f"示例的 template 不存在：{template}")

    def test_readme_模板示例与默认模板一致(self):
        """README 里给人看的 `[layout] body` 不能与 `templates/default.toml` 走样。

        正文只留指针，模板只剩 `templates/default.toml` 与 `references/template.md` 两处权威；
        README 为了让人看懂保留半份拷贝，就得有东西盯着它。
        """
        default = tomllib.loads(
            (SKILL / "templates" / "default.toml").read_text(encoding="utf-8"))
        readme = (SKILL / "README.md").read_text(encoding="utf-8")
        bodies = []
        for match in re.finditer(r"```toml\n(.*?)```", readme, re.S):
            try:
                data = tomllib.loads(match.group(1))
            except tomllib.TOMLDecodeError:
                continue
            if isinstance(data.get("layout"), dict):
                bodies.append(data["layout"]["body"])
        self.assertTrue(bodies, "README 应给出 [layout] body 示例")
        for body in bodies:
            self.assertEqual(default["layout"]["body"], body,
                             "README 的 body 与 templates/default.toml 不一致")


class TestReadHelpers(unittest.TestCase):
    def test_type_resolve_accepts_story_and_bug(self):
        api = FakeApi([])
        requirement = READ.resolve_type(api, "p1", ["用户故事"], kind="需求")
        defect = READ.resolve_type(api, "p1", ["缺陷"], kind="缺陷")
        self.assertEqual(requirement["id"], "t-story")
        self.assertEqual(defect["id"], "t-bug")

    def test_next_sprint(self):
        api = FakeApi([])
        sprints = READ.list_sprints(api, "p1")
        current = READ.select_current_sprint(sprints, UNTIL)
        nxt = READ.select_next_sprint(sprints, UNTIL)
        self.assertEqual(current["id"], "s1")
        self.assertEqual(nxt["id"], "s2")


class TestCliOutput(unittest.TestCase):
    def _assigned_payload(self):
        def item(number, name):
            return {
                "id": f"DOC-{number}", "title": name, "kind": "requirement",
                "type": "用户故事", "state": "处理中", "state_type": "in_progress",
                "assignee": name, "assignee_id": f"u-{number}", "priority": "普通",
                "severity": None, "summary": f"{name}的事项", "summary_source": "custom",
                "created_at": "2026-10-20T10:00:00+08:00",
                "updated_at": "2026-10-21T10:00:00+08:00",
                "completed_at": None, "sprint": "2026-W43", "parent": None,
                "url": f"https://example.test/DOC-{number}", "open": True,
                "created_in_window": True, "updated_in_window": True,
                "completed_in_window": False, "planned": False, "age_days": 1,
            }
        return {
            "version": 1,
            "generated_at": "2026-10-23T12:00:00+08:00",
            "window": {"since": "2026-10-19T00:00:00+08:00",
                       "until": "2026-10-25T23:59:59+08:00"},
            "projects": [{
                "id": "p1", "identifier": "DOC", "name": "文档平台",
                "requirements": [item(1, "张三"), item(2, "李四")],
                "bugs": [], "quality": {},
                "sprints": {"current": {"name": "2026-W43"}, "next": None},
                "done_state_types": ["completed"],
            }],
            "quality": {},
        }

    def test_assignee_filter_only_outputs_selected_person(self):
        payload = self._assigned_payload()
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(CLI, "collect_workspace", return_value=payload), \
                mock.patch.dict(os.environ, {OUTPUT.OUTPUT_ENV: tmp}), \
                redirect_stdout(io.StringIO()) as out:
            code = CLI.main(["weekly", "--project", "PROJ", "--week", "2026-W43",
                             "--assignee", "张三", "--stdout"])
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertIn("DOC-1", text)
        self.assertNotIn("DOC-2", text)

    def test_mine_filters_by_current_user(self):
        payload = self._assigned_payload()
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(CLI, "collect_workspace", return_value=payload), \
                mock.patch.object(CLI, "open_client", return_value=object()), \
                mock.patch.object(CLI, "current_user", return_value={"id": "u-1", "name": "张三"}), \
                mock.patch.dict(os.environ, {OUTPUT.OUTPUT_ENV: tmp}), \
                redirect_stdout(io.StringIO()) as out:
            code = CLI.main(["weekly", "--project", "PROJ", "--week", "2026-W43",
                             "--mine", "--stdout"])
        self.assertEqual(code, 0)
        self.assertIn("DOC-1", out.getvalue())
        self.assertNotIn("DOC-2", out.getvalue())

    def test_weekly_warns_when_filter_excludes_unassigned(self):
        payload = self._assigned_payload()
        extra = {
            "id": "DOC-3", "title": "未分配需求", "kind": "requirement",
            "type": "用户故事", "state": "处理中", "state_type": "in_progress",
            "assignee": None, "assignee_id": None, "priority": "普通",
            "severity": None, "summary": "没人负责的事项", "summary_source": "title",
            "created_at": "2026-10-20T10:00:00+08:00",
            "updated_at": "2026-10-21T10:00:00+08:00",
            "completed_at": None, "sprint": "2026-W43", "parent": None,
            "url": "https://example.test/DOC-3", "open": True,
            "created_in_window": True, "updated_in_window": True,
            "completed_in_window": False, "planned": False, "age_days": 1,
        }
        payload["projects"][0]["requirements"].append(extra)
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(CLI, "collect_workspace", return_value=payload), \
                mock.patch.dict(os.environ, {OUTPUT.OUTPUT_ENV: tmp}), \
                redirect_stdout(io.StringIO()) as out, \
                redirect_stderr(io.StringIO()) as err:
            code = CLI.main(["weekly", "--project", "PROJ", "--week", "2026-W43",
                             "--assignee", "张三", "--stdout"])
        self.assertEqual(code, 0)
        self.assertIn("DOC-1", out.getvalue())
        self.assertIn("按负责人过滤", err.getvalue())
        self.assertIn("DOC-3", err.getvalue())
        self.assertIn("按负责人过滤", out.getvalue())

    def test_per_assignee_writes_one_file_per_person(self):
        payload = self._assigned_payload()
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(CLI, "collect_workspace", return_value=payload), \
                mock.patch.dict(os.environ, {OUTPUT.OUTPUT_ENV: tmp}), \
                redirect_stdout(io.StringIO()):
            code = CLI.main(["weekly", "--project", "PROJ", "--week", "2026-W43",
                             "--per-assignee", "--output-dir", tmp])
            files = {path.name for path in Path(tmp).iterdir()}
        self.assertEqual(code, 0)
        self.assertIn("DOC-2026-W43-张三-weekly.md", files)
        self.assertIn("DOC-2026-W43-李四-weekly.md", files)

    def test_weekly_defaults_to_download_dir(self):
        payload = {
            "version": 1,
            "projects": [{
                "id": "p1", "identifier": "DOC", "name": "文档平台",
                "requirements": [{"id": "DOC-1"}], "bugs": [], "quality": {},
            }],
            "quality": {},
        }
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(CLI, "collect_workspace", return_value=payload), \
                mock.patch.object(CLI, "render_weekly", return_value="report\n"), \
                mock.patch.dict(os.environ, {OUTPUT.OUTPUT_ENV: tmp}), \
                redirect_stdout(io.StringIO()):
            code = CLI.main(["weekly", "--project", "PROJ", "--week", "2026-W43"])
            target = Path(tmp) / "DOC-2026-W43-weekly.md"
            text = target.read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertEqual(text, "report\n")


class TestCliSurface(unittest.TestCase):
    def test_help_does_not_require_pingcode(self):
        import subprocess
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "pingcode_weekly.py"), "weekly", "--help"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("--project", proc.stdout)
        self.assertIn("--workspace", proc.stdout)
        self.assertIn("--stdout", proc.stdout)
