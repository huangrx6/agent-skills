#!/usr/bin/env python3
"""validate_resilience.py 的单元测试。

运行：python -m unittest discover -s scripts/tests -p 'test_*.py'
"""
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import validate_resilience as v  # noqa: E402


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


BASE_CONTROL = {
    'controlId': 'RES-001', 'category': 'TIMEOUT', 'requirement': '所有远程依赖有 Deadline/Timeout',
    'severity': 'MUST',
}
BASE_DEP = {
    'dependency': 'payment-provider', 'criticality': 'CRITICAL', 'timeoutMs': '800',
    'maxAttempts': '2', 'retryable': 'timeout', 'concurrencyLimit': '50',
    'fallback': 'none', 'owner': 'payments',
}
BASE_REVIEW = {
    'checkId': 'RR-001', 'requirement': '关键路径有端到端 Deadline', 'severity': 'BLOCKER',
}


class ControlTableTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'control.csv'
            write_csv(p, ['controlId', 'category', 'requirement', 'severity'], [BASE_CONTROL])
            errors = v.check_table(p, ['controlId', 'category', 'requirement', 'severity'],
                                   'controlId', '控制目录',
                                   value_checks={'category': v.CONTROL_CATEGORIES,
                                                  'severity': v.SEVERITIES})
            self.assertEqual(errors, [])

    def test_bad_category_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'control.csv'
            write_csv(p, ['controlId', 'category', 'requirement', 'severity'],
                      [dict(BASE_CONTROL, category='UNKNOWN')])
            errors = v.check_table(p, ['controlId', 'category', 'requirement', 'severity'],
                                   'controlId', '控制目录',
                                   value_checks={'category': v.CONTROL_CATEGORIES})
            self.assertTrue(any('category 无效' in e for e in errors))

    def test_bad_severity_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'control.csv'
            write_csv(p, ['controlId', 'category', 'requirement', 'severity'],
                      [dict(BASE_CONTROL, severity='CRITICAL')])
            errors = v.check_table(p, ['controlId', 'category', 'requirement', 'severity'],
                                   'controlId', '控制目录',
                                   value_checks={'severity': v.SEVERITIES})
            self.assertTrue(any('severity 无效' in e for e in errors))

    def test_duplicate_control_id_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'control.csv'
            write_csv(p, ['controlId', 'category', 'requirement', 'severity'],
                      [BASE_CONTROL, dict(BASE_CONTROL)])
            errors = v.check_table(p, ['controlId', 'category', 'requirement', 'severity'],
                                   'controlId', '控制目录')
            self.assertTrue(any('重复' in e for e in errors))

    def test_short_row_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'control.csv'
            p.write_text('controlId,category,requirement,severity\nX,TIMEOUT\n', encoding='utf-8')
            try:
                v.check_table(p, ['controlId', 'category', 'requirement', 'severity'],
                              'controlId', '控制目录')
            except Exception as exc:
                self.fail(f'缺列导致崩溃：{type(exc).__name__}: {exc}')


class DependencyTableTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'dep.csv'
            write_csv(p, ['dependency', 'criticality', 'timeoutMs', 'maxAttempts',
                          'retryable', 'concurrencyLimit', 'fallback', 'owner'], [BASE_DEP])
            errors = v.check_table(p, ['dependency', 'criticality', 'timeoutMs', 'maxAttempts',
                                        'retryable', 'concurrencyLimit', 'fallback', 'owner'],
                                   'dependency', '依赖策略',
                                   value_checks={'criticality': v.DEPENDENCY_CRITICALITY,
                                                 'retryable': v.RETRYABLE_VALUES})
            self.assertEqual(errors, [])

    def test_bad_criticality_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'dep.csv'
            write_csv(p, ['dependency', 'criticality', 'timeoutMs', 'maxAttempts',
                          'retryable', 'concurrencyLimit', 'fallback', 'owner'],
                      [dict(BASE_DEP, criticality='URGENT')])
            errors = v.check_table(p, ['dependency', 'criticality', 'timeoutMs', 'maxAttempts',
                                        'retryable', 'concurrencyLimit', 'fallback', 'owner'],
                                   'dependency', '依赖策略',
                                   value_checks={'criticality': v.DEPENDENCY_CRITICALITY})
            self.assertTrue(any('criticality 无效' in e for e in errors))

    def test_bad_retryable_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'dep.csv'
            write_csv(p, ['dependency', 'criticality', 'timeoutMs', 'maxAttempts',
                          'retryable', 'concurrencyLimit', 'fallback', 'owner'],
                      [dict(BASE_DEP, retryable='EVERYTHING')])
            errors = v.check_table(p, ['dependency', 'criticality', 'timeoutMs', 'maxAttempts',
                                        'retryable', 'concurrencyLimit', 'fallback', 'owner'],
                                   'dependency', '依赖策略',
                                   value_checks={'retryable': v.RETRYABLE_VALUES})
            self.assertTrue(any('retryable 无效' in e for e in errors))

    def test_duplicate_dependency_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'dep.csv'
            write_csv(p, ['dependency', 'criticality', 'timeoutMs', 'maxAttempts',
                          'retryable', 'concurrencyLimit', 'fallback', 'owner'],
                      [BASE_DEP, dict(BASE_DEP)])
            errors = v.check_table(p, ['dependency', 'criticality', 'timeoutMs', 'maxAttempts',
                                        'retryable', 'concurrencyLimit', 'fallback', 'owner'],
                                   'dependency', '依赖策略')
            self.assertTrue(any('重复' in e for e in errors))


class ReviewTableTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'review.csv'
            write_csv(p, ['checkId', 'requirement', 'severity'], [BASE_REVIEW])
            errors = v.check_table(p, ['checkId', 'requirement', 'severity'],
                                   'checkId', '评审清单',
                                   value_checks={'severity': v.REVIEW_SEVERITIES})
            self.assertEqual(errors, [])

    def test_bad_severity_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'review.csv'
            write_csv(p, ['checkId', 'requirement', 'severity'],
                      [dict(BASE_REVIEW, severity='CRITICAL')])
            errors = v.check_table(p, ['checkId', 'requirement', 'severity'],
                                   'checkId', '评审清单',
                                   value_checks={'severity': v.REVIEW_SEVERITIES})
            self.assertTrue(any('severity 无效' in e for e in errors))


class TemplateTest(unittest.TestCase):
    def _write_template(self, path: Path, text: str):
        path.write_text(text, encoding='utf-8')

    def test_template_with_all_sections_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'fip.md'
            self._write_template(p, '# Plan\n\n'
                '- Service: order-service\n'
                '- Owner: 交易组\n'
                '- Hypothesis: slow payment will not cause cascade\n'
                '- Blast radius: 1 canary, 1% traffic\n'
                '- Stop condition: P99 > 1.5s\n\n'
                '## Failure\n## Expected behavior\n## Metrics\n## Result\n## Follow-up\n')
            self.assertEqual(v.check_failure_injection_template(p), [])

    def test_template_missing_section_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'fip.md'
            self._write_template(p, '# Plan\n- Service: x\n')
            errors = v.check_failure_injection_template(p)
            self.assertTrue(any('缺少' in e for e in errors))

    def test_template_missing_file_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'nonexistent.md'
            errors = v.check_failure_injection_template(p)
            self.assertTrue(any('不存在' in e for e in errors))


class BadHeaderTest(unittest.TestCase):
    def test_bad_header_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'bad.csv'
            p.write_text('bad1,bad2\nfoo,bar\n', encoding='utf-8')
            try:
                v.check_table(p, ['controlId', 'category', 'requirement', 'severity'],
                              'controlId', '控制目录')
            except Exception as exc:
                self.fail(f'表头错误导致崩溃：{type(exc).__name__}: {exc}')


class MainEndToEndTest(unittest.TestCase):
    """走真实 main() 入口，验证参数解析、退出码。"""

    def _make_assets_dir(self, tmp: Path) -> Path:
        assets = Path(tmp) / 'assets'
        assets.mkdir()
        write_csv(assets / 'resilience-control-catalog.csv',
                  ['controlId', 'category', 'requirement', 'severity'], [BASE_CONTROL])
        write_csv(assets / 'dependency-resilience-policy.csv',
                  ['dependency', 'criticality', 'timeoutMs', 'maxAttempts',
                   'retryable', 'concurrencyLimit', 'fallback', 'owner'], [BASE_DEP])
        write_csv(assets / 'resilience-review-checklist.csv',
                  ['checkId', 'requirement', 'severity'], [BASE_REVIEW])
        (assets / 'failure-injection-plan.template.md').write_text(
            '- Service: x\n- Owner: y\n- Hypothesis: z\n- Blast radius: a\n- Stop condition: b\n\n'
            '## Failure\n## Expected behavior\n## Metrics\n## Result\n## Follow-up\n',
            encoding='utf-8')
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
        # 不传 --assets 触发 argparse 错误 → SystemExit(exit 2)
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
        # 资产目录存在但 CSV 缺失 → check_table 返回 errors → exit 1
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
