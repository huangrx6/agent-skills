---
name: obsidian-personal-knowledge-base
description: >-
  Use when the user asks to create, edit, review, move, rename, or organize Obsidian notes,
  choose a PARA location, or maintain a vault MOC, index, project page, weekly plan or report.
  中文：存到知识库、整理笔记、这篇放哪、更新索引。适用于明确的 Obsidian/vault 内容操作。
  Do NOT use for recording newly completed implementation or release facts (use obsidian-work-log-release-recorder),
  generic file editing, or discussion with no requested note change.
---

# Obsidian 知识库维护

按实际目录和邻近笔记的约定维护 PARA + MOC 知识库。只选一个内容主家，其他位置用链接引用。

## 路径与范围

脚本路径相对于本 skill 目录。先解析本次 vault：

```sh
python3 scripts/vault_path.py --explain
```

来源依次为显式路径、`OBSIDIAN_VAULT_PATH`、`$AGENT_SKILLS_CONFIG_DIR/obsidian-vault-path`
（配置目录默认 `~/.config/agent-skills`）；兼容读取旧配置 `~/.config/obsidian-vault-path`。
未配置或目录不存在时，给出配置缺口，不能猜测其他 vault。

本 skill 负责笔记本身。将刚完成的开发、配置或发布事实沉淀为记录时，使用
`obsidian-work-log-release-recorder`；仅修订已有发版笔记的排版、链接或位置仍属本 skill。
结合上下文判断，不因同时出现“发版”和“整理”就重复追问。确实无法判断要周报还是发版记录时再问。

## 工作流程

1. 读取 [归位规则](references/vault-map.md) 和 [通用写作规范](references/writing-conventions.md)。
   单层查看目标目录，再读最近的索引、模板和待修改笔记；需要更多信息时逐层缩小范围。
   目录与文档不符时以实际文件和用户当前要求为准，不恢复已删除的历史结构。
2. 选择下表中的任务规则。已有笔记能容纳内容时优先更新；新建内容不复制完整聊天记录。
3. 修改授权范围内的笔记及必要导航。保留 frontmatter 和有效内容，修订日期只在内容实际改变时更新。
   用户明确指定的新路径可以创建；未指定且无法可靠归位时，临时捕获进 Inbox，结构性新建再澄清落点。
4. 移动、重命名、拆分或合并前，按旧文件名和路径搜索全库入链（包括附件引用）；同步受影响的链接和索引。
   不因邻近笔记没有引用就认定全库没有引用。附件清理只有在任务包含清理且确认无引用时才删除源文件。
5. 按改动选择验证，区分本次新增问题与原有问题。结果只需说明改了哪些笔记、归位理由、检查结果和剩余缺口。

| 任务 | 按需读取 |
| --- | --- |
| Projects、Areas、会议、周计划、周报 | [工作管理](references/work-management.md) |
| Resources、学习笔记、技术资料 | [资源笔记](references/resource-notes.md) |
| 需要查资料、比较方案或综合多个来源 | [研究与综合](references/research-and-synthesis.md) |
| 链接、附件或插件配置路径检查 | [结构检查](references/structural-checks.md) |

新建或改动目录后更新 vault 内受影响的索引，不把普通笔记任务扩展成修改本 skill、维护漂移计数或 git 提交。
只读审阅只报告发现，用户要求修订或整理时再落实相应修改。

## 验证入口

```sh
python3 scripts/check_links.py --ignore-template
python3 scripts/check_paths.py
```

链接、命名或位置改变时跑链接检查；改了插件配置或迁移 vault 时才需要路径检查。
两个检查器都只读：`0` 表示未发现其范围内的失败，`1` 表示发现问题，`2` 表示路径或输入不可用。
已有断链可能是待写笔记，不能为了返回 `0` 自动删链接或补造内容。检查范围和误判边界见结构检查说明。
