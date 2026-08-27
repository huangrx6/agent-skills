# JSON-RPC 2.0 契约

## 适用场景

适合工具协议、内部控制面和轻量命令式 RPC。资源型公开 Web API、强依赖 HTTP 缓存或需要成熟强类型代码生成时，通常优先 REST-style HTTP 或 gRPC。

## 请求与方法

```json
{"jsonrpc":"2.0","method":"orders.cancel","params":{"orderId":"ord_123"},"id":"req_456"}
```

- `jsonrpc` 必须为 `2.0`；
- method 大小写敏感；
- `rpc.` 前缀保留；
- params 优先命名对象；
- id 只用于请求响应关联，不与 Trace ID、幂等键混用；
- method 使用稳定命名空间。

## Notification

无 `id` 是 Notification，服务端不得返回响应。只用于调用方不需要确认的场景，不用于支付、状态关键变更或必须确认的动作。

## 响应与错误

成功使用 `result`，失败使用 `error`，二者不得同时存在。保留标准错误码范围；业务错误使用独立稳定命名空间。message 不作为机器判断依据，data 只返回安全结构化信息。

## HTTP 传输

JSON-RPC 与传输无关。通过 HTTP 时通常使用 POST，并固定“HTTP 状态与 JSON-RPC error”的映射策略；仍需定义认证、限额、Content-Type、最大载荷和超时。

## Batch

启用 batch 时定义最大请求数、总载荷、并行/串行、单项失败、Notification、限流和成本预算。响应按 id 关联，不能假设顺序与请求一致。Batch 默认不是事务。

## 兼容性与测试

重命名 method、改变 params/result 语义或新增必填参数通常破坏兼容。新增 method 和可选参数通常兼容。

至少测试 Parse error、Invalid Request、Method not found、Invalid params、Internal error、Notification 无响应、混合 batch、权限、业务错误映射和跨版本客户端。
