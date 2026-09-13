#!/usr/bin/env python3
"""config / client / auth 的回归测试。

为什么需要
----------
这一层管的是**认证、限流、错误翻译**，全都出错在"看不见的地方"：

1. 令牌与凭据是安全的边界。`write_private` 必须原子写 + 0600，`describe_credentials`
   绝不能把 secret 带出去 —— 这两条坏了不会报错，只会静默泄露。
2. 限流有两个响应头（公有云 `X-RateLimit-Retry-After`、私有部署 `X-PC-Retry-After`），
   参考实现只处理了后者。测试把两个都钉住。
3. 403 的提示要能指出缺哪个 scope —— 那是 `api_index` 与 `client` 的接口，靠 `scopes_for`
   回调接上，容易在重构里悄悄断掉。
4. 官方示例的 `expires_in` 给的是**绝对时间戳**（1577808000），而 OAuth 常规语义是秒数。
   两种都要能算对，否则要么立刻过期要么几十年后过期。

测试全部在临时配置目录里跑（`PINGCODE_CONFIG_DIR`），**不碰真实的 ~/.config/pingcode**。

跑法：
    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.error
from email.message import Message
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")


def _load(name: str, alias: str):
    """按路径加载脚本，**用和脚本内部一致的模块名**。

    脚本之间用 `_load_sibling("config")` 互相加载（注册名 `_pingcode_config`）。
    测试若用另一个别名再加载一次，就会得到**两个不同的模块对象**，于是
    `cfg.TokenError` 与 auth 里抛的那个不是同一个类 —— assertRaises 抓不到。
    """
    spec = importlib.util.spec_from_file_location(alias, os.path.join(SCRIPTS, f"{name}.py"))
    if spec is None or spec.loader is None:
        raise RuntimeError(name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


cfg = _load("config", "_pingcode_config")
client = _load("client", "_pingcode_client")
auth = _load("auth", "_pingcode_auth")

ENV_KEYS = (cfg.ENV_DIR, cfg.ENV_HOST, cfg.ENV_MODE, cfg.ENV_ID, cfg.ENV_SECRET, cfg.ENV_TOKEN)


class TempConfigCase(unittest.TestCase):
    """每个用例一个干净的配置目录。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = {k: os.environ.get(k) for k in ENV_KEYS}
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        os.environ[cfg.ENV_DIR] = self._tmp.name
        self.addCleanup(self._restore_env)

    def _restore_env(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def write_credentials(self, **fields: str) -> None:
        data = {"host": "open.pingcode.com", "auth_mode": "user",
                "client_id": "cid", "client_secret": "sec"}
        data.update(fields)
        cfg.write_private(cfg.path_of(cfg.CREDENTIALS), data)


# ── 响应替身 ──────────────────────────────────────────────────
class FakeResponse(io.BytesIO):
    def __init__(self, payload, status: int = 200, headers: dict | None = None) -> None:
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        super().__init__(body)
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def header_message(headers: dict | None) -> Message:
    """HTTPError 要的 hdrs 是 email.message.Message（不是 dict），构造一个。"""
    message = Message()
    for key, value in (headers or {}).items():
        message[key] = str(value)
    return message


def http_error(code: int, payload, headers: dict | None = None) -> urllib.error.HTTPError:
    body = json.dumps(payload).encode("utf-8")
    return urllib.error.HTTPError("https://x/y", code, "err", header_message(headers), io.BytesIO(body))


class TransportCase(TempConfigCase):
    def opener_returning(self, response):
        def opener(_request, timeout=None):  # noqa: ARG001
            if isinstance(response, Exception):
                raise response
            return response
        return opener

    def make_client(self, response, **kw) -> tuple:
        calls = []
        slept: list[float] = []

        def opener(request, timeout=None):
            calls.append(request)
            # response 可以是实例，也可以是工厂函数 —— 重试时要拿到**新的**错误对象
            item = response() if callable(response) else response
            if isinstance(item, Exception):
                raise item
            return item

        options = {"bearer": lambda: "tok", "host": "open.pingcode.com", "opener": opener,
                   # 默认把 sleep 换成空操作：真等一次 429 建议的 50 秒，一个用例就花掉 150 秒
                   "sleep": lambda seconds: slept.append(seconds)}
        options.update(kw)
        return client.Client(**options), calls


# ── 配置 ──────────────────────────────────────────────────────
class ConfigTest(TempConfigCase):
    def test_目录与文件名稳定(self):
        saved = os.environ.pop(cfg.ENV_DIR, None)
        try:
            self.assertTrue(cfg.config_dir().endswith(os.path.join(".config", "pingcode")))
        finally:
            if saved is not None:
                os.environ[cfg.ENV_DIR] = saved
        self.assertEqual(os.path.join(cfg.config_dir(), "token.json"), cfg.path_of(cfg.TOKEN))

    def test_原子写且权限是0600(self):
        path = cfg.path_of(cfg.CREDENTIALS)
        cfg.write_private(path, {"client_secret": "s"})
        self.assertEqual(0o600, os.stat(path).st_mode & 0o777)
        leftovers = [f for f in os.listdir(cfg.config_dir()) if f.startswith(".tmp-")]
        self.assertEqual([], leftovers, "临时文件不能留在配置目录里")

    def test_凭据默认值与环境变量覆盖(self):
        self.write_credentials()
        cr = cfg.load_credentials()
        self.assertEqual(("user", "cid"), (cr.auth_mode, cr.client_id))
        self.assertEqual(cfg.path_of(cfg.CREDENTIALS), cr.source)

        os.environ[cfg.ENV_MODE] = "enterprise"
        os.environ[cfg.ENV_ID] = "env-id"
        cr = cfg.load_credentials()
        self.assertEqual(("enterprise", "env-id", "环境变量"), (cr.auth_mode, cr.client_id, cr.source))

    def test_没凭据时报错要说清怎么补(self):
        with self.assertRaises(cfg.ConfigError) as ctx:
            cfg.load_credentials()
        message = str(ctx.exception)
        self.assertIn(cfg.path_of(cfg.CREDENTIALS), message)
        self.assertIn(cfg.ENV_ID, message)

    def test_auth_mode_写错要报错(self):
        self.write_credentials(auth_mode="whatever")
        with self.assertRaises(cfg.ConfigError) as ctx:
            cfg.load_credentials()
        self.assertIn("enterprise", str(ctx.exception))

    def test_只给访问令牌可以不配客户端凭据(self):
        os.environ[cfg.ENV_TOKEN] = "direct"
        cr = cfg.load_credentials()
        self.assertIn(cfg.ENV_TOKEN, cr.source)

    def test_摘要里不能出现_secret(self):
        self.write_credentials(client_secret="超级机密")
        summary = cfg.describe_credentials(cfg.load_credentials())
        self.assertNotIn("超级机密", json.dumps(summary, ensure_ascii=False))
        self.assertEqual("已配置", summary["client_secret"])

    def test_私有部署的_open_前缀只影响_REST_根(self):
        self.assertEqual("https://open.pingcode.com", cfg.api_base("open.pingcode.com"))
        self.assertEqual("https://open.pingcode.com/oauth2", cfg.oauth2_base("open.pingcode.com"))
        self.assertEqual("https://corp.example.com/open", cfg.api_base("corp.example.com/open"))
        self.assertEqual("https://corp.example.com/oauth2", cfg.oauth2_base("corp.example.com/open"))

    def test_到期时间两种语义都算对(self):
        self.assertEqual(1577808000, cfg.expire_at({"expires_in": 1577808000}, 100),
                         "大于阈值的 expires_in 是绝对时间戳")
        now = int(time.time())
        seconds = cfg.expire_at({"expires_in": 2592000}, 100)
        self.assertLess(abs(seconds - (now + 2592000)), 5, "秒数要换算成「现在 + N」")
        fallback = cfg.expire_at({"expires_in": "坏值"}, 100)
        self.assertLess(abs(fallback - (now + 100)), 5, "拿不到 expires_in 时用兜底 TTL")
        missing = cfg.expire_at({}, cfg.FALLBACK_ACCESS_TTL)
        self.assertLess(abs(missing - (now + cfg.FALLBACK_ACCESS_TTL)), 5)

    def test_令牌读写与状态(self):
        record = cfg.save_token({"access_token": "a", "refresh_token": "r", "expires_in": 2592000}, "user")
        self.assertEqual("user", record["mode"])
        state = cfg.token_state()
        self.assertTrue(state["present"])
        self.assertFalse(state["expired"])
        self.assertTrue(state["has_refresh"])
        self.assertGreater(state["seconds_left"], 0)

    def test_刷新响应没带_refresh_token_时要保留旧的(self):
        cfg.save_token({"access_token": "a", "refresh_token": "r1"}, "user")
        record = cfg.save_token({"access_token": "a2"}, "user", keep_refresh="r1")
        self.assertEqual("r1", record["refresh_token"])
        self.assertEqual("a2", cfg.load_token()["access_token"])

    def test_没有_access_token_要报错(self):
        with self.assertRaises(cfg.TokenError):
            cfg.save_token({"token_type": "Bearer"}, "user")

    def test_过期令牌的状态(self):
        cfg.write_private(cfg.path_of(cfg.TOKEN), {"access_token": "a", "expires_at": 1})
        state = cfg.token_state()
        self.assertTrue(state["expired"])
        self.assertEqual(0, state["seconds_left"])

    def test_上下文只覆盖给到的键(self):
        cfg.save_context(project="演示", sprint="S1")
        cfg.save_context(sprint="S2")
        self.assertEqual({"project": "演示", "sprint": "S2"}, cfg.load_context())
        cfg.save_context(project=None)
        self.assertEqual({"sprint": "S2"}, cfg.load_context())


# ── 客户端 ────────────────────────────────────────────────────
class ClientTest(TransportCase):
    def test_describe_不带真令牌(self):
        cli, _calls = self.make_client(FakeResponse({}))
        plan = cli.describe("GET", "/v1/myself")
        self.assertEqual("Bearer ***", plan["headers"]["Authorization"])
        self.assertNotIn("tok", json.dumps(plan))

    def test_dry_run_不发请求(self):
        cli, calls = self.make_client(FakeResponse({"id": "x"}), dry_run=True)
        result = cli.post("/v1/pjm/workitems", {"title": "t"})
        self.assertEqual(0, result.status)
        self.assertEqual([], calls)
        self.assertEqual("t", result.data["body"]["title"])

    def test_查询参数只带非空值(self):
        cli, calls = self.make_client(FakeResponse({"values": []}))
        cli.get("/v1/pjm/workitems", project_id="p", keywords=None, state_id="")
        self.assertIn("project_id=p", calls[0].full_url)
        self.assertNotIn("keywords", calls[0].full_url)

    def test_换令牌时不带认证头(self):
        cli, calls = self.make_client(FakeResponse({"access_token": "x"}), bearer=lambda: "should-not-appear")
        cli.request("GET", "/v1/auth/token", params={"grant_type": "refresh_token"}, authenticate=False)
        self.assertIsNone(calls[0].get_header("Authorization"))

    def test_有令牌时带上认证头(self):
        cli, calls = self.make_client(FakeResponse({}))
        cli.get("/v1/myself")
        self.assertEqual("Bearer tok", calls[0].get_header("Authorization"))

    def test_公有云的429读_X_RateLimit_Retry_After(self):
        def make_error():
            return http_error(429, {"code": "100038", "message": "请求频率过高"},
                              {"X-RateLimit-Retry-After": "50", "X-RateLimit-Reason": "pingcode-team",
                               "X-RateLimit-Team-Remaining": "0"})

        cli, _calls = self.make_client(make_error, retries=0)
        with self.assertRaises(client.RateLimited) as ctx:
            cli.get("/v1/pjm/workitems")
        self.assertEqual(50, ctx.exception.retry_after)
        self.assertEqual("pingcode-team", ctx.exception.reason)
        self.assertIn("X-RateLimit-Retry-After", str(ctx.exception))
        self.assertIn("企业本周期剩余 0", str(ctx.exception), "429 要把配额情况一并说出来")

    def test_私有部署的429读_X_PC_Retry_After(self):
        retry, reason, header = client.parse_retry_after({"X-PC-Retry-After": "30"})
        self.assertEqual((30, "", "X-PC-Retry-After"), (retry, reason, header))

    def test_429按建议等待并重试(self):
        slept: list[float] = []

        def opener(request, timeout=None):
            raise http_error(429, {"message": "too many"}, {"X-RateLimit-Retry-After": "7"})

        cli = client.Client(bearer=lambda: "t", host="h", opener=opener,
                            retries=2, sleep=lambda s: slept.append(s))
        with self.assertRaises(client.RateLimited):
            cli.get("/v1/pjm/workitems")
        self.assertEqual([7, 7], slept, "每次重试都按官方建议等待")

    def test_429没有建议时用指数退避且封顶(self):
        slept: list[float] = []

        def opener(request, timeout=None):
            raise http_error(429, {"message": "x"})

        cli = client.Client(bearer=lambda: "t", host="h", opener=opener,
                            retries=3, sleep=lambda s: slept.append(s))
        with self.assertRaises(client.RateLimited):
            cli.get("/v1/pjm/workitems")
        self.assertEqual(3, len(slept))
        self.assertLessEqual(max(slept), client.MAX_RETRY_SLEEP)

    def test_重试成功时不再抛错(self):
        attempts = {"n": 0}

        def opener(request, timeout=None):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise http_error(429, {"message": "slow down"}, {"X-RateLimit-Retry-After": "1"})
            return FakeResponse({"values": [{"id": "ok"}]})

        cli = client.Client(bearer=lambda: "t", host="h", opener=opener,
                            retries=2, sleep=lambda s: None)
        self.assertEqual(["ok"], [v["id"] for v in cli.get("/v1/pjm/workitems").values])

    def test_配额从响应头读出来(self):
        cli, _calls = self.make_client(FakeResponse(
            {"values": []}, headers={"X-RateLimit-Team-Limit": "200", "X-RateLimit-Team-Remaining": "0"}))
        result = cli.get("/v1/pjm/workitems")
        self.assertTrue(result.quota.have_any)
        self.assertIn("企业每分钟上限 200", result.quota.line())

    def test_403要指出缺哪个_scope(self):
        cli, _calls = self.make_client(
            http_error(403, {"message": "无权限"}),
            scopes_for=lambda method, url: ("pcp:write:pjm:workitem",))
        with self.assertRaises(client.ApiError) as ctx:
            cli.post("/v1/pjm/workitems", {})
        self.assertIn("pcp:write:pjm:workitem", str(ctx.exception))

    def test_401要说去重新授权(self):
        cli, _calls = self.make_client(http_error(401, {"message": "invalid token"}))
        with self.assertRaises(client.ApiError) as ctx:
            cli.get("/v1/myself")
        self.assertIn("auth login", str(ctx.exception))

    def test_错误体里的_code_与_message_要带出来(self):
        cli, _calls = self.make_client(http_error(400, {"code": "100014", "message": "参数不合法"}))
        with self.assertRaises(client.ApiError) as ctx:
            cli.get("/v1/pjm/workitems")
        self.assertEqual("100014", ctx.exception.code)
        self.assertEqual("参数不合法", ctx.exception.message)
        self.assertEqual(400, ctx.exception.status)

    def test_不是_json的错误体也要能报出来(self):
        error = urllib.error.HTTPError("https://x/y", 502, "bad", header_message(None),
                                       io.BytesIO(b"<html>502</html>"))
        cli, _calls = self.make_client(error)
        with self.assertRaises(client.ApiError) as ctx:
            cli.get("/v1/pjm/projects")
        self.assertIn("502", str(ctx.exception))

    def test_连不上要给网络提示(self):
        cli, _calls = self.make_client(urllib.error.URLError("dns 挂了"))
        with self.assertRaises(client.ApiError) as ctx:
            cli.get("/v1/myself")
        self.assertEqual(0, ctx.exception.status)
        self.assertIn("host", str(ctx.exception))

    def test_分页按首页短页停(self):
        pages = [{"values": [{"id": "1"}, {"id": "2"}], "total": 3},
                 {"values": [{"id": "3"}], "total": 3}]
        seen: list[int] = []

        def opener(request, timeout=None):
            seen.append(1)
            return FakeResponse(pages[min(len(seen) - 1, len(pages) - 1)])

        cli = client.Client(bearer=lambda: "t", host="h", opener=opener)
        values = cli.paginate("/v1/pjm/workitems", page_size=2)
        self.assertEqual(["1", "2", "3"], [v["id"] for v in values])
        self.assertEqual(2, len(seen), "拿到短页就停，不要多打一次")

    def test_分页不吃超过上限的_page_size(self):
        cli, calls = self.make_client(FakeResponse({"values": []}))
        cli.paginate("/v1/pjm/workitems", page_size=999)
        self.assertIn("page_size=100", calls[0].full_url, "官方上限是 100")


# ── 授权 ──────────────────────────────────────────────────────
class AuthTest(TempConfigCase):
    def test_三个_grant_type_都能唯一定位(self):
        for grant in ("client_credentials", "authorization_code", "refresh_token"):
            with self.subTest(grant=grant):
                entry = auth.grant_entry(grant)
                self.assertIn(f"grant_type={grant}", entry.url)

    def test_凭据优先用环境变量里的令牌(self):
        os.environ[cfg.ENV_TOKEN] = "env-token"
        self.assertEqual("env-token", auth.bearer())

    def test_有缓存令牌就直接用(self):
        cfg.save_token({"access_token": "cached", "expires_in": 2592000}, "user")
        self.assertEqual("cached", auth.bearer())

    def test_过期且有_refresh_就自动续(self):
        cfg.save_token({"access_token": "old", "refresh_token": "r1", "expires_in": 2592000}, "user")
        record = cfg.load_token()
        record["expires_at"] = 1
        cfg.write_private(cfg.path_of(cfg.TOKEN), record)

        calls: list[str] = []

        def fake_refresh():
            calls.append("refresh")
            return cfg.save_token({"access_token": "new", "expires_in": 2592000}, "user",
                                  keep_refresh="r1")

        with mock.patch.object(auth, "refresh", fake_refresh):
            self.assertEqual("new", auth.bearer())
        self.assertEqual(["refresh"], calls)

    def test_没令牌时报错要说怎么授权(self):
        with self.assertRaises(cfg.TokenError) as ctx:
            auth.bearer()
        self.assertIn("auth login", str(ctx.exception))

    def test_过期且没有_refresh_要说重新授权(self):
        cfg.write_private(cfg.path_of(cfg.TOKEN), {"access_token": "a", "expires_at": 1})
        with self.assertRaises(cfg.TokenError) as ctx:
            auth.bearer()
        self.assertIn("auth login", str(ctx.exception))

    def test_授权页地址用_oauth2_根(self):
        self.write_credentials(client_id="cid")
        url = auth.authorize_url()
        self.assertTrue(url.startswith("https://open.pingcode.com/oauth2/authorize?"))
        self.assertIn("response_type=code", url)
        self.assertIn("client_id=cid", url)
        self.assertIn("redirect_uri=", url)

    def test_企业令牌拿不到_myself_要提前说清(self):
        cfg.save_token({"access_token": "a", "expires_in": 2592000}, "enterprise")
        with self.assertRaises(cfg.TokenError) as ctx:
            auth.whoami(object())
        self.assertIn("用户令牌", str(ctx.exception))

    def test_企业令牌登录用_client_credentials(self):
        self.write_credentials()
        seen: list[str] = []

        def opener(request, timeout=None):
            seen.append(request.full_url)
            return FakeResponse({"access_token": "ent", "expires_in": 2592000})

        fake_transport = client.Client(bearer=lambda: "", host="h", opener=opener)
        with mock.patch.object(auth, "anonymous", lambda host: fake_transport):
            record = auth.login_enterprise()
        self.assertEqual("enterprise", record["mode"])
        self.assertIn("grant_type=client_credentials", seen[0])
        self.assertIn("client_id=cid", seen[0])

    def test_status_在没配置时也给出下一步(self):
        info = auth.status()
        self.assertIn("auth login", " ".join(str(v) for v in info.values()))

    def test_status_不回显_secret(self):
        self.write_credentials(client_secret="机密值")
        cfg.save_token({"access_token": "tok-value", "expires_in": 2592000}, "user")
        text = json.dumps(auth.status(), ensure_ascii=False)
        self.assertNotIn("机密值", text)
        self.assertNotIn("tok-value", text)
        self.assertIn("已配置", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
