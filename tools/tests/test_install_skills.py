#!/usr/bin/env python3
"""`tools/install_skills.py` 的回归测试。

这个脚本会**往用户主目录写东西**（默认 `~/.agents/skills`），所以它的两种形态
（软链 / 副本）与三种状态（指向对了 / 指向别处 / 未安装）必须测得清清楚楚 ——
判错一个有价值的后果是把用户的 skill 装到错地方，或者把"没装"报成"已装"。

**所有用例都在临时目录里跑**，靠 `--install-dir` 指过去，绝不碰真的 `~/.agents/skills`。
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(HERE), "install_skills.py")


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


I = _load("install_skills_under_test", TOOL)


class InstallCase(unittest.TestCase):
    """一个假仓库 + 一个假安装位。仓库里放一个最小可用的 skill。"""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="install-skills-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = os.path.join(self.tmp, "repo")
        self.install = os.path.join(self.tmp, "install")
        self.skills_dir = os.path.join(self.repo, "skills")
        self.skill = "demo-skill"
        os.makedirs(os.path.join(self.skills_dir, self.skill, "references"))
        os.makedirs(self.install)
        self.write("SKILL.md", "---\nname: demo-skill\ndescription: 用例用\n---\n")
        self.write("references/note.md", "内容\n")

    def write(self, rel: str, text: str) -> None:
        path = os.path.join(self.skills_dir, self.skill, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def run_tool(self, *args: str) -> int:
        """跑一次工具，返回退出码。

        `skills_dir` 直接传进去 —— 不去改模块全局（那样读代码的人看不出依赖从哪来）。
        打印**收起来**：工具每次都要说一句装到哪了，20 个用例叠起来会把 unittest 的
        结果淹掉（实测过一次：只看得到 "装成软链"，看不见 OK / FAILED）。
        """
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = I.main([*args, "--install-dir", self.install], skills_dir=self.skills_dir)
        self._output = buffer.getvalue()
        return code

    @property
    def installed(self) -> str:
        return os.path.join(self.install, self.skill)


class TestLinkMode(InstallCase):
    """默认（软链）不该留副本 —— 留了就会漂，漂了就会装旧的。"""

    def test_default_installs_a_link_into_the_repo(self):
        self.assertEqual(0, self.run_tool())
        self.assertTrue(os.path.islink(self.installed), "默认应该是软链")
        self.assertTrue(I._same_path(self.installed, os.path.join(self.skills_dir, self.skill)))

    def test_link_reads_through_to_the_repo(self):
        """关键性质：改仓库，通过安装位读到的**立刻**是新内容。"""
        self.run_tool()
        self.write("references/note.md", "改过\n")
        with open(os.path.join(self.installed, "references", "note.md"), encoding="utf-8") as fh:
            self.assertEqual("改过\n", fh.read())

    def test_check_passes_when_linked(self):
        self.run_tool()
        self.assertEqual(0, self.run_tool("--check"))

    def test_check_rejects_a_link_to_elsewhere(self):
        """指着别的副本（比如旧的 clone）是**真问题**：那是最难发现的一种漂移。"""
        os.symlink(self.tmp, self.installed)          # 指向别处
        self.assertEqual(1, self.run_tool("--check"))

    def test_check_rejects_a_broken_link(self):
        os.symlink(os.path.join(self.tmp, "gone"), self.installed)
        self.assertEqual(1, self.run_tool("--check"))

    def test_check_reports_missing(self):
        self.assertEqual(1, self.run_tool("--check"))
        self.assertIn("未安装", self._output, "检查结果要说人话，不能只给退出码")

    def test_replacing_a_copy_with_a_link(self):
        self.assertEqual(0, self.run_tool("--copy"))
        self.assertFalse(os.path.islink(self.installed))
        self.assertEqual(0, self.run_tool())                   # 再来一次：改成软链
        self.assertTrue(os.path.islink(self.installed))
        self.assertEqual(0, self.run_tool("--check"))

    def test_relinking_is_idempotent(self):
        self.run_tool()
        first = os.readlink(self.installed)
        self.assertEqual(0, self.run_tool())
        self.assertEqual(first, os.readlink(self.installed))


class TestCopyMode(InstallCase):
    """副本模式是给"仓库会被移走"的场景留的 —— 那就必须能查出内容漂移。"""

    def test_copy_contains_the_content(self):
        self.run_tool("--copy")
        path = os.path.join(self.installed, "references", "note.md")
        with open(path, encoding="utf-8") as fh:
            self.assertEqual("内容\n", fh.read())

    def test_check_detects_a_stale_copy(self):
        self.run_tool("--copy")
        self.write("references/note.md", "仓库这边改了\n")
        self.assertEqual(1, self.run_tool("--check"), "副本落后于仓库时必须报出来")

    def test_check_detects_files_left_behind_in_the_install(self):
        """仓库里删掉的文件不能留在安装位当幽灵 —— 那会被当成 skill 的一部分。"""
        self.run_tool("--copy")
        self.assertEqual(0, self.run_tool("--check"))
        with open(os.path.join(self.installed, "references", "ghost.md"), "w",
                  encoding="utf-8") as fh:
            fh.write("幽灵\n")
        self.assertEqual(1, self.run_tool("--check"))

    def test_resync_removes_the_ghost(self):
        self.run_tool("--copy")
        with open(os.path.join(self.installed, "references", "ghost.md"), "w",
                  encoding="utf-8") as fh:
            fh.write("幽灵\n")
        self.assertEqual(0, self.run_tool("--copy"))
        self.assertFalse(os.path.exists(os.path.join(self.installed, "references", "ghost.md")))
        self.assertEqual(0, self.run_tool("--check"))


class TestMissingInstallDir(InstallCase):
    """安装位不存在 = 未安装，**不是失败**（换机器、CI 上很常见）。"""

    def test_absent_dir_is_not_a_failure(self):
        shutil.rmtree(self.install)
        self.assertEqual(0, self.run_tool("--check"))
        self.assertEqual(0, self.run_tool())

    def test_does_not_create_the_dir_behind_your_back(self):
        shutil.rmtree(self.install)
        self.run_tool()
        self.assertFalse(os.path.exists(self.install), "不该顺手把安装位建出来")


class TestInstalledKind(InstallCase):
    """`installed_kind` 的顺序很要紧：`isdir` 会跟随软链，所以**必须先问 islink**。"""

    def test_link_wins_over_directory(self):
        self.run_tool()
        self.assertEqual("link", I.installed_kind(self.installed))

    def test_copy_is_copy(self):
        self.run_tool("--copy")
        self.assertEqual("copy", I.installed_kind(self.installed))

    def test_missing_is_missing(self):
        self.assertEqual("missing", I.installed_kind(self.installed))


class TestSamePath(InstallCase):
    """`_same_path` 走 realpath —— macOS 上 `/var` 与 `/private/var` 是同一个目录。"""

    def test_follows_symlinked_parents(self):
        real = os.path.join(self.tmp, "real")
        os.makedirs(real)
        alias = os.path.join(self.tmp, "alias")
        os.symlink(real, alias)
        self.assertTrue(I._same_path(real, alias))

    def test_different_paths_are_not_same(self):
        other = os.path.join(self.tmp, "other")
        os.makedirs(other)
        self.assertFalse(I._same_path(self.tmp, other))


class TestIgnoreRules(InstallCase):
    """本地产物不算内容：`__pycache__` 不该被拷、也不该被当成漂移。"""

    def test_pycache_is_ignored(self):
        self.run_tool("--copy")
        junk = os.path.join(self.installed, "__pycache__")
        os.makedirs(junk)
        with open(os.path.join(junk, "x.pyc"), "wb") as fh:
            fh.write(b"\x00")
        self.assertEqual(0, self.run_tool("--check"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
