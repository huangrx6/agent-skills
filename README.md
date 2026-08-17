# huangrx6 / skills

个人 skills 集合，覆盖工程实践设计、skill 创建流程、视觉理解工具三个领域。每个 skill 是给 AI Coding Agent 读的"专业领域提示词 + 工作流"，由 Agent 根据 `SKILL.md` 第一段 `description` 字段自动决定是否触发。

> **跨 Agent 通用**：兼容 Claude Code / pi / OpenCode / Cursor / Codex 等任意支持 `SKILL.md` frontmatter 约定的 Agent。

## 快速安装

使用 skills 生态的**事实标准 CLI** [`vercel-labs/skills`](https://github.com/vercel-labs/skills)（支持 75+ Agent）：

```sh
# 交互式安装：让选 skill / agent / 全局或项目级 / symlink 或 copy
npx skills add huangrx6/skills

# 精确指定：只装某个 skill 到某个 agent 的全局目录，跳过确认
npx skills add huangrx6/skills \
  --skill design-api-contracts \
  --agent claude-code --global --yes

# 一次装全部到指定 agent
npx skills add huangrx6/skills --skill '*' --agent claude-code

# 列出本仓库所有 skill（不装）
npx skills add huangrx6/skills --list
```

### 完整 flag 速查

| Flag | 作用 | 例子 |
|---|---|---|
| `-s, --skill <name>` | 选择性安装（可多次；`'*'` 代表全部）| `--skill design-api-contracts` |
| `-a, --agent <name>` | 目标 agent（可多次；`'*'` 代表全部）| `-a claude-code -a opencode` |
| `-g, --global` | 装到用户目录而不是项目目录 | `--global` |
| `-y, --yes` | 跳过所有确认提示 | `--yes` |
| `--all` | 装全部 skill 到全部 agent，无提示 | `--all` |
| `--copy` | 拷贝而不是 symlink | `--copy` |
| `-l, --list` | 只列出不装 | `--list` |

### 不依赖 `npx skills` 的备选

任何能读 `SKILL.md` 的 Agent 都能直接 git clone 后用：

```sh
git clone https://github.com/huangrx6/skills.git

# 把 skills/<想装的>/ 软链或拷贝到你的 Agent 加载目录，例如：
#   Claude Code 项目级：./.claude/skills/<name>
#   Claude Code 全局级：~/.claude/skills/<name>
#   pi 全局级：       ~/.agents/skills/<name>
#   OpenCode 全局级：  ~/.opencode/skills/<name>
#   Codex 全局级：    ~/.codex/skills/<name>
```

## 目录结构

```
skills/
├── design-* (13 个)                       ← 设计类：按工程领域切分
├── skill-creator/                         ← 流程类：新建/改进/评估 skill
└── visual-{image-understanding,ui-layout-spec}/   ← 工具类：视觉相关
```

每个 skill 目录内统一结构（参考 [skill-creator](./skills/skill-creator) 的"Anatomy of a Skill"）：

```
<skill-name>/
├── SKILL.md                # 必填：YAML frontmatter（name + description）+ Markdown 正文
├── references/             # 按需加载的长文参考
├── assets/                 # 输出用模板 / 数据 / 图表
├── scripts/                # 可执行脚本（uv run / node）
├── agents/                 # 子 agent 定义
└── examples/               # 输入输出示例
```

## Skill 索引

### 设计类（13 个）

工程实践的 design skill，每个聚焦一个领域。被 Agent 调用来辅助**设计、审查、完善**对应领域的规范、方案、清单、模板。

| Skill | 一句话定位 |
|---|---|
| [design-api-contracts](./skills/design-api-contracts) | API 契约设计：REST / gRPC / GraphQL / WebSocket / SSE / Webhook / JSON-RPC |
| [design-application-logging](./skills/design-application-logging) | 应用日志规范：级别、字段、生命周期、注入防护、滚动归档 |
| [design-code-writing-standards](./skills/design-code-writing-standards) | 代码书写规范：命名、格式化、注释、设计原则、Review 清单 |
| [design-configuration-management](./skills/design-configuration-management) | 配置管理：Schema、来源优先级、热更新、Secret 分离、漂移检测 |
| [design-database-standards](./skills/design-database-standards) | 数据库规范：关系型数据模型、索引、迁移、在线 DDL、分区分片 |
| [design-engineering-documentation](./skills/design-engineering-documentation) | 工程文档体系：README、ADR、文档防腐、AI-first 仓库设计 |
| [design-exception-handling](./skills/design-exception-handling) | 异常处理：失败分类、错误码、统一响应、超时、重试、幂等 |
| [design-git-workflows](./skills/design-git-workflows) | Git 工作流：分支策略、提交信息、worktree、回退恢复、危险门控 |
| [design-observability](./skills/design-observability) | 可观测性：OpenTelemetry、SLI/SLO、采样、告警降噪 |
| [design-performance-capacity](./skills/design-performance-capacity) | 性能与容量：基准、压测、瓶颈分析、自动扩缩、性能回归 |
| [design-secure-coding](./skills/design-secure-coding) | 安全编码：信任边界、注入防护、密钥管理、AI 生成代码审查 |
| [design-service-resilience](./skills/design-service-resilience) | 服务韧性：超时、重试、熔断、舱壁、限流、降级、故障注入 |
| [design-software-architecture](./skills/design-software-architecture) | 软件架构：模块边界、风格选择、ADR、C4、架构风险评审 |

### 流程类（1 个）

| Skill | 一句话定位 |
|---|---|
| [skill-creator](./skills/skill-creator) | 创建 / 改进 / 评估 skill 的端到端流程（草稿→试跑→反馈→迭代→描述优化）|

### 工具类（2 个）

| Skill | 一句话定位 |
|---|---|
| [visual-image-understanding](./skills/visual-image-understanding) | 本地图片 → 远端视觉模型 → 分节 Markdown 描述（不依赖 Agent 原生视觉）|
| [visual-ui-layout-spec](./skills/visual-ui-layout-spec) | UI 截图 / 数据大屏 / 设计稿 → 可交付前端的布局规格（双轨证据 + 设计令牌）|

## 使用

每个 skill 的 `SKILL.md` 第一段 `description` 字段是 Agent 决定是否触发它的依据；正文写的是详细的输入输出约定、调用流程、注意事项。要了解某个 skill 的具体能力，直接点进对应目录读 `SKILL.md`。

## 维护约定

- **目录名 = frontmatter `name` 字段**，保持一致
- 修改某个 skill 后，跑一次 `skill-creator` 里的"如何测试"流程（多数 design skill 没有自动化测试，主要靠人工 review）
- **设计类** 内容相对稳定（按工程领域沉淀），**工具类**（visual-*）会因上游依赖变动需要跟进
- 新增 skill：参考 `skill-creator/SKILL.md` 的"Anatomy of a Skill"和"Writing Patterns"
- 仓库根的 `.skill-lock.json` 已被 `.gitignore` 排除——那是 pi 工具的本地 lock，每台机器自己生成

## 仓库布局遵循

- [`vercel-labs/agent-skills`](https://github.com/vercel-labs/agent-skills) — skills 生态参考仓库
- [Anthropic — Equipping agents for the real world with agent skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) — SKILL.md frontmatter 约定
- [`vercel-labs/skills`](https://github.com/vercel-labs/skills) — `npx skills` CLI（支持 75+ Agent）