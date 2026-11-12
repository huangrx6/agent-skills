#!/usr/bin/env python3
"""vault 健康检查的回归测试。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "obsidian-wiki" / "scripts" / "health_check.py"
INIT_SCRIPT = ROOT / "skills" / "obsidian-wiki" / "scripts" / "init_vault.py"


def _load():
    spec = importlib.util.spec_from_file_location("health_check_under_test", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_init():
    spec = importlib.util.spec_from_file_location("init_vault_for_health_test", INIT_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {INIT_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HealthCheckTest(unittest.TestCase):
    def test_initialized_vault_passes_strict_check(self):
        health = _load()
        with tempfile.TemporaryDirectory(prefix="health-vault-") as tmp:
            _load_init().initialize(tmp)
            report = health.inspect(tmp, strict=True)
            self.assertTrue(report["ok"])
            self.assertEqual([], report["errors"])

    def test_broken_link_fails_by_default(self):
        health = _load()
        with tempfile.TemporaryDirectory(prefix="health-vault-broken-") as tmp:
            Path(tmp, "note.md").write_text("[[不存在]]\n", encoding="utf-8")
            report = health.inspect(tmp)
            self.assertFalse(report["ok"])
            self.assertEqual(1, len(report["broken_links"]))

    def test_missing_structure_only_fails_in_strict_mode(self):
        health = _load()
        with tempfile.TemporaryDirectory(prefix="health-vault-minimal-") as tmp:
            relaxed = health.inspect(tmp)
            strict = health.inspect(tmp, strict=True)
            self.assertTrue(relaxed["ok"])
            self.assertFalse(strict["ok"])

    def test_cli_strict_json_passes_initialized_vault(self):
        with tempfile.TemporaryDirectory(prefix="health-vault-cli-") as tmp:
            _load_init().initialize(tmp)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--vault", tmp, "--strict", "--json"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(json.loads(result.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
