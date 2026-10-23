"""从 PingCode 的需求/缺陷生成可复核的周报证据。

唯一数据源是 PingCode。
"""

from __future__ import annotations

import calendar
import re
import tomllib
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from pingcode_read import (
    DEFAULT_DEFECT_TYPES,
    DEFAULT_REQUIREMENT_TYPES,
    PingCodeError,
    history,
    list_sprints,
    list_states,
    list_workitems,
    resolve_project,
    resolve_type,
    select_current_sprint,
    select_next_sprint,
)

DEFAULT_WINDOW_DAYS = 7
DONE_STATE_TYPES = ("completed",)
CLOSED_STATE_TYPES = ("closed",)
WEEK_RE = re.compile(r"^(?P<year>\d{4})-W(?P<week>\d{1,2})$")
MONTH_RE = re.compile(r"^(?P<year>\d{4})-(?P<month>\d{1,2})$")
WORKSPACE_KEYS = {"template", "output_dir"}
PROJECT_KEYS = {
    "name", "pingcode_project", "project", "requirement_types", "defect_types",
    "summary_field", "summary_max_chars", "done_state_types",
}


class CollectError(Exception):
    """参数或数据源失败。"""


def parse_window(*, week: str | None = None, month: str | None = None,
                 since: str | None = None, until: str | None = None,
                 now: datetime | None = None) -> tuple[datetime, datetime]:
    now = (now or datetime.now().astimezone()).astimezone()
    if week and month:
        raise CollectError("--week 和 --month 只能选一个")
    if (week or month) and (since or until):
        raise CollectError("--week / --month 不能和 --since/--until 同时使用")
    if week:
        start, end = _week_bounds(week, now)
        return start, end
    if month:
        start, end = _month_bounds(month, now)
        return start, end
    start = _parse_time(since, now, end_of_day=False) if since else now - timedelta(days=DEFAULT_WINDOW_DAYS)
    end = _parse_time(until, now, end_of_day=True) if until else now
    if start > end:
        raise CollectError("--since 不能晚于 --until")
    return start, end


def week_label(start: datetime, end: datetime) -> str:
    return f"{start.date().isoformat()} ~ {end.date().isoformat()}"


def collect_project(api: Any, project_ref: str, *, since: datetime, until: datetime,
                    requirement_types: list[str] | None = None,
                    defect_types: list[str] | None = None,
                    summary_field: str = "周报摘要",
                    summary_max_chars: int = 300,
                    done_state_types: list[str] | None = None,
                    limit: int = 500) -> dict[str, Any]:
    project = resolve_project(api, project_ref, limit=limit)
    project_id = str(project.get("id") or "")
    requirement_type = resolve_type(api, project_id,
                                    requirement_types or DEFAULT_REQUIREMENT_TYPES,
                                    kind="需求")
    defect_type = resolve_type(api, project_id,
                               defect_types or DEFAULT_DEFECT_TYPES,
                               kind="缺陷")
    requirement_states = _state_map(api, project_id, str(requirement_type.get("id") or ""))
    defect_states = _state_map(api, project_id, str(defect_type.get("id") or ""))
    done_types = tuple(done_state_types or DONE_STATE_TYPES)
    sprints = list_sprints(api, project_id)
    current_sprint = select_current_sprint(sprints, until)
    next_sprint = select_next_sprint(sprints, until)
    updated_range = _epoch_range(since, until)

    requirements_updated, req_truncated = list_workitems(
        api, project_id, str(requirement_type.get("id") or ""), limit=limit,
        updated_between=updated_range,
    )
    bugs_all, bug_truncated = list_workitems(
        api, project_id, str(defect_type.get("id") or ""), limit=limit,
    )
    current_requirements: list[dict[str, Any]] = []
    if current_sprint:
        current_requirements, current_req_truncated = list_workitems(
            api, project_id, str(requirement_type.get("id") or ""), limit=limit,
            sprint_id=str(current_sprint.get("id") or ""),
        )
        req_truncated = req_truncated or current_req_truncated
    next_requirements: list[dict[str, Any]] = []
    next_bugs: list[dict[str, Any]] = []
    if next_sprint:
        next_requirements, next_req_truncated = list_workitems(
            api, project_id, str(requirement_type.get("id") or ""), limit=limit,
            sprint_id=str(next_sprint.get("id") or ""),
        )
        next_bugs, next_bug_truncated = list_workitems(
            api, project_id, str(defect_type.get("id") or ""), limit=limit,
            sprint_id=str(next_sprint.get("id") or ""),
        )
        req_truncated = req_truncated or next_req_truncated
        bug_truncated = bug_truncated or next_bug_truncated

    state_names = {**requirement_states, **defect_states}
    requirements = _normalize_many(
        api, _merge(requirements_updated, current_requirements, next_requirements),
        kind="requirement", since=since, until=until, summary_field=summary_field,
        summary_max_chars=summary_max_chars, state_names=state_names,
        done_state_types=done_types,
        next_sprint_id=str((next_sprint or {}).get("id") or ""),
    )
    bugs = _normalize_many(
        api, _merge(bugs_all, next_bugs), kind="bug", since=since, until=until,
        summary_field=summary_field, summary_max_chars=summary_max_chars,
        state_names=state_names, done_state_types=done_types,
        next_sprint_id=str((next_sprint or {}).get("id") or ""),
    )
    quality = _quality(requirements, bugs, current_sprint, next_sprint,
                       done_state_types=done_types,
                       truncated=req_truncated or bug_truncated)
    return {
        "id": project_id,
        "identifier": project.get("identifier") or project_ref,
        "name": project.get("name") or project_ref,
        "types": {"requirement": _type_row(requirement_type),
                  "defect": _type_row(defect_type)},
        "sprints": {"current": _sprint_row(current_sprint),
                    "next": _sprint_row(next_sprint)},
        "requirements": requirements,
        "bugs": bugs,
        "quality": quality,
        "done_state_types": list(done_types),
    }


