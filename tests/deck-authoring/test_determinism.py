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
# 测试自有夹具：风格与内容样本都放在 tests/ 下，**不随 skill 发布** ——
# 可拷贝的模板必然变成默认答案（每份 deck 长得一样）。
FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
# 夹具当"额外风格根"：工具链不内置任何风格（可拷贝的模板必然变成
# 默认答案）。脚本各持一份模块副本，所以走环境变量而不是改常量。
os.environ.setdefault("DECK_STYLES",
                      os.path.join(FIXTURES_DIR, "styles"))
os.environ.setdefault("DECK_BRANDS",
                      os.path.join(FIXTURES_DIR, "brands"))

# 夹具第一套风格（tests/fixtures/styles 下；风格不再有内置解析根）
FIXTURE_STYLE = os.path.join(FIXTURES_DIR, "styles", "swiss-grid")
SCRIPTS = os.path.join(SKILL, "scripts")
TOKENS = os.path.join(FIXTURES_DIR, "styles", "swiss-grid", "style.json")
DEMO = os.path.join(FIXTURES_DIR, "demo.spec.json")


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
        with open(DEMO, encoding="utf-8") as fh:
            self.spec = json.load(fh)
        self.style = render.load_style(FIXTURE_STYLE)      # {"name", "tokens", "skin"}
        with open(DEMO, encoding="utf-8") as fh:
            self.spec = json.load(fh)

    def _render(self, spec: dict) -> str:
        return render.render(spec)

    def test_same_spec_same_seed_is_byte_identical(self) -> None:
        """同 spec + 同种子两次渲染必须逐字节一致。"""
        first, second = self._render(self.spec), self._render(self.spec)
        self.assertEqual(first, second,
                         "同种子两次渲染不一致 —— 派生函数里混进了全局 random")

    def test_different_seed_changes_output_for_a_random_style(self) -> None:
        """改 seed 必须改变产物 —— 但**仅限真的带随机性的风格**。

        ⚠️ 这条原本是拿默认风格测的，而在默认风格从叠印那套换成瑞士栅格之后
        它挂了 —— 因为瑞士栅格的 `misregistration` 与 `grainOpacity` 都是 [0,0]，
        它就是一个**确定性风格**，seed 对它本就无事可做。

        那不是 bug，是断言的前提错了：seed 的作用范围就是“声明了随机区间的风格”。
        所以要测的是**机制还活着**，而不是“每个风格都必须抖”—— 明确给一份
        带非零区间的 token 去驱它。
        """
        style = dict(render.load_style(FIXTURE_STYLE), tokens=copy.deepcopy(self.style["tokens"]))
        style["tokens"]["misregistration"]["offsetRangeX"] = [3, 7]
        style["tokens"]["misregistration"]["offsetRangeY"] = [3, 7]
        style["tokens"]["texture"]["grainOpacity"] = [0.08, 0.15]
        first = render.render(self.spec, style)
        other = copy.deepcopy(self.spec)
        other["deck"]["seed"] = other["deck"].get("seed", 1) + 1
        self.assertNotEqual(first, render.render(other, style),
                            "给了非零随机区间、只改 seed，产物却没变 —— 派生函数没用到 seed")

    def test_check_result_is_idempotent_on_same_product(self) -> None:
        """同一份产物跑两次 check，判定必须一致。"""
        with tempfile.TemporaryDirectory() as td:
            html = os.path.join(td, "out.html")
            with open(html, "w", encoding="utf-8") as fh:
                fh.write(self._render(self.spec))
            first = check.check(self.spec, html)
            second = check.check(self.spec, html)
            self.assertEqual(first, second, "check.py 对同一产物两次判定不同")

    def test_clean_product_passes_all_checks(self) -> None:
        """demo spec 的产物必须过全部校验 —— 别的用例的 baseline。

        产物旁边要放上 `sample-treated.png`：demo 的图文页引用了它，
        不放就是真·裂图，而“图片没加载”那条检查会（正确地）报出来。
        要的是一个真的干净产物，不是把检查关掉。
        """
        from PIL import Image
        with tempfile.TemporaryDirectory() as td:
            html = os.path.join(td, "out.html")
            with open(html, "w", encoding="utf-8") as fh:
                fh.write(self._render(self.spec))
            Image.new("RGB", (2, 2), (245, 239, 221)).save(
                os.path.join(td, "sample-treated.png"))
            problems = check.check(self.spec, html)
            self.assertEqual(problems, [], f"demo 产物本应干干净净：{problems}")


if __name__ == "__main__":
    unittest.main()
