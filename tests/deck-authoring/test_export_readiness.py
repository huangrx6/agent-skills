"""真实浏览器验导出时机：资源延迟必须等待，资源失败必须拒绝交付。"""
from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image

SCRIPT = Path(__file__).resolve().parents[2] / "skills/deck-authoring/scripts/animate.py"
spec = importlib.util.spec_from_file_location("export_readiness_animate", SCRIPT)
animate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = animate
spec.loader.exec_module(animate)


@unittest.skipUnless(Path(animate.CHROME).is_file(), "需要 Chrome")
class ExportReadiness(unittest.TestCase):
    def test_capture_waits_for_delayed_chart_promise(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "delayed.html"
            source.write_text('''<html><head><style>html,body{margin:0}</style></head><body>
              <div class="g2" data-g2="{}"><canvas></canvas></div><script>
              let ready=false;
              window.__deck_charts_ready=new Promise(resolve=>setTimeout(()=>{
                ready=true;document.querySelector('.g2').setAttribute('data-chart-ready','1');resolve();
              },500));
              window.__deck={seek:function(){document.body.style.background=ready?'#ff0000':'#0000ff';}};
              </script></body></html>''')
            frames = asyncio.run(animate._capture_async(str(source), tmp, [0], 1))
            with Image.open(frames[0]) as image:
                self.assertEqual(image.convert("RGB").getpixel((1200, 700)), (255, 0, 0))

    def test_broken_image_rejects_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "broken.html"
            source.write_text('<html><body><img src="missing.png">'
                              '<script>window.__deck={seek:function(){}};</script></body></html>')
            with self.assertRaisesRegex(SystemExit, "资源加载失败"):
                asyncio.run(animate._capture_async(str(source), tmp, [0], 1))
            self.assertFalse((Path(tmp) / "f00000.png").exists())


if __name__ == "__main__":
    unittest.main()
