"""Compile the published JSON examples to catch stale or invented interfaces."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

SKILL = Path(__file__).resolve().parents[2] / 'skills' / 'deck-authoring'


def load(name):
    spec = importlib.util.spec_from_file_location('_deck_docs_' + name,
                                                SKILL / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestDocumentedExamples(unittest.TestCase):
    def test_style_and_deck_examples_compile_together_without_browser(self):
        body = (SKILL / 'references' / 'style-architecture.md').read_text(encoding='utf-8')
        values = [json.loads(raw) for raw in re.findall(r'```json\n(.*?)\n```', body, re.S)]
        tokens = next(value for value in values if 'colorSets' in value)
        spec = next(value for value in values if 'deck' in value)
        render, validator = load('render'), load('validate_spec')
        self.assertTrue(render.REQUIRED_TYPE_TIERS <= tokens['type'].keys())
        self.assertEqual(validator.validate(spec, set(tokens['colorSets'])).errors, [])
        with tempfile.TemporaryDirectory() as folder:
            style_dir = Path(folder) / 'styles' / spec['deck']['style']
            style_dir.mkdir(parents=True)
            (style_dir / 'style.json').write_text(json.dumps(tokens), encoding='utf-8')
            # This checks the data contract, not a proposed visual template.
            (style_dir / 'skin.css').write_text('.slide{color:var(--text)}', encoding='utf-8')
            style = render.load_style(str(style_dir), folder)
            resolved = render.deck_mod.compile_spec(spec, style, project_dir=folder)
            html = render.render_resolved(resolved)
            self.assertEqual(html.count('<section class="slide"'), len(spec['deck']['slides']))
            manifest = render.measure_mod.read_manifest(html)
            titles = {item['text'] for item in manifest if item.get('role') == 'title'}
            self.assertEqual(titles, {slide['title'] for slide in spec['deck']['slides']})


if __name__ == '__main__':
    unittest.main()
