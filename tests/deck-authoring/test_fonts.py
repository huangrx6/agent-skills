#!/usr/bin/env python3
"""字体库的回归测试：清单、映射表、识别、格式优先级、渲染接线。

这一层最容易出的错是**"看着成功其实不对"** —— 所以下面这些用例大多不是"功能能用吗"，
而是"它会不会悄悄错"：

- **假阳性**：`--installed` 报"已就位"但其实是回退 → 静默渲出一份字体不对的 deck。
  实测踩过：用短记号做子串匹配，`AR PL UKai` 的 `ar` 撞上 `Regul**ar**`、
  `OPPO **Sans**` 撞上 `Smiley**Sans**`，只下了 4 款却报 8 款。
- **选错文件**：同一个字族有 `.otf` 和 `.ttf` 时挑了 `.otf` → Chrome **完全不嵌**
  （实测出 PDF 零字体、40KB），而 `.ttf` 正常嵌成子集（45KB）。
- **format 关键字写错**：`.otf` 写成 `truetype` → Chrome **直接不用这款字体，且不报错**。
- **映射表指向不存在的字体** → 等于给了一条走不通的路。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/deck-authoring/test_fonts.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")


def _load(name: str):
    key = f"_deck_test_{name}"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, os.path.join(SCRIPTS, f"{name}.py"))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


fonts = _load("fonts")
render = _load("render")


class TestCatalog(unittest.TestCase):
    """清单本身：条数、分类、字段、授权标记。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.cat = json.loads(open(os.path.join(SKILL, "fonts", "catalog.json"),
                                  encoding="utf-8").read())
        cls.fonts = cls.cat["fonts"]

    def test_126_fonts_in_six_categories(self) -> None:
        self.assertEqual(len(self.fonts), 126)
        seen = {}
        for f in self.fonts:
            seen[f["category"]] = seen.get(f["category"], 0) + 1
        self.assertEqual(sorted(seen.values()), [21] * 6, seen)

    def test_names_are_unique_and_numbered(self) -> None:
        names = [f["name"] for f in self.fonts]
        self.assertEqual(len(names), len(set(names)), "有重名")
        self.assertEqual([f["i"] for f in self.fonts], list(range(1, 127)))

    def test_every_entry_has_what_a_user_needs(self) -> None:
        """名称 + 适合什么 + 来源 + 授权 —— 缺任何一项，这条清单就没法用。"""
        for f in self.fonts:
            with self.subTest(name=f["name"]):
                for key in ("name", "for", "source", "license"):
                    self.assertTrue(f.get(key), f"{key} 是空的")
                self.assertIn(f["license"][0], "ABC")
                # 来源可以是复合的（"S5/S7" 表示两个索引都收录了它）
                for part in str(f["source"]).split("/"):
                    self.assertIn(part.strip(), self.cat["sources"],
                                  f"来源 {part!r}（来自 {f['source']!r}）不在 sources 表里")

    def test_license_notice_is_present(self) -> None:
        """授权提醒必须在清单里 —— 免费字体的授权会调整，这不能只写在文档里。"""
        notice = self.cat["notice"]
        self.assertIn("授权", notice)
        self.assertIn("最新", notice)

    def test_match_marks_are_not_invented(self) -> None:
        """`match` 只允许出现在**验证过**的条目上，且不能和别的条目撞车。"""
        marks = [f["match"] for f in self.fonts if f.get("match")]
        self.assertEqual(len(marks), len(set(marks)), f"match 有重复：{marks}")
        for m in marks:
            self.assertGreaterEqual(len(m), 5, f"{m!r} 太短，会误匹配")


