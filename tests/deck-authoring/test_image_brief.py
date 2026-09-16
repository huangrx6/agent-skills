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
import re
import sys
import tempfile
import unittest

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
# 测试自有夹具（v4）：风格与内容样本都放在 tests/ 下，**不随 skill 发布** ——
# 可拷贝的模板必然变成默认答案（用户实测：每份 deck 长得一样）。
FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
# 夹具当"额外风格根"：v4 起工具链不内置任何风格（可拷贝的模板必然变成
# 默认答案）。脚本各持一份模块副本，所以走环境变量而不是改常量。
os.environ.setdefault("DECK_STYLES",
                      os.path.join(FIXTURES_DIR, "styles"))
os.environ.setdefault("DECK_BRANDS",
                      os.path.join(FIXTURES_DIR, "brands"))
SCRIPTS = os.path.join(SKILL, "scripts")
STRESS = os.path.join(FIXTURES_DIR, "stress.spec.json")


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

    def test_prompt_asks_for_a_safe_area_around_the_subject(self) -> None:
        """主体必须留余量 —— 否则裁切/留边一定把它切掉。

        版面按**槽位**裁切（照片 `cover`）或留边（结构图 `contain`），谁也不知道
        出图时主体贴没贴边；所以约束要写进提示词的【限制】栏（中英都要），
        并且 brief 末尾再给三条**只能人眼看**的自检。
        """
        for slot in self.brief["slots"]:
            zh = image_source.render_prompt(slot, self.brief, "zh")
            en = image_source.render_prompt(slot, self.brief, "en")
            self.assertIn("中心 80%", zh, slot.get("file"))
            self.assertIn("10%", zh, slot.get("file"))
            self.assertIn("CENTRAL 80%", en, slot.get("file"))
            self.assertIn("10%", en, slot.get("file"))
        for must in ("主体在不在中心 80%", "画面里有没有文字", "结构图有没有被压扁"):
            self.assertIn(must, self.md, must)

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
        for key in ("文件名", "尺寸", "透明通道", "色彩要落在色板内", "内容"):
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
        # v4：制版后处理已退役 —— 限制项改成"进版式会糊"这条管线事实
        self.assertIn("糊成一团", limits)
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


class TestCompositionByVariant(unittest.TestCase):
    """构图文案按版式变体分支（审计发现 2：hero 满幅不能说'只占一栏'）。"""

    def test_hero_says_full_bleed_not_one_column(self) -> None:
        hero = image_source._composition_text("hero", zh=True)
        self.assertIn("满幅主角", hero)
        self.assertIn("上 2/3", hero, "没说标题条压图的安全区")
        self.assertNotIn("只占一栏", hero, "hero 页却说只占一栏 —— 反指示")

    def test_default_still_says_one_column(self) -> None:
        plain = image_source._composition_text("", zh=True)
        self.assertIn("只占一栏", plain)

    def test_negative_space_branches(self) -> None:
        self.assertIn("标题条压图", image_source._negative_space_text("hero"))
        self.assertIn("另一栏", image_source._negative_space_text(""))


