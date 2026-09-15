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


def remove(path: str) -> None:
    """删文件，删不掉也不报（清理临时产物用的）。

    “删不掉就算了”是这里的**意图**，不是捎过去 —— 临时文件清不掉不该让整件事失败。
    """
    try:
        os.unlink(path)
    except OSError:
        pass


def list_dirs(path: str) -> list[str]:
    """列出目录下的子目录名（已排序）。

    目录不存在时返回空表 —— 调用方（如“认不出风格，列一下有哪些”）要的是**能写进
    报错里的候选表**，而不是一个 traceback。没得列就列空。
    """
    try:
        return sorted(d for d in os.listdir(path)
                      if os.path.isdir(os.path.join(path, d)))
    except OSError:
        return []


def list_files(path: str, suffix: str = "") -> list[str]:
    """列出目录下的文件名（已排序），可按后缀过滤。

    与 `list_dirs` 同一套理由：目录不存在时返回空表 —— 调用方要的是"能写进报错里的
    候选表"，不是一个 traceback。
    """
    try:
        names = os.listdir(path)
    except OSError:
        return []
    return sorted(f for f in names
                  if os.path.isfile(os.path.join(path, f))
                  and (not suffix or f.lower().endswith(suffix)))


def read_bytes(path: str) -> bytes:
    """读二进制（PDF / PNG 之类）。

    为什么要单独一个：验 PDF 要看文件里的字节标记，而 `read_text` 会在非 UTF-8
    上抛 UnicodeDecodeError —— 那不属于 OSError，会被它漏过去。
    """
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError as exc:
        raise SystemExit(f"✗ 读不到 {path}：{exc}") from exc


def write_bytes(path: str, data: bytes) -> None:
    """写二进制（录制的帧、复制的图）。

    录制一帧写一次，一录就是几百帧 —— 所以这里连目录都不建（目录由调用方建一次），
    也不加多余判断。写不进去就报，不静默丢帧（丢帧 = 视频少几帧，最难发现）。
    """
    try:
        with open(path, "wb") as fh:
            fh.write(data)
    except OSError as exc:
        raise SystemExit(f"✗ 写不了 {path}：{exc}") from exc


def copy(src: str, dst: str) -> None:
    """复制文件（抽帧检查用：把某几帧拣出来另存）。"""
    write_bytes(dst, read_bytes(src))


def as_number(value, what: str) -> float:
    """把可能是字符串/None 的值转成数字；转不了就如实报错，不甩 traceback。"""
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"✗ {what} 不是数字：{value!r}") from exc
