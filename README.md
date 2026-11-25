<h1 align="center">Agent Skills</h1>

<p align="center">
  <strong>把重复的工作方法，写成 Agent 能执行、能验证的 skill。</strong><br>
  <sub>演示文稿 · 技术图 · COSMIC · Obsidian · Git · PingCode · 学习路线 · 邮件 · 工程基线 · 需求规格 · 界面工艺 · 前后端研发 · 测试与验收</sub>
</p>

<p align="center">
  <code>17 skills</code> &nbsp;·&nbsp; <code>Python 3.10+（learning-scout、pingcode-weekly 需 3.11+）</code> &nbsp;·&nbsp; <code>MIT</code>
</p>

<p align="center">
  <a href="https://huangrx6.github.io/agent-skills/">项目主页</a>
</p>

每个 skill 都是一个独立目录：`SKILL.md` 说明什么时候触发、怎么执行，`README.md` 交代依赖、用法和边界。
能力之间可以组合，但安装和配置互不依赖。

## 项目主页

项目主页与文档：<https://huangrx6.github.io/agent-skills/>。

站点由本仓库的 README、skill README、GUIDE 与 ROADMAP 生成，默认黑夜主题，
右上角可切换白天/黑夜。生成结果在 `docs/`，改完文档后重新生成并提交：

```sh
python3 tools/build_site.py --out docs --check
```

依赖与部署说明见 [`tools/site/README.md`](tools/site/README.md)；发布由
[`.github/workflows/pages.yml`](.github/workflows/pages.yml) 完成。首次发布需在仓库
Settings → Pages 把 Source 设为 GitHub Actions；不要手改 `docs/` 下的 HTML。

## Skills

### 内容与表达

| Skill | 做什么 | 产出 |
| --- | --- | --- |
| [**deck-authoring**](skills/deck-authoring/README.md) | 从材料组织内容、设计版面与配图，用真实页面迭代 | HTML 演示 · PDF · PNG · PPTX · 视频 |
| [**diagram-authoring**](skills/diagram-authoring/README.md) | 把结构描述变成可编辑的技术图，支持圆角/曲线/直连、无框图标与跨后端 .excalidrawlib 素材 | Excalidraw · draw.io · Mermaid · PNG |
| [**cosmic-split**](skills/cosmic-split/README.md) | 按需求、接口、页面或代码识别 COSMIC 数据移动 | 拆分表 · 自检报告 · 覆盖清单 |
| [**email-composer**](skills/email-composer/README.md) | 起草与制作工作邮件，复用 Spec / HTML 模板 | 邮件草稿 · .eml · 模板库 |

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
| [**repo-baseline**](skills/repo-baseline/README.md) | 检测并补齐仓库工程基线，只补缺失项 | 基线文件 · 检测报告 · 巡检结论 |
| [**learning-scout**](skills/learning-scout/README.md) | 把学习需求研究成一组独立笔记与离线入口页 | 笔记 · HTML 入口 · 打印版 · PDF |

### 产品、设计与研发

| Skill | 做什么 | 产出 |
| --- | --- | --- |
| [**product-spec**](skills/product-spec/README.md) | 澄清模糊需求、收敛范围边界、对比方案并写可复测 AC | 产品规格书 · 编号 AC · 异常矩阵 |
| [**ui-design-craft**](skills/ui-design-craft/README.md) | 界面视觉与交互工艺、反模板审视、动效打磨与极端加固 | 设计调整方案 · 动效规范 · 5 维审计报告 |
| [**frontend-engineering**](skills/frontend-engineering/README.md) | React/TS 组合架构、异步与重渲染优化、作用域 CSS 与根因调试 | 组合组件与纯模型 · 性能与样式修复 |
| [**arch-backend-craft**](skills/arch-backend-craft/README.md) | 跨语言（Node / Python / Java）系统架构、单源事实、后端安全契约、迁移回滚与分级评审 | 架构决策 · 迁移实现 · 分级评审报告 |
| [**tdd-testing**](skills/tdd-testing/README.md) | 红绿重构 TDD、真实行为测试、测试隔离与污染定位、完成前验证门控 | 自动化测试 · 污染定位 · 验证报告 |
| [**ui-qa-acceptance**](skills/ui-qa-acceptance/README.md) | 真实页面黑盒交互验收、7 维高压质检与本地多服务启停 | 验收结论 · AC 核对表 · 分级缺陷单 |

