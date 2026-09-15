#!/usr/bin/env python3
"""图片提示词契约（`--brief`）与交付验收（`--check`）的验证。

这一层换了一个分工：**脚本写契约与提示词 → 人出图 → 脚本再验一遍**。
所以要钉的也是这两头：

1. **契约要说得清楚**（文件名 / 尺寸 / 比例 / 透明通道 / 会被怎么处理 / 可粘贴的
   中英提示词），而且**会说错的地方不能有**：同一张图用在多页时要合并而不是列三遍
   （否则人会出三张互相覆盖）；提示词里不能出现"给文字留压字空间"（我们的版式里
   文字在**独立一栏**，不压在图上 —— 第一版就这么写错了）。
2. **验收要有牙，而且不能自己作弊**：`--check` 一旦顺手把占位图造出来，
   就永远验不出"图还没出"（实测踩过：删掉图之后它照样报"符合契约"）。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/deck-authoring/test_image_brief.py
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
STRESS = os.path.join(SKILL, "dev-tools", "stress.spec.json")


def _load(name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, f"{name}.py"))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


image_source = _load("image_source")
deckio = _load("deckio")


class TestBrief(unittest.TestCase):
    """契约内容：该说的都要说到，说错的不能有。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        cls.brief = image_source.build_brief(STRESS, cls._tmp.name)
        cls.md_path = os.path.join(cls._tmp.name, "image-brief.md")
        image_source.write_brief_md(cls.brief, cls.md_path)
        cls.md = deckio.read_text(cls.md_path)

    def test_one_entry_per_filename_not_per_page(self) -> None:
        """同一个文件名用在多页 → **合并成一条**。

        第一版按页列：压测 deck 里 `sample-treated.png` 用在第 11/12/18 页，
        于是契约里出现三遍 —— 人会出三张、互相覆盖（实测）。
        """
        names = [s["file"] for s in self.brief["slots"]]
        self.assertEqual(len(names), len(set(names)), f"有重复文件名：{names}")
        used = [s for s in self.brief["slots"] if len(s["pages"]) > 1]
        self.assertTrue(used, "压测 deck 里本该有跨页复用的图 —— 用例前提变了")
        self.assertGreaterEqual(len(used[0]["pages"]), 2)
        self.assertIn("第 11 页", self.md)

    def test_target_size_is_the_measured_slot_at_2x(self) -> None:
        """尺寸是**实测槽位 × 2**，不是拍一个数：槽位宽是布局定的 640px。"""
        self.assertEqual(self.brief["target_px"][0], 640 * image_source.BRIEF_SCALE)
        self.assertGreater(self.brief["target_px"][1], 0)
        for s in self.brief["slots"]:
            self.assertEqual(s["target_px"], self.brief["target_px"])

    def test_contract_states_every_thing_the_user_listed(self) -> None:
        """用户点名的每一项都要在契约里：名称 / 大小 / 透明度 / 风格 / 内容 / 元素。"""
        for key in ("文件名", "尺寸", "透明通道", "会被制版处理", "内容"):
            with self.subTest(field=key):
                self.assertIn(key, self.md, f"契约里没写「{key}」")

    def test_prompt_carries_both_languages(self) -> None:
        self.assertIn("中文说明", self.md)
        self.assertIn("English prompt", self.md)

    def test_prompt_knows_the_halftone_constraint(self) -> None:
        """提示词必须说清"会被压成两墨 + 半调" —— 这是这条流水线特有的约束。

        不写的话模型会交一张很漂亮、制完版就糊掉的图（细密纹理/细线是主要的坑）。
        """
        for token in ("半调", "两个墨色"):
            self.assertIn(token, self.md)
        self.assertIn("fine mesh", self.md)          # 英文那侧的负面清单

    def test_prompt_does_not_tell_the_model_to_leave_room_for_overlay(self) -> None:
        """**不能**说"给文字留压字空间"：我们的版式里文字是独立一栏，不压在图上。

        第一版写错了：模型会交一张主体偏到一边、空掉半张的图。
        """
        self.assertNotIn("压文字", self.md)
        self.assertNotIn("overlay", self.md)
        self.assertIn("SEPARATE column", self.md)

    def test_subject_is_marked_as_a_draft(self) -> None:
        """内容那一栏是**草稿**：条目往往在讲 deck 的叙事，不是在讲画面里该有什么。

        标不清楚的后果是人直接把草稿丢给模型，然后拿到一张文不对题的图。
        """
        self.assertIn("这是草稿", self.md)
        self.assertIn("REPLACE THIS", self.md)
        self.assertTrue(all(s["subject_is_draft"] for s in self.brief["slots"]))

    def test_style_bibliography_stays_out_of_the_prompt(self) -> None:
        """风格的"参考文献"只给人看，**不进提示词**（对模型是噪音）。"""
        ref = self.brief["reference"]
        self.assertTrue(ref, "这套风格本该有 reference")
        body = self.md.split("**中文说明**")[1] if "**中文说明**" in self.md else ""
        self.assertNotIn(ref, body, "把风格文献塞进提示词了")


