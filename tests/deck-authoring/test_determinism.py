#!/usr/bin/env python3
"""render.py / check.py 的确定性测试：同 spec + 同种子 → 逐字节一致。

## 为什么这条是不变量

错位量与颗粒强度按 `(seed, 元素)` 派生，不用全局 random。若换成全局 random，
两次渲染就「看起来差不多但不完全一样」—— 无法回归对比，也无法复现一版给别人。
症状就是这条测试变红：同种子两次产物不同。

反向也测：改 seed 必须改变产物 —— 否则派生函数根本没用到 seed（另一种退化）。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/deck-authoring/test_determinism.py
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")
TOKENS = os.path.join(SKILL, "styles", "risograph", "style.json")
DEMO = os.path.join(SKILL, "dev-tools", "demo.spec.json")


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


render = _load("_deck_test_render", os.path.join(SCRIPTS, "render.py"))
check = _load("_deck_test_check", os.path.join(SCRIPTS, "check.py"))


class TestDeterminism(unittest.TestCase):
    def setUp(self) -> None:
        with open(TOKENS, encoding="utf-8") as fh:
            self.tokens = json.load(fh)
        with open(DEMO, encoding="utf-8") as fh:
            self.spec = json.load(fh)

    def _render(self, spec: dict) -> str:
        return render.render(spec, self.tokens)

    def test_same_spec_same_seed_is_byte_identical(self) -> None:
        """同 spec + 同种子两次渲染必须逐字节一致。"""
        first, second = self._render(self.spec), self._render(self.spec)
        self.assertEqual(first, second,
                         "同种子两次渲染不一致 —— 派生函数里混进了全局 random")

    def test_different_seed_changes_output(self) -> None:
        """改 seed 必须改变产物 —— 否则 seed 没被真正使用。"""
        other = copy.deepcopy(self.spec)
        other["deck"]["seed"] = other["deck"].get("seed", 1) + 1
        self.assertNotEqual(self._render(self.spec), self._render(other),
                            "改 seed 后产物没变 —— 派生函数没用到 seed")

    def test_check_result_is_idempotent_on_same_product(self) -> None:
        """同一份产物跑两次 check，判定必须一致。"""
        with tempfile.TemporaryDirectory() as td:
            html = os.path.join(td, "out.html")
            with open(html, "w", encoding="utf-8") as fh:
                fh.write(self._render(self.spec))
            first = check.check(self.spec, html, self.tokens)
            second = check.check(self.spec, html, self.tokens)
            self.assertEqual(first, second, "check.py 对同一产物两次判定不同")

    def test_clean_product_passes_all_checks(self) -> None:
        """demo spec 的产物必须过全部校验 —— 别的用例的 baseline。"""
        with tempfile.TemporaryDirectory() as td:
            html = os.path.join(td, "out.html")
            with open(html, "w", encoding="utf-8") as fh:
                fh.write(self._render(self.spec))
            problems = check.check(self.spec, html, self.tokens)
            self.assertEqual(problems, [], f"demo 产物本应干干净净：{problems}")


if __name__ == "__main__":
    unittest.main()
