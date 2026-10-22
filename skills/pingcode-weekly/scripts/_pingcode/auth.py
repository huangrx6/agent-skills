"""PingCode 只读周报用的最小认证/令牌支持。

这里只保留授权、刷新和身份查询。
用户授权沿用 PingCode OAuth2 的 authorization_code；企业授权用
client_credentials。令牌缓存格式与 `~/.config/agent-skills/pingcode` 兼容。
"""

from __future__ import annotations

import os
import urllib.parse
from typing import Any

from . import client, config

GRANT_PATH = "/v2/auth/token"
MYSELF_PATH = "/v2/myself"


def _anonymous(host: str) -> client.Client:
    return client.Client(bearer=lambda: "", host=host)


def _token_request(cr: config.Credentials, grant: str, **params: Any) -> dict[str, Any]:
    result = _anonymous(cr.host).request(
        "GET",
        GRANT_PATH,
        params={"grant_type": grant, **params},
        authenticate=False,
    )
    return result.data if isinstance(result.data, dict) else {}


def bearer() -> str:
    """环境变量 > 有效缓存 > refresh_token。"""
    from_env = os.environ.get(config.ENV_BEARER, "").strip()
    if from_env:
        return from_env

    record = config.load_token()
    state = config.token_state(record)
    if state["present"] and not state["expired"]:
        return str(record.get("access_token", ""))
    if record.get("refresh_token"):
        return str(refresh().get("access_token", ""))
    if state["present"]:
        raise config.TokenError(
            "令牌已过期，而且没有 refresh_token。重新授权："
            "python3 scripts/pingcode_weekly.py auth login"
        )
    raise config.TokenError(
        "还没有 PingCode 令牌。先授权：python3 scripts/pingcode_weekly.py auth login"
        f"（或设置 {config.ENV_BEARER}）"
    )


def current_mode() -> str:
    env_mode = os.environ.get(config.ENV_MODE, "").strip()
    if os.environ.get(config.ENV_BEARER, "").strip() and env_mode:
        return env_mode
    record = config.load_token()
    mode = str(record.get("mode", "") or "")
    if mode:
        return mode
    try:
        return config.load_credentials().auth_mode
    except config.ConfigError:
        return ""


def login_enterprise() -> dict[str, Any]:
    cr = config.load_credentials()
    data = _token_request(
        cr,
        "client_credentials",
        client_id=cr.client_id,
        client_secret=cr.client_secret,
    )
    return config.save_token(data, "enterprise")


def authorize_url() -> str:
    cr = config.load_credentials()
    params = {
        "response_type": "code",
        "client_id": cr.client_id,
        "redirect_uri": cr.redirect_uri,
    }
    return config.oauth2_base(cr.host) + "/authorize?" + urllib.parse.urlencode(params)


def exchange_code(code: str) -> dict[str, Any]:
    cr = config.load_credentials()
    data = _token_request(
        cr,
        "authorization_code",
        client_id=cr.client_id,
        client_secret=cr.client_secret,
        code=code,
    )
    return config.save_token(data, "user")


def refresh() -> dict[str, Any]:
    record = config.load_token()
    refresh_token = str(record.get("refresh_token", "") or "")
    if not refresh_token:
        raise config.TokenError(
            "本地没有 refresh_token。重新授权：python3 scripts/pingcode_weekly.py auth login"
        )
    cr = config.load_credentials()
    data = _token_request(cr, "refresh_token", refresh_token=refresh_token)
    return config.save_token(
        data,
        str(record.get("mode", "user") or "user"),
        keep_refresh=refresh_token,
    )


def whoami(api: client.Client | None = None) -> dict[str, Any]:
    if api is None:
        cr = config.load_credentials()
        api = client.Client(bearer=bearer, host=cr.host)
    data = api.get(MYSELF_PATH).data
    return data if isinstance(data, dict) else {}


def status() -> dict[str, Any]:
    record = config.load_token()
    state = config.token_state(record)
    return {
        "mode": current_mode(),
        "has_access_token": bool(record.get("access_token")),
        "has_refresh_token": bool(record.get("refresh_token")),
        "expires_at": state.get("expires_at"),
        "expired": state.get("expired"),
        "config_dir": config.config_dir(),
        "host": _host(),
    }


def _host() -> str:
    try:
        return config.load_credentials().host
    except config.ConfigError:
        return os.environ.get(config.ENV_HOST, config.DEFAULT_HOST)
