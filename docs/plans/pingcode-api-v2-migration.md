# PingCode REST API V2 迁移清单

状态：**代码迁移完成，真实租户核心链路已验证**（分支 `feat/pingcode-api-v2`）
范围：`skills/pingcode` 的项目 / 工作项 / 评论 / 附件 / 字典命令。
不在本次范围：成员权限管理、测试管理、知识库、工单、发布、DevOps。

## 1. 事实与判断

| 项 | 迁移前 | 官方当前 |
| --- | --- | --- |
| 文档标题 | REST API V1 | **REST API V2** |
| 接口数 | 470 | 460（582 条原始条目） |
| 路径前缀 | `/v1/...` | `/v2/...` |
| 快照 | 2026-09-13 | 2026-10-14 |

`dev-tools/gen_endpoints.py --check` 在迁移前报 593 处漂移。V1 端点目前仍能响应
（未授权请求返回 400 “缺 access_token”，不是 404），所以迁移不是救火，而是把 skill
从“无文档背书的旧契约”拉回官方当前契约。

## 2. 路径清单

| 能力 | V1 | V2 | 变化 |
| --- | --- | --- | --- |
| 获取令牌 | `GET /v1/auth/token` | `GET /v2/auth/token` | 前缀 |
| 我是谁 | `GET /v1/myself` | `GET /v2/myself` | 前缀 |
| 成员 | `GET /v1/directory/users` | `GET /v2/directory/users` | 前缀 |
| 项目列表 / 创建 | `/v1/pjm/projects` | `/v2/pjm/projects` | GET 的 `type` → `template_type` |
| 项目详情 / 更新 | `/v1/pjm/projects/{id}` | `/v2/pjm/projects/{id}` | 请求/响应字段变化 |
| 项目进度 | `/v1/pjm/projects/{id}/progress` | `/v2/pjm/projects/{id}/progress` | 前缀 |
| 项目状态 | `/v1/pjm/project/states?project_id=` | `/v2/pjm/project/project_states?project_id=` | 路径重命名 |
| 项目流程 | `GET /v1/pjm/processes` | `GET /v2/pjm/project_templates` | 语义改名（流程 → 模板） |
| 迭代 | `GET /v1/pjm/projects/{id}/sprints` | `GET /v2/pjm/sprints?project_id={id}` | 路径参数变查询参数 |
| 工作项类型 | `/v1/pjm/workitem/types?project_id=` | `/v2/pjm/workitem/workitem_types?project_id=` | 路径重命名 |
| 工作项状态 | `/v1/pjm/workitem/states?project_id=&workitem_type_id=` | `/v2/pjm/workitem/workitem_states?...` | 路径重命名 |
| 优先级 | `/v1/pjm/workitem/priorities?project_id=` | `/v2/pjm/workitem/workitem_priorities?...` | 路径重命名 |
| 标签 | `/v1/pjm/workitem/tags?project_id=` | `/v2/pjm/workitem/workitem_tags?...` | 路径重命名 |
| 工作项列表 / 创建 | `/v1/pjm/workitems` | `/v2/pjm/workitems` | 列表 `identifier` 变数字；创建字段变化 |
| 工作项详情 / 更新 / 删除 | `/v1/pjm/workitems/{id}` | `/v2/pjm/workitems/{id}` | 更新字段变化 |
| 结构化搜索 | `POST /v1/pjm/workitems/search` | `POST /v2/pjm/workitems/search` | `{mode, payload}` 不变 |
| 批量改 | `PATCH /v1/pjm/workitems` | `POST /v2/pjm/workitems/bulk/set` | **方法和路径都变** |
| 评论 | `/v1/comments` | `/v2/comments` | 前缀 |
| 附件列表 / 上传 | `/v1/attachments` | `/v2/attachments` | 前缀；两个 POST 变体形状不变 |
| 单个附件删除 | `/v1/attachments/{id}?principal_type=&principal_id=` | `/v2/attachments/{id}?...` | 前缀 |

