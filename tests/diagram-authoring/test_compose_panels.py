#!/usr/bin/env python3
"""compose_panels.py 的回归：面板平移、ID 隔离和计划校验。

这里用最小 Excalidraw 场景，不跑 layout/emit；合成器只负责几何与引用，
不应该把布局行为混进自己的测试。
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills",
                     os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")


def _load(name: str, filename: str):
    path = os.path.join(SCRIPTS, filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CP = _load("compose_panels_under_test", "compose_panels.py")


def _rect(element_id: str, x: float, y: float, width: float, height: float,
          **extra) -> dict:
    return {"id": element_id, "type": "rectangle", "x": x, "y": y,
            "width": width, "height": height, **extra}


def _text(element_id: str, container: str, x: float, y: float,
          width: float, height: float, **extra) -> dict:
    return {"id": element_id, "type": "text", "x": x, "y": y,
            "width": width, "height": height, "containerId": container, **extra}


def _arrow(element_id: str, x: float, y: float, width: float,
           source: str, target: str | None, **extra) -> dict:
    return {"id": element_id, "type": "arrow", "x": x, "y": y,
            "width": width, "height": 0, "points": [[0, 0], [width, 0]],
            "startBinding": {"elementId": source},
            "endBinding": {"elementId": target} if target else None, **extra}


class TestComposePanels(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = self.temp.name

    def tearDown(self):
        self.temp.cleanup()

    def _write(self, name: str, payload: dict) -> None:
        with open(os.path.join(self.dir, name), "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)

    def _scene(self, elements: list[dict], *, files: dict | None = None,
               background: str = "#FFFFFF") -> dict:
        return {"type": "excalidraw", "version": 2, "elements": elements,
                "appState": {"viewBackgroundColor": background},
                "files": files or {}}

    def _plan(self, panels: list[dict], **extra) -> dict:
        return {"version": 1, "panels": panels, **extra}

    def _compose(self, plan: dict) -> dict:
        return CP.compose(plan, self.dir)

    @staticmethod
    def _backgrounds(scene: dict) -> list[dict]:
        return sorted((element for element in scene["elements"]
                       if element["id"].endswith("--panel-bg")),
                      key=lambda element: element["x"])

    def test_row_layout_moves_content_inside_each_panel(self):
        self._write("main.json", self._scene([_rect("main-node", 10, 20, 100, 50)]))
        self._write("ops.json", self._scene([_rect("ops-node", -50, 100, 60, 120)]))
        scene = self._compose(self._plan(
            [{"name": "main", "file": "main.json"},
             {"name": "ops", "file": "ops.json"}],
            layout="row", gap=80, padding=24))

        backgrounds = self._backgrounds(scene)
        self.assertEqual([(b["x"], b["width"], b["height"]) for b in backgrounds],
                         [(0.0, 148.0, 98.0), (228.0, 108.0, 168.0)])
        by_id = {element["id"]: element for element in scene["elements"]}
        self.assertEqual(by_id["main--main-node"]["x"], 24)
        self.assertEqual(by_id["main--main-node"]["y"], 24)
        self.assertEqual(by_id["ops--ops-node"]["x"], 252)
        self.assertEqual(by_id["ops--ops-node"]["y"], 24)
        self.assertEqual(scene["appState"]["width"], 336)
        self.assertEqual(scene["appState"]["height"], 168)

    def test_column_layout_stacks_panels(self):
        self._write("main.json", self._scene([_rect("main-node", 0, 0, 100, 50)]))
        self._write("ops.json", self._scene([_rect("ops-node", -50, 100, 60, 120)]))
        scene = self._compose(self._plan(
            [{"name": "main", "file": "main.json"},
             {"name": "ops", "file": "ops.json"}],
            layout="column", gap=80, padding=24))

        backgrounds = sorted(self._backgrounds(scene), key=lambda element: element["y"])
        self.assertEqual([(b["x"], b["y"], b["width"], b["height"]) for b in backgrounds],
                         [(0.0, 0.0, 148.0, 98.0), (0.0, 178.0, 108.0, 168.0)])
        by_id = {element["id"]: element for element in scene["elements"]}
        self.assertEqual(by_id["ops--ops-node"]["y"], 202)
        self.assertEqual(scene["appState"]["width"], 148)
        self.assertEqual(scene["appState"]["height"], 346)

    def test_ids_references_and_groups_are_isolated(self):
        main = self._scene([
            _rect("node-a", 10, 20, 100, 50,
                  groupIds=["pair"], boundElements=[{"id": "label-a", "type": "text"}]),
            _text("label-a", "node-a", 20, 30, 80, 20, groupIds=["pair"]),
            _arrow("edge-a", 110, 45, 100, "node-a", None,
                   groupIds=["pair"]),
        ])
        ops = self._scene([
            _rect("node-b", 0, 0, 60, 120,
                  boundElements=[{"id": "label-b", "type": "text"}]),
            _text("label-b", "node-b", 10, 10, 40, 20),
        ])
        self._write("main.json", main)
        self._write("ops.json", ops)
        scene = self._compose(self._plan(
            [{"name": "main", "file": "main.json"},
             {"name": "ops", "file": "ops.json"}]))

        ids = [element["id"] for element in scene["elements"]]
        self.assertEqual(len(ids), len(set(ids)))
        known = set(ids)
        by_id = {element["id"]: element for element in scene["elements"]}
        self.assertEqual(by_id["main--node-a"]["groupIds"], ["main--pair"])
        self.assertEqual(by_id["main--node-a"]["boundElements"],
                         [{"id": "main--label-a", "type": "text"}])
        self.assertEqual(by_id["main--label-a"]["containerId"], "main--node-a")
        self.assertEqual(by_id["main--edge-a"]["startBinding"],
                         {"elementId": "main--node-a"})
        for element in scene["elements"]:
            for key in ("containerId", "frameId"):
                if element.get(key):
                    self.assertIn(element[key], known, (element["id"], key))
            for item in element.get("boundElements") or []:
                self.assertIn(item["id"], known, (element["id"], "boundElements"))
            for key in ("startBinding", "endBinding"):
                binding = element.get(key)
                if binding and binding.get("elementId"):
                    self.assertIn(binding["elementId"], known, (element["id"], key))
        self.assertEqual(main["elements"][0]["id"], "node-a")
        self.assertEqual(main["elements"][0]["groupIds"], ["pair"])

    def test_files_are_namespaced_with_elements(self):
        self._write("main.json", self._scene([
            {"id": "img", "type": "image", "x": 0, "y": 0,
             "width": 10, "height": 10, "fileId": "file-1"},
        ], files={"file-1": {"id": "file-1", "dataURL": "data:image/png;base64,AA=="}}))
        self._write("ops.json", self._scene([_rect("node", 0, 0, 10, 10)]))
        scene = self._compose(self._plan(
            [{"name": "main", "file": "main.json"},
             {"name": "ops", "file": "ops.json"}]))
        image = next(element for element in scene["elements"] if element["id"] == "main--img")
        self.assertEqual(image["fileId"], "main--file-1")
        self.assertIn("main--file-1", scene["files"])

    def test_background_id_does_not_collide_with_content(self):
        self._write("main.json", self._scene([_rect("panel-bg", 0, 0, 10, 10)]))
        self._write("ops.json", self._scene([_rect("node", 0, 0, 10, 10)]))
        scene = self._compose(self._plan(
            [{"name": "main", "file": "main.json"},
             {"name": "ops", "file": "ops.json"}]))
        ids = [element["id"] for element in scene["elements"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("main--panel-bg", ids)
        self.assertIn("main--panel-bg-x", ids)

    def test_plan_errors_are_reported(self):
        self._write("main.json", self._scene([_rect("node", 0, 0, 10, 10)]))
        cases = [
            ({"version": 2, "panels": [{"name": "main", "file": "main.json"}]},
             "version"),
            ({"version": 1, "panels": []}, "panels"),
            ({"version": 1, "panels": [{"name": "main", "file": "missing.json"}]},
             "找不到面板文件"),
            ({"version": 1, "panels": [
                {"name": "main", "file": "main.json"},
                {"name": "main", "file": "main.json"}]}, "面板名重复"),
            ({"version": 1, "panels": [{"name": "main", "file": "main.json",
                                        "oops": 1}]}, "未知字段"),
            ({"version": 1, "layout": "grid",
              "panels": [{"name": "main", "file": "main.json"}]}, "layout"),
        ]
        for plan, message in cases:
            with self.subTest(plan=plan), self.assertRaisesRegex(ValueError, message):
                self._compose(plan)


if __name__ == "__main__":
    unittest.main()
