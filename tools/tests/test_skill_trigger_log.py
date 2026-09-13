#!/usr/bin/env python3
"""`tools/skill_trigger_log.py` 的回归测试。

这个脚本的作用是**给「该不该建下一个 skill」提供数据**。它算错的后果不是崩掉，而是
给出一个错的频率表 —— 而人会拿那张表做决定。所以下面这些边界必须有测试：

- **口径**：`forks/`（父会话副本）与 `subagent-artifacts/`（子代理产物）必须排除 ——
  不排会把同一个触发重复计数，把数字整体抬高
- **归属**：skill 名优先取 `<skill location=...>` 的父目录名（改名后仍能对上），
  拿不到才退回 `name`
- **两类信号分开算**：自动触发（description 生效）与显式加载（`$name`）是两回事，
  合并了就看不出「哪个 description 真的在干活」
- **历史名字**：触发了但仓库里没有的，要单独列，不能静默丢掉
- 坏行、超大行、空目录都不能让它崩

测试造一个假会话目录 + 假仓库，不碰真的 `~/.pi`。
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
LOG = os.path.join(TOOLS, "skill_trigger_log.py")


def _load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


log = _load(LOG, "_test_skill_trigger_log")


def inline(skill: str, location: str = "", stamp: str = "2026-09-01T10:00:00.000Z") -> str:
    loc = location or f"/repo/skills/{skill}/SKILL.md"
    content = f'<skill name="{skill}" location="{loc}">\n正文\n</skill>'
    return json.dumps({"type": "custom_message", "customType": "inline-skill",
                       "content": content, "timestamp": stamp}, ensure_ascii=False)


def loaded(skill: str, stamp: str = "2026-09-01T11:00:00.000Z",
           source: str = "tool-result") -> str:
    return json.dumps({"type": "custom", "customType": "loaded-skill",
                       "data": {"name": skill, "source": source},
                       "timestamp": stamp}, ensure_ascii=False)


OTHER = json.dumps({"type": "message", "content": "普通对话，什么都没触发"})


class Case(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.sessions = os.path.join(self.root, "sessions")
        os.makedirs(os.path.join(self.sessions, "--proj-a--"))
        os.makedirs(os.path.join(self.sessions, "--proj-b--"))

    def write_session(self, project: str, name: str, lines: list[str]) -> str:
        path = os.path.join(self.sessions, project, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        return path

    def fake_sessions(self, project: str, name: str, lines: list) -> str:
        return self.write_session(project, name, lines)


class CollectTest(Case):
    def test_两类信号分开计数(self):
        self.write_session("--proj-a--", "s1.jsonl", [inline("aaa"), loaded("aaa"), loaded("bbb")])
        data = log.collect(self.sessions)
        self.assertEqual(1, data["skills"]["aaa"]["自动触发"])
        self.assertEqual(1, data["skills"]["aaa"]["显式加载"])
        self.assertEqual(2, data["skills"]["aaa"]["total"])
        self.assertEqual(0, data["skills"]["bbb"]["自动触发"])
        self.assertEqual(1, data["skills"]["bbb"]["显式加载"])

    def test_同一会话内多次触发分别计数(self):
        self.write_session("--proj-a--", "s1.jsonl", [inline("aaa"), inline("aaa"), inline("aaa")])
        data = log.collect(self.sessions)
        self.assertEqual(3, data["skills"]["aaa"]["自动触发"])
        self.assertEqual(1, data["skills"]["aaa"]["sessions"], "但只算出现过 1 个会话")

    def test_跨会话累计且记项目数(self):
        self.write_session("--proj-a--", "s1.jsonl", [inline("aaa")])
        self.write_session("--proj-b--", "s2.jsonl", [inline("aaa"), loaded("aaa")])
        bucket = log.collect(self.sessions)["skills"]["aaa"]
        self.assertEqual(2, bucket["sessions"])
        self.assertEqual(["--proj-a--", "--proj-b--"], bucket["projects"])

    def test_排除_fork_副本(self):
        """不排 forks/ 就会把父会话的触发重复算一遍。"""
        self.write_session("--proj-a--", "s1.jsonl", [inline("aaa")])
        os.makedirs(os.path.join(self.sessions, "--proj-a--", "forks"))
        self.write_session("--proj-a--", os.path.join("forks", "f1.jsonl"), [inline("aaa")])
        data = log.collect(self.sessions)
        self.assertEqual(1, data["skills"]["aaa"]["自动触发"])
        self.assertEqual(1, data["sessions_scanned"])

    def test_排除子代理产物(self):
        self.write_session("--proj-a--", "s1.jsonl", [inline("aaa")])
        os.makedirs(os.path.join(self.sessions, "--proj-a--", "subagent-artifacts"))
        self.write_session("--proj-a--", os.path.join("subagent-artifacts", "x.jsonl"),
                           [inline("aaa")])
        data = log.collect(self.sessions)
        self.assertEqual(1, data["skills"]["aaa"]["自动触发"])
        self.assertEqual(1, data["sessions_scanned"])

    def test_归属优先用_location_的父目录名(self):
        """skill 改过名时 location 指向现名（name 可能是旧名）。"""
        self.write_session("--proj-a--", "s1.jsonl",
                           [inline("old-name", location="/repo/skills/new-name/SKILL.md")])
        self.assertIn("new-name", log.collect(self.sessions)["skills"])

    def test_location_拿不到时退回_name(self):
        self.write_session("--proj-a--", "s1.jsonl", [inline("aaa", location="")])
        self.assertIn("aaa", log.collect(self.sessions)["skills"])

    def test_坏行与其它记录不影响统计(self):
        self.write_session("--proj-a--", "s1.jsonl",
                           ["{不是合法 json", OTHER, inline("aaa"), "", "   "])
        data = log.collect(self.sessions)
        self.assertEqual(["aaa"], list(data["skills"]))

    def test_没有会话目录时返回空而不是崩(self):
        data = log.collect(os.path.join(self.root, "不存在"))
        self.assertEqual(0, data["sessions_scanned"])
        self.assertEqual({}, data["skills"])

    def test_空目录也安全(self):
        empty = os.path.join(self.root, "empty")
        os.makedirs(empty)
        self.assertEqual(0, log.collect(empty)["sessions_scanned"])


class SummarizeTest(Case):
    def repo_with(self, *names: str) -> str:
        repo = os.path.join(self.root, "repo")
        for name in names:
            os.makedirs(os.path.join(repo, "skills", name), exist_ok=True)
        return repo

    def test_列出从未触发的与不在仓库里的(self):
        repo = self.repo_with("aaa", "bbb")
        self.write_session("--proj-a--", "s1.jsonl", [inline("aaa"), inline("外部skill")])
        groups = log.summarize(log.collect(self.sessions), repo)
        self.assertEqual(["bbb"], groups["从未触发的 skill"])
        self.assertEqual(["外部skill"], groups["已不在仓库里的 skill"])

    def test_窗口取最早与最晚(self):
        self.write_session("--proj-a--", "s1.jsonl",
                           [inline("aaa", stamp="2026-08-01T00:00:00.000Z"),
                            inline("aaa", stamp="2026-09-20T00:00:00.000Z")])
        groups = log.summarize(log.collect(self.sessions), self.repo_with("aaa"))
        self.assertEqual(("2026-08-01", "2026-09-20"), groups["窗口"])


class BaselineTest(Case):
    """基线快照：没有它，「三周后再看一次」就只能靠人翻旧终端输出 —— 那就等于不会发生。"""

    def repo(self) -> str:
        repo = os.path.join(self.root, "repo")
        os.makedirs(os.path.join(repo, "skills", "aaa"), exist_ok=True)
        os.makedirs(os.path.join(repo, "tools"), exist_ok=True)
        return repo

    def test_存基线带上日期与计数(self):
        repo = self.repo()
        self.write_session("--proj-a--", "s1.jsonl", [inline("aaa"), loaded("aaa")])
        path = log.save_baseline(repo, log.collect(self.sessions), "补了中文触发词")
        self.assertTrue(path.endswith("trigger-baseline.json"))
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        self.assertEqual(1, payload["skills"]["aaa"]["auto"])
        self.assertEqual(1, payload["skills"]["aaa"]["manual"])
        self.assertRegex(payload["saved_at"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual("补了中文触发词", payload["note"])

    def test_没有基线时读回_None(self):
        self.assertIsNone(log.load_baseline(self.repo()))

    def test_对比只说变化(self):
        base = {"saved_at": "2026-09-01", "sessions_scanned": 9,
                "skills": {"aaa": {"auto": 0, "manual": 2}, "bbb": {"auto": 0, "manual": 1}}}
        self.write_session("--proj-a--", "s1.jsonl", [inline("aaa"), loaded("bbb")])
        lines = "\n".join(log.compare(log.collect(self.sessions), base))
        self.assertIn("0 → 1", lines, "自动触发从 0 变 1 要标出来")
        self.assertIn("← 变了", lines)
        self.assertIn("自动触发总数：0 → 1", lines)
        self.assertIn("样本量", lines, "结论要带样本量提醒")

    def test_对比没变化时要说没变化(self):
        data = log.collect(self.sessions)
        base = {"saved_at": "2026-09-01", "sessions_scanned": 0, "skills": {}}
        lines = "\n".join(log.compare(data, base))
        self.assertIn("没有变化", lines)

    def test_compare_在没有基线时给提示且不报失败(self):
        repo = self.repo()
        self.write_session("--proj-a--", "s1.jsonl", [inline("aaa")])
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            code = log.main(["--sessions-dir", self.sessions, "--root", repo, "--compare"])
        self.assertEqual(0, code)
        self.assertIn("--save-baseline", err.getvalue())

    def test_save_baseline_写到仓库的_tools_下(self):
        repo = self.repo()
        self.write_session("--proj-a--", "s1.jsonl", [inline("aaa")])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = log.main(["--sessions-dir", self.sessions, "--root", repo, "--save-baseline"])
        self.assertEqual(0, code)
        self.assertIn("基线已存", buf.getvalue())
        self.assertIsNotNone(log.load_baseline(repo))


class RenderTest(Case):
    def test_表格含两类信号与口径说明(self):
        repo = os.path.join(self.root, "repo")
        os.makedirs(os.path.join(repo, "skills", "aaa"))
        os.makedirs(os.path.join(repo, "skills", "bbb"))
        self.write_session("--proj-a--", "s1.jsonl", [inline("aaa"), loaded("aaa")])
        data = log.collect(self.sessions)
        text = log.render(data, repo)
        self.assertIn("自动触发", text)
        self.assertIn("显式加载", text)
        self.assertIn("bbb", text, "从未触发的要列出来")
        self.assertIn("口径", text, "别让读者把它当成全部历史")
        self.assertIn("forks", text)

    def test_一条记录都没有时给一句人话(self):
        text = log.render(log.collect(self.sessions), self.root)
        self.assertIn("一个触发记录都没有", text)

    def test_json_输出可解析(self):
        repo = os.path.join(self.root, "repo")
        os.makedirs(os.path.join(repo, "skills", "aaa"))
        self.write_session("--proj-a--", "s1.jsonl", [inline("aaa")])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = log.main(["--sessions-dir", self.sessions, "--root", repo, "--json"])
        self.assertEqual(0, code)
        payload = json.loads(buf.getvalue())
        self.assertEqual(1, payload["sessions_scanned"])
        self.assertEqual(1, payload["skills"]["aaa"]["自动触发"])

    def test_会话目录不存在时给提示且不报失败(self):
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            code = log.main(["--sessions-dir", os.path.join(self.root, "没有")])
        self.assertEqual(0, code, "这只是个报告工具，不该让调用方失败")


if __name__ == "__main__":
    unittest.main(verbosity=2)
