"""`check_leakage.py` 与 `preflight.py` 的边界值测试。

按项目定的停止判据：**元工具只需要边界值测试**，不要求"验证测试本身对不对"。

这两个脚本原本**一个测试都没有** —— 而 `check_pointers.py` 刚被证明
"假阴性比没有检查更糟"（只扫含「见」的句子，别的写法的悬空引用完全看不见）。
所以同一条理由适用于这里：它们是报告事实的来源，而**来源本身没人查**过。
"""
import contextlib
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))   # 仓库根


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
            tests = os.path.join(path, "tests")
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

    def test_count_tests_reads_the_real_number(self):
        path = self._skill("with-tests", test_methods=3)
        self.assertEqual(3, PRE._count_tests(path, self.dir))

    def test_skill_without_tests_counts_zero(self):
        path = self._skill("no-tests")
        self.assertEqual(0, PRE._count_tests(path, self.dir))

    def test_skill_facts_reports_every_skill(self):
        self._skill("aaa", test_methods=1)
        self._skill("bbb")
        names = [f["skill"] for f in PRE.skill_facts(self.dir)]
        self.assertEqual(["aaa", "bbb"], names, "技能要按名字排序，缺一个都不行")

    def test_hook_steps_are_read_from_the_actual_hook(self):
        """hook 步骤数是从 `.githooks/pre-commit` 读出来的，不是写死在报告里。"""
        steps = PRE.hook_steps(ROOT)
        self.assertGreaterEqual(len(steps), 4, f"读到的步骤：{steps}")
        self.assertTrue(all(s[0].isdigit() for s in steps),
                        f"步骤应以序号开头：{steps}")


if __name__ == "__main__":
    unittest.main()
