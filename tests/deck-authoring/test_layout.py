#!/usr/bin/env python3
"""layout/ 包：几何模型 + 安全盒碰撞政策。

一半在测「会报」：deny×deny 安全盒相交必须开口，且报告里带「需要 X 实际 Y」
（只说"撞了"的诊断没法修）。另一半在测「不许报」：同组、父子包含、
figure 内部（visual×caption）、跨页 —— 这四类是视觉整体，报了就是误伤，
误伤会把人练成忽略整个门。
"""
from __future__ import annotations

import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)),
                     "skills", os.path.basename(HERE))
FIXTURES_DIR = os.path.join(HERE, "fixtures")
os.environ.setdefault("DECK_STYLES", os.path.join(FIXTURES_DIR, "styles"))
os.environ.setdefault("DECK_BRANDS", os.path.join(FIXTURES_DIR, "brands"))

PKG = os.path.join(SKILL, "scripts", "layout", "__init__.py")


def _load_layout():
    spec = importlib.util.spec_from_file_location("_deck_test_layout", PKG)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 layout 包：{PKG}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_deck_test_layout"] = module
    spec.loader.exec_module(module)
    return module


layout = _load_layout()
model, collision = layout.model, layout.collision


class TestModel(unittest.TestCase):
    def test_expand_rect(self) -> None:
        safe = model.expand_rect(
            model.Rect(84, 280, 600, 300),
            model.Insets(top=16, right=32, bottom=24, left=0))
        self.assertEqual((safe.x, safe.y, safe.width, safe.height),
                         (84, 264, 632, 340))

    def test_edge_touch_is_not_intersection(self) -> None:
        """净距恰好等于需要间距 = 合格（安全盒边贴边不算撞）。"""
        a = model.Rect(84, 200, 600, 100)
        b = model.Rect(84, 328, 600, 100)      # 净距 28
        self.assertFalse(model.intersects(a, b))

    def test_gap_between(self) -> None:
        a = model.Rect(0, 0, 100, 100)
        self.assertEqual(model.gap_between(a, model.Rect(0, 150, 100, 50)), 50)
        self.assertEqual(model.gap_between(a, model.Rect(130, 0, 50, 100)), 30)
        self.assertEqual(model.gap_between(a, model.Rect(50, 50, 100, 100)), 0)


class TestCollision(unittest.TestCase):
    @staticmethod
    def _el(eid: str, role: str, slide: int, x: float, y: float,
            w: float, h: float) -> dict:
        return {"id": eid, "role": role, "slide": slide,
                "x": x, "y": y, "w": w, "h": h}

    def _violations(self, els: list[dict], hero=frozenset()) -> list[dict]:
        return collision.violations(collision.build_boxes(els), hero)

    def test_deny_pair_too_close_is_reported_with_numbers(self) -> None:
        """标题底 → 条目顶：需要 48（28+20），只给 24 → 报，且带两个数。"""
        v = self._violations([
            self._el("s1.title", "title", 1, 84, 132, 700, 104),
            self._el("s1.bullet.0", "bullet", 1, 84, 260, 600, 40),
        ])
        self.assertEqual(len(v), 1)
        self.assertEqual(v[0]["required"], 48)
        self.assertEqual(v[0]["actual"], 24)

    def test_comfortable_gap_passes(self) -> None:
        self.assertEqual(self._violations([
            self._el("s1.title", "title", 1, 84, 132, 700, 104),
            self._el("s1.bullet.0", "bullet", 1, 84, 304, 600, 40),  # 净距 68
        ]), [])

    def test_same_group_exempt(self) -> None:
        """列表条目之间、标题与副标题之间是一个视觉整体 —— 不互判。"""
        self.assertEqual(self._violations([
            # 同组贴脸（净距 4）不报；跨组（subtitle→bullet）给足 48
            self._el("s1.bullet.0", "bullet", 1, 84, 324, 600, 40),
            self._el("s1.bullet.1", "bullet", 1, 84, 368, 600, 40),
            self._el("s1.title", "title", 1, 84, 132, 700, 104),
            self._el("s1.subtitle", "subtitle", 1, 84, 240, 700, 36),
        ]), [])

    def test_containment_exempt(self) -> None:
        """caption 在 figure 盒内部（父子 DOM）—— 组件内部不是页布局的事。"""
        self.assertEqual(self._violations([
            self._el("s1.image", "image", 1, 84, 300, 600, 400),
            self._el("s1.caption", "caption", 1, 84, 664, 560, 36),  # 盒内贴底
        ]), [])

    def test_visual_and_its_caption_exempt(self) -> None:
        """caption 属于 figure（图内间距由 figure 的 padding 管）—— 不互判。"""
        self.assertEqual(self._violations([
            self._el("s1.chart", "chart", 1, 84, 300, 1432, 378),
            self._el("s1.caption", "bullet", 1, 84, 702, 600, 36),  # 净距 24
        ]), [])

    def test_cross_slide_never_compares(self) -> None:
        self.assertEqual(self._violations([
            self._el("s1.title", "title", 1, 84, 132, 700, 104),
            self._el("s2.bullet.0", "bullet", 2, 84, 200, 600, 40),
        ]), [])

    def test_hero_title_over_image_is_intentional(self) -> None:
        """hero：实心反色标题条压图是设计本身 —— 豁免；非 hero 页同样的重叠照报。"""
        els = [
            self._el("s1.image", "image", 1, 0, 0, 1600, 900),
            self._el("s1.title", "title", 1, 84, 700, 1000, 80),
        ]
        self.assertEqual(self._violations(els, hero=frozenset({1})), [])
        self.assertEqual(len(self._violations(els)), 1)

    def test_caption_clearance_by_id_not_role(self) -> None:
        """图表页 caption 的登记角色是 bullet；安全距离按真实身份取（12 不是 20）。"""
        boxes = collision.build_boxes(
            [self._el("s1.caption", "bullet", 1, 84, 300, 600, 36)])
        self.assertEqual(boxes[0].clearance.top, 12)

    def test_malformed_elements_skipped(self) -> None:
        """缺几何 / 非数字的元素不参与（check 从不抛）。"""
        self.assertEqual(collision.build_boxes(
            [{"id": "s1.x", "role": "title", "slide": 1},
             {"id": "s1.y", "role": "title", "slide": 1,
              "x": "84", "y": 132, "w": 100, "h": 40}]), [])


