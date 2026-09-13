#!/usr/bin/env python3
"""授权：企业令牌 / 用户令牌，令牌缓存与自动刷新。

为什么默认用户令牌
------------------
官方文档里 `/v1/myself` 的 `permission` 只有**用户令牌** —— 企业令牌拿不到"我是谁"。
参考实现选了企业令牌（配置最少），于是「我的任务」只能靠一个 `PINGCODE_USER_ID`
环境变量来表达"我"，配错了不报错、只是查出来是别人的东西。

两种模式的取舍（都实现了，`auth_mode` 选）：

| 模式 | 怎么来 | 有效期 | 能不能识别"我" | 风险 |
| --- | --- | --- | --- | --- |
| `user`（默认） | 授权码 `authorization_code`，浏览器点一次授权 | access 30 天 / refresh 90 天 | ✅ `/v1/myself` | 只能访问该用户权限内的数据 |
| `enterprise` | 客户端凭据 `client_credentials` | 30 天 | ❌ 要显式指定用户 | 官方原话：**系统管理员权限** |

令牌接口本身不需要认证头，所以走 `authenticate=False`。
刷新用 `refresh_token`（官方那条只需要 `grant_type` + `refresh_token`）。
"""

from __future__ import annotations

import contextlib
import http.server
import importlib.util
import os
import sys
import time
import urllib.parse
from typing import Any, Callable


def _load_sibling(name: str):
    """动态加载同目录脚本（`scripts/` 不是包，同级 import 在静态层面无法解析）。

    **同一个模块只加载一次**：这个函数会被好几个模块各自调用，如果每次都新建一个模块
    对象，就会出现两份互不相干的模块状态 —— 连异常类都不是同一个，`except` 会静默抓不到。
    所以先查 `sys.modules`。
    """
    key = f"_pingcode_{name}"
    loaded = sys.modules.get(key)
    if loaded is not None:
        return loaded
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.py")
    spec = importlib.util.spec_from_file_location(key, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了同目录模块：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


_config = _load_sibling("config")
_client = _load_sibling("client")
_api = _load_sibling("api_index")

TOKEN_PATH = "/v1/auth/token"
MYSELF_PATH = "/v1/myself"
CALLBACK_TIMEOUT = 180


def grant_entry(grant: str) -> Any:
    """取令牌端点。同一路径有三个 grant_type，必须靠 query 消歧（表里有测试钉住）。"""
    return _api.require("GET", TOKEN_PATH, {"grant_type": grant})


def anonymous(host: str) -> Any:
    """不带认证头的客户端 —— 换令牌时用。"""
    return _client.Client(bearer=lambda: "", host=host)


# ── 令牌的取用 ────────────────────────────────────────────────
def bearer() -> str:
    """拿来就能用的访问令牌：环境变量 > 缓存（过期则自动 refresh）。"""
    from_env = os.environ.get(_config.ENV_TOKEN, "").strip()
    if from_env:
        return from_env

    record = _config.load_token()
    state = _config.token_state(record)
    if state["present"] and not state["expired"]:
        return str(record.get("access_token", ""))

    if record.get("refresh_token"):
        return str(refresh().get("access_token", ""))

    if state["present"]:
        raise _config.TokenError(
            "令牌已过期，而且没有 refresh_token 可用。重新授权：pingcode.py auth login"
        )
    raise _config.TokenError(
        "还没有令牌。先授权：pingcode.py auth login"
        "（或者在环境变量 PINGCODE_ACCESS_TOKEN 里直接给一个令牌）"
    )


def current_mode() -> str:
    """当前令牌是哪一种。没有令牌时按配置里的 auth_mode。"""
    record = _config.load_token()
    mode = str(record.get("mode", "") or "")
    if mode:
        return mode
    try:
        return _config.load_credentials().auth_mode
    except _config.ConfigError:
        return ""


# ── 两种授权 ──────────────────────────────────────────────────
def login_enterprise() -> dict[str, Any]:
    """客户端凭据模式 → 企业令牌。"""
    cr = _config.load_credentials()
    entry = grant_entry("client_credentials")
    result = anonymous(cr.host).request(
        "GET", entry.url, authenticate=False,
        params={"client_id": cr.client_id, "client_secret": cr.client_secret},
    )
    return _config.save_token(result.data or {}, "enterprise")


def authorize_url() -> str:
    """给用户点的授权页地址（用户令牌的第一步）。"""
    cr = _config.load_credentials()
    params = {
        "response_type": "code",
        "client_id": cr.client_id,
        "redirect_uri": cr.redirect_uri,
    }
    return _config.oauth2_base(cr.host) + "/authorize?" + urllib.parse.urlencode(params)


def exchange_code(code: str) -> dict[str, Any]:
    """用授权码换用户令牌。"""
    cr = _config.load_credentials()
    entry = grant_entry("authorization_code")
    result = anonymous(cr.host).request(
        "GET", entry.url, authenticate=False,
        params={"client_id": cr.client_id, "client_secret": cr.client_secret, "code": code},
    )
    return _config.save_token(result.data or {}, "user")


def refresh() -> dict[str, Any]:
    """用 refresh_token 换新令牌（官方那条只要 grant_type + refresh_token）。"""
    record = _config.load_token()
    token = str(record.get("refresh_token", "") or "")
    if not token:
        raise _config.TokenError("本地没有 refresh_token：重新授权 pingcode.py auth login")
    cr = _config.load_credentials()
    entry = grant_entry("refresh_token")
    result = anonymous(cr.host).request(
        "GET", entry.url, authenticate=False, params={"refresh_token": token},
    )
    return _config.save_token(result.data or {}, str(record.get("mode", "user") or "user"),
                              keep_refresh=token)


# ── 本地回调：自动收授权码 ────────────────────────────────────
class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    code: str = ""
    error: str = ""

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 的约定
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
        type(self).code = str(params.get("code", "") or "")
        type(self).error = str(params.get("error", "") or "")
        ok = bool(type(self).code)
        text = "授权成功，可以关闭此页面，回到终端继续。" if ok else f"没拿到授权码（{self.error or '未知原因'}）。"
        body = ("<html><head><meta charset='utf-8'><title>PingCode</title></head>"
                f"<body style='font-family:sans-serif;padding:2rem'><h3>{text}</h3></body></html>")
        # 已经拿到 code 了，回不回得去网页不重要（用户可能提前关页面）—— 不让它变成异常
        with contextlib.suppress(OSError):
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body.encode("utf-8"))))
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - 基类就是这么签名的
        """默认会把每个请求打到 stderr，这里静音（终端输出由我们自己控制）。"""


