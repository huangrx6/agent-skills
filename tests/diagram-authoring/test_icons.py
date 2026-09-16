"""图标层：素材库读取、固有尺寸、复制进场景时的 id 与引用重映射。

这一层的特殊之处：**图标的宽高来自外部文件**，不是我们算的 ——
这是这个项目第一次有外部数据直接决定画出来的东西有多大。
所以 `references/validation.md` 第六节那条"尺寸只有一个来源"的前提，
从有这个模块起就不成立了（已按约定先改文档，再改 `TestSizeSourcePremise`）。
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
# 测试住在仓库顶层 `tests/<skill>/`（**刻意不在 skill 目录里**：AI 调用 skill 时
# 读的是 `skills/<skill>/` 那棵树，测试放在里面会被顺手读进去）。
# 测试住在仓库顶层 `tests/<skill>/`（**刻意不在 skill 目录里**：AI 调用 skill 时读的是
# `skills/<skill>/` 那棵树，测试放在里面会被顺手读进去）。
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")
LIBS = os.path.join(HERE, "fixtures", "libraries")


def _load(name, filename):
    path = os.path.join(SCRIPTS, filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


I = _load("icons", "icons.py")
V2 = os.path.join(LIBS, "mini-v2.excalidrawlib")
# 图标相关用例共用的规格。放模块级而不是类属性 —— 可变的类属性是共享可变状态。
ICON_SPEC = {"type": "flow", "direction": "TB",
             "nodes": [{"id": "a", "kind": "service", "label": "订单服务",
                        "icon": "Bound Box"}],
             "edges": []}
V1 = os.path.join(LIBS, "mini-v1.excalidrawlib")


class TestLibraryFormats(unittest.TestCase):
    def test_v2_reads_names(self):
        lib = I.load(V2)
        self.assertTrue(lib["named"])
        self.assertEqual(["Bound Box", "Linked Nodes", "Two Sizes"], I.names(lib))

    def test_v1_has_no_names_and_says_so(self):
        """v1 的项真的没有名字 —— 不能造一个看起来像名字的东西。"""
        lib = I.load(V1)
        self.assertFalse(lib["named"])
        self.assertEqual(["#0"], I.names(lib))

    def test_rejects_a_file_that_is_not_a_library(self):
        bad = os.path.join(LIBS, "not-a-library.json")
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write('{"type": "excalidraw"}')
        try:
            with self.assertRaises(I.LibraryError):
                I.load(bad)
        finally:
            os.remove(bad)

    def test_missing_file_is_an_error_not_an_empty_library(self):
        with self.assertRaises(I.LibraryError):
            I.load(os.path.join(LIBS, "nope.excalidrawlib"))

    def test_unknown_icon_name_lists_what_is_available(self):
        lib = I.load(V2)
        with self.assertRaises(I.LibraryError) as ctx:
            I.resolve(lib, "没有这个图标")
        message = str(ctx.exception)
        self.assertIn("Bound Box", message, "报错要列出可用的名字")
        self.assertNotIn("fallback", message)


class TestIntrinsicSize(unittest.TestCase):
    def test_size_comes_from_the_file(self):
        """固有宽高是**外部数据** —— 这里就是它进入项目的地方。"""
        lib = I.load(V2)
        self.assertEqual((100.0, 60.0), I.intrinsic_size(I.resolve(lib, "Bound Box")))
        self.assertEqual((160.0, 40.0), I.intrinsic_size(I.resolve(lib, "Linked Nodes")))

    def test_scale_fits_the_target_height(self):
        lib = I.load(V2)
        self.assertAlmostEqual(0.5, I.fit_scale(I.resolve(lib, "Linked Nodes"), 20.0))

    def test_zero_height_does_not_divide_by_zero(self):
        """纯水平线条的素材高度是 0 —— 不能在这里炸。"""
        self.assertEqual(1.0, I.fit_scale([{"x": 0, "y": 0, "width": 10, "height": 0}], 22.0))


class TestPlacement(unittest.TestCase):
    """复制进场景时最容易错的三件事：id 撞、引用悬空、坐标没换算。"""

    def setUp(self):
        self.lib = I.load(V2)

    def test_every_id_is_fresh(self):
        for name in I.names(self.lib):
            with self.subTest(icon=name):
                src = I.resolve(self.lib, name)
                placed = I.place(src, 0, 0, key=f"icon-{name}")
                old = {e["id"] for e in src}
                new = {e["id"] for e in placed}
                self.assertEqual(len(new), len(placed), "新 id 之间有重复")
                self.assertEqual(set(), old & new, "新 id 和素材库里的 id 撞了")

    def test_internal_references_follow_the_new_ids(self):
        """带内部引用的素材最容易出错：容器的 boundElements 指向文字，
        文字的 containerId 指回容器 —— 只改一半就会在 Excalidraw 里拖不动。"""
        src = I.resolve(self.lib, "Bound Box")
        placed = I.place(src, 0, 0, key="icon-b")
        new_ids = {e["id"] for e in placed}
        by_id = {e["id"]: e for e in placed}
        for element in placed:
            for bound in element.get("boundElements") or []:
                self.assertIn(bound["id"], new_ids, "boundElements 指向了不存在的元素")
                target = by_id[bound["id"]]
                self.assertEqual(element["id"], target.get("containerId"),
                                 "绑定不是双向的 —— Excalidraw 里会拖不动")
            if element.get("containerId"):
                self.assertIn(element["containerId"], new_ids)

    def test_arrow_bindings_are_remapped_too(self):
        placed = I.place(I.resolve(self.lib, "Linked Nodes"), 0, 0, key="icon-n")
        new_ids = {e["id"] for e in placed}
        arrow = next(e for e in placed if e["type"] == "arrow")
        self.assertIn(arrow["startBinding"]["elementId"], new_ids)
        self.assertIn(arrow["endBinding"]["elementId"], new_ids)
        self.assertNotEqual(arrow["startBinding"]["elementId"],
                            arrow["endBinding"]["elementId"])

    def test_bindings_pointing_outside_the_item_are_dropped(self):
        """指向素材项**外面**的引用必须清掉 —— 留着就是悬空引用。"""
        src = [{"id": "x", "type": "arrow", "x": 0, "y": 0, "width": 10, "height": 10,
                "points": [[0, 0], [10, 0]],
                "startBinding": {"elementId": "不在这一项里", "gap": 4}}]
        placed = I.place(src, 0, 0, key="icon-o")
        self.assertIsNone(placed[0]["startBinding"])

    def test_position_and_scale_are_both_applied(self):
        src = I.resolve(self.lib, "Bound Box")          # 100×60
        placed = I.place(src, 500.0, 300.0, key="icon-p", target_height=30.0)
        xs = [e["x"] for e in placed] + [e["x"] + e["width"] for e in placed]
        ys = [e["y"] for e in placed] + [e["y"] + e["height"] for e in placed]
        self.assertAlmostEqual(500.0, min(xs), places=2)
        self.assertAlmostEqual(300.0, min(ys), places=2)
        self.assertAlmostEqual(30.0, max(ys) - min(ys), places=2)

    def test_everything_shares_one_group(self):
        """图标常常是"图形 + 文字"好几个元素。挂同一个 groupId 有两个作用：
        用户在 Excalidraw 里拖动时它们一起动；以及本项目的
        "没有 groupId 的才算节点"这条判定会把图标当装饰 —— 正是想要的。"""
        placed = I.place(I.resolve(self.lib, "Linked Nodes"), 0, 0, key="icon-g")
        self.assertEqual(1, len({tuple(e["groupIds"]) for e in placed}))
        self.assertTrue(all(e["groupIds"] for e in placed), "没有 groupId 会被误当成节点")

    def test_source_is_not_mutated(self):
        """不能改调用方传进来的素材 —— 同一个图标会在多个节点上用。"""
        src = I.resolve(self.lib, "Bound Box")
        before = [dict(e) for e in src]
        I.place(src, 999, 999, key="icon-q")
        self.assertEqual(before, src)

    def test_two_placements_do_not_collide(self):
        src = I.resolve(self.lib, "Bound Box")
        a = I.place(src, 0, 0, key="icon-1")
        b = I.place(src, 200, 0, key="icon-2")
        self.assertEqual(set(), {e["id"] for e in a} & {e["id"] for e in b},
                         "同一个图标用两次，id 不能撞")

    def test_empty_item_places_nothing(self):
        self.assertEqual([], I.place([], 0, 0, key="icon-z"))


class TestRealLibrarySmoke(unittest.TestCase):
    """拿**真实素材库**过一遍（在 vault 里，不在仓库里）。

    没有就跳过 —— 素材库是几 MB 的第三方文件，不放仓库（体积 + 许可）。
    """

    PATH = os.path.expanduser(
        "~/Documents/obsidian/90 Assets/Excalidraw/my-obsidian-library.excalidrawlib")

    @unittest.skipUnless(os.path.isfile(PATH), "本机没有真实素材库，跳过")
    def test_every_item_can_be_placed_without_collisions(self):
        lib = I.load(self.PATH)
        self.assertGreater(len(lib["items"]), 100)
        checked = 0
        for name in I.names(lib):
            placed = I.place(lib["items"][name], 0, 0, key="probe")
            new_ids = {e["id"] for e in placed}
            self.assertEqual(len(new_ids), len(placed), f"{name}: id 有重复")
            for element in placed:
                for bound in element.get("boundElements") or []:
                    self.assertIn(bound["id"], new_ids,
                                  f"{name}: boundElements 悬空")
                if element.get("containerId"):
                    self.assertIn(element["containerId"], new_ids,
                                  f"{name}: containerId 悬空")
                for field in ("startBinding", "endBinding"):
                    binding = element.get(field)
                    if isinstance(binding, dict):
                        self.assertIn(binding["elementId"], new_ids,
                                      f"{name}: {field} 悬空")
            checked += 1
        self.assertEqual(len(lib["items"]), checked)


if __name__ == "__main__":
    unittest.main()


class TestIconWiring(unittest.TestCase):
    """规格里写了 `icon` → 端到端跑一遍：盒子加宽、场景里有它、不压文字。"""

    SPEC = {"type": "flow", "direction": "TB", "title": "带图标",
            "nodes": [{"id": "a", "kind": "service", "label": "订单服务", "icon": "Bound Box"},
                      {"id": "b", "kind": "data", "label": "订单库"}],
            "edges": [{"from": "a", "to": "b"}]}

    @classmethod
    def setUpClass(cls):
        path = os.path.join(SCRIPTS, "emit_excalidraw.py")
        spec = importlib.util.spec_from_file_location("emit_icons", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"加载不了 {path}")
        cls.E = importlib.util.module_from_spec(spec)
        sys.modules["emit_icons"] = cls.E
        spec.loader.exec_module(cls.E)

    def test_box_grows_by_the_icon(self):
        """图标是**外部尺寸来源** —— 盒子必须为它让出位置，否则会盖住文字。

        对照组要**不带 icon 字段**：带着它的 spec 即使不给尺寸表，
        也已经按保守占位加宽过了，两边都含占位就量不出图标的贡献。
        """
        without = {"type": "flow", "direction": "TB",
                   "nodes": [{"id": "a", "kind": "service", "label": "订单服务"}],
                   "edges": []}
        plain = self.E.L.boxes_from_spec(without)["a"]
        with_icon = self.E.L.boxes_from_spec(self.SPEC, {"a": (40.0, 22.0)})["a"]
        self.assertAlmostEqual(plain.width + 40.0 + self.E.L.ICON_GAP,
                               with_icon.width, places=6)
        self.assertGreaterEqual(with_icon.height, plain.height)

    def test_scene_contains_the_icon_and_it_is_grouped(self):
        """图标按 **id 前缀 `icon-`** 筛（组号里现在有嵌套：图标组 + 节点组）。"""
        scene, _, _, _ = self.E.emit(ICON_SPEC, library=V2)
        icons = [e for e in scene["elements"] if e["id"].startswith("icon-a")]
        # 默认只取图形：素材自带的文字被丢掉了（节点自己已经有标签）
        self.assertEqual(1, len(icons), "默认应当只剩图形那一个元素")
        self.assertEqual("rectangle", icons[0]["type"])
        # 图标要和形状、标签同组 —— 标签解绑之后，靠分组才能在编辑器里一起动
        node = next(e for e in scene["elements"] if e["id"] == "node-a")
        title = next(e for e in scene["elements"] if e["id"] == "title-a")
        self.assertIn(node["groupIds"][0], icons[0]["groupIds"])
        self.assertEqual(node["groupIds"], title["groupIds"])

    def test_full_mode_keeps_the_items_own_text(self):
        """`icon_full=True` 时保留素材自带的文字 —— 两条路都要真的不一样。"""
        scene, _, _, _ = self.E.emit(ICON_SPEC, library=V2, icon_full=True)
        icons = [e for e in scene["elements"] if e["id"].startswith("icon-a")]
        self.assertEqual(2, len(icons))
        self.assertIn("text", [e["type"] for e in icons])

    def test_icon_does_not_get_counted_as_a_node(self):
        """节点按 **id 前缀 `node-`** 认。

        旧判据是"有没有 groupIds"，带图标的节点引入分组后它不再成立：形状 / 标签
        / 图标挂同一个组号（标签解绑后要靠分组才能一起拖动），圆柱顶盖也带组号。
        这条**刻意用两个节点**：一个有图标、一个是圆柱，两种"带组号但不是装饰、
        或既装饰又同组"的情况都覆盖到。
        """
        two = {"type": "flow", "direction": "TB",
               "nodes": [{"id": "a", "kind": "service", "label": "订单服务",
                          "icon": "Bound Box"},
                         {"id": "b", "kind": "data", "label": "订单库"}],
               "edges": [{"from": "a", "to": "b"}]}
        scene, _, _, _ = self.E.emit(two, library=V2)
        # 节点 = `node-<规格里的 id>` 那个元素（圆柱顶盖是 `node-b-cap`，不是节点）
        want = {self.E._eid("node", n["id"]) for n in two["nodes"]}
        nodes = [e for e in scene["elements"] if e["id"] in want]
        self.assertEqual(2, len(nodes), "两个节点就是两个；图标与圆柱顶盖都不能算进去")
        self.assertEqual(want, {e["id"] for e in nodes})
        decorations = [e["id"] for e in scene["elements"]
                       if e["id"].startswith("icon-") or e["id"].endswith("-cap")]
        self.assertTrue(decorations, "这条测试得有装饰可查，否则等于没测")
        self.assertTrue(all(d not in want for d in decorations))

    def test_icon_hugs_the_visible_text(self):
        """图标要紧贴**可见文字**的左边 —— 不是紧贴文字元素那个盒子。

        文字元素是个**居中的盒子**（宽 = 断行宽度），可见文字在盒子里居中。
        按盒子左边对齐，间距会凭空多出一大截（用户原话：和文本间距是不是太大了），
        而且在真实 Excalidraw 里更糟：官方会把绑定文字拉回容器中心，
        于是成了「文字居中、图标丢在左边」（为什么图标这么靠左）。

        所以这条验的是**可见**的那条边，不是盒子的边。
        """
        scene, _, _, _ = self.E.emit(ICON_SPEC, library=V2)
        icons = [e for e in scene["elements"] if e["id"].startswith("icon-a")]
        icon_right = max(e["x"] + e["width"] for e in icons)
        title = next(e for e in scene["elements"] if e["id"].startswith("title-a"))
        visible_w = max(self.E.tm.weighted_units(line)
                        for line in title["text"].split("\n")) * title["fontSize"]
        visible_left = title["x"] + title["width"] / 2.0 - visible_w / 2.0
        self.assertAlmostEqual(self.E.layout_gap(), visible_left - icon_right, places=1,
                               msg="图标与可见文字之间的间隔不是设计值")

    def test_icon_group_is_centred_and_the_label_is_unbound(self):
        """带图标的节点：标签**解绑**，且 (图标 + 间隔 + 可见文字) 整组居中。

        官方会把 `containerId` 非空的文字拉回容器中心（我们写的 x 不算数），
        所以"整组居中"在**绑定**前提下数学上做不到 —— 实测偏左 19px，
        用户原话"图标和文本，不应该居中吗"。解绑后位置由我们定，这条守住它。
        """
        scene, _, _, _ = self.E.emit(ICON_SPEC, library=V2)
        node = next(e for e in scene["elements"] if e["id"] == "node-a")
        title = next(e for e in scene["elements"] if e["id"] == "title-a")
        self.assertIsNone(title["containerId"], "带图标的标签必须解绑，否则居中不了")
        icons = [e for e in scene["elements"] if e["id"].startswith("icon-a")]
        visible_w = max(self.E.tm.weighted_units(line)
                        for line in title["text"].split("\n")) * title["fontSize"]
        text_center = title["x"] + title["width"] / 2.0
        group_left = min(e["x"] for e in icons)
        group_right = max(text_center + visible_w / 2.0,
                          max(e["x"] + e["width"] for e in icons))
        self.assertAlmostEqual(node["x"] + node["width"] / 2.0,
                               (group_left + group_right) / 2.0, places=1,
                               msg="图标 + 文字的整组重心不在节点中心")

    def test_plain_node_keeps_the_label_bound(self):
        """没有图标的节点**保持绑定** —— 绑定文字在编辑器里会自动重排，更顺手。

        只有"整组居中"这一个理由值得解绑，没有图标的节点不该跟着付代价。
        """
        spec = {"type": "flow", "direction": "TB",
                "nodes": [{"id": "a", "kind": "service", "label": "订单服务"}],
                "edges": []}
        scene, _, _, _ = self.E.emit(spec)
        title = next(e for e in scene["elements"] if e["id"] == "title-a")
        self.assertEqual("node-a", title["containerId"])
        self.assertEqual([], title["groupIds"])

    def test_icon_stays_inside_the_padding(self):
        scene, _, _, _ = self.E.emit(ICON_SPEC, library=V2)
        node = next(e for e in scene["elements"] if e["id"] == "node-a")
        icon_left = min(e["x"] for e in scene["elements"]
                        if e["id"].startswith("icon-a"))
        self.assertGreaterEqual(icon_left, node["x"] + 4.0,
                                "图标越出了节点的边框")

    def test_icon_stays_inside_even_with_a_long_detail(self):
        """图标 + 长说明时图标也不能越出边框（用户截图里的溢出就是这个）。

        根因是算"可见文字宽度"时把说明行也乘了标题字号（说明实际是 12px）——
        高估 33%，说明一宽就把图标推到左边框外面。这条臂的两个用例分别卡
        "没有说明"与"有长说明"两种情况，只测前者是漏的。
        """
        detail = ("组合根里的 _LazyQAHistoryRepo：未接线时 reessors 必返 503，"
                  "而不是假装空列表；落库失败不影响已经给出的答案")
        for label, got_detail in (("QAHistoryRepo（延迟装配）", detail),
                                  ("q", "短说明")):
            spec = {"type": "flow", "direction": "TB", "detail": "diagnostic",
                    "nodes": [{"id": "a", "kind": "service", "label": label,
                               "detail": got_detail, "icon": "Bound Box"}],
                    "edges": []}
            scene, _, _, _ = self.E.emit(spec, library=V2)
            node = next(e for e in scene["elements"] if e["id"] == "node-a")
            icon = [e for e in scene["elements"] if e["id"].startswith("icon-a")]
            icon_left = min(e["x"] for e in icon)
            icon_right = max(e["x"] + e["width"] for e in icon)
            with self.subTest(label=label):
                self.assertGreaterEqual(
                    icon_left, node["x"] + 4.0,
                    f"图标越出了节点左边框（{label!r}）：图标左 {icon_left:.1f} < 框左 {node['x']:.1f}")
                self.assertLessEqual(
                    icon_right, node["x"] + node["width"] - 4.0,
                    f"图标越出了节点右边框（{label!r}）")

    def test_visible_width_uses_the_detail_own_font_size(self):
        """可见宽度取 max(标题行×16, 说明行×12) —— 不能拿标题字号乘说明行。

        否则同一张图里说明越长、图标越往左跳，最后跑到框外面 ——
        一个只有"真渲染"才看得出来、而数值上看不出错的偏移。
        """
        short = {"type": "flow", "direction": "TB",
                 "nodes": [{"id": "a", "kind": "service", "label": "订单服务",
                            "detail": "短说明", "icon": "Bound Box"}], "edges": []}
        long_detail = "；".join(["说明第一段要足够长才能把可见宽度推起来"] * 3)
        long = {"type": "flow", "direction": "TB",
                "nodes": [{"id": "a", "kind": "service", "label": "订单服务",
                           "detail": long_detail, "icon": "Bound Box"}], "edges": []}
        a = self.E.emit(short, library=V2)[0]
        b = self.E.emit(long, library=V2)[0]
        gap_a = self._icon_gap(a)
        gap_b = self._icon_gap(b)
        self.assertAlmostEqual(gap_a, gap_b, places=1,
                               msg="说明长短不同时图标↔文字间隔应当一致（设计值）")

    def _icon_gap(self, scene: dict) -> float:
        """图标右边界到可见文字左边界的间隔。"""
        icon = [e for e in scene["elements"] if e["id"].startswith("icon-a")]
        title = next(e for e in scene["elements"] if e["id"] == "title-a")
        detail = next(e for e in scene["elements"] if e["id"] == "detail-a")
        widest = max(
            max(self.E.tm.weighted_units(l) for l in title["text"].split("\n")) * title["fontSize"],
            max(self.E.tm.weighted_units(l) for l in detail["text"].split("\n")) * detail["fontSize"],
        )
        visible_left = title["x"] + title["width"] / 2.0 - widest / 2.0
        icon_right = max(e["x"] + e["width"] for e in icon)
        return visible_left - icon_right

    def _mixed_library(self, tmp: str) -> str:
        """造一个"作者风格不一致"的库：一项粗黑实心、一项细线空心。

        真实素材库里这很常见（不同作者 / 同一作者不同批次），也正是用户截图里
        "粗黑图标和细线图标混在一起"的来源。
        """
        path = os.path.join(tmp, "mixed.excalidrawlib")

        def rect(rid, stroke, width, bg):
            return {"id": rid, "type": "rectangle", "x": 0, "y": 0, "width": 40,
                    "height": 24, "angle": 0, "strokeColor": stroke,
                    "backgroundColor": bg, "fillStyle": "solid",
                    "strokeWidth": width, "strokeStyle": "solid", "roughness": 0,
                    "opacity": 100, "groupIds": [], "frameId": None, "roundness": None,
                    "seed": 1, "version": 1, "versionNonce": 1, "isDeleted": False,
                    "boundElements": [], "updated": 1, "link": None, "locked": False}

        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"type": "excalidrawlib", "version": 2, "libraryItems": [
                {"id": "bold", "name": "Bold", "elements": [
                    rect("b1", "#000000", 4, "#000000")]},
                {"id": "thin", "name": "Thin", "elements": [
                    rect("t1", "#888888", 1, "transparent")]},
                {"id": "dot", "name": "Dot", "elements": [
                    rect("d1", "#000000", 1, "transparent"),
                    {"id": "d2", "type": "ellipse", "x": 16, "y": 10, "width": 3,
                     "height": 3, "angle": 0, "strokeColor": "#000000",
                     "backgroundColor": "#000000", "fillStyle": "solid",
                     "strokeWidth": 1, "strokeStyle": "solid", "roughness": 0,
                     "opacity": 100, "groupIds": [], "frameId": None,
                     "roundness": None, "seed": 2, "version": 1, "versionNonce": 2,
                     "isDeleted": False, "boundElements": [], "updated": 1,
                     "link": None, "locked": False}]},
            ]}, fh)
        return path

    def test_icon_style_is_normalised(self):
        """图标落笔时统一：描边粗细 / 颜色（= 所属节点的描边色）/ 粗糙度 / 填充。

        素材的作者风格一律不保留 —— 否则同一张图里会出现粗黑与细线混排。
        """
        with tempfile.TemporaryDirectory() as tmp:
            lib = self._mixed_library(tmp)
            spec = {"type": "flow", "direction": "TB",
                    "nodes": [{"id": "a", "kind": "service", "label": "订单服务",
                               "icon": "Bold"},
                              {"id": "b", "kind": "service", "label": "支付服务",
                               "icon": "Thin"}],
                    "edges": [{"from": "a", "to": "b"}]}
            scene, _, _, _ = self.E.emit(spec, library=lib)
        icons = [e for e in scene["elements"] if e["id"].startswith("icon-")]
        self.assertEqual(2, len(icons))
        for el in icons:
            self.assertEqual(self.E.icons.ICON_STROKE_WIDTH, el["strokeWidth"],
                             "描边粗细必须统一")
            self.assertEqual(self.E.icons.ICON_ROUGHNESS, el["roughness"])
            self.assertEqual("solid", el["fillStyle"])
            self.assertEqual(100, el["opacity"])
        cols = {el["strokeColor"] for el in icons}
        self.assertEqual(1, len(cols), f"图标颜色必须统一（现在是 {cols}）")
        node = next(e for e in scene["elements"] if e["id"] == "node-a")
        self.assertEqual(node["strokeColor"], icons[0]["strokeColor"],
                         "图标应当与所属节点同色")
        # "大块实心"要转成空心（否则一张图里就是实心块 + 细线两套语言）
        self.assertTrue(all(e["backgroundColor"] == "transparent" for e in icons),
                        "大块实心没有被转成空心")

    def test_small_filled_details_are_kept_but_recoloured(self):
        """**小面积实心**（点 / 箭头头部）要保留 —— 那是设计细节，不是风格。

        一刀切"全部转空心"会把我们自己的 `_queue`（三个点）削成三个圈，
        也会把别家的箭头头部抹掉。
        """
        with tempfile.TemporaryDirectory() as tmp:
            lib = self._mixed_library(tmp)
            spec = {"type": "flow", "direction": "TB",
                    "nodes": [{"id": "a", "kind": "service", "label": "订单服务",
                               "icon": "Dot"}], "edges": []}
            scene, _, _, _ = self.E.emit(spec, library=lib)
        node = next(e for e in scene["elements"] if e["id"] == "node-a")
        icons = [e for e in scene["elements"] if e["id"].startswith("icon-a")]
        kept = [e for e in icons if e["backgroundColor"] != "transparent"]
        self.assertEqual(1, len(kept), f"应当只保留那个小点，实际保留了 {len(kept)} 个")
        self.assertEqual(node["strokeColor"], kept[0]["backgroundColor"],
                         "保留的实心也要换成同一个墨色，不引入第二种颜色")

    def test_sigil_and_library_icon_look_like_one_set(self):
        """同一张图里**混用**内置 sigil 与素材库图标时，风格必须仍然一致。

        这是用户截图里的场景（粗黑的库图标 + 细线的库图标/内置图形混排）。
        """
        with tempfile.TemporaryDirectory() as tmp:
            lib = self._mixed_library(tmp)
            builtin = sorted(self.E.sigils.NAMES)[0]   # 任意一个内置名（规范名或别名）
            spec = {"type": "flow", "direction": "TB",
                    "nodes": [{"id": "a", "kind": "service", "label": "订单服务",
                               "icon": builtin},
                              {"id": "b", "kind": "service", "label": "支付服务",
                               "icon": "Bold"}],
                    "edges": [{"from": "a", "to": "b"}]}
            scene, _, _, _ = self.E.emit(spec, library=lib)
        groups = {}
        for el in scene["elements"]:
            for gid in el.get("groupIds") or []:
                if gid.startswith("icon-"):
                    groups.setdefault(gid, []).append(el)
        self.assertEqual(2, len(groups), "两个节点各有一个图标")
        styles = {(e["strokeWidth"], e["strokeColor"], e["roughness"], e["fillStyle"])
                  for els in groups.values() for e in els}
        self.assertEqual(1, len(styles),
                         f"内置图形与素材库图标必须是一套风格，现在有 {len(styles)} 套：{styles}")

    def test_original_library_elements_are_not_mutated(self):
        """统一风格改的是**复制品**，不能把调用方（或库里）的元素改掉。"""
        with tempfile.TemporaryDirectory() as tmp:
            lib = self._mixed_library(tmp)
            spec = {"type": "flow", "direction": "TB",
                    "nodes": [{"id": "a", "kind": "service", "label": "订单服务",
                               "icon": "Bold"}], "edges": []}
            self.E.emit(spec, library=lib)
            with open(lib, encoding="utf-8") as fh:
                after = json.load(fh)
        el = after["libraryItems"][0]["elements"][0]
        self.assertEqual(4, el["strokeWidth"], "素材文件本身不该被改写")
        self.assertEqual("#000000", el["strokeColor"])

    def _colour_library(self, tmp: str) -> str:
        """造三种颜色情形的库：单色线描 / 多色但颜色都读得出来 / 多色且有的读不出来。"""
        path = os.path.join(tmp, "colours.excalidrawlib")

        def item(name: str, stroke: str, fill: str, rid: str) -> dict:
            return {"id": name, "name": name, "elements": [
                {"id": rid, "type": "rectangle", "x": 0, "y": 0, "width": 40,
                 "height": 24, "angle": 0, "strokeColor": stroke,
                 "backgroundColor": fill, "fillStyle": "solid", "strokeWidth": 2,
                 "strokeStyle": "solid", "roughness": 0, "opacity": 100,
                 "groupIds": [], "frameId": None, "roundness": None, "seed": 1,
                 "version": 1, "versionNonce": 1, "isDeleted": False,
                 "boundElements": [], "updated": 1, "link": None, "locked": False},
                {"id": rid + "b", "type": "line", "x": 4, "y": 4, "width": 20,
                 "height": 0, "points": [[0, 0], [20, 0]], "angle": 0,
                 "strokeColor": stroke, "backgroundColor": "transparent",
                 "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid",
                 "roughness": 0, "opacity": 100, "groupIds": [], "frameId": None,
                 "roundness": None, "seed": 2, "version": 1, "versionNonce": 2,
                 "isDeleted": False, "boundElements": [], "updated": 1,
                 "link": None, "locked": False}]}

        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"type": "excalidrawlib", "version": 2, "libraryItems": [
                item("Mono", "#123456", "transparent", "m1"),
                # 深色画布/浅色画布上都读得出来的两色
                item("Duo", "#232F3E", "#7BA7E0", "d1"),
                # 品牌橙在浅画布上对比度只有 2.04 —— 读不出来那一类
                item("Faint", "#232F3E", "#FF9900", "f1"),
            ]}, fh)
        return path

    def _emit_one(self, lib: str, icon: str, style: dict | None = None):
        spec = {"type": "flow", "direction": "TB", "style": style,
                "nodes": [{"id": "a", "kind": "service", "label": "订单服务",
                           "icon": icon}], "edges": []}
        scene, _, _, _ = self.E.emit(spec, library=lib)
        node = next(e for e in scene["elements"] if e["id"] == "node-a")
        icons = [e for e in scene["elements"] if e["id"].startswith("icon-a")]
        return node, icons

    def test_mono_icon_still_uses_the_node_ink(self):
        """单色素材是**线描图形**：一律用墨色（与图纸同一套语言）。"""
        with tempfile.TemporaryDirectory() as tmp:
            lib = self._colour_library(tmp)
            node, icons = self._emit_one(lib, "Mono")
        self.assertTrue(icons)
        self.assertTrue(all(e["strokeColor"] == node["strokeColor"] for e in icons),
                        "单色素材必须被换成节点墨色")

    def test_multicolour_icon_keeps_its_colours(self):
        """多色素材是**作品**（品牌 logo）：保留配色 —— 这就是用户要的"带颜色好看"。"""
        with tempfile.TemporaryDirectory() as tmp:
            lib = self._colour_library(tmp)
            node, icons = self._emit_one(lib, "Duo")
        strokes = {e["strokeColor"].lower() for e in icons}
        self.assertIn("#232f3e", strokes, "深蓝是素材原色，应当保留")
        self.assertNotEqual({node["strokeColor"].lower()}, strokes,
                            "多色素材不该被压成节点墨色")

    def test_faint_colour_is_darkened_to_a_readable_one(self):
        """读不出来的品牌色：**保留色相、压到可读**，而不是丢掉颜色或糊在画布上。"""
        with tempfile.TemporaryDirectory() as tmp:
            lib = self._colour_library(tmp)
            node, icons = self._emit_one(lib, "Faint")
        fills = {e["backgroundColor"] for e in icons if e["backgroundColor"] != "transparent"}
        self.assertTrue(fills, "多色素材的实心色块要保留（那是 logo 的一部分）")
        bg = self.E.palette.CANVAS["background"]
        for got in fills:
            self.assertGreaterEqual(
                round(self.E.palette.contrast(got, bg), 2), self.E.icons.ICON_MIN_CONTRAST,
                f"{got} 在画布上读不出来 —— 没被压暗")
        self.assertNotIn("#ff9900", {f.lower() for f in fills},
                         "原始品牌橙对比度不足，必须被压过")
        self.assertNotEqual({node["strokeColor"]}, fills,
                            "压暗不是直接换成墨色，应当保留色相")
        strokes = {e["strokeColor"].lower() for e in icons}
        self.assertIn("#232f3e", strokes, "读得出来的颜色不该被动")

    def test_ink_mode_forces_monochrome(self):
        """`style.icons = ink`：严格蓝图风，品牌 logo 也压成单色。"""
        with tempfile.TemporaryDirectory() as tmp:
            lib = self._colour_library(tmp)
            node, icons = self._emit_one(lib, "Duo", style={"icons": "ink"})
        self.assertTrue(all(e["strokeColor"] == node["strokeColor"] for e in icons))
        self.assertTrue(all(e["backgroundColor"] == "transparent" for e in icons),
                        "单色模式下大块实心要转空心")

    def test_native_mode_keeps_colours_untouched(self):
        """`style.icons = native`：原样保留，连对比度也不改（显式选择，后果自负）。"""
        with tempfile.TemporaryDirectory() as tmp:
            lib = self._colour_library(tmp)
            _node, icons = self._emit_one(lib, "Faint", style={"icons": "native"})
        fills = {e["backgroundColor"].lower() for e in icons
                 if e["backgroundColor"] != "transparent"}
        self.assertIn("#ff9900", fills, "native 档必须原样保留品牌色")

    def test_unknown_icon_colour_mode_is_refused(self):
        """未知取值要报错，不能静默当成 auto（与未知 kind 同一条规矩）。"""
        with tempfile.TemporaryDirectory() as tmp:
            lib = self._colour_library(tmp)
            spec = {"type": "flow", "direction": "TB", "style": {"icons": "colorful"},
                    "nodes": [{"id": "a", "kind": "service", "label": "订单服务",
                               "icon": "Mono"}], "edges": []}
            with self.assertRaises(Exception) as ctx:
                self.E.emit(spec, library=lib)
        self.assertIn("icons", str(ctx.exception))

    def test_no_icon_means_the_library_is_never_opened(self):
        """一个图标都不用的话，即使给了一个不存在的库也不该出错。"""
        spec = {"type": "flow", "direction": "TB",
                "nodes": [{"id": "a", "kind": "service", "label": "订单服务"}],
                "edges": []}
        scene, _, _, _ = self.E.emit(spec, library="/不存在的库.excalidrawlib")
        self.assertTrue(scene["elements"])

    def test_icon_without_a_library_fails_loudly(self):
        with self.assertRaises(self.E.icons.LibraryError) as ctx:
            self.E.emit(ICON_SPEC, library=None)
        self.assertIn("素材库", str(ctx.exception))

    def test_unknown_icon_name_fails_loudly(self):
        spec = {"type": "flow", "direction": "TB",
                "nodes": [{"id": "a", "kind": "service", "label": "订单服务",
                           "icon": "根本没有这个素材"}],
                "edges": []}
        with self.assertRaises(self.E.icons.LibraryError) as ctx:
            self.E.emit(spec, library=V2)
        self.assertIn("Bound Box", str(ctx.exception), "报错要列出可用的名字")

    def test_empty_icon_name_is_rejected_by_the_validator(self):
        spec = {"type": "flow", "direction": "TB",
                "nodes": [{"id": "a", "kind": "service", "label": "订单服务",
                           "icon": "  "}],
                "edges": []}
        with self.assertRaises(self.E.SpecError):
            self.E.emit(spec, library=V2)


class TestIconReadability(unittest.TestCase):
    """素材自带的文字缩到看不清时要报出来 —— 这是**选型问题**，不是布局问题。

    来历：拿真实素材库跑了一遍，图长得没错，但图标里自带的标签缩成了 2px 噪点。
    根因是那个库是厂商**示意图**集合（图形 + 自带文字），不是图标集。
    纯机械判断（外部文件里的字号 × 缩放比），所以做成检查而不是文档里的一句提醒。
    """

    @classmethod
    def setUpClass(cls):
        path = os.path.join(SCRIPTS, "emit_excalidraw.py")
        spec = importlib.util.spec_from_file_location("emit_read", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"加载不了 {path}")
        cls.E = importlib.util.module_from_spec(spec)
        sys.modules["emit_read"] = cls.E
        spec.loader.exec_module(cls.E)

    def test_font_size_scales_with_the_icon(self):
        lib = I.load(V2)
        elements = I.resolve(lib, "Bound Box")          # 文字 fontSize=16，盒子高 60
        self.assertEqual([10.0], I.scaled_font_sizes(elements, 37.5))
        self.assertAlmostEqual(16.0, I.scaled_font_sizes(elements, 60.0)[0])

    def test_the_smallest_text_decides_not_the_largest(self):
        """一个素材里有两处文字时，**小的那处**先变成噪点 —— 判据必须取最小。

        这条是被一次变异逼出来的：合成素材里原来只有一个文字元素（min == max），
        所以把 `min` 改成 `max` 测试照样全绿 —— 测不出这个 bug 的测试等于没测。
        """
        lib = I.load(V2)
        elements = I.resolve(lib, "Two Sizes")      # 字号 24 与 10，素材高 60
        sizes = I.scaled_font_sizes(elements, 30.0)  # 缩放 0.5
        self.assertEqual([12.0, 5.0], sizes)
        smallest, _scale = I.readability(elements, 30.0)
        self.assertAlmostEqual(5.0, smallest, msg="取的是最大那个字号")
        self.assertLess(smallest, I.MIN_LEGIBLE_PT, "5px 应当被判为看不清")

    def test_items_without_text_are_never_flagged(self):
        """纯图形素材没有可读性问题 —— 不能把所有图标都报一遍。"""
        lib = I.load(V2)
        plain = [e for e in I.resolve(lib, "Linked Nodes")]
        self.assertIsNone(I.readability(plain))

    def test_glyph_mode_never_reports_illegible_text(self):
        """默认只取图形 → 素材自带的文字根本不进来，**这个提示从构造上不会出现**。

        这比"报个警告让人去改"强：不是检测到了问题再提醒，是这个问题不存在。
        """
        _, _, outcome, _ = self.E.emit(ICON_SPEC, library=V2)
        self.assertEqual([], [i for i in outcome.issues if i.check == "icon"])

    def test_full_mode_reports_illegible_text(self):
        """保留自带文字时才会撞上可读性 —— 这时报出来是**选型提示**，不阻塞。"""
        _, _, outcome, _ = self.E.emit(ICON_SPEC, library=V2, icon_full=True)
        got = [i for i in outcome.issues if i.check == "icon"]
        self.assertEqual(1, len(got), f"应当报 1 条，实得 {len(got)}")
        self.assertFalse(got[0].blocking, "这是选型提示，不该阻塞出图")
        self.assertIn("看不清", got[0].detail)
        self.assertIn("换一个", got[0].advice or "", "建议要是内容级的")

    def test_bigger_icon_clears_the_warning_in_full_mode(self):
        """把图标调大到自带文字可读，提示就该消失 —— 否则这条检查会变成噪音。"""
        _, _, outcome, _ = self.E.emit(ICON_SPEC, library=V2, icon_full=True,
                                       icon_height=60.0)
        self.assertEqual([], [i for i in outcome.issues if i.check == "icon"])


class TestGlyphOnly(unittest.TestCase):
    """默认只取图形 —— 这一条是"图标又小又糊"的根因修复。"""

    def test_text_elements_are_dropped(self):
        lib = I.load(V2)
        full = I.resolve(lib, "Bound Box")
        glyph = I.glyph_only(full)
        self.assertEqual(1, len(glyph))
        self.assertNotIn("text", [e["type"] for e in glyph])

    def test_items_without_text_are_returned_unchanged(self):
        lib = I.load(V2)
        plain = I.resolve(lib, "Linked Nodes")
        self.assertEqual(plain, I.glyph_only(plain))

    def test_a_text_only_item_is_not_emptied(self):
        """整项只有文字时不能返回空数组 —— 空数组会让节点上什么都不显示，而且不报错。"""
        only_text = [{"id": "t", "type": "text", "x": 0, "y": 0, "width": 10,
                      "height": 10, "fontSize": 16}]
        self.assertEqual(only_text, I.glyph_only(only_text))

    def test_the_same_height_now_gives_a_bigger_glyph(self):
        """丢掉标签之后，图形在同样的高度里占得更满 —— 这就是"看起来更大"从哪来。"""
        lib = I.load(V2)
        full = I.resolve(lib, "Bound Box")          # 框 0..60，文字在 20..40
        glyph = I.glyph_only(full)
        self.assertEqual((100.0, 60.0), I.intrinsic_size(full))
        w, h = I.intrinsic_size(glyph)
        self.assertEqual((100.0, 60.0), (w, h),
                         "这一项的标签在框内，所以外框不变 —— 变大的是"
                         "**不再有噪点**，以及可以用更大的目标高度")

    def test_height_adapts_to_the_node(self):
        """按节点自己的高度算 —— 用户要的"适配每一个元素"。"""
        small = I.height_for(28.0)                  # 单行小节点
        big = I.height_for(64.0)                    # 两行带 detail 的节点
        self.assertLess(small, big, "大节点的图标该更大")
        self.assertGreaterEqual(small, I.ICON_MIN, "不能小到看不清")
        self.assertLessEqual(big, I.ICON_MAX, "不能大到失衡")
        self.assertEqual(I.ICON_MAX, I.height_for(500.0), "要夹住上限")


class TestIconColourClash(unittest.TestCase):
    """图标自带品牌色**不随主题变** —— 在深色主题下可能直接看不见（#91）。"""

    @classmethod
    def setUpClass(cls):
        path = os.path.join(SCRIPTS, "emit_excalidraw.py")
        spec = importlib.util.spec_from_file_location("emit_clash", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"加载不了 {path}")
        cls.E = importlib.util.module_from_spec(spec)
        sys.modules["emit_clash"] = cls.E
        spec.loader.exec_module(cls.E)

    def test_visible_colours_skips_transparent(self):
        """线框图标只有描边色 —— 把 transparent 也拿去算对比度是无意义的。"""
        got = I.visible_colours([
            {"strokeColor": "#333333", "backgroundColor": "transparent"},
            {"strokeColor": "#888888", "backgroundColor": "#EEEEEE"},
        ])
        self.assertEqual(["#333333", "#888888", "#EEEEEE"], got)

    @staticmethod
    def _spec(theme=None):
        """方向要写进**规格**，不能用 `palette.use_direction()` —— emit 会按规格重置它。

        这条踩过：测试里切了主题，emit 一进来就按规格（没有 theme 字段）重置回默认，
        于是两次跑的都是同一个主题，断言看起来像"行为反了"。
        """
        spec = json.loads(json.dumps(ICON_SPEC))
        if theme:
            spec["visual"] = theme
        return spec

    def test_dark_icon_on_dark_fill_is_reported(self):
        """合成素材的元素是 #333333 描边；放到深色主题的深填充上就该报。"""
        _, _, light_outcome, _ = self.E.emit(self._spec(), library=V2)
        _, _, dark_outcome, _ = self.E.emit(self._spec("night"), library=V2)
        light = [i for i in light_outcome.issues if i.check == "icon"]
        dark = [i for i in dark_outcome.issues if i.check == "icon"]
        self.assertEqual([], light, "浅色主题下不该报撞色")
        self.assertEqual(1, len(dark), f"深色主题下应当报 1 条，实得 {len(dark)}")
        self.assertIn("看不见", dark[0].detail)
        self.assertFalse(dark[0].blocking, "这是选型提示，不该阻塞出图")
        self.assertIn("不建议自动改色", dark[0].advice or "",
                      "建议里要说明为什么不自动改色")

    def test_bright_icon_on_dark_fill_is_fine(self):
        """亮色图标在深色底上没问题 —— 这条检查不能把所有图标都报一遍。"""
        lib = I.load(V2)
        bright = json.loads(json.dumps(lib["items"]["Bound Box"]))
        for el in bright:
            el["strokeColor"] = "#EEEEEE"
        directory = tempfile.mkdtemp(prefix="bright-")
        path = os.path.join(directory, "lib.excalidrawlib")
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"type": "excalidrawlib", "version": 2, "libraryItems": [
                    {"id": "i", "name": "Bound Box", "elements": bright}]},
                    fh, ensure_ascii=False)
            _, _, outcome, _ = self.E.emit(self._spec("night"), library=path)
            self.assertEqual([], [i for i in outcome.issues if i.check == "icon"])
        finally:
            shutil.rmtree(directory, ignore_errors=True)


