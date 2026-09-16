#!/usr/bin/env python3
"""`scripts/icons_fetch.py`（官方素材库目录的搜索与下载）的测试。

**全部不联网**：官方索引用假数据喂进去，缓存用临时目录 —— 测的是"解析与判定"，
不是"能不能连上 GitHub"（那条靠 --list/--search 的实测，见 references/icons.md）。

守三件事：
1. **库名解析**：精确名 / slug / 唯一前缀都要能中，歧义前缀必须**不猜**（返回 None）；
2. **中文能搜到英文项名**（别名表）—— 官方库里项名全是英文，没这层模型就搜不到；
3. **缓存命中不重复下载**；缓存目录规则与 `icons.py` **同源**（只留一份真话）。

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
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills",
                     os.path.basename(HERE))


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


F = _load("_diagram_icons_fetch", os.path.join(SKILL, "scripts", "icons_fetch.py"))
I = _load("_diagram_icons_for_fetch_test", os.path.join(SKILL, "scripts", "icons.py"))

FAKE_INDEX = [
    {"name": "IT icons", "source": "who/it-icons.excalidrawlib",
     "authors": [{"name": "某作者"}],
     "itemNames": ["Database", "Server", "Firewall", "User", "Cloud", "Timer"]},
    {"name": "IT icons pro", "source": "who/it-icons-pro.excalidrawlib",
     "authors": [{"name": "另一作者"}], "itemNames": ["Database Cluster"]},
    {"name": "Kubernetes icons", "source": "who/k8s.excalidrawlib",
     "authors": [{"name": "第三作者"}], "itemNames": ["Pod", "Service", "Ingress"]},
]


class TestSlugAndLookup(unittest.TestCase):

    def test_slug_is_stable_and_readable(self):
        self.assertEqual("it-icons", F.slug("IT icons"))
        self.assertEqual("aws-architecture-icons", F.slug("AWS Architecture Icons"))
        self.assertEqual("library", F.slug("!!!"))

    def test_exact_name_and_slug_both_hit(self):
        self.assertEqual("IT icons", F.find_library(FAKE_INDEX, "IT icons")["name"])
        self.assertEqual("IT icons", F.find_library(FAKE_INDEX, "it-icons")["name"])

    def test_unique_prefix_hits_but_ambiguous_prefix_does_not(self):
        """`--get kubernetes` 该中（唯一前缀）；`it-icons` 前缀有歧义时必须返回 None。"""
        self.assertEqual("Kubernetes icons",
                         F.find_library(FAKE_INDEX, "kubernetes")["name"])
        self.assertIsNone(F.find_library(FAKE_INDEX, "it"),
                          "前缀有歧义时不能猜一个")
        self.assertIsNone(F.find_library(FAKE_INDEX, "根本不存在"))


class TestSearch(unittest.TestCase):

    def test_english_keyword_matches_item_names(self):
        hits = F.search(FAKE_INDEX, "database")
        self.assertTrue(hits)
        self.assertIn("Database", hits[0][1])

    def test_chinese_keyword_falls_back_to_english_terms(self):
        """中文关键词要靠别名表落到英文项名上（官方库里没有中文）。"""
        hits = F.search(FAKE_INDEX, "数据库")
        self.assertTrue(hits, "「数据库」应当能搜到 Database —— 别名表没生效")
        self.assertIn("Database", hits[0][1])

    def test_chinese_queue_and_security(self):
        index = FAKE_INDEX + [{"name": "杂项", "source": "x/y.excalidrawlib",
                               "authors": [], "itemNames": ["Message Queue", "Key"]}]
        self.assertIn("Message Queue", F.search(index, "队列")[0][1])
        self.assertIn("Key", F.search(index, "密钥")[0][1])

    def test_no_match_returns_empty(self):
        self.assertEqual([], F.search(FAKE_INDEX, "完全不存在的图形"))


class TestCacheAndDownload(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cache = self._tmp.name
        self._old = os.environ.get(I.ICON_CACHE_ENV)
        os.environ[I.ICON_CACHE_ENV] = self.cache
        self.addCleanup(self._restore)

    def _restore(self):
        if self._old is None:
            os.environ.pop(I.ICON_CACHE_ENV, None)
        else:
            os.environ[I.ICON_CACHE_ENV] = self._old
        self._tmp.cleanup()

    def _write_cached(self, name: str, items: list[str] | None = None) -> str:
        path = os.path.join(self.cache, F.slug(name) + ".excalidrawlib")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"type": "excalidrawlib", "version": 2,
                       "libraryItems": [{"id": f"i{k}", "name": n, "elements": []}
                                        for k, n in enumerate(items or ["Database"])]}, fh)
        return path

    def test_cache_rule_is_shared_with_icons(self):
        """缓存目录只留一份真话：两边必须算出同一个目录。"""
        self.assertEqual(self.cache, F.cache_dir())
        self.assertEqual(F.cache_dir(), I.cache_dir())

    def test_library_name_resolves_to_the_cached_file(self):
        path = self._write_cached("IT icons")
        got, source = I.library_path("it-icons")
        self.assertEqual(path, got)
        self.assertIn("缓存", source)

    def test_unknown_library_name_lists_what_is_cached(self):
        self._write_cached("IT icons")
        got, source = I.library_path("不存在的库")
        self.assertIsNone(got)
        self.assertIn("it-icons", source, "报错要把缓存里有的列出来")
        self.assertIn("icons_fetch.py", source, "报错要给出下一步动作")

    def test_cached_library_is_not_downloaded_again(self):
        """缓存命中就不该再联网 —— 用不存在的 URL 也应当成功返回。"""
        self._write_cached("IT icons")
        entry = {"name": "IT icons", "source": "who/never.excalidrawlib",
                 "authors": [], "itemNames": ["Database"]}
        got = F.download(entry, self.cache)
        self.assertTrue(got["ok"])
        self.assertTrue(got.get("cached"))
        self.assertEqual("cache", got["stage"])

    def test_download_writes_provenance_next_to_the_file(self):
        """出处要落盘（作者 / 来源 / 官方页面）—— 第三方作品不能"来路不明"。"""
        self._write_cached("IT icons")
        entry = {"name": "IT icons", "source": "who/it-icons.excalidrawlib",
                 "authors": [{"name": "某作者"}], "itemNames": ["Database"]}
        F.download(entry, self.cache)
        meta_path = os.path.join(self.cache, "it-icons.meta.json")
        with open(meta_path, encoding="utf-8") as fh:
            meta = json.load(fh)
        self.assertEqual("某作者", meta["authors"][0]["name"])
        self.assertIn("excalidraw-libraries", meta["url"])
        self.assertIn("libraries.excalidraw.com", meta["page"])

    def test_download_failure_returns_a_receipt_not_an_exception(self):
        """**不联网**测失败路径：把取数据那一步换成抛 URLError。"""
        import urllib.error

        def boom(url, timeout=0):
            raise urllib.error.URLError("假装断网")

        old_get = F._get
        setattr(F, "_get", boom)
        self.addCleanup(setattr, F, "_get", old_get)
        entry = {"name": "连不上的库", "source": "who/x.excalidrawlib",
                 "authors": [], "itemNames": []}
        got = F.download(entry, self.cache, force=True)
        self.assertFalse(got["ok"])
        self.assertEqual("download", got["stage"])
        self.assertIn("断网", got["message"])


class TestCli(unittest.TestCase):
    """CLI 层：用假索引替掉联网那一步，测输出与退出码。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_env = os.environ.get(I.ICON_CACHE_ENV)
        os.environ[I.ICON_CACHE_ENV] = self._tmp.name
        self._old_fetch = F.fetch_index
        # 动态加载的模块，类型检查器不知道属性 —— 用 setattr/getattr 更直白
        setattr(F, "fetch_index", lambda cache, refresh=False: FAKE_INDEX)
        self.addCleanup(self._restore)

    def _restore(self):
        setattr(F, "fetch_index", self._old_fetch)
        if self._old_env is None:
            os.environ.pop(I.ICON_CACHE_ENV, None)
        else:
            os.environ[I.ICON_CACHE_ENV] = self._old_env
        self._tmp.cleanup()

    def test_list_with_keyword(self):
        self.assertEqual(0, F.main(["--list", "kubernetes"]))

    def test_search_exit_codes(self):
        self.assertEqual(0, F.main(["--search", "数据库"]))
        self.assertEqual(1, F.main(["--search", "完全不存在的东西"]))

    def test_get_unknown_library_suggests_close_names(self):
        self.assertEqual(1, F.main(["--get", "IT iconz"]))

    def test_no_action_prints_help(self):
        self.assertEqual(2, F.main([]))


if __name__ == "__main__":
    unittest.main()
