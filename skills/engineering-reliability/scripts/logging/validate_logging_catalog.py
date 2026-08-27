#!/usr/bin/env python3
"""应用日志规范资产校验。

校验四个 CSV 目录的格式、枚举、跨表引用一致性和基本语义：

- 事件目录：eventName 命名、级别、字段引用、保留期
- 格式目录：公共字段的命名、类型、必填与索引标记
- 事件字段目录：事件专属字段登记（与格式目录同构）
- 存储策略：输出目标、轮转归属、滚动条件、容量约束、跨表审计保留期
- 敏感策略：字段模式、动作、分类

跨表规则（本脚本的核心价值）：
- 事件目录 requiredFields 中出现的每个字段，必须登记在格式目录
  （公共字段）或事件字段目录（事件专属字段）中；
- 事件专属字段与公共字段不得重名（先登记后引用）；
- 审计流（cleanupPolicy=LEGAL_HOLD_AWARE）的保留期必须不小于
  审计类事件（responsibilityBoundary 含 audit）的保留期；
- 文件日志的本地磁盘上限必须容纳按滚动配置计算出的最大占用。

用法：
  python scripts/validate_logging_catalog.py assets/log-event-catalog.csv \\
      --format-schema assets/log-format-schema.csv \\
      --event-fields assets/log-event-fields.csv \\
      --storage-policy assets/log-storage-policy.csv \\
      --sensitive-policy assets/sensitive-field-policy.csv
"""
from __future__ import annotations

import argparse
import csv
import fnmatch
import math
import re
import sys
from pathlib import Path

EVENT_HEADERS = [
    'eventName', 'description', 'defaultLevel', 'responsibilityBoundary',
    'requiredFields', 'samplingPolicy', 'retentionDays', 'owner'
]
POLICY_HEADERS = ['fieldPattern', 'classification', 'action', 'exampleOutput', 'notes']
FIELD_HEADERS = [
    'fieldName', 'required', 'type', 'format', 'description', 'classification',
    'indexed', 'maxLength', 'example'
]
STORAGE_HEADERS = [
    'logStream', 'environment', 'outputTarget', 'format', 'rotationOwner',
    'rotationTrigger', 'rotationInterval', 'maxFileSizeMB', 'maxFiles', 'compress',
    'retentionDays', 'maxLocalDiskMB', 'archiveTarget', 'cleanupPolicy', 'owner'
]

LEVELS = {'DEBUG', 'INFO', 'WARN', 'ERROR'}
ACTIONS = {'DROP', 'MASK', 'HASH', 'TRUNCATE', 'ALLOW'}
BOOLS = {'true', 'false'}
FIELD_TYPES = {'STRING', 'INTEGER', 'DOUBLE', 'BOOLEAN', 'TIMESTAMP', 'OBJECT', 'ARRAY'}
OUTPUT_TARGETS = {'STDOUT', 'STDERR', 'FILE', 'SYSLOG', 'OTLP', 'PLATFORM'}
FORMATS = {'JSON_LINES', 'RFC5424', 'OTLP', 'PLATFORM_NATIVE'}
ROTATION_OWNERS = {'APPLICATION', 'OS', 'RUNTIME', 'PLATFORM'}
ROTATION_TRIGGERS = {'TIME', 'SIZE', 'SIZE_OR_TIME', 'PLATFORM'}
ROTATION_INTERVALS = {'HOURLY', 'DAILY', 'WEEKLY', 'MONTHLY', 'PLATFORM'}
# 按时间滚动时每天至少产生的归档文件数下界（用于校验文件数能否覆盖保留期）
FILES_PER_DAY = {'HOURLY': 24, 'DAILY': 1, 'WEEKLY': 1 / 7, 'MONTHLY': 1 / 30}
REQUIRED_FORMAT_FIELDS = {
    'timestamp', 'level', 'event.name', 'message', 'service.name',
    'deployment.environment',
}

# 标为这些分类的字段，必须在敏感字段策略中有覆盖 pattern
SENSITIVE_CLASSIFICATIONS = {'SECRET', 'PAYMENT', 'PERSONAL', 'PERSONAL_SENSITIVE'}

# 每个事件至少应登记哪些信息，避免目录退化成空壳
EVENT_REQUIRED_ATTRIBUTES = {
    'description', 'responsibilityBoundary', 'samplingPolicy', 'owner'
}


