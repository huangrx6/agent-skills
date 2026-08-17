# 错误码与统一 API 错误响应

## 错误码规则

每个对外错误码必须：

- 在声明作用域内唯一；
- 发布后语义稳定；
- 与本地化消息相互独立；
- 不包含用户 ID、订单 ID、时间戳或实现名称；
- 记录默认状态码、可重试性、责任方和生命周期；
- 废弃后保留，不得重新分配。

优先使用大写蛇形命名，例如：

```text
INVALID_REQUEST
INVALID_ARGUMENT
UNAUTHENTICATED
PERMISSION_DENIED
RESOURCE_NOT_FOUND
ORDER_STATE_CONFLICT
RATE_LIMITED
DEPENDENCY_UNAVAILABLE
DEPENDENCY_TIMEOUT
INTERNAL_ERROR
```

调用方需要采取不同动作时，不得使用 `BUSINESS_ERROR` 等过宽错误码。

## 集中注册表

错误码必须集中维护，不得散落在控制器和业务代码中。至少登记：

- `code`；
- `title`；
- `httpStatus`；
- `category`；
- `retryable`；
- `publicDetail`；
- `owner`；
- `introducedVersion`；
- `deprecatedVersion`。

## HTTP 状态语义

| 状态码 | 默认用途 |
|---:|---|
| 400 | 请求语法、编码或基础结构错误 |
| 401 | 缺少有效认证凭据 |
| 403 | 已识别调用方，但无权执行操作 |
| 404 | 资源不存在，或出于安全目的隐藏存在性 |
| 409 | 当前状态、重复请求或版本冲突 |
| 422 | 请求结构正确，但字段语义或处理指令不合法 |
| 429 | 超过请求频率限制 |
| 500 | 未识别的服务端程序缺陷 |
| 502 | 网关或代理收到无效上游响应 |
| 503 | 服务临时不可用或过载（依赖不可用） |
| 504 | 网关或代理等待上游超时（依赖超时） |

HTTP 状态码表达协议含义，`code` 表达具体失败原因。不得使用 HTTP 200 包装失败，也不得把服务端缺陷伪装成 4xx。

## RFC 9457 响应

优先使用 `Content-Type: application/problem+json`：

```json
{
  "type": "https://errors.example.com/order/state-conflict",
  "title": "订单状态冲突",
  "status": 409,
  "detail": "当前订单状态不允许取消",
  "instance": "/orders/123/cancel",
  "code": "ORDER_STATE_CONFLICT",
  "traceId": "01K1ABCDEF23456789"
}
```

`type`、`title`、`status`、`detail`、`instance` 是 RFC 9457 标准字段；`code`、`traceId` 是本规范扩展字段（用于调用方按稳定错误码分支、与日志/链路关联）。标准字段不得重定义语义，扩展字段必须在校验过的字段目录中登记。

要求：

- `status` 与实际 HTTP 状态一致；
- `title` 对同一问题类型保持稳定；
- `detail` 只包含调用方可安全获知的信息；
- 禁止直接使用原始异常消息；
- 调用方根据 `code` 分支，不解析自然语言。

## 参数校验错误

字段级错误可增加结构化 `errors` 数组，但不得暴露正则表达式、数据库列名、内部对象路径或原始敏感值。

## 兼容性

- 新增错误码不得改变既有错误码含义；
- 废弃错误码不得重新使用；
- 可兼容增加可选字段；
- 未经版本化迁移不得删除必需字段；
- 语义变化必须发布新错误码。

## 标准依据

- RFC 9110：HTTP Semantics
- RFC 9457：Problem Details for HTTP APIs
- RFC 6585：Additional HTTP Status Codes
