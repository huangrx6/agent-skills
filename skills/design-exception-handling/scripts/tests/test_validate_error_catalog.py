#!/usr/bin/env python3
"""validate_error_catalog.py 的单元测试。

运行：python -m unittest discover -s scripts/tests -p 'test_*.py'
"""
from __future__ import annotations

import contextlib
import csv
import io
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import validate_error_catalog as v  # noqa: E402

REGISTRY_HEADERS = v.REGISTRY
MAPPING_HEADERS = v.MAPPING

BASE_REG = {
    'code': 'INVALID_REQUEST', 'title': '请求格式不正确', 'httpStatus': '400',
    'category': 'INPUT', 'retryable': 'false', 'publicDetail': '请求格式不正确',
    'owner': '平台团队', 'introducedVersion': '1.0', 'deprecatedVersion': '',
}
BASE_MAP = {
    'internalException': 'RequestParseException', 'publicCode': 'INVALID_REQUEST',
    'httpStatus': '400', 'retryable': 'false', 'notes': '请求语法错误',
}


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def run_validation(registry: list[dict], mapping: list[dict] | None = None,
                   warnings_out: list[str] | None = None) -> list[str]:
    errors: list[str] = []
    warnings = warnings_out if warnings_out is not None else []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        reg_path = tmp / 'reg.csv'
        write_csv(reg_path, REGISTRY_HEADERS, registry)
        codes = v.validate_registry(reg_path, errors, warnings)
        if mapping is not None:
            map_path = tmp / 'map.csv'
            write_csv(map_path, MAPPING_HEADERS, mapping)
            v.validate_mapping(map_path, codes, errors, warnings)
    return errors


class ValidateRegistryTest(unittest.TestCase):
    def test_valid_registry_passes(self):
        self.assertEqual(run_validation([BASE_REG]), [])

    def test_bad_code_format_rejected(self):
        errors = run_validation([dict(BASE_REG, code='invalid-code')])
        self.assertTrue(any('错误码格式不正确' in e for e in errors))

    def test_duplicate_code_rejected(self):
        errors = run_validation([BASE_REG, dict(BASE_REG, title='重复')])
        self.assertTrue(any('错误码重复' in e for e in errors))

    def test_bad_http_status_rejected(self):
        errors = run_validation([dict(BASE_REG, httpStatus='300')])
        self.assertTrue(any('httpStatus 不正确' in e for e in errors))

    def test_bad_category_rejected(self):
        errors = run_validation([dict(BASE_REG, category='UNKNOWN')])
        self.assertTrue(any('category 不正确' in e for e in errors))

    def test_bad_retryable_rejected(self):
        errors = run_validation([dict(BASE_REG, retryable='maybe')])
        self.assertTrue(any('retryable 不正确' in e for e in errors))

    def test_empty_required_fields_rejected(self):
        for field in ('title', 'publicDetail', 'owner', 'introducedVersion'):
            errors = run_validation([dict(BASE_REG, **{field: ''})])
            self.assertTrue(any(f'{field} 不能为空' in e for e in errors),
                            f'{field} 空值未报错')

    def test_deprecated_without_introduced_rejected(self):
        row = dict(BASE_REG, introducedVersion='', deprecatedVersion='2.0')
        errors = run_validation([row])
        self.assertTrue(any('deprecatedVersion 有值但 introducedVersion 为空' in e for e in errors))

    def test_category_status_mismatch_rejected(self):
        # SYSTEM 类应为 5xx，配 400 应报错
        errors = run_validation([dict(BASE_REG, category='SYSTEM', httpStatus='500')])
        self.assertEqual(errors, [])
        errors = run_validation([dict(BASE_REG, category='SYSTEM', httpStatus='400')])
        self.assertTrue(any('语义不匹配' in e for e in errors))

    def test_rate_limit_category(self):
        # RATE_LIMIT 新类别应为 429
        row = dict(BASE_REG, code='RATE_LIMITED', httpStatus='429', category='RATE_LIMIT')
        self.assertEqual(run_validation([row]), [])
        row = dict(BASE_REG, code='RATE_LIMITED', httpStatus='500', category='RATE_LIMIT')
        self.assertTrue(any('语义不匹配' in e for e in run_validation([row])))

    def test_dependency_rejects_429(self):
        # DEPENDENCY 类不得使用 429（429 归 RATE_LIMIT，避免分类边界模糊）
        row = dict(BASE_REG, code='UPSTREAM_THROTTLED', httpStatus='429',
                   category='DEPENDENCY')
        self.assertTrue(any('语义不匹配' in e for e in run_validation([row])))

    def test_deprecated_warns(self):
        row = dict(BASE_REG, code='OLD_CODE', deprecatedVersion='2.0')
        warnings: list[str] = []
        run_validation([row], warnings_out=warnings)
        self.assertTrue(any('已标记废弃' in w for w in warnings))
        # 废弃码本身合法，不应阻断
        self.assertEqual(run_validation([row]), [])


class ValidateRetryablePoisoningTest(unittest.TestCase):
    """注册表 retryable 无效时不得污染 codes 供映射表级联比较（N6）。"""

    def test_invalid_retryable_does_not_cascade_to_mapping(self):
        row = dict(BASE_REG, code='BAD_RETRY', retryable='maybe')
        errors, warnings = [], []
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            reg_path = tmp / 'reg.csv'
            write_csv(reg_path, REGISTRY_HEADERS, [row])
            codes = v.validate_registry(reg_path, errors, warnings)
            self.assertIsNone(codes['BAD_RETRY']['retryable'],
                              '无效 retryable 不应以脏值进入 codes')
            # 映射表引用该码，不再产生“与注册表不一致”的级联错误
            map_path = tmp / 'map.csv'
            write_csv(map_path, MAPPING_HEADERS, [dict(BASE_MAP, publicCode='BAD_RETRY')])
            errors2, warnings2 = [], []
            v.validate_mapping(map_path, codes, errors2, warnings2)
            self.assertFalse(any('与注册表' in e for e in errors2),
                             '无效 retryable 不应级联为“不一致”')


