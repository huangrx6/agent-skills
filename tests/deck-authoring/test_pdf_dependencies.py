"""PDF integration dependencies must not terminate unittest discovery."""
from __future__ import annotations

import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent


def load_pdf_tests(override: str, found: str | None):
    spec = importlib.util.spec_from_file_location("_pdf_dependency_fixture", HERE / "test_pdf.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(os.environ, {"DECK_PDFINFO": override}), patch("shutil.which", return_value=found):
        spec.loader.exec_module(module)
    return module


def run_with_following_test(case):
    visited = []

    class FollowingModule(unittest.TestCase):
        def test_still_runs(self):
            visited.append(True)

    suite = unittest.TestSuite([
        unittest.defaultTestLoader.loadTestsFromTestCase(case),
        unittest.defaultTestLoader.loadTestsFromTestCase(FollowingModule),
    ])
    result = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
    return result, visited


class TestPdfDependencies(unittest.TestCase):
    def test_missing_dependency_skips_all_exports_and_runs_following_tests(self):
        module = load_pdf_tests("", None)
        with patch.object(module, "_load", side_effect=AssertionError("must not launch export")) as load:
            result, visited = run_with_following_test(module.TestPdfExport)
        self.assertTrue(result.wasSuccessful())
        self.assertEqual(result.testsRun, 7)
        self.assertEqual(len(result.skipped), 6)
        self.assertTrue(all("pdfinfo" in reason for _, reason in result.skipped))
        self.assertEqual(visited, [True])
        load.assert_not_called()

    def test_configured_dependency_failure_is_an_error_and_suite_continues(self):
        for override, found in (("/configured/pdfinfo", None), ("", "/path/pdfinfo")):
            with self.subTest(override=override, found=found):
                module = load_pdf_tests(override, found)
                with patch.object(module.TestPdfExport, "_prepare_exports",
                                  side_effect=SystemExit("pdfinfo execution failed")) as prepare:
                    result, visited = run_with_following_test(module.TestPdfExport)
                prepare.assert_called_once()
                self.assertEqual(len(result.errors), 1)
                self.assertIn("RuntimeError: PDF integration setup failed", result.errors[0][1])
                self.assertEqual(result.skipped, [])
                self.assertEqual(visited, [True])

    def test_production_inspection_still_requires_pdfinfo(self):
        module = load_pdf_tests("", None)
        pdf = module._load("_pdf_required_dependency", os.path.join(module.SCRIPTS, "pdf.py"))
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "sample.pdf"
            source.write_bytes(b"%PDF-1.4\n")
            with patch.dict(os.environ, {"DECK_PDFINFO": ""}), patch.object(pdf.shutil, "which", return_value=None):
                with self.assertRaisesRegex(SystemExit, "找不到 pdfinfo"):
                    pdf.inspect(str(source))


if __name__ == "__main__":
    unittest.main()
