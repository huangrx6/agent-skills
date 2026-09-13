# pingcode

> 用命令行维护 PingCode 的**项目**、**工作项**（史诗 / 特性 / 用户故事 / 任务 / 缺陷 / 事务）、
> 迭代与看板：查我的待办、按条件搜、看详情、建项目、建改工作项（描述、起止日期、负责人、
> 优先级、父项、迭代）、改状态、加评论、删工作项。
> **不做**成员 / 权限 / 部门管理，不做 CI 与流水线，也不提供任何绕过权限的操作。

## 解决什么问题

「我的任务」和「帮我建个缺陷」这两件事，在网页端要点七八下；交给 Agent 做又不能靠它背 API ——
PingCode 的 PJM 前缀是 `/v1/pjm/`（`workitems` 没有下划线），凭印象拼路径会 404，而**这类错
最容易被假测试掩盖**（有个公开实现就写死了 `/v1/project/work_items`，测试 mock 了网络所以一直绿）。

这个 skill 把这条风险变成机械错误：路径来自官方文档生成的端点表，发送前就校验；
项目名、迭代名、状态名、人名都走解析，**有歧义就列候选**而不是挑一个。

触发语：`查一下我在 PingCode 里的任务` / `把 SCR-12 关掉` / `建一个缺陷` / `这个项目进度怎么样` /
`我在 PingCode 上的令牌过期了`。

## 安装

```sh
python3 tools/install_skills.py                   # 默认装软链（推荐，改仓库即时生效）
python3 tools/install_skills.py --check           # 看指向对不对
npx skills add <repo> --skill pingcode --agent claude-code --global   # 副本方式
```

依赖：**只用 Python 标准库**（3.11+，用到 `X | Y` 类型标注）。不需要 pip install。

## 配置

| 配置项 | 从哪里读 | 说明 |
| --- | --- | --- |
| `client_id` / `client_secret` | `$PINGCODE_CLIENT_ID` / `$PINGCODE_CLIENT_SECRET` → `~/.config/pingcode/credentials.json` | 在 PingCode 企业后台的凭据管理里建应用后获得 |
| `host` | `$PINGCODE_HOST` → 同一文件 | 公有云 `open.pingcode.com`；私有部署 `你的域名/open` |
| `auth_mode` | `$PINGCODE_AUTH_MODE` → 同一文件 | 默认 `user`（用户令牌，能识别「我」） |
| 访问令牌 | `$PINGCODE_ACCESS_TOKEN` → `~/.config/pingcode/token.json` | 环境变量给了就跳过登录（临时/只读场景） |
| 当前项目 / 迭代 | `~/.config/pingcode/context.json` | `config context --project …` 设置 |
| 字典缓存 | `~/.config/pingcode/cache.json` | 项目/迭代/类型/状态/优先级/标签/成员，6 小时 |

**全局一套，不放进仓库**（`$PINGCODE_CONFIG_DIR` 可换目录）。凭据与令牌一律 0600 + 原子写，
`auth status` / `config show` 不回显 secret。

首次配置三步（详见 `references/auth.md`）：

```sh
# 1. 在后台建应用，拿 client_id / secret，登记回调 http://localhost:8765/callback
#    并按 references/auth.md 的表勾上 scope（最容易漏 pcp:read:pjm:configuration）
# 2. 写 ~/.config/pingcode/credentials.json（格式见上面的 reference），chmod 600
# 3. 授权
python3 scripts/pingcode.py auth login      # 打印授权链接，本机自动收 code
python3 scripts/pingcode.py whoami          # 确认「我」是谁
```

## 快速开始

```sh
P=skills/pingcode/scripts/pingcode.py

python3 $P config context --project 演示项目   # 设一次当前项目
python3 $P workitem mine --open-only                  # 我的未完成工作项
python3 $P workitem mine --type bug --open-only       # 我的未解决缺陷
python3 $P workitem show SCR-12                       # 详情（带描述与网页链接）
python3 $P workitem create --type bug --title "登录页 500" --assignee @me --dry-run
python3 $P workitem set-state SCR-12 已完成
python3 $P project progress
```

