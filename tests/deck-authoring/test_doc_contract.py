#!/usr/bin/env python3
"""文档契约测试 —— 文档里那些**由代码生成**的段落，改代码就必须跟着动。

## 为什么

一份规范最危险的漂移不是"写错了"，是"两边都对，但不一样"：代码里 22 个角色、
文档表里 21 个（有人加角色时漏了表），然后读者按文档选角色，脚本按代码判合规 ——
两边都振振有词。人盯不住这种东西，逐字比对能。

做法（跟"文档由注册表生成"是同一条路）：正文里用 `<!-- xxx:start -->/<!-- xxx:end -->`
圈出生成段，测试**从代码重新生成一遍**再比对。漂移当场红，而不是等读者踩。

跑法：
    python3 -m unittest discover -s tests/deck-authoring -p "test_doc_contract.py"
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills",
                     os.path.basename(HERE))
REFS = os.path.join(SKILL, "references")
SCRIPTS = os.path.join(SKILL, "scripts")


def _load(name: str):
    path = os.path.join(SCRIPTS, "layout", f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"_doc_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def block(path: str, tag: str) -> str:
    """取 `<!-- <tag>:start … -->` 与 `<!-- <tag>:end -->` 之间的正文。"""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    hit = re.search(rf"<!-- {tag}:start[^>]*-->\n(.*?)\n<!-- {tag}:end -->",
                    text, re.S)
    if hit is None:
        raise AssertionError(f"{os.path.basename(path)} 里没有 {tag} 生成段标记")
    return hit.group(1)


class TestRolesDoc(unittest.TestCase):
    """角色表：planning.md 里那张表必须是 layout/roles.py 的产物。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.roles = _load("roles")
        cls.doc = os.path.join(REFS, "planning.md")

    def test_table_matches_the_registry_verbatim(self) -> None:
        self.assertEqual(block(self.doc, "roles"), self.roles.markdown_table(),
                         "planning.md 的角色表与 layout/roles.py 不一致 —— "
                         "改角色请改 roles.py，然后重新生成这一段")

    def test_markers_appear_exactly_once(self) -> None:
        with open(self.doc, encoding="utf-8") as fh:
            text = fh.read()
        for tag in ("roles:start", "roles:end"):
            self.assertEqual(text.count(f"<!-- {tag}"), 1,
                             f"{tag} 标记该有且只有一个")

    def _row_role(self, row: str) -> str:
        """取一行的角色名；不是角色行就当场失败（不是静默跳过）。"""
        hit = re.match(r"\| `([a-z_]+)` \|", row)
        if hit is None:
            self.fail(f"这一行不是角色行：{row!r}")
            return ""                      # fail 会抛异常，这行到不了
        return hit.group(1)

    def test_every_role_has_a_row(self) -> None:
        rows = [line for line in block(self.doc, "roles").split("\n")[2:] if line.strip()]
        named = [self._row_role(row) for row in rows]
        self.assertEqual(named, list(self.roles.ROLES),
                         "表里的角色名与顺序都要跟注册表一致（顺序也是信息）")

    def test_visual_column_comes_from_the_registry(self) -> None:
        """主视觉档以前只写在文档里 —— 现在它也在注册表里，两边必须同源。"""
        for role, spec in self.roles.ROLES.items():
            self.assertIn("visual", spec, f"{role} 缺 visual（推荐主视觉档）")
            self.assertTrue(spec["visual"], f"{role} 的 visual 不能为空")
            for tier in spec["visual"]:
                self.assertIn(tier, ("none", "data", "evidence_image"),
                              f"{role} 的 visual 档 {tier!r} 不是三档之一")


if __name__ == "__main__":
    unittest.main()
