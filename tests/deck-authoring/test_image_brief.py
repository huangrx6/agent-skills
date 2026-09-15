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
        self.assertIn("中文提示词", self.md)
        self.assertIn("English prompt", self.md)

    def test_fields_appear_in_the_mandated_order(self) -> None:
        """出现的字段**必须按序**：主体 → 场景 → 构图 → (镜头) → 光线 → 色彩 → 风格 → 细节 → 文字 → 限制。

        顺序本身就是"先明白画什么、再明白怎么画"。堆成一段的写法会让
        「不要细密纹理」这种约束把「主体是什么」淹掉 —— 而主体最优先。
        """
        for lang in ("zh", "en"):
            with self.subTest(lang=lang):
                block = self._prompt_block(lang)
                positions = []
                for field in image_source.PROMPT_ORDER:
                    if field in image_source.OPTIONAL_FIELDS:
                        continue
                    self.assertIn(f"【{field}】", block, f"{lang} 缺字段「{field}」")
                    positions.append(block.index(f"【{field}】"))
                self.assertEqual(positions, sorted(positions),
                                 f"{lang} 的字段顺序乱了：{positions}")

    def test_lens_line_is_absent_by_default(self) -> None:
        """**只在需要时加** —— 所以默认整行不出现。

        给一个"安全默认值"看起来无害，但它意味着**每次都加**，正好违反
        "只有当镜头信息能明显改善画面时才加入"。工具判断不了这张图需不需要镜头感，
        就把判断权交回给看图的人。
        """
        for lang in ("zh", "en"):
            with self.subTest(lang=lang):
                self.assertNotIn("【镜头】", self._prompt_block(lang))
        # 但要告诉人怎么加、加在哪
        self.assertIn("镜头", self.md)
        self.assertIn("在【构图】和【光线】之间", self.md)
        self.assertIn("LENS", self.md) if "LENS" in self.md else None

    def test_api_params_are_not_written_into_the_prompt(self) -> None:
        """**回归**：尺寸 / 比例 / 数量不能出现在提示词正文里。

        生图 API 有独立参数，prompt 里再写一遍只会在冲突时给出随机结果。
        第一版就把 `3:2` 与 `1280x853px` 写进了正文。
        """
        for lang in ("zh", "en"):
            with self.subTest(lang=lang):
                block = self._prompt_block(lang)
                w, h = self.brief["target_px"]
                for banned in (f"{w}", f"{h}", f"{w}×{h}", f"{w}x{h}", "3:2", "aspect ratio"):
                    self.assertNotIn(banned, block,
                                     f"{lang} 提示词里出现了 API 参数「{banned}」")
        self.assertIn("参数", self.md)
        self.assertIn("不要写进 prompt", self.md)

    def test_out_of_frame_metadata_stays_out_of_the_prompt(self) -> None:
        """**回归**：提示词只装"模型要照做的事"，不能混进写给读者的旁白。

        上一版漏进去三句：「（可执行的视觉语言）」「限制只列与这条管线相关的，
        不堆通用负面词」「优先于任何装饰性的色彩偏好」—— 后者是人看的规则说明，
        模型会把它当成画面要求。两个读者不能混在一段里。
        """
        banned = ["可执行的视觉语言", "限制只列", "不堆通用负面词",
                  "优先于任何装饰性的色彩偏好", "优先于",
                  "pipeline-relevant", "boilerplate"]
        for lang in ("zh", "en"):
            for text in banned:
                with self.subTest(lang=lang, text=text):
                    self.assertNotIn(text, self._prompt_block(lang))

    def test_style_is_not_duplicated_and_is_executable(self) -> None:
        """风格栏要写"可执行的视觉语言"，且不许重复说同一件事。

        上一版是「纪实摄影（可执行的视觉语言）；克制平静的**纪实摄影**…」。
        """
        block = self._prompt_block("zh")
        style = block.split("【风格】")[1].split("\n")[0]
        self.assertEqual(style.count("纪实摄影"), 1, style)
        self.assertIn("大块明暗", style)

    def _prompt_block(self, lang: str) -> str:
        """取出某个语言的提示词正文（不含契约里的叙述部分）。"""
        head = "**中文提示词**" if lang == "zh" else "**English prompt**"
        chunk = self.md.split(head, 1)[1]
        return chunk.split("```text", 1)[1].split("```", 1)[0]

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
        self.assertIn("SEPARATE column", self.md)
        self.assertIn("不要在图内为文字留白", self.md)

    def test_limits_are_pipeline_specific_not_boilerplate(self) -> None:
        """限制项要与任务相关。通用的"不要水印/不要额外人物"是噪音。"""
        block = self._prompt_block("zh")
        limits = block.split("【限制】")[1]
        self.assertIn("细线", limits)
        self.assertIn("双色调", limits)
        for generic in ("水印", "额外人物", "畸形手指"):
            self.assertNotIn(generic, limits)

    def test_tool_does_not_invent_the_subject(self) -> None:
        """**回归**：主体 / 场景 / 细节留空给人填 —— 工具**不许**自己编。

        规则是"用户未提供且会影响事实准确性的内容，不得擅自补充"。第一版把该页标题
        拼成"内容草稿"塞进了提示词，而条目往往在讲这份 deck 的叙事
        （"原始照片降噪后重新制版"），不是在讲画面里该有什么。
        """
        for lang in ("zh", "en"):
            for field in ("主体", "场景", "细节"):
                with self.subTest(lang=lang, field=field):
                    block = self._prompt_block(lang)
                    line = block.split(f"【{field}】")[1].split("\n")[0]
                    self.assertIn("〈" if lang == "zh" else "<", line,
                                  f"{lang} 的「{field}」没留空，工具自己填了：{line}")
        # 但参考材料要给到，否则人无从下手
        self.assertIn("参考材料", self.md)
        self.assertIn("现场", self.md)

    def test_text_field_points_at_the_layout_not_the_model(self) -> None:
        """「文字」那一栏要落到**版面**上：画面里不要字，字由版面排。

        这比笼统的"不要水印"有用 —— 而且它把准确性放在后期排版，不押在模型身上。
        """
        block = self._prompt_block("zh")
        self.assertIn("不要出现任何文字", block)
        self.assertIn("版面", block)

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



