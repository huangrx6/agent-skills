"""External generation handoff works without a renderer or image backend."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/deck-authoring/scripts/image_handoff.py"
spec = importlib.util.spec_from_file_location("image_handoff_test", SCRIPT)
handoff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handoff)


def example():
    return {"schemaVersion": 1, "project": "Neutral demonstration", "images": [{
        "id": "opening", "pages": [1, 4], "file": "assets/images/opening.png",
        "role": "concept illustration", "purpose": "Introduce an idea without illustrating factual data",
        "target_px": [600, 400], "aspect": "3:2", "fit": "cover", "focal": [70, 50],
        "prompt": ("A single translucent glass sphere resting on warm paper, positioned in the right third. "
                   "Soft side lighting from the upper left, restrained editorial still-life photography. "
                   "Leave the left half quiet and free of objects for a title added later as live text."),
        "negative": ["No text, numbers, watermark, logos or decorative borders."],
        "alt": "A translucent sphere with a soft shadow on paper",
    }]}


class TestImageHandoff(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.planfile = self.root / "image-plan.json"
        self.data = example()

    def plan(self, data=None):
        self.planfile.write_text(json.dumps(data or self.data, ensure_ascii=False), encoding="utf-8")
        return handoff.load_plan(self.planfile)

    def image(self, size=(600, 400), format="PNG", filename="assets/images/opening.png"):
        target = self.root / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, "#e8e4da").save(target, format=format)
        return target

    def test_complete_handoff_is_route_independent_and_creates_no_images(self):
        plan = self.plan()
        document = handoff.write_brief(plan)
        text = document.read_text(encoding="utf-8")
        for expected in ("assets/images/opening.png", "第 1, 4 页", "600 × 400", "3:2",
                         "不改 HTML，不做接入步骤", "缺图时只显示空白占位框",
                         self.data["images"][0]["prompt"], self.data["images"][0]["negative"][0],
                         "object-position: 70% 50%", "替代文本", "输出规格：600 × 400 px（3:2）"):
            self.assertIn(expected, text)
        self.assertFalse((self.root / "assets").exists())
        self.assertEqual(self.data, json.loads(self.planfile.read_text()))

    def test_brief_never_overwrites_manual_edits(self):
        plan = self.plan()
        document = handoff.write_brief(plan)
        document.write_text("An edited prompt owned by the user.")
        with self.assertRaisesRegex(handoff.PlanError, "不覆盖"):
            handoff.write_brief(plan)
        self.assertEqual(document.read_text(), "An edited prompt owned by the user.")
        new_document = handoff.write_brief(plan, "briefs/round-two.md")
        self.assertTrue(new_document.is_file())

    def test_missing_empty_or_placeholder_prompt_is_not_a_ready_brief(self):
        for prompt in (None, "", "TODO: write the full prompt for this image.",
                       "A calm editorial photograph of 〈subject〉 on a paper background, softly lit.",
                       "A calm editorial photograph of {{subject}} on a paper background, softly lit.",
                       "A calm editorial photograph of <subject> on a paper background, softly lit.",
                       "A calm editorial photograph of [insert subject] on a paper background, softly lit."):
            data = example()
            data["images"][0]["prompt"] = prompt
            with self.subTest(prompt=prompt), self.assertRaises(handoff.PlanError):
                self.plan(data)
        self.assertFalse((self.root / "image-brief.md").exists())

    def test_requires_meaningful_contract_fields_and_real_page_numbers(self):
        variants = [({"pages": []}), ({"pages": [1, 1]}), ({"pages": [True]}), ({"pages": [0]}),
                    ({"negative": None}), ({"negative": ["TODO"]}), ({"role": ""}), ({"purpose": None}),
                    ({"alt": ""}), ({"target_px": [True, 400]}), ({"target_px": [0, 400]}),
                    ({"target_px": [600]}), ({"fit": "stretch"}), ({"focal": [101, 0]}),
                    ({"focal": [float("nan"), 50]})]
        for changes in variants:
            data = example()
            data["images"][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(handoff.PlanError):
                self.plan(data)

    def test_concise_prompt_does_not_require_arbitrary_length_or_negative_list(self):
        self.data["images"][0]["prompt"] = "一枚半透明橙色玻璃片，位于画面右侧，柔光，透明背景。"
        del self.data["images"][0]["negative"]
        plan = self.plan()
        self.assertEqual(plan["images"][0]["negative"], [])
        self.assertIn(self.data["images"][0]["prompt"], handoff.write_brief(plan).read_text())

    def test_transparency_is_verified_from_pixels_and_safe_area_reaches_brief(self):
        self.data["images"][0].update(transparent=True, negativeSpace="左侧 40% 保持低细节")
        plan = self.plan()
        target = self.image()
        self.assertFalse(handoff.check_images(plan)["ready"])
        with Image.open(target) as source:
            cutout = source.convert("RGBA")
        cutout.putpixel((0, 0), (0, 0, 0, 0))
        cutout.save(target)
        self.assertTrue(handoff.check_images(plan)["ready"])
        opaque_plan = copy.deepcopy(plan)
        opaque_plan["images"][0]["transparent"] = False
        self.assertFalse(handoff.check_images(opaque_plan)["ready"])
        brief = handoff.write_brief(plan).read_text()
        # The generation spec carries the measured slot size into the copied prompt.
        self.assertIn("输出规格：600 × 400 px（3:2）", brief)
        self.assertIn("不裁切、不拉伸、不加白边", brief)
        self.assertIn("左侧 40% 保持低细节", brief)
        self.assertIn("alpha 通道", brief)
        Image.new("RGBA", (600, 400), (0, 0, 0, 0)).save(target)
        self.assertFalse(handoff.check_images(plan)["ready"])

    def test_invalid_transparency_contract_fails_before_generation(self):
        for changes in ({"transparent": "true"}, {"transparent": True, "file": "assets/a.jpg"},
                        {"negativeSpace": ""}):
            data = example()
            data["images"][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(handoff.PlanError):
                self.plan(data)

    def test_validates_schema_and_duplicate_asset_identity(self):
        for data in ({}, [], {"schemaVersion": True, "images": []}, {"schemaVersion": 1, "images": []}):
            self.planfile.write_text(json.dumps(data))
            with self.subTest(data=data), self.assertRaises(handoff.PlanError):
                handoff.load_plan(self.planfile)
        duplicate = example()
        duplicate["images"].append(copy.deepcopy(duplicate["images"][0]))
        with self.assertRaisesRegex(handoff.PlanError, "唯一"):
            self.plan(duplicate)
        duplicate["images"][1]["id"] = "different"
        with self.assertRaisesRegex(handoff.PlanError, "重复"):
            self.plan(duplicate)

    def test_derives_aspect_but_rejects_contradictory_geometry(self):
        del self.data["images"][0]["aspect"]
        self.assertEqual(self.plan()["images"][0]["aspect"], "3:2")
        for aspect in ("16:9", "0:1", "3:0", "wide", 1.5):
            self.data["images"][0]["aspect"] = aspect
            with self.subTest(aspect=aspect), self.assertRaises(handoff.PlanError):
                self.plan()

    def test_blocks_absolute_windows_traversal_and_nonimage_targets(self):
        for filename in ("/tmp/opening.png", "../opening.png", "assets/../../opening.png",
                         "C:\\images\\opening.png", "https://example.test/image.png", "assets//image.png",
                         "assets/./image.png", "assets/image.svg", "assets/image.png\n"):
            self.data["images"][0]["file"] = filename
            with self.subTest(filename=filename), self.assertRaises(handoff.PlanError):
                self.plan()

    def test_rejects_image_and_document_symlink_escapes(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.root / "external").symlink_to(outside, target_is_directory=True)
            self.data["images"][0]["file"] = "external/opening.png"
            with self.assertRaisesRegex(handoff.PlanError, "逃逸"):
                self.plan()
            plan = self.plan(example())
            with self.assertRaisesRegex(handoff.PlanError, "逃逸"):
                handoff.write_brief(plan, "external/image-brief.md")
            self.assertEqual(list(Path(outside).iterdir()), [])

    def test_rechecks_paths_after_plan_loading(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as outside:
            (self.root / "assets").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(handoff.PlanError, "逃逸"):
                handoff.check_images(plan)

    def test_internal_symlink_cannot_hide_wrong_extension(self):
        self.image()
        (self.root / "assets/images/renamed.jpg").symlink_to("opening.png")
        self.data["images"][0]["file"] = "assets/images/renamed.jpg"
        report = handoff.check_images(self.plan())
        self.assertFalse(report["ready"])
        self.assertIn("后缀要求 JPEG，真实内容为 PNG", report["assets"][0]["errors"][0])

    def test_output_cannot_replace_plan_or_asset_or_leave_project(self):
        plan = self.plan()
        for out in ("image-plan.json", "assets/images/opening.png", "../image-brief.md", "/tmp/image-brief.md"):
            with self.subTest(out=out), self.assertRaises(handoff.PlanError):
                handoff.write_brief(plan, out)
        self.assertEqual(json.loads(self.planfile.read_text()), self.data)

    def test_missing_files_fail_without_readiness_from_plan_status(self):
        self.data["images"][0]["status"] = "ready"
        report = handoff.check_images(self.plan())
        self.assertFalse(report["ready"])
        self.assertEqual(report["assets"][0]["status"], "pending")
        self.assertIn("文件缺失", report["assets"][0]["errors"][0])

    def test_valid_file_passes_and_reports_real_dimensions(self):
        self.image()
        result = handoff.check_images(self.plan())
        self.assertTrue(result["ready"])
        self.assertEqual(result["assets"][0]["actual_px"], [600, 400])
        self.assertEqual(result["assets"][0]["status"], "ready")
        self.assertIn("仍需", result["review_required"])

    def test_corrupt_files_and_extension_disguises_fail(self):
        target = self.image(format="JPEG")
        report = handoff.check_images(self.plan())
        self.assertFalse(report["ready"])
        self.assertIn("真实内容为 JPEG", report["assets"][0]["errors"][0])
        target.write_text("This is not an image.")
        report = handoff.check_images(self.plan())
        self.assertEqual(report["assets"][0]["status"], "invalid")
        self.assertIn("不能安全解码", report["assets"][0]["errors"][0])

    def test_low_resolution_is_blocking_for_cover(self):
        self.image(size=(300, 200))
        report = handoff.check_images(self.plan())
        self.assertFalse(report["ready"])
        self.assertIn("放大 2.00 倍", report["assets"][0]["errors"][0])

    def test_contain_does_not_require_unused_canvas_pixels(self):
        self.image(size=(600, 200))
        self.data["images"][0]["fit"] = "contain"
        report = handoff.check_images(self.plan())
        self.assertTrue(report["ready"])
        self.assertIn("50.0% 图位留边", report["assets"][0]["warnings"][0])
        self.data["images"][0]["fit"] = "cover"
        report = handoff.check_images(self.plan())
        self.assertFalse(report["ready"])
        self.assertIn("50.0% 图像面积", report["assets"][0]["warnings"][0])

    def test_aspect_mismatch_warns_without_rejecting_valid_cover(self):
        self.image(size=(800, 800))
        report = handoff.check_images(self.plan())
        self.assertTrue(report["ready"])
        self.assertIn("裁掉 33.3%", report["assets"][0]["warnings"][0])

    def test_exif_orientation_controls_effective_dimensions(self):
        self.data["images"][0]["file"] = "assets/images/opening.jpg"
        target = self.image(size=(400, 600), format="JPEG", filename="assets/images/opening.jpg")
        with Image.open(target) as original:
            exif = original.getexif()
            exif[274] = 6
            original.save(target, exif=exif)
        report = handoff.check_images(self.plan())
        self.assertTrue(report["ready"])
        self.assertEqual(report["assets"][0]["actual_px"], [600, 400])

    def test_animated_images_are_not_silently_accepted_as_stills(self):
        target = self.image()
        first = Image.new("RGB", (600, 400), "red")
        first.save(target, save_all=True, append_images=[Image.new("RGB", (600, 400), "blue")], duration=100)
        report = handoff.check_images(self.plan())
        self.assertFalse(report["ready"])
        self.assertIn("单帧静态图", report["assets"][0]["errors"][0])

    def test_literal_markdown_in_prompts_cannot_close_generated_fence(self):
        self.data["images"][0]["prompt"] += "\n```\nLiteral markdown used as a visual reference."
        document = handoff.write_brief(self.plan())
        self.assertIn("````text\n", document.read_text())

    def test_cli_pending_then_manual_fill_then_ready_and_preserves_brief(self):
        self.plan()
        command = [sys.executable, str(SCRIPT)]
        first = subprocess.run(command + ["--brief", str(self.planfile)], capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        pending = subprocess.run(command + ["--check", str(self.planfile)], capture_output=True, text=True)
        self.assertEqual(pending.returncode, 1, pending.stderr)
        self.assertFalse(json.loads(pending.stdout)["ready"])
        self.image()
        ready = subprocess.run(command + ["--check", str(self.planfile)], capture_output=True, text=True)
        self.assertEqual(ready.returncode, 0, ready.stderr)
        self.assertTrue(json.loads(ready.stdout)["ready"])
        before = (self.root / "image-brief.md").read_bytes()
        repeat = subprocess.run(command + ["--brief", str(self.planfile)], capture_output=True, text=True)
        self.assertEqual(repeat.returncode, 2)
        self.assertEqual((self.root / "image-brief.md").read_bytes(), before)

    def html(self, markup=None, filename="source.html"):
        markup = markup or handoff.image_markup(self.plan()["images"][0])
        target = self.root / filename
        target.write_text('<html><body>' + ''.join(
            f'<section class="slide" data-slide="{page}">{markup}</section>'
            for page in (1, 4)) + '</body></html>', encoding="utf-8")
        return target

    def test_generated_snippet_reserves_space_and_escapes_resource_and_alt(self):
        self.data["images"][0].update(file="assets/images/a #中.png", alt='A < B & "C"')
        plan = self.plan()
        markup = handoff.image_markup(plan["images"][0])
        self.assertIn('width="600" height="400"', markup)
        self.assertIn('aspect-ratio:600/400', markup)
        self.assertIn('a%20%23%E4%B8%AD.png', markup)
        self.assertIn('A &lt; B &amp; &quot;C&quot;', markup)
        self.assertTrue(handoff.check_bindings(plan, self.html(markup))["ready"])

    def test_bindings_and_files_are_independent_until_both_pass(self):
        plan = self.plan()
        path = self.html()
        self.assertTrue(handoff.check_bindings(plan, path)["ready"])
        command = [sys.executable, str(SCRIPT), "--check", str(self.planfile), "--html", str(path)]
        missing = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(missing.returncode, 1, missing.stderr)
        report = json.loads(missing.stdout)
        self.assertTrue(report["bindings"]["ready"])
        self.assertFalse(report["files_ready"])
        self.image()
        ready = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(ready.returncode, 0, ready.stderr)
        self.assertTrue(json.loads(ready.stdout)["ready"])

    def test_ready_files_cannot_hide_missing_or_wrong_page_hookups(self):
        self.image()
        plan = self.plan()
        for markup in ('<p>No image yet</p>', '<img data-image-id="opening" src="wrong.png">',
                       '<img data-image-id="unknown" src="assets/images/opening.png">',
                       '<img src="assets/images/opening.png" srcset="other.png 2x">',
                       '<picture><source srcset="other.png"><img src="assets/images/opening.png"></picture>'):
            with self.subTest(markup=markup):
                self.assertFalse(handoff.check_bindings(plan, self.html(markup))["ready"])
        path = self.html()
        path.write_text(path.read_text().replace('data-slide="4"', 'data-slide="2"'))
        report = handoff.check_bindings(plan, path)
        self.assertFalse(report["ready"])
        self.assertIn("[4]", str(report["errors"]))
        self.assertIn("[2]", str(report["errors"]))

    def test_nested_sections_and_relative_paths_match_without_required_id(self):
        plan = self.plan()
        (self.root / "preview").mkdir()
        path = self.html('<section><img src="../assets/images/opening.png?v=2"></section>', "preview/deck.html")
        self.assertTrue(handoff.check_bindings(plan, path)["ready"])
        path.write_text('<base href="https://example.test/">' + path.read_text())
        self.assertFalse(handoff.check_bindings(plan, path)["ready"])

    def test_brief_reports_unwired_and_preserves_html(self):
        plan = self.plan()
        path = self.html("<p>Still unwired</p>")
        original = path.read_bytes()
        with self.assertRaises(handoff.PlanError):
            handoff.write_brief(plan, "source.html", path)
        document = handoff.write_brief(plan, html_path=path).read_text()
        self.assertIn("尚未接好", document)
        self.assertIn('data-image-id="opening"', document)
        self.assertEqual(original, path.read_bytes())

    def test_handoff_accepts_pending_images_but_requires_real_document_and_bindings(self):
        plan = self.plan()
        path = self.html()
        self.assertFalse(handoff.check_handoff(plan, path)["ready"])
        document = handoff.write_brief(plan, html_path=path)
        result = handoff.check_handoff(plan, path)
        self.assertTrue(result["ready"], result)
        self.assertFalse(result["files_ready"])
        self.assertEqual(result["pending_images"], ["opening"])
        self.assertFalse((self.root / "assets").exists())
        path.write_text(path.read_text().replace("assets/images/opening.png", "assets/images/wrong.png"))
        self.assertFalse(handoff.check_handoff(plan, path)["ready"])
        self.assertTrue(document.exists())

    def test_handoff_rejects_stale_or_incomplete_markdown_and_accepts_new_version(self):
        plan = self.plan()
        path = self.html()
        document = handoff.write_brief(plan)
        original = document.read_text()
        document.write_text(original.replace(plan["images"][0]["prompt"], ""))
        self.assertFalse(handoff.check_handoff(plan, path)["ready"])
        document.write_text(original)
        self.data["images"][0]["purpose"] = "A revised purpose for a different composition"
        revised = self.plan()
        self.assertFalse(handoff.check_handoff(revised, path)["ready"])
        handoff.write_brief(revised, "briefs/v2.md", path)
        self.assertTrue(handoff.check_handoff(revised, path, "briefs/v2.md")["ready"])
        self.assertEqual(document.read_text(), original)

    def test_provided_images_need_no_generation_prompt_but_must_exist_for_handoff(self):
        self.data["images"][0].update(source="provided", source_note="用户提供的真实流程截图")
        del self.data["images"][0]["prompt"]
        plan = self.plan()
        path = self.html()
        document = handoff.write_brief(plan)
        self.assertIn("复用来源（无需生成）", document.read_text())
        self.assertNotIn("可直接复制的完整提示词", document.read_text())
        self.assertFalse(handoff.check_handoff(plan, path)["ready"])
        self.image()
        self.assertTrue(handoff.check_handoff(plan, path)["ready"])
        self.data["images"][0]["source_note"] = ""
        with self.assertRaises(handoff.PlanError):
            self.plan()

    def test_handoff_cli_requires_html_and_reports_pending_separately(self):
        plan = self.plan()
        path = self.html()
        handoff.write_brief(plan)
        command = [sys.executable, str(SCRIPT), "--handoff", str(self.planfile)]
        missing_html = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(missing_html.returncode, 2)
        result = subprocess.run(command + ["--html", str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ready"])
        self.assertFalse(json.loads(result.stdout)["files_ready"])

    def test_compiler_handoff_gate_preserves_output_until_document_and_slots_are_ready(self):
        plan = self.plan()
        # The standalone binding checker accepts nonconsecutive pages; the compiler does not.
        self.data["images"][0]["pages"] = [1]
        plan = self.plan()
        source = self.root / "source.html"
        source.write_text('<!doctype html><html><head><title>Handoff</title></head><body>'
                          '<section class="slide" data-slide="1" data-title="One">'
                          + handoff.image_markup(plan["images"][0]) + '</section></body></html>')
        output = self.root / "deck.html"
        output.write_text("previous deliverable")
        command = [sys.executable, str(SCRIPT.with_name("web_deck.py")), str(source), "-o", str(output),
                   "--image-plan", str(self.planfile)]
        missing_md = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(missing_md.returncode, 0)
        self.assertEqual(output.read_text(), "previous deliverable")
        handoff.write_brief(plan, html_path=source)
        passed = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(passed.returncode, 0, passed.stderr)
        self.assertIn('name="deck-web-runtime"', output.read_text())
        self.assertIn("占位待回填", passed.stdout)
        before = output.read_bytes()
        source.write_text(source.read_text().replace("assets/images/opening.png", "assets/images/wrong.png"))
        wrong_path = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(wrong_path.returncode, 0)
        self.assertEqual(output.read_bytes(), before)

    def test_compiler_cannot_overwrite_handoff_inputs(self):
        self.data["images"][0]["pages"] = [1]
        plan = self.plan()
        source = self.root / "source.html"
        source.write_text('<html><head></head><body><section class="slide" data-slide="1" data-title="One">'
                          + handoff.image_markup(plan["images"][0]) + '</section></body></html>')
        document = handoff.write_brief(plan, html_path=source)
        for target in (self.planfile, document, self.root / plan["images"][0]["file"]):
            before = target.read_bytes() if target.exists() else None
            command = [sys.executable, str(SCRIPT.with_name("web_deck.py")), str(source), "-o", str(target),
                       "--image-plan", str(self.planfile)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("overwrite", result.stderr)
            self.assertEqual(target.read_bytes() if target.exists() else None, before)


if __name__ == "__main__":
    unittest.main()
