#!/usr/bin/env python3
"""Tests for flexible edge styles (style.edges), barycenter balancing, L-shape routing, and curves."""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = Path(__file__).resolve().parents[2] / "skills" / "diagram-authoring"


def _load(name: str):
    key = f"edge_style_test_{name}"
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, BASE / "scripts" / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module
        spec.loader.exec_module(module)
    return sys.modules[key]


P = _load("palette")
V = _load("validate_spec")
L = _load("layout")
C = _load("check_layout")
R = _load("readable_routing")
E = _load("emit_excalidraw")
D = _load("emit_drawio")
M = _load("emit_mermaid")


def _fanout_spec(direction: str = "LR", edges_style: str | None = None) -> dict:
    spec = {
        "type": "architecture",
        "direction": direction,
        "nodes": [
            {"id": "gw", "label": "API Gateway", "kind": "service", "emphasis": "primary"},
            {"id": "auth", "label": "Auth Service", "kind": "service"},
            {"id": "orders", "label": "Orders Service", "kind": "service"},
            {"id": "billing", "label": "Billing Service", "kind": "service"},
        ],
        "edges": [
            {"from": "gw", "to": "auth"},
            {"from": "gw", "to": "orders"},
            {"from": "gw", "to": "billing"},
        ],
    }
    if edges_style is not None:
        spec["style"] = {"edges": edges_style}
    return spec


class StyleEdgesContractTests(unittest.TestCase):
    def test_palette_declares_edges_axis_and_default_rounded(self):
        self.assertIn("edges", P.STYLE_AXES)
        self.assertEqual(P.STYLE_AXES["edges"], ("rounded", "curved", "sharp", "straight"))
        self.assertEqual(P.STYLE_DEFAULT["edges"], "rounded")
        self.assertEqual(P.edge_style_of(None), "rounded")
        for mode in ("rounded", "curved", "sharp", "straight"):
            self.assertEqual(P.edge_style_of({"edges": mode}), mode)

    def test_validator_accepts_valid_edge_styles_and_rejects_unknown(self):
        for mode in ("rounded", "curved", "sharp", "straight"):
            report = V.validate(_fanout_spec("LR", mode))
            self.assertEqual(report.errors, [], mode)
        bad = V.validate(_fanout_spec("LR", "wavy"))
        self.assertTrue(any(item["code"] == "BAD_STYLE_VALUE" for item in bad.errors))


class BarycenterAndRoutingTests(unittest.TestCase):
    def test_fanout_parent_centers_between_outer_children(self):
        spec = {
            "type": "flow",
            "direction": "TB",
            "nodes": [
                {"id": "start", "label": "Start", "kind": "client"},
                {"id": "left", "label": "Branch Left", "kind": "service"},
                {"id": "right", "label": "Branch Right", "kind": "service"},
            ],
            "edges": [
                {"from": "start", "to": "left"},
                {"from": "start", "to": "right"},
            ],
        }
        boxes = L.boxes_from_spec(spec)
        res = L.layout(spec, boxes)
        s = res.placed["start"]
        left = res.placed["left"]
        right = res.placed["right"]
        s_cx = s.x + s.width / 2.0
        mid = ((left.x + left.width / 2.0) + (right.x + right.width / 2.0)) / 2.0
        self.assertAlmostEqual(s_cx, mid, delta=2.0)

    def test_offset_fanout_uses_single_bend_l_shape_in_orthogonal_mode(self):
        spec = _fanout_spec("LR", "rounded")
        boxes = L.boxes_from_spec(spec)
        res = L.layout(spec, boxes)
        bends_by_target = {e["to"]: max(0, len(e["points"]) - 2) for e in res.edges}
        # Center child straight (0 bends), upper/lower children use 1-bend L-shape instead of 2-bend Z
        self.assertEqual(bends_by_target["orders"], 0)
        self.assertLessEqual(bends_by_target["auth"], 1)
        self.assertLessEqual(bends_by_target["billing"], 1)

    def test_curved_mode_generates_obstacle_free_arcs_and_passes_showcase(self):
        spec = _fanout_spec("LR", "curved")
        boxes = L.boxes_from_spec(spec)
        res, outcome, _ = C.layout_with_retry(spec, boxes)
        outcome = outcome.promote("showcase")
        self.assertEqual(outcome.blocking, [])
        self.assertEqual(C.check_edge_slant(res, spec), [])
        # Upper and lower branches should be smooth 3-point arcs (not rigid 4-point staircases)
        for edge in res.edges:
            if edge["to"] in ("auth", "billing"):
                self.assertEqual(len(edge["points"]), 3)
            self.assertEqual(L.nodes_hit_by_polyline(edge["points"], res.placed, {edge["from"], edge["to"]}), [])

    def test_curved_mode_does_not_clip_intermediate_node(self):
        spec = {
            "type": "architecture",
            "direction": "LR",
            "style": {"edges": "curved"},
            "nodes": [
                {"id": "a", "label": "Source", "kind": "client", "rank": 0},
                {"id": "mid1", "label": "Middle Top", "kind": "service", "rank": 1},
                {"id": "mid2", "label": "Middle Bot", "kind": "service", "rank": 1},
                {"id": "b", "label": "Sink", "kind": "data", "rank": 2},
            ],
            "edges": [
                {"from": "a", "to": "mid1"},
                {"from": "a", "to": "mid2"},
                {"from": "mid1", "to": "b"},
                {"from": "mid2", "to": "b"},
                {"from": "a", "to": "b"},
            ],
        }
        boxes = L.boxes_from_spec(spec)
        res, outcome, _ = C.layout_with_retry(spec, boxes)
        self.assertEqual(outcome.blocking, [])
        for edge in res.edges:
            self.assertEqual(L.nodes_hit_by_polyline(edge["points"], res.placed, {edge["from"], edge["to"]}), [])

    def test_straight_mode_uses_direct_two_point_chords_when_unobstructed(self):
        spec = _fanout_spec("LR", "straight")
        boxes = L.boxes_from_spec(spec)
        res, outcome, _ = C.layout_with_retry(spec, boxes)
        outcome = outcome.promote("showcase")
        self.assertEqual(outcome.blocking, [])
        for edge in res.edges:
            self.assertEqual(len(edge["points"]), 2)

    def test_readable_routing_preserves_curved_and_straight_modes(self):
        for mode in ("curved", "straight"):
            spec = _fanout_spec("LR", mode)
            ctx = L.P.resolve("doc-inline")
            boxes = L.boxes_from_spec(spec, presentation=ctx)
            res = L.layout(spec, boxes, presentation=ctx)
            refined = R.refine(spec, res, boxes, L, ctx)
            self.assertEqual(refined.edges, res.edges)


