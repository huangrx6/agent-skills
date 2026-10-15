"""复制单个工作台包，在没有相邻 skill 的临时目录里运行真实 CLI。"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[2] / "skills" / "obsidian-work"


class StandalonePackageTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.package = self.root / "isolated skills" / "obsidian-work"
        shutil.copytree(SOURCE, self.package, ignore=shutil.ignore_patterns("__pycache__"))
        self.vault = self.root / "工作 笔记"
        self.vault.mkdir()
        self.config = self.root / "configuration"
        self.config.mkdir()
        (self.config / "obsidian-vault-path").write_text(str(self.vault), encoding="utf-8")
        self.env = os.environ.copy()
        self.env.pop("OBSIDIAN_VAULT_PATH", None)
        self.env["AGENT_SKILLS_CONFIG_DIR"] = str(self.config)

    def run_cli(self, name, *args):
        return subprocess.run(
            [sys.executable, "-I", str(self.package / "scripts" / name), *map(str, args)],
            cwd=self.root, env=self.env, capture_output=True, text=True, timeout=10,
        )

    def release_note(self):
        text = (self.package / "references" / "release-note-template.md").read_text(encoding="utf-8")
        body = re.findall(r"^````markdown\n(.*?)^````$", text, re.DOTALL | re.MULTILINE)[0]
        title = "发版 - 演示系统 - 2026-W18"
        body = body.replace("# 发版 - <系统或项目名> - YYYY-Www", f"# {title}")
        body = body.replace("created: YYYY-MM-DD", "created: 2026-05-01")
        note = self.vault / f"{title}.md"
        note.write_text(body, encoding="utf-8")
        (self.vault / "项目索引.md").write_text(f"[[{title}]]\n", encoding="utf-8")
        return note

    def test_release_cli_works_without_sibling_skills_and_is_read_only(self):
        note = self.release_note()
        before = {p.name: p.read_bytes() for p in self.vault.iterdir()}
        self.assertEqual([self.package], list(self.package.parent.iterdir()))
        result = self.run_cli("check_release_note.py", note, "--vault", self.vault)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("0 有问题", result.stdout)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.vault.iterdir()})

    def test_release_cli_resolves_config_with_packaged_path_helper(self):
        note = self.release_note()
        result = self.run_cli("check_release_note.py", note)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertNotIn("跳过", result.stdout)
        self.assertIn("1 篇有明确 wikilink", result.stdout)

    def test_packaged_link_checker_detects_real_broken_link_ignores_code(self):
        (self.vault / "任务.md").write_text(
            "[[不存在的需求]]\n`[[代码示例]]`\n![[附件.txt]]\n", encoding="utf-8")
        (self.vault / "附件.txt").write_text("fixture", encoding="utf-8")
        result = self.run_cli("check_links.py", "--vault", self.vault, "--json")
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(1, data["broken_count"])
        self.assertEqual("不存在的需求", data["broken"][0]["target"])

    def test_packaged_link_checker_ignores_only_complete_template_directory_names(self):
        template_notes = {
            "Templates/英文.md", "99 System/templates/小写.md",
            "99 System/模板/工作台/中文.md",
        }
        ordinary_notes = {
            "MyTemplates/说明.md", "模板研究/说明.md", "templates-old/说明.md", "模板.md",
        }
        for relative in template_notes | ordinary_notes:
            note = self.vault / relative
            note.parent.mkdir(parents=True, exist_ok=True)
            note.write_text("[[尚不存在的目标]]\n", encoding="utf-8")
        normal = self.run_cli("check_links.py", "--vault", self.vault, "--json")
        self.assertEqual(1, normal.returncode, normal.stdout + normal.stderr)
        self.assertEqual(len(template_notes | ordinary_notes), json.loads(normal.stdout)["broken_count"])
        filtered = self.run_cli("check_links.py", "--vault", self.vault, "--ignore-template", "--json")
        self.assertEqual(1, filtered.returncode, filtered.stdout + filtered.stderr)
        data = json.loads(filtered.stdout)
        self.assertEqual(ordinary_notes, {item["file"] for item in data["broken"]})
        self.assertEqual(len(ordinary_notes), data["broken_count"])

    def test_packaged_path_helper_preserves_explicit_env_config_precedence(self):
        env_vault, explicit_vault = self.root / "env vault", self.root / "explicit vault"
        env_vault.mkdir()
        explicit_vault.mkdir()
        result = self.run_cli("vault_path.py")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(str(self.vault), result.stdout.strip())
        self.env["OBSIDIAN_VAULT_PATH"] = str(env_vault)
        result = self.run_cli("vault_path.py")
        self.assertEqual(str(env_vault), result.stdout.strip())
        result = self.run_cli("vault_path.py", explicit_vault)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(str(explicit_vault), result.stdout.strip())

    def test_incomplete_standalone_package_returns_friendly_error(self):
        note = self.release_note()
        (self.package / "scripts" / "check_links.py").unlink()
        result = self.run_cli("check_release_note.py", note, "--vault", self.vault)
        self.assertEqual(2, result.returncode)
        self.assertIn("缺少包内链接检查器", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
