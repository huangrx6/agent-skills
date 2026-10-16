"""Behavior contracts for open project palettes and their emitted colors."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

SKILL = Path(__file__).resolve().parents[2] / 'skills/diagram-authoring'


def load(name):
    spec = importlib.util.spec_from_file_location('colors_test_' + name, SKILL / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


C, E, D = load('color_design'), load('emit_excalidraw'), load('emit_drawio')


def diagram():
    return json.loads((SKILL / 'examples/presentation/source.diagram.json').read_text())


def design():
    result = C.propose('#7148B9', offsets=(67, 193, 245))
    result['by_kind'] = {'service': 'accent', 'data': 'companion-1'}
    result['by_node'] = {'api': 'companion-2'}
    return result


def style(cell):
    return dict(part.split('=', 1) for part in cell.get('style', '').split(';') if '=' in part)


class ColorDesignTests(unittest.TestCase):
    def test_arbitrary_seed_offsets_and_names_do_not_require_profile_registration(self):
        a = C.propose('#538A31', offsets=(-123, 13, 71, 290))
        b = C.propose('#538A31', offsets=(-124, 14, 72, 291))
        self.assertEqual(a['accent'], '#538A31')
        self.assertEqual(len(a['swatches']), 4)
        self.assertNotEqual(a['swatches'], b['swatches'])
        a['swatches']['project-color'] = '#BA7629'
        a['by_kind']['data'] = 'project-color'
        self.assertEqual(C.resolve(a, E.palette)['report']['status'], 'pass')

    def test_generated_companions_do_not_automatically_color_every_role(self):
        raw = C.propose('#7255B8', offsets=(15, 120, 180, 240))
        E.palette.use_colors(raw)
        normal = {E.palette.fill_for(kind) for kind in E.palette.DEFAULT_KIND_LEVELS}
        self.assertEqual(normal, {raw['canvas']})
        self.assertNotIn(E.palette.fill_for('service', 'primary'), normal)
        self.assertEqual(raw['by_kind'], {})

    def test_ordinary_groups_and_notes_do_not_inherit_accent_hue(self):
        raw = design(); other = {**raw, 'accent': '#B52F31'}
        a, b = C.resolve(raw, E.palette), C.resolve(other, E.palette)
        for level in ('neutral', 'tint'):
            self.assertEqual(a['levels'][level], b['levels'][level])
        self.assertNotEqual(a['levels']['accent'], b['levels']['accent'])
        for emitter in (E, D):
            artifact, *_ = emitter.emit(diagram(), colors=other)
            p = emitter.palette
            self.assertNotEqual(p.frame_stroke('tint'), p.LEVELS['accent']['stroke'])
            if emitter is E:
                shapes = {e['id']: e for e in artifact['elements']}
                self.assertEqual(shapes['region-core']['strokeColor'], p.frame_stroke('tint'))
                self.assertEqual(shapes['card-card-0']['strokeColor'], p.frame_stroke('tint'))
            else:
                root = ET.fromstring(artifact)
                for key in ('region-core', 'card-0'):
                    self.assertEqual(style(root.find(f'.//mxCell[@id="{key}"]'))['strokeColor'], p.frame_stroke('tint'))

    def test_explicit_group_fill_matches_backends_without_recoloring_nodes(self):
        raw = design()
        raw['by_group'] = {'core': {'color': 'companion-1', 'strength': .22}}
        resolved = C.resolve(raw, E.palette)
        scene, *_ = E.emit(diagram(), colors=raw)
        xml, *_ = D.emit(diagram(), colors=raw)
        elements = {e['id']: e for e in scene['elements']}
        expected = resolved['groups']['core']
        self.assertEqual(elements['region-core']['backgroundColor'], expected['fill'])
        self.assertEqual(elements['region-label-core']['strokeColor'], expected['text'])
        self.assertEqual(style(ET.fromstring(xml).find('.//mxCell[@id="region-core"]'))['fillColor'], expected['fill'])
        without = {k: v for k, v in raw.items() if k != 'by_group'}
        a, b = C.resolve(raw, E.palette), C.resolve(without, E.palette)
        self.assertEqual(a['colors']['companion-1']['fill'], b['colors']['companion-1']['fill'])
        for check in a['report']['checks']:
            self.assertTrue(check['passed'])

    def test_group_colors_validate_ids_names_and_strength(self):
        for mapping in ({'core': 'accent'}, {'core': {'color': []}},
                        {'core': {'color': 'missing'}}, {'core': {'color': 'accent', 'strength': True}},
                        {'core': {'color': 'accent', 'strength': -1}}, {'core': {'color': 'accent', 'extra': 0}}):
            with self.subTest(mapping=mapping), self.assertRaises(ValueError):
                C.resolve({**design(), 'by_group': mapping}, E.palette)
        for emitter in (E, D):
            with self.assertRaisesRegex(ValueError, 'typo'):
                emitter.emit(diagram(), colors={**design(), 'by_group': {'typo': {'color': 'accent'}}})

    def test_group_alert_is_not_hidden_by_an_area_color(self):
        spec = diagram(); spec['groups'][0]['level'] = 'critical'
        scene, *_ = E.emit(spec, colors={**design(), 'by_group': {'core': {'color': 'companion-1'}}})
        group = next(e for e in scene['elements'] if e['id'] == 'region-core')
        self.assertEqual(group['backgroundColor'], E.palette.LEVELS['critical']['fill'])

    def test_resolving_never_mutates_source_or_input_swatches(self):
        raw = design(); before = deepcopy(raw)
        result = C.resolve(raw, E.palette)
        result['by_kind']['service'] = 'changed'
        result['raw']['swatches']['companion-1'] = '#000000'
        self.assertEqual(raw, before)

    def test_low_contrast_canvas_text_is_rejected_not_silently_recolored(self):
        raw = design(); raw.update(canvas='#EEEEEE', ink='#DDDDDD')
        with self.assertRaisesRegex(ValueError, '4.5'):
            C.resolve(raw, E.palette)

    def test_bad_keys_values_targets_and_references_fail(self):
        for change in ({'unknown': 1}, {'version': True}, {'accent': 'red'},
                       {'by_kind': {'wrong': 'accent'}}, {'by_node': {'api': 'missing'}},
                       {'strength': {'normal': float('nan')}}, {'strength': {'normal': 2}},
                       {'swatches': {'accent': '#123456'}}, {'source': {'run': 'bad'}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                C.resolve({**design(), **change}, E.palette)

    def test_source_url_is_provenance_only(self):
        raw = design(); raw['source'] = 'https://invalid.example/never-fetch'
        self.assertEqual(C.resolve(raw, E.palette)['raw']['source'], raw['source'])

    def test_node_assignment_takes_precedence_and_critical_keeps_alert_semantics(self):
        p = E.palette
        p.use_colors(design())
        self.assertNotEqual(p.fill_for('service', 'normal', 'api'), p.fill_for('service', 'normal', 'order'))
        self.assertEqual(p.fill_for('service', 'critical', 'api'), p.LEVELS['critical']['fill'])
        self.assertEqual(p.fill_for('service', 'muted', 'api'), p.LEVELS['neutral']['fill'])

    def test_unknown_node_id_is_not_silently_ignored(self):
        raw = design(); raw['by_node']['typo'] = 'accent'
        for emitter in (E, D):
            with self.assertRaisesRegex(ValueError, 'typo'):
                emitter.emit(diagram(), colors=raw)

    def test_design_changes_colors_not_facts_or_geometry(self):
        spec = diagram(); before = deepcopy(spec)
        plain, layout, *_ = E.emit(spec)
        colored, custom_layout, *_ = E.emit(spec, colors=design())
        geometry = lambda scene: [(e['id'], e['type'], e['x'], e['y'], e['width'], e['height'], e.get('text')) for e in scene['elements']]
        self.assertEqual(geometry(plain), geometry(colored))
        self.assertNotEqual(plain, colored)
        self.assertEqual(spec, before)

    def test_emitted_node_fill_text_match_across_backends(self):
        raw = design()
        raw['strength']['primary'] = 1.0
        scene, *_ = E.emit(diagram(), colors=raw)
        xml, *_ = D.emit(diagram(), colors=raw, scheme='classic')
        elements = {e['id']: e for e in scene['elements']}
        root = ET.fromstring(xml)
        for node in diagram()['nodes']:
            key = node['id']
            cell = root.find(f'.//UserObject[@id="n-{key}"]/mxCell')
            st = style(cell)
            self.assertEqual(st['fillColor'], E.palette.fill_for(node['kind'], node.get('emphasis', 'normal'), key))
            self.assertEqual(st['fontColor'], E.palette.text_for(node['kind'], node.get('emphasis', 'normal'), key))
            self.assertGreaterEqual(E.palette.contrast(st['fontColor'], st['fillColor']), 4.5)
            self.assertEqual(elements[E._eid('title', key)]['strokeColor'], st['fontColor'])

    def test_serial_palettes_and_legacy_calls_are_isolated(self):
        for emitter in (E, D):
            baseline, *_ = emitter.emit(diagram())
            custom, *_ = emitter.emit(diagram(), colors=design())
            again, *_ = emitter.emit(diagram())
            self.assertEqual(baseline, again)
            self.assertNotEqual(baseline, custom)

    def test_dark_drawio_node_edge_and_card_text_are_explicit(self):
        for kwargs in ({'scheme': 'night'}, {'colors': {**design(), 'canvas': '#131B2B', 'ink': '#F4F5FC'}}):
            xml, *_ = D.emit(diagram(), **kwargs)
            root = ET.fromstring(xml)
            for cell in root.findall('.//mxCell'):
                parent = next((x for x in root.findall('.//UserObject') if cell in list(x)), None)
                label = parent.get('label') if parent is not None else cell.get('value')
                if label and (cell.get("vertex") == "1" or cell.get("edge") == "1"):
                    self.assertIn('fontColor', style(cell))

    def test_reversed_text_cannot_hide_in_hatch_gaps(self):
        raw = design(); raw['strength']['primary'] = 1.0
        spec = diagram(); spec['style']['fill'] = 'hachure'
        with self.assertRaisesRegex(ValueError, 'solid'):
            E.emit(spec, colors=raw)
        spec['style']['fill'] = 'solid'
        artifact, *_ = E.emit(spec, colors=raw)
        self.assertTrue(artifact)

    def test_conflicting_legacy_overrides_fail(self):
        with self.assertRaisesRegex(ValueError, '--colors'):
            D.emit(diagram(), colors=design(), seeds={'accent': '#AA4411'})


if __name__ == '__main__':
    unittest.main()