def read(path: Path):
    if not path.is_file():
        raise ValueError(f'文件不存在：{path}')
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        # 行缺列时 DictReader 给 None，统一转成空串避免后续 .strip() 崩溃
        rows = [{k: (v or '') for k, v in row.items()} for row in reader]
        return reader.fieldnames or [], rows


def positive_int(value: str, location: str, field: str, errors: list[str],
                 allow_blank: bool = False) -> int | None:
    value = value.strip()
    if allow_blank and not value:
        return None
    try:
        number = int(value)
        if number <= 0:
            raise ValueError
        return number
    except ValueError:
        errors.append(f'{location} {field} 必须为正整数')
        return None


def validate_events(path: Path, errors: list[str],
                    known_fields: set[str],
                    warnings: list[str] | None = None) -> None:
    if warnings is None:
        warnings = []
    headers, rows = read(path)
    if headers != EVENT_HEADERS:
        errors.append(f'日志事件目录表头不正确：{headers}')
        return
    names = set()
    for n, row in enumerate(rows, 2):
        location = f'日志事件目录第 {n} 行'
        name = row['eventName'].strip()
        if not re.fullmatch(r'[a-z][a-z0-9_.-]*', name):
            errors.append(f'{location} eventName 格式不正确：{name}')
        if name in names:
            errors.append(f'{location} eventName 重复：{name}')
        names.add(name)
        if row['defaultLevel'].strip().upper() not in LEVELS:
            errors.append(f'{location} defaultLevel 不正确：{row["defaultLevel"]}')
        if row['defaultLevel'].strip().upper() == 'ERROR' and \
                'error.code' not in (row['requiredFields'] or ''):
            warnings.append(f'{location} ERROR 事件 {name} 建议在 requiredFields 中登记 error.code，'
                          f'便于检索与告警关联')
        positive_int(row['retentionDays'], location, 'retentionDays', errors)
        for field in EVENT_REQUIRED_ATTRIBUTES:
            if not row[field].strip():
                errors.append(f'{location} {field} 不能为空')
        required = row['requiredFields'].strip()
        for field_name in (f.strip() for f in required.split('|')) if required else ():
            if not field_name:
                continue
            if field_name not in known_fields:
                errors.append(f'{location} requiredFields 引用未登记字段：{field_name}'
                              f'（请加入格式目录或事件字段目录）')


def validate_fields(path: Path, errors: list[str], label: str,
                    require_common: bool = False) -> set[str]:
    """校验公共字段或事件字段目录，返回已登记字段名集合。

    require_common=True 时检查格式目录是否包含全部必填公共字段。
    """
    headers, rows = read(path)
    if headers != FIELD_HEADERS:
        errors.append(f'{label}表头不正确：{headers}')
        return set()
    names: set[str] = set()
    for n, row in enumerate(rows, 2):
        location = f'{label}第 {n} 行'
        name = row['fieldName'].strip()
        if not re.fullmatch(r'[a-z][a-z0-9_.]*', name):
            errors.append(f'{location} fieldName 格式不正确：{name}')
        if name in names:
            errors.append(f'{location} fieldName 重复：{name}')
        names.add(name)
        if row['required'].strip().lower() not in BOOLS:
            errors.append(f'{location} required 必须为 true 或 false')
        if row['indexed'].strip().lower() not in BOOLS:
            errors.append(f'{location} indexed 必须为 true 或 false')
        if row['type'].strip().upper() not in FIELD_TYPES:
            errors.append(f'{location} type 不正确：{row["type"]}')
        if not row['format'].strip() or not row['description'].strip() \
                or not row['classification'].strip():
            errors.append(f'{location} format、description、classification 不能为空')
        positive_int(row['maxLength'], location, 'maxLength', errors, allow_blank=True)
    if require_common:
        missing = REQUIRED_FORMAT_FIELDS - names
        if missing:
            errors.append(f'{label}缺少必填公共字段：{sorted(missing)}')
    return names


