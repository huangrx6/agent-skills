---
name: pingcode
description: >-
  Use when querying or updating PingCode projects and work items, including tasks, bugs, sprints,
  statuses, assignees, comments, and attachments. 中文：PingCode 里查待办、查缺陷、建任务、
  改状态、看迭代或排查授权。Use for PingCode work tracking and authentication or API errors. Do NOT use for local Git work or administration of members,
  permissions, or CI pipelines.
---

# PingCode 项目与工作项

入口为本 skill 的 `scripts/pingcode.py`：`python3 <skill路径>/scripts/pingcode.py <子命令>`。
使用类型化命令和生成端点表，不凭记忆拼 API 路径。首次配置或授权失败时读
[auth.md](references/auth.md)。

## 操作原则

- 只执行用户请求的范围。编号先解析成真实 ID；名字解析有歧义时列候选，请用户指定，不能取首项。
- 更新或删除前核对目标及当前字段。类型化 update/set-state/delete 命令已读取目标，
  不必为了流程固定再查一遍；需要向用户消除歧义时才单独 `show`。
- 用户已明确授权且参数齐全时直接执行。复杂多字段或批量操作可用 `--dry-run` 检查计划；
  dry-run 仍允许为解析 ID 发起只读请求。删除和树形创建要求 `--yes`，这是 CLI 执行开关，
  不要求重复获取已有授权。
- 评论会对外发送信息，仅在用户明确要求评论时执行；上传附件也须属于请求范围。
- 写操作失败或超时后先检查是否已生效，再决定重试，避免重复创建。批量/树形操作报告已完成部分，
  不宣称自动回滚或可直接整棵重跑。
- 凭据与令牌不回显；状态只用 `auth status` / `config show`，不要读取或粘贴凭据文件内容。
- 工作项不缓存；字典默认缓存 6 小时。目标刚改名、新建或状态配置变化时用 `--no-cache`。

## 常用入口

| 任务 | 命令 |
| --- | --- |
| 我的未完成任务 / 缺陷 | `workitem mine --open-only [--type bug]` |
| 条件列表 / 结构化搜索 | `workitem list …` / `workitem search …` |
| 详情 | `workitem show SCR-12 [--all]` |
| 创建 / 更新 / 改状态 | `workitem create …` / `workitem update SCR-12 …` / `workitem set-state SCR-12 状态` |
| 树形创建 / 单字段批量更新 | `workitem create-plan --file plan.json [--yes]` / `workitem bulk-update …` |
| 评论 / 附件 | `workitem comment/comments/attachments/attach/attach-code/attach-remove …` |
| 删除工作项 | `workitem delete SCR-12 --yes` |
| 项目列表 / 详情 / 进度 / 创建 / 更新 | `project list/show/progress/create/update …` |
| 字典 / 默认项目 | `list projects\|sprints\|types\|states\|priorities\|tags\|users` / `config context --project X` |
| 授权与诊断 | `auth login/status/logout` / `whoami` / `config show` |

“未完成”按 `state.type` 排除 `completed` 和 `closed`，不能按中文状态名猜。
状态表只约束可选 ID，具体状态流转仍由服务端校验；企业令牌不能识别 `@me`。

## 按需查阅

- [commands.md](references/commands.md)：参数、搜索语法、树形计划与批量操作。
- [fields.md](references/fields.md)：字段映射、状态、编号解析和分页。
- [auth.md](references/auth.md)：配置路径、两种令牌与错误处理。
- [api.md](references/api.md)：端点表、参数来源、维护和通用 API。
- [README.md](README.md)：本地运行与测试。

通用 `api` 用于范围内未封装的接口；表中存在端点不代表获得了执行权限。
`--force` 只跳过端点存在性校验，不能替代官方契约或扩大到成员、权限、部门、DevOps 管理。
当前随附端点表没有项目删除接口；不要把“删除项目”替换成改状态或删除工作项。
