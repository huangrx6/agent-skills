#!/usr/bin/env python3
"""`tools/skill_health.py` 的回归测试。

这个脚本是 ROADMAP 的**数字来源** —— 它算错不会让任何东西失败，只会让"该优化什么"
这件事按错的数字排序（比如把余量算成负数、把被引用的素材报成死文件）。
所以判据要有边界测试：余量、行数、死文件识别、没有 skills/ 的目录。

测试在临时目录里造一个**假仓库**，并把真的 `validate_skill.py` 拷进去 ——
体检脚本复用的正是它的 `MAX_BODY_LINES` / `HEADROOM_MIN` / `FM_RE`，如果那几个名字
改了，这里应当一起红，而不是让体检悄悄按旧常量算。
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
TOOLS = os.path.dirname(HERE)
REPO = os.path.dirname(TOOLS)
HEALTH = os.path.join(TOOLS, "skill_health.py")
VALIDATOR = os.path.join(REPO, "skills", "skill-builder", "scripts", "validate_skill.py")


def _load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


health = _load(HEALTH, "_test_skill_health")

SKILL_MD = """---
name: {name}
description: Use this skill when 测试体检. Do NOT use for 别的。
---

# {name}

正文在这里。
{body}
"""


# frontmatter 之后模板还有 4 个换行（空行 / 标题 / 空行 / 一句说明），
# 所以想让正文恰好是 N 行，模板里只要补 N - 4 行。
BODY_PADDING = 4


class RepoCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        os.makedirs(os.path.join(self.root, "skills"))
        # 把真的校验器拷进去：体检脚本复用它的常量，改名字了这里要一起红
        # （体检按固定的相对路径找它，所以假仓库里得照那个路径放一份）
        validator_dir = os.path.join(self.root, "skills", "skill-builder")
        os.makedirs(os.path.join(validator_dir, "scripts"))
        shutil.copy(VALIDATOR, os.path.join(validator_dir, "scripts", "validate_skill.py"))
        # 那个目录在真仓库里本来就是个 skill，这里也给它配上，免得成为“缺 README”的噪声
        self.make_skill("skill-builder", body_lines=3, readme=True, evals=True)

    def make_skill(self, name: str, body_lines: int = 3, *, readme: bool = False,
                   evals: bool = True, assets: tuple[str, ...] = ()) -> str:
        """造一个 skill，`body_lines` 是**最终正文的行数**（含模板自带的那几行）。"""
        skill = os.path.join(self.root, "skills", name)
        os.makedirs(skill, exist_ok=True)
        extra = max(0, body_lines - BODY_PADDING)
        body = "\n".join(f"第 {i} 行" for i in range(extra))
        with open(os.path.join(skill, "SKILL.md"), "w", encoding="utf-8") as fh:
            fh.write(SKILL_MD.format(name=name, body=body))
        if readme:
            with open(os.path.join(skill, "README.md"), "w", encoding="utf-8") as fh:
                fh.write(f"# {name}\n")
        if evals:
            os.makedirs(os.path.join(skill, "evals"))
            with open(os.path.join(skill, "evals", "evals.json"), "w", encoding="utf-8") as fh:
                json.dump({"skill_name": name, "evals": []}, fh)
        for rel in assets:
            target = os.path.join(skill, "assets", rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as fh:
                fh.write("x")
        return skill


class ScanTest(RepoCase):
    def test_数行数与余量(self):
        self.make_skill("aaa", body_lines=5)
        report = health.scan_repo(self.root)
        skill = report["skills"][0]
        self.assertEqual(5, skill["body_lines"])
        self.assertEqual(report["limits"]["max_body_lines"] - 5, skill["headroom"])

    def test_模板补白走通了_不然边界用例会假绿(self):
        """这条守的是夹具自身：如果补白算错，145/151 那两条边界用例就是假绿。"""
        self.make_skill("aaa", body_lines=140)
        self.assertEqual(140, health.scan_repo(self.root)["skills"][0]["body_lines"])

    def test_上限与提示线来自真的校验器(self):
        validator = health._load_validator(self.root)
        self.assertEqual(validator.MAX_BODY_LINES, health.scan_repo(self.root)["limits"]["max_body_lines"])
        self.assertEqual(validator.HEADROOM_MIN, health.scan_repo(self.root)["limits"]["headroom_min"])

    def test_缺_readme_与缺_evals_要能被看出来(self):
        self.make_skill("有", readme=True, evals=True)
        self.make_skill("没有", readme=False, evals=False)
        by_name = {s["name"]: s for s in health.scan_repo(self.root)["skills"]}
        self.assertTrue(by_name["有"]["has_readme"])
        self.assertTrue(by_name["有"]["has_evals"])
        self.assertFalse(by_name["没有"]["has_readme"])
        self.assertFalse(by_name["没有"]["has_evals"])

    def test_没有_skills_目录不当成崩溃(self):
        empty = tempfile.TemporaryDirectory()
        self.addCleanup(empty.cleanup)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            code = health.main(["--root", empty.name])
        self.assertEqual(0, code, "体检只报告，不判失败")

    def test_每个_skills_下的目录都会被当成一个条目(self):
        """包括夹具里放校验器的那一个 —— 这样才不会出现“幽灵 skill”被漏掉。"""
        self.make_skill("aaa")
        names = [s["name"] for s in health.scan_repo(self.root)["skills"]]
        self.assertEqual(["aaa", "skill-builder"], names)


class AssetTest(RepoCase):
    def test_被引用的素材不算死文件(self):
        skill = self.make_skill("aaa", assets=("icons/used.svg",))
        with open(os.path.join(skill, "README.md"), "w", encoding="utf-8") as fh:
            fh.write("# aaa\n\n图标：assets/icons/used.svg\n")
        assets = health.scan_repo(self.root)["assets"]
        self.assertTrue(assets["skills/aaa/assets/icons/used.svg"], "被 README 引用了")

    def test_没人引用的素材要算成死文件(self):
        self.make_skill("aaa", assets=("icons/dead.svg",))
        assets = health.scan_repo(self.root)["assets"]
        self.assertFalse(assets["skills/aaa/assets/icons/dead.svg"])
        self.assertIn("skills/aaa/assets/icons/dead.svg", health.summarize(
            health.scan_repo(self.root))["死文件"])

    def test_素材不会因为自己提到自己而变成活文件(self):
        """扫引用时要把 assets 目录自身排除掉，否则每个文件都'引用'了自己。"""
        self.make_skill("aaa", assets=("icons/only.svg",))
        assets = health.scan_repo(self.root)["assets"]
        self.assertFalse(assets["skills/aaa/assets/icons/only.svg"])

    def test_根目录的_assets_也算进来(self):
        target = os.path.join(self.root, "assets", "icons", "root.svg")
        os.makedirs(os.path.dirname(target))
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("x")
        assets = health.scan_repo(self.root)["assets"]
        self.assertIn("assets/icons/root.svg", assets)


class ReportTest(RepoCase):
    def test_分类汇总与正文超限(self):
        self.make_skill("紧", body_lines=145)      # 余量 5 < 10
        self.make_skill("超", body_lines=151)      # 余量 -1
        report = health.scan_repo(self.root)
        groups = health.summarize(report)
        self.assertIn("紧", groups["正文余量偏紧"])
        self.assertIn("超", groups["正文超限"])
        self.assertNotIn("超", groups["正文余量偏紧"], "超限不重复算进偏紧")

    def test_渲染出的表格含每行与汇总(self):
        self.make_skill("aaa")
        text = health.render(health.scan_repo(self.root))
        self.assertIn("aaa", text)
        self.assertIn("值得看的", text)
        self.assertIn("validate_skill.py", text, "要指向真正的结构校验器")

    def test_json_输出可解析且含汇总(self):
        self.make_skill("aaa", readme=False)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = health.main(["--root", self.root, "--json"])
        self.assertEqual(0, code)
        payload = json.loads(buf.getvalue())
        self.assertEqual(["aaa", "skill-builder"], [s["name"] for s in payload["skills"]])
        self.assertEqual(["aaa"], payload["summary"]["缺 README.md"])

    def test_全是干净的时候要说没有(self):
        self.make_skill("aaa", readme=True, evals=True)
        text = health.render(health.scan_repo(self.root))
        self.assertIn("· 没有", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
