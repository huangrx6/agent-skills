"""Exercise real CLIs: compact delivery must preserve content and old paths."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

SCRIPTS = Path(__file__).resolve().parents[2] / "skills/diagram-authoring/scripts"
SPEC = {"type": "architecture", "nodes": [
    {"id": "client", "kind": "client", "label": "客户端"},
    {"id": "service", "kind": "service", "label": "服务"},
], "edges": [{"from": "client", "to": "service"}]}


class DeliveryPaths(unittest.TestCase):
    def write_spec(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(SPEC, ensure_ascii=False), encoding="utf-8")

    def run_cli(self, backend, path, *args):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / f"emit_{backend}.py"), str(path), *args],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def files(self, root):
        return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}

    def test_multiple_views_update_in_place_without_overwriting_each_other(self):
        for backend in ("excalidraw", "drawio"):
            with self.subTest(backend=backend), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "图集"
                expected = set()
                for name in ("01-entry", "02-storage"):
                    source = root / ".source" / f"{name}.diagram.json"
                    self.write_spec(source)
                    self.run_cli(backend, source)
                    expected.update({f".source/{name}.diagram.json", f"{name}.{backend}"})
                second_bytes = (root / f"02-storage.{backend}").read_bytes()
                self.run_cli(backend, root / ".source/01-entry.diagram.json")
                self.assertEqual(self.files(root), expected)
                self.assertEqual((root / f"02-storage.{backend}").read_bytes(), second_bytes)

    def test_relocating_source_preserves_diagram_bytes_and_legacy_filename(self):
        for backend in ("excalidraw", "drawio"):
            with self.subTest(backend=backend), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                flat = root / "system.diagram.json"
                nested = root / "system/.source/system.diagram.json"
                for source in (flat, nested):
                    self.write_spec(source)
                    self.run_cli(backend, source)
                legacy = root / f"system.diagram.{backend}"
                compact = root / "system" / f"system.{backend}"
                self.assertEqual(legacy.read_bytes(), compact.read_bytes())
                self.assertEqual(self.files(root), {
                    "system.diagram.json", f"system.diagram.{backend}",
                    "system/.source/system.diagram.json", f"system/system.{backend}"})

    def test_explicit_path_wins_over_source_convention(self):
        for backend in ("excalidraw", "drawio"):
            with self.subTest(backend=backend), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / ".source/system.diagram.json"
                self.write_spec(source)
                target = root / f"指定文件.{backend}"
                self.run_cli(backend, source, "-o", str(target))
                self.assertEqual(self.files(root), {".source/system.diagram.json", target.name})

    def test_stdout_from_source_writes_no_files(self):
        for backend in ("excalidraw", "drawio"):
            with self.subTest(backend=backend), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / ".source/system.diagram.json"
                self.write_spec(source)
                output = self.run_cli(backend, source, "--stdout")
                if backend == "excalidraw":
                    self.assertEqual(json.loads(output)["type"], "excalidraw")
                else:
                    self.assertEqual(ET.fromstring(output).tag, "mxfile")
                self.assertEqual(self.files(root), {".source/system.diagram.json"})


if __name__ == "__main__":
    unittest.main()
