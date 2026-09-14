# ROADMAP

> 这份文档回答两件事：**已有的 skill 接下来优化什么**、**该不该新建 skill**。
>
> **数字不在这里抄一份** —— 手抄的表必然过期（本仓库已经栽过一次：根 README 的 Roadmap
> 还写着「P1 待开工」，而那几个早就做完了）。现状一律现算：
>
> ```sh
> python3 tools/skill_health.py                              # 规模 / 余量 / 缺 README / 缺 evals / 死文件
> python3 skills/skill-builder/scripts/validate_skill.py     # 结构硬错误（挡提交的那道）
> ```

## 怎么读

- 每条都带**判据**（能跑的命令或明确的前置条件）。没有判据的写进「候选」，不写进「该做」。
- 「值不值得建」的门槛跟 `skill-builder` 一致：**会不会高频触发**。低频的宁可写进已有 skill，
  也不要新建 —— 仓库立身之本是「不做 11 个只用 2 个」。
- 「明确不做」单独一节。不写下来的话，每次讨论都要重新权衡一遍。

---

## 一、优化方向（已有 skill）

### P0 · 有明确判据

已完成（2026-09-13）：

| # | 做了什么 | 结果 |
| --- | --- | --- |
| 1 | **回填 6 个 skill 的 README** | 体检的「缺 README.md」从 5 个降到 **0**；六份章节结构完全一致（都按 `skill-readme-template.md`） |
| 4 | **清死文件** | 删了 10 个没人引用的图标 svg（去掉 assets 约定后留下的）；体检的「死文件」从 10 降到 **0** |
| 5 | **pingcode 建项目实测** | 在真实租户建了一个项目（scrum，带描述与起止日期），`project list` 从 1 个变 2 个 |
| 3 | **补 2 个缺 evals 的 skill** | 给 diagram-authoring（6 条）与 skill-builder（6 条）写了 `evals/evals.json`；体检的「缺 evals」从 2 降到 **0** |

还开着：

| # | 做什么 | 判据（怎么知道还没做） | 怎么做 |
| --- | --- | --- | --- |
| 2 | **给余量不足的 skill 做 references 瘦身** | 「正文余量偏紧」非空（具体哪些跑命令看）。**已按真实需求做过一次**：往 `skill-builder` 加第 7 条规则后只剩 2 行，于是把报告纪律的「为什么」搬进 `references/reporting.md`（正文 148 → 137，余量 2 → 13）。其余三个（excalidraw 3 / PKB 4 / WLRR 5）**等各自的真实规则到来再搬** | 搬法见 `skills/skill-builder/references/slimming.md`；核心判断是「搬为什么，不搬什么」 |

> 体检里现在只剩「正文余量偏紧」一行。**它是刻意不清零的**：瘦身由下一次真实的「要往正文加规则」
> 逼出来，而不是现在硬搬一批（硬搬的结果是正文与 references 都变得零碎）。

### P1 · 需要一点新东西才能做（已全部完成）

| # | 做什么 | 为什么它排在这里 |
| --- | --- | --- |
| 6 | ~~触发日志~~ | ✅ **已做**：`tools/skill_trigger_log.py`（见下面第三节）。不需要新埋点 —— pi 的会话记录里本来就有 `inline-skill` / `loaded-skill` 两类信号，历史数据直接能算 |
| 7 | ~~把 `skill_health.py` 接进 pre-commit~~ | ✅ **已做**：接在 `.githooks/pre-commit` 第 5 段，**只提示不阻塞**（它报的是「该优化什么」，不是「代码错了」；拿它挡提交会把人逼到 `--no-verify`，连前面四道真防线一起丢掉）。配套 4 条回归测试，守的正是「体检报出内容时提交仍然成功」 |
| 8 | ~~给 WLRR 补机械部分，或者明确它不补~~ | ✅ **已做**，但结论与当初写的不同：读完材料发现 WLRR **不是「0 机械验证」** —— 它已经要求跑 PKB 的 `check_links.py`。真正没被守住的是它**自己写下的另外几条规则**（文件名格式、同周不重复、必须挂到 MOC）。所以补的是这些（`check_release_note.py`，章节骨架从模板文件读、不另抄），20 条测试；链接失效仍归 PKB，两者互补 |
| 9 | ~~重看 5 个 skill 的 description~~ | ✅ **已做**：查出了原因（两个「中文 0 字」的描述就是从没自动触发的两个），补了中文触发词，并把这条写进 `skill-builder` 的描述规则。PKB 与 WLRR 为何仍未自动触发→留到下一次日志 |

### P2 · 等数据再说

