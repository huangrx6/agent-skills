# 知识库地图

本技能操作一个由配置决定的 vault（解析顺序见 SKILL.md 的 Prerequisites）。

这个库采用 PARA + MOC 结构。

> **⚠️ 本文档是快照，不是权威结构。**
> 每次任务开始前先对目标区域做单层探查（`ls` / `rg --files`），用真实结果覆盖本文档的结构假设。冲突时以文件系统为准。
> 本文档只用于导航和归位参考，不用于直接信任。
>
> 最近一次完整探查：**2026-09-12**

## 顶层结构

| 区域 | 入口文件 |
| --- | --- |
| `00 Inbox` | `00 Inbox/收件箱 - 说明.md` |
| `01 Projects` | `01 Projects/项目区 - 索引.md` |
| `02 Areas` | `02 Areas/领域区 - 索引.md` |
| `03 Resources` | `03 Resources/资源区 - 索引.md` |
| `04 Archive` | `04 Archive/归档区 - 说明.md` |
| `90 Assets` | `90 Assets/Attachments`（附件、图片、绘图） |
| `99 System` | `99 System/首页.md`、`99 System/00 MOC - System.md` |

> 入口文件本身也可能被改名、移动或重建。本节只记定位，不记内容——用前先探查。

## 归位规则

| 区域 | 用于 | 不用于 |
| --- | --- | --- |
| `00 Inbox` | 未分类捕获、临时笔记 | 已有明确归属的长期笔记 |
| `01 Projects` | 有明确交付结果、能完成或关闭的工作 | 长期持续责任 |
| `02 Areas` | 长期责任、周期性维护 | 一次性交付 |
| `03 Resources` | 可复用知识、学习笔记、技术资料 | 项目状态、周计划、周报 |
| `04 Archive` | 已不活跃但需要保留的历史内容 | 当前活跃工作 |
| `90 Assets` | 附件、图片、绘图 | 正文笔记 |
| `99 System` | 模板、工作流、知识库规则 | 用户知识内容 |

如果一篇笔记可能放在多个地方，只选一个主家，其他地方用链接引用。

## 当前 Projects 结构

**本文件不枚举具体项目名。** 项目会增删改名，枚举一次就过期一次；而且把真实项目清单写进 skill，与本 skill 的核心设计（probe-first：地图给结构，真实内容靠探查）相矛盾。

要拿真实结构，探查：

```sh
ls -d "$VAULT/01 Projects"/*/
```

**新增项目时的约定**：项目目录使用数字前缀方便扫描（`NN 项目名/`）。需要持续跟踪的活跃项目，应有一篇 `项目 - 名称` 主页。会议记录、实现记录、交付记录只有在直接服务该项目结果时才放入对应项目目录。

**索引入口**：`01 Projects/项目区 - 索引.md`。

## 当前 Areas 结构

> **当前状态（2026-09-12 探查）**：`02 Areas/` 下**没有领域子目录**，只有一个索引文件。历史上存在的领域目录已被重置或迁移。Agent 处理 Areas 相关操作前，必须先 `ls` 真实目录，不能依赖历史假设。

**历史领域**：曾有两三个领域目录，现在都已不在。**具体名字不在这里记录** —— 探查 `ls "$VAULT/02 Areas"` 即知现状。

> ⚠️ 上述领域目录当前**不存在**。任何写入 `02 Areas/<领域>/` 的操作都必须先探查确认目录存在，不存在时询问用户建在哪里。

**新增领域时的约定**：领域 MOC 可以链接到 `01 Projects` 的活跃项目主页，但不要在领域页里重复维护完整项目计划。周期性记录（周计划/周报）放在领域目录下的 `NN 周计划/` / `NN 周报/` 子目录。

**索引入口**：`02 Areas/领域区 - 索引.md`（2026-09-12 已建，已写明当前为空及新建领域的步骤）。

## 当前 Resources 结构

入口：

- `03 Resources/资源区 - 索引.md`

资源区顶层分组使用数字排序：

```text
00 计算机基础/
01 算法与数据结构/
02 操作系统与 Linux/
03 网络协议/
04 数据库与存储/
05 编程语言/
06 后端框架与中间件/
07 前端与界面/
10 开发环境与工作流/
20 云原生与基础设施/
30 数据平台与业务建模/
40 大模型与应用开发/
```

放置可复用技术知识时，优先查看 `03 Resources/资源区 - 索引.md` 里的判定表。

## 系统笔记和模板

重要笔记：

- `99 System/首页.md`
- `99 System/工作流.md`
- `99 System/命名规范.md`
- `99 System/00 MOC - System.md`（System 区自身的 MOC）

Templater 脚本：

- `99 System/Templater Scripts/`（Templater plugin 的 JS 脚本目录）

重要模板：

