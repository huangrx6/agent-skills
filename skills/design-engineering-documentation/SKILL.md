---
name: design-engineering-documentation
description: "设计、建立、审查和维护面向人类开发者与 AI Coding Agent 的工程文档体系，包括文档目录与分层、README、PROJECT_CONTEXT.md、AGENTS.md、项目概览、领域词汇、架构文档、ADR/决策记录、开发指南、接口与数据文档、运行手册、工作约定、任务交接、文档生命周期、创建还是更新的判断、AI 任务结束后的文档影响分析、对话知识沉淀、个人偏好与团队规则的边界、Docs-as-Code、自动校验和文档防腐。用于新项目文档初始化、AI-first 仓库设计、已有文档重构、新成员/新 AI 会话快速理解项目，以及在代码变更后同步维护项目知识。不覆盖系统架构、API 契约、数据库设计与代码书写规范的具体内容。"
---

# 工程文档设计

## 目标

建立一个同时服务人类和 AI Agent 的工程知识系统：

- 人类进入项目后能快速知道“这是什么、怎么运行、怎么改、为什么这样设计”；
- 新 AI 会话不需要先扫描整个仓库，就能从受控入口获得项目结构、关键约束和文档路由；
- 详细知识只在需要时加载，避免把全部上下文塞进 Agent 指令；
- 代码、契约、配置和文档具有明确事实来源，不维护互相冲突的复制品；
- 每次任务结束时，Agent 能判断哪些长期知识值得沉淀、应更新哪个文件、何时需要新建文档。

## 推荐四层模型

### L0：Agent 启动指令

仓库根目录使用 `AGENTS.md`，只放：

- 开始工作前必须读取什么；
- 构建、测试、检查命令；
- 禁止事项；
- 修改文档的工作流；
- 目录级特殊规则。

不要把完整架构、API、数据库设计或历史决策塞进 `AGENTS.md`。

### L1：项目快速上下文

仓库根目录使用 `PROJECT_CONTEXT.md`，面向所有 AI 工具和人类读者。

它只保存当前稳定快照：

- 项目目标；
- 代码库地图；
- 核心技术栈；
- 架构摘要；
- 关键领域概念；
- 关键不变量和风险；
- 常用命令；
- 指向详细文档的链接。

保持有界、可快速读取，不保存任务流水账。

### L2：文档索引与长期知识

使用 `docs/index.md` 作为唯一文档导航入口，再按主题进入：

- project；
- architecture；
- decisions；
- development；
- contracts；
- data；
- operations；
- working-agreements；
- handoffs。

不要要求读者按文件系统盲目搜索。

### L3：时间性记录

只把需要保留时间上下文的内容写成独立记录：

- ADR/决策；
- 事故复盘；
- 迁移计划；
- 活跃任务 handoff。

时间性记录不能取代当前状态文档。

## 工作流

1. 识别文档消费者：新人、现有开发者、运维、架构评审、外部调用方、AI Agent。
2. 识别信息类型：当前事实、操作步骤、技术参考、解释、历史决策、临时任务状态、团队工作约定。
3. 查找当前唯一事实来源；优先更新已有 canonical 文档。
4. 只有主题、生命周期或所有权确实不同才新建文档。
5. 对重大决策新建 ADR，而不是重写旧决策历史。
6. 对代码可生成的信息，更新源文件并重新生成，不手工维护复制品。
7. 在任务完成前执行文档影响分析。
8. 从任务对话和 diff 中只沉淀稳定、明确、项目相关且非敏感的知识。
9. 校验索引、链接、Owner、陈旧文档和 Agent 上下文大小。
10. 删除失效文档或明确标记 superseded/archived，不让错误文档继续被 AI 检索。

## 核心规则

- 文档是产品的一部分，使用 Git、代码评审和 CI 管理。
- 每条重要知识必须有唯一 canonical source。
- `README.md` 是人类入口，不是项目百科。
- `AGENTS.md` 是执行指令，不是项目知识仓库。
- `PROJECT_CONTEXT.md` 是稳定项目快照，不保存临时进度、个人聊天记录或完整历史。
- `docs/index.md` 是导航图，不复制所有文档内容。
- 文档标题、文件名和目录按读者要解决的问题组织，而不是按作者或会议组织。
- “教程、How-to、Reference、Explanation”应保持目的清晰，不把所有内容混成一个长文档。
- 新功能、接口、配置、架构、数据模型和运行方式发生变化时，文档与代码在同一变更中更新。
- 重大、难逆转、有多个方案的重要决策写 ADR；普通实现细节不写 ADR。
- ADR 的历史决定不应静默改写；改变决定时创建新 ADR 并 supersede 旧记录。
- 临时任务 handoff 只用于未完成或跨会话工作；任务完成后关闭、归档或删除，不能无限积累。
- 不自动把一次性的聊天要求升级为团队规范。
- 用户明确说“以后这个项目都这样”“统一采用”“团队约定”时，可沉淀为项目工作约定。
- 从重复对话推断出的个人偏好只能作为候选，不应直接提交到共享仓库。
- 跨项目个人偏好属于用户级 Agent 配置，不属于项目文档；写入前需明确同意。
- 密钥、令牌、客户数据、隐私信息和安全敏感细节不得为了“帮助 AI”写入上下文文档。
- 文档必须有边界；不能通过无限增加文件解决可发现性问题。
- AI 在开始任务时先读索引和相关 canonical 文档，再按需读取代码；不能只相信陈旧文档。
- AI 在修改事实时必须同时检查文档；不能把文档维护作为可选收尾。

