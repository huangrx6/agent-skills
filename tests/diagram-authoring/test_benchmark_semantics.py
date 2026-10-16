"""Aliases must not let a missing mandatory relationship pass the benchmark."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[2] / 'skills/diagram-authoring/benchmarks/first-pass/verify.py'
spec = importlib.util.spec_from_file_location('benchmark_semantics_test', path)
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)


class BenchmarkSemanticTests(unittest.TestCase):
    CASE = {'required_nodes': [{'aliases': ['用户', 'client'], 'kind': 'client'},
                               {'aliases': ['服务', 'service'], 'kind': 'service'}],
            'required_edges': [{'from': '用户', 'to': '服务'}]}

    def candidate(self, edges):
        return {'nodes': [{'id': 'a', 'label': 'client', 'kind': 'client'},
                          {'id': 'b', 'label': 'service', 'kind': 'service'}], 'edges': edges}

    def test_secondary_alias_does_not_skip_missing_edge(self):
        ok, problems = V.gate_semantic(self.CASE, self.candidate([]))
        self.assertFalse(ok)
        self.assertTrue(any('必须边缺失' in p for p in problems))

    def test_secondary_alias_with_correct_edge_passes(self):
        self.assertEqual(V.gate_semantic(self.CASE, self.candidate([{'from': 'a', 'to': 'b'}])), (True, []))

    def test_ambiguous_and_reused_nodes_do_not_pass(self):
        candidate = self.candidate([])
        candidate['nodes'].append({'id': 'c', 'label': 'client', 'kind': 'client'})
        _, missing = V.bind_nodes(candidate, self.CASE['required_nodes'])
        self.assertTrue(missing)
        _, missing = V.bind_nodes(self.candidate([]), [self.CASE['required_nodes'][0]] * 2)
        self.assertTrue(missing)


if __name__ == '__main__':
    unittest.main()
