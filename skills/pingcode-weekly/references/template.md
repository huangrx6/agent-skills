# 周报模板

默认模板：`templates/default.toml`。模板只读证据 JSON，不访问 PingCode。

## 结构

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

## body 可用块

| 块 | 内容 |
| --- | --- |
| `{this_week}` | 本周完成/进行中的需求和缺陷，按项目分组 |
| `{new_items}` | 本周新增、尚未进入完成/进行中且不在下一迭代的需求 |
| `{requirements}` | 只列本周完成/进行中的需求 |
| `{new_bugs}` | 本周新建的缺陷，按严重程度排序 |
| `{bugs}` | 未关闭缺陷，按严重程度排序 |
| `{next_week}` | 下一迭代里的需求和缺陷 |
| `{gaps}` | 数据缺口；没有缺口时为空 |
| `{week_start}` / `{week_end}` | 窗口日期 |
| `{generated_at}` | 证据生成时间 |

`{this_week}`、`{bugs}`、`{next_week}` 不包含章节标题；标题写在 `body` 里。
项目分组由 `[format].project` 控制。

## 条目字段

| 字段 | 说明 |
| --- | --- |
| `{id}` | PingCode 编号 |
| `{link}` | Markdown 链接；没有 URL 时退化为编号 |
| `{title}` | 原始标题 |
| `{summary}` | 周报摘要（自定义字段/描述/标题） |
| `{state}` | 状态名 |
| `{assignee}` | 负责人；缺失时为“未分配” |
| `{severity}` | 缺陷严重程度；缺失时为“未分级” |
| `{priority}` | 优先级；缺失时为“未设置” |
| `{age_days}` | 缺陷存在天数；未知时为 `?` |
| `{type}` | 需求/缺陷类型名 |

格式串出现未知字段会报错，不会静默留占位符。body 出现未知 `{字段}` 也会报错。

## 自定义示例

```toml
[layout]
body = """
# {week_start} ~ {week_end} 周报

## 本周交付
{this_week}

## 未关闭缺陷
{bugs}

## 下周
{next_week}
"""

[format]
project = "### {name}"
requirement = "- {summary}（{link}）"
open_bug = "- **{severity}** {summary} · {assignee}"
```

## 多项目

`weekly --workspace weekly.toml` 会按 `projects` 顺序渲染。每个块内按项目分组；
项目之间空一行。没有来源项目的错误会进入 `{gaps}`，不静默省略。

## 空报告

PingCode 没有记录时，`weekly` 默认退出 2。使用 `--allow-empty` 才生成：
`{this_week}` 会写“本周没有已完成或进行中的…”，`{new_bugs}` 写“本周没有新增缺陷”，`{bugs}` 写“无未关闭缺陷”，
`{next_week}` 写“下周计划未在 PingCode 录入”。
