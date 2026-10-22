"""PingCode 只读访问层：项目、类型、状态、迭代、工作项与流转历史。

这是周报 skill 自带的只读客户端。
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from _pingcode import auth, client, compat, config


class PingCodeError(Exception):
    """PingCode 数据不可用或解析失败。"""


PROJECTS = "/v2/pjm/projects"
TYPES = "/v2/pjm/workitem/workitem_types"
STATES = "/v2/pjm/workitem/workitem_states"
SPRINTS = "/v2/pjm/sprints"
WORKITEMS = "/v2/pjm/workitems"
WORKITEM = "/v2/pjm/workitems/{work_item_id}"
HISTORY = "/v2/pjm/workitems/{work_item_id}/transition_histories"

SYSTEM_TYPES = {
    "epic": "史诗",
    "feature": "特性",
    "story": "用户故事",
    "requirement": "需求",
    "task": "任务",
    "bug": "缺陷",
    "issue": "事务",
}

DEFAULT_REQUIREMENT_TYPES = ("需求", "用户故事", "story", "requirement")
DEFAULT_DEFECT_TYPES = ("缺陷", "bug")


def open_client() -> client.Client:
    try:
        credentials = config.load_credentials()
    except config.ConfigError as exc:
        raise PingCodeError(f"PingCode 配置不可用：{exc}") from exc
    return client.Client(bearer=auth.bearer, host=credentials.host)


def current_user(api: client.Client) -> dict[str, Any]:
    data = auth.whoami(api)
    return {
        "id": str(data.get("id") or "") or None,
        "name": str(data.get("display_name") or data.get("name") or data.get("email") or "") or None,
    }


def list_projects(api: client.Client, limit: int = 500) -> list[dict[str, Any]]:
    return [_project(row) for row in api.paginate(PROJECTS, max_items=limit)]


def resolve_project(api: client.Client, ref: str, limit: int = 500) -> dict[str, Any]:
    wanted = str(ref or "").strip()
    if not wanted:
        raise PingCodeError("必须指定 PingCode 项目（名称、标识或 ID）")
    projects = list_projects(api, limit=limit)
    exact = [row for row in projects
             if wanted in {str(row.get("id")), str(row.get("identifier")), str(row.get("name"))}]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise PingCodeError(_ambiguous("项目", wanted, exact))
    folded = wanted.casefold()
    partial = [row for row in projects
               if folded in str(row.get("name", "")).casefold()
               or folded in str(row.get("identifier", "")).casefold()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        raise PingCodeError(_ambiguous("项目", wanted, partial))
    available = "、".join(f"{row.get('identifier')} {row.get('name')}" for row in projects[:20])
    raise PingCodeError(f"没找到项目 {wanted!r}。可用项目：{available or '当前令牌看不到项目'}")


def list_types(api: client.Client, project_id: str) -> list[dict[str, Any]]:
    return api.paginate(TYPES, max_items=200, project_id=project_id)


def resolve_type(api: client.Client, project_id: str, wanted: str | Iterable[str],
                 kind: str = "工作项") -> dict[str, Any]:
    wanted_values = [wanted] if isinstance(wanted, str) else list(wanted)
    types = list_types(api, project_id)
    if not types:
        raise PingCodeError(f"项目 {project_id} 没有返回工作项类型")
    for text in wanted_values:
        key = str(text).strip().casefold()
        exact = [row for row in types
                 if key in {str(row.get("id", "")).casefold(),
                            str(row.get("name", "")).casefold(),
                            str(row.get("group", "")).casefold()}]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            raise PingCodeError(_ambiguous(f"{kind}类型", str(text), exact))
    # 允许只写“需求/缺陷”，命中系统类型组。
    aliases = {"requirement": {"requirement", "story", "需求", "用户故事"},
               "bug": {"bug", "缺陷"}}
    for text in wanted_values:
        key = str(text).strip().casefold()
        groups = aliases.get(key, set())
        if groups:
            matched = [row for row in types if str(row.get("group", "")).casefold() in groups]
            if len(matched) == 1:
                return matched[0]
    available = "、".join(str(row.get("name") or row.get("id")) for row in types)
    raise PingCodeError(
        f"没找到{kind}类型 {wanted_values!r}。项目可用类型：{available}。"
        "请在配置里写明 requirement_types / defect_types。"
    )


def list_states(api: client.Client, project_id: str, type_id: str) -> list[dict[str, Any]]:
    return api.paginate(STATES, max_items=200,
                        project_id=project_id, workitem_type_id=type_id)


def list_sprints(api: client.Client, project_id: str, limit: int = 200) -> list[dict[str, Any]]:
    return [compat.normalize_sprint(row)
            for row in api.paginate(SPRINTS, max_items=limit, project_id=project_id)]


def select_current_sprint(sprints: list[dict[str, Any]], at: datetime) -> dict[str, Any] | None:
    current = []
    for sprint in sprints:
        start = _dt(sprint.get("start_at"))
        end = _dt(sprint.get("end_at"))
        if (start and end and start <= at <= end) or str(sprint.get("status", "")).lower() == "in_progress":
            current.append(sprint)
    if not current:
        return None
    return max(current, key=lambda sprint: _dt(sprint.get("start_at")) or at)


def select_next_sprint(sprints: list[dict[str, Any]], after: datetime) -> dict[str, Any] | None:
    future = []
    for sprint in sprints:
        start = _dt(sprint.get("start_at"))
        if start and start > after and str(sprint.get("status", "")).lower() != "completed":
            future.append(sprint)
    if future:
        return min(future, key=lambda sprint: _dt(sprint.get("start_at")) or after)
    pending = [sprint for sprint in sprints
               if str(sprint.get("status", "")).lower() == "pending"
               and (_dt(sprint.get("end_at")) or after) > after]
    return pending[0] if pending else None


def list_workitems(api: client.Client, project_id: str, type_id: str,
                   limit: int = 500, **params: Any) -> tuple[list[dict[str, Any]], bool]:
    values = api.paginate(WORKITEMS, max_items=limit,
                          project_id=project_id, type_id=type_id, **params)
    return [_item(row) for row in values], len(values) >= limit


def fetch_workitem(api: client.Client, item_id: str) -> dict[str, Any]:
    return _item(api.get(WORKITEM.format(work_item_id=item_id)).data or {})


def history(api: client.Client, item_id: str, limit: int = 100) -> list[dict[str, Any]]:
    return api.paginate(HISTORY.format(work_item_id=item_id), max_items=limit)


def _project(row: dict[str, Any]) -> dict[str, Any]:
    return compat.normalize_project(row)


def _item(row: dict[str, Any]) -> dict[str, Any]:
    return compat.normalize_workitem(row)


def _ambiguous(kind: str, wanted: str, rows: list[dict[str, Any]]) -> str:
    names = "、".join(f"{row.get('identifier') or row.get('id')} {row.get('name', '')}".strip()
                      for row in rows[:10])
    return f"{kind} {wanted!r} 匹配到多个：{names}。请写完整名称或标识。"


def _dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        value = value.get("date")
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value)).astimezone()
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone()
    except (TypeError, ValueError, OSError):
        return None