class BackendEdgeStyleEmissionTests(unittest.TestCase):
    def test_excalidraw_arrow_roundness_across_modes_and_short_leg_guard(self):
        long_edge = {"from": "a", "to": "b", "points": [[0.0, 0.0], [100.0, 0.0], [100.0, 80.0]]}
        cramped_edge = {"from": "a", "to": "b", "points": [[0.0, 0.0], [18.0, 0.0], [18.0, 80.0]]}

        self.assertEqual(E.arrow_element(long_edge, 0, {"edges": "rounded"})["roundness"], {"type": 2})
        self.assertIsNone(E.arrow_element(cramped_edge, 0, {"edges": "rounded"})["roundness"])
        self.assertEqual(E.arrow_element(cramped_edge, 0, {"edges": "curved"})["roundness"], {"type": 2})
        self.assertIsNone(E.arrow_element(long_edge, 0, {"edges": "sharp"})["roundness"])
        self.assertIsNone(E.arrow_element(long_edge, 0, {"edges": "straight"})["roundness"])

    def test_drawio_emits_matching_edge_routing_styles(self):
        expectations = {
            "rounded": ("edgeStyle=orthogonalEdgeStyle", "rounded=1", "arcSize=12"),
            "curved": ("curved=1",),
            "sharp": ("edgeStyle=orthogonalEdgeStyle", "rounded=0"),
            "straight": ("edgeStyle=none", "rounded=0"),
        }
        for mode, tokens in expectations.items():
            xml, _res, outcome, _ = D.emit(_fanout_spec("LR", mode), quality="showcase")
            self.assertTrue(xml, f"{mode}: {outcome.blocking}")
            root = ET.fromstring(xml)
            edge_cells = [c for c in root.iter("mxCell") if c.get("edge") == "1"]
            self.assertTrue(edge_cells)
            for cell in edge_cells:
                style = cell.get("style", "")
                for token in tokens:
                    self.assertIn(token, style, f"mode={mode}, style={style}")

    def test_mermaid_maps_edges_style_to_curve_config(self):
        cases = [
            ("LR", "rounded", "monotoneX"),
            ("TB", "rounded", "monotoneY"),
            ("LR", "curved", "basis"),
            ("LR", "sharp", "linear"),
            ("TB", "straight", "linear"),
        ]
        for direction, mode, expected_curve in cases:
            text = M.emit(_fanout_spec(direction, mode))
            self.assertIn(f'"curve": "{expected_curve}"', text, (direction, mode))


if __name__ == "__main__":
    unittest.main()