class TestMapping(unittest.TestCase):
    """映射表：不许指向清单里没有的字体。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.map = json.loads(open(os.path.join(SKILL, "fonts", "mapping.json"),
                                  encoding="utf-8").read())
        cls.names = [f["name"] for f in fonts.catalog()]

    def test_every_style_is_covered(self) -> None:
        styles = set(render.available_styles()) if hasattr(render, "available_styles") \
            else set(fonts.deckio.list_dirs(os.path.join(SKILL, "styles")))
        missing = styles - set(self.map["styles"])
        self.assertEqual(missing, set(), f"这些风格没有字体映射：{sorted(missing)}")

    def test_every_category_is_covered(self) -> None:
        cats = {f["category"] for f in fonts.catalog()}
        self.assertEqual(cats - set(self.map["categories"]), set())

    def test_style_role_picks_exist_in_the_catalog(self) -> None:
        """每条推荐里点到的字体，要么在**清单**里，要么在**系统字体白名单**里。

        否则这条推荐就是**走不通的路** —— 用户照着写进 style.json，渲染时静默
        回退，而且没有任何提示。系统字体（Menlo / Georgia 那类）允许出现：
        它们跟着操作系统走，映射表把它们当回退项是对的。
        """
        for style, row in self.map["styles"].items():
            for role, pick in row["roles"].items():
                for cand in pick.split("/"):
                    cand = cand.strip().split("（")[0].replace("ⓑ", "").strip()
                    with self.subTest(style=style, role=role, font=cand):
                        allowed = self.names + self.map["system_fonts"]["list"]
                        self.assertTrue(
                            any(cand in n or n.split()[0] in cand for n in allowed),
                            f"{cand!r} 既不在清单里，也不在系统字体白名单里")

    def test_categories_reference_real_styles(self) -> None:
        for key, row in self.map["categories"].items():
            for style in row["styles"]:
                with self.subTest(category=key, style=style):
                    self.assertIn(style, self.map["styles"])


class TestIdentification(unittest.TestCase):
    """认字体：宁可漏，不可错。"""

    def test_norm_strips_everything_non_alphanumeric(self) -> None:
        self.assertEqual(fonts._norm("LXGW WenKai-Regular.ttf"), "lxgwwenkairegularttf")

    def test_short_tokens_are_never_used(self) -> None:
        """**回归**：短记号是假阳性的来源。

        实测：`AR PL UKai` → `ar`、`OPPO Sans` → `sans`、`全字库楷体 TW-Kai` → `tw`，
        这些都会在长文件名里到处撞上（`Regul**ar**` / `Smiley**Sans**`），
        于是只下了 4 款却报"已就位 8 款"。
        """
        self.assertGreaterEqual(fonts.MIN_TOKEN, 5)
        for name in ("AR PL UKai", "OPPO Sans 4.0", "全字库楷体 TW-Kai"):
            entry = fonts.by_name(name)
            self.assertIsNotNone(entry, f"{name} 不在清单里")
            for tok in fonts._file_tokens(entry):
                self.assertGreaterEqual(len(tok), fonts.MIN_TOKEN,
                                        f"{name} 会产出过短的记号 {tok!r}")

    def test_installed_never_reports_more_than_local_files_can_support(self) -> None:
        """自洽性：报"已就位"的款数不可能超过本地字体文件数 ——
        一款文件最多认一款字体（`match` 不重复，见 TestCatalog）。"""
        self.assertLessEqual(len(fonts.installed_names()), len(fonts.local_files()))

    def test_no_cross_match_between_unrelated_names(self) -> None:
        """拿两个只在短记号上相似的名字试：不许互认。"""
        a = fonts.by_name("AR PL UKai")
        b = fonts.by_name("OPPO Sans 4.0")
        fake = "someRegularSansFile"          # 含 'ar' 与 'sans'
        for entry in (a, b):
            toks = fonts._file_tokens(entry)
            self.assertFalse(any(len(t) >= fonts.MIN_TOKEN and t in fonts._norm(fake)
                                 for t in toks),
                             f"{entry['name']} 被 {fake!r} 误认了（记号 {toks}）")


class TestFormatChoice(unittest.TestCase):
    """格式：`.ttf` 优先，`format()` 关键字按后缀给。"""

    def test_css_format_keywords(self) -> None:
        self.assertEqual(fonts.css_format("a.ttf"), "truetype")
        self.assertEqual(fonts.css_format("a.otf"), "opentype")
        self.assertEqual(fonts.css_format("a.ttc"), "opentype")
        self.assertEqual(fonts.css_format("a.woff2"), "woff2")

    def test_ttf_beats_otf_for_the_same_family(self) -> None:
        """**回归**：同一个字族有 `.ttf` 和 `.otf` 时必须挑 `.ttf`。

        实测同一个得意黑：`.otf` 那份 Chrome 完全不嵌（出 PDF 零字体、40KB），
        `.ttf` 那份正常嵌成 `AAAAAA+SmileySans-Oblique`（45KB）。
        """
        picked = fonts._preferred(["/x/SmileySans-Oblique.otf", "/x/SmileySans-Oblique.ttf"])
        self.assertTrue(picked.endswith(".ttf"), picked)

    def test_preferred_handles_empty(self) -> None:
        self.assertIsNone(fonts._preferred([]))


class TestFaceCss(unittest.TestCase):
    """`@font-face` 注入：认清单名，也认真字族名；没有文件就闭嘴。"""

    def _local_entry(self):
        for entry in fonts.catalog():
            if fonts._local_path_for(entry):
                return entry
        self.skipTest("本地没有已下载的字体（先跑 fonts.py --fetch）")
        return None

    def test_emits_for_the_catalog_name(self) -> None:
        entry = self._local_entry()
        css = fonts.face_css([f"{entry['name']}, sans-serif"])
        self.assertIn(f'font-family:"{entry["name"]}"', css)
        self.assertIn("@font-face", css)

    def test_emits_for_the_real_family_name_too(self) -> None:
        """手写 style.json 的人很自然会写字体自己的字族名，不是清单名。

        **回归**：第一版只查拉丁记号，于是写中文清单名（`霞鹜文楷`）的用法全落空 ——
        而且归一化只留 `[a-z0-9]`，中文名归一化后是空串，永远匹配不上。
        实测：display 用得意黑、body 用霞鹜文楷的风格，只注入了前者。
        """
        entry = self._local_entry()
        path = fonts._local_path_for(entry)
        fams = [f for f, p in fonts.local_families().items() if p == path]
        self.assertTrue(fams, "本地字体里读不出字族名")
        for fam in fams:
            with self.subTest(family=fam):
                self.assertIn("@font-face", fonts.face_css([f"{fam}, serif"]))

    def test_silent_for_fonts_without_local_files(self) -> None:
        """本地没有的字体不许注入 —— 注入了指向不存在文件的 @font-face，
        浏览器会静默回退，比不注入更难查。"""
        missing = [f["name"] for f in fonts.catalog() if not fonts._local_path_for(f)]
        self.assertTrue(missing, "本地装了全部 126 款？这条用例的前提变了")
        self.assertEqual(fonts.face_css([", ".join(missing[:5])]), "")

    def test_empty_input_is_safe(self) -> None:
        self.assertEqual(fonts.face_css([]), "")
        self.assertEqual(fonts.face_css([""]), "")


class TestRenderIntegration(unittest.TestCase):
    """端到端：写清单名的风格，产物里真出现 @font-face。"""

    STYLE = "zz_test_fonts"

    @classmethod
    def setUpClass(cls) -> None:
        cls.entry = None
        for entry in fonts.catalog():
            if fonts._local_path_for(entry):
                cls.entry = entry
                break
        if cls.entry is None:
            raise unittest.SkipTest("本地没有已下载的字体（先跑 fonts.py --fetch）")

    def setUp(self) -> None:
        # 收敛成局部变量：setUpClass 已经 skip 过一次，这里只是让"可能为 None"
        # 这件事在类型层面落定，后面就不用反复断言。
        entry = self.entry
        if entry is None:
            raise unittest.SkipTest("本地没有已下载的字体（先跑 fonts.py --fetch）")
        self.font_name = entry["name"]
        self.style_dir = os.path.join(SKILL, "styles", self.STYLE)
        shutil.rmtree(self.style_dir, ignore_errors=True)
        shutil.copytree(os.path.join(SKILL, "styles", "swiss-grid"), self.style_dir)
        self.addCleanup(shutil.rmtree, self.style_dir, True)
        path = os.path.join(self.style_dir, "style.json")
        payload = json.loads(open(path, encoding="utf-8").read())
        payload["label"] = "字体接线测试"
        payload["fonts"]["display"] = f"{self.font_name}, sans-serif"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)

    def test_render_injects_the_font_face(self) -> None:
        """产物里必须有 `@font-face` —— 否则"库"就只是个清单。

        而且**不能靠把字体装进系统**：实测 macOS 的字体缓存不刷新，
        装对了、名字也对了，Chrome 仍然回退。
        """
        spec = {"deck": {"title": "字体接线", "style": self.STYLE, "colorSet": "blue",
                         "slides": [{"type": "title", "title": "标题", "subtitle": "副标题"},
                                    {"type": "end", "title": "谢谢"}]}}
        html = render.render(spec)
        self.assertIn("@font-face", html)
        self.assertIn(f'font-family:"{self.font_name}"', html)
        self.assertIn("file://", html)



class TestFreeOnly(unittest.TestCase):
    """**没有 license 也能用的那一档** —— 判据是严格 A。

    用户的原话是"我只需要免费的字体，我没有什么 license"。所以这一层要保证两件事：
    A/B 那种含糊标记**不算通过**，而且每套风格都有一份完整的纯 A 方案（否则
    "只用免费的"就变成"有几套风格不能用"）。
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.cat = json.loads(open(os.path.join(SKILL, "fonts", "catalog.json"),
                                  encoding="utf-8").read())
        cls.map = json.loads(open(os.path.join(SKILL, "fonts", "mapping.json"),
                                  encoding="utf-8").read())
        cls.license = {f["name"]: f["license"] for f in cls.cat["fonts"]}

    def test_tier_a_is_strict_not_prefix(self) -> None:
        """**回归**：`"A/B"` 在选 A 时不算通过。

        原先写的是 `license.startswith(tier)` —— 于是 `A/B` 一路放过去。而 B 意味着
        署名 / 地区 / 禁商标 / **禁嵌入**等限制；把字体嵌进交付物属于再分发，
        对没有 license 的人来说含糊等于不能用。
        """
        self.assertFalse(fonts.tier_matches("A/B", "A"))
        self.assertFalse(fonts.tier_matches("B", "A"))
        self.assertFalse(fonts.tier_matches("C", "A"))
        self.assertTrue(fonts.tier_matches("A", "A"))
        # all / 空 = 全都要（显式选择）
        self.assertTrue(fonts.tier_matches("B", "all"))
        self.assertTrue(fonts.tier_matches("B", None))

    def test_fetch_defaults_to_free_only(self) -> None:
        self.assertEqual(fonts.DEFAULT_TIER, fonts.FREE_LICENSE)
        self.assertEqual(fonts.FREE_LICENSE, "A")

    def test_a_only_table_covers_every_style_and_role(self) -> None:
        """每套风格的每一档都得有纯 A 方案 —— 缺一档就是那套风格用不了。"""
        a_only = self.map["a_only"]["styles"]
        for style, row in self.map["styles"].items():
            with self.subTest(style=style):
                self.assertIn(style, a_only, f"{style} 没有纯 A 方案")
                self.assertEqual(set(a_only[style]), set(row["roles"]),
                                 f"{style} 的档位对不上")

    def test_every_a_only_pick_is_strictly_free(self) -> None:
        """**最关键的一条**：纯 A 方案里点到的每一款，license 必须恰好是 "A"。

        这一条要是松了，"只用免费的"就变成一句空话 —— 而用户拿不到 license，
        出事的时候是真的出事。
        """
        allowed = set(self.map["system_fonts"]["list"])
        for style, roles in self.map["a_only"]["styles"].items():
            for role, pick in roles.items():
                for cand in pick.split("/"):
                    c = cand.strip().split("（")[0].strip()
                    if c in allowed:
                        continue
                    with self.subTest(style=style, role=role, font=c):
                        hit = next((n for n in self.license
                                    if n == c or c in n or n.split()[0] in c), None)
                        self.assertIsNotNone(hit, f"{c!r} 不在清单里")
                        self.assertEqual(self.license[hit], "A",
                                         f"{c!r} 的授权是 {self.license[hit]}，不是纯 A")

    def test_a_only_does_not_reuse_the_questionable_picks(self) -> None:
        """主映射里那些 B / A/B 的推荐，不许原样出现在纯 A 方案里。"""
        risky = {n for n, code in self.license.items() if code != "A"}
        for style, roles in self.map["a_only"]["styles"].items():
            for role, pick in roles.items():
                for cand in pick.split("/"):
                    c = cand.strip().split("（")[0].strip()
                    with self.subTest(style=style, role=role, font=c):
                        self.assertFalse(
                            any(c == n or c in n for n in risky),
                            f"{c!r} 是 B/C 档，不该出现在纯 A 方案里")

    def test_strict_a_share_is_reported_honestly(self) -> None:
        """清单里严格 A 只占一部分 —— 文档与 CLI 都得说清这件事，不能让人以为
        126 款都是随便用的。"""
        strict = [n for n, code in self.license.items() if code == "A"]
        self.assertLess(len(strict), len(self.license))
        self.assertGreater(len(strict), 50, "严格 A 的款数太少，值得复核清单")

if __name__ == "__main__":
    unittest.main()
