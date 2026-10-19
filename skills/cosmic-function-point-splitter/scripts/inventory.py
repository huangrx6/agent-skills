#!/usr/bin/env python3
"""接口与页面清单：把「素材里有什么」变成可核对的覆盖证据。

拆 COSMIC 时最容易出的错不是算错移动，而是整块模块没进表。实测过一次 234 个接口
只转出 283 个功能过程、漏掉 24 个真实接口（分发服务器管理、站内通知、操作日志、
重试策略查询整块丢失），原因是聚合时只顺着模块往下写，没有反向核对。

这里只做确定性核对，不猜关系：
  - 每个接口要么被某个过程的 `evidence` 认领，要么进「未覆盖」清单；
  - 过程里写了不存在的接口 id，进「悬空证据」清单；
  - 页面有导航但没有接口，进「空页面」清单（可能是纯前端页，也可能漏提取）。

覆盖通过只证明清单与规格对得上，不证明接口清单本身完整或需求理解正确。
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

VERSION = 1


@dataclass
class Inventory:
    source: str = ""
    endpoints: list[dict] = field(default_factory=list)
    pages: list[dict] = field(default_factory=list)


@dataclass
class Coverage:
    endpoints: int = 0
    claimed: int = 0
    uncovered: list[dict] = field(default_factory=list)
    dangling: list[str] = field(default_factory=list)
    ownership_issues: list[str] = field(default_factory=list)
    pages: int = 0
    pages_with_endpoints: int = 0
    empty_pages: list[dict] = field(default_factory=list)
    unclaimed_pages: list[dict] = field(default_factory=list)
    suggestions: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.uncovered and not self.dangling and not self.ownership_issues

    @property
    def page_ratio(self) -> float:
        return self.pages_with_endpoints / self.pages if self.pages else 1.0


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"清单有误：{message}")


def load(path: str | Path) -> Inventory:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"无法读取清单 {path}：{exc}") from None
    _require(isinstance(raw, dict), f"{path} 顶层必须是对象")
    _require(type(raw.get("version")) is int and raw["version"] == VERSION,
             f"{path} 的 version 必须为 {VERSION}")
    endpoints = raw.get("endpoints")
    _require(isinstance(endpoints, list) and bool(endpoints), f"{path} 的 endpoints 必须是非空列表")
    ids = set()
    for index, item in enumerate(endpoints, 1):
        _require(isinstance(item, dict), f"endpoints[{index}] 必须是对象")
        for key in ("id", "path"):
            _require(_text(item.get(key)), f"endpoints[{index}].{key} 不能为空")
        _require(item["id"] not in ids, f"endpoint id 重复：{item['id']}")
        ids.add(item["id"])
        if "method" in item:
            _require(_text(item["method"]), f"endpoints[{index}].method 必须是非空字符串")
        if "process" in item and item["process"] is not None:
            _require(_text(item["process"]), f"endpoints[{index}].process 必须是非空字符串")
    pages = raw.get("pages", [])
    _require(isinstance(pages, list), f"{path} 的 pages 必须是数组")
    page_ids = set()
    for index, page in enumerate(pages, 1):
        _require(isinstance(page, dict), f"pages[{index}] 必须是对象")
        _require(_text(page.get("id")), f"pages[{index}].id 不能为空")
        _require(page["id"] not in page_ids, f"page id 重复：{page['id']}")
        page_ids.add(page["id"])
        refs = page.get("endpoints", [])
        _require(isinstance(refs, list), f"pages[{index}].endpoints 必须是数组")
        for ref in refs:
            _require(isinstance(ref, str) and ref in ids, f"pages[{index}] 引用了不存在的接口 {ref}")
    return Inventory(source=str(raw.get("source", "")), endpoints=endpoints, pages=pages)


def coverage(spec: dict, inventory: Inventory) -> Coverage:
    known = {item["id"] for item in inventory.endpoints}
    process_ids = {process['id'] for process in spec.get('processes', [])}
    claimed_by = {item['id']: {item['process']} if item.get('process') else set()
                  for item in inventory.endpoints}
    for process in spec.get("processes", []):
        for endpoint in process.get("evidence", []):
            claimed_by.setdefault(endpoint, set()).add(process['id'])

    result = Coverage(endpoints=len(inventory.endpoints), pages=len(inventory.pages))
    result.dangling = sorted({ref for process in spec.get("processes", [])
                              for ref in process.get("evidence", []) if ref not in known})
    found = Counter()
    for item in inventory.endpoints:
        owners = claimed_by.get(item["id"], set())
        unknown = owners - process_ids
        if unknown:
            result.ownership_issues.append(f"{item['id']} 引用了不存在的过程：{', '.join(sorted(unknown))}")
        if len(owners) > 1:
            result.ownership_issues.append(f"{item['id']} 过程归属冲突：{', '.join(sorted(owners))}")
        if len(owners) == 1 and not unknown:
            result.claimed += 1
            found[item["id"]] = 1
        else:
            result.uncovered.append(item)
    names = [(process["id"], process["name"]) for process in spec.get("processes", [])]
    for item in result.uncovered:
        summary = str(item.get("summary", "")).strip()
        key = summary[:4]
        if key:
            for pid, name in names:
                if key and key in name:
                    result.suggestions.append((item["id"], pid))
                    break
    for page in inventory.pages:
        refs = page.get("endpoints", [])
        if not refs:
            result.empty_pages.append(page)
        else:
            result.pages_with_endpoints += 1
            if not any(found[ref] for ref in refs):
                result.unclaimed_pages.append(page)
    return result


def as_dict(result: Coverage) -> dict:
    return {
        "endpoints": result.endpoints,
        "claimed": result.claimed,
        "uncovered": result.uncovered,
        "dangling": result.dangling,
        "ownership_issues": result.ownership_issues,
        "pages": result.pages,
        "pages_with_endpoints": result.pages_with_endpoints,
        "empty_pages": result.empty_pages,
        "unclaimed_pages": result.unclaimed_pages,
        "suggestions": result.suggestions,
    }


def render(result: Coverage) -> str:
    lines = [f"接口覆盖 {result.claimed}/{result.endpoints}；"
             f"有接口的页面 {result.pages_with_endpoints}/{result.pages}"]
    if result.dangling:
        lines.append("")
        lines.append("悬空证据（规格引用了清单里不存在的接口）：")
        lines += [f"- {item}" for item in result.dangling]
    if result.ownership_issues:
        lines += ["", "接口过程归属需核实："]
        lines += [f"- {item}" for item in result.ownership_issues]
    if result.uncovered:
        lines.append("")
        lines.append("未覆盖接口（请确认是范围外、重复，还是漏拆）：")
        suggested = dict(result.suggestions)
        for item in result.uncovered:
            hint = f"；可能对应 {suggested[item['id']]}" if item["id"] in suggested else ""
            lines.append(f"- {item['id']} {item.get('method', '')} {item['path']} "
                         f"{item.get('summary', '')}{hint}")
    if result.empty_pages:
        lines.append("")
        lines.append("无接口的页面（纯前端页或漏提取，需逐个判断）：")
        lines += [f"- {page['id']} {page.get('name', '')} {page.get('evidence', '')}"
                  for page in result.empty_pages]
    if result.unclaimed_pages:
        lines += ["", "有接口但均未被过程认领的页面："]
        lines += [f"- {page['id']} {page.get('name', '')}" for page in result.unclaimed_pages]
    if result.pages and result.page_ratio < 0.9:
        lines.append("")
        lines.append(f"！素材可能不完整：有接口的页面只占 {result.page_ratio:.0%}，"
                     "先确认剩余页面的范围，不要默认素材已齐。")
    return "\n".join(lines)
