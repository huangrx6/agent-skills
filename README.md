<h1 align="center">Agent Skills</h1>

<p align="center">
  <strong>把重复的工作方法，写成 Agent 能执行、能验证的 skill。</strong><br>
  <sub>演示文稿 · 技术图 · COSMIC · Obsidian · Git · PingCode · 学习路线</sub>
</p>

<p align="center">
  <code>9 skills</code> &nbsp;·&nbsp; <code>Python 3.10+（learning-scout、pingcode-weekly 需 3.11+）</code> &nbsp;·&nbsp; <code>MIT</code>
</p>

每个 skill 都是一个独立目录：`SKILL.md` 说明什么时候触发、怎么执行，`README.md` 交代依赖、用法和边界。
能力之间可以组合，但安装和配置互不依赖。

## Skills

### 内容与表达

| Skill | 做什么 | 产出 |
| --- | --- | --- |
| [**deck-authoring**](skills/deck-authoring/README.md) | 从材料组织内容、设计版面与配图，用真实页面迭代 | HTML 演示 · PDF · PNG · PPTX · 视频 |
| [**diagram-authoring**](skills/diagram-authoring/README.md) | 把结构描述变成可编辑的技术图，并检查布局与可读性 | Excalidraw · draw.io · Mermaid · PNG |
| [**cosmic-split**](skills/cosmic-split/README.md) | 按需求、接口、页面或代码识别 COSMIC 数据移动 | 拆分表 · 自检报告 · 覆盖清单 |

### 知识与工作

| Skill | 做什么 | 产出 |
| --- | --- | --- |
| [**obsidian-wiki**](skills/obsidian-wiki/README.md) | 吸收资料、关联证据、按笔记问答与复习 | 可持续维护的学习 Wiki |
| [**obsidian-work**](skills/obsidian-work/README.md) | 管理需求、缺陷、任务、周报与发布记录 | 工作项主档 · Bases 工作台 |
| [**pingcode**](skills/pingcode/README.md) | 查询和维护 PingCode 项目、工作项与迭代 | CLI 输出 · 结构化工作项 |
| [**pingcode-weekly**](skills/pingcode-weekly/README.md) | 从需求与缺陷生成项目周报，只读 PingCode | Markdown 周报 · 证据 JSON |

### 开发与学习

| Skill | 做什么 | 产出 |
| --- | --- | --- |
| [**git-dev-workflow**](skills/git-dev-workflow/README.md) | 本地 Git 状态、破坏性操作预检、提交与 worktree | 状态快照 · 风险结论 · 操作建议 |
| [**learning-scout**](skills/learning-scout/README.md) | 把学习需求研究成一组独立笔记与离线入口页 | 笔记 · HTML 入口 · 打印版 · PDF |

Obsidian 两项能力各自独立，通过笔记数据关联。

例如：“使用 `$deck-authoring` 把材料做成演示文稿”，或“使用 `$learning-scout` 给我一条两周的 RAG 学习路线”。
是否自动发现、如何显式调用，取决于使用的 Agent。

## 维护工具

技能之外的仓库工具放在 `tools/`，不会被安装到 agent：

| 工具 | 作用 |
| --- | --- |
| [**skill-builder**](tools/skill-builder/README.md) | 编写 / 评审 skill 的指南，以及结构、引用、名称泄露检查器 |
| `install_skills.py` | 把 `skills/` 软链或复制到 agent 发现目录 |
| `skills_lock.py` | 记录并校验各个 `SKILL.md` 的哈希 |
| `migrate_skill_home.py` | 把旧配置 / 缓存迁到 `~/.agent-skills` |
| `skill_health.py` | 仓库体检与维护建议 |
| `skill_trigger_log.py` | 分析本机会话日志，不做触发效果承诺 |

## 安装

### 本机开发：软链

```sh
git clone https://github.com/huangrx6/agent-skills.git
cd agent-skills

python3 tools/install_skills.py          # 装成软链，改仓库立即生效
python3 tools/install_skills.py --check  # 检查安装状态
```

默认安装到 `~/.agents/skills/`。`~/.agents` 是 Pi、Codex、Zed 等共享的发现目录，
本项目只往里放安装位，不放配置和缓存。换目录用 `--install-dir`。

### 其他 Agent 或项目：官方 CLI

```sh
# 全局安装到 Claude Code / Codex
npx skills add https://github.com/huangrx6/agent-skills -a claude-code -a codex -g

# 装到当前项目的 .agents/skills
npx skills add https://github.com/huangrx6/agent-skills -a cursor
```

只装一个或选装几个：

```sh
# 先看仓库里有哪些 skill 名称（不安装）
npx skills add https://github.com/huangrx6/agent-skills --list

# 只装 learning-scout
npx skills add https://github.com/huangrx6/agent-skills -a cursor --skill learning-scout

# 选装多个：--skill 可重复，'*' 表示全部
npx skills add https://github.com/huangrx6/agent-skills -a claude-code -g \
  --skill learning-scout --skill pingcode --skill pingcode-weekly
```

