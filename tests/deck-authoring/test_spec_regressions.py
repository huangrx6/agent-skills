"""Input errors must fail before content can be lost or rendered differently."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parents[1] / "skills" / "deck-authoring" / "scripts"
loader = importlib.util.spec_from_file_location("spec_regression_validator", SCRIPTS / "validate_spec.py")
vs = importlib.util.module_from_spec(loader)
loader.loader.exec_module(vs)


def deck(slide):
    return {"deck": {"style": "local", "colorSet": "blue", "slides": [slide]}}


class InputIntegrity(unittest.TestCase):
    def errors(self, slide):
        return vs.validate(deck(slide)).errors

    def test_wrong_types_are_diagnostics_not_tracebacks(self):
        for change in ({"type": {}}, {"title": None}, {"bullets": "abc"},
                       {"bullets": [None]}, {"bullets": [12]}):
            with self.subTest(change=change):
                self.assertTrue(self.errors({"type": "content-text", "title": "T", "bullets": ["a"], **change}))

    def test_columns_must_never_be_truncated(self):
        columns = [{"title": str(i), "bullets": [str(i)]} for i in range(3)]
        self.assertTrue(self.errors({"type": "two-column", "title": "T", "columns": columns}))

    def test_chart_ratio_and_intent_are_validated(self):
        base = {"type": "chart", "title": "T", "chart": "bar", "data": [{"label": "A", "value": 1}]}
        for change in ({"visual": {"kind": "data"}}, {"visual": {"kind": "data", "ratio": "0:0"}}, {"intent": "typo"}):
            with self.subTest(change=change):
                self.assertTrue(self.errors({**base, **change}))

    def test_nested_series_contract_and_finite_numbers(self):
        base = {"type": "chart", "title": "T", "chart": "line"}
        for row in ({"label": "A", "value": float("nan")}, {"label": "A", "value": float("inf")},
                    {"label": "A", "value": True}, {"label": "A", "value": 2, "fontSize": 100}):
            with self.subTest(row=row):
                self.assertTrue(self.errors({**base, "series": [{"name": "A", "data": [row]}]}))

    def test_data_and_series_cannot_compete(self):
        rows = [{"label": "Q1", "value": 1}]
        self.assertTrue(self.errors({"type": "chart", "title": "T", "chart": "line", "data": rows,
                                     "series": [{"name": "A", "data": rows}]}))

    def test_combo_requires_explicit_marks(self):
        series = [{"name": "A", "mark": "bar", "data": [{"label": "Q1", "value": 2}]},
                  {"name": "B", "mark": "line", "data": [{"label": "Q1", "value": 3}]}]
        slide = {"type": "chart", "title": "T", "chart": "combo", "series": series}
        self.assertEqual(self.errors(slide), [])
        slide = copy.deepcopy(slide)
        del slide["series"][0]["mark"]
        self.assertTrue(self.errors(slide))

    def test_unimplemented_annotations_fail_explicitly(self):
        self.assertTrue(self.errors({"type": "chart", "title": "T", "chart": "bar",
                                     "data": [{"label": "A", "value": 1}],
                                     "annotations": [{"type": "reference", "value": 2}]}))

    def test_scatter_coordinates_and_donut_total(self):
        self.assertEqual(self.errors({"type": "chart", "title": "T", "chart": "scatter",
                                      "data": [{"label": "A", "x": 1, "y": 2}]}), [])
        for value in (-1, 0):
            self.assertTrue(self.errors({"type": "chart", "title": "T", "chart": "donut",
                                         "data": [{"label": "A", "value": value}]}))


class ProjectThemeCLI(unittest.TestCase):
    def test_project_style_and_brand_are_resolved_from_other_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            shutil.copytree(HERE / "fixtures/styles/minimal-baseline", project / "styles/local")
            brand = project / "brands/company"
            brand.mkdir(parents=True)
            (brand / "brand.json").write_text(json.dumps({"version": 1, "label": "Company", "logoOn": "none",
                "colorSets": {"brand-only": {"primary": "#123456", "secondary": "#111111",
                    "background": "#FFFFFF", "text": "#111111"}}}))
            spec = deck({"type": "title", "title": "T"})
            spec["deck"]["brand"] = "company"
            path = project / "deck.json"
            env = {k: v for k, v in os.environ.items() if k not in ("DECK_STYLES", "DECK_BRANDS")}
            for name, expected in (("brand-only", 0), ("missing", 1)):
                with self.subTest(name=name):
                    spec["deck"]["colorSet"] = name
                    path.write_text(json.dumps(spec))
                    proc = subprocess.run([sys.executable, str(SCRIPTS / "validate_spec.py"), str(path), "--json"],
                                          cwd="/tmp", env=env, text=True, capture_output=True)
                    self.assertEqual(proc.returncode, expected, proc.stdout + proc.stderr)
                    result = json.loads(proc.stdout)
                    self.assertEqual(bool(result["error_count"]), bool(expected))


if __name__ == "__main__":
    unittest.main()
