#!/usr/bin/env python3
"""guide.py 场景路由的回归：打分确定、同分不硬选、无信号不出推荐。"""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills",
                       os.path.basename(HERE), "scripts")


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


G = _load("guide", os.path.join(SCRIPTS, "guide.py"))


class TestGuide(unittest.TestCase):

    def test_flow_wins_for_workflow_text(self):
        rec = G.recommend("审批通过后部署，失败则回滚重试")
        self.assertEqual("flow", rec["recommended"])
        self.assertEqual("TB", rec["direction"])

    def test_dependency_wins_for_import_text(self):
        self.assertEqual("dependency", G.recommend("模块之间的 import 依赖关系")["recommended"])

    def test_state_wins_for_lifecycle_text(self):
        self.assertEqual("state", G.recommend("订单生命周期里的状态转移与终态")["recommended"])

    def test_no_signal_recommends_nothing(self):
        rec = G.recommend("zzz qqq")
        self.assertIsNone(rec["recommended"])

    def test_scoring_is_deterministic(self):
        self.assertEqual(G.score("画个状态机"), G.score("画个状态机"))


if __name__ == "__main__":
    unittest.main()
