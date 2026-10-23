#!/usr/bin/env python3
"""`tools/migrate_skill_home.py` 的回归测试。

迁移动的是用户主目录，最贵的错误是覆盖已有配置或把别的目录搬走。
所有用例都在临时 home 里跑，不碰真实 `~/.agent-skills`。
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL = HERE.parent / "migrate_skill_home.py"


def _load():
    spec = importlib.util.spec_from_file_location("migrate_under_test", TOOL)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {TOOL}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


M = _load()


class MigrationCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="migrate-home-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        self.repo = self.tmp / "repo"
        (self.home / ".config" / "agent-skills" / "pingcode").mkdir(parents=True)
        (self.home / ".config" / "agent-skills" / "pingcode" / "token.json").write_text("new")
        (self.home / ".config" / "deck-authoring" / "fonts").mkdir(parents=True)
        (self.home / ".config" / "deck-authoring" / "fonts" / "a.ttf").write_text("font")
        (self.home / ".cache" / "diagram-authoring" / "libraries").mkdir(parents=True)
        (self.home / ".cache" / "diagram-authoring" / "libraries" / "b.excalidrawlib").write_text("lib")
        (self.repo / "skills" / "learning-scout" / ".venv" / "bin").mkdir(parents=True)
        (self.repo / "skills" / "learning-scout" / ".venv" / "bin" / "python").write_text("py")

    def run_tool(self, *args: str) -> int:
        with contextlib.redirect_stdout(io.StringIO()):
            return M.main(["--home", str(self.home), "--repo", str(self.repo), *args])


class TestDryRun(MigrationCase):
    def test_dry_run_changes_nothing(self):
        self.assertEqual(0, self.run_tool())
        self.assertTrue((self.home / ".config" / "agent-skills" / "pingcode" / "token.json").exists())
        self.assertFalse((self.home / ".agent-skills").exists())


class TestApply(MigrationCase):
    def test_moves_config_and_data(self):
        self.assertEqual(0, self.run_tool("--apply"))
        base = self.home / ".agent-skills"
        self.assertEqual("new", (base / "config" / "pingcode" / "token.json").read_text())
        self.assertEqual("font", (base / "data" / "deck-authoring" / "fonts" / "a.ttf").read_text())
        self.assertEqual("lib", (base / "data" / "diagram-authoring" / "libraries" / "b.excalidrawlib").read_text())
        self.assertEqual("py", (base / "data" / "learning-scout" / "venv" / "bin" / "python").read_text())
        self.assertFalse((self.home / ".config" / "agent-skills").exists())

    def test_existing_target_is_not_overwritten(self):
        target = self.home / ".agent-skills" / "config" / "pingcode"
        target.mkdir(parents=True)
        (target / "token.json").write_text("old")
        self.assertEqual(1, self.run_tool("--apply"))
        self.assertEqual("old", (target / "token.json").read_text())
        self.assertEqual("new", (self.home / ".config" / "agent-skills" / "pingcode" / "token.json").read_text())

    def test_apply_is_idempotent(self):
        self.assertEqual(0, self.run_tool("--apply"))
        self.assertEqual(0, self.run_tool("--apply"))
        base = self.home / ".agent-skills"
        self.assertTrue((base / "config" / "pingcode" / "token.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