class TestAssetRequests(unittest.TestCase):
    """机读的资产请求（`assets/requests/<槽位id>.json`）—— manifest 的上游合同。

    `--brief` 在人读的 image-brief.md 之外，给每个图槽位写一份请求 JSON：
    先有请求 → 人出图 → 登记进 manifest，assetId 即槽位 id（spec 的 image 值），
    管线闭环（见 references/images.md 的 requests 节）。
    """

    # 封闭集：封闭集外字段不许写（与 render.py 的 manifest 同一套现法）
    FIELDS = frozenset({"schemaVersion", "slide", "role", "aspect", "focal",
                        "negative_space", "prompt", "required", "note"})

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        cls.brief = image_source.build_brief(STRESS, cls._tmp.name)
        cls.requests_dir = os.path.join(cls._tmp.name, "assets", "requests")

    def _load(self, slot: dict) -> dict:
        with open(os.path.join(self.requests_dir, f"{slot['file']}.json"),
                  encoding="utf-8") as fh:
            return json.load(fh)

    def test_one_request_per_image_slot_named_by_the_slot_id(self) -> None:
        """槽位数与图槽位一致，文件名 = 槽位 id（spec 的 image 值）+ .json ——
        这个 id 就是将来登记进 manifest 的 assetId，不另起一套。"""
        spec = deckio.read_json(STRESS)
        wanted = {str(s["image"]) for s in spec["deck"]["slides"] if s.get("image")}
        self.assertTrue(wanted, "压测 deck 本该有图槽位 —— 用例前提变了")
        self.assertEqual(set(os.listdir(self.requests_dir)),
                         {f"{name}.json" for name in wanted})

    def test_schema_is_closed_v1_and_required_is_always_true(self) -> None:
        for slot in self.brief["slots"]:
            with self.subTest(file=slot["file"]):
                data = self._load(slot)         # 能 json.load 本身就是要验的
                self.assertEqual(set(data), self.FIELDS, "封闭集外字段不许写")
                self.assertEqual(data["schemaVersion"], 1)
                self.assertIs(data["required"], True)
                self.assertEqual(data["slide"], slot["pages"])
                self.assertEqual(data["role"], slot["layout"])

    def test_aspect_is_the_measured_slot_ratio(self) -> None:
        """aspect 是实测槽位宽高比（来自 _slot_geometry），不是推荐的 3:2 拍脑袋数 ——
        从 brief 自己的实测字符串交叉验。容差 ±0.01：字符串是 :.0f 取整后的展示值，
        JSON 里存的是原始测量值，取整会差这么点。"""
        for slot in self.brief["slots"]:
            with self.subTest(file=slot["file"]):
                m = re.search(r"实测槽位 (\d+)×(\d+)px", slot["measured"])
                if m is None:
                    self.fail(f"槽位没有实测值：{slot['measured']!r}")
                else:
                    self.assertGreater(self._load(slot)["aspect"], 0)
                    self.assertAlmostEqual(self._load(slot)["aspect"],
                                           int(m.group(1)) / int(m.group(2)),
                                           delta=0.01)

    def test_prompt_is_render_prompt_of_the_slot(self) -> None:
        """prompt 就是 render_prompt 的产物 —— 同一份契约的两个视图，不许各说各的。"""
        for slot in self.brief["slots"]:
            with self.subTest(file=slot["file"]):
                self.assertEqual(self._load(slot)["prompt"],
                                 image_source.render_prompt(slot, self.brief, "zh"))


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
        code, problems, _notes = image_source.check_images(self.spec, self.dir)
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
        code, problems, _notes = image_source.check_images(self.spec, self.dir)
        self.assertEqual(code, 1)
        self.assertTrue(any("400px 宽" in p for p in problems), problems)
        self.assertTrue(any("1280px" in p for p in problems), problems)

    def test_svg_slots_are_read_from_viewbox(self) -> None:
        """SVG 是矢量：尺寸读 viewBox，且不做"放大=糊"那条。

        实测踩过：用户的 4 张结构图是 SVG，`Image.open` 直接抛 —— 检查器整个崩掉。
        """
        with tempfile.TemporaryDirectory() as tmp:
            svg = os.path.join(tmp, "diagram.svg")
            with open(svg, "w", encoding="utf-8") as fh:
                fh.write('<svg xmlns="http://www.w3.org/2000/svg" '
                         'viewBox="0 0 1280 800"></svg>')
            self.assertEqual(image_source.image_size(svg), (1280, 800))
            # 缺文件不能把检查器带走（deckio.read_text 读不到时抛 SystemExit）
            self.assertIsNone(image_source.image_size(os.path.join(tmp, "nope.svg")))
            self.assertIsNone(image_source.image_size(os.path.join(tmp, "not-a.svg")))

    def test_wrong_aspect_is_a_note_not_a_blocker(self) -> None:
        """够大但是方的（1:1）→ **不阻塞**：渲染按槽位处理（照片裁切 / 结构图留边）。

        为什么改：为比例重出图是浪费 —— 生图工具按不住比例是常态（各家默认都不同），
        而高度由**槽位**定（`.imgwrap img{aspect-ratio:3/2}`），1:1 不会撑出页底、
        2:1 不会留空洞。真的该重出的只有两件：宽度不够、主要内容被裁到。
        """
        self._write(1280, 1280)
        code, problems, notes = image_source.check_images(self.spec, self.dir)
        self.assertEqual(code, 0, problems)
        self.assertEqual(problems, [])
        self.assertTrue(any("不用为比例重出图" in n for n in notes), notes)

    def test_a_good_image_passes(self) -> None:
        """反面对照：按契约出的图必须**一条都不报** ——
        否则上面那些"有牙"的用例可能只是"永远会报"。"""
        self._write(*self.brief_size())
        code, problems, _notes = image_source.check_images(self.spec, self.dir)
        self.assertEqual(problems, [])
        self.assertEqual(code, 0)

    def brief_size(self) -> tuple[int, int]:
        w = 640 * image_source.BRIEF_SCALE
        return (w, round(w * image_source.BRIEF_ASPECT[1] / image_source.BRIEF_ASPECT[0]))

    def test_shared_filename_is_verified_once(self) -> None:
        """同一个文件用在多页时只验一次、只报一条 —— 三条一样的报错是噪音。"""
        self._write(320, 213)
        _code, problems, _notes = image_source.check_images(self.spec, self.dir)
        self.assertEqual(len(problems), 1, problems)