输出默认是紧凑表格（编号 / 标题 / 类型 / 状态 / 优先级 / 负责人 / 迭代 / 截止 / 链接）；
要原始 JSON 加 `--full`。

```text
编号    标题          类型  状态    优先级  负责人  截止             链接
------  ------------  ----  ------  ------  ------  --------------  -----------------------
SCR-12  登录页 500    缺陷  处理中  高      John    2026-09-30 00:00  https://…/d9WqLmTO
```

## 能力详解

| 能力 | 入口 | 说明 |
| --- | --- | --- |
| 身份 | `whoami` | `/v1/myself`，**只认用户令牌**；企业令牌会明确提示换模式 |
| 我的工作项 | `workitem mine [--type bug] [--open-only]` | 未完成 = `state.type != completed` |
| 检索 | `workitem list --project/--type/--state/--assignee/--sprint/--keywords/--identifier` | 全部条件可选；不写 `--project` 就用上下文 |
| 详情 | `workitem show <编号\|short_id\|id>` | 编号只有 GET 收，删除只收 id —— 解析由 CLI 做 |
| 建项目 | `project create --type --name --identifier` | 三者官方必填；**项目没有删除接口** |
| 改项目 | `project update --name/--description/--start/--end/--assignee/--state` | 「关闭项目」= 改项目状态 |
| 建工作项 | `workitem create --type epic\|feature\|story\|task\|bug\|issue …` | 描述、起止、负责人、优先级、父项、迭代、故事点、工时都支持 |
| 改工作项 | `workitem update <ref> …` | 只发改动的字段；`--description-file` 读长文本 |
| 改状态 | `workitem set-state <ref> <状态名>` | 先查该类型可用的状态；失败时把可用状态列出来 |
| 评论 | `workitem comment <ref> "…"` | |
| 删除 | `workitem delete <ref> --yes` | 不可逆，缺 `--yes` 拒绝执行 |
| 字典 | `list projects\|sprints\|types\|states\|priorities\|tags\|users` | 带 6 小时缓存，`--no-cache` 强制重拉 |
| 逃生口 | `api --list/--show/--method/--path/--param/--data` | 覆盖剩下约 460 个接口（测试管理 / 需求 / 工单 / 知识库 / DevOps …） |

细节见 `references/commands.md`（命令与流程）、`references/fields.md`（字段与状态语义）。

## 目录结构

```text
skills/pingcode/
├── SKILL.md                # 给 Agent 的规则（触发、红线、命令索引）
├── README.md               # 本文件
├── references/
│   ├── auth.md             # 建应用、两种授权、scope 表、令牌生命周期、排错
│   ├── commands.md         # 命令详解 + 自然语言 → 命令序列
│   ├── fields.md           # 字段、state.type 语义、分页、错误格式
│   └── api.md              # 端点表三层结构、怎么加接口、漂移检测
├── scripts/
│   ├── pingcode.py         # CLI 入口
│   ├── endpoints.py        # 【生成】官方 470 条接口表 + 来源指纹
│   ├── api_index.py        # 端点查询门（require / build / find / scopes）
│   ├── config.py           # 配置与本地状态（原子写 + 0600）
│   ├── client.py           # 传输：认证头、双头 429、配额、错误归一化
│   ├── auth.py             # 两种授权 + 自动刷新 + 本地回调收 code
│   ├── resolve.py          # 字典缓存 + 名字→ID（歧义列候选）
│   └── format.py           # 紧凑输出白名单 + 时间转换 + 表格
├── dev-tools/
│   └── gen_endpoints.py    # 从官方 api_data.json 生成 endpoints.py
├── tests/                  # 120 条：契约 / 传输 / 解析 / CLI
└── evals/
    └── evals.json          # 触发与行为评估
```

## 边界（不该用它的时候）

- 想读写本机文件或提交 git → 用 `git-dev-workflow`。
- 想把工作项整理成笔记 → 用 `obsidian-personal-knowledge-base`。
- 想画图 → 用 `excalidraw-diagram`。
- 想建/评审 skill → 用 `skill-builder`。
- 成员 / 权限 / 角色 / 部门 / 流水线管理：本 skill 没有类型化命令（官方有接口，走 `api` 逃生口）。
- 项目**不能删**：官方没有删除项目的接口。

