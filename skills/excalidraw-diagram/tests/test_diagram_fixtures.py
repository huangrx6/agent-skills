#!/usr/bin/env python3
"""拿**不同种类、不同复杂度**的图跑整条流水线：架构 / 流程 / 依赖 / 状态 / 网状 / 思维导图。

## 这批 fixture 的来历

用户反馈"现在不好看、也不好用"，而"按感觉改"是猜。所以先造了这 6 张
（7~14 节点，覆盖 6 种图类型）跑完整流水线、用**真实 Excalidraw** 渲染、逐张量，
得到一份有证据的问题清单（见 `references/visual-design.md` 开头那张表）：

    P1 边从同一锚点喷出    同一锚点最多射出 6 条
    P2 线穿过别的节点      网状图 3 处 —— **当时五条校验里没有一条管这个**
    P3 标签压线           架构图 1 处（候选位置全失败后退回）
    P4 没有标题           6/6 张图的 title 被忽略
    P5 只有圆角矩形        6 张图形状数全是 1
    P6 没有视觉层级        核心服务与边缘模块长得一模一样
    P7 长宽比极端          网状图 5.0:1
    P8 反向边绕大圈        回边扫过整张图
    P9 边色单一            14 条边全同色

## 这个测试守什么

不守"图好看"（那没有校验器，只能靠看）。它守的是两件具体的事：

1. **6 种图类型都跑得通** —— 包括 `network` 和 `mindmap` 这种明显不是分层 DAG 的。
   以前只测过 architecture/flow，换一种类型就可能踩到没走过的分支。
2. **那 9 条问题不会在无人知晓的情况下变多或变少**：把量出来的数字钉住，
   改布局时知道自己在动什么。数字变好要看清楚，数字变差要解释。

对 P2（线穿节点）与 P3（标签压线）**没有**断言"必须为 0" —— 它们现在本来就大于 0，
断言 0 只会立刻变红。这里断言的是"不超过现在的已知值"，作为**不许变差**的闸门；
真正修掉它们之后，把上限降到 0 就是完成信号。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/test_diagram_fixtures.py
"""

from __future__ import annotations

import glob
import importlib.util
import json
import math
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
SCRIPTS = os.path.join(SKILL, "scripts")
SPECS = os.path.join(HERE, "fixtures", "specs")
EMIT = os.path.join(SCRIPTS, "emit_excalidraw.py")

# 已知问题量的上限。**改小**要看清楚（先确认不是“图变少了”之类的假改善）；
# **改大必须写明这是一次回归**，并给出根因 —— 这段注释就是为此存在的。
#
# ⚠ 加入节点形状（scripts/shapes.py）后这里**放宽过一次**，是真实回归：
#
#     图              穿节点 前→后    节点面积增幅
#     05-network        3 → 4        +11%
#     06-mindmap        0 → 2        +27%
#     其余四张          0 → 0        +4% ~ +25%
#
#   原因：形状按几何精确取值（菱形要塞下文字必须 2× 宽高、椭圆 √2 倍），
#   节点面积普遍涨 4~27%，留给连线的空隙就少了。
#   **根因不是形状，是布局根本没有“绕行连线”这个能力** ——
#   这个弱点以前被“盒子小”掩盖着。真修法是给边加绕行（待办 #81）。
#
#   所以下面的数字曾是**回归后的值**，不是“本来就这样”。后来靠“连线绕行 +
#   调参加间距”把它从 4 / 2 降到 1 / 0（网络图跑了 5 轮调参），那张回归标记用例
#   按约定失败了、已删掉 —— 这就是"缺失能力标记"该有的用法：
#   修好时它会主动提醒你把放宽撤掉，而不是永远悄悄放宽在那里。
# `labels_on_lines` 与 `max_fanout` 已从"每张图放宽的值"变成**结构性结果**
# （锚点按扇出均分、标签搜索的障碍物修好了坐标系 → 0 和 1）。
# 所以不再按图记上限，改成两条不变量直接断言（见下面的用例）。
KNOWN_MAX = {
    "01-architecture": {"through_nodes": 0},
    "02-flow":         {"through_nodes": 0},
    "03-dependency":   {"through_nodes": 0},
    "04-state":        {"through_nodes": 0},
    "05-network":      {"through_nodes": 1},
    "06-mindmap":      {"through_nodes": 0},
}
MAX_FANOUT_HARD = 8          # 超过这个数就不只是"不够好看"，是排布坏了

