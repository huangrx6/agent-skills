# obsidian-work-log-release-recorder

> 把**已经落地的活儿**写成 vault 里的长期记录：改了什么、跑哪条命令、怎么验证、怎么回滚，
> 并维护每周一篇的发版笔记（`发版 - <系统或项目名> - YYYY-Www.md`）。
> **不负责**笔记本身的编辑 / 移动 / 重命名 / MOC 维护 / 周报 —— 那是
> `obsidian-personal-knowledge-base`（下称 PKB）的事。

## 解决什么问题

一次会话里改完代码、发完版，聊天记录不会留在任何地方。等要回滚、换人接手、或者重跑那串命令时，
真正需要的东西恰恰最容易丢：**准确的命令、路径、配置项、验证方式和执行顺序**。

以前的做法是「事后想起来再补」，结果发版文档要么没有、要么只有一句「发布了」。
这个 skill 把它变成一次收尾动作 —— 只写**已经发生的事**，不写打算做的事。

触发语：`记一下` / `沉淀一下` / `更新知识库` / `写发版文档` / `这次发布记一下`。

## 安装

```sh
python3 tools/install_skills.py        # 默认软链，装的就是仓库那一份
python3 tools/install_skills.py --check
npx skills add huangrx6/agent-skills   # 副本方式（skills 生态的标准 CLI）
```

**必须先装 PKB**：本 skill 的强制启动清单要读它的 `references/vault-map.md` 与
`references/writing-conventions.md`，读不到就拒绝写 vault，不会凭猜测的结构动手。

```sh
python3 tools/install_skills.py
ls ~/.agents/skills | grep obsidian      # 两个 obsidian-* 都要在
```

本 skill 自身**没有脚本**，是纯规则 + 一份模板；它调用的是 PKB 的脚本（只用 Python 标准库）。

## 配置

| 配置项 | 从哪里读 | 说明 |
| --- | --- | --- |
| vault 路径 | `$OBSIDIAN_VAULT_PATH` → `~/.config/agent-skills/obsidian-vault-path` | 全仓库唯一来源（只在 PKB 的 `vault_path.py` 里解析一次），**任何文档都不写死路径** |
| 目录结构约定 | PKB 的 `references/vault-map.md` | 启动清单必读，但它是**快照**；与文件系统冲突时以 `ls` 为准 |
| 命名 / frontmatter / 链接约定 | PKB 的 `references/writing-conventions.md` | 同上，本 skill 不另立一套 |
| 发版笔记结构 | `references/release-note-template.md` | 附近已有发版笔记有更强的本地约定时，沿用它的 |

换机器或 vault 搬家只改一处，两个 skill 都跟着走。

## 快速开始

本 skill **没有自己的命令行**，入口是「对 Agent 说一句话」，例如 `这次发布记一下`、
`把刚才那些命令沉淀进知识库`、`写一下本周发版文档`。

能执行的两条命令都属于 PKB，一条确认「能不能写」，一条确认「写完有没有坏链」：

```sh
PKB=skills/obsidian-personal-knowledge-base/scripts

# vault 在哪、从哪解析出来的、目录在不在（退出码 0 = 目录存在，2 = 解析不出或不存在）
python3 $PKB/vault_path.py --explain

# 链接体检：退出码 0 = 无失效 wikilink，1 = 有失效链接，2 = vault 路径不可用
python3 $PKB/check_links.py --ignore-template
```

`--ignore-template` 不能省：Templates 下的占位符链接是有意为之，不跳过会被算成坏链。

## 能力详解

| 能力 | 入口 | 说明 |
| --- | --- | --- |
| 判断值不值得记 | 用户说「记一下」之后 | 只记**已落地**的点（跑过的命令、改过的配置、验证结果、回滚步骤）；未采纳的猜想、失败试验、原始对话不记 |
| 选归属位置 | 先探查再决定 | 先 `ls` 候选区域；项目类进 `01 Projects/<项目>/`，长期职责/运维知识进 `02 Areas/`，可复用技术知识进 `03 Resources/`；都不匹配就**问用户**，不写进不存在的路径 |
| 写周发版笔记 | `references/release-note-template.md` | 一周一篇；本周已有就更新，不再建一篇。只放结构化要点，完整脚本进依赖清单区 |
| 同步结构改动 | 同一次操作内 | 新建目录/文件会改变 vault 结构，要把 PKB 的 `vault-map.md` 或索引里对它的描述一起改掉，不留给下次探查发现 |
| 明确交出去的 | PKB | 笔记编辑 / 移动 / 重命名 / MOC 维护 / 周报（后者的规则在 PKB 的 `references/work-management.md`） |

## 目录结构

