# 命令详解与常用流程

入口：`python3 skills/pingcode/scripts/pingcode.py <子命令>`。全局开关 `--full` / `--dry-run` /
`--no-cache` / `--host` 写在**子命令前或后都可以**。

## 全局开关

| 开关 | 作用 |
| --- | --- |
| `--full` | 出原始 JSON（默认是紧凑表格：编号/标题/类型/状态/优先级/负责人/迭代/截止/链接） |
| `--dry-run` | 写操作只打印将发出的 `method / url / headers / body`，**不发送** |
| `--no-cache` | 字典（项目/迭代/类型/状态/优先级/标签/成员）不吃缓存，重新拉 |
| `--host` | 临时覆盖 host |

## 只读

```sh
# 我名下（--open-only 排除 state.type 为 completed / closed 的）
# --type 可以用中文（缺陷 / 任务 …），本地会翻成枚举；自定义类型要带 --project
pingcode.py workitem mine [--type bug|缺陷] [--open-only] [--limit 100]

# 按条件查（--project 不给就用上下文里的当前项目）
pingcode.py workitem list [--project X] [--type bug|缺陷] [--state 新建] \
                          [--assignee 张三|@me] [--sprint "Sprint 12"] \
                          [--keywords 登录] [--identifier SCR-12] [--limit 50] [--all]

# 结构化搜索：GET 那套盖不住的场景（按创建时间、标题包含、组合条件…）
pingcode.py workitem search --project X --type bug --created-after 2026-09-01
pingcode.py workitem search --project X --type bug --title-contains 登录
pingcode.py workitem search --filter '{"priority.id":{"in":["…"]}}'

pingcode.py workitem show SCR-12            # 编号 / short_id / id 都收；带描述与链接
pingcode.py workitem show SCR-12 --all      # 连已删除的一起看（DELETE 是软删除）
pingcode.py project list [--keywords X] [--type scrum]
pingcode.py project show X
pingcode.py project progress [--project X]
pingcode.py list projects|sprints|types|states|priorities|tags|users [--project X] [--type bug]
```

`--assignee @me`（或 `我` / `me`）需要**用户令牌**；企业令牌下请给人名或用户 ID。

## 搜索的过滤语法（实测出来的，与文档描述不完全一致）

`workitem search` 走的是 `POST /v1/pjm/workitems/search`（类 MongoDB 语法）。官方文档
列出了操作符**名字**，但没说格式 —— 下面几条是拿真实接口试出来的：

| 实测结论 | 证据 |
| --- | --- |
| 操作符**不带 `$` 前缀** | `{"in":[…]}` → 200；`{"$in":[…]}` → 400「缺少有效的操作符」 |
| 值**必须是对象**，不能直接给标量 | `{"type":"epic"}` → 400「值必须是对象」 |
| 引用类型用 `属性名.id` | `project.id` / `state.id` / `assignee.id` / `sprint.id` |
| `identifier` 这类内置属性**不能**过滤 | 400「不支持使用过滤条件 filter.identifier」 |
| 每个属性只能带一个操作符、不支持逻辑运算符 | 官方文档明说 |

各类型的可用操作符（官方文档）：文本 `exists`/`contains`；枚举与选项 `exists`/`in`/`nin`；
数字 `exists`/`eq`/`ne`/`gt`/`lt`/`gte`/`lte`；时间 `exists`/`gt`/`lt`/`gte`/`lte`/`between`。

CLI 把常用条件做成了参数（`--type` / `--state` / `--assignee` / `--sprint` / `--title-contains` /
`--created-after`），其余用 `--filter` 直接给原始条件（不另发明语法）。

## 写

```sh
# 项目：type / name / identifier 是官方必填
pingcode.py project create --type scrum --name "演示项目" --identifier DEMO \
                          [--description …] [--start 2026-09-01] [--end 2026-12-31] [--assignee @me]
pingcode.py project update [--project X] [--name …] [--description …] [--start …] [--end …] \
                          [--assignee …] [--state 进行中]

# 工作项：epic(史诗) / feature(特性) / story(用户故事) / task(任务) / bug(缺陷) / issue(事务)…
pingcode.py workitem create --project X --type bug --title "登录页 500" \
    [--description "…"] [--description-file 描述.md] \
    [--assignee @me] [--priority 高] [--sprint "Sprint 12"] [--parent SCR-1] \
    [--state 新建] [--start 2026-09-20] [--end 2026-09-30] \
    [--story-points 3] [--estimated-workload 8]

pingcode.py workitem update SCR-12 --description "…" --end 2026-09-30
pingcode.py workitem set-state SCR-12 已完成
pingcode.py workitem comment SCR-12 "已定位到网关超时"
pingcode.py workitem delete SCR-12 --yes            # 不可逆

# 批量改**一个**属性（官方限制：单属性 + 单值 + ≤100 个 id）
pingcode.py workitem bulk-update --ids SCR-1,SCR-2,SCR-3 --state 已完成
pingcode.py workitem bulk-update --ids SCR-1,SCR-2 --assignee @me --dry-run

# 一次建一棵树（史诗 → 特性 → 用户故事 → 任务）：适合把一段需求/一份计划落成工作项
pingcode.py workitem create-plan --file plan.json             # 默认只打印整棵树，不建
pingcode.py workitem create-plan --file plan.json --yes       # 确认才建
```

