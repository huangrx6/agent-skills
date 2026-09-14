#!/usr/bin/env python3
"""配置与本地状态：凭据、令牌缓存、当前上下文。

设计取舍
--------
**全局一套，不放进仓库。** 配置目录默认 `~/.config/agent-skills/pingcode/`（`PINGCODE_CONFIG_DIR`
可换），三个文件职责分开 —— 它们的**生命周期不同**，混在一起就会互相覆盖：

| 文件 | 内容 | 谁写 | 生命周期 |
| --- | --- | --- | --- |
| `credentials.json` | host / 授权模式 / client_id / client_secret / redirect_uri | **人**手填 | 长期 |
| `token.json` | access_token / refresh_token / 到期时间 | 程序 | 30 天（refresh 90 天） |
| `context.json` | 当前项目 / 当前迭代 / 当前用户 | 程序 | 随时改 |
| `cache.json` | 字典类数据（项目 / 迭代 / 类型 / 状态 / 优先级 / 成员） | 程序 | 手动刷新 |

写文件一律**原子写 + 0600**：令牌是凭证，不能留下半截文件，也不能让同机器其他用户读到。

优先级：命令行参数 > 环境变量 > `credentials.json`。
环境变量（CI / Agent 用）：`PINGCODE_HOST` `PINGCODE_AUTH_MODE` `PINGCODE_CLIENT_ID`
`PINGCODE_CLIENT_SECRET` `PINGCODE_ACCESS_TOKEN` `PINGCODE_CONFIG_DIR`。

**绝不回显 client_secret 与 token。** `describe_credentials()` 只给「从哪来 + 前 4 位」。
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time
from typing import Any, NamedTuple

FILE_MODE = 0o600
DIR_MODE = 0o700

CREDENTIALS = "credentials.json"
TOKEN = "token.json"
CONTEXT = "context.json"
CACHE = "cache.json"

AUTH_MODES = ("user", "enterprise")
DEFAULT_HOST = "open.pingcode.com"
DEFAULT_REDIRECT = "http://localhost:8765/callback"
DEFAULT_PORT = 8765

ENV_HOST = "PINGCODE_HOST"
ENV_MODE = "PINGCODE_AUTH_MODE"
ENV_ID = "PINGCODE_CLIENT_ID"
ENV_SECRET = "PINGCODE_CLIENT_SECRET"
ENV_TOKEN = "PINGCODE_ACCESS_TOKEN"
ENV_DIR = "PINGCODE_CONFIG_DIR"

# 官方文档：access_token 30 天，refresh_token 90 天。
FALLBACK_ACCESS_TTL = 30 * 24 * 3600
FALLBACK_REFRESH_TTL = 90 * 24 * 3600

# 官方示例里的 expires_in 是 1577808000 —— 那是**绝对时间戳**（2020-01-01），
# 不是秒数。正常 OAuth 的 expires_in 是秒，所以这里两种都可能，靠量级判断。
# 这条属于「未实测」：等真实令牌到手后第一次 `auth status` 就能确认。
ABSOLUTE_TS_FLOOR = 10 ** 9


class ConfigError(Exception):
    """配置缺失或不可用。消息里要带上「怎么修」。"""


class TokenError(Exception):
    """令牌不可用（过期 / 撤销 / 格式不对）。"""


class Credentials(NamedTuple):
    host: str
    auth_mode: str
    client_id: str
    client_secret: str
    redirect_uri: str
    source: str          # 凭据从哪来，供 `config show` 交代
    has_secret: bool


def _as_int(value: object, default: int = 0) -> int:
    """宽松取整：拿不到就用默认值。

    配置和令牌是**外部输入**（人手写的 JSON、服务端返回的字段），不能因为一个字段
    类型不对就整个命令崩掉。
    """
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def shared_config_dir() -> str:
    """**统一配置根**：所有 skill 的配置都在这儿，跨平台同一个路径。

    `AGENT_SKILLS_CONFIG_DIR` 可以把它整体搬走（换机器、放加密盘都行）。
    """
    override = os.environ.get("AGENT_SKILLS_CONFIG_DIR", "").strip()
    if override:
        return os.path.abspath(os.path.expanduser(override))
    return os.path.expanduser(os.path.join("~", ".config", "agent-skills"))


def legacy_config_dir() -> str:
    """旧位置 `~/.config/agent-skills/pingcode`（只兼容读取，不再首选）。"""
    return os.path.join(os.path.expanduser("~"), ".config", "pingcode")


def config_dir() -> str:
    """配置目录（`PINGCODE_CONFIG_DIR` 优先，其次统一配置根）。

    旧目录里有配置、新目录里没有时，**继续读旧的** —— 老机器不用搬也能跑；
    一旦新目录存在就用新的（搬迁是一次性的，不是必须的）。
    """
    override = os.environ.get(ENV_DIR, "").strip()
    if override:
        return os.path.abspath(os.path.expanduser(override))
    new = os.path.join(shared_config_dir(), "pingcode")
    if not os.path.isdir(new) and os.path.isdir(legacy_config_dir()):
        return legacy_config_dir()
    return new


def path_of(name: str) -> str:
    return os.path.join(config_dir(), name)


def read_json(path: str) -> dict[str, Any]:
    """读一个 JSON 文件；不存在 → 空表（不是错误）。"""
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        raise ConfigError(f"读不到 {path}：{exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} 不是合法 JSON：{exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} 顶层应当是对象（JSON object）")
    return data


def write_private(path: str, data: dict[str, Any]) -> None:
    """原子写 + 0600。先写同目录临时文件再 os.replace，避免半截文件。"""
    directory = os.path.dirname(path)
    try:
        os.makedirs(directory, mode=DIR_MODE, exist_ok=True)
    except OSError as exc:
        raise ConfigError(f"建不了配置目录 {directory}：{exc}") from exc

    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=directory)
        os.fchmod(fd, FILE_MODE)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except OSError as exc:
        if tmp is not None:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
        raise ConfigError(f"写不了 {path}：{exc}") from exc


def remove_file(path: str) -> bool:
    try:
        os.unlink(path)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise ConfigError(f"删不掉 {path}：{exc}") from exc
    return True


def api_base(host: str) -> str:
    """REST 根地址。官方：公有云 `open.pingcode.com`，私有部署 `{域名}/open`。"""
    host = (host or DEFAULT_HOST).strip().rstrip("/")
    if "://" in host:
        return host
    return "https://" + host


def oauth2_base(host: str) -> str:
    """OAuth2 授权页根地址。私有部署的 REST 根带 `/open`，但授权页**不带**。"""
    host = (host or DEFAULT_HOST).strip().rstrip("/")
    if host.endswith("/open"):
        host = host[: -len("/open")]
    if "://" in host:
        return host + "/oauth2"
    return "https://" + host + "/oauth2"


def load_credentials() -> Credentials:
    """按「环境变量 > 配置文件」的顺序取凭据。取不到就报错，并说清怎么补。"""
    stored = read_json(path_of(CREDENTIALS))

    def pick(env_name: str, key: str, default: str = "") -> tuple[str, bool]:
        """环境变量优先；配置文件里为空就用默认值（不能把空串当已配置）。"""
        env_val = os.environ.get(env_name, "").strip()
        if env_val:
            return env_val, True
        value = str(stored.get(key, "") or "").strip()
        return (value or default), False

    host, host_env = pick(ENV_HOST, "host", DEFAULT_HOST)
    mode, _ = pick(ENV_MODE, "auth_mode", "user")
    client_id, id_env = pick(ENV_ID, "client_id")
    client_secret, sec_env = pick(ENV_SECRET, "client_secret")
    redirect_uri, _ = pick("PINGCODE_REDIRECT_URI", "redirect_uri", DEFAULT_REDIRECT)

    # 直接给了令牌就不需要 client 凭据 —— 那条路在 auth.bearer() 里单独走。
    if os.environ.get(ENV_TOKEN, "").strip():
        source = f"环境变量 {ENV_TOKEN}"
    elif host_env or id_env or sec_env:
        source = "环境变量"
    else:
        source = path_of(CREDENTIALS)

    if not host:
        host = DEFAULT_HOST
    if mode not in AUTH_MODES:
        raise ConfigError(
            f"auth_mode 只能是 {' 或 '.join(AUTH_MODES)}（当前 {mode!r}）；"
            f"在 {path_of(CREDENTIALS)} 里改，或设 {ENV_MODE}"
        )
    has_secret = bool(client_secret)
    if not client_id or not client_secret:
        if not os.environ.get(ENV_TOKEN, "").strip():
            raise ConfigError(
                "缺 client_id / client_secret。两种补法：\n"
                f"  1) 写 {path_of(CREDENTIALS)}（0600），格式见 README 的「配置」一节；\n"
                f"  2) 设环境变量 {ENV_ID} 与 {ENV_SECRET}。\n"
                "凭据在 PingCode 企业后台的凭据管理里创建应用后获得。\n"
                f"配置会写到这里：{path_of(CREDENTIALS)}\n"
                "目录不存在就先建它（macOS / Linux / Windows 通用）：\n"
                f'  python3 -c "from pathlib import Path; '
                f'Path(\'{config_dir()}\').mkdir(parents=True, exist_ok=True)"'
            )
    return Credentials(host, mode, client_id, client_secret, redirect_uri, source, has_secret)


def describe_credentials(cr: Credentials) -> dict[str, Any]:
    """给 `config show` 用的安全摘要 —— 不回显 secret。"""
    return {
        "凭据来源": cr.source,
        "host": cr.host,
        "REST 根": api_base(cr.host),
        "OAuth2 根": oauth2_base(cr.host),
        "授权模式": cr.auth_mode,
        "client_id": cr.client_id or "（未配）",
        "client_secret": "已配置" if cr.has_secret else "（未配）",
        "redirect_uri": cr.redirect_uri,
        "配置文件目录": config_dir(),
    }


def expire_at(payload: dict[str, Any], fallback_ttl: int) -> int:
    """由令牌响应算出到期时间戳（秒）。

    官方示例的 `expires_in` 给的是 1577808000（绝对时间戳），而 OAuth 常规语义是
    「还有多少秒」。两种都接：大于 `ABSOLUTE_TS_FLOOR` 当绝对时间戳，否则当秒数。
    """
    raw = payload.get("expires_in")
    value = _as_int(raw)
    if value >= ABSOLUTE_TS_FLOOR:
        return value
    if value > 0:
        return _as_int(time.time()) + value
    return _as_int(time.time()) + fallback_ttl


def save_token(payload: dict[str, Any], mode: str, keep_refresh: str = "") -> dict[str, Any]:
    """落盘令牌。保留上一次的 refresh_token（刷新响应有时不回它）。"""
    access = str(payload.get("access_token", "") or "")
    if not access:
        raise TokenError(f"授权响应里没有 access_token：{sorted(payload)}")
    refresh = str(payload.get("refresh_token", "") or "") or keep_refresh
    ttl_fallback = FALLBACK_REFRESH_TTL if refresh else FALLBACK_ACCESS_TTL
    record = {
        "mode": mode,
        "access_token": access,
        "refresh_token": refresh,
        "token_type": str(payload.get("token_type", "Bearer") or "Bearer"),
        "expires_at": expire_at(payload, ttl_fallback),
        "obtained_at": _as_int(time.time()),
    }
    write_private(path_of(TOKEN), record)
    return record


def load_token() -> dict[str, Any]:
    return read_json(path_of(TOKEN))


def clear_token() -> bool:
    return remove_file(path_of(TOKEN))


def token_state(record: dict[str, Any] | None = None) -> dict[str, Any]:
    """令牌状态摘要：是否过期、还剩多久、能不能 refresh。"""
    record = load_token() if record is None else record
    if not record.get("access_token"):
        return {"present": False, "expired": True, "seconds_left": 0,
                "has_refresh": False, "mode": ""}
    expires_at = _as_int(record.get("expires_at"))
    left = expires_at - _as_int(time.time())
    return {
        "present": True,
        "expired": left <= 0,
        "seconds_left": max(0, left),
        "expires_at": expires_at,
        "has_refresh": bool(record.get("refresh_token")),
        "mode": str(record.get("mode", "")),
    }


def load_context() -> dict[str, Any]:
    return read_json(path_of(CONTEXT))


def save_context(**fields: Any) -> dict[str, Any]:
    """只覆盖给到的键；值给 None 表示删除该键。"""
    ctx = load_context()
    for key, value in fields.items():
        if value is None:
            ctx.pop(key, None)
        else:
            ctx[key] = value
    write_private(path_of(CONTEXT), ctx)
    return ctx


def load_cache() -> dict[str, Any]:
    return read_json(path_of(CACHE))


def save_cache(data: dict[str, Any]) -> None:
    write_private(path_of(CACHE), data)
