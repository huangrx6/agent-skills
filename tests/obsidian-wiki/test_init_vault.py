#!/usr/bin/env python3
"""初始化脚本的回归测试：不覆盖已有内容，可选配置路径和 Git。"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "obsidian-wiki" / "scripts" / "init_vault.py"


def _load():
    spec = importlib.util.spec_from_file_location("init_vault_under_test", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InitVaultTest(unittest.TestCase):
    def test_creates_layout_and_is_idempotent(self):
        mod = _load()
        with tempfile.TemporaryDirectory(prefix="init-vault-") as tmp:
            target = Path(tmp) / "vault"
            first = mod.initialize(str(target))
            self.assertGreaterEqual(len(first["created"]), 8)
            self.assertTrue((target / "03 Resources/资源区 - 索引.md").is_file())
            self.assertTrue((target / "90 Assets/Attachments").is_dir())
            self.assertTrue((target / "90 Assets/Attachments/.gitkeep").is_file())

            custom = target / "99 System/首页.md"
            custom.write_text("# 我的首页\n", encoding="utf-8")
            obsidian_config = target / ".obsidian/app.json"
            obsidian_config.parent.mkdir()
            obsidian_config.write_text('{"readableLineLength": true}\n', encoding="utf-8")
            second = mod.initialize(str(target))
            self.assertEqual("# 我的首页\n", custom.read_text(encoding="utf-8"))
            self.assertEqual(
                '{"readableLineLength": true}\n',
                obsidian_config.read_text(encoding="utf-8"),
            )
            self.assertEqual([], second["created"])
            self.assertGreater(len(second["existing"]), 0)

    def test_git_and_config_are_opt_in_and_reported(self):
        mod = _load()
        with tempfile.TemporaryDirectory(prefix="init-vault-git-") as tmp:
            target = Path(tmp) / "vault"
            config_dir = Path(tmp) / "config"
            old = os.environ.get("AGENT_SKILLS_CONFIG_DIR")
            os.environ["AGENT_SKILLS_CONFIG_DIR"] = str(config_dir)
            try:
                report = mod.initialize(str(target), use_git=True, configure=True)
            finally:
                if old is None:
                    os.environ.pop("AGENT_SKILLS_CONFIG_DIR", None)
                else:
                    os.environ["AGENT_SKILLS_CONFIG_DIR"] = old
            self.assertTrue((target / ".git").exists())
            self.assertEqual(str((config_dir / "obsidian-vault-path").resolve()), report["config"])
            self.assertEqual(str(target.resolve()), (config_dir / "obsidian-vault-path").read_text().strip())

    def test_cli_json_is_machine_readable(self):
        with tempfile.TemporaryDirectory(prefix="init-vault-cli-") as tmp:
            target = Path(tmp) / "vault"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(target), "--json"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(str(target.resolve()), payload["vault"])
            self.assertIsNone(payload["git"])

    def test_config_conflict_does_not_write_vault_files(self):
        mod = _load()
        with tempfile.TemporaryDirectory(prefix="init-vault-conflict-") as tmp:
            target = Path(tmp) / "vault"
            config_dir = Path(tmp) / "config"
            config_dir.mkdir()
            (config_dir / "obsidian-vault-path").write_text("/another/vault\n", encoding="utf-8")
            old = os.environ.get("AGENT_SKILLS_CONFIG_DIR")
            os.environ["AGENT_SKILLS_CONFIG_DIR"] = str(config_dir)
            try:
                with self.assertRaises(mod.InitError):
                    mod.initialize(str(target), configure=True)
            finally:
                if old is None:
                    os.environ.pop("AGENT_SKILLS_CONFIG_DIR", None)
                else:
                    os.environ["AGENT_SKILLS_CONFIG_DIR"] = old
            self.assertFalse(target.exists())

    def test_nested_git_target_is_rejected_before_writes(self):
        mod = _load()
        with tempfile.TemporaryDirectory(prefix="init-vault-nested-") as tmp:
            parent = Path(tmp) / "repo"
            parent.mkdir()
            subprocess.run(["git", "init", "-q", str(parent)], check=True)
            target = parent / "vault"
            with self.assertRaises(mod.InitError):
                mod.initialize(str(target), use_git=True)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
