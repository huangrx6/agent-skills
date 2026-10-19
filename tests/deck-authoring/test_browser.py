"""Browser discovery is portable and respects explicit configuration."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / "skills/deck-authoring/scripts/browser.py"
spec = importlib.util.spec_from_file_location("deck_browser_test", SCRIPT)
browser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(browser)


class TestBrowser(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def executable(self, name):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test executable fixture, never launched")
        path.chmod(0o755)
        return str(path.resolve())

    def test_explicit_overrides_environment_and_accepts_spaces(self):
        binary = self.executable("Application Support/chrome")
        with patch.dict(os.environ, {"DECK_CHROME": "/missing"}), patch.object(browser.shutil, "which", return_value=None):
            self.assertEqual(browser.find_chrome(binary), binary)

    def test_bad_explicit_setting_is_not_silently_ignored(self):
        with patch.dict(os.environ, {"DECK_CHROME": "/missing"}), patch.object(browser.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "Configured"):
                browser.find_chrome()

    def test_linux_path_detection(self):
        binary = self.executable("chromium")
        with patch.dict(os.environ, {}, clear=True), patch.object(browser.sys, "platform", "linux"), \
                patch.object(browser.shutil, "which", side_effect=lambda name: binary if name == "chromium" else None):
            self.assertEqual(browser.find_chrome(), binary)

    def test_windows_install_location(self):
        binary = self.executable("Google/Chrome/Application/chrome.exe")
        with patch.dict(os.environ, {"PROGRAMFILES": str(self.root)}, clear=True), \
                patch.object(browser.sys, "platform", "win32"), patch.object(browser.shutil, "which", return_value=None):
            self.assertEqual(browser.find_chrome(), binary)

    def test_nonexecutable_does_not_pass_and_missing_browser_is_actionable(self):
        binary = Path(self.executable("chrome"))
        binary.chmod(0o644)
        with patch.dict(os.environ, {}, clear=True), patch.object(browser.shutil, "which", return_value=None):
            with self.assertRaises(RuntimeError):
                browser.find_chrome(str(binary))
        with patch.dict(os.environ, {}, clear=True), patch.object(browser.sys, "platform", "linux"), \
                patch.object(browser.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "DECK_CHROME"):
                browser.find_chrome()

    def test_doctor_reports_failure_without_claiming_rendering(self):
        with patch.object(browser, "find_chrome", side_effect=RuntimeError("Unavailable")):
            report = browser.diagnose()
        self.assertIsNone(report["browser"]["path"])
        self.assertEqual(report["browser"]["error"], "Unavailable")
        self.assertIn("real render", report["scope"])


if __name__ == "__main__":
    unittest.main()
