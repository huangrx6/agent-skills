"""跨平台输出目录与原子文件写入。

周报、证据 JSON 默认都落在用户下载目录下的 `pingcode-weekly` 子目录：
macOS/Linux 为 `~/Downloads/pingcode-weekly`，Windows 为
`%USERPROFILE%\\Downloads\\pingcode-weekly`。可用环境变量
`PINGCODE_WEEKLY_OUTPUT_DIR` 或 `[workspace] output_dir` 改到同一目录。
"""

from __future__ import annotations

import contextlib
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

OUTPUT_ENV = "PINGCODE_WEEKLY_OUTPUT_DIR"
OUTPUT_SUBDIR = "pingcode-weekly"


def default_output_dir() -> Path:
    override = os.environ.get(OUTPUT_ENV)
    if override:
        return Path(override).expanduser()
    try:
        home = Path.home()
    except RuntimeError:
        home = Path.cwd()
    return home / "Downloads" / OUTPUT_SUBDIR


def resolve_output_dir(value: str | Path | None = None) -> Path:
    if value not in (None, ""):
        return Path(value).expanduser()
    return default_output_dir()


def safe_name(value: object, fallback: str = "pingcode") -> str:
    text = re.sub(r"[^\w.-]+", "-", str(value or "").strip(), flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text).strip("._-")
    return text[:60].rstrip("._-") or fallback


def window_slug(since: datetime, until: datetime, week: str | None = None,
                month: str | None = None) -> str:
    if week:
        return safe_name(str(week).upper(), fallback="window")
    if month:
        return safe_name(str(month), fallback="month")
    return f"{since.date().isoformat()}_{until.date().isoformat()}"


def build_filename(label: object, window: object, suffix: str) -> str:
    return f"{safe_name(label)}-{safe_name(window, fallback='window')}-{suffix}"


def render_filename(stem: str) -> str:
    base = stem[:-len("-evidence")] if stem.endswith("-evidence") else stem
    return f"{safe_name(base)}-rendered-weekly.md"


def atomic_write_text(path: str | Path, text: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise
    return target
