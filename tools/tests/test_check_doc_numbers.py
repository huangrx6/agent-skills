#!/usr/bin/env python3
"""`tools/check_doc_numbers.py` 的回归测试。

它守的是「文档里写的测试条数不能过期」—— 这类错在本仓库出现过四次，而它**只能**
在「认对了地方」时才有用：

- 认宽了（随便哪个 `N 条` 都拿来比）→ 拿「470 条接口」「8 条 eval」去和 166 比，
  全是误报，人就会开始无视这个检查
- 认窄了（比如只认 README、不认 SKILL.md）→ 漏掉一半位置
- 一条都不认 → 静默通过，等于没写

所以下面既测「该报的报」，也测「不该报的不报」。
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
SCRIPT = os.path.join(TOOLS, "check_doc_numbers.py")


def _load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


check = _load(SCRIPT, "_test_check_doc_numbers")

README = """# 演示

## 验证

```sh
python3 -m unittest discover -s tests -v     # 166 条：全绿
```

本 skill 覆盖 470 条接口表，另有 8 条 eval 与 9 条问题清单。
"""


class Case(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = self._tmp.name

    def write(self, name: str, content: str) -> None:
        with open(os.path.join(self.dir, name), "w", encoding="utf-8") as fh:
            fh.write(content)


class ClaimsTest(Case):
    def test_只认测试命令那一行上的数字(self):
        self.write("README.md", README)
        found = check.claims(self.dir)
        self.assertEqual([("README.md", 6, "166")], found,
                         "470 条接口 / 8 条 eval 都不是测试条数，不能被认进来")

    def test_别的行上的数字不算(self):
        self.write("README.md", "本 skill 有 470 条接口，跑了 12 条边界测试。\n")
        self.assertEqual([], check.claims(self.dir))

    def test_SKILL_md_里的也要看(self):
        self.write("SKILL.md", "python3 -m unittest discover -s tests   # 19 条\n")
        self.assertEqual([("SKILL.md", 1, "19")], check.claims(self.dir))

    def test_大小写不敏感(self):
        self.write("README.md", "python3 -m UNITTEST discover -s tests   # 3 条\n")
        self.assertEqual(1, len(check.claims(self.dir)))

    def test_没有文档时返回空(self):
        self.assertEqual([], check.claims(self.dir))

    def test_多行声称都能找到(self):
        self.write("README.md", "python3 -m unittest discover -s tests  # 10 条\n"
                                 "python3 -m unittest discover -s tests  # 10 条\n")
        self.assertEqual(2, len(check.claims(self.dir)))


class CheckTest(Case):
    def test_对得上就没有问题(self):
        self.write("README.md", README)
        self.assertEqual([], check.check(self.dir, 166))

    def test_对不上就报出文件与行号(self):
        self.write("README.md", README)
        bad = check.check(self.dir, 170)
        self.assertEqual([("README.md", 6, "166", 170)], bad)

    def test_多处声称要逐个比(self):
        self.write("README.md", "python3 -m unittest discover -s tests  # 166 条\n"
                                 "python3 -m unittest discover -s tests  # 139 条\n")
        bad = check.check(self.dir, 166)
        self.assertEqual(1, len(bad))
        self.assertEqual("139", bad[0][2])


class MainTest(Case):
    def test_一致时退出码_0(self):
        self.write("README.md", README)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = check.main([self.dir, "--actual", "166"])
        self.assertEqual(0, code)
        self.assertIn("一致", buf.getvalue())

    def test_不一致时退出码_1并给改法(self):
        self.write("README.md", README)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = check.main([self.dir, "--actual", "999"])
        self.assertEqual(1, code)
        self.assertIn("166", err.getvalue())
        self.assertIn("改法", err.getvalue())

    def test_没有声称时静默通过(self):
        self.write("README.md", "# 没有任何数字\n")
        code = check.main([self.dir, "--actual", "5"])
        self.assertEqual(0, code)

    def test_list_只看声称(self):
        self.write("README.md", README)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = check.main([self.dir, "--list"])
        self.assertEqual(0, code)
        self.assertIn("声称 166 条", buf.getvalue())

    def test_缺_actual_时退_2(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = check.main([self.dir])
        self.assertEqual(2, code)

    def test_目录读不到时退_2(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = check.main([os.path.join(self.dir, "没有这个目录"), "--actual", "1"])
        self.assertEqual(2, code)


if __name__ == "__main__":
    unittest.main(verbosity=2)
