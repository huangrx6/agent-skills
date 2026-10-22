#!/usr/bin/env python3
"""PingCode REST API V2 的路径与字段适配。

V2 与 V1 的差异不只是 `/v1` → `/v2`：

- 工作项编号：响应里是 `identifier`（数字）+ `whole_identifier`（`SCR-5`）；
- 工作项类型：`type` 是对象，系统类型 id 是 24 位，不再能靠 `bug` 枚举映射；
- 日期：`start` / `due` 是 `{date, with_time}` 对象；
- 工作量：`story_points` / `estimated_workload` / `remaining_workload` 在 `properties` 里；
- 项目：`type` → `template_type`；
- 批量改：`POST /v2/pjm/workitems/bulk/set`。

命令层继续用一套“规范字段”（编号字符串、`start_at` / `end_at` 时间戳、
顶层工作量字段），由这里在边界上转换。这样 `format.py` 与命令逻辑不必到处判断版本。
"""

from __future__ import annotations

from typing import Any

# ── 路径 ──────────────────────────────────────────────────────
# 只列本 skill 用到的端点；其余走 `api` 逃生口。
WORKITEMS = "/v2/pjm/workitems"
WORKITEM = "/v2/pjm/workitems/{workitem_id}"
WORKITEM_SEARCH = "/v2/pjm/workitems/search"
WORKITEM_BULK = "/v2/pjm/workitems/bulk/set"
PROJECTS = "/v2/pjm/projects"
PROJECT = "/v2/pjm/projects/{project_id}"
PROJECT_PROGRESS = "/v2/pjm/projects/{project_id}/progress"
COMMENTS = "/v2/comments"
TRANSITION_HISTORIES = "/v2/pjm/workitems/{workitem_id}/transition_histories"
ATTACHMENTS = "/v2/attachments"
ATTACHMENT = ("/v2/attachments/{attachment_id}"
              "?principal_type={principal_type}&principal_id={principal_id}")
OAUTH_ENDPOINT = "/v2/auth/token"
MYSELF = "/v2/myself"

# 字典类端点：kind → url 模板（占位符由 api_index.build 填）。
DICT_PATHS: dict[str, str] = {
    "projects": "/v2/pjm/projects",
    "sprints": "/v2/pjm/sprints?project_id={project_id}",
    "types": "/v2/pjm/workitem/workitem_types?project_id={project_id}",
    "states": ("/v2/pjm/workitem/workitem_states"
               "?project_id={project_id}&workitem_type_id={workitem_type_id}"),
    "project_states": "/v2/pjm/project/project_states?project_id={project_id}",
    "priorities": "/v2/pjm/workitem/workitem_priorities?project_id={project_id}",
    "tags": "/v2/pjm/workitem/workitem_tags?project_id={project_id}",
    "workitem_properties": ("/v2/pjm/workitem/workitem_properties"
                           "?project_id={project_id}&workitem_type_id={workitem_type_id}"),
    "users": "/v2/directory/users",
    # V2 把项目流程改成了项目模板；保留 `list processes` 这个命令名，
    # 避免用户为了“看有哪些流程”再记一个新命令。
    "processes": "/v2/pjm/project_templates",
}

DICT_LABELS: dict[str, str] = {
    "projects": "项目",
    "sprints": "迭代",
    "types": "工作项类型",
    "states": "工作项状态",
    "project_states": "项目状态",
    "priorities": "优先级",
    "tags": "工作项标签",
    "workitem_properties": "工作项属性方案",
    "users": "企业成员",
    "processes": "项目模板",
}

WORKLOAD_FIELDS = ("story_points", "estimated_workload", "remaining_workload")


# ── 响应规范化 ────────────────────────────────────────────────
def _date_of(value: Any) -> Any:
    """`{date, with_time}` → 时间戳；已经是时间戳就原样返回。"""
    if isinstance(value, dict):
        return value.get("date")
    return value


def normalize_sprint(record: dict[str, Any]) -> dict[str, Any]:
    out = dict(record)
    if "start_at" not in out:
        out["start_at"] = _date_of(out.get("start"))
    if "end_at" not in out:
        out["end_at"] = _date_of(out.get("due"))
    return out


def normalize_project(record: dict[str, Any]) -> dict[str, Any]:
    out = dict(record)
    if not out.get("type") and out.get("template_type"):
        out["type"] = out["template_type"]
    if "start_at" not in out:
        out["start_at"] = _date_of(out.get("start"))
    if "end_at" not in out:
        out["end_at"] = _date_of(out.get("due"))
    return out


