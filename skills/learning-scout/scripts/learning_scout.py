#!/usr/bin/env python3
"""Validate a learning journey and render a standalone HTML field guide.

The renderer deliberately does not fetch resources. Research and verification belong to
the agent; this script only enforces structural rules, escapes text, and builds the page.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import html
import json
import os
import re
import sys
import tempfile
import webbrowser
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "templates" / "page.html"
CSS = ROOT / "assets" / "learning.css"
JS = ROOT / "assets" / "learning.js"
PAGED_TEMPLATE = ROOT / "templates" / "page-paged.html"
PAGED_CSS = ROOT / "assets" / "paged.css"
PAGED_JS = ROOT / "assets" / "paged.js"

FORMATS = {
    "docs": "官方文档",
    "blog": "工程博客",
    "video": "视频",
    "course": "课程",
    "paper": "论文",
    "book": "书",
    "repo": "代码库",
    "lab": "实验",
    "podcast": "播客",
    "other": "资源",
}
TIERS = {
    "primary": "一手来源",
    "practitioner": "工程实践",
    "community": "社区课程",
    "video": "视频",
}
THEMES = {
    "deep-field": {"accent": "#c8ff4d", "motif": "orbit", "scheme": "dark"},
    "paper-trail": {"accent": "#d64b2a", "motif": "grid", "scheme": "light"},
    "citrus": {"accent": "#e4572e", "motif": "bloom", "scheme": "light"},
    "blueprint": {"accent": "#62e6ff", "motif": "waves", "scheme": "dark"},
}
MOTIFS = {"orbit", "grid", "waves", "bloom"}
LAYOUTS = {"journey", "atlas", "studio", "paged"}
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
VIDEO_FORMATS = {"video", "course"}

THEME_HINTS = (
    (("rag", "llm", "ai", "ml", "model", "agent", "机器学习", "大模型", "检索"), "deep-field"),
    (("design", "frontend", "css", "ui", "产品", "设计", "创意"), "citrus"),
    (("system", "infra", "cloud", "k8s", "kubernetes", "架构", "后端", "数据库"), "blueprint"),
    (("writing", "history", "philosophy", "写作", "人文", "历史", "阅读"), "paper-trail"),
)


class PlanError(ValueError):
    """The plan cannot be rendered."""


def _text(value: object) -> str:
    return html.escape(str(value), quote=False)


def _inline(value: object) -> str:
    """Escape plain text but allow single-backtick inline code."""
    parts = re.split(r"(`[^`]+`)", str(value))
    return "".join(
        f"<code>{html.escape(part[1:-1])}</code>"
        if len(part) >= 2 and part.startswith("`") and part.endswith("`")
        else html.escape(part, quote=False)
        for part in parts
    )


def _attr(value: object) -> str:
    return html.escape(str(value), quote=True)


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _is_http_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _normalize_url(value: str) -> str:
    parsed = urlparse(value)
    path = parsed.path.rstrip("/") or "/"
    return parsed._replace(path=path).geturl()


def _pick_theme(plan: dict) -> str:
    requested = _as_dict(plan.get("theme")).get("name")
    if requested in THEMES:
        return str(requested)
    headline = " ".join(str(plan.get(key, "")) for key in ("topic", "title")).lower()
    for words, name in THEME_HINTS:
        if any(word in headline for word in words):
            return name
    context = " ".join(str(plan.get(key, "")) for key in ("promise", "why_now")).lower()
    for words, name in THEME_HINTS:
        if any(word in context for word in words):
            return name
    return "deep-field"


def _theme_config(plan: dict, override_name: str | None = None,
                  override_accent: str | None = None,
                  override_motif: str | None = None) -> dict:
    name = override_name or _pick_theme(plan)
    if name not in THEMES:
        raise PlanError(f"未知主题：{name}；可选 {', '.join(THEMES)}")
    base = THEMES[name]
    theme = _as_dict(plan.get("theme"))
    # A theme switch should actually switch the visual language. Keep custom
    # accent/motif when they are explicitly passed, otherwise use the theme's own.
    accent = override_accent or (None if override_name else theme.get("accent")) or base["accent"]
    motif = override_motif or (None if override_name else theme.get("motif")) or base["motif"]
    if not isinstance(accent, str) or not HEX_RE.fullmatch(accent):
        raise PlanError("theme.accent 必须是 #rrggbb 形式的颜色")
    if motif not in MOTIFS:
        raise PlanError(f"未知 motif：{motif}；可选 {', '.join(sorted(MOTIFS))}")
    reason = "由命令行主题覆盖" if override_name else str(theme.get("reason") or "").strip()
    return {"name": name, "accent": accent, "motif": motif,
            "scheme": base["scheme"], "reason": reason}


def _count_practices(stages: list[dict]) -> int:
    return sum(1 for stage in stages if isinstance(stage.get("practice"), dict))


def _validate_resource(resource: object, where: str, errors: list[str],
                       warnings: list[str], seen_urls: dict[str, str]) -> None:
    if not isinstance(resource, dict):
        errors.append(f"{where} 不是对象")
        return
    title = resource.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append(f"{where}.title 不能为空")
    url = resource.get("url")
    if not _is_http_url(url):
        errors.append(f"{where}.url 必须是 http(s) 地址")
    else:
        key = _normalize_url(str(url))
        if key in seen_urls:
            errors.append(f"{where}.url 与 {seen_urls[key]} 重复")
        else:
            seen_urls[key] = where
    fmt = resource.get("format")
    if fmt not in FORMATS:
        errors.append(f"{where}.format 必须是 {', '.join(FORMATS)} 之一")
    tier = resource.get("tier")
    if tier is not None and tier not in TIERS:
        errors.append(f"{where}.tier 必须是 {', '.join(TIERS)} 之一")
    if not resource.get("why"):
        warnings.append(f"{where} 没有写推荐理由（why）")


def validate_plan(plan: object) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). A plan is renderable only when errors is empty."""
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(plan, dict):
        return ["JSON 顶层必须是对象"], warnings
    if plan.get("version") != 1:
        errors.append("version 必须是 1")
    for key in ("topic", "promise"):
        if not isinstance(plan.get(key), str) or not str(plan[key]).strip():
            errors.append(f"{key} 不能为空")
    title_lines = plan.get("title_lines")
    if title_lines is not None:
        if not isinstance(title_lines, list) or not title_lines:
            errors.append("title_lines 必须是非空字符串列表")
        elif any(not isinstance(line, str) or not line.strip() for line in title_lines):
            errors.append("title_lines 里每一行都必须是非空字符串")
    layout = plan.get("layout", "journey")
    if layout not in LAYOUTS:
        errors.append(f"layout 必须是 {'/'.join(sorted(LAYOUTS))} 之一")
    learner = plan.get("learner")
    if learner is not None:
        if not isinstance(learner, dict):
            errors.append("learner 必须是对象")
        else:
            for key in ("level", "background", "goal", "time_per_day"):
                if learner.get(key) is not None and not isinstance(learner[key], str):
                    errors.append(f"learner.{key} 必须是字符串")
            for key in ("preferences", "constraints"):
                if learner.get(key) is not None and not isinstance(learner[key], list):
                    errors.append(f"learner.{key} 必须是列表")
    capstone = plan.get("capstone")
    if capstone is not None and not isinstance(capstone, dict):
        errors.append("capstone 必须是对象")
    elif isinstance(capstone, dict):
        if not str(capstone.get("title", "")).strip():
            errors.append("capstone.title 不能为空")
        if capstone.get("acceptance") is not None and not isinstance(capstone["acceptance"], list):
            errors.append("capstone.acceptance 必须是列表")
    glossary = plan.get("glossary")
    if glossary is not None:
        if not isinstance(glossary, list):
            errors.append("glossary 必须是列表")
        else:
            terms: set[str] = set()
            for index, item in enumerate(glossary):
                where = f"glossary[{index}]"
                if not isinstance(item, dict):
                    errors.append(f"{where} 不是对象")
                    continue
                term = item.get("term")
                if not isinstance(term, str) or not term.strip():
                    errors.append(f"{where}.term 不能为空")
                elif term.strip().casefold() in terms:
                    errors.append(f"{where}.term 重复：{term}")
                else:
                    terms.add(term.strip().casefold())
                if not str(item.get("definition", "")).strip():
                    errors.append(f"{where}.definition 不能为空")
                if item.get("url") is not None and not _is_http_url(item["url"]):
                    errors.append(f"{where}.url 必须是 http(s) 地址")
    prerequisites = plan.get("prerequisites")
    if prerequisites is not None:
        if not isinstance(prerequisites, list):
            errors.append("prerequisites 必须是列表")
        else:
            for index, item in enumerate(prerequisites):
                where = f"prerequisites[{index}]"
                if not isinstance(item, dict) or not str(item.get("skill", "")).strip():
                    errors.append(f"{where} 必须包含 skill")
                elif item.get("why") is not None and not isinstance(item["why"], str):
                    errors.append(f"{where}.why 必须是字符串")

    stages = plan.get("stages")
    if not isinstance(stages, list) or not stages:
        errors.append("stages 必须是非空列表")
        stages = []
    if len(stages) > 8:
        errors.append("stages 最多 8 个阶段；更多内容请拆成两份计划")

    sources = plan.get("sources")
    if not isinstance(sources, dict):
        errors.append("sources 必须是对象，并提供 verified_at")
    else:
        verified = sources.get("verified_at")
        if not isinstance(verified, str) or not DATE_RE.fullmatch(verified):
            errors.append("sources.verified_at 必须是 YYYY-MM-DD")
        else:
            try:
                date.fromisoformat(verified)
            except ValueError:
                errors.append("sources.verified_at 不是有效日期")

    theme = plan.get("theme")
    if theme is not None and not isinstance(theme, dict):
        errors.append("theme 必须是对象")
    else:
        theme = _as_dict(theme)
        name = theme.get("name")
        if name not in (None, "auto") and name not in THEMES:
            errors.append(f"theme.name 必须是 {'/'.join(THEMES)} 或 auto")
        accent = theme.get("accent")
        if accent is not None and (not isinstance(accent, str) or not HEX_RE.fullmatch(accent)):
            errors.append("theme.accent 必须是 #rrggbb")
        motif = theme.get("motif")
        if motif is not None and motif not in MOTIFS:
            errors.append(f"theme.motif 必须是 {'/'.join(sorted(MOTIFS))}")

    stage_ids: set[str] = set()
    section_ids: set[str] = set()
    seen_urls: dict[str, str] = {}
    practices = 0
    resource_count = 0
    for index, stage in enumerate(stages, start=1):
        where = f"stages[{index - 1}]"
        if not isinstance(stage, dict):
            errors.append(f"{where} 不是对象")
            continue
        sid = stage.get("id")
        if not isinstance(sid, str) or not ID_RE.fullmatch(sid):
            errors.append(f"{where}.id 只能包含字母、数字、下划线和短横线")
        elif sid in stage_ids:
            errors.append(f"{where}.id 重复：{sid}")
        else:
            stage_ids.add(sid)
        if not isinstance(stage.get("title"), str) or not str(stage["title"]).strip():
            errors.append(f"{where}.title 不能为空")
        stage_title_lines = stage.get("title_lines")
        if stage_title_lines is not None:
            if not isinstance(stage_title_lines, list) or not stage_title_lines:
                errors.append(f"{where}.title_lines 必须是非空字符串列表")
            elif any(not isinstance(line, str) or not line.strip() for line in stage_title_lines):
                errors.append(f"{where}.title_lines 里每一行都必须是非空字符串")

        sections = stage.get("sections", [])
        if sections is None:
            sections = []
        if not isinstance(sections, list):
            errors.append(f"{where}.sections 必须是列表")
            sections = []
        if layout == "paged" and not sections:
            errors.append(f"{where} 使用 paged 版式时必须提供 sections 笔记内容")
        for sec_index, section in enumerate(sections):
            sec_where = f"{where}.sections[{sec_index}]"
            if not isinstance(section, dict):
                errors.append(f"{sec_where} 不是对象")
                continue
            sec_id = section.get("id")
            if not isinstance(sec_id, str) or not ID_RE.fullmatch(sec_id):
                errors.append(f"{sec_where}.id 只能包含字母、数字、下划线和短横线")
            elif sec_id in section_ids:
                errors.append(f"{sec_where}.id 重复：{sec_id}")
            else:
                section_ids.add(sec_id)
            if not isinstance(section.get("title"), str) or not str(section["title"]).strip():
                errors.append(f"{sec_where}.title 不能为空")
            body = section.get("body")
            if body is not None and (not isinstance(body, list) or any(not isinstance(p, str) for p in body)):
                errors.append(f"{sec_where}.body 必须是字符串列表")
            points = section.get("points")
            if points is not None:
                if not isinstance(points, list):
                    errors.append(f"{sec_where}.points 必须是列表")
                else:
                    for pindex, point in enumerate(points):
                        if not isinstance(point, dict) or not str(point.get("title", "")).strip():
                            errors.append(f"{sec_where}.points[{pindex}] 必须包含 title")
            code = section.get("code")
            if code is not None:
                if not isinstance(code, dict):
                    errors.append(f"{sec_where}.code 必须是对象")
                elif not isinstance(code.get("content"), str) or not code["content"].strip():
                    errors.append(f"{sec_where}.code.content 不能为空")
                status = code.get("status")
                if status is not None and status not in {"tested", "illustrative", "pseudo"}:
                    errors.append(f"{sec_where}.code.status 必须是 tested/illustrative/pseudo")
            if not body and not points and not code:
                errors.append(f"{sec_where} 至少要有 body、points 或 code 之一")
            sec_sources = section.get("sources")
            if sec_sources is not None:
                if not isinstance(sec_sources, list):
                    errors.append(f"{sec_where}.sources 必须是列表")
                else:
                    for src_index, src in enumerate(sec_sources):
                        if not isinstance(src, dict) or not str(src.get("label", "")).strip():
                            errors.append(f"{sec_where}.sources[{src_index}] 必须包含 label")
                        if not _is_http_url(src.get("url")):
                            errors.append(f"{sec_where}.sources[{src_index}].url 必须是 http(s) 地址")
            aside = section.get("aside")
            if aside is not None and not isinstance(aside, dict):
                errors.append(f"{sec_where}.aside 必须是对象")

        resources = stage.get("resources", [])
        if resources is None:
            resources = []
        if not isinstance(resources, list):
            errors.append(f"{where}.resources 必须是列表")
            resources = []
        if len(resources) > 4:
            warnings.append(f"{where} 有 {len(resources)} 个资源；主路线建议 1–3 个")
        for rindex, resource in enumerate(resources):
            _validate_resource(resource, f"{where}.resources[{rindex}]", errors, warnings, seen_urls)
        resource_count += len(resources)

        practice = stage.get("practice")
        if practice is not None:
            if not isinstance(practice, dict):
                errors.append(f"{where}.practice 必须是对象")
            else:
                practices += 1
                if not str(practice.get("title", "")).strip():
                    errors.append(f"{where}.practice.title 不能为空")
                steps = practice.get("steps")
                if steps is not None:
                    if not isinstance(steps, list):
                        errors.append(f"{where}.practice.steps 必须是列表")
                    else:
                        for step_index, step in enumerate(steps):
                            if not isinstance(step, dict) or not str(step.get("do", "")).strip():
                                errors.append(f"{where}.practice.steps[{step_index}] 必须包含 do")
        quiz = stage.get("quiz")
        if quiz is not None:
            if not isinstance(quiz, list):
                errors.append(f"{where}.quiz 必须是列表")
            elif len(quiz) > 5:
                errors.append(f"{where}.quiz 最多 5 题")
            else:
                for qindex, question in enumerate(quiz):
                    qwhere = f"{where}.quiz[{qindex}]"
                    if not isinstance(question, dict):
                        errors.append(f"{qwhere} 不是对象")
                        continue
                    if not str(question.get("question", "")).strip():
                        errors.append(f"{qwhere}.question 不能为空")
                    options = question.get("options")
                    if not isinstance(options, list) or len(options) < 2:
                        errors.append(f"{qwhere}.options 至少要有 2 个选项")
                    answer = question.get("answer")
                    if not isinstance(answer, int) or isinstance(answer, bool):
                        errors.append(f"{qwhere}.answer 必须是选项索引")
                    elif isinstance(options, list) and not 0 <= answer < len(options):
                        errors.append(f"{qwhere}.answer 越界")
        checkpoint = stage.get("checkpoint")
        if checkpoint is not None:
            if not isinstance(checkpoint, dict):
                errors.append(f"{where}.checkpoint 必须是对象")
            elif not str(checkpoint.get("question", "")).strip():
                errors.append(f"{where}.checkpoint.question 不能为空")
        detour = stage.get("detour")
        if detour is not None:
            if not isinstance(detour, dict):
                errors.append(f"{where}.detour 必须是对象")
            else:
                if not str(detour.get("title", "")).strip():
                    errors.append(f"{where}.detour.title 不能为空")
                if detour.get("url") is not None and not _is_http_url(detour["url"]):
                    errors.append(f"{where}.detour.url 必须是 http(s) 地址")
        skills = stage.get("skills")
        if skills is not None and not isinstance(skills, list):
            errors.append(f"{where}.skills 必须是字符串列表")
        misconceptions = stage.get("misconceptions")
        if misconceptions is not None:
            if not isinstance(misconceptions, list):
                errors.append(f"{where}.misconceptions 必须是列表")
            else:
                for m_index, item in enumerate(misconceptions):
                    m_where = f"{where}.misconceptions[{m_index}]"
                    if not isinstance(item, dict) or not str(item.get("wrong", "")).strip():
                        errors.append(f"{m_where} 必须包含 wrong")
                    elif not str(item.get("right", "")).strip():
                        errors.append(f"{m_where}.right 不能为空")
        teach_back = stage.get("teach_back")
        if teach_back is not None and not isinstance(teach_back, str):
            errors.append(f"{where}.teach_back 必须是字符串")
        if not resources and practice is None and checkpoint is None:
            errors.append(f"{where} 至少要有资源、练习或检查点之一")

    if not practices:
        warnings.append("整条路线没有动手任务；学习计划容易变成收藏夹")

    interludes = plan.get("interludes")
    if interludes is not None:
        if not isinstance(interludes, list):
            errors.append("interludes 必须是列表")
        else:
            for index, interlude in enumerate(interludes):
                where = f"interludes[{index}]"
                if not isinstance(interlude, dict):
                    errors.append(f"{where} 不是对象")
                    continue
                after = interlude.get("after")
                if after not in stage_ids:
                    errors.append(f"{where}.after 必须引用一个存在的阶段 id")
                if not str(interlude.get("quote", "")).strip():
                    errors.append(f"{where}.quote 不能为空")

    for key, required in (("not_now", "title"), ("rabbit_holes", "title")):
        values = plan.get(key)
        if values is None:
            continue
        if not isinstance(values, list):
            errors.append(f"{key} 必须是列表")
            continue
        for index, item in enumerate(values):
            if not isinstance(item, dict):
                errors.append(f"{key}[{index}] 不是对象")
                continue
            if not str(item.get(required, "")).strip():
                errors.append(f"{key}[{index}].{required} 不能为空")
            if key == "rabbit_holes" and item.get("url") is not None and not _is_http_url(item["url"]):
                errors.append(f"{key}[{index}].url 必须是 http(s) 地址")

    start = plan.get("start")
    if start is not None:
        if not isinstance(start, dict):
            errors.append("start 必须是对象")
        else:
            for key in ("today", "week_one"):
                if start.get(key) is not None and not isinstance(start[key], list):
                    errors.append(f"start.{key} 必须是列表")

    review = plan.get("review")
    if review is not None:
        if not isinstance(review, list):
            errors.append("review 必须是列表")
        else:
            review_ids: set[str] = set()
            for index, card in enumerate(review):
                where = f"review[{index}]"
                if not isinstance(card, dict):
                    errors.append(f"{where} 不是对象")
                    continue
                card_id = card.get("id")
                if not isinstance(card_id, str) or not ID_RE.fullmatch(card_id):
                    errors.append(f"{where}.id 只能包含字母、数字、下划线和短横线")
                elif card_id in review_ids:
                    errors.append(f"{where}.id 重复：{card_id}")
                else:
                    review_ids.add(card_id)
                if card.get("stage") not in stage_ids:
                    errors.append(f"{where}.stage 必须引用一个存在的阶段 id")
                for key in ("front", "back"):
                    if not str(card.get(key, "")).strip():
                        errors.append(f"{where}.{key} 不能为空")
                if card.get("url") is not None and not _is_http_url(card["url"]):
                    errors.append(f"{where}.url 必须是 http(s) 地址")
    return errors, warnings


