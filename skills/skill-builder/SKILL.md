---
name: skill-builder
description: >-
  Use this skill before creating a new skill, or when judging whether an existing skill's trigger description is too broad / too narrow / too vague.
  Decides whether a skill is the right tool, defines a non-flaky trigger description, scopes the new skill to P0 / P1 / P2, and produces a SKILL.md checklist.
  Also use it when an existing skill keeps getting missed or over-firing, to revise the description.
  Do NOT use for: editing an existing skill's body content, writing a one-off prompt that does not need to persist, running formal eval to validate trigger accuracy, or maintaining references/ assets/ scripts/ inside an existing skill.
---

# skill-builder — 建 Skill 前的 5 分钟决策

Decides whether a skill is worth building and produces a tight SKILL.md draft. Lightweight by design — no eval pipeline, no asset tooling.

Use when: 用户想建一个 skill / 问触发描述是不是太宽太窄 / 拿新需求问要不要包成 skill / 现有 skill 触发重叠要拆合 / 现有 skill 反复触发错要重写 description。

Do NOT use when: 编辑现有 skill 的正文(直接改 SKILL.md)/ 写一次性 prompt 或 alias / 跑 formal eval 验证触发准确度(另起流程)/ 补 references/ 或 assets/(直接补,不重做决策)。

## The 5-Minute Decision Tree

按顺序回答 5 个问题。任何一题答不上来 = 不要建 skill,先回去想清楚再回来。

### Q1. 这是不是一个 skill 该解决的问题?

Skill 解决"Agent 该做但反复做"的事。如果只是单次任务,不要包成 skill。

| 信号 | 含义 |
| --- | --- |
| 同一个动作 / 决策 / 流程,在最近 30 天出现 ≥3 次 | 值得建 skill |
| 单次一次性需求,只在本次对话里出现 | 不需要 skill,直接 prompt |
| 是 prompt / alias / config toggle 就能解决的 | 不是 skill 问题 |
| 用户已经把流程写成 SOP / runbook | 可以考虑 skill 化,但先确认 Q2 |

**怎么验证频率**:去查会话日志、git log、自己的笔记,数出具体次数。数不出来就说"数不出来",不要用"感觉经常"充当证据。

### Q2. 触发关键词能不能写在 1-3 句话里?

description 字段决定 Agent 何时触发。模糊 description = 永不触发 / 永远误触发。

能写出来 = 继续;写不出来 = Q1 答错了,回去再确认需求。

### Q3. 这个 skill 的"做什么"和"不做什么"边界清不清?

先做一件事:**列出现有 skill 的 description,逐个对照**。边界只有相对现有 skill 才有意义。

| 检查 | 处理 |
| --- | --- |
| 现有 skill 里有没有覆盖同一批动词? | 有 → 要么合并,要么把差异写进 Do NOT use |
| 触发现场有没有可能同时命中两个 skill? | 会 → **双方**的 description 都要写明排他边界 |
| 能不能用一句话说清"这个 skill 不做什么"? | 不能 → 边界还没想清,别建 |

如果边界说不清:

- 太宽:拆成 P0 skill + 引用
- 太窄:合并到现有 skill
- 不清:先写一版 Do NOT use this skill when,看能不能收紧;收不紧就别建

> ⚠ **边界必须写进 description,不能只写在正文。** 触发决策只看 description;正文要等触发后才被读到——写在正文的边界等于没有。

### Q4. 范围是 P0 / P1 / P2 哪一档?

| 档 | 触发频率 | 范围 | 例子 |
| --- | --- | --- | --- |
| **P0** | 每天 / 每周多次 | 单流程、单一决策 | skill-builder(本 skill)、仓库考古、PR diff 解读 |
| **P1** | 每周一次左右 | 跨流程 / 多步骤 | 工作流闭环、完整发版文档生成 |
| **P2** | 每月 / 按需 | 大而广,通用方法论 | 工程标准合集、安全审查清单 |

P0 是新 skill 的最佳档。P1 / P2 一开始就要警惕——很可能该拆成几个 P0 而不是一个大 skill。

### Q5. 你能在 15 分钟内写完 SKILL.md 一稿吗?

写不完 = 范围太大,先回到 Q4 拆。

如果 Q4 已经 P0 还写不完 = SKILL.md 超过 ~150 行,把长文背景知识移到 `references/`,正文只留决策表和 anti-pattern。

## Trigger Description 写作规范

description 是 Agent 唯一的触发器,占整张 SKILL.md 工作量的 60%。

### 六条规则（每条都带反例）

- 第一句 `Use this skill when...` 说清触发场景。**别写“AI 助手”“提高效率”“通用工具”** —— 太宽，Agent 不知道何时触发。
- 列 3-6 个具体动词 + 1-3 个对象（`整理`、`归位`、`创建`、`审阅` + `笔记`）。**别列举具体文件路径、人名、机器** —— 太窄，换环境就不触发。
- 第二句 `Do NOT use this skill when...`，边界尽量具体。**没有 Do NOT 边界几乎一定误触发**；也别堆关键词（`X、Y、Z`），那没有权重信号。
- 动词要具体。**别用“处理”“搞定”“做”** —— 没说做什么动作。
- 总长度 ≤ 800 字符，太长会触发阈值被截断。
- 真的跨机不可用时才显式声明；而**把它改造成从配置读路径之后，必须在同一次里删掉那条声明** —— 留着会自相矛盾（实测 WLRR：上面说绑定本机，下面说路径从配置解析），agent 会据此拒绍在别的机器上工作。

