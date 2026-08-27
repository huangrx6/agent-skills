#!/usr/bin/env python3
"""校验数据库规范 Skill 的目录资产与模板。"""
from __future__ import annotations
import argparse, csv, sys
from pathlib import Path

SEVERITIES={'MUST','SHOULD','MAY','BLOCKER','MAJOR','MINOR'}
RULE_SEVERITIES={'MUST','SHOULD','MAY'}
REVIEW_SEVERITIES={'BLOCKER','MAJOR','MINOR'}
AUTOMATABLE={'true','false','partly'}


def g(r, k):
    """安全读取 CSV 单元格：缺列返回空串而非 KeyError。"""
    v = r.get(k)
    return "" if v is None else v

def read(path):
    if not path.is_file(): raise ValueError(f'文件不存在：{path}')
    with path.open('r',encoding='utf-8-sig',newline='') as f:
        r=csv.DictReader(f)
        if not r.fieldnames: raise ValueError(f'缺少表头：{path}')
        return r.fieldnames,list(r)

def exact(path, headers, label):
    h,rows=read(path); e=[]
    if h!=headers: e.append(f'{label}表头不正确：{h}')
    if not rows: e.append(f'{label}至少需要一条数据')
    return rows,e

def validate_naming(path):
    rows,e=exact(path,['ruleId','objectType','convention','example','severity','notes'],'命名目录')
    seen=set()
    for i,r in enumerate(rows,2):
        rid=g(r,'ruleId')
        if not rid or rid in seen: e.append(f'命名目录第 {i} 行 ruleId 无效或重复')
        seen.add(rid)
        if g(r,'severity') not in RULE_SEVERITIES: e.append(f'命名目录第 {i} 行 severity 无效（应为 {sorted(RULE_SEVERITIES)}）')
    return e

def validate_types(path):
    rows,e=exact(path,['businessData','preferredType','avoid','keyDecision'],'类型矩阵')
    for i,r in enumerate(rows,2):
        if not all(g(r,k) for k in ('businessData','preferredType','avoid','keyDecision')):
            e.append(f'类型矩阵第 {i} 行存在空字段')
    return e

def validate_migration(path):
    rows,e=exact(path,['change','defaultRisk','compatibleRollout','unsafeShortcut','verification'],'迁移矩阵')
    allowed={'LOW','MEDIUM','HIGH','DESTRUCTIVE','CONDITIONAL'}
    for i,r in enumerate(rows,2):
        if g(r,'defaultRisk') not in allowed: e.append(f'迁移矩阵第 {i} 行风险等级无效（应为 {sorted(allowed)}）')
        for k in ('change','compatibleRollout','unsafeShortcut','verification'):
            if not g(r,k): e.append(f'迁移矩阵第 {i} 行 {k} 为空')
    return e

def validate_review(path):
    rows,e=exact(path,['checkId','category','requirement','severity','automatable','evidence'],'评审清单')
    seen=set()
    for i,r in enumerate(rows,2):
        cid=g(r,'checkId')
        if not cid or cid in seen: e.append(f'评审清单第 {i} 行 checkId 无效或重复')
        seen.add(cid)
        if g(r,'severity') not in REVIEW_SEVERITIES: e.append(f'评审清单第 {i} 行 severity 无效（应为 {sorted(REVIEW_SEVERITIES)}）')
        if g(r,'automatable') not in AUTOMATABLE: e.append(f'评审清单第 {i} 行 automatable 无效（应为 {sorted(AUTOMATABLE)}）')
    return e

def validate_template(path, tokens, label):
    if not path.is_file(): return [f'{label}不存在：{path}']
    text=path.read_text(encoding='utf-8')
    return [f'{label}缺少：{x}' for x in tokens if x not in text]

def main():
    p=argparse.ArgumentParser()
    p.add_argument('naming',type=Path)
    p.add_argument('--types',type=Path,required=True)
    p.add_argument('--migration',type=Path,required=True)
    p.add_argument('--review',type=Path,required=True)
    p.add_argument('--table-template',type=Path,required=True)
    p.add_argument('--migration-template',type=Path,required=True)
    a=p.parse_args(); errors=[]
    try:
        errors+=validate_naming(a.naming)
        errors+=validate_types(a.types)
        errors+=validate_migration(a.migration)
        errors+=validate_review(a.review)
        errors+=validate_template(a.table_template,['业务不变量','字段','索引','生命周期'],'表设计模板')
        errors+=validate_template(a.migration_template,['Expand','Migrate','Contract','停止条件','失败处理'],'迁移模板')
    except (OSError,ValueError) as exc:
        print(f'错误：{exc}',file=sys.stderr); return 2
    if errors:
        for e in errors: print(f'错误：{e}',file=sys.stderr)
        return 1
    print('数据库规范 Skill 校验通过。'); return 0
if __name__=='__main__': raise SystemExit(main())