## 验证

```sh
cd skills/pingcode
python3 -m unittest discover -s tests -v     # 134 条：全绿
python3 dev-tools/gen_endpoints.py --check   # 端点表与官方文档无漂移（离线时加 --input）
```

「通过」的意思是：契约测试证明用到的每个端点都在官方表里、那几条过期路径确实不存在；
传输层证明了 429 读公有云/私有部署两个响应头并按建议重试；解析层证明了歧义会报错而不是猜；
CLI 层证明了 dry-run 不发写、写操作打到正确端点且 body 里是解析后的真 id。

**真实租户实测（2026-09-13，企业令牌）**：已跑通只读（项目/类型/状态/迭代/优先级/成员/进度）
与写（建史诗→特性→用户故事→任务、建缺陷、改描述与截止日期、改状态、加评论、删）全链路。
下面这些原本标「未实测」的条目，已经用真实响应改成实测值。

## 已知限制与未验证项

| 项 | 状态 |
| --- | --- |
| 真实租户只读 + 写全链路（企业令牌） | ✅ 已实测 |
| **用户令牌模式**（浏览器授权） | ✅ 已实测：授权 → 本机回调收到 code → 换令牌落盘（30 天） |
| `refresh_token` 自动续期 | ✅ 已实测：换到新令牌，到期日顺延 30 天，`refresh_token` 保留 |
| `whoami` / `--assignee @me` 的前提 | ✅ 实测：应用数据范围里要有 `pcp:read:account:personal`；缺了 `/v1/myself` 返回 **403**（报错点名 scope，并给 `--assignee <真名>` 替代）。**加上之后现有令牌直接就能用**，`whoami` 与 `workitem mine --open-only` 均通 |
| `mine --type` 的类型名 | ✅ 实测：中文名（缺陷 / 任务 …）会被本地翻成枚举，不用先查项目字典；自定义类型仍要带项目上下文 |
| `state.type` 的完整取值集合 | ✅ 实测 **4 个**：`pending` / `in_progress` / `completed` / **`closed`**（已拒绝）。所以「已修复」仍算未完成，判据用黑名单 |
| 令牌响应里的 `expires_in` 是绝对时间戳还是秒数 | ✅ 实测是**绝对时间戳**（真实值 `1791902383`），不是常规 OAuth 的秒数。代码两种都接 |
| 成员名字段 | ✅ 实测成员的 `name` 是**手机号**，真名在 `display_name`。已按真名/邮箱/手机号都能匹配 |
| 编号能不能直接 `GET /v1/pjm/workitems/{编号}` | ✅ 实测**不能**：返回 **400 + code=100317**（不是 404）。已按编号形状分流 + 400 兜底 |
| `DELETE` 的行为 | ✅ 实测是**软删除**：删完 `show` 默认看不到（会提示加 `--all`），`--all` 能查到并标注「已被删除」 |
| 父工作项的类型约束 | ✅ 实测存在：这个项目里用户故事的父项**不能是史诗**，得是特性（400「父工作项的类型不正确」）。错误提示已写进去 |
| 编号会因失败的创建被消耗 | ✅ 实测：一次失败的创建用掉了 `DEMO-82`，所以编号会有空档 |
| `assignee_id` 是否接受 `me` 这类占位 | 仍未试；本 skill 一律解析成真实 id，不依赖服务端支持 |
| `POST /v1/pjm/workitems/search`（复杂过滤：日期、自定义属性） | 未封装，走 `api` 逃生口 |
| 批量改（`PATCH /v1/pjm/workitems`） | 未封装成子命令（官方只支持单属性 + 单值 + ≤100 个 id），走逃生口 |
| 附件 / 评论列表 / 关注人 / 关联 / 测试管理 / 需求 / 工单 | 未封装，走逃生口 |
| 成员 / 权限 / 部门 / DevOps 流水线 | 明确不做类型化命令 |
