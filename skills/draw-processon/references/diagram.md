# ProcessOn 图表引擎

将此分支用于关系导向和技术图表。

## 选择图表类型

- 流程/程序 → 流程图
- 跨角色/流程所有权 → 泳道图
- 运行时调用/消息 → 时序图
- 模块/服务/依赖 → 架构图
- 表/实体/键 → ER 图
- 部署/运行时主机 → 部署/云架构
- 状态转换 → 状态流图
- 随时间推移的里程碑 → 时间线/路线图

如果用户明确指定了类型，请使用该类型。

## 构建高质量的生成提示

在生成之前，提取实际的实体和关系。仅包含用户材料或仓库证据支持的信息。

对于技术图表，优先考虑：

- 清晰的子系统边界；
- 调用/数据/消息的明确方向；
- 重要边缘上的有意义标签；
- 重要的外部系统和持久化层；
- 简洁的节点，而不是文件级别的噪音。

图表特定指导：

- 流程图：明确的开始/结束；决策点应明确无误。
- 时序图：首先识别参与者，然后是有序的消息和关键返回。
- 架构图：按层/边界组织，并标记关键通信路径。
- ER：包含材料实体、关键字段、PK/FK 关系以及基数（如果源支持）。

## 认证

包含的包装器使用 ProcessOn 的浏览器授权流程及其可流式 HTTP MCP 端点。

从此技能目录运行：

```bash
node scripts/processon-diagram.mjs check
```

可能的输出：

- `READY` → 立即生成。
- `AUTH_REQUIRED:<url>` → 向用户显示确切的 URL 并要求他们打开。
- `ERROR:*` → 报告简洁的错误。

显示 `AUTH_REQUIRED:<url>` 后，轮询：

```bash
node scripts/processon-diagram.mjs poll
```

如果返回 `TOKEN_PENDING`，请稍等片刻并再次轮询。如果自动轮询不切实际，请要求用户在授权后回复并运行：

```bash
node scripts/processon-diagram.mjs fetch
```

如果生成请求报告 `AUTH_EXPIRED`，请运行：

```bash
node scripts/processon-diagram.mjs reauth
```

并显示新的授权 URL。

## 生成

创建一个简洁但信息丰富的自然语言提示，然后运行：

```bash
node scripts/processon-diagram.mjs generate "<prompt>"
```

包装器调用 ProcessOn MCP 工具 `generate_chart`。

成功时，返回工具响应中的预览/编辑链接。当用户要求 ProcessOn 可编辑图表时，不要用 SVG/HTML 替换 ProcessOn 生成。