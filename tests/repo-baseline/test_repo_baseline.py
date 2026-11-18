#!/usr/bin/env python3
"""`repo-baseline` 的回归测试。

这个 skill 的产物是「在别人仓库里写文件」，所以判据只有两类：

1. **只增不改**：已有文件一个字节都不能动，`.gitignore` 只追加缺失行；
2. **状态判定不撒谎**：只有源码没有依赖清单的目录不能报成「空目录」，
   有 husky 的仓库不能静默写入。

`git` 相关用例在缺少 git 时跳过（钩子位置要真实仓库才解析得出来）。
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
# 测试住在仓库顶层 `tests/<skill>/`，被测脚本在 `skills/<skill>/scripts/`。
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


DETECT = _load("detect", os.path.join(SCRIPTS, "detect.py"))
APPLY = _load("apply", os.path.join(SCRIPTS, "apply.py"))

HAS_GIT = shutil.which("git") is not None


def run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, script), *args],
        capture_output=True, text=True, timeout=120,
    )


class Fixture(unittest.TestCase):
    """每个用例一个临时目录；需要 git 的用例自己调 `init_repo`。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def init_repo(self, github: bool = False) -> None:
        self.git("init", "-q")
        if github:
            self.git("remote", "add", "origin", "https://github.com/acme/demo.git")
        self.git("add", "-A")

    def python_project(self, relative: str = "pyproject.toml") -> None:
        """最小 Python 清单：让目录确定落在 partial，而不是被当成空目录。"""
        self.write(relative, '[project]\nname = "demo"\nrequires-python = ">=3.11"\n')

    def git(self, *args: str) -> None:
        subprocess.run(["git", "-C", str(self.root), *args],
                       capture_output=True, text=True, timeout=60, check=False)

    def detect(self) -> dict:
        result = run("detect.py", "--root", str(self.root))
        self.assertEqual(0, result.returncode, result.stderr)
        return json.loads(result.stdout)

    def apply(self, *args: str) -> tuple[int, dict]:
        result = run("apply.py", "--root", str(self.root), *args)
        return result.returncode, json.loads(result.stdout or "{}")


class TestState(Fixture):
    def test_空目录是_empty(self):
        self.assertEqual("empty", self.detect()["state"])

    def test_只有源码没有依赖清单不算空目录(self):
        """实测踩过：只有 a.py 时被判成 empty，提示语还断言「没有代码」。"""
        self.write("a.py", "print(1)\n")
        report = self.detect()
        self.assertEqual("partial", report["state"])
        self.assertIn("git 仓库（需先 git init，需确认）", report["missing"])

    def test_git_init_后的空仓库仍是_empty(self):
        if not HAS_GIT:
            self.skipTest("没有 git")
        self.init_repo()
        self.assertEqual("empty", self.detect()["state"])

    def test_依赖清单存在就是_partial(self):
        self.write("pyproject.toml", '[project]\nname = "x"\nrequires-python = ">=3.11"\n')
        self.assertEqual("partial", self.detect()["state"])

    def test_基线齐全且钩子已装才是_complete(self):
        if not HAS_GIT:
            self.skipTest("没有 git")
        self.write(".editorconfig", "root = true\n")
        self.write(".gitignore", "\n".join(DETECT.GITIGNORE_LINES) + "\n")
        self.write(".pre-commit-config.yaml", "repos: []\n")
        self.write("Makefile", "check: lint test\nlint:\n\t@echo x\n")
        self.write("AGENTS.md", "# x\n")
        self.write("CLAUDE.md", "@AGENTS.md\n")
        self.init_repo()
        hook = self.root / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\n# pre-commit\n", encoding="utf-8")
        hook.chmod(0o755)
        self.assertEqual("complete", self.detect()["state"])

    def test_子目录仓库也能认到父仓库的钩子(self):
        """git rev-parse --git-path hooks：子目录里的 `.git/hooks` 并不存在。"""
        if not HAS_GIT:
            self.skipTest("没有 git")
        self.init_repo()
        hook = self.root / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\n# pre-commit\n", encoding="utf-8")
        hook.chmod(0o755)
        sub = self.root / "sub"
        sub.mkdir()
        self.assertTrue(DETECT.analyze_hooks(sub)["git_hook_installed"])

    def test_大于1MB的跟踪文件进风险清单(self):
        if not HAS_GIT:
            self.skipTest("没有 git")
        (self.root / "big.bin").write_bytes(b"0" * (1024 * 1024 + 1))
        self.init_repo()
        risks = self.detect()["risks"]
        self.assertTrue(any("big.bin" in item for item in risks), risks)


