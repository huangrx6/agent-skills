#!/usr/bin/env python3
"""check_paths.py 的回归测试。

为什么需要：这个脚本存在的理由就是"配置指向虚空 + 失败静默"没法靠自觉发现
（better-export-pdf 的 cssSnippet 指向旧 vault 位置，插件的 catch 只打 console，
PDF 静默地不带自定义样式，而且错误路径还被 prevConfig 每次导出重新固化）。
脚本本身每个设计决定也都来自具体的坑 —— 含空格的路径被截断、"文件 vs 目录"
的分层、扫描范围必须排除笔记正文与插件打包 JS。这些同样是会淡忘的经验。

fixture 在 setUpClass 里生成到临时目录，不落盘成真实文件 —— 那些故意写坏的
路径会被编辑器/检查工具当成真问题报警，而它们本来就是用来测"坏路径能被报出来"的。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/test_check_paths.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
# 测试住在仓库顶层 `tests/<skill>/`（**刻意不在 skill 目录里**：AI 调用 skill 时读的是
# `skills/<skill>/` 那棵树，测试放在里面会被顺手读进去）。
# 所以从 `tests/<skill>/` 往上两级到仓库根，再进 `skills/<skill>/`。
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")
CHECK_PATHS = os.path.join(SCRIPTS, "check_paths.py")


def _load_check_paths():
    """按路径加载 check_paths.py(scripts/ 不是包,不能用 import 语句)。"""
    spec = importlib.util.spec_from_file_location("check_paths_under_test", CHECK_PATHS)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {CHECK_PATHS}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _config_json(root: str) -> str:
    """一份覆盖全部分支的插件配置。"""
    return json.dumps(
        {
            # 存在 → 不该报
            "goodCss": f"{root}/.obsidian/snippets/存在.css",
            # 不存在但带扩展名 → 引用文件 → 必须报
            "badCss": f"{root}/.obsidian/snippets/缺失.css",
            # 含空格且存在 → 截断取法会把它切成不存在的路径而误报
            "spacedOk": f"{root}/.obsidian/我 的/也在.css",
            # 含空格且不存在 → 要能报出**完整**路径
            "spacedBad": f"{root}/.obsidian/我 的/也缺.css",
            # 不存在、无扩展名 → 目录类,只提示
            "outDir": f"{root}/.obsidian/还没建的目录",
            # ~ 开头:Node 的 fs 不做展开,必然失败 → 要标出来
            "tilde": "~/绝不可能存在-ABC123/foo.css",
        },
        indent=2,
        ensure_ascii=False,
    )


def _build_vault(root: str) -> None:
    """搭一个最小 vault。写的是"故意坏掉"的路径,所以生成到临时目录。"""
    files = {
        # 被引用的真文件
        ".obsidian/snippets/存在.css": "body{}",
        # 文件正文里有示例绝对路径 → 整个 .md 都不在扫描范围内
        "01 Notes/示例.md": (
            "# 示例\n\n"
            "Windows 上的 `/Users/me/workspace/app` 只是举例。\n"
            "```sh\ncd /opt/app\n```\n"
        ),
        # 插件打包 JS 里的路径是"候选列表"(逐个尝试直到命中)→ 不扫
        ".obsidian/plugins/some-plugin/main.js": (
            'const candidates = ["/opt/homebrew/bin/lark-cli", "/usr/local/bin/lark-cli"];\n'
        ),
        # 配置主体
        ".obsidian/plugins/some-plugin/data.json": _config_json(root),
        ".obsidian/app.json": "{}",
    }
    for rel, content in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)

    # 含空格的目录(用来验证截断取法会误报)
    os.makedirs(os.path.join(root, ".obsidian/我 的"), exist_ok=True)
    with open(os.path.join(root, ".obsidian/我 的/也在.css"), "w", encoding="utf-8") as fh:
        fh.write("body{}")


class CheckPathsTest(unittest.TestCase):
    tmp: str

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_check_paths()
        cls.tmp = tempfile.mkdtemp(prefix="check-paths-fixture-")
        _build_vault(cls.tmp)
        cls.result = cls.mod.scan(cls.tmp)
        cls.paths = {i["path"] for i in cls.result["file_refs"]}
        cls.dirs = {i["path"] for i in cls.result["dir_refs"]}
        # 范围类断言必须看**全部**取到的路径。
        # 只看 file_refs 会写出恒过的空壳 —— fixture 里的示例路径
        # （/Users/me/workspace/app、/opt/homebrew/bin/lark-cli）都没有扩展名，
        # 分在 dir_refs 里，于是“扫描范围没泄露”这两条断言无论真伪都通过。
        # 这是变异测试发现的：把 CONFIG_EXTS 扩到 .md/.js 后那两条测试仍绿。
        cls.everything = cls.paths | cls.dirs

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ── 防线 1:引用了不存在的文件必须报出来(防止永远全绿) ──
    def test_missing_file_is_reported(self):
        self.assertIn(
            f"{self.tmp}/.obsidian/snippets/缺失.css",
            self.paths,
            "配置指向不存在的 CSS 文件却没被报出 —— 这正是 better-export-pdf 那个 bug",
        )

    # ── 防线 2:存在的路径不该报(误报会让人不再信任检查) ──
    def test_existing_file_is_not_reported(self):
        self.assertNotIn(
            f"{self.tmp}/.obsidian/snippets/存在.css",
            self.paths,
            "存在的文件被误报成失效",
        )

    # ── 防线 3:含空格的路径不能被截断 ──
    def test_path_with_spaces_is_not_truncated(self):
        # 截断取法会把 ".../我 的/也缺.css" 切成 ".../我" 然后当成失效路径报出来
        self.assertNotIn(
            f"{self.tmp}/.obsidian/我",
            self.paths,
            "含空格的路径被截断,报出了一个根本不是配置里写的路径",
        )
        self.assertIn(
            f"{self.tmp}/.obsidian/我 的/也缺.css",
            self.paths,
            "含空格的失效路径没有被完整报出",
        )

    # ── 防线 4:文件 vs 目录分层(决定阻塞与否) ──
    def test_missing_dir_is_separated_from_missing_file(self):
        self.assertIn(
            f"{self.tmp}/.obsidian/还没建的目录",
            self.dirs,
            "无扩展名的不存在路径应归为目录类",
        )
        self.assertNotIn(
            f"{self.tmp}/.obsidian/还没建的目录",
            self.paths,
            "目录类路径被误归成文件类 —— 会挡住正常的提交",
        )

    # ── 防线 5:~ 开头的路径要被标出来 ──
    def test_tilde_path_is_flagged(self):
        tilde = [i for i in self.result["file_refs"] if i["tilde"]]
        self.assertEqual(len(tilde), 1, "~/ 开头的路径没有被标记 —— Node 的 fs 不会展开它")
        self.assertTrue(tilde[0]["path"].startswith("~/"))

    # ── 防线 6:扫描范围只限配置文件 ──
    def test_notes_are_not_scanned(self):
        self.assertFalse(
            [p for p in self.everything if "/Users/me/" in p or "/opt/app" in p],
            "笔记正文里的示例绝对路径被扫进来了 —— 实测 vault 里有 64 处,全是误报",
        )

    def test_bundled_plugin_js_is_not_scanned(self):
        self.assertFalse(
            [p for p in self.everything if "homebrew/bin" in p],
            "插件打包 JS 里的候选路径列表被扫进来了 —— 不存在的候选是设计如此",
        )

    def test_only_expected_hits(self):
        self.assertEqual(
            len(self.result["file_refs"]), 3,
            f"期望恰好 3 个失效文件引用,实得 {sorted(self.paths)}",
        )
        self.assertEqual(
            len(self.result["dir_refs"]), 1,
            f"期望恰好 1 个不存在的目录,实得 {sorted(self.dirs)}",
        )

    # ── CLI 行为:退出码契约 ──
    def test_cli_exit_code_is_1_when_file_missing(self):
        proc = subprocess.run(
            [sys.executable, CHECK_PATHS, "--vault", self.tmp, "--quiet"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 1, "有失效文件引用时退出码应为 1")

    def test_cli_exit_code_is_0_when_only_dir_missing(self):
        with tempfile.TemporaryDirectory(prefix="check-paths-dironly-") as root:
            os.makedirs(os.path.join(root, ".obsidian/plugins/p"))
            with open(os.path.join(root, ".obsidian/plugins/p/data.json"), "w",
                      encoding="utf-8") as fh:
                json.dump({"outDir": f"{root}/还没建"}, fh)
            proc = subprocess.run(
                [sys.executable, CHECK_PATHS, "--vault", root, "--quiet"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, "只有目录缺失时不应阻塞提交")

    def test_cli_exit_code_is_2_when_vault_missing(self):
        proc = subprocess.run(
            [sys.executable, CHECK_PATHS, "--vault", "/definitely/not/here", "--quiet"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 2, "vault 不存在时退出码应为 2")


if __name__ == "__main__":
    unittest.main(verbosity=2)
