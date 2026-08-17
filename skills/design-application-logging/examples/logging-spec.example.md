# NovaPay 应用日志五件套示范

## 1. 事件目录（摘录）

| eventName | defaultLevel | responsibilityBoundary | requiredFields |
|---|---|---|---|
| service.started | INFO | process-boundary | service.name\|service.version |
| request.failed | ERROR | request-boundary | operation\|error.code\|trace_id\|duration_ms |
| order.cancelled | INFO | request-boundary | operation\|order.id\|actor.id |
| dependency.retry_exhausted | ERROR | request-boundary | operation\|dependency.name\|retry.count |
| authentication.failed | WARN | request-boundary | operation\|failure.reason |
| audit.permission_changed | INFO | audit-boundary | audit.action\|actor.id\|resource.id |

## 2. 字段目录（摘录）

| fieldName | required | type | classification |
|---|---|---|---|
| timestamp | true | TIMESTAMP | PUBLIC |
| event.name | true | STRING | PUBLIC |
| trace_id | true | STRING | PUBLIC |
| error.code | false | STRING | INTERNAL（复用错误码注册表） |
| error.type | false | STRING | INTERNAL（validation/dependency/timeout） |
| duration_ms | false | INT | PUBLIC |

## 3. 存储策略（摘录）

| logStream | outputTarget | format | rotationOwner | retentionDays |
|---|---|---|---|---|
| application | STDOUT | JSON_LINES | PLATFORM | 30 |
| application-file | FILE | JSON_LINES | OS | 30（maxFiles=31, maxLocalDiskMB=4096） |

## 4. 敏感字段策略（摘录）

| fieldPattern | classification | action |
|---|---|---|
| password | SECRET | DROP |
| *token* | SECRET | DROP |
| card_number | SENSITIVE | MASK |

## 5. 测试计划（3 条最小断言 + 扩展）

```text
1. JSON 可解析：每条事件是合法单行 JSON
2. 必填字段齐全：timestamp/event.name/trace_id 等
3. 敏感字段不出现：password/token 不出现在输出
扩展：滚动/压缩/清理行为、审计降级告警、双流字段一致、动态调级回退
```

## 6. 落地实现要点

- 入口注入 trace_id → 上下文 → 请求结束清理；
- 统一业务事件记录（注解/拦截点，不逐函数手写日志）；
- 统一错误出口（全局异常处理器输出最终失败日志，中间层不重复打印）；
- 双流：文本流 `[auth] result=SUCCESS principal=alice`，JSON 流同字段；
- 异步有界队列 + 满时按优先级丢弃（先丢 DEBUG，不丢 ERROR，审计独立）。