def wait_for_code(redirect_uri: str, timeout: int = CALLBACK_TIMEOUT,
                  echo: Callable[[str], None] = print) -> str:
    """起本地监听等回调，自动拿到 code。

    端口从 `redirect_uri` 里取，所以**必须和应用里登记的回调地址一致**（默认
    `http://localhost:8765/callback`）。不想用监听就加 `--manual` 手动贴 code。
    """
    parsed = urllib.parse.urlparse(redirect_uri)
    host = parsed.hostname or "localhost"
    port = parsed.port or _config.DEFAULT_PORT
    _CallbackHandler.code = ""
    _CallbackHandler.error = ""
    try:
        server = http.server.HTTPServer((host, port), _CallbackHandler)
    except OSError as exc:
        raise _config.TokenError(
            f"起不了本地回调监听 {host}:{port} —— {exc}\n"
            f"  端口被占用就换一个（改 credentials.json 的 redirect_uri + 后台登记的地址），"
            f"或者加 --manual 手动贴 code。"
        ) from exc

    server.timeout = 1
    deadline = time.time() + timeout
    echo(f"等到授权为止（最多 {timeout} 秒）… 监听 {host}:{port}")
    with server:
        while not _CallbackHandler.code and time.time() < deadline:
            server.handle_request()
    if not _CallbackHandler.code:
        raise _config.TokenError("等不到授权回调（超时）。可以加 --manual 手动贴 code。")
    return _CallbackHandler.code


# ── 身份 ──────────────────────────────────────────────────────
def whoami(client: Any) -> dict[str, Any]:
    """`/v1/myself`。企业令牌拿不到 —— 这里提前说清，不让它变成一句 403。"""
    if current_mode() == "enterprise":
        raise _config.TokenError(
            "企业令牌拿不到个人信息（官方约定 /v1/myself 只认用户令牌）。\n"
            "  想看「我是谁」：pingcode.py auth login --mode user\n"
            "  企业令牌下指定负责人要显式给用户 ID 或名字。"
        )
    entry = _api.require("GET", MYSELF_PATH)
    return dict(client.get(entry.path).data or {})


def status() -> dict[str, Any]:
    """`auth status` 的数据：令牌从哪来、还剩多久、能不能 refresh。"""
    info: dict[str, Any] = {}
    env_token = os.environ.get(_config.ENV_TOKEN, "").strip()
    record = _config.load_token()
    state = _config.token_state(record)
    if env_token:
        info["令牌来源"] = f"环境变量 {_config.ENV_TOKEN}"
        info["授权模式"] = "（由环境变量提供，未知）"
        info["状态"] = "可用"
    elif state["present"]:
        info["令牌来源"] = _config.path_of(_config.TOKEN)
        info["授权模式"] = state["mode"] or "(未记录)"
        if state["expired"]:
            info["状态"] = "已过期" + ("（可用 refresh_token 续）" if state["has_refresh"] else "（需要重新授权）")
        else:
            days = state["seconds_left"] // 86400
            hours = (state["seconds_left"] % 86400) // 3600
            info["状态"] = f"可用，还剩 {days} 天 {hours} 小时"
        info["到期时间"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(state["expires_at"]))
        info["有 refresh_token"] = "有" if state["has_refresh"] else "没有"
    else:
        info["令牌来源"] = "（还没有令牌）"
        info["状态"] = "未授权：pingcode.py auth login"

    try:
        cr = _config.load_credentials()
        described = _config.describe_credentials(cr)
        # describe_credentials 里的「授权模式」指的是**配置里**想要的模式，
        # 不能盖掉上面从**当前令牌**读出来的那个 —— 实测就撞到过：配置写 user、
        # 实际存的是企业令牌，这一列会显示 user（谎报）。两个分开列。
        described["配置里的模式"] = described.pop("授权模式")
        info.update(described)
    except _config.ConfigError as exc:
        info["凭据"] = str(exc).splitlines()[0]
    return info