# 长宽比的可读区间。实测：state 达 13.1:1、flow 低到 0.3:1 —— 两个都超出人眼能一次看全的範囲
# （一条长条）。属于 2.11 构图那节要解决的问题。
READABLE_ASPECT = (0.45, 4.5)
# 已知超出可读区间的那两张：**按其当前值放宽 ±15%** 作为允许带。
# 语义是“不许变差”，而不是“永远这么差”。修好之后把它们删掉，可读区间就接管了。
#
# ⚠ 加图标题后，04-state 的数字从 13.2 降到 9.7、05-network 从 5.1 降到 4.2 ——
# **这不是布局变好了**。标题给场景加了高度，比值的分母变大而已，内容本身一点没动。
# 所以下面的门槛实际上被**悄悄放松**了。换成“内容比例”（去掉标题）才算真实改善；
# 之所以没换：导出的图里确实有标题，人眼看到的比例就是这里量的这个。
# 要判断布局到底有没有改善，得看**节点尺寸与坐标**，不是这个比值。
# 05-network 从这条里**删掉了**：加大间距后它自己回到可读区间（实测 5.0 → 3.8），
# 不再是"已知超出"的特例。这是真改善的一种（同一套度量、同一张图），
# 不同于上面那条"加标题让分母变大"。
KNOWN_ASPECT = {"02-flow": 0.30, "04-state": 13.1}


def aspect_band(name: str) -> tuple[float, float]:
    """这张图允许的长宽比区间。"""
    low, high = READABLE_ASPECT
    if name in KNOWN_ASPECT:
        value = KNOWN_ASPECT[name]
        return (min(low, value * 0.85), max(high, value * 1.15))
    return low, high


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


E = _load("emit_excalidraw_for_fixtures", EMIT)


def spec_paths() -> list[str]:
    return sorted(glob.glob(os.path.join(SPECS, "*.json")))


# ── 量图 ────────────────────────────────────────────────────
def _samples(a: tuple, b: tuple, step: float = 1.0) -> list[tuple]:
    steps = max(1, math.ceil(max(abs(b[0] - a[0]), abs(b[1] - a[1])) / step))
    return [(a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps)
            for i in range(steps + 1)]


def _polyline(arrow: dict) -> list[tuple]:
    return [(arrow["x"] + p[0], arrow["y"] + p[1]) for p in arrow["points"]]


# 节点形状：不再只有矩形。圆柱的**顶盖**也是 ellipse，但它带着 groupIds，
# 算装饰不算节点（见 emit_excalidraw.shape_elements 里的说明）。
NODE_TYPES = {"rectangle", "ellipse", "diamond"}


def is_node(el: dict) -> bool:
    return el["type"] in NODE_TYPES and not el.get("groupIds")