def validate_storage(path: Path, errors: list[str], events: list[dict]) -> None:
    headers, rows = read(path)
    if headers != STORAGE_HEADERS:
        errors.append(f'日志存储策略表头不正确：{headers}')
        return
    streams = set()
    audit_streams: list[dict] = []
    for n, row in enumerate(rows, 2):
        location = f'日志存储策略第 {n} 行'
        stream = row['logStream'].strip()
        if not stream:
            errors.append(f'{location} logStream 不能为空')
        if stream in streams:
            errors.append(f'{location} logStream 重复：{stream}')
        streams.add(stream)
        target = row['outputTarget'].strip().upper()
        fmt = row['format'].strip().upper()
        owner = row['rotationOwner'].strip().upper()
        trigger = row['rotationTrigger'].strip().upper()
        interval = row['rotationInterval'].strip().upper()
        if target not in OUTPUT_TARGETS:
            errors.append(f'{location} outputTarget 不正确：{target}')
        if fmt not in FORMATS:
            errors.append(f'{location} format 不正确：{fmt}')
        if owner not in ROTATION_OWNERS:
            errors.append(f'{location} rotationOwner 不正确：{owner}')
        if trigger not in ROTATION_TRIGGERS:
            errors.append(f'{location} rotationTrigger 不正确：{trigger}')
        if interval not in ROTATION_INTERVALS:
            errors.append(f'{location} rotationInterval 不正确：{interval}')
        if row['compress'].strip().lower() not in BOOLS:
            errors.append(f'{location} compress 必须为 true 或 false')
        if target in {'STDOUT', 'STDERR'} and owner == 'APPLICATION':
            errors.append(f'{location} stdout/stderr 不应由应用负责文件轮转')
        if trigger == 'PLATFORM' and owner not in {'PLATFORM', 'RUNTIME'}:
            errors.append(f'{location} PLATFORM 触发应由 PLATFORM 或 RUNTIME 负责')
        if target == 'FILE' and trigger == 'PLATFORM' and owner == 'APPLICATION':
            errors.append(f'{location} FILE 由应用负责时必须配置明确的时间或大小滚动条件')
        if target == 'FILE' and trigger in {'TIME', 'SIZE_OR_TIME'} \
                and interval not in {'HOURLY', 'DAILY', 'WEEKLY', 'MONTHLY'}:
            errors.append(f'{location} FILE 按时间滚动时必须配置具体周期（HOURLY/DAILY/WEEKLY/MONTHLY）')
        if target == 'FILE' and trigger in {'SIZE', 'SIZE_OR_TIME'} \
                and not row['maxFileSizeMB'].strip():
            errors.append(f'{location} SIZE 触发必须配置 maxFileSizeMB')
        retention = positive_int(row['retentionDays'], location, 'retentionDays', errors)
        max_files = positive_int(row['maxFiles'], location, 'maxFiles', errors, allow_blank=True)
        max_size = positive_int(row['maxFileSizeMB'], location, 'maxFileSizeMB', errors,
                                allow_blank=True)
        disk_cap = positive_int(row['maxLocalDiskMB'], location, 'maxLocalDiskMB', errors,
                                allow_blank=True)
        if target == 'FILE' and disk_cap is not None:
            if max_files is not None and max_size is not None \
                    and max_files * max_size > disk_cap:
                errors.append(
                    f'{location} maxLocalDiskMB={disk_cap} 小于按滚动配置的最大占用'
                    f'（maxFileSizeMB × maxFiles = {max_files * max_size}），'
                    f'磁盘上限将永远无法触发或会过早删除归档')
        if (target == 'FILE' and trigger in {'TIME', 'SIZE_OR_TIME'}
                and interval in FILES_PER_DAY
                and max_files is not None and retention is not None):
            needed = math.ceil(retention * FILES_PER_DAY[interval])
            if max_files < needed:
                errors.append(
                    f'{location} maxFiles={max_files} 无法覆盖 retentionDays={retention}'
                    f'（按 {interval} 滚动至少需 {needed} 个归档文件），'
                    f'日志会在保留期满前被文件数上限提前清理')
        if row['cleanupPolicy'].strip() == 'LEGAL_HOLD_AWARE':
            audit_streams.append({'row': row, 'location': location, 'retentionDays': retention})
        for field in ('environment', 'archiveTarget', 'cleanupPolicy', 'owner'):
            if not row[field].strip():
                errors.append(f'{location} {field} 不能为空')

    # 跨表：审计流保留期不得低于审计类事件的保留期
    audit_events = [e for e in events
                    if 'audit' in e.get('responsibilityBoundary', '').lower()]
    for audit in audit_streams:
        stream_retention = audit['retentionDays'] or 0
        for event in audit_events:
            try:
                event_retention = int(event.get('retentionDays') or 0)
            except ValueError:
                continue
            if event_retention > stream_retention:
                errors.append(
                    f'{audit["location"]} 审计流 {audit["row"]["logStream"]} 保留期'
                    f'（{stream_retention} 天）小于审计事件 '
                    f'{event["eventName"]} 的保留期（{event_retention} 天），'
                    f'审计证据可能在合规要求前被清理')


