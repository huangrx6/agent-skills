# Docs-as-Code 与自动化

## 目录

- [基本原则](#基本原则)
- [CI](#ci)
- [文档影响分析](#文档影响分析)
- [生成文档](#生成文档)
- [链接和索引](#链接和索引)
- [防止陈旧](#防止陈旧)
- [AI 自动更新](#ai-自动更新)

## 基本原则

工程文档使用与代码相同的：

- Git；
- Review；
- CI；
- Issue；
- Ownership。

Write the Docs 将 Docs as Code 描述为使用版本控制、纯文本、代码评审和自动测试等软件开发工作流管理文档。

## CI

建议检查：

- Markdown lint；
- 内部链接；
- 外部链接按计划检查；
- 重复标题/断链；
- docs/index 覆盖；
- metadata；
- AGENTS/PROJECT_CONTEXT 大小；
- OpenAPI/Proto 等生成引用；
- 架构图生成；
- 文档示例和命令。

不要为所有措辞建立机械 lint。

## 文档影响分析

维护 `document-impact-rules.csv`。

例如：

```text
src/api/** → contracts
migrations/** → data + operations
infra/** → operations + architecture
```

CI 或 Agent 根据 changed files 输出“需要检查”的文档，而不是强制每次都改文档。

## 生成文档

适合生成：

- API Reference；
- CLI Reference；
- 配置项；
- Schema；
- 依赖图；
- C4/diagram render；
- 错误码表。

规则：

- Source 文件是事实来源；
- generated 文件标明不可手改；
- 生成器版本固定；
- CI 检查生成结果无漂移。

## 链接和索引

所有长期文档必须从以下至少一个入口可到达：

- docs/index；
- 主题 index；
- PROJECT_CONTEXT；
- 相关 canonical doc。

孤儿文档对人和 AI 都接近不存在。

## 防止陈旧

使用：

- Owner；
- change trigger；
- last_reviewed；
- CI impact hint；
- periodic stale report。

不要自动更新 `last_reviewed` 只为了让 CI 变绿。

## AI 自动更新

AI 可以自动：

- 根据 diff 建议受影响文档；
- 修改明确受影响的 canonical 文档；
- 更新索引；
- 创建 ADR 草案；
- 关闭 handoff；
- 校验链接。

AI 不应自动：

- 猜测新团队规则；
- 修改历史决策内容；
- 把聊天记录原样提交；
- 编造 Owner；
- 为没有内容的目录制造空文档。