class ValidateMappingTest(unittest.TestCase):
    def test_valid_mapping_passes(self):
        self.assertEqual(run_validation([BASE_REG], [BASE_MAP]), [])

    def test_unregistered_code_rejected(self):
        errors = run_validation([BASE_REG], [dict(BASE_MAP, publicCode='GHOST')])
        self.assertTrue(any('错误码未登记' in e for e in errors))

    def test_status_mismatch_with_registry_rejected(self):
        errors = run_validation([BASE_REG], [dict(BASE_MAP, httpStatus='422')])
        self.assertTrue(any('与注册表' in e and '不一致' in e for e in errors))

    def test_retryable_mismatch_with_registry_rejected(self):
        errors = run_validation([BASE_REG], [dict(BASE_MAP, retryable='true')])
        self.assertTrue(any('retryable' in e and '与注册表' in e for e in errors))

    def test_duplicate_internal_exception_rejected(self):
        errors = run_validation([BASE_REG], [BASE_MAP, dict(BASE_MAP)])
        self.assertTrue(any('重复登记' in e for e in errors))

    def test_conflicting_internal_exception_mapping_rejected(self):
        reg = [BASE_REG, dict(BASE_REG, code='OTHER_CODE', httpStatus='422',
                              title='其他')]
        mapping = [BASE_MAP, dict(BASE_MAP, publicCode='OTHER_CODE', httpStatus='422')]
        errors = run_validation(reg, mapping)
        self.assertTrue(any('映射矛盾' in e for e in errors))

    def test_empty_internal_exception_rejected(self):
        errors = run_validation([BASE_REG], [dict(BASE_MAP, internalException='')])
        self.assertTrue(any('internalException 不能为空' in e for e in errors))

    def test_empty_notes_warns(self):
        warnings: list[str] = []
        run_validation([BASE_REG], [dict(BASE_MAP, notes='')], warnings_out=warnings)
        self.assertTrue(any('notes 为空' in w for w in warnings))


class ValidateMappingHeaderTest(unittest.TestCase):
    def test_bad_mapping_header_does_not_crash(self):
        """映射表表头错误应报错退出，不 KeyError 崩溃。"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            map_path = tmp / 'map.csv'
            map_path.write_text('bad1,bad2\nfoo,bar\n', encoding='utf-8')
            errors: list[str] = []
            warnings: list[str] = []
            v.validate_mapping(map_path, {}, errors, warnings)
        self.assertTrue(any('表头不正确' in e for e in errors))


class ValidateRegistryHeaderTest(unittest.TestCase):
    def test_bad_header_does_not_crash(self):
        """表头错误应报错退出，不 KeyError 崩溃。"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            reg_path = tmp / 'reg.csv'
            reg_path.write_text('bad1,bad2\nfoo,bar\n', encoding='utf-8')
            errors: list[str] = []
            warnings: list[str] = []
            v.validate_registry(reg_path, errors, warnings)
        self.assertTrue(any('表头不正确' in e for e in errors))


class ValidateShortRowTest(unittest.TestCase):
    """CSV 行缺列（DictReader 给 None）时不应崩溃，应报错退出。"""

    def test_registry_short_row_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            reg_path = tmp / 'reg.csv'
            # 表头 9 列，行只有 4 列
            reg_path.write_text(
                'code,title,httpStatus,category,retryable,publicDetail,'
                'owner,introducedVersion,deprecatedVersion\n'
                'X,t,400,INPUT\n', encoding='utf-8')
            errors: list[str] = []
            warnings: list[str] = []
            try:
                v.validate_registry(reg_path, errors, warnings)
            except Exception as exc:
                self.fail(f'缺列导致崩溃：{type(exc).__name__}: {exc}')
            # 缺列的字段应为空值，触发“不能为空”而非崩溃
            self.assertTrue(any('不能为空' in e for e in errors))


class ValidateMainEndToEndTest(unittest.TestCase):
    """走真实 main() 入口：参数解析、退出码、文件缺失。"""

    def _run_main(self, tmp: Path, registry: list[dict], mapping: list[dict] | None):
        reg_path = tmp / 'reg.csv'
        write_csv(reg_path, REGISTRY_HEADERS, registry)
        argv = ['prog', str(reg_path)]
        if mapping is not None:
            map_path = tmp / 'map.csv'
            write_csv(map_path, MAPPING_HEADERS, mapping)
            argv += ['--mapping', str(map_path)]
        old_argv = sys.argv
        sys.argv = argv
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                return v.main()
        finally:
            sys.argv = old_argv

    def test_valid_assets_exit_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = self._run_main(Path(tmp), [BASE_REG], [BASE_MAP])
        self.assertEqual(code, 0)

    def test_invalid_status_exit_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = self._run_main(Path(tmp), [dict(BASE_REG, httpStatus='300')], None)
        self.assertEqual(code, 1)

    def test_missing_file_exit_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_argv = sys.argv
            sys.argv = ['prog', str(Path(tmp) / 'nonexistent.csv')]
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                    code = v.main()
            finally:
                sys.argv = old_argv
        self.assertEqual(code, 2)


if __name__ == '__main__':
    unittest.main()
