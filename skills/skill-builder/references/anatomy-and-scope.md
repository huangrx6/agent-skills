# Anatomy of a Skill & Scope Boundaries

Reference material — not part of the core 5-minute decision flow. Read this only when you need to decide which subdirectory a piece of content belongs to.

## Anatomy of a Skill

```text
<skill-name>/
├── SKILL.md                # 必填:YAML frontmatter(name + description)+ Markdown 正文
├── references/             # 按需加载的长文参考(决策树、anti-patterns、术语表)
├── assets/                 # 输出用模板 / 数据 / 图表 / 图标
├── scripts/                # 可执行脚本(uv run / node),仅当 SKILL.md 不够时再加
├── agents/                 # 子 agent 定义,默认不放
└── examples/               # 输入输出示例,默认不放
```

**默认只有 SKILL.md**。`references/` 在正文超过 ~150 行时再加。其他目录按需——能不放就不放。

## Out of Scope(本 skill-builder 不负责的事)

- **Formal eval**:脚本化的触发准确度测量,需要单独流程
- **Asset / icon 自动生成**:本 skill 不产出视觉资源
- **与 Agent 加载机制耦合的兼容性测试**:交给各 Agent 维护者
- **skill-creator 风格的"建 skill 全流程"教学**:那个 skill 已经被这个仓库删除——skill-builder 是它的精简替代

## 哪些内容该放 references/ 而不是 SKILL.md?

- 决策树的可视化(mermaid / dot)
- 完整 anti-pattern 清单(超过 5 条时)
- 跨 skill 共用的写作约定
- 大段术语表 / 缩写解释
- 历史决策日志(为什么这么设计)
