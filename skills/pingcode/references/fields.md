# 字段、状态与分页

字段名都来自官方响应示例（`open.pingcode.com/api_data.json` 的 `success.examples`），不是猜的。
紧凑输出只保留下面这些列，`--full` 才出原始 JSON。

## 工作项

| 紧凑列 | 字段路径 | 说明 |
| --- | --- | --- |
| 编号 | `identifier` | 形如 `SCR-12`。**注意：只有 `GET` 收它**，`DELETE` 只收 `id` —— CLI 会先解析 |
| 标题 | `title` | |
| 类型 | `type` | 系统类型枚举：`epic` 史诗 / `feature` 特性 / `story` 用户故事 / `stage` 阶段 / `milestone` 里程碑 / `requirement` 需求 / `task` 任务 / `bug` 缺陷 / `issue` 事务；自定义类型是 24 位 id |
| 状态 | `state.name` / `state.type` | `state.type` 是语义值（见下），**判断完没完用它，不要用中文名** |
| 优先级 | `priority.name` | |
| 负责人 | `assignee.display_name` | |
| 迭代 | `sprint.name` | 只有 scrum / hybrid 项目有 |
| 项目 | `project.name` | |
| 截止 | `end_at` | 10 位秒级时间戳，显示时转成本地时间 |
| 链接 | `html_url` | 网页端地址，可以直接给人 |

创建/更新时用到的字段（`workitem create` / `update` 的 flag → 官方字段名）：

| flag | 官方字段 | 备注 |
| --- | --- | --- |
| `--project` | `project_id` | 必填（可用上下文代替） |
| `--type` | `type_id` | 必填；系统枚举或自定义类型 id |
| `--title` | `title` | 必填 |
| `--description` / `--description-file` | `description` | |
| `--start` / `--end` | `start_at` / `end_at` | 里程碑类型的 `start_at` 无效 |
| `--assignee` | `assignee_id` | 支持名字、id、`@me` |
| `--priority` | `priority_id` | |
| `--sprint` | `sprint_id` | 仅 scrum / hybrid |
| `--parent` | `parent_id` | 父工作项的类型要支持这种子类型 |
| `--state` | `state_id` | 必须同时满足该类型的「状态方案」与「状态流转」 |
| `--story-points` | `story_points` | ≥0 的整数或最多一位小数 |
| `--estimated-workload` / `--remaining-workload` | `estimated_workload` / `remaining_workload` | |
| （未封装） | `board_id` / `entry_id` / `swimlane_id` | 仅 kanban / hybrid；走逃生口 |
| （未封装） | `properties.{key}` | 自定义属性，需在该类型的属性方案里；走逃生口 |

## `state.type`：判断「完没完」用这个

官方状态对象是 `{id, name, type, color}`，其中 `type` 是语义值：

| `state.type` | 意思 |
| --- | --- |
| `pending` | 待处理 |
| `in_progress` | 处理中 |
| `completed` | 已完成 |

`workitem mine --open-only` 的判据就是 `state.type != completed`。

> **未实测**：完整取值集合以真实租户返回为准（官方示例只给了 `pending`）。
> 判据写的是「不等于 completed 就算未完成」—— 宁可多列，不要把活藏起来。

状态名每个项目、每种类型都不一样（`GET /v1/pjm/workitem/states?project_id=&workitem_type_id=`），
所以 `set-state` 一定先查表；名字对不上时会把该类型的可用状态列出来。

## 项目

| 紧凑列 | 字段 | 说明 |
| --- | --- | --- |
| 标识 | `identifier` | ≤15 位大写字母/数字/`_`/`-`，**全企业唯一** |
| 名称 | `name` | ≤255 |
| 类型 | `type` | `scrum` / `kanban` / `waterfall` / `hybrid` |
| 状态 | `state.name` | 项目自己的状态（和 `workitem_states` 不是一套） |
| 负责人 | `assignee.display_name` | |
| 开始 / 结束 | `start_at` / `end_at` | |
| ID | `id` | |

创建项目必填：`type`、`name`、`identifier`。`process_id`（项目流程）可选，
来自 `GET /v1/pjm/processes`（要 `pcp:read:pjm:configuration` scope）。

**项目没有删除接口。** 只有 `POST /v1/pjm/projects`、`PATCH /v1/pjm/projects/{id}`、
`POST /v1/pjm/projects/{id}/clone`、`PATCH /v1/pjm/project_states/{id}`。要「关闭项目」
就改项目状态。

## 迭代 / 类型 / 优先级 / 标签 / 成员

都在 `/v1/pjm/...` 下，且**大部分要带 `project_id`**（不同项目的配置是独立的）：

| 字典 | 端点 | 需要的上下文 |
| --- | --- | --- |
| 项目 | `GET /v1/pjm/projects` | — |
| 迭代 | `GET /v1/pjm/projects/{project_id}/sprints` | 项目 |
| 工作项类型 | `GET /v1/pjm/workitem/types?project_id=` | 项目 |
| 工作项状态 | `GET /v1/pjm/workitem/states?project_id=&workitem_type_id=` | 项目 + 类型 |
| 优先级 | `GET /v1/pjm/workitem/priorities?project_id=` | 项目 |
| 标签 | `GET /v1/pjm/workitem/tags?project_id=` | 项目 |
| 成员 | `GET /v1/directory/users` | — |
| 项目状态 | `GET /v1/pjm/project/states?project_id=` | 项目 |

这些进 6 小时的本地缓存；`--no-cache` 或 `config refresh` 可以强制重拉。

## 分页

- `page_size` 默认 30、**上限 100**；`page_index` **从 0 开始**。
- 响应：`{page_size, page_index, total, values: [...]}`。
- 不需要 `page_index` 的调用用 `GET /v1/pjm/workitems`；复杂组合、日期、自定义属性过滤要用
  `POST /v1/pjm/workitems/search`（类 MongoDB 的 `payload.filter`），本 skill 目前只封了前者
  （`workitem list` 的常用条件都走前者），复杂条件走 `api` 逃生口。

## 错误格式与限流

失败时 HTTP 状态码 + `{code, message}`。CLI 会把它翻译成人话并给出下一步：

| 状态 | CLI 会说什么 |
| --- | --- |
| 401 | 令牌无效/过期 → `auth login` |
| 403 | 权限不够，**并指出这个端点需要哪个 scope** |
| 404 | 对象不存在或路径不对 —— 路径以生成的端点表为准 |
| 429 | 官方建议等待秒数 + 剩余配额；已自动按建议重试（默认 3 次） |
| 5xx | 服务端错误，稍后重试 |

限流是**两层**：企业每分钟总数（免费版 200 / 付费版 500 + 成员数 × 20）+ 单接口每秒 30。
响应头 `X-RateLimit-Team-*` / `X-RateLimit-Burst-*` 会在写操作后顺带打出来。

## 时间

官方全部用 **10 位秒级时间戳**。CLI 收 `2026-09-20`、`2026-09-20 18:30` 或时间戳本身，
只写日期时按当天 00:00（本地时区）算。

> 一个官方文档上的坑：`/v1/auth/token` 响应示例里的 `expires_in` 是 `1577808000`，
> 那是**绝对时间戳**（2020-01-01），不是常规 OAuth 的「还有多少秒」。代码两种都接
> （大于 10^9 当绝对时间戳），并在 `auth status` 里把算出来的到期时间打出来 ——
> 这条属于**未实测**，等真实令牌到手第一次 `auth status` 就能确认。
