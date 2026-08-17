#!/usr/bin/env python3
"""visual-ui-layout-spec Skill 脚本测试。

运行：uv run python -m unittest discover -s scripts/tests
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = SKILL_ROOT / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import visual_runtime as vr  # noqa: E402
import validate_layout_spec as vlayout  # noqa: E402


def write_json(p, obj):
    Path(p).write_text(json.dumps(obj), encoding='utf-8')


def run_uv(script, args, timeout=120):
    return subprocess.run(
        ['uv', 'run', f'scripts/{script}'] + list(args),
        capture_output=True, text=True, cwd=str(SKILL_ROOT), timeout=timeout,
    )


# ---------- visual_runtime 单元测试（共享逻辑）----------



class ExtractJsonTextTest(unittest.TestCase):
    def test_plain_and_fenced(self):
        self.assertEqual(vr.extract_json_text('{"a":1}'), {'a': 1})
        self.assertEqual(vr.extract_json_text('```\n{"a":1}\n```'), {'a': 1})
        self.assertIsNone(vr.extract_json_text('bad'))


class NormalizeResultTest(unittest.TestCase):
    """normalize_result 确保输出对齐 schema。"""
    def test_bbox_normalized_01(self):
        out = vr.normalize_result({'objects': [{'id': 1, 'bbox': [0.1, 0.2, 0.3, 0.4]}]}, width=1000, height=500)
        self.assertEqual(out['objects'][0]['bbox'], {'x': 100, 'y': 100, 'width': 300, 'height': 200})
        self.assertEqual(out['objects'][0]['id'], '1')

    def test_bbox_polygon_and_pixel(self):
        # 多边形→最小外接矩形
        out = vr.normalize_result({'objects': [{'id': 'O1', 'bbox': [[0, 0], [100, 0], [100, 50], [0, 50]]}]}, width=100, height=50)
        self.assertEqual(out['objects'][0]['bbox'], {'x': 0, 'y': 0, 'width': 100, 'height': 50})
        # 画布内整数像素不误归一化
        out2 = vr.normalize_result({'objects': [{'id': 'O1', 'bbox': [100, 100, 300, 200]}]}, width=1000, height=500)
        self.assertEqual(out2['objects'][0]['bbox'], {'x': 100, 'y': 100, 'width': 300, 'height': 200})

    def test_fills_missing_fields(self):
        out = vr.normalize_result({'image_type': 'SCREENSHOT_UI'}, width=1440, height=900)
        self.assertEqual(out['image']['type'], 'SCREENSHOT_UI')
        self.assertEqual(out['degradation'], {'degraded': False})
        for k in ('regions', 'components', 'objects', 'relations'):
            pass  # 仅确认不崩
        self.assertEqual(out['relations'], [])

    def test_vlm_wrong_canvas_overridden_by_real_size(self):
        """VLM 自报画布被真实原图尺寸覆盖（bbox 坐标系一致）。"""
        raw = {'image': {'width': 1920, 'height': 1280, 'type': 'PHOTO'},
               'objects': [{'id': 'O1', 'bbox': [0.5, 0.5, 0.2, 0.1], 'confidence': 0.9}]}
        out = vr.normalize_result(raw, width=2358, height=1734)
        self.assertEqual(out['image']['width'], 2358)
        self.assertEqual(out['objects'][0]['bbox'], {'x': 1179, 'y': 867, 'width': 472, 'height': 173})


# ---------- validate_layout_spec 单元测试 ----------

class ValidateLayoutSpecLogicTest(unittest.TestCase):
    def _doc(self, extra=''):
        parts = ['# Title']
        for n in range(1, 11):
            parts.append(f'## §{n} content')
        parts.append('Evidence Ledger')
        return '\n\n'.join(parts) + extra

    def test_valid_passes(self):
        self.assertEqual(vlayout.check_layout_spec(self._doc()), [])

    def test_missing_section(self):
        errs = vlayout.check_layout_spec('# T\n## §1\n')
        self.assertTrue(any('§2' in e for e in errs))

    def test_placeholder_outside_fence(self):
        errs = vlayout.check_layout_spec(self._doc('\n\nTODO XXX 待补充'))
        self.assertTrue(any('占位符' in e for e in errs))

    def test_json_inside_fence_not_flagged(self):
        doc = self._doc('\n\n```json\n{"width": 100}\n```\n')
        self.assertEqual(vlayout.check_layout_spec(doc), [])


# ---------- 脚本端到端 ----------

class ScriptsE2ETest(unittest.TestCase):
    def test_validate_skill_assets_passes(self):
        r = run_uv('validate_skill_assets.py', ['.'])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('校验通过', r.stdout)

    def test_validate_layout_spec_example_passes(self):
        r = run_uv('validate_layout_spec.py', ['examples/orders-page.example.md'])
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_validate_layout_spec_missing_exit2(self):
        r = run_uv('validate_layout_spec.py', ['/no/such.md'])
        self.assertEqual(r.returncode, 2)

    def test_image_probe_all_commands(self):
        gen = subprocess.run(['uv', 'run', '--with', 'pillow', 'python', '-c',
                              "from PIL import Image, ImageDraw; im=Image.new('RGB',(200,200),'white'); "
                              "d=ImageDraw.Draw(im); d.rectangle([20,20,180,80],fill=(0,120,215)); "
                              "d.rectangle([20,120,180,180],fill=(200,200,200)); im.save('/tmp/ip_test.png')"],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(gen.returncode, 0, gen.stderr)
        for cmd, args in [('info', ['--json']), ('quality', ['--json']),
                          ('bands', ['--axis', 'both', '--json']), ('runs', ['--row', '100', '--json']),
                          ('palette', ['--colors', '4']), ('pick', ['--points', '50,50'])]:
            r = run_uv('image_probe.py', [cmd, '/tmp/ip_test.png'] + args)
            self.assertEqual(r.returncode, 0, f"{cmd}: {r.stderr}")
        # grid + crop 生成文件
        run_uv('image_probe.py', ['grid', '/tmp/ip_test.png', '--out', '/tmp/ip_g.png'])
        self.assertTrue(Path('/tmp/ip_g.png').is_file())
        run_uv('image_probe.py', ['crop', '/tmp/ip_test.png', '--box', '0,0,50,50', '--out', '/tmp/ip_c.png'])
        self.assertTrue(Path('/tmp/ip_c.png').is_file())

    def test_image_probe_missing_exit1(self):
        r = run_uv('image_probe.py', ['info', '/no/such.png', '--json'])
        self.assertEqual(r.returncode, 1)


if __name__ == '__main__':
    unittest.main()
