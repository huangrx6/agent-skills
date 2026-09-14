"""`check_pointers.py` 的边界值测试。

按项目定的停止判据：**元工具只需要边界值测试**，不再要求"验证测试本身对不对"。
所以这里只钉住几条行为分界，不追求穷尽：

  1. 「见 X」而 X 不存在 → **阻塞**（这句话在指路，路是断的）
  2. 只是提到一个像路径的词、X 不存在 → **列出但不阻塞**
  3. 以点开头的不是路径而是扩展名（`.excalidraw.md`）→ 忽略
  4. 代码块里的 → 忽略
  5. 真的存在 → 通过

第 2 条为什么不能也阻塞：实测有两条**合理**的"解析不到"——
skill-builder 自己写「假如有决策树图就放 references/decision-tree.md」（举例子），
PKB 里写 vault 的 `better-export-pdf/data.json`（仓库外的路径）。
全都阻塞就会制造误报，而**误报会训练人忽略整个检查**（前作 lint 全 warn 没人看）。

第 1 / 2 条的分界来自一次真实缺陷：一句「图标（`references/icons.md`）遵循同一条纪律」
指向了一个不存在的文件 —— 当时检查器完全查不出来，因为它只扫含「见 / 参见」这类动词的行。
"""
import contextlib
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
# 测试住在仓库顶层 `tests/<skill>/`（**刻意不在 skill 目录里**：AI 调用 skill 时读的是
# `skills/<skill>/` 那棵树，测试放在里面会被顺手读进去）。
# 所以从 `tests/<skill>/` 往上两级到仓库根，再进 `skills/<skill>/`。
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPT = os.path.join(SKILL, "scripts", "check_pointers.py")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CP = _load("check_pointers", SCRIPT)


class TestPointerBoundaries(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="ptr-")
        self.docs = os.path.join(self.root, "skills", "demo")
        os.makedirs(self.docs)
        os.makedirs(os.path.join(self.docs, "references"))
        # 一个真实存在的目标
        self._write("references/real.md", "# real\n")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _write(self, rel, text):
        path = os.path.join(self.docs, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def _run(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = CP.main(["--root", self.root, os.path.join(self.root, "skills")])
        return code, buf.getvalue()

    def test_missing_target_on_a_pointer_line_blocks(self):
        self._write("SKILL.md", "细节见 `references/gone.md`。\n")
        code, out = self._run()
        self.assertEqual(1, code, "「见 X」而 X 不存在必须阻塞")
        self.assertIn("参考", out + "参考")  # 输出里要有可读内容（不做措辞断言）

    def test_missing_target_without_a_verb_is_reported_but_not_blocking(self):
        self._write("SKILL.md", "假如有决策树图就放 `references/maybe-later.md`。\n")
        code, out = self._run()
        self.assertEqual(0, code, "举例子之类的写法不该阻塞")
        self.assertIn("references/maybe-later.md", out,
                      "不阻塞也必须**列出来**，否则又变成静默放行")

    def test_the_excalidraw_extension_is_not_a_path(self):
        """`.excalidraw.md` 是扩展名不是路径 —— 不能因为点开头就当成悬空引用。"""
        self._write("SKILL.md", "输出 plain `.excalidraw.md` 文件见 `references/real.md`。\n")
        code, out = self._run()
        self.assertEqual(0, code)
        self.assertNotIn("excalidraw.md", out)

    def test_pointer_inside_a_code_fence_is_ignored(self):
        self._write("SKILL.md", "```\n见 `references/gone.md`\n```\n")
        code, _out = self._run()
        self.assertEqual(0, code, "代码块里的不算指针")

    def test_existing_target_passes(self):
        self._write("SKILL.md", "细节见 `references/real.md`。\n")
        code, _out = self._run()
        self.assertEqual(0, code)

    def test_basename_resolution_across_skills(self):
        """跨 skill 只写文件名的情况靠 basename 解析 —— 那是常见写法，不能误报。"""
        self._write("SKILL.md", "写法规矩见 `real.md`。\n")
        code, _out = self._run()
        self.assertEqual(0, code)

    def test_json_output_separates_the_two_classes(self):
        self._write("SKILL.md", "见 `references/gone.md`。\n")
        self._write("references/other.md", "以后可以放 `references/also-gone.md`。\n")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = CP.main(["--root", self.root, "--json",
                            os.path.join(self.root, "skills")])
        self.assertEqual(1, code)
        import json
        data = json.loads(buf.getvalue())
        self.assertEqual(1, data["broken_count"])
        self.assertGreaterEqual(data["suspect_count"], 1)


if __name__ == "__main__":
    unittest.main()
