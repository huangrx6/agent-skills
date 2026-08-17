#!/usr/bin/env python3
"""validate_git_assets.py 的单元测试。

运行：python -m unittest discover -s scripts/tests -p 'test_*.py'
"""
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import validate_git_assets as v  # noqa: E402


def write_csv(path: Path, headers: list, rows: list) -> None:
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


BASE_COMMAND = {
    'command': 'git status', 'category': 'inspection', 'safetyLevel': 'readonly',
    'changesHistory': 'false', 'affectsRemote': 'false', 'requiresConfirm': 'false',
    'notes': '查看状态',
}
BASE_TYPE = {
    'type': 'feat', 'purpose': '新增功能', 'semverImpact': 'MINOR',
    'example': 'feat: add x', 'scopeExample': 'orders',
}
BASE_MERGE = {
    'strategy': 'fast-forward', 'command': 'git merge <b>', 'when': '能 ff 时',
    'producesMergeCommit': '否', 'preservesHistory': '线性', 'recommendedFor': '简单更新',
}
BASE_REVIEW = {
    'checkId': 'GIT-001', 'requirement': '操作前先 git status', 'severity': 'BLOCKER',
}


class CommandMatrixTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'cmd.csv'
            write_csv(p, v.COMMAND_HEADERS, [BASE_COMMAND])
            self.assertEqual(v.check_table(p, v.COMMAND_HEADERS, 'command', '命令安全矩阵',
                                           value_checks={'safetyLevel': v.SAFETY_LEVELS}), [])

    def test_bad_safety_level_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'cmd.csv'
            write_csv(p, v.COMMAND_HEADERS, [dict(BASE_COMMAND, safetyLevel='SAFE')])
            errors = v.check_table(p, v.COMMAND_HEADERS, 'command', '命令安全矩阵',
                                   value_checks={'safetyLevel': v.SAFETY_LEVELS})
            self.assertTrue(any('safetyLevel 无效' in e for e in errors))

    def test_duplicate_command_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'cmd.csv'
            write_csv(p, v.COMMAND_HEADERS, [BASE_COMMAND, dict(BASE_COMMAND)])
            errors = v.check_table(p, v.COMMAND_HEADERS, 'command', '命令安全矩阵')
            self.assertTrue(any('重复' in e for e in errors))

    def test_short_row_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'cmd.csv'
            p.write_text('command,category,safetyLevel,changesHistory,affectsRemote,requiresConfirm,notes\nstatus,inspection\n',
                         encoding='utf-8')
            try:
                v.check_table(p, v.COMMAND_HEADERS, 'command', '命令安全矩阵')
            except Exception as exc:
                self.fail(f'缺列导致崩溃：{type(exc).__name__}: {exc}')

    def test_bad_bool_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'cmd.csv'
            write_csv(p, v.COMMAND_HEADERS, [dict(BASE_COMMAND, changesHistory='YES')])
            errors = v.check_table(p, v.COMMAND_HEADERS, 'command', '命令安全矩阵',
                                   value_checks={'changesHistory': v.BOOLEANS_STR})
            self.assertTrue(any('changesHistory 无效' in e for e in errors))


class CommitTypeTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'type.csv'
            write_csv(p, v.TYPE_HEADERS, [BASE_TYPE])
            self.assertEqual(v.check_table(p, v.TYPE_HEADERS, 'type', '提交类型目录',
                                           value_checks={'type': v.COMMIT_TYPES,
                                                         'semverImpact': v.SEMVER_IMPACTS}), [])

    def test_bad_type_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'type.csv'
            write_csv(p, v.TYPE_HEADERS, [dict(BASE_TYPE, type='feature')])
            errors = v.check_table(p, v.TYPE_HEADERS, 'type', '提交类型目录',
                                   value_checks={'type': v.COMMIT_TYPES})
            self.assertTrue(any('type 无效' in e for e in errors))

    def test_bad_semver_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'type.csv'
            write_csv(p, v.TYPE_HEADERS, [dict(BASE_TYPE, semverImpact='CRITICAL')])
            errors = v.check_table(p, v.TYPE_HEADERS, 'type', '提交类型目录',
                                   value_checks={'semverImpact': v.SEMVER_IMPACTS})
            self.assertTrue(any('semverImpact 无效' in e for e in errors))


class MergeStrategyTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'merge.csv'
            write_csv(p, v.MERGE_HEADERS, [BASE_MERGE])
            self.assertEqual(v.check_table(p, v.MERGE_HEADERS, 'strategy', '合并策略矩阵'), [])

    def test_duplicate_strategy_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'merge.csv'
            write_csv(p, v.MERGE_HEADERS, [BASE_MERGE, dict(BASE_MERGE)])
            errors = v.check_table(p, v.MERGE_HEADERS, 'strategy', '合并策略矩阵')
            self.assertTrue(any('重复' in e for e in errors))


class ReviewChecklistTest(unittest.TestCase):
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


class CommitTemplateTest(unittest.TestCase):
    def test_template_with_all_sections_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'tmpl.md'
            p.write_text('# Conventional Commit\n<type>\nfeat\nfix\nBREAKING CHANGE\n## 撰写检查\n',
                         encoding='utf-8')
            self.assertEqual(v.check_commit_template(p), [])

    def test_template_missing_section_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'tmpl.md'
            p.write_text('# Commit\n', encoding='utf-8')
            self.assertTrue(any('缺少' in e for e in v.check_commit_template(p)))

    def test_template_missing_file_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'nonexistent.md'
            self.assertTrue(any('不存在' in e for e in v.check_commit_template(p)))


class BadHeaderTest(unittest.TestCase):
    def test_bad_header_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'bad.csv'
            p.write_text('bad1,bad2\nfoo,bar\n', encoding='utf-8')
            try:
                v.check_table(p, v.COMMAND_HEADERS, 'command', '命令安全矩阵')
            except Exception as exc:
                self.fail(f'表头错误导致崩溃：{type(exc).__name__}: {exc}')


class MainEndToEndTest(unittest.TestCase):
    def _make_assets_dir(self, tmp: Path) -> Path:
        assets = Path(tmp) / 'assets'
        assets.mkdir()
        write_csv(assets / 'git-command-safety-matrix.csv', v.COMMAND_HEADERS, [BASE_COMMAND])
        write_csv(assets / 'commit-type-catalog.csv', v.TYPE_HEADERS, [BASE_TYPE])
        write_csv(assets / 'merge-strategy-matrix.csv', v.MERGE_HEADERS, [BASE_MERGE])
        write_csv(assets / 'git-review-checklist.csv', v.REVIEW_HEADERS, [BASE_REVIEW])
        (assets / 'commit-message.template.md').write_text(
            '# Conventional Commit\n<type>\nfeat\nfix\nBREAKING CHANGE\n## 撰写检查\n',
            encoding='utf-8')
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