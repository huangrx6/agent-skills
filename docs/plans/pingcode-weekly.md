# pingcode-weekly：PingCode-only 周报设计

## 目标

从 PingCode 的需求和缺陷生成项目周报。PingCode 是唯一事实源，服务产品、文员和
非开发角色：他们只需要在 PingCode 录入工作项。

## 非目标

- 只读 PingCode，不写回。
- 不写 PingCode：不创建/修改工作项、评论、附件或工时。
- 不从标题或常识推断“完成”“下周计划”或缺陷严重程度。
- 只生成周报和证据，不执行写入。

## 数据流

```text
PingCode 项目
  ├─ 需求类型 → 本周完成 / 进行中 / 新增 / 下一迭代
  └─ 缺陷类型 → 本周修复 / 未关闭 / 新增 / 下一迭代
        ↓
   check / collect（只读）
        ↓
   evidence.json（version 1）
        ↓
   weekly + TOML 模板
        ↓
   ~/Downloads/pingcode-weekly/*.md
```

## 内置客户端

`scripts/_pingcode/` 是内置的只读代码：

- `config.py`：凭据、令牌缓存、配置目录（格式兼容）。
- `client.py`：HTTP、分页、429 重试；周报只调用 GET。
- `auth.py`：用户/企业授权、刷新、状态。
- `compat.py`：V2 工作项字段规范化。


## 数据合同

硬性条件：

- 项目可解析。
- 需求类型、缺陷类型可解析。
- 完成项有完成时间（字段或 history）。
- 缺陷有严重程度或明确标“未分级”。

软性缺口：

- 缺负责人。
- 缺下一迭代。
- 缺摘要字段；退回描述/标题。
- 达到采集上限。

缺字段进入报告“数据缺口”，不用默认值补造。没有需求/缺陷记录时 `weekly` 默认
退出 2，`--allow-empty` 才生成空报告。

## 采集口径

- 窗口：ISO 周（周一到周日）或 `--since/--until`。
- 需求：窗口内更新 + 当前迭代；本周完成看 `completed_at`；进行中看 `state_type`。
- 缺陷：全部缺陷 + 当前/下一迭代；未关闭按严重程度排序；完成看完成时间。
- 下周计划：窗口结束后的下一迭代；没有就显式写缺口。
- `closed` 默认不算完成，避免把“已拒绝”写成修复；工作区可用 `done_state_types` 显式加入 `closed`。

## 模板

默认 `templates/default.toml`：

- `[layout].body` 控制章节顺序和静态文字。
- `[format]` 控制项目标题、需求/缺陷/未关闭缺陷/下周计划条目。
- 可用块：`this_week`、`new_items`、`requirements`、`new_bugs`、`bugs`、`next_week`、`gaps`。
- 未知占位符直接报错。

不在 v1 引入 Jinja2；TOML 模板已能覆盖章节顺序和条目格式，对非开发用户更友好。

## 按人

- 默认所有人合并。
- `--mine`：当前登录人；企业令牌拿不到身份时改用 `--assignee`。
- `--assignee`：可重复/逗号分隔，按负责人 ID 或显示名过滤。
- `--per-assignee`：每人一个 Markdown 文件，文件名带负责人。
- `--month`：自然月窗口，适合月底合并。
- 过滤后重算 quality，不沿用全量统计。

## 输出

- `weekly`、`collect`、`render` 默认写到系统下载目录下的 `pingcode-weekly/`。
- macOS/Linux 为 `~/Downloads/pingcode-weekly/`；Windows 为
  `%USERPROFILE%\Downloads\pingcode-weekly\`。
- 文件名带项目/工作区标签和窗口，周报为 `*-weekly.md`，证据为 `*-evidence.json`。
- `--out` 可指定完整路径；`--output-dir`、`PINGCODE_WEEKLY_OUTPUT_DIR` 或
  `[workspace] output_dir` 可换目录；`--stdout` 不落盘。
- 写入使用临时文件加原子替换，失败不破坏旧文件。

## 验证

- fake PingCode API：项目/类型/状态/迭代/工作项/history。
- 窗口、完成时间回退、需求/缺陷分组、计划、缺口。
- 默认模板和自定义模板。
- CLI `weekly --help` 不访问 PingCode。
- 真实租户只读验证：用测试项目跑 `check`；不提交真实输出。

## 阶段

| 阶段 | 内容 |
| --- | --- |
| 当前 | PingCode 只读、需求/缺陷、check/collect/weekly/render、默认下载目录、原子写、默认/自定义模板 |
| 后续 | 缺陷趋势/年龄分档、更多工作项类型 |

只做周报和证据；任何写回都不在当前承诺内。
