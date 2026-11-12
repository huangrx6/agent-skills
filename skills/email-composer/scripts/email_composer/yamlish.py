"""本 skill 规格使用的 YAML 子集解析器与写出器。

为什么不直接依赖 PyYAML：skill 要在任意 agent 环境里直接运行，装依赖不是必然的。
这里只覆盖内容规格实际会出现的写法，遇到不支持的构造就报错，不静默猜：

- 缩进映射与列表（2 空格缩进，禁止 tab 缩进）
- 行内标量、双引号/单引号、`|` 与 `>` 块标量
- 行内集合 `[a, b]`、`{kind: paragraph, text: "..."}`
- 注释、空行
- `true` / `false` / `null` / 整数 / 小数；不转换带前导零的数字

明确不支持（会报错或按字符串处理）：锚点、别名、合并键、标签、多文档、复杂折叠缩进。
JSON 也是合法输入：`.json` 文件或首字符为 `{` 时优先按 JSON 解析。
"""

from __future__ import annotations

import json
import re
from typing import Any

__all__ = ["YamlError", "loads", "dumps", "load_file"]


class YamlError(ValueError):
    """YAML 子集解析失败。消息里带行号，便于直接改规格。"""


_INT_RE = re.compile(r"^-?(?:0|[1-9]\d*)$")
_FLOAT_RE = re.compile(r"^-?(?:0|[1-9]\d*)\.\d+$")
_SPECIAL_START = set("-?:,[]{}#&*!|>'\"%@`")


def _indent_of(line: str, lineno: int) -> int:
    lead = line[: len(line) - len(line.lstrip(" "))]
    if "\t" in line[: len(lead) + 1]:
        raise YamlError(f"第 {lineno} 行：缩进不能用 tab，请改成空格")
    return len(lead)


def _skip_blank(lines: list[str], i: int) -> int:
    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("#"):
            i += 1
        else:
            break
    return i


def _strip_comment(text: str) -> str:
    """去掉行尾注释。引号内和行内集合里的 `#` 不算注释。"""
    quote = None
    depth = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            if quote == '"' and ch == "\\":
                i += 2
                continue
            if ch == quote:
                if quote == "'" and i + 1 < len(text) and text[i + 1] == "'":
                    i += 2
                    continue
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == "#" and depth == 0 and (i == 0 or text[i - 1] in " \t"):
            return text[:i].rstrip()
        i += 1
    return text.rstrip()


def _split_key(text: str, lineno: int) -> tuple[str, str | None]:
    """把 `key: value` 拆成两段。冒号后必须是空白或行尾，避免切断 20:00 / https://。"""
    quote = None
    depth = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            if quote == '"' and ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == ":" and depth == 0:
            if i + 1 == len(text) or text[i + 1] in " \t":
                key = text[:i].strip()
                if not key:
                    raise YamlError(f"第 {lineno} 行：冒号前缺少键名")
                return _unquote_key(key, lineno), text[i + 1 :].strip()
        i += 1
    return text.strip(), None


def _unquote_key(key: str, lineno: int) -> str:
    if key.startswith('"') and key.endswith('"'):
        try:
            return json.loads(key)
        except ValueError as exc:
            raise YamlError(f"第 {lineno} 行：键名转义不合法：{exc}") from exc
    if key.startswith("'") and key.endswith("'"):
        return key[1:-1].replace("''", "'")
    return key


