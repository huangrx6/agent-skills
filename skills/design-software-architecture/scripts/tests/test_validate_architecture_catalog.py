#!/usr/bin/env python3
"""validate_architecture_catalog.py 的单元测试。

运行：python -m unittest discover -s scripts/tests -p 'test_*.py'
"""
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import validate_architecture_catalog as v  # noqa: E402


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


BASE_DECISION = {
    'style': 'MODULAR_MONOLITH', 'preferWhen': '边界演进中',
    'avoidWhen': '独立扩缩需求明确', 'keyBenefits': '简单部署',
    'keyCosts': '需严格模块治理', 'evidenceRequired': '模块依赖证明',
}
BASE_QUALITY = {
    'id': 'QA-001', 'qualityAttribute': 'PERFORMANCE', 'source': '用户',
    'stimulus': '提交订单', 'environment': '正常高峰', 'artifact': '订单 API',
    'response': '完成创建', 'measure': 'P99 <= 800ms', 'priority': 'HIGH',
}
BASE_RISK = {
    'riskId': 'AR-001', 'category': 'COUPLING', 'risk': '共享写数据库',
    'likelihood': 'HIGH', 'impact': 'HIGH', 'mitigation': '明确 Owner',
    'owner': 'Architecture', 'status': 'OPEN', 'revisitTrigger': '新增第三个共享写',
}
BASE_REVIEW = {
    'checkId': 'ARCH-001', 'category': 'DRIVERS', 'requirement': '质量属性可测',
    'severity': 'BLOCKER', 'automatable': 'partly', 'evidence': 'QA scenarios',
}


class ValidateDecisionTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'decision.csv'
            write_csv(p, ['style', 'preferWhen', 'avoidWhen', 'keyBenefits',
                          'keyCosts', 'evidenceRequired'], [BASE_DECISION])
            self.assertEqual(v.validate_decision(p), [])

    def test_unknown_style_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'decision.csv'
            write_csv(p, ['style', 'preferWhen', 'avoidWhen', 'keyBenefits',
                          'keyCosts', 'evidenceRequired'],
                      [dict(BASE_DECISION, style='SPAGHETTI')])
            self.assertTrue(any('style 无效' in e for e in v.validate_decision(p)))

    def test_duplicate_style_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'decision.csv'
            write_csv(p, ['style', 'preferWhen', 'avoidWhen', 'keyBenefits',
                          'keyCosts', 'evidenceRequired'],
                      [BASE_DECISION, dict(BASE_DECISION)])
            self.assertTrue(any('重复' in e for e in v.validate_decision(p)))


class ValidateQualityTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'qa.csv'
            write_csv(p, ['id', 'qualityAttribute', 'source', 'stimulus',
                          'environment', 'artifact', 'response', 'measure', 'priority'],
                      [BASE_QUALITY])
            self.assertEqual(v.validate_quality(p), [])

    def test_bad_priority_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'qa.csv'
            write_csv(p, ['id', 'qualityAttribute', 'source', 'stimulus',
                          'environment', 'artifact', 'response', 'measure', 'priority'],
                      [dict(BASE_QUALITY, priority='URGENT')])
            self.assertTrue(any('priority' in e for e in v.validate_quality(p)))

    def test_duplicate_id_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'qa.csv'
            write_csv(p, ['id', 'qualityAttribute', 'source', 'stimulus',
                          'environment', 'artifact', 'response', 'measure', 'priority'],
                      [BASE_QUALITY, dict(BASE_QUALITY)])
            self.assertTrue(any('重复' in e for e in v.validate_quality(p)))


class ValidateRiskTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'risk.csv'
            write_csv(p, ['riskId', 'category', 'risk', 'likelihood', 'impact',
                          'mitigation', 'owner', 'status', 'revisitTrigger'], [BASE_RISK])
            self.assertEqual(v.validate_risk(p), [])

    def test_bad_likelihood_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'risk.csv'
            write_csv(p, ['riskId', 'category', 'risk', 'likelihood', 'impact',
                          'mitigation', 'owner', 'status', 'revisitTrigger'],
                      [dict(BASE_RISK, likelihood='EXTREME')])
            self.assertTrue(any('likelihood' in e for e in v.validate_risk(p)))

    def test_bad_status_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'risk.csv'
            write_csv(p, ['riskId', 'category', 'risk', 'likelihood', 'impact',
                          'mitigation', 'owner', 'status', 'revisitTrigger'],
                      [dict(BASE_RISK, status='HIDDEN')])
            self.assertTrue(any('status' in e for e in v.validate_risk(p)))


class ValidateReviewTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'review.csv'
            write_csv(p, ['checkId', 'category', 'requirement', 'severity',
                          'automatable', 'evidence'], [BASE_REVIEW])
            self.assertEqual(v.validate_review(p), [])

    def test_bad_severity_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'review.csv'
            write_csv(p, ['checkId', 'category', 'requirement', 'severity',
                          'automatable', 'evidence'],
                      [dict(BASE_REVIEW, severity='CRITICAL')])
            self.assertTrue(any('severity' in e for e in v.validate_review(p)))

    def test_bad_automatable_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'review.csv'
            write_csv(p, ['checkId', 'category', 'requirement', 'severity',
                          'automatable', 'evidence'],
                      [dict(BASE_REVIEW, automatable='sometimes')])
            self.assertTrue(any('automatable' in e for e in v.validate_review(p)))

    def test_short_row_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'review.csv'
            p.write_text('checkId,category,requirement,severity,automatable,evidence\nX,DRIVERS\n',
                         encoding='utf-8')
            try:
                v.validate_review(p)
            except Exception as exc:
                self.fail(f'缺列导致崩溃：{type(exc).__name__}: {exc}')


class ValidateTemplatesTest(unittest.TestCase):
    def test_adr_with_all_sections_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            adr = Path(tmp) / 'adr.md'
            brief = Path(tmp) / 'brief.md'
            adr.write_text(''.join(f'## {s}\n' for s in (
                '## Context', '## Architecture Drivers', '## Decision', '## Alternatives',
                '## Consequences', '## Risks and Mitigations', '## Validation',
                '## Revisit Trigger', '## Supersedes / Superseded By')), encoding='utf-8')
            brief.write_text(''.join(f'## {s}\n' for s in (
                '## 1. 系统目标', '## 3. Architecture Drivers', '## 4. 边界与数据所有权',
                '## 6. 集成与一致性', '## 9. 关键风险')), encoding='utf-8')
            self.assertEqual(v.validate_templates(adr, brief), [])

    def test_adr_missing_section_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            adr = Path(tmp) / 'adr.md'
            brief = Path(tmp) / 'brief.md'
            adr.write_text('## Context\n', encoding='utf-8')
            brief.write_text('## 1. 系统目标\n', encoding='utf-8')
            self.assertTrue(any('ADR 模板缺少' in e for e in v.validate_templates(adr, brief)))


class ValidateBadHeaderTest(unittest.TestCase):
    def test_bad_header_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'bad.csv'
            p.write_text('bad1,bad2\nfoo,bar\n', encoding='utf-8')
            try:
                v.validate_decision(p)
            except Exception as exc:
                self.fail(f'表头错误导致崩溃：{type(exc).__name__}: {exc}')


if __name__ == '__main__':
    unittest.main()
