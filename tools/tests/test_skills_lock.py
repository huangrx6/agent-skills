#!/usr/bin/env python3
"""`tools/skills_lock.py` 的回归测试。

它守的是 `skills-lock.json` —— 一个**派生文件**，而它被手工维护过 10 次之后
漂成了「6 个 skill 里 3 个没登记、2 个哈希过期」。判错的后果有两侧：

- 该报不报 → 锁文件又悄悄漂回去，而这次没人会手工发现
- 不该报乱报 → 每次提交都要跟它纠缠，人会开始用 --no-verify（仓库明确担心的失败模式）

所以既测「漂移能报出来」，也测「一致时**不报**」。
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
SCRIPT = os.path.join(TOOLS, "skills_lock.py")


def _load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


lock = _load(SCRIPT, "_test_skills_lock")


class Case(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        os.makedirs(os.path.join(self.root, "skills"))

    def make_skill(self, name: str, body: str = "正文") -> None:
        path = os.path.join(self.root, "skills", name, "SKILL.md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"---\nname: {name}\n---\n{body}\n")

    def write_lock(self, skills: dict) -> None:
        with open(os.path.join(self.root, "skills-lock.json"), "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "skills": skills}, fh, ensure_ascii=False)

    def read_lock(self) -> dict:
        with open(os.path.join(self.root, "skills-lock.json"), encoding="utf-8") as fh:
            return json.load(fh)


class ExpectedTest(Case):
    def test_列出全部_skill_且哈希等于_skill_md_的_sha256(self):
        self.make_skill("aaa")
        self.make_skill("bbb")
        want = lock.expected(self.root)
        self.assertEqual(["aaa", "bbb"], sorted(want))
        self.assertEqual(lock.sha256_of(os.path.join(self.root, "skills/aaa/SKILL.md")),
                         want["aaa"]["computedHash"])
        self.assertEqual("skills/bbb/SKILL.md", want["bbb"]["skillPath"])

    def test_source_继承旧值(self):
        self.make_skill("aaa")
        self.write_lock({"aaa": {"source": "别的来源", "sourceType": "local",
                                 "skillPath": "x", "computedHash": "旧"}})
        want = lock.expected(self.root)
        self.assertEqual("别的来源", want["aaa"]["source"])
        self.assertEqual("local", want["aaa"]["sourceType"])

    def test_没有旧值时用默认(self):
        self.make_skill("aaa")
        want = lock.expected(self.root)
        self.assertEqual("huangrx6/agent-skills", want["aaa"]["source"])
        self.assertEqual("github", want["aaa"]["sourceType"])

    def test_没有_SKILL_md_的目录不算_skill(self):
        os.makedirs(os.path.join(self.root, "skills", "不是skill"))
        self.make_skill("aaa")
        self.assertEqual(["aaa"], sorted(lock.expected(self.root)))


class DiffTest(Case):
    def test_缺登记与哈希过期与多余都能报出来(self):
        self.make_skill("aaa")
        self.make_skill("bbb")
        self.make_skill("ccc")
        self.write_lock({
            "aaa": {"computedHash": lock.sha256_of(os.path.join(self.root, "skills/aaa/SKILL.md"))},
            "bbb": {"computedHash": "早就过期了"},
            "已经删掉的": {"computedHash": "x"},
        })
        report = lock.diff(self.root)
        self.assertEqual(["ccc"], report["缺登记"])
        self.assertEqual(["bbb"], report["哈希过期"])
        self.assertEqual(["已经删掉的"], report["多出来的"])

    def test_一致时三项都空(self):
        self.make_skill("aaa")
        lock.write_lock(self.root, lock.build(self.root))
        self.assertEqual({"缺登记": [], "哈希过期": [], "多出来的": []}, lock.diff(self.root))

    def test_改了正文就算过期(self):
        self.make_skill("aaa", "第一版")
        lock.write_lock(self.root, lock.build(self.root))
        self.make_skill("aaa", "第二版")
        self.assertEqual(["aaa"], lock.diff(self.root)["哈希过期"])


class MainTest(Case):
    def test_check_不一致时退出_1并给改法(self):
        self.make_skill("aaa")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = lock.main(["--root", self.root, "--check"])
        self.assertEqual(1, code)
        self.assertIn("缺登记", err.getvalue())
        self.assertIn("--update", err.getvalue())

    def test_update_之后_check_就过(self):
        self.make_skill("aaa")
        self.make_skill("bbb")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(0, lock.main(["--root", self.root, "--update"]))
        self.assertIn("已按仓库现状重写", buf.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, lock.main(["--root", self.root, "--check"]))
        self.assertEqual(["aaa", "bbb"], sorted(self.read_lock()["skills"]))

    def test_update_幂等(self):
        self.make_skill("aaa")
        with contextlib.redirect_stdout(io.StringIO()):
            lock.main(["--root", self.root, "--update"])
        first = self.read_lock()
        with contextlib.redirect_stdout(io.StringIO()):
            lock.main(["--root", self.root, "--update"])
        self.assertEqual(first, self.read_lock())

    def test_update_不丢掉_source(self):
        self.make_skill("aaa")
        self.write_lock({"aaa": {"source": "保留我", "sourceType": "github",
                                 "skillPath": "x", "computedHash": "旧"}})
        with contextlib.redirect_stdout(io.StringIO()):
            lock.main(["--root", self.root, "--update"])
        self.assertEqual("保留我", self.read_lock()["skills"]["aaa"]["source"])

    def test_json_输出含_diff_与_expected(self):
        self.make_skill("aaa")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = lock.main(["--root", self.root, "--json"])
        self.assertEqual(0, code)
        payload = json.loads(buf.getvalue())
        self.assertEqual(["aaa"], payload["diff"]["缺登记"])
        self.assertIn("aaa", payload["expected"])

    def test_不是仓库根目录时退_2(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = lock.main(["--root", self._tmp.name + "/nope"])
        self.assertEqual(2, code)


if __name__ == "__main__":
    unittest.main(verbosity=2)
