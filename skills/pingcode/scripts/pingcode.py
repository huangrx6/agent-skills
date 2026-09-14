#!/usr/bin/env python3
"""PingCode 命令行：查询与维护项目 / 工作项（史诗 / 特性 / 用户故事 / 任务 / 缺陷）。

四条设计原则
------------
1. **路径不交给调用方。** 端点来自 `scripts/endpoints.py`（由官方 `api_data.json`
   生成），用 `api_index.require()` 取。参考实现把 `--path` 暴露给调用方，结果写死了
   `/v1/project/work_items` 这种官方根本不存在的路径 —— 而它的测试 mock 了网络，
   错路径照样全绿。
2. **默认紧凑输出。** 要原始 JSON 才加 `--full`。默认值写在代码里，不写在文档里。
3. **不猜 ID。** 项目名 / 迭代名 / 状态名 / 人名都走 `resolve`；匹配到多个就**列候选**，
   不自动取第一个。
4. **写操作先回显。** 发送前打印「将要做什么」，`--dry-run` 只看不发；删除要 `--yes`。

配置与授权见 README。自查命令：`pingcode.py api --list 工作项`
"""

from __future__ import annotations

import argparse
import difflib
import importlib.util
import json
import os
import re
import sys
import urllib.parse
from typing import Any


