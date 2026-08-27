#!/usr/bin/env python3
"""validate_api_contract_catalog.py 的单元测试。

运行：python -m unittest discover -s scripts/tests -p 'test_*.py'
"""
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import validate_api_contract_catalog as v  # noqa: E402


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


BASE_RULE = {
    'ruleId': 'API-001', 'category': '资源', 'requirement': 'URI 标识资源',
    'severity': 'MUST', 'automatable': 'partly', 'evidence': 'OpenAPI lint',
}
BASE_COMPAT = {
    'changeType': '新增可选字段', 'location': '响应', 'example': '新增 displayName',
    'defaultClassification': 'COMPATIBLE', 'conditions': '客户端容忍未知字段',
    'requiredAction': '运行差异检查',
}
BASE_STATUS = {
    'operation': '读取单资源', 'method': 'GET', 'successStatus': '200',
    'conditionalStatus': '304', 'commonClientErrors': '400|401|403|404|429',
    'notes': '支持条件 GET',
}
BASE_REVIEW = {
    'checkId': 'REV-API-001', 'category': '资源', 'requirement': '资源和动作模型清晰',
    'severity': 'BLOCKER', 'automatable': 'false', 'evidence': '设计说明',
}
BASE_STYLE = {
    'style': 'REST_STYLE_HTTP', 'primaryUse': '公开 API', 'direction': 'request-response',
    'contract': 'OpenAPI', 'strengths': '通用', 'mainRisks': '聚合多请求',
    'defaultFor': '资源生命周期',
}


class RulesTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'rules.csv'
            write_csv(p, ['ruleId', 'category', 'requirement', 'severity', 'automatable', 'evidence'],
                      [BASE_RULE])
            self.assertEqual(v.rules(p), [])

    def test_duplicate_rule_id_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'rules.csv'
            write_csv(p, ['ruleId', 'category', 'requirement', 'severity', 'automatable', 'evidence'],
                      [BASE_RULE, dict(BASE_RULE)])
            self.assertTrue(any('ruleId' in e for e in v.rules(p)))

    def test_bad_severity_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'rules.csv'
            write_csv(p, ['ruleId', 'category', 'requirement', 'severity', 'automatable', 'evidence'],
                      [dict(BASE_RULE, severity='INVALID')])
            self.assertTrue(any('severity' in e for e in v.rules(p)))

    def test_bad_automatable_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'rules.csv'
            write_csv(p, ['ruleId', 'category', 'requirement', 'severity', 'automatable', 'evidence'],
                      [dict(BASE_RULE, automatable='sometimes')])
            self.assertTrue(any('automatable' in e for e in v.rules(p)))

    def test_short_row_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'rules.csv'
            p.write_text('ruleId,category,requirement,severity,automatable,evidence\nX,资源\n',
                         encoding='utf-8')
            try:
                v.rules(p)
            except Exception as exc:
                self.fail(f'缺列导致崩溃：{type(exc).__name__}: {exc}')


class CompatTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'compat.csv'
            write_csv(p, ['changeType', 'location', 'example', 'defaultClassification',
                          'conditions', 'requiredAction'], [BASE_COMPAT])
            self.assertEqual(v.compat(p), [])

    def test_bad_classification_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'compat.csv'
            write_csv(p, ['changeType', 'location', 'example', 'defaultClassification',
                          'conditions', 'requiredAction'],
                      [dict(BASE_COMPAT, defaultClassification='MAYBE')])
            self.assertTrue(any('分类无效' in e for e in v.compat(p)))


class StatusTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'status.csv'
            write_csv(p, ['operation', 'method', 'successStatus', 'conditionalStatus',
                          'commonClientErrors', 'notes'], [BASE_STATUS])
            self.assertEqual(v.status(p), [])

    def test_unknown_method_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'status.csv'
            write_csv(p, ['operation', 'method', 'successStatus', 'conditionalStatus',
                          'commonClientErrors', 'notes'], [dict(BASE_STATUS, method='FETCH')])
            self.assertTrue(any('未知方法' in e for e in v.status(p)))

    def test_bad_status_code_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'status.csv'
            write_csv(p, ['operation', 'method', 'successStatus', 'conditionalStatus',
                          'commonClientErrors', 'notes'], [dict(BASE_STATUS, successStatus='999')])
            self.assertTrue(any('状态码无效' in e for e in v.status(p)))


class ReviewTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'review.csv'
            write_csv(p, ['checkId', 'category', 'requirement', 'severity', 'automatable', 'evidence'],
                      [BASE_REVIEW])
            self.assertEqual(v.review(p), [])

    def test_duplicate_check_id_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'review.csv'
            write_csv(p, ['checkId', 'category', 'requirement', 'severity', 'automatable', 'evidence'],
                      [BASE_REVIEW, dict(BASE_REVIEW)])
            self.assertTrue(any('checkId' in e for e in v.review(p)))


class StylesTest(unittest.TestCase):
    ALL_STYLES = ['REST_STYLE_HTTP', 'GRPC', 'GRAPHQL', 'SSE', 'WEBSOCKET',
                  'HTTP_STREAMING', 'EVENT_PUBSUB', 'WEBHOOK', 'JSON_RPC']

    def _style_row(self, style):
        return {'style': style, 'primaryUse': 'x', 'direction': 'y',
                'contract': 'z', 'strengths': 'a', 'mainRisks': 'b', 'defaultFor': 'c'}

    def test_all_required_styles_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'styles.csv'
            write_csv(p, ['style', 'primaryUse', 'direction', 'contract',
                          'strengths', 'mainRisks', 'defaultFor'],
                      [self._style_row(s) for s in self.ALL_STYLES])
            self.assertEqual(v.styles(p), [])

    def test_missing_required_style_reported(self):
        # 缺 GRPC 等必选风格时提示，但不崩溃
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'styles.csv'
            write_csv(p, ['style', 'primaryUse', 'direction', 'contract',
                          'strengths', 'mainRisks', 'defaultFor'],
                      [self._style_row('REST_STYLE_HTTP')])
            errors = v.styles(p)
            self.assertTrue(any('缺少' in e for e in errors))


class TemplateTest(unittest.TestCase):
    def test_openapi_template_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'openapi.yaml'
            p.write_text('openapi: 3.2.0\npaths: {}\ncomponents: {}\n'
                         'operationId: x\napplication/problem+json: x\n'
                         'Idempotency-Key: x\nIf-Match: x\n', encoding='utf-8')
            # 缺实际 OpenAPI 结构会报部分缺失，但不崩溃
            v.openapi(p)

    def test_change_proposal_missing_section_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'proposal.md'
            p.write_text('## 背景\n', encoding='utf-8')
            errors = v.change_proposal(p)
            self.assertTrue(any('缺少章节' in e for e in errors))

    def test_change_proposal_all_sections_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'proposal.md'
            p.write_text(''.join(f'## {s}\n' for s in v.CHANGE_PROPOSAL_SECTIONS),
                         encoding='utf-8')
            self.assertEqual(v.change_proposal(p), [])


if __name__ == '__main__':
    unittest.main()