def collect_workspace(*, projects: list[dict[str, Any]], since: datetime, until: datetime,
                      limit: int = 500, allow_partial: bool = True) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    api = None
    for spec in projects:
        name = spec.get("name") or spec.get("pingcode_project") or "未命名项目"
        try:
            if api is None:
                from pingcode_read import open_client
                api = open_client()
            row = collect_project(
                api,
                str(spec.get("pingcode_project") or spec.get("project") or name),
                since=since, until=until,
                requirement_types=_as_list(spec.get("requirement_types")),
                defect_types=_as_list(spec.get("defect_types")),
                summary_field=str(spec.get("summary_field") or "周报摘要"),
                summary_max_chars=_as_int(spec.get("summary_max_chars")) or 300,
                done_state_types=_as_list(spec.get("done_state_types")),
                limit=limit,
            )
            row["config_name"] = name
            rows.append(row)
        except (PingCodeError, CollectError, OSError, ValueError) as exc:
            if not allow_partial:
                raise CollectError(f"{name}：{exc}") from exc
            rows.append({"id": "", "identifier": "", "name": name,
                         "error": str(exc), "requirements": [], "bugs": [],
                         "quality": {"error": str(exc), "empty": True, "warnings": [str(exc)]}})
    return {
        "version": 1,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "window": {"since": since.isoformat(), "until": until.isoformat(),
                   "label": week_label(since, until)},
        "projects": rows,
        "quality": _aggregate_quality(rows),
    }


