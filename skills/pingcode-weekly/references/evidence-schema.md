# 证据 JSON（version 1）

`collect` 的输出。它是周报的审计底稿；`weekly` 只读它，不重新访问 PingCode。
所有时间使用带时区的 ISO 8601。

## 顶层

```json
{
  "version": 1,
  "generated_at": "2026-10-23T12:00:00+08:00",
  "window": {
    "since": "2026-10-19T00:00:00+08:00",
    "until": "2026-10-25T23:59:59.999999+08:00",
    "label": "2026-10-19 ~ 2026-10-25"
  },
  "projects": [],
  "quality": {}
}
```

## 项目

```json
{
  "id": "project-id",
  "identifier": "PROJ",
  "name": "示例项目 A",
  "types": {
    "requirement": {"id": "type-story", "name": "用户故事", "group": "requirement"},
    "defect": {"id": "type-bug", "name": "缺陷", "group": "bug"}
  },
  "sprints": {
    "current": {"id": "s1", "name": "2026-W43", "status": "in_progress"},
    "next": {"id": "s2", "name": "2026-W44", "status": "pending"}
  },
  "requirements": [],
  "bugs": [],
  "quality": {}
}
```

采集失败的项目保留 `error`，不伪造 `types`/`sprints`：

```json
{"name": "另一个项目", "error": "没找到项目 …", "requirements": [], "bugs": []}
```

## 需求 / 缺陷条目

```json
{
  "id": "PROJ-23",
  "title": "文档解析 MCP 接口服务封装",
  "kind": "requirement",
  "type": "用户故事",
  "state": "进行中",
  "state_type": "in_progress",
  "assignee": "示例负责人",
  "assignee_id": "user-id",
  "priority": "普通",
  "severity": null,
  "summary": "封装四个 MCP 工具入口，补调用说明与联调。",
  "summary_source": "custom",
  "created_at": "2026-10-20T10:00:00+08:00",
  "updated_at": "2026-10-22T18:00:00+08:00",
  "completed_at": null,
  "sprint": "2026-W43",
  "parent": "PROJ-22",
  "url": "https://…/workitems/…",
  "open": true,
  "created_in_window": true,
  "updated_in_window": true,
  "completed_in_window": false,
  "planned": false,
  "age_days": 3
}
```

- `kind`：`requirement` 或 `bug`。
- `state_type`：PingCode 的状态语义；缺失时为空并进入 `unmapped_state`。
- `open`：不是 `completed`/`closed`；只有缺陷用它判断“未关闭”。
- `planned`：属于下一迭代。
- `summary_source`：`custom` / `description` / `title`。
- `age_days`：从创建日到窗口终点；只对缺陷有意义。

## quality

单个项目：

```json
{
  "requirements_total": 8,
  "bugs_total": 3,
  "completed_requirements": 2,
  "completed_bugs": 1,
  "in_progress_requirements": 3,
  "open_bugs": 2,
  "new_requirements": 4,
  "new_bugs": 2,
  "planned_requirements": 1,
  "planned_bugs": 1,
  "missing_assignee": ["PROJ-12"],
  "missing_completion_time": ["PROJ-18"],
  "missing_severity": ["PROJ-21"],
  "unmapped_state": [],
  "summary_custom": 2,
  "summary_description": 6,
  "summary_title": 0,
  "missing_next_week": false,
  "empty": false,
  "truncated": false,
  "warnings": []
}
```

顶层 `quality` 是跨项目汇总，含 `projects`、需求/缺陷计数、`empty` 和 `errors`。

顶层筛选后会带 `scope`：

```json
{"scope": {"assignees": ["示例负责人"]}}
```

`assignee_id` 用于同名负责人消歧；没有 ID 时退回显示名。`--mine` / `--assignee`
过滤后，项目 `quality` 会按过滤后的条目重算，不沿用全量统计。

## 边界

- 不包含附件或评论。
- 不包含令牌、cookie、客户端 secret 或本机绝对配置路径。
- `generated_at` 每次运行会变化；同一窗口的其余字段来自同一批 PingCode 数据。
- `truncated=true` 时不能把报告当全量历史。