官方安装器维护各 Agent 的路径与更新；本仓库的 `tools/install_skills.py` 仍然一次安装全部 9 个。
本地 `--copy` 只复制 Git 跟踪的内容，不会带上 `.venv` 或 IDE 配置。仓库可能移动、需要固定副本时：

```sh
python3 tools/install_skills.py --copy
```

> [!NOTE]
> 安装 skill 不等于安装运行依赖。浏览器、LibreOffice、字体、Python 包和 PingCode 令牌
> 见各 skill 的 README。

## 配置

所有配置与运行数据收在一个家目录：

```text
~/.agent-skills/
├── config/     # 词表、vault 路径、PingCode 凭据与令牌
└── data/       # venv、字体、图标库等可重建数据
```

| 变量 | 默认 | 用途 |
| --- | --- | --- |
| `AGENT_SKILLS_HOME` | `~/.agent-skills` | 项目家目录根 |
| `AGENT_SKILLS_CONFIG_DIR` | `$AGENT_SKILLS_HOME/config` | 共享配置根 |
| `AGENT_SKILLS_DATA_DIR` | `$AGENT_SKILLS_HOME/data` | 共享运行数据根 |

输出目录例外：报告和构建产物仍写到 `~/Downloads/<skill>/`。
旧位置（`~/.config/agent-skills`、`~/.cache/diagram-authoring` 等）只读兼容，迁移一次即可：

```sh
python3 tools/migrate_skill_home.py --apply
```

迁移与覆盖变量见 `python3 tools/migrate_skill_home.py --help`。令牌、账号和实际 vault 路径不随 skill 分发。

## 设计原则

- **独立可装**：每个目录都能单独复制运行，不依赖相邻 skill 或仓库里的维护工具。
- **可验证**：结论要能回到命令、测试、源码行号或外部快照；不把“检查通过”当成品质量。
- **状态收拢**：配置与运行数据进 `~/.agent-skills`，仓库只留可分发内容。
- **产物落地**：默认写 `~/Downloads/<skill>/`，用普通文件交付，不锁在对话里。

## 仓库结构

```text
agent-skills/
├── skills/        # 9 个可独立安装的 skill
├── tools/         # 安装、锁文件、迁移、体检、skill 编写
├── tests/         # 回归测试，按 skill 分目录
├── .githooks/     # 提交检查
└── skills-lock.json
```

## 开发与验证

```sh
python3 tools/skill-builder/scripts/preflight.py
python3 -m unittest discover -s tools/tests -v
python3 tools/skills_lock.py --check
```

修改其他 skill 时，把测试目录换成对应名称。`preflight.py` 只做结构、泄露、指针与文件快照，
不执行回归，也不证明产物质量；Deck 的浏览器与 PDF 测试需要其运行依赖。
`tools/skill_health.py` 提供维护建议，`tools/skill_trigger_log.py` 分析本机会话日志。
`skill-builder` 的写作方法在 [GUIDE.md](tools/skill-builder/GUIDE.md)，检查器命令见其 README。

CI 在 [`.github/workflows/gate.yml`](.github/workflows/gate.yml)：推送与 PR 时跑结构、泄露、
指针、锁文件校验，并按 `Python 3.10 / 3.11` 跑各 skill 与 `tools/` 的回归——版本声明要能被验证。Deck 与 diagram 的重型套件需要 Chrome / LibreOffice，不在 CI 里跑，仍由发布前的人工闸门覆盖：

改动 description 或触发边界后，用 `tools/trigger_eval.py` 算触发率：数据在
`skills/<name>/evals/triggers.json`（正例 + 近邻反例），`--template` 生成待记录结果，
`--score` 算分。方法与判据见 [GUIDE](tools/skill-builder/GUIDE.md#触发评测)。

```sh
AGENT_SKILLS_GATE=1 git commit --allow-empty -m "release gate"
```

提交涉及 `skills/`、`tests/`、`tools/` 或 `.githooks/` 时，可启用仓库 hook：

```sh
git config core.hooksPath .githooks
```

| 检查 | 行为 |
| --- | --- |
| 结构、敏感名称、引用目标、文档测试数字 | 发现错误时阻塞；词表未配置则跳过该扫描 |
| 各 skill 与仓库工具回归 | 默认只提示；`AGENT_SKILLS_GATE=1` 时阻塞 |
| 仓库体检 | 维护建议，不阻塞 |
| 锁文件同步 | 按暂存区的 SKILL.md 更新锁文件 |

后续方向见 [ROADMAP.md](ROADMAP.md)。

---

<p align="center">
  <sub>原创代码与文档采用 <a href="LICENSE">MIT License</a>；第三方依赖、字体与品牌素材按各自许可使用。</sub>
</p>
