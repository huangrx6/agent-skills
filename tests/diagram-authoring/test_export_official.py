#!/usr/bin/env python3
"""`dev-tools/export_excalidraw.py`（官方导出）的测试。

**这些用例不需要 Chrome、不需要联网** —— 它们守的是三件容易坏、坏了又很难发现的事：

1. **官方 API 的形状**。`@excalidraw/utils` 的签名是 `{ data, config }` 两段式，
   而且**倍率两条路不一样**（PNG 走 `config.scale`、SVG 走 `appState.exportScale`）。
   这两条都是实测出来的（见 `references/validation.md`），写错的表现是
   "出来一张 1 倍图"或 `Cannot read properties of undefined (reading 'elements')` ——
   前者不会报错，只是图糊。
2. **场景注入不能把页面撑破**。标签里出现 `</script>` 会把内嵌 JSON 提前闭合，
   页面里剩下的 JSON 变成正文 —— 导出直接失败，而原因看起来像个语法错误。
3. **失败要进结构化回执**，不能抛：上游（修复循环、基准验证器）要能读懂
   "是环境缺 Chrome" 还是"页面里导出失败"。

跑法：
    python3 -m unittest discover -s tests/diagram-authoring -v
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
# 测试住在仓库顶层 `tests/<skill>/`（刻意不在 skill 目录里，理由见同目录其它测试）。
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills",
                     os.path.basename(HERE))
EXPORT = os.path.join(SKILL, "dev-tools", "export_excalidraw.py")


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


X = _load("_diagram_export_excalidraw", EXPORT)

SCENE = {"type": "excalidraw", "version": 2, "source": "x",
         "elements": [{"id": "r1", "type": "rectangle", "x": 0, "y": 0,
                       "width": 10, "height": 10}],
         "appState": {"viewBackgroundColor": "#ffffff"}, "files": {}}


class TestPageWiring(unittest.TestCase):
    """页面里那几行 JS 是我们与官方包之间唯一的接口 —— 它们错了没人替我们报错。"""

    def test_scene_is_embedded_and_cannot_break_the_page(self):
        """`</` 必须转义：否则标签里一个 `</script>` 就能把内嵌 JSON 提前闭合。"""
        nasty = dict(SCENE)
        nasty["elements"] = [dict(SCENE["elements"][0],
                                  x_label="</script><b>注入</b>")]
        page = X._inject_scene(X.PAGE_TEMPLATE, nasty, 2, 16)
        self.assertIn("x_label", page)
        self.assertNotIn("</script><b>", page)
        self.assertIn("<\\/script>", page)
        # 场景还得是能被 JSON.parse 吃下的合法 JSON（转义不能把内容改坏）
        raw = page.split('id="excalidraw-scene">', 1)[1].split("</script>", 1)[0]
        self.assertEqual("</script><b>注入</b>",
                         json.loads(raw)["elements"][0]["x_label"])

    def test_uses_the_official_package_and_both_scale_knobs(self):
        """守住实测出来的 API 形状 —— 这三处任一写错都会静默出糊图或直接报错。"""
        page = X.PAGE_TEMPLATE
        self.assertIn("@excalidraw/utils", X.CDN, "必须是官方包，不能是自制的替代品")
        self.assertIn("__CDN__", page, "页面必须用那个占位符拿官方包（不写死 URL）")
        self.assertIn("exportToBlob", page)
        self.assertIn("exportToSvg", page)
        self.assertIn("data: data", page, "0.1.5 是 { data, config } 两段式")
        self.assertIn("config: { mimeType: \"image/png\", scale: __SCALE__, padding: __PADDING__ }",
                      page, "PNG 的留白在 config.padding（实测：appState.exportPadding 被忽略）")
        self.assertIn("exportScale = __SCALE__", page,
                      "SVG 的倍率在 appState.exportScale（实测）")
        self.assertIn("config: { padding: __PADDING__ }", page, "SVG 的留白也在 config.padding")
        self.assertNotIn("appState.exportPadding = ", page,
                         "别写这个哑参数 —— 官方包忽略它（实测：设 32 与不设出一模一样的图），"
                         "只写它的话留白不生效、图贴边（用户报过一次）")

    def test_no_umd_global_is_used(self):
        """0.1.4 起只发 ESM、没有 UMD —— 别再退回 `ExcalidrawUtils` 全局那个写法。"""
        self.assertNotIn("ExcalidrawUtils", X.PAGE_TEMPLATE)
        self.assertIn('type="module"', X.PAGE_TEMPLATE)


class TestDefaultPadding(unittest.TestCase):
    """默认留白是用户拿真实产物反馈"内容紧挨边框"之后定的 —— 官方默认会贴边。"""

    def test_default_padding_clears_the_inners_padding(self):
        """留白不能比**图内节点自己的内边距**（22~24）还窄 —— 外紧里松就不自然。"""
        self.assertGreaterEqual(X.DEFAULT_PADDING, 24,
                                "默认留白窄于图内内边距，导出会显得局促")

    def test_export_and_cli_share_that_default(self):
        """默认值只有一处来源（DEFAULT_PADDING），函数签名与命令行都得用它。"""
        import contextlib
        import inspect
        import io

        self.assertEqual(X.DEFAULT_PADDING,
                         inspect.signature(X.export).parameters["padding"].default,
                         "函数签名默认值要取自常量，不要并写一个数")
        seen = {}
        real_export = X.export

        def fake_export(*args, **kwargs):
            seen.update(kwargs)
            # 回执形状要够 main() 走完成功那条路（它会读 outputs）
            return {"ok": True, "outputs": {"png": "x.png"}}

        setattr(X, "export", fake_export)
        self.addCleanup(setattr, X, "export", real_export)
        with contextlib.redirect_stdout(io.StringIO()):
            X.main(["不存在的场景.excalidraw", "-o", "x.png"])
        self.assertEqual(X.DEFAULT_PADDING, seen.get("padding"),
                         "命令行默认留白必须取自同一个常量（两处写死会漂）")


class TestReceipts(unittest.TestCase):
    """失败要回结构化回执，不抛异常：上游要能分辨"缺环境"与"页面里失败"。"""

    def test_unreadable_scene_returns_an_input_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            missing = os.path.join(td, "没有这个文件.excalidraw")
            got = X.export(missing, None, None)
        self.assertFalse(got["ok"])
        self.assertEqual("input", got["stage"])
        self.assertIn("读不了", got["message"])

    def test_broken_json_returns_an_input_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "broken.excalidraw")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("{ 不是 JSON")
            got = X.export(path, None, None)
        self.assertFalse(got["ok"])
        self.assertEqual("input", got["stage"])

    def test_bad_scale_or_padding_is_reported_not_raised(self):
        """纵深防御：argparse 已经限了类型，但这条路上也算一次。"""
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "ok.excalidraw")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(SCENE, fh)
            got = X.export(path, None, None, scale="不是数")
        self.assertFalse(got["ok"])
        self.assertEqual("input", got["stage"])

    def test_main_exit_codes(self):
        """2 = 环境/输入不可用，1 = 页面里导出失败；成功是 0。"""
        with tempfile.TemporaryDirectory() as td:
            missing = os.path.join(td, "没有.excalidraw")
            self.assertEqual(2, X.main([missing, "-o", os.path.join(td, "x.png")]))


class TestBrowserDetection(unittest.TestCase):

    def test_explicit_path_wins_and_missing_is_none(self):
        self.assertIsNone(X.find_browser("/绝对不存在的浏览器"))
        self.assertEqual(sys.executable, X.find_browser(sys.executable))

    def test_detection_never_raises(self):
        """探测失败只是"返回 None"，不能把调用方炸掉。"""
        got = X.find_browser(None)
        self.assertTrue(got is None or isinstance(got, str))


if __name__ == "__main__":
    unittest.main()
