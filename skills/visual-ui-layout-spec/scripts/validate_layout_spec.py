#!/usr/bin/env python3
"""校验 UI 布局规格 Markdown 文档是否符合 layout-spec.template.md 的骨架。

运行：uv run scripts/validate_layout_spec.py doc.md [--json]

纯标准库，无第三方依赖。
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path

SECTION_PATTERN = r'^## §{}\b'
PLACEHOLDER_PATTERN = re.compile(r'\{[^\n{}]+\}|\bXXX\b|待补充')
FENCE_PATTERN = re.compile(r'```[^\n]*\n.*?```', re.DOTALL)


def _strip_fences(text):
    return FENCE_PATTERN.sub('', text)


def check_layout_spec(text):
    errors = []
    for n in range(1, 11):
        if not re.search(SECTION_PATTERN.format(n), text, re.MULTILINE):
            errors.append(f'缺少 §{n} 分节')
    if PLACEHOLDER_PATTERN.search(_strip_fences(text)):
        errors.append('存在模板占位符（{xxx}/XXX/待补充）')
    if 'Evidence Ledger' not in text:
        errors.append('缺少 Evidence Ledger 段')
    return errors


def main():
    p = argparse.ArgumentParser(description="校验 UI 布局规格 Markdown 文档")
    p.add_argument("path", help="布局规格 Markdown 文件路径")
    p.add_argument("--json", action="store_true", help="以 JSON 输出诊断")
    args = p.parse_args()
    path = Path(args.path)
    if not path.is_file():
        print(f"错误：文件不存在 {path}", file=sys.stderr)
        return 2
    text = path.read_text(encoding='utf-8')
    errors = check_layout_spec(text)
    if errors:
        if args.json:
            print(json.dumps({'ok': False, 'errors': errors}, ensure_ascii=False, indent=2))
        else:
            print('\n'.join('错误: ' + x for x in errors), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({'ok': True, 'path': str(path.resolve())}, ensure_ascii=False, indent=2))
    else:
        print('UI 布局规格文档校验通过。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
