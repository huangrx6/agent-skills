#!/usr/bin/env python3
"""Image brief direction, measured geometry and actual asset acceptance regressions."""

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
# 测试自有夹具：风格与内容样本都放在 tests/ 下，**不随 skill 发布** ——
# 可拷贝的模板必然变成默认答案（每份 deck 长得一样）。
FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
# 夹具当"额外风格根"：工具链不内置任何风格（可拷贝的模板必然变成
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
    """Legacy specs retain measured contracts without imposing a photographic style."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        cls.brief = image_source.build_brief(STRESS, cls._tmp.name)
        cls.md_path = os.path.join(cls._tmp.name, "image-brief.md")
        image_source.write_brief_md(cls.brief, cls.md_path)
        cls.md = deckio.read_text(cls.md_path)

    def test_no_unrequested_medium_color_limit_or_focal_area(self) -> None:
        for slot in self.brief["slots"]:
            for lang in ("zh", "en"):
                prompt = image_source.render_prompt(slot, self.brief, lang)
                for phrase in ("纪实摄影", "documentary photography", "1~3", "1-3 colour",
                               "中心 80%", "CENTRAL 80%", "60~70%", "上 2/3",
                               "只占一栏", "ONE COLUMN", "不透明照片"):
                    self.assertNotIn(phrase, prompt)
                self.assertNotIn("【风格】", prompt)
                self.assertNotIn("【背景】", prompt)

    def test_one_entry_per_filename_not_per_page(self) -> None:
        names = [s["file"] for s in self.brief["slots"]]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(any(len(s["pages"]) > 1 for s in self.brief["slots"]))

    def test_target_size_covers_all_measured_reuse_slots(self) -> None:
        import math
        for slot in self.brief["slots"]:
            self.assertEqual(slot["target_px"], [
                math.ceil(max(r[d] for r in slot["requirements"]) * image_source.BRIEF_SCALE)
                for d in ("width", "height")])

    def test_missing_subject_stays_unresolved_without_inventing_evidence(self) -> None:
        for slot in self.brief["slots"]:
            self.assertTrue(image_source.PLACEHOLDER_RE.search(
                image_source.render_prompt(slot, self.brief)))
        self.assertIn("参考材料", self.md)
        self.assertIn("真实截图", self.md)

    def test_geometry_and_transparency_parameters_are_honest(self) -> None:
        self.assertIn("尺寸", self.md)
        self.assertIn("来自实测尺寸", self.md)
        self.assertIn("透明通道未指定", self.md)
        self.assertNotIn("整张不透明照片", self.md)
        self.assertNotIn("盖住整页是不允许的", self.md)
        self.assertIn("English prompt", self.md)


class TestAuthoredImageBrief(unittest.TestCase):
    def setUp(self) -> None:
        self.brief = {"temperature": "安静", "colors": {"primary": "#0033CC", "secondary": "#111111", "background": "#FFFFFF"}}
        self.slot = {"imageBrief": {}, "requirements": [{"fit": "cover"}]}

    def test_illustration_direction_and_explicit_text_are_not_overruled(self) -> None:
        self.slot["imageBrief"] = {
            "purpose": "封面，表达两种观点的对话", "subject": "两只纸雕鸟，各持写有 YES 和 NO 的卡片",
            "style": "彩色纸雕插画，柔和渐变和细线纹理", "composition": "双主体放在画面右侧",
            "negativeSpace": "左侧 40% 留给正文，保持低细节", "focal": [78, 43],
            "transparent": True, "avoid": ["不裁断鸟喙", "不要复制卡片"]}
        for lang in ("zh", "en"):
            prompt = image_source.render_prompt(self.slot, self.brief, lang)
            for field in ("purpose", "subject", "style", "composition", "negativeSpace"):
                self.assertIn(self.slot["imageBrief"][field], prompt)
            self.assertIn("78%", prompt)
            self.assertIn("43%", prompt)
            self.assertNotIn("不要出现任何文字", prompt)
            self.assertNotIn("documentary photography", prompt)
            self.assertFalse(image_source.PLACEHOLDER_RE.search(prompt))
        self.assertIn("真实透明通道", image_source.render_prompt(self.slot, self.brief))

    def test_contain_does_not_warn_that_all_edges_will_be_cropped(self) -> None:
        self.slot["requirements"] = [{"fit": "contain"}]
        self.slot["imageBrief"] = {"subject": "完整保留的产品组件示意图"}
        prompt = image_source.render_prompt(self.slot, self.brief)
        self.assertIn("保留完整画面", prompt)
        self.assertNotIn("cover 裁切", prompt)
        self.assertNotIn("中心 80%", prompt)

    def test_legacy_hero_warning_requires_actual_route_metadata(self) -> None:
        self.slot["layout"] = "hero"
        self.assertNotIn("底部标题带", image_source.render_prompt(self.slot, self.brief))
        self.slot["hero_overlay_pages"] = [2]
        prompt = image_source.render_prompt(self.slot, self.brief)
        self.assertIn("底部标题带", prompt)
        self.assertNotIn("上 2/3", prompt)
        self.assertNotIn("不需要在图内为文字留白", prompt)

    def test_transparent_false_is_explicit_not_the_default(self) -> None:
        self.assertNotIn("【背景】", image_source.render_prompt(self.slot, self.brief))
        self.slot["imageBrief"]["transparent"] = False
        self.assertIn("不透明背景", image_source.render_prompt(self.slot, self.brief))

    def test_spec_direction_reaches_measured_request_and_both_prompt_views(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec = deckio.read_json(STRESS)
            spec["deck"]["slides"] = [{
                "type": "content-image", "title": "不是图中文字", "image": "cutout.png", "layout": "hero",
                "visual": {"kind": "evidence_image", "ratio": "4:3", "imageBrief": {
                    "subject": "纸雕鸟", "purpose": "品牌概念示意", "focal": [72, 30],
                    "negativeSpace": "左侧留白", "style": "多彩纸雕", "transparent": True}}}]
            path = os.path.join(tmp, "deck.spec.json")
            deckio.write_json(path, spec)
            brief = image_source.build_brief(path, tmp)
            slot = brief["slots"][0]
            request = deckio.read_json(os.path.join(tmp, "assets", "requests", "cutout.png.json"))
            self.assertEqual(request["focal"], [72, 30])
            self.assertEqual(request["negative_space"], "左侧留白")
            self.assertIs(request["transparent"], True)
            self.assertEqual(request["prompt"], image_source.render_prompt(slot, brief))
            self.assertIn("底部标题带", request["prompt"])
            self.assertIn("纸雕鸟", request["prompt"])
            self.assertFalse(image_source.PLACEHOLDER_RE.search(request["prompt"]))
            self.assertGreater(request["target_px"][0], 0)

    def test_conflicting_reused_image_directions_do_not_silently_pick_first(self) -> None:
        from unittest.mock import patch
        slides = {i: {"file": "same.png", "box": {"w": 100, "h": 100}, "title": "t", "bullets": [],
                      "imageBrief": {"focal": focal}} for i, focal in ((1, [20, 50]), (2, [80, 50]))}
        with tempfile.TemporaryDirectory() as tmp, patch.object(
                image_source, "_slot_geometry", return_value=({"slides": slides, "colors": self.brief["colors"]}, "swiss-grid")):
            with self.assertRaisesRegex(SystemExit, "imageBrief.focal 不一致"):
                image_source.build_brief(STRESS, tmp)


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

    def test_schema_is_closed_v2_and_required_is_always_true(self) -> None:
        for slot in self.brief["slots"]:
            with self.subTest(file=slot["file"]):
                data = self._load(slot)         # 能 json.load 本身就是要验的
                self.assertEqual(set(data), self.FIELDS | {"target_px", "requirements"}, "封闭集外字段不许写")
                self.assertEqual(data["schemaVersion"], 2)
                self.assertIs(data["required"], True)
                self.assertEqual(data["slide"], slot["pages"])
                self.assertEqual(data["role"], slot["layout"])

    def test_aspect_covers_all_measured_reuse_slots(self) -> None:
        """生成比例来自所有复用图位的最大宽高，不能只承诺第一次出现的尺寸。"""
        for slot in self.brief["slots"]:
            with self.subTest(file=slot["file"]):
                data = self._load(slot)
                self.assertEqual(data["requirements"], slot["requirements"])
                width, height = data["target_px"]
                self.assertGreater(data["aspect"], 0)
                self.assertAlmostEqual(data["aspect"], width / height, delta=0.001)
                for requirement in data["requirements"]:
                    self.assertGreaterEqual(width, requirement["width"] * image_source.BRIEF_SCALE)
                    self.assertGreaterEqual(height, requirement["height"] * image_source.BRIEF_SCALE)

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
        # 几何是否真实由 TestBrief 验；这里只测验收数学，避免每个尺寸用例都启动浏览器。
        from unittest.mock import patch
        geometry = {"slides": {
            page: {"file": slide["image"], "box": {
                "w": 640, "h": 640 * 2 / 3, "objectFit": "cover"}}
            for page, slide in enumerate(spec["deck"]["slides"], 1) if slide.get("image")}}
        self.geometry_patch = patch.object(image_source, "_slot_geometry", return_value=(geometry, "test"))
        self.geometry_patch.start()
        self.addCleanup(self.geometry_patch.stop)

    def _write(self, w: int, h: int) -> None:
        Image.new("RGB", (w, h), (180, 90, 60)).save(os.path.join(self.dir, self.name))

    def test_transparency_contract_checks_pixels_instead_of_only_channel_name(self) -> None:
        spec = deckio.read_json(self.spec)
        for slide in spec["deck"]["slides"]:
            if slide.get("image") == self.name:
                slide.setdefault("visual", {})["imageBrief"] = {"transparent": True}
        deckio.write_json(self.spec, spec)
        self._write(1536, 1024)
        _, problems, _ = image_source.check_images(self.spec, self.dir)
        self.assertTrue(any("不满足声明的真实透明通道" in p for p in problems))
        pixels = Image.new("RGBA", (1536, 1024), (20, 30, 40, 0))
        pixels.save(os.path.join(self.dir, self.name))
        _, problems, _ = image_source.check_images(self.spec, self.dir)
        self.assertTrue(any("没有可见内容" in p for p in problems))
        pixels.putpixel((700, 500), (20, 30, 40, 255))
        pixels.save(os.path.join(self.dir, self.name))
        _, problems, _ = image_source.check_images(self.spec, self.dir)
        self.assertFalse(any("透明" in p for p in problems), problems)

    def test_missing_image_is_reported(self) -> None:
        code, problems, _notes = image_source.check_images(self.spec, self.dir)
        self.assertEqual(code, 1)
        self.assertTrue(any("还没出图" in p for p in problems), problems)

    def test_check_does_not_create_the_image_it_verifies(self) -> None:
        """`--check` 绝不能顺手造占位图。

        检查只该看"文件名 + 契约里的尺寸/比例"这一层事实：一旦它先把该验的东西
        自己造出来，就永远验不出"还没出图"（删掉图之后照样报"符合契约"）。
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

    def test_a_tiny_shortfall_is_a_note_not_a_blocker(self) -> None:
        """“出小了”那条门的容差：生图服务每个比例给的是**固定像素**，未必正好够 1280。

        实测形状：官方 MiniMax 的 3:2 就是 1248×832（少 2.5%）。这种图判成“会糊”
        会把整条链卡在一张本来能用的图上 —— 而门该拦的是“拿缩略图当大图”。
        """
        self._write(1248, 832)
        code, problems, notes = image_source.check_images(self.spec, self.dir)
        self.assertEqual(code, 0, problems)
        self.assertTrue(any("1248px 宽" in n for n in notes), notes)

    def test_the_tolerance_does_not_swallow_a_real_shortfall(self) -> None:
        """反面对照：容差不是把门拆了 —— 差得多仍然是阻塞项。"""
        self.assertEqual(image_source.SIZE_TOLERANCE, 0.05)
        self._write(int(1280 * (1 - image_source.SIZE_TOLERANCE)) - 1, 704)
        code, problems, _notes = image_source.check_images(self.spec, self.dir)
        self.assertEqual(code, 1, problems)

    def test_svg_slots_are_read_from_viewbox(self) -> None:
        """SVG 是矢量：尺寸读 viewBox，且不做"放大=糊"那条。

        为什么不能直接 `Image.open`：结构图常是 SVG，PIL 对它直接抛 ——
        把整个检查器带走（一个不合格式的文件不该让门本身倒掉）。
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
