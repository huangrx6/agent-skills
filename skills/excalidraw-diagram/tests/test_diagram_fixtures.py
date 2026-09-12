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

# 已知问题量的上限。改布局让这些数字变小时：把上限跟着降下来。
# 变小时不要只是"顺手更新数字"——先确认那不是"图变少了"之类的假改善。
KNOWN_MAX = {
    "01-architecture": {"through_nodes": 0, "labels_on_lines": 1, "max_fanout": 6},
    "02-flow":         {"through_nodes": 0, "labels_on_lines": 0, "max_fanout": 2},
    "03-dependency":   {"through_nodes": 0, "labels_on_lines": 0, "max_fanout": 3},
    "04-state":        {"through_nodes": 0, "labels_on_lines": 0, "max_fanout": 2},
    "05-network":      {"through_nodes": 3, "labels_on_lines": 0, "max_fanout": 4},
    "06-mindmap":      {"through_nodes": 0, "labels_on_lines": 0, "max_fanout": 6},
}
MAX_FANOUT_HARD = 8          # 超过这个数就不只是"不够好看"，是排布坏了

# 长宽比的可读区间。实测：state 达 13.1:1、flow 低到 0.3:1 —— 两个都超出人眼能一次看全的範囲
# （一条长条）。属于 2.11 构图那节要解决的问题。
READABLE_ASPECT = (0.45, 4.5)
# 已知超出可读区间的那两张：**按其当前值放宽 ±15%** 作为允许带。
# 语义是“不许变差”，而不是“永远这么差”。修好之后把它们删掉，可读区间就接管了。
KNOWN_ASPECT = {"02-flow": 0.30, "04-state": 13.1, "05-network": 5.0}


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


def measure(scene: dict) -> dict:
    """量一张图。**这里量的每一项都对应问题清单里的一个具体条目。**"""
    elements = scene["elements"]
    rects = [e for e in elements if e["type"] == "rectangle"]
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

    # P1：同一节点同一锚点射出几条
    fanout: dict[tuple, int] = {}
    for arrow in arrows:
        key = (arrow["startBinding"]["elementId"],
               round(arrow["points"][0][0], 1), round(arrow["points"][0][1], 1))
        fanout[key] = fanout.get(key, 0) + 1

    # P4：有没有标题（字号 >= 20 才算标题，节点标题是 16）
    has_title = any(e["type"] == "text" and e.get("fontSize", 0) >= 20 for e in elements)

    # P5：用了几种形状
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

    def test_problems_are_still_unfixed_marker(self):
        """把"还有哪些没修"写成断言，免得它随时间变成"本来就这样"。

        这条故意会在修好之后失败 —— 那时应该来把上限降下去、并删掉这条。
        """
        remaining = {os.path.basename(p).replace(".json", ""): self.measured(p)
                     for p in spec_paths()}
        unresolved = [n for n, m in remaining.items()
                      if m["through_nodes"] or m["labels_on_lines"]]
        self.assertTrue(unresolved,
                        "线穿节点/标签压线都归零了 —— 请把 KNOWN_MAX 的上限降到 0 并删掉这条用例")


class TestMissingCapabilitiesAreRecorded(unittest.TestCase):
    """把"还没实现的能力"也钉住 —— 否则它们会静默消失在"图看起来还行"里。"""

    def test_title_is_currently_dropped(self):
        """P4：`title` 字段被忽略。这条在实现标题渲染后应该**失败**，那时改断言即可。"""
        with open(spec_paths()[0], encoding="utf-8") as fh:
            spec = json.load(fh)
        self.assertTrue(spec.get("title"), "fixture 里得有 title 才能测这件事")
        scene, _, _, _ = E.emit(spec)
        self.assertFalse(measure(scene)["has_title"],
                         "标题已经实现了 —— 删掉这条用例，并在 visual-design.md 里划掉 P4")

    def test_only_one_shape_is_used(self):
        """P5：形状与语义无关（只有圆角矩形）。实现形状映射后这条应该失败。"""
        shapes = set()
        for path in spec_paths():
            with open(path, encoding="utf-8") as fh:
                spec = json.load(fh)
            scene, _, _, _ = E.emit(spec)
            shapes |= set(measure(scene)["shape_kinds"])
        self.assertEqual({"rectangle"}, shapes,
                         "出现了新形状 —— 去把 visual-design.md 里 P5 那条划掉")


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