## 参考文件选择

- 设计目录、分层、README/PROJECT_CONTEXT/docs/index：读取 [references/information-architecture.md](references/information-architecture.md)。
- 配置 AGENTS.md、AI 启动上下文和多 Agent 工具适配：读取 [references/ai-context-agents.md](references/ai-context-agents.md)。
- 判断何时新建、何时更新、Owner、Review Cycle 和文档状态：读取 [references/document-lifecycle.md](references/document-lifecycle.md)。
- AI 完成任务后自动从对话、diff 和测试结果沉淀知识：读取 [references/task-completion-synthesis.md](references/task-completion-synthesis.md)。
- 管理团队习惯、个人偏好、工作约定和隐私边界：读取 [references/working-agreements-memory.md](references/working-agreements-memory.md)。
- 区分 Tutorial、How-to、Reference、Explanation 和不同文档类型：读取 [references/document-types.md](references/document-types.md)。
- ADR、决策历史和架构知识：读取 [references/decision-records.md](references/decision-records.md)。
- 跨人/跨会话未完成任务交接：读取 [references/handoffs-current-state.md](references/handoffs-current-state.md)。
- Docs-as-Code、CI、链接、漂移和生成文档：读取 [references/docs-as-code-automation.md](references/docs-as-code-automation.md)。
- 需要官方来源和标准依据：读取 [references/standards-sources.md](references/standards-sources.md)。
- 需要完整产出样例时：读取 [examples/README.md](examples/README.md) 下的虚构项目示范。

## 职责边界

- 系统架构内容本身：不属本 Skill 范围。
- API 契约内容本身：不属本 Skill 范围。
- 数据库设计与迁移：不属本 Skill 范围。
- 代码书写规范：不属本 Skill 范围。
- 异常和日志：对应独立 Skill。

本 Skill 负责“知识放在哪里、如何被发现、何时更新、如何防止漂移”。

注：ADR 文档的放置、生命周期、AI 发现与索引属本 Skill；ADR 记录的架构决策内容属架构层。

## 输出结构

完整文档体系优先采用：

1. L0 Agent 启动指令（`AGENTS.md`）；
2. L1 项目概览（README、PROJECT_CONTEXT.md）；
3. L2 领域与架构文档（ADR、架构图、领域词汇）；
4. L3 开发指南与运行手册（开发/部署/排障）；
5. L4 任务交接与当下状态（handoff、current-state）。

使用“必须、应、可”表达约束强度。文档层级与路由是本组织决策，不直接复制他人默认。

## 内置资源

- [assets/project-documentation-tree.template.txt](assets/project-documentation-tree.template.txt)：推荐目录。
- [assets/project-context.template.md](assets/project-context.template.md)：AI/Human 快速上下文模板。
- [assets/agents.template.md](assets/agents.template.md)：根级 Agent 指令模板。
- [assets/docs-index.template.md](assets/docs-index.template.md)：文档索引模板。
- [assets/working-agreements.template.md](assets/working-agreements.template.md)：工作约定模板。
- [assets/handoff.template.md](assets/handoff.template.md)：任务交接模板。
- [assets/decision.template.md](assets/decision.template.md)：决策记录模板。
- [assets/document-type-policy.csv](assets/document-type-policy.csv)：文档类型与更新策略。
- [assets/document-impact-rules.csv](assets/document-impact-rules.csv)：代码变更到文档影响的路由规则。
- [assets/documentation-review-checklist.csv](assets/documentation-review-checklist.csv)：评审清单。
- `scripts/validate_documentation_system.py`：验证 Skill 资产及项目文档结构。
- `scripts/doc_impact.py`：根据变更路径输出应检查的文档类别。

## 环境与运行

本 Skill 脚本统一通过 **uv** 运行（不使用宿主机的原始 Python，避免环境污染）。

- 所有脚本均为纯标准库，无需安装任何第三方包；uv 仅用于隔离 Python 解释器。
- uv 使用全局缓存（`~/.cache/uv`），**不会在每个 skill 目录创建 .venv**；Python 解释器与依赖在所有 skill 间共享，不重复下载。
- 固定路径约定：
  - uv 二进制：`~/.local/bin/uv`
  - 依赖与 Python 缓存：`~/.cache/uv`（全局共享）
  - Python 解释器：`~/.local/share/uv/python/`
  - 脚本：各 skill 的 `scripts/` 目录

首次使用前确保 uv 可用（不可用则自动安装，无需用户操作）：

```bash
python scripts/ensure_uv.py
# 或手动：curl -LsSf https://astral.sh/uv/install.sh | sh
```

统一运行方式：

```bash
uv run scripts/validate_documentation_system.py --assets assets/
uv run python -m unittest discover -s scripts/tests   # 跑测试
```

