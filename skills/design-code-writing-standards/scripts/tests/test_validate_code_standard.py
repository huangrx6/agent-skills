#!/usr/bin/env python3
"""validate_code_standard.py 的单元测试。

运行：python -m unittest discover -s scripts/tests -p 'test_*.py'
"""
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import validate_code_standard as v  # noqa: E402


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


BASE_NAMING = {
    'ruleId': 'NAM-001', 'scope': '领域术语', 'language': 'ALL',
    'convention': '同一概念使用同一术语', 'example': 'orderId',
    'severity': 'MUST', 'rationale': '减少语义漂移',
}
BASE_HEADER = {
    'policyId': 'HDR-001', 'fileType': '普通源文件', 'field': 'SPDX-License-Identifier',
    'requirement': 'CONDITIONAL', 'sourceOfTruth': '法务策略',
    'example': 'SPDX-License-Identifier: Apache-2.0', 'notes': '',
}
BASE_PATTERN = {
    'pattern': 'Strategy', 'useWhen': '多个可替换算法',
    'avoidWhen': '单个分支', 'requiredEvidence': '两个真实策略',
    'reviewQuestions': '契约是否稳定',
}
BASE_REVIEW = {
    'checkId': 'REV-001', 'category': '格式', 'requirement': '通过唯一格式化器',
    'severity': 'BLOCKER', 'automatable': 'true', 'evidence': 'CI 格式检查',
}
BASE_STD = {
    'checkId': 'STD-001', 'section': '元要求', 'requirement': '明确适用范围',
    'severity': 'BLOCKER', 'guidance': '引用 SKILL',
}


class ValidateNamingTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'naming.csv'
            write_csv(p, v.NAMING_HEADERS, [BASE_NAMING])
            self.assertEqual(v.validate_naming(p), [])

    def test_duplicate_rule_id_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'naming.csv'
            write_csv(p, v.NAMING_HEADERS, [BASE_NAMING, dict(BASE_NAMING)])
            self.assertTrue(any('重复' in e for e in v.validate_naming(p)))

    def test_bad_severity_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'naming.csv'
            write_csv(p, v.NAMING_HEADERS, [dict(BASE_NAMING, severity='INVALID')])
            self.assertTrue(any('severity' in e for e in v.validate_naming(p)))

    def test_missing_example_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'naming.csv'
            write_csv(p, v.NAMING_HEADERS, [dict(BASE_NAMING, example='')])
            self.assertTrue(any('example 不能为空' in e for e in v.validate_naming(p)))

    def test_short_row_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'naming.csv'
            p.write_text('ruleId,scope,language,convention,example,severity,rationale\nX,领域,ALL\n',
                         encoding='utf-8')
            try:
                v.validate_naming(p)
            except Exception as exc:
                self.fail(f'缺列导致崩溃：{type(exc).__name__}: {exc}')


class ValidateHeaderPolicyTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'hdr.csv'
            write_csv(p, v.HEADER_POLICY_HEADERS, [BASE_HEADER])
            self.assertEqual(v.validate_header_policy(p), [])

    def test_required_without_example_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'hdr.csv'
            write_csv(p, v.HEADER_POLICY_HEADERS,
                      [dict(BASE_HEADER, requirement='REQUIRED', example='')])
            self.assertTrue(any('REQUIRED 项必须提供 example' in e for e in v.validate_header_policy(p)))

    def test_bad_requirement_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'hdr.csv'
            write_csv(p, v.HEADER_POLICY_HEADERS, [dict(BASE_HEADER, requirement='NEVER')])
            self.assertTrue(any('requirement' in e for e in v.validate_header_policy(p)))

    def test_prohibited_without_example_ok(self):
        # PROHIBITED 项不要求 example（反例留空合理）
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'hdr.csv'
            write_csv(p, v.HEADER_POLICY_HEADERS,
                      [dict(BASE_HEADER, requirement='PROHIBITED', example='')])
            self.assertEqual(v.validate_header_policy(p), [])


class ValidatePatternsTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'patterns.csv'
            write_csv(p, v.PATTERN_HEADERS, [BASE_PATTERN])
            self.assertEqual(v.validate_patterns(p), [])

    def test_duplicate_pattern_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'patterns.csv'
            write_csv(p, v.PATTERN_HEADERS, [BASE_PATTERN, dict(BASE_PATTERN)])
            self.assertTrue(any('重复' in e for e in v.validate_patterns(p)))

    def test_empty_use_when_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'patterns.csv'
            write_csv(p, v.PATTERN_HEADERS, [dict(BASE_PATTERN, useWhen='')])
            self.assertTrue(any('useWhen 不能为空' in e for e in v.validate_patterns(p)))


class ValidateReviewTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'review.csv'
            write_csv(p, v.REVIEW_HEADERS, [BASE_REVIEW])
            self.assertEqual(v.validate_review(p), [])

    def test_bad_severity_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'review.csv'
            write_csv(p, v.REVIEW_HEADERS, [dict(BASE_REVIEW, severity='CRITICAL')])
            self.assertTrue(any('severity' in e for e in v.validate_review(p)))

    def test_bad_automatable_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'review.csv'
            write_csv(p, v.REVIEW_HEADERS, [dict(BASE_REVIEW, automatable='sometimes')])
            self.assertTrue(any('automatable' in e for e in v.validate_review(p)))


class ValidateStandardCompletenessTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'std.csv'
            write_csv(p, v.STD_HEADERS, [BASE_STD])
            self.assertEqual(v.validate_standard_completeness(p), [])

    def test_bad_severity_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'std.csv'
            write_csv(p, v.STD_HEADERS, [dict(BASE_STD, severity='URGENT')])
            self.assertTrue(any('severity' in e for e in v.validate_standard_completeness(p)))

    def test_empty_section_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'std.csv'
            write_csv(p, v.STD_HEADERS, [dict(BASE_STD, section='')])
            self.assertTrue(any('section 不能为空' in e for e in v.validate_standard_completeness(p)))


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