def load_workspace(path: str | Path) -> dict[str, Any]:
    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except OSError as exc:
        raise CollectError(f"读不了工作区配置 {path}：{exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise CollectError(f"工作区配置不是合法 TOML：{exc}") from exc
    projects = data.get("projects")
    if not isinstance(projects, list) or not projects:
        raise CollectError("工作区配置至少需要一个 [[projects]]")
    _validate_workspace(data, Path(path))
    return data


def _validate_workspace(data: dict[str, Any], path: Path) -> None:
    unknown = sorted(set(data) - {"workspace", "projects"})
    if unknown:
        raise CollectError(f"{path}：未知的顶层配置 {'、'.join(unknown)}")
    section = data.get("workspace")
    if section is not None:
        if not isinstance(section, dict):
            raise CollectError(f"{path}：[workspace] 必须是表")
        unknown = sorted(set(section) - WORKSPACE_KEYS)
        if unknown:
            raise CollectError(f"{path}：[workspace] 未知字段 {'、'.join(unknown)}")
        for key in ("template", "output_dir"):
            value = section.get(key)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise CollectError(f"{path}：[workspace].{key} 必须是非空字符串")
    for index, spec in enumerate(data["projects"], 1):
        where = f"{path}：第 {index} 个 [[projects]]"
        if not isinstance(spec, dict):
            raise CollectError(f"{where} 必须是表")
        unknown = sorted(set(spec) - PROJECT_KEYS)
        if unknown:
            raise CollectError(f"{where} 有未知字段 {'、'.join(unknown)}")
        if not any(key in spec for key in ("pingcode_project", "project", "name")):
            raise CollectError(f"{where} 缺少 pingcode_project、project 或 name")
        for key in ("name", "pingcode_project", "project"):
            value = spec.get(key)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise CollectError(f"{where} 的 {key} 必须是非空字符串")
        for key in ("requirement_types", "defect_types", "done_state_types"):
            if key in spec:
                _validate_string_list(spec[key], where, key)
        if "summary_field" in spec and not isinstance(spec["summary_field"], str):
            raise CollectError(f"{where} 的 summary_field 必须是字符串")
        if "summary_max_chars" in spec:
            value = spec["summary_max_chars"]
            if isinstance(value, bool):
                raise CollectError(f"{where} 的 summary_max_chars 必须是 1..10000 的整数")
            try:
                number = int(value)
            except (TypeError, ValueError) as exc:
                raise CollectError(f"{where} 的 summary_max_chars 必须是 1..10000 的整数") from exc
            if not 1 <= number <= 10000:
                raise CollectError(f"{where} 的 summary_max_chars 必须是 1..10000 的整数")


def _validate_string_list(value: Any, where: str, key: str) -> None:
    if isinstance(value, str):
        if not value.strip():
            raise CollectError(f"{where} 的 {key} 不能是空字符串")
        return
    if not isinstance(value, list) or not value:
        raise CollectError(f"{where} 的 {key} 必须是非空字符串或非空字符串列表")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise CollectError(f"{where} 的 {key} 必须是非空字符串或非空字符串列表")


def single_project_workspace(project: str) -> dict[str, Any]:
    return {"projects": [{"name": project, "pingcode_project": project}]}


def _scope_display(assignees: list[str] | None) -> str:
    """优先显示人名，过滤掉纯 ID 形式的匹配键。"""
    values = [str(value) for value in assignees or [] if str(value).strip()]
    names = [value for value in values
             if not re.fullmatch(r"[0-9a-f]{16,}", value.casefold())]
    return "、".join(names or values or ["指定负责人"])


def build_check(payload: dict[str, Any]) -> tuple[bool, list[str]]:
    lines: list[str] = []
    ok = True
    for project in payload.get("projects") or []:
        name = project.get("name") or project.get("config_name") or "项目"
        if project.get("error"):
            ok = False
            lines.append(f"[FAIL] {name}：{project['error']}")
            continue
        quality = project.get("quality") or {}
        if quality.get("empty"):
            ok = False
            lines.append(f"[EMPTY] {name}：窗口内没有 PingCode 需求/缺陷")
        else:
            lines.append(f"[OK] {name}：需求 {len(project.get('requirements') or [])} 条，"
                         f"缺陷 {len(project.get('bugs') or [])} 条")
            types = project.get("types") or {}
            requirement_type = (types.get("requirement") or {}).get("name") or "?"
            defect_type = (types.get("defect") or {}).get("name") or "?"
            lines.append(f"  类型：需求={requirement_type}，缺陷={defect_type}")
            sprints = project.get("sprints") or {}
            current = (sprints.get("current") or {}).get("name")
            nxt = (sprints.get("next") or {}).get("name")
            lines.append(f"  迭代：当前={current or '无'}，下一={nxt or '无'}")
        for label, values in (
            ("缺负责人", quality.get("missing_assignee")),
            ("缺完成时间", quality.get("missing_completion_time")),
            ("缺陷缺严重程度", quality.get("missing_severity")),
            ("状态未映射", quality.get("unmapped_state")),
        ):
            if values:
                lines.append(f"  - {label}：{'、'.join(values[:12])}")
        total = int(quality.get("requirements_total") or 0) + int(quality.get("bugs_total") or 0)
        if total and not quality.get("summary_custom"):
            lines.append("  - 周报摘要：未找到自定义摘要字段，使用描述/标题")
        if quality.get("missing_next_week"):
            lines.append("  - 下周计划：没有找到下一迭代或计划项")
        if quality.get("truncated"):
            lines.append("  - 采集达到上限，结果可能被截断")
        scope = project.get("scope")
        if scope:
            excluded = scope.get("excluded_unassigned") or []
            detail = f"，未分配被排除 {len(excluded)} 条" if excluded else ""
            lines.append(f"  按人过滤（{_scope_display(scope.get('assignees'))}）："
                         f"匹配 {scope.get('matched', 0)} 条{detail}")
        duplicate_of_above = {"窗口内没有 PingCode 需求和缺陷记录",
                              "PingCode 工作项达到采集上限，结果可能被截断"}
        for warning in quality.get("warnings") or []:
            if warning not in duplicate_of_above:
                lines.append(f"  - {warning}")
    return ok, lines


def _normalize_many(api: Any, rows: list[dict[str, Any]], *, kind: str,
                    since: datetime, until: datetime, summary_field: str,
                    summary_max_chars: int,
                    state_names: dict[str, str], done_state_types: tuple[str, ...],
                    next_sprint_id: str) -> list[dict[str, Any]]:
    normalized = []
    for raw in rows:
        item = _normalize(raw, kind=kind, since=since, until=until,
                          summary_field=summary_field,
                          summary_max_chars=summary_max_chars,
                          state_names=state_names,
                          done_state_types=done_state_types,
                          next_sprint_id=next_sprint_id)
        if item["state_type"] in done_state_types and not item["completed_at"]:
            completed = _completion_from_history(api, raw, done_state_types, state_names)
            if completed:
                item["completed_at"] = completed.isoformat()
                item["completed_in_window"] = since <= completed <= until
        normalized.append(item)
    normalized.sort(key=lambda item: _id_sort_key(item["id"]))
    return normalized


def _normalize(raw: dict[str, Any], *, kind: str, since: datetime, until: datetime,
               summary_field: str, summary_max_chars: int,
               state_names: dict[str, str], done_state_types: tuple[str, ...],
               next_sprint_id: str) -> dict[str, Any]:
    state_value = raw.get("state")
    state: dict[str, Any] = state_value if isinstance(state_value, dict) else {}
    state_name = str(state.get("name") or "")
    state_type = str(state.get("type") or state_names.get(state_name, ""))
    created = _dt(raw.get("created_at"))
    updated = _dt(raw.get("updated_at"))
    completed = _dt(raw.get("completed_at") or raw.get("closed_at"))
    sprint_value = raw.get("sprint")
    sprint: dict[str, Any] = sprint_value if isinstance(sprint_value, dict) else {}
    summary, summary_source = _summary(raw, summary_field, summary_max_chars)
    return {
        "id": str(raw.get("identifier") or raw.get("whole_identifier") or raw.get("id") or ""),
        "title": str(raw.get("title") or ""),
        "kind": kind,
        "type": str(raw.get("type_name") or ""),
        "state": state_name,
        "state_type": state_type,
        "assignee": _person(raw.get("assignee")),
        "assignee_id": _person_id(raw.get("assignee")),
        "priority": _name_of(raw.get("priority")),
        "severity": _property(raw, ("severity", "严重程度", "severity_name")),
        "summary": summary,
        "summary_source": summary_source,
        "created_at": _iso(created),
        "updated_at": _iso(updated),
        "completed_at": _iso(completed),
        "sprint": str(sprint.get("name") or ""),
        "parent": _parent(raw),
        "url": raw.get("html_url") or raw.get("url"),
        "open": state_type not in (*done_state_types, *CLOSED_STATE_TYPES),
        "created_in_window": bool(created and since <= created <= until),
        "updated_in_window": bool(updated and since <= updated <= until),
        "completed_in_window": bool(
            completed and state_type in done_state_types and since <= completed <= until
        ),
        "planned": bool(next_sprint_id and str(sprint.get("id") or "") == next_sprint_id),
        "age_days": max(0, (until.date() - created.date()).days) if created else None,
    }


def _summary(raw: dict[str, Any], summary_field: str,
             summary_max_chars: int) -> tuple[str, str]:
    limit = max(1, int(summary_max_chars))
    if summary_field:
        value = _property(raw, (summary_field,))
        if value:
            text = _plain(value)
            return text[:limit] + ("…" if len(text) > limit else ""), "custom"
    description = str(raw.get("description") or "").strip()
    if description:
        first = re.split(r"\n\s*\n", description, maxsplit=1)[0].strip()
        first = _plain(first)
        if first:
            return first[:limit] + ("…" if len(first) > limit else ""), "description"
    return str(raw.get("title") or ""), "title"


def _property(raw: dict[str, Any], names: tuple[str, ...]) -> str | None:
    wanted = {name.casefold() for name in names}
    for name in names:
        value = raw.get(name)
        if value not in (None, ""):
            return _name_of(value)
    for key in ("properties", "entity_properties"):
        props = raw.get(key)
        if isinstance(props, dict):
            for label, value in props.items():
                if str(label).casefold() in wanted:
                    return _name_of(value)
        if isinstance(props, list):
            for entry in props:
                if not isinstance(entry, dict):
                    continue
                label = entry.get("name") or entry.get("key") or entry.get("title")
                if str(label).casefold() in wanted:
                    return _name_of(entry.get("value") or entry.get("values"))
    return None


def _completion_from_history(api: Any, raw: dict[str, Any],
                             done_state_types: tuple[str, ...],
                             state_names: dict[str, str]) -> datetime | None:
    item_id = str(raw.get("id") or "")
    if not item_id:
        return None
    try:
        rows = history(api, item_id)
    except Exception:
        return None
    found = None
    for row in rows:
        value = row.get("to_state")
        to_state: dict[str, Any] = value if isinstance(value, dict) else {}
        to_name = str(to_state.get("name") or "")
        to_type = str(to_state.get("type") or state_names.get(to_name, ""))
        if to_type in done_state_types:
            found = _dt(row.get("created_at")) or found
    return found


def _report_relevant(item: dict[str, Any]) -> bool:
    """和本周报内容相关的条目：未关闭、窗口内完成/新增，或已排入下一迭代。"""
    return bool(item.get("open") or item.get("completed_in_window")
                or item.get("created_in_window") or item.get("planned"))


def _quality(requirements: list[dict[str, Any]], bugs: list[dict[str, Any]],
             current_sprint: dict[str, Any] | None, next_sprint: dict[str, Any] | None,
             *, done_state_types: tuple[str, ...], truncated: bool) -> dict[str, Any]:
    open_bugs = [item for item in bugs if item["open"]]
    done = [item for item in requirements + bugs
            if item["state_type"] in done_state_types]
    missing_completion = [item["id"] for item in done if not item["completed_at"]]
    missing_assignee = [item["id"] for item in requirements + bugs
                        if not item["assignee"] and _report_relevant(item)]
    missing_severity = [item["id"] for item in open_bugs if not item["severity"]]
    unmapped_state = [item["id"] for item in requirements + bugs if not item["state_type"]]
    warnings = []
    if not requirements and not bugs:
        warnings.append("窗口内没有 PingCode 需求和缺陷记录")
    if truncated:
        warnings.append("PingCode 工作项达到采集上限，结果可能被截断")
    return {
        "requirements_total": len(requirements),
        "bugs_total": len(bugs),
        "completed_requirements": sum(1 for item in requirements if item["completed_in_window"]),
        "completed_bugs": sum(1 for item in bugs if item["completed_in_window"]),
        "in_progress_requirements": sum(1 for item in requirements
                                         if item["state_type"] == "in_progress"),
        "open_bugs": len(open_bugs),
        "new_requirements": sum(1 for item in requirements if item["created_in_window"]),
        "new_bugs": sum(1 for item in bugs if item["created_in_window"]),
        "planned_requirements": sum(1 for item in requirements if item["planned"]),
        "planned_bugs": sum(1 for item in bugs if item["planned"]),
        "missing_assignee": missing_assignee,
        "missing_completion_time": missing_completion,
        "missing_severity": missing_severity,
        "unmapped_state": unmapped_state,
        "summary_custom": sum(1 for item in requirements + bugs
                              if item["summary_source"] == "custom"),
        "summary_description": sum(1 for item in requirements + bugs
                                   if item["summary_source"] == "description"),
        "summary_title": sum(1 for item in requirements + bugs
                             if item["summary_source"] == "title"),
        "missing_next_week": not any(item["planned"] for item in requirements + bugs),
        "current_sprint": _sprint_row(current_sprint),
        "next_sprint": _sprint_row(next_sprint),
        "empty": not requirements and not bugs,
        "truncated": truncated,
        "warnings": warnings,
    }


def assignee_names(payload: dict[str, Any]) -> list[str]:
    names = set()
    for project in payload.get("projects") or []:
        if project.get("error"):
            continue
        for item in (project.get("requirements") or []) + (project.get("bugs") or []):
            name = str(item.get("assignee") or "").strip()
            if name:
                names.add(name)
    return sorted(names, key=str.casefold)


def filter_payload(payload: dict[str, Any], wanted: list[str]) -> dict[str, Any]:
    """按负责人 id/名字过滤，并重算每个项目和顶层的 quality。

    未分配负责人的条目不匹配任何人；窗口内这类条目会计入 scope，
    并在 quality.warnings 里显式披露，避免按人周报静默缩水。
    """
    wanted_keys = {str(value).strip().casefold() for value in wanted if str(value).strip()}
    if not wanted_keys:
        return payload
    out = dict(payload)
    projects: list[dict[str, Any]] = []
    for project in payload.get("projects") or []:
        if project.get("error"):
            projects.append(project)
            continue
        row = dict(project)
        requirements = [
            item for item in project.get("requirements") or []
            if _assignee_matches(item, wanted_keys)
        ]
        bugs = [
            item for item in project.get("bugs") or []
            if _assignee_matches(item, wanted_keys)
        ]
        dropped = [
            item for item in (project.get("requirements") or []) + (project.get("bugs") or [])
            if not _assignee_matches(item, wanted_keys)
        ]
        excluded_unassigned = [item["id"] for item in dropped
                               if not item.get("assignee") and _report_relevant(item)]
        row["requirements"] = requirements
        row["bugs"] = bugs
        row["scope"] = {
            "assignees": list(wanted),
            "matched": len(requirements) + len(bugs),
            "excluded_unassigned": excluded_unassigned,
            "excluded_other": len(dropped) - len(excluded_unassigned),
        }
        quality = _quality(
            requirements, bugs,
            (project.get("sprints") or {}).get("current"),
            (project.get("sprints") or {}).get("next"),
            done_state_types=tuple(project.get("done_state_types") or DONE_STATE_TYPES),
            truncated=bool((project.get("quality") or {}).get("truncated")),
        )
        if excluded_unassigned:
            shown = "、".join(excluded_unassigned[:8])
            more = "…" if len(excluded_unassigned) > 8 else ""
            quality["warnings"].append(
                f"按负责人过滤：{len(excluded_unassigned)} 条窗口内工作项未分配负责人，"
                f"不匹配任何人被排除（{shown}{more}）；"
                "它们不会出现在按人周报里，先在 PingCode 补负责人"
            )
        row["quality"] = quality
        projects.append(row)
    out["projects"] = projects
    out["quality"] = _aggregate_quality(projects)
    out["scope"] = {"assignees": list(wanted)}
    return out


def _assignee_matches(item: dict[str, Any], wanted: set[str]) -> bool:
    values = {
        str(item.get("assignee_id") or "").strip().casefold(),
        str(item.get("assignee") or "").strip().casefold(),
    }
    return bool(values & wanted)


def _aggregate_quality(projects: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [project.get("quality") or {} for project in projects]
    return {
        "projects": len(projects),
        "requirements": sum(_as_int(row.get("requirements_total")) for row in rows),
        "bugs": sum(_as_int(row.get("bugs_total")) for row in rows),
        "completed_requirements": sum(_as_int(row.get("completed_requirements")) for row in rows),
        "completed_bugs": sum(_as_int(row.get("completed_bugs")) for row in rows),
        "open_bugs": sum(_as_int(row.get("open_bugs")) for row in rows),
        "new_requirements": sum(_as_int(row.get("new_requirements")) for row in rows),
        "new_bugs": sum(_as_int(row.get("new_bugs")) for row in rows),
        "empty": all(bool(row.get("empty", True)) for row in rows) if rows else True,
        "errors": [project["error"] for project in projects if project.get("error")],
    }


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _merge(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for group in groups:
        for row in group:
            key = str(row.get("id") or row.get("identifier") or row.get("whole_identifier") or "")
            if key and key not in merged:
                merged[key] = row
    return list(merged.values())


def _state_map(api: Any, project_id: str, type_id: str) -> dict[str, str]:
    try:
        states = list_states(api, project_id, type_id)
    except Exception:
        return {}
    return {str(row.get("name") or ""): str(row.get("type") or "")
            for row in states if isinstance(row, dict)}


def _type_row(row: dict[str, Any]) -> dict[str, Any]:
    return {"id": str(row.get("id") or ""), "name": str(row.get("name") or ""),
            "group": str(row.get("group") or "")}


def _sprint_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {"id": str(row.get("id") or ""), "name": str(row.get("name") or ""),
            "status": str(row.get("status") or ""),
            "start_at": row.get("start_at"), "end_at": row.get("end_at")}


def _plain(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value)).strip()
    return re.sub(r"(?<=[。；：！？，、])\s+", "", text)


def _person(value: Any) -> str | None:
    if isinstance(value, dict):
        return str(value.get("display_name") or value.get("name") or value.get("email") or "") or None
    return str(value) if value else None


def _person_id(value: Any) -> str | None:
    if isinstance(value, dict):
        return str(value.get("id") or "") or None
    return None


def _name_of(value: Any) -> str | None:
    if isinstance(value, dict):
        return str(value.get("name") or value.get("display_name") or value.get("value") or "") or None
    if isinstance(value, list):
        names = [_name_of(item) for item in value]
        return "、".join(name for name in names if name) or None
    return str(value) if value not in (None, "") else None


def _parent(raw: dict[str, Any]) -> str | None:
    parent = raw.get("parent")
    if isinstance(parent, dict):
        return str(parent.get("whole_identifier") or parent.get("identifier") or "") or None
    return str(parent) if parent else None


def _as_list(value: Any) -> list[str] | None:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [value]
    return None


def _month_bounds(value: str, now: datetime) -> tuple[datetime, datetime]:
    text = str(value).strip()
    match = MONTH_RE.match(text)
    if not match:
        raise CollectError(f"月份格式不对：{value}（用 YYYY-MM，例如 2026-10）")
    year = int(match.group("year"))
    month = int(match.group("month"))
    if not 1 <= month <= 12:
        raise CollectError(f"月份格式不对：{value}")
    start = datetime(year, month, 1, tzinfo=now.tzinfo)
    last = calendar.monthrange(year, month)[1]
    end = datetime.combine(date(year, month, last), time.max, tzinfo=now.tzinfo)
    return start, end


def _week_bounds(value: str, now: datetime) -> tuple[datetime, datetime]:
    text = str(value).strip()
    match = WEEK_RE.match(text)
    if not match:
        raise CollectError(f"周格式不对：{value}（用 YYYY-Www，例如 2026-W43）")
    try:
        start_date = date.fromisocalendar(int(match.group("year")), int(match.group("week")), 1)
    except ValueError as exc:
        raise CollectError(f"周格式不对：{value}") from exc
    start = datetime.combine(start_date, time.min, tzinfo=now.tzinfo)
    end = datetime.combine(start_date + timedelta(days=6), time.max, tzinfo=now.tzinfo)
    return start, end


def _parse_time(value: str, now: datetime, *, end_of_day: bool) -> datetime:
    text = str(value).strip()
    try:
        if len(text) == 10:
            parsed_date = date.fromisoformat(text)
            return datetime.combine(parsed_date, time.max if end_of_day else time.min,
                                    tzinfo=now.tzinfo)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CollectError(f"时间格式不对：{value}（用 YYYY-MM-DD 或 ISO 日期时间）") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=now.tzinfo)
    return parsed.astimezone(now.tzinfo)


def _epoch_range(start: datetime, end: datetime) -> str:
    return f"{int(start.timestamp())},{int(end.timestamp())}"


def _dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        if isinstance(value, dict):
            value = value.get("date")
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value)).astimezone()
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone()
    except (TypeError, ValueError, OSError):
        return None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") if value else None


def _id_sort_key(value: str) -> tuple[str, int, str]:
    prefix, _, number = str(value).rpartition("-")
    try:
        return prefix, int(number), str(value)
    except ValueError:
        return str(value), 0, str(value)
