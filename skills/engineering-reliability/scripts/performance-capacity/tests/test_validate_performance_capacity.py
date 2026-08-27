#!/usr/bin/env python3
"""validate_performance_capacity.py 的单元测试。

运行：python -m unittest discover -s scripts/tests -p 'test_*.py'
"""
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import validate_performance_capacity as v  # noqa: E402


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


BASE_BUDGET = {
    'operation': 'document-parse', 'workload': 'median_20_page', 'p50Ms': '800',
    'p95Ms': '1500', 'p99Ms': '3000', 'throughput': '20 docs/s',
    'errorRate': '<0.5%', 'owner': 'knowledge',
}
BASE_SCENARIO = {
    'scenario': 'steady-normal', 'type': 'LOAD', 'duration': '30m',
    'workload': 'production_mix', 'target': 'target_peak', 'stopCondition': 'error>2%',
}
BASE_CAPACITY = {
    'component': 'parser', 'workUnit': 'pages/s', 'capacityPerInstance': '120',
    'limitingResource': 'CPU', 'safeUtilization': '70%', 'headroom': '30%',
    'owner': 'knowledge',
}
BASE_REVIEW = {
    'checkId': 'PERF-001', 'requirement': '关键场景有 P95/P99 与吞吐目标',
    'severity': 'BLOCKER',
}


class BudgetTableTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'budget.csv'
            write_csv(p, v.BUDGET_HEADERS, [BASE_BUDGET])
            self.assertEqual(v.check_table(p, v.BUDGET_HEADERS, 'operation', '性能预算'), [])

    def test_duplicate_operation_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'budget.csv'
            write_csv(p, v.BUDGET_HEADERS, [BASE_BUDGET, dict(BASE_BUDGET)])
            errors = v.check_table(p, v.BUDGET_HEADERS, 'operation', '性能预算')
            self.assertTrue(any('重复' in e for e in errors))

    def test_short_row_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'budget.csv'
            p.write_text('operation,workload,p50Ms,p95Ms,p99Ms,throughput,errorRate,owner\nX,median\n',
                         encoding='utf-8')
            try:
                v.check_table(p, v.BUDGET_HEADERS, 'operation', '性能预算')
            except Exception as exc:
                self.fail(f'缺列导致崩溃：{type(exc).__name__}: {exc}')


class ScenarioTableTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'scenarios.csv'
            write_csv(p, v.SCENARIO_HEADERS, [BASE_SCENARIO])
            self.assertEqual(v.check_table(
                p, v.SCENARIO_HEADERS, 'scenario', '负载测试场景',
                value_checks={'type': v.SCENARIO_TYPES}), [])

    def test_bad_type_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'scenarios.csv'
            write_csv(p, v.SCENARIO_HEADERS, [dict(BASE_SCENARIO, type='DESTROY')])
            errors = v.check_table(p, v.SCENARIO_HEADERS, 'scenario', '负载测试场景',
                                   value_checks={'type': v.SCENARIO_TYPES})
            self.assertTrue(any('type 无效' in e for e in errors))

    def test_duplicate_scenario_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'scenarios.csv'
            write_csv(p, v.SCENARIO_HEADERS, [BASE_SCENARIO, dict(BASE_SCENARIO)])
            errors = v.check_table(p, v.SCENARIO_HEADERS, 'scenario', '负载测试场景')
            self.assertTrue(any('重复' in e for e in errors))


class CapacityTableTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'capacity.csv'
            write_csv(p, v.CAPACITY_HEADERS, [BASE_CAPACITY])
            self.assertEqual(v.check_table(p, v.CAPACITY_HEADERS, 'component', '容量模型'), [])

    def test_duplicate_component_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'capacity.csv'
            write_csv(p, v.CAPACITY_HEADERS, [BASE_CAPACITY, dict(BASE_CAPACITY)])
            errors = v.check_table(p, v.CAPACITY_HEADERS, 'component', '容量模型')
            self.assertTrue(any('重复' in e for e in errors))


class ReviewTableTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'review.csv'
            write_csv(p, v.REVIEW_HEADERS, [BASE_REVIEW])
            self.assertEqual(v.check_table(p, v.REVIEW_HEADERS, 'checkId', '评审清单',
                                           value_checks={'severity': v.SEVERITIES}), [])

    def test_bad_severity_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'review.csv'
            write_csv(p, v.REVIEW_HEADERS, [dict(BASE_REVIEW, severity='CRITICAL')])
            errors = v.check_table(p, v.REVIEW_HEADERS, 'checkId', '评审清单',
                                   value_checks={'severity': v.SEVERITIES})
            self.assertTrue(any('severity 无效' in e for e in errors))


class TemplateTest(unittest.TestCase):
    def test_template_with_all_sections_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'exp.md'
            p.write_text('# Experiment\n\n'
                '- Hypothesis: x\n- Baseline version: 1.0\n- Candidate version: 2.0\n'
                '- Environment: staging\n- Dataset: prod_sample\n- Workload: mix\n\n'
                '## Metrics\n## Single variable changed\n## Result\n'
                '## Bottleneck\n## Decision\n## Follow-up\n', encoding='utf-8')
            self.assertEqual(v.check_experiment_template(p), [])

    def test_template_missing_section_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'exp.md'
            p.write_text('# Experiment\n- Hypothesis: x\n', encoding='utf-8')
            self.assertTrue(any('缺少' in e for e in v.check_experiment_template(p)))

    def test_template_missing_file_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'nonexistent.md'
            self.assertTrue(any('不存在' in e for e in v.check_experiment_template(p)))


class BadHeaderTest(unittest.TestCase):
    def test_bad_header_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'bad.csv'
            p.write_text('bad1,bad2\nfoo,bar\n', encoding='utf-8')
            try:
                v.check_table(p, v.BUDGET_HEADERS, 'operation', '性能预算')
            except Exception as exc:
                self.fail(f'表头错误导致崩溃：{type(exc).__name__}: {exc}')


class MainEndToEndTest(unittest.TestCase):
    def _make_assets_dir(self, tmp: Path) -> Path:
        assets = Path(tmp) / 'assets'
        assets.mkdir()
        write_csv(assets / 'performance-budget.csv', v.BUDGET_HEADERS, [BASE_BUDGET])
        write_csv(assets / 'load-test-scenarios.csv', v.SCENARIO_HEADERS, [BASE_SCENARIO])
        write_csv(assets / 'capacity-model.csv', v.CAPACITY_HEADERS, [BASE_CAPACITY])
        write_csv(assets / 'performance-review-checklist.csv', v.REVIEW_HEADERS, [BASE_REVIEW])
        (assets / 'performance-experiment.template.md').write_text(
            '- Hypothesis: x\n- Baseline version: 1.0\n- Candidate version: 2.0\n'
            '- Environment: s\n- Dataset: d\n- Workload: w\n\n'
            '## Metrics\n## Single variable changed\n## Result\n## Bottleneck\n'
            '## Decision\n## Follow-up\n', encoding='utf-8')
        return assets

    def test_valid_assets_exit_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            assets = self._make_assets_dir(Path(tmp))
            old_argv = sys.argv
            sys.argv = ['prog', '--assets', str(assets)]
            try:
                rc = v.main()
            finally:
                sys.argv = old_argv
            self.assertEqual(rc, 0)

    def test_missing_required_arg_exit_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_argv = sys.argv
            sys.argv = ['prog']
            try:
                rc = v.main()
            except SystemExit as e:
                rc = e.code
            finally:
                sys.argv = old_argv
            self.assertEqual(rc, 2)

    def test_existing_dir_missing_csv_exit_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_argv = sys.argv
            sys.argv = ['prog', '--assets', str(Path(tmp))]
            try:
                rc = v.main()
            finally:
                sys.argv = old_argv
            self.assertEqual(rc, 1)


if __name__ == '__main__':
    unittest.main()
