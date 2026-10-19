#!/usr/bin/env python3
"""显式数据移动规格的读取、来源和引用校验（version 3）。

唯一真源是 `movements`：E/R/W/X、兴趣对象、数据组、属性逐项写出。
`op` 只是可选分类标签，用来推导默认描述、检查命名一致性和排序；
它不产生移动，也不改变 CFP。`description` 可省略，省略时按 op 与移动类型推导。
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import operation_types as ops  # noqa: E402  # pyright: ignore[reportMissingImports]

VERSION = 3


class SpecError(SystemExit):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SpecError(f"规格有误：{message}")


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise SpecError(f"规格有误：{label} 不能为空")
    _require(value == value.strip(), f"{label} 不能含首尾空白，否则回读时标识会变化")


def _fields(values: object, label: str) -> None:
    if not isinstance(values, list) or not values:
        raise SpecError(f"规格有误：{label} 必须是非空字段列表")
    _require(all(_text(v) and ',' not in v and '，' not in v for v in values),
             f"{label} 字段必须是非空字符串，字段名不能包含逗号")
    _require(len(set(values)) == len(values), f"{label} 有重复字段")


def load(path: str | Path) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SpecError(f"无法读取规格 {path}：{exc}") from None
    return load_from_dict(value)


def load_from_dict(value: object) -> dict:
    if not isinstance(value, dict):
        raise SpecError("规格有误：顶层必须是对象")
    spec = copy.deepcopy(value)
    _require(type(spec.get("version")) is int and spec["version"] == VERSION,
             f"仅支持 version {VERSION}；请按 init 生成的格式填写，旧规格需按新格式重写")
    _require(_text(spec.get("project")), "缺少 project")
    removed = {'profile', 'profile_source', 'entities', 'users', 'user_scope', 'global_extras'} & spec.keys()
    _require(not removed, f"不支持旧规格字段：{', '.join(sorted(removed))}")
    modules = spec.get("modules")
    if not isinstance(modules, list) or not modules:
        raise SpecError("规格有误：modules 必须是非空列表")
    mapping = {}
    for m in modules:
        _require(isinstance(m, dict) and _text(m.get("l2")) and _text(m.get("l3")), "模块缺 l2/l3")
        _require(m['l3'] not in mapping, f"三级模块 {m['l3']} 重复声明")
        for key in ("l2", "l3"):
            _identifier(m[key], f"模块.{key}")
        mapping[m['l3']] = m['l2']
    spec['_l3_to_l2'] = mapping
    measurement = spec.get('measurement')
    if not isinstance(measurement, dict):
        raise SpecError("规格有误：缺少 measurement")
    for key in ('purpose', 'scope', 'boundary', 'layer'):
        _require(_text(measurement.get(key)), f"measurement.{key} 不能为空")
    _fields(measurement.get('functional_users'), 'measurement.functional_users')
    for user in measurement['functional_users']:
        _identifier(user, 'measurement.functional_users')
    conventions = measurement.get('conventions', {})
    _require(isinstance(conventions, dict), "measurement.conventions 必须是对象")
    for key, item in conventions.items():
        _require(_text(key) and _text(item), "measurement.conventions 的键和值都必须是非空文字")
    processes = spec.get('processes')
    if not isinstance(processes, list) or not processes:
        raise SpecError('规格有误：processes 必须是非空列表')
    ids, names = set(), set()
    for i, p in enumerate(processes, 1):
        _require(isinstance(p, dict), f'processes[{i}] 不是对象')
        for key in ('l3', 'name'):
            _identifier(p.get(key), f'processes[{i}].{key}')
        _require(p['l3'] in mapping, f"三级模块 {p['l3']} 没在 modules 里声明")
        _require(p['name'] not in names, f"功能过程名 {p['name']} 重复，请用业务限定区分展示名称")
        names.add(p['name'])
        _require(not ({'op', 'entity'} & set(p) - {'op'}), '过程只使用显式 movements，不使用 op/entity 模板')
        for key in ('id', 'trigger', 'user'):
            _require(_text(p.get(key)), f'processes[{i}].{key} 不能为空')
        for key in ('id', 'user'):
            _identifier(p[key], f'processes[{i}].{key}')
        _require(p['user'] in spec['measurement']['functional_users'], f"{p['id']} 功能用户未在 measurement 声明")
        _require(p.get('status') in ('confirmed', 'unverified'), f"{p['id']} status 必须为 confirmed/unverified")
        if p.get('op') is not None:
            _require(isinstance(p['op'], str) and p['op'] in ops.OPS,
                     f"{p['id']} op 不在词表里：{p['op']}；允许值 {sorted(ops.OPS)}")
        if p.get('op_note') is not None:
            _require(_text(p['op_note']), f"{p['id']}.op_note 必须是非空字符串")
        if p.get('evidence') is not None:
            items = p['evidence']
            _require(isinstance(items, list) and bool(items), f"{p['id']}.evidence 必须是非空数组")
            for item in items:
                _identifier(item, f"{p['id']}.evidence 项")
            _require(len(set(items)) == len(items), f"{p['id']}.evidence 有重复项")
        _require(isinstance(p.get('movements'), list) and len(p['movements']) >= 2, f"{p['id']} 至少两个数据移动")
        if 'source' in p:
            _require(_text(p['source']), f"{p['id']}.source 必须是非空字符串")
        for j, m in enumerate(p['movements'], 1):
            label = f"{p['id']}.movements[{j}]"
            _require(isinstance(m, dict), f'{label} 必须是对象')
            _require(m.get('type') in ('E', 'R', 'W', 'X'), f'{label} type 非法')
            for key in ('object', 'group'):
                _require(_text(m.get(key)), f'{label}.{key} 不能为空')
                _identifier(m[key], f'{label}.{key}')
            for key in ('description', 'source', 'repeat_reason'):
                if key in m:
                    _require(_text(m[key]), f'{label}.{key} 必须是非空字符串')
            _fields(m.get('attributes'), f'{label}.attributes')
            if p['status'] == 'confirmed':
                _require(_text(m.get('source') or p.get('source')), f'{label} 已确认项必须提供 source')
        _require(p['id'] not in ids, f"过程编号 {p['id']} 重复")
        ids.add(p['id'])
    return spec


def moves_for(proc: dict) -> list[str]:
    return [m['type'] for m in proc['movements']]


def group_by_module(spec: dict) -> list[tuple[str, str, list[dict]]]:
    return [(m['l2'], m['l3'], [p for p in spec['processes'] if p['l3'] == m['l3']]) for m in spec['modules']]


def stats(spec: dict) -> dict:
    modules = {}
    for l2, l3, procs in group_by_module(spec):
        item = modules.setdefault(l2, {'l3': 0, 'processes': 0, 'cfp': 0})
        item['l3'] += 1
        item['processes'] += len(procs)
        item['cfp'] += sum(len(moves_for(p)) for p in procs)
    return {'modules': modules, 'processes': len(spec['processes']),
            'cfp': sum(m['cfp'] for m in modules.values())}
