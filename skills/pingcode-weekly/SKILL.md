---
name: pingcode-weekly
description: >-
  Use when 从 PingCode 的需求和缺陷生成项目周报，或检查周报所需数据是否已经录入。
  中文触发：PingCode 周报、按人周报、月度总结、这周需求进展、缺陷清单、项目周报、下周计划、周报数据检查。
  只读 PingCode；工作项必须先在 PingCode 录入。
  Do NOT use for: 非 PingCode 数据源的周报或 PingCode 写入。
---

# pingcode-weekly：PingCode 周报

从 PingCode 的**需求**和**缺陷**生成项目周报。PingCode 是唯一事实源：
没有录入的工作项不会出现在周报里。

## 先确认

- PingCode 项目（名称、标识或 ID）。
- 项目里有明确的“需求”和“缺陷”工作项类型；模板名称不同时在配置里映射。
- 时间窗：`--week 2026-W43`、`--month 2026-10`，或 `--since/--until`。
- 当前迭代/下一迭代是否已经在 PingCode 建好；没有下一迭代时，“下周计划”会显示缺口。

## 认证

第一次使用先授权：

```sh
python3 scripts/pingcode_weekly.py auth login
# 企业令牌
python3 scripts/pingcode_weekly.py auth login --mode enterprise
# 用户 OAuth：浏览器授权后把 code 带回
python3 scripts/pingcode_weekly.py auth login --code <code>
```

`auth status` 查看令牌状态。也支持直接给令牌：

```sh
export PINGCODE_ACCESS_TOKEN=...
export PINGCODE_HOST=open.pingcode.com
```

令牌缓存默认在 `~/.agent-skills/config/pingcode/token.json`，凭据文件同目录；
详细格式和 scope 见
[PingCode 数据合同](references/data-contract.md)。本 skill 内置只读客户端。

## 快速使用

```sh
# 单项目：默认写到下载目录，命令会回显完整路径
python3 scripts/pingcode_weekly.py check --project PROJ --week 2026-W43
python3 scripts/pingcode_weekly.py weekly --project PROJ --week 2026-W43

# 只看不落盘
python3 scripts/pingcode_weekly.py weekly --project PROJ --week 2026-W43 --stdout

# 多项目
python3 scripts/pingcode_weekly.py check --workspace weekly.toml --week 2026-W43
python3 scripts/pingcode_weekly.py weekly --workspace weekly.toml --week 2026-W43

# 先留证据再渲染
python3 scripts/pingcode_weekly.py collect --project PROJ --week 2026-W43
python3 scripts/pingcode_weekly.py render --input <collect 的输出路径> --template custom.toml
```

`check` 不生成周报，只报告项目、类型、需求/缺陷数量、缺口和下一迭代。
`weekly` 发现没有任何 PingCode 记录时默认退出 2，并提示先录入；确实要空周报才加
`--allow-empty`。`collect` 只读，可重复运行。按人筛选见下面的“按人总结”。

## 输出位置

`weekly`、`collect`、`render` 默认写到同一个下载目录：

- macOS/Linux：`~/Downloads/pingcode-weekly/`
- Windows：`%USERPROFILE%\Downloads\pingcode-weekly\`

文件名：

- 周报：`<项目或工作区>-<窗口>-weekly.md`
- 证据：`<项目或工作区>-<窗口>-evidence.json`
- 重渲染：`<证据文件名>-rendered-weekly.md`

`check`、`auth`、`projects` 只打印，不写文件。`--stdout` 不落盘；`--out` 指定完整路径；
`--output-dir`、环境变量 `PINGCODE_WEEKLY_OUTPUT_DIR` 或工作区 `[workspace] output_dir`
可以换目录。写入使用临时文件加原子替换，不会留下半个周报。

## 按人总结

默认把所有人的工作项合在一份周报里。按人筛选或拆分时：

```sh
# 只看自己
python3 scripts/pingcode_weekly.py weekly --project PROJ --week 2026-W43 --mine

# 看指定的人（可重复，也可用逗号）
python3 scripts/pingcode_weekly.py weekly --project PROJ --week 2026-W43 \
  --assignee 张三 --assignee 李四

# 每人一份文件：DOC-2026-W43-张三-weekly.md
python3 scripts/pingcode_weekly.py weekly --project PROJ --week 2026-W43 --per-assignee

