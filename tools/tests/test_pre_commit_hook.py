#!/usr/bin/env python3
"""在临时仓库验证 hook 的触发、阻塞/提示区别和暂存区锁同步。"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
import json
import hashlib

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
        # hook 可能继承临时 GIT_INDEX_FILE；夹具里的 git 只能操作自己的仓库。
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
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
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True, env=self.env)

    def write(self, rel: str, content: str, stage: bool = True) -> None:
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        if stage:
            self._git("add", rel)

    def run_hook(self, gate="0") -> subprocess.CompletedProcess:
        env = dict(self.env, AGENT_SKILLS_GATE=gate)
        return subprocess.run(["sh", self.hook], cwd=self.root, capture_output=True, text=True, env=env)

    def test_文档里的测试条数过期要挡住提交(self):
        """这一类错在本仓库出现过四次；真实条数在跑完测试时就在手上，比一下不要钱。"""
        self.write("tests/foo/test_one.py",
                   "import unittest\n\nclass T(unittest.TestCase):\n"
                   "    def test_ok(self):\n        self.assertTrue(True)\n")
        self.write("skills/foo/README.md",
                   "```sh\npython3 -m unittest discover -s tests   # 99 条\n```\n")
        result = self.run_hook()
        self.assertEqual(1, result.returncode, "写错了数字就该挡住")
        self.assertIn("99", result.stdout + result.stderr)
        self.assertIn("1 条", result.stdout + result.stderr, "要给实际值")

    def test_文档里的测试条数对得上就放过(self):
        self.write("tests/foo/test_one.py",
                   "import unittest\n\nclass T(unittest.TestCase):\n"
                   "    def test_ok(self):\n        self.assertTrue(True)\n")
        self.write("skills/foo/README.md",
                   "```sh\npython3 -m unittest discover -s tests   # 1 条\n```\n")
        result = self.run_hook()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_文档里没有数字就不管(self):
        self.write("tests/foo/test_one.py",
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
        self.assertEqual("", self._git("diff", "--", "skills-lock.json").stdout)
        self.assertEqual(payload, json.loads(self._git("show", ":skills-lock.json").stdout))

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
        self.assertIn("pre-commit: 已执行的结构、泄露、指针与文档数字检查通过", result.stdout)

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

    def test_tests_only_failure_runs_and_is_advisory_by_default(self):
        self.write("tests/foo/test_fail.py", "import unittest\nclass T(unittest.TestCase):\n    def test_fail(self):\n        self.fail('fixture failure')\n")
        result = self.run_hook()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("1 个目录失败", result.stdout)
        self.assertNotIn("1 个目录通过", result.stdout)
        self.assertIn("fixture failure", result.stderr)

    def test_tests_only_failure_blocks_when_gate_enabled(self):
        self.write("tests/foo/test_fail.py", "import unittest\nclass T(unittest.TestCase):\n    def test_fail(self):\n        self.fail('fixture failure')\n")
        result = self.run_hook(gate="1")
        self.assertEqual(1, result.returncode)
        self.assertIn("提交已中止", result.stdout)

    def test_skip_count_is_reported_separately(self):
        self.write("tests/foo/test_skip.py", "import unittest\nclass T(unittest.TestCase):\n    @unittest.skip('missing optional dependency')\n    def test_skip(self):\n        pass\n")
        result = self.run_hook()
        self.assertEqual(0, result.returncode)
        self.assertIn("跳过 1 条", result.stdout)

    def test_hook_only_change_runs_checks(self):
        with open(HOOK, encoding="utf-8") as handle:
            self.write(".githooks/pre-commit", handle.read())
        result = self.run_hook()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("检查通过", result.stdout)

    def test_lock_uses_staged_skill_and_excludes_unstaged_new_skill(self):
        staged = "---\nname: foo\n---\nstaged body\n"
        self.write("skills/foo/SKILL.md", staged)
        self.write("skills/foo/SKILL.md", staged + "not staged\n", stage=False)
        self.write("skills/bar/SKILL.md", "unstaged new skill", stage=False)
        result = self.run_hook()
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(self._git("show", ":skills-lock.json").stdout)
        self.assertEqual(["foo"], list(payload["skills"]))
        self.assertEqual(hashlib.sha256(staged.encode()).hexdigest(), payload["skills"]["foo"]["computedHash"])
        with open(os.path.join(self.root, "skills/foo/SKILL.md"), encoding="utf-8") as handle:
            self.assertIn("not staged", handle.read())

    def test_current_worktree_lock_does_not_hide_stale_index_lock(self):
        self.write("skills/foo/SKILL.md", "first body")
        self.assertEqual(0, self.run_hook().returncode)
        self.write("skills/foo/SKILL.md", "second body")
        # 模拟维护者先在工作区生成锁，却忘记暂存它。
        subprocess.run(["python3", os.path.join(self.root, "tools/skills_lock.py"),
                        "--root", self.root, "--update"], check=True, capture_output=True, env=self.env)
        with open(os.path.join(self.root, "skills-lock.json"), "rb") as handle:
            before = handle.read()
        result = self.run_hook()
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(self._git("show", ":skills-lock.json").stdout)
        self.assertEqual(hashlib.sha256(b"second body").hexdigest(), payload["skills"]["foo"]["computedHash"])
        with open(os.path.join(self.root, "skills-lock.json"), "rb") as handle:
            self.assertEqual(before, handle.read())

    def test_unstaged_lock_source_type_and_arbitrary_bytes_are_preserved(self):
        for change in ("source", "sourceType", "arbitrary bytes"):
            with self.subTest(change=change):
                self.write("skills/foo/SKILL.md", "first body")
                payload = {"version": 1, "skills": {"foo": {
                    "source": "team/staged", "sourceType": "github",
                    "skillPath": "skills/foo/SKILL.md",
                    "computedHash": hashlib.sha256(b"first body").hexdigest(),
                }}}
                self.write("skills-lock.json", json.dumps(payload))
                if change == "arbitrary bytes":
                    pending = b"unfinished lock edit\r\n\xff\x00"
                else:
                    payload["skills"]["foo"][change] = "pending value"
                    pending = (json.dumps(payload, indent=3) + "\r\n").encode()
                with open(os.path.join(self.root, "skills-lock.json"), "wb") as handle:
                    handle.write(pending)
                self.write("skills/foo/SKILL.md", "second body")

                result = self.run_hook()
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertIn("已按字节保留", result.stdout)
                with open(os.path.join(self.root, "skills-lock.json"), "rb") as handle:
                    self.assertEqual(pending, handle.read())
                staged = json.loads(self._git("show", ":skills-lock.json").stdout)["skills"]["foo"]
                self.assertEqual("team/staged", staged["source"])
                self.assertEqual("github", staged["sourceType"])
                self.assertEqual(hashlib.sha256(b"second body").hexdigest(), staged["computedHash"])

    def test_untracked_lock_content_is_preserved(self):
        self.write("skills/foo/SKILL.md", "body")
        self.write("skills-lock.json", "unfinished local lock", stage=False)
        result = self.run_hook()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        with open(os.path.join(self.root, "skills-lock.json"), "rb") as handle:
            self.assertEqual(b"unfinished local lock", handle.read())
        staged = json.loads(self._git("show", ":skills-lock.json").stdout)
        self.assertEqual(hashlib.sha256(b"body").hexdigest(), staged["skills"]["foo"]["computedHash"])

    def test_missing_worktree_lock_is_recreated_after_index_sync(self):
        self.write("skills/foo/SKILL.md", "first body")
        self.assertEqual(0, self.run_hook().returncode)
        os.unlink(os.path.join(self.root, "skills-lock.json"))
        self.write("skills/foo/SKILL.md", "second body")
        result = self.run_hook()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("", self._git("diff", "--", "skills-lock.json").stdout)
        with open(os.path.join(self.root, "skills-lock.json"), encoding="utf-8") as handle:
            payload = json.load(handle)
        self.assertEqual(hashlib.sha256(b"second body").hexdigest(), payload["skills"]["foo"]["computedHash"])

    def test_failed_index_update_does_not_modify_worktree_lock(self):
        self.write("skills/foo/SKILL.md", "first body")
        self.assertEqual(0, self.run_hook().returncode)
        with open(os.path.join(self.root, "skills-lock.json"), "rb") as handle:
            before = handle.read()
        self.write("skills/foo/SKILL.md", "second body")
        self.write(".git/index.lock", "fixture lock", stage=False)
        result = self.run_hook()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("无法同步", result.stderr)
        with open(os.path.join(self.root, "skills-lock.json"), "rb") as handle:
            self.assertEqual(before, handle.read())
        staged = json.loads(self._git("show", ":skills-lock.json").stdout)
        self.assertEqual(hashlib.sha256(b"first body").hexdigest(), staged["skills"]["foo"]["computedHash"])

    def test_staged_skill_deletion_is_removed_from_lock(self):
        self.write("skills/foo/SKILL.md", "body")
        self.assertEqual(0, self.run_hook().returncode)
        commit = self._git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                           "-c", "commit.gpgsign=false", "commit", "-qm", "fixture")
        self.assertEqual(0, commit.returncode, commit.stderr)
        removed = self._git("rm", "--cached", "skills/foo/SKILL.md")
        self.assertEqual(0, removed.returncode, removed.stderr)
        result = self.run_hook()
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(self._git("show", ":skills-lock.json").stdout)
        self.assertEqual({}, payload["skills"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