def _load_sibling(name: str):
    """动态加载同目录脚本（`scripts/` 不是包，同级 import 在静态层面无法解析）。

    **同一个模块只加载一次**：这个函数会被好几个模块各自调用，如果每次都新建一个模块
    对象，就会出现两份互不相干的模块状态 —— 连异常类都不是同一个，`except` 会静默抓不到。
    所以先查 `sys.modules`。
    """
    key = f"_pingcode_{name}"
    loaded = sys.modules.get(key)
    if loaded is not None:
        return loaded
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.py")
    spec = importlib.util.spec_from_file_location(key, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了同目录模块：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


_api = _load_sibling("api_index")
_auth = _load_sibling("auth")
_client = _load_sibling("client")
_config = _load_sibling("config")
_fmt = _load_sibling("format")
_resolve = _load_sibling("resolve")

WORKITEM = "/v1/pjm/workitems"
PROJECTS = "/v1/pjm/projects"
COMMENTS = "/v1/comments"
ATTACHMENTS = "/v1/attachments"

# 工作项编号的形状（`DEMO-80` / `SCR-12`）：带连字符 + 结尾是数字。
# 用形状先分流，省掉一次注定 400 的直取（官方对编号返回 400 而不是 404）。
_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*-\d+$")

# 工作项 state.type 的语义值。**实测（真实租户）得到 4 个**：
#   pending 新提交 / in_progress 处理中·已修复·重新打开·挂起 / completed 已发布 / closed 已拒绝
# 官方文档的响应示例只给了 pending，所以这里只能实测。
# 判据用**黑名单**（不等于这几个就算未完成）：以后出现新的语义值时，
# 会被算进「未完成」—— 宁可多列，也不要把活藏起来。
DONE_STATE_TYPES = ("completed", "closed")
BOOLEAN_TRUE = "true"


class CliError(Exception):
    """给用户看的一句话错误（不带堆栈）。"""


def fail(message: str, code: int = 1) -> None:
    """在命令处理函数里直接中止（抛 SystemExit，不走堆栈）。"""
    print(f"✗ {message}", file=sys.stderr)
    raise SystemExit(code)


def _error(message: str, code: int = 1) -> int:
    """在 main 里把异常翻译成退出码。

    这里**不能**用 `fail()`：它会抛 SystemExit，那样后面的 except 分支就永远到不了
    （静态检查会把它们全报成 unreachable）。
    """
    print(f"✗ {message}", file=sys.stderr)
    return code


# ── 客户端与上下文 ────────────────────────────────────────────
def scopes_for(method: str, url: str) -> tuple[str, ...]:
    """403 时用来指出缺哪个 scope（表里有就说得准，没有就退化成泛泛提示）。"""
    path = urllib.parse.urlparse(url).path
    try:
        return _api.require(method, path).scopes
    except _api.EndpointError:
        return ()


def build_client(args: argparse.Namespace) -> Any:
    cr = _config.load_credentials()
    return _client.Client(
        bearer=_auth.bearer,
        host=getattr(args, "host", "") or cr.host,
        dry_run=bool(getattr(args, "dry_run", False)),
        scopes_for=scopes_for,
    )


def from_context(name: str) -> str:
    return str(_config.load_context().get(name, "") or "")


def pick(args: argparse.Namespace, name: str, context_key: str = "") -> str:
    """参数 > 上下文文件。"""
    value = getattr(args, name, None)
    if value:
        return str(value)
    return from_context(context_key or name)


def need_project(args: argparse.Namespace, client: Any) -> tuple[str, str]:
    ref = pick(args, "project", "project")
    if not ref:
        raise CliError(
            "没指定项目：加 --project <名字或标识>，"
            "或先 `pingcode.py config context --project <名字>` 设一次"
        )
    return _resolve.project_id(client, ref, force=args.no_cache)


def resolve_type(args: argparse.Namespace, client: Any, project_id: str) -> str:
    """--type 支持系统类型枚举（bug）、中文名（缺陷）与自定义类型 id。"""
    raw = str(args.type or "").strip()
    if not raw:
        raise CliError("没指定工作项类型：--type bug / task / story / epic …")
    try:
        return _resolve.type_id(client, project_id, raw, force=args.no_cache)
    except (_resolve.NotFound, _resolve.Ambiguous):
        if _looks_like_id(raw):
            return raw
        raise


def _looks_like_id(text: str) -> bool:
    return len(text) == 24 and all(ch in "0123456789abcdef" for ch in text.lower())


def system_type_or_raw(text: str) -> str:
    """把系统类型的中文名/枚举统一成枚举值。

    `mine` 没有项目上下文，查不了类型字典（类型是**按项目**配的），但 9 种系统类型的
    枚举是全局固定的，本地就能翻译。实测：`mine --type 缺陷` 把中文原样发出去会
    400「'type_id'不是有效的字符串」。自定义类型仍然只能靠项目上下文，交给服务端报错。
    """
    raw = str(text or "").strip()
    lower = raw.lower()
    if lower in _fmt.TYPE_NAMES:
        return lower
    for enum, label in _fmt.TYPE_NAMES.items():
        if label == raw:
            return enum
    return raw


def fetch_workitem(client: Any, ref: str, include_deleted: bool = False) -> dict[str, Any]:
    """按 id / short_id / 编号（SCR-12）取一个工作项。

    官方：`GET /v1/pjm/workitems/{id}` 收 id **或 short_id**，但**不收编号**，而且给编号时
    返回的是 **400 + code=100317「工作项资源不存在」**（不是 404，实测得到）。所以：
    形状像编号的（`DEMO-80`）直接走列表接口的 `identifier` 查询；其它先直取，
    400/404 再兜底。

    归档的默认找得到（引用旧条目是常事）；**已删除的默认不找** —— 实测：DELETE 是软删除，
    若把 `include_deleted` 也打开，刚删掉的工作项会像没删一样接着显示出来。
    """
    ref = str(ref or "").strip()
    if not ref:
        raise CliError("没给工作项：可以是编号（SCR-12）、short_id 或 id")

    if not _IDENTIFIER_RE.match(ref):
        path = _api.build("/v1/pjm/workitems/{workitem_id}", workitem_id=ref)
        try:
            data = client.get(path).data
            if isinstance(data, dict) and data.get("id"):
                return dict(data)
        except _client.ApiError as exc:
            if exc.status not in (400, 404):
                raise

    result = client.get(WORKITEM, identifier=ref, include_archived=BOOLEAN_TRUE,
                        include_deleted=BOOLEAN_TRUE if include_deleted else None)
    values = result.values
    if not values:
        hint = "" if include_deleted else "（它可能已被删除，加 --all 看已删除的）"
        raise CliError(f"找不到工作项 {ref!r}（编号 / short_id / id 都试过了）{hint}")
    return dict(values[0])


def perform(args: argparse.Namespace, client: Any, method: str, path: str,
            body: dict[str, Any] | None = None, params: dict[str, Any] | None = None,
            summary: str = "") -> Any:
    """统一的写入口：先回显「要做什么」，dry-run 就停在这里。"""
    plan = client.describe(method, path, params, body)
    if args.dry_run:
        print("--dry-run：只描述，不发送")
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return None
    if summary:
        # flush=True：管道里 stdout 会被缓冲，stderr 不会 —— 不刷的话错误信息会
        # 出现在这句「将要做什么」的**前面**（Agent 抓输出时看着就像先报错后动手）。
        print(f"→ {summary}", flush=True)
    result = client.request(method, path, params=params, body=body)
    if result.quota.have_any:
        print(f"  配额：{result.quota.line()}")
    return result


def emit(records: list[dict[str, Any]], args: argparse.Namespace, kind: str,
         raw: list[dict[str, Any]] | None = None) -> None:
    if args.full:
        print(json.dumps(raw if raw is not None else records, ensure_ascii=False, indent=2))
        return
    print(_fmt.render(records))


# ── auth / config ─────────────────────────────────────────────
def cmd_auth_login(args: argparse.Namespace) -> int:
    cr = _config.load_credentials()
    mode = str(args.mode or cr.auth_mode)
    if mode == "enterprise":
        record = _auth.login_enterprise()
        print("✓ 企业令牌已保存")
    else:
        url = _auth.authorize_url()
        if args.code:
            # 回调收不到时（后台登记的 redirect_uri 与本机监听对不上、或在远程机器上）
            # 就手动把地址栏里的 code 拿过来 —— 不依赖本地监听。
            code = args.code.strip()
            print("用你给的 code 换令牌。")
        else:
            print("在浏览器里打开这个地址，登录并点授权：\n  " + url, flush=True)
            if args.manual:
                code = input("把回调地址里的 code 贴进来：").strip()
            else:
                code = _auth.wait_for_code(cr.redirect_uri, timeout=args.timeout)
                print("✓ 收到授权码", flush=True)
        record = _auth.exchange_code(code)
        print("✓ 用户令牌已保存")
    state = _config.token_state(record)
    days = state["seconds_left"] // 86400
    print(f"  到期：{_fmt.show_time(state['expires_at'])}（还有 {days} 天）")
    print(f"  续期：{'有 refresh_token，到期会自动续' if state['has_refresh'] else '没有 refresh_token，到期需重新授权'}")
    print(f"  存放：{_config.path_of(_config.TOKEN)}（0600）")
    return 0


def cmd_auth_status(args: argparse.Namespace) -> int:
    print(_fmt.render([{k: v for k, v in _auth.status().items()}]))
    return 0


def cmd_auth_logout(args: argparse.Namespace) -> int:
    existed = _config.clear_token()
    print("✓ 已删除本地令牌" if existed else "· 本地没有令牌")
    print("  （应用凭据 credentials.json 没动；要换应用才需要改它）")
    return 0


def cmd_whoami(args: argparse.Namespace) -> int:
    client = build_client(args)
    me = _auth.whoami(client)
    if args.full:
        print(json.dumps(me, ensure_ascii=False, indent=2))
        return 0
    print(_fmt.render([_fmt.compact("user", me)]))
    return 0


def cmd_config_show(args: argparse.Namespace) -> int:
    info = dict(_auth.status())
    ctx = _config.load_context()
    if ctx:
        info["当前上下文"] = "；".join(f"{k}={v}" for k, v in sorted(ctx.items()))
    print(_fmt.render([info]))
    return 0


def cmd_config_context(args: argparse.Namespace) -> int:
    if args.clear:
        _config.save_context(project=None, sprint=None)
        print("✓ 已清空当前项目 / 迭代")
        return 0
    if not (args.project or args.sprint):
        ctx = _config.load_context()
        if not ctx:
            print("（还没设过：pingcode.py config context --project <名字>）")
            return 0
        print(_fmt.render([ctx]))
        return 0
    ctx = _config.save_context(**{k: v for k, v in
                                  (("project", args.project), ("sprint", args.sprint)) if v})
    print("✓ 已更新上下文：" + "；".join(f"{k}={v}" for k, v in sorted(ctx.items())))
    return 0


def cmd_config_refresh(args: argparse.Namespace) -> int:
    client = build_client(args)
    kinds = [k.strip() for k in (args.what or "").split(",") if k.strip()]
    if not kinds:
        _resolve.clear()
        print("✓ 已清空字典缓存")
        return 0
    keys: dict[str, Any] = {}
    project = pick(args, "project", "project")
    if project:
        keys["project_id"] = _resolve.project_id(client, project)[0]
    for kind in kinds:
        spec = _resolve.SOURCES.get(kind)
        if spec is None:
            raise CliError(f"未知字典 {kind!r}；可用：{'、'.join(sorted(_resolve.SOURCES))}")
        values = _resolve.items(kind, client, force=True, **keys)
        print(f"✓ {spec['label']}：{len(values)} 条")
    return 0


# ── 只读 ──────────────────────────────────────────────────────
def cmd_project_list(args: argparse.Namespace) -> int:
    client = build_client(args)
    params: dict[str, Any] = {"keywords": args.keywords, "type": args.type}
    if args.all:
        # 实测：项目被删/归档后从默认列表里消失，不看这两个开关会以为“项目没了”。
        # 当初查 DEMO 去哪了，就是靠逃生口手动加这两个参数才看出来的。
        params["include_archived"] = BOOLEAN_TRUE
        params["include_deleted"] = BOOLEAN_TRUE
    result = client.get(PROJECTS, **params)
    values = result.values
    emit(_fmt.rows("project", values), args, "project", values)
    total = result.total
    if total is not None and not args.full and total > len(values):
        print(f"（共 {total} 个，这里只列了第一页 {len(values)} 个；想看全部加 --limit）")
    return 0


def cmd_project_show(args: argparse.Namespace) -> int:
    client = build_client(args)
    pid, _name = _resolve.project_id(client, args.project, force=args.no_cache)
    data = client.get(_api.build("/v1/pjm/projects/{project_id}", project_id=pid)).data
    if args.full:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    print(_fmt.render([_fmt.compact("project", dict(data or {}))]))
    return 0


PROGRESS_LABELS = {"workitem": "工作项"}
PROGRESS_FIELDS = (("total", "总数"), ("pending_count", "待处理"),
                   ("in_progress_count", "进行中"), ("completed_count", "已完成"))


def cmd_project_progress(args: argparse.Namespace) -> int:
    client = build_client(args)
    pid, name = _resolve.project_id(client, args.project, force=args.no_cache)
    data = client.get(_api.build("/v1/pjm/projects/{project_id}/progress", project_id=pid)).data
    if args.full:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    print(f"{name} 的进度：")
    # 返回结构是 {工作项: {total, pending_count, …}}（见官方响应示例），
    # 直接当一行记录渲染会把整个 dict 打印成一列，很难看。按子项铺成表。
    rows: list[dict[str, Any]] = []
    if isinstance(data, dict):
        for key, value in data.items():
            if not isinstance(value, dict):
                continue
            row: dict[str, Any] = {"统计项": PROGRESS_LABELS.get(key, str(key))}
            for field, label in PROGRESS_FIELDS:
                if field in value:
                    row[label] = value[field]
            rows.append(row)
    if rows:
        emit(rows, args, "simple")
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def cmd_workitem_list(args: argparse.Namespace) -> int:
    client = build_client(args)
    params: dict[str, Any] = {"keywords": args.keywords, "identifier": args.identifier}
    if pick(args, "project", "project"):
        params["project_id"] = need_project(args, client)[0]
    if args.type:
        params["type_id"] = resolve_type(args, client, params.get("project_id", ""))
    if args.state:
        # 状态名必须解析成 state_id：状态是「项目 + 类型」独有的表，把中文名当 id 发出去
        # 服务端会回 400 code=100003（实测过）。缺上下文时给可执行的提示，不要发一个必错的请求。
        missing = [flag for flag, key in (("--project", "project_id"), ("--type", "type_id"))
                   if not params.get(key)]
        if missing:
            raise CliError(f"用 --state 过滤时要同时给 {' 和 '.join(missing)}："
                           "工作项状态是「项目 + 类型」独有的表，光有状态名定位不了")
        params["state_id"] = _resolve.state_id_for(client, params["project_id"],
                                                   params["type_id"], args.state,
                                                   force=args.no_cache)
    if args.assignee:
        params["assignee_id"] = _resolve.user_id(client, args.assignee, force=args.no_cache)
    if args.sprint and params.get("project_id"):
        params["sprint_id"] = _resolve.find("sprints", client, args.sprint,
                                            force=args.no_cache,
                                            project_id=params["project_id"])["id"]
    if args.all:
        params["include_archived"] = BOOLEAN_TRUE
        params["include_deleted"] = BOOLEAN_TRUE
    values = client.paginate(WORKITEM, max_items=args.limit, **params)
    emit(_fmt.rows("workitem", values), args, "workitem", values)
    return 0


def cmd_workitem_show(args: argparse.Namespace) -> int:
    client = build_client(args)
    data = fetch_workitem(client, args.ref, include_deleted=bool(args.all))
    if args.full:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    print(_fmt.render([_fmt.compact("workitem", data)]))
    if args.all and data.get("is_deleted"):
        print("（注意：这条已被删除）")
    if data.get("description"):
        print("\n描述：\n" + str(data["description"]))
    return 0


def cmd_workitem_mine(args: argparse.Namespace) -> int:
    client = build_client(args)
    try:
        me = _resolve.user_id(client, "@me", force=args.no_cache)
    except _client.ApiError as exc:
        if exc.status != 403:
            raise
        # 实测：应用的数据范围里没有 pcp:read:account:personal 时，/v1/myself 会 403。
        # 这条报错本身已经点名了 scope，这里再给一个**不用改后台**的替代做法，
        # 否则「我的任务」这条最常用的路径就成了死胡同。
        raise CliError(
            f"{exc}\n  「我」要读 /v1/myself，需要应用数据范围里有 pcp:read:account:personal。\n"
            "  不想动后台：改用 `workitem list --assignee <你的真名>`（效果一样）。"
        ) from exc
    params: dict[str, Any] = {"assignee_id": me}
    if args.type:
        params["type_id"] = system_type_or_raw(args.type)
    values = client.paginate(WORKITEM, max_items=args.limit, **params)
    open_items = [v for v in values
                  if str(_fmt.dig(v, "state.type") or "") not in DONE_STATE_TYPES]
    if args.open_only:
        values = open_items
    emit(_fmt.rows("workitem", values), args, "workitem", values)
    if not args.full:
        print(f"（我名下 {len(values)} 条，其中未完成 {len(open_items)} 条）")
    return 0


def cmd_dict_list(args: argparse.Namespace) -> int:
    client = build_client(args)
    kind = args.kind
    keys: dict[str, Any] = {}
    if kind in ("states",) and not args.type:
        raise CliError("列工作项状态要指定类型：--type bug / task / …（不同类型的状态表不一样）")
    project = pick(args, "project", "project")
    if kind in ("sprints", "types", "priorities", "tags", "states", "project_states"):
        if not project:
            raise CliError(f"列{_resolve.SOURCES[kind]['label']}要指定项目：--project <名字>")
        keys["project_id"] = _resolve.project_id(client, project, force=args.no_cache)[0]
    if kind == "states":
        keys["workitem_type_id"] = resolve_type(args, client, keys["project_id"])
    values = _resolve.items(kind, client, force=args.no_cache, **keys)
    # 字典各有自己的看头：成员要看**真名**（name 是手机号）、项目要看标识与类型、
    # 状态要看语义值。统一用 simple 会把有用的列全滤掉。
    schema = {"states": "state", "users": "user", "sprints": "sprint",
              "projects": "project"}.get(kind, "simple")
    emit(_fmt.rows(schema, values), args, "simple", values)
    return 0


# ── 写 ────────────────────────────────────────────────────────
def _workitem_body(args: argparse.Namespace, client: Any, project_id: str,
                   type_id: str) -> dict[str, Any]:
    body: dict[str, Any] = {}
    if getattr(args, "title", None):
        body["title"] = args.title
    if getattr(args, "description", None) or getattr(args, "description_file", None):
        body["description"] = _read_description(args)
    if getattr(args, "start", None):
        body["start_at"] = _fmt.parse_time(args.start)
    if getattr(args, "end", None):
        body["end_at"] = _fmt.parse_time(args.end)
    if getattr(args, "assignee", None):
        body["assignee_id"] = _resolve.user_id(client, args.assignee, force=args.no_cache)
    if getattr(args, "priority", None):
        body["priority_id"] = _resolve.find("priorities", client, args.priority,
                                            force=args.no_cache, project_id=project_id)["id"]
    if getattr(args, "sprint", None):
        body["sprint_id"] = _resolve.find("sprints", client, args.sprint,
                                          force=args.no_cache, project_id=project_id)["id"]
    if getattr(args, "parent", None):
        body["parent_id"] = fetch_workitem(client, args.parent)["id"]
    if getattr(args, "state", None):
        body["state_id"] = _resolve.state_id_for(client, project_id, type_id, args.state,
                                                 force=args.no_cache)
    for flag, field in (("story_points", "story_points"),
                        ("estimated_workload", "estimated_workload"),
                        ("remaining_workload", "remaining_workload")):
        value = getattr(args, flag, None)
        if value is not None:
            body[field] = value
    return body


def _read_description(args: argparse.Namespace) -> str:
    path = getattr(args, "description_file", None)
    if not path:
        return str(args.description)
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        raise CliError(f"读不到描述文件 {path}：{exc}") from exc


def cmd_workitem_create(args: argparse.Namespace) -> int:
    client = build_client(args)
    pid, pname = need_project(args, client)
    tid = resolve_type(args, client, pid)
    if not args.title:
        raise CliError("要一个标题：--title <标题>")
    body = {"project_id": pid, "type_id": tid, "title": args.title}
    body.update(_workitem_body(args, client, pid, tid))
    summary = f"在「{pname}」创建 {_fmt.type_label(tid)}：{args.title}"
    result = perform(args, client, "POST", WORKITEM, body=body, summary=summary)
    if result is not None:
        data = result.data if isinstance(result.data, dict) else {}
        emit([_fmt.compact("workitem", data)], args, "workitem", [data])
    return 0


# ── 计划：一次建一棵树 ────────────────────────────────────────
# 字段集是**封闭的** —— 写错字段名（比如 titel）要当场报错并给候选，
# 而不是默默忽略、建出一棵缺东西的树。
PLAN_FIELDS = ("type", "title", "description", "description_file", "assignee", "priority",
               "sprint", "state", "start", "end", "story_points", "estimated_workload",
               "remaining_workload", "children")
PLAN_TOP_FIELDS = ("project", "nodes")


def load_plan(path: str) -> dict[str, Any]:
    """读计划文件（JSON）。"""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        raise CliError(f"读不到计划文件 {path}：{exc}") from exc
    except json.JSONDecodeError as exc:
        raise CliError(f"{path} 不是合法 JSON：{exc}") from exc
    if not isinstance(data, dict):
        raise CliError('计划文件顶层要是一个对象：{"project": …, "nodes": […]}')
    unknown = [k for k in data if k not in PLAN_TOP_FIELDS]
    if unknown:
        raise CliError(f"计划文件顶层不认识的键：{'、'.join(unknown)}"
                       f"（只允许 {'、'.join(PLAN_TOP_FIELDS)}）")
    nodes = data.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise CliError("计划文件缺 nodes（非空数组）")
    _check_plan_nodes(nodes, "nodes")
    return data


def _check_plan_nodes(nodes: list[Any], where: str) -> None:
    for index, node in enumerate(nodes):
        at = f"{where}[{index}]"
        if not isinstance(node, dict):
            raise CliError(f"{at} 不是对象")
        unknown = [k for k in node if k not in PLAN_FIELDS]
        if unknown:
            near = difflib.get_close_matches(str(unknown[0]), PLAN_FIELDS, n=1)
            hint = f"，是不是想写 {near[0]}？" if near else ""
            raise CliError(f"{at} 不认识的字段：{'、'.join(unknown)}{hint}"
                           f"（允许：{'、'.join(PLAN_FIELDS)}）")
        for required in ("type", "title"):
            if not str(node.get(required) or "").strip():
                raise CliError(f"{at} 缺 {required}（每一条都必须有类型和标题）")
        children = node.get("children")
        if children is None:
            continue
        if not isinstance(children, list):
            raise CliError(f"{at}.children 要是数组")
        _check_plan_nodes(children, f"{at}.children")


def count_plan_nodes(nodes: list[Any]) -> int:
    return sum(1 + count_plan_nodes(node.get("children") or []) for node in nodes)


def plan_lines(nodes: list[Any], prefix: str = "", depth: int = 0,
               created: dict[str, str] | None = None) -> list[str]:
    """把计划画成树。建完了就把编号接在后面。"""
    out: list[str] = []
    for index, node in enumerate(nodes, start=1):
        key = f"{prefix}{index}"
        ident = (created or {}).get(key, "")
        tail = f"   → {ident}" if ident else ""
        out.append("  " * depth + f"- [{_fmt.type_label(node['type'])}] {node['title']}{tail}")
        out.extend(plan_lines(node.get("children") or [], key + ".", depth + 1, created))
    return out


def _node_namespace(node: dict[str, Any]) -> argparse.Namespace:
    """把计划里的一个节点伪装成 _workitem_body 认识的那种参数对象。

    这样字段映射（节点字段 → 官方参数字段名）仍然只有一处，不会两句两份。
    """
    return argparse.Namespace(
        title=node.get("title"), description=node.get("description"),
        description_file=node.get("description_file"),
        start=node.get("start"), end=node.get("end"), assignee=node.get("assignee"),
        priority=node.get("priority"), sprint=node.get("sprint"), state=node.get("state"),
        story_points=node.get("story_points"),
        estimated_workload=node.get("estimated_workload"),
        remaining_workload=node.get("remaining_workload"), parent=None,
    )


def _plan_type_id(text: str, client: Any, project_id: str, args: argparse.Namespace) -> str:
    try:
        return _resolve.type_id(client, project_id, text, force=args.no_cache)
    except (_resolve.NotFound, _resolve.Ambiguous):
        if _looks_like_id(text):
            return text
        raise


def _plan_key(path: str) -> tuple[int, ...]:
    """按 1.2.10 这种路径排序 —— 数字段要比数值，不然 10 会排在 2 前面。"""
    parts: list[int] = []
    for part in path.split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _created_summary(created: dict[str, str]) -> str:
    """「已建成的」那一段。抽出来是因为 except 块里不许写布尔表达式（本仓库的检查会拦）。"""
    done = "、".join(created[key] for key in sorted(created, key=_plan_key))
    return done if done else "（无）"


def _create_plan_node(args: argparse.Namespace, client: Any, project_id: str,
                      node: dict[str, Any], parent_id: str, created: dict[str, str],
                      path: str) -> None:
    """深度优先建：**父先子后** —— 子项需要父项的 id。"""
    type_id = _plan_type_id(str(node["type"]), client, project_id, args)
    body: dict[str, Any] = {"project_id": project_id, "type_id": type_id,
                            "title": node["title"]}
    if parent_id:
        body["parent_id"] = parent_id
    body.update(_workitem_body(_node_namespace(node), client, project_id, type_id))
    try:
        result = client.request("POST", WORKITEM, body=body)
    except _client.ApiError as exc:
        # 不能静默半途而废 —— 把已建成的编号报出来，用户才知道不用从头再来
        raise CliError(
            f"建到 {path}（{node['title']}）失败：{exc}\n"
            f"  已建成的：{_created_summary(created)}\n"
            "  修好后把**剩下的子树**单独放一个计划文件再跑（已建成的不会重复建）。"
        ) from exc
    data = result.data if isinstance(result.data, dict) else {}
    new_id = str(data.get("id") or "")
    created[path] = str(data.get("identifier") or new_id or "?")
    print(f"  ✓ {created[path]:11} {_fmt.type_label(type_id):8} {node['title']}")
    for index, child in enumerate(node.get("children") or [], start=1):
        _create_plan_node(args, client, project_id, child, new_id, created, f"{path}.{index}")


def cmd_workitem_create_plan(args: argparse.Namespace) -> int:
    client = build_client(args)
    plan = load_plan(args.file)
    ref = args.project or str(plan.get("project") or "") or pick(args, "project", "project")
    if not ref:
        raise CliError("没说建到哪个项目：在计划文件里写 \"project\"，或加 --project，"
                       "或先 `config context --project <名字>`")
    pid, pname = _resolve.project_id(client, ref, force=args.no_cache)
    nodes = list(plan["nodes"])
    print(f"计划：在「{pname}」建 {count_plan_nodes(nodes)} 条工作项")
    print("\n".join(plan_lines(nodes)))
    print()
    if not args.yes:
        # 「先打印整棵树再建」不靠自觉，靠接口：默认不建，--yes 才建
        print("以上只是计划 —— **没有建任何东西**。确认要建就加 --yes。")
        return 0
    created: dict[str, str] = {}
    for index, node in enumerate(nodes, start=1):
        _create_plan_node(args, client, pid, node, "", created, str(index))
    print()
    print("建成的树：")
    print("\n".join(plan_lines(nodes, created=created)))
    return 0


def cmd_workitem_update(args: argparse.Namespace) -> int:
    client = build_client(args)
    current = fetch_workitem(client, args.ref)
    pid = str(_fmt.dig(current, "project.id") or "")
    tid = str(current.get("type", "") or "")
    body = _workitem_body(args, client, pid, tid)
    if not body:
        raise CliError("没有要改的字段（--title / --description / --assignee / --priority / "
                       "--sprint / --start / --end / --parent / --state / --story-points）")
    path = _api.build("/v1/pjm/workitems/{workitem_id}", workitem_id=current["id"])
    summary = f"更新 {current.get('identifier', args.ref)}：{'、'.join(sorted(body))}"
    result = perform(args, client, "PATCH", path, body=body, summary=summary)
    if result is not None:
        data = result.data if isinstance(result.data, dict) else {}
        emit([_fmt.compact("workitem", data)], args, "workitem", [data])
    return 0


def cmd_workitem_set_state(args: argparse.Namespace) -> int:
    client = build_client(args)
    current = fetch_workitem(client, args.ref)
    pid = str(_fmt.dig(current, "project.id") or "")
    tid = str(current.get("type", "") or "")
    try:
        sid = _resolve.state_id_for(client, pid, tid, args.state, force=args.no_cache)
    except (_resolve.NotFound, _resolve.Ambiguous) as exc:
        # 报错时把「这个类型到底能用哪些状态」贴出来。这里**不强制联网**：
        # 字典有缓存就用缓存，拿不到也不能把原始错误盖掉。
        names = ""
        try:
            available = _resolve.items("states", client, project_id=pid, workitem_type_id=tid)
            names = "、".join(str(s.get("name", "")) for s in available)
        except (_resolve.NotFound, _client.ApiError):
            names = ""
        if not names:
            raise CliError(str(exc)) from exc
        # 只在**这里**报一次可用状态 —— 把 find 那句已经带列表的消息盖掉，
        # 否则同一串状态名会在输出里出现两遍（实测看着很吵）。
        raise CliError(
            f"{_fmt.type_label(tid)}没有叫「{args.state}」的状态。"
            f"这个类型可用：{names}"
        ) from exc
    path = _api.build("/v1/pjm/workitems/{workitem_id}", workitem_id=current["id"])
    summary = f"{current.get('identifier', args.ref)} 状态改为「{args.state}」"
    result = perform(args, client, "PATCH", path, body={"state_id": sid}, summary=summary)
    if result is not None:
        data = result.data if isinstance(result.data, dict) else {}
        emit([_fmt.compact("workitem", data)], args, "workitem", [data])
    return 0


def cmd_workitem_search(args: argparse.Namespace) -> int:
    """POST /v1/pjm/workitems/search —— 结构化条件查询（GET 那套盖不住的场景）。

    操作符写法是**实测**出来的（官方文档只列了名字，没说格式）：
      · 不带 `$` 前缀：`{"in": [...]}` 可以，`{"$in": [...]}` 报 400「缺少有效的操作符」
      · 值必须是**对象**：`{"type": "epic"}` 报 400「值必须是对象」
      · 引用类型用 `属性名.id`；每个属性只能带**一个**操作符；不支持逻辑运算符
      · `identifier` 这类内置属性**不支持**过滤（实测 400）
    """
    client = build_client(args)
    flt: dict[str, Any] = {}
    pid = ""
    if pick(args, "project", "project"):
        pid, _name = need_project(args, client)
        flt["project.id"] = {"in": [pid]}
    if args.type:
        if not pid:
            raise CliError("按类型搜要指定项目：--project（类型是**按项目**配的）")
        flt["type"] = {"in": [resolve_type(args, client, pid)]}
    if args.state:
        if _looks_like_id(args.state):
            flt["state.id"] = {"in": [args.state]}
        else:
            if not (pid and args.type):
                raise CliError("按状态搜要同时给 --project 与 --type"
                               "（状态 id 是按「项目 + 类型」配的），或者直接给状态 id")
            type_id = resolve_type(args, client, pid)
            flt["state.id"] = {"in": [_resolve.state_id_for(client, pid, type_id, args.state,
                                                            force=args.no_cache)]}
    if args.assignee:
        flt["assignee.id"] = {"in": [_resolve.user_id(client, args.assignee, force=args.no_cache)]}
    if args.sprint:
        if not pid:
            raise CliError("按迭代搜要指定项目：--project")
        flt["sprint.id"] = {"in": [_resolve.find("sprints", client, args.sprint,
                                                 force=args.no_cache, project_id=pid)["id"]]}
    if args.title_contains:
        flt["title"] = {"contains": args.title_contains}
    if args.created_after:
        flt["created_at"] = {"gte": _fmt.parse_time(args.created_after)}
    if args.created_before:
        flt.setdefault("created_at", {})["lte"] = _fmt.parse_time(args.created_before)
    if args.filter:
        try:
            extra = json.loads(args.filter)
        except json.JSONDecodeError as exc:
            raise CliError(f"--filter 不是合法 JSON：{exc}") from exc
        if not isinstance(extra, dict):
            raise CliError("--filter 要是一个 JSON 对象，例如 '{\"priority.id\": {\"in\": [\"…\"]}}'")
        flt.update(extra)

    payload: dict[str, Any] = {"filter": flt, "page_size": min(max(1, args.limit), 100),
                               "page_index": 0, "keywords": args.keywords}
    if args.all:
        payload["include_deleted"] = True
        payload["include_archived"] = True
    result = client.request("POST", "/v1/pjm/workitems/search",
                            body={"mode": "query", "payload": payload})
    values = result.values
    if args.full:
        print(json.dumps(result.data, ensure_ascii=False, indent=2))
        return 0
    emit(_fmt.rows("workitem", values), args, "workitem", values)
    if result.total is not None:
        print(f"（命中 {result.total} 条，列了前 {len(values)} 条）")
    return 0


def cmd_workitem_bulk_update(args: argparse.Namespace) -> int:
    """PATCH /v1/pjm/workitems —— 官方限制：**一个属性 + 一个相同值 + ≤100 个 id**。

    所以参数面故意做成「与单条 update 同一套 flag」，但只允许给**一个**：
    给了两个就报错，而不是默默取一个（那样用户以为都改了）。
    """
    client = build_client(args)
    refs = [r.strip() for r in str(args.ids).split(",") if r.strip()]
    if not refs:
        raise CliError("--ids 是空的（用逗号分隔：SCR-1,SCR-2）")
    if len(refs) > 100:
        raise CliError(f"官方限制单次最多 100 个，你给了 {len(refs)} 个 —— 分批跑")
    items = [fetch_workitem(client, ref, include_deleted=bool(args.all)) for ref in refs]
    types = {str(item.get("type", "")) for item in items}
    pid = str(_fmt.dig(items[0], "project.id") or "")
    if args.state and len(types) > 1:
        raise CliError(
            f"这批工作项的类型不一样（{'、'.join(sorted(_fmt.type_label(t) for t in types))}），"
            "而状态 id 是按类型配的 —— 分成几批改，或换成别的属性"
        )
    body = _workitem_body(args, client, pid, sorted(types)[0] if len(types) == 1 else "")
    if len(body) != 1:
        raise CliError(
            f"批量接口一次只能改**一个**属性，你给了 {len(body)} 个：{'、'.join(sorted(body)) or '（一个都没给）'}\n"
            "  分开跑，或者用 create-plan / 逐条 update。"
        )
    name, value = next(iter(body.items()))
    summary = f"把 {len(items)} 条改成 {name}={args.state or args.assignee or args.priority or args.sprint or args.title or value}"
    result = perform(args, client, "PATCH", WORKITEM,
                     body={"ids": [str(i.get("id", "")) for i in items],
                           "property_name": name, "property_value": value}, summary=summary)
    if result is not None:
        data = result.data if isinstance(result.data, dict) else {}
        print(f"✓ 已更新 {data.get('updated', len(items))} 条")
    return 0


def cmd_workitem_comments(args: argparse.Namespace) -> int:
    """列评论：GET /v1/comments?principal_type=workitem&principal_id=<id>。"""
    client = build_client(args)
    current = fetch_workitem(client, args.ref, include_deleted=bool(args.all))
    values = client.paginate(COMMENTS, max_items=args.limit,
                             principal_type="workitem", principal_id=current["id"])
    if args.full:
        print(json.dumps(values, ensure_ascii=False, indent=2))
        return 0
    if not values:
        print(f"{current.get('identifier', args.ref)} 还没有评论")
        return 0
    emit(_fmt.rows("comment", values), args, "comment", values)
    return 0


def cmd_workitem_attachments(args: argparse.Namespace) -> int:
    """列附件：GET /v1/attachments?principal_type=workitem&principal_id=<id>。

    只列不传 —— 上传是 multipart/form-data，字段名没法从文档确认，而且列附件才是
    日常真正要看的那一半（“这个缺陷有没有附日志”）。
    """
    client = build_client(args)
    current = fetch_workitem(client, args.ref, include_deleted=bool(args.all))
    values = client.paginate(ATTACHMENTS, max_items=args.limit,
                             principal_type="workitem", principal_id=current["id"])
    if args.full:
        print(json.dumps(values, ensure_ascii=False, indent=2))
        return 0
    if not values:
        print(f"{current.get('identifier', args.ref)} 没有附件")
        return 0
    emit(_fmt.rows("attachment", values), args, "attachment", values)
    return 0


def cmd_workitem_comment(args: argparse.Namespace) -> int:
    client = build_client(args)
    current = fetch_workitem(client, args.ref)
    body = {"principal_type": "workitem", "principal_id": current["id"], "content": args.content}
    summary = f"给 {current.get('identifier', args.ref)} 加一条评论"
    result = perform(args, client, "POST", COMMENTS, body=body, summary=summary)
    if result is not None and isinstance(result.data, dict):
        print(f"✓ 评论已创建（id={result.data.get('id', '?')}）")
    return 0


def cmd_workitem_delete(args: argparse.Namespace) -> int:
    client = build_client(args)
    current = fetch_workitem(client, args.ref)
    if not args.yes and not args.dry_run:
        raise CliError(
            f"删除是不可逆的。确认要删 {current.get('identifier', args.ref)}"
            f"「{current.get('title', '')}」就加 --yes"
        )
    path = _api.build("/v1/pjm/workitems/{workitem_id}", workitem_id=current["id"])
    summary = f"删除 {current.get('identifier', args.ref)}「{current.get('title', '')}」"
    perform(args, client, "DELETE", path, summary=summary)
    if not args.dry_run:
        print("✓ 已删除")
    return 0


def cmd_project_create(args: argparse.Namespace) -> int:
    client = build_client(args)
    body: dict[str, Any] = {"type": args.type, "name": args.name, "identifier": args.identifier}
    if args.description:
        body["description"] = args.description
    if args.start:
        body["start_at"] = _fmt.parse_time(args.start)
    if args.end:
        body["end_at"] = _fmt.parse_time(args.end)
    if args.assignee:
        body["assignee_id"] = _resolve.user_id(client, args.assignee, force=args.no_cache)
    summary = f"创建项目「{args.name}」（标识 {args.identifier}，类型 {args.type}）"
    result = perform(args, client, "POST", PROJECTS, body=body, summary=summary)
    if result is not None:
        # 新建项目会让「项目列表」这份字典当场过期 —— 不清的话，紧接着建工作项
        # 会报「没有叫 X 的项目」（实测踩到）。
        _resolve.invalidate("projects")
        data = result.data if isinstance(result.data, dict) else {}
        emit([_fmt.compact("project", data)], args, "project", [data])
    return 0


def cmd_project_update(args: argparse.Namespace) -> int:
    client = build_client(args)
    pid, pname = _resolve.project_id(client, args.project, force=args.no_cache)
    body: dict[str, Any] = {}
    if args.name:
        body["name"] = args.name
    if args.identifier:
        body["identifier"] = args.identifier
    if args.description:
        body["description"] = args.description
    if args.start:
        body["start_at"] = _fmt.parse_time(args.start)
    if args.end:
        body["end_at"] = _fmt.parse_time(args.end)
    if args.assignee:
        body["assignee_id"] = _resolve.user_id(client, args.assignee, force=args.no_cache)
    if args.state:
        # 项目状态走 project_states（/v1/pjm/project/states），不是工作项状态表
        body["state_id"] = str(_resolve.find("project_states", client, args.state,
                                            force=args.no_cache, project_id=pid)["id"])
    if not body:
        raise CliError("没有要改的字段（--name / --identifier / --description / --start / "
                       "--end / --assignee / --state）")
    path = _api.build("/v1/pjm/projects/{project_id}", project_id=pid)
    summary = f"更新项目「{pname}」：{'、'.join(sorted(body))}"
    perform(args, client, "PATCH", path, body=body, summary=summary)
    if not args.dry_run:
        # 名字 / 标识改了就缓存里的旧名字就错了
        _resolve.invalidate("projects")
    return 0


# ── 逃生口 ────────────────────────────────────────────────────
def cmd_api(args: argparse.Namespace) -> int:
    forwarded: list[str] = []
    if args.groups:
        forwarded.append("--groups")
    if args.scopes:
        forwarded.append("--scopes")
    if args.list:
        forwarded += ["--list", args.list]
    if args.show:
        forwarded += ["--show", args.show[0], args.show[1]]
    if forwarded:
        return _api.main(forwarded)
    if not args.path:
        raise CliError("要一个路径：--path /v1/pjm/workitems（先用 --list 关键词 找）")
    method = args.method.upper()
    path = args.path.split("?")[0]
    try:
        _api.require(method, path)
    except _api.EndpointError as exc:
        if not args.force:
            raise CliError(f"{exc}\n  确认要用就加 --force") from exc
        print(f"⚠ {exc}", file=sys.stderr)

    params: dict[str, Any] = {}
    for pair in args.param or []:
        key, _, value = pair.partition("=")
        params[key] = value
    query = urllib.parse.urlparse(args.path).query
    for key, value in urllib.parse.parse_qsl(query):
        params[key] = value
    body = None
    if args.data:
        try:
            body = json.loads(args.data)
        except json.JSONDecodeError as exc:
            raise CliError(f"--data 不是合法 JSON：{exc}") from exc
    client = build_client(args)
    result = client.request(method, path, params=params or None, body=body)
    payload = result.data
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.full or args.data
          else json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


# ── 参数表 ────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    def add_common(target: argparse.ArgumentParser, suppress: bool) -> None:
        """全局开关。

        argparse 只认**子命令之前**的全局参数，但人（和 Agent）习惯把它们写在后面
        （`workitem create … --dry-run`）。所以每个子命令也挂一份；
        子命令那份用 `SUPPRESS` 默认值 —— 不然它的默认值会把前面已经解析到的值盖掉。
        """
        default: Any = argparse.SUPPRESS if suppress else False
        target.add_argument("--full", action="store_true", default=default,
                            help="输出原始 JSON（默认紧凑）")
        target.add_argument("--dry-run", action="store_true", default=default,
                            help="写操作只回显请求，不发送")
        target.add_argument("--no-cache", action="store_true", default=default,
                            help="字典不吃缓存，重新拉")
        target.add_argument("--host", default=argparse.SUPPRESS if suppress else "",
                            help="覆盖 credentials.json 里的 host")

    parser = argparse.ArgumentParser(
        prog="pingcode.py",
        description="PingCode 项目 / 工作项命令行（默认紧凑输出，路径来自官方文档生成的端点表）",
    )
    add_common(parser, suppress=False)
    sub = parser.add_subparsers(dest="command", required=True)

    parsers: list[argparse.ArgumentParser] = []

    def make(parent: Any, name: str, **kw: Any) -> argparse.ArgumentParser:
        """建一个子命令解析器并登记 —— 最后统一给它们挂全局开关（含嵌套的）。

        parent 实际是 `_SubParsersAction`（argparse 的私有类型），所以标 Any。
        """
        child: argparse.ArgumentParser = parent.add_parser(name, **kw)
        parsers.append(child)
        return child

    p = make(sub, "auth", help="授权与令牌")
    auth_sub = p.add_subparsers(dest="action", required=True)
    login = make(auth_sub, "login", help="授权（默认用户令牌）")
    login.add_argument("--mode", choices=list(_config.AUTH_MODES), help="user（默认）/ enterprise")
    login.add_argument("--manual", action="store_true", help="手动贴 code，不起本地监听")
    login.add_argument("--code", help="直接给授权码（回调收不到时用：从浏览器地址栏复制 code=…）")
    login.add_argument("--timeout", type=int, default=_auth.CALLBACK_TIMEOUT,
                       help="等回调的秒数（默认 %(default)s）")
    login.set_defaults(func=cmd_auth_login)
    make(auth_sub, "status", help="令牌状态").set_defaults(func=cmd_auth_status)
    make(auth_sub, "logout", help="删掉本地令牌").set_defaults(func=cmd_auth_logout)

    p = make(sub, "whoami", help="我是谁（需要用户令牌）")
    p.set_defaults(func=cmd_whoami)

    cfg = make(sub, "config", help="配置与当前上下文")
    cfg_sub = cfg.add_subparsers(dest="action", required=True)
    make(cfg_sub, "show", help="配置总览").set_defaults(func=cmd_config_show)
    ctx = make(cfg_sub, "context", help="看 / 设当前项目与迭代")
    ctx.add_argument("--project")
    ctx.add_argument("--sprint")
    ctx.add_argument("--clear", action="store_true", help="清空")
    ctx.set_defaults(func=cmd_config_context)
    refresh = make(cfg_sub, "refresh", help="刷新字典缓存")
    refresh.add_argument("--what", help="projects,sprints,types,states,priorities,tags,users；不给就全清")
    refresh.add_argument("--project")
    refresh.set_defaults(func=cmd_config_refresh)

    project = make(sub, "project", help="项目")
    pj = project.add_subparsers(dest="action", required=True)
    pl = make(pj, "list", help="项目列表")
    pl.add_argument("--keywords")
    pl.add_argument("--type", help="scrum / kanban / waterfall / hybrid")
    pl.add_argument("--all", action="store_true",
                     help="连已归档 / 已删除的项目一起列（默认看不到）")
    pl.set_defaults(func=cmd_project_list)
    ps = make(pj, "show", help="一个项目")
    ps.add_argument("project")
    ps.set_defaults(func=cmd_project_show)
    pp = make(pj, "progress", help="项目进度")
    pp.add_argument("--project")
    pp.set_defaults(func=cmd_project_progress)
    pc = make(pj, "create", help="创建项目")
    pc.add_argument("--type", required=True, help="scrum / kanban / waterfall / hybrid")
    pc.add_argument("--name", required=True)
    pc.add_argument("--identifier", required=True, help="项目标识，≤15 位大写字母/数字/_-，全企业唯一")
    pc.add_argument("--description")
    pc.add_argument("--start")
    pc.add_argument("--end")
    pc.add_argument("--assignee", help="负责人（名字 / id / @me）")
    pc.set_defaults(func=cmd_project_create)
    pu = make(pj, "update", help="改项目字段 / 项目状态")
    pu.add_argument("--project")
    pu.add_argument("--name")
    pu.add_argument("--identifier")
    pu.add_argument("--description")
    pu.add_argument("--start")
    pu.add_argument("--end")
    pu.add_argument("--assignee")
    pu.add_argument("--state", help="项目状态名（官方没有删除项目的接口，关闭靠状态）")
    pu.set_defaults(func=cmd_project_update)

    wi = make(sub, "workitem", help="工作项（史诗 / 故事 / 任务 / 缺陷 …）")
    wsub = wi.add_subparsers(dest="action", required=True)
    wl = make(wsub, "list", help="按条件列工作项")
    wl.add_argument("--project")
    wl.add_argument("--type", help="bug / task / story / epic / 缺陷 …")
    wl.add_argument("--state")
    wl.add_argument("--assignee", help="负责人：名字 / id / @me")
    wl.add_argument("--sprint")
    wl.add_argument("--keywords")
    wl.add_argument("--identifier", help="工作项编号，如 SCR-12")
    wl.add_argument("--limit", type=int, default=50)
    wl.add_argument("--all", action="store_true", help="含已归档 / 已删除")
    wl.set_defaults(func=cmd_workitem_list)
    ws = make(wsub, "show", help="一个工作项")
    ws.add_argument("ref", help="编号 / short_id / id")
    ws.add_argument("--all", action="store_true", help="连已删除的一起看（默认看不到已删除的）")
    ws.set_defaults(func=cmd_workitem_show)
    wm = make(wsub, "mine", help="我名下的工作项")
    wm.add_argument("--type")
    wm.add_argument("--limit", type=int, default=100)
    wm.add_argument("--open-only", action="store_true", help="只要未完成的")
    wm.set_defaults(func=cmd_workitem_mine)
    wc = make(wsub, "create", help="创建工作项")
    wc.add_argument("--project")
    wc.add_argument("--type", required=True, help="epic / story / task / bug / 缺陷 / 自定义类型 id")
    wc.add_argument("--title", required=True)
    wc.add_argument("--description")
    wc.add_argument("--description-file", help="从文件读描述（长文本用这个）")
    wc.add_argument("--assignee")
    wc.add_argument("--priority")
    wc.add_argument("--sprint")
    wc.add_argument("--parent", help="父工作项：编号 / id")
    wc.add_argument("--state")
    wc.add_argument("--start", help="开始时间：2026-09-20 / 2026-09-20 18:30")
    wc.add_argument("--end", help="截止时间")
    wc.add_argument("--story-points", type=float)
    wc.add_argument("--estimated-workload", type=float)
    wc.add_argument("--remaining-workload", type=float)
    wc.set_defaults(func=cmd_workitem_create)

    def add_update_flags(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("ref", help="编号 / short_id / id")
        parser.add_argument("--title")
        parser.add_argument("--description")
        parser.add_argument("--description-file")
        parser.add_argument("--assignee")
        parser.add_argument("--priority")
        parser.add_argument("--sprint")
        parser.add_argument("--parent")
        parser.add_argument("--state")
        parser.add_argument("--start")
        parser.add_argument("--end")
        parser.add_argument("--story-points", type=float)
        parser.add_argument("--estimated-workload", type=float)
        parser.add_argument("--remaining-workload", type=float)

    wu = make(wsub, "update", help="改工作项字段（标题 / 描述 / 起止 / 负责人 / 迭代 …）")
    add_update_flags(wu)
    wu.set_defaults(func=cmd_workitem_update)
    wst = make(wsub, "set-state", help="改状态（先查该类型的可用状态）")
    wst.add_argument("ref")
    wst.add_argument("state", help="状态名，如 已完成 / 处理中")
    wst.set_defaults(func=cmd_workitem_set_state)
    ws2 = make(wsub, "search", help="结构化搜索（类 MongoDB 条件，GET 那套盖不住的场景）")
    ws2.add_argument("--project")
    ws2.add_argument("--type", help="bug / task / 缺陷 …（按项目配的）")
    ws2.add_argument("--state", help="状态名（需同时给 --project 与 --type）或状态 id")
    ws2.add_argument("--assignee")
    ws2.add_argument("--sprint")
    ws2.add_argument("--keywords", help="编号或标题关键字")
    ws2.add_argument("--title-contains", help="标题包含（官方 contains 操作符）")
    ws2.add_argument("--created-after", help="创建时间不早于：2026-09-01")
    ws2.add_argument("--created-before", help="创建时间不晚于")
    ws2.add_argument("--filter", help="原始过滤条件 JSON（操作符不带 $ 前缀，值必须是对象）")
    ws2.add_argument("--all", action="store_true", help="含已删除 / 已归档")
    ws2.add_argument("--limit", type=int, default=30)
    ws2.set_defaults(func=cmd_workitem_search)
    wbu = make(wsub, "bulk-update", help="批量改一个属性（官方限制：单属性 + 单值 + ≤100 个）")
    wbu.add_argument("--ids", required=True, help="逗号分隔的编号 / id，最多 100 个")
    wbu.add_argument("--state")
    wbu.add_argument("--assignee")
    wbu.add_argument("--priority")
    wbu.add_argument("--sprint")
    wbu.add_argument("--title")
    wbu.add_argument("--description")
    wbu.add_argument("--start")
    wbu.add_argument("--end")
    wbu.add_argument("--story-points", type=float)
    wbu.add_argument("--all", action="store_true", help="按编号找时含已删除的")
    wbu.set_defaults(func=cmd_workitem_bulk_update)
    wcm = make(wsub, "comment", help="加评论")
    wcm.add_argument("ref")
    wcm.add_argument("content")
    wcm.set_defaults(func=cmd_workitem_comment)
    wcp = make(wsub, "create-plan", help="按计划文件一次建一棵树（默认只打印，--yes 才建）")
    wcp.add_argument("--file", required=True, help="plan.json（字段集封闭：type/title/…/children）")
    wcp.add_argument("--project", help="建到哪个项目（也可写在计划文件的 project 里）")
    wcp.add_argument("--yes", action="store_true", help="确认建（不加则只打印计划）")
    wcp.set_defaults(func=cmd_workitem_create_plan)
    wcl = make(wsub, "comments", help="列评论")
    wcl.add_argument("ref")
    wcl.add_argument("--limit", type=int, default=50)
    wcl.add_argument("--all", action="store_true", help="按编号找时含已删除的")
    wcl.set_defaults(func=cmd_workitem_comments)
    wat = make(wsub, "attachments", help="列附件（上传未实现，见 README 已知限制）")
    wat.add_argument("ref")
    wat.add_argument("--limit", type=int, default=50)
    wat.add_argument("--all", action="store_true", help="按编号找时含已删除的")
    wat.set_defaults(func=cmd_workitem_attachments)
    wd = make(wsub, "delete", help="删除工作项（不可逆）")
    wd.add_argument("ref")
    wd.add_argument("--yes", action="store_true", help="确认删除")
    wd.set_defaults(func=cmd_workitem_delete)

    d = make(sub, "list", help="列字典类数据（项目 / 迭代 / 类型 / 状态 / 优先级 / 标签 / 成员）")
    d.add_argument("kind", choices=sorted(_resolve.SOURCES))
    d.add_argument("--project")
    d.add_argument("--type")
    d.set_defaults(func=cmd_dict_list)

    api = make(sub, "api", help="逃生口：直接调官方接口（先 --list 找路径）")
    api.add_argument("--method", default="GET", choices=list(_api.METHODS))
    api.add_argument("--path")
    api.add_argument("--param", action="append", metavar="k=v", help="可重复")
    api.add_argument("--data", help="JSON 请求体")
    api.add_argument("--force", action="store_true", help="端点不在官方表里也发")
    api.add_argument("--groups", action="store_true")
    api.add_argument("--scopes", action="store_true")
    api.add_argument("--list", metavar="关键词")
    api.add_argument("--show", nargs=2, metavar=("METHOD", "PATH"))
    api.set_defaults(func=cmd_api)

    # 每个子命令（含嵌套的）都挂上全局开关，见 add_common 的说明
    for subparser in parsers:
        add_common(subparser, suppress=True)
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except CliError as exc:
        return _error(str(exc))
    except (_config.ConfigError, _config.TokenError) as exc:
        return _error(str(exc))
    except (_resolve.NotFound, _resolve.Ambiguous) as exc:
        return _error(str(exc))
    except _client.ApiError as exc:
        return _error(str(exc))
    except _fmt.TimeParseError as exc:
        return _error(str(exc))
    except KeyboardInterrupt:
        print("\n已中断", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
