# NovaPay API 契约示范

## 1. 风格选择（先选协议）

| 场景 | 候选风格 | 选择 | 理由 |
| --- | --- | --- | --- |
| 商户查询订单列表 | REST / GraphQL | **REST** | 公开 API、缓存成熟、客户端简单 |
| 商户-收银系统实时通知 | Webhook | **Webhook** | 跨组织异步、单消费者、签名验证 |
| 银行对账批量上报 | gRPC | **gRPC** | 内部服务、强类型、流式大文件 |
| 管理员后台聚合查询 | GraphQL | **GraphQL** | 多前端、字段需求差异大 |
| 交易状态实时推送 | WebSocket | **WebSocket** | 双向、需持续连接 |
| 审计事件总线 | Event/Pub-Sub | **Pub-Sub** | 多消费者、需重放 |

## 2. 资源建模

```
GET    /v1/orders                       列表（分页）
GET    /v1/orders/{orderId}             单笔
POST   /v1/orders                       创建
POST   /v1/orders/{orderId}/cancellations 取消（命令资源）
GET    /v1/merchants/{merchantId}/orders  子集合
```

- URI 用复数名词（orders/merchants），子集合用 `/{parentId}/{children}`。
- 不暴露表名或 ORM 类型。
- 业务动作（取消）用命令资源 `POST .../cancellations`，不用 `POST .../cancel`。

## 3. HTTP 状态码

| 场景 | 状态 |
| --- | --- |
| 成功读取 | 200 |
| 创建成功 | 201 + Location |
| 异步受理 | 202 + Location（操作资源） |
| 参数不合法 | 400 |
| 未认证 | 401 |
| 无权限 | 403 |
| 不存在 | 404 |
| 状态冲突 | 409 |
| 限流 | 429 + Retry-After |
| 依赖不可用 | 503 + Retry-After |

不用 HTTP 200 包装失败；状态码与业务 code 分离。

## 4. 业务错误响应（RFC 9457 + 扩展）

```json
{
  "type": "https://errors.novapay.com/order/state-conflict",
  "title": "订单状态冲突",
  "status": 409,
  "detail": "当前订单状态不允许取消",
  "instance": "/v1/orders/ord_123/cancellations",
  "code": "ORDER_STATE_CONFLICT",
  "traceId": "01K1ABCDEF23456789"
}
```

`type/title/status/detail/instance` 来自 RFC 9457；`code/traceId` 是组织扩展（用于按稳定错误码分支和日志关联）。

## 5. 版本兼容（变更分级）

| 变更 | 兼容性 | 处理 |
| --- | --- | --- |
| 新增可选请求/响应字段 | ✅ COMPATIBLE | 旧客户端忽略 |
| 新增错误码 | ✅ CONDITIONAL | 客户端有 UNKNOWN 分支 |
| 缩短字段长度 | ❌ BREAKING | 发新版本 + 双轨期 |
| 删除端点 | ❌ BREAKING | Sunset Header + 通知 |
| 收紧必填 | ❌ BREAKING | 新版本 + 兼容填充 |

## 6. 校验脚本输出风格（提醒）

```text
src/v1/orders/{orderId}.yaml -> CONTRACTS
  原因: API contract changed
  动作: Run machine contract validation and compatibility check
```
