# ![agent-skills](assets/icons/agent-skills-light.svg#gh-light-mode-only) ![agent-skills](assets/icons/agent-skills-dark.svg#gh-dark-mode-only) **Agent Skills**

> 11 个 skill，给 AI Coding Agent 用的专业领域提示词 + 工作流集合。覆盖工程实践（4）+ 视觉 / Obsidian / 流程工具（7）。

## What this is

每个 skill 是一个独立目录，包含 `SKILL.md`（YAML frontmatter + Markdown 正文）和可选的 `references/` / `assets/` / `scripts/` / `examples/`。Agent 通过 `SKILL.md` 第一段 `description` 字段自动判断是否触发。

**跨 Agent 通用**：兼容 Claude Code / pi / OpenCode / Cursor / Codex 等任意支持 `SKILL.md` frontmatter 约定的 Agent。

---

## Quick install（推荐）

使用 skills 生态的**事实标准 CLI** [`vercel-labs/skills`](https://github.com/vercel-labs/skills)（支持 75+ Agent）：

```sh
# 交互式安装
npx skills add <repo>

# 精确指定：只装某个 skill 到某个 agent 的全局目录
npx skills add <repo> \
  --skill engineering-architecture \
  --agent claude-code --global --yes

# 一次装全部到指定 agent
npx skills add <repo> --skill '*' --agent claude-code
```

### 备选：git clone + 手动软链

任何能读 `SKILL.md` 的 Agent 都能直接用：

```sh
git clone https://github.com/<owner>/agent-skills.git

# 把 skills/<想装的>/ 软链到你的 Agent 加载目录，例如：
#   Claude Code 项目级：./.claude/skills/<name>
#   Claude Code 全局级：~/.claude/skills/<name>
#   pi 全局级：       ~/.agents/skills/<name>
#   OpenCode 全局级：  ~/.opencode/skills/<name>
#   Codex 全局级：    ~/.codex/skills/<name>
```

---

## Skills 索引（11 个）

### 1. 工程标准（4 个 `engineering-*`）

覆盖软件工程生命周期 4 个维度。每个 skill 都有独立子主题（13 个 sub-topic），子主题的 README 提供快速参考和决策表。

| Icon | Skill | 覆盖 |
| --- | --- | --- |
| ![arch](skills/assets/icons/engineering-architecture-light.svg#gh-light-mode-only) ![arch](skills/assets/icons/engineering-architecture-dark.svg#gh-dark-mode-only) | [**engineering-architecture**](skills/engineering-architecture/SKILL.md) | 系统骨架与契约：边界 · 风格 · API · 数据库 · 文档 · Git |
| ![rel](skills/assets/icons/engineering-reliability-light.svg#gh-light-mode-only) ![rel](skills/assets/icons/engineering-reliability-dark.svg#gh-dark-mode-only) | [**engineering-reliability**](skills/engineering-reliability/SKILL.md) | 运行时可靠性与可观测性：异常 · 韧性 · 监控 · 日志 · 性能容量 |
| ![sec](skills/assets/icons/engineering-security-light.svg#gh-light-mode-only) ![sec](skills/assets/icons/engineering-security-dark.svg#gh-dark-mode-only) | [**engineering-security**](skills/engineering-security/SKILL.md) | 代码与依赖的安全实现：威胁建模 · 注入防护 · 认证授权 · 密钥 · SAST |
| ![qual](skills/assets/icons/engineering-quality-light.svg#gh-light-mode-only) ![qual](skills/assets/icons/engineering-quality-dark.svg#gh-dark-mode-only) | [**engineering-quality**](skills/engineering-quality/SKILL.md) | 代码级一致性与配置体系：代码规范 · 命名 · 配置分类 · Feature Flag |

**触发语法**：

```text
使用 $engineering-<area>[/<sub-topic>] 帮我 <做什么>
```

**子主题入口**：[architecture](skills/engineering-architecture/architecture/README.md) · [api-contracts](skills/engineering-architecture/api-contracts/README.md) · [database](skills/engineering-architecture/database/README.md) · [documentation](skills/engineering-architecture/documentation/README.md) · [git](skills/engineering-architecture/git/README.md) · [exception-handling](skills/engineering-reliability/exception-handling/README.md) · [resilience](skills/engineering-reliability/resilience/README.md) · [observability](skills/engineering-reliability/observability/README.md) · [logging](skills/engineering-reliability/logging/README.md) · [performance-capacity](skills/engineering-reliability/performance-capacity/README.md) · [secure-coding](skills/engineering-security/secure-coding/README.md) · [code-style](skills/engineering-quality/code-style/README.md) · [configuration](skills/engineering-quality/configuration/README.md)

### 2. 工具与流程（7 个）

围绕工程标准做事的辅助 skill：阅读图片 / 写文档 / 操作 Obsidian / 创建新 skill 等。

| Icon | Skill | 用途 |
| --- | --- | --- |
| ![readme](skills/assets/icons/developer-readme-design-light.svg#gh-light-mode-only) ![readme](skills/assets/icons/developer-readme-design-dark.svg#gh-dark-mode-only) | [**developer-readme-design**](skills/developer-readme-design/SKILL.md) | 把仓库 README 改造成成熟的开发者工具 landing page（monochrome / restrained / technical） |
| ![draw](skills/assets/icons/draw-processon-light.svg#gh-light-mode-only) ![draw](skills/assets/icons/draw-processon-dark.svg#gh-dark-mode-only) | [**draw-processon**](skills/draw-processon/SKILL.md) | 统一调用 ProcessOn 画架构图 / 流程图 / ER 图 / 思维导图 |
| ![vault](skills/assets/icons/obsidian-personal-knowledge-base-light.svg#gh-light-mode-only) ![vault](skills/assets/icons/obsidian-personal-knowledge-base-dark.svg#gh-dark-mode-only) | [**obsidian-personal-knowledge-base**](skills/obsidian-personal-knowledge-base/SKILL.md) | 操作 PARA + MOC 结构的 Obsidian vault |
| ![record](skills/assets/icons/obsidian-work-log-release-recorder-light.svg#gh-light-mode-only) ![record](skills/assets/icons/obsidian-work-log-release-recorder-dark.svg#gh-dark-mode-only) | [**obsidian-work-log-release-recorder**](skills/obsidian-work-log-release-recorder/SKILL.md) | 任务完成后把可复用事实沉淀到 Obsidian 长期知识 |
| ![create](skills/assets/icons/skill-creator-light.svg#gh-light-mode-only) ![create](skills/assets/icons/skill-creator-dark.svg#gh-dark-mode-only) | [**skill-creator**](skills/skill-creator/SKILL.md) | 创建新 skill / 改进现有 skill / 跑 eval 测触发准确度 |
| ![image](skills/assets/icons/visual-image-understanding-light.svg#gh-light-mode-only) ![image](skills/assets/icons/visual-image-understanding-dark.svg#gh-dark-mode-only) | [**visual-image-understanding**](skills/visual-image-understanding/SKILL.md) | 读图片（截图 / 照片 / 文档 / 图表），OCR + 视觉理解 |
| ![layout](skills/assets/icons/visual-ui-layout-spec-light.svg#gh-light-mode-only) ![layout](skills/assets/icons/visual-ui-layout-spec-dark.svg#gh-dark-mode-only) | [**visual-ui-layout-spec**](skills/visual-ui-layout-spec/SKILL.md) | UI 截图 / 数据大屏转可交付前端的布局规格（双轨证据：原生视觉 + 远端 VLM） |

---

## Anatomy of a Skill

每个 skill 目录内统一结构（参考 [`skill-creator`](skills/skill-creator/SKILL.md) 的"Anatomy of a Skill"）：

```text
<skill-name>/
├── SKILL.md                # 必填：YAML frontmatter（name + description）+ Markdown 正文
├── references/             # 按需加载的长文参考
├── assets/                 # 输出用模板 / 数据 / 图表 / 图标
├── scripts/                # 可执行脚本（uv run / node）
├── agents/                 # 子 agent 定义
└── examples/               # 输入输出示例
```

## 维护约定

- **目录名 = frontmatter `name` 字段**，保持一致
- 修改某个 skill 后：跑它自带的 `validate_*.py` + `unittest`；新加 skill 用 [`skill-creator`](skills/skill-creator/SKILL.md) 的流程
- **工程标准**（4 个 `engineering-*`）相对稳定；**工具类**（visual-*）会因上游依赖变动需跟进；**Obsidian 类**绑定具体 vault 路径（跨机复用性低）
- 本仓库的 `.skill-lock.json` 已被 `.gitignore` 排除——那是 pi 工具的本地 lock，每台机器自己生成
- git 历史包含旧 skill 演化轨迹；通过 `git log --diff-filter=D` 追溯

## 参考

- [`vercel-labs/agent-skills`](https://github.com/vercel-labs/agent-skills) — skills 生态参考仓库
- [Anthropic — Equipping agents for the real world with agent skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) — SKILL.md frontmatter 约定
- [`vercel-labs/skills`](https://github.com/vercel-labs/skills) — `npx skills` CLI（支持 75+ Agent）
- [developer-readme-design](skills/developer-readme-design/SKILL.md) — 本仓库所有 README 的视觉规范来源
