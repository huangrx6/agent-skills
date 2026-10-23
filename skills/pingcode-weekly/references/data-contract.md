# PingCode 数据合同

本 skill 只读 PingCode。周报质量取决于 PingCode 里录入了什么；没有录入的内容不会
出现在周报里。

## 认证与 scope

最小读取 scope：

| 用途 | scope |
| --- | --- |
| 项目 | `pcp:read:pjm:project` |
| 工作项、类型、状态 | `pcp:read:pjm:workitem` |
| 迭代 | `pcp:read:pjm:sprint` |

如果令牌只通过 `PINGCODE_ACCESS_TOKEN` 提供，至少要有以上读取权限。
用户 OAuth 还需要在 PingCode 企业后台创建应用并登记回调地址。

凭据文件默认：

```json
{
  "host": "open.pingcode.com",
  "auth_mode": "user",
  "client_id": "…",
  "client_secret": "…",
  "redirect_uri": "http://localhost:8765/callback"
}
```

路径：`~/.agent-skills/config/pingcode/credentials.json`；令牌缓存同目录。
不把 secret/token 写进证据或周报。

## 输出位置

`weekly`、`collect`、`render` 默认统一写到：

- macOS/Linux：`~/Downloads/pingcode-weekly/`
- Windows：`%USERPROFILE%\Downloads\pingcode-weekly\`

文件名由项目/工作区标签、窗口和类型组成，例如
`PROJ-2026-W43-weekly.md`、`PROJ-2026-W43-evidence.json`；重渲染为
`PROJ-2026-W43-rendered-weekly.md`。
`--out` 指定完整路径；`--output-dir`、`PINGCODE_WEEKLY_OUTPUT_DIR` 或
`[workspace] output_dir` 改目录；`--stdout` 不落盘。
写入使用临时文件加原子替换，不留下半个文件。

## 项目与类型

每个项目必须能解析出：

- 一个“需求”类型（`requirement_types`）
- 一个“缺陷”类型（`defect_types`）

PingCode 模板可能把需求叫“需求”“用户故事”或 `story`；把缺陷叫“缺陷”或 `bug`。
配置可以写多个候选，按顺序匹配；匹配到多个会报错并列出候选。

如果项目没有缺陷类型，`check` 会失败。先在 PingCode 启用缺陷类型，或改配置映射。

## 需求字段

| 字段 | 用途 | 缺失时 |
| --- | --- | --- |
| 编号 | 周报引用 | 无法生成该条，报错 |
| 标题 | 条目名称 | 不进入报告 |
| 状态 | 完成/进行中/待开始 | 进入“状态未映射”缺口 |
| 负责人 / 负责人 ID | 报告责任人、按人筛选 | 未完成/未关闭项进入“缺负责人”缺口 |
| 完成时间 | 判断本周完成 | 读 history；仍无则进入“完成项缺完成时间” |
| 创建/更新时间 | 判断本周新增/变更 | 该维度不纳入 |
| 迭代 | 当前/下周计划 | 下周计划可能为空 |
| 描述/摘要字段 | 周报叙事 | 退回标题 |

## 缺陷字段

除需求字段外：

| 字段 | 用途 | 缺失时 |
| --- | --- | --- |
| 严重程度 | 缺陷排序 | 显示“未分级”，进入缺口 |
| 优先级 | 辅助排序 | 显示“未设置” |
| 关闭/拒绝状态 | 区分修复与拒绝 | `closed` 默认不算修复 |
| 流转历史 | 补完成时间/重新打开 | 无历史时只保留缺口 |

建议在 PingCode 里使用一个自定义字段 **“周报摘要”**，写一到两句业务结果。
没有该字段时，使用描述第一段；再没有就用标题。`check` 会提示没有找到自定义摘要字段。

## 按人筛选

`--mine` 用当前登录人的用户 ID/姓名过滤；`--assignee NAME` 可重复，也接受逗号分隔，
匹配负责人 ID 或显示名。过滤后会重算需求和缺陷计数、完成数、缺口，不会把所有人的
统计混在一起。

`collect` 的证据会带：

```json
{
  "scope": {"assignees": ["张三"]},
  "projects": [
    {"requirements": [{"assignee": "张三", "assignee_id": "user-id"}]}
  ]
}
```

`--per-assignee` 只在 `weekly` 使用：按负责人拆成多个文件，文件名形如
`PROJ-2026-W43-张三-weekly.md`。没有匹配负责人时失败；确实要空报告才加
`--allow-empty`。

`--month YYYY-MM` 是自然月窗口，适合月底把所有人合并；不能和 `--week` /
`--since` / `--until` 同时使用。

## 状态口径

- `state_type=completed`：完成；完成时间必须在窗口内才计入“本周完成”。
- `state_type=in_progress`：进行中。
- `state_type=pending`：待开始；只有进入下一迭代才进入“下周计划”。
- `state_type=closed`：关闭/拒绝；默认不算完成，避免把“已拒绝”写成修复。

如果项目的“已关闭”确实代表完成，在工作区里配置：

```toml
[[projects]]
# …
done_state_types = ["completed", "closed"]
```

默认只把 `completed` 当完成；`closed` 仍视为关闭/拒绝，避免把“已拒绝”写成修复。

## 下周计划

“下周计划”只来自 PingCode：

1. 找到窗口结束后的下一个迭代；
2. 读取该迭代下的需求和缺陷；
3. 没有下一迭代或迭代为空时，报告写“下周计划未在 PingCode 录入”。

不从历史提交、标题关键词或外部文档推断计划。

## `check` 会报告什么

```text
窗口：2026-10-19 ~ 2026-10-25
[OK] 示例项目 A：需求 8 条，缺陷 3 条
  - 缺负责人：PROJ-12
  - 缺陷缺严重程度：PROJ-21
  - 下周计划：没有找到下一迭代或计划项
```

`check` 返回 2 表示不能生成完整周报：项目/类型不可用、没有记录、或严格模式下
某个项目失败。缺字段本身会列在报告缺口里，不阻止其他项目生成。