def normalize_workitem(record: dict[str, Any]) -> dict[str, Any]:
    """把 V2 工作项转成命令层习惯的字段，保留原始字段以免丢信息。"""
    out = dict(record)

    # 编号：优先 whole_identifier；退而求其次用 project.identifier + 数字。
    whole = out.get("whole_identifier")
    ident = out.get("identifier")
    if whole:
        out["identifier"] = whole
    elif isinstance(ident, int):
        prefix = str((out.get("project") or {}).get("identifier") or "")
        out["identifier"] = f"{prefix}-{ident}" if prefix else str(ident)

    # 类型：V2 是对象 {id, name, group}。逻辑用 id，显示用 name。
    kind = out.get("type")
    if isinstance(kind, dict):
        out["type_name"] = kind.get("name") or ""
        out["type_group"] = kind.get("group") or ""
        out["type"] = kind.get("id") or kind.get("group") or kind.get("name") or ""
    elif "type_name" not in out:
        out["type_name"] = ""

    # 日期：对象 → 时间戳。
    if "start_at" not in out:
        out["start_at"] = _date_of(out.get("start"))
    if "end_at" not in out:
        out["end_at"] = _date_of(out.get("due"))

    # 工作量：V2 放在 properties 里；命令层仍按顶层字段读取。
    props = out.get("properties")
    if isinstance(props, dict):
        for key in WORKLOAD_FIELDS:
            if key not in out and key in props:
                out[key] = props[key]

    if isinstance(out.get("sprint"), dict):
        out["sprint"] = normalize_sprint(out["sprint"])
    return out


def normalize(kind: str, record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        return record
    if kind in ("workitem", "comment", "attachment"):
        # 评论/附件的字段与 V1 基本一致；工作项才需要转换。
        return normalize_workitem(record) if kind == "workitem" else dict(record)
    if kind == "project":
        return normalize_project(record)
    if kind == "sprint":
        return normalize_sprint(record)
    return dict(record)


# ── 请求体适配 ────────────────────────────────────────────────
def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"不是数字：{value!r}") from exc


def date_object(timestamp: Any, with_time: Any = 0) -> dict[str, Any]:
    """V2 日期对象。`with_time` 由调用方按输入是否带时分秒决定。"""
    return {"date": _as_int(timestamp), "with_time": 1 if with_time else 0}


def _pop_dates(body: dict[str, Any]) -> dict[str, Any]:
    out = dict(body)
    start_with_time = out.pop("_start_with_time", 0)
    end_with_time = out.pop("_end_with_time", 0)
    if "start_at" in out:
        out["start"] = date_object(out.pop("start_at"), start_with_time)
    if "end_at" in out:
        out["due"] = date_object(out.pop("end_at"), end_with_time)
    return out


def workitem_body(body: dict[str, Any]) -> dict[str, Any]:
    """规范工作项请求体 → V2 请求体。"""
    out = _pop_dates(body)
    props: dict[str, Any] = {}
    for key in WORKLOAD_FIELDS:
        if key in out:
            props[key] = out.pop(key)
    if props:
        existing = out.get("properties")
        if isinstance(existing, dict):
            existing.update(props)
        else:
            out["properties"] = props
    return out


def project_body(body: dict[str, Any]) -> dict[str, Any]:
    """规范项目请求体 → V2 请求体。"""
    out = _pop_dates(body)
    if "type" in out:
        out["template_type"] = out.pop("type")
    return out


def bulk_request(body: dict[str, Any]) -> tuple[str, str, str, Any]:
    """把“一个属性”的规范 body 转成 V2 批量接口的 (method, path, name, value)。"""
    visible = [key for key in body if not key.startswith("_")]
    if len(visible) != 1:
        raise ValueError(f"批量接口一次只能改一个属性，收到 {visible}")
    key = visible[0]
    value = body[key]
    if key == "start_at":
        return "POST", WORKITEM_BULK, "start", date_object(value, body.get("_start_with_time", 0))
    if key == "end_at":
        return "POST", WORKITEM_BULK, "due", date_object(value, body.get("_end_with_time", 0))
    if key in WORKLOAD_FIELDS:
        return "POST", WORKITEM_BULK, f"properties.{key}", value
    return "POST", WORKITEM_BULK, key, value
