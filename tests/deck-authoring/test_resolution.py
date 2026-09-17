#!/usr/bin/env python3
"""风格 / 品牌的解析根：**deck 项目 = spec 所在目录**，cwd 只是兜底。

为什么单独一个文件：两条解析链（`render.style_roots` / `deck.brand_roots`）"认**项目目录**"
这条必须被钉住 —— 只认 `os.getcwd()` 时，"从别的目录跑同一个 spec"会找不到
它自己带的风格与品牌，而报错文案还指着"deck 项目的 styles/<名>/"。

这里把不变量钉死（四条）：

1. 给了项目目录 → 项目里的 `styles/` `brands/` 命中，**与 cwd 无关**；
2. 不给 → 回到 cwd 兜底，列风格 / 列品牌的旧行为不变；
3. 端到端：子进程在**别的 cwd**、且**清掉 `DECK_STYLES`/`DECK_BRANDS`** 跑
   `render.py` —— 不清掉就是夹具根抢先命中，这条会退化成空转（测试里最贵的错）；
4. 早退模式（`--contract` / `--repair` / `--candidates`）同给 → 必须报错，
   不能静默只跑第一个（"有其他模式静默失效"正是产品级缺陷本缺陷的反面）。

跑法：
    python3 -m unittest discover -s tests
    python3 tests/deck-authoring/test_resolution.py
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
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
FIXTURES_DIR = os.path.join(HERE, "fixtures")
SCRIPTS = os.path.join(SKILL, "scripts")

# 夹具风格当"现成的一套"用（工具链不内置任何风格）。名字故意与夹具里的
# 风格名不同：这样"找到了"只可能来自本项目目录，不会与夹具根混淆。
STYLE_SRC = os.path.join(FIXTURES_DIR, "styles", "minimal-baseline")
STYLE_NAME = "zres-face"
BRAND_NAME = "zres-acme"
BRAND_PRIMARY = "#123456"

LOGO_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="120" height="40">'
            '<rect width="120" height="40" fill="#123456"/></svg>')

SPEC = {
    "deck": {
        "title": "解析根", "style": STYLE_NAME, "brand": BRAND_NAME,
        "colorSet": "blue", "seed": 3,
        "slides": [{"type": "title", "title": "一页", "subtitle": "最小可渲"}],
    }
}


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _make_project(root: str) -> str:
    """建一个**完整 deck 项目**：spec + styles/<名>/ + brands/<名>/ 同处一室。"""
    proj = os.path.join(root, "proj")
    style = os.path.join(proj, "styles", STYLE_NAME)
    brand = os.path.join(proj, "brands", BRAND_NAME)
    os.makedirs(style)
    os.makedirs(brand)
    for name in ("style.json", "skin.css"):
        shutil.copyfile(os.path.join(STYLE_SRC, name), os.path.join(style, name))
    for name in ("logo.svg", "logo-inverse.svg"):
        with open(os.path.join(brand, name), "w", encoding="utf-8") as fh:
            fh.write(LOGO_SVG)
    # 色板键必须与 spec 的 deck.colorSet 同名才会合并（品牌按同名键赢）
    with open(os.path.join(brand, "brand.json"), "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "label": "ZRES", "logo": "logo.svg",
                   "logoInverse": "logo-inverse.svg",
                   "colorSets": {"blue": {"primary": BRAND_PRIMARY,
                                          "secondary": "#654321",
                                          "background": "#FFFFFF",
                                          "text": "#111111"}}},
                  fh, ensure_ascii=False, indent=2)
    spec_path = os.path.join(proj, "deck-spec.json")
    with open(spec_path, "w", encoding="utf-8") as fh:
        json.dump(SPEC, fh, ensure_ascii=False, indent=2)
    return spec_path


def _clean_env() -> dict:
    """子进程的环境：**去掉夹具根** —— 留着的话夹具会抢先命中，测的就成了夹具。"""
    return {k: v for k, v in os.environ.items()
            if k not in ("DECK_STYLES", "DECK_BRANDS")}


class TestProjectDirResolution(unittest.TestCase):
    """`load_style` / `deck.load` 的项目目录参数。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="deck-res-")
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.spec_path = _make_project(self.root)
        self.project = os.path.dirname(self.spec_path)
        # 一个**没有** styles/ 与 brands/ 的 cwd（兜底根在这里什么也找不到）
        self.elsewhere = os.path.join(self.root, "elsewhere")
        os.makedirs(self.elsewhere)
        self._cwd = os.getcwd()
        os.chdir(self.elsewhere)
        self.addCleanup(os.chdir, self._cwd)

    def test_style_found_from_project_dir_not_cwd(self):
        render = _load("_res_render", os.path.join(SCRIPTS, "render.py"))
        style = render.load_style(STYLE_NAME, self.project)
        self.assertEqual(style["name"], STYLE_NAME)
        self.assertIn("colorSets", style["tokens"])
        # 同一份风格，不给项目目录 → 从 cwd 找不到（这正是修复前的行为）
        with self.assertRaises(SystemExit):
            render.load_style(STYLE_NAME)

    def test_style_folder_and_names_use_project_dir(self):
        render = _load("_res_render2", os.path.join(SCRIPTS, "render.py"))
        folder = render.style_folder(STYLE_NAME, self.project)
        self.assertEqual(os.path.realpath(folder),
                         os.path.realpath(os.path.join(self.project, "styles", STYLE_NAME)))
        self.assertIn(STYLE_NAME, render.style_names(self.project))
        self.assertNotIn(STYLE_NAME, render.style_names())

    def test_brand_found_from_project_dir_not_cwd(self):
        deck = _load("_res_deck", os.path.join(SCRIPTS, "deck.py"))
        brand = deck.load(BRAND_NAME, self.project)
        self.assertEqual(brand.get("colorSets", {}).get("blue", {}).get("primary"),
                         BRAND_PRIMARY)
        self.assertIn(BRAND_NAME, deck.available(self.project))
        self.assertEqual(os.path.realpath(deck.brand_dir(BRAND_NAME, self.project)),
                         os.path.realpath(os.path.join(self.project, "brands", BRAND_NAME)))
        # 解析根的顺序：环境变量根最优先，**项目根紧随其后、且在 cwd 兜底根之前**
        # （不钉下标：同名测试模块可能已经设了 DECK_BRANDS 夹具根，那是文档里
        #  契约的“显式入口”，排在项目根前面是对的）
        roots = [os.path.realpath(r) for r in deck.brand_roots(self.project)]
        proj_root = os.path.realpath(os.path.join(self.project, "brands"))
        cwd_root = os.path.realpath(os.path.join(self.elsewhere, "brands"))
        self.assertIn(proj_root, roots)
        self.assertLess(roots.index(proj_root), roots.index(cwd_root),
                        "项目根必须先于 cwd 兜底根 —— 否则换个 cwd 就换了品牌")
        with self.assertRaises(SystemExit):
            deck.load(BRAND_NAME)


