#!/usr/bin/env python3
"""validate_observability.py 的单元测试。

运行：python -m unittest discover -s scripts/tests -p 'test_*.py'
"""
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import validate_observability as v  # noqa: E402


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


BASE_SIGNAL = {
    'signal': 'METRICS', 'purpose': 'trend/sli/alert',
    'requiredIdentity': 'service.name|environment',
    'cardinalityPolicy': 'bounded_labels_only', 'owner': 'platform',
}
BASE_SLI = {
    'sliId': 'SLI-001', 'service': 'orders', 'name': 'availability',
    'numerator': 'successful_valid_requests', 'denominator': 'valid_requests',
    'window': '28d', 'target': '99.9%', 'owner': 'orders',
}
BASE_ALERT = {
    'alert': 'orders-slo-burn', 'condition': 'multi_window_burn',
    'severity': 'PAGE', 'action': 'investigate_user_impact',
    'runbook': 'runbooks/orders-slo.md', 'owner': 'orders',
}
BASE_REVIEW = {
    'checkId': 'OBS-001', 'requirement': '跨信号 Resource Identity 一致',
    'severity': 'BLOCKER',
}


class SignalTableTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'signal.csv'
            write_csv(p, v.SIGNAL_HEADERS, [BASE_SIGNAL])
            self.assertEqual(v.check_table(p, v.SIGNAL_HEADERS, 'signal', '信号目录',
                                           value_checks={'signal': v.SIGNAL_TYPES}), [])

    def test_bad_signal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'signal.csv'
            write_csv(p, v.SIGNAL_HEADERS, [dict(BASE_SIGNAL, signal='EVENTS')])
            errors = v.check_table(p, v.SIGNAL_HEADERS, 'signal', '信号目录',
                                   value_checks={'signal': v.SIGNAL_TYPES})
            self.assertTrue(any('signal 无效' in e for e in errors))

    def test_duplicate_signal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'signal.csv'
            write_csv(p, v.SIGNAL_HEADERS, [BASE_SIGNAL, dict(BASE_SIGNAL)])
            errors = v.check_table(p, v.SIGNAL_HEADERS, 'signal', '信号目录')
            self.assertTrue(any('重复' in e for e in errors))

    def test_short_row_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'signal.csv'
            p.write_text('signal,purpose,requiredIdentity,cardinalityPolicy,owner\nX,trend\n',
                         encoding='utf-8')
            try:
                v.check_table(p, v.SIGNAL_HEADERS, 'signal', '信号目录')
            except Exception as exc:
                self.fail(f'缺列导致崩溃：{type(exc).__name__}: {exc}')


class SliTableTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'sli.csv'
            write_csv(p, v.SLI_HEADERS, [BASE_SLI])
            self.assertEqual(v.check_table(p, v.SLI_HEADERS, 'sliId', 'SLI 目录'), [])

    def test_duplicate_sli_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'sli.csv'
            write_csv(p, v.SLI_HEADERS, [BASE_SLI, dict(BASE_SLI)])
            errors = v.check_table(p, v.SLI_HEADERS, 'sliId', 'SLI 目录')
            self.assertTrue(any('重复' in e for e in errors))


class AlertTableTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'alert.csv'
            write_csv(p, v.ALERT_HEADERS, [BASE_ALERT])
            self.assertEqual(v.check_table(p, v.ALERT_HEADERS, 'alert', '告警策略',
                                           value_checks={'severity': v.ALERT_SEVERITIES}), [])

    def test_bad_severity_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'alert.csv'
            write_csv(p, v.ALERT_HEADERS, [dict(BASE_ALERT, severity='URGENT')])
            errors = v.check_table(p, v.ALERT_HEADERS, 'alert', '告警策略',
                                   value_checks={'severity': v.ALERT_SEVERITIES})
            self.assertTrue(any('severity 无效' in e for e in errors))


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


class BadHeaderTest(unittest.TestCase):
    def test_bad_header_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'bad.csv'
            p.write_text('bad1,bad2\nfoo,bar\n', encoding='utf-8')
            try:
                v.check_table(p, v.SIGNAL_HEADERS, 'signal', '信号目录')
            except Exception as exc:
                self.fail(f'表头错误导致崩溃：{type(exc).__name__}: {exc}')


class MainEndToEndTest(unittest.TestCase):
    def _make_assets_dir(self, tmp: Path) -> Path:
        assets = Path(tmp) / 'assets'
        assets.mkdir()
        write_csv(assets / 'telemetry-signal-catalog.csv', v.SIGNAL_HEADERS, [BASE_SIGNAL])
        write_csv(assets / 'sli-catalog.csv', v.SLI_HEADERS, [BASE_SLI])
        write_csv(assets / 'alert-policy.csv', v.ALERT_HEADERS, [BASE_ALERT])
        write_csv(assets / 'observability-review-checklist.csv', v.REVIEW_HEADERS, [BASE_REVIEW])
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
