#!/usr/bin/env python3
"""validate_documentation_system.py 与 doc_impact.py 的单元测试。

运行：python -m unittest discover -s scripts/tests -p 'test_*.py'
"""
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import validate_documentation_system as v  # noqa: E402
import doc_impact  # noqa: E402


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


BASE_TYPE = {
    'type': 'README', 'canonicalLocation': 'README.md', 'purpose': 'human entrypoint',
    'createWhen': 'repository created', 'updateWhen': 'setup changes',
    'newVsUpdate': 'always update existing', 'lifecycle': 'active',
}
BASE_REVIEW = {
    'checkId': 'DOC-001', 'category': 'DISCOVERY', 'requirement': '职责清楚',
    'severity': 'BLOCKER', 'automatable': 'partly', 'evidence': 'link validation',
}


class CheckCsvTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'types.csv'
            write_csv(p, ['type', 'canonicalLocation', 'purpose', 'createWhen',
                          'updateWhen', 'newVsUpdate', 'lifecycle'], [BASE_TYPE])
            self.assertEqual(v.check_csv(p, ['type', 'canonicalLocation', 'purpose',
                                             'createWhen', 'updateWhen', 'newVsUpdate',
                                             'lifecycle'], 'type'), [])

    def test_duplicate_key_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'types.csv'
            write_csv(p, ['type', 'canonicalLocation', 'purpose', 'createWhen',
                          'updateWhen', 'newVsUpdate', 'lifecycle'],
                      [BASE_TYPE, dict(BASE_TYPE)])
            self.assertTrue(any('重复' in e for e in v.check_csv(
                p, ['type', 'canonicalLocation', 'purpose', 'createWhen',
                    'updateWhen', 'newVsUpdate', 'lifecycle'], 'type')))


class CheckReviewValuesTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'review.csv'
            write_csv(p, ['checkId', 'category', 'requirement', 'severity',
                          'automatable', 'evidence'], [BASE_REVIEW])
            self.assertEqual(v.check_review_values(p), [])

    def test_bad_severity_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'review.csv'
            write_csv(p, ['checkId', 'category', 'requirement', 'severity',
                          'automatable', 'evidence'],
                      [dict(BASE_REVIEW, severity='CRITICAL')])
            self.assertTrue(any('severity' in e for e in v.check_review_values(p)))

    def test_bad_automatable_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'review.csv'
            write_csv(p, ['checkId', 'category', 'requirement', 'severity',
                          'automatable', 'evidence'],
                      [dict(BASE_REVIEW, automatable='sometimes')])
            self.assertTrue(any('automatable' in e for e in v.check_review_values(p)))

    def test_short_row_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'review.csv'
            p.write_text('checkId,category,requirement,severity,automatable,evidence\nX,DISCOVERY\n',
                         encoding='utf-8')
            try:
                v.check_review_values(p)
            except Exception as exc:
                self.fail(f'缺列导致崩溃：{type(exc).__name__}: {exc}')


class CheckTypeValuesTest(unittest.TestCase):
    def test_valid_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'types.csv'
            write_csv(p, ['type', 'canonicalLocation', 'purpose', 'createWhen',
                          'updateWhen', 'newVsUpdate', 'lifecycle'], [BASE_TYPE])
            self.assertEqual(v.check_type_values(p), [])

    def test_bad_lifecycle_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'types.csv'
            write_csv(p, ['type', 'canonicalLocation', 'purpose', 'createWhen',
                          'updateWhen', 'newVsUpdate', 'lifecycle'],
                      [dict(BASE_TYPE, lifecycle='FOREVER')])
            self.assertTrue(any('lifecycle' in e for e in v.check_type_values(p)))


class CheckTemplateTest(unittest.TestCase):
    def test_template_with_sections_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 't.md'
            p.write_text('## Purpose\n## Repository Map\n', encoding='utf-8')
            self.assertEqual(v.check_template(p, ['## Purpose', '## Repository Map']), [])

    def test_template_missing_section_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 't.md'
            p.write_text('## Purpose\n', encoding='utf-8')
            self.assertTrue(any('缺少' in e for e in
                                v.check_template(p, ['## Purpose', '## Repository Map'])))


class CheckExamplesTest(unittest.TestCase):
    def _make_assets(self, tmp: Path, readme_text: str) -> Path:
        assets = Path(tmp) / 'assets'
        assets.mkdir()
        (Path(tmp) / 'examples').mkdir()
        (Path(tmp) / 'examples' / 'README.md').write_text(readme_text, encoding='utf-8')
        return assets

    def test_readme_with_boundary_declaration_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            assets = self._make_assets(Path(tmp), '不抄用，作参照。实际项目以自身为准。')
            self.assertEqual(v.check_examples(assets), [])

    def test_readme_without_boundary_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            assets = self._make_assets(Path(tmp), '示例内容')
            self.assertTrue(any('边界声明' in e for e in v.check_examples(assets)))


class DocImpactMatchTest(unittest.TestCase):
    def test_match_src_glob(self):
        self.assertTrue(doc_impact.match('src/**', 'src/main/java/x.java'))
        self.assertTrue(doc_impact.match('src/**', 'src/x.java'))
        self.assertFalse(doc_impact.match('src/**', 'other/x.java'))

    def test_match_docs_glob(self):
        self.assertTrue(doc_impact.match('docs/**', 'docs/index.md'))
        self.assertTrue(doc_impact.match('docs/**', 'docs/architecture/x.md'))

    def test_match_exact_filename(self):
        self.assertTrue(doc_impact.match('AGENTS.md', 'AGENTS.md'))
        self.assertFalse(doc_impact.match('AGENTS.md', 'src/AGENTS.md'))

    def test_match_alt_without_double_star(self):
        # **/api/** 也应匹配根级 api/...
        self.assertTrue(doc_impact.match('**/api/**', 'api/v1/orders.yaml'))
        self.assertTrue(doc_impact.match('**/api/**', 'contracts/api/spec.yaml'))


class DocImpactMainTest(unittest.TestCase):
    def _run(self, tmp: Path, paths: list[str]):
        rules = tmp / 'rules.csv'
        write_csv(rules, ['pathPattern', 'documentAreas', 'reason', 'requiredAction'],
                  [{'pathPattern': 'src/**', 'documentAreas': 'DEVELOPMENT',
                    'reason': 'code changed', 'requiredAction': 'update docs'}])
        old_argv = sys.argv
        sys.argv = ['prog', '--rules', str(rules)] + paths
        import io, contextlib
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = doc_impact.main()
            return rc, buf.getvalue()
        finally:
            sys.argv = old_argv

    def test_matching_path_outputs_areas(self):
        import tempfile as tf
        with tf.TemporaryDirectory() as tmp:
            rc, out = self._run(Path(tmp), ['src/x.java'])
            self.assertEqual(rc, 0)
            self.assertIn('DEVELOPMENT', out)

    def test_no_match_prints_hint(self):
        import tempfile as tf
        with tf.TemporaryDirectory() as tmp:
            rc, out = self._run(Path(tmp), ['other/file.txt'])
            self.assertEqual(rc, 0)
            self.assertIn('未匹配', out)


if __name__ == '__main__':
    unittest.main()
