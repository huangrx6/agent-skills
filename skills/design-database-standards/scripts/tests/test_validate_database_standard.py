#!/usr/bin/env python3
"""validate_database_standard.py 的单元测试。

运行：python -m unittest discover -s scripts/tests -p 'test_*.py'
"""
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import validate_database_standard as v  # noqa: E402


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


BASE_NAMING = {
    'ruleId': 'DBN-001', 'objectType': 'table', 'convention': '小写 snake_case',
    'example': 'order_items', 'severity': 'MUST', 'notes': '',
}
BASE_TYPE = {
    'businessData': '金额', 'preferredType': 'NUMERIC/DECIMAL',
    'avoid': 'FLOAT/DOUBLE', 'keyDecision': '精度和舍入',
}
BASE_MIGRATION = {
    'change': '新增 nullable 列', 'defaultRisk': 'LOW',
    'compatibleRollout': '先加列再发布', 'unsafeShortcut': '同时要求旧应用必填',
    'verification': '新旧应用并存',
}
BASE_REVIEW = {
    'checkId': 'DBR-001', 'category': '模型', 'requirement': '业务不变量明确',
    'severity': 'BLOCKER', 'automatable': 'false', 'evidence': '表设计文档',
}


class ValidateNamingTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'naming.csv'
            write_csv(p, ['ruleId', 'objectType', 'convention', 'example', 'severity', 'notes'],
                      [BASE_NAMING])
            self.assertEqual(v.validate_naming(p), [])

    def test_duplicate_rule_id_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'naming.csv'
            write_csv(p, ['ruleId', 'objectType', 'convention', 'example', 'severity', 'notes'],
                      [BASE_NAMING, dict(BASE_NAMING)])
            self.assertTrue(any('ruleId' in e for e in v.validate_naming(p)))

    def test_bad_severity_rejected(self):
        # naming 用 RULE_SEVERITIES（MUST/SHOULD/MAY），BLOCKER 应被拒
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'naming.csv'
            write_csv(p, ['ruleId', 'objectType', 'convention', 'example', 'severity', 'notes'],
                      [dict(BASE_NAMING, severity='BLOCKER')])
            self.assertTrue(any('severity' in e for e in v.validate_naming(p)))

    def test_short_row_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'naming.csv'
            p.write_text('ruleId,objectType,convention,example,severity,notes\nX,table\n',
                         encoding='utf-8')
            try:
                v.validate_naming(p)
            except Exception as exc:
                self.fail(f'缺列导致崩溃：{type(exc).__name__}: {exc}')


class ValidateTypesTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'types.csv'
            write_csv(p, ['businessData', 'preferredType', 'avoid', 'keyDecision'], [BASE_TYPE])
            self.assertEqual(v.validate_types(p), [])

    def test_empty_field_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'types.csv'
            write_csv(p, ['businessData', 'preferredType', 'avoid', 'keyDecision'],
                      [dict(BASE_TYPE, preferredType='')])
            self.assertTrue(any('空字段' in e for e in v.validate_types(p)))


class ValidateMigrationTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'migration.csv'
            write_csv(p, ['change', 'defaultRisk', 'compatibleRollout', 'unsafeShortcut', 'verification'],
                      [BASE_MIGRATION])
            self.assertEqual(v.validate_migration(p), [])

    def test_bad_risk_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'migration.csv'
            write_csv(p, ['change', 'defaultRisk', 'compatibleRollout', 'unsafeShortcut', 'verification'],
                      [dict(BASE_MIGRATION, defaultRisk='EXTREME')])
            self.assertTrue(any('风险等级无效' in e for e in v.validate_migration(p)))

    def test_empty_rollout_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'migration.csv'
            write_csv(p, ['change', 'defaultRisk', 'compatibleRollout', 'unsafeShortcut', 'verification'],
                      [dict(BASE_MIGRATION, compatibleRollout='')])
            self.assertTrue(any('compatibleRollout 为空' in e for e in v.validate_migration(p)))


class ValidateReviewTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'review.csv'
            write_csv(p, ['checkId', 'category', 'requirement', 'severity', 'automatable', 'evidence'],
                      [BASE_REVIEW])
            self.assertEqual(v.validate_review(p), [])

    def test_bad_severity_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'review.csv'
            write_csv(p, ['checkId', 'category', 'requirement', 'severity', 'automatable', 'evidence'],
                      [dict(BASE_REVIEW, severity='MUST')])
            # review 用 REVIEW_SEVERITIES（BLOCKER/MAJOR/MINOR），MUST 应被拒
            self.assertTrue(any('severity' in e for e in v.validate_review(p)))

    def test_bad_automatable_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'review.csv'
            write_csv(p, ['checkId', 'category', 'requirement', 'severity', 'automatable', 'evidence'],
                      [dict(BASE_REVIEW, automatable='maybe')])
            self.assertTrue(any('automatable' in e for e in v.validate_review(p)))

    def test_duplicate_check_id_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'review.csv'
            write_csv(p, ['checkId', 'category', 'requirement', 'severity', 'automatable', 'evidence'],
                      [BASE_REVIEW, dict(BASE_REVIEW)])
            self.assertTrue(any('checkId' in e for e in v.validate_review(p)))


class ValidateTemplateTest(unittest.TestCase):
    def test_template_with_required_sections_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 't.md'
            p.write_text('## 业务不变量\n## 字段\n## 索引\n## 生命周期\n', encoding='utf-8')
            self.assertEqual(v.validate_template(p, ['业务不变量', '字段', '索引', '生命周期'], '表'), [])

    def test_template_missing_section_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 't.md'
            p.write_text('## 字段\n', encoding='utf-8')
            self.assertTrue(any('缺少' in e for e in
                                v.validate_template(p, ['业务不变量', '字段'], '表')))


class ValidateBadHeaderTest(unittest.TestCase):
    def test_bad_header_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'bad.csv'
            p.write_text('bad1,bad2\nfoo,bar\n', encoding='utf-8')
            try:
                v.validate_naming(p)
            except Exception as exc:
                self.fail(f'表头错误导致崩溃：{type(exc).__name__}: {exc}')


if __name__ == '__main__':
    unittest.main()