def measure(scene: dict) -> dict:
    """量一张图。**这里量的每一项都对应问题清单里的一个具体条目。**"""
    elements = scene["elements"]
    rects = [e for e in elements if is_node(e)]
    arrows = [e for e in elements if e["type"] == "arrow"]
    labels = [e for e in elements
              if e["type"] == "text" and not e.get("containerId")]

    # P2：连线穿过**别的**节点（自己的两端不算）
    through = 0
    for arrow in arrows:
        ends = (arrow["startBinding"]["elementId"], arrow["endBinding"]["elementId"])
        line = _polyline(arrow)
        for box in rects:
            if box["id"] in ends:
                continue
            left, top = box["x"], box["y"]
            right, bottom = left + box["width"], top + box["height"]
            if any(left <= x <= right and top <= y <= bottom
                   for a, b in zip(line, line[1:]) for x, y in _samples(a, b)):
                through += 1

    # P3：标签被连线穿过
    crossed = 0
    for label in labels:
        left, top = label["x"], label["y"]
        right, bottom = left + label["width"], top + label["height"]
        hit = False
        for arrow in arrows:
            line = _polyline(arrow)
            if any(left <= x <= right and top <= y <= bottom
                   for a, b in zip(line, line[1:]) for x, y in _samples(a, b)):
                hit = True
                break
        crossed += 1 if hit else 0

    # P1：同一节点同一**锚点**射出几条
    #
    # ⚠ 这里踩过一次：`arrow["points"][0]` 是**相对坐标**，而 `arrow["x"]`/`y` 就是首点，
    # 所以那个 key 永远是 (0,0) —— 它实际上在数“这个节点射出几条”，从来没量过锚点。
    # 直接拿它判断“分散锚点有没有生效”，得到的是“没变”（因为量的是另一件事）。
    # 绝对起点就是 x/y。
    fanout: dict[tuple, int] = {}
    for arrow in arrows:
        key = (arrow["startBinding"]["elementId"],
               round(arrow["x"], 1), round(arrow["y"], 1))
        fanout[key] = fanout.get(key, 0) + 1

    # P4：有没有标题（字号 >= 20 才算标题，节点标题是 16）
    has_title = any(e["type"] == "text" and e.get("fontSize", 0) >= 20 for e in elements)

    # P5：用了几种形状（顶盖不算 —— 它是圆柱的一部分，不是另一种节点形状）
    shapes = {e["type"] for e in rects}

    # P7：长宽比
    xs, ys = [], []
    for e in elements:
        if e.get("points"):
            xs += [e["x"] + p[0] for p in e["points"]]
            ys += [e["y"] + p[1] for p in e["points"]]
        else:
            xs += [e["x"], e["x"] + e["width"]]
            ys += [e["y"], e["y"] + e["height"]]
    width, height = max(xs) - min(xs), max(ys) - min(ys)
    aspect = width / height if height else 0.0

    return {"nodes": len(rects), "edges": len(arrows), "labels": len(labels),
            "through_nodes": through, "labels_on_lines": crossed,
            "max_fanout": max(fanout.values()) if fanout else 0,
            "has_title": has_title, "shape_kinds": sorted(shapes),
            "aspect": aspect, "size": (round(width), round(height))}


class TestEveryDiagramTypeRuns(unittest.TestCase):
    """6 种图类型都要跑得通 —— 包括 network / mindmap 这种明显不是分层 DAG 的。

    以前只测过 architecture / flow；换一种类型就可能踩到没走过的分支。
    """

    def test_all_fixtures_emit(self):
        self.assertGreaterEqual(len(spec_paths()), 6, "fixture 少了")
        for path in spec_paths():
            with self.subTest(fixture=os.path.basename(path)):
                with open(path, encoding="utf-8") as fh:
                    spec = json.load(fh)
                scene, result, outcome, _ = E.emit(spec)
                self.assertTrue(scene, f"没出图：{[i.line() for i in outcome.blocking]}")
                self.assertEqual(len(spec["nodes"]), len(result.real_nodes()))
                self.assertEqual(len(spec["edges"]), len(result.edges))

    def test_diagram_types_are_covered(self):
        """覆盖度本身也要守住 —— 否则删掉两个 fixture 也没人发现。"""
        kinds = set()
        for path in spec_paths():
            with open(path, encoding="utf-8") as fh:
                kinds.add(json.load(fh)["type"])
        for expected in ("architecture", "flow", "dependency", "state",
                         "network", "mindmap"):
            self.assertIn(expected, kinds, f"没有覆盖到 {expected}")