def validate_sensitive(path: Path, errors: list[str]) -> None:
    headers, rows = read(path)
    if headers != POLICY_HEADERS:
        errors.append(f'敏感字段策略表头不正确：{headers}')
        return
    patterns = set()
    for n, row in enumerate(rows, 2):
        location = f'敏感字段策略第 {n} 行'
        pattern = row['fieldPattern'].strip()
        if not pattern:
            errors.append(f'{location} fieldPattern 不能为空')
        if pattern in patterns:
            errors.append(f'{location} fieldPattern 重复：{pattern}')
        patterns.add(pattern)
        if row['action'].strip().upper() not in ACTIONS:
            errors.append(f'{location} action 不正确：{row["action"]}')
        if not row['classification'].strip():
            errors.append(f'{location} classification 不能为空')
        if row['action'].strip().upper() == 'ALLOW' and not row['notes'].strip():
            errors.append(f'{location} ALLOW 动作必须在 notes 中说明用途和权限控制')


def validate_sensitive_coverage(field_rows: list[dict],
                              sensitive_rows: list[dict],
                              errors: list[str]) -> None:
    """标为敏感分类的字段必须被敏感策略中的 pattern 覆盖（* 通配）。"""
    patterns = [r['fieldPattern'].strip() for r in sensitive_rows if r['fieldPattern'].strip()]
    for row in field_rows:
        classification = row['classification'].strip().upper()
        if classification not in SENSITIVE_CLASSIFICATIONS:
            continue
        field_name = row['fieldName'].strip()
        if not any(fnmatch.fnmatchcase(field_name, pattern) for pattern in patterns):
            errors.append(
                f'字段 {field_name}（classification={classification}）未被敏感字段策略覆盖：'
                f'必须在 sensitive-field-policy.csv 中登记处理动作'
                f'（DROP/MASK/HASH/TRUNCATE/ALLOW）')


def main() -> int:
    parser = argparse.ArgumentParser(description='校验应用日志事件、字段、存储与敏感字段策略。')
    parser.add_argument('events', type=Path)
    parser.add_argument('--format-schema', type=Path)
    parser.add_argument('--event-fields', type=Path)
    parser.add_argument('--storage-policy', type=Path)
    parser.add_argument('--sensitive-policy', type=Path)
    args = parser.parse_args()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        events = []
        known_fields: set[str] = set()
        if args.format_schema:
            known_fields |= validate_fields(args.format_schema, errors, '日志格式目录',
                                            require_common=True)
        if args.event_fields:
            event_field_names = validate_fields(args.event_fields, errors, '事件字段目录')
            if args.format_schema:
                common = known_fields & event_field_names
                if common:
                    errors.append(f'事件字段目录与格式目录字段重名：{sorted(common)}'
                                  f'（同一字段只应在公共格式目录登记一次）')
            known_fields |= event_field_names
        _, events = read(args.events)
        validate_events(args.events, errors, known_fields, warnings)
        if args.storage_policy:
            validate_storage(args.storage_policy, errors, events)
        if args.sensitive_policy:
            validate_sensitive(args.sensitive_policy, errors)
            _, sensitive_rows = read(args.sensitive_policy)
            for fields_path, label in ((args.format_schema, '格式目录'),
                                       (args.event_fields, '事件字段目录')):
                if fields_path:
                    _, field_rows = read(fields_path)
                    validate_sensitive_coverage(field_rows, sensitive_rows, errors)
    except (OSError, ValueError) as exc:
        print(f'错误：{exc}', file=sys.stderr)
        return 2
    for warning in warnings:
        print(f'提示：{warning}', file=sys.stderr)
    if errors:
        for error in errors:
            print(f'错误：{error}', file=sys.stderr)
        return 1
    print('应用日志目录、字段、存储与敏感策略校验通过。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
