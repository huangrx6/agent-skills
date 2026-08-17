#!/usr/bin/env python3
"""validate_logging_catalog.py 的单元测试。

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

import validate_logging_catalog as v  # noqa: E402

EVENT_HEADERS = v.EVENT_HEADERS
FIELD_HEADERS = v.FIELD_HEADERS
STORAGE_HEADERS = v.STORAGE_HEADERS
POLICY_HEADERS = v.POLICY_HEADERS

BASE_EVENT = {
    'eventName': 'request.failed',
    'description': '请求最终失败',
    'defaultLevel': 'ERROR',
    'responsibilityBoundary': 'request-boundary',
    'requiredFields': 'operation|error.code|error.type|trace_id',
    'samplingPolicy': 'ALL',
    'retentionDays': '30',
    'owner': '平台团队',
}
BASE_FIELD = {
    'fieldName': 'operation',
    'required': 'true',
    'type': 'STRING',
    'format': 'OPERATION_NAME',
    'description': '操作标识',
    'classification': 'INTERNAL',
    'indexed': 'true',
    'maxLength': '128',
    'example': 'user.create',
}
BASE_STORAGE = {
    'logStream': 'application-file',
    'environment': 'production',
    'outputTarget': 'FILE',
    'format': 'JSON_LINES',
    'rotationOwner': 'OS',
    'rotationTrigger': 'SIZE_OR_TIME',
    'rotationInterval': 'DAILY',
    'maxFileSizeMB': '100',
    'maxFiles': '31',
    'compress': 'true',
    'retentionDays': '30',
    'maxLocalDiskMB': '4096',
    'archiveTarget': 'central-log-platform',
    'cleanupPolicy': 'OLDEST_ELIGIBLE_FIRST',
    'owner': '平台团队',
}
BASE_POLICY = {
    'fieldPattern': 'password',
    'classification': 'SECRET',
    'action': 'DROP',
    'exampleOutput': '',
    'notes': '任何密码字段均不得记录',
}
COMMON_FIELDS = ['timestamp', 'level', 'event.name', 'message',
                 'service.name', 'service.version', 'deployment.environment',
                 'operation', 'error.code', 'error.type', 'trace_id',
                 'span_id', 'correlation_id', 'duration_ms']


def read_csv(path: Path) -> list[dict]:
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def run_validation(events: list[dict], fields: list[dict] | None = None,
                   storage: list[dict] | None = None,
                   policies: list[dict] | None = None,
                   warnings_out: list[str] | None = None) -> list[str]:
    errors: list[str] = []
    warnings = warnings_out if warnings_out is not None else []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        event_path = tmp / 'events.csv'
        write_csv(event_path, EVENT_HEADERS, events)
        v.validate_events(event_path, errors, known_fields=set(COMMON_FIELDS),
                          warnings=warnings)
        if fields is not None:
            field_path = tmp / 'fields.csv'
            write_csv(field_path, FIELD_HEADERS, fields)
            names = v.validate_fields(field_path, errors, '事件字段目录')
            known = set(COMMON_FIELDS) | names
            v.validate_events(event_path, errors, known_fields=known, warnings=warnings)
        if storage is not None:
            storage_path = tmp / 'storage.csv'
            write_csv(storage_path, STORAGE_HEADERS, storage)
            v.validate_storage(storage_path, errors, events)
        if policies is not None:
            policy_path = tmp / 'policies.csv'
            write_csv(policy_path, POLICY_HEADERS, policies)
            v.validate_sensitive(policy_path, errors)
            sensitive_rows = read_csv(policy_path)
            v.validate_sensitive_coverage(fields or [], sensitive_rows, errors)
    return errors


class ValidateEventsTest(unittest.TestCase):
    def test_valid_event_passes(self):
        errors = run_validation([BASE_EVENT])
        self.assertEqual(errors, [])

    def test_duplicate_event_name_rejected(self):
        errors = run_validation([BASE_EVENT, dict(BASE_EVENT, description='重复')])
        self.assertTrue(any('eventName 重复' in e for e in errors))

    def test_invalid_level_rejected(self):
        errors = run_validation([dict(BASE_EVENT, defaultLevel='FATAL')])
        self.assertTrue(any('defaultLevel 不正确' in e for e in errors))

    def test_unregistered_required_field_rejected(self):
        event = dict(BASE_EVENT, requiredFields='operation|ghost.field')
        errors = run_validation([event])
        self.assertTrue(any('引用未登记字段：ghost.field' in e for e in errors))

    def test_missing_attribute_rejected(self):
        errors = run_validation([dict(BASE_EVENT, owner='')])
        self.assertTrue(any('owner 不能为空' in e for e in errors))

    def test_bad_event_name_rejected(self):
        errors = run_validation([dict(BASE_EVENT, eventName='Request.Failed')])
        self.assertTrue(any('eventName 格式不正确' in e for e in errors))

    def test_error_event_without_error_code_warns_not_blocks(self):
        event = dict(BASE_EVENT, requiredFields='operation|trace_id')
        warnings: list[str] = []
        errors = run_validation([event], warnings_out=warnings)
        self.assertTrue(any('error.code' in w for w in warnings))
        self.assertEqual(errors, [])

    def test_system_level_error_without_code_does_not_block(self):
        # 系统级致命事件无业务错误码：仅提示不阻断（不再硬编码 process. 豁免）
        event = dict(BASE_EVENT, eventName='system.fatal',
                     requiredFields='service.name|error.type')
        errors = run_validation([event])
        self.assertEqual(errors, [])


class ValidateFieldsTest(unittest.TestCase):
    def test_valid_field_passes(self):
        errors = run_validation([BASE_EVENT], fields=[BASE_FIELD])
        self.assertEqual(errors, [])

    def test_duplicate_field_rejected(self):
        errors = run_validation([BASE_EVENT], fields=[BASE_FIELD, dict(BASE_FIELD)])
        self.assertTrue(any('fieldName 重复' in e for e in errors))

    def test_bad_type_rejected(self):
        errors = run_validation([BASE_EVENT], fields=[dict(BASE_FIELD, type='JSON')])
        self.assertTrue(any('type 不正确' in e for e in errors))


class ValidateStorageTest(unittest.TestCase):
    def test_valid_storage_passes(self):
        errors = run_validation([BASE_EVENT], storage=[BASE_STORAGE])
        self.assertEqual(errors, [])

    def test_stdout_with_application_rotation_rejected(self):
        storage = dict(BASE_STORAGE, outputTarget='STDOUT', rotationOwner='APPLICATION')
        errors = run_validation([BASE_EVENT], storage=[storage])
        self.assertTrue(any('stdout/stderr 不应由应用负责文件轮转' in e for e in errors))

    def test_disk_cap_smaller_than_rotation_rejected(self):
        storage = dict(BASE_STORAGE, maxFileSizeMB='100', maxFiles='90',
                       maxLocalDiskMB='4096')
        errors = run_validation([BASE_EVENT], storage=[storage])
        self.assertTrue(any('小于按滚动配置的最大占用' in e for e in errors))

    def test_file_rotation_without_size_trigger_rejected(self):
        storage = dict(BASE_STORAGE, rotationTrigger='SIZE', maxFileSizeMB='')
        errors = run_validation([BASE_EVENT], storage=[storage])
        self.assertTrue(any('SIZE 触发必须配置 maxFileSizeMB' in e for e in errors))

    def test_retention_alone_satisfies_capacity_constraint(self):
        # retentionDays 本身即合法的最终容量约束（文档：文件数/保留天数/总占用任一即可）
        storage = dict(BASE_STORAGE, maxFiles='', maxLocalDiskMB='')
        errors = run_validation([BASE_EVENT], storage=[storage])
        self.assertEqual(errors, [])

    def test_audit_stream_retention_short_than_audit_event_rejected(self):
        audit_event = dict(BASE_EVENT, eventName='security.permission_changed',
                           defaultLevel='INFO', responsibilityBoundary='audit-boundary',
                           requiredFields='actor.id|resource.id|action|result',
                           retentionDays='365')
        storage = dict(BASE_STORAGE, logStream='audit', cleanupPolicy='LEGAL_HOLD_AWARE',
                       retentionDays='180')
        errors = run_validation([audit_event], storage=[storage])
        self.assertTrue(any('审计流' in e and '小于审计事件' in e for e in errors))


    def test_maxfiles_below_retention_coverage_rejected(self):
        storage = dict(BASE_STORAGE, maxFiles='10', retentionDays='30')
        errors = run_validation([BASE_EVENT], storage=[storage])
        self.assertTrue(any('无法覆盖 retentionDays' in e for e in errors))

    def test_maxfiles_coverage_by_interval(self):
        # 覆盖校验对所有按时间滚动的周期都生效，且按每天文件数换算
        cases = [
            # (interval, retentionDays, maxFiles, 是否应报错)
            ('HOURLY', 1, 24, False),    # ceil(1*24)=24
            ('HOURLY', 1, 23, True),
            ('DAILY', 30, 30, False),    # ceil(30*1)=30
            ('DAILY', 30, 29, True),
            ('WEEKLY', 30, 5, False),    # ceil(30/7)=5
            ('WEEKLY', 30, 4, True),
            ('MONTHLY', 30, 1, False),   # ceil(30/30)=1
        ]
        for interval, retention, maxfiles, should_fail in cases:
            storage = dict(BASE_STORAGE, rotationTrigger='TIME',
                           rotationInterval=interval, maxFileSizeMB='10',
                           maxFiles=str(maxfiles), retentionDays=str(retention),
                           maxLocalDiskMB='102400')
            errors = run_validation([BASE_EVENT], storage=[storage])
            hit = any('无法覆盖 retentionDays' in e for e in errors)
            self.assertEqual(
                hit, should_fail,
                f'{interval} retention={retention} maxFiles={maxfiles}: '
                f'期望{"报错" if should_fail else "通过"}，实际{"报错" if hit else "通过"}')


class ValidateSensitiveTest(unittest.TestCase):
    def test_valid_policy_passes(self):
        errors = run_validation([BASE_EVENT], policies=[BASE_POLICY])
        self.assertEqual(errors, [])

    def test_duplicate_pattern_rejected(self):
        errors = run_validation([BASE_EVENT], policies=[BASE_POLICY, dict(BASE_POLICY)])
        self.assertTrue(any('fieldPattern 重复' in e for e in errors))

    def test_bad_action_rejected(self):
        errors = run_validation([BASE_EVENT], policies=[dict(BASE_POLICY, action='REDACT')])
        self.assertTrue(any('action 不正确' in e for e in errors))

    def test_allow_action_requires_notes(self):
        policy = dict(BASE_POLICY, action='ALLOW', notes='')
        errors = run_validation([BASE_EVENT], policies=[policy])
        self.assertTrue(any('ALLOW 动作必须在 notes 中说明' in e for e in errors))



class ValidateSensitiveCoverageTest(unittest.TestCase):
    def test_sensitive_field_without_policy_rejected(self):
        field = dict(BASE_FIELD, fieldName='actor.id', classification='PERSONAL')
        policy = dict(BASE_POLICY, fieldPattern='email')
        errors = run_validation([BASE_EVENT], fields=[field], policies=[policy])
        self.assertTrue(any('未被敏感字段策略覆盖' in e and 'actor.id' in e for e in errors))

    def test_sensitive_field_with_exact_policy_passes(self):
        field = dict(BASE_FIELD, fieldName='actor.id', classification='PERSONAL')
        policy = dict(BASE_POLICY, fieldPattern='actor.id', action='ALLOW',
                      notes='审计追溯需要主体标识；仅限日志查询权限内访问')
        errors = run_validation([BASE_EVENT], fields=[field], policies=[policy])
        self.assertEqual(errors, [])

    def test_sensitive_field_with_wildcard_policy_passes(self):
        field = dict(BASE_FIELD, fieldName='access_token', classification='SECRET')
        policy = dict(BASE_POLICY, fieldPattern='*token*')
        errors = run_validation([BASE_EVENT], fields=[field], policies=[policy])
        self.assertEqual(errors, [])

    def test_internal_field_does_not_require_policy(self):
        field = dict(BASE_FIELD, fieldName='operation', classification='INTERNAL')
        errors = run_validation([BASE_EVENT], fields=[field], policies=[])
        self.assertEqual(errors, [])



class ValidateFormatSchemaTest(unittest.TestCase):
    def test_missing_required_common_field_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            field_path = tmp / 'format.csv'
            write_csv(field_path, FIELD_HEADERS,
                      [dict(BASE_FIELD, fieldName='operation', classification='INTERNAL')])
            errors: list[str] = []
            v.validate_fields(field_path, errors, '日志格式目录', require_common=True)
        self.assertTrue(any('缺少必填公共字段' in e for e in errors))

    def test_all_required_common_fields_present_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            field_path = tmp / 'format.csv'
            required = ['timestamp', 'level', 'event.name', 'message',
                        'service.name', 'deployment.environment']
            rows = [dict(BASE_FIELD, fieldName=name) for name in required]
            write_csv(field_path, FIELD_HEADERS, rows)
            errors: list[str] = []
            v.validate_fields(field_path, errors, '日志格式目录', require_common=True)
        self.assertEqual(errors, [])


class ValidateStorageSyslogTest(unittest.TestCase):
    def test_syslog_without_disk_cap_not_rejected(self):
        storage = dict(BASE_STORAGE, outputTarget='SYSLOG', maxFileSizeMB='',
                       maxFiles='', maxLocalDiskMB='')
        errors = run_validation([BASE_EVENT], storage=[storage])
        self.assertEqual(errors, [])


class ValidateShortRowTest(unittest.TestCase):
    """CSV 行缺列（DictReader 给 None）时不应崩溃，应报错退出。"""

    def test_events_short_row_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            event_path = tmp / 'events.csv'
            # 表头 8 列，行只有 3 列
            event_path.write_text(
                'eventName,description,defaultLevel,responsibilityBoundary,'
                'requiredFields,samplingPolicy,retentionDays,owner\n'
                'service.started,desc,INFO\n', encoding='utf-8')
            errors: list[str] = []
            warnings: list[str] = []
            try:
                v.validate_events(event_path, errors, set(), warnings)
            except Exception as exc:
                self.fail(f'缺列导致崩溃：{type(exc).__name__}: {exc}')


class ValidateMainEndToEndTest(unittest.TestCase):
    """走真实 main() 入口：参数解析、退出码、文件缺失。"""

    REQUIRED_COMMON = ['timestamp', 'level', 'event.name', 'message',
                       'service.name', 'deployment.environment']

    def _run_main(self, tmp, events, format_fields, event_fields,
                  storage, policies):
        ev = tmp / 'e.csv'
        write_csv(ev, EVENT_HEADERS, events)
        ff = tmp / 'f.csv'
        write_csv(ff, FIELD_HEADERS, format_fields)
        ef = tmp / 'ef.csv'
        write_csv(ef, FIELD_HEADERS, event_fields)
        sp = tmp / 's.csv'
        write_csv(sp, STORAGE_HEADERS, storage)
        pp = tmp / 'p.csv'
        write_csv(pp, POLICY_HEADERS, policies)
        old_argv = sys.argv
        sys.argv = ['prog', str(ev), '--format-schema', str(ff),
                    '--event-fields', str(ef), '--storage-policy', str(sp),
                    '--sensitive-policy', str(pp)]
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                return v.main()
        finally:
            sys.argv = old_argv

    def _valid_assets(self):
        events = [BASE_EVENT]
        format_fields = [dict(BASE_FIELD, fieldName=n) for n in self.REQUIRED_COMMON]
        event_fields = [dict(BASE_FIELD, fieldName=n)
                        for n in ['operation', 'error.code', 'error.type', 'trace_id']]
        storage = [BASE_STORAGE]
        policies = [BASE_POLICY]
        return events, format_fields, event_fields, storage, policies

    def test_valid_assets_exit_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = self._run_main(Path(tmp), *self._valid_assets())
        self.assertEqual(code, 0)

    def test_unregistered_field_exit_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            events, ff, ef, sp, pp = self._valid_assets()
            events = [dict(events[0], requiredFields='operation|ghost.field')]
            code = self._run_main(Path(tmp), events, ff, ef, sp, pp)
        self.assertEqual(code, 1)

    def test_missing_event_file_exit_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            old_argv = sys.argv
            sys.argv = ['prog', str(tmp / 'nonexistent.csv')]
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                    code = v.main()
            finally:
                sys.argv = old_argv
        self.assertEqual(code, 2)


if __name__ == '__main__':
    unittest.main()
