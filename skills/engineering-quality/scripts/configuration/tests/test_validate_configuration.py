#!/usr/bin/env python3
"""validate_configuration.py 的单元测试。

运行：python -m unittest discover -s scripts/tests -p 'test_*.py'
"""
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import validate_configuration as v  # noqa: E402


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


BASE_SCHEMA = {
    'key': 'http.client.payment.timeout_ms', 'type': 'INTEGER', 'unit': 'ms',
    'required': 'true', 'default': '800', 'dynamic': 'true', 'secret': 'false',
    'owner': 'payments', 'description': 'payment timeout',
}
BASE_PRECEDENCE = {
    'priority': '10', 'source': 'CODE_DEFAULT', 'allowedFor': 'safe_defaults',
    'notes': 'universally safe only',
}
BASE_DYNAMIC = {
    'keyPattern': 'worker.*', 'reloadMode': 'ATOMIC_SNAPSHOT',
    'validation': 'schema+semantic', 'fallback': 'LAST_KNOWN_GOOD',
    'maxStale': '30m', 'owner': 'platform',
}
BASE_REVIEW = {
    'checkId': 'CFG-001', 'requirement': '新增配置有 Schema、类型、单位和 Owner',
    'severity': 'BLOCKER',
}


class SchemaTableTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'schema.csv'
            write_csv(p, v.SCHEMA_HEADERS, [BASE_SCHEMA])
            self.assertEqual(v.check_table(p, v.SCHEMA_HEADERS, 'key', '配置 Schema 目录',
                                           value_checks={'type': v.CONFIG_TYPES}), [])

    def test_bad_type_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'schema.csv'
            write_csv(p, v.SCHEMA_HEADERS, [dict(BASE_SCHEMA, type='OBJECT')])
            errors = v.check_table(p, v.SCHEMA_HEADERS, 'key', '配置 Schema 目录',
                                   value_checks={'type': v.CONFIG_TYPES})
            self.assertTrue(any('type 无效' in e for e in errors))

    def test_duplicate_key_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'schema.csv'
            write_csv(p, v.SCHEMA_HEADERS, [BASE_SCHEMA, dict(BASE_SCHEMA)])
            errors = v.check_table(p, v.SCHEMA_HEADERS, 'key', '配置 Schema 目录')
            self.assertTrue(any('重复' in e for e in errors))

    def test_short_row_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'schema.csv'
            p.write_text('key,type,unit,required,default,dynamic,secret,owner,description\nX,INTEGER\n',
                         encoding='utf-8')
            try:
                v.check_table(p, v.SCHEMA_HEADERS, 'key', '配置 Schema 目录')
            except Exception as exc:
                self.fail(f'缺列导致崩溃：{type(exc).__name__}: {exc}')


class PrecedenceTableTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'precedence.csv'
            write_csv(p, v.PRECEDENCE_HEADERS, [BASE_PRECEDENCE])
            self.assertEqual(v.check_table(p, v.PRECEDENCE_HEADERS, 'source', '来源优先级'), [])

    def test_duplicate_source_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'precedence.csv'
            write_csv(p, v.PRECEDENCE_HEADERS, [BASE_PRECEDENCE, dict(BASE_PRECEDENCE)])
            errors = v.check_table(p, v.PRECEDENCE_HEADERS, 'source', '来源优先级')
            self.assertTrue(any('重复' in e for e in errors))


class DynamicTableTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'dynamic.csv'
            write_csv(p, v.DYNAMIC_HEADERS, [BASE_DYNAMIC])
            self.assertEqual(v.check_table(p, v.DYNAMIC_HEADERS, 'keyPattern', '动态配置策略',
                                           value_checks={'reloadMode': v.RELOAD_MODES,
                                                         'fallback': v.FALLBACKS}), [])

    def test_bad_reload_mode_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'dynamic.csv'
            write_csv(p, v.DYNAMIC_HEADERS, [dict(BASE_DYNAMIC, reloadMode='MANUAL')])
            errors = v.check_table(p, v.DYNAMIC_HEADERS, 'keyPattern', '动态配置策略',
                                   value_checks={'reloadMode': v.RELOAD_MODES})
            self.assertTrue(any('reloadMode 无效' in e for e in errors))

    def test_bad_fallback_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'dynamic.csv'
            write_csv(p, v.DYNAMIC_HEADERS, [dict(BASE_DYNAMIC, fallback='IGNORE')])
            errors = v.check_table(p, v.DYNAMIC_HEADERS, 'keyPattern', '动态配置策略',
                                   value_checks={'fallback': v.FALLBACKS})
            self.assertTrue(any('fallback 无效' in e for e in errors))


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
            p = Path(tmp) / 'change.md'
            p.write_text('# Change\n\n'
                '- Key: x\n- Owner: y\n- Current: a\n- Proposed: b\n- Scope: s\n- Risk: r\n\n'
                '## Validation\n## Canary\n## Metrics\n## Rollback\n## Cleanup\n', encoding='utf-8')
            self.assertEqual(v.check_change_template(p), [])

    def test_template_missing_section_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'change.md'
            p.write_text('# Change\n- Key: x\n', encoding='utf-8')
            self.assertTrue(any('缺少' in e for e in v.check_change_template(p)))

    def test_template_missing_file_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'nonexistent.md'
            self.assertTrue(any('不存在' in e for e in v.check_change_template(p)))


class BadHeaderTest(unittest.TestCase):
    def test_bad_header_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'bad.csv'
            p.write_text('bad1,bad2\nfoo,bar\n', encoding='utf-8')
            try:
                v.check_table(p, v.SCHEMA_HEADERS, 'key', '配置 Schema 目录')
            except Exception as exc:
                self.fail(f'表头错误导致崩溃：{type(exc).__name__}: {exc}')


class MainEndToEndTest(unittest.TestCase):
    def _make_assets_dir(self, tmp: Path) -> Path:
        assets = Path(tmp) / 'assets'
        assets.mkdir()
        write_csv(assets / 'config-schema-catalog.csv', v.SCHEMA_HEADERS, [BASE_SCHEMA])
        write_csv(assets / 'config-source-precedence.csv', v.PRECEDENCE_HEADERS, [BASE_PRECEDENCE])
        write_csv(assets / 'dynamic-config-policy.csv', v.DYNAMIC_HEADERS, [BASE_DYNAMIC])
        write_csv(assets / 'config-review-checklist.csv', v.REVIEW_HEADERS, [BASE_REVIEW])
        (assets / 'config-change.template.md').write_text(
            '- Key: x\n- Owner: y\n- Current: a\n- Proposed: b\n- Scope: s\n- Risk: r\n\n'
            '## Validation\n## Canary\n## Metrics\n## Rollback\n## Cleanup\n', encoding='utf-8')
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
