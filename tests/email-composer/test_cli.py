"""CLI 契约：退出码、输出文件与参数接线。"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parents[1] / "skills" / "email-composer"
SCRIPTS = SKILL / "scripts"
EXAMPLE = SKILL / "examples" / "approval-release.yaml"

VARIABLES = [
    "Orbit={{project}}",
    "2026-11-20 20:00={{release_time}}",
    "2026-11-18 18:00={{confirm_deadline}}",
    "2026-11-19 12:00={{notify_deadline}}",
    "20:00={{freeze_time}}",
    "20:30={{gray_time}}",
    "22:00={{full_time}}",
]
SETS = [
    "project=Nova",
    "release_time=2026-12-01 21:00",
    "confirm_deadline=2026-11-28 18:00",
    "notify_deadline=2026-11-29 12:00",
    "freeze_time=21:00",
    "gray_time=21:30",
    "full_time=23:00",
]


def run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


class TestRenderCli(unittest.TestCase):
    def test_render_writes_selected_formats(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run(
                "render.py", str(EXAMPLE), "--outdir", tmp, "--formats", "html,text", "--json"
            )
            self.assertEqual(0, result.returncode, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual({"html", "text"}, set(payload["files"]))
            for path in payload["files"].values():
                self.assertTrue(Path(path).is_file())
            self.assertEqual("business", payload["preset"])

    def test_bad_spec_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = Path(tmp) / "bad.yaml"
            spec.write_text("blocks:\n  - kind: nope\n    text: x\n", encoding="utf-8")
            result = run("render.py", str(spec), "--outdir", tmp)
            self.assertEqual(2, result.returncode)
            self.assertIn("错误", result.stderr)


class TestValidateCli(unittest.TestCase):
    def test_clean_spec_exit_zero(self):
        result = run("validate.py", str(EXAMPLE))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])

    def test_blocking_spec_exit_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = Path(tmp) / "bad.yaml"
            spec.write_text(
                "type: notice\nsubject: ''\nsummary: 系统维护。\nfacts: []\n",
                encoding="utf-8",
            )
            result = run("validate.py", str(spec))
            self.assertEqual(1, result.returncode)
            report = json.loads(result.stdout)
            self.assertFalse(report["ok"])
            self.assertIn("subject_missing", {item["code"] for item in report["blocking"]})


class TestTemplateCli(unittest.TestCase):
    def test_empty_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run("template.py", "--root", tmp, "list", "--json")
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual([], json.loads(result.stdout)["templates"])

    def test_save_and_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = [
                "template.py",
                "--root",
                tmp,
                "save",
                "--spec",
                str(EXAMPLE),
                "--id",
                "approval-release",
                "--name",
                "上线申请",
            ]
            for item in VARIABLES:
                args.extend(["--var", item])
            saved = run(*args)
            self.assertEqual(0, saved.returncode, saved.stderr)
            self.assertEqual("v1", json.loads(saved.stdout)["version"])

            outdir = Path(tmp) / "out"
            apply_args = [
                "template.py",
                "--root",
                tmp,
                "apply",
                "approval-release",
                "--outdir",
                str(outdir),
            ]
            for item in SETS:
                apply_args.extend(["--set", item])
            applied = run(*apply_args)
            self.assertEqual(0, applied.returncode, applied.stderr)
            payload = json.loads(applied.stdout)
            self.assertTrue(payload["ok"])
            self.assertTrue(all(Path(path).is_file() for path in payload["files"].values()))

    def test_add_html_and_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "demo.html"
            source.write_text(
                '<!DOCTYPE html><html><head><title>通知｜{{name}}</title></head>'
                '<body><p>{{name}}</p></body></html>',
                encoding="utf-8",
            )
            added = run("template.py", "--root", tmp, "add-html", str(source))
            self.assertEqual(0, added.returncode, added.stderr)
            payload = json.loads(added.stdout)
            self.assertEqual("html/demo", payload["id"])

            outdir = Path(tmp) / "out"
            applied = run(
                "template.py", "--root", tmp, "apply", "html/demo",
                "--outdir", str(outdir), "--set", "name=客服",
            )
            self.assertEqual(0, applied.returncode, applied.stderr)
            result = json.loads(applied.stdout)
            self.assertTrue(result["ok"])
            self.assertIn("客服", Path(result["files"]["text"]).read_text())


if __name__ == "__main__":
    unittest.main()
