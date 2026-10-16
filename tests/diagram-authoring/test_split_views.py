"""Authored views preserve source facts, including parallel edges and notes."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest
import contextlib
import io
import json
import tempfile

path = Path(__file__).resolve().parents[2] / 'skills/diagram-authoring/scripts/split_views.py'
spec = importlib.util.spec_from_file_location('split_views_test', path)
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)


def fixture():
    source = {'type': 'architecture', 'direction': 'TB', 'nodes': [
        {'id': 'a', 'label': '入口', 'kind': 'client', 'rank': 0},
        {'id': 'b', 'label': '处理', 'kind': 'service', 'rank': 1, 'group': 'g', 'detail': '校验并派发'},
        {'id': 'c', 'label': '数据', 'kind': 'data', 'rank': 2, 'group': 'g'}],
        'edges': [{'from': 'a', 'to': 'b', 'label': '提交'},
                  {'from': 'b', 'to': 'c', 'label': '保存', 'kind': 'data'},
                  {'from': 'b', 'to': 'c', 'label': '查询', 'kind': 'sync'}],
        'groups': [{'id': 'g', 'label': '处理区'}],
        'cards': [{'title': '约束', 'items': ['所有原始说明必须保留。']}]}
    plan = {'version': 1, 'views': [
        {'name': 'entry', 'title': '入口', 'question': '如何进入？', 'edges': [0]},
        {'name': 'data', 'title': '数据', 'question': '如何保存和查询？', 'edges': [1, 2],
         'ranks': {'b': 0, 'c': 1}, 'pins': {'b': 'left'}, 'direction': 'LR'}]}
    return source, plan


class SplitViewsTests(unittest.TestCase):
    def test_output_cannot_overwrite_input_source(self):
        source, plan = fixture()
        plan['views'][0]['name'] = 'source'
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src, config = root/'source.diagram.json', root/'views.json'
            src.write_text(json.dumps(source)); config.write_text(json.dumps(plan))
            before = src.read_bytes()
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
                V.main([str(src), str(config), '-o', str(root)])
            self.assertEqual(exc.exception.code, 2)
            self.assertEqual(src.read_bytes(), before)
            self.assertEqual({p.name for p in root.iterdir()}, {'source.diagram.json', 'views.json'})

    def test_complete_coverage_preserves_all_facts_without_mutating_inputs(self):
        source, plan = fixture(); before = deepcopy((source, plan))
        views, receipt, notes = V.build_views(source, plan)
        self.assertEqual((source, plan), before)
        self.assertEqual(notes, source['cards'])
        self.assertEqual(receipt['cards'], source['cards'])
        self.assertEqual([x['edge'] for x in receipt['edges']], source['edges'])
        self.assertEqual(views['data']['edges'], source['edges'][1:])
        self.assertEqual(views['data']['nodes'][0]['detail'], source['nodes'][1]['detail'])
        self.assertEqual(views['data']['nodes'][0]['rank'], 0)
        self.assertNotIn('cards', views['entry'])
        self.assertEqual(receipt['nodes'][1]['views'], ['entry', 'data'])

    def test_missing_parallel_edge_is_not_masked_by_matching_endpoints(self):
        source, plan = fixture(); plan['views'][1]['edges'] = [1]
        with self.assertRaisesRegex(ValueError, r'边 \[2\]'):
            V.build_views(source, plan)

    def test_isolated_node_requires_explicit_view_membership(self):
        source, plan = fixture()
        source['nodes'].append({'id': 'isolated', 'label': '独立组件', 'kind': 'service'})
        with self.assertRaisesRegex(ValueError, 'isolated'):
            V.build_views(source, plan)
        plan['views'][0]['nodes'] = ['isolated']
        self.assertEqual(V.build_views(source, plan)[1]['nodes'][-1]['views'], ['entry'])

    def test_rejects_invalid_plan_without_partial_results(self):
        source, original = fixture()
        for patch in ({'name': '../escape'}, {'edges': [True]}, {'edges': [0, 0]},
                      {'nodes': ['unknown']}, {'ranks': {'unknown': 0}},
                      {'pins': {'a': 'centre'}}, {'made_up': []}):
            plan = deepcopy(original); plan['views'][0].update(patch)
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                V.build_views(source, plan)

    def test_view_colors_retain_ids_and_swatches_without_mutation(self):
        source, plan = fixture(); views, *_ = V.build_views(source, plan)
        colors = {'by_node': {'a': 'blue', 'c': 'green'}, 'by_group': {'g': {'color': 'blue'}, 'elsewhere': {'color': 'green'}}, 'swatches': {'blue': '#123456', 'green': '#567890'}}
        before = deepcopy(colors)
        subset = V.colors_for_view(colors, views['entry'])
        self.assertEqual(subset['by_node'], {'a': 'blue'})
        self.assertEqual(set(subset['by_group']), {'g'})
        self.assertEqual(colors, before)


if __name__ == '__main__':
    unittest.main()