Obsidian 两项能力各自独立，通过笔记数据关联。

例如：“使用 `$deck-authoring` 把材料做成演示文稿”、“使用 `$diagram-authoring` 画出带无框图标和圆角连线的网络拓扑图”，或“使用 `$product-spec` 把这条模糊需求整理成可验收规格书”。
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
| [`build_site.py`](tools/build_site.py) | 从 README 与 skill 文档生成项目站点（首页 + docs） |

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

官方安装器维护各 Agent 的路径与更新；本仓库的 `tools/install_skills.py` 仍然一次安装全部 17 个。
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
├── skills/        # 17 个可独立安装的 skill
├── tools/         # 安装、锁文件、迁移、体检、skill 编写
├── tests/         # 回归测试，按 skill 分目录
├── docs/          # 生成的项目站点（GitHub Pages 发布）
├── .github/       # CI 与 Pages 发布
├── .githooks/     # 提交检查
└── skills-lock.json
```

## 开源借鉴与整合说明

本仓库的原创文档、工作流编排与自研脚本采用 [MIT License](LICENSE)。其中 `产品、设计与研发` 分组的 6 个工程流 skill 并非凭空撰写，而是在参考多个优秀开源 Agent Skill 项目的核心方法论后，进行了**交叉整合、去冗余合并、跨技术栈泛化与工具脚本重写**。各上游项目均按其原始开源许可在此及对应 skill 文档中公开致谢，且不将上游规则条目、内部指标或原始文件直接等同于本仓库状态。

> 注：[`deck-authoring`](skills/deck-authoring/README.md#维护与借鉴) 的自由排版路线与开源生态取舍已在 [`skills/deck-authoring/references/layout-technology.md`](skills/deck-authoring/references/layout-technology.md) 单独记录；[`diagram-authoring`](skills/diagram-authoring/README.md) 使用标准 `.excalidrawlib` 素材格式并支持按需选用外部图标库，其来源约束与使用说明详见该 skill 文档。

### 上游参考项目与许可

| 上游仓库 | 主要参考组件 / Skill | 引用与借鉴的核心方法 | 开源许可 |
| --- | --- | --- | --- |
| [`obra/superpowers`](https://github.com/obra/superpowers) | `brainstorming`、`writing-plans`、`systematic-debugging`、`test-driven-development`、`requesting-code-review`、`receiving-code-review`、`verification-before-completion` | 探索式单问收敛、独立构建视角审查、零占位符任务拆分、四阶段根因溯源与纵深防御、条件等待与轮询隔离、RED → GREEN → REFACTOR 纪律及完成前实证要求 | MIT License |
| [`pbakaus/impeccable`](https://github.com/pbakaus/impeccable) | `impeccable` 主体系与 `reference` 方法集（访客模式、质量底线、排版、色彩、交互、打磨、极值加固与审查打分） | 三类访客模式识别、界面质量底线、字体与色彩节制、信息精简与引导优化、极端内容加固以及多维度设计审查尺度 | Apache License 2.0 |
| [`vercel-labs/agent-skills`](https://github.com/vercel-labs/agent-skills) | `react-best-practices`、`composition-patterns`（并结合 `web-design-guidelines` 检查视角） | 按性能收益排名的前端关键路径优化（异步瀑布流、包体积、服务端/RSC、客户端去重、重渲染与渲染微优化、高级 Hooks）与复合组件/显式变体组合架构 | MIT License |
| [`anthropics/skills`](https://github.com/anthropics/skills) | `frontend-design`、`webapp-testing` | 明确美学方向与反模板化前端设计立意；本地多服务托管及「静默页面探测先于自动化点击」的浏览器测试思路 | 按其各技能目录 `LICENSE.txt` 条款 |

### 各整合 Skill 的引用与调整对照

| 本仓库 Skill | 主要引用来源 | 整合调整与自研增强 |
| --- | --- | --- |
| [`product-spec`](skills/product-spec/README.md) | `obra/superpowers`（`brainstorming`、`writing-plans`） | 收口为 7 步连续门控与「未定稿不写代码」硬闸门；新增短/全规格双深度路由、18 类模糊词改写为 Given/When/Then 可测 AC、9 场景边界异常矩阵及实施计划桥接；剥离原仓库宿主会话 Hook 与固定目录假设 |
| [`ui-design-craft`](skills/ui-design-craft/README.md) | `pbakaus/impeccable`（`impeccable` 全参考体系）、`anthropics/skills`（`frontend-design`） | 将二十余份分散规范与斜杠指令整合为「3 类访客模式 × 5 种工艺模式」统一路由与 10 份专题参考；新增中文与中英混排补偿、桌面多表面打磨及 `P0–P3` 缺陷分级；去除与简洁工作台/社论风格冲突的一刀切禁用表 |
| [`frontend-engineering`](skills/frontend-engineering/README.md) | `vercel-labs/agent-skills`（`react-best-practices`、`composition-patterns`）、`obra/superpowers`（`systematic-debugging`） | 将零散规则按前端性能、组合架构与状态影响面重构为 9 份按场景加载的手册；融合四阶段排错与连续失败熔断；补充无 `!important` 样式隔离、粘滞滚动、`focus-return`、竞态取消与 React 19 状态 Action；解除纯 Next.js/Vercel 框架绑定，兼容 Vite/SPA |
| [`arch-backend-craft`](skills/arch-backend-craft/README.md) | `obra/superpowers`（`systematic-debugging`、`requesting-code-review`、`receiving-code-review`、`verification-before-completion`） | 保留根因溯源、纵深防御与实证审阅主干，**泛化为跨语言后端指南**：新增 Python（FastAPI / Django / SQLAlchemy / Alembic）与 Java（Spring Boot / JPA / MyBatis / Flyway / HikariCP）专门指引；补充 SSOT、唯一公共入口、五级配置优先级、`realpath`/Zip-Slip 校验、凭据保护与 Expand-Contract 零停机迁移 |
| [`tdd-testing`](skills/tdd-testing/README.md) | `obra/superpowers`（`test-driven-development`、`systematic-debugging`、`verification-before-completion`） | 统一红绿重构与反镜像断言铁律；用自研跨平台 Python 3.10+ 标准库脚本 `scripts/find_polluter.py`（支持 `--json`、预检与早停，附单元测试）取代 shell 版污染扫描思路；新增 `L1–L4` 分层测试策略表、LIFO 清理栈治理与变异校验 |
| [`ui-qa-acceptance`](skills/ui-qa-acceptance/README.md) | `anthropics/skills`（`webapp-testing`）、`pbakaus/impeccable`（审查与极值思路）、`obra/superpowers`（`verification-before-completion`） | 用自研 Python 3.10+ 标准库 `scripts/with_server.py`（进程组销毁、多服务编排与 HTTP 就绪探测，附单元测试）替代示例脚本；新增七维高压测试矩阵、DOM 几何溢出检测脚本、Electron/WebView 隔离 `USER_DATA` 与 SPA Hydration 验收及 `Blocker–Low` 报告模板 |

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
  <sub>原创代码与文档采用 <a href="LICENSE">MIT License</a>；借鉴整合的开源方法论、第三方依赖、字体与外部素材按各自原始许可标注并使用。</sub>
</p>
