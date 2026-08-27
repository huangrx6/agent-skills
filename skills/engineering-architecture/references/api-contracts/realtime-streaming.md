# WebSocket、SSE 与 HTTP Streaming

## 目录

- [选择方式](#选择方式)
- [共同规则](#共同规则)
- [WebSocket](#websocket)
- [SSE](#sse)
- [HTTP Streaming](#http-streaming)
- [重连与恢复](#重连与恢复)
- [背压与限额](#背压与限额)
- [安全与测试](#安全与测试)

## 选择方式

- 服务器单向推送浏览器：优先 SSE。
- 双向低延迟会话：WebSocket。
- 单个请求持续输出结果：HTTP Streaming。
- 需要可靠离线消费、多个消费者和重放：事件总线，而不是 WebSocket。
- 只需偶发异步结果：轮询或 Webhook 可能更简单。

## 共同规则

所有长连接或流式接口必须定义：连接建立、认证、会话/流 ID、消息类型和 Schema 版本、消息 ID、关联 ID、顺序、重复、丢失、重连、恢复位置、心跳、空闲超时、最大连接时长、消息大小、速率、过载行为和关闭原因。

禁止只定义“连接地址 + JSON 示例”就认为实时契约完整。

## WebSocket

WebSocket 提供双向通道，但应用协议必须自行定义。

必须规定：`wss://`、握手认证和 Origin、Subprotocol、text/binary、消息 envelope、request/response/event 区分、心跳、业务 ack、close code、重连、发布 draining、多实例路由、每连接队列和慢消费者行为。

推荐 envelope：

```json
{"type":"order.updated","id":"evt_123","correlationId":"req_456","version":1,"sentAt":"2026-08-07T04:00:00Z","payload":{}}
```

WebSocket 帧边界不等于领域事务边界。

## SSE

SSE 使用 `text/event-stream`，适合服务器到客户端推送。

定义：`event`、`data` Schema、`id`、`retry`、`Last-Event-ID` 恢复、心跳注释、连接过期、代理缓冲、每用户最大连接数和事件保留窗口。

- data 若为 JSON，仍需 Schema；
- `id` 用于恢复，不与业务资源 ID 混用；
- 重连可能收到重复事件，消费必须幂等；
- 无法恢复时返回明确重置策略；
- 不用 SSE 做客户端到服务器实时命令通道。

## HTTP Streaming

适用于 AI 输出、逐批结果、进度或诊断流。可使用 NDJSON、JSON Text Sequences、multipart 或其他明确 framing。

必须定义媒体类型、每条消息边界、完成标记、中途错误、客户端取消、总时长、空闲超时、代理缓冲、最大输出和续传语义。

不要把无限流伪装成普通 JSON 数组。

## 重连与恢复

重连使用有上限的指数退避和抖动。明确恢复语义：至多一次、至少一次、从序号继续、从时间继续，或无法恢复只能重新获取快照。

如果恢复依赖事件保留，必须定义保留窗口和游标失效。

## 背压与限额

限制总连接、单身份连接、订阅数、消息速率、消息大小、发送队列、单连接内存和最大积压时间。

慢消费者策略必须明确：丢弃低优先级消息、合并状态、发送重置、主动断开或重新同步。禁止无限内存缓冲。

## 安全与测试

- 浏览器 WebSocket 校验 Origin；
- 建连和订阅都授权；
- 身份过期需重新验证或断开；
- 每个事件只包含订阅者有权看到的数据；
- 防止大量连接、订阅和复杂过滤耗尽资源。

测试握手失败、token 过期、重连、重复、乱序、恢复游标失效、服务器重启、慢消费者、消息超限、大量连接、客户端取消和版本不兼容。