if __name__ == "__main__":
    unittest.main()


class TestEdgeGates(unittest.TestCase):
    """右缘栅格 + 同级左缘一致（提示级，挂在网格对齐那组）。"""

    @staticmethod
    def _measured(els):
        return {"elements": els}

    @staticmethod
    def _notes(measured):
        check_spec = importlib.util.spec_from_file_location(
            "_deck_test_check_align", os.path.join(SKILL, "scripts", "check.py"))
        if check_spec is None or check_spec.loader is None:
            raise RuntimeError("加载不了 check.py")
        check = importlib.util.module_from_spec(check_spec)
        sys.modules["_deck_test_check_align"] = check
        check_spec.loader.exec_module(check)
        return check._check_grid_alignment(measured)

    def test_chart_box_wider_than_grid_fires_right_edge_note(self) -> None:
        """图表盒 1480 宽（右缘 1564）—— 左缘吸得完美也必须被看见。"""
        notes = self._notes(self._measured([
            {"id": "s1.chart", "role": "chart", "slide": 1,
             "x": 84, "y": 300, "w": 1480, "h": 378},
        ]))
        self.assertTrue(any("右缘不在栅格缘" in n for n in notes), notes)

    def test_chart_right_on_content_edge_passes(self) -> None:
        self.assertEqual(self._notes(self._measured([
            {"id": "s1.chart", "role": "chart", "slide": 1,
             "x": 84, "y": 300, "w": 1432, "h": 378},
        ])), [])

    def test_image_right_at_span_end_passes(self) -> None:
        """span5 的图（582.67 宽）右缘 = 列起点减一档 gutter —— 合法。"""
        self.assertEqual(self._notes(self._measured([
            {"id": "s1.image", "role": "image", "slide": 1,
             "x": 84, "y": 300, "w": 582.67, "h": 400},
        ])), [])

    def test_title_subtitle_left_mismatch_fires(self) -> None:
        """2px 漂移（标题块内缩 30、副标题用了 32 的档）—— 肉眼成品上才看得见。"""
        notes = self._notes(self._measured([
            {"id": "s1.title", "role": "title", "slide": 1,
             "x": 114, "y": 195, "w": 282, "h": 81},
            {"id": "s1.subtitle", "role": "subtitle", "slide": 1,
             "x": 116, "y": 300, "w": 1400, "h": 33},
        ]))
        self.assertTrue(any("左缘不一致" in n and "2px" in n for n in notes), notes)

    def test_aligned_pair_passes(self) -> None:
        # 取列起点 84：既过「同级左缘一致」，也过「左缘吸附」（x=114 会命中
        # 另一条门 —— 那条对 114 报警是对的，风格故意内缩要走它的豁免口径）
        self.assertEqual(self._notes(self._measured([
            {"id": "s1.title", "role": "title", "slide": 1,
             "x": 84, "y": 195, "w": 282, "h": 81},
            {"id": "s1.subtitle", "role": "subtitle", "slide": 1,
             "x": 84, "y": 300, "w": 1400, "h": 33},
        ])), [])
