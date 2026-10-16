"""Meaningful routing, semantic preservation and display-size regressions."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[2] / 'skills/diagram-authoring/scripts'


def load(name):
    spec = importlib.util.spec_from_file_location(f'review_{name}', SCRIPTS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


V, S, P, G = (load(name) for name in ('validate_spec', 'check_semantics', 'check_presentation', 'guide'))


def graph(kind='flow'):
    return {'type': kind, 'nodes': [
        {'id': 'a', 'label': '检查库存', 'kind': 'plain', 'shape': 'diamond'},
        {'id': 'b', 'label': '接单', 'kind': 'service'},
        {'id': 'c', 'label': '等待', 'kind': 'plain'}],
        'edges': [{'from': 'a', 'to': 'b'}, {'from': 'a', 'to': 'c'}]}


class IntentContract(unittest.TestCase):
    def test_old_spec_and_semantic_intent_are_both_valid(self):
        spec = graph()
        self.assertFalse(V.validate(spec).errors)
        spec['intent'] = {'question': '库存不足时怎么办？', 'audience': 'executive', 'pattern': 'recovery'}
        self.assertFalse(V.validate(spec).errors)

    def test_bad_intent_values_do_not_crash_or_admit_geometry(self):
        for value in (None, [], {'x': 10}, {'audience': []}, {'pattern': 'made-up'}, {'question': ''}):
            with self.subTest(value=value):
                spec = graph(); spec['intent'] = value
                self.assertTrue(V.validate(spec).errors)

    def test_intent_does_not_change_generated_content(self):
        emitter = load('emit_excalidraw')
        spec = graph(); spec['nodes'][0].pop('shape')
        before, *_ = emitter.emit(spec)
        spec['intent'] = {'audience': 'executive', 'question': '发生什么？'}
        after, *_ = emitter.emit(spec)
        self.assertTrue(before)
        self.assertEqual(before, after)


class SemanticReview(unittest.TestCase):
    def codes(self, spec):
        return {item['code'] for item in S.check(spec)}

    def test_decision_missing_or_duplicate_labels(self):
        spec = graph()
        self.assertIn('semantic/decision-labels', self.codes(spec))
        for edge in spec['edges']: edge['label'] = '通过'
        self.assertIn('semantic/decision-labels', self.codes(spec))
        spec['edges'][1]['label'] = '不足'
        self.assertNotIn('semantic/decision-labels', self.codes(spec))

    def test_one_outcome_is_reviewed_not_invented(self):
        spec = graph(); spec['edges'].pop()
        original = deepcopy(spec)
        self.assertIn('semantic/decision-outcomes', self.codes(spec))
        self.assertEqual(spec, original)

    def test_unlabeled_state_transition(self):
        spec = graph('state')
        self.assertIn('semantic/unlabeled-transition', self.codes(spec))
        for edge in spec['edges']: edge['label'] = '事件 [条件] / 动作'
        self.assertNotIn('semantic/unlabeled-transition', self.codes(spec))

    def test_disconnected_cycle_is_not_a_rooted_tree(self):
        spec = graph('mindmap')
        spec['edges'] = [{'from': 'b', 'to': 'c'}, {'from': 'c', 'to': 'b'}]
        self.assertIn('semantic/non-tree-mindmap', self.codes(spec))
        self.assertNotIn('semantic/non-tree-mindmap', self.codes(graph('mindmap')))

    def test_wrong_root_and_multiple_parents(self):
        spec = graph('mindmap'); spec['nodes'].reverse()
        self.assertIn('semantic/non-tree-mindmap', self.codes(spec))
        spec = graph('mindmap'); spec['edges'].append({'from': 'b', 'to': 'c'})
        self.assertIn('semantic/non-tree-mindmap', self.codes(spec))

    def test_pattern_mismatch_and_focus_are_advisory(self):
        spec = graph(); spec['intent'] = {'pattern': 'capacity'}
        for node in spec['nodes']: node['emphasis'] = 'primary'
        results = S.check(spec)
        self.assertIn('semantic/pattern-type', {r['code'] for r in results})
        self.assertIn('semantic/competing-focus', {r['code'] for r in results})
        self.assertTrue(all(r['severity'] == 'warning' for r in results))

    def test_cli_exit_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'input.json'; path.write_text(json.dumps(graph()))
            cmd = [sys.executable, str(SCRIPTS / 'check_semantics.py'), str(path)]
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
            self.assertEqual(subprocess.run(cmd + ['--strict'], capture_output=True).returncode, 1)
            path.write_text('{"type":"unknown"}')
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)


class RouteReview(unittest.TestCase):
    def test_capacity_routes_by_question_not_just_nouns(self):
        result = G.recommend('多个来源排队，怎样显示处理瓶颈？')
        self.assertEqual((result['pattern'], result['recommended']), ('capacity', 'architecture'))

    def test_ambiguity_and_override(self):
        result = G.recommend('解释生命周期与回滚')
        self.assertIsNone(result['pattern'])
        self.assertEqual(set(result['pattern_candidates']), {'lifecycle', 'recovery'})
        self.assertEqual(G.recommend('解释生命周期与回滚', pattern='recovery')['recommended'], 'flow')

    def test_unsupported_type_never_becomes_supported_via_pattern(self):
        for request in ('画 API 时序图', '审批泳道图', '数据库 ER 图'):
            self.assertIsNone(G.recommend(request, pattern='recovery')['recommended'])

    def test_audience_and_target_are_independent(self):
        result = G.recommend('订单状态', audience='executive', preset='slide-16x9')
        self.assertEqual(result['audience'], 'executive')
        self.assertEqual(result['display_target']['height'], 720)
        self.assertNotIn('detail', result)


class PresentationReview(unittest.TestCase):
    def test_projection_checks_both_axes(self):
        pages = [('tall', (300, 1600), [('label', 16)])]
        result = P.assess(pages, 'slide-16x9')['pages'][0]
        self.assertEqual(result['status'], 'warning')
        self.assertLess(result['min_viewing_px'], 8)

    def test_natural_fit_is_not_target_pass(self):
        result = P.assess([('page', (300, 200), [('tiny', 4)])], 'fit')
        self.assertEqual(result['pages'][0]['status'], 'not_assessed')
        self.assertFalse(result['render_verified'])

    def test_larger_canvas_does_not_rescue_small_nominal_type(self):
        result = P.assess([('page', (300, 200), [('small', 12)])], 'slide-16x9')
        self.assertEqual(result['pages'][0]['status'], 'warning')
        self.assertEqual(result['pages'][0]['fit_scale'], 1)

    def test_both_native_outputs_and_all_pages_are_measurable(self):
        spec = graph(); spec['nodes'][0].pop('shape')
        excal = load('emit_excalidraw'); draw = load('emit_drawio')
        scene, *_ = excal.emit(spec)
        self.assertTrue(P.excalidraw(json.dumps(scene))[0][2])
        page, *_ = draw.emit_page(spec)
        pages = P.drawio(draw.build_file([page, page]))
        self.assertEqual(len(pages), 2)
        self.assertTrue(all(p[2] for p in pages))

    def test_rotated_and_unknown_inputs_are_unmeasurable(self):
        scene = {'type': 'excalidraw', 'elements': [{'angle': 0.5}]}
        with self.assertRaises(ValueError): P.excalidraw(json.dumps(scene))
        with self.assertRaises(ValueError): P.drawio('<mxfile/>')
        with self.assertRaises(ValueError): P.number(float('nan'))


class RenderDiscoveredRegressions(unittest.TestCase):
    def test_antiparallel_edges_keep_identity_direction_and_labels(self):
        spec = {'type': 'state', 'nodes': [
            {'id': 'draft', 'label': '草稿', 'kind': 'plain'},
            {'id': 'review', 'label': '审核中', 'kind': 'plain'}],
            'edges': [{'from': 'draft', 'to': 'review', 'label': '提交'},
                      {'from': 'review', 'to': 'draft', 'label': '退回'},
                      {'from': 'draft', 'to': 'review', 'label': '再次提交'}]}
        layout = load('layout'); result = layout.layout(spec, layout.boxes_from_spec(spec))
        self.assertCountEqual([(e['from'], e['to'], e['label']) for e in result.edges],
                              [(e['from'], e['to'], e['label']) for e in spec['edges']])
        import xml.etree.ElementTree as ET
        xml, *_ = load('emit_drawio').emit(spec)
        self.assertTrue(xml)
        edges = ET.fromstring(xml).findall('.//mxCell[@edge="1"]')
        self.assertCountEqual([(e.get('source'), e.get('target'), e.get('value')) for e in edges],
                              [('n-'+e['from'], 'n-'+e['to'], e['label']) for e in spec['edges']])

    def test_card_below_nodes_after_page_translation(self):
        import xml.etree.ElementTree as ET
        spec = graph('dependency'); spec['title'] = '标题引入额外垂直平移'
        spec['cards'] = [{'title': '说明', 'items': ['不能遮住任何节点。']}]
        xml, *_ = load('emit_drawio').emit(spec)
        self.assertTrue(xml)
        root = ET.fromstring(xml)
        nodes = root.findall('.//UserObject/mxCell/mxGeometry')
        card = root.find('.//mxCell[@id="card-0"]/mxGeometry')
        self.assertIsNotNone(card)
        self.assertGreater(float(card.get('y')), max(float(n.get('y')) + float(n.get('height')) for n in nodes))

    def test_nonrectangular_ports_follow_visible_outline(self):
        import xml.etree.ElementTree as ET
        xml, *_ = load('emit_drawio').emit(graph())
        edges = ET.fromstring(xml).findall('.//mxCell[@source="n-a"]')
        self.assertEqual(len(edges), 2)
        self.assertTrue(all('exitPerimeter=1' in e.get('style') for e in edges))

    def test_excalidraw_diamond_ports_touch_actual_shape(self):
        emitter = load('emit_excalidraw')
        spec = graph()
        scene, result, *_ = emitter.emit(spec)
        boxes = emitter.L.boxes_from_spec(spec)
        original = deepcopy(result.edges)
        box = result.placed['a']
        for edge in result.edges:
            visible = emitter.visible_edge(edge, result.placed, boxes)
            x, y = visible['points'][0]
            distance = abs((x-box.x-box.width/2)/(box.width/2)) + abs((y-box.y-box.height/2)/(box.height/2))
            self.assertAlmostEqual(distance, 1, places=3)
            self.assertEqual(visible['points'][0][0], edge['points'][0][0])
        self.assertEqual(result.edges, original)
        self.assertTrue(scene)

    def test_excalidraw_rounded_ellipse_port_stays_on_near_side(self):
        from types import SimpleNamespace
        emitter = load('emit_excalidraw')
        placed = {'a': SimpleNamespace(x=0, y=0, width=100, height=99.999),
                  'b': SimpleNamespace(x=0, y=150, width=100, height=100)}
        boxes = {'a': SimpleNamespace(shape='ellipse'), 'b': SimpleNamespace(shape='rectangle')}
        for y in (99.99, 100.0):
            edge = {'from': 'a', 'to': 'b', 'points': [[50, y], [50, 150]]}
            visible = emitter.visible_edge(edge, placed, boxes)
            self.assertEqual(visible['points'], edge['points'])


if __name__ == '__main__':
    unittest.main()
