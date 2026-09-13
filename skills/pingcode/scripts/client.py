#!/usr/bin/env python3
"""HTTP 传输层：一个地方管好认证头、限流、错误归一化。

为什么值得单独一层
------------------
官方的限流是**两层**，而且公有云与私有部署给的重试响应头**不一样**：

| 环境 | 429 时 | 平时 |
| --- | --- | --- |
| 公有云 | `X-RateLimit-Retry-After` + `X-RateLimit-Reason` | `X-RateLimit-Team-*`、`X-RateLimit-Burst-*` |
| 私有部署 | `X-PC-Retry-After` | — |

参考实现只处理了私有的 `x-pc-retry-after`，在公有云上收到 429 就只会硬失败。这里两个
都读，并把「还剩多少配额」也算出来。

错误也在这里归一化：官方失败时返回 `{code, message}`。401/403 要说清「该怎么办」——
尤其是 403，我们**知道**这个端点需要哪个 scope（`api_index` 里有），所以能直接指出来，
而不是让调用方对着一句"无权限"猜。

测试用 `opener=` 注入假的传输函数，不 mock 到库内部。
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, NamedTuple


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


def _as_int(value: object, default: int = 0) -> int:
    """宽松取整：响应头与响应体都是外部输入，不能因为一个字段坏了就整个崩。"""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default

DEFAULT_TIMEOUT = 30
DEFAULT_RETRIES = 3
MAX_RETRY_SLEEP = 60

# `--dry-run` 只拦**写**。实测撞到过：如果连 GET 也拦，字典解析（项目/类型/状态/
# 优先级/成员）会拿到空列表，**而空列表会被写进缓存** —— 之后正常命令会一直说
# 「这个范围里没有优先级可选项」。而 dry-run 的用处正是「把解析后的真 body 给人看一眼」，
# 那本来就必须要能读。
WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")

RETRY_HEADERS = ("X-RateLimit-Retry-After", "X-PC-Retry-After")
REASON_HEADER = "X-RateLimit-Reason"
QUOTA_HEADERS = (
    ("X-RateLimit-Team-Limit", "企业每分钟上限"),
    ("X-RateLimit-Team-Remaining", "企业本周期剩余"),
    ("X-RateLimit-Team-Reset", "企业配额重置时间"),
    ("X-RateLimit-Burst-Limit", "单接口每秒上限"),
    ("X-RateLimit-Burst-Remaining", "单接口本周期剩余"),
    ("X-RateLimit-Burst-Reset", "单接口配额重置时间"),
)


def _retry_wait(exc: RateLimited, attempt: int) -> int:
    """官方给了建议等待就用它，否则指数退避（上限 MAX_RETRY_SLEEP）。"""
    if exc.retry_after > 0:
        return exc.retry_after
    return min(MAX_RETRY_SLEEP, 2 ** attempt)


class ApiError(Exception):
    """一次 API 调用失败。带足够信息让上层给出「下一步」。"""

    def __init__(self, status: int, message: str, method: str = "", url: str = "",
                 code: str = "", hints: list[str] | None = None) -> None:
        self.status = status
        self.message = message
        self.method = method
        self.url = url
        self.code = code
        self.hints = list(hints or [])
        super().__init__(self.render())

    def render(self) -> str:
        head = f"{self.status} {self.message}"
        if self.method and self.url:
            head = f"{self.method} {self.url} → {head}"
        if self.code:
            head += f"（code={self.code}）"
        if self.hints:
            head += "\n" + "\n".join("  · " + h for h in self.hints)
        return head


class RateLimited(ApiError):
    """429。带上官方建议的等待秒数与原因。"""

    def __init__(self, status: int, message: str, retry_after: int, reason: str,
                 header: str, **kw: Any) -> None:
        self.retry_after = retry_after
        self.reason = reason
        self.header = header
        super().__init__(status, message, **kw)


class Quota(NamedTuple):
    """响应头里的配额快照。拿不到就是空表。"""

    values: dict[str, str]

    @property
    def have_any(self) -> bool:
        return bool(self.values)

    def line(self) -> str:
        if not self.values:
            return ""
        parts = [f"{label} {self.values[key]}" for key, label in QUOTA_HEADERS if key in self.values]
        return "；".join(parts)


class Result(NamedTuple):
    status: int
    data: Any
    method: str
    url: str
    quota: Quota

    @property
    def values(self) -> list[dict[str, Any]]:
        """分页响应的 values；不是分页结构就返回空表。"""
        if isinstance(self.data, dict) and isinstance(self.data.get("values"), list):
            return list(self.data["values"])
        return []

    @property
    def total(self) -> int | None:
        if isinstance(self.data, dict) and isinstance(self.data.get("total"), int):
            return self.data["total"]
        return None


def _reason_of(headers: Any) -> str:
    """429 的原因头（公有云才有）：`pingcode-team` = 企业限流，`pingcode-burst` = 单接口限流。"""
    if not headers:
        return ""
    return str(headers.get(REASON_HEADER) or "")


def parse_retry_after(headers: Any) -> tuple[int, str, str]:
    """从 429 响应头里取（建议等待秒数, 原因, 用到的头名）。

    公有云给 `X-RateLimit-Retry-After`，私有部署给 `X-PC-Retry-After`；两个都读。
    都没有就返回 0 —— 由调用方退回指数退避，不要在这里编一个数。
    """
    if not headers:
        return 0, "", ""
    for name in RETRY_HEADERS:
        raw = headers.get(name)
        if raw is None:
            continue
        return max(0, _as_int(raw)), _reason_of(headers), name
    return 0, _reason_of(headers), ""


def quota_of(headers: Any) -> Quota:
    """把响应头里的配额字段抽出来（拿不到就是空表）。"""
    if not headers:
        return Quota({})
    values = {}
    for key, _label in QUOTA_HEADERS:
        raw = headers.get(key)
        if raw is not None:
            values[key] = str(raw)
    return Quota(values)


def _decode(body: bytes) -> Any:
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return body.decode("utf-8", errors="replace")


class Client:
    """带令牌、限流与错误归一化的客户端。

    `opener` 默认是 `urllib.request.urlopen`；测试注入一个假的就能离线跑，
    不需要 mock 库内部（参考实现 mock 的就是 `urlopen` 本身，所以路径写错也测不出来）。
    """

    def __init__(self, bearer: Callable[[], str], host: str,
                 timeout: int = DEFAULT_TIMEOUT, retries: int = DEFAULT_RETRIES,
                 dry_run: bool = False, sleep: Callable[[float], None] = time.sleep,
                 opener: Callable[..., Any] | None = None,
                 scopes_for: Callable[[str, str], tuple[str, ...]] | None = None) -> None:
        self._bearer = bearer
        self.host = host
        self.timeout = timeout
        self.retries = retries
        self.dry_run = dry_run
        self._sleep = sleep
        self._opener = opener or urllib.request.urlopen
        self._scopes_for = scopes_for

    # ── 请求拼装 ───────────────────────────────────────────────
    def url_for(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return _config.api_base(self.host) + "/" + path.lstrip("/")

    def _headers(self, has_body: bool, authenticate: bool = True) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if authenticate:
            token = self._bearer()
            if token:
                headers["Authorization"] = f"Bearer {token}"
        if has_body:
            headers["Content-Type"] = "application/json"
        return headers

    def describe(self, method: str, path: str, params: dict[str, Any] | None = None,
                 body: dict[str, Any] | None = None,
                 authenticate: bool = True) -> dict[str, Any]:
        """只描述将发出的请求（`--dry-run` 与写操作回显都用它）。**不含令牌。**"""
        method = method.upper()
        url = self.url_for(path)
        if params:
            query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            if query:
                url = url + ("&" if "?" in url else "?") + query
        headers = {"Accept": "application/json"}
        if authenticate:
            headers["Authorization"] = "Bearer ***"
        if body:
            headers["Content-Type"] = "application/json"
        return {"method": method, "url": url, "headers": headers, "body": body}

    # ── 发送 ──────────────────────────────────────────────────
    def request(self, method: str, path: str, params: dict[str, Any] | None = None,
                body: dict[str, Any] | None = None,
                authenticate: bool = True) -> Result:
        method = method.upper()
        plan = self.describe(method, path, params, body, authenticate)
        if self.dry_run and method in WRITE_METHODS:
            return Result(0, plan, method, plan["url"], Quota({}))

        payload = None
        if body is not None:
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")

        attempt = 0
        while True:
            attempt += 1
            try:
                return self._once(method, plan["url"], payload, authenticate)
            except RateLimited as exc:
                if attempt > self.retries:
                    raise
                self._sleep(_retry_wait(exc, attempt))

    def _once(self, method: str, url: str, payload: bytes | None,
              authenticate: bool = True) -> Result:
        request = urllib.request.Request(
            url, data=payload, method=method, headers=self._headers(payload is not None, authenticate)
        )
        try:
            response = self._opener(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            raise self._error_from(method, url, exc, payload) from exc
        except urllib.error.URLError as exc:
            raise ApiError(0, f"连不上 {url}：{exc.reason}", method, url,
                           hints=["检查网络 / 代理，或确认 host 写对了（私有部署形如 your.domain/open）"]) from exc
        except OSError as exc:
            raise ApiError(0, f"请求失败：{exc}", method, url) from exc

        with response:
            data = _decode(response.read())
            status = _as_int(getattr(response, "status", 0))
            headers = getattr(response, "headers", None)
        return Result(status, data, method, url, quota_of(headers))

    def _error_from(self, method: str, url: str, exc: urllib.error.HTTPError,
                    payload: bytes | None = None) -> ApiError:
        try:
            raw = exc.read()
        except (OSError, ValueError):
            raw = b""
        # HTTPError 自带一个未关的 fp：读完要收掉，否则每次失败都留下一个未关对象
        with contextlib.suppress(Exception):
            exc.close()
        data = _decode(raw)
        message, code = "请求失败", ""
        if isinstance(data, dict):
            message = str(data.get("message") or data.get("error") or message)
            code = str(data.get("code") or "")
        elif isinstance(data, str) and data.strip():
            message = data.strip()[:200]

        kwargs = {"code": code, "hints": self._hints_for(method, url, exc.code, payload)}
        if exc.code == 429:
            retry_after, reason, header = parse_retry_after(exc.headers)
            hints = kwargs["hints"]
            if retry_after:
                hints.append(f"官方建议等待 {retry_after} 秒（{header}）")
            hints.append(f"配额：{quota_of(exc.headers).line() or '响应头没给'}")
            return RateLimited(exc.code, message, retry_after, reason, header,
                               method=method, url=url, **kwargs)
        return ApiError(exc.code, message, method, url, **kwargs)

    def _hints_for(self, method: str, url: str, status: int,
                   payload: bytes | None = None) -> list[str]:
        """把状态码翻译成「下一步做什么」。403 能直接点出缺哪个 scope。"""
        if status == 401:
            return ["令牌无效或已过期：跑 `pingcode.py auth login` 重新授权"]
        if status == 403:
            hints = ["当前令牌的权限不够"]
            need = self._scopes_for(method, url) if self._scopes_for else ()
            if need:
                hints.append("这个端点需要 scope：" + "、".join(need) + "（在应用的数据范围里勾上）")
            else:
                hints.append("确认应用的数据范围覆盖了这个资源")
            return hints
        if status == 404:
            return ["对象不存在，或路径不对；路径必须以官方文档为准"]
        if status == 400:
            hints = ["参数不合法：检查必填项、ID 是否属于该项目、状态是否在该类型的可用范围内"]
            # 只在**真的带了父项**时才提父项类型约束 —— 否则每条 400 都挂着一句
            # 无关的提示，反而把真正的错因冲淡了（实测撞到过）。
            if payload and b'"parent_id"' in payload:
                hints.append(
                    "父工作项的**类型**要允许做它的父（官方报 400「父工作项的类型不正确」；"
                    "实测：这个项目里用户故事的父项不能是史诗，得是特性）"
                )
            return hints
        if status >= 500:
            return ["服务端错误，稍后重试"]
        return []

    # ── 便捷方法 ──────────────────────────────────────────────
    def get(self, path: str, **params: Any) -> Result:
        clean = {k: v for k, v in params.items() if v is not None and v != ""}
        return self.request("GET", path, params=clean or None)

    def post(self, path: str, body: dict[str, Any], **params: Any) -> Result:
        clean = {k: v for k, v in params.items() if v is not None and v != ""}
        return self.request("POST", path, params=clean or None, body=body)

    def patch(self, path: str, body: dict[str, Any], **params: Any) -> Result:
        clean = {k: v for k, v in params.items() if v is not None and v != ""}
        return self.request("PATCH", path, params=clean or None, body=body)

    def delete(self, path: str, **params: Any) -> Result:
        clean = {k: v for k, v in params.items() if v is not None and v != ""}
        return self.request("DELETE", path, params=clean or None)

    def paginate(self, path: str, page_size: int = 100, max_items: int = 500,
                 **params: Any) -> list[dict[str, Any]]:
        """翻完所有页（默认最多 500 条）。官方 page_size 上限 100，page_index 从 0 开始。"""
        collected: list[dict[str, Any]] = []
        index = 0
        size = min(max(1, page_size), 100)
        while len(collected) < max_items:
            result = self.get(path, page_size=size, page_index=index, **params)
            values = result.values
            collected.extend(values)
            if len(values) < size:
                break
            index += 1
        return collected[:max_items]
