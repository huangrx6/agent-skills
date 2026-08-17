---
name: design-api-contracts
description: "设计、选择、审查和完善 API 契约风格，包括资源化 HTTP/REST-style API、gRPC/Protobuf、GraphQL、WebSocket、Server-Sent Events、HTTP Streaming、Webhook、事件接口和 JSON-RPC。覆盖资源与方法语义、Schema、分页过滤、幂等与并发、实时连接、查询成本、版本兼容、弃用、OpenAPI、GraphQL Schema、Proto、AsyncAPI、契约测试、安全和 API 治理。用于建立组织级或项目级 API 设计规范、选择接口风格、评审接口方案、生成契约模板和兼容性检查清单。不覆盖错误码体系、统一错误响应实现、代码书写规范与日志格式。"
---

# API 契约设计

## 目标

先为问题选择合适的接口风格，再产出稳定、一致、可演进、可测试且可机器验证的契约。不要把 REST、RPC、GraphQL、实时连接和事件接口混成同一套规则，也不要为了技术统一强迫所有场景使用同一种协议。

## 支持的接口风格

本技能重点支持：

- **资源化 HTTP / REST-style API**：资源生命周期、CRUD、缓存、条件请求和广泛客户端兼容；
- **gRPC / Protobuf**：内部服务、强类型 RPC、低延迟和双向流；
- **GraphQL**：客户端驱动查询形状、聚合读取和多前端场景；
- **WebSocket**：低延迟、长连接、双向实时通信；
- **Server-Sent Events（SSE）**：服务器到客户端的单向事件流；
- **HTTP Streaming**：NDJSON、分块或流式响应等单请求持续输出；
- **Webhook**：跨系统异步回调；
- **事件 / Pub-Sub**：异步解耦、多消费者和可重放事实流；
- **JSON-RPC 2.0**：轻量命令式 RPC，适合资源模型不自然、又不需要完整 gRPC 工具链的场景。

SOAP/WSDL、OData、WebTransport 等只在现有生态、合作方或专门业务明确要求时采用，不作为默认核心。

## 工作流

1. 识别交互模型：资源生命周期、远程方法、客户端自选查询、单向推送、双向实时、异步广播或跨组织回调。
2. 读取 `references/api-style-selection.md` 选择主协议，不默认 REST。
3. 明确调用方、信任边界、延迟、吞吐、消息大小、连接时长和兼容期限。
4. 只加载所选协议的参考文件。
5. 为每个操作明确成功、失败、幂等、并发、取消、超时和重试语义。
6. 用机器契约定义字段类型、必填、可空、单位、枚举和限制。
7. 明确分页、批量、流式传输和大数据量行为。
8. 建立兼容矩阵、弃用流程和版本策略。
9. 运行契约 lint、Schema 验证、差异检测和契约测试。
10. 使用评审清单完成发布验收。

## 核心规则

- API 风格由交互模型和运维约束决定，不由团队偏好决定。
- HTTP API 不自动等同于 REST；没有采用完整 REST 约束时，应准确称为资源化或 REST-style HTTP API。
- 标识符对调用方视为不透明字符串。
- 时间、金额、单位、精度、时区、枚举、空值和默认值必须明确。
- 可重试写操作必须定义幂等机制；网络超时不能证明写入未发生。
- 并发修改必须有丢失更新防护，或明确接受最后写入者获胜。
- 长耗时操作必须定义异步状态模型，而不是无限占用同步请求。
- 流式和长连接接口必须定义连接生命周期、消息边界、顺序、重复、恢复、背压和限额。
- GraphQL 必须定义查询复杂度、深度、分页、部分数据和 Schema 演进策略。
- gRPC 必须定义 Deadline、取消、状态、消息大小、Streaming 和 Protobuf 兼容规则。
- 事件和 Webhook 必须假设重复投递可能发生，并定义幂等、顺序和重放行为。
- 契约兼容性必须由自动差异检查和跨版本测试验证。
- API 安全默认拒绝，资源级授权不能只依赖网关。

## 参考文件选择

- 选择 REST、gRPC、GraphQL、WebSocket/SSE、事件或 JSON-RPC：`references/api-style-selection.md`。
- 资源化 HTTP / REST-style：`references/resource-http-semantics.md`。
- GraphQL：`references/graphql.md`。
- WebSocket、SSE、HTTP Streaming：`references/realtime-streaming.md`。
- gRPC、Protobuf：`references/grpc-protobuf.md`。
- 事件与 Webhook：`references/events-webhooks.md`。
- JSON-RPC：`references/json-rpc.md`。
- 字段和 Schema：`references/schema-and-payloads.md`。
- 分页、过滤、排序和批量：`references/collections-and-batch.md`。
- 幂等、并发和异步：`references/idempotency-concurrency-async.md`。
- 版本、兼容和弃用：`references/versioning-compatibility.md`。
- OpenAPI、契约测试和治理：`references/specification-testing-governance.md`。
- 安全和隐私：`references/security-privacy.md`。
- 标准来源：`references/standards-sources.md`。

## 输出原则

完整规范优先包含：接口风格选择、主协议、数据 Schema、查询/流式/批量、幂等并发、安全、兼容弃用、机器契约和测试治理。

不要为了“全面”同时输出所有协议规则；只输出项目实际采用和准备采用的协议。

## 职责边界

- 异常分类、错误码体系、重试与超时策略：不属本 Skill 范围。
- 数据库表结构、索引、Schema 迁移：不属本 Skill 范围。
- 代码书写规范、命名、注释：不属本 Skill 范围。
- 日志格式与脱敏：不属本 Skill 范围。

本 Skill 负责“接口契约的风格选择、语义、Schema、兼容性与测试”，不复制上述领域的实施细节。

注：HTTP 幂等键的契约设计（Header、作用域、冲突行为）属本 Skill；API 字段命名属本 Skill；重试时的幂等消费与失败处理属错误处理层。

## 内置资源

- `assets/api-style-selection.csv`：接口风格选择矩阵。
- `assets/api-rule-catalog.csv`：API 核心规则目录。
- `assets/compatibility-change-matrix.csv`：变更兼容性矩阵。
- `assets/http-operation-status-map.csv`：HTTP 方法与状态参考。
- `assets/api-review-checklist.csv`：API 评审清单。
- `assets/openapi.template.yaml`：OpenAPI 起始模板。
- `assets/graphql-schema.template.graphql`：GraphQL Schema 起始模板。
- `assets/api-change-proposal.template.md`：接口变更提案模板。
- `scripts/validate_api_contract_catalog.py`：目录与模板校验脚本。
- `examples/README.md` 与 `examples/contract-brief.example.md`：虚构项目契约产出样例。

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
uv run scripts/validate_api_contract_catalog.py assets/api-rule-catalog.csv --compatibility assets/compatibility-change-matrix.csv --status-map assets/http-operation-status-map.csv --review assets/api-review-checklist.csv --styles assets/api-style-selection.csv --openapi assets/openapi.template.yaml --graphql assets/graphql-schema.template.graphql --change-proposal assets/api-change-proposal.template.md
uv run python -m unittest discover -s scripts/tests   # 跑测试
```

