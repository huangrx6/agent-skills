#!/usr/bin/env python3
"""Tests for multi-library .excalidrawlib discovery, draw.io SVG icons, shape:icon, parallel edges & edge colors."""
from __future__ import annotations

import base64
import importlib.util
import io
import json
import math
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[2] / "skills" / "diagram-authoring"


def _load(name: str):
    key = f"icon_channel_test_{name}"
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, BASE / "scripts" / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module
        spec.loader.exec_module(module)
    return sys.modules[key]


I = _load("icons")
F = _load("icons_fetch")
L = _load("layout")
CD = _load("color_design")
E = _load("emit_excalidraw")
D = _load("emit_drawio")
CKD = _load("check_drawio")
M = _load("emit_mermaid")


def _write_lib(directory: Path, slug: str, items: dict[str, list[dict]]) -> Path:
    path = directory / f"{slug}.excalidrawlib"
    payload = {
        "type": "excalidrawlib",
        "version": 2,
        "libraryItems": [
            {"id": f"id-{idx}", "status": "published", "name": name, "elements": els}
            for idx, (name, els) in enumerate(items.items())
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _server_elements() -> list[dict]:
    return [
        {"id": "s1", "type": "rectangle", "x": 0, "y": 0, "width": 24, "height": 40,
         "strokeColor": "#1e293b", "backgroundColor": "transparent", "strokeWidth": 2,
         "roundness": {"type": 3}},
        {"id": "s2", "type": "line", "x": 4, "y": 8, "width": 16, "height": 0,
         "points": [[0, 0], [16, 0]], "strokeColor": "#1e293b", "backgroundColor": "transparent",
         "strokeWidth": 2},
        {"id": "s3", "type": "ellipse", "x": 10, "y": 30, "width": 4, "height": 4,
         "strokeColor": "#1e293b", "backgroundColor": "#1e293b", "strokeWidth": 1},
    ]


def _firewall_elements() -> list[dict]:
    return [
        {"id": "f1", "type": "rectangle", "x": 0, "y": 0, "width": 44, "height": 30,
         "strokeColor": "#1e293b", "backgroundColor": "#f97316", "strokeWidth": 2,
         "roundness": {"type": 3}},
        {"id": "f2", "type": "line", "x": 0, "y": 15, "width": 44, "height": 0,
         "points": [[0, 0], [44, 0]], "strokeColor": "#ffffff", "backgroundColor": "transparent",
         "strokeWidth": 2},
    ]


def _mobile_elements() -> list[dict]:
    return [
        {"id": "m1", "type": "rectangle", "x": 0, "y": 0, "width": 22, "height": 38,
         "strokeColor": "#1e293b", "backgroundColor": "transparent", "strokeWidth": 2,
         "roundness": {"type": 3}},
        {"id": "m2", "type": "ellipse", "x": 9, "y": 31, "width": 4, "height": 4,
         "strokeColor": "#1e293b", "backgroundColor": "transparent", "strokeWidth": 1},
    ]


class MultiLibraryAndSvgTests(unittest.TestCase):
    def test_auto_discovers_cached_libraries_and_supports_cross_library_refs(self):
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            _write_lib(cache, "net-icons", {"Firewall": _firewall_elements(), "App Server": _server_elements()})
            _write_lib(cache, "device-icons", {"Mobile Phone": _mobile_elements(), "Firewall": _firewall_elements()})

            with patch.dict(os.environ, {"DIAGRAM_ICON_CACHE": str(cache)}, clear=False):
                # Unique case/punctuation-insensitive resolution across cached libs without --library
                els, src = I.resolve_across_libraries("app-server")
                self.assertEqual(src, "net-icons")
                self.assertEqual(len(els), 3)

                # Ambiguous across 2 libs must fail loudly with explicit disambiguation hints
                with self.assertRaises(I.LibraryError) as caught:
                    I.resolve_across_libraries("Firewall")
                self.assertIn("net-icons:Firewall", str(caught.exception))
                self.assertIn("device-icons:Firewall", str(caught.exception))

                # Explicit lib:item syntax resolves cleanly and lets one diagram mix libraries
                els_fw, src_fw = I.resolve_across_libraries("net-icons:Firewall")
                els_mob, src_mob = I.resolve_across_libraries("device-icons:mobile-phone")
                self.assertEqual(src_fw, "net-icons")
                self.assertEqual(src_mob, "device-icons")
                self.assertEqual(len(els_fw), 2)
                self.assertEqual(len(els_mob), 2)

    def test_icons_fetch_cached_and_find_work_offline(self):
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            _write_lib(cache, "net-icons", {"Firewall": _firewall_elements(), "App Server": _server_elements()})

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = F.main(["--cached", "--dir", str(cache)])
            self.assertEqual(rc, 0)
            self.assertIn("net-icons", buf.getvalue())

            buf2 = io.StringIO()
            with redirect_stdout(buf2):
                rc2 = F.main(["--find", "防火墙", "--dir", str(cache), "--json"])
            self.assertEqual(rc2, 0)
            hits = json.loads(buf2.getvalue())
            self.assertEqual(hits[0]["ref"], "net-icons:Firewall")

    def test_to_svg_data_uri_is_valid_svg_and_drawio_comma_syntax(self):
        uri = I.to_svg_data_uri(_firewall_elements(), target_height=48.0,
                                stroke="#1e293b", canvas="#ffffff", colours="auto")
        self.assertTrue(uri.startswith("data:image/svg+xml,"))
        self.assertNotIn(";base64", uri)
        raw_svg = base64.b64decode(uri.split(",", 1)[1]).decode("utf-8")
        root = ET.fromstring(raw_svg)
        self.assertTrue(root.tag.endswith("svg"))
        self.assertTrue(any(el.tag.endswith("rect") for el in root))


class FramelessIconNodeAndCrossBackendTests(unittest.TestCase):
    def test_frameless_icon_shape_renders_in_excalidraw_and_drawio_with_shared_library(self):
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            _write_lib(cache, "topo", {"Server Tower": _server_elements(), "Firewall": _firewall_elements()})
            spec = {
                "type": "architecture",
                "direction": "LR",
                "groups": [{"id": "dmz", "label": "省内安全域", "level": "tint"}],
                "nodes": [
                    {"id": "srv", "label": "业务主机", "kind": "service", "shape": "icon",
                     "icon": "topo:Server Tower", "group": "dmz"},
                    {"id": "fw", "label": "省内防火墙", "kind": "security", "shape": "icon",
                     "icon": "topo:Firewall", "group": "dmz"},
                    {"id": "core", "label": "核心平台", "kind": "service", "icon": "topo:Server Tower"},
                ],
                "edges": [
                    {"from": "srv", "to": "fw"},
                    {"from": "fw", "to": "core"},
                ],
            }
            with patch.dict(os.environ, {"DIAGRAM_ICON_CACHE": str(cache)}, clear=False):
                scene, _res_e, out_e, _ = E.emit(spec, quality="showcase")
                self.assertTrue(scene)
                self.assertEqual(out_e.blocking, [])
                by_id = {el["id"]: el for el in scene["elements"]}
                # Frameless anchor has invisible stroke/fill (opacity 0), icon centered above label
                anchor = by_id[E._eid("node", "fw")]
                title = by_id[E._eid("title", "fw")]
                icon_els = [el for el in scene["elements"] if el["id"].startswith(E._eid("icon", "fw") + "-")]
                self.assertEqual(anchor["opacity"], 0)
                self.assertEqual(anchor["strokeColor"], "transparent")
                self.assertTrue(icon_els)
                icon_bottom = max(el["y"] + el.get("height", 0) for el in icon_els)
                self.assertGreater(title["y"], icon_bottom - 1.0)

                # draw.io uses the EXACT same .excalidrawlib via inline SVG and passes check_drawio
                xml, _res_d, out_d, _ = D.emit(spec, quality="showcase")
                self.assertTrue(xml)
                self.assertEqual(out_d.blocking, [])
                self.assertEqual(CKD.check_text(xml), [])
                root = ET.fromstring(xml)
                fw_cell = root.find('.//UserObject[@id="n-fw"]/mxCell')
                core_cell = root.find('.//UserObject[@id="n-core"]/mxCell')
                self.assertIn("image=data:image/svg+xml,", fw_cell.get("style"))
                self.assertIn("strokeColor=none", fw_cell.get("style"))
                self.assertIn("fillColor=none", fw_cell.get("style"))
                self.assertIn("image=data:image/svg+xml,", core_cell.get("style"))
                self.assertIn("imageAlign=left", core_cell.get("style"))


class ParallelEdgesAndChannelColorTests(unittest.TestCase):
    def test_bidirectional_and_parallel_edges_separate_into_distinct_tracks(self):
        for mode in ("rounded", "curved", "straight"):
            spec = {
                "type": "architecture",
                "direction": "LR",
                "style": {"edges": mode},
                "nodes": [
                    {"id": "a", "label": "省内节点", "kind": "service"},
                    {"id": "b", "label": "集团网关", "kind": "service"},
                ],
                "edges": [
                    {"id": "req", "from": "a", "to": "b", "kind": "sync"},
                    {"id": "data", "from": "a", "to": "b", "kind": "data"},
                    {"id": "resp", "from": "b", "to": "a", "kind": "async"},
                ],
            }
            boxes = L.boxes_from_spec(spec)
            res = L.layout(spec, boxes)
            self.assertEqual(len(res.edges), 3)
            # Midpoint y coordinates of the 3 horizontal parallel edges must be distinct (>= 6px apart)
            mid_ys = sorted(
                (e["points"][len(e["points"]) // 2][1] if len(e["points"]) > 2
                 else (e["points"][0][1] + e["points"][-1][1]) / 2.0)
                for e in res.edges
            )
            for y1, y2 in zip(mid_ys, mid_ys[1:]):
                self.assertGreaterEqual(y2 - y1, 6.0, f"mode={mode}, mid_ys={mid_ys}")

    def test_content_driven_edge_colors_apply_across_all_three_backends(self):
        spec = {
            "type": "architecture",
            "direction": "LR",
            "nodes": [
                {"id": "a", "label": "入口主机", "kind": "service"},
                {"id": "b", "label": "边界网关", "kind": "security"},
            ],
            "edges": [
                {"id": "up", "from": "a", "to": "b", "kind": "sync"},
                {"id": "down", "from": "b", "to": "a", "kind": "async"},
                {"id": "alert", "from": "a", "to": "b", "kind": "optional"},
            ],
        }
        colors = CD.propose("#2563EB", offsets=(140, 35))
        colors["swatches"]["emerald"] = "#15803D"
        colors["by_edge_kind"] = {"async": "emerald"}
        colors["by_edge"] = {"alert": "critical", "up": "accent"}

        scene, *_ = E.emit(spec, colors=colors)
        arrows = [el for el in scene["elements"] if el["type"] == "arrow"]
        arrow_colors = {el["strokeColor"] for el in arrows}
        self.assertEqual(len(arrow_colors), 3)

        xml, *_ = D.emit(spec, colors=colors)
        root = ET.fromstring(xml)
        edge_styles = [c.get("style", "") for c in root.iter("mxCell") if c.get("edge") == "1"]
        drawio_strokes = {
            dict(p.split("=", 1) for p in s.split(";") if "=" in p)["strokeColor"]
            for s in edge_styles
        }
        self.assertEqual(drawio_strokes, arrow_colors)

        mmd = M.emit(spec, colors=colors)
        self.assertIn("linkStyle 0 stroke:", mmd)
        self.assertIn("linkStyle 1 stroke:", mmd)
        self.assertIn("linkStyle 2 stroke:", mmd)

        # Unknown edge reference must fail loudly
        bad_colors = {**colors, "by_edge": {"no-such-edge": "critical"}}
        with self.assertRaisesRegex(ValueError, "no-such-edge"):
            E.emit(spec, colors=bad_colors)


if __name__ == "__main__":
    unittest.main()
