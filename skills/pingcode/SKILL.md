---
name: pingcode
description: >-
  Use when 在 PingCode 里查或改项目、工作项（史诗 / 特性 / 用户故事 / 任务 / 缺陷 / 事务）、迭代、
  看板：列我名下的待办与缺陷、按条件搜工作项、看详情、建项目、建或改工作项（描述、起止日期、
  负责人、优先级、父项、迭代、故事点）、改状态、加评论、删工作项；也用于排查 PingCode 的授权
  与限流问题（401/403/429）。命令形如 python3 scripts/pingcode.py …，端点和参数名以官方文档
  生成的端点表为准。
  Do NOT use for: 读写本机文件或 git 仓库（用 git-dev-workflow）、把工作项整理成 Obsidian 笔记
  （用 obsidian-personal-knowledge-base）、画图（用 diagram-authoring）、创建或评审 skill
  （用 skill-builder）；也不要用它做成员/权限/流水线管理，也不要凭记忆拼 API 路径。
---

# pingcode — 用命令行维护 PingCode 的项目与工作项

所有操作走一个入口：`python3 skills/pingcode/scripts/pingcode.py <子命令>`。

## 红线

| 红线 | 为什么 | 怎么守 |
| --- | --- | --- |
| **不猜 ID** | 同名迭代/项目选错不会报错，只会改错东西 | 名字一律交给 `resolve` 解析；歧义会**列候选**并中止 —— 这时要问用户，不要挑一个 |
| **不手拼 API 路径** | 官方 PJM 前缀是 `/v1/pjm/`（`workitems` 无下划线），凭印象写会 404 | 只用类型化子命令；逃生口 `api` 也先查生成的端点表 |
| **写操作先回显** | 建/改/删都会真的落到别人看得见的系统里 | 先跑一次 `--dry-run` 确认 body；删除必须 `--yes` |
| **不打印凭据与令牌** | `~/.config/pingcode/` 里的东西是凭证 | 状态只报「配了没配 / 还剩几天」；secret 一律不回显 |
| **改状态先查可用状态** | 官方要求 `state_id` 同时满足该类型的「状态方案」与「状态流转」 | `workitem set-state` 会自动查该类型的状态表；失败时把可用状态列出来 |
| **不缓存业务数据** | 缓存住工作项列表会得到「看着像真的」的过期答案 | 只有项目/迭代/类型/状态/优先级/标签/成员进缓存（6 小时） |

## 命令索引

| 想做什么 | 命令 |
| --- | --- |
| 我是谁（要用户令牌） | `whoami` |
| 我的未完成工作项 | `workitem mine --open-only` |
| 我的未解决缺陷 | `workitem mine --type bug --open-only` |
| 按条件搜工作项 | `workitem list --project X --type bug --state 新建 --keywords 登录` |
| 看一个工作项 | `workitem show SCR-12`（编号 / short_id / id 都收） |
| 建项目 | `project create --type scrum --name X --identifier DOC` |
| 建工作项 | `workitem create --type bug --title X [--description/--assignee/--start/--end/--parent/--sprint/--priority]` |
| 改字段 | `workitem update SCR-12 --description … --end 2026-09-30` |
| 改状态 | `workitem set-state SCR-12 已完成` |
| 加评论 | `workitem comment SCR-12 "…"` |
| 删工作项 | `workitem delete SCR-12 --yes`（不可逆） |
| 看项目进度 | `project progress --project X` |
| 列字典 | `list projects\|sprints\|types\|states\|priorities\|tags\|users` |
| 设当前项目 | `config context --project X`（之后可省 `--project`） |
| 授权 | `auth login [--mode user\|enterprise]`、`auth status`、`auth logout` |
| 覆盖没封装的接口 | `api --list 关键词` 找路径，再 `api --method/--path/--param/--data` |

## 工作方式

1. **先看现状再改**：改任何东西前先 `workitem show` / `workitem list`，别凭用户一句话就写。
2. **一次一个动作**：创建 → 回显编号；改状态 → 回显新状态。不要把一串写操作揉进一次调用。
3. **失败就翻译**：429 时把官方建议的等待秒数与剩余配额说出来；403 时指出缺哪个 scope；
   401 时说明要重新授权。**不要把原始 JSON 或状态码直接甩给用户。**
4. **拿不到就说拿不到**：本地没有凭据 / 没有令牌时，给出下一步命令（`auth login`），
   不要去猜环境里有什么。

## 细节在哪

| 主题 | 文件 |
| --- | --- |
| 建应用、两种授权模式、要勾哪些 scope、令牌会不会过期 | `skills/pingcode/references/auth.md` |
| 每条命令的参数、常用流程（自然语言 → 命令序列） | `skills/pingcode/references/commands.md` |
| 工作项/项目/迭代的字段、状态语义、分页与错误格式 | `skills/pingcode/references/fields.md` |
| 端点在代码里的位置、怎么加一个新接口、怎么发现文档漂移 | `skills/pingcode/references/api.md` |
| 给人看的完整说明（安装、配置、能力详解） | `skills/pingcode/README.md` |

## 本 skill 不做

- 不做成员 / 权限 / 角色 / 部门管理（官方有接口，但没有类型化命令 —— 需要时走 `api` 逃生口）。
- 不做 CI / 代码库 / 流水线（那是 DevOps 域）。
- **官方没有删除项目的接口**：关闭项目靠改项目状态（`project update --state`），要真删只能去网页端。
- 不缓存业务数据、不代做决策：状态流转不合规、必填缺失这类事，报错比猜好。