| # | 做什么 | 等什么 |
| --- | --- | --- |
| 9 | pingcode 的扩展面（复杂搜索 / 批量 / 附件 / 测试管理 / 需求 / 工单） | 等你在真实工作里真的被 `api` 逃生口卡住，再封装成子命令 |
| 10 | `diagram-authoring` 的图标库与其它视觉细节 | 等它真的被高频使用，而不是「有空就打磨」 |

---

## 二、触发日志读出来的

现算：`python3 tools/skill_trigger_log.py`。**先说样本量：窗口 2026-08-25 → 09-13、9 个会话** ——
这是方向，不是判决。

| skill | 自动触发（description 生效） | 显式加载（`$name`） |
| --- | --- | --- |
| excalidraw-diagram&nbsp;※ | 2 | 0 |
| git-dev-workflow | 0 | 2 |
| obsidian-personal-knowledge-base | 0 | 1 |
| obsidian-work-log-release-recorder | 0 | 1 |
| skill-builder | 0 | 1 |
| pingcode | 0 | 0（刚建） |

> ※ **2026-09-14 改名为 `diagram-authoring`**（原因：同一个 skill 要出 Excalidraw 与 draw.io 两种格式，
> 名字不该带工具名）。上表是**改名前的历史数据，不改写**；`tools/trigger-baseline.json` 里写了
> `aliases`，所以 `--compare` 会把两边合并计数 —— 否则一次改名会被读成「旧 skill 停用、新 skill 从零开始」。

**最值得注意的一条：6 个 skill 里只有一个被「自动触发」过。**
其余全部靠显式 `$name` 调用 —— 也就是说，那些 skill 的 `description` 在**自动触发**这件事上
目前没在干活。两种可能，处理方式完全不同：

1. **description 写得不对**（触发词不是你真会说出口的话）→ 按 skill-builder 的六条规则逐条过一遍再改。
2. **它们本来就该显式调用**（git 写操作、发版记录这种「我不想让它自作主张」的场景）→
   那就承认它们是**显式调用型**，把 description 往那个方向写清，**不再假装它会自动触发**。

这两种不能靠猜 —— 先改一两个词，再看三周后的日志。

**后来查出了更具体的原因**：description 里**中文 0 字**的两个 skill（`git-dev-workflow`、`skill-builder`）
正是从未自动触发的两个；而中文触发词最多的 `excalidraw-diagram` 自动触发了 2 次。
也就是说那两个不是「本来就该显式调用」，而是**描述里没有一个你真会说出口的中文词**（它们原本是纯英文）。
已处理：

- 给这两个补上中文触发词（`提交` / `建分支` / `建个 skill` / `这个 skill 老是不触发` …），见 `ASKILL-12`；
- 把「必须列出人真会说的中文说法」加进 `skill-builder` 的描述规则（第 7 条），
  以后新建的 skill 不会再重复这个错 —— 这是**改下一次的成因，而不只是改这一次的结果**。

还剩一个未解的问题：PKB 与 WLRR 的 description 里已经有中文触发词，却仍然只被显式调用过。
它们到底是「描述还不够贴近原话」还是「这些场景用户习惯直接点名」—— 等下一条日志才有答案。

另两条：

- 改名或删掉的 skill（如 `design-git-workflows`）仍会从历史记录里出现，工具会单独列出来，不静默丢掉。
- `pingcode` 是 0 —— 它刚建。**0 不代表没用，只代表「这个窗口里没有」**，所以输出里必须带窗口与样本量。

---

## 三、候选新 skill

判据统一：**一次会话里会不会重复做 ≥2 次**；拿不到这个证据就先不动手。

### ① 触发日志 / 使用统计 · ✅ **已做**

- **做成了什么**：`tools/skill_trigger_log.py`。不需要新埋点 —— pi 的会话记录里本来就写了两类信号：
  `inline-skill`（按 description **自动内联**，真·自动触发）与 `loaded-skill`（工具**显式加载**，`$name` 那种）。
  所以历史数据直接能算，装个 hook 反而多一处会坏的零件。
- **口径**（输出里会自己声明）：只统计 pi（这台机器没装 Claude Code / Codex）；排除 `forks/`
  与 `subagent-artifacts/`；统计的是磁盘上还留着的会话，不是全部历史。
- **副产品**：写它的过程拓出我自己的一个口径 bug —— 第一版用 `"/forks/" in dirpath` 判排除，
  而那个写法**匹配不到 `.../forks` 本身**（结尾没斜杠），于是 fork 副本全被算了进去：
  文件数从 **9 虚报成 24**、所有频率翻了一倍。测试里那条「排除 fork 副本」就是为它写的。

### ② 需求 → 工作项树（`pingcode-plan`）· 建议**并入 pingcode**，不新建

