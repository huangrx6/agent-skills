# 字段、状态与分页

字段名来自官方 **REST API V2** 响应示例（`open.pingcode.com/api_data.json` 的
`success.examples`，2026-10-14 快照），不是猜的。
紧凑输出只保留下面这些列，`--full` 才出原始 JSON。
命令层使用一套规范字段（编号字符串、`start_at` / `end_at` 时间戳、顶层工作量），
由 `scripts/compat.py` 在 V2 边界上转换。

## 工作项

| 紧凑列 | 字段路径 | 说明 |
| --- | --- | --- |
| 编号 | `whole_identifier`（回退 `identifier`） | V2 响应里 `identifier` 是数字（如 `5`），完整编号在 `whole_identifier`（如 `SCR-5`）。**它不是 id** —— `GET /{ref}` 与 `DELETE` 都不收完整编号，所以 CLI 会先解析成 id（见下面「编号不是 id」） |
| 标题 | `title` | |
| 类型 | `type` | V2 是对象 `{id, name, group}`；CLI 用 id 做逻辑、用 name 做展示。系统类型 id 是 24 位（不再是 `bug` 这种枚举），`--type bug` 由类型字典解析 |
| 状态 | `state.name` / `state.type` | `state.type` 是语义值（见下），**判断完没完用它，不要用中文名** |
| 优先级 | `priority.name` | |
| 负责人 | `assignee.display_name` | |
| 迭代 | `sprint.name` | 只有 scrum / hybrid 项目有 |
| 项目 | `project.name` | |
| 截止 | `due.date` | V2 是 `{date, with_time}` 对象；CLI 规范成 10 位秒级时间戳，显示时转本地时间 |
| 链接 | `html_url` | 网页端地址，可以直接给人 |

创建/更新时用到的字段（`workitem create` / `update` 的 flag → 官方字段名）：

| flag | 官方字段 | 备注 |
| --- | --- | --- |
| `--project` | `project_id` | 必填（可用上下文代替） |
| `--type` | `type_id` | 必填；系统枚举或自定义类型 id |
| `--title` | `title` | 必填 |
| `--description` / `--description-file` | `description` | |
| `--start` / `--end` | `start` / `due` | V2 是 `{date, with_time}` 对象；日期输入 `with_time=0`，带时分秒 `with_time=1`。里程碑类型的 `start` 无效 |
| `--assignee` | `assignee_id` | 支持名字、id、`@me` |
| `--priority` | `priority_id` | |
| `--sprint` | `sprint_id` | 仅 scrum / hybrid |
| `--parent` | `parent_id` | 父工作项的类型要支持这种子类型 |
| `--state` | `state_id` | 必须同时满足该类型的「状态方案」与「状态流转」 |
| `--story-points` | `properties.story_points` | 仅当该类型的属性方案包含 `story_points` 时可写（用户故事等）。任务类型没有这个属性，CLI 会先查 `workitem_properties` 并当场拒绝；V2 直接发会 400 `code=100355` |
| `--estimated-workload` / `--remaining-workload` | `properties.estimated_workload` / `properties.remaining_workload` | V2 放在 `properties` 里，命令层仍按顶层字段接收；写前查属性方案，不支持会拒绝 |
| （未封装） | `board_id` / `entry_id` / `swimlane_id` | 仅 kanban / hybrid；走逃生口 |
| （未封装） | `properties.{key}` | 自定义属性，需在该类型的属性方案里；走逃生口 |

## `state.type`：判断「完没完」用这个

官方状态对象是 `{id, name, type, color}`。`type` 是语义值，历史租户验证中包括以下值；以后可能扩展：

| `state.type` | 实测对应哪些状态名 | 算不算未完成 |
| --- | --- | --- |
| `pending` | 新提交 | ✅ 未完成 |
| `in_progress` | 处理中、**已修复**、重新打开、挂起 | ✅ 未完成 |
| `completed` | 已发布 | ❌ 已完成 |
| `closed` | 已拒绝 | ❌ 已完成（不再需要跟） |

两件事容易踩：

1. **`closed` 是第四个值**（已拒绝）。只看 `completed` 会把已拒绝的条目录进「未完成」。
2. **「已修复」的语义是 `in_progress`**，不是 `completed` —— 因为还没发布/验收。这只是该租户的配置，其他项目应读取返回的 `state.type`。

`workitem mine --open-only` 的判据是 `state.type ∉ {completed, closed}`（**黑名单**）：
以后官方再加语义值时，新值会被算进「未完成」—— 宁可多列，也不要把活藏起来。

状态名每个项目、每种类型都不一样（`GET /v2/pjm/workitem/workitem_states?project_id=&workitem_type_id=`），
所以 `set-state` 一定先查表；名字对不上时会把该类型的可用状态列出来。

`mine --type` 没有项目上下文，V2 的系统类型 id 又是 24 位，不能把 `bug` / `缺陷` 直接当
`type_id` 发；CLI 先取回「我名下」的条目，再按 `type.group` / `type.name` 本地过滤。

## 项目

