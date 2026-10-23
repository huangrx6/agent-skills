# pingcode-weekly

> 从 PingCode 的需求和缺陷生成项目周报。PingCode 是唯一事实源；只读，不写回任何系统。

| 适合 | 产物 | 依赖 |
| --- | --- | --- |
| 周报 / 月报 · 按项目或按人汇总 · 数据缺口检查 | Markdown 周报 · 证据 JSON | Python 3.11+（标准库）· PingCode 令牌 |

<details>
<summary><strong>目录</strong></summary>

- [快速开始](#快速开始)
- [认证](#认证)
- [输出位置](#输出位置)
- [按人总结](#按人总结)
- [多项目](#多项目)
- [模板](#模板)
- [输出内容](#输出内容)
- [验证](#验证)
- [当前限制](#当前限制)

</details>

## 依赖

- Python 3.11+，只用标准库（`tomllib`、`urllib`）。
- 一个可访问的 PingCode 租户，以及能读取项目、工作项、类型、状态、迭代的令牌。
- 本 skill 内置只读客户端。

## 目录

| 文件 | 作用 |
| --- | --- |
| `scripts/pingcode_weekly.py` | CLI：`auth`、`check`、`collect`、`weekly`、`render`、`projects` |
| `scripts/collect.py` | 窗口、需求/缺陷采集、数据合同和缺口 |
| `scripts/pingcode_read.py` | 项目/类型/状态/迭代/工作项/history 只读接口 |
| `scripts/weekly.py` | 模板加载与 Markdown 渲染 |
| `scripts/output_paths.py` | 跨平台下载目录、文件名清洗和原子写入 |
| `scripts/_pingcode/` | 内置只读认证与 HTTP 客户端 |
| `templates/default.toml` | 默认周报模板 |
| `references/` | 数据合同、模板和证据 JSON |

## 认证

第一次使用：

```sh
python3 scripts/pingcode_weekly.py auth login
python3 scripts/pingcode_weekly.py auth status
```

- 用户 OAuth：`auth login` 打印授权地址；回调地址打不开时，把地址栏的 `code` 带回：
  `auth login --code <code>`。
- 企业令牌：`auth login --mode enterprise`。
- 也可以直接提供令牌：`PINGCODE_ACCESS_TOKEN`、`PINGCODE_HOST`。
- 配置目录默认是 `~/.agent-skills/config/pingcode/`，可用 `PINGCODE_CONFIG_DIR` 改。
- 凭据格式和所需 scope 见 [references/data-contract.md](references/data-contract.md)。

认证代码是内置的只读副本；配置目录只用于保存凭据和令牌。

## 快速开始

```sh
# 先检查数据是否足够
python3 scripts/pingcode_weekly.py check --project PROJ --week 2026-W43

# 生成周报：默认写到下载目录
python3 scripts/pingcode_weekly.py weekly --project PROJ --week 2026-W43

# 只看不落盘
python3 scripts/pingcode_weekly.py weekly --project PROJ --week 2026-W43 --stdout

# 保存证据 JSON：默认写到同一个目录
python3 scripts/pingcode_weekly.py collect --project PROJ --week 2026-W43

# 从已有证据重渲染
python3 scripts/pingcode_weekly.py render --input <collect 的输出路径> --template custom.toml
```

`--week` 使用 ISO 周（周一到周日）；也可用 `--month 2026-10` 或 `--since/--until`。
`weekly` 在没有 PingCode 记录时默认退出 2；确实要空周报时加 `--allow-empty`。

## 输出位置

`weekly`、`collect`、`render` 的默认输出都在同一个下载目录：

- macOS/Linux：`~/Downloads/pingcode-weekly/`
- Windows：`%USERPROFILE%\Downloads\pingcode-weekly\`

文件名：

- 周报：`<项目或工作区>-<窗口>-weekly.md`
- 证据：`<项目或工作区>-<窗口>-evidence.json`
- 重渲染：`<证据文件名>-rendered-weekly.md`

`check`、`auth`、`projects` 只打印，不写文件。可用 `--stdout` 不落盘，
`--out` 指定完整路径，或用 `--output-dir`、`PINGCODE_WEEKLY_OUTPUT_DIR`、
`[workspace] output_dir` 换目录。写入是临时文件加原子替换，失败不会覆盖旧文件。

## 按人总结

默认所有人合并。需要按人看时：

```sh
# 只看自己
python3 scripts/pingcode_weekly.py weekly --project PROJ --week 2026-W43 --mine

# 指定一个或多个人
python3 scripts/pingcode_weekly.py weekly --project PROJ --week 2026-W43 \
  --assignee 张三 --assignee 李四

# 每人一份文件
python3 scripts/pingcode_weekly.py weekly --project PROJ --week 2026-W43 --per-assignee

# 月底所有人合并
python3 scripts/pingcode_weekly.py weekly --project PROJ --month 2026-10
```

`--mine` / `--assignee` 对 `check`、`collect`、`weekly` 都生效；`--per-assignee`
只用于 `weekly`。`--per-assignee` 生成 `<项目>-<窗口>-<姓名>-weekly.md`，不能和 `--stdout` / `--out`
一起用。`--month` 是自然月，不能与 `--week` / `--since` / `--until` 同时使用。
`--mine` 需要用户令牌；企业令牌下改用人名。

## 多项目

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
# 如果“已关闭”也算完成：
# done_state_types = ["completed", "closed"]

[[projects]]
name = "示例项目 B"
pingcode_project = "DEMO"
requirement_types = ["用户故事"]
defect_types = ["缺陷"]
```

```sh
python3 scripts/pingcode_weekly.py weekly --workspace weekly.toml --week 2026-W43
```

所有项目都通过 PingCode 解析。

## 模板

默认模板是 `templates/default.toml`。用 `[layout] body` 控制章节顺序，
用 `[format]` 控制项目标题和条目写法：

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
```

完整块和字段见 [references/template.md](references/template.md)。

## 输出内容

`collect` 输出 `version: 1` 的证据 JSON；`weekly` 输出 Markdown，含本周任务、本周新增缺陷、缺陷清单和下周计划。
每个需求/缺陷都保留 PingCode 编号、状态、负责人、摘要和链接。
缺负责人、缺完成时间、缺陷缺严重程度、没有下一迭代会进入“数据缺口”，不会用默认值补造。

## 验证

```sh
python3 -m unittest discover -s tests/pingcode-weekly -v
```

测试使用 fake PingCode API，不访问真实租户。真实租户只读验证可以用一个测试项目跑
`check`，不要把真实输出提交为固定夹具。

## 当前限制

- 只支持需求/缺陷；任务、史诗、特性不进入默认周报。
- `closed` 默认不算完成；如果项目的“已关闭”确实代表完成，需要在采集口径里调整。
- 缺陷严重程度依赖工作项属性或 `severity` 字段；没有就显示“未分级”。
- 只做 PingCode 周报，不执行写入。
- 工作项达到 `--limit` 时标记截断，不能声称覆盖全部历史。