- **想解决什么**：把一段需求描述 / 会议记录拆成「史诗 → 特性 → 用户故事 → 任务」并按层级建进 PingCode。
- **证据**：你的原话是「AI 自动创建项目、史诗、故事、任务、缺陷等条目」。而且这次实测暴露了层级约束（这个项目里**用户故事的父项不能是史诗**，得是特性）—— 批量建树前必须先校验父项类型，正是脚本该干的活。
- **为什么并入而不是新建**：它和 `pingcode` 共用凭据、端点表、解析层；单独建一个 skill 只会多一份触发竞争，还多一处要同步的端点表。
- **形态建议**：`workitem create-plan --file plan.yaml`（先 dry-run 打印整棵树与层级校验结果，确认后逐条建，建完回显编号映射）。

### ③ 周计划 ↔ PingCode 迭代（`weekly-plan`）

- **想解决什么**：Obsidian 里写的周计划，和 PingCode 里的迭代/任务，两边对不上（计划了没建任务、建了任务没进计划）。
- **证据**：你已经有 PKB（计划侧）和 WLRR（回顾侧），而执行侧在 PingCode —— 三者目前互不相通。
- **⚠ 触发日志不支持它**：窗口内 PKB 与 WLRR 各只被用过 **1 次**。所谓「先写笔记再画图 / 再建任务」这条链路，
  在数据上还没有形。→ **先放着**，等三周后再看一次日志；两个 Obsidian skill 都涨到每几周多次再说。
- **风险**：容易做成「双写」，那是典型的越做越错；真要做得先定**谁是唯一事实来源**。

### ④ 笔记 → 图（`obsidian-excalidraw-bridge`）

- **想解决什么**：笔记里已经把结构写清楚了，画图还要再说一遍。
- **⚠ 触发日志目前也不支持**：excalidraw-diagram 窗口内自动触发 2 次，但 PKB 只 1 次，
  两者没有同现的迹象。这条要成立，得先看到「同一件事里先笔记后图」的真实序列。
- **为什么可能不该建**：`excalidraw-diagram` 已经接受「一段说明」作为输入；桥的价值只在「笔记结构比口述更完整」时才存在。

### ⑤ `skill-doctor` · ✅ **已做，而且确实是「加 references 而不是新建 skill」**

当初的预测是「更可能的结果是给 `skill-builder` 加一个 references，而不是新建 skill」。
实测下来就是这个结论：

- **加的是** `skills/skill-builder/references/slimming.md`（怎么搬、搬什么、留什么、搬完怎么机械核对）
- 没建新 skill —— 因为「读体检输出并行动」就是 `skill-builder` 已有的职责（评审现有 skill）
- 顺带把 `skill-builder` 自己搬了一次（报告纪律的「为什么」→ `references/reporting.md`，
  正文 148 → 137），因为它的真实需求已经发生了

### 明确不建议

| 想法 | 为什么不 |
| --- | --- |
| 周报 / 汇报生成 | 与 `obsidian-work-log-release-recorder` 重叠（它管的就是「已完成事实的沉淀」）。真需要就改它，别再开一个 |
| 通用第三方 API 包装（「给 X 平台做个 skill」） | `pingcode` 那轮已经证伪：把 path 交给调用方=把正确性推给模型，参考实现就是这么写错 4 条路径还全绿的 |
| 定时任务类 skill（每天自动跑） | Agent 会话是事件驱动的，定时能力属于调度器不属于 skill |
| 再建一个 Obsidian 相关 skill | 已经有两个，第三个的边际价值最低 —— 除非候选 ① 的日志明确说某类操作频繁且现在没覆盖 |

---

## 四、判断该不该建（复用现成判据）

新 skill 一律先过 `skill-builder` 的那几个问题，答案写进它的 `references/anatomy-and-scope.md` 里：

1. 触发描述能不能不靠「希望它触发」而写清楚？触发词是用户真会说的吗？
2. 它和已有 skill 的边界在哪（必须能写出 Do NOT）？
3. 核心行为能不能被机械验证（测试 / eval）？不能的话，凭什么说它工作？
4. 一年后还有人会用它吗 —— 还是解决了这一周的问题？

四条里任意一条答不上来，就停在候选区，不动手。

---

## 五、PingCode 镜像

这份 roadmap 同时镜像在 PingCode 的项目里，方便当待办跟：

```sh
P=skills/pingcode/scripts/pingcode.py
python3 $P workitem list --project ASKILL --limit 50    # 看全部（当前 32 条：4 史诗 / 7 特性 / 11 故事 / 3 任务 / 7 缺陷）
python3 $P project progress --project ASKILL            # 看进度
```

四个史诗与本文档的章节一一对应：

