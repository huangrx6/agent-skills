#!/usr/bin/env python3
"""异常处理规范资产校验。

校验错误码注册表与异常映射表的格式、枚举、跨表一致性和基本语义：

- 注册表：错误码命名、状态码范围、分类、可重试性、关键字段非空、生命周期
- 映射表：内部异常到对外契约的映射、状态码与注册表一致、可重试性一致
- 跨表：映射引用的错误码必须已登记；映射与注册表的 httpStatus/retryable 不得矛盾；
  同一内部异常不得重复映射到不同错误码

分类与状态码的语义约束（按 HTTP 惯例）：
- INPUT 类对应 400/422
- AUTH 类对应 401/403/404
- BUSINESS 类对应 400/404/409/422；CONFLICT 类对应 409
- DEPENDENCY 类对应 5xx（502/503/504）
- SYSTEM 类对应 5xx（500）
- RATE_LIMIT 类对应 429

用法：
  python scripts/validate_error_catalog.py assets/error-code-registry.csv \\
      --mapping assets/exception-mapping.csv
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

REGISTRY = ['code', 'title', 'httpStatus', 'category', 'retryable',
            'publicDetail', 'owner', 'introducedVersion', 'deprecatedVersion']
MAPPING = ['internalException', 'publicCode', 'httpStatus', 'retryable', 'notes']

# RATE_LIMIT 新增（覆盖限流，failure-model 的"取消与超时"中限流场景）
CATEGORIES = {'INPUT', 'BUSINESS', 'AUTH', 'CONFLICT', 'DEPENDENCY',
              'RATE_LIMIT', 'SYSTEM'}
BOOLS = {'true', 'false'}

# 分类 → 允许的 HTTP 状态码区间（语义约束，用于跨字段校验）
CATEGORY_STATUS = {
    'INPUT': {400, 422},
    'BUSINESS': {400, 404, 409, 422},
    'AUTH': {401, 403, 404},
    'CONFLICT': {409},
    'DEPENDENCY': {502, 503, 504},
    'RATE_LIMIT': {429},
    'SYSTEM': {500},
}


def read(path: Path):
    if not path.is_file():
        raise ValueError(f'文件不存在：{path}')
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        # 行缺列时 DictReader 给 None，统一转成空串避免后续 .strip() 崩溃
        rows = [{k: (v or '') for k, v in row.items()} for row in reader]
        return reader.fieldnames or [], rows


def bool_or_error(value: str, location: str, field: str, errors: list[str]) -> bool:
    if value.strip().lower() in BOOLS:
        return True
    errors.append(f'{location} {field} 不正确：{value}')
    return False


def validate_registry(path: Path, errors: list[str],
                      warnings: list[str]) -> dict[str, dict]:
    """校验错误码注册表，返回 {code: row} 供映射表跨表校验使用。"""
    headers, rows = read(path)
    if headers != REGISTRY:
        errors.append(f'错误码注册表表头不正确：{headers}')
        return {}
    codes: dict[str, dict] = {}
    for n, row in enumerate(rows, 2):
        location = f'错误码注册表第 {n} 行'
        code = row['code'].strip()
        if not re.fullmatch(r'[A-Z][A-Z0-9_]*', code):
            errors.append(f'{location} 错误码格式不正确：{code}')
        if code in codes:
            errors.append(f'{location} 错误码重复：{code}')
        # 关键字段非空
        for field in ('title', 'publicDetail', 'owner', 'introducedVersion'):
            if not row[field].strip():
                errors.append(f'{location} {field} 不能为空')
        # 废弃应记录引入版本
        if row['deprecatedVersion'].strip() and not row['introducedVersion'].strip():
            errors.append(f'{location} deprecatedVersion 有值但 introducedVersion 为空')
        if row['deprecatedVersion'].strip():
            warnings.append(
                f'{location} {code} 已标记废弃（{row["deprecatedVersion"].strip()}），应规划调用方迁移')
        category = row['category'].strip()
        if category not in CATEGORIES:
            errors.append(f'{location} category 不正确：{category}')
        # httpStatus
        try:
            status = int(row['httpStatus'])
            if not 400 <= status <= 599:
                raise ValueError
        except ValueError:
            errors.append(f'{location} httpStatus 不正确：{row["httpStatus"]}')
            status = None
        retryable_valid = bool_or_error(row['retryable'], location, 'retryable', errors)
        # category 与 httpStatus 语义一致性
        if status is not None and category in CATEGORY_STATUS \
                and status not in CATEGORY_STATUS[category]:
            errors.append(
                f'{location} category={category} 与 httpStatus={status} 语义不匹配'
                f'（{category} 类应为 {sorted(CATEGORY_STATUS[category])} 之一）')
        if code:
            codes[code] = {'httpStatus': status, 'category': category,
                           'retryable': row['retryable'].strip().lower()
                           if retryable_valid else None}
    return codes


def validate_mapping(path: Path, codes: dict[str, dict],
                     errors: list[str], warnings: list[str]) -> None:
    """校验异常映射表，并做与注册表的跨表一致性检查。"""
    headers, rows = read(path)
    if headers != MAPPING:
        errors.append(f'异常映射表表头不正确：{headers}')
        return
    seen_internals: dict[str, str] = {}
    for n, row in enumerate(rows, 2):
        location = f'异常映射表第 {n} 行'
        internal = row['internalException'].strip()
        code = row['publicCode'].strip()
        if not internal:
            errors.append(f'{location} internalException 不能为空')
        if not code:
            errors.append(f'{location} publicCode 不能为空')
            continue
        # 同一内部异常不得重复登记（无论是否映射到相同错误码）
        if internal and internal in seen_internals:
            prev = seen_internals[internal]
            if prev != code:
                errors.append(
                    f'{location} internalException={internal} 映射矛盾'
                    f'（已映射到 {prev}，此处又映射到 {code}）')
            else:
                errors.append(f'{location} internalException={internal} 重复登记')
        elif internal:
            seen_internals[internal] = code
        if code not in codes:
            errors.append(f'{location} 错误码未登记：{code}')
            continue
        # httpStatus 与注册表一致
        try:
            status = int(row['httpStatus'])
        except ValueError:
            errors.append(f'{location} httpStatus 不正确：{row["httpStatus"]}')
            status = None
        reg_status = codes[code]['httpStatus']
        if status is not None and reg_status is not None and status != reg_status:
            errors.append(
                f'{location} httpStatus={status} 与注册表（{reg_status}）不一致')
        # retryable 与注册表一致（注册表值为 None 时跳过，避免脏值级联）
        reg_retryable = codes[code]['retryable']
        if bool_or_error(row['retryable'], location, 'retryable', errors):
            map_retryable = row['retryable'].strip().lower()
            if reg_retryable is not None and map_retryable != reg_retryable:
                errors.append(
                    f'{location} retryable={map_retryable} 与注册表（{reg_retryable}）不一致')
        if not row['notes'].strip():
            warnings.append(f'{location} notes 为空，建议补充映射说明')


def main() -> int:
    parser = argparse.ArgumentParser(
        description='校验异常处理错误码注册表与异常映射表的格式、枚举和跨表一致性。')
    parser.add_argument('registry', type=Path)
    parser.add_argument('--mapping', type=Path)
    args = parser.parse_args()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        codes = validate_registry(args.registry, errors, warnings)
        if args.mapping:
            validate_mapping(args.mapping, codes, errors, warnings)
    except (OSError, ValueError) as exc:
        print(f'错误：{exc}', file=sys.stderr)
        return 2
    for warning in warnings:
        print(f'提示：{warning}', file=sys.stderr)
    if errors:
        for error in errors:
            print(f'错误：{error}', file=sys.stderr)
        return 1
    print('异常处理目录校验通过。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