class TestEndToEndFromForeignCwd(unittest.TestCase):
    """真跑 CLI：cwd 在别处、环境里也没有夹具根。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="deck-res-e2e-")
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.spec_path = _make_project(self.root)
        self.elsewhere = os.path.join(self.root, "elsewhere")
        os.makedirs(self.elsewhere)

    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "render.py"), *args],
            cwd=self.elsewhere, env=_clean_env(),
            capture_output=True, text=True, timeout=600)
        return proc

    def test_render_from_foreign_cwd_uses_the_spec_own_style_and_brand(self):
        out = os.path.join(self.root, "out.html")
        proc = self._run([self.spec_path, "--out", out])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        with open(out, encoding="utf-8") as fh:
            html = fh.read()
        # 品牌合并生效 = 项目里的品牌真的被读到（不是"渲染器用了兜底色"）
        self.assertIn(BRAND_PRIMARY, html)

    def test_render_without_the_project_style_fails_loudly(self):
        """反向对照：风格不在项目里 → 必须失败。证明上一条测的是项目目录。"""
        shutil.rmtree(os.path.join(os.path.dirname(self.spec_path), "styles"))
        proc = self._run([self.spec_path, "--out", os.path.join(self.root, "no.html")])
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("没有风格", proc.stdout + proc.stderr)

    def test_mutually_exclusive_modes_are_rejected(self):
        """--contract / --repair / --candidates 同给 → 报错，不静默只跑一个。"""
        proc = self._run([self.spec_path, "--out", os.path.join(self.root, "x.html"),
                          "--candidates", "--contract"])
        self.assertNotEqual(proc.returncode, 0)
        text = proc.stdout + proc.stderr
        self.assertIn("互斥", text)
        # 单独给仍然是正常模式（不是把开关整体关掉）
        solo = self._run([self.spec_path, "--out", os.path.join(self.root, "y.html"),
                          "--contract"])
        self.assertEqual(solo.returncode, 0, solo.stdout + solo.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
