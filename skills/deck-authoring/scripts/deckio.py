"""读写文件与数值解析 —— **IO 一律走这里**。

为什么单独一层（这是本会话挣来的一条）：仓库的检查项要求"调用文件 IO 必须有 try/except"，
而逐个调用点去包，既贵又容易漏（实测漏过 ✗）。收在一个模块里，新代码自然就带上了。
"""
from __future__ import annotations

import json
import os


def read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        raise SystemExit(f"✗ 读不到 {path}：{exc}") from exc


def read_json(path: str) -> dict:
    try:
        payload = json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"✗ {path} 不是合法 JSON：{exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"✗ {path} 的顶层应是对象，实际是 {type(payload).__name__}")
    return payload


def write_text(path: str, text: str) -> None:
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    except OSError as exc:
        raise SystemExit(f"✗ 写不了 {path}：{exc}") from exc


def ensure_dir(path: str) -> None:
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as exc:
        raise SystemExit(f"✗ 建不了目录 {path}：{exc}") from exc


def as_number(value, what: str) -> float:
    """把可能是字符串/None 的值转成数字；转不了就如实报错，不甩 traceback。"""
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"✗ {what} 不是数字：{value!r}") from exc
