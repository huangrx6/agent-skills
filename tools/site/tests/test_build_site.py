"""站点生成器：内容解析、链接改写与整站构建。

这些测试守的是「页面能不能从现有文档稳定生成」；视觉呈现仍需浏览器截图人工检查。
"""

from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SCRIPT = REPO / "tools" / "build_site.py"

spec = importlib.util.spec_from_file_location("_test_build_site", SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError(f"加载不了 {SCRIPT}")
site = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = site
spec.loader.exec_module(site)


class TestContentParsing(unittest.TestCase):
    def test_root_readme_yields_three_categories_and_all_skills(self):
        _, categories = site.load_skills()
        self.assertEqual(
            ["内容与表达", "知识与工作", "开发与学习"],
            [category["name"] for category in categories],
        )
        names = [item["name"] for category in categories for item in category["skills"]]
        self.assertEqual(11, len(names))
        self.assertEqual(len(names), len(set(names)))
        self.assertIn("email-composer", names)
        deck = next(
            item
            for category in categories
            for item in category["skills"]
            if item["name"] == "deck-authoring"
        )
        self.assertEqual("演示文稿制作", deck["subtitle"])
        self.assertTrue(deck["lead"])
        self.assertTrue(deck["body"])

    def test_markdown_alerts_are_localized(self):
        text = "> [!NOTE]\n> 安装不等于依赖。\n"
        converted = site.preprocess_alerts(text)
        self.assertIn("> **注意**", converted)
        self.assertNotIn("[!NOTE]", converted)


class TestMarkdownRendering(unittest.TestCase):
    def test_headings_tables_and_toc(self):
        html, toc = site.render_markdown(
            "## 安装\n\n内容\n\n### 子节\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n",
            "",
            "tool",
        )
        self.assertIn('<h2 id="安装">安装</h2>', html)
        self.assertIn('<h3 id="子节">子节</h3>', html)
        self.assertIn('<div class="table-wrap"><table>', html)
        self.assertEqual([(2, "安装", "安装"), (3, "子节", "子节")], toc)

    def test_skill_links_point_to_github(self):
        html, _ = site.render_markdown(
            "[SKILL.md](SKILL.md) ![图](assets/a.png) [锚点](#x) [网页](https://example.com)\n",
            "skills/deck-authoring",
            "skill",
        )
        self.assertIn(
            'href="https://github.com/huangrx6/agent-skills/blob/main/skills/deck-authoring/SKILL.md"',
            html,
        )
        self.assertIn(
            'src="https://raw.githubusercontent.com/huangrx6/agent-skills/main/skills/deck-authoring/assets/a.png"',
            html,
        )
        self.assertIn('href="#x"', html)
        self.assertIn('href="https://example.com"', html)

    def test_root_links_map_to_site_pages(self):
        html, _ = site.render_markdown(
            "[deck](skills/deck-authoring/README.md) [roadmap](ROADMAP.md) "
            "[readme](README.md) [tool](tools/install_skills.py)\n",
            "",
            "root",
        )
        self.assertIn('href="skills/deck-authoring.html"', html)
        self.assertIn('href="roadmap.html"', html)
        self.assertIn('href="../index.html"', html)
        self.assertIn(
            'href="https://github.com/huangrx6/agent-skills/blob/main/tools/install_skills.py"',
            html,
        )


class TestBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "site"
        cls.pages = site.build(cls.out)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_builds_expected_pages(self):
        self.assertEqual(19, self.pages)
        for relative in (
            "index.html",
            "404.html",
            "docs/index.html",
            "docs/getting-started.html",
            "docs/skills/index.html",
            "docs/guide.html",
            "docs/maintenance.html",
            "docs/roadmap.html",
            "docs/skills/deck-authoring.html",
            "assets/site.css",
            "assets/site.js",
            "assets/favicon.svg",
            ".nojekyll",
        ):
            self.assertTrue((self.out / relative).is_file(), relative)

    def test_no_template_tokens_and_no_broken_links(self):
        self.assertEqual([], site.check_output(self.out, site.load_skills()[1]))
        for path in self.out.rglob("*.html"):
            self.assertNotIn("@@", path.read_text(encoding="utf-8"))

    def test_skill_page_has_one_h1_and_no_manual_toc(self):
        html = (self.out / "docs/skills/deck-authoring.html").read_text(encoding="utf-8")
        self.assertEqual(1, len(re.findall(r"<h1\b", html)))
        self.assertNotIn("<summary><strong>目录</strong></summary>", html)

    def test_dark_default_and_theme_toggle(self):
        home = (self.out / "index.html").read_text(encoding="utf-8")
        docs = (self.out / "docs/index.html").read_text(encoding="utf-8")
        for page in (home, docs):
            self.assertIn('<html lang="zh-CN" data-theme="dark">', page)
            self.assertIn('content="#0f1012"', page)
            self.assertIn("let theme = 'dark';", page)
            self.assertIn("data-theme-toggle", page)
            self.assertIn("agent-skills-theme", page)
            self.assertNotIn("prefers-color-scheme", page)
        css = (self.out / "assets/site.css").read_text(encoding="utf-8")
        self.assertIn('html[data-theme="dark"]', css)
        self.assertNotIn("@media (prefers-color-scheme: dark)", css)
        js = (self.out / "assets/site.js").read_text(encoding="utf-8")
        self.assertIn("data-theme-toggle", js)
        self.assertIn("agent-skills-theme", js)

    def test_header_and_docs_share_content_width(self):
        css = (self.out / "assets/site.css").read_text(encoding="utf-8")
        self.assertIn("--container: 1180px;", css)
        self.assertEqual(2, css.count("width: min(var(--container), calc(100% - 48px));"))

    def test_link_checker_reports_missing_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "index.html").write_text(
                '<html><head><title>x</title></head><body><a href="missing.html">x</a></body></html>',
                encoding="utf-8",
            )
            problems = site.check_output(out, [])
            self.assertTrue(any("链接目标不存在" in item for item in problems))


if __name__ == "__main__":
    unittest.main()