class TestParsing(unittest.TestCase):
    def test_依赖按完整包名匹配(self):
        """`"pytest` 曾命中 `"pytest-cov`，于是漏掉「未声明 pytest」。"""
        text = 'deps = ["pytest-cov>=5", "ruffle"]'
        self.assertFalse(DETECT.has_dep(text, "", "pytest"))
        self.assertFalse(DETECT.has_dep(text, "", "ruff"))
        self.assertTrue(DETECT.has_dep('deps = ["ruff>=0.5"]', "", "ruff"))
        self.assertTrue(DETECT.has_dep('deps = ["ruff[dev]"]', "", "ruff"))
        self.assertTrue(DETECT.has_dep("", 'name = "ruff"\n', "ruff"))

    def test_目标名不吃_url_也不含特殊目标(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Makefile"
            path.write_text(
                "# https://example.com/x\nhttps://example.com/y\n.SUFFIXES:\nVERSION := 1\n"
                "check: lint test\nlint:\n\t@echo x\n",
                encoding="utf-8",
            )
            self.assertEqual(["check", "lint"], DETECT.make_targets(path))

    def test_根目录项目不生成_cd_点(self):
        self.assertEqual("uv sync", DETECT.in_dir(".", "uv sync"))
        self.assertEqual("cd backend && uv sync", DETECT.in_dir("backend", "uv sync"))
        self.assertEqual("pnpm install", DETECT.pnpm(".", "install"))
        self.assertEqual("pnpm -C web install", DETECT.pnpm("web", "install"))


class TestWrite(Fixture):
    def test_只创建缺失文件且不动已有文件(self):
        original = "root = true\n# 用户自己写的\n"
        self.write(".editorconfig", original)
        self.write("Makefile", "check:\n\t@echo mine\n")
        code, report = self.apply("--write")
        self.assertEqual(0, code)
        created = [item["path"] for item in report["results"] if item["result"] == "已创建"]
        self.assertNotIn(".editorconfig", created)
        self.assertNotIn("Makefile", created)
        self.assertEqual(original, (self.root / ".editorconfig").read_text(encoding="utf-8"))
        self.assertEqual("check:\n\t@echo mine\n", (self.root / "Makefile").read_text(encoding="utf-8"))

    def test_gitignore_只追加缺失行并保留原内容(self):
        self.write(".gitignore", "custom/\n")
        self.apply("--write")
        text = (self.root / ".gitignore").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("custom/\n"))
        for line in DETECT.GITIGNORE_LINES:
            self.assertIn(line, text.splitlines())
        self.assertEqual(1, text.count("# repo-baseline 追加"))

    def test_重复写入是幂等的(self):
        self.python_project()
        self.apply("--write")
        code, report = self.apply("--write")
        self.assertEqual(0, code)
        self.assertEqual([], report["results"])

    def test_husky_阻断写入除非显式接受(self):
        self.python_project()
        self.write(".husky/pre-commit", "npx lint-staged\n")
        code, report = self.apply("--write")
        self.assertEqual(3, code, "阻断冲突必须拒绝写入")
        self.assertTrue(report["blocking"])
        self.assertFalse((self.root / "Makefile").exists())

        code, _ = self.apply("--write", "--accept-conflicts")
        self.assertEqual(0, code)
        self.assertTrue((self.root / "Makefile").exists())

    def test_计划模式不写任何文件(self):
        self.python_project()
        code, report = self.apply()
        self.assertEqual(0, code)
        self.assertEqual("plan", report["mode"])
        self.assertTrue(report["actions"])
        self.assertEqual(["pyproject.toml"], sorted(p.name for p in self.root.iterdir()))

    def test_格式检查跳过锁文件(self):
        """prettier 会重写锁文件，和 pnpm 维护的格式打架；钩子已排掉，Makefile 也要排。"""
        self.write("web/package.json", '{"name": "web", "devDependencies": {"prettier": "^3"}}\n')
        self.apply("--write")
        makefile = (self.root / "Makefile").read_text(encoding="utf-8")
        self.assertIn('"!pnpm-lock.yaml"', makefile)
        self.assertIn('"!package-lock.json"', makefile)
        self.assertIn('"!yarn.lock"', makefile)

    def test_AGENTS_生成后就能直接过_prettier(self):
        """标题后缺空行会让全新的 make check 在自家生成的文件上就报错（实测）。"""
        self.python_project()
        self.apply("--write")
        text = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        for heading in ("## 常用命令", "## 结构", "## 工具检查不到的约定"):
            self.assertIn(f"{heading}\n\n", text)

    def test_有tests但没有pytest时说清原因(self):
        self.python_project()
        (self.root / "tests").mkdir()
        self.apply("--write")
        makefile = (self.root / "Makefile").read_text(encoding="utf-8")
        self.assertIn("tests/ 存在，但未声明 pytest", makefile)
        self.assertNotIn("没有可执行的测试", makefile)

    def test_没有lock时CI不传_frozen_也不开缓存(self):
        self.python_project()
        self.write("web/package.json", '{"name": "web", "scripts": {"test": "vitest"}}\n')
        self.init_repo(github=True)
        self.apply("--write", "--with-ci")
        ci = (self.root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("- run: uv sync\n", ci)
        self.assertNotIn("--frozen", ci)
        self.assertNotIn("cache: pnpm", ci)
        self.assertIn("pnpm -C web install\n", ci)

    def test_有lock时CI按lock收紧(self):
        self.python_project()
        self.write("uv.lock", "")
        self.write("web/package.json", '{"name": "web", "packageManager": "pnpm@9.12.0"}\n')
        self.write("web/pnpm-lock.yaml", "")
        self.init_repo(github=True)
        self.apply("--write", "--with-ci")
        ci = (self.root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("uv sync --frozen", ci)
        self.assertIn('version: "9.12.0"', ci)
        self.assertIn("cache-dependency-path: web/pnpm-lock.yaml", ci)
        self.assertIn("pnpm -C web install --frozen-lockfile", ci)


class TestHook(Fixture):
    def settings(self) -> dict:
        path = self.root / ".claude" / "settings.local.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_安装幂等且不动其他钩子(self):
        self.write(".claude/settings.local.json", json.dumps({
            "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo hi"}]}],
                      "PreToolUse": [{"hooks": [{"type": "command", "command": "echo pre"}]}]},
        }, ensure_ascii=False))
        self.assertEqual(0, run("hook.py", "install", "--root", str(self.root)).returncode)
        self.assertEqual(0, run("hook.py", "install", "--root", str(self.root)).returncode)
        hooks = self.settings()["hooks"]
        self.assertEqual(2, len(hooks["SessionStart"]), "重复安装不能叠加")
        self.assertEqual("echo hi", hooks["SessionStart"][0]["hooks"][0]["command"])
        self.assertIn("PreToolUse", hooks)
        marked = [group for group in hooks["SessionStart"]
                  if "repo-baseline" in group["hooks"][0]["command"]]
        self.assertEqual(1, len(marked))

    def test_卸载只删自己的条目(self):
        self.write(".claude/settings.local.json", json.dumps({
            "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo hi"}]}]},
        }, ensure_ascii=False))
        run("hook.py", "install", "--root", str(self.root))
        self.assertEqual(0, run("hook.py", "remove", "--root", str(self.root)).returncode)
        groups = self.settings()["hooks"]["SessionStart"]
        self.assertEqual(["echo hi"], [g["hooks"][0]["command"] for g in groups])

    def test_设置文件解析失败时停止且不覆盖(self):
        broken = '{"hooks": '
        self.write(".claude/settings.local.json", broken)
        result = run("hook.py", "install", "--root", str(self.root))
        self.assertEqual(1, result.returncode)
        self.assertEqual(broken, (self.root / ".claude" / "settings.local.json")
                         .read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
