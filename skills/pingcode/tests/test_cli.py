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
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")


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
        self.calls: list[tuple[str, str, object]] = []

    def __call__(self, request, timeout=None):  # noqa: ARG002
        body = request.data
        self.calls.append((request.method, request.full_url,
                           json.loads(body.decode("utf-8")) if body else None))
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
            ["project", "list"], {("GET", "/v1/pjm/projects"): {"values": PROJECTS, "total": 2}})
        self.assertEqual(0, code)
        self.assertIn("演示项目", out)
        self.assertIn("示例项目 B", out)

    def test_项目列表默认看不到已_归档_删除的(self):
        """实测：项目被删后从默认列表里消失，会让人以为“项目没了”。"""
        code, _out, _err, router = self.run_cli(
            ["project", "list"],
            {("GET", "/v1/pjm/projects"): {"values": PROJECTS, "total": 1}})
        self.assertEqual(0, code)
        url = router.find("GET", "/v1/pjm/projects")[0][1]
        self.assertNotIn("include_deleted", url)

        code, _out, _err, router = self.run_cli(
            ["project", "list", "--all"],
            {("GET", "/v1/pjm/projects"): {"values": PROJECTS, "total": 3}})
        self.assertEqual(0, code)
        url = router.find("GET", "/v1/pjm/projects")[0][1]
        self.assertIn("include_archived=true", url)
        self.assertIn("include_deleted=true", url)

    def test_列出某项目的类型(self):
        code, out, _err, _router = self.run_cli(["list", "types", "--project", "演示项目"])
        self.assertEqual(0, code)
        self.assertIn("缺陷", out)
        self.assertIn("bug", out)

    def test_看一个工作项_带描述(self):
        item = dict(WORKITEM, description="详细的复现步骤")
        code, out, _err, _router = self.run_cli(["workitem", "show", "DOC-1"],
                                                {("GET", "/v1/pjm/workitems"): {"values": [item]}})
        self.assertEqual(0, code)
        self.assertIn("DOC-1", out)
        self.assertIn("缺陷", out)
        self.assertIn("详细的复现步骤", out)
        # 编号形状（DOC-1）应当**直接**走 identifier 查询，不去撞那个注定 400 的直取
        self.assertEqual([], [c for c in _router.calls if "/v1/pjm/workitems/DOC-1" in c[1]])

    def test_按_id_看工作项走直取(self):
        code, out, _err, router = self.run_cli(
            ["workitem", "show", "w1"], {("GET", "/v1/pjm/workitems/w1"): WORKITEM})
        self.assertEqual(0, code)
        self.assertIn("DOC-1", out)
        self.assertEqual(1, len(router.find("GET", "/v1/pjm/workitems/w1")))

    def test_直取撞上_400_也要兜底到编号查询(self):
        """实测得到：给编号时官方返回 400 + code=100317，不是 404。

        这里用一个**不像编号**的 ref（`w9abc`），所以会先直取，再兜底。
        """
        item = dict(WORKITEM, title="兜底找到的")
        code, out, _err, router = self.run_cli(
            ["workitem", "show", "w9abc"],
            {("GET", "/v1/pjm/workitems/w9abc"): http_error(400, {"code": "100317",
                                                                  "message": "工作项资源不存在"}),
             ("GET", "/v1/pjm/workitems"): {"values": [item]}})
        self.assertEqual(0, code)
        self.assertIn("兜底找到的", out)
        self.assertEqual(1, len(router.find("GET", "/v1/pjm/workitems/w9abc")))

    def test_编号也找不到时要说清楚(self):
        code, _out, err, _router = self.run_cli(
            ["workitem", "show", "DOC-404"],
            {("GET", "/v1/pjm/workitems"): {"values": []}})
        self.assertEqual(1, code)
        self.assertIn("DOC-404", err)

    def test_删掉之后默认看不到_加_all_才看得到(self):
        """实测：DELETE 是**软删除**，若默认带上 include_deleted，刚删的会像没删一样又显示出来。"""
        code, _out, err, router = self.run_cli(
            ["workitem", "show", "DOC-1"],
            {("GET", "/v1/pjm/workitems"): {"values": []}})
        self.assertEqual(1, code)
        self.assertIn("--all", err, "要告诉用户可能是被删了以及怎么看")
        querystring = router.find("GET", "/v1/pjm/workitems")[0][1]
        self.assertNotIn("include_deleted=true", querystring, "默认不能查已删除的")

        code, out, _err, router = self.run_cli(
            ["workitem", "show", "DOC-1", "--all"],
            {("GET", "/v1/pjm/workitems"): {"values": [dict(WORKITEM, is_deleted=1)]}})
        self.assertEqual(0, code)
        self.assertIn("已被删除", out)
        self.assertIn("include_deleted=true", router.find("GET", "/v1/pjm/workitems")[0][1])

    def test_full_出原始_json(self):
        code, out, _err, _router = self.run_cli(["workitem", "show", "DOC-1", "--full"],
                                                {("GET", "/v1/pjm/workitems"): {"values": [WORKITEM]}})
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
            {("POST", "/v1/pjm/workitems"): created})
        self.assertEqual(0, code)
        posts = router.find("POST", "/v1/pjm/workitems")
        self.assertEqual(1, len(posts))
        body = posts[0][2]
        self.assertEqual("pj1", body["project_id"])
        self.assertEqual("bug", body["type_id"], "中文名「缺陷」要解析成 bug")
        self.assertEqual("2026-09-20", __import__("datetime").datetime.fromtimestamp(
            body["start_at"]).strftime("%Y-%m-%d"))
        self.assertIn("DOC-9", out)

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
            {("GET", "/v1/myself"): {"id": "u1", "name": "john", "display_name": "John"},
             ("GET", "/v1/pjm/workitems"): {"values": items, "total": 5}})
        self.assertEqual(0, code)
        for kept in ("D-1", "D-2", "D-5"):
            self.assertIn(kept, out, f"{kept} 应当算未完成")
        for dropped in ("D-3", "D-4"):
            self.assertNotIn(dropped, out, f"{dropped} 不该出现在未完成里")
        self.assertIn("其中未完成 3 条", out, "未知语义值算未完成（宁可多列）")

    def test_mine_缺_scope_时要给不改后台的办法(self):
        """实测：数据范围里没有 pcp:read:account:personal 时 /v1/myself 会 403。
        报错要点名 scope，并给出不用改后台的替代做法，否则「我的任务」是死胡同。
        """
        code, _out, err, _router = self.run_cli(
            ["workitem", "mine", "--open-only"],
            {("GET", "/v1/myself"): http_error(403, {"code": "100027",
                                                      "message": "'access_token'权限不足"})})
        self.assertEqual(1, code)
        self.assertIn("pcp:read:account:personal", err)
        self.assertIn("--assignee", err)

    def test_mine_的中文类型名要翻译成枚举(self):
        """实测：`mine --type 缺陷` 把中文原样发出去会 400（类型字典是按项目的，
        mine 没有项目上下文），但 9 种系统类型的枚举是全局固定的。
        """
        items = [{"id": "1", "identifier": "D-1", "state": {"type": "pending"}}]
        code, _out, _err, router = self.run_cli(
            ["workitem", "mine", "--type", "缺陷"],
            {("GET", "/v1/myself"): {"id": "u1", "name": "john"},
             ("GET", "/v1/pjm/workitems"): {"values": items, "total": 1}})
        self.assertEqual(0, code)
        url = router.find("GET", "/v1/pjm/workitems")[0][1]
        self.assertIn("type_id=bug", url, "中文要翻成枚举 bug")
        self.assertNotIn("%E7%BC%BA%E9%99%B7", url)

    # ── 计划：一次建一棵树 ──
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
        self.assertEqual([], router.find("POST", "/v1/pjm/workitems"), "不加 --yes 绝不能建")

    def test_计划带_yes_才建且父先子后(self):
        path = self.write_plan(self.GOOD_PLAN)
        code, out, _err, router = self.run_cli(
            ["workitem", "create-plan", "--file", path, "--yes"],
            {("POST", "/v1/pjm/workitems"): {"id": "w1", "identifier": "DEMO-9",
                                               "title": "x", "type": "epic"}})
        self.assertEqual(0, code, out)
        posts = router.find("POST", "/v1/pjm/workitems")
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
            {("POST", "/v1/pjm/workitems"): route})
        self.assertEqual(1, code)
        self.assertIn("已建成的", err)
        self.assertIn("DEMO-1", err, "要说清楚已经建成了哪些")
        self.assertIn("剩下的子树", err, "要给出怎么接着做")

    def test_计划建到一半时根节点就失败_要说已建成的是无(self):
        path = self.write_plan(self.GOOD_PLAN)
        code, _out, err, _router = self.run_cli(
            ["workitem", "create-plan", "--file", path, "--yes"],
            {("POST", "/v1/pjm/workitems"): http_error(400, {"message": "bad"})})
        self.assertEqual(1, code)
        self.assertIn("（无）", err)
    def test_改状态用解析后的_state_id(self):
        updated = dict(WORKITEM, state={"id": "st2", "name": "已完成", "type": "completed"})
        code, out, _err, router = self.run_cli(
            ["workitem", "set-state", "DOC-1", "已完成"],
            {("GET", "/v1/pjm/workitems"): {"values": [WORKITEM]},
             ("PATCH", "/v1/pjm/workitems/w1"): updated})
        self.assertEqual(0, code)
        patches = router.find("PATCH", "/v1/pjm/workitems/w1")
        self.assertEqual([{"state_id": "st2"}], [p[2] for p in patches])
        self.assertIn("已完成", out)

    def test_改状态时名字不存在要列出可用状态(self):
        code, _out, err, router = self.run_cli(
            ["workitem", "set-state", "DOC-1", "随便写的状态"],
            {("GET", "/v1/pjm/workitems"): {"values": [WORKITEM]}})
        self.assertEqual(1, code)
        self.assertIn("新建", err)
        self.assertIn("已完成", err)
        self.assertEqual([], router.find("PATCH", "/v1/pjm/workitems/w1"), "不能瞎改")

    # ── 删除 ──
    def test_删除缺_yes_要拒绝(self):
        code, _out, err, router = self.run_cli(
            ["workitem", "delete", "DOC-1"], {("GET", "/v1/pjm/workitems"): {"values": [WORKITEM]}})
        self.assertEqual(1, code)
        self.assertIn("--yes", err)
        self.assertEqual([], router.find("DELETE", "/v1/pjm/workitems/w1"))

    def test_删除带_yes_会打_DELETE(self):
        code, out, _err, router = self.run_cli(
            ["workitem", "delete", "DOC-1", "--yes"],
            {("GET", "/v1/pjm/workitems"): {"values": [WORKITEM]},
             ("DELETE", "/v1/pjm/workitems/w1"): {}})
        self.assertEqual(0, code)
        self.assertIn("已删除", out)
        self.assertEqual(1, len(router.find("DELETE", "/v1/pjm/workitems/w1")))

    # ── 歧义与错误 ──
    def test_项目名有歧义要列候选并中止(self):
        code, _out, err, router = self.run_cli(
            ["workitem", "create", "--project", "项目", "--type", "bug", "--title", "x"])
        self.assertEqual(1, code)
        self.assertIn("演示项目", err)
        self.assertIn("示例项目 B", err)
        self.assertEqual([], router.calls, "有歧义就不能发任何请求")

    def test_逃生口会拦下官方文档里没有的路径(self):
        code, _out, err, router = self.run_cli(["api", "--path", "/v1/project/work_items"])
        self.assertEqual(1, code)
        self.assertIn("官方文档里没有", err)
        self.assertIn("/v1/pjm/workitems", err, "要给最接近的候选")
        self.assertEqual([], router.calls)

    def test_逃生口带_force_才真发(self):
        code, out, _err, router = self.run_cli(
            ["api", "--path", "/v1/whatever", "--force", "--full"],
            {("GET", "/v1/whatever"): {"ok": True}})
        self.assertEqual(0, code)
        self.assertIn("ok", out)
        self.assertEqual(1, len(router.find("GET", "/v1/whatever")))

    def test_401_要说去重新授权(self):
        code, _out, err, _router = self.run_cli(
            ["project", "list"], {("GET", "/v1/pjm/projects"): http_error(401, {"message": "invalid"})})
        self.assertEqual(1, code)
        self.assertIn("auth login", err)

    def test_whoami_用企业令牌要提示换模式(self):
        cfg.save_token({"access_token": "e", "expires_in": 2592000}, "enterprise")
        code, _out, err, _router = self.run_cli(["whoami"])
        self.assertEqual(1, code)
        self.assertIn("用户令牌", err)

    def test_whoami_用用户令牌能出结果(self):
        code, out, _err, _router = self.run_cli(
            ["whoami"], {("GET", "/v1/myself"): {"id": "u1", "name": "john", "display_name": "John"}})
        self.assertEqual(0, code)
        self.assertIn("John", out)

    # ── 配置 ──
    def test_用_code_直接换令牌_不依赖回调(self):
        """后台没登记 redirect_uri 或本机收不到回调时，要能从地址栏贴 code 把事办完。"""
        payload = {"access_token": "at", "refresh_token": "rt", "expires_in": 1791902383}
        code, out, err, router = self.run_cli(
            ["auth", "login", "--mode", "user", "--code", "the-code"],
            {("GET", "/v1/auth/token"): payload})
        self.assertEqual(0, code, err)
        self.assertIn("用户令牌已保存", out)
        self.assertEqual("at", cfg.load_token()["access_token"])
        self.assertEqual("user", cfg.load_token()["mode"])
        url = router.find("GET", "/v1/auth/token")[0][1]
        self.assertIn("grant_type=authorization_code", url)
        self.assertIn("code=the-code", url)

    def test_config_context_能设也能清(self):
        code, out, _err, _router = self.run_cli(["config", "context", "--project", "演示项目"])
        self.assertEqual(0, code)
        self.assertIn("演示项目", out)
        self.assertEqual("演示项目", cfg.load_context()["project"])
        self.run_cli(["config", "context", "--clear"])
        self.assertEqual({}, cfg.load_context())

    def test_没有上下文与参数时报错要说怎么补(self):
        code, _out, err, _router = self.run_cli(["workitem", "create", "--type", "bug", "--title", "x"])
        self.assertEqual(1, code)
        self.assertIn("--project", err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
