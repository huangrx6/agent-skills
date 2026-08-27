# 事件与 Webhook 契约

## 目录

- [事件语义](#事件语义)
- [事件 Envelope](#事件-envelope)
- [投递、顺序与重放](#投递顺序与重放)
- [Schema 演进](#schema-演进)
- [Webhook](#webhook)
- [AsyncAPI](#asyncapi)
- [测试与治理](#测试与治理)

## 事件语义

事件表示已经发生的事实，名称使用过去式，例如 `OrderCreated`、`PaymentAuthorized`。

每个事件必须明确稳定事件类型、事件 ID、发生时间、生产者、Schema 版本、业务键、correlation/causation 标识、数据分类、载荷 Schema、分区键、顺序保证、重复投递、幂等、保留和重放策略。

不要把命令和事件混为一谈。

## 事件 Envelope

建议统一最小 Envelope：

```json
{
  "id": "evt_123",
  "type": "order.created",
  "source": "order-service",
  "time": "2026-08-07T04:00:00Z",
  "specVersion": "1",
  "correlationId": "corr_456",
  "subject": "orders/ord_789",
  "data": {}
}
```

可采用 CloudEvents 或组织等效标准。事件 ID 用于去重和追踪，不与业务资源 ID 混用。

## 投递、顺序与重放

- 默认按“至少一次”设计消费者，不能假设消息只投递一次。
- 消费者必须具备幂等或去重能力。
- 顺序通常只在同一 partition/key 内有保证。
- 明确 partition key；需要单实体顺序时使用稳定实体键。
- 消费者必须处理延迟、乱序和重复。
- 定义保留时间、重放起点、历史 Schema 解析和重放副作用策略。
- 需要版本冲突控制时携带聚合版本或序号。
- 高风险消费者应提供 dry-run、去重表或重放保护。

## Schema 演进

- 新增可选字段通常兼容。
- 删除、重命名或改变字段语义通常是破坏性变更。
- 枚举新增必须有未知值处理。
- 历史事件长期存在时，旧 Schema 必须仍可解析或可迁移。
- 破坏性变化使用新事件版本或新事件类型。
- 事件类型不得静默复用为不同业务含义。
- 生产者和消费者不会同时升级，必须支持滚动兼容。

## Webhook

Webhook 是跨系统异步 HTTP 投递，必须定义事件类型和版本、endpoint 所有权验证、TLS、签名算法与密钥轮换、时间戳与重放保护、delivery ID、超时、重试、退避、最大次数、2xx/4xx/5xx 语义、去重、顺序、死信/人工重放、保留期限和主动查询最终状态的替代接口。

Webhook 目标必须防 SSRF：禁止回环、未授权内网和云元数据地址。消费者不得依赖严格顺序或只投递一次。

## AsyncAPI

事件驱动接口应使用 AsyncAPI 或组织等效机器契约描述 servers、channels、operations、messages、schemas、correlation ID、security、protocol bindings 和 examples，并运行验证、lint、兼容差异和示例测试。

## 测试与治理

至少测试重复、乱序、丢失与重放、新旧消费者兼容、死信、生产者重试、消费者崩溃、Webhook 签名与重放攻击、endpoint 超时和大积压恢复。

每个事件必须有 Owner、契约位置、主要生产者/消费者、生命周期状态、数据分类和保留策略。
