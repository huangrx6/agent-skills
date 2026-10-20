"""配图政策：**只交接，不代生图**。

锁住三件事，防止旧逻辑回流：

1. `image_source.py` 不再提供 `--generate` / `--provider-cmd` / `--prompt` 等出图入口；
2. 脚本里没有内置生图后端、服务名或密钥读取；
3. `image_handoff.py --brief` 明确要求用户用自己的模型生成，且不创建任何图片。

这些检查都不需要浏览器，也不访问网络。
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/deck-authoring/scripts"
IMAGE_SOURCE = SCRIPTS / "image_source.py"
IMAGE_HANDOFF = SCRIPTS / "image_handoff.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(f"_image_policy_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True, text=True, timeout=60,
    )


PLAN = {
    "schemaVersion": 1,
    "project": "政策验证",
    "styleDirection": "纸感、冷灰、低对比，母题为纸张层叠。",
    "images": [{
        "id": "cover", "pages": [1], "file": "assets/images/cover.png",
        "role": "cover", "purpose": "封面主视觉",
        "target_px": [1600, 900], "aspect": "16:9", "fit": "cover",
        "focal": [65, 50],
        "prompt": "Layered paper sheets in cool grey, soft light from upper left.",
        "negative": ["No text, logos or watermark"],
        "alt": "层叠纸张",
    }],
}


class TestNoGenerationEntrypoints(unittest.TestCase):
    def test_generate_flags_are_rejected(self) -> None:
        for argv in (("--generate", "deck.spec.json"),
                     ("--provider-cmd", "my-tool"),
                     ("--prompt", "a cat")):
            result = _run(IMAGE_SOURCE, *argv)
            self.assertNotEqual(result.returncode, 0, argv)
            self.assertIn("unrecognized arguments", result.stderr, argv)

    def test_module_has_no_generation_backend(self) -> None:
        module = _load("source", IMAGE_SOURCE)
        for name in ("generate_images", "resolve", "minimax_key", "cache_key", "cache_dir"):
            self.assertFalse(hasattr(module, name), f"{name} 不应再存在")

    def test_source_has_no_service_or_key_references(self) -> None:
        text = IMAGE_SOURCE.read_text(encoding="utf-8").lower()
        for term in ("minimax", "siliconflow", "images/generations", "--provider-cmd", "--generate"):
            self.assertNotIn(term, text, f"生成逻辑残留：{term}")


class TestSkillPolicy(unittest.TestCase):
    def test_entry_states_handoff_only(self) -> None:
        text = (ROOT / "skills/deck-authoring/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("不代用户生图（硬约束）", text)
        self.assertIn("配图只交接、不代生", text)
        for stale in ("有生图能力就按本版提示词生成", "能生成就生成", "先自己生成或从可授权素材站获取"):
            self.assertNotIn(stale, text)

    def test_image_reference_has_no_self_generation_workflow(self) -> None:
        text = (ROOT / "skills/deck-authoring/references/images.md").read_text(encoding="utf-8")
        self.assertIn("先写交接清单，不代生图", text)
        self.assertIn("image_source.py --brief", text)
        for stale in ("自己生成时的做法", "--generate", "--provider-cmd", "MINIMAX_API_KEY"):
            self.assertNotIn(stale, text)


class TestBriefHandsOffToUser(unittest.TestCase):
    def test_brief_is_addressed_to_the_user_and_creates_no_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "image-plan.json"
            plan.write_text(json.dumps(PLAN, ensure_ascii=False), encoding="utf-8")

            result = _run(IMAGE_HANDOFF, "--brief", str(plan))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("尚未生成或改写任何图片", result.stdout)

            brief = (Path(tmp) / "image-brief.md").read_text(encoding="utf-8")
            self.assertIn("请用你自己的模型", brief)
            self.assertIn("输出规格：1600 × 900 px", brief)
            self.assertFalse((Path(tmp) / "assets/images/cover.png").exists())

    def test_missing_image_blocks_the_handoff_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "image-plan.json"
            plan.write_text(json.dumps(PLAN, ensure_ascii=False), encoding="utf-8")
            result = _run(IMAGE_HANDOFF, "--check", str(plan))
            self.assertEqual(result.returncode, 1)
            self.assertIn("cover.png", result.stdout)


if __name__ == "__main__":
    unittest.main()
