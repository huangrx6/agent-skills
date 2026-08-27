# AI 上下文与 Agent 指令

## 目录

- [三种信息必须分开](#三种信息必须分开)
- [AGENTS.md](#agentsmd)
- [PROJECT_CONTEXT.md](#project_contextmd)
- [目录级指令](#目录级指令)
- [多 AI 工具](#多-ai-工具)
- [AI 启动流程](#ai-启动流程)
- [上下文预算](#上下文预算)
- [可信度规则](#可信度规则)

## 三种信息必须分开

### 执行指令

例如：

```text
修改后运行什么测试
禁止修改什么
必须先读什么
```

放 `AGENTS.md`。

### 项目稳定事实

例如：

```text
系统做什么
关键模块在哪里
订单数据由谁拥有
```

放 `PROJECT_CONTEXT.md` 或长期 docs。

### 临时任务状态

例如：

```text
重构完成了前两步
测试 X 还失败
下一步改文件 Y
```

放 active handoff，不放 AGENTS 或 PROJECT_CONTEXT。

## AGENTS.md

OpenAI Codex 会在开始工作前加载 `AGENTS.md` 层级指令。

根级文件应保持短小，只包含高价值执行规则：

```text
# Before work
- Read PROJECT_CONTEXT.md.
- Read docs/index.md.
- Read only the domain docs relevant to the task.

# Validation
- Run ...

# Documentation
- Before finishing, perform documentation impact analysis.
```

不要写：

- 20 页架构说明；
- API 字段表；
- 数据库表定义；
- 每个历史事故；
- 大量示例。

OpenAI Codex 当前默认对合并后的项目指令使用 32 KiB 上限，因此根级文件建议远低于此值。可以把特殊规则放到更靠近目标目录的 `AGENTS.md`/`AGENTS.override.md`。

## PROJECT_CONTEXT.md

这是跨 AI 工具共享的项目知识入口。

目标：

- 新会话在几分钟内理解项目；
- 不依赖某个模型厂商；
- 可以由 AGENTS、CLAUDE、Copilot、Cursor 等工具指向同一事实来源。

它不是自动指令文件，因此可以比 AGENTS 稍详细，但仍应有界。

## 目录级指令

服务或子项目有不同命令、约束、安全规则时，使用更靠近代码的 Agent 指令。

规则：

- 根级写全局规则；
- 子目录只写差异；
- 不复制根级内容；
- 临时 override 必须有退出计划。

Codex 的自动发现取决于启动时从项目根到当前工作目录的路径。Agent 从仓库根运行时，不应假设所有更深目录的指令都会自动加载；工作到特殊目录时要确认对应指令是否生效。

## 多 AI 工具

推荐“Canonical Core + Adapter”：

```text
PROJECT_CONTEXT.md        # 公共事实
docs/                     # 公共知识
AGENTS.md                 # Codex adapter/instructions
CLAUDE.md                 # 可选 Claude adapter
.github/...               # 可选 Copilot adapter
.cursor/...               # 可选 Cursor adapter
```

Adapter 只写：

- 工具加载方式；
- 工具特有命令；
- 指向公共事实的读取要求。

禁止把同一项目规则复制到四套 Agent 文件。

## AI 启动流程

新 Agent 开始任务时：

1. 加载适用 Agent 指令；
2. 读取 `PROJECT_CONTEXT.md`；
3. 读取 `docs/index.md`；
4. 根据任务类型选择 1–3 个相关 canonical 文档；
5. 检查目标代码附近是否有更具体指令；
6. 再读取代码和测试。

不要先遍历全仓库再建立模型。

## 上下文预算

AI 上下文应采用渐进披露：

- 启动信息尽量少；
- 导航信息优先于详细正文；
- 按任务加载；
- 大型生成参考不默认加载；
- 过长文档拆成主题而不是任意分页。

推荐内部预算：

- 根 AGENTS：≤ 12 KiB（向下补充子目录 AGENTS.md/AGENTS.override.md 负责溢出）；
- PROJECT_CONTEXT：≤ 12 KiB；
- docs/index：≤ 8 KiB；
- 单个高频参考：尽量 ≤ 20 KiB。

子目录 AGENTS.override.md 可以容纳服务/子项目的局部规则、特殊命令或额外 guardrails。Codex 从项目根运行时仅加载根 AGENTS.md；Agent 工作到特殊目录时需主动检查 `AGENTS.override.md` 是否被加载。

这些是团队治理建议，不是协议限制；目的是让启动上下文有界，详细知识下沉。

## 可信度规则

文档不是永远正确。

Agent 遇到以下情况必须回到代码/Schema/运行配置验证：

- 文档与代码明显冲突；
- 文档超过 review 周期；
- 行为最近大改；
- 涉及安全/数据迁移/生产操作；
- 文档声明自己是 generated 或 secondary。

发现冲突后修正 canonical source，而不是在回答中默默忽略。