## 3. 字段映射

### 3.1 工作项响应

| V2 字段 | 内部规范字段 | 说明 |
| --- | --- | --- |
| `whole_identifier` | `identifier` | V2 列表示例 `identifier: 5` + `whole_identifier: "SCR-5"`；另有示例 `identifier: "PLM-001"`。两者都要兼容。 |
| `type` 对象 `{id,name,group}` | `type`（id）+ `type_name` / `type_group` | 逻辑用 id，显示用 name（V2 系统类型 id 是 24 位，不再能靠 `bug` 枚举映射中文）。 |
| `start` / `due` `{date,with_time}` | `start_at` / `end_at` | 显示和逻辑统一用时间戳；`with_time` 只在写回时使用。 |
| `properties.story_points` 等 | 顶层 `story_points` 等 | 响应里工作量字段在 `properties` 内；内部仍保留顶层，减少命令层改动。 |
| `state` / `priority` / `assignee` / `sprint` / `project` | 不变 | `state.type` 仍存在（示例 `pending`）。 |
| `is_deleted` / `is_archived` | 不变 | `--all` 仍用这两个参数。 |

### 3.2 工作项请求

| 内部字段 | V2 字段 | 说明 |
| --- | --- | --- |
| `start_at` | `start` `{date, with_time}` | `with_time`：日期输入 0，带时分秒 1；时间戳输入默认 0。 |
| `end_at` | `due` `{date, with_time}` | 同上。 |
| `story_points` | `properties.story_points` | V2 创建字段表没有顶层 `story_points`。 |
| `estimated_workload` | `properties.estimated_workload` | 同上。 |
| `remaining_workload` | `properties.remaining_workload` | 同上。 |
| `type_id` / `project_id` / `title` / `description` / `assignee_id` / `priority_id` / `sprint_id` / `parent_id` / `state_id` | 不变 | 必填约束不变。 |

### 3.3 项目请求 / 响应

| 内部字段 | V2 字段 | 说明 |
| --- | --- | --- |
| `type` | `template_type` | 创建必填，列表过滤也用它。 |
| `start_at` / `end_at` | `start` / `due` `{date, with_time}` | 与工作项相同的对象形状。 |
| `process_id` | `template_id` | CLI 当前没有暴露 process/template 参数；`list processes` 改为列 `project_templates`。 |
| `name` / `identifier` / `description` / `assignee_id` / `state_id` | 不变 | `state_id` 仍来自项目状态表。 |

### 3.4 批量改

V2：`POST /v2/pjm/workitems/bulk/set`

```json
{
  "ids": ["..."],
  "property_name": "state_id",
  "property_value": "..."
}
```

- `property_name` 支持内置字段和 `properties.prop_a`。
- 日期字段应传 `start` / `due`，值为 `{date, with_time}`。
- 工作量字段应传 `properties.story_points` 等。
- 仍然一次只改一个属性、最多 100 个 id。

## 4. 行为差异与风险点

### 4.1 编号解析

V1 直接把 `SCR-12` 传给列表的 `identifier` 查询。V2 文档把 `identifier` 标为 Number，
同时响应里给了 `whole_identifier`。迁移方案：

1. 形状像 `PREFIX-123`：拆成项目标识 + 数字；
2. 用项目字典把 `PREFIX` 解析成 `project_id`；
3. 查询 `GET /v2/pjm/workitems?identifier=123&project_id=...`；
4. 解析不到项目时给出可执行提示，不静默退回注定失败的字符串查询。

仍需真实租户确认 V2 是否也接受 `identifier=SCR-12`；如果接受，可保留一条更简单的回退。

### 4.2 `mine --type`

V1 的 `mine --type bug` 直接把 `bug` 当 `type_id` 发。V2 的系统类型 id 是 24 位
（类型字典示例：用户故事 `630da...`、缺陷 `630da...`），没有项目上下文就无法解析。

