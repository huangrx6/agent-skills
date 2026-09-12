# 知识库地图

本技能操作 `/Users/huangrx6/Documents/obsidian`。

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

> **当前状态（2026-09-12 探查）**：3 个项目目录，6 篇笔记。

| 目录 | 笔记 |
| --- | --- |
| `01 Projects/某项目目录/` | 某内部系统、某环境、某内部系统 |
| `01 Projects/01 某项目/` | 某服务说明 |
| `01 Projects/02 某项目/` | 某文档解析服务 架构白话讲解、某文档解析服务 文档解析本地回归测试 |

**历史项目（已被移除，仅供参考）**：`01 某历史项目`、`02 内部系统B`、`03 某平台`、`04 某审查系统`、`05 某开源框架`。

**新增项目时的约定**：项目目录使用数字前缀方便扫描（`NN 项目名/`）。需要持续跟踪的活跃项目，应有一篇 `项目 - 名称` 主页。会议记录、实现记录、交付记录只有在直接服务该项目结果时才放入对应项目目录。

**索引入口**：`01 Projects/项目区 - 索引.md`（2026-09-12 已建）。

## 当前 Areas 结构

> **当前状态（2026-09-12 探查）**：`02 Areas/` 目录**为空**（0 个文件）——历史上存在的领域目录已被重置或迁移。Agent 处理 Areas 相关操作前，必须先 `ls` 真实目录，不能依赖历史假设。

**历史领域（已被移除，仅供参考）**：`01 客户X`、`某领域`。

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
- **提交时会自动跑链接检查**（`.githooks/pre-commit`）：只在提交涉及 `.md` 时运行，发现失效引用会提示，但**不阻塞提交**——失效链接在 vault 里经常是有意为之（先写笔记、目标还没写）。换机器后需执行一次 `git config core.hooksPath .githooks` 才会生效。

## 探查命令示例

任务开始前对目标区域做单层探查：

```sh
VAULT="/Users/huangrx6/Documents/obsidian"

# 顶层区域
ls "$VAULT/01 Projects"
ls "$VAULT/02 Areas"

# 某个 Resources 主题下有什么
rg --files "$VAULT/03 Resources/40 大模型与应用开发" | head -30

# 找某个主题的 MOC / 索引
ls "$VAULT/03 Resources/07 前端与界面" | grep -E "MOC|索引"

# 校验某个路径是否真的存在（写之前必做）
test -e "$VAULT/01 Projects/02 某项目" && echo exists || echo missing
```

## 重置规则

如果用户说某个区域被删除、重置或调整，以文件系统和当前索引为准，不以本地图旧信息为准。结构稳定后再更新本文件。
