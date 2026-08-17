#!/usr/bin/env python3
"""validate_secure_coding.py 与 security_impact.py 的单元测试。

运行：python -m unittest discover -s scripts/tests -p 'test_*.py'
"""
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import validate_secure_coding as v  # noqa: E402
import security_impact  # noqa: E402


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


BASE_CONTROL = {
    'controlId': 'SEC-001', 'category': 'TRUST_BOUNDARY', 'requirement': '输入按不可信处理',
    'severity': 'MUST', 'automatable': 'partly', 'evidence': 'data-flow review',
}
BASE_TAINT = {
    'source': 'HTTP/RPC/GraphQL input', 'sink': 'SQL/NoSQL',
    'primaryControl': 'parameterized query', 'secondaryControls': 'allowlist',
    'reviewPriority': 'CRITICAL',
}
BASE_IMPACT = {
    'pathPattern': '**/auth/**', 'securityAreas': 'AUTHN|AUTHZ',
    'reason': 'identity boundary changed', 'requiredAction': 'Run auth review',
}
BASE_REVIEW = {
    'checkId': 'SR-001', 'category': 'INPUT', 'requirement': '输入有资源限制',
    'severity': 'BLOCKER', 'automatable': 'partly', 'evidence': 'schema/tests',
}


class ControlValuesTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'control.csv'
            write_csv(p, ['controlId', 'category', 'requirement', 'severity',
                          'automatable', 'evidence'], [BASE_CONTROL])
            self.assertEqual(v.validate_control_values(p), [])

    def test_bad_severity_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'control.csv'
            write_csv(p, ['controlId', 'category', 'requirement', 'severity',
                          'automatable', 'evidence'],
                      [dict(BASE_CONTROL, severity='CRITICAL')])
            self.assertTrue(any('severity' in e for e in v.validate_control_values(p)))

    def test_bad_automatable_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'control.csv'
            write_csv(p, ['controlId', 'category', 'requirement', 'severity',
                          'automatable', 'evidence'],
                      [dict(BASE_CONTROL, automatable='sometimes')])
            self.assertTrue(any('automatable' in e for e in v.validate_control_values(p)))

    def test_duplicate_control_id_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'control.csv'
            write_csv(p, ['controlId', 'category', 'requirement', 'severity',
                          'automatable', 'evidence'],
                      [BASE_CONTROL, dict(BASE_CONTROL)])
            self.assertTrue(any('重复' in e for e in v.validate_control_values(p)))

    def test_short_row_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'control.csv'
            p.write_text('controlId,category,requirement,severity,automatable,evidence\nX,TRUST\n',
                         encoding='utf-8')
            try:
                v.validate_control_values(p)
            except Exception as exc:
                self.fail(f'缺列导致崩溃：{type(exc).__name__}: {exc}')


class TaintValuesTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'taint.csv'
            write_csv(p, ['source', 'sink', 'primaryControl', 'secondaryControls',
                          'reviewPriority'], [BASE_TAINT])
            self.assertEqual(v.validate_taint_values(p), [])

    def test_bad_priority_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'taint.csv'
            write_csv(p, ['source', 'sink', 'primaryControl', 'secondaryControls',
                          'reviewPriority'],
                      [dict(BASE_TAINT, reviewPriority='URGENT')])
            self.assertTrue(any('reviewPriority' in e for e in v.validate_taint_values(p)))

    def test_duplicate_source_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'taint.csv'
            write_csv(p, ['source', 'sink', 'primaryControl', 'secondaryControls',
                          'reviewPriority'],
                      [BASE_TAINT, dict(BASE_TAINT)])
            self.assertTrue(any('重复' in e for e in v.validate_taint_values(p)))


class ImpactTableTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'impact.csv'
            write_csv(p, ['pathPattern', 'securityAreas', 'reason', 'requiredAction'],
                      [BASE_IMPACT])
            self.assertEqual(v.table(p, ['pathPattern', 'securityAreas', 'reason',
                                         'requiredAction'], 'pathPattern'), [])


class ReviewValuesTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'review.csv'
            write_csv(p, ['checkId', 'category', 'requirement', 'severity',
                          'automatable', 'evidence'], [BASE_REVIEW])
            self.assertEqual(v.validate_review_values(p), [])

    def test_bad_severity_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'review.csv'
            write_csv(p, ['checkId', 'category', 'requirement', 'severity',
                          'automatable', 'evidence'],
                      [dict(BASE_REVIEW, severity='MUST')])
            self.assertTrue(any('severity' in e for e in v.validate_review_values(p)))


class SecurityImpactMatchTest(unittest.TestCase):
    def test_match_directory_pattern(self):
        self.assertTrue(security_impact.matches('**/auth/**', 'src/main/java/com/x/auth/Service.java'))
        self.assertFalse(security_impact.matches('**/auth/**', 'src/main/java/com/x/Service.java'))

    def test_match_filename_pattern(self):
        # 类名规则：*Controller*.java
        self.assertTrue(security_impact.matches('*Controller*.java', 'OrderController.java'))
        self.assertTrue(security_impact.matches('*Controller*.java', 'src/main/java/OrderController.java'))
        self.assertFalse(security_impact.matches('*Controller*.java', 'OrderService.java'))

    def test_match_config_file(self):
        self.assertTrue(security_impact.matches('*.yml', 'application.yml'))
        self.assertTrue(security_impact.matches('*.env', '.env'))

    def test_match_without_double_star(self):
        self.assertTrue(security_impact.matches('**/api/**', 'api/v1/orders.yaml'))


class SecurityImpactMainTest(unittest.TestCase):
    def _run(self, tmp: Path, path: str):
        rules = tmp / 'rules.csv'
        write_csv(rules, ['pathPattern', 'securityAreas', 'reason', 'requiredAction'],
                  [{'pathPattern': '*Controller*.java', 'securityAreas': 'INPUT|AUTHZ',
                    'reason': 'input surface changed', 'requiredAction': 'check validation'}])
        old_argv = sys.argv
        sys.argv = ['prog', '--rules', str(rules), path]
        import io, contextlib
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = security_impact.main()
            return rc, buf.getvalue()
        finally:
            sys.argv = old_argv

    def test_matching_path_outputs_areas(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, out = self._run(Path(tmp), 'src/OrderController.java')
            self.assertEqual(rc, 0)
            self.assertIn('INPUT|AUTHZ', out)

    def test_no_match_prints_hint(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, out = self._run(Path(tmp), 'src/OrderService.java')
            self.assertEqual(rc, 0)
            self.assertIn('未匹配', out)



if __name__ == '__main__':
    unittest.main()
