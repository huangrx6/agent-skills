# GraphQL 契约规范

## 目录

- [适用边界](#适用边界)
- [Schema 设计](#schema-设计)
- [Query 与 Mutation](#query-与-mutation)
- [Subscription](#subscription)
- [分页](#分页)
- [Null 与错误](#null-与错误)
- [兼容性与弃用](#兼容性与弃用)
- [查询成本与安全](#查询成本与安全)
- [性能与 N+1](#性能与-n1)
- [GraphQL over HTTP](#graphql-over-http)
- [测试与治理](#测试与治理)

## 适用边界

GraphQL 适用于多前端字段组合差异大、跨领域聚合读取、客户端希望声明所需数据形状的场景。

不优先用于简单稳定 CRUD、大文件上传下载、无界批处理、强依赖 HTTP 缓存的合作方 API，或团队没有查询成本与 Resolver 性能治理能力的场景。

GraphQL 是查询语言和执行语义，不等于数据库查询透传，也不要求每个后端都使用 GraphQL。

## Schema 设计

- Schema 使用领域语言，不映射数据库表或内部微服务。
- Query、Mutation、Subscription 根字段表达调用方能力。
- Output Type 与 Input Type 分离。
- ID 使用 `ID`，调用方不得解析内部结构。
- Money、DateTime、URL 等使用明确 Scalar，并定义格式和语义。
- 不滥用 JSON/Any Scalar 逃避 Schema。
- 枚举用于稳定机器值，展示文本使用普通字段。
- Interface/Union 只在多态模型有真实调用价值时使用。
- 描述文本说明权限、单位、成本或特殊行为。

## Query 与 Mutation

Query 必须无业务副作用。列表字段必须分页或有严格上限；搜索、过滤、排序使用可治理 Input Type，不向客户端暴露任意数据库表达式。

Mutation：

- 名称表达业务意图，如 `cancelOrder`；
- 使用单一命名 Input，便于演进；
- 返回 Payload 类型；
- 明确幂等、重复提交和事务边界；
- 不建立万能 `execute` Mutation；
- 顶层 Mutation 字段按 GraphQL 执行语义串行，但下游事务和副作用仍需应用明确。

## Subscription

仅在客户端确实需要持续实时更新时使用。

必须定义事件语义、过滤参数、连接期间授权、传输协议、重连、重复、顺序、丢失、心跳、空闲超时、每连接订阅数、Schema 变化和恢复方式。

GraphQL 规范定义 Subscription 执行模型，但网络传输协议需另行约定。

## 分页

优先游标分页。可采用 Connection 风格，但不要描述成 GraphQL 核心规范强制要求。

要求：cursor 不透明；绑定过滤、排序和身份上下文；排序稳定；最大页大小有硬限制；昂贵 `totalCount` 可省略或单独授权。

## Null 与错误

- GraphQL 字段默认可空，Non-Null 会影响错误传播。
- 只在业务和数据源能长期保证时使用 Non-Null。
- 输入新增无默认值的 non-null 字段/参数通常是破坏性变更。
- 客户端必须允许 `data` 与 `errors` 同时存在。
- 不把部分成功强行转换成 REST 风格“整个响应失败”。
- 业务错误采用 Payload/Union 还是 GraphQL `errors`，组织必须统一。
- 程序缺陷不得在 error message 中暴露堆栈。

## 兼容性与弃用

通常破坏性：删除或重命名字段/参数/类型、改变字段类型、增加无默认值的必填参数、收紧输入、改变语义或授权。

通常可兼容但仍需验证：新增可选字段、类型、可选参数、Mutation。新增枚举值对生成客户端和穷举逻辑可能不兼容。

弃用使用 `@deprecated(reason: "...")`，reason 提供替代方案；监测字段使用量，完成迁移后再删除。

## 查询成本与安全

必须建立资源成本控制：

- 最大文档大小；
- 最大 AST 节点、字段深度、字段/alias 数量和 fragment 展开；
- 最大分页大小；
- Query Complexity/Cost 预算；
- 单请求总结果大小；
- 单身份并发和速率；
- Mutation 独立限额；
- Subscription 数和事件速率。

高价值场景可使用 persisted operations、allowlist 或 query hashing。

不要只按 HTTP 请求数限流，一个 GraphQL 请求可能非常昂贵。

生产是否关闭 introspection 不是通用安全要求；即使关闭，也不能替代授权和成本控制。

## 性能与 N+1

- Resolver 不得无界逐项调用数据库或下游服务。
- 对同一请求可合并读取使用 batching/caching。
- DataLoader 是常见实现方式，不是规范强制。
- 跨请求缓存考虑身份、租户、权限和新鲜度。
- 对大列表、嵌套关系和昂贵聚合设置上限。

## GraphQL over HTTP

GraphQL 核心规范不定义网络传输。通过 HTTP 时：

- Query 通常使用 POST；允许 GET 时必须无副作用并考虑 URL 长度和缓存；
- Mutation 不使用 GET；
- 优先支持 `application/graphql-response+json`；
- 区分 HTTP 请求/传输错误与 GraphQL 执行错误；
- 不假设出现 GraphQL `errors` 就必须返回 4xx/5xx；
- 批量 GraphQL 请求不是核心规范能力，启用时另行定义成本与结果语义。

## 测试与治理

至少测试 Schema 验证、旧 Query 对新 Schema、对象/字段授权、null 错误冒泡、alias/fragment 成本、枚举未知值、分页稳定性、Resolver batching、Mutation 幂等、Subscription 重连和生产 Schema 一致性。

发布前运行 Schema diff，对破坏性变化实施审批。