| PingCode | 对应本文档 |
| --- | --- |
| `ASKILL-1` 触发质量：让 skill 真的会被触发 | 第二节 + P1 #9 |
| `ASKILL-2` 仓库机械化：把已知的检查接上 | P1 #7、#8 |
| `ASKILL-3` pingcode skill 收尾 | P2 #9 |
| `ASKILL-4` 候选新 skill（等数据） | 第三节的候选 |

**更细的层级不在本文档里拄一份** —— 工作项会被改标题、改状态、拆任务，拄一份必然漂移。
要看现状就跑上面那条命令。

> 建这个镜像时本身又抓到一个缺陷（`ASKILL-27`）：新建项目后字典缓存未失效，
> 紧接着建工作项会报「没有叫 X 的项目」—— 已修（`resolve.invalidate()`）。

---

## 六、当前的执行顺序

```text
已完成：回填 6 份 README ・ 清死文件 ・ 补 2 个 evals ・ 触发日志 + 基线 ・ 重看 description
         ・ 体检接进 pre-commit ・ pingcode 建项目实测 + 镜像 32 条工作项
         ・ 补 create-plan / search / bulk-update / 评论附件 ・ WLRR 机械校验
         ・ 行为 eval **6 个 skill 全跑过一遍**（2026-09-14，共 41 次运行）—— 查出 9 个真缺陷：
           3 个代码 bug（pingcode --state 两处、gen_endpoints --check 跨天虚报、
           excalidraw groups[].style 静默失效）、4 处规则表述缺口、2 处 eval 自身的设计缺口
         ↓
1. 三周后跑 skill_trigger_log.py --compare   ← 基线已存，只需等时间
2. 其余候选（pingcode-plan 已做；weekly-plan / 桥等数据）
3. references 瘦身    ← 不主动做；两个 skill 已只剩 2~5 行余量，下次加规则时会先被迫瘦身
```

## 七、行为 eval 怎么跑（实测出来的，不是设想）

`evals.json` 建起来之后一直没跑过。2026-09-14 第一次真跑（skill-builder 6 条、
git-dev-workflow 7 条，共 13 条全过），过程里踩到两件必须记住的事：

1. **跑之前把仓库/ skill 复制出去，并删掉 `evals/`** —— 实测被测 Agent 会翻到
   `evals/evals.json` 直接读到自己那条 `expected_output`（skill-builder 第 6 条那次判定
   因此作废，隔离重跑后才有效）。能跑干净的机例：一次性 git 仓库（git-dev-workflow）、
   浅克隆的仓库副本（skill-builder）。
2. **一条 eval 一个沙箱**。同一轮里 6 个子 agent 共享一个仓库时，会互相改文件（其中一个
   把另一个新建的 references 当成「别人写的并发改动」）。

已知的覆盖缺口（也是跑出来的，已补两条用例）：git-dev-workflow 原来的 7 条里，
「worktree 撞上已有路径 → 拒绝」与「未提交内容救不回」这两条规则从未被触发过 ——
现在补成第 8、9 条。

### vault 类 eval（PKB / WLRR / excalidraw）怎么隔离

落点在 Obsidian 库上的 skill 不能只靠「不要碰真库」这句话，要真隔离：

```sh
cp -cR "$VAULT" /tmp/eval-vault/<name>      # macOS/APFS 写时复制克隆
```

实测：2.9 G 的库（含 .git）**0.93 秒克隆完、只多占 3 MB**，而且写入是真隔离的
（改克隆里的文件，真库的哈希不变 —— 已验证）。所以「一条 eval 一个库」在这里成本几乎为零，
不必为了省空间而串行化或删内容。

> ⚠️ **一个真的泄漏点**：`vault_path.py` 在没设 `$OBSIDIAN_VAULT_PATH` 时，会回退到
> `~/.config/obsidian-vault-path` —— 那是**真库**。本轮就有一个子 agent 这么解析到了真库
> （它如实报告了，且只读没写）。所以：每条任务的**每一个命令**都要带 env，
> 并且要把「绝对不要碰 <真库路径>」写成硬禁止，而不是只靠 env。

本轮 14 个 agent 跑完，真库的 HEAD 与未提交项**与跑之前完全一致**（HEAD `65b2f2b` +
两个运行前就存在的未跟踪文件）。

### 第一轮 vault 类 eval 又拓出一条：prompt 不能依赖上文

PKB #4、PKB #6、WLRR #8 的原 prompt 里分别写着「**这段东西**」「**刚整理的笔记**」
「**这次的**发版记录」—— 都指向上文，而 eval 是**隔离跑**的：子 agent 只能如实回答
「没看到正文」。三条已改成自包含（把正文/事实直接写进 prompt）。

第 1 件就是当初那个「真正改变后续所有判断」的那一件（触发日志）—— 它已到位，基线已存，
剩下的事只有等时间：三周后跑一次 `--compare`，看看自动触发的 skill 数有没有真的上去。