- `99 System/Templates/模板 - 项目.md`
- `99 System/Templates/模板 - 领域.md`
- `99 System/Templates/模板 - 资源笔记.md`
- `99 System/Templates/模板 - 文献笔记.md`
- `99 System/Templates/模板 - 会议.md`
- `99 System/Templates/模板 - MOC.md`
- `99 System/Templates/模板 - 日记.md`
- `99 System/Templates/模板 - 周计划.md`
- `99 System/Templates/模板 - 周报.md`
- `99 System/Templates/模板 - 周复盘.md`
- `99 System/Templates/动作 - 整理当前笔记图片.md`（一次性动作模板）

## 不要动的东西

| 路径 | 为什么不能删 |
| --- | --- |
| `Icon\r`（Vault 根，0 字节） | macOS **自定义文件夹图标**标记文件，配合根目录的 `com.apple.FinderInfo` 属性生效。看起来像空文件垃圾，删了会丢失 Vault 图标。它真实文件名带回车符，`ls` 显示为 `Icon`。 |
| `.obsidian/` | Obsidian 配置（主题、插件、工作区） |
| `.theme-publish/` | 自定义主题的发布仓库（Haru Paper），内部有自己的 `.git` |
| `90 Assets/Attachments/` | 全库图片附件，大量笔记靠它解析嵌入 |

> 清理 Vault 前先确认文件用途。名字奇怪 / 大小为 0 不等于可删。

## 版本控制

本 vault 已用 git 管理（2026-09-12 初始化）。改动前不需要额外备份，但要知道：

- **`.gitignore` 排除了 `.obsidian/plugins/feishu-lark-cli-sync/data.json`**——那里存着每个同步目录的飞书文档 token，是真实凭据。不要把它加进版本控制，也不要用 `git add -f` 绕过。
- 删除/移动笔记用 `git rm` / `git mv`，这样可回滚；不要直接 `rm`。
- 大规模结构调整（删目录、改编号）建议单独提交，commit message 写清原因，方便日后 `git revert`。
- 工作区状态文件（`workspace*.json`、`*冲突文件*.json`）被忽略，这是有意的。
- **提交时跑两道检查**（`.githooks/pre-commit`），两者阻塞度不同：
  - **链接检查**（只在提交涉及 `.md` 时运行）：**不阻塞**——失效链接在 vault 里经常是有意为之（先写笔记、目标还没写）。
  - **配置路径检查**（每次都跑）：**阻塞**——`.obsidian/` 配置里指向不存在文件的值从来没有“故意这样写”的解释，插件会静默忽略它（真实案例：vault 搬家后 better-export-pdf 的 cssSnippet 失效，PDF 静默地不带自定义样式）。引用目录而非文件的路径只看不拦。
  检查器来自 agent-skills 仓库的 PKB skill；位置可用 `git config hooks.agentSkillsRepo` 或 `$AGENT_SKILLS_REPO` 覆盖。
- 换机器后需执行一次 `git config core.hooksPath .githooks` 才会生效。

## 探查命令示例

任务开始前对目标区域做单层探查：

```sh
VAULT=$(python3 scripts/vault_path.py)   # 路径来自环境变量或配置文件

# 顶层区域
ls "$VAULT/01 Projects"
ls "$VAULT/02 Areas"

# 某个 Resources 主题下有什么
rg --files "$VAULT/03 Resources/40 大模型与应用开发" | head -30

# 找某个主题的 MOC / 索引
ls "$VAULT/03 Resources/07 前端与界面" | grep -E "MOC|索引"

# 校验某个路径是否真的存在（写之前必做）
test -e "$VAULT/01 Projects/<项目名>" && echo exists || echo missing
```

### 探查开销上限

探查的目标是“拿到足够做决策的信息”，不是把目录整个列出来。

| 探查结果 | 处理 |
| --- | --- |
| ≤ 约 30 行 | 直接看 |
| > 约 30 行 | **只列子目录名**（`ls -d .../*/`），不列文件；要看细节时再单独列某个子目录 |

超过阈值时不要把整个列表读进上下文 —— 既慢，又会淹没真正要判断的结构信息。这条规则是防 vault 变大后 probe-first 静默失效的。

```sh
# 大目录：只列子目录名
ls -d "$VAULT/03 Resources/40 大模型与应用开发"/*/

# 需要细节时再单独列某个子目录
ls "$VAULT/03 Resources/40 大模型与应用开发/13 RAG 系统"
```

## 漂移记录

探查发现本文件某段与实际不符时，在下面给该段 +1。**同一段落累计 3 次**而该段仍未更新时，主动向用户提议“要不要现在更新 vault-map 的这一段？”；该段更新后把计数清零。

存在的意义：probe-first 让 skill 不会因为文档过期而写错，但也让“文档永远没人更新”变得无害 —— 结果就是腐坏速度变慢而不是停止。这张表把更新从“等用户想起”变成“skill 主动提”。

| 段落 | 累计不一致次数 | 最近一次 |
| --- | --- | --- |
| （暂无） | | |

## 重置规则

如果用户说某个区域被删除、重置或调整，以文件系统和当前索引为准，不以本地图旧信息为准。结构稳定后再更新本文件。
