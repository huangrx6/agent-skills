#!/usr/bin/env python3
"""check_drawio.py 的回归测试：**这个自检必须真的会拦人**。

## 为什么"自检器自己的测试"值得单独写一份

`check_drawio` 是 `emit_drawio` 唯一的守门人（emit 在写文件之前调它）。一个只会说
"✓" 的守门人和没有守门人**在结果上完全一样**，但会让人以为有人守着 —— 这就是这类
工具最坏的失败方式。所以下面每个用例都构造一份**坏文件**，断言它被点名报出来，
而不是"没崩就算过"。

第一版 `check_drawio` 自己就错过一次（也是这轮被抓出来的）：它要求**边**的
`<mxGeometry>` 也带 `width`/`height`，而 drawio 的边几何是**相对**的 —— 边根本没有
宽高，路由由 `source`/`target` 与折点决定。于是三张本来正确的图被判成"坏文件"。
下面 `test_edge_geometry_needs_no_width_height` 就是这个事故的钉子。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/test_check_drawio.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


C = _load("check_drawio", os.path.join(SCRIPTS, "check_drawio.py"))

GOOD = """<?xml version="1.0" encoding="UTF-8"?>
<mxfile host="diagram-authoring" type="device">
  <diagram id="abc123" name="夹具">
    <mxGraphModel pageWidth="800" pageHeight="600">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        <mxCell id="n-a" value="A" style="rounded=1" vertex="1" parent="1">
          <mxGeometry x="10" y="20" width="100" height="40" as="geometry" />
        </mxCell>
        <mxCell id="n-b" value="B" style="rounded=1" vertex="1" parent="1">
          <mxGeometry x="200" y="20" width="100" height="40" as="geometry" />
        </mxCell>
        <mxCell id="e-0" value="" style="endArrow=classic" edge="1" parent="1"
                source="n-a" target="n-b">
          <mxGeometry relative="1" as="geometry">
            <Array as="points"><mxPoint x="150" y="40" /></Array>
          </mxGeometry>
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
"""


def check(text: str) -> str:
    """把问题列表拼成一段文本，断言里就不用到处下标。"""
    return " | ".join(C.check_text(text))


class TestGoodFile(unittest.TestCase):
    def test_clean_file_has_no_problems(self):
        self.assertEqual(C.check_text(GOOD), [])

    def test_edge_geometry_needs_no_width_height(self):
        """边是相对几何：没有 x/y/width/height 是**对的**（第一版在这里误报三张图）。"""
        problems = C.check_text(GOOD)
        self.assertEqual(problems, [], f"边被误判：{problems}")

    def test_check_file_reads_from_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "ok.drawio")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(GOOD)
            self.assertEqual(C.check_file(path), [])

    def test_check_file_missing_path_reports(self):
        problems = C.check_file("/nonexistent/nope.drawio")
        self.assertEqual(len(problems), 1)
        self.assertIn("读不到", problems[0])


class TestStructuralFacts(unittest.TestCase):
    """每条要守的结构事实各有至少一个用例 —— 少了这条，那条检查就是装饰。"""

    def test_missing_root_cell_zero(self):
        text = GOOD.replace('        <mxCell id="0" />\n', "")
        self.assertIn('id="0"', check(text))

    def test_missing_root_cell_one(self):
        text = GOOD.replace('        <mxCell id="1" parent="0" />\n', "")
        self.assertIn('id="1"', check(text))

    def test_duplicate_id(self):
        text = GOOD.replace('id="n-b"', 'id="n-a"')
        self.assertIn("id 重复：n-a", check(text))

    def test_parent_not_existing(self):
        text = GOOD.replace('id="n-b" value="B" style="rounded=1" vertex="1" parent="1"',
                            'id="n-b" value="B" style="rounded=1" vertex="1" parent="n-ghost"')
        self.assertIn("parent=n-ghost 不存在", check(text))

    def test_vertex_without_geometry(self):
        # 三行一起换（连 </mxCell>）—— 只删开标签会造出一份**语法就是坏的** XML，
        # 那样 checker 报的是"解析失败"，用例看着过了，其实什么都没测到。
        text = GOOD.replace(
            '        <mxCell id="n-b" value="B" style="rounded=1" vertex="1" parent="1">\n'
            '          <mxGeometry x="200" y="20" width="100" height="40" as="geometry" />\n'
            '        </mxCell>\n',
            '        <mxCell id="n-b" value="B" style="rounded=1" vertex="1" parent="1" />\n')
        self.assertIn("n-b 没有 <mxGeometry>", check(text))

    def test_zero_sized_vertex(self):
        text = GOOD.replace('width="100" height="40" as="geometry"', 'width="0" height="40" as="geometry"', 1)
        self.assertIn("width = 0", check(text))

    def test_non_numeric_geometry(self):
        text = GOOD.replace('x="10"', 'x="左边一点"', 1)
        self.assertIn("不是有限数", check(text))

    def test_nan_geometry(self):
        text = GOOD.replace('y="20"', 'y="nan"', 1)
        self.assertIn("不是有限数", check(text))

    def test_edge_point_must_be_finite(self):
        text = GOOD.replace('<mxPoint x="150" y="40" />', '<mxPoint x="150" y="inf" />')
        self.assertIn("折点", check(text))

    def test_edge_source_must_be_existing_vertex(self):
        text = GOOD.replace('source="n-a"', 'source="n-gone"')
        self.assertIn("source=n-gone 不是存在的节点", check(text))

    def test_edge_source_pointing_at_edge_is_rejected(self):
        """source 指到**另一条边**上也算坏 —— 必须是 vertex。"""
        text = GOOD.replace('source="n-a"', 'source="e-0"')
        self.assertIn("不是存在的节点", check(text))


class TestUnreadableInput(unittest.TestCase):
    def test_empty_file(self):
        self.assertIn("空", check("   \n"))

    def test_broken_xml(self):
        self.assertIn("XML 解析失败", check('<mxfile><diagram></mxfile>'))

    def test_no_diagram_element(self):
        self.assertIn("没有 <diagram>", check("<mxfile></mxfile>"))

    def test_diagram_without_model(self):
        text = GOOD.replace("<mxGraphModel", "<mxWhatever").replace(
            "</mxGraphModel>", "</mxWhatever>")
        self.assertIn("没有 <mxGraphModel>", check(text))

    def test_compressed_diagram_is_reported_not_ignored(self):
        """app 保存的默认形态是 deflate+base64。**必须报出来**，不能当空文件放行。"""
        text = ('<?xml version="1.0" encoding="UTF-8"?>\n<mxfile>\n'
                '  <diagram id="x" name="Page-1">7Vpbc9o4FP41zLQP</diagram>\n</mxfile>\n')
        problems = C.check_text(text)
        self.assertEqual(len(problems), 1)
        self.assertIn("压缩", problems[0])


class TestCli(unittest.TestCase):
    def test_cli_exit_codes_and_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = os.path.join(tmp, "good.drawio")
            bad = os.path.join(tmp, "bad.drawio")
            with open(good, "w", encoding="utf-8") as handle:
                handle.write(GOOD)
            with open(bad, "w", encoding="utf-8") as handle:
                handle.write(GOOD.replace('id="0"', 'id="zero"'))
            import contextlib
            import io
            err = io.StringIO()
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(C.main([good]), 0)
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = C.main([bad])
            self.assertEqual(code, 1)
            # 改掉 id="0" 会连带让 `id="1" parent="0"` 悬空 —— 所以这里是 2 个问题。
            # （断言"1 个"曾经过不了，恰好说明这两条检查各管各的、没有互相掩盖。）
            self.assertIn("共 2 个问题", err.getvalue())
            self.assertIn('id="0"', out.getvalue())

    def test_cli_multiple_files_reports_each(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for index in range(2):
                path = os.path.join(tmp, f"f{index}.drawio")
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(GOOD)
                paths.append(path)
            import contextlib
            import io
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = C.main(paths)
            self.assertEqual(code, 0)
            self.assertEqual(out.getvalue().count("✓"), 2)


if __name__ == "__main__":
    unittest.main()
