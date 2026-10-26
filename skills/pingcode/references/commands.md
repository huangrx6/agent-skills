# 命令详解与常用流程

入口：`python3 skills/pingcode/scripts/pingcode.py <子命令>`。全局开关 `--full` / `--dry-run` /
`--no-cache` / `--host` 写在**子命令前或后都可以**。

## 目录

- [全局开关](#全局开关)
- [只读](#只读)
- [搜索的过滤语法（实测出来的，与文档描述不完全一致）](#搜索的过滤语法实测出来的与文档描述不完全一致)
- [写](#写)
- [上下文](#上下文)
- [逃生口](#逃生口)
- [常用流程](#常用流程)
- [命令不做的事](#命令不做的事)
- [evals 执行器](#evals-执行器)

## 全局开关

| 开关 | 作用 |
| --- | --- |
| `--full` | 出原始 JSON（默认是紧凑表格：编号/标题/类型/状态/优先级/负责人/迭代/开始/截止/链接） |
| `--dry-run` | 写操作只打印将发出的 `method / url / headers / body`，**不发送写请求；ID 解析仍可读取接口** |
| `--no-cache` | 字典（项目/迭代/类型/状态/优先级/标签/成员）不吃缓存，重新拉 |
| `--host` | 临时覆盖 host |

## 只读

```sh
# 我名下（--open-only 排除 state.type 为 completed / closed 的）
# --type 可以用中文（缺陷 / 任务 …）；V2 的系统类型 id 是 24 位，
# 没有项目上下文时按 type.group / type.name 本地过滤
pingcode.py workitem mine [--project X] [--type bug|缺陷] [--open-only] [--limit 100]
# 有 --project 时解析 type_id 交给服务端过滤；没有时按页扫描本地过滤（最多 1000 条，超出会提示）

# 按条件查（--project 不给就用上下文里的当前项目）
pingcode.py workitem list [--project X] [--type bug|缺陷] [--state 新建] \
                          [--assignee 张三|@me] [--sprint "Sprint 12"] \
                          [--priority 高] [--tag 后端] [--parent SCR-1] \
                          [--created-by 张三] [--participant 张三] \
                          [--created-between 2026-09-01,2026-09-30] \
                          [--updated-between 2026-09-01,2026-09-30] \
                          [--keywords 登录] [--identifier SCR-12] [--limit 50] [--all]

# 结构化搜索：GET 那套盖不住的场景（按创建时间、标题包含、组合条件…）
pingcode.py workitem search --project X --type bug --created-after 2026-09-01
pingcode.py workitem search --project X --type bug --title-contains 登录
pingcode.py workitem search --filter '{"priority.id":{"in":["…"]}}' --page 1 --limit 50

pingcode.py workitem show SCR-12            # 编号 / short_id / id 都收；带描述与链接
pingcode.py workitem show SCR-12 --all      # 连已删除的一起看（DELETE 是软删除）
pingcode.py workitem history SCR-12         # 流转历史：时间 / 原状态 / 新状态 / 操作人
pingcode.py workitem relations SCR-12       # 内部关联：类型 / 另一端编号 / 标题
pingcode.py workitem relations SCR-12 --type blocked_by  # 只看某类关联
pingcode.py workitem participants SCR-12    # 关注人 / 用户组
pingcode.py list user_groups                # 团队（--group 关注/取消关注用）
pingcode.py project members --project X     # 项目成员与角色
pingcode.py list roles                      # 角色字典
pingcode.py list boards --project X         # 看板（仅 kanban/hybrid）
pingcode.py board create --project X --name 测试看板
pingcode.py board entry-create --project X --board 看板 --name 待办 --wip-limit 3
pingcode.py board swimlane-create --project X --board 看板 --name 泳道
pingcode.py board entries --project X --board 看板
pingcode.py board swimlanes --project X --board 看板
pingcode.py board entry-update <栏 id> --project X --board 看板 --name 进行中
pingcode.py board swimlane-update <泳道 id> --project X --board 看板 --name 新泳道
pingcode.py board entry-delete <栏 id> --project X --board 看板 --yes
pingcode.py board swimlane-delete <泳道 id> --project X --board 看板 --yes
pingcode.py board update --project X --board 看板 --name 新名字
pingcode.py board delete --project X --board 看板 --yes
pingcode.py workitem tags SCR-12            # 当前工作项已打的标签
pingcode.py tag create --project X --name 后端   # 创建项目标签
pingcode.py tag update <tag_id> --name 服务端   # 重命名
pingcode.py tag delete <tag_id> --yes          # 删除
pingcode.py worklog list SCR-12 [--start 2026-09-01 --end 2026-09-30]  # 工时
pingcode.py worklog update <工时 id> --duration 3 --description 补记
pingcode.py workitem download SCR-12 <附件 id> --out ./日志.txt  # 下载附件
pingcode.py project list [--keywords X] [--type scrum] [--all] [--limit 50]
pingcode.py project show X
pingcode.py project progress [--project X]
pingcode.py list projects|sprints|types|states|priorities|tags|users|project_states|processes|relation_types|workload_types \
    [--project X] [--type bug]
pingcode.py list workitem_properties --project X --type 用户故事   # 看该类型能写哪些属性
```

`--assignee @me`（或 `我` / `me`）需要**用户令牌**；企业令牌下请给人名或用户 ID。

## 搜索的过滤语法（实测出来的，与文档描述不完全一致）

`workitem search` 走的是 `POST /v2/pjm/workitems/search`（类 MongoDB 语法）。官方文档
列出了操作符**名字**，但没说格式 —— 下面几条是拿真实接口试出来的（V1 租户；V2 待复核）：

| 实测结论 | 证据 |
| --- | --- |
| 操作符**不带 `$` 前缀** | `{"in":[…]}` → 200；`{"$in":[…]}` → 400「缺少有效的操作符」 |
| 值**必须是对象**，不能直接给标量 | `{"type":"epic"}` → 400「值必须是对象」 |
| 引用类型用 `属性名.id` | `project.id` / `type.id` / `state.id` / `assignee.id` / `sprint.id` |
| `identifier` 这类内置属性**不能**过滤 | 400「不支持使用过滤条件 filter.identifier」 |
| 每个属性只能带一个操作符、不支持逻辑运算符 | 官方文档明说 |

各类型的可用操作符（官方文档）：文本 `exists`/`contains`；枚举与选项 `exists`/`in`/`nin`；
数字 `exists`/`eq`/`ne`/`gt`/`lt`/`gte`/`lte`；时间 `exists`/`gt`/`lt`/`gte`/`lte`/`between`。

CLI 把常用条件做成了参数（`--type` / `--state` / `--assignee` / `--sprint` / `--keywords` /
`--title-contains` / `--created-after` / `--created-before`），其余用 `--filter` 直接给原始条件
（不另发明语法）。`--state` 按名字过滤时要同时给 `--project` 与 `--type`（状态 id 是按
「项目 + 类型」配的），直接给状态 id 除外。

## 写

```sh
# 项目：V2 官方必填 template_type / name / identifier（CLI 的 --type 会映射成 template_type）
pingcode.py project create --type scrum --name "演示项目" --identifier DEMO \
                          [--description …] [--start 2026-09-01] [--end 2026-12-31] [--assignee @me]
pingcode.py project update [--project X] [--name …] [--identifier …] [--description …] \
                          [--start …] [--end …] [--assignee …] [--state 进行中]

# 工作项：epic(史诗) / feature(特性) / story(用户故事) / task(任务) / bug(缺陷) / issue(事务)…
# 没给 --start/--end 时，会从 --sprint、带日期的 --parent 或项目日期自动继承；
# 都没有时会提示，建议先补日期再建。
pingcode.py workitem create --project X --type bug --title "登录页 500" \
    [--description "…"] [--description-file 描述.md] \
    [--assignee @me | --unassigned] [--priority 高] [--sprint "Sprint 12"] [--parent SCR-1] \
    [--state 新建] [--start 2026-09-20] [--end 2026-09-30] \
    [--story-points 3] [--estimated-workload 8] [--property risk=high]

# --story-points 只对该类型属性方案包含 story_points 的类型可用（用户故事等）。
# 任务没有这个属性；CLI 会先查 workitem_properties 并拒绝，避免 400 code=100355。

pingcode.py workitem update SCR-12 --description "…" --end 2026-09-30

# 回填缺失起止时间：默认只预览，--yes 才写
# 推导顺序：迭代 → 子项汇总 → 创建时间/完成时间 → 项目日期 → 兜底日期
# 超过 --limit 时结果可能截断；项目很大时先调大 --limit
pingcode.py workitem fill-dates --project X
pingcode.py workitem fill-dates --project X --yes
# 没有迭代/父项可继承的根节点，用兜底日期
pingcode.py workitem fill-dates --project X --start 2026-10-19 --end 2026-10-25 --yes
pingcode.py workitem set-state SCR-12 已完成
pingcode.py workitem comment SCR-12 "已定位到网关超时"
pingcode.py workitem delete SCR-12 --yes            # 需明确授权

# 附件：列表默认不列软删除的（--all 才列）；上传两端点形状不同
pingcode.py workitem attachments SCR-12              # 直接附件
pingcode.py workitem attachments SCR-12 --comment <评论 id>  # 评论附件/代码段
pingcode.py workitem attach SCR-12 --file ./trace.log --title "网关日志" [--comment <评论 id>]
# 代码段**实测必须带 --comment**（官方文档把 comment_id 标成可选，不带回 400 code=100039）：
pingcode.py workitem comment SCR-12 "这段是根因"     # 先拿评论 id
pingcode.py workitem comments SCR-12 --full
pingcode.py workitem attach-code SCR-12 --comment <评论 id> --title "ngx.conf" \
    --format nginx --content-file ./ngx.conf
# 删附件：需明确授权，所以要 --yes（评论里的附件再加 --comment <评论 id>）
pingcode.py workitem attach-remove SCR-12 <附件 id> --yes

# 批量改**一个**属性（官方限制：单属性 + 单值 + ≤100 个 id）
# 改状态/优先级/迭代/工作量时，所有 id 必须在同一项目、同一类型；否则先分批。
pingcode.py workitem bulk-update --ids SCR-1,SCR-2,SCR-3 --state 已完成
pingcode.py workitem bulk-update --ids SCR-1,SCR-2 --assignee @me --dry-run
pingcode.py workitem bulk-update --ids SCR-1,SCR-2 --property risk=high

# 一次建一棵树（史诗 → 特性 → 用户故事 → 任务）：适合把一段需求/一份计划落成工作项
pingcode.py workitem create-plan --file plan.json             # 默认只打印整棵树，不建
pingcode.py workitem create-plan --file plan.json --yes       # 确认才建
# 给未写负责人的节点统一指定；--unassigned 明确不分配
pingcode.py workitem create-plan --file plan.json --assignee @me
pingcode.py workitem create-plan --file plan.json --unassigned
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
- **建前全树只读预检** —— `--yes` 时先把所有节点的类型、属性方案、负责人、优先级、
  迭代、状态、日期和描述文件解析一遍；任何节点失败都**不创建任何一条**，并报出节点路径。
- **深度优先建（父先子后）** —— 子项要父项的 id。
- **预检通过后中途 API 失败不静默** —— 报出**已建成的编号**与失败的节点，让你把剩下的
  子树单独放一个计划文件接着跑（不要整棵重跑；CLI 没有持久化断点或自动去重）。

若剩余节点要挂到已经创建的父项，改用 `workitem create --parent <现有编号>`；
`create-plan` 的根节点没有“接到既有父项”的参数。

`type` 写中文也行（史诗 / 特性 / 用户故事 / 任务 / 缺陷），本地会翻成枚举；
自定义类型要写 id。

需求拆分、描述模板和截图附件流程见 [workitem-authoring.md](workitem-authoring.md)。
树建好后逐条上传截图，再在描述里回链附件标题：

```sh
pingcode.py workitem attach SCR-3 --file ./截图.png --title "下单流程-异常状态"
pingcode.py workitem attachments SCR-3
```

**写操作会先回显**：`→ 在「演示项目」创建 缺陷：登录页 500`，然后才发。
不确定就先加 `--dry-run` 看 body。

**时间格式**：`2026-09-20`（当天 00:00，V2 `with_time=0`）、
`2026-09-20 18:30`（`with_time=1`）、或 10 位时间戳。

## 上下文

```sh
pingcode.py config context --project 演示项目 --sprint "Sprint 12"
pingcode.py config context                # 看当前
pingcode.py config context --clear
pingcode.py config refresh [--what projects,sprints,types,states,priorities,tags,users,project_states,processes,workitem_properties,relation_types,workload_types] \
    [--project X] [--type bug]
# --type 只在刷新 states / workitem_properties 时需要
pingcode.py config show                   # 凭据/令牌/上下文的完整状态
```

设了当前项目后，`workitem list` / `create` 都可以不写 `--project`。

## 逃生口

```sh
pingcode.py api --list 工作项                  # 在生成的端点表里按关键词找
pingcode.py api --show GET /v2/pjm/workitems   # 看某个端点的分组 / scope / 令牌要求
pingcode.py api --method GET --path /v2/pjm/workitem/workitem_priorities --param project_id=xxx
pingcode.py api --method POST --path /v2/comments --data '{"principal_type":"workitem","principal_id":"…","content":"…"}'
```

路径不在随附官方文档快照里会被拦下（并给出最接近的候选）；先核实官方契约且属于已授权范围，才使用 `--force`。

## 常用流程

| 用户这么说 | 这样做 |
| --- | --- |
| "我今天要做哪些事" | `workitem mine --open-only` ；企业令牌下用不了「我」，改 `workitem list --assignee <真名>` |
| "这条怎么改过来的" | `workitem history SCR-12`；已删除工作项的流转历史服务端不返回 |
| "这条和哪些工作项有关联" | `workitem relations SCR-12 [--type blocked_by]` |
| "谁在关注这条" | `workitem participants SCR-12` / `workitem watch SCR-12 Open Team --group` |
| "给这条打/去标签" | `workitem tags SCR-12` / `workitem tag SCR-12 后端` / `workitem untag SCR-12 后端 --yes` |
| "管理项目标签" | `tag create/update/delete …` |
| "项目成员/角色" | `project members --project X` / `list roles` |
| "看看板栏/泳道" | `list boards --project X` / `board entries / swimlanes …` |
| "建/改/删看板栏或泳道" | `board entry-create/update/delete …` / `board swimlane-create/update/delete …` |
| "登记/查看/修改工时" | `worklog add SCR-12 --duration 2` / `worklog list SCR-12` / `worklog update <id> --duration 3` |
| "建/改迭代" | `sprint create …` / `sprint update …`（没有删除迭代接口） |
| "删评论" | `workitem comment-delete SCR-12 <id> --yes`（官方没有评论编辑接口） |
| "把附件下载下来" | `workitem download SCR-12 <附件 id> --out ./文件` |
| "看评论里的代码段" | `workitem attachments SCR-12 --comment <评论 id>` |
| "把两条工作项关联起来" | `workitem relate SCR-12 --to SCR-5 [--type relate]` |
| "我名下某项目的任务" | `workitem mine --project X --open-only`（服务端按项目/类型过滤） |
| "有哪些没修的缺陷" | `workitem mine --type bug --open-only`（指定项目时加 `--project X` 走服务端过滤） |
| "把 SCR-12 关了" | 先 `workitem show SCR-12` 确认是它，再 `workitem set-state SCR-12 已完成`（状态名要真实存在，报错会列出可选项） |
| "建一个需求 / 任务 / 缺陷" | `workitem create`，`--type story\|task\|bug`；缺的信息（项目、标题）先问，别编。不确定先 `--dry-run` |
| "建一棵史诗 → 特性 → 故事 → 任务" | 写一份 `plan.json` 跑 `workitem create-plan --file plan.json`（先看树）→ 授权已覆盖该计划时加 `--yes`。比逐条 create 少一整轮编号传递 |
| "把这个迭代的任务列出来" | `workitem list --sprint "Sprint 12"`（迭代名有歧义时会列候选） |
| "这个项目进度怎么样" | `project progress --project X` → 总数 / 待处理 / 进行中 / 已完成 |
| "帮我建个新项目" | `project create --type scrum --name … --identifier …`（identifier ≤15 位大写字母/数字/`_`/`-`，全企业唯一） |
| "把一批任务都标完成" | 用 `workitem bulk-update --ids A,B,C --state 已完成`（官方限制：**单属性、单值、≤100 个 id**） |

## 命令不做的事

- 不做成员 / 权限 / 部门 / 角色管理；通用 API 不扩大该范围。
- **不删项目**（当前随附端点表没有删除项目的接口）。`project update --state` 只能改状态。
- 不按「不同值」批量改字段（官方批量接口只支持一个属性名 + 一个相同值）。
- 不替你做状态流转判断：可用状态由该类型的「状态方案 + 状态流转」决定，CLI 查询该类型的状态表，具体流转仍由服务端校验。

## evals 执行器

`dev-tools/run_evals.py` 不内置模型，agent/judge 由命令行或环境变量提供：

```sh
python3 skills/pingcode/dev-tools/run_evals.py --check
python3 skills/pingcode/dev-tools/run_evals.py --dry-run --agent-cmd 'pi -p {prompt}'
python3 skills/pingcode/dev-tools/run_evals.py \
    --agent-cmd 'pi -p {prompt}' \
    --judge-cmd './judge.sh --expected {expected} --actual {actual}'
```

judge 退出 0 视为通过；不给 judge 时只记录 transcript。运行记录写到
`skills/pingcode/evals/runs/<时间>/`。

项目创建/更新的真实写链路没有在随附验证中执行：端点表没有项目删除接口，
创建后无法保证“用完即删”；命令已有 mock/dry-run 覆盖，真实写需在专用测试租户进行。

工时端点需要 `pcp:read/write:global:workload`，并依赖工时所属工作项的作用域；
当前租户未开这个 scope 时，`worklog list/add` 会返回 403，错误会点名所需 scope。

看板只适用于 kanban/hybrid 项目。新建看板会自动生成一个“默认泳道”和系统栏；
再建泳道时先 `board swimlanes` 看名字，避免重名 400。