class TestCheck(unittest.TestCase):
    """验收：有牙，且不自己作弊。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = self._tmp.name
        spec = deckio.read_json(STRESS)
        deckio.write_text(os.path.join(self.dir, "deck.spec.json"),
                          json.dumps(spec, ensure_ascii=False))
        self.spec = os.path.join(self.dir, "deck.spec.json")
        self.name = next(s["image"] for s in spec["deck"]["slides"] if s.get("image"))

    def _write(self, w: int, h: int) -> None:
        from PIL import Image   # noqa: PLC0415

        Image.new("RGB", (w, h), (180, 90, 60)).save(os.path.join(self.dir, self.name))

    def test_missing_image_is_reported(self) -> None:
        code, problems = image_source.check_images(self.spec, self.dir)
        self.assertEqual(code, 1)
        self.assertTrue(any("还没出图" in p for p in problems), problems)

    def test_check_does_not_create_the_image_it_verifies(self) -> None:
        """**回归**：`--check` 绝不能顺手造占位图。

        第一版它先调了 `_slot_geometry()`（那个函数会造占位图），于是删掉图之后
        照样报"符合契约" —— 检查把它该验的东西自己造了出来，永远验不出"还没出图"。
        """
        target = os.path.join(self.dir, self.name)
        self.assertFalse(os.path.isfile(target))
        image_source.check_images(self.spec, self.dir)
        self.assertFalse(os.path.isfile(target),
                         "--check 自己把图造出来了 —— 它再也验不出「图还没出」")

    def test_too_small_image_is_reported_with_the_number(self) -> None:
        self._write(400, 267)                     # 比例对，但只有 400px 宽
        code, problems = image_source.check_images(self.spec, self.dir)
        self.assertEqual(code, 1)
        self.assertTrue(any("400px 宽" in p for p in problems), problems)
        self.assertTrue(any("1280px" in p for p in problems), problems)

    def test_wrong_aspect_is_reported(self) -> None:
        self._write(1280, 1280)                   # 够大但是方的
        code, problems = image_source.check_images(self.spec, self.dir)
        self.assertEqual(code, 1)
        self.assertTrue(any("比例" in p for p in problems), problems)

    def test_a_good_image_passes(self) -> None:
        """反面对照：按契约出的图必须**一条都不报** ——
        否则上面那些"有牙"的用例可能只是"永远会报"。"""
        self._write(*self.brief_size())
        code, problems = image_source.check_images(self.spec, self.dir)
        self.assertEqual(problems, [])
        self.assertEqual(code, 0)

    def brief_size(self) -> tuple[int, int]:
        w = 640 * image_source.BRIEF_SCALE
        return (w, round(w * image_source.BRIEF_ASPECT[1] / image_source.BRIEF_ASPECT[0]))

    def test_shared_filename_is_verified_once(self) -> None:
        """同一个文件用在多页时只验一次、只报一条 —— 三条一样的报错是噪音。"""
        self._write(320, 213)
        _code, problems = image_source.check_images(self.spec, self.dir)
        self.assertEqual(len(problems), 1, problems)


class TestPlaceholderPath(unittest.TestCase):
    def test_brief_generates_placeholders_so_the_deck_still_renders(self) -> None:
        """契约阶段会放占位图 —— 这是有意的：出图要时间，而流水线不该因此停住。"""
        with tempfile.TemporaryDirectory() as tmp:
            brief = image_source.build_brief(STRESS, tmp)
            for s in brief["slots"]:
                self.assertTrue(os.path.isfile(os.path.join(tmp, s["file"])),
                                f"没放占位图：{s['file']}")


if __name__ == "__main__":
    unittest.main()
