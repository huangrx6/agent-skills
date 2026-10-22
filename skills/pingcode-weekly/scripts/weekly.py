"""把 PingCode 需求/缺陷证据渲染为周报。

模板只读 report 数据，不访问外部系统。默认模板在 templates/default.toml。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

DEFAULT_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "default.toml"
ITEM_LIMIT = 50
GAP_LIMIT = 12
SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4,
                  "最高": 0, "较高": 1, "普通": 2, "较低": 3, "最低": 4}


class TemplateError(Exception):
    """模板缺字段或格式不合法。"""


def render_weekly(payload: dict[str, Any], template_path: str | Path | None = None) -> str:
    body, formats = load_template(template_path)
    projects = payload.get("projects") or []
    window = payload.get("window") or {}
    blocks = {
        "week_start": _date(window.get("since")),
        "week_end": _date(window.get("until")),
        "generated_at": payload.get("generated_at") or "未知",
        "this_week": _this_week(projects, formats),
        "new_items": _new_items(projects, formats),
        "requirements": _requirements(projects, formats),
        "new_bugs": _new_bugs(projects, formats),
        "bugs": _bugs(projects, formats),
        "next_week": _next_week(projects, formats),
        "gaps": _gaps(projects, formats),
    }
    text = body
    for key, value in blocks.items():
        text = text.replace("{" + key + "}", value)
    missing = sorted(set(re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", text)))
    if missing:
        raise TemplateError(f"模板字段不存在：{'、'.join(missing)}")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def load_template(path: str | Path | None = None) -> tuple[str, dict[str, str]]:
    import tomllib

    target = Path(path) if path else DEFAULT_TEMPLATE
    try:
        with open(target, "rb") as handle:
            data = tomllib.load(handle)
    except OSError as exc:
        raise TemplateError(f"读不了模板 {target}：{exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise TemplateError(f"模板不是合法 TOML：{exc}") from exc
    layout = data.get("layout")
    if not isinstance(layout, dict) or not isinstance(layout.get("body"), str):
        raise TemplateError("模板缺 [layout] body")
    formats = data.get("format") or {}
    if not isinstance(formats, dict):
        raise TemplateError("[format] 必须是表")
    return str(layout["body"]), {str(key): str(value) for key, value in formats.items()}


def _this_week(projects: list[dict[str, Any]], formats: dict[str, str]) -> str:
    lines: list[str] = []
    for project in projects:
        if project.get("error"):
            continue
        items = [item for item in project.get("requirements") or []
                 if item.get("completed_in_window") or item.get("state_type") == "in_progress"]
        items += [item for item in project.get("bugs") or []
                  if item.get("completed_in_window") or item.get("state_type") == "in_progress"]
        if not items:
            continue
        lines += _project_block(project, items, formats, "requirement")
    return "\n".join(lines) or "本周没有已完成或进行中的 PingCode 需求/缺陷。"


def _new_items(projects: list[dict[str, Any]], formats: dict[str, str]) -> str:
    lines: list[str] = []
    for project in projects:
        if project.get("error"):
            continue
        items = [item for item in project.get("requirements") or []
                 if item.get("created_in_window")
                 and item.get("open")
                 and item.get("state_type") != "in_progress"
                 and not item.get("planned")]
        if items:
            lines += _project_block(project, items, formats, "requirement")
    return "\n".join(lines) or "本周没有新增待开始需求。"


def _new_bugs(projects: list[dict[str, Any]], formats: dict[str, str]) -> str:
    lines: list[str] = []
    for project in projects:
        if project.get("error"):
            continue
        items = [item for item in project.get("bugs") or [] if item.get("created_in_window")]
        items.sort(key=_bug_sort_key)
        if items:
            lines += _project_block(project, items, formats, "new_bug")
    return "\n".join(lines) or "本周没有新增缺陷。"


def _requirements(projects: list[dict[str, Any]], formats: dict[str, str]) -> str:
    lines: list[str] = []
    for project in projects:
        if project.get("error"):
            continue
        items = [item for item in project.get("requirements") or []
                 if item.get("completed_in_window") or item.get("state_type") == "in_progress"]
        if items:
            lines += _project_block(project, items, formats, "requirement")
    return "\n".join(lines) or "本周没有已完成或进行中的需求。"


def _bugs(projects: list[dict[str, Any]], formats: dict[str, str]) -> str:
    lines: list[str] = []
    for project in projects:
        if project.get("error"):
            continue
        items = [item for item in project.get("bugs") or [] if item.get("open")]
        items.sort(key=_bug_sort_key)
        if items:
            lines += _project_block(project, items, formats, "open_bug")
    return "\n".join(lines) or "无未关闭缺陷。"


def _next_week(projects: list[dict[str, Any]], formats: dict[str, str]) -> str:
    lines: list[str] = []
    for project in projects:
        if project.get("error"):
            continue
        items = [item for item in (project.get("requirements") or []) + (project.get("bugs") or [])
                 if item.get("planned")]
        if items:
            lines += _project_block(project, items, formats, "next_item")
    return "\n".join(lines) or "下周计划未在 PingCode 录入。"


def _gaps(projects: list[dict[str, Any]], formats: dict[str, str]) -> str:
    entries: list[str] = []
    for project in projects:
        name = project.get("name") or project.get("config_name") or "项目"
        if project.get("error"):
            entries.append(f"- {name}：{project['error']}")
            continue
        quality = project.get("quality") or {}
        for key, label in (("missing_assignee", "缺负责人"),
                           ("missing_completion_time", "完成项缺完成时间"),
                           ("missing_severity", "未关闭缺陷缺严重程度"),
                           ("unmapped_state", "状态未映射")):
            values = quality.get(key) or []
            if values:
                entries.append(f"- {name} {label}：{'、'.join(str(v) for v in values[:GAP_LIMIT])}")
        if quality.get("missing_next_week"):
            entries.append(f"- {name}：没有找到下一迭代/计划项")
        if quality.get("truncated"):
            entries.append(f"- {name}：PingCode 采集达到上限，结果可能被截断")
        for warning in quality.get("warnings") or []:
            entries.append(f"- {name}：{warning}")
    if not entries:
        return ""
    return "## 数据缺口\n\n" + "\n".join(entries)


def _project_block(project: dict[str, Any], items: list[dict[str, Any]],
                   formats: dict[str, str], default_kind: str) -> list[str]:
    name = project.get("name") or project.get("config_name") or "项目"
    lines = [_line(formats.get("project", "**{name}**："), {"name": name})]
    for item in items[:ITEM_LIMIT]:
        kind = "bug" if item.get("kind") == "bug" else "requirement"
        key = default_kind if default_kind in ("open_bug", "new_bug", "next_item") else kind
        fmt = formats.get(key) or formats.get(kind) or "- {summary}"
        lines.append(_line(fmt, _values(item)))
    if len(items) > ITEM_LIMIT:
        lines.append(f"- 还有 {len(items) - ITEM_LIMIT} 条未列出。")
    lines.append("")
    return lines


def _values(item: dict[str, Any]) -> dict[str, Any]:
    item_id = str(item.get("id") or "")
    url = item.get("url")
    return {
        "id": item_id,
        "link": f"[{item_id}]({url})" if url else item_id,
        "title": item.get("title") or "",
        "summary": item.get("summary") or item.get("title") or "",
        "state": item.get("state") or "未知",
        "assignee": item.get("assignee") or "未分配",
        "severity": item.get("severity") or "未分级",
        "priority": item.get("priority") or "未设置",
        "age_days": item.get("age_days") if item.get("age_days") is not None else "?",
        "type": item.get("type") or ("缺陷" if item.get("kind") == "bug" else "需求"),
    }


def _line(template: str, values: dict[str, Any]) -> str:
    try:
        return template.format_map(values)
    except KeyError as exc:
        raise TemplateError(f"模板字段 {{{exc.args[0]}}} 在条目里不存在") from exc
    except ValueError as exc:
        raise TemplateError(f"模板格式不合法：{template}") from exc


def _bug_sort_key(item: dict[str, Any]) -> tuple[int, str]:
    severity = str(item.get("severity") or "")
    return SEVERITY_ORDER.get(severity, 9), str(item.get("id") or "")


def _date(value: Any) -> str:
    text = str(value or "")
    return text[:10] if len(text) >= 10 else text or "未知"
