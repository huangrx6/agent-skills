# 知识库地图

本技能操作 `/Users/huangrx6/obsidian`。

这个库采用 PARA + MOC 结构。编辑前始终先检查当前文件，因为用户可能在不同轮次之间调整目录。

## 顶层结构

- `00 Inbox`
- `01 Projects`
- `02 Areas`
- `03 Resources`
- `04 Archive`
- `90 Assets`
- `99 System`

## 归位规则

| 区域 | 用于 | 不用于 |
|---|---|---|
| `00 Inbox` | 未分类捕获、临时笔记 | 已有明确归属的长期笔记 |
| `01 Projects` | 有明确交付结果、能完成或关闭的工作 | 长期持续责任 |
| `02 Areas` | 长期责任、周期性维护 | 一次性交付 |
| `03 Resources` | 可复用知识、学习笔记、技术资料 | 项目状态、周计划、周报 |
| `04 Archive` | 已不活跃但需要保留的历史内容 | 当前活跃工作 |
| `90 Assets` | 附件、图片、绘图 | 正文笔记 |
| `99 System` | 模板、工作流、知识库规则 | 用户知识内容 |

如果一篇笔记可能放在多个地方，只选一个主家，其他地方用链接引用。

## 当前 Projects 结构

入口：

- `01 Projects/项目区 - 索引.md`

当前项目目录：

- `01 Projects/01 人人一个智能体/`
- `01 Projects/02 AI 网关/`
- `01 Projects/03 AI 统一能力平台/`
- `01 Projects/04 服务报告审核/`
- `01 Projects/05 SpecForge/`

项目目录使用数字前缀方便扫描。需要持续跟踪的活跃项目，应有一篇 `项目 - 名称` 主页。会议记录、实现记录、交付记录只有在直接服务该项目结果时才放入对应项目目录。

## 当前 Areas 结构

入口：

- `02 Areas/领域区 - 索引.md`

当前领域目录：

- `02 Areas/01 亚信/`
- `02 Areas/02 个人/`

当前领域入口：

- `02 Areas/01 亚信/00 MOC - 亚信.md`
- `02 Areas/02 个人/00 MOC - 个人.md`

当前周期性记录：

- `02 Areas/01 亚信/01 周计划/`
- `02 Areas/01 亚信/02 周报/`

领域区应保持轻量导航。领域 MOC 可以链接到 `01 Projects` 的活跃项目主页，但不要在领域页里重复维护完整项目计划。

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

## 重置规则

如果用户说某个区域被删除、重置或调整，以文件系统和当前索引为准，不以本地图旧信息为准。结构稳定后再更新本文件。
