# 标准与权威来源

## OpenAI Codex AGENTS.md

- Custom instructions with AGENTS.md  
  https://learn.chatgpt.com/docs/agent-configuration/agents-md

Codex 在工作前读取适用的 AGENTS.md。当前文档说明：

- 支持用户级和项目级指令；
- 项目内从根到当前工作目录分层；
- 更靠近当前目录的规则后加载并覆盖更广规则；
- 默认 `project_doc_max_bytes` 为 32 KiB；
- 可以用目录级 AGENTS/override 拆分特殊规则。

因此本 Skill 不把完整项目知识放进 AGENTS。

## OpenAI Skills

- Build skills  
  https://learn.chatgpt.com/docs/build-skills

Skills 本身使用渐进披露：先暴露 name/description，实际使用时再加载 SKILL.md 和按需资源。本 Skill 对项目文档采用类似原则：入口短、索引清楚、详细知识按需加载。

## Docs as Code

- Write the Docs — Docs as Code  
  https://www.writethedocs.org/guide/docs-as-code/

Docs as Code 使用 Git、纯文本、代码评审和自动测试等开发工作流维护文档。

## Diátaxis

- Diátaxis  
  https://diataxis.fr/

Diátaxis 区分 Tutorial、How-to、Reference、Explanation 四种不同用户需要。本 Skill 使用它帮助判断文档目的，但不要求项目机械创建四个顶级目录。

## ADR

- Architecture Decision Record repository  
  https://github.com/architecture-decision-record/architecture-decision-record

ADR 保存重要架构决定、上下文和后果。决策变化时，应保留历史并通过新记录表达替代关系。

## C4

- C4 Model  
  https://c4model.com/

C4 使用不同缩放层级帮助理解软件系统。官方说明 System Context 和 Container 图对多数团队已足够，不应默认维护所有层级。

## 使用原则

- 外部框架用于指导，不替代项目具体事实。
- 工具行为可能变化，应以当前官方文档为准。
- 文档结构服务可发现性，不为了符合某框架建立空目录。