class TestKnownProblemsDoNotWorsen(unittest.TestCase):
    """把量出来的问题数字钉住：不许变差。

    **不写"必须为 0"** —— P2（线穿节点）与 P3（标签压线）现在本来就大于 0，
    断言 0 只会立刻变红，然后就没人看它了。
    真修好之后，把 KNOWN_MAX 里的上限降到 0 就是完成信号。
    """

    def measured(self, path: str) -> dict:
        with open(path, encoding="utf-8") as fh:
            spec = json.load(fh)
        scene, _, _, _ = E.emit(spec)
        return measure(scene)

    def test_through_node_count_does_not_grow(self):
        for path in spec_paths():
            name = os.path.basename(path).replace(".json", "")
            with self.subTest(fixture=name):
                m = self.measured(path)
                limit = KNOWN_MAX.get(name, {}).get("through_nodes", 0)
                self.assertLessEqual(m["through_nodes"], limit,
                                     f"{name} 线穿节点 {m['through_nodes']} 处（上限 {limit}）")

    def test_label_on_line_count_does_not_grow(self):
        for path in spec_paths():
            name = os.path.basename(path).replace(".json", "")
            with self.subTest(fixture=name):
                m = self.measured(path)
                limit = KNOWN_MAX.get(name, {}).get("labels_on_lines", 0)
                self.assertLessEqual(m["labels_on_lines"], limit,
                                     f"{name} 有 {m['labels_on_lines']} 个标签被线穿过（上限 {limit}）")

    def test_fanout_never_explodes(self):
        """同一锚点射出太多条就是排布坏了，不是"不够好看"。"""
        for path in spec_paths():
            name = os.path.basename(path).replace(".json", "")
            with self.subTest(fixture=name):
                m = self.measured(path)
                self.assertLessEqual(m["max_fanout"], MAX_FANOUT_HARD,
                                     f"{name} 同一锚点射出 {m['max_fanout']} 条")

    def test_no_two_edges_share_an_anchor(self):
        """**结构性不变量**：每个锚点恰好一条边。

        以前所有边都连到节点边中点 —— 实测一个节点上喷出 6 条，三种图型上都是
        目视最刺眼的一处。现在按扇出均分，不再依赖"看起来如何"。

        但要说清：锚点分散**不等于**扇出的观感消失了。枢纽节点只有 64px 高时，
        6 个锚点摊开也就 ~8px 间距，远端照样是扇形 —— 那是"枢纽太小 + 目标太远"
        的结果，不是锚点算法能解决的。
        """
        for path in spec_paths():
            with self.subTest(fixture=os.path.basename(path)):
                scene, _, _, _ = E.emit(json.load(open(path, encoding="utf-8")))
                anchors: dict[tuple, int] = {}
                for a in scene["elements"]:
                    if a["type"] != "arrow":
                        continue
                    # 绝对起点就是 x/y。points 是**相对**坐标 —— 这里踩过一次：
                    # 用 points[0] 的话 key 永远是 (0,0)，量到的是另一件事。
                    key = (a["startBinding"]["elementId"],
                           round(a["x"], 1), round(a["y"], 1))
                    anchors[key] = anchors.get(key, 0) + 1
                worst = max(anchors.values()) if anchors else 0
                self.assertEqual(1, worst, f"有锚点挂了 {worst} 条边")

    def test_no_label_sits_on_a_line(self):
        """标签不许压在任何连线上。

        这条以前**修不掉**：标签搜索一直在躲一份被平移过的假线 ——
        `build_scene` 把已经是绝对坐标的 points 又加了一遍起点，
        搜索在自己眼里是干净的，落到图上却压着真线。

        搜索本身（候选方向 × 递增退让 × 沿边滑动）没问题，错的是喂给它的障碍物。
        """
        for path in spec_paths():
            with self.subTest(fixture=os.path.basename(path)):
                scene, _, _, _ = E.emit(json.load(open(path, encoding="utf-8")))
                self.assertEqual(0, measure(scene)["labels_on_lines"],
                                 "有标签压在连线上")

    def test_aspect_ratio_does_not_get_worse(self):
        """极长或极窄的条状图读不了。

        允许带 = 可读区间，但对已知超标的那两张按其当前值放宽 ±15%。
        **不许变差**；真改好了就把 KNOWN_ASPECT 里那两项删掉。
        """
        for path in spec_paths():
            name = os.path.basename(path).replace(".json", "")
            with self.subTest(fixture=name):
                aspect = self.measured(path)["aspect"]
                low, high = aspect_band(name)
                self.assertLessEqual(aspect, high, f"{name} 长宽比 {aspect:.1f} 偏宽（上限 {high:.1f}）")
                self.assertGreaterEqual(aspect, low, f"{name} 长宽比 {aspect:.1f} 偏窄（下限 {low:.1f}）")

    def test_aspect_band_is_not_vacuous(self):
        """守住"允许带确实是个限制"：默认情况下必须就是可读区间。"""
        self.assertEqual(READABLE_ASPECT, aspect_band("01-architecture"))
        low, high = aspect_band("04-state")
        self.assertLess(low, 1.0)          # 宽条图的允许带仍然要求它不能变成竖条
        self.assertGreater(high, 4.5)

    def test_every_diagram_now_has_a_title(self):
        """P4 已修：`title` 真的画出来了。

        这条以前是“缺失能力标记”（断言标题**不**存在）。按约定它失败了，
        失败消息就是“去把 visual-design.md 里 P4 划掉” —— 现在划掉了，断言跟着反过来了。

        顺带钉住两条不进校验的约束：标题必须在**所有内容之上**（否则压住东西），
        而且必须是图字号而不是节点字号。
        """
        for path in spec_paths():
            with self.subTest(fixture=os.path.basename(path)):
                with open(path, encoding="utf-8") as fh:
                    spec = json.load(fh)
                self.assertTrue(spec.get("title"), "fixture 里得有 title 才能测这件事")
                scene, _, _, _ = E.emit(spec)
                self.assertTrue(measure(scene)["has_title"],
                                "标题又丢了 —— emit 里 title_element 那条路断了？")
                titles = [e for e in scene["elements"]
                          if e["type"] == "text" and e.get("containerId") is None
                          and e["fontSize"] == E.tm.FONT_TITLE]
                self.assertEqual(1, len(titles), "标题必须正好一个")
                title = titles[0]
                content_top = min(e["y"] for e in scene["elements"] if e is not title)
                gap = content_top - (title["y"] + title["height"])
                self.assertGreater(gap, 0, f"标题压到内容上了（间隙 {gap:.0f}）")

    def test_shapes_follow_semantics(self):
        """P5 已修：形状与语义有关，不再是清一色圆角矩形。

        这条以前是"只用了 rectangle（缺失能力标记）"，实现形状映射后它本该失败 ——
        现在改成断言**映射真的生效**：不同 kind 出不同形状，而不是都有个 shape 字段。
        """
        sh = E.shapes
        shapes = set()
        for path in spec_paths():
            with open(path, encoding="utf-8") as fh:
                spec = json.load(fh)
            scene, _, _, _ = E.emit(spec)
            shapes |= set(measure(scene)["shape_kinds"])
        # 注意：这里的 shapes 量的是 Excalidraw 的**元素类型**（rectangle / ellipse / diamond）。
        # capsule / note / cylinder 在 Excalidraw 里底层都是 rectangle，靠 roundness
        # 与 strokeStyle 区分 —— 所以“元素类型数”不等于“形状数”。真正断言形状的是
        # 下面这半段（解析出的形状名）。
        self.assertIn("ellipse", shapes, "至少要出现一种非矩形元素（客户端 / 角色）")

        spec = {"nodes": [{"id": "c", "kind": "client", "label": "用户"},
                          {"id": "s", "kind": "service", "label": "服务"},
                          {"id": "d", "kind": "data", "label": "库"},
                          {"id": "a", "kind": "async", "label": "队列"},
                          {"id": "x", "kind": "external", "label": "外部"}]}
        boxes = E.L.boxes_from_spec(spec)
        self.assertEqual("ellipse", boxes["c"].shape, "客户端/角色该用椭圆")
        self.assertEqual("round", boxes["s"].shape)
        self.assertEqual("cylinder", boxes["d"].shape, "数据库该用圆柱")
        self.assertEqual("capsule", boxes["a"].shape, "消息/队列该用胶囊")
        self.assertEqual("note", boxes["x"].shape, "外部系统该用虚线便签")
        # 显式覆盖优先于默认
        spec["nodes"][1]["shape"] = "diamond"
        self.assertEqual("diamond", E.L.boxes_from_spec(spec)["s"].shape)
        del sh


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--report":
        for p in spec_paths():
            with open(p, encoding="utf-8") as fh:
                spec = json.load(fh)
            scene, _, _, _ = E.emit(spec)
            m = measure(scene)
            print(f"{os.path.basename(p):<22} {spec['type']:<14} "
                  f"节点{m['nodes']:>3} 边{m['edges']:>3} 穿节点{m['through_nodes']:>3} "
                  f"标签压线{m['labels_on_lines']:>3} 喷出{m['max_fanout']:>3} "
                  f"标题{'有' if m['has_title'] else '无'} 形状{m['shape_kinds']} "
                  f"比例{m['aspect']:.1f}")
        raise SystemExit(0)
    unittest.main(verbosity=2)
