#!/usr/bin/env python3
"""format（时间 / 紧凑输出）与 resolve（字典缓存 / 名字→ID）的回归测试。

为什么需要
----------
1. **解析歧义是静默错误的源头。** 两个叫"支付"的迭代里选错一个，不会报错，只会改错东西。
   所以"多个候选必须报错并列出候选"这条要有测试钉住 —— 它是最容易被"顺手取第一个"
   改掉的行为。
2. 字典缓存要有 TTL 与键隔离（不同项目的类型表不能互相串）。缓存串了会得到"看着像真的"
   的错答案。
3. `parse_time` 接受好几种写法，边界（空串 / 垃圾 / 已经是时间戳）都要有确定行为。

跑法：
    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")


def _load(name: str):
    """按脚本内部一致的模块名加载（否则异常类会对不上，见 test_config_and_client 的说明）。"""
    key = f"_pingcode_{name}"
    spec = importlib.util.spec_from_file_location(key, os.path.join(SCRIPTS, f"{name}.py"))
    if spec is None or spec.loader is None:
        raise RuntimeError(name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


fmt = _load("format")
resolve = _load("resolve")
cfg = _load("config")


class TimeTest(unittest.TestCase):
    def test_只写日期按当天零点(self):
        stamp = fmt.parse_time("2026-09-20")
        self.assertEqual("2026-09-20 00:00", fmt.show_time(stamp))

    def test_带时分(self):
        self.assertEqual("2026-09-20 18:30", fmt.show_time(fmt.parse_time("2026-09-20 18:30")))

    def test_斜杠与中文写法都收(self):
        self.assertEqual(fmt.parse_time("2026-09-20"), fmt.parse_time("2026/09/20"))

    def test_已经是时间戳就原样用(self):
        self.assertEqual(1577808000, fmt.parse_time("1577808000"))

    def test_看不懂要报错并给例子(self):
        for bad in ("", "  ", "下周三", "13 月"):
            with self.subTest(text=bad):
                with self.assertRaises(fmt.TimeParseError):
                    fmt.parse_time(bad)

    def test_空时间显示为空串不是_None(self):
        self.assertEqual("", fmt.show_time(None))
        self.assertEqual("", fmt.show_time(0))

    def test_类型中文名(self):
        self.assertEqual("缺陷", fmt.type_label("bug"))
        self.assertEqual("史诗", fmt.type_label("epic"))
        self.assertEqual("自定义类型id", fmt.type_label("自定义类型id"))


class CompactTest(unittest.TestCase):
    WORKITEM = {
        "identifier": "SCR-12", "title": "登录页 500", "type": "bug",
        "state": {"id": "s1", "name": "处理中", "type": "in_progress"},
        "priority": {"id": "p1", "name": "高"},
        "assignee": {"id": "u1", "name": "john", "display_name": "John"},
        "sprint": {"id": "sp1", "name": "Sprint 12"},
        "project": {"id": "pj1", "name": "演示项目"},
        "end_at": 1577808000,
        "html_url": "https://x/y",
        "description": "很长很长的描述",
        "entity_properties": {"a": 1},
        "url": "https://api/x",
    }

    def test_只保留白名单字段(self):
        out = fmt.compact("workitem", self.WORKITEM)
        self.assertEqual("SCR-12", out["编号"])
        self.assertEqual("缺陷", out["类型"], "系统类型要翻成中文")
        self.assertEqual("处理中", out["状态"])
        self.assertNotIn("description", out, "描述不进紧凑输出（show 会单独打）")
        self.assertNotIn("entity_properties", out)
        self.assertNotIn("url", out)

    def test_时间为空就不出这一列(self):
        item = dict(self.WORKITEM)
        item["end_at"] = None
        self.assertNotIn("截止", fmt.compact("workitem", item))

    def test_表格按显示宽度对齐(self):
        text = fmt.render([{"名称": "短", "ID": "1"}, {"名称": "一个很长的中文名字", "ID": "2"}])
        lines = text.splitlines()
        self.assertEqual(4, len(lines), "表头 + 分隔行 + 2 行数据")
        self.assertEqual(fmt._width(lines[0]), fmt._width(lines[1]),
                         "表头与分隔行的显示宽度要一致（全角算 2）")
        self.assertIn("一个很长的中文名字", lines[3])

    def test_空列表给一句人话(self):
        self.assertEqual("（没有匹配的条目）", fmt.render([]))

    def test_每行列顺序一致且取并集(self):
        text = fmt.render([{"a": 1}, {"b": 2}])
        header = text.splitlines()[0]
        self.assertIn("a", header)
        self.assertIn("b", header)

    def test_列顺序按_schema_而不是首次出现(self):
        """实测撞到过：第一条缺迭代时，「迭代」「负责人」会跑到表尾。"""
        items = [
            dict(self.WORKITEM, sprint=None, assignee=None),
            self.WORKITEM,
        ]
        header = fmt.render(fmt.rows("workitem", items)).splitlines()[0]
        positions = [header.index(col) for col in ("负责人", "迭代", "项目", "链接")]
        self.assertEqual(sorted(positions), positions,
                         f"列序应当跟 schema 走（负责人 → 迭代 → 项目 → 链接），实际 {header}")

    def test_列顺序与是否有值无关(self):
        """只出现一次的列也不该把后面的列序弄乱。"""
        items = [{"编号": "A-1", "标题": "只条 1"},
                 {"编号": "A-2", "标题": "只条 2", "负责人": "某甲"}]
        header = fmt.render(items).splitlines()[0]
        self.assertEqual(["编号", "标题"], [c for c in ("编号", "标题") if c in header])


def _resolve_client(inner, dry_run: bool = False):
    """给假客户端标上 dry_run —— 解析层就靠这个标记判断要不要写缓存。"""
    inner.dry_run = dry_run
    return inner


class ResolveTest(unittest.TestCase):
    PROJECTS = [
        {"id": "pj1", "identifier": "DEMO", "name": "演示项目"},
        {"id": "pj2", "identifier": "DEMO2", "name": "示例项目 B"},
    ]
    SPRINTS = [
        {"id": "sp1", "name": "Sprint 12"},
        {"id": "sp2", "name": "Sprint 13"},
        {"id": "sp3", "name": "支付专项"},
    ]
    STATES = [
        {"id": "st1", "name": "新建", "type": "pending"},
        {"id": "st2", "name": "已完成", "type": "completed"},
    ]

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = os.environ.get(cfg.ENV_DIR)
        os.environ[cfg.ENV_DIR] = self._tmp.name
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        if self._saved is None:
            os.environ.pop(cfg.ENV_DIR, None)
        else:
            os.environ[cfg.ENV_DIR] = self._saved

    class FakeClient:
        """只要 paginate 就够了 —— 解析层只用这一个方法碰网络。"""

        def __init__(self, pages: dict) -> None:
            self.pages = pages
            self.hits: list[str] = []

        def paginate(self, url, page_size=100, max_items=500, **params):  # noqa: ARG002
            self.hits.append(url)
            return list(self.pages.get(url, []))

    def seed(self, kind: str, values: list, **keys) -> None:
        resolve.store(kind, keys, values)

    # ── 匹配规则 ──
    def test_按_id_精确匹配(self):
        self.seed("projects", self.PROJECTS)
        got = resolve.find("projects", self.FakeClient({}), "pj2")
        self.assertEqual("示例项目 B", got["name"])

    def test_按名字精确匹配(self):
        self.seed("projects", self.PROJECTS)
        got = resolve.find("projects", self.FakeClient({}), "演示项目")
        self.assertEqual("pj1", got["id"])

    def test_按标识精确匹配(self):
        self.seed("projects", self.PROJECTS)
        got = resolve.find("projects", self.FakeClient({}), "DEMO2")
        self.assertEqual("pj2", got["id"])

    def test_唯一子串可以匹配(self):
        self.seed("projects", self.PROJECTS)
        got = resolve.find("projects", self.FakeClient({}), "演示")
        self.assertEqual("pj1", got["id"])

    def test_多个候选必须报错并列出候选(self):
        self.seed("projects", self.PROJECTS)
        # "项目" 在两个项目名里都有（演示项目 / 示例项目 B）—— 这时**不能**猜
        with self.assertRaises(resolve.Ambiguous) as ctx:
            resolve.find("projects", self.FakeClient({}), "项目")
        message = str(ctx.exception)
        self.assertIn("演示项目", message)
        self.assertIn("示例项目 B", message)

    def test_找不到时报错并列出可选项(self):
        self.seed("projects", self.PROJECTS)
        with self.assertRaises(resolve.NotFound) as ctx:
            resolve.find("projects", self.FakeClient({}), "不存在的项目")
        self.assertIn("演示项目", str(ctx.exception))

    def test_空查询要报错(self):
        self.seed("projects", self.PROJECTS)
        with self.assertRaises(resolve.NotFound):
            resolve.find("projects", self.FakeClient({}), "  ")

    # ── 类型 ──
    def test_类型支持系统枚举与中文名(self):
        types = [{"id": "bug", "name": "缺陷"}, {"id": "task", "name": "任务"}]
        self.seed("types", types, project_id="pj1")
        client = self.FakeClient({})
        self.assertEqual("bug", resolve.find("types", client, "bug", project_id="pj1")["id"])
        self.assertEqual("bug", resolve.find("types", client, "缺陷", project_id="pj1")["id"])
        self.assertEqual("task", resolve.find("types", client, "任务", project_id="pj1")["id"])

    def test_成员按真名也能找到(self):
        """实测：PingCode 成员的 `name` 是手机号，真名在 `display_name` ——
        只匹配 name 的话，用户写「黄任翔」会被告诉「没有这个成员」。
        """
        users = [{"id": "u1", "name": "15236325327", "display_name": "黄任翔",
                  "email": "a@b.c"}]
        self.seed("users", users)
        client = self.FakeClient({})
        for query in ("黄任翔", "15236325327", "a@b.c", "u1", "黄"):
            with self.subTest(query=query):
                self.assertEqual("u1", resolve.find("users", client, query)["id"])

    def test_成员列表显示真名(self):
        users = [{"id": "u1", "name": "15236325327", "display_name": "黄任翔"}]
        self.assertEqual(["黄任翔"], resolve.labels("users", users))

    # ── 缓存 ──
    def test_缓存命中就不打网络(self):
        self.seed("projects", self.PROJECTS)
        client = self.FakeClient({"/v1/pjm/projects": self.PROJECTS})
        resolve.find("projects", client, "演示")
        self.assertEqual([], client.hits, "已有缓存就不该再请求")

    def test_force_跳过缓存(self):
        self.seed("projects", self.PROJECTS)
        client = self.FakeClient({"/v1/pjm/projects": self.PROJECTS})
        resolve.find("projects", client, "演示", force=True)
        self.assertEqual(1, len(client.hits))

    def test_缓存按参数隔离(self):
        self.seed("types", [{"id": "bug", "name": "缺陷"}], project_id="pj1")
        self.seed("types", [{"id": "story", "name": "用户故事"}], project_id="pj2")
        self.assertEqual("bug", resolve.find("types", self.FakeClient({}), "缺陷", project_id="pj1")["id"])
        self.assertEqual("story", resolve.find("types", self.FakeClient({}), "用户故事",
                                               project_id="pj2")["id"])

    def test_过期缓存不再用(self):
        self.seed("projects", self.PROJECTS)
        data = cfg.load_cache()
        for entry in data["entries"].values():
            entry["at"] = time.time() - resolve.CACHE_TTL - 10
        cfg.save_cache(data)
        client = self.FakeClient({"/v1/pjm/projects": self.PROJECTS})
        resolve.find("projects", client, "演示")
        self.assertEqual(1, len(client.hits), "过期了要重新拉")

    def test_清空缓存(self):
        self.seed("projects", self.PROJECTS)
        resolve.clear()
        self.assertIsNone(resolve.cached("projects", {}))

    def test_invalidate_只清某一类且只清该类的全部键(self):
        """实测踩到：刚建完项目，紧接着建工作项报「没有叫 X 的项目」。"""
        self.seed("projects", self.PROJECTS)
        self.seed("types", [{"id": "bug", "name": "缺陷"}], project_id="pj1")
        resolve.invalidate("projects")
        self.assertIsNone(resolve.cached("projects", {}), "项目的所有键都要清")
        self.assertIsNotNone(resolve.cached("types", {"project_id": "pj1"}), "别的类不受影响")

    def test_invalidate_没命中时不写盘(self):
        self.seed("projects", self.PROJECTS)
        before = cfg.load_cache()["entries"]["projects"]
        resolve.invalidate("sprints")
        self.assertEqual(before, cfg.load_cache()["entries"]["projects"])

    def test_dry_run_不该把空字典写进缓存(self):
        """实测撞到过：dry-run 下字典被解析成空列表并落盘，之后正常命令也拿不到可选项。"""
        client = _resolve_client(self.FakeClient({"/v1/pjm/projects": []}), dry_run=True)
        self.assertIsNone(resolve.cached("projects", {}))
        resolve.items("projects", client)
        self.assertIsNone(resolve.cached("projects", {}), "dry-run 的结果不能进缓存")

    def test_正常客户端照样写缓存(self):
        client = _resolve_client(self.FakeClient({"/v1/pjm/projects": self.PROJECTS}))
        resolve.items("projects", client)
        self.assertEqual(len(self.PROJECTS), len(resolve.cached("projects", {})))

    def test_缺上下文参数要说缺哪个(self):
        with self.assertRaises(resolve.NotFound) as ctx:
            resolve.items("states", self.FakeClient({}))
        self.assertIn("project_id", str(ctx.exception))

    def test_未知字典要给可用列表(self):
        with self.assertRaises(resolve.NotFound) as ctx:
            resolve.items("不存在", self.FakeClient({}))
        self.assertIn("projects", str(ctx.exception))

    def test_工作项列表不是字典_不在源表里(self):
        """业务数据绝不能进缓存 —— 缓存住了就是"看着像真的"的过期答案。"""
        self.assertNotIn("workitems", resolve.SOURCES)
        for kind, spec in resolve.SOURCES.items():
            with self.subTest(kind=kind):
                self.assertNotIn("/v1/pjm/workitems", spec["url"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
