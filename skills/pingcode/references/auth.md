# 授权与配置

## 一次性准备（在企业后台建应用）

1. PingCode **企业后台 → 凭据管理（应用管理）→ 创建应用**，拿到 `Client ID` 与 `Secret`。
2. 同一个应用里登记 **回调地址**。默认用 `http://localhost:8765/callback` ——
   CLI 会在本机起一个监听自动收授权码，不用手抄。换端口就同时改这里和 `credentials.json`。
3. 配 **数据范围（scope）**。官方一共 54 个 scope，本 skill 的常用命令需要下面这些：

| 要干的事 | 必需的 scope |
| --- | --- |
| 识别「我」（`whoami` / `--assignee @me`） | `pcp:read:account:personal` |
| 人名 → ID（`--assignee 张三`） | `pcp:read:global:team` |
| 查工作项 / 类型 / 状态 / 标签 | `pcp:read:pjm:workitem` |
| 建 / 改 / 删工作项 | `pcp:write:pjm:workitem` |
| 查项目 / 项目状态 / 进度 | `pcp:read:pjm:project` |
| 建 / 改项目 | `pcp:write:pjm:project` |
| 迭代 | `pcp:read:pjm:sprint`（要建迭代再加 `pcp:write:pjm:sprint`） |
| 看板 | `pcp:read:pjm:board` |
| 项目流程、工作项优先级 | `pcp:read:pjm:configuration` |

`pcp:read:pjm:configuration` 最容易漏：漏了会表现为「能查工作项，但列不出优先级和项目流程」，
建项目时也就填不了 `process_id`。

## 两种授权模式（都实现了）

| 模式 | 怎么来 | 有效期 | 能不能识别「我」 | 说明 |
| --- | --- | --- | --- | --- |
| `user`（默认） | 授权码 `authorization_code`：浏览器点一次授权 | access **30 天** / refresh **90 天** | ✅ `/v1/myself` | 只能访问该用户权限内的数据 |
| `enterprise` | 客户端凭据 `client_credentials` | **30 天** | ❌ 要显式给用户 | 官方原话：企业令牌「拥有系统管理员权限」，**谨慎保管** |

默认走 `user`，原因是官方 `/v1/myself` 只认**用户令牌** —— 企业令牌下「我的任务」只能靠
手工维护一个用户 ID，配错了不报错，只是查出来是别人的东西。

```sh
python3 scripts/pingcode.py auth login                 # 默认 user：打印授权链接，本机等回调
python3 scripts/pingcode.py auth login --manual        # 不想起监听：自己贴回调里的 code
python3 scripts/pingcode.py auth login --mode enterprise
python3 scripts/pingcode.py auth status                # 令牌来源 / 模式 / 还剩多久 / 能不能续
python3 scripts/pingcode.py auth logout                # 只删本地令牌，不动应用凭据
```

## 令牌生命周期

- 到期前：直接用缓存里的 `access_token`。
- 到期后：**自动用 `refresh_token` 换新的**，不需要重新授权（refresh 有效期 90 天）。
- `refresh_token` 也失效：报错让你重新 `auth login`。
- 在后台**重置应用密钥或删除应用**，当前令牌立即失效。
- 想立刻换：`auth logout` 后再 `auth login`。

## 配置放在哪

**全局一套，放在用户目录，不进仓库**（`PINGCODE_CONFIG_DIR` 可以换目录）：

```text
~/.config/pingcode/
├── credentials.json    # 你手填：host / auth_mode / client_id / client_secret / redirect_uri
├── token.json          # 程序写：access_token / refresh_token / 到期时间
├── context.json        # 程序写：当前项目、当前迭代
└── cache.json          # 程序写：项目/迭代/类型/状态/优先级/标签/成员的字典缓存（6 小时）
```

`credentials.json`：

```json
{
  "host": "open.pingcode.com",
  "auth_mode": "user",
  "client_id": "填你的 Client ID",
  "client_secret": "填你的 Secret",
  "redirect_uri": "http://localhost:8765/callback"
}
```

私有部署把 `host` 写成 `你的域名/open`（REST 根带 `/open`，授权页根不带 —— 代码会自动区分）。

令牌与上下文**原子写 + 权限 0600**（先写临时文件再 `os.replace`），不会留下半截文件，
同机器其他用户也读不到。

## 环境变量（优先级高于配置文件）

| 变量 | 用途 |
| --- | --- |
| `PINGCODE_CLIENT_ID` / `PINGCODE_CLIENT_SECRET` | CI / Agent 里免写文件 |
| `PINGCODE_HOST` | 覆盖 host（私有部署 / 测试环境） |
| `PINGCODE_AUTH_MODE` | `user` / `enterprise` |
| `PINGCODE_ACCESS_TOKEN` | **直接给一个令牌**，跳过登录（临时排障、只读场景） |
| `PINGCODE_CONFIG_DIR` | 换配置目录（每个企业一套配置、跑测试时隔离） |

## 排错

| 现象 | 意思 | 怎么办 |
| --- | --- | --- |
| 401 | 令牌无效/过期/被撤销 | `auth login` 重新授权 |
| 403 | 应用的数据范围不够（**报错会指出缺哪个 scope**） | 去后台把这个 scope 勾上，然后重新授权 |
| 404 | 对象不存在，或路径不对 | 对象确认一遍；路径以生成的端点表为准（`api --list 关键词`） |
| 429 | 触发了限流 | 报错会带官方建议的等待秒数与剩余配额；CLI 已自动按建议重试 |
| 连不上 / 域名解析失败 | host 写错（私有部署少了 `/open`）或网络 | `auth status` 会打出解析后的 REST 根与 OAuth2 根 |
| `/v1/myself` 报「只认用户令牌」 | 当前是企业令牌 | `auth login --mode user` |

限流细节（官方）：公有云两层限流 —— 企业每分钟 200（免费版）/ 500 + 成员数 × 20（付费版），
单接口每秒 30；429 时公有云返回 `X-RateLimit-Retry-After`，私有部署返回 `X-PC-Retry-After`。
两种响应头都读。
