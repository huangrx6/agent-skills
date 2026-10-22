#!/usr/bin/env python3
"""CLI 层（scripts/pingcode.py）的回归测试。

为什么需要
----------
命令行是唯一被人和 Agent 直接调用的面 —— 出错的代价最大，而且**大多不会抛异常**：
写错的项目、写错的状态、少一个 --yes，都会"看起来成功了"。

这里的做法是把**真实 Client 的传输换掉**（注入假的 `opener`），而不是 mock
`urllib.request.urlopen`：重试、分页、参数拼装、dry-run、错误翻译全都还是真代码在跑。
参考实现 mock 的是 `urlopen` 本身，所以路径写错、参数写错都测不出来。

覆盖的关键行为：
  · dry-run 真的不发请求，并且把要发的 body 打出来
  · 创建 / 改状态 / 删除分别打到正确的端点，body 里的 id 是**解析后的**真 id
  · 状态名不存在时给出该类型的可用状态列表（而不是只报一句失败）
  · 项目名有歧义时列候选并中止（不能猜）
  · 删除缺 --yes 时拒绝
  · 上下文（当前项目）真的被 create 用上
  · 逃生口 `api` 会把官方文档里不存在的路径拦下来

跑法：
    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from email.message import Message

HERE = os.path.dirname(os.path.abspath(__file__))
# 测试住在仓库顶层 `tests/<skill>/`（**刻意不在 skill 目录里**：AI 调用 skill 时读的是
# `skills/<skill>/` 那棵树，测试放在里面会被顺手读进去）。
# 所以从 `tests/<skill>/` 往上两级到仓库根，再进 `skills/<skill>/`。
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")


def _load(name: str):
    """按脚本内部一致的模块名加载（否则异常类会对不上）。"""
    key = f"_pingcode_{name}"
    spec = importlib.util.spec_from_file_location(key, os.path.join(SCRIPTS, f"{name}.py"))
    if spec is None or spec.loader is None:
        raise RuntimeError(name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


pc = _load("pingcode")
cfg = _load("config")
resolve = _load("resolve")


class FakeResponse(io.BytesIO):
    def __init__(self, payload, status: int = 200) -> None:
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        super().__init__(body)
        self.status = status
        self.headers: dict = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def header_message(headers: dict) -> Message:
    message = Message()
    for key, value in headers.items():
        message[key] = str(value)
    return message


def http_error(code: int, payload) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x/y", code, "err", header_message({}),
                                  io.BytesIO(json.dumps(payload).encode("utf-8")))


class Router:
    """按 (method, url 里的一段) 路由；更长的 needle 先匹配。"""

    def __init__(self, routes: dict) -> None:
        self.routes = sorted(routes.items(), key=lambda kv: len(kv[0][1]), reverse=True)
        self.calls: list[tuple[str, str, object, dict[str, str]]] = []

    def __call__(self, request, timeout=None):  # noqa: ARG002
        body = request.data
        parsed: object = None
        if body:
            try:
                parsed = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                # multipart 之类的二进制正文：原样记下来，别在这里炸
                parsed = body
        self.calls.append((request.method, request.full_url, parsed,
                           dict(request.headers)))
        for (method, needle), payload in self.routes:
            if method == request.method and needle in request.full_url:
                # payload 可以是：响应体 / 异常实例 / 函数（按调用次序造不同响应）
                if callable(payload):
                    payload = payload(request)
                if isinstance(payload, Exception):
                    raise payload
                return FakeResponse(payload)
        raise http_error(404, {"message": f"测试里没有为 {request.method} {request.full_url} 配路由"})

    def find(self, method: str, needle: str) -> list:
        return [c for c in self.calls if c[0] == method and needle in c[1]]


WORKITEM = {
    "id": "w1", "identifier": "DOC-1", "title": "登录页 500", "type": "bug",
    "state": {"id": "st1", "name": "新建", "type": "pending"},
    "priority": {"id": "pr1", "name": "高"},
    "project": {"id": "pj1", "name": "演示项目"},
    "assignee": {"id": "u1", "display_name": "John"},
    "end_at": 1577808000, "html_url": "https://x/w1",
}

PROJECTS = [
    {"id": "pj1", "identifier": "DEMO", "name": "演示项目"},
    {"id": "pj2", "identifier": "DEMO2", "name": "示例项目 B"},
]
TYPES = [{"id": "epic", "name": "史诗"}, {"id": "feature", "name": "特性"},
         {"id": "story", "name": "用户故事"}, {"id": "task", "name": "任务"},
         {"id": "bug", "name": "缺陷"}]
STATES = [{"id": "st1", "name": "新建", "type": "pending"},
          {"id": "st2", "name": "已完成", "type": "completed"}]
# 项目状态是**另一张表**（/v2/pjm/project/states），与工作项状态不同
PROJECT_STATES = [{"id": "ps1", "name": "未开始"}, {"id": "ps2", "name": "正常"}]
SPRINTS = [{"id": "sp1", "name": "Sprint 12"}]
PRIORITIES = [{"id": "pr1", "name": "高"}]


class CliCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = {k: os.environ.get(k) for k in
                       (cfg.ENV_DIR, cfg.ENV_TOKEN, cfg.ENV_ID, cfg.ENV_SECRET, cfg.ENV_HOST)}
        for key in self._saved:
            os.environ.pop(key, None)
        os.environ[cfg.ENV_DIR] = self._tmp.name
        self.addCleanup(self._restore_env)

        cfg.write_private(cfg.path_of(cfg.CREDENTIALS),
                          {"host": "open.pingcode.com", "auth_mode": "user",
                           "client_id": "cid", "client_secret": "sec"})
        cfg.save_token({"access_token": "tok", "expires_in": 2592000}, "user")
        self.seed_dictionaries()

    def _restore_env(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def seed_dictionaries(self) -> None:
        resolve.store("projects", {}, PROJECTS)
        resolve.store("types", {"project_id": "pj1"}, TYPES)
        resolve.store("states", {"project_id": "pj1", "workitem_type_id": "bug"}, STATES)
        resolve.store("sprints", {"project_id": "pj1"}, SPRINTS)
        resolve.store("priorities", {"project_id": "pj1"}, PRIORITIES)
        resolve.store("users", {}, [{"id": "u1", "name": "john", "display_name": "John"}])
        # V2：故事点是否可写取决于该类型的属性方案。任务没有 story_points，缺陷有。
        resolve.store("workitem_properties", {"project_id": "pj1", "workitem_type_id": "task"},
                       [{"id": "description"}, {"id": "start"}])
        resolve.store("workitem_properties", {"project_id": "pj1", "workitem_type_id": "bug"},
                       [{"id": "description"}, {"id": "story_points"},
                        {"id": "estimated_workload"}, {"id": "remaining_workload"}])

    # ── 运行与断言 ──
    def run_cli(self, argv: list[str], routes: dict | None = None) -> tuple[int, str, str, Router]:
        router = Router(routes or {})
        original = pc._client.Client

        class Bound(original):  # type: ignore[misc, valid-type]
            def __init__(self, *args, **kwargs):
                kwargs["opener"] = router
                super().__init__(*args, **kwargs)

        pc._client.Client = Bound
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = pc.main(argv)
        finally:
            pc._client.Client = original
        return code, out.getvalue(), err.getvalue(), router

    # ── 只读 ──
    def test_列出项目(self):
        code, out, _err, _router = self.run_cli(
            ["project", "list"], {("GET", "/v2/pjm/projects"): {"values": PROJECTS, "total": 2}})
        self.assertEqual(0, code)
        self.assertIn("演示项目", out)
        self.assertIn("示例项目 B", out)

    def test_项目列表默认看不到已_归档_删除的(self):
        """实测：项目被删后从默认列表里消失，会让人以为“项目没了”。"""
        code, _out, _err, router = self.run_cli(
            ["project", "list"],
            {("GET", "/v2/pjm/projects"): {"values": PROJECTS, "total": 1}})
        self.assertEqual(0, code)
        url = router.find("GET", "/v2/pjm/projects")[0][1]
        self.assertNotIn("include_deleted", url)

        code, _out, _err, router = self.run_cli(
            ["project", "list", "--all"],
            {("GET", "/v2/pjm/projects"): {"values": PROJECTS, "total": 3}})
        self.assertEqual(0, code)
        url = router.find("GET", "/v2/pjm/projects")[0][1]
        self.assertIn("include_archived=true", url)
        self.assertIn("include_deleted=true", url)

    def test_列出某项目的类型(self):
        code, out, _err, _router = self.run_cli(["list", "types", "--project", "演示项目"])
        self.assertEqual(0, code)
        self.assertIn("缺陷", out)
        self.assertIn("bug", out)

    def test_项目列表_limit_真的能限制条数(self):
        code, out, _err, _router = self.run_cli(
            ["project", "list", "--limit", "1"],
            {("GET", "/v2/pjm/projects"): {"values": PROJECTS, "total": 2}})
        self.assertEqual(0, code)
        self.assertIn("演示项目", out)
        self.assertNotIn("示例项目 B", out)
        self.assertIn("最多显示 1 个", out)

    def test_列出某类型的属性方案(self):
        code, _out, _err, router = self.run_cli(
            ["list", "workitem_properties", "--project", "演示项目", "--type", "bug",
             "--no-cache"],
            {("GET", "/v2/pjm/projects"):
                 {"values": PROJECTS, "total": len(PROJECTS)},
             ("GET", "/v2/pjm/workitem/workitem_types"):
                 {"values": TYPES, "total": len(TYPES)},
             ("GET", "/v2/pjm/workitem/workitem_properties"):
                 {"values": [{"id": "story_points", "name": "故事点"}], "total": 1}})
        self.assertEqual(0, code)
        url = router.find("GET", "/v2/pjm/workitem/workitem_properties")[0][1]
        self.assertIn("project_id=pj1", url)
        self.assertIn("workitem_type_id=bug", url)

    def test_看一个工作项_带描述(self):
        item = dict(WORKITEM, description="详细的复现步骤")
        code, out, _err, _router = self.run_cli(["workitem", "show", "DOC-1"],
                                                {("GET", "/v2/pjm/workitems"): {"values": [item]}})
        self.assertEqual(0, code)
        self.assertIn("DOC-1", out)
        self.assertIn("缺陷", out)
        self.assertIn("详细的复现步骤", out)
        # 编号形状（DOC-1）应当**直接**走 identifier 查询，不去撞那个注定 400 的直取
        self.assertEqual([], [c for c in _router.calls if "/v2/pjm/workitems/DOC-1" in c[1]])

    def test_按_id_看工作项走直取(self):
        code, out, _err, router = self.run_cli(
            ["workitem", "show", "w1"], {("GET", "/v2/pjm/workitems/w1"): WORKITEM})
        self.assertEqual(0, code)
        self.assertIn("DOC-1", out)
        self.assertEqual(1, len(router.find("GET", "/v2/pjm/workitems/w1")))

    def test_直取撞上_400_也要兜底到编号查询(self):
        """实测得到：给编号时官方返回 400 + code=100317，不是 404。

        这里用一个**不像编号**的 ref（`w9abc`），所以会先直取，再兜底。
        """
        item = dict(WORKITEM, title="兜底找到的")
        code, out, _err, router = self.run_cli(
            ["workitem", "show", "w9abc"],
            {("GET", "/v2/pjm/workitems/w9abc"): http_error(400, {"code": "100317",
                                                                  "message": "工作项资源不存在"}),
             ("GET", "/v2/pjm/workitems"): {"values": [item]}})
        self.assertEqual(0, code)
        self.assertIn("兜底找到的", out)
        self.assertEqual(1, len(router.find("GET", "/v2/pjm/workitems/w9abc")))

    def test_编号也找不到时要说清楚(self):
        code, _out, err, _router = self.run_cli(
            ["workitem", "show", "DOC-404"],
            {("GET", "/v2/pjm/workitems"): {"values": []}})
        self.assertEqual(1, code)
        self.assertIn("DOC-404", err)

    def test_删掉之后默认看不到_加_all_才看得到(self):
        """实测：DELETE 是**软删除**，若默认带上 include_deleted，刚删的会像没删一样又显示出来。"""
        code, _out, err, router = self.run_cli(
            ["workitem", "show", "DOC-1"],
            {("GET", "/v2/pjm/workitems"): {"values": []}})
        self.assertEqual(1, code)
        self.assertIn("--all", err, "要告诉用户可能是被删了以及怎么看")
        querystring = router.find("GET", "/v2/pjm/workitems")[0][1]
        self.assertNotIn("include_deleted=true", querystring, "默认不能查已删除的")

        code, out, _err, router = self.run_cli(
            ["workitem", "show", "DOC-1", "--all"],
            {("GET", "/v2/pjm/workitems"): {"values": [dict(WORKITEM, is_deleted=1)]}})
        self.assertEqual(0, code)
        self.assertIn("已被删除", out)
        self.assertIn("include_deleted=true", router.find("GET", "/v2/pjm/workitems")[0][1])

    def test_full_出原始_json(self):
        code, out, _err, _router = self.run_cli(["workitem", "show", "DOC-1", "--full"],
                                                {("GET", "/v2/pjm/workitems"): {"values": [WORKITEM]}})
        self.assertEqual(0, code)
        self.assertIn('"identifier": "DOC-1"', out)

    # ── 创建 ──
    def test_创建的_dry_run_不发请求且打出_body(self):
        code, out, _err, router = self.run_cli(
            ["workitem", "create", "--project", "演示项目", "--type", "bug",
             "--title", "登录报 500", "--assignee", "John", "--start", "2026-09-20",
             "--dry-run"])
        self.assertEqual(0, code)
        self.assertIn("--dry-run", out)
        self.assertIn('"project_id": "pj1"', out)
        self.assertIn('"type_id": "bug"', out)
        self.assertIn('"assignee_id": "u1"', out, "人名要解析成 id")
        self.assertIn("登录报 500", out)
        self.assertEqual([], router.calls, "dry-run 不能真的发请求")

    def test_创建打对了端点且_id_是解析后的(self):
        created = dict(WORKITEM, id="w9", identifier="DOC-9", title="登录报 500")
        code, out, _err, router = self.run_cli(
            ["workitem", "create", "--project", "演示项目", "--type", "缺陷",
             "--title", "登录报 500", "--start", "2026-09-20", "--end", "2026-09-30"],
            {("POST", "/v2/pjm/workitems"): created})
        self.assertEqual(0, code)
        posts = router.find("POST", "/v2/pjm/workitems")
        self.assertEqual(1, len(posts))
        body = posts[0][2]
        self.assertEqual("pj1", body["project_id"])
        self.assertEqual("bug", body["type_id"], "中文名「缺陷」要解析成 bug")
        self.assertEqual("2026-09-20", __import__("datetime").datetime.fromtimestamp(
            body["start"]["date"]).strftime("%Y-%m-%d"))
        self.assertEqual(0, body["start"]["with_time"])
        self.assertIn("DOC-9", out)

    def test_创建工作项_V2_日期和工作量字段(self):
        created = dict(WORKITEM, id="w9", identifier="DOC-9", title="登录报 500")
        code, _out, _err, router = self.run_cli(
            ["workitem", "create", "--project", "演示项目", "--type", "bug",
             "--title", "登录报 500", "--start", "2026-09-20 18:30",
             "--story-points", "3", "--estimated-workload", "8"],
            {("POST", "/v2/pjm/workitems"): created})
        self.assertEqual(0, code)
        body = router.find("POST", "/v2/pjm/workitems")[0][2]
        self.assertEqual(1, body["start"]["with_time"], "带时分秒要标 with_time=1")
        self.assertEqual({"story_points": 3, "estimated_workload": 8}, body["properties"])
        self.assertNotIn("start_at", body)
        self.assertNotIn("story_points", body)

    def test_任务类型没有故事点要当场拒绝(self):
        code, _out, err, router = self.run_cli(
            ["workitem", "create", "--project", "演示项目", "--type", "task",
             "--title", "x", "--story-points", "1"])
        self.assertEqual(1, code)
        self.assertIn("属性方案", err)
        self.assertIn("story_points", err)
        self.assertEqual([], router.find("POST", "/v2/pjm/workitems"), "不能发一个必 400 的请求")

    def test_任务类型没有预估工作量也要当场拒绝(self):
        code, _out, err, router = self.run_cli(
            ["workitem", "create", "--project", "演示项目", "--type", "task",
             "--title", "x", "--estimated-workload", "2"])
        self.assertEqual(1, code)
        self.assertIn("属性方案", err)
        self.assertIn("estimated_workload", err)
        self.assertEqual([], router.find("POST", "/v2/pjm/workitems"))

        project = {"id": "pj9", "identifier": "NEW", "name": "新项目",
                   "template_type": "scrum"}
        code, _out, _err, router = self.run_cli(
            ["project", "create", "--type", "scrum", "--name", "新项目",
             "--identifier", "NEW", "--start", "2026-09-01"],
            {("POST", "/v2/pjm/projects"): project})
        self.assertEqual(0, code)
        body = router.find("POST", "/v2/pjm/projects")[0][2]
        self.assertEqual("scrum", body["template_type"])
        self.assertNotIn("type", body)
        self.assertEqual(0, body["start"]["with_time"])

    def test_项目列表按_template_type_过滤(self):
        code, _out, _err, router = self.run_cli(
            ["project", "list", "--type", "scrum"],
            {("GET", "/v2/pjm/projects"): {"values": PROJECTS, "total": 2}})
        self.assertEqual(0, code)
        url = router.find("GET", "/v2/pjm/projects")[0][1]
        self.assertIn("template_type=scrum", url)
        self.assertNotIn("&type=scrum", url)

    def test_编号查询_V2_拆成数字和项目_id(self):
        code, _out, _err, router = self.run_cli(
            ["workitem", "show", "DEMO-1"],
            {("GET", "/v2/pjm/workitems"): {"values": [WORKITEM]}})
        self.assertEqual(0, code)
        url = router.find("GET", "/v2/pjm/workitems")[0][1]
        self.assertIn("identifier=1", url)
        self.assertIn("project_id=pj1", url)
        self.assertNotIn("identifier=DEMO-1", url)

    def test_full_输出_V2_原始字段(self):
        item = {"id": "w1", "identifier": 5, "whole_identifier": "SCR-5",
                "title": "用户故事", "type": {"id": "t1", "name": "用户故事",
                                             "group": "requirement"},
                "state": {"id": "s1", "name": "新建", "type": "pending"}}
        code, out, _err, _router = self.run_cli(
            ["workitem", "show", "w1", "--full"],
            {("GET", "/v2/pjm/workitems/w1"): item})
        self.assertEqual(0, code)
        self.assertIn('"whole_identifier": "SCR-5"', out)
        self.assertIn('"group": "requirement"', out)

    def test_创建用得上下文里的项目(self):
        self.run_cli(["config", "context", "--project", "演示项目"])
        code, _out, _err, router = self.run_cli(
            ["workitem", "create", "--type", "task", "--title", "x", "--dry-run"])
        self.assertEqual(0, code)
        self.assertEqual([], router.calls)
        # dry-run 也要能解析出项目，否则说明上下文没被用上
        self.assertEqual("pj1", resolve.project_id(
            pc._client.Client(bearer=lambda: "", host="h", opener=lambda r, timeout=None: None),
            "演示项目")[0])

    def test_创建缺标题时_argparse_先挡住(self):
        with self.assertRaises(SystemExit) as ctx:
            self.run_cli(["workitem", "create", "--project", "演示项目", "--type", "bug"])
        self.assertEqual(2, ctx.exception.code, "缺必填参数时 argparse 直接退 2")

    def test_mine_把_closed_也算已完成(self):
        """实测得到：已拒绝的 state.type 是 closed（第四个语义值）。

        只把 completed 当完成，会把已拒绝的条目录进「未完成」。
        """
        items = [
            {"id": "1", "identifier": "D-1", "state": {"type": "pending"}},
            {"id": "2", "identifier": "D-2", "state": {"type": "in_progress"}},
            {"id": "3", "identifier": "D-3", "state": {"type": "completed"}},
            {"id": "4", "identifier": "D-4", "state": {"type": "closed"}},
            {"id": "5", "identifier": "D-5", "state": {"type": "将来才有的值"}},
        ]
        code, out, _err, _router = self.run_cli(
            ["workitem", "mine", "--open-only"],
            {("GET", "/v2/myself"): {"id": "u1", "name": "john", "display_name": "John"},
             ("GET", "/v2/pjm/workitems"): {"values": items, "total": 5}})
        self.assertEqual(0, code)
        for kept in ("D-1", "D-2", "D-5"):
            self.assertIn(kept, out, f"{kept} 应当算未完成")
        for dropped in ("D-3", "D-4"):
            self.assertNotIn(dropped, out, f"{dropped} 不该出现在未完成里")
        self.assertIn("其中未完成 3 条", out, "未知语义值算未完成（宁可多列）")

    # ── 搜索 ──
    SEARCH_ROUTE = {("POST", "/v2/pjm/workitems/search"): {"values": [], "total": 0}}

    def test_搜索的操作符写法与实测一致(self):
        """官方文档只列了操作符名字，没写格式 —— 这几条是实测出来的。"""
        code, _out, _err, router = self.run_cli(
            ["workitem", "search", "--project", "演示项目", "--type", "bug",
             "--title-contains", "登录"], dict(self.SEARCH_ROUTE))
        self.assertEqual(0, code)
        body = router.find("POST", "/v2/pjm/workitems/search")[0][2]
        self.assertEqual("query", body["mode"])
        flt = body["payload"]["filter"]
        self.assertEqual({"in": ["pj1"]}, flt["project.id"])
        self.assertEqual({"in": ["bug"]}, flt["type.id"])
        self.assertNotIn("$in", str(flt), "实测：操作符**不带** $ 前缀")
        self.assertEqual({"contains": "登录"}, flt["title"])
        self.assertIsInstance(flt["type.id"], dict, "实测：值必须是对象，标量会 400")

    def test_搜索按状态要同时给项目与类型(self):
        code, _out, err, router = self.run_cli(["workitem", "search", "--state", "已完成"])
        self.assertEqual(1, code)
        self.assertIn("--type", err, "状态 id 是按「项目 + 类型」配的")
        self.assertEqual([], router.calls)

    def test_搜索状态也可以直接给_id(self):
        code, _out, _err, router = self.run_cli(
            ["workitem", "search", "--state", "5c9b35de90ad7153c2062f18"],
            dict(self.SEARCH_ROUTE))
        self.assertEqual(0, code)
        flt = router.find("POST", "/v2/pjm/workitems/search")[0][2]["payload"]["filter"]
        self.assertEqual({"in": ["5c9b35de90ad7153c2062f18"]}, flt["state.id"])

    def test_搜索_created_after_转成时间戳(self):
        code, _out, _err, router = self.run_cli(
            ["workitem", "search", "--created-after", "2026-09-01"], dict(self.SEARCH_ROUTE))
        self.assertEqual(0, code)
        flt = router.find("POST", "/v2/pjm/workitems/search")[0][2]["payload"]["filter"]
        self.assertIn("gte", flt["created_at"])
        self.assertGreater(flt["created_at"]["gte"], 1_700_000_000)

    def test_搜索_filter_写错要报错(self):
        for bad in ("{不是 json", "[1,2,3]"):
            with self.subTest(value=bad):
                code, _out, err, router = self.run_cli(["workitem", "search", "--filter", bad])
                self.assertEqual(1, code)
                self.assertEqual([], router.calls)

    def test_搜索_all_带上已删除与已归档(self):
        code, _out, _err, router = self.run_cli(["workitem", "search", "--all"],
                                                dict(self.SEARCH_ROUTE))
        self.assertEqual(0, code)
        payload = router.find("POST", "/v2/pjm/workitems/search")[0][2]["payload"]
        self.assertTrue(payload["include_deleted"])
        self.assertTrue(payload["include_archived"])

    def test_搜索默认不带已删除的(self):
        code, _out, _err, router = self.run_cli(["workitem", "search"], dict(self.SEARCH_ROUTE))
        self.assertEqual(0, code)
        payload = router.find("POST", "/v2/pjm/workitems/search")[0][2]["payload"]
        self.assertNotIn("include_deleted", payload)

    # ── 批量改 ──
    def test_批量改一次只能一个属性(self):
        code, _out, err, router = self.run_cli(
            ["workitem", "bulk-update", "--ids", "DOC-1,DOC-2",
             "--state", "已完成", "--priority", "高"],
            {("GET", "/v2/pjm/workitems"): {"values": [WORKITEM]}})
        self.assertEqual(1, code)
        self.assertIn("只能改", err)
        self.assertIn("state_id", err)
        self.assertEqual([], router.find("PATCH", "/v2/pjm/workitems"))

    def test_批量改超过_100_个要拒绝(self):
        ids = ",".join(f"DOC-{i}" for i in range(101))
        code, _out, err, router = self.run_cli(
            ["workitem", "bulk-update", "--ids", ids, "--title", "x"])
        self.assertEqual(1, code)
        self.assertIn("100", err)
        self.assertEqual([], router.calls)

    def test_批量改混类型加状态要说清原因(self):
        # 用不像编号的 ref（w1/w2）→ 走直取，这样两条能各自拿到不同的类型；
        # 若用 DOC-1/DOC-2 走 identifier 查询，假路由会两条都返回 values[0]。
        task = dict(WORKITEM, id="w2", identifier="DOC-2", type="task")
        code, _out, err, router = self.run_cli(
            ["workitem", "bulk-update", "--ids", "w1,w2", "--state", "已完成"],
            {("GET", "/v2/pjm/workitems/w1"): WORKITEM,
             ("GET", "/v2/pjm/workitems/w2"): task})
        self.assertEqual(1, code)
        self.assertIn("类型不一样", err)
        self.assertEqual([], router.find("PATCH", "/v2/pjm/workitems"))

    def test_批量改跨项目要拒绝(self):
        other = dict(WORKITEM, id="w2", identifier="DOC-2",
                     project={"id": "pj2", "name": "示例项目 B"})
        code, _out, err, router = self.run_cli(
            ["workitem", "bulk-update", "--ids", "w1,w2", "--state", "已完成"],
            {("GET", "/v2/pjm/workitems/w1"): WORKITEM,
             ("GET", "/v2/pjm/workitems/w2"): other})
        self.assertEqual(1, code)
        self.assertIn("同一个项目", err)
        self.assertEqual([], router.find("POST", "/v2/pjm/workitems/bulk/set"))

    def test_批量改跨项目标题允许(self):
        other = dict(WORKITEM, id="w2", identifier="DOC-2",
                     project={"id": "pj2", "name": "示例项目 B"})
        code, _out, _err, router = self.run_cli(
            ["workitem", "bulk-update", "--ids", "w1,w2", "--title", "统一标题"],
            {("GET", "/v2/pjm/workitems/w1"): WORKITEM,
             ("GET", "/v2/pjm/workitems/w2"): other,
             ("POST", "/v2/pjm/workitems/bulk/set"):
                 [{"state": "success", "id": "w1"}, {"state": "success", "id": "w2"}]})
        self.assertEqual(0, code)
        body = router.find("POST", "/v2/pjm/workitems/bulk/set")[0][2]
        self.assertEqual("title", body["property_name"])

    def test_批量改正常路径(self):
        code, out, _err, router = self.run_cli(
            ["workitem", "bulk-update", "--ids", "DOC-1", "--title", "统一标题"],
            {("GET", "/v2/pjm/workitems"): {"values": [WORKITEM]},
             ("POST", "/v2/pjm/workitems/bulk/set"):
                 [{"state": "success", "id": "w1"}]})
        self.assertEqual(0, code)
        body = router.find("POST", "/v2/pjm/workitems/bulk/set")[0][2]
        self.assertEqual("title", body["property_name"])
        self.assertEqual("统一标题", body["property_value"])
        self.assertEqual(["w1"], body["ids"], "要传解析后的真 id，不传编号")
        self.assertIn("已更新", out)

    def test_批量改日期映射到_due(self):
        code, _out, _err, router = self.run_cli(
            ["workitem", "bulk-update", "--ids", "DOC-1", "--end", "2026-09-30"],
            {("GET", "/v2/pjm/workitems"): {"values": [WORKITEM]},
             ("POST", "/v2/pjm/workitems/bulk/set"):
                 [{"state": "success", "id": "w1"}]})
        self.assertEqual(0, code)
        body = router.find("POST", "/v2/pjm/workitems/bulk/set")[0][2]
        self.assertEqual("due", body["property_name"])
        self.assertEqual(0, body["property_value"]["with_time"])

    def test_批量改工作量映射到_properties(self):
        code, _out, _err, router = self.run_cli(
            ["workitem", "bulk-update", "--ids", "DOC-1", "--story-points", "5"],
            {("GET", "/v2/pjm/workitems"): {"values": [WORKITEM]},
             ("POST", "/v2/pjm/workitems/bulk/set"):
                 [{"state": "success", "id": "w1"}]})
        self.assertEqual(0, code)
        body = router.find("POST", "/v2/pjm/workitems/bulk/set")[0][2]
        self.assertEqual("properties.story_points", body["property_name"])
        self.assertEqual(5, body["property_value"])

    def test_列评论用解析后的主体_id(self):
        comments = [{"id": "c1", "content": "已定位到网关超时", "created_at": 1583290347,
                     "created_by": {"display_name": "某甲"}}]
        code, out, _err, router = self.run_cli(
            ["workitem", "comments", "DOC-1"],
            {("GET", "/v2/pjm/workitems"): {"values": [WORKITEM]},
             ("GET", "/v2/comments"): {"values": comments, "total": 1}})
        self.assertEqual(0, code, out)
        self.assertIn("已定位到网关超时", out)
        self.assertIn("某甲", out)
        query = router.find("GET", "/v2/comments")[0][1]
        self.assertIn("principal_type=workitem", query)
        self.assertIn("principal_id=w1", query, "要传解析后的真 id，不传编号")

    def test_没有评论时说一句人话(self):
        code, out, _err, _router = self.run_cli(
            ["workitem", "comments", "DOC-1"],
            {("GET", "/v2/pjm/workitems"): {"values": [WORKITEM]},
             ("GET", "/v2/comments"): {"values": [], "total": 0}})
        self.assertEqual(0, code)
        self.assertIn("还没有评论", out)

    def test_列附件把大小变人看的(self):
        files = [{"id": "a1", "title": "控制台日志", "size": 2048, "type": "file",
                  "download_url": "https://x/a.log", "created_at": 1583290347,
                  "created_by": {"display_name": "某甲"}}]
        code, out, _err, router = self.run_cli(
            ["workitem", "attachments", "DOC-1"],
            {("GET", "/v2/pjm/workitems"): {"values": [WORKITEM]},
             ("GET", "/v2/attachments"): {"values": files, "total": 1}})
        self.assertEqual(0, code, out)
        self.assertIn("控制台日志", out)
        self.assertIn("2.0 KB", out, "字节数要变成人看的")
        self.assertIn("principal_id=w1", router.find("GET", "/v2/attachments")[0][1])

    def test_没有附件时说一句人话(self):
        code, out, _err, _router = self.run_cli(
            ["workitem", "attachments", "DOC-1"],
            {("GET", "/v2/pjm/workitems"): {"values": [WORKITEM]},
             ("GET", "/v2/attachments"): {"values": [], "total": 0}})
        self.assertEqual(0, code)
        self.assertIn("没有附件", out)

    def test_流转历史列出状态变化(self):
        history = [
            {"id": "h1", "from_state": {"name": "新建"}, "to_state": {"name": "进行中"},
             "created_at": 1700000000, "created_by": {"display_name": "John"}},
            {"id": "h2", "from_state": {"name": "进行中"}, "to_state": {"name": "已完成"},
             "created_at": 1700003600, "created_by": {"display_name": "John"}},
        ]
        code, out, err, _router = self.run_cli(
            ["workitem", "history", "DOC-1"],
            {("GET", "/v2/pjm/workitems"): {"values": [WORKITEM]},
             ("GET", "/v2/pjm/workitems/w1/transition_histories"):
                 {"values": history, "total": 2}})
        self.assertEqual(0, code, err)
        for text in ("新建", "进行中", "已完成", "John"):
            self.assertIn(text, out)

    def test_没有流转记录时说一句人话(self):
        code, out, _err, _router = self.run_cli(
            ["workitem", "history", "DOC-1"],
            {("GET", "/v2/pjm/workitems"): {"values": [WORKITEM]},
             ("GET", "/v2/pjm/workitems/w1/transition_histories"):
                 {"values": [], "total": 0}})
        self.assertEqual(0, code)
        self.assertIn("还没有流转记录", out)

    def test_已删除工作项的流转历史给出人话(self):
        deleted = dict(WORKITEM, is_deleted=1)
        code, _out, err, _router = self.run_cli(
            ["workitem", "history", "DOC-1", "--all"],
            {("GET", "/v2/pjm/workitems"): {"values": [deleted]},
             ("GET", "/v2/pjm/workitems/w1/transition_histories"):
                 http_error(400, {"code": "100317", "message": "工作项资源不存在"})})
        self.assertEqual(1, code)
        self.assertIn("已删除", err)
        self.assertIn("流转历史", err)

    # ── mine 缺 scope 时的替代做法 ──
    def test_关联列表永远显示另一端(self):
        relation = {
            "id": "r1",
            "relation_type": {"id": "rt1", "name": "阻塞", "category": "block"},
            "origin_workitem": {"id": "w1", "whole_identifier": "DOC-1", "title": "登录页 500"},
            "target_workitem": {"id": "w2", "whole_identifier": "DOC-2", "title": "支付回调"},
        }
        code, out, err, _router = self.run_cli(
            ["workitem", "relations", "DOC-1"],
            {("GET", "/v2/pjm/workitems"): {"values": [WORKITEM]},
             ("GET", "/v2/pjm/workitems/w1/relations"):
                 {"values": [relation], "total": 1}})
        self.assertEqual(0, code, err)
        self.assertIn("阻塞", out)
        self.assertIn("DOC-2", out)
        self.assertIn("支付回调", out)

    def test_当前项是_target_时关联也显示另一端(self):
        current = dict(WORKITEM, id="w2", identifier="DOC-2", title="支付回调")
        relation = {
            "id": "r1",
            "relation_type": {"name": "被阻塞", "category": "blocked_by"},
            "origin_workitem": {"id": "w1", "whole_identifier": "DOC-1", "title": "登录页 500"},
            "target_workitem": {"id": "w2", "whole_identifier": "DOC-2", "title": "支付回调"},
        }
        code, out, err, _router = self.run_cli(
            ["workitem", "relations", "DOC-2"],
            {("GET", "/v2/pjm/workitems"): {"values": [current]},
             ("GET", "/v2/pjm/workitems/w2/relations"):
                 {"values": [relation], "total": 1}})
        self.assertEqual(0, code, err)
        self.assertIn("DOC-1", out)
        self.assertIn("登录页 500", out)

    def test_关联按类型过滤且空列表说人话(self):
        code, out, _err, router = self.run_cli(
            ["workitem", "relations", "DOC-1", "--type", "blocked_by"],
            {("GET", "/v2/pjm/workitems"): {"values": [WORKITEM]},
             ("GET", "/v2/pjm/workitems/w1/relations"):
                 {"values": [], "total": 0}})
        self.assertEqual(0, code)
        self.assertIn("还没有关联", out)
        url = router.find("GET", "/v2/pjm/workitems/w1/relations")[0][1]
        self.assertIn("relation_type=blocked_by", url)

    def test_mine_缺_scope_时要给不改后台的办法(self):
        """实测：数据范围里没有 pcp:read:account:personal 时 /v2/myself 会 403。
        报错要点名 scope，并给出不用改后台的替代做法，否则「我的任务」是死胡同。
        """
        code, _out, err, _router = self.run_cli(
            ["workitem", "mine", "--open-only"],
            {("GET", "/v2/myself"): http_error(403, {"code": "100027",
                                                      "message": "'access_token'权限不足"})})
        self.assertEqual(1, code)
        self.assertIn("pcp:read:account:personal", err)
        self.assertIn("--assignee", err)

    def test_mine_的中文类型名本地过滤(self):
        """V2 的系统类型 id 是 24 位，`mine` 没有项目上下文，不能把 `bug` 当 type_id 发；
        改为取回「我名下」后按 type.group / type.name 本地过滤。
        """
        items = [
            {"id": "1", "identifier": "D-1", "state": {"type": "pending"},
             "type": {"id": "t1", "name": "缺陷", "group": "bug"}},
            {"id": "2", "identifier": "D-2", "state": {"type": "pending"},
             "type": {"id": "t2", "name": "任务", "group": "task"}},
        ]
        code, out, _err, router = self.run_cli(
            ["workitem", "mine", "--type", "缺陷"],
            {("GET", "/v2/myself"): {"id": "u1", "name": "john"},
             ("GET", "/v2/pjm/workitems"): {"values": items, "total": 2}})
        self.assertEqual(0, code)
        url = router.find("GET", "/v2/pjm/workitems")[0][1]
        self.assertNotIn("type_id=", url, "没有项目上下文时不能把系统枚举当 type_id 发")
        self.assertIn("D-1", out)
        self.assertNotIn("D-2", out, "本地过滤要排掉其他类型")

    def test_mine_有项目时用服务端_type_id(self):
        items = [
            {"id": "1", "identifier": "D-1", "state": {"type": "pending"},
             "type": {"id": "t1", "name": "缺陷", "group": "bug"}},
        ]
        code, out, err, router = self.run_cli(
            ["workitem", "mine", "--project", "演示项目", "--type", "缺陷"],
            {("GET", "/v2/myself"): {"id": "u1", "name": "john"},
             ("GET", "/v2/pjm/workitems"): {"values": items, "total": 1}})
        self.assertEqual(0, code, err)
        url = router.find("GET", "/v2/pjm/workitems")[0][1]
        self.assertIn("project_id=pj1", url)
        self.assertIn("type_id=bug", url)
        self.assertIn("D-1", out)

    def test_mine_本地类型过滤会翻页(self):
        """目标类型不在第一页时不能直接放弃；要按页扫描到凑够 --limit。"""
        task = {"id": "t", "identifier": "TASK-1", "state": {"type": "pending"},
                "type": {"id": "t2", "name": "任务", "group": "task"}}
        bug = {"id": "b", "identifier": "BUG-101", "title": "目标的缺陷",
               "state": {"type": "pending"},
               "type": {"id": "t1", "name": "缺陷", "group": "bug"}}

        def pages(request):
            if "page_index=0" in request.full_url:
                return {"values": [task] * 100, "total": 101}
            return {"values": [bug], "total": 101}

        code, out, err, router = self.run_cli(
            ["workitem", "mine", "--type", "缺陷", "--limit", "1", "--open-only"],
            {("GET", "/v2/myself"): {"id": "u1", "name": "john"},
             ("GET", "/v2/pjm/workitems"): pages})
        self.assertEqual(0, code, err)
        self.assertEqual(2, len(router.find("GET", "/v2/pjm/workitems")))
        self.assertIn("BUG-101", out)
        self.assertNotIn("TASK-1", out)

    # ── 计划：一次建一棵树 ──
    def write_temp(self, name: str, text: str) -> str:
        path = os.path.join(self._tmp.name, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def write_plan(self, payload: dict) -> str:
        path = os.path.join(self._tmp.name, "plan.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        return path

    GOOD_PLAN = {
        "project": "演示项目",
        "nodes": [
            {"type": "epic", "title": "商城改版", "children": [
                {"type": "feature", "title": "下单与支付", "children": [
                    {"type": "story", "title": "下单流程", "children": [
                        {"type": "task", "title": "接入支付网关"}]}]}]},
        ],
    }

    def created_workitem(self, request_body: dict) -> dict:
        """把 POST 的 body 回显成一条已创建的工作项（测试用）。"""
        return dict(WORKITEM, id="w-" + str(len(request_body)), title=request_body.get("title", ""),
                    type=request_body.get("type_id", ""))

    def test_计划默认只打印不建(self):
        path = self.write_plan(self.GOOD_PLAN)
        code, out, _err, router = self.run_cli(["workitem", "create-plan", "--file", path])
        self.assertEqual(0, code)
        self.assertIn("建 4 条工作项", out)
        self.assertIn("- [史诗] 商城改版", out)
        self.assertIn("- [用户故事] 下单流程", out, "要画出层级（缩进）")
        self.assertIn("没有建任何东西", out)
        self.assertEqual([], router.find("POST", "/v2/pjm/workitems"), "不加 --yes 绝不能建")

    def test_计划带_yes和dry_run不创建也不报告已建成(self):
        code, out, err, router = self.run_cli([
            "workitem", "create-plan", "--file", self.write_plan(self.GOOD_PLAN), "--yes", "--dry-run"])
        self.assertEqual(0, code, err)
        self.assertNotIn("建成的树", out)
        self.assertEqual([], router.find("POST", "/v2/pjm/workitems"))

    def test_计划可解析负责人优先级和迭代(self):
        plan = {"project": "演示项目", "nodes": [{"type": "bug", "title": "测试",
                "assignee": "John", "priority": "高", "sprint": "Sprint 12", "state": "新建"}]}
        code, out, err, router = self.run_cli(
            ["workitem", "create-plan", "--file", self.write_plan(plan), "--yes"],
            {("POST", "/v2/pjm/workitems"): {"id": "new", "identifier": "DEMO-9"}})
        self.assertEqual(0, code, err)
        body = router.find("POST", "/v2/pjm/workitems")[0][2]
        self.assertEqual(("u1", "pr1", "sp1", "st1"),
                         tuple(body[key] for key in ("assignee_id", "priority_id", "sprint_id", "state_id")))

    def test_父项响应缺id时不得把子项建成无父根节点(self):
        code, out, err, router = self.run_cli(
            ["workitem", "create-plan", "--file", self.write_plan(self.GOOD_PLAN), "--yes"],
            {("POST", "/v2/pjm/workitems"): {"identifier": "DEMO-9"}})
        self.assertEqual(1, code)
        self.assertIn("DEMO-9", err)
        self.assertIn("缺少 id", err)
        self.assertEqual(1, len(router.find("POST", "/v2/pjm/workitems")))

    def test_计划后续本地解析失败时零创建(self):
        plan = {"project": "演示项目", "nodes": [
            {"type": "bug", "title": "第一项"},
            {"type": "bug", "title": "第二项", "priority": "不存在的优先级"}]}
        code, _out, err, router = self.run_cli(
            ["workitem", "create-plan", "--file", self.write_plan(plan), "--yes"],
            {("POST", "/v2/pjm/workitems"): {"id": "new", "identifier": "DEMO-9"}})
        self.assertEqual(1, code)
        self.assertIn("计划预检失败", err)
        self.assertIn("2（第二项）", err)
        self.assertIn("尚未创建任何节点", err)
        self.assertEqual([], router.find("POST", "/v2/pjm/workitems"))

    def test_计划后续描述文件缺失时零创建(self):
        plan = {"project": "演示项目", "nodes": [
            {"type": "bug", "title": "第一项"},
            {"type": "bug", "title": "第二项", "description_file": os.path.join(self._tmp.name, "missing.md")}]}
        code, _out, err, router = self.run_cli(
            ["workitem", "create-plan", "--file", self.write_plan(plan), "--yes"],
            {("POST", "/v2/pjm/workitems"): {"id": "new", "identifier": "DEMO-9"}})
        self.assertEqual(1, code)
        self.assertIn("计划预检失败", err)
        self.assertIn("2（第二项）", err)
        self.assertIn("尚未创建任何节点", err)
        self.assertEqual([], router.find("POST", "/v2/pjm/workitems"))

    def test_计划预检第二项工作量属性不支持时不创建第一项(self):
        plan = {"project": "演示项目", "nodes": [
            {"type": "bug", "title": "第一项"},
            {"type": "task", "title": "第二项", "estimated_workload": 2}]}
        code, _out, err, router = self.run_cli(
            ["workitem", "create-plan", "--file", self.write_plan(plan), "--yes"],
            {("POST", "/v2/pjm/workitems"): {"id": "new", "identifier": "DEMO-9"}})
        self.assertEqual(1, code)
        self.assertIn("计划预检失败", err)
        self.assertIn("2（第二项）", err)
        self.assertIn("estimated_workload", err)
        self.assertEqual([], router.find("POST", "/v2/pjm/workitems"))

    def test_计划带_yes_才建且父先子后(self):
        path = self.write_plan(self.GOOD_PLAN)
        code, out, _err, router = self.run_cli(
            ["workitem", "create-plan", "--file", path, "--yes"],
            {("POST", "/v2/pjm/workitems"): {"id": "w1", "identifier": "DEMO-9",
                                               "title": "x", "type": "epic"}})
        self.assertEqual(0, code, out)
        posts = router.find("POST", "/v2/pjm/workitems")
        self.assertEqual(4, len(posts))
        self.assertNotIn("parent_id", posts[0][2], "第一条是根，没有父项")
        for index, call in enumerate(posts[1:], start=1):
            self.assertEqual("w1", call[2]["parent_id"], f"第 {index + 1} 条要挂在刚建出来的父项上")
        self.assertIn("建成的树", out)
        self.assertIn("→ DEMO-9", out, "建成后要把编号回显在树上")

    def test_计划里写错字段名要当场报错并给候选(self):
        plan = {"nodes": [{"type": "epic", "titel": "打错了"}]}
        code, _out, err, router = self.run_cli(
            ["workitem", "create-plan", "--file", self.write_plan(plan)])
        self.assertEqual(1, code)
        self.assertIn("titel", err)
        self.assertIn("title", err, "要给最接近的候选")
        self.assertEqual([], router.calls, "校验不过就不能发任何请求")

    def test_计划缺_type_或_title_要报错(self):
        for node in ({"title": "没类型"}, {"type": "epic"}, {"type": "  ", "title": "  "}):
            with self.subTest(node=node):
                code, _out, err, router = self.run_cli(
                    ["workitem", "create-plan", "--file", self.write_plan({"nodes": [node]})])
                self.assertEqual(1, code)
                self.assertEqual([], router.calls)

    def test_计划不是_json_要报错(self):
        path = os.path.join(self._tmp.name, "bad.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("这不是 json")
        code, _out, err, _router = self.run_cli(["workitem", "create-plan", "--file", path])
        self.assertEqual(1, code)
        self.assertIn("合法 JSON", err)

    def test_计划中途失败要报出已建成的(self):
        """不能静默半途而废 —— 已建成的编号要报出来，否则用户只能从头猜。"""
        path = self.write_plan(self.GOOD_PLAN)
        calls = {"n": 0}

        def route(request) -> dict:  # noqa: ARG001 - Router 会把 request 传进来
            calls["n"] += 1
            if calls["n"] >= 3:
                raise http_error(400, {"code": "100319", "message": "父工作项的类型不正确"})
            return {"id": f"w{calls['n']}", "identifier": f"DEMO-{calls['n']}"}

        code, _out, err, _router = self.run_cli(
            ["workitem", "create-plan", "--file", path, "--yes"],
            {("POST", "/v2/pjm/workitems"): route})
        self.assertEqual(1, code)
        self.assertIn("已建成的", err)
        self.assertIn("DEMO-1", err, "要说清楚已经建成了哪些")
        self.assertIn("剩下的子树", err, "要给出怎么接着做")

    def test_计划建到一半时根节点就失败_要说已建成的是无(self):
        path = self.write_plan(self.GOOD_PLAN)
        code, _out, err, _router = self.run_cli(
            ["workitem", "create-plan", "--file", path, "--yes"],
            {("POST", "/v2/pjm/workitems"): http_error(400, {"message": "bad"})})
        self.assertEqual(1, code)
        self.assertIn("（无）", err)
    def test_改状态用解析后的_state_id(self):
        updated = dict(WORKITEM, state={"id": "st2", "name": "已完成", "type": "completed"})
        code, out, _err, router = self.run_cli(
            ["workitem", "set-state", "DOC-1", "已完成"],
            {("GET", "/v2/pjm/workitems"): {"values": [WORKITEM]},
             ("PATCH", "/v2/pjm/workitems/w1"): updated})
        self.assertEqual(0, code)
        patches = router.find("PATCH", "/v2/pjm/workitems/w1")
        self.assertEqual([{"state_id": "st2"}], [p[2] for p in patches])
        self.assertIn("已完成", out)

    def test_改状态时名字不存在要列出可用状态(self):
        code, _out, err, router = self.run_cli(
            ["workitem", "set-state", "DOC-1", "随便写的状态"],
            {("GET", "/v2/pjm/workitems"): {"values": [WORKITEM]}})
        self.assertEqual(1, code)
        self.assertIn("新建", err)
        self.assertIn("已完成", err)
        self.assertEqual([], router.find("PATCH", "/v2/pjm/workitems/w1"), "不能瞎改")

    # ── 按状态名过滤（实测踩过：中文名被当 id 发出去，服务端 400 code=100003）──
    def test_按状态过滤要用解析后的_id_不是名字(self):
        code, _out, _err, router = self.run_cli(
            ["workitem", "list", "--project", "演示项目", "--type", "bug", "--state", "新建"],
            {("GET", "/v2/pjm/workitems"): {"values": [WORKITEM]}})
        self.assertEqual(0, code)
        urls = [call[1] for call in router.find("GET", "/v2/pjm/workitems")]
        self.assertTrue(urls, "应该真的发了查询")
        self.assertIn("state_id=st1", urls[0])
        self.assertNotIn("%E6%96%B0%E5%BB%BA", urls[0], "不能把状态名当 id 发出去")

    def test_按状态过滤缺_type_要拒绝而不是发一个必错的请求(self):
        code, _out, err, router = self.run_cli(
            ["workitem", "list", "--project", "演示项目", "--state", "新建"])
        self.assertEqual(1, code)
        self.assertIn("--type", err)
        self.assertEqual([], router.calls, "缺上下文时不该发请求（状态是项目+类型独有的表）")

    # ── 项目状态是另一张表（实测踩过：拿工作项状态表去改项目状态）──
    def test_改项目状态走项目状态表(self):
        project = {"id": "pj1", "identifier": "DEMO", "name": "演示项目"}
        code, _out, _err, router = self.run_cli(
            ["project", "update", "--project", "演示项目", "--state", "正常"],
            {("GET", "/v2/pjm/project/project_states"): {"values": PROJECT_STATES},
             ("PATCH", "/v2/pjm/projects/pj1"): project})
        self.assertEqual(0, code)
        patches = router.find("PATCH", "/v2/pjm/projects/pj1")
        self.assertEqual([{"state_id": "ps2"}], [p[2] for p in patches])

    def test_改项目状态时名字不存在要列出项目状态(self):
        code, _out, err, router = self.run_cli(
            ["project", "update", "--project", "演示项目", "--state", "随便写的"],
            {("GET", "/v2/pjm/project/project_states"): {"values": PROJECT_STATES}})
        self.assertEqual(1, code)
        self.assertIn("未开始", err)
        self.assertIn("正常", err)
        self.assertEqual([], router.find("PATCH", "/v2/pjm/projects/pj1"), "不能瞎改")

    # ── 附件上传（字段名 title + file 是官方文档定的，不是猜的）──
    def test_上传文件走_multipart_字段名对(self):
        path = self.write_temp("日志.txt", "trace 内容")
        code, _out, _err, router = self.run_cli(
            ["workitem", "attach", "DOC-1", "--file", path],
            {("GET", "/v2/pjm/workitems"): {"values": [WORKITEM]},
             ("POST", "/v2/attachments"): {"id": "at1", "title": "日志.txt", "size": 9}})
        self.assertEqual(0, code)
        posts = router.find("POST", "/v2/attachments")
        self.assertEqual(1, len(posts))
        _method, url, body, headers = posts[0]
        self.assertIn("principal_type=workitem", url)
        self.assertIn("principal_id=w1", url)
        ctype = next(v for k, v in headers.items() if k.lower() == "content-type")
        self.assertTrue(ctype.startswith("multipart/form-data; boundary="), ctype)
        assert isinstance(body, bytes)
        text = body.decode("utf-8")
        self.assertIn('name="title"', text)
        self.assertIn('name="file"; filename="日志.txt"', text)
        self.assertIn("trace 内容", text)
        self.assertTrue(text.endswith("--\r\n"), "结尾要是结束边界 + CRLF")

    def test_上传文件的_dry_run_不发请求且写明是_multipart(self):
        path = self.write_temp("日志.txt", "x")
        code, out, _err, router = self.run_cli(
            ["workitem", "attach", "DOC-1", "--file", path, "--dry-run"],
            {("GET", "/v2/pjm/workitems"): {"values": [WORKITEM]}})
        self.assertEqual(0, code)
        self.assertIn("multipart/form-data", out)
        self.assertIn("日志.txt", out)
        self.assertEqual([], router.find("POST", "/v2/attachments"), "dry-run 不能真发")

    def test_上传代码段走_json_那个变体(self):
        code, _out, _err, router = self.run_cli(
            ["workitem", "attach-code", "DOC-1", "--title", "t", "--format", "python",
             "--content", "print(1)", "--comment", "cm1"],
            {("GET", "/v2/pjm/workitems"): {"values": [WORKITEM]},
             ("POST", "/v2/attachments"): {"id": "at2"}})
        self.assertEqual(0, code)
        _method, url, body, _headers = router.find("POST", "/v2/attachments")[0]
        self.assertNotIn("principal_type=", url, "代码段那个变体没有任何查询参数")
        self.assertEqual(["comment_id", "content", "format", "principal_id",
                          "principal_type", "title"], sorted(body))
        self.assertEqual("w1", body["principal_id"])
        self.assertEqual("cm1", body["comment_id"])

    def test_上传代码段缺_comment_当场拒绝而不是白跑一趟(self):
        """官方文档把 comment_id 标成「可选」，实测不带必回 400 code=100039 ——
        那个错误不会告诉你是缺它。所以做成接口形状约束：当场拒绝 + 说清原因。"""
        code, _out, err, router = self.run_cli(
            ["workitem", "attach-code", "DOC-1", "--title", "t", "--format", "python",
             "--content", "print(1)"],
            {("GET", "/v2/pjm/workitems"): {"values": [WORKITEM]}})
        self.assertEqual(1, code)
        self.assertIn("--comment", err)
        self.assertIn("100039", err)
        self.assertEqual([], router.find("POST", "/v2/attachments"), "不该白跑一趟")

    # ── 删附件（不可逆；上传能用了，没有配对的删除就是陷阱）──
    def test_删附件缺_yes_要拒绝(self):
        code, _out, err, router = self.run_cli(
            ["workitem", "attach-remove", "DOC-1", "at1"],
            {("GET", "/v2/pjm/workitems"): {"values": [WORKITEM]}})
        self.assertEqual(1, code)
        self.assertIn("--yes", err)
        self.assertEqual([], router.find("DELETE", "/v2/attachments"), "没确认不能删")

    def test_删附件把路径与查询占位符都填上(self):
        """「字面量 {attachment_id} 被发出去」那个错不能再犯一次。"""
        code, out, _err, router = self.run_cli(
            ["workitem", "attach-remove", "DOC-1", "at1", "--yes"],
            {("GET", "/v2/pjm/workitems"): {"values": [WORKITEM]},
             ("DELETE", "/v2/attachments"): {}})
        self.assertEqual(0, code)
        deletes = router.find("DELETE", "/v2/attachments")
        self.assertEqual(1, len(deletes))
        url = deletes[0][1]
        self.assertIn("/v2/attachments/at1", url)
        self.assertNotIn("{", url, "路径里不能残留字面量占位符")
        self.assertIn("principal_type=workitem", url)
        self.assertIn("principal_id=w1", url)
        self.assertIn("已删除", out)

    # ── 删除 ──
    def test_删除缺_yes_要拒绝(self):
        code, _out, err, router = self.run_cli(
            ["workitem", "delete", "DOC-1"], {("GET", "/v2/pjm/workitems"): {"values": [WORKITEM]}})
        self.assertEqual(1, code)
        self.assertIn("--yes", err)
        self.assertEqual([], router.find("DELETE", "/v2/pjm/workitems/w1"))

    def test_删除带_yes_会打_DELETE(self):
        code, out, _err, router = self.run_cli(
            ["workitem", "delete", "DOC-1", "--yes"],
            {("GET", "/v2/pjm/workitems"): {"values": [WORKITEM]},
             ("DELETE", "/v2/pjm/workitems/w1"): {}})
        self.assertEqual(0, code)
        self.assertIn("已删除", out)
        self.assertEqual(1, len(router.find("DELETE", "/v2/pjm/workitems/w1")))

    # ── 歧义与错误 ──
    def test_项目名有歧义要列候选并中止(self):
        code, _out, err, router = self.run_cli(
            ["workitem", "create", "--project", "项目", "--type", "bug", "--title", "x"])
        self.assertEqual(1, code)
        self.assertIn("演示项目", err)
        self.assertIn("示例项目 B", err)
        self.assertEqual([], router.calls, "有歧义就不能发任何请求")

    def test_逃生口会拦下官方文档里没有的路径(self):
        code, _out, err, router = self.run_cli(["api", "--path", "/v2/project/work_items"])
        self.assertEqual(1, code)
        self.assertIn("官方文档里没有", err)
        self.assertIn("/v2/pjm/workitems", err, "要给最接近的候选")
        self.assertEqual([], router.calls)

    def test_逃生口带_force_才真发(self):
        code, out, _err, router = self.run_cli(
            ["api", "--path", "/v2/whatever", "--force", "--full"],
            {("GET", "/v2/whatever"): {"ok": True}})
        self.assertEqual(0, code)
        self.assertIn("ok", out)
        self.assertEqual(1, len(router.find("GET", "/v2/whatever")))

    # ── 同一路径多个变体：query 必须能消歧（实测就翻在这上面）──
    def test_逃生口用_param_选多变体里的那个(self):
        """/v2/attachments 有两个 POST 变体：「代码段」无查询参数、「文件」要
        principal_type + principal_id。以前 cmd_api 把 query 从路径里切掉就不管了，
        于是**给了 --param 也照样报歧义**，唯一出路是 --force（而 --force 是
        「我知道路径存在」的确认，不是「选哪个变体」）。
        """
        code, out, _err, router = self.run_cli(
            ["api", "--method", "POST", "--path", "/v2/attachments",
             "--param", "principal_type=workitem", "--param", "principal_id=w1", "--dry-run"])
        self.assertEqual(0, code)
        self.assertIn("principal_type=workitem", out)
        self.assertIn("principal_id=w1", out)
        self.assertEqual([], router.calls, "dry-run 不能真发")

    def test_逃生口没给参数时走无查询参数的那个变体且说出来(self):
        code, out, err, _router = self.run_cli(
            ["api", "--method", "POST", "--path", "/v2/attachments",
             "--data", "{}", "--dry-run"])
        self.assertEqual(0, code)
        self.assertIn("变体", err, "默默挑一个是不要的行为，得说出选了哪个")
        self.assertIn("按不需要查询参数的那个走", err)
        self.assertIn("https://open.pingcode.com/v2/attachments", out)

    def test_单变体端点多给一个参数不能被判成路径不存在(self):
        """列表端点的 page_size 之类不在文档模板里，不该影响路径判定。"""
        code, _out, err, _router = self.run_cli(
            ["api", "--method", "GET", "--path", "/v2/pjm/workitems", "--param", "page_size=5"],
            {("GET", "/v2/pjm/workitems"): {"values": []}})
        self.assertEqual(0, code)
        self.assertNotIn("官方文档里没有", err)

    def test_401_要说去重新授权(self):
        code, _out, err, _router = self.run_cli(
            ["project", "list"], {("GET", "/v2/pjm/projects"): http_error(401, {"message": "invalid"})})
        self.assertEqual(1, code)
        self.assertIn("auth login", err)

    def test_whoami_用企业令牌要提示换模式(self):
        cfg.save_token({"access_token": "e", "expires_in": 2592000}, "enterprise")
        code, _out, err, _router = self.run_cli(["whoami"])
        self.assertEqual(1, code)
        self.assertIn("用户令牌", err)

    def test_whoami_用用户令牌能出结果(self):
        code, out, _err, _router = self.run_cli(
            ["whoami"], {("GET", "/v2/myself"): {"id": "u1", "name": "john", "display_name": "John"}})
        self.assertEqual(0, code)
        self.assertIn("John", out)

    # ── 配置 ──
    def test_用_code_直接换令牌_不依赖回调(self):
        """后台没登记 redirect_uri 或本机收不到回调时，要能从地址栏贴 code 把事办完。"""
        payload = {"access_token": "at", "refresh_token": "rt", "expires_in": 1791902383}
        code, out, err, router = self.run_cli(
            ["auth", "login", "--mode", "user", "--code", "the-code"],
            {("GET", "/v2/auth/token"): payload})
        self.assertEqual(0, code, err)
        self.assertIn("用户令牌已保存", out)
        self.assertEqual("at", cfg.load_token()["access_token"])
        self.assertEqual("user", cfg.load_token()["mode"])
        url = router.find("GET", "/v2/auth/token")[0][1]
        self.assertIn("grant_type=authorization_code", url)
        self.assertIn("code=the-code", url)

    def test_config_context_能设也能清(self):
        code, out, _err, _router = self.run_cli(["config", "context", "--project", "演示项目"])
        self.assertEqual(0, code)
        self.assertIn("演示项目", out)
        self.assertEqual("演示项目", cfg.load_context()["project"])
        self.run_cli(["config", "context", "--clear"])
        self.assertEqual({}, cfg.load_context())

    def test_config_refresh_states_要带_type(self):
        code, out, err, router = self.run_cli(
            ["config", "refresh", "--what", "states", "--project", "演示项目",
             "--type", "bug", "--no-cache"],
            {("GET", "/v2/pjm/workitem/workitem_types"):
                 {"values": TYPES, "total": len(TYPES)},
             ("GET", "/v2/pjm/workitem/workitem_states"):
                 {"values": STATES, "total": len(STATES)}})
        self.assertEqual(0, code, err)
        self.assertIn("工作项状态", out)
        url = router.find("GET", "/v2/pjm/workitem/workitem_states")[0][1]
        self.assertIn("project_id=pj1", url)
        self.assertIn("workitem_type_id=bug", url)

    def test_config_refresh_states_缺_type_要报错(self):
        code, _out, err, _router = self.run_cli(
            ["config", "refresh", "--what", "states", "--project", "演示项目"])
        self.assertEqual(1, code)
        self.assertIn("--type", err)

    def test_没有上下文与参数时报错要说怎么补(self):
        code, _out, err, _router = self.run_cli(["workitem", "create", "--type", "bug", "--title", "x"])
        self.assertEqual(1, code)
        self.assertIn("--project", err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
