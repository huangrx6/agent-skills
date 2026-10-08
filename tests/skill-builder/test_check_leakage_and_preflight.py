"""名称泄露检查与 preflight 快照的回归测试。"""
import contextlib
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
# 测试住在仓库顶层 `tests/<skill>/`（**刻意不在 skill 目录里**：AI 调用 skill 时读的是
# `skills/<skill>/` 那棵树，测试放在里面会被顺手读进去）。
# 所以从 `tests/<skill>/` 往上两级到仓库根，再进 `skills/<skill>/`。
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")
ROOT = os.path.dirname(os.path.dirname(HERE))   # 仓库根


def _load(name, filename):
    path = os.path.join(SCRIPTS, filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


LEAK = _load("check_leakage", "check_leakage.py")
PRE = _load("preflight", "preflight.py")


class TestBlocklistBoundaries(unittest.TestCase):
    """blocklist 是**仓库外**的配置（设计如此：词条本身不能进仓库）。"""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="leak-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _blocklist(self, text):
        path = os.path.join(self.dir, "blocklist.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def test_comments_and_blank_lines_are_not_terms(self):
        terms, _source = LEAK.load_blocklist(
            self._blocklist("# 这是注释\n\n某公司\n  \n# 又一条注释\n某系统\n"))
        self.assertEqual(["某公司", "某系统"], terms)

    def test_missing_blocklist_is_not_an_error(self):
        """没配 blocklist 不是错误 —— 它本来就不该进仓库，新克隆的仓库必然没有。"""
        terms, source = LEAK.load_blocklist(os.path.join(self.dir, "nope.txt"))
        self.assertEqual([], terms)
        self.assertEqual("未配置", source)

    def test_scan_reports_line_numbers(self):
        target = os.path.join(self.dir, "doc.md")
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("第一行\n第二行有 某公司 在里面\n第三行\n")
        hits = LEAK.scan_worktree([target], ["某公司"])
        self.assertEqual(1, len(hits))
        self.assertEqual(2, hits[0]["line"], "行号错了，人就找不到那句在哪儿")

    def test_scan_with_no_terms_is_clean(self):
        target = os.path.join(self.dir, "doc.md")
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("随便写点东西\n")
        self.assertEqual([], LEAK.scan_worktree([target], []))

    def test_dot_dirs_are_skipped(self):
        """`.git` 这种目录要跳过 —— 否则历史里的旧名字会被当成工作区命中。"""
        hidden = os.path.join(self.dir, ".git")
        os.makedirs(hidden)
        with open(os.path.join(hidden, "doc.md"), "w", encoding="utf-8") as fh:
            fh.write("某公司\n")
        self.assertEqual([], LEAK.scan_worktree([self.dir], ["某公司"]))
        # 同一个词放在正常目录里必须命中，否则上一条就成了"什么都没扫"
        with open(os.path.join(self.dir, "doc.md"), "w", encoding="utf-8") as fh:
            fh.write("某公司\n")
        self.assertEqual(1, len(LEAK.scan_worktree([self.dir], ["某公司"])))

    def test_main_exit_code_follows_hits(self):
        target = os.path.join(self.dir, "doc.md")
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("干净的一行\n")
        blocklist = self._blocklist("某公司\n")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, LEAK.main([target, "--blocklist", blocklist]))
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("某公司 出现了\n")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(1, LEAK.main([target, "--blocklist", blocklist]))


class TestPreflightBoundaries(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="pre-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _skill(self, name, test_methods=0):
        path = os.path.join(self.dir, "skills", name)
        os.makedirs(path)
        with open(os.path.join(path, "SKILL.md"), "w", encoding="utf-8") as fh:
            fh.write("---\nname: x\ndescription: y\n---\n\n# 标题\n")
        if test_methods:
            tests = os.path.join(self.dir, "tests", name)
            os.makedirs(tests)
            body = "import unittest\n\n\nclass T(unittest.TestCase):\n"
            for i in range(test_methods):
                body += f"    def test_{i}(self):\n        pass\n\n\n"
            body += 'if __name__ == "__main__":\n    unittest.main()\n'
            with open(os.path.join(tests, "test_x.py"), "w", encoding="utf-8") as fh:
                fh.write(body)
        return path

    def test_find_root_walks_up_to_the_repo(self):
        nested = os.path.join(self.dir, "skills", "demo", "references")
        os.makedirs(nested)
        self.assertEqual(self.dir, PRE.find_root(nested))

    def test_find_root_returns_none_outside_a_repo(self):
        """临时目录往上找不到 skills/ 时要返回 None，而不是一路走到根目录乱认。"""
        self.assertIsNone(PRE.find_root(self.dir))

    def test_counts_test_files_without_running_or_importing_them(self):
        path = self._skill("with-tests", test_methods=3)
        marker = os.path.join(self.dir, "tests", "with-tests", "test_crash.py")
        with open(marker, "w", encoding="utf-8") as fh:
            fh.write("raise SystemExit('must not execute')\n")
        with mock.patch.object(PRE, "_run", side_effect=AssertionError("no execution")):
            facts = PRE.skill_facts(self.dir)
        self.assertEqual(2, facts[0]["test_files"])
        self.assertNotIn("tests", facts[0])

    def test_skill_without_tests_counts_zero(self):
        path = self._skill("no-tests")
        self.assertEqual(0, PRE._count_test_files(path, self.dir))

    def test_skill_facts_reports_every_skill(self):
        self._skill("aaa", test_methods=1)
        self._skill("bbb")
        names = [f["skill"] for f in PRE.skill_facts(self.dir)]
        self.assertEqual(["aaa", "bbb"], names, "技能要按名字排序，缺一个都不行")

    def test_snapshot_survives_invalid_frontmatter_types(self):
        self._skill("bad-fm")
        for data in (None, 42, [], {"description": 42}):
            with self.subTest(data=data), mock.patch.object(PRE._vs, "load_yaml", return_value=(data, None)):
                fact = PRE.skill_facts(self.dir)[0]
                self.assertEqual(0, fact["description_chars"])

    def test_snapshot_shares_validator_body_limit(self):
        path = self._skill("within-limit")
        with open(os.path.join(path, "SKILL.md"), "a", encoding="utf-8") as fh:
            fh.write("text\n" * 180)
        fact = PRE.skill_facts(self.dir)[0]
        self.assertEqual(PRE._vs.MAX_BODY_LINES, PRE.MAX_BODY_LINES)
        self.assertFalse(fact["over_limit"])
        self.assertEqual(PRE._vs.MAX_BODY_LINES - fact["body_lines"], fact["headroom"])

    def test_hook_steps_allow_adjacent_closing_separator(self):
        os.makedirs(os.path.join(self.dir, ".githooks"))
        with open(os.path.join(self.dir, ".githooks", "pre-commit"), "w") as fh:
            fh.write("# ── 1. Check ──\n# ── 2. Advisory（only）──\n")
        self.assertEqual(["1. Check", "2. Advisory（only）"], PRE.hook_steps(self.dir))

    def test_undocumented_helper_is_advisory_and_snapshot_is_not_a_test_run(self):
        path = self._skill("demo")
        os.makedirs(os.path.join(path, "scripts"))
        with open(os.path.join(path, "scripts", "internal.py"), "w") as fh:
            fh.write("# loaded by another module\n")
        output = io.StringIO()
        with mock.patch.object(PRE, "find_root", return_value=self.dir), \
                mock.patch.object(PRE, "install_drift", return_value=(True, "fixture")), \
                contextlib.redirect_stdout(output):
            code = PRE.main(["--snapshot-only", "--json"])
        import json
        payload = json.loads(output.getvalue())
        self.assertEqual(0, code)
        self.assertFalse(payload["tests_run"])
        self.assertNotIn("total_tests", payload)
        self.assertEqual([["demo", "internal.py"]], payload["orphan_scripts"])


if __name__ == "__main__":
    unittest.main()
