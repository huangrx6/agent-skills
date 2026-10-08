"""Execute the spec example instead of checking instructional wording."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

SKILL = Path(__file__).resolve().parents[2] / 'skills' / 'diagram-authoring'


class TestDocumentedSpec(unittest.TestCase):
    def test_complete_example_validates_and_emits_both_editable_formats(self):
        body = (SKILL / 'references' / 'diagram-spec.md').read_text(encoding='utf-8')
        blocks = re.findall(r'```json\n(.*?)\n```', body, re.S)
        specs = [json.loads(block) for block in blocks]
        specs = [spec for spec in specs if isinstance(spec, dict) and 'nodes' in spec]
        self.assertTrue(specs, 'The spec reference needs an executable complete example')
        with tempfile.TemporaryDirectory() as folder:
            for index, spec in enumerate(specs):
                source = Path(folder) / f'example-{index}.diagram.json'
                source.write_text(json.dumps(spec, ensure_ascii=False), encoding='utf-8')
                for command in ('validate_spec.py', 'emit_excalidraw.py', 'emit_drawio.py'):
                    with self.subTest(command=command, example=index):
                        run = subprocess.run([sys.executable, str(SKILL / 'scripts' / command),
                                              str(source)], text=True, capture_output=True)
                        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                scene = json.loads(source.with_suffix('.excalidraw').read_text())
                self.assertTrue(scene['elements'])
                graph = ET.parse(source.with_suffix('.drawio'))
                self.assertEqual(len(graph.findall('./diagram')), 1)


if __name__ == '__main__':
    unittest.main()
