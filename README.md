# ![agent-skills](assets/icons/agent-skills-light.svg#gh-light-mode-only) ![agent-skills](assets/icons/agent-skills-dark.svg#gh-dark-mode-only) **Agent Skills**

> 个人精选的 AI Coding Agent skill 集合。从头重建,只保留真正高频触发的;obsidian 工作流优先,其余按需补齐。

## What this is

每个 skill 是一个独立目录,内含 `SKILL.md`(YAML frontmatter + Markdown 正文)和按需的 `references/` / `assets/` / `scripts/` / `examples/`。Agent 通过 `SKILL.md` 第一段 `description` 字段自动判断是否触发。

**跨 Agent 通用**:兼容 Claude Code / pi / OpenCode / Cursor / Codex 等任意支持 `SKILL.md` frontmatter 约定的 Agent。

---

## Quick install(推荐)

使用 skills 生态的**事实标准 CLI** [`vercel-labs/skills`](https://github.com/vercel-labs/skills)(支持 75+ Agent):

```sh
# 交互式安装
npx skills add <repo>

# 精确指定:只装某个 skill 到某个 agent 的全局目录
npx skills add <repo> \
  --skill obsidian-personal-knowledge-base \
  --agent claude-code --global --yes

# 一次装全部到指定 agent
npx skills add <repo> --skill '*' --agent claude-code
```

### 备选:git clone + 手动软链

任何能读 `SKILL.md` 的 Agent 都能直接用:

```sh
git clone https://github.com/<owner>/agent-skills.git

# 把 skills/<想装的>/ 软链到你的 Agent 加载目录,例如:
#   Claude Code 项目级:./.claude/skills/<name>
#   Claude Code 全局级:~/.claude/skills/<name>
#   pi 全局级:       ~/.agents/skills/<name>
#   OpenCode 全局级:  ~/.opencode/skills/<name>
#   Codex 全局级:    ~/.codex/skills/<name>
```

---

## Skills 索引(当前 3 个)

### Obsidian 工作流(2 个)

围绕 Huangrx6 的 Obsidian vault(`/Users/huangrx6/Documents/obsidian`)构建的工作流。绑定特定 vault 路径,**跨机复用性低**——换电脑或换 vault 路径需要重新校准 `references/vault-map.md`。

| Icon | Skill | 覆盖 |
| --- | --- | --- |
| ![vault](skills/obsidian-personal-knowledge-base/assets/icons/obsidian-personal-knowledge-base-light.svg#gh-light-mode-only) ![vault](skills/obsidian-personal-knowledge-base/assets/icons/obsidian-personal-knowledge-base-dark.svg#gh-dark-mode-only) | [**obsidian-personal-knowledge-base**](skills/obsidian-personal-knowledge-base/SKILL.md) | 在 PARA + MOC vault 内创建、更新、移动、审阅笔记;按 Inbox/Projects/Areas/Resources/Archive/Assets/System 判断归属 |
| ![record](skills/obsidian-work-log-release-recorder/assets/icons/obsidian-work-log-release-recorder-light.svg#gh-light-mode-only) ![record](skills/obsidian-work-log-release-recorder/assets/icons/obsidian-work-log-release-recorder-dark.svg#gh-dark-mode-only) | [**obsidian-work-log-release-recorder**](skills/obsidian-work-log-release-recorder/SKILL.md) | 任务结束后把可复用事实沉淀到长期知识;维护周发版记录(脚本、配置、部署路径、验证、回滚、执行假设) |

### 元能力(1 个)

不绑定具体业务场景,Agent 在本仓库内工作时反复用到的元 skill。

| Icon | Skill | 覆盖 |
| --- | --- | --- |
| ![build](skills/obsidian-personal-knowledge-base/assets/icons/obsidian-personal-knowledge-base-light.svg#gh-light-mode-only) | [**skill-builder**](skills/skill-builder/SKILL.md) | 建新 skill 前的 5 分钟决策:该不该建 / 触发描述怎么写 / 范围定 P0 还是 P1 / 起 SKILL.md 一稿的 checklist |

**触发语法**:

```text
使用 $obsidian-personal-knowledge-base 帮我 <整理 / 归位 / 创建 / 审阅 笔记>
使用 $obsidian-work-log-release-recorder 帮我 <记录 / 沉淀 / 写发版文档>
使用 $skill-builder 帮我 <判断要不要建 skill / 评审触发描述 / 起 SKILL.md 一稿>
```

---

## Roadmap

按价值频率排序,后续 skill 计划:

| 优先级 | 方向 | 状态 |
| --- | --- | --- |
| P0 | `skill-builder`(5 分钟决策树) | ✅ 已建(2025-09) |
| P1 | Obsidian 工作流闭环补齐 | ⏳ 待开工 |
| P2 | 日常高频触发类 | ⏳ 等 P0/P1 落地后,根据真实触发日志再定 |

每个新 skill 都要通过 skill-builder 的设计评审才会被加进来——避免重蹈"11 个 skill 只用 2 个"的覆辙。

---

## 维护约定

- **目录名 = frontmatter `name` 字段**,保持一致
- 修改某个 skill 后:跑它自带的 `validate_*.py` + `unittest`
- **Obsidian 类**绑定具体 vault 路径(跨机复用性低)
- 本仓库的 `.skill-lock.json` 已被 `.gitignore` 排除——那是 pi 工具的本地 lock,每台机器自己生成

## 参考

- [`vercel-labs/agent-skills`](https://github.com/vercel-labs/agent-skills) — skills 生态参考仓库
- [Anthropic — Equipping agents for the real world with agent skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) — SKILL.md frontmatter 约定
- [`vercel-labs/skills`](https://github.com/vercel-labs/skills) — `npx skills` CLI(支持 75+ Agent)
