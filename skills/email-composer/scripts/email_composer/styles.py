"""样式令牌：加载四套预设、合并覆盖、给出 C2 用的一句话描述。"""

from __future__ import annotations

import copy
import json
import os
from typing import Any

from . import STYLES
from .spec import choose_preset

__all__ = ["StyleError", "PRESETS", "load_preset", "resolve", "describe"]

PRESETS = ("business", "report", "plain", "alert")

REQUIRED = (
    "width",
    "font.family",
    "font.size",
    "font.line_height",
    "color.accent",
    "color.text",
    "color.muted",
    "color.background",
    "color.page",
    "color.surface",
    "color.border",
    "spacing.page",
    "spacing.content",
    "spacing.block",
    "heading.bar",
    "heading.size",
    "heading.section_size",
    "summary.card",
    "callout.card",
    "table.zebra",
    "table.header_background",
    "frame.border",
    "band.enabled",
    "band.color",
    "band.text",
)


class StyleError(ValueError):
    """样式预设不存在或令牌不完整。"""


def load_preset(name: str) -> dict:
    if name not in PRESETS:
        raise StyleError(f"未知预设 {name!r}；可用：{', '.join(PRESETS)}")
    path = os.path.join(STYLES, f"{name}.json")
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    return data


def _merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if value is None:
            continue
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _get(tokens: dict, dotted: str) -> Any:
    node: Any = tokens
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _check(tokens: dict) -> None:
    missing = [key for key in REQUIRED if _get(tokens, key) is None]
    if missing:
        raise StyleError(f"样式令牌缺字段：{', '.join(missing)}")
    try:
        tokens["width"] = int(tokens["width"])
    except (TypeError, ValueError) as exc:
        raise StyleError("样式 width 需要整数像素") from exc


def _load_style_file(path: str) -> dict:
    if not os.path.isfile(path):
        raise StyleError(f"找不到样式文件：{path}")
    with open(path, encoding="utf-8") as handle:
        try:
            data = json.load(handle)
        except ValueError as exc:
            raise StyleError(f"{path} 不是合法 JSON：{exc}") from exc
    if not isinstance(data, dict):
        raise StyleError(f"{path} 顶层需要对象")
    return data


def resolve(
    spec: dict,
    preset: str | None = None,
    style_file: str | None = None,
) -> tuple[dict, str, str]:
    """返回 (样式令牌, 预设名, 选择依据)。

    优先级：命令行 --preset > 模板 style.json 的 preset > Spec 的 style.preset
    > 按类型与内容自动选择。覆盖统一深合并到预设之上。
    """
    name, reason = choose_preset(spec)
    style = spec.get("style")
    data = _load_style_file(style_file) if style_file else {}
    if data.get("preset"):
        name, reason = str(data["preset"]), "模板样式"
    if preset:
        name, reason = preset, "命令行指定"
    tokens = load_preset(name)
    overrides = style.get("overrides") if isinstance(style, dict) else None
    if overrides is not None:
        if not isinstance(overrides, dict):
            raise StyleError("Spec 的 style.overrides 需要对象")
        tokens = _merge(tokens, overrides)
    if data:
        overrides = data.get("overrides", {k: v for k, v in data.items() if k != "preset"})
        if not isinstance(overrides, dict):
            raise StyleError("style.json 的 overrides 需要对象")
        tokens = _merge(tokens, overrides)

    tokens["name"] = name
    _check(tokens)
    return tokens, name, reason


def describe(tokens: dict) -> str:
    """C2 确认用的一句话样式说明。"""
    parts = [
        f"{tokens['name']} 预设",
        f"强调色 {tokens['color']['accent']}",
        f"宽 {tokens['width']}px",
    ]
    if tokens["band"]["enabled"]:
        parts.append("顶部警示色带")
    if tokens["heading"]["bar"]:
        parts.append("标题左侧色条")
    if tokens["table"]["zebra"]:
        parts.append("表格斑马纹")
    return " · ".join(parts)