| 紧凑列 | 字段 | 说明 |
| --- | --- | --- |
| 标识 | `identifier` | ≤15 位大写字母/数字/`_`/`-`，**全企业唯一** |
| 名称 | `name` | ≤255 |
| 类型 | `template_type` | `scrum` / `kanban` / `waterfall` / `hybrid`；CLI 的 `--type` 对外仍是这个参数 |
| 状态 | `state.name` | 项目自己的状态（和 `workitem_states` 不是一套） |
| 负责人 | `assignee.display_name` | |
| 开始 / 结束 | `start` / `due` | V2 是 `{date, with_time}` 对象 |
| ID | `id` | |

创建项目必填：`template_type`、`name`、`identifier`。可选 `template_id`（项目模板，来自
`GET /v2/pjm/project_templates`，要 `pcp:read:pjm:configuration` scope）；V1 的 `process_id`
在 V2 文档里已不存在。

**当前随附端点表没有项目删除接口。** 只有 `POST /v2/pjm/projects`、`PATCH /v2/pjm/projects/{id}`、
`POST /v2/pjm/projects/{id}/clone`、`PATCH /v2/pjm/project_states/{id}`。用户明确要求关闭项目时，可修改其项目状态。

## 迭代 / 类型 / 优先级 / 标签 / 成员

都在 `/v2/pjm/...` 下，且**大部分要带 `project_id`**（不同项目的配置是独立的）：

| 字典 | 端点 | 需要的上下文 |
| --- | --- | --- |
| 项目 | `GET /v2/pjm/projects` | — |
| 迭代 | `GET /v2/pjm/sprints?project_id=` | 项目 |
| 工作项类型 | `GET /v2/pjm/workitem/workitem_types?project_id=` | 项目 |
| 工作项状态 | `GET /v2/pjm/workitem/workitem_states?project_id=&workitem_type_id=` | 项目 + 类型 |
| 优先级 | `GET /v2/pjm/workitem/workitem_priorities?project_id=` | 项目 |
| 标签 | `GET /v2/pjm/workitem/workitem_tags?project_id=` | 项目 |
| 工作项属性方案 | `GET /v2/pjm/workitem/workitem_properties?project_id=&workitem_type_id=` | 项目 + 类型 |
| 成员 | `GET /v2/directory/users` | — |
| 项目状态 | `GET /v2/pjm/project/project_states?project_id=` | 项目 |
| 项目模板 | `GET /v2/pjm/project_templates` | — |

这些进 6 小时的本地缓存；`--no-cache` 或 `config refresh` 可以强制重拉。

成员展示名优先读 `display_name`；`name` 可能是用户名或手机号。
所以 `--assignee` 支持真名 / 用户名（手机号）/ 邮箱 / id 四种写法。

## 编号不是 id

实测三条关于编号的硬事实（都会影响怎么写调用）：

1. `GET /v2/pjm/workitems/{ref}` **只收 id 或 short_id，不收完整编号**；给完整编号返回的是
   **400 + code=100317「工作项资源不存在」**，不是 404（V1 实测；V2 待复核）。
2. `DELETE /v2/pjm/workitems/{id}` 只收 id。
3. **失败也会消耗编号**：一次父项类型不对的创建用掉了 `DEMO-82`，所以编号有空档。

V2 列表接口的 `identifier` 查询参数在文档里是 **Number**；CLI 把 `DEMO-80` 拆成
`identifier=80` + `project_id`（项目标识 `DEMO` 由项目字典解析）。其它先直取，
400/404 再兜底；删除前先把编号解析成 id。

## 删除是软删除

`DELETE` 之后条目还在（官方把它标为已删除）：

- `workitem show <编号>` 默认**看不到**，并提示「它可能已被删除，加 `--all` 看已删除的」；
- `workitem show <编号> --all` 能看到，并标一句「（注意：这条已被删除）」。

## 父工作项的**类型**有约束

实测：某次验证的项目里用户故事的父项**不能是史诗**，得是特性（史诗 → 特性 → 用户故事 → 任务）。
越级挂会返回 **400「父工作项的类型不正确」**。这是项目的类型配置，CLI 不替你猜 ——
报错提示里已写明这一条。

## 分页

- `page_size` 默认 30、**上限 100**；`page_index` **从 0 开始**。
- 响应：`{page_size, page_index, total, values: [...]}`。
- 不需要 `page_index` 的调用用 `GET /v2/pjm/workitems`；复杂组合、日期、自定义属性过滤要用
  `POST /v2/pjm/workitems/search`（类 MongoDB 的 `payload.filter`），CLI 分别提供 `workitem list` 与 `workitem search`，常用搜索参数和 `--filter` 见 commands.md。

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

官方全部用 **10 位秒级时间戳**；V2 的请求/响应把日期包成 `{date, with_time}`，
CLI 在边界上转换。CLI 收 `2026-09-20`、`2026-09-20 18:30` 或时间戳本身，
只写日期时按当天 00:00（本地时区）算；带时分秒时 V2 `with_time=1`。

`expires_in` 兼容相对秒数和绝对时间戳（大于等于 10^9 按绝对时间处理）。
缺少有效值时，访问令牌按 30 天回退；refresh_token 的存在不会延长访问令牌寿命。
实际可用性仍由服务端判断，401 时按授权流程处理。