```text
skills/obsidian-work-log-release-recorder/
├── SKILL.md                        # 给 Agent 的规则（启动清单、落点决策、更新工作流）
├── README.md                       # 本文件
├── references/
│   └── release-note-template.md    # 周发版笔记模板 + 填写规则
├── scripts/
│   └── check_release_note.py       # 守本 skill 自己写下的规则（文件名/周号/骨架/重复周/已挂 MOC）
├── tests/
│   └── test_check_release_note.py  # 夹具从模板生成，模板改了测试跟着变
└── evals/
    └── evals.json                  # 8 条行为评估（触发边界 / 位置探查 / 该不该记）
```

链接失效**不在这里查** —— 那是 PKB 的 `check_links.py`（SKILL.md 明确要求跑），两者互补不重叠。

## 边界（不该用它的时候）

- 编辑 / 移动 / 重命名 / 审阅笔记，维护 MOC、索引、周计划、周报 → 用 PKB。
- `把这周做的事记一下` 这种话**两边都像**：正确反应是**先问你要哪一种**（周报，还是本周已落地的
  发版事实），问清之前不动手 —— 两个意图都合法，只有你知道要哪个。
- git 提交 / 分支 / 回滚操作本身 → 用 `git-dev-workflow`。本 skill 只记录已发生的，不执行。
- 讨论、头脑风暴、还没定的方案 → 不记。等有了确认的决定或可复用的约束再说。

## 验证

```sh
python3 tools/skill_health.py | grep obsidian-work-log-release-recorder
python3 -m unittest discover -s tests/<skill>                       # 20 条
python3 skills/skill-builder/scripts/validate_skill.py skills/obsidian-work-log-release-recorder
python3 skills/skill-builder/scripts/check_leakage.py
```

「通过」的意思：结构检查全过（frontmatter 可解析、`name` 与目录名一致、description < 800 字符、
含 Do NOT 边界、正文 ≤ 150 行）；泄露扫描不报真实名称。

**写笔记前后各跑一条机械检查**（两者互补，不重叠）：

```sh
# 守本 skill 自己写下的规则：文件名格式 / ISO 周号 / 标题与文件名一致 / frontmatter /
# 模板里的章节骨架 / 同一系统同一周不重复 / 已挂到 MOC / 没有明显密钥值
python3 skills/obsidian-work-log-release-recorder/scripts/check_release_note.py "<笔记路径>"

# 守链接：失效 wikilink 与嵌入（这是 PKB 的脚本，SKILL.md 明确要求跑它）
python3 skills/obsidian-personal-knowledge-base/scripts/check_links.py --ignore-template
```

行为层面靠 `evals/evals.json` 的 8 条（触发边界、位置以探查为准、未落地的想法不记、
与 PKB 撞车时先问）—— 但那是给人看的标尺，见下。

## 已知限制与未验证项

| 项 | 状态 |
| --- | --- |
| **eval 只是标尺，没有自动跑** | 8 条 eval 的期望输出是文本，仓库里没有任何东西执行它们并判分 |
| **脚本只守「格式与挂载」，不守「内容对不对」** | `check_release_note.py` 能查文件名、周号、标题、frontmatter、章节骨架、重复周、是否挂到 MOC、有没有明显密钥值。它**不能**判断你记的事实准不准、该记的有没有漏 —— 那仍然靠人。 |
| **链接失效不归它管** | 那是 PKB 的 `check_links.py`（SKILL.md 已要求跑），两者互补、不重叠。 |
| **没有真实发版笔记样本** | 探查发现 vault 里现有发版笔记 **0 篇**，所以「校验器」只能按模板与 SKILL.md 写明的规则做 —— 没有发明格式。拿到第一篇真实笔记后要回头对照一次。 |
| `02 Areas/` 目前只有索引文件，没有领域目录 | **已核实**（`ls` 只看到一个索引 md）。SKILL.md 里「部署运维类发布通常归到 `02 Areas/<领域>/<子主题>/`」现在**没有现成归属**，探查不到必须问用户，不能写进记忆中的旧路径。SKILL.md 自己也标了 ⚠️ |
| `04 发布依赖清单` | **vault 里不存在**（按目录名搜到 0 个），但 SKILL.md 与模板都引用它放完整脚本/配置片段。第一次真用之前得先确认这个目录建在哪 |
| 周发版笔记的命名与模板 | **未实测**：vault 里现有发版笔记数量为 **0**，模板没有被真实使用过；ISO 周编号也只按约定写，没有历史笔记可对照 |
| 「结构改动要同步文档」执行起来有多难 | 要同时改 vault 里的索引 + PKB 的 `vault-map.md`，目前靠人记得，**没有任何检查会拦住漏改** |
| 正文余量 | 143 行 / 上限 150（余量 7 < 10）：下次要往正文加规则前，先做 references 瘦身 |