# 月底把所有人合在一起；窗口是自然月
python3 scripts/pingcode_weekly.py weekly --project PROJ --month 2026-10
```

- `--mine` / `--assignee` 对 `check`、`collect`、`weekly` 都生效；
  `--per-assignee` 只用于 `weekly`。
- `--mine` 需要用户令牌；企业令牌拿不到当前登录人时，改用 `--assignee 姓名`。
- `--assignee` 同时过滤需求和缺陷；拆分后每个文件仍按项目分组。
- **未分配负责人的工作项不匹配任何人**：不会出现在 `--mine` / `--assignee`
  结果里，`--per-assignee` 也不会输出它们。窗口内有这类条目时，`weekly` 会在
  stderr 和“数据缺口”里列出被排除的 ID（`check` 显示“未分配被排除 N 条”）。
  按人生成前先跑 `check`；看到未分配条目先去 PingCode 补负责人，否则周报会缺任务。
- `--per-assignee` 不能和 `--stdout` / `--out` 一起用，用 `--output-dir` 指定目录。
- `--month` 不能和 `--week` / `--since` / `--until` 同时用。
- `--per-assignee` 没有匹配到负责人时直接失败，不生成空文件。

## 工作区

多项目用 TOML 描述：

```toml
[workspace]
template = "templates/weekly.toml"
# output_dir = "~/Downloads/pingcode-weekly"

[[projects]]
name = "示例项目 A"
pingcode_project = "PROJ"
requirement_types = ["需求", "用户故事"]
defect_types = ["缺陷"]
summary_field = "周报摘要"
summary_max_chars = 300
# 如果“已关闭”也算完成，显式加上 closed：
# done_state_types = ["completed", "closed"]

[[projects]]
name = "示例项目 B"
pingcode_project = "DEMO"
requirement_types = ["需求", "用户故事"]
defect_types = ["缺陷"]
```

`pingcode_project` 可写项目名称、标识或 ID。项目还没有缺陷类型时，先在 PingCode
启用或调整类型，`check` 会列出可用类型。

## 采集口径

### 需求

- **本周完成**：`state_type=completed` 且 `completed_at` 在窗口内；`closed` 默认不算完成。
- **进行中**：`state_type=in_progress`；包含当前迭代里的需求。
- **本周新增**：`created_at` 在窗口内。
- **下周计划**：下一迭代里的需求；没有下一迭代时显式标缺口。

### 缺陷

- **本周修复**：`state_type=completed` 且完成时间在窗口内。
- **未关闭缺陷**：`state_type` 不是 `completed/closed`，按严重程度排序。
- **本周新增**：`created_at` 在窗口内。
- **下周计划**：下一迭代里的缺陷。
- 缺严重程度写“未分级”，缺负责人写“未分配”，不猜。

完成时间优先取 `completed_at/closed_at`；缺失时读工作项流转历史，找不到就进入
“完成项缺完成时间”缺口，不拿 `updated_at` 冒充完成时间。

### 摘要

摘要优先级：

1. 工作项自定义字段 `summary_field`（默认“周报摘要”）；
2. 描述第一段；
3. 标题。

不在 PingCode 里的补充说明不会进入周报。需要多句总结时，在 PingCode 里写摘要字段或描述。

## 模板

默认模板在 `templates/default.toml`，由 `[layout] body` 和 `[format]` 组成：

```toml
[layout]
body = """
# {week_start} ~ {week_end} 周报

## 本周任务
{this_week}

## 本周新增/待开始
{new_items}

## 本周新增缺陷
{new_bugs}

## 缺陷清单
{bugs}

## 下周计划
{next_week}

{gaps}
"""

[format]
project = "**{name}**："
requirement = "- [需求] {summary}（{id}，{state}）"
bug = "- [缺陷] {summary}（{id}，{state}）"
new_bug = "- [{severity}] {summary}（{id}，{state}）"
open_bug = "- [{severity}] {summary}（{id}，{state}，{assignee}，已存在 {age_days} 天）"
next_item = "- {summary}（{id}）"
```

可用块：`this_week`、`new_items`、`requirements`、`new_bugs`、`bugs`、`next_week`、`gaps`，以及
`week_start`、`week_end`、`generated_at`。可用条目字段：`id`、`link`、`title`、
`summary`、`state`、`assignee`、`severity`、`priority`、`age_days`、`type`。
块和格式的完整说明见 [模板说明](references/template.md)。

模板里出现未知 `{字段}` 会直接报错，不静默留占位符。

## 失败与边界

- 项目、需求类型、缺陷类型无法解析：`check` 失败并列出可用值。
- 窗口内没有需求/缺陷：`weekly` 默认失败；`--allow-empty` 才生成空报告。
- `--mine` / `--assignee` 只匹配有负责人的条目；窗口内未分配条目被排除时会在
  stderr 和周报“数据缺口”里显式警告，不静默缩水。首次生成建议先跑全量或 `check`。
- 缺少下一迭代：周报写“下周计划未在 PingCode 录入”，不根据描述推断计划。
- 达到 `--limit`：标记 `truncated`，不声称覆盖全部历史。
- 只读：不创建、不修改 PingCode 工作项，不写评论、不写回。
- 只使用 PingCode 数据。
- 只生成周报和证据 JSON，不执行其他动作。

## 参考

- [PingCode 数据合同](references/data-contract.md)：类型、状态、字段和 scope。
- [模板说明](references/template.md)：块、格式、项目分组和错误。
- [证据 JSON](references/evidence-schema.md)：`collect` 输出字段。
- `README.md`：安装、认证、测试和当前限制。
