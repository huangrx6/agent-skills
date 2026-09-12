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

### ⚠️ 装了之后：**安装位不会自己跟着仓库走**

`npx skills add` 是**复制**，不是链接 —— 所以仓库里改了，安装位还是旧的。实测过一次：
某个 skill 的安装位比仓库**少 571 行**，当天新加的能力一个都没有，而它在下一个会话里
会照旧配置出图、连新能力叫什么都不知道。软链没这个问题（它本来就不会漂）。

所以每次改完 `skills/`：

```sh
python3 tools/install_skills.py            # 仓库 → ~/.agents/skills（会删掉安装位多出来的文件）
python3 tools/install_skills.py --check    # 只比对，不一致退出码 1（给 CI / 钩子用）
```

`skills/skill-builder/scripts/preflight.py` 的报告里也会带一行安装位状态——
**只报告、不算失败**（钩子在 commit 之前跑，那时安装位按定义就是旧的）。

---

## Skills 索引(当前 3 个)

### Obsidian 工作流(2 个)

围绕 Huangrx6 的 Obsidian vault 构建的工作流。**vault 路径不写死在文档里**——按 `$OBSIDIAN_VAULT_PATH` → `~/.config/obsidian-vault-path` 的顺序解析，换机器或 vault 搬家只改一处。

| Icon | Skill | 覆盖 |
| --- | --- | --- |
| ![vault](skills/obsidian-personal-knowledge-base/assets/icons/obsidian-personal-knowledge-base-light.svg#gh-light-mode-only) ![vault](skills/obsidian-personal-knowledge-base/assets/icons/obsidian-personal-knowledge-base-dark.svg#gh-dark-mode-only) | [**obsidian-personal-knowledge-base**](skills/obsidian-personal-knowledge-base/SKILL.md) | 在 PARA + MOC vault 内创建、更新、移动、审阅笔记;按 Inbox/Projects/Areas/Resources/Archive/Assets/System 判断归属 |
| ![record](skills/obsidian-work-log-release-recorder/assets/icons/obsidian-work-log-release-recorder-light.svg#gh-light-mode-only) ![record](skills/obsidian-work-log-release-recorder/assets/icons/obsidian-work-log-release-recorder-dark.svg#gh-dark-mode-only) | [**obsidian-work-log-release-recorder**](skills/obsidian-work-log-release-recorder/SKILL.md) | 任务结束后把可复用事实沉淀到长期知识;维护周发版记录(脚本、配置、部署路径、验证、回滚、执行假设) |

### 元能力(1 个)

不绑定具体业务场景,Agent 在本仓库内工作时反复用到的元 skill。

| Icon | Skill | 覆盖 |
| --- | --- | --- |
| ![build](skills/skill-builder/assets/icons/skill-builder-light.svg#gh-light-mode-only) ![build](skills/skill-builder/assets/icons/skill-builder-dark.svg#gh-dark-mode-only) | [**skill-builder**](skills/skill-builder/SKILL.md) | 建新 skill 前的 5 分钟决策:该不该建 / 触发描述怎么写 / 范围定 P0 还是 P1 / 起 SKILL.md 一稿的 checklist |

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
- 改完 skill 跑 `python3 skills/skill-builder/scripts/validate_skill.py` —— 机械检查结构硬错误(YAML 可解析、name 匹配目录名、description < 800 字符、含 Do NOT 边界、正文 ≤ 150 行、无绑定声明矛盾等),退出码 `0` 通过 / `1` 失败。**完整清单以脚本输出为准,不在这里拄一份**——拄了就会和脚本漂移
- 正文余量不足 10 行时脚本会另提示一行(`!` 前缀,不影响退出码):**下次要往正文加规则前,先做 references 瘦身**。瘦身由下一次真实需求触发,不靠“等哪天有空”——一直没空就一直不做。
- **Obsidian 类**的 vault 路径从配置解析(见上方 Skills 索引),换机器或 vault 搬家只改一处,不要在文档或脚本里写死。某个 skill 真的不可移植时才显式声明——而**把它改造成可移植之后,必须在同一次里删掉那条声明**,否则就成了自相矛盾(`validate_skill.py` 会把这种情况判为失败)
- 本仓库的 `.skill-lock.json` 已被 `.gitignore` 排除——那是 pi 工具的本地 lock,每台机器自己生成
- **改完 skill 记得同步安装位**:`python3 tools/install_skills.py`（原因与边界见上方安装一节）

### 什么时候可以不修(停止判据)

改进会递归:修完一个问题会露出下一层(写回规则 → eval 标尺 → 检查器自己没测试),而“给测试写的测试谁来验证”理论上没有尽头。所以设一条线:

| 层 | 要求 | 不再要求 |
| --- | --- | --- |
| **核心行为**(skill 的规则本身) | 必须有 eval 覆盖 | — |
| **元工具**(校验脚本) | 边界值测试 | 不再验证“测试本身对不对” |

遇到新遗留先归到这二层:落第一层的就得做;落第二层的,边界值测完就停——不用每轮重新权衡。

### 自动校验(git hook)

`.githooks/pre-commit` 在提交触及 `skills/` 时跑**两道检查**，任一失败就挡住提交：

| 检查 | 抓什么 |
| --- | --- |
| `validate_skill.py` | 结构硬错误：YAML 不可解析、`name` 与目录名不一致、description 超 800 字符、正文超 150 行 |
| `check_leakage.py` | 外发内容里的真实名称（真实客户名 / 内部系统名 / 内网主机路径 / 内部接口名） |

`check_leakage.py` 的 blocklist 放在仓库**之外**（`~/.config/skill-name-blocklist.txt`，一行一个词）——放进仓库它自己就泄露了。未配置时跳过、不阻塞。

hook 不会随 clone 自动生效，新机器上执行一次：

```sh
git config core.hooksPath .githooks
```

跳过单次检查用 `git commit --no-verify`。

> 为什么用 hook 而不是靠自觉:2026-09-12 一次会话里“正文 ≤ 150 行”被连续违反两次(WLRR 256 行、PKB 174 行),两次都是脚本抓出来的,肉眼没发现。同一会话里还发生过一次真实名称被推送到本仓库（当时 public），清除它需要重写 35/38 个 commit 并 force push。

## 参考

- [`vercel-labs/agent-skills`](https://github.com/vercel-labs/agent-skills) — skills 生态参考仓库
- [Anthropic — Equipping agents for the real world with agent skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) — SKILL.md frontmatter 约定
- [`vercel-labs/skills`](https://github.com/vercel-labs/skills) — `npx skills` CLI(支持 75+ Agent)
