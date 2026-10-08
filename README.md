# ![agent-skills](assets/icons/agent-skills-light.svg#gh-light-mode-only) ![agent-skills](assets/icons/agent-skills-dark.svg#gh-dark-mode-only) Agent Skills

个人维护的 Agent 工作流：演示文稿、技术图、Obsidian 知识管理、Git、PingCode 和 skill 设计。
每个目录都以 `SKILL.md` 描述触发条件与操作流程，`README.md` 提供依赖、用法和限制。

## Skills

| Skill | 用途 |
| --- | --- |
| [deck-authoring](skills/deck-authoring/README.md) | 从结构规格制作演示文稿，建立项目视觉风格，预览并导出 HTML、PDF、PNG、PPTX 或视频 |
| [diagram-authoring](skills/diagram-authoring/README.md) | 从结构描述生成技术图，支持 Excalidraw 与 draw.io，并检查布局和引用 |
| [obsidian-personal-knowledge-base](skills/obsidian-personal-knowledge-base/README.md) | 创建、更新、归位和审阅笔记，维护 PARA 目录与 MOC |
| [obsidian-work-log-release-recorder](skills/obsidian-work-log-release-recorder/README.md) | 将已完成的开发、配置和发布事实记录到工作日志、发版文档与长期知识 |
| [git-dev-workflow](skills/git-dev-workflow/README.md) | 本地 Git 写操作的状态探查、风险检查、提交规划和结果核验 |
| [pingcode](skills/pingcode/README.md) | 查询和维护 PingCode 项目、工作项、迭代和看板，按真实接口解析名称和 ID |
| [skill-builder](skills/skill-builder/README.md) | 设计新 skill、评审触发边界，提供仓库结构与引用检查工具 |

例如：“使用 `$deck-authoring` 把材料做成演示文稿”，或“使用 `$pingcode` 查我的待办”。
是否自动发现和如何显式调用，取决于使用的 Agent。

## 安装

克隆仓库后，在仓库根目录执行：

```sh
python3 tools/install_skills.py
python3 tools/install_skills.py --check
```

默认安装到 `~/.agents/skills/`，使用指向当前仓库的软链，修改即时可见。
目标 Agent 使用其他目录时，通过 `--install-dir` 指定；安装器的 `--help` 提供完整选项。
仓库可能移动或需要固定副本时使用 `--copy`，更新后再次安装并检查。
已有安装内容有差异时，先查看安装器提示，避免覆盖本机定制。

Python 是维护工具的基础依赖；各 skill 所需的浏览器、图形工具、Python 包和外部服务配置，
见各自 README。安装 skill 不等于安装这些运行依赖。

## 配置

本机配置放在用户配置目录，令牌、账号和实际 vault 路径不随 skill 分发。
主要配置包括 Obsidian vault 路径、PingCode 凭据与令牌缓存、名称泄露词表。
各解析器的环境变量、文件位置和兼容路径以对应 README 为准。

`skills-lock.json` 是仓库派生文件，记录 SKILL.md 的哈希；
被忽略的 `.skill-lock.json` 是本机安装状态，两者用途不同。

## 开发与验证

- `SKILL.md` 保留入口和必要流程，`references/` 按需放详细说明，避免重复维护规则。
- `scripts/`、`assets/` 只放实际使用的程序或素材；目录不是必须凑齐的清单。
- 回归测试放在根目录的 `tests/<skill>/`，仓库工具测试在 `tools/tests/`。
- `evals/evals.json` 保存触发和行为场景，不代表这些场景已自动执行或通过。
- 删除文件前检查代码、文档和动态加载的消费者；忽略的本机文件不作为普通清理对象。

从仓库根目录运行：

```sh
python3 skills/skill-builder/scripts/preflight.py
python3 -m unittest discover -s tests/skill-builder -v
python3 -m unittest discover -s tools/tests -v
python3 tools/skills_lock.py --update
python3 tools/skills_lock.py --check
```

修改其他 skill 时，将测试目录替换为对应名称。Deck 的浏览器和 PDF 测试需要其运行依赖。
`preflight.py` 执行结构、名称泄露与本地引用检查，并统计测试文件；它不执行回归或视觉验收。
`tools/skill_health.py` 给出维护建议；`tools/skill_trigger_log.py` 可分析所支持的本机会话日志，
覆盖范围取决于日志来源，不能代表所有 Agent 的使用情况。

## 提交检查

如需启用仓库 hook，执行一次：

```sh
git config core.hooksPath .githooks
```

提交涉及 `skills/`、`tests/`、`tools/` 或 `.githooks/` 时运行：

| 检查 | 行为 |
| --- | --- |
| 结构、敏感名称、引用目标、文档中的测试数字 | 发现错误时阻塞；敏感名称词表未配置则跳过该扫描 |
| 各 skill 与仓库工具回归 | 默认失败只提示；`AGENT_SKILLS_GATE=1` 时阻塞；跳过项单独报告 |
| 仓库体检 | 维护建议，不阻塞 |
| 锁文件同步 | 按暂存区的 SKILL.md 直接更新锁文件的暂存版本，保留工作区未暂存内容 |

检查上限与具体规则以脚本为准。通过静态检查不代表外部服务可用、视觉产物合格或所有集成测试已执行。
后续方向见 [ROADMAP.md](ROADMAP.md)。
