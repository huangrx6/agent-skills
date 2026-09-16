#!/usr/bin/env python3
"""固定基准（§53/§54）的回归测试：指标结构、实测口径、回归判定。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/deck-authoring/test_benchmark.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")
DEV = os.path.join(SKILL, "dev-tools")


def _load(name: str):
    key = f"_deck_test_{name}"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, os.path.join(SCRIPTS, f"{name}.py"))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


benchmark = _load("benchmark")
validate = _load("validate_spec")
deckio = _load("deckio")


class TestFixtureSet(unittest.TestCase):
    """§53 基线集：每份 fixture 必须先过规格门（基线不合法 = 测了个寂寞）。"""

    def test_all_fixtures_validate_green(self) -> None:
        for name in benchmark.FIXTURES:
            with self.subTest(fixture=name):
                spec = deckio.read_json(os.path.join(DEV, f"{name}.spec.json"))
                issues = validate.validate(spec)
                self.assertEqual(issues.errors, [],
                                 f"{name} 基线规格就有错：{issues.errors}")

    def test_fixture_set_is_fixed(self) -> None:
        """基线集是**固定**的 —— 增删 fixture 都该是有意识的提交，不是漂移。"""
        self.assertEqual(benchmark.FIXTURES, ("demo", "stress", "chart-intents"))


class TestWriteJsonRoundTrip(unittest.TestCase):
    def test_round_trip_keeps_unicode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.json")
            data = {"名": "中文", "n": 3, "nested": {"a": [1, 2]}}
            deckio.write_json(path, data)
            with open(path, encoding="utf-8") as fh:
                raw = fh.read()
            self.assertIn("中文", raw, "中文被转义了 —— 产物不可读")
            self.assertEqual(deckio.read_json(path), data)


class TestRunFixture(unittest.TestCase):
    """实测口径：一份 fixture 的指标结构 + 确定性（真浏览器，慢但只有一份）。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        cls.metrics = benchmark.run_fixture("chart-intents", cls._tmp.name)

    def test_metric_shape(self) -> None:
        for key in ("pages", "render_ms", "reproducible", "deterministic",
                    "check_problems", "script_errors", "focal_issues",
                    "budget_issues", "unique_kinds", "max_consecutive_same_kind",
                    "densities"):
            self.assertIn(key, self.metrics)
        self.assertEqual(self.metrics["pages"], 6)
        self.assertTrue(self.metrics["densities"], "密度没量到")

    def test_baseline_quality(self) -> None:
        """基线自身必须是干净的：0 问题、0 脚本错、双确定性。"""
        self.assertEqual(self.metrics["check_problems"], 0)
        self.assertEqual(self.metrics["script_errors"], 0)
        self.assertTrue(self.metrics["reproducible"], "渲两次不逐字节相同")
        self.assertTrue(self.metrics["deterministic"], "编两次不相等")


class TestCompare(unittest.TestCase):
    """回归判定：计数类指标变多 = 回归（退出 1）；变好不算回归。"""

    BASE = {"fixtures": {"demo": {"check_problems": 0, "script_errors": 0,
                                  "focal_issues": 1, "budget_issues": 0,
                                  "max_consecutive_same_kind": 2,
                                  "render_ms": 1000}}}

    def test_regression_detected(self) -> None:
        worse = {"fixtures": {"demo": {**self.BASE["fixtures"]["demo"],
                                       "check_problems": 2, "render_ms": 999}}}
        self.assertEqual(benchmark.compare(self.BASE, worse), 1)

    def test_improvement_is_not_regression(self) -> None:
        better = {"fixtures": {"demo": {**self.BASE["fixtures"]["demo"],
                                        "focal_issues": 0, "render_ms": 5000}}}
        self.assertEqual(benchmark.compare(self.BASE, better), 0)

    def test_new_fixture_is_not_regression(self) -> None:
        added = {"fixtures": {**self.BASE["fixtures"],
                              "chart-intents": {"check_problems": 9}}}
        self.assertEqual(benchmark.compare(self.BASE, added), 0)


if __name__ == "__main__":
    unittest.main()
