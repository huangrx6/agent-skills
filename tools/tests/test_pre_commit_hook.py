#!/usr/bin/env python3
"""`.githooks/pre-commit` 第 5 段（仓库体检）的回归测试。

为什么只测这一段
----------------
前四段（结构 / 泄露 / 回归测试 / 指针）是**阻塞**的，它们的行为已经由各自的脚本测试
覆盖；这里要守的是一个**很容易在重构里被改错、而改错后不会有人立刻发现**的性质：

> 体检**只提示，不阻塞**。

一旦它变成阻塞，人会开始用 `--no-verify` 跳过整个 hook —— 而那意味着前面四道真的
防线也一起失效了。所以「体检报出内容时，提交仍然成功」这件事必须有测试。

测试在临时 git 仓库里跑，不碰真仓库。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
import json

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
REPO = os.path.dirname(TOOLS)
HOOK = os.path.join(REPO, ".githooks", "pre-commit")
HEALTH_OK = (
    "#!/usr/bin/env python3\n"
    "print('仓库体检  /x')\n"
    "print('')\n"
    "print('值得看的（只报告，不判失败）：')\n"
    "print('  · 缺 README.md（2）：aaa、bbb')\n"
    "raise SystemExit(0)\n"
)
HEALTH_CRASH = (
    "#!/usr/bin/env python3\n"
    "print('值得看的')\n"
    "raise SystemExit(3)\n"
)


class HookCase(unittest.TestCase):
    def setUp(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("没有 git")
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self._git("init", "-q")
        hooks = os.path.join(self.root, ".githooks")
        os.makedirs(hooks)
        shutil.copy(HOOK, os.path.join(hooks, "pre-commit"))
        self.hook = os.path.join(hooks, "pre-commit")
        # 文档数字检查与锁文件同步都是 hook 的一环，得把真脚本一并拷进假仓库
        os.makedirs(os.path.join(self.root, "tools"), exist_ok=True)
        for name in ("check_doc_numbers.py", "skills_lock.py"):
            shutil.copy(os.path.join(TOOLS, name), os.path.join(self.root, "tools", name))

    def _git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True)

    def write(self, rel: str, content: str, stage: bool = True) -> None:
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        if stage:
            self._git("add", rel)

    def run_hook(self) -> subprocess.CompletedProcess:
        return subprocess.run(["sh", self.hook], cwd=self.root, capture_output=True, text=True)

    def test_文档里的测试条数过期要挡住提交(self):
        """这一类错在本仓库出现过四次；真实条数在跑完测试时就在手上，比一下不要钱。"""
        self.write("skills/foo/tests/test_one.py",
                   "import unittest\n\nclass T(unittest.TestCase):\n"
                   "    def test_ok(self):\n        self.assertTrue(True)\n")
        self.write("skills/foo/README.md",
                   "```sh\npython3 -m unittest discover -s tests   # 99 条\n```\n")
        result = self.run_hook()
        self.assertEqual(1, result.returncode, "写错了数字就该挡住")
        self.assertIn("99", result.stdout + result.stderr)
        self.assertIn("1 条", result.stdout + result.stderr, "要给实际值")

    def test_文档里的测试条数对得上就放过(self):
        self.write("skills/foo/tests/test_one.py",
                   "import unittest\n\nclass T(unittest.TestCase):\n"
                   "    def test_ok(self):\n        self.assertTrue(True)\n")
        self.write("skills/foo/README.md",
                   "```sh\npython3 -m unittest discover -s tests   # 1 条\n```\n")
        result = self.run_hook()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_文档里没有数字就不管(self):
        self.write("skills/foo/tests/test_one.py",
                   "import unittest\n\nclass T(unittest.TestCase):\n"
                   "    def test_ok(self):\n        self.assertTrue(True)\n")
        self.write("skills/foo/README.md", "# foo\n\n只写「全绿」，不写数字。\n")
        result = self.run_hook()
        self.assertEqual(0, result.returncode)

    def test_锁文件漂了会自动更新并重新暂存(self):
        """派生文件：不阻塞提交，而是自动修 —— 阻塞会把人逼到 --no-verify。"""
        self.write("skills/foo/SKILL.md", "---\nname: foo\n---\n正文\n")
        self.write("skills-lock.json", '{"version": 1, "skills": {}}')
        result = self.run_hook()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("已自动更新 skills-lock.json", result.stdout)
        # 已经重新暂存进 index（不出现在“未暂存”里）
        staged = self._git("diff", "--cached", "--name-only").stdout
        self.assertIn("skills-lock.json", staged)
        with open(os.path.join(self.root, "skills-lock.json"), encoding="utf-8") as fh:
            payload = json.load(fh)
        self.assertIn("foo", payload["skills"])

    def test_锁文件本来就对时不插话(self):
        self.write("skills/foo/SKILL.md", "---\nname: foo\n---\n正文\n")
        self.run_hook()          # 第一遍会生成并同步（夹具里本来没有锁文件）
        result = self.run_hook()  # 第二遍已经一致 → 不该再插话
        self.assertEqual(0, result.returncode)
        self.assertNotIn("已自动更新", result.stdout)

    def test_体检提示出现但提交不被挡(self):
        self.write("tools/skill_health.py", HEALTH_OK, stage=False)
        self.write("skills/some/SKILL.md", "---\nname: some\n---\n")
        result = self.run_hook()
        self.assertEqual(0, result.returncode, "体检只提示，不许挡提交")
        self.assertIn("缺 README.md", result.stdout, "提示要真的打出来")
        self.assertIn("不阻塞提交", result.stdout, "要写清它不挡")
        self.assertIn("pre-commit: 结构、泄露、指针、回归测试与文档数字通过", result.stdout)

    def test_体检脚本自己崩了也不许挡(self):
        """它是个报告工具 —— 崩了也不该把一次正常提交卡住。"""
        self.write("tools/skill_health.py", HEALTH_CRASH, stage=False)
        self.write("skills/some/SKILL.md", "---\nname: some\n---\n")
        result = self.run_hook()
        self.assertEqual(0, result.returncode)

    def test_没有体检脚本时也不出错(self):
        self.write("skills/some/SKILL.md", "---\nname: some\n---\n")
        result = self.run_hook()
        self.assertEqual(0, result.returncode)
        self.assertIn("通过", result.stdout)

    def test_不触及_skills_或_tools_时直接放过(self):
        self.write("README.md", "只改文档\n")
        result = self.run_hook()
        self.assertEqual(0, result.returncode)
        self.assertNotIn("体检提示", result.stdout, "没改 skills/tools 就不跑体检")


if __name__ == "__main__":
    unittest.main(verbosity=2)