def _load(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as handle:
            plan = json.load(handle)
    except FileNotFoundError as exc:
        raise PlanError(f"找不到计划文件：{path}") from exc
    except json.JSONDecodeError as exc:
        raise PlanError(f"JSON 解析失败：{exc}") from exc
    errors, warnings = validate_plan(plan)
    if errors:
        raise PlanError("计划不能渲染：\n- " + "\n- ".join(errors))
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return plan


def _resource_id(stage_id: str, index: int) -> str:
    return f"{stage_id}:r:{index}"


def _resource_action(fmt: str) -> str:
    if fmt in VIDEO_FORMATS:
        return "已看"
    if fmt in {"repo", "lab"}:
        return "已练"
    return "已读"


def _render_resource(resource: dict, stage_id: str, index: int, *,
                     compact: bool = False) -> str:
    fmt = str(resource.get("format", "other"))
    tier = resource.get("tier")
    title = _text(resource.get("title", "未命名资源"))
    why = resource.get("why")
    source = resource.get("source")
    language = resource.get("language")
    time = resource.get("time")
    cost = resource.get("cost")
    meta = " · ".join(_text(item) for item in (language, time, cost) if item)
    tier_text = TIERS.get(str(tier), "") if tier else ""
    label = FORMATS.get(fmt, "资源")
    url = _attr(resource.get("url", "#"))
    key = _attr(_resource_id(stage_id, index))
    action = _resource_action(fmt)
    classes = "resource-card" + (" resource-card--compact" if compact else "")
    why_html = f'<p class="resource-why">{_text(why)}</p>' if why else ""
    source_html = f'<span class="resource-source">{_text(source)}</span>' if source else "<span></span>"
    tier_html = f'<span class="tier">{_text(tier_text)}</span>' if tier_text else ""
    meta_html = f'<span class="resource-meta">{meta}</span>' if meta else ""
    return f"""
    <article class="{classes}" data-format="{_attr(fmt)}" data-tier="{_attr(tier or '')}">
      <div class="resource-top">
        <span class="badge badge--{_attr(fmt)}">{_text(label)}</span>
        {tier_html}
        {meta_html}
      </div>
      <h4><a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a><span class="resource-arrow" aria-hidden="true">↗</span></h4>
      {why_html}
      <div class="resource-foot">
        {source_html}
        <label class="check"><input type="checkbox" data-progress-key="{key}"><span>{_text(action)}</span></label>
      </div>
    </article>"""


def _render_stage(stage: dict, number: int) -> str:
    sid = str(stage.get("id", ""))
    title_lines = _as_list(stage.get("title_lines"))
    title = (
        "".join(f"<span>{_text(line)}</span>" for line in title_lines)
        if title_lines else _text(stage.get("title", ""))
    )
    label = _text(stage.get("label") or f"STAGE {number:02d}")
    kicker = _text(stage.get("kicker", ""))
    hook = stage.get("hook")
    time = stage.get("time")
    goal = stage.get("goal")
    metaphor = stage.get("metaphor")
    resources = _as_list(stage.get("resources"))
    practice = _as_dict(stage.get("practice"))
    checkpoint = _as_dict(stage.get("checkpoint"))
    detour = _as_dict(stage.get("detour"))
    skills = _as_list(stage.get("skills"))

    kicker_html = f' <span class="slash">/</span> {kicker}' if kicker else ""
    hook_html = f'<p class="stage-hook">{_text(hook)}</p>' if hook else ""
    time_html = f'<span class="stage-time">{_text(time)}</span>' if time else ""
    goal_html = f"""
      <div class="note-block">
        <span class="section-label">这一站在解决什么</span>
        <p>{_text(goal)}</p>
      </div>""" if goal else ""
    metaphor_html = f"""
      <blockquote class="metaphor">
        <span class="metaphor-mark" aria-hidden="true">“</span>
        <p>{_text(metaphor)}</p>
      </blockquote>""" if metaphor else ""

    resources_html = ""
    if resources:
        cards = "".join(
            _render_resource(resource, sid, index)
            for index, resource in enumerate(resources)
            if isinstance(resource, dict)
        )
        resources_html = f"""
      <div class="resource-list">
        <div class="section-head"><span class="section-label">读 / 看 / 练</span><span class="section-count">{len(resources):02d}</span></div>
        {cards}
      </div>"""

    practice_html = ""
    if practice:
        brief = practice.get("brief")
        deliverable = practice.get("deliverable")
        ptime = practice.get("time")
        brief_html = f"<p>{_text(brief)}</p>" if brief else ""
        deliverable_html = f'<span><b>交付物</b> {_text(deliverable)}</span>' if deliverable else ""
        ptime_html = f"<span>{_text(ptime)}</span>" if ptime else ""
        practice_html = f"""
      <div class="mission">
        <div class="section-head"><span class="section-label">FIELD MISSION / 动手</span><span class="section-count">做</span></div>
        <h3>{_text(practice.get("title", "动手任务"))}</h3>
        {brief_html}
        <div class="mission-meta">{deliverable_html}{ptime_html}</div>
        <label class="check check--strong"><input type="checkbox" data-progress-key="{_attr(sid + ':practice')}"><span>标记完成</span></label>
      </div>"""

    checkpoint_html = ""
    if checkpoint:
        question = checkpoint.get("question")
        passed = checkpoint.get("pass")
        passed_html = f'<p class="checkpoint-pass"><span>过关标准</span>{_text(passed)}</p>' if passed else ""
        checkpoint_html = f"""
      <div class="checkpoint">
        <div class="section-head"><span class="section-label">CHECKPOINT / 过关</span><span class="section-count">?</span></div>
        <p class="checkpoint-question">{_text(question)}</p>
        {passed_html}
      </div>"""

    skills_html = ""
    if skills:
        items = "".join(f"<li>{_text(item)}</li>" for item in skills if str(item).strip())
        skills_html = f"""
        <div class="side-block skills">
          <span class="section-label">带走的能力</span>
          <ul>{items}</ul>
        </div>"""

    detour_html = ""
    if detour:
        dbrief = detour.get("brief")
        durl = detour.get("url")
        dbrief_html = f"<p>{_text(dbrief)}</p>" if dbrief else ""
        dlink = f'<a href="{_attr(durl)}" target="_blank" rel="noopener noreferrer">去看看 ↗</a>' if durl else ""
        detour_html = f"""
        <div class="side-block detour">
          <span class="section-label">绕路也值得</span>
          <h4>{_text(detour.get("title", ""))}</h4>
          {dbrief_html}
          {dlink}
        </div>"""

    side_html = skills_html + detour_html
    if not side_html:
        side_html = """
        <div class="side-block side-quote">
          <span class="section-label">留一点空白</span>
          <p>这一站不用把所有资料看完。带走一个能说清楚的判断，就可以继续。</p>
        </div>"""
    grid_class = "stage-grid" + ("" if skills_html or detour_html else " stage-grid--single")

    return f"""
  <section class="stage reveal" id="stage-{_attr(sid)}" data-stage="{_attr(sid)}">
    <div class="stage-rail" aria-hidden="true">
      <span class="stage-number">{number:02d}</span>
      <span class="stage-spine"></span>
    </div>
    <div class="stage-body">
      <header class="stage-header">
        <div class="stage-eyebrow"><span>{label}</span>{kicker_html}</div>
        <h2>{title}</h2>
        {hook_html}
        {time_html}
      </header>
      <div class="{grid_class}">
        <div class="stage-main">
          {goal_html}
          {metaphor_html}
          {resources_html}
          {practice_html}
          {checkpoint_html}
        </div>
        <aside class="stage-side">{side_html}</aside>
      </div>
    </div>
  </section>"""


def _layout_name(plan: dict, override: str | None = None) -> str:
    layout = override or plan.get("layout") or "journey"
    if layout not in LAYOUTS:
        raise PlanError(f"未知布局：{layout}；可选 {', '.join(sorted(LAYOUTS))}")
    return str(layout)


def _stage_plain_title(stage: dict) -> str:
    lines = _as_list(stage.get("title_lines"))
    if lines:
        return " ".join(str(line) for line in lines)
    return str(stage.get("title", ""))


def _render_sources(sources: object) -> str:
    items = []
    for src in _as_list(sources):
        if not isinstance(src, dict) or not src.get("url"):
            continue
        label = _text(src.get("label") or src.get("url"))
        items.append(
            f'<a class="source-chip" href="{_attr(src["url"])}" target="_blank" '
            f'rel="noopener noreferrer">{label}<span aria-hidden="true">↗</span></a>'
        )
    if not items:
        return ""
    return f'<div class="source-links"><span class="source-label">依据</span>{"".join(items)}</div>'


def _render_code_block(code: object) -> str:
    if not isinstance(code, dict) or not code.get("content"):
        return ""
    language = str(code.get("language") or "text")
    title = _text(code.get("title") or "源码片段")
    status = str(code.get("status") or "")
    status_text = {"tested": "已运行", "illustrative": "示例代码", "pseudo": "伪代码"}.get(status, "")
    status_html = f'<span class="code-status">{_text(status_text)}</span>' if status_text else ""
    content = html.escape(str(code["content"]))
    hint = '<span class="code-hint">↕ 可滚动</span>' if len(str(code["content"]).splitlines()) > 18 else ""
    return (
        '<figure class="code-card">'
        f'<figcaption><span>{title}</span><span class="code-lang">{status_html}{_text(language)}{hint}</span></figcaption>'
        f'<pre><code class="language-{_attr(language)}">{content}</code></pre>'
        '</figure>'
    )


def _render_page_art(kind: str) -> str:
    return f"""
      <div class="page-art page-art--{_attr(kind)}" aria-hidden="true">
        <span class="page-grid"></span>
        <span class="page-orbit page-orbit--a"></span>
        <span class="page-orbit page-orbit--b"></span>
        <span class="page-orbit page-orbit--c"></span>
        <span class="page-glow"></span>
      </div>"""


def _render_paged_rail(stages: list[dict]) -> str:
    links = []
    for index, stage in enumerate(stages, start=1):
        sid = _attr(stage.get("id", ""))
        title = _text(_stage_plain_title(stage))
        links.append(
            f'<a href="#chapter-{sid}" data-stage="{sid}" aria-label="第 {index} 章：{title}">'
            f'<span>{index:02d}</span><i aria-hidden="true"></i></a>'
        )
    return "".join(links)


def _paged_specs(plan: dict, stages: list[dict]) -> list[dict]:
    specs = [
        {"kind": "cover", "id": "p1", "title": "封面"},
        {"kind": "route", "id": "p2", "title": "路线总览"},
    ]
    if _as_list(plan.get("glossary")) or _as_list(plan.get("prerequisites")):
        specs.append({"kind": "orientation", "id": "p-orientation", "title": "先修与术语"})
    for stage in stages:
        sid = str(stage.get("id", ""))
        specs.append({"kind": "chapter", "id": f"chapter-{sid}",
                      "title": _stage_plain_title(stage), "stage": stage, "stage_id": sid})
        for index, section in enumerate(_as_list(stage.get("sections")), start=1):
            if isinstance(section, dict):
                sec_id = str(section.get("id") or f"note-{index}")
                specs.append({"kind": "note", "id": f"note-{sid}-{sec_id}",
                              "title": str(section.get("title", "")),
                              "stage": stage, "stage_id": sid, "section": section,
                              "section_index": index})
        if stage.get("practice") or stage.get("checkpoint") or stage.get("quiz"):
            specs.append({"kind": "work", "id": f"work-{sid}",
                          "title": f"{_stage_plain_title(stage)} · 动手",
                          "stage": stage, "stage_id": sid})
    if _as_list(plan.get("review")):
        specs.append({"kind": "review", "id": "p-review", "title": "间隔复习"})
    specs.append({"kind": "closing", "id": "p-end", "title": "开始行动"})
    return specs


def _page_shell(spec: dict, index: int, total: int, content: str, next_id: str) -> str:
    kind = str(spec["kind"])
    pid = _attr(spec["id"])
    stage_id = _attr(spec.get("stage_id", ""))
    stage_name = _attr(_stage_plain_title(spec["stage"]) if spec.get("stage") else "")
    label = _text(f"第 {index} 页：{spec.get('title', '')}")
    if index == total:
        next_html = '<a class="page-next" href="#p1">回到开头 <span aria-hidden="true">↑</span></a>'
    else:
        next_html = f'<a class="page-next" href="#{_attr(next_id)}">下一页 <span aria-hidden="true">↓</span></a>'
    return f"""
    <section class="page page--{kind}" id="{pid}" data-page-index="{index}" data-stage="{stage_id}" data-stage-name="{stage_name}" aria-label="{label}">
      {_render_page_art(kind)}
      <div class="page-inner">{content}</div>
      <div class="page-edge">
        <span class="page-edge-index">{index:02d} / {total:02d}</span>
        {next_html}
      </div>
    </section>"""


def _render_cover(plan: dict, title_html: str, specs: list[dict], stages: list[dict]) -> str:
    topic = _text(plan.get("topic", ""))
    promise = _text(plan.get("promise", ""))
    subtitle = plan.get("subtitle")
    audience = plan.get("audience")
    learner = _as_dict(plan.get("learner"))
    notes = sum(len(_as_list(stage.get("sections"))) for stage in stages)
    meta = "".join(
        f"<span>{_text(value)}</span>"
        for value in (plan.get("duration"), plan.get("effort"), plan.get("language"))
        if value
    )
    subtitle_html = f'<p class="cover-subtitle">{_text(subtitle)}</p>' if subtitle else ""
    audience_html = "" if learner else (f'<p class="cover-audience">{_text(audience)}</p>' if audience else "")
    learner_html = ""
    if learner:
        bits = " · ".join(
            _text(learner.get(key, "")) for key in ("goal", "time_per_day")
            if learner.get(key)
        )
        if bits:
            learner_html = f'<p class="cover-learner"><span>起点</span>{bits}</p>'
    return f"""
      <div class="cover-grid">
        <div class="cover-main">
          <p class="eyebrow"><span class="eyebrow-mark">01</span> LEARNING NOTES <span class="eyebrow-topic">/ {topic}</span></p>
          <h1><span class="cover-topic">{topic}</span><em>{title_html}</em></h1>
          <p class="cover-promise">{promise}</p>
          {subtitle_html}
          <div class="cover-meta">{meta}</div>
          <div class="cover-actions">
            <a class="cover-start" href="#p2">开始阅读 <span aria-hidden="true">↓</span></a>
            <a class="cover-resume" id="resume-link" href="#p1" hidden>继续上次 · <span id="resume-label">第 1 页</span></a>
          </div>
          {learner_html}
          {audience_html}
        </div>
        <aside class="cover-aside">
          <span class="cover-aside-label">FIELD NOTES</span>
          <strong>{len(specs):02d}</strong>
          <span class="cover-aside-unit">页 · {notes:02d} 篇笔记</span>
          <p>不是先把链接收藏起来，而是先把一条执行链读懂，再自己写一遍。</p>
          <span class="cover-aside-foot">READ / DO / QUIZ / REVIEW</span>
          <p class="cover-aside-note">每章有笔记、动手、测验；完成记录只保存在本机浏览器。</p>
        </aside>
      </div>"""


def _render_orientation(plan: dict) -> str:
    prereqs = []
    for item in _as_list(plan.get("prerequisites")):
        if isinstance(item, dict) and item.get("skill"):
            why = f'<span>{_inline(item.get("why", ""))}</span>' if item.get("why") else ""
            prereqs.append(f'<li><b>{_text(item.get("skill", ""))}</b>{why}</li>')
    terms = []
    for item in _as_list(plan.get("glossary")):
        if not isinstance(item, dict):
            continue
        source = ""
        if item.get("url"):
            source = (
                f'<a href="{_attr(item["url"])}" target="_blank" rel="noopener noreferrer">'
                f'{_text(item.get("source") or "依据")} ↗</a>'
            )
        terms.append(
            f'<div class="glossary-item"><dt>{_text(item.get("term", ""))}</dt>'
            f'<dd>{_inline(item.get("definition", ""))}{source}</dd></div>'
        )
    prereq_html = f'<ol class="prereq-list">{"" .join(prereqs)}</ol>' if prereqs else ""
    glossary_html = f'<dl class="glossary-list">{"".join(terms)}</dl>' if terms else ""
    return f"""
      <p class="eyebrow"><span class="eyebrow-mark">03</span> ORIENTATION <span class="eyebrow-topic">/ 先修 & 术语</span></p>
      <h2 class="orientation-title">先知道这些词，<br><em>再读源码。</em></h2>
      <p class="orientation-lede">第一次遇到缩写时，先回到这里。术语表不替代正文，但能让你在后面的页面里少停几次。</p>
      <div class="orientation-grid">
        <section><span class="section-label">开始之前，最好会</span>{prereq_html}</section>
        <section><span class="section-label">本笔记会反复用到的词</span>{glossary_html}</section>
      </div>"""


def _render_route(plan: dict, stages: list[dict], specs: list[dict]) -> str:
    rows = []
    for index, stage in enumerate(stages, start=1):
        sid = _attr(stage.get("id", ""))
        sections = len(_as_list(stage.get("sections")))
        rows.append(
            f'<li class="route-row"><span>{index:02d}</span>'
            f'<a href="#chapter-{sid}"><b>{_text(_stage_plain_title(stage))}</b>'
            f'<em>{_text(stage.get("time", ""))} · {sections} 篇笔记 · {len(_as_list(stage.get("quiz")))} 题</em></a></li>'
        )
    outcomes = "".join(
        f'<li><span>{_text(item.get("title", ""))}</span>{_text(item.get("detail", ""))}</li>'
        for item in _as_list(plan.get("outcomes")) if isinstance(item, dict)
    )
    outcomes_html = f'<ul class="route-outcomes">{outcomes}</ul>' if outcomes else ""
    learner = _as_dict(plan.get("learner"))
    learner_html = ""
    if learner:
        bits = " · ".join(
            _text(learner.get(key, "")) for key in ("background", "goal", "time_per_day")
            if learner.get(key)
        )
        prefs = "".join(f"<span>{_text(item)}</span>" for item in _as_list(learner.get("preferences")))
        learner_html = f'<div class="route-learner"><span class="section-label">你的起点</span><p>{bits}</p><div>{prefs}</div></div>'
    return f"""
      <p class="eyebrow"><span class="eyebrow-mark">02</span> THE ROUTE <span class="eyebrow-topic">/ {len(stages):02d} CHAPTERS</span></p>
      <div class="route-heading">
        <h2>不是资料清单，<br><em>是一条能跟着走的路线。</em></h2>
        <p>每章 2–3 篇笔记 → 1 次动手 → 1 次测验。最后按 1 / 3 / 7 天做间隔复习；每一页都告诉你去哪看依据。<br><span class="route-scope">范围：create_agent → middleware → StateGraph → checkpoint；不覆盖所有 integrations、部署和多 Agent。</span></p>
      </div>
      {learner_html}
      <ol class="route-list">{''.join(rows)}</ol>
      {outcomes_html}"""


def _render_chapter(stage: dict, chapter_index: int, next_id: str) -> str:
    sid = _attr(stage.get("id", ""))
    title_lines = _as_list(stage.get("title_lines"))
    title = (
        "".join(f"<span>{_text(line)}</span>" for line in title_lines)
        if title_lines else _text(stage.get("title", ""))
    )
    skills = "".join(f"<li>{_text(item)}</li>" for item in _as_list(stage.get("skills")))
    resources = []
    for resource in _as_list(stage.get("resources")):
        if isinstance(resource, dict) and resource.get("url"):
            resources.append(
                f'<a href="{_attr(resource["url"])}" target="_blank" rel="noopener noreferrer">'
                f'{_text(resource.get("title", ""))}<span aria-hidden="true">↗</span></a>'
            )
    goal = f'<p>{_text(stage.get("goal", ""))}</p>' if stage.get("goal") else ""
    metaphor = stage.get("metaphor")
    metaphor_html = f'<blockquote class="chapter-metaphor">{_text(metaphor)}</blockquote>' if metaphor else ""
    resources_html = f'<div class="chapter-resources"><span>本章资料</span>{"".join(resources)}</div>' if resources else ""
    mistakes = "".join(
        f'<li><s>{_text(item.get("wrong", ""))}</s><p>{_inline(item.get("right", ""))}</p></li>'
        for item in _as_list(stage.get("misconceptions")) if isinstance(item, dict)
    )
    mistakes_html = (
        f'<div class="chapter-watch"><span class="section-label">先纠正误解</span><ul>{mistakes}</ul></div>'
        if mistakes else ""
    )
    teach = stage.get("teach_back")
    teach_html = f'<p class="chapter-teach"><span class="section-label">学完自测</span>{_inline(teach)}</p>' if teach else ""
    return f"""
      <p class="eyebrow"><span class="eyebrow-mark">{chapter_index:02d}</span> {_text(stage.get("label", ""))} <span class="eyebrow-topic">/ {_text(stage.get("kicker", ""))}</span></p>
      <div class="chapter-heading">
        <span class="chapter-index">{chapter_index:02d}</span>
        <h2>{title}</h2>
      </div>
      <p class="chapter-hook">{_text(stage.get("hook", ""))}</p>
      <div class="chapter-grid">
        <div><span class="section-label">本章目标</span>{goal}</div>
        <div><span class="section-label">带走的能力</span><ul>{skills}</ul></div>
      </div>
      {mistakes_html}
      {teach_html}
      {metaphor_html}
      {resources_html}
      <a class="chapter-next" href="#{_attr(next_id)}">进入本章笔记 <span aria-hidden="true">↓</span></a>"""


def _render_note(stage: dict, section: dict, section_index: int) -> str:
    body = "".join(f"<p>{_inline(paragraph)}</p>" for paragraph in _as_list(section.get("body")) if str(paragraph).strip())
    points = "".join(
        f'<li><b>{_text(point.get("title", ""))}</b><span>{_inline(point.get("text", ""))}</span></li>'
        for point in _as_list(section.get("points")) if isinstance(point, dict)
    )
    points_html = f'<ul class="key-points">{points}</ul>' if points else ""
    lede = section.get("lede")
    lede_html = f'<p class="note-lede">{_inline(lede)}</p>' if lede else ""
    eyebrow = section.get("eyebrow") or f"{stage.get('label', '')} / NOTE {section_index:02d}"
    aside = _as_dict(section.get("aside"))
    aside_html = ""
    if aside:
        aside_html = (
            f'<div class="note-aside"><span class="section-label">{_text(aside.get("label", "旁注"))}</span>'
            f'<p>{_inline(aside.get("text", ""))}</p></div>'
        )
    code_html = _render_code_block(section.get("code"))
    sources_html = _render_sources(section.get("sources"))
    side = code_html + aside_html + sources_html
    side_html = f'<aside class="note-side">{side}</aside>' if side else ""
    grid_class = "note-grid" + (" note-grid--single" if not side else "")
    return f"""
      <div class="note-head"><p class="eyebrow"><span class="eyebrow-mark">{section_index:02d}</span> {_text(eyebrow)}</p><span class="note-mark">READ / DO / CHECK</span></div>
      <h2 class="note-title">{_inline(section.get("title", ""))}</h2>
      {lede_html}
      <div class="{grid_class}">
        <div class="note-copy">{body}{points_html}</div>
        {side_html}
      </div>"""


def _render_work(stage: dict) -> str:
    sid = _attr(stage.get("id", ""))
    practice = _as_dict(stage.get("practice"))
    checkpoint = _as_dict(stage.get("checkpoint"))
    p_html = ""
    if practice:
        steps = "".join(
            f"<li><b>{_text(step.get('do', ''))}</b><span>{_inline(step.get('expect', ''))}</span><em>{_inline(step.get('check', ''))}</em></li>"
            for step in _as_list(practice.get("steps")) if isinstance(step, dict)
        )
        steps_html = f'<ol class="work-steps">{steps}</ol>' if steps else ""
        p_html = f"""
        <div class="work-card work-card--mission">
          <span class="section-label">FIELD MISSION / 动手</span>
          <h3>{_inline(practice.get("title", ""))}</h3>
          <p>{_inline(practice.get("brief", ""))}</p>
          {steps_html}
          <div class="work-meta"><span><b>交付物</b>{_text(practice.get("deliverable", ""))}</span><span>{_text(practice.get("time", ""))}</span></div>
        </div>"""
    quiz = [q for q in _as_list(stage.get("quiz")) if isinstance(q, dict)]
    q_html = ""
    if quiz:
        items = []
        for qindex, question in enumerate(quiz, start=1):
            options = "".join(
                f'<button class="quiz-option" type="button" data-index="{option_index}">{_text(option)}</button>'
                for option_index, option in enumerate(_as_list(question.get("options")))
            )
            explain = _inline(question.get("explain", ""))
            explain_html = f'<p class="quiz-explain" hidden>{explain}</p>' if explain else ""
            items.append(
                f'<div class="quiz-item" data-quiz-id="{sid}-q{qindex}" data-stage="{sid}" data-answer="{int(question.get("answer", 0))}">'
                f'<p class="quiz-q"><span>{qindex:02d}</span>{_inline(question.get("question", ""))}</p>'
                f'<div class="quiz-options">{options}</div>{explain_html}</div>'
            )
        q_html = f"""
        <div class="work-card work-card--quiz">
          <span class="section-label">RECALL / 立刻检验</span>
          <h3>别翻回去，先选。</h3>
          {''.join(items)}
        </div>"""
    c_html = ""
    if checkpoint:
        c_html = f"""
        <div class="work-check">
          <span class="section-label">CHECKPOINT / 过关</span>
          <b>{_inline(checkpoint.get("question", ""))}</b>
          <p>{_inline(checkpoint.get("pass", ""))}</p>
        </div>"""
    detour = _as_dict(stage.get("detour"))
    d_html = ""
    if detour:
        d_html = f'<div class="work-detour"><span class="section-label">绕路也值得</span><b>{_text(detour.get("title", ""))}</b><p>{_inline(detour.get("brief", ""))}</p></div>'
    grid_class = "work-grid" + (" work-grid--single" if not q_html else "")
    return f"""
      <div class="work-heading">
        <div><p class="eyebrow"><span class="eyebrow-mark">+</span> FIELD WORK <span class="eyebrow-topic">/ {_text(stage.get("label", ""))}</span></p>
        <h2 class="work-title">把这一章<br><em>变成你自己的东西。</em></h2></div>
        <div class="work-complete">
          <button class="complete-btn" type="button" data-complete-stage="{sid}" aria-pressed="false">标记本章完成</button>
          <span class="complete-state" data-complete-state="{sid}">未完成 · 记录在本机</span>
        </div>
      </div>
      <div class="{grid_class}">{p_html}{q_html}</div>
      {c_html}
      {d_html}"""


def _render_review(plan: dict, stages: list[dict]) -> str:
    labels = {str(stage.get("id", "")): str(stage.get("label", "")) for stage in stages}
    cards = []
    for card in _as_list(plan.get("review")):
        if not isinstance(card, dict):
            continue
        rid = _attr(card.get("id", ""))
        stage_id = str(card.get("stage", ""))
        source_url = card.get("url")
        source_html = (
            f'<a class="review-source" href="{_attr(source_url)}" target="_blank" rel="noopener noreferrer">'
            f'{_text(card.get("source") or "依据")} ↗</a>'
            if source_url else ""
        )
        cards.append(f"""
        <article class="review-card" data-review-id="{rid}" data-stage="{_attr(stage_id)}">
          <div class="review-top"><span>{_text(labels.get(stage_id, "REVIEW"))}</span><span class="review-due" data-review-due>未安排</span></div>
          <p class="review-front">{_inline(card.get("front", ""))}</p>
          <div class="review-back" hidden><p>{_inline(card.get("back", ""))}</p>{source_html}</div>
          <div class="review-actions">
            <button class="review-reveal" type="button">先回忆，再翻面 <span aria-hidden="true">↻</span></button>
            <div class="review-rating" hidden>
              <button type="button" data-rating="1">没懂 · 1 天</button>
              <button type="button" data-rating="2">模糊 · 3 天</button>
              <button type="button" data-rating="3">记住 · 7 天</button>
            </div>
          </div>
        </article>""")
    return f"""
      <p class="eyebrow"><span class="eyebrow-mark">↻</span> REVIEW <span class="eyebrow-topic">/ 间隔复习</span></p>
      <h2 class="review-title">把今天读过的，<br><em>留给一周后的自己。</em></h2>
      <p class="review-lede">每张卡先在心里回答，再翻面。按掌握程度安排 1 / 3 / 7 天后的复习；记录只保存在本机浏览器。</p>
      <div class="review-summary"><span id="review-due-count">0 张待复习</span><span id="weak-count">0 个薄弱章节</span><span>今天：<b id="review-today">—</b></span><span>不联网也能用</span></div>
      <div class="review-grid">{''.join(cards)}</div>
      {_render_capstone(plan)}"""


def _render_capstone(plan: dict) -> str:
    capstone = _as_dict(plan.get("capstone"))
    if not capstone:
        return ""
    acceptance = "".join(f"<span>{_text(item)}</span>" for item in _as_list(capstone.get("acceptance")))
    return f"""
      <div class="review-capstone">
        <span class="section-label">CAPSTONE / 最终交付</span>
        <b>{_text(capstone.get("title", ""))}</b>
        <p>{_inline(capstone.get("brief", ""))}</p>
        <div>{acceptance}</div>
      </div>"""


def _render_closing(plan: dict) -> str:
    start = _as_dict(plan.get("start"))
    today = "".join(f"<li>{_inline(item)}</li>" for item in _as_list(start.get("today")) if str(item).strip())
    week = "".join(f"<li>{_inline(item)}</li>" for item in _as_list(start.get("week_one")) if str(item).strip())
    not_now = "".join(
        f'<li><b>{_text(item.get("title", ""))}</b><span>{_inline(item.get("why", ""))}</span></li>'
        for item in _as_list(plan.get("not_now")) if isinstance(item, dict)
    )
    today_html = f'<div class="closing-column"><span class="section-label">TODAY / 今天</span><ol>{today}</ol></div>' if today else ""
    week_html = f'<div class="closing-column"><span class="section-label">WEEK ONE / 第一周</span><ol>{week}</ol></div>' if week else ""
    not_now_html = f'<div class="closing-not-now"><span class="section-label">NOT NOW / 先别学</span><ul>{not_now}</ul></div>' if not_now else ""
    sources = _as_dict(plan.get("sources"))
    return f"""
      <p class="eyebrow"><span class="eyebrow-mark">↳</span> START HERE <span class="eyebrow-topic">/ 现在</span></p>
      <h2 class="closing-title">不要再收藏了。<br><em>今天先做一件小事。</em></h2>
      <div class="closing-grid">{today_html}{week_html}</div>
      {not_now_html}
      <div class="closing-foot">
        <p>{_text(sources.get("note", ""))}</p>
        <p>资源核验：{_text(sources.get("verified_at", ""))} · 读到这里，去做 Day 1 的第一个实验。</p>
      </div>
      <div class="closing-actions">
        <button id="export-progress" type="button">导出学习记录 .md</button>
        <button id="reset-progress" type="button">重置本机进度</button>
        <span>进度只保存在浏览器 localStorage；换设备不会同步。</span>
      </div>"""


def render_paged_html(plan: dict, theme: dict, layout: str) -> str:
    stages = [s for s in _as_list(plan.get("stages")) if isinstance(s, dict)]
    specs = _paged_specs(plan, stages)
    total = len(specs)
    pages = []
    for index, spec in enumerate(specs, start=1):
        next_id = specs[index]["id"] if index < total else "p1"
        kind = spec["kind"]
        if kind == "cover":
            title_lines = _as_list(plan.get("title_lines"))
            title_html = (
                "".join(f"<span>{_text(line)}</span>" for line in title_lines)
                if title_lines else _text(plan.get("title") or plan.get("topic", ""))
            )
            content = _render_cover(plan, title_html, specs, stages)
        elif kind == "route":
            content = _render_route(plan, stages, specs)
        elif kind == "chapter":
            content = _render_chapter(spec["stage"], next(
                i for i, s in enumerate(stages, start=1) if s is spec["stage"]
            ), next_id)
        elif kind == "note":
            content = _render_note(spec["stage"], spec["section"], int(spec["section_index"]))
        elif kind == "orientation":
            content = _render_orientation(plan)
        elif kind == "work":
            content = _render_work(spec["stage"])
        elif kind == "review":
            content = _render_review(plan, stages)
        else:
            content = _render_closing(plan)
        pages.append(_page_shell(spec, index, total, content, next_id))
    plan_id = hashlib.sha256(
        f"{plan.get('topic', '')}|{plan.get('title', '')}|paged|{plan.get('sources', {}).get('verified_at', '')}".encode()
    ).hexdigest()[:10]
    sources = _as_dict(plan.get("sources"))
    template = PAGED_TEMPLATE.read_text(encoding="utf-8")
    replacements = {
        "LANG": "zh-CN",
        "PAGE_TITLE": _text(f"{plan.get('topic', '')} · 学习笔记"),
        "THEME": _attr(theme["name"]),
        "MOTIF": _attr(theme["motif"]),
        "LAYOUT": _attr(layout),
        "ACCENT": _attr(theme["accent"]),
        "COLOR_SCHEME": "dark" if theme["scheme"] == "dark" else "light",
        "CSS": PAGED_CSS.read_text(encoding="utf-8"),
        "JS": PAGED_JS.read_text(encoding="utf-8"),
        "PLAN_ID": _attr(plan_id),
        "TOPIC": _text(plan.get("topic", "")),
        "TOTAL_PAGES": f"{total:02d}",
        "STAGE_COUNT": f"{len(stages):02d}",
        "PAGE_RAIL": _render_paged_rail(stages),
        "PAGES": "".join(pages),
        "VERIFIED_AT": _text(sources.get("verified_at", "")),
        "SOURCE_NOTE": _text(sources.get("note", "")),
    }
    for key, value in replacements.items():
        marker = "{{" + key + "}}"
        if marker not in template:
            raise PlanError(f"分页模板缺少占位符：{marker}")
        template = template.replace(marker, value)
    leftover = re.search(r"\{\{[A-Z_]+\}\}", template)
    if leftover:
        raise PlanError(f"分页模板存在未替换占位符：{leftover.group(0)}")
    return template


def _render_hero(plan: dict, layout: str, title_html: str, stages: list[dict],
                 resources: list[tuple[dict, str, int]]) -> str:
    topic = _text(plan.get("topic", ""))
    promise = _text(plan.get("promise", ""))
    subtitle = plan.get("subtitle")
    duration = _text(plan.get("duration", ""))
    effort = _text(plan.get("effort", ""))
    language = _text(plan.get("language", ""))
    audience = plan.get("audience")
    meta = "".join(f"<span>{item}</span>" for item in (duration, effort, language) if item)
    subtitle_html = f'<p class="hero-subtitle">{_text(subtitle)}</p>' if subtitle else ""
    audience_html = f'<p class="hero-audience">{_text(audience)}</p>' if audience else ""
    actions = '<a class="hero-cta" href="#stage-' + _attr(stages[0].get("id", "")) + '">从第一站开始 <span aria-hidden="true">↓</span></a>' if stages else ""

    if layout == "atlas":
        rows = "".join(
            f'<li><span>{index:02d}</span><b>{_text(_stage_plain_title(stage))}</b><em>{_text(stage.get("time", ""))}</em></li>'
            for index, stage in enumerate(stages, start=1)
        )
        panel = f"""
        <aside class="atlas-panel">
          <div class="atlas-panel-head"><span>CONTENTS</span><b>{len(stages):02d}</b></div>
          <ol>{rows}</ol>
          <div class="atlas-panel-foot"><span>{len(resources):02d} 份资料</span><span>{_text(plan.get("duration", ""))}</span></div>
        </aside>"""
        return f"""
        <section class="hero hero--atlas">
          <div class="atlas-copy">
            <p class="hero-topic">{topic}</p>
            <h1><em>{title_html}</em></h1>
            <p class="hero-promise">{promise}</p>
            {subtitle_html}
            <div class="hero-meta">{meta}</div>
            {actions}
            {audience_html}
          </div>
          {panel}
        </section>"""

    if layout == "studio":
        ticker = "".join(f"<span>{_text(stage.get('label', ''))} / {_text(_stage_plain_title(stage))}</span>" for stage in stages)
        return f"""
        <section class="hero hero--studio">
          <div class="studio-poster">
            <div class="studio-poster-mark" aria-hidden="true">L / S</div>
            <div class="studio-copy">
              <p class="hero-topic">{topic}</p>
              <h1><em>{title_html}</em></h1>
              <p class="hero-promise">{promise}</p>
              {subtitle_html}
              <div class="hero-meta">{meta}</div>
              {actions}
            </div>
          </div>
          <div class="studio-ticker" aria-hidden="true">{ticker}</div>
          {audience_html}
        </section>"""

    nodes = "".join(
        f'<a class="hero-board-node" href="#stage-{_attr(stage.get("id", ""))}"><span>{index:02d}</span>{_text(stage.get("label", ""))}</a>'
        for index, stage in enumerate(stages, start=1)
    )
    return f"""
    <section class="hero">
      <div class="hero-copy">
        <p class="hero-topic">{topic}</p>
        <h1><em>{title_html}</em></h1>
        <p class="hero-promise">{promise}</p>
        {subtitle_html}
        <div class="hero-meta">{meta}</div>
        <div class="hero-actions">{actions}</div>
        {audience_html}
      </div>
      <div class="hero-board" aria-label="路线轨道">{nodes}</div>
    </section>"""


def _render_stats(plan: dict, stages: list[dict], resources: list[tuple[dict, str, int]]) -> str:
    stats = _as_list(plan.get("stats"))
    if not stats:
        return ""
    items = "".join(
        f'<div class="stat"><strong>{_text(item.get("value", ""))}</strong><span>{_text(item.get("label", ""))}</span></div>'
        for item in stats if isinstance(item, dict)
    )
    return f'<section class="stat-strip" aria-label="路线统计">{items}</section>'


def _render_outcomes(outcomes: list) -> str:
    if not outcomes:
        return ""
    items = "".join(
        f'<li><span>{_text(item.get("title", ""))}</span><p>{_text(item.get("detail", ""))}</p></li>'
        for item in outcomes if isinstance(item, dict)
    )
    return f'<section class="outcomes"><div class="section-head"><span class="section-label">学完能做到</span><span class="section-count">{len(outcomes):02d}</span></div><ul>{items}</ul></section>'


def _render_shelf(resources: list[tuple[dict, str, int]]) -> str:
    cards = "".join(
        _render_resource(resource, sid, index, compact=True)
        for resource, sid, index in resources
    )
    return f'<section class="shelf" id="shelf"><div class="section-head"><span class="section-label">THE LIBRARY</span><span class="section-count">{len(resources):02d}</span></div><div class="shelf-grid">{cards}</div></section>'


def _render_not_now(items: list) -> str:
    if not items:
        return ""
    rows = "".join(
        f'<li><b>{_text(item.get("title", ""))}</b><p>{_text(item.get("why", ""))}</p></li>'
        for item in items if isinstance(item, dict)
    )
    return f'<section class="not-now"><div class="section-head"><span class="section-label">NOT NOW</span><span class="section-count">以后</span></div><ul>{rows}</ul></section>'


def _render_rabbit_holes(items: list) -> str:
    if not items:
        return ""
    rows = "".join(
        f'<li><a href="{_attr(item.get("url", "#"))}" target="_blank" rel="noopener noreferrer">{_text(item.get("title", ""))} <span aria-hidden="true">↗</span></a><p>{_text(item.get("why", ""))}</p></li>'
        for item in items if isinstance(item, dict)
    )
    return f'<section class="rabbit"><div class="section-head"><span class="section-label">RABBIT HOLES</span><span class="section-count">想深挖时</span></div><ul>{rows}</ul></section>'


def _render_start(start: dict) -> str:
    today = "".join(f"<li>{_text(item)}</li>" for item in _as_list(start.get("today")) if str(item).strip())
    week = "".join(f"<li>{_text(item)}</li>" for item in _as_list(start.get("week_one")) if str(item).strip())
    if not today and not week:
        return ""
    today_html = f'<div><span class="section-label">今天</span><ol>{today}</ol></div>' if today else ""
    week_html = f'<div><span class="section-label">第一周</span><ol>{week}</ol></div>' if week else ""
    return f'<section class="start"><div class="section-head"><span class="section-label">START HERE</span><span class="section-count">现在</span></div><div class="start-grid">{today_html}{week_html}</div></section>'


def _render_interlude(interlude: dict) -> str:
    quote = _text(interlude.get("quote", ""))
    note = interlude.get("note")
    source = interlude.get("source")
    note_html = f'<p>{_text(note)}</p>' if note else ""
    source_html = f'<span class="interlude-source">{_text(source)}</span>' if source else ""
    return (
        '<section class="interlude"><div class="interlude-inner">'
        '<span class="interlude-arrow" aria-hidden="true">↳</span>'
        f'<blockquote>{quote}</blockquote>'
        f'<div class="interlude-copy">{note_html}{source_html}</div>'
        '</div></section>'
    )


def render_html(plan: dict, theme: dict, layout: str | None = None) -> str:
    layout = _layout_name(plan, layout)
    if layout == "paged":
        return render_paged_html(plan, theme, layout)
    stages = [s for s in _as_list(plan.get("stages")) if isinstance(s, dict)]
    resources: list[tuple[dict, str, int]] = []
    for stage in stages:
        sid = str(stage.get("id", ""))
        for index, resource in enumerate(_as_list(stage.get("resources"))):
            if isinstance(resource, dict):
                resources.append((resource, sid, index))

    nav = "".join(
        f'<a href="#stage-{_attr(stage.get("id", ""))}"><span>{index:02d}</span>{_text(stage.get("title", ""))}</a>'
        for index, stage in enumerate(stages, start=1)
    )
    interludes_by_stage: dict[str, list] = {}
    for interlude in _as_list(plan.get("interludes")):
        if isinstance(interlude, dict):
            interludes_by_stage.setdefault(str(interlude.get("after", "")), []).append(interlude)

    stage_html = ""
    for index, stage in enumerate(stages, start=1):
        stage_html += _render_stage(stage, index)
        for interlude in interludes_by_stage.get(str(stage.get("id", "")), []):
            stage_html += _render_interlude(interlude)

    theme_name = theme["name"]
    title_lines = _as_list(plan.get("title_lines"))
    title_html = (
        "".join(f"<span>{_text(line)}</span>" for line in title_lines)
        if title_lines else _text(plan.get("title") or plan.get("topic", ""))
    )
    theme_reason = theme.get("reason") or "根据主题、资料形态和阅读节奏选择"
    plan_id = hashlib.sha256(
        f"{plan.get('topic', '')}|{plan.get('title', '')}|{plan.get('sources', {}).get('verified_at', '')}".encode()
    ).hexdigest()[:10]
    sources = _as_dict(plan.get("sources"))
    total = len(resources) + _count_practices(stages)
    template = TEMPLATE.read_text(encoding="utf-8")
    replacements = {
        "LANG": "zh-CN",
        "PAGE_TITLE": _text(f"{plan.get('topic', '')} · 学习路线"),
        "LAYOUT": _attr(layout),
        "THEME": _attr(theme_name),
        "MOTIF": _attr(theme["motif"]),
        "ACCENT": _attr(theme["accent"]),
        "COLOR_SCHEME": "dark" if theme["scheme"] == "dark" else "light",
        "CSS": CSS.read_text(encoding="utf-8"),
        "JS": JS.read_text(encoding="utf-8"),
        "PLAN_ID": _attr(plan_id),
        "PROMISE_ATTR": _attr(plan.get("promise", "")),
        "DURATION": _text(plan.get("duration", "")),
        "EFFORT": _text(plan.get("effort", "")),
        "WHY_NOW": _text(plan.get("why_now") or plan.get("subtitle") or plan.get("promise", "")),
        "THESIS": _text(plan.get("thesis") or plan.get("promise", "")),
        "THEME_REASON": _text(theme_reason),
        "VERIFIED_AT": _text(sources.get("verified_at", "")),
        "SOURCE_NOTE": _text(sources.get("note", "")),
        "TOTAL": str(total),
        "HERO": _render_hero(plan, layout, title_html, stages, resources),
        "STAGE_NAV": nav,
        "STATS": _render_stats(plan, stages, resources),
        "OUTCOMES": _render_outcomes(_as_list(plan.get("outcomes"))),
        "STAGES": stage_html,
        "SHELF": _render_shelf(resources) if resources else "",
        "NOT_NOW": _render_not_now(_as_list(plan.get("not_now"))),
        "RABBIT_HOLES": _render_rabbit_holes(_as_list(plan.get("rabbit_holes"))),
        "START": _render_start(_as_dict(plan.get("start"))),
    }
    for key, value in replacements.items():
        marker = "{{" + key + "}}"
        if marker not in template and key not in {"CSS", "JS"}:
            raise PlanError(f"模板缺少占位符：{marker}")
        template = template.replace(marker, value)
    # Catch a typo instead of silently shipping a broken page.
    leftover = re.search(r"\{\{[A-Z_]+\}\}", template)
    if leftover:
        raise PlanError(f"模板存在未替换占位符：{leftover.group(0)}")
    return template


def _slugify(value: str) -> str:
    value = str(value).strip().lower()
    value = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", value, flags=re.UNICODE)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "learning-plan"


def _output_path(plan: dict, out: str | None, output_dir: str | None) -> Path:
    if out:
        return Path(out).expanduser()
    root = output_dir or os.environ.get("LEARNING_SCOUT_OUTPUT_DIR")
    base = Path(root).expanduser() if root else Path.home() / "Downloads" / "learning-scout"
    stamp = str(_as_dict(plan.get("sources")).get("verified_at", date.today().isoformat()))
    return base / f"{_slugify(str(plan.get('topic', 'learning-plan')))}-{stamp}" / "index.html"


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(temp_name)
        raise


def _print_validation(plan: dict) -> None:
    stages = _as_list(plan.get("stages"))
    resources = sum(len(_as_list(stage.get("resources"))) for stage in stages if isinstance(stage, dict))
    practices = _count_practices(stages)
    print(f"✓ {plan.get('topic', '')}")
    print(f"  {len(stages)} 个阶段 · {resources} 个资源 · {practices} 个动手任务")
    theme = _theme_config(plan)
    layout = _layout_name(plan)
    print(f"  版式：{layout}")
    print(f"  主题：{theme['name']} / {theme['motif']} / {theme['accent']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把学习路线计划渲染成独立 HTML 学习指南")
    sub = parser.add_subparsers(dest="command", required=True)

    validate_cmd = sub.add_parser("validate", help="只校验计划 JSON")
    validate_cmd.add_argument("--input", required=True)

    render_cmd = sub.add_parser("render", help="校验并渲染 HTML")
    render_cmd.add_argument("--input", required=True)
    render_cmd.add_argument("--out", help="完整输出路径")
    render_cmd.add_argument("--output-dir", help="输出目录，默认 ~/Downloads/learning-scout")
    render_cmd.add_argument("--stdout", action="store_true", help="只打印 HTML，不落盘")
    render_cmd.add_argument("--open", action="store_true", help="渲染后用浏览器打开")
    render_cmd.add_argument("--layout", choices=sorted(LAYOUTS))
    render_cmd.add_argument("--theme", choices=sorted(THEMES))
    render_cmd.add_argument("--accent", help="#rrggbb")
    render_cmd.add_argument("--motif", choices=sorted(MOTIFS))

    args = parser.parse_args(argv)
    try:
        plan = _load(Path(args.input).expanduser())
        if args.command == "validate":
            _print_validation(plan)
            return 0

        if args.stdout and args.open:
            raise PlanError("--stdout 不能和 --open 同时使用")
        theme = _theme_config(plan, getattr(args, "theme", None),
                              getattr(args, "accent", None), getattr(args, "motif", None))
        page = render_html(plan, theme, getattr(args, "layout", None))
        layout = _layout_name(plan, getattr(args, "layout", None))
        if args.stdout:
            print(page)
            return 0
        out = _output_path(plan, args.out, args.output_dir)
        _write_atomic(out, page)
        print(f"HTML: {out}")
        print(f"版式: {layout}")
        print(f"主题: {theme['name']} / {theme['motif']} / {theme['accent']}")
        if args.open:
            webbrowser.open(out.resolve().as_uri())
        return 0
    except PlanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