class TestNoImagesWritten(unittest.TestCase):
    """`--brief` **不往产物目录写任何图** —— 量槽位的尺子只活在临时目录里。

    写进产物目录就等于把一张脚本拼的图混进交付（实测踩过：`--brief` 跑完，图片
    目录里躺着几张拼贴，没人替换它们就跟着交付了）。图只能来自人拿提示词出的那一份。
    """

    def test_brief_writes_no_image_into_the_deck_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            brief = image_source.build_brief(STRESS, tmp)
            stray = sorted(f for f in os.listdir(tmp) if f.endswith(".png"))
            self.assertEqual(stray, [], f"产物目录里出现了脚本写的图：{stray}")
            # 尺子进临时目录≠不量：几何仍是**实测**的，不是估算的
            self.assertGreater(brief["target_px"][1], 0)
            for slot in brief["slots"]:
                self.assertTrue(slot["file"].endswith(".png"),
                                "契约里的文件名必须还是用户那个路径（不能被尺子顶掉）")
                self.assertNotIn("ruler", slot["file"])

    def test_existing_image_is_untouched(self) -> None:
        """已经放好的图不许被覆盖 —— 那是人的成果。"""
        with tempfile.TemporaryDirectory() as tmp:
            brief = image_source.build_brief(STRESS, tmp)
            path = os.path.join(tmp, brief["slots"][0]["file"])
            os.makedirs(os.path.dirname(path), exist_ok=True)
            Image.new("RGB", (8, 8), (200, 30, 30)).save(path)
            with open(path, "rb") as fh:
                before = fh.read()
            image_source.build_brief(STRESS, tmp)
            with open(path, "rb") as fh:
                self.assertEqual(fh.read(), before, "已有的图被脚本覆盖了")



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