class TestImageEconomy(unittest.TestCase):
    """「图片该要就要，别因为嫌麻烦就少要，多了也没事」——

    这条准则在两处落地：**输入门**（版式要图就必须给图）与**产物提示**
    （全篇一张图都没有时开口）。前者阻塞、后者提示，因为"该有几张图"取决于内容。
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.check_mod = _load("check")
        cls.stress = deckio.read_json(STRESS)

    def _deck(self, strip_images: bool):
        deck = json.loads(json.dumps(self.stress["deck"]))
        for s in deck["slides"]:
            if strip_images:
                s.pop("image", None)
                s.pop("caption", None)
                if s.get("type") == "content-image":
                    s["type"] = "content-text"
        return deck

    def _notes(self, strip_images: bool) -> str:
        # 只给 {} 当 measured：内容跨度取不到就是 None，于是这里只会跑
        # deck 级那几条（图量 / 版式单一 / 缺封面），不必真渲一遍。
        _problems, notes = self.check_mod._check_deck_shape({}, self._deck(strip_images))
        return " / ".join(notes)

    def test_zero_images_is_called_out(self) -> None:
        self.assertIn("没有一张图", self._notes(strip_images=True))

    def test_a_deck_with_images_is_not_nagged(self) -> None:
        """已有图的 deck 不许被唠叨 —— 唠叨会让人整体忽略提示。"""
        self.assertNotIn("没有一张图", self._notes(strip_images=False))

    def test_note_names_where_to_add_one(self) -> None:
        """光说"没图"没有用，得指出最容易加图的那几页。"""
        notes = self._notes(strip_images=True)
        self.assertIn("纯文字", notes)

    def test_slot_suggestions_point_at_text_only_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            deck = self._deck(strip_images=True)
            path = os.path.join(tmp, "noimg.spec.json")
            deckio.write_text(path, json.dumps({"deck": deck}, ensure_ascii=False))
            hints = image_source.suggest_image_slots(path)
        self.assertTrue(hints, "全文字 deck 本该给出建议")
        self.assertTrue(any("纯文字页" in h for h in hints), hints)

    def test_brief_without_slots_suggests_instead_of_refusing(self) -> None:
        """**回归**：一张图都没有时 `--brief` 不再甩一句"没有要出图的地方"就完事。

        那是把"少要"做成了默认。现在它指出哪几页可能该有图，由内容定要不要加。
        """
        with tempfile.TemporaryDirectory() as tmp:
            deck = self._deck(strip_images=True)
            path = os.path.join(tmp, "noimg.spec.json")
            deckio.write_text(path, json.dumps({"deck": deck}, ensure_ascii=False))
            with self.assertRaises(SystemExit) as ctx:
                image_source.build_brief(path, tmp)
        msg = str(ctx.exception)
        self.assertIn("没有任何 image 槽位", msg)
        self.assertIn("要不要加图由内容定", msg)
        self.assertIn("content-image", msg)

if __name__ == "__main__":
    unittest.main()
