# obsidian-personal-knowledge-base

> 在一个 **PARA + MOC** 结构的 Obsidian 知识库里干活：新建 / 补写 / 更新 / 审阅 / 归位 / 移动 / 重命名笔记，
> 维护 MOC、索引、模板、周计划、周报、项目主页、领域主页、学习笔记与技术资源笔记。
> **不干什么**：不记录「已完成的工作」与发版事实（那是 `obsidian-work-log-release-recorder`），
> 不做纯讨论与头脑风暴，也**不一次服务多个 vault**。

## 解决什么问题

知识库不靠「记住目录结构」来维护 —— 目录会被重置、重组、改名，所以这个 skill 每次都先探查真实文件再动手。

真实的痛点是三件：

1. **这篇该放哪**：Inbox / Projects / Areas / Resources / Archive 之间怎么选，以及「两个地方都像」时怎么办。
2. **同一类内容在不同目录该按哪套写法**：Projects/Areas 要短、要能看状态；Resources 要能长期复用、要有可运行示例。
   把学习笔记的深度标准套到项目计划上，两边都会写坏。
3. **移动或改名之后**：全库的 wikilink 会静默失效；`.obsidian/` 配置里的绝对路径失效更隐蔽 ——
   插件的读取失败只打 console，界面零提示（这个坑真发生过：导出 PDF 静默地不带自定义样式，而且错误路径每次导出被重新固化）。

触发语：`把这段存到知识库` / `整理一下我的笔记` / `这个该放哪` / `审阅一下这篇` / `检查失效链接` / `更新项目区索引`。

## 安装

```sh
python3 tools/install_skills.py                      # 默认装软链（推荐，改仓库即时生效）
python3 tools/install_skills.py --check              # 看指向对不对
npx skills add <repo> --skill obsidian-personal-knowledge-base --agent claude-code --global   # 副本方式
```

依赖：**只用 Python 标准库**，不需要 pip install。

## 配置

| 配置项 | 从哪里读 | 说明 |
| --- | --- | --- |
| vault 路径 | `$OBSIDIAN_VAULT_PATH` → `~/.config/obsidian-vault-path` | 后者是单行文本文件，内容就是路径 |

**一次只服务一个 vault**：没有「多库」配置。两个 skill 与三个脚本都从上面这一处解析，
换机器或 vault 搬家只改这里一处 —— 这个路径以前散在 10 个地方，漏改一处就会**静默用错路径**。
都解析不出时脚本会报错并给出配置指引，**不会退回任何硬编码路径**。

```sh
# 二选一
export OBSIDIAN_VAULT_PATH="/path/to/your/vault"
echo "/path/to/your/vault" > ~/.config/obsidian-vault-path

python3 scripts/vault_path.py --explain     # 确认：解析结果 + 来源 + 目录是否存在
```

## 快速开始

```sh
cd skills/obsidian-personal-knowledge-base

python3 scripts/vault_path.py --explain            # 路径 / 来源 / 目录是否存在；退出码 0 或 2
python3 scripts/check_links.py --ignore-template   # 全库失效 wikilink 与嵌入；0 无 / 1 有 / 2 路径解析失败
python3 scripts/check_paths.py                     # .obsidian/ 配置里的失效绝对路径
python3 -m unittest discover -s tests              # 19 条脚本回归
```

```text
$ python3 scripts/vault_path.py --explain
/path/to/your/vault
来源:配置文件 ~/.config/obsidian-vault-path
✓ 目录存在
```

`check_paths.py` 可能多打一行「合计：N 个不存在的目录」，**那不影响退出码** —— 目录可能本来就还没建，脚本只提示。

## 能力详解

