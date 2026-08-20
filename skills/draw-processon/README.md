# ProcessOn 统一技能（适用于 DSH）

面向 DSH 的三个 ProcessOn 技能系列的整合：

- 技术/结构化图表生成；
- 思维导图生成；
- 文档转思维导图处理。

DSH 只暴露一个技能名称：`processon`。该技能在内部进行路由。

## 安装

### Linux / macOS

从包根目录：

```bash
./install.sh
```

### Windows PowerShell

```powershell
./install.ps1
```

或者手动将 `processon` 目录复制到：

```text
~/.dsh/skills/processon
```

您的 DSH 预设必须暴露 `@deepseek-ai/dsh-skill-filesystem` 和 `@deepseek-ai/dsh-tool-skill`（DSH Standard 风格的预设通常如此）。

## 运行时要求

- 推荐 Node.js 18+。
- 实际生成时需要访问 ProcessOn 端点的互联网。
- 图表生成需要一次性 ProcessOn 浏览器授权。
- 思维导图生成使用 ProcessOn 的 Markdown 转换服务。

此包不需要单独的 DSH MCP 服务器形式条目。图表包装器在授权后直接与 ProcessOn 的 HTTP MCP 端点通信。

## 示例提示

- `分析当前项目并用 ProcessOn 画一张系统架构图`
- `把登录调用过程画成时序图`
- `根据这些 MySQL 表结构生成 ER 图`
- `把这个需求拆成 ProcessOn 思维导图`
- `读取这个 PDF，把内容整理成 ProcessOn 脑图`

## 路由

- 架构 / 流程 / 时序 / ER / 泳道 / 依赖 / 重绘 → 图表
- 知识层次 / 任务分解 / 头脑风暴 / 大纲 → 思维导图
- 文档 + 总结/结构/思维导图 → 文档转思维导图

## 注意事项

此包是基于当前公开的 ProcessOn 技能行为和接口构建的 DSH 特定集成层。它不是官方的 ProcessOn 版本，并且故意不逐字镜像上游技能提示。有关上游参考，请参阅 `SOURCES.md`。