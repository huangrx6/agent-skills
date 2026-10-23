#!/usr/bin/env python3
"""子过程句式、命名检查与英文残留。

三条边界：

1. **句式不是计量规则。** 这里只做两件事：在作者没写 `description` 时给一个默认句式；
   把旧模板句（「接收…请求并校验输入数据」这类）改成项目送审偏好的简洁写法。
   句式检查是提示，不是结构错误。
2. **不改事实。** 改写只动措辞；对象、属性、数据组、移动类型一律不碰。
   英文替换按整词匹配，`addressID` 这类标识不会被拆成 `address编码`。
3. **不为了唯一而改写。** 两个过程描述相同只提示复核，不追加前缀、数字或虚构属性去凑「全表唯一」。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import operation_types as ops  # noqa: E402  # pyright: ignore[reportMissingImports]

DATA = Path(__file__).with_name("glossary.json")

# 旧模板句：这些是实测被要求重写的写法，不影响移动本身的成立。
LEGACY = (
    (re.compile(r"^接收(.+?)请求(?:并校验输入数据)?$"), "E"),
    (re.compile(r"^从数据存储读取(.+)$"), "R"),
    (re.compile(r"^读取数据库中(.+)$"), "R"),
    (re.compile(r"^将(.+)写入数据存储$"), "W"),
    (re.compile(r"^保存变更后的(.+)$"), "W"),
    (re.compile(r"^向用户返回(.+?)(?:结果|数据)$"), "X"),
)
LEGACY_HINTS = (
    "并校验输入数据", "从数据存储读取", "写入数据存储", "向用户返回",
)

# 同一词连续出现通常来自拼接（「查询查询」「数据数据」）。
DOUBLED = re.compile(r"(数据|查询|信息|请求|结果|记录|统计|配置|采集|导入|导出|新增|修改|删除)\1")
WORD = re.compile(r"[A-Za-z][A-Za-z0-9]*")

def load_glossary(path: str | Path | bool | None = None) -> dict:
    try:
        data = json.loads(DATA.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"无法读取内置术语表 {DATA}：{exc}") from None
    if path and path is not True:
        try:
            extra = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SystemExit(f"无法读取术语文件 {path}：{exc}") from None
        if not isinstance(extra, dict) or not isinstance(extra.get("map"), dict):
            raise SystemExit(f"{path} 不是术语文件：顶层需要 map 对象")
        for key in ("keep", "system_attributes"):
            if key in extra:
                if not isinstance(extra[key], list):
                    raise SystemExit(f"{path} 的 {key} 必须是数组")
                data[key] = sorted(set(data[key]) | {str(v) for v in extra[key]})
        data["map"].update({str(k): str(v) for k, v in extra["map"].items()})
    data["keep_set"] = {item.casefold() for item in data["keep"]}
    return data


def _w_verb(op: str | None) -> str:
    if op == "delete":
        return "删除"
    if op in ("update", "enable", "publish", "up", "pass", "import"):
        return "更新"
    return "保存"


def describe(move: str, obj: str, op: str | None = None) -> str:
    """按移动类型给默认描述。只用于作者没写描述时，不覆盖已有文字。"""
    action = ops.OPS[op].action if op in ops.OPS else ""
    if move == "E":
        return clean(f"输入{obj}{action}请求")
    if move == "R":
        return clean(f"读取{obj}信息")
    if move == "W":
        return clean(f"{_w_verb(op)}{obj}信息")
    if move == "X":
        return clean(f"返回{obj}{action}结果")
    return ""


def clean(text: str) -> str:
    text = DOUBLED.sub(r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def rewrite_description(text: str, move: str, name: str = "") -> str:
    """只替换已识别的句式外壳；不根据过程名猜删除，不裁剪业务对象。"""
    value = (text or "").strip()
    if not value:
        return value
    for pattern, expected in LEGACY:
        if expected != move:
            continue
        match = pattern.match(value)
        if not match:
            continue
        obj = match.group(1)
        if move == "E":
            return f"输入{obj}请求"
        if move == "R":
            return f"读取{obj}"
        if move == "W":
            if value.startswith("保存变更后的"):
                return f"更新{obj}"
            return f"保存{obj}"
        if move == "X":
            return f"返回{obj}结果" if value.endswith("结果") else f"返回{obj}数据"
    return text


def legacy_hits(text: str) -> list[str]:
    return [hint for hint in LEGACY_HINTS if hint in (text or "")]


def _boundary(text: str, start: int, end: int) -> bool:
    before = text[start - 1] if start else ""
    after = text[end] if end < len(text) else ""
    return not (before.isascii() and before.isalnum()) and not (after.isascii() and after.isalnum())


def english_tokens(text: str, glossary: dict) -> list[str]:
    keep = glossary["keep_set"]
    found = []
    for match in WORD.finditer(text or ""):
        token = match.group(0)
        if len(token) < 2 or token.casefold() in keep:
            continue
        if _boundary(text, match.start(), match.end()):
            found.append(token)
    return found


def replace_english(text: str, glossary: dict) -> tuple[str, list[tuple[str, str]]]:
    """按整词替换术语；返回新文本与逐项改动。"""
    mapping = sorted(glossary["map"].items(), key=lambda item: -len(item[0]))
    keep = glossary["keep_set"]
    changes: list[tuple[str, str]] = []
    value = text or ""
    for source, target in mapping:
        if source.casefold() in keep:
            continue
        pattern = re.compile(rf"{re.escape(source)}", re.IGNORECASE)
        out, last = [], 0
        for match in pattern.finditer(value):
            if not _boundary(value, match.start(), match.end()):
                continue
            out.append(value[last:match.start()])
            out.append(target)
            last = match.end()
            changes.append((match.group(0), target))
        if out:
            out.append(value[last:])
            value = "".join(out)
    return value, changes


def naming_hints(rows, glossary: dict) -> list[str]:
    hints: list[str] = []
    seen_desc: dict[str, str] = {}
    for row in rows:
        where = f"{row.func}/{row.move}" + (f" 第 {row.excel_row} 行" if row.excel_row else "")
        if row.is_process_head:
            if row.event and row.func and row.event.strip() == row.func.strip():
                hints.append(f"触发事件与功能过程同名，未说明是谁触发了什么 {where}")
            if row.event.startswith("发起") and row.event[2:].strip() == row.func.strip():
                hints.append(f"触发事件只是「发起」+过程名，未说明真实触发主体或动作 {where}")
        for label, text in (("触发事件", row.event), ("子过程描述", row.desc),
                            ("数据组", row.group), ("数据属性", row.attrs)):
            doubled = DOUBLED.search(text or "")
            if doubled:
                hints.append(f"{label}有连续重复词「{doubled.group(0)}」 {where}")
            for token in english_tokens(text or "", glossary):
                target = glossary["map"].get(token) or glossary["map"].get(token.casefold())
                suffix = f"，可写作「{target}」" if target else "，请确认是否为字段名"
                hints.append(f"{label}含英文「{token}」{suffix} {where}")
        for hint in legacy_hits(row.desc):
            hints.append(f"子过程描述用了旧模板句「{hint}」 {where}")
        key = (row.desc or "").strip()
        if key and key in seen_desc and seen_desc[key] != row.func:
            hints.append(f"子过程描述与「{seen_desc[key]}」完全相同，请确认不是复制粘贴 {where}")
        elif key:
            seen_desc[key] = row.func
        if row.is_process_head and row.l3:
            for suffix in ops.MODULE_SUFFIXES:
                if row.l3.endswith(suffix) and len(row.l3) > len(suffix):
                    hints.append(f"三级模块名带操作后缀「{suffix}」，建议只留实体名 第 {row.excel_row} 行：{row.l3}")
                    break
    return list(dict.fromkeys(hints))
