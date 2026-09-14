#!/usr/bin/env python3
"""端点表的契约测试（scripts/endpoints.py + scripts/api_index.py）。

为什么需要
----------
1. 这个 skill 的全部网络调用都建立在 `scripts/endpoints.py` 这份**生成表**上。表错了，
   错法是「用了官方文档里不存在的路径」—— 而 mock 掉网络的测试抓不到。第三方的那个
   pingcode 实现写死了 `/v1/project/work_items`（官方当前文档里不存在，PJM 前缀是
   `/v1/pjm/`），因为它的测试 mock 了 `urlopen`，错路径照样全绿。所以这里有一条测试
   专门盯「本 skill 用到的端点必须在表里」，另有一条把那些错路径钉成**必须不存在**。
2. `build()` 负责拼路径与查询占位符。参数名拼错时要当场报错，而不是拼出一个注定 404
   的 URL —— 那正是参考实现里发生的事。
3. 生成器自己也会坏，坏了的表现是「静默生成一份错的表」。所以正常化、排序、diff、
   `--check` 的退出码都要有测试守住边界。

跑法
----
    python3 -m unittest discover -s tests -v
    python3 tests/test_endpoints.py
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
# 测试住在仓库顶层 `tests/<skill>/`（**刻意不在 skill 目录里**：AI 调用 skill 时读的是
# `skills/<skill>/` 那棵树，测试放在里面会被顺手读进去）。
# 所以从 `tests/<skill>/` 往上两级到仓库根，再进 `skills/<skill>/`。
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
# 测试住在仓库顶层 `tests/<skill>/`（**刻意不在 skill 目录里**：AI 调用 skill 时读的是
# `skills/<skill>/` 那棵树，测试放在里面会被顺手读进去）。
SKILL_ROOT = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")
DEV_TOOLS = os.path.join(SKILL_ROOT, "dev-tools")


def _load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


api = _load(os.path.join(SCRIPTS, "api_index.py"), "_test_api_index")
endpoints = api.endpoints
gen = _load(os.path.join(DEV_TOOLS, "gen_endpoints.py"), "_test_gen_endpoints")


# 本 skill 的类型化子命令会调的端点。这里的每一条都必须能在官方表里解析到 ——
# 少一条就会在真实调用时 404，而那是本文件最想提前拦住的失败。
USED = [
    ("GET", "/v1/auth/token", {"grant_type": "client_credentials"}),
    ("GET", "/v1/auth/token", {"grant_type": "authorization_code"}),
    ("GET", "/v1/auth/token", {"grant_type": "refresh_token"}),
    ("GET", "/v1/myself", None),
    ("GET", "/v1/directory/users", None),
    ("GET", "/v1/pjm/processes", None),
    ("GET", "/v1/pjm/projects", None),
    ("POST", "/v1/pjm/projects", None),
    ("GET", "/v1/pjm/projects/{project_id}", None),
    ("PATCH", "/v1/pjm/projects/{project_id}", None),
    ("GET", "/v1/pjm/projects/{project_id}/progress", None),
    ("GET", "/v1/pjm/projects/{project_id}/members", None),
    ("GET", "/v1/pjm/projects/{project_id}/sprints", None),
    ("POST", "/v1/pjm/projects/{project_id}/sprints", None),
    ("PATCH", "/v1/pjm/projects/{project_id}/sprints/{sprint_id}", None),
    ("GET", "/v1/pjm/projects/{project_id}/boards", None),
    ("GET", "/v1/pjm/project/states", None),
    ("GET", "/v1/pjm/workitems", None),
    ("POST", "/v1/pjm/workitems", None),
    ("PATCH", "/v1/pjm/workitems", None),
    ("POST", "/v1/pjm/workitems/search", None),
    # 附件三件套（此前一条都没进 USED —— 契约测试其实没守住它们）
    ("GET", "/v1/attachments", {"principal_type": "workitem", "principal_id": "x"}),
    ("POST", "/v1/attachments", {"principal_type": "workitem", "principal_id": "x"}),
    ("DELETE", "/v1/attachments/{attachment_id}",
     {"principal_type": "workitem", "principal_id": "x"}),
    ("GET", "/v1/pjm/workitems/{workitem_id}", None),
    ("PATCH", "/v1/pjm/workitems/{workitem_id}", None),
    ("DELETE", "/v1/pjm/workitems/{workitem_id}", None),
    ("GET", "/v1/pjm/workitem/types", None),
    ("GET", "/v1/pjm/workitem/states", None),
    ("GET", "/v1/pjm/workitem/priorities", None),
    ("GET", "/v1/pjm/workitem/tags", None),
    ("GET", "/v1/comments", None),
    ("POST", "/v1/comments", None),
]

# 参考实现里写过、官方当前文档里**不存在**的路径。钉成"必须不存在"，
# 以后有人照着那份实现抄回来时测试会直接红。
STALE_PATHS = [
    ("GET", "/v1/project/projects"),
    ("GET", "/v1/project/work_items"),
    ("GET", "/v1/project/work_item/types"),
    ("GET", "/v1/project/work_item/states"),
]

FIXTURE_SOURCE = [
    {"type": "GET", "url": "/v1/pjm/workitems", "group": "工作项", "name": "获取工作项列表",
     "scopes": [{"name": "pcp:read:pjm:workitem"}], "permission": [{"name": "企业令牌/用户令牌"}]},
    {"type": "POST", "url": "/v1/pjm/workitems", "group": "工作项", "name": "创建一个工作项",
     "scopes": [{"name": "pcp:write:pjm:workitem"}], "permission": [{"name": "企业令牌/用户令牌"}]},
    {"type": "GET", "url": "/v1/myself", "group": "个人", "name": "获取个人信息",
     "scopes": [{"name": "pcp:read:account:personal"}], "permission": [{"name": "用户令牌"}]},
    {"group": "概述", "name": "欢迎使用", "description": "<p>纯文档页，没有 method/url</p>"},
]


class TableShapeTest(unittest.TestCase):
    """生成表本身的形状。表坏了，上层全是错的。"""

    def test_条目数与文件自报的计数一致(self):
        self.assertEqual(endpoints.ENDPOINT_COUNT, len(endpoints.ENTRIES))
        self.assertGreater(len(endpoints.ENTRIES), 100, "官方表不可能只有这么点接口")

    def test_每条都是_v1_路径且方法合法(self):
        for e in api.ENTRIES:
            self.assertTrue(e.url.startswith("/v1/"), e.url)
            self.assertIn(e.method, gen.METHODS, e.url)

    def test_method_url_不重复(self):
        seen = [(e.method, e.url) for e in api.ENTRIES]
        self.assertEqual(len(seen), len(set(seen)), "(method, url) 必须唯一，否则 require 会误判歧义")

    def test_来源与指纹都记下来了(self):
        self.assertTrue(endpoints.SOURCE_URL.startswith("https://"))
        self.assertTrue(endpoints.SOURCE_SHA256.startswith("sha256:"))
        self.assertRegex(endpoints.FETCHED_AT, r"^\d{4}-\d{2}-\d{2}$")

    def test_关键_scope_都在表里(self):
        have = set(api.scopes())
        for scope in (
            "pcp:read:pjm:workitem", "pcp:write:pjm:workitem",
            "pcp:read:pjm:project", "pcp:write:pjm:project",
            "pcp:read:account:personal", "pcp:read:global:team",
            "pcp:read:pjm:configuration",
        ):
            self.assertIn(scope, have)


class UsedEndpointsContractTest(unittest.TestCase):
    """本 skill 用到的端点必须在官方表里存在。"""

    def test_用到的端点都能解析(self):
        for method, path, query in USED:
            with self.subTest(endpoint=f"{method} {path}"):
                entry = api.require(method, path, query)
                self.assertEqual(path, entry.path)

    def test_代码段那个附件变体在表里且没有查询参数(self):
        """`POST /v1/attachments` 有两个变体：**无查询参数**的是「代码段」，带
        principal_type/principal_id 的是「文件」。前一个没法用 `require(query)` 选
        （空 query 不做窄化），所以这里直接盯住「两个变体都在、且哪个是空的」。
        """
        variants = api.find(method="POST", path="/v1/attachments")
        templates = sorted(tuple(sorted(k for k, _ in v.query_template)) for v in variants)
        self.assertEqual([(), ("principal_id", "principal_type")], templates)

    def test_写操作要的是写_scope(self):
        for method, path in (("POST", "/v1/pjm/workitems"),
                             ("PATCH", "/v1/pjm/workitems/{workitem_id}"),
                             ("DELETE", "/v1/pjm/workitems/{workitem_id}"),
                             ("POST", "/v1/pjm/projects"),
                             ("PATCH", "/v1/pjm/projects/{project_id}")):
            with self.subTest(endpoint=f"{method} {path}"):
                entry = api.require(method, path)
                joined = " ".join(entry.scopes)
                self.assertIn(":write:", joined, f"{method} {path} 的 scope 应为写权限")

    def test_参考实现的过期路径必须不存在(self):
        """这条测试是那轮调研的结论，不是猜测。

        第三方实现用 /v1/project/*；官方当前文档里 PJM 是 /v1/pjm/ 且 workitems 无下划线。
        错误能活下来是因为它的测试 mock 了网络 —— 这里不 mock，直接查表。
        """
        for method, path in STALE_PATHS:
            with self.subTest(endpoint=f"{method} {path}"):
                with self.assertRaises(api.UnknownEndpoint):
                    api.require(method, path)

    def test_myself_只认用户令牌(self):
        entry = api.require("GET", "/v1/myself")
        self.assertEqual(("用户令牌",), entry.perms)
        self.assertTrue(entry.needs_user_token)
        self.assertFalse(entry.needs_enterprise_token)


class RequireTest(unittest.TestCase):
    def test_取不到时报错并给最接近的候选(self):
        with self.assertRaises(api.UnknownEndpoint) as ctx:
            api.require("GET", "/v1/pjm/work_item")
        msg = str(ctx.exception)
        self.assertIn("/v1/pjm/work_item", msg)
        self.assertIn("/v1/pjm/workitems", msg, "报错要给出候选，否则调用方只能猜")

    def test_同路径多变体要报歧义并列出变体(self):
        with self.assertRaises(api.AmbiguousEndpoint) as ctx:
            api.require("GET", "/v1/auth/token")
        msg = str(ctx.exception)
        for grant in ("client_credentials", "authorization_code", "refresh_token"):
            self.assertIn(grant, msg)

    def test_补上_query_就能唯一定位(self):
        entry = api.require("GET", "/v1/auth/token", {"grant_type": "refresh_token"})
        self.assertIn("grant_type=refresh_token", entry.url)
        self.assertEqual(("grant_type",), tuple(k for k, _v in entry.query_template))

    def test_方法大小写不敏感(self):
        self.assertEqual(api.require("get", "/v1/myself").method, "GET")

    def test_find_支持前缀与分组(self):
        self.assertTrue(api.find(path_prefix="/v1/pjm/"))
        self.assertTrue(api.find(group="工作项"))
        self.assertEqual([], api.find(path="/v1/不存在的路径"))


class BuildTest(unittest.TestCase):
    def test_填路径占位符(self):
        url = api.build("/v1/pjm/workitems/{workitem_id}", workitem_id="abc123")
        self.assertEqual("/v1/pjm/workitems/abc123", url)

    def test_填查询占位符(self):
        url = api.build(
            "/v1/pjm/workitem/states?project_id={project_id}&workitem_type_id={workitem_type_id}",
            project_id="p1", workitem_type_id="bug")
        self.assertEqual("/v1/pjm/workitem/states?project_id=p1&workitem_type_id=bug", url)

    def test_缺占位符要报错(self):
        with self.assertRaises(api.PathParamError) as ctx:
            api.build("/v1/pjm/workitems/{workitem_id}")
        self.assertIn("workitem_id", str(ctx.exception))

    def test_多给参数名要报错(self):
        """拼错参数名（比如把 assignee_id 写成 assignee_ids）必须当场报错。"""
        with self.assertRaises(api.PathParamError) as ctx:
            api.build("/v1/pjm/workitems/{workitem_id}", workitem_id="a", assignee_ids="u1")
        self.assertIn("assignee_ids", str(ctx.exception))

    def test_值要转义(self):
        url = api.build("/v1/pjm/workitems/{workitem_id}", workitem_id="a b/c")
        self.assertEqual("/v1/pjm/workitems/a%20b%2Fc", url)

    def test_占位符识别(self):
        self.assertEqual(("workitem_id",), api.path_placeholders("/v1/pjm/workitems/{workitem_id}"))
        self.assertEqual(
            ("project_id", "workitem_type_id"),
            api.placeholders("/v1/pjm/workitem/states?project_id={project_id}&workitem_type_id={workitem_type_id}"))


class GeneratorTest(unittest.TestCase):
    """生成器自己也要有边界测试：它坏了是静默生成一份错表。"""

    def test_正常化会跳过纯文档页并排序(self):
        raw = json.dumps(FIXTURE_SOURCE).encode("utf-8")
        entries, total, docpages = gen.normalize(raw)
        self.assertEqual(4, total)
        self.assertEqual(1, docpages, "没有 method/url 的条目是纯文档页，不进表")
        self.assertEqual(3, len(entries))
        urls = [e[1] for e in entries]
        self.assertEqual(["/v1/myself", "/v1/pjm/workitems", "/v1/pjm/workitems"], urls,
                         "排序要按 (路径, 方法, url)，同一路径的 GET 排在 POST 前")
        self.assertEqual(("用户令牌",), entries[0][3])

    def test_顶层不是数组要报错(self):
        with self.assertRaises(ValueError):
            gen.normalize(b'{"not": "a list"}')

    def test_坏_json_要报错而不是静默出空表(self):
        with self.assertRaises(ValueError):
            gen.normalize(b"not json at all")

    def test_渲染是幂等的(self):
        raw = json.dumps(FIXTURE_SOURCE).encode("utf-8")
        entries, total, docpages = gen.normalize(raw)
        a = gen.render(entries, total, docpages, "sha256:x", "2026-01-01")
        b = gen.render(entries, total, docpages, "sha256:x", "2026-01-01")
        self.assertEqual(a, b)
        self.assertIn("不要手改", a)
        self.assertIn("sha256:x", a)

    def test_diff_报增删改(self):
        old = [("GET", "/a", (), (), "g", "旧名"), ("GET", "/b", (), (), "g", "要删的")]
        new = [("GET", "/a", (), ("s",), "g", "旧名"), ("GET", "/c", (), (), "g", "新增的")]
        lines = "\n".join(gen.diff(old, new))
        self.assertIn("+ GET /c", lines)
        self.assertIn("- GET /b", lines)
        self.assertIn("~ GET /a", lines)

    def test_check_无漂移返回0_有漂移返回1(self):
        raw = json.dumps(FIXTURE_SOURCE).encode("utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "api.json")
            out = os.path.join(tmp, "endpoints.py")
            with open(src, "wb") as fh:
                fh.write(raw)

            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(1, gen.main(["--input", src, "--out", out, "--check"]),
                                 "生成文件不存在时 --check 必须失败")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(0, gen.main(["--input", src, "--out", out]))
                self.assertEqual(0, gen.main(["--input", src, "--out", out, "--check"]),
                                 "刚生成完再 --check 必须无漂移")

            # 改模版注释也要能被 --check 发现 —— 只在端点集合上比会漏掉这类漂移
            with open(out, encoding="utf-8") as fh:
                text = fh.read()
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(text.replace("不要手改", "被手改了"))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(1, gen.main(["--input", src, "--out", out, "--check"]),
                                 "文件被手改过，--check 必须报漂移")

    def test_check_只差抓取日期不算漂移(self):
        """--check 是**跨天**跑的：文件里记的是抓取那天，而今天是新的一天。

        实测：生成日的次日跑 --check 会报「模版或元信息有变化」—— 天天虚报的检查
        会被无视，而它只该报官方文档的漂移。
        """
        raw = json.dumps(FIXTURE_SOURCE).encode("utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "api.json")
            out = os.path.join(tmp, "endpoints.py")
            with open(src, "wb") as fh:
                fh.write(raw)
            with redirect_stdout(io.StringIO()):
                gen.main(["--input", src, "--out", out])
            with open(out, encoding="utf-8") as fh:
                text = fh.read()
            real_at = gen.fetch_date_for_check(text, "2099-01-01")
            self.assertIn(real_at, text)
            # 日期在生成物里出现两处（人类可读的「抓取时间」行 + FETCHED_AT），两处都要改：
            # 只改一处会留下真实的不一致，而检查把它当漂移是对的。
            with open(out, "w", encoding="utf-8") as fh:      # 假装它是 2020 年抓的
                fh.write(text.replace(real_at, "2020-01-01"))
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = gen.main(["--input", src, "--out", out, "--check"])
            self.assertEqual(0, rc, "只差抓取日期不算漂移：" + buf.getvalue())
            self.assertIn("无漂移", buf.getvalue())

    def test_取抓取日期_读不到就退回今天(self):
        self.assertEqual("2026-05-06",
                         gen.fetch_date_for_check("FETCHED_AT = '2026-05-06'\n", "2099-01-01"))
        self.assertEqual("2099-01-01", gen.fetch_date_for_check("没有这一行\n", "2099-01-01"))

    def test_读不到输入文件返回1(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "o.py")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as err:
                rc = gen.main(["--input", os.path.join(tmp, "没有这个文件.json"), "--out", out])
            self.assertEqual(1, rc)
            self.assertIn("没有这个文件.json", err.getvalue())

    def test_顶层不是数组时报错信息带原因(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "bad.json")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write('{"not": "a list"}')
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as err:
                rc = gen.main(["--input", src, "--out", os.path.join(tmp, "o.py")])
            self.assertEqual(1, rc)
            self.assertIn("数组", err.getvalue())

    def test_本地快照跑出来的表能过一遍_require(self):
        """生成物与查询门要能接上：这是两个文件之间的真实接口。"""
        raw = json.dumps(FIXTURE_SOURCE).encode("utf-8")
        entries, total, docpages = gen.normalize(raw)
        self.assertTrue(all(len(e) == 6 for e in entries), "条目结构变了，api_index.Entry 也要跟着改")
        self.assertTrue(all(isinstance(e[2], tuple) and isinstance(e[3], tuple) for e in entries))


if __name__ == "__main__":
    unittest.main(verbosity=2)
