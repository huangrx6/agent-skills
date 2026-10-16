"""The export lifecycle must not create unsolicited files or publish stale sets."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[2] / 'skills/diagram-authoring/dev-tools'
spec = importlib.util.spec_from_file_location('sync_exports_test', TOOLS / 'sync_exports.py')
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)


class SyncExportsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'example.excalidraw'
        self.source.write_text('native diagram')

    def fake_render(self, source, staged, options):
        for fmt, path in staged.items():
            path.write_bytes(('new-' + fmt).encode())

    def files(self):
        return {str(p.relative_to(self.root)) for p in self.root.rglob('*') if p.is_file()}

    def test_new_native_does_not_load_renderer_or_create_files(self):
        with patch.object(S, 'load_exporter', side_effect=AssertionError('renderer loaded')):
            result = S.sync(self.source)
        self.assertEqual(result['status'], 'not-requested')
        self.assertEqual(self.files(), {'example.excalidraw'})

    def test_svg_only_refresh_keeps_other_diagrams_and_reuses_parameters(self):
        svg = self.source.with_suffix('.svg'); svg.write_text('old-svg')
        (self.root / 'other.png').write_text('unrelated')
        with patch.object(S, 'render', side_effect=self.fake_render) as renderer:
            first = S.sync(self.source, scale=1, padding=100)
            self.assertTrue(first['ok'], first)
            second = S.sync(self.source)
            self.assertEqual(second['options'], {'scale': 1, 'padding': 100})
            self.assertEqual(set(renderer.call_args.args[1]), {'svg'})
        self.assertEqual(svg.read_text(), 'new-svg')
        self.assertEqual((self.root / 'other.png').read_text(), 'unrelated')
        self.assertEqual(self.files(), {'example.excalidraw', 'example.svg', 'other.png',
                                        '.source/example.exports.json'})

    def test_explicit_new_format_also_refreshes_existing_and_does_not_resurrect_deleted(self):
        svg = self.source.with_suffix('.svg'); svg.write_text('old-svg')
        png = self.source.with_suffix('.png')
        with patch.object(S, 'render', side_effect=self.fake_render) as renderer:
            self.assertTrue(S.sync(self.source, ['png'])['ok'])
            self.assertEqual(set(renderer.call_args.args[1]), {'png', 'svg'})
            png.unlink()
            self.assertTrue(S.sync(self.source)['ok'])
            self.assertEqual(set(renderer.call_args.args[1]), {'svg'})
        self.assertFalse(png.exists())

    def test_render_failure_keeps_all_old_exports_and_creates_no_recipe(self):
        for fmt in ('png', 'svg'):
            self.source.with_suffix('.' + fmt).write_text('old-' + fmt)
        def fail(source, staged, options):
            staged['png'].write_text('half-rendered')
            raise RuntimeError('SVG failed')
        with patch.object(S, 'render', side_effect=fail):
            result = S.sync(self.source)
        self.assertFalse(result['ok'])
        for fmt in ('png', 'svg'):
            self.assertEqual(self.source.with_suffix('.' + fmt).read_text(), 'old-' + fmt)
        self.assertEqual(self.files(), {'example.excalidraw', 'example.png', 'example.svg'})
        self.assertFalse((self.root / '.source').exists())

    def test_publish_failure_rolls_back_already_updated_file(self):
        png = self.source.with_suffix('.png'); png.write_text('old-png')
        svg = self.source.with_suffix('.svg'); svg.write_text('old-svg')
        replace = S.os.replace
        def fail_once(src, dst):
            if Path(dst) == svg:
                raise OSError('disk write failed')
            return replace(src, dst)
        with patch.object(S, 'render', side_effect=self.fake_render), patch.object(S.os, 'replace', side_effect=fail_once):
            result = S.sync(self.source)
        self.assertFalse(result['ok'])
        self.assertEqual(png.read_text(), 'old-png')
        self.assertEqual(svg.read_text(), 'old-svg')
        self.assertFalse((self.root / '.source').exists())

    def test_source_change_during_export_prevents_publication(self):
        svg = self.source.with_suffix('.svg'); svg.write_text('old-svg')
        def change_source(source, staged, options):
            self.fake_render(source, staged, options)
            source.write_text('new user edit')
        with patch.object(S, 'render', side_effect=change_source):
            result = S.sync(self.source)
        self.assertFalse(result['ok'])
        self.assertEqual(svg.read_text(), 'old-svg')
        self.assertEqual(self.source.read_text(), 'new user edit')

    def test_target_change_during_export_is_not_overwritten(self):
        svg = self.source.with_suffix('.svg'); svg.write_text('old-svg')
        def change_target(source, staged, options):
            self.fake_render(source, staged, options)
            svg.write_text('concurrent edit')
        with patch.object(S, 'render', side_effect=change_target):
            result = S.sync(self.source)
        self.assertFalse(result['ok'])
        self.assertEqual(svg.read_text(), 'concurrent edit')

    def test_wrong_backend_format_and_ambiguous_basename_fail_without_rendering(self):
        with patch.object(S, 'render', side_effect=AssertionError('renderer called')):
            self.assertFalse(S.sync(self.source, ['pdf'])['ok'])
            self.source.with_suffix('.drawio').write_text('another backend')
            self.assertFalse(S.sync(self.source, ['svg'])['ok'])
        self.assertFalse(self.source.with_suffix('.svg').exists())

    def test_only_requested_backend_apis_are_used(self):
        calls = []
        def fake_export(source, png, svg, **options):
            calls.append((png, svg))
            self.assertIsNone(png)
            Path(svg).write_text('<svg/>')
            return {'ok': True}
        engine = SimpleNamespace(DEFAULT_PADDING=80, export=fake_export)
        with patch.object(S, 'load_exporter', return_value=engine):
            self.assertTrue(S.sync(self.source, ['svg'])['ok'])
        self.assertEqual(len(calls), 1)
        self.assertFalse(self.source.with_suffix('.png').exists())

    def test_drawio_refreshes_only_existing_supported_formats(self):
        self.source = self.source.with_suffix('.drawio')
        (self.root / 'example.excalidraw').unlink()
        self.source.write_text('<mxfile/>')
        for fmt in ('svg', 'pdf'):
            self.source.with_suffix('.' + fmt).write_text('old')
        calls = []
        def fake_export(source, out, fmt, **options):
            calls.append(fmt)
            Path(out).write_text('new-' + fmt)
            return {'ok': True}
        engine = SimpleNamespace(DEFAULT_BORDER=48, export=fake_export)
        with patch.object(S, 'load_exporter', return_value=engine):
            self.assertTrue(S.sync(self.source)['ok'])
        self.assertEqual(calls, ['svg', 'pdf'])
        self.assertFalse(self.source.with_suffix('.png').exists())

    def test_missing_rendered_file_is_failure_not_success(self):
        engine = SimpleNamespace(DEFAULT_PADDING=80, export=lambda *args, **kw: {'ok': True})
        with patch.object(S, 'load_exporter', return_value=engine):
            self.assertFalse(S.sync(self.source, ['svg'])['ok'])
        self.assertEqual(self.files(), {'example.excalidraw'})

    def test_invalid_saved_options_do_not_reach_renderer(self):
        recipe = self.root / '.source/example.exports.json'
        recipe.parent.mkdir()
        recipe.write_text(json.dumps({'version': 1, 'backend': 'excalidraw',
                                      'options': {'scale': float('nan')}}))
        with patch.object(S, 'load_exporter', side_effect=AssertionError('renderer loaded')):
            self.assertFalse(S.sync(self.source, ['svg'])['ok'])
        self.assertFalse(self.source.with_suffix('.svg').exists())


if __name__ == '__main__':
    unittest.main()