`plan.json`：字段集是**封闭的**（写错字段名当场报错并给候选），层次靠 `children` 嵌套：

```json
{
  "project": "演示项目",
  "nodes": [
    {"type": "epic", "title": "商城改版", "children": [
      {"type": "feature", "title": "下单与支付", "children": [
        {"type": "story", "title": "下单流程", "priority": "普通",
         "children": [{"type": "task", "title": "接入支付网关"}]}
      ]}
    ]}
  ]
}
```

节点可用字段：`type` `title`（必填）、`description` `description_file` `assignee` `priority`
`sprint` `state` `start` `end` `story_points` `estimated_workload` `remaining_workload` `children`。

行为上有三条是刻意的：

- **`--yes` 之前一定不建** —— 「先打印整棵树再建」不靠自觉，靠接口默认值。
- **深度优先建（父先子后）** —— 子项要父项的 id。
- **中途失败不静默** —— 报出**已建成的编号**与失败的节点，让你把剩下的子树单独放一个
  计划文件接着跑（已建成的不会重复建）。

`type` 写中文也行（史诗 / 特性 / 用户故事 / 任务 / 缺陷），本地会翻成枚举；
自定义类型要写 id。

**写操作会先回显**：`→ 在「演示项目」创建 缺陷：登录页 500`，然后才发。
不确定就先加 `--dry-run` 看 body。

**时间格式**：`2026-09-20`（当天 00:00）、`2026-09-20 18:30`、或 10 位时间戳。

## 上下文

```sh
pingcode.py config context --project 演示项目 --sprint "Sprint 12"
pingcode.py config context                # 看当前
pingcode.py config context --clear
pingcode.py config refresh [--what projects,sprints,types,states,priorities,tags,users]
pingcode.py config show                   # 凭据/令牌/上下文的完整状态
```

设了当前项目后，`workitem list` / `create` 都可以不写 `--project`。

## 逃生口

```sh
pingcode.py api --list 工作项                  # 在生成的端点表里按关键词找
pingcode.py api --show GET /v1/pjm/workitems   # 看某个端点的分组 / scope / 令牌要求
pingcode.py api --method GET --path /v1/pjm/workitem_priorities --param project_id=xxx
pingcode.py api --method POST --path /v1/comments --data '{"principal_type":"workitem","principal_id":"…","content":"…"}'
```

路径不在官方文档里会被拦下（并给出最接近的候选）；确认要用就加 `--force`。

## 常用流程

| 用户这么说 | 这样做 |
| --- | --- |
| "我今天要做哪些事" | `workitem mine --open-only` ；企业令牌下用不了「我」，改 `workitem list --assignee <真名>` |
| "有哪些没修的缺陷" | `workitem mine --type bug --open-only` 或 `workitem list --type bug` |
| "把 SCR-12 关了" | 先 `workitem show SCR-12` 确认是它，再 `workitem set-state SCR-12 已完成`（状态名要真实存在，报错会列出可选项） |
| "建一个需求 / 任务 / 缺陷" | `workitem create`，`--type story\|task\|bug`；缺的信息（项目、标题）先问，别编。不确定先 `--dry-run` |
| "建一棵史诗 → 特性 → 故事 → 任务" | 写一份 `plan.json` 跑 `workitem create-plan --file plan.json`（先看树）→ 确认后 `--yes`。比逐条 create 少一整轮编号传递 |
| "把这个迭代的任务列出来" | `workitem list --sprint "Sprint 12"`（迭代名有歧义时会列候选） |
| "这个项目进度怎么样" | `project progress --project X` → 总数 / 待处理 / 进行中 / 已完成 |
| "帮我建个新项目" | `project create --type scrum --name … --identifier …`（identifier ≤15 位大写字母/数字/`_`/`-`，全企业唯一） |
| "把一批任务都标完成" | 用 `api --method PATCH --path /v1/pjm/workitems` 批量（官方限制：**单属性、单值、≤100 个 id**） |

## 命令不做的事

- 不做成员 / 权限 / 部门 / 角色管理 —— 走 `api` 逃生口。
- **不删项目**（官方没有删除项目的接口）。`project update --state` 只能改状态。
- 不按「不同值」批量改字段（官方批量接口只支持一个属性名 + 一个相同值）。
- 不替你做状态流转判断：可用状态由该类型的「状态方案 + 状态流转」决定，CLI 会把可用状态查出来。
