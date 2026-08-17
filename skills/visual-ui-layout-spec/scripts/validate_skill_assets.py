#!/usr/bin/env python3
"""校验 visual-ui-layout-spec Skill 的所有资产存在且 JSON 合法。

运行：uv run scripts/validate_skill_assets.py .

纯标准库，无第三方依赖。
"""
from __future__ import annotations
import argparse, csv, json, sys
from pathlib import Path

REQUIRED_FILES = [
    'assets/layout-spec.template.md', 'assets/ui-layout-model.schema.json',
    'assets/self-check.csv', 'assets/prompts/ui-semantic.md',
    'references/workflow.md', 'references/visual-runtime.md', 'references/remote-vllm.md',
    'references/measurement-strategy.md', 'references/typography-color-style.md',
    'references/components-charts-tables.md', 'references/states-responsive.md',
    'references/evidence-confidence.md',
    'scripts/image_probe.py', 'scripts/visual_runtime.py',
    'scripts/validate_layout_spec.py', 'scripts/tests/test_skill.py', 'SKILL.md',
]
JSON_FILES = [
    'assets/ui-layout-model.schema.json',
]
SELF_CHECK_CSV = 'assets/self-check.csv'
SELF_CHECK_HEADERS = ['checkId', 'requirement', 'severity']


def check_skill(root):
    errors, warnings = [], []
    for rel in REQUIRED_FILES:
        if not (root / rel).is_file():
            errors.append(f'缺少 {rel}')
    for rel in JSON_FILES:
        path = root / rel
        if not path.is_file():
            continue
        try:
            json.loads(path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as e:
            errors.append(f'{rel} JSON 无效 line {e.lineno} col {e.colno}: {e.msg}')
        except Exception as e:
            errors.append(f'{rel} 读取失败: {type(e).__name__}: {e}')
    sc_path = root / SELF_CHECK_CSV
    if sc_path.is_file():
        try:
            with sc_path.open('r', encoding='utf-8-sig', newline='') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                rows = list(reader)
            if header != SELF_CHECK_HEADERS or not rows:
                errors.append(f'{SELF_CHECK_CSV} 表头或内容无效')
        except Exception as e:
            errors.append(f'{SELF_CHECK_CSV} 读取失败: {type(e).__name__}: {e}')
    else:
        errors.append(f'缺少 {SELF_CHECK_CSV}')
    try:
        import PIL  # noqa: F401
    except ImportError:
        warnings.append("Pillow 未安装：image_probe.py 首次运行时 uv 会自动安装（PEP 723）")
    return errors, warnings


def main():
    p = argparse.ArgumentParser(description="校验 visual-ui-layout-spec Skill 资产")
    p.add_argument("path", nargs="?", default=".", help="Skill 根目录（默认当前目录）")
    args = p.parse_args()
    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"错误：目录不存在 {root}", file=sys.stderr)
        return 2
    errors, warnings = check_skill(root)
    for w in warnings:
        print(f"警告: {w}", file=sys.stderr)
    if errors:
        print('\n'.join('错误: ' + e for e in errors), file=sys.stderr)
        return 1
    print('visual-ui-layout-spec Skill 资源校验通过。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