| 能力 | 入口 | 说明 |
| --- | --- | --- |
| 归位判断 | 探查目标区域 + `references/vault-map.md` 的归位规则 | 只选**一个最稳定的主家**，其他地方用链接引用 |
| 新建 / 补写笔记 | 按目标目录加载对应 references | 编辑已有笔记时保留原 frontmatter；新建的笔记「最小但有用」 |
| 审阅已有笔记 | 按笔记**所在目录**的规则审阅 | 不套一套全局写法；Resources 的深度标准不会自动套到 Projects |
| 移动 / 重命名 / 重编号 | 改完同步 MOC、索引、wikilink | 结构性改动后跑一次链接检查 |
| 结构检查 | `scripts/check_links.py`、`scripts/check_paths.py` | 用脚本而不是临时扫描：临时扫描会把代码块里的 `[[ ... ]]` 当 wikilink、还会漏掉图片嵌入 |
| 地图漂移 | `references/vault-map.md` 的漂移记录 | 文档与真实不符时**以文件系统为准**；同一段累计 3 次仍未更新会主动提议更新 |
| 目录专属规则 | `references/work-management.md`、`references/resource-notes.md` | Areas/Projects 用轻量工作管理规则；Resources 才用深度学习笔记规则 |

细节手册在 `references/`：`vault-map.md`（地图与归位）、`writing-conventions.md`（命名/链接/排版）、
`work-management.md`（周计划周报与交付）、`resource-notes.md`（仅 Resources 的写作标准）、
`research-and-synthesis.md`（仅 Resources 的研究流程）、`structural-checks.md`（两类检查的用法）。

## 目录结构

```text
skills/obsidian-personal-knowledge-base/
├── SKILL.md          # 给 Agent 的规则（触发、起手流程、任务分流）
├── README.md         # 本文件
├── references/       # 6 个细节手册（见上）
├── scripts/          # vault_path.py（路径唯一来源）+ check_links.py + check_paths.py
├── tests/            # 19 条回归，守两个检查脚本的误报与漏报
├── evals/            # 6 条触发与行为评估
└── agents/           # openai.yaml（Agent 接口描述）
```

## 边界（不该用它的时候）

- 要记录**已完成**的工作、落地事实、发版文档 → 用 `obsidian-work-log-release-recorder`。
- 纯讨论 / 头脑风暴 / 没有笔记要建要改 → 不需要 skill，直接聊。
- 要画技术图 → 用 `diagram-authoring`（本 skill 只负责笔记里的配图清单与图片引用）。
- 要读写本机文件或提交 git → 用 `git-dev-workflow`。
- 请求在「编辑已有笔记」与「记录已完成工作」之间模糊（比如同时出现「发版」和「整理」）→ **先问清是哪一种**，不猜。

## 验证

```sh
python3 -m unittest discover -s tests        # 19 条，全绿
python3 scripts/check_links.py --ignore-template
python3 scripts/check_paths.py
```

「通过」的意思：19 条测试守的是两个检查脚本的**误报与漏报** —— 代码块里的 `[[ "$a" == *"$b"* ]]`
不算 wikilink、只索引 `.md` 会让图片嵌入假失效、含空格的路径不能被截断。链接检查输出 `0` 表示无失效链接。

## 已知限制与未验证项

| 项 | 状态 |
| --- | --- |
| 一次只服务一个 vault | 设计如此（不做多库） |
| `vault-map.md` 是快照、不是权威结构 | 设计如此：先探查再对照，冲突时以文件系统为准 |
| 笔记**内容**质量（深度够不够、该不该展开） | **无机械校验** —— 脚本只查链接与路径；内容判断靠审阅规则与 evals，不是自动的 |
| `check_paths.py` 对「目录不存在」 | 只提示、不判失败（目录可能本来就还没建），需要人看那一行 |
| 批量重命名 / 重编号 | 没有脚本，靠按规则手工改 + 改完跑链接检查；**未实测**过大范围重编号 |
| `check_paths.py` 的扫描范围 | 刻意只含 `.obsidian/` 下的配置文件（笔记正文与插件打包 JS 都排除），范围外的问题它不会报 |