def _split_top(text: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    quote = None
    depth = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            buf.append(ch)
            if quote == '"' and ch == "\\" and i + 1 < len(text):
                buf.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                if quote == "'" and i + 1 < len(text) and text[i + 1] == "'":
                    buf.append(text[i + 1])
                    i += 2
                    continue
                quote = None
        else:
            if ch in "\"'":
                quote = ch
                buf.append(ch)
            elif ch in "[{":
                depth += 1
                buf.append(ch)
            elif ch in "]}":
                depth -= 1
                buf.append(ch)
            elif ch == "," and depth == 0:
                parts.append("".join(buf).strip())
                buf = []
            else:
                buf.append(ch)
        i += 1
    if quote:
        raise YamlError("行内集合里的引号没有闭合")
    parts.append("".join(buf).strip())
    return [part for part in parts if part != ""]


def _parse_quoted(text: str, lineno: int) -> str:
    if text.startswith('"'):
        try:
            return json.loads(text)
        except ValueError as exc:
            raise YamlError(f"第 {lineno} 行：双引号字符串不合法（{exc}）") from exc
    if not text.endswith("'"):
        raise YamlError(f"第 {lineno} 行：单引号字符串没有闭合")
    return text[1:-1].replace("''", "'")


def _parse_scalar(text: str, lineno: int) -> Any:
    text = _strip_comment(text).strip()
    if text == "":
        return None
    if text[0] in "[{":
        return _parse_flow(text, lineno)
    if text[0] in "\"'":
        return _parse_quoted(text, lineno)
    if text[0] in "&*":
        raise YamlError(f"第 {lineno} 行：不支持 YAML 锚点或别名")
    if text.startswith("<<"):
        raise YamlError(f"第 {lineno} 行：不支持 YAML 合并键")
    low = text.lower()
    if low in ("null", "~"):
        return None
    if low in ("true", "false"):
        return low == "true"
    if _INT_RE.match(text):
        return int(text)
    if _FLOAT_RE.match(text):
        return float(text)
    return text


def _parse_flow(text: str, lineno: int) -> Any:
    opener, closer = text[0], text[-1]
    if (opener, closer) != ("[", "]") and (opener, closer) != ("{", "}"):
        raise YamlError(f"第 {lineno} 行：行内集合没有闭合")
    inner = text[1:-1].strip()
    if opener == "[":
        return [_parse_scalar(part, lineno) for part in _split_top(inner)]
    result: dict[str, Any] = {}
    for part in _split_top(inner):
        key, rest = _split_key(part, lineno)
        if rest is None:
            raise YamlError(f"第 {lineno} 行：行内映射缺少冒号：{part!r}")
        result[key] = _parse_scalar(rest, lineno)
    return result


def _fold(lines: list[str]) -> str:
    """折叠折行。中文之间不插空格：`一个句子\n后半句` 应读作一个句子。"""
    text = lines[0]
    for line in lines[1:]:
        if not text or not line:
            text += line
        elif ord(text[-1]) > 127 or ord(line[0]) > 127:
            text += line
        else:
            text += " " + line
    return text


def _parse_block_scalar(
    lines: list[str], start: int, parent_indent: int, marker: str, lineno: int
) -> tuple[str, int]:
    style = marker[0]
    chomp = marker[1] if len(marker) > 1 else ""
    if chomp not in ("", "-", "+"):
        raise YamlError(f"第 {lineno} 行：块标量标记只支持 |、|-、>、>-")
    collected: list[str] = []
    block_indent = None
    i = start
    while i < len(lines):
        raw = lines[i]
        if raw.strip() == "":
            collected.append("")
            i += 1
            continue
        indent = _indent_of(raw, i + 1)
        if indent <= parent_indent:
            break
        if block_indent is None:
            block_indent = indent
        if indent < block_indent:
            break
        collected.append(raw[block_indent:])
        i += 1
    while collected and collected[-1] == "":
        collected.pop()
    if style == "|":
        text = "\n".join(collected)
    else:
        chunks: list[str] = []
        buf: list[str] = []
        for line in collected:
            if line == "":
                if buf:
                    chunks.append(_fold(buf))
                    buf = []
                chunks.append("")
            else:
                buf.append(line)
        if buf:
            chunks.append(_fold(buf))
        text = "\n".join(chunks)
        while "\n\n\n" in text:
            text = text.replace("\n\n\n", "\n\n")
    if chomp != "+":
        text = text.rstrip("\n")
    return text, i


def _parse_value(
    rest: str, lines: list[str], i: int, parent_indent: int, lineno: int
) -> tuple[Any, int]:
    rest = rest.strip()
    if rest == "":
        j = _skip_blank(lines, i)
        if j < len(lines) and _indent_of(lines[j], j + 1) > parent_indent:
            return _parse_block(lines, j, _indent_of(lines[j], j + 1))
        return None, i
    if rest[0] in "|>":
        return _parse_block_scalar(lines, i, parent_indent, rest, lineno)
    return _parse_scalar(rest, lineno), i


def _parse_entries(
    lines: list[str], i: int, indent: int, first: tuple[str, str] | None = None
) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    pending = first
    while True:
        if pending is None:
            i = _skip_blank(lines, i)
            if i >= len(lines):
                break
            raw = lines[i]
            current_indent = _indent_of(raw, i + 1)
            if current_indent < indent:
                break
            if current_indent > indent:
                raise YamlError(f"第 {i + 1} 行：缩进与同级键不一致")
            content = raw.strip()
            if content == "-" or content.startswith("- "):
                break
            key, rest = _split_key(content, i + 1)
            if rest is None:
                raise YamlError(f"第 {i + 1} 行：缺少冒号：{content!r}")
            lineno = i + 1
            i += 1
        else:
            key, rest = pending
            pending = None
            lineno = i + 1
        value, i = _parse_value(rest, lines, i, indent, lineno)
        result[key] = value
    return result, i


def _parse_block(lines: list[str], i: int, indent: int) -> tuple[Any, int]:
    i = _skip_blank(lines, i)
    if i >= len(lines):
        return None, i
    content = lines[i].strip()
    if content == "-" or content.startswith("- "):
        return _parse_list(lines, i, indent)
    return _parse_entries(lines, i, indent)


def _parse_list(lines: list[str], i: int, indent: int) -> tuple[list[Any], int]:
    items: list[Any] = []
    while True:
        i = _skip_blank(lines, i)
        if i >= len(lines):
            break
        raw = lines[i]
        current_indent = _indent_of(raw, i + 1)
        if current_indent < indent:
            break
        if current_indent > indent:
            raise YamlError(f"第 {i + 1} 行：缩进与同级列表项不一致")
        content = raw.strip()
        if content != "-" and not content.startswith("- "):
            break
        rest = content[1:].strip()
        if rest == "":
            j = _skip_blank(lines, i + 1)
            if j < len(lines) and _indent_of(lines[j], j + 1) > indent:
                value, i = _parse_block(lines, j, _indent_of(lines[j], j + 1))
            else:
                value, i = None, i + 1
        elif rest[0] in "|>":
            value, i = _parse_block_scalar(lines, i + 1, indent, rest, i + 1)
        elif rest[0] in "[{":
            value, i = _parse_scalar(rest, i + 1), i + 1
        else:
            key, rest_value = _split_key(rest, i + 1)
            if rest_value is None:
                value, i = _parse_scalar(rest, i + 1), i + 1
            else:
                # `- kind: paragraph`：行内第一对键值，后续键与第一个键对齐。
                dash_pos = raw.index("-")
                key_pos = raw.index(rest, dash_pos + 1)
                first_value, next_i = _parse_value(
                    rest_value, lines, i + 1, key_pos, i + 1
                )
                more, next_i = _parse_entries(lines, next_i, key_pos)
                merged = {key: first_value}
                merged.update(more)
                value, i = merged, next_i
        items.append(value)
    return items, i


def loads(text: str) -> Any:
    """解析本 skill 规格使用的 YAML 子集。"""
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i = _skip_blank(lines, 0)
    if i >= len(lines):
        return None
    if _indent_of(lines[i], i + 1) != 0:
        raise YamlError(f"第 {i + 1} 行：顶层内容不能缩进")
    value, i = _parse_block(lines, i, 0)
    i = _skip_blank(lines, i)
    if i < len(lines):
        raise YamlError(f"第 {i + 1} 行：无法解析的内容：{lines[i].strip()!r}")
    return value


def load_file(path: str) -> Any:
    with open(path, encoding="utf-8-sig") as handle:
        text = handle.read()
    if path.endswith(".json") or text.lstrip().startswith("{"):
        try:
            return json.loads(text)
        except ValueError:
            if path.endswith(".json"):
                raise
    return loads(text)


# ── 写出器：模板需要人能直接编辑的 YAML ──────────────────────────────────
_PLAIN_FORBIDDEN = re.compile(r":\s|\s#|\t|\n|^\s|\s$")
_NUMBER_LIKE = re.compile(r"^-?(?:0|[1-9]\d*)(?:\.\d+)?$")
_RESERVED = {"null", "~", "true", "false", "yes", "no", "on", "off"}


def _needs_quote(text: str) -> bool:
    if text == "":
        return True
    if text[0] in _SPECIAL_START:
        return True
    if text.endswith(":"):
        return True
    if _PLAIN_FORBIDDEN.search(text):
        return True
    if _NUMBER_LIKE.match(text):
        return True
    if text.lower() in _RESERVED:
        return True
    return False


def _format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return repr(value)
    text = str(value)
    if "\n" in text:
        raise ValueError("多行文本由调用方用块标量写出")
    if _needs_quote(text):
        return json.dumps(text, ensure_ascii=False)
    return text


def _inline(value: Any) -> str:
    if isinstance(value, dict):
        return "{}"
    if isinstance(value, list):
        return "[]"
    return _format_scalar(value)


def _dump_map(value: dict, indent: int) -> list[str]:
    lines: list[str] = []
    pad = " " * indent
    for key, item in value.items():
        name = (
            key
            if isinstance(key, str) and not _needs_quote(key)
            else json.dumps(str(key), ensure_ascii=False)
        )
        if isinstance(item, str) and "\n" in item:
            lines.append(f"{pad}{name}: |-")
            for line in item.split("\n"):
                lines.append((" " * (indent + 2) + line) if line else "")
        elif isinstance(item, dict) and item:
            lines.append(f"{pad}{name}:")
            lines.extend(_dump_map(item, indent + 2))
        elif isinstance(item, list) and item:
            lines.append(f"{pad}{name}:")
            lines.extend(_dump_list(item, indent + 2))
        else:
            lines.append(f"{pad}{name}: {_inline(item)}")
    return lines


def _dump_list(value: list, indent: int) -> list[str]:
    lines: list[str] = []
    pad = " " * indent
    for item in value:
        if isinstance(item, str) and "\n" in item:
            lines.append(f"{pad}- |-")
            for line in item.split("\n"):
                lines.append((" " * (indent + 2) + line) if line else "")
        elif isinstance(item, dict) and item:
            sub = _dump_map(item, indent + 2)
            lines.append(f"{pad}- {sub[0][indent + 2:]}")
            lines.extend(sub[1:])
        elif isinstance(item, list) and item:
            lines.append(f"{pad}-")
            lines.extend(_dump_list(item, indent + 2))
        else:
            lines.append(f"{pad}- {_inline(item)}")
    return lines


def dumps(value: Any) -> str:
    """把规格写成块状 YAML。键顺序保持插入顺序；注释不保留。"""
    if isinstance(value, dict):
        lines = _dump_map(value, 0)
    elif isinstance(value, list):
        lines = _dump_list(value, 0)
    else:
        lines = [_format_scalar(value)]
    return "\n".join(lines) + "\n"