方案 A（推荐）：V2 下不把 `bug` 当 `type_id` 发，先取回“我名下”的条目，再按
`type.group` / `type.name` 本地过滤。
方案 B：给 `mine` 增加 `--project`，再走类型字典解析。

### 4.3 写字段

V2 的 `start` / `due` 是对象，`story_points` 等进入 `properties`。如果只改前缀，
创建出来的日期和工作量会静默丢失或 400，所以必须有请求体适配层。

### 4.4 附件代码段

V2 文档仍把 `comment_id` 标为可选；V1 真实租户实测不带会 400 `code=100039`。
迁移时先保留“代码段必须带 `--comment`”的保守约束，等真实租户复核后再决定是否放宽。

### 4.5 逃生口

V2 表生成后，`api --show/--list` 只认 V2 路径。V1 路径会被拦下并给候选；这是预期行为，
不再用 `--force` 当版本兼容开关。

## 5. 真实租户验证结果（2026-10-22）

已跑通：令牌刷新 → `whoami`；项目列表/详情/进度、`template_type` 过滤；类型/状态/优先级/标签/
迭代/项目状态/项目模板/成员字典；工作项 list/show/mine/search；按编号查询（`ASKILL-70/71`）；
创建任务与用户故事、更新故事点、改状态；批量改标题（`bulk/set`）；文件附件上传/列表/删除；
删除与 `--all` 软删除确认。两条一次性测试数据已删除。

| 待验证项 | 结果 |
| --- | --- |
| 当前租户支持 `/v2` | ✅ |
| `identifier` 查询收数字；`GET /{ref}` 仍只收 id/short_id | ✅（CLI 走数字 + project_id；未再用完整编号直取） |
| `start` / `due` 的 `with_time` | ✅ 带时分秒写入 `with_time=1`，日期写入 `0` |
| `properties.story_points` | ✅ 用户故事可写；❌ 任务类型没有该属性，更新返回 400 `code=100355` |
| `mine --type` 本地过滤 | ⚠ 路径已跑通（无匹配数据，结果为空） |
| `state.type` 四个值 | ✅ `pending` / `in_progress` / `completed` / `closed` |
| `bulk/set` | ✅ 改标题实写；改状态只做 dry-run |
| 附件代码段强制 `comment_id` | ❌ 未测（需要先发评论，避免未经要求的外发） |
| 项目创建/更新的真实写 | ❌ 只做 dry-run（避免改动正式项目） |
| 错误码 | ✅ 100355；软删除；100317 未再触发 |

## 6. 实施与验收

- [x] 生成 V2 端点表，`gen_endpoints.py --check` 退出 0。
- [x] 所有命令改用 V2 路径；代码里不再出现可执行的 `/v1/` 常量。
- [x] 工作项/项目响应规范化：编号、类型、日期、properties。
- [x] 请求体适配：`start`/`due`、`template_type`、`properties.*`、`bulk/set`。
- [x] 单测：现有测试迁移到 V2，新增编号/日期/类型/批量/`mine --type` 覆盖。
- [x] 真实租户只读冒烟 + 可丢弃写操作；记录实际响应。
- [x] 文档：`fields.md`、`commands.md`、`api.md`、`auth.md`、README、evals。

当前结果：459 个 V2 接口；235 个单元测试通过；`gen_endpoints.py --check` 无漂移；
`validate_skill.py` / `check_pointers.py` / `preflight.py` 通过。
真实租户核心链路已跑通；剩余边缘项见上一节。

验收标准：`gen_endpoints.py --check` 绿；单测绿；真实租户只读命令返回正确数据；
创建/更新/改状态/删除在测试项目上成功；`--full` 能看出 V2 原始字段。

## 7. 合并策略

- 本分支只做 V2。V1 代码保留在 `main` 与 git 历史，不维护双版本分支逻辑。
- 真实租户验证通过后再合并；若租户暂不支持 V2，保留 `main`，另开版本策略讨论，
  不要在没有验证的情况下把默认路径切到 V2。
- 合并后更新 `skills-lock.json` 哈希、根 README 的能力描述和 evals。
