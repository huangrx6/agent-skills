# ![agent-skills](assets/icons/agent-skills-light.svg#gh-light-mode-only) ![agent-skills](assets/icons/agent-skills-dark.svg#gh-dark-mode-only) **Agent Skills**

> 个人精选的 AI Coding Agent skill 集合。从头重建，只保留真正高频触发的：Obsidian 工作流、技术图、git 写操作、PingCode 项目与工作项，以及「建 skill」本身的元能力。

## 这是什么

每个 skill 是一个独立目录，含 `SKILL.md`（YAML frontmatter + Markdown 正文，**给 Agent 看的规则**）与 `README.md`（**给人看的详解**），以及按需展开的 `references/`（细节手册）、`scripts/`（确定性脚本）、`tests/`（脚本回归）、`evals/`（触发与行为的评估集）。Agent 靠 `SKILL.md` 的 `description` 判断该不该触发。

**跨 Agent 通用**：兼容 Claude Code / pi / OpenCode / Cursor / Codex 等任意支持 `SKILL.md` frontmatter 约定的 Agent。

---

## 快速安装（推荐）

用的是 skills 生态的**事实标准 CLI** [`vercel-labs/skills`](https://github.com/vercel-labs/skills)（支持 75+ Agent）：

```sh
# 交互式安装
npx skills add <repo>

# 只装某个 skill 到某个 Agent 的全局目录
npx skills add <repo> \
  --skill obsidian-personal-knowledge-base \
  --agent claude-code --global --yes

# 一次装全部到指定 Agent
npx skills add <repo> --skill '*' --agent claude-code
```

### 开发机：clone + 软链（本仓库自带安装器）

`npx skills add` 装的是**副本**，仓库里改了它不会跟着变 —— 实测过一次：某个 skill 的安装位比仓库**少 571 行**，当天新加的能力一个都没有，而它在下一个会话里会照旧工作、连新能力叫什么都不知道。

本仓库自己的安装器**默认装成软链**，装的就是 clone 下来的那一份，没有「两份东西必然漂移」这件事：

```sh
git clone https://github.com/<owner>/agent-skills.git

python3 tools/install_skills.py            # 默认：装成软链（推荐）
python3 tools/install_skills.py --copy     # 要副本（比如仓库会被移走）
python3 tools/install_skills.py --check    # 软链指向对不对 / 副本内容一致吗
```

默认装到 `~/.agents/skills/`（`--install-dir` 可换）。常见的加载目录：

```text
Claude Code  项目级  →  ./.claude/skills/<name>
Claude Code  全局级  →  ~/.claude/skills/<name>
pi           全局级  →  ~/.agents/skills/<name>
OpenCode     全局级  →  ~/.opencode/skills/<name>
Codex        全局级  →  ~/.codex/skills/<name>
```

**「pi 认不认软链」不是猜的**，两处证据：

1. 源码 `dist/core/skills.js` 对每个目录项先 `entry.isDirectory()`，若是 `isSymbolicLink()` 再用 `statSync`（会跟随软链）取真实类型 —— 注释就是「For symlinks, check if they point to a directory and follow them」；
2. 用**它自己的** `loadSkillsFromDir()` 实测：目录里放两个指向本仓库的软链 + 一个普通目录，两个 skill 都被发现、非 skill 目录被正确忽略；再验主文件内容 —— 真实路径落在仓库、只有仓库新版才有的字串能读到。

两个边界：

- 软链指向仓库，所以**未提交的修改也是活的**（开发时正是想要的）；仓库被移走则链接失效，重跑一次安装器即可。
- 想让某个 skill 与副本共存（例如固定一个发布版），用 `--copy` 单独装。

`skills/skill-builder/scripts/preflight.py` 的报告里也会带一行安装位状态 —— **只报告、不算失败**（钩子在 commit 之前跑）。

---

## Skills 索引（6 个）

### Obsidian 工作流（2 个）

围绕 Huangrx6 的 Obsidian vault 构建的工作流。**vault 路径不写死在文档里** —— 按 `$OBSIDIAN_VAULT_PATH` → `~/.config/obsidian-vault-path` 的顺序解析，换机器或 vault 搬家只改一处。

| Skill | 覆盖 |
| --- | --- |
| [**obsidian-personal-knowledge-base**](skills/obsidian-personal-knowledge-base/SKILL.md) | 在 PARA + MOC vault 内创建、更新、移动、审阅笔记；按 Inbox / Projects / Areas / Resources / Archive / Assets / System 判断归属 |
| [**obsidian-work-log-release-recorder**](skills/obsidian-work-log-release-recorder/SKILL.md) | 任务结束后把可复用事实沉淀到长期知识；维护周发版记录（脚本、配置、部署路径、验证、回滚、执行假设） |

### 通用能力（3 个）

不绑定某个 vault 或某个工具，按需触发的确定性能力。

| Skill | 覆盖 |
| --- | --- |
| [**excalidraw-diagram**](skills/excalidraw-diagram/SKILL.md) | 把系统画成可编辑的 Excalidraw 图（架构 / 依赖 / 流程 / 状态 / 部署拓扑 / 思维导图）：区域（网格底 + 虚线框）、四组样式轴、一套配色系统；模型只描述结构，坐标全由脚本算 |
| [**git-dev-workflow**](skills/git-dev-workflow/SKILL.md) | git 写操作（提交 / 分支 / 丢弃改动 / 删分支与 worktree / 改写历史 / force push）前的状态核对与拦截：先读真实状态，不可逆动作前跑机械前置检查，报告只引原始输出 |
| [**pingcode**](skills/pingcode/SKILL.md) | PingCode 项目 / 工作项（史诗·特性·用户故事·任务·缺陷）的命令行：查我的待办与缺陷、按条件搜、看详情、建项目、建改工作项（描述 / 起止日期 / 负责人 / 优先级 / 父项 / 迭代）、改状态、加评论、删工作项。端点来自官方文档生成的端点表（发送前校验），名字→ID 解析歧义时列候选而不猜 |

### 元能力（1 个）

不绑定具体业务场景，Agent 在本仓库内工作时反复用到的元 skill。

| Skill | 覆盖 |
| --- | --- |
| [**skill-builder**](skills/skill-builder/SKILL.md) | 建新 skill 前的 5 分钟决策：该不该建 / 触发描述怎么写 / 范围定 P0 还是 P1 / 起 `SKILL.md` 一稿的 checklist |

**触发语法**：

```text
使用 $obsidian-personal-knowledge-base 帮我 <整理 / 归位 / 创建 / 审阅 笔记>
使用 $obsidian-work-log-release-recorder 帮我 <记录 / 沉淀 / 写发版文档>
使用 $excalidraw-diagram 帮我 <画架构图 / 画流程图 / 把这段说明画出来>
使用 $git-dev-workflow 帮我 <提交 / 建分支 / 丢弃改动 / 清理分支 / 改写历史>
使用 $pingcode 帮我 <查我的任务与缺陷 / 建项目 / 建任务或缺陷 / 改状态 / 看项目进度>
使用 $skill-builder 帮我 <判断要不要建 skill / 评审触发描述 / 起 SKILL.md 一稿>
```

---

## Roadmap

**详细方向与判据看 [`ROADMAP.md`](ROADMAP.md)** —— 这里不抄一份（手抄的表必然过期，实际上已经过期过一次：上一次写「P1 待开工」时 pingcode 已经做完了）。

现状数字现算：

```sh
python3 tools/skill_health.py                            # 规模 / 余量 / 缺 README / 缺 evals / 死文件
python3 tools/skill_trigger_log.py                       # 哪个 skill 真在被用（从 pi 会话记录里读）
python3 skills/skill-builder/scripts/validate_skill.py   # 结构硬错误
```

已完成的部分：

| 优先级 | 方向 | 状态 |
| --- | --- | --- |
| P0 | Obsidian 工作流（知识库 + 发版记录） | ✅ 2026-08 |
| P0 | `skill-builder`（建 skill 的元能力） | ✅ 2026-09 |
| P0 | `excalidraw-diagram`（技术图） | ✅ 2026-09 |
| P0 | `git-dev-workflow`（git 写操作） | ✅ 2026-09 |
| P1 | `pingcode`（PingCode 项目 / 工作项） | ✅ 2026-09，已在真实租户跑通只读 + 写全链路 |

每个新 skill 都要通过 skill-builder 的设计评审才会被加进来 —— 避免重蹈「11 个 skill 只用 2 个」的覆辙。

---

## 维护约定

- **目录名 = frontmatter `name` 字段**，保持一致。
- 每个 skill 都要有 `README.md`（详解），模版与硬约束见 `skills/skill-builder/references/skill-readme-template.md`。**`SKILL.md` 管规则、`README.md` 管怎么用与为什么**，两份不要互相复制；README 里不能出现还没实现的能力（没做的归到「已知限制」）。
- **不再要求 `assets/`**：skill 目录不再约定放图标之类的素材。存量 skill 里已有的 `assets/icons/` 保留（根 README 的索引表还在引用），但新 skill 不用补。
- 改完 skill 跑 `python3 skills/skill-builder/scripts/validate_skill.py` —— 机械检查结构硬错误（YAML 可解析、`name` 匹配目录名、description < 800 字符、含 Do NOT 边界、正文 ≤ 150 行、无绑定声明矛盾等），退出码 `0` 通过 / `1` 失败。**完整清单以脚本输出为准，不在这里抄一份** —— 抄了就会和脚本漂移。
- 正文余量不足 10 行时脚本会另提示一行（`!` 前缀，不影响退出码）：**下次要往正文加规则前，先做 references 瘦身**。瘦身由下一次真实需求触发，不靠「等哪天有空」 —— 一直没空就一直不做。
- **Obsidian 类**的 vault 路径从配置解析（见上方 Skills 索引），换机器或 vault 搬家只改一处，不要在文档或脚本里写死。某个 skill 真的不可移植时才显式声明 —— 而**把它改造成可移植之后，必须在同一次里删掉那条声明**，否则就成了自相矛盾（`validate_skill.py` 会把这种情况判为失败）。
- `.skill-lock.json` 已被 `.gitignore` 排除 —— 那是 pi 工具的本地 lock，每台机器自己生成。
- **改完 skill 不用同步安装位**：安装器默认装的是**软链**，装的就是仓库那一份（见上方安装一节）。想确认状态就跑 `python3 tools/install_skills.py --check`。

### 什么时候可以不修（停止判据）

改进会递归：修完一个问题会露出下一层（写回规则 → eval 标尺 → 检查器自己没测试），而「给测试写的测试谁来验证」理论上没有尽头。所以设一条线：

| 层 | 要求 | 不再要求 |
| --- | --- | --- |
| **核心行为**（skill 的规则本身） | 必须有 eval 覆盖 | — |
| **元工具**（校验脚本） | 边界值测试 | 不再验证「测试本身对不对」 |

遇到新遗留先归到这二层：落第一层的就得做；落第二层的，边界值测完就停 —— 不用每轮重新权衡。

### 自动校验（git hook）

`.githooks/pre-commit` 在提交触及 `skills/` 或 `tools/` 时跑**五道检查 + 一道提示 + 一步自动同步**：

| 工序 | 抓什么 |
| --- | --- |
| `validate_skill.py` | 结构硬错误：YAML 不可解析、`name` 与目录名不一致、description 超 800 字符、正文超 150 行 |
| `check_leakage.py` | 外发内容里的真实名称（真实客户名 / 内部系统名 / 内网主机路径 / 内部接口名） |
| `skills/*/tests` 与 `tools/tests` | 脚本回归：校验器自己的边界、含空格的路径不被截断、扫描范围不扩散…… 这些测试守的正是上面几道的防线，不跑就等于没写 |
| → 跟在同一段里的 `check_doc_numbers.py` | 文档里写的**测试条数**是不是真的。真实条数刚跑出来就在手上，比一下不要钱 |
| `check_pointers.py` | 指针指向一个不存在的文件（客观错误）；「内容有没有真的搬过去」是语义判断，留给人工核对 |
| 提示：`tools/skill_health.py` | **只提示不阻塞** —— 它报的是「该优化什么」（正文余量、缺 README、缺 evals、死文件），不是「代码错了」。拿它挡提交会把人逼到 `--no-verify`，而一旦养成那个习惯，前面四道真防线也一起失效 |
| 同步：`tools/skills_lock.py` | **自动更新并重新暂存** `skills-lock.json`。它是派生文件（`computedHash` = `sha256(SKILL.md)`），却被手工维护过 —— 实测漂成「6 个 skill 里 3 个没登记、2 个哈希过期」。自动而不阻塞的理由同上 |

`check_leakage.py` 的 blocklist 放在仓库**之外**（`~/.config/skill-name-blocklist.txt`，一行一个词）—— 放进仓库它自己就泄露了。未配置时跳过、不阻塞。

hook 不会随 clone 自动生效，新机器上执行一次：

```sh
git config core.hooksPath .githooks
```

跳过单次检查用 `git commit --no-verify`。

> 为什么用 hook 而不是靠自觉：2026-09-12 一次会话里「正文 ≤ 150 行」被连续违反两次（WLRR 256 行、PKB 174 行），两次都是脚本抓出来的，肉眼没发现。同一会话里还发生过一次真实名称被推送到本仓库（当时 public），清除它需要重写 35/38 个 commit 并 force push。
>
> **文档里的测试条数**也是同一类问题：`pingcode` 的 README 写过「120 条」「134 条」（实际早已 139/166）、WLRR 的「0 脚本 0 测试」在补上脚本后还留着、`git-dev-workflow` 的 README 初稿把仓库**实时状态**（「未提交 13 项」）抄进了文档。共同点是**数字手写、事实会变**，而人眼读文档看不出哪个过期了 —— 一个对不上的数字会让人开始怀疑整份文档。所以它现在也由 hook 守：只认测试命令那一行上的数字（「470 条接口」「8 条 eval」不是同一个东西，硬比就是制造误报）。

## 参考

- [`vercel-labs/agent-skills`](https://github.com/vercel-labs/agent-skills) —— skills 生态参考仓库
- [Anthropic — Equipping agents for the real world with agent skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) —— SKILL.md frontmatter 约定
- [`vercel-labs/skills`](https://github.com/vercel-labs/skills) —— `npx skills` CLI（支持 75+ Agent）