### 描述模板

```yaml
description: >-
  Use this skill when <触发场景 1> or <触发场景 2>.
  <这个 skill 做什么,一句话>.
  Also use it when <边界场景>.
  Do NOT use for <不该用的场景 1> or <不该用的场景 2>.
```

## Scope Discipline — 写什么 / 不写什么

| 归属 | 内容 |
| --- | --- |
| 写进 SKILL.md | 起手流程(用户在第一句问“怎么办”时就能跑)、 1-3 个核心决策表、 anti-pattern(明确的“不要做”)、 一两个例子(如果有) |
| 移到 `references/` 或 `examples/` | 长文背景知识、 完整决策树图(mermaid 放 `references/decision-tree.md`)、 工具 / 库的安装说明、 重复的引用、 跨 skill 共用写作约定(那是根 README 或单独的 style-guide) |
| **永不写进 skill** | 个人吐槽、临时想法、试验性段落、 没经过验证的“最佳实践”、 “读者复制代码”“这里要提醒读者”“给作者自己看”这类后台话术 |

## Minimum Viable SKILL.md Checklist

**先跑脚本**（机械检查，不要靠肉眼——实测中“正文 ≤ 150 行”被连续违反两次都没看出来）：

```sh
python3 scripts/validate_skill.py [skill 目录]   # 结构检查（默认扫全部 skill）
python3 scripts/check_leakage.py                 # 外发内容里的真实名称（需配 blocklist）
python3 scripts/check_pointers.py                # 找出“这事定义在别处”的指针语句
python3 scripts/preflight.py                     # 报告前跑：全部检查 + 事实快照
```

脚本覆盖：SKILL.md 存在 / 可读 / frontmatter 存在 / YAML 可解析 / `name` == 目录名 / description < 800 字符 / 含触发表达 / 含 Do NOT 边界 / 正文 ≤ 150 行 / 含表格或清单。退出码 `0` 通过、`1` 失败。

**加内容前先看余量**：脚本会报「正文余量只剩 N 行」。余量 < 10 时**先瘦身再加**（把长规则移到 `references/`）—— 硬塞的结果是三个 skill 一起顶到 150 行，下一次真实需求反而被迫先瘦身，更费事。余量提示不影响退出码，就是个提醒：瘦身由下一次真实需求触发，而不靠“等哪天有空”。

**脚本查不到的，人工确认**：

- [ ] description 里的动词是用户真会说的话，不是“处理”“搞定”这类模糊词
- [ ] Do NOT 边界是真边界，不是凑数
- [ ] 没有“个人吐槽 / 临时想法 / 试验性”段落
- [ ] **把某段改成“见别处”的指针时，逐词核对目标真的接住了内容** —— “指针写对了” ≠ “内容搬过去了”（实测：删掉 8 条风格规格改成指针，目标文件里一条都没落地）。先跑 `scripts/check_pointers.py` 列出所有指针，再逐条比对
- [ ] 同步更新根 README 索引表 + Roadmap
- [ ] 同步更新 `skills-lock.json`，新增一条 entry

## 报告纪律（写任何“已完成 X”之前）

**工具报“成功”不等于文件真的变了。** 实测过两次：

- 编辑工具回“成功替换 1 块”，文件其实没动 —— 而我把“已加入 checklist”写进了报告。
  事后核查：`git log -S"check_leakage.py" -- skills/skill-builder/SKILL.md` 无输出。
- 报告里写“SKILL.md（142 行）”，实际 74 行 —— 那个数来自印象，不是测量。
- 更隐蔽的一次：**已经跑了 preflight，快照就在眼前写着 146 行，我在提交信息里仍写了 137** ——
  用的是几步之前中间状态的记忆。所以不只是“要跑”，是**要从它的输出里复制粘贴**。

两次的共同点：**数字与存在性来自记忆，而不是测量**。而“下次记得验证”解决不了 ——
“记得”正是本仓库反复证明不可靠的东西。所以它是一条前置步骤：

**写报告前先跑 `python3 scripts/preflight.py`**（全部检查 + 事实快照 + 孤儿脚本检测）。
报告里的每个数字、每个存在性声明，都从它的输出里抄。

顺带：那个脚本会查一类容易被漏的错 —— **孤儿脚本**。`scripts/` 里有文件、检查在跑，
但从 SKILL.md 和 references 里一个字都找不到它。脚本存在、但没有任何地方叫你去跑它，
等于没接线。（实测：它第一次跑就报出了刚写的 `validate_spec.py` 没被起手流程提到。）

## Anatomy & Out-of-Scope

`SKILL.md` 默认是 skill 的全部内容;`references/` 留给长文(决策树可视化、anti-pattern 详表、跨 skill 约定)。完整目录树 + Out-of-Scope 列表见 `references/anatomy-and-scope.md`。

## Self-Review(写完前 1 分钟)

把这 3 个问题在脑子里过一遍:① 3 个具体动词(Q2)每个 Agent 都能命中?② "Do NOT use this skill when" 是真边界而不是凑数?③ 30 天后再打开这个 skill,是否仍然觉得它"显然该做"?3 个都过 = ship。
