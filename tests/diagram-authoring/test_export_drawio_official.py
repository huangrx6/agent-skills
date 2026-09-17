#!/usr/bin/env python3
"""`dev-tools/export_drawio.py`（draw.io 官方命令行导出的封装）的测试。

**不需要装 draw.io** —— 这些用例守的是"没装的时候必须明确报环境、不能假装成功"，
以及命令行参数拼接（那部分错了，表现是导出出来一张尺寸不对或带白边的图）。

**已实测**（2026-09-17，本机装了 draw.io 31.4.5）：`-x -f png -o out.png -s 2` 出图正确、
`--embed` 真嵌进图、`--crop` 对图片无效、`-t` 被显式底色挡住 —— 三条都进了下面的用例。
这里测的仍然是**封装**（不依赖机器上有没有 draw.io）；"真的能导出"靠实测，
证据在 `references/drawio-backend.md` 第五节。

跑法：
    python3 -m unittest discover -s tests/diagram-authoring -v
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills",
                     os.path.basename(HERE))
TOOL = os.path.join(SKILL, "dev-tools", "export_drawio.py")


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


D = _load("_diagram_export_drawio", TOOL)


class TestCommandLine(unittest.TestCase):
    """官方 CLI 的参数形状。错一个的表现是"导出成功但图不对"。"""

    def test_minimal_command(self):
        cmd = D.build_command("/x/draw.io", "in.drawio", "out.png", "png", 2.0)
        self.assertEqual(["/x/draw.io", "-x", "-f", "png", "-o", "out.png",
                          "-s", "2", "in.drawio"], cmd)

    def test_optional_flags(self):
        cmd = D.build_command("/x/draw.io", "in.drawio", "out.pdf", "pdf", 1.5,
                              transparent=True, crop=True, no_sandbox=True)
        self.assertIn("-t", cmd)
        self.assertIn("--crop", cmd)
        self.assertIn("--no-sandbox", cmd)
        self.assertIn("1.5", cmd)

    def test_embed_and_border_and_size(self):
        """`-e` 嵌入图（产物可再编辑）、`-b` 留白、`--size page` 整页。"""
        cmd = D.build_command("/x/draw.io", "in.drawio", "out.png", "png", 2.0,
                              border=16.0, embed=True, size="page")
        self.assertIn("-e", cmd)
        self.assertEqual("16", cmd[cmd.index("-b") + 1])
        self.assertEqual("page", cmd[cmd.index("--size") + 1])

    def test_diagram_size_is_the_default_and_not_written(self):
        """`diagram` 是官方默认值 —— 不要往命令行里塞废话。"""
        cmd = D.build_command("/x/draw.io", "in.drawio", "out.png", "png", 2.0)
        self.assertNotIn("--size", cmd)

    def test_border_is_converted_to_drawio_units(self):
        """实测 `-b N` 每边只加 0.75×N 图内单位 —— 对外承诺的 16 要换算后再传。"""
        self.assertAlmostEqual(0.75, D.BORDER_TO_DIAGRAM)

    def test_flags_are_absent_unless_asked(self):
        cmd = D.build_command("/x/draw.io", "in.drawio", "out.png", "png", 2.0)
        for flag in ("-t", "--crop", "--no-sandbox"):
            self.assertNotIn(flag, cmd, "默认不该带这些开关")

    def test_source_is_always_last(self):
        """位置参数放在最后：Electron 解析开关到位置参数为止。"""
        cmd = D.build_command("/x/draw.io", "in.drawio", "out.png", "png", 2.0,
                              transparent=True)
        self.assertEqual("in.drawio", cmd[-1])


class TestDefaultBorder(unittest.TestCase):
    """默认留白：用户反馈"内容紧挨边框"之后定的 —— 别退回官方默认 0。"""

    def test_default_border_clears_the_inners_padding_on_the_tightest_side(self):
        """官方把 border 分得不均（实测右/下 ≈0.69×B），所以按**最紧的一边**定默认值。

        实测曲线（scale 2）：`--border 16/32/64` → 右/下 11.5/22/43.5 图内单位。
        图内节点自己的内边距是 22~24 —— 外面比里面还紧就不自然。
        """
        tightest_share = 0.69
        self.assertGreaterEqual(
            D.DEFAULT_BORDER * tightest_share, 24.0,
            "默认留白下最紧的一边不能比图内内边距（22~24）还窄")

    def test_cli_uses_that_default(self):
        """默认值只有一处来源（DEFAULT_BORDER）；命令行要真的带上换算后的 -b。"""
        from types import SimpleNamespace

        seen = []

        def fake_run(cmd, **kwargs):
            seen.append(cmd)
            with open(cmd[cmd.index("-o") + 1], "wb") as fh:
                fh.write(b"\x89PNG\r\n\x1a\n")
            return SimpleNamespace(returncode=0, stdout="exported", stderr="")

        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "x.drawio")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("<mxfile/>")
            out = os.path.join(td, "x.png")
            # ⚠ 先抓真函数再打补丁（反过来的话 cleanup 会把假的恢复回去）
            real_run = D.subprocess.run
            setattr(D.subprocess, "run", fake_run)
            self.addCleanup(setattr, D.subprocess, "run", real_run)
            code = D.main([src, "-o", out, "--binary", sys.executable])
        self.assertEqual(0, code)
        cmd = seen[0]
        self.assertEqual(f"{D.DEFAULT_BORDER / D.BORDER_TO_DIAGRAM:g}",
                         cmd[cmd.index("-b") + 1],
                         "命令行里的 -b 应当是对默认留白换算后的值")


class TestFixedSize(unittest.TestCase):
    """固定宽高：官方 `--width/--height` 原生支持（实测：单边精确、两边=装进框）。

    `--aspect` 在这个后端**故意拒绝** —— 官方只有均匀的 -b，均匀加白只能把比例
    推向 1:1。与其给个对不上的数，不如说清楚并指路。
    """

    def test_width_height_go_on_the_command_line(self):
        cmd = D.build_command("/x/draw.io", "in.drawio", "out.png", "png", 2.0,
                              width=1600, height=900)
        self.assertEqual("1600", cmd[cmd.index("--width") + 1])
        self.assertEqual("900", cmd[cmd.index("--height") + 1])

    def test_only_the_given_side_is_written(self):
        """只给一边就只传一边 —— 另一边由官方按内容比例算。"""
        cmd = D.build_command("/x/draw.io", "in.drawio", "out.png", "png", 2.0,
                              width=1600)
        self.assertIn("--width", cmd)
        self.assertNotIn("--height", cmd)

    def test_bad_sizes_are_refused_not_guessed(self):
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "x.drawio")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("<mxfile/>")
            for kw in ({"width": 0}, {"width": -3}, {"width": "宽"},
                       {"height": "0"}, {"aspect": "16:9"}, {"aspect": "16/9"}):
                got = D.export(src, os.path.join(td, "x.png"), fmt="png", **kw)
                self.assertFalse(got["ok"], kw)
                self.assertEqual("input", got["stage"], kw)

    def test_aspect_refusal_explains_the_reason_and_the_way_out(self):
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "x.drawio")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("<mxfile/>")
            got = D.export(src, os.path.join(td, "x.png"), fmt="png", aspect="16:9")
        self.assertFalse(got["ok"])
        self.assertIn("均匀", got["message"], "要说清为什么做不到")
        self.assertIn("export_excalidraw.py", got["message"], "要给能走的那条路")

    def test_library_default_border_matches_the_cli(self):
        """库调用不该比命令行更容易出贴边图（默认留白只有一处来源）。"""
        import inspect
        self.assertEqual(D.DEFAULT_BORDER,
                         inspect.signature(D.export).parameters["border"].default)

    def test_image_size_is_measured_from_the_file(self):
        import struct
        with tempfile.TemporaryDirectory() as td:
            png = os.path.join(td, "x.png")
            with open(png, "wb") as fh:
                fh.write(b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
                         + struct.pack(">II", 1559, 900) + b"\x08\x06\x00\x00\x00")
            self.assertEqual((1559, 900), D._image_size(png))
            jpg = os.path.join(td, "x.jpg")
            with open(jpg, "wb") as fh:
                fh.write(b"\xff\xd8\xff\xc0" + struct.pack(">H", 17) + b"\x08"
                         + struct.pack(">HH", 725, 1280) + b"\x03")
            self.assertEqual((1280, 725), D._image_size(jpg))
            junk = os.path.join(td, "x.bin")
            with open(junk, "wb") as fh:
                fh.write(b"???")
            self.assertIsNone(D._image_size(junk))

    def test_requested_size_that_the_official_did_not_honour_is_reported(self):
        """实测：`--width X --height Y` 是“装进这个框”，绑定轴精确、另一边更小。

        用户看到的是“我要 1600×900，出来 1559×900” —— 这种事必须进回执。
        """
        import struct
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "x.drawio")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("<mxfile/>")
            out = os.path.join(td, "x.png")

            def fake_run(cmd, **kwargs):
                with open(out, "wb") as fh:
                    fh.write(b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
                             + struct.pack(">II", 1559, 900) + b"\x08\x06\x00\x00\x00")
                return SimpleNamespace(returncode=0, stdout="exported", stderr="")

            real_run = D.subprocess.run
            setattr(D.subprocess, "run", fake_run)
            self.addCleanup(setattr, D.subprocess, "run", real_run)
            got = D.export(src, out, fmt="png", binary=sys.executable,
                           width=1600, height=900)
        self.assertTrue(got["ok"], got.get("message"))
        self.assertEqual({"width": 1559, "height": 900}, got["size"])
        self.assertIn("--width 1600", got.get("note", ""), "差的那一边要说出来")


class TestReceipts(unittest.TestCase):
    """失败一律进回执；没装 draw.io 时必须说清"环境不具备"而不是别的。"""

    def test_missing_binary_reports_environment(self):
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "x.drawio")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("<mxfile/>")
            got = D.export(src, os.path.join(td, "x.png"),
                           binary="/绝对不存在的drawio")
        self.assertFalse(got["ok"])
        self.assertEqual("environment", got["stage"])
        self.assertIn("draw.io", got["message"])
        # 报错里要给出不装也能干的办法（文档里那条人手动导出的路）
        self.assertIn("app.diagrams.net", got["message"])

    def test_unknown_format_is_refused_not_guessed(self):
        """封闭集合：未知格式直接拒绝（与未知 kind 不 fallback 同一条规矩）。"""
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "x.drawio")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("<mxfile/>")
            got = D.export(src, os.path.join(td, "x.webp"), fmt="webp")
        self.assertFalse(got["ok"])
        self.assertEqual("input", got["stage"])
        for fmt in D.FORMATS:
            self.assertIn(fmt, got["message"], "报错要列出可用格式")

    def test_crop_on_an_image_is_refused_not_silently_ignored(self):
        """`--crop` 是 PDF 专用的（官方原话）；对图片传它是**静默无效** —— 必须报错。

        这条是实测出来的：`--crop` 出来的 PNG 与不加它的**字节完全相同**。
        """
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "x.drawio")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write('<mxfile><diagram><mxGraphModel background="#FFFFFF"/>'
                         "</diagram></mxfile>")
            got = D.export(src, os.path.join(td, "x.png"), fmt="png", crop=True,
                           binary=sys.executable)
        self.assertFalse(got["ok"])
        self.assertEqual("input", got["stage"])
        self.assertIn("--size page", got["message"], "报错要给出正确写法")

    def test_transparency_on_a_file_with_its_own_background_is_explained(self):
        """我们 emit 的 .drawio 写了显式底色，`-t` 去不掉它 —— 要在回执里说清楚。

        不静默：否则你拿到一份"以为透明其实不透明"的图。
        （用假的 subprocess 造一次"导出成功"，这样测的是回执而不是环境。）
        """
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "x.drawio")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write('<mxfile><diagram><mxGraphModel background="#FFFFFF"/>'
                         "</diagram></mxfile>")
            out = os.path.join(td, "x.png")
            self._fake_success(out)
            got = D.export(src, out, fmt="png", transparent=True, binary=sys.executable)
        self.assertTrue(got["ok"], got.get("message"))
        self.assertIn("显式底色", got.get("note", ""),
                      "文件自带底色时必须提示透明不会生效")

    def test_no_transparency_note_when_the_file_has_no_background(self):
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "x.drawio")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write('<mxfile><diagram><mxGraphModel/></diagram></mxfile>')
            out = os.path.join(td, "x.png")
            self._fake_success(out)
            got = D.export(src, out, fmt="png", transparent=True, binary=sys.executable)
        self.assertTrue(got["ok"], got.get("message"))
        self.assertNotIn("note", got, "没写底色的文件不该被提示")

    def _fake_success(self, out: str) -> None:
        """把 subprocess 换成"跑成功了并写出文件"，用于测回执。"""
        import subprocess
        from types import SimpleNamespace

        def fake_run(cmd, **kwargs):
            with open(out, "wb") as fh:
                fh.write(b"\x89PNG\r\n\x1a\n")
            return SimpleNamespace(returncode=0, stdout="exported", stderr="")

        # ⚠ 先抓住真函数再打补丁：反过来的话 cleanup 恢复的是**假的那个**，
        # 补丁会永久留在 subprocess 模块上（这个坑当场踩过，别的测试全红）。
        real_run = subprocess.run
        setattr(D.subprocess, "run", fake_run)
        self.addCleanup(setattr, D.subprocess, "run", real_run)

    def test_declared_background_is_detected(self):
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "a.drawio"), "w", encoding="utf-8") as fh:
                fh.write('<mxfile><diagram><mxGraphModel background="#FBFAF2"/>')
            self.assertEqual("#FBFAF2", D._declares_background(os.path.join(td, "a.drawio")))
            with open(os.path.join(td, "b.drawio"), "w", encoding="utf-8") as fh:
                fh.write('<mxfile><diagram><mxGraphModel/>')
            self.assertIsNone(D._declares_background(os.path.join(td, "b.drawio")))

    def test_missing_source_is_an_input_error(self):
        got = D.export("/不存在的图.drawio", "/tmp/x.png", binary=sys.executable)
        self.assertFalse(got["ok"])
        self.assertEqual("input", got["stage"])

    def test_bad_scale_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "x.drawio")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("<mxfile/>")
            got = D.export(src, os.path.join(td, "x.png"), scale="不是数")
        self.assertFalse(got["ok"])
        self.assertEqual("input", got["stage"])

    def test_main_returns_2_when_the_environment_is_missing(self):
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "x.drawio")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("<mxfile/>")
            code = D.main([src, "-o", os.path.join(td, "x.png"),
                           "--binary", "/绝对不存在的drawio"])
        self.assertEqual(2, code)

    def test_find_binary_explicit_path(self):
        self.assertIsNone(D.find_binary("/绝对不存在的drawio"))
        self.assertEqual(sys.executable, D.find_binary(sys.executable))

    def test_detection_never_raises(self):
        got = D.find_binary(None)
        self.assertTrue(got is None or isinstance(got, str))


if __name__ == "__main__":
    unittest.main()