class TestNoFullPageImage(unittest.TestCase):
    """**一张图盖住整页是不允许的。**

    一页的信息（标题 / 条目 / 数字 / 示意）烘进图里之后，同时失去可编辑、可搜索、
    可翻译、可被读屏器读这四件事 —— 而"对方要改字"正是这个 skill 能出原生 PPTX 的
    理由。所以这条是**禁止**（阻塞级），不是提示。
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.check_mod = _load("check")

    def _el(self, w, h, role="image", slide=2):
        return {"elements": [{"role": role, "slide": slide, "w": w, "h": h,
                              "intendedText": "a.png"}]}

    def test_full_page_image_is_blocked(self) -> None:
        out = self.check_mod._check_full_page_image(self._el(1560, 850), self._deck())
        self.assertEqual(len(out), 1, out)
        self.assertIn("盖住了整页", out[0])
        self.assertIn("不允许", out[0])

    @staticmethod
    def _deck() -> dict:
        """非 hero 页的 deck（这些用例测的就是非主角图的守卫；hero 放行
        在 test_check_mutations 的 TestFullPageImageRoleAware 里另有四面）。"""
        return {"slides": [{"type": "content-image", "variant": "visual-right",
                           "image": "x.png"}]}

    def test_ordinary_figure_is_fine(self) -> None:
        """反面对照：真实的配图（实测整页 17%）一条都不许报 ——
        否则上面那条可能只是"永远会报"。"""
        self.assertEqual(self.check_mod._check_full_page_image(
            self._el(607, 404), self._deck()), [])

    def test_threshold_has_margin_from_reality(self) -> None:
        """阈值必须离真实情况远 —— 差一点点就报错的守卫会被人一律忽略。"""
        self.assertGreater(self.check_mod.FULL_PAGE_IMAGE, 0.4)
        self.assertLess(self.check_mod.FULL_PAGE_IMAGE, 1.0)

    def test_a_tall_banner_image_is_not_full_page(self) -> None:
        """按**面积**判，不是按宽度：一条通栏横幅没那么严重（占不满高）。"""
        self.assertEqual(self.check_mod._check_full_page_image(
            self._el(1600, 300), self._deck()), [])

    def test_bad_measurements_do_not_raise(self) -> None:
        """`check()` 从不抛 —— 尺寸缺失就该跳过，不是崩掉整次校验。"""
        for w, h in ((None, None), ("", ""), (0, 0), ("a", "b")):
            with self.subTest(w=w, h=h):
                self.assertEqual(self.check_mod._check_full_page_image(
                self._el(w, h), self._deck()), [])

    def test_error_says_where_the_information_should_live(self) -> None:
        """报错要给出路：信息由版面用**真文字**排，不是"别这么干"。"""
        msg = self.check_mod._check_full_page_image(
            self._el(1600, 900), self._deck())[0]
        self.assertIn("真文字", msg)
        self.assertIn("配图或点缀", msg)


class TestRoleStaysOutOfTheImage(unittest.TestCase):
    """提示词要说清图的**角色**：配图 / 点缀，不是整页背景；信息不画进图里。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        brief = image_source.build_brief(STRESS, cls._tmp.name)
        cls.path = os.path.join(cls._tmp.name, "image-brief.md")
        image_source.write_brief_md(brief, cls.path)
        cls.md = deckio.read_text(cls.path)

    def _block(self, lang: str) -> str:
        head = "**中文提示词**" if lang == "zh" else "**English prompt**"
        return self.md.split(head, 1)[1].split("```text", 1)[1].split("```", 1)[0]

    def test_image_is_declared_a_column_not_a_background(self) -> None:
        for lang, needle in (("zh", "只占一栏"), ("en", "ONE COLUMN")):
            with self.subTest(lang=lang):
                self.assertIn(needle, self._block(lang))
        self.assertIn("不是整页背景", self._block("zh"))

    def test_page_information_must_not_be_drawn_into_the_image(self) -> None:
        """这条是用户明确禁掉的那件事的正面表述：信息由版面排，图只负责观感。"""
        self.assertIn("不要把这一页的信息画进去", self._block("zh"))
        self.assertIn("界面截图", self._block("zh"))     # 点名了不许装的几类东西
        self.assertIn("real text", self._block("en"))

    def test_contract_header_states_the_two_roles(self) -> None:
        self.assertIn("两种角色", self.md)
        self.assertIn("配图", self.md)
        self.assertIn("点缀", self.md)
        self.assertIn("盖住整页是不允许的", self.md)


class TestContractLocation(unittest.TestCase):
    """合同（提示词 + requests）的落点：**永远跟着 spec（deck 项目）走**。

    实测踩过：一份 17 页 deck 的提示词合同被 `--dir` 搬进了 /tmp —— 用户拿不到
    那份要他拿去出图的东西。`--dir` 的本意只是"图片在哪"：占位图仍按它落
    （渲染按图片目录解析 `image`），但合同留在 spec 同目录。
    """

    def test_brief_and_requests_stay_with_spec_while_images_follow_dir(self) -> None:
        import contextlib
        import io
        import shutil

        with tempfile.TemporaryDirectory() as spec_dir, \
                tempfile.TemporaryDirectory() as img_dir:
            spec = os.path.join(spec_dir, "deck.spec.json")
            shutil.copyfile(STRESS, spec)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = image_source.main(
                    ["image_source.py", "--brief", spec, "--dir", img_dir])
            self.assertEqual(rc, 0, buf.getvalue())
            self.assertTrue(os.path.isfile(os.path.join(spec_dir, "image-brief.md")),
                            "提示词合同必须落在 spec 同目录（deck 项目）")
            self.assertFalse(os.path.exists(os.path.join(img_dir, "image-brief.md")))
            self.assertTrue(os.path.isdir(os.path.join(spec_dir, "assets", "requests")),
                            "机读 requests 与合同同根")
            self.assertEqual([f for f in os.listdir(img_dir) if f.endswith(".png")], [],
                             "脚本不往图片目录写任何东西（图是人出的，--dir 只说明存哪儿）")
            self.assertIn(img_dir, buf.getvalue(), "要告诉人出完图存到哪")
            self.assertIn("临时目录", buf.getvalue(),
                          "deck 建在临时目录里要开口说一声")

    def test_temp_dir_note_only_fires_for_temp_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIn("临时目录", image_source._temp_dir_note(tmp) or "")
        project = os.path.dirname(os.path.abspath(STRESS))
        self.assertIsNone(image_source._temp_dir_note(project))


if __name__ == "__main__":
    unittest.main()
