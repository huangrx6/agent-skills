# NovaPay 异常处理四件套示范

> 场景：订单取消接口。演示错误码注册表 → 异常映射 → 全局处理器 → 失败测试。

## 1. 失败分类（先分类再定码）

- 订单不存在 → BUSINESS（业务失败）
- 订单已结算不可取消 → CONFLICT（状态冲突）
- 依赖库存服务超时 → DEPENDENCY（依赖失败）

## 2. 错误码注册表（摘录）

| code | httpStatus | category | retryable | owner |
|---|---|---|---|---|
| ORDER_NOT_FOUND | 404 | BUSINESS | false | 交易组 |
| ORDER_STATE_CONFLICT | 409 | CONFLICT | false | 交易组 |
| INVENTORY_UNAVAILABLE | 503 | DEPENDENCY | true | 交易组 |
| INTERNAL_ERROR | 500 | SYSTEM | false | 平台团队 |

## 3. 异常映射表（摘录）

| internalException | publicCode | httpStatus | retryable | notes |
|---|---|---|---|---|
| OrderNotFoundException | ORDER_NOT_FOUND | 404 | false | 资源不存在 |
| OrderStateConflictException | ORDER_STATE_CONFLICT | 409 | false | 按领域细化 |
| InventoryTimeoutException | INVENTORY_UNAVAILABLE | 503 | true | 仅幂等重试 |

## 4. 全局异常处理器（伪代码）

```java
@RestControllerAdvice
class GlobalExceptionHandler {
    // 1. 识别已登记预期失败 → 2. 映射错误码/状态 → 3. 透传 traceId
    // 4. 统一安全响应 → 5. 清理内部细节 → 6. 未知兜底 INTERNAL_ERROR
    @ExceptionHandler(BusinessConflictException.class)
    ApiResponse<Void> handleConflict(BusinessConflictException e, HttpServletRequest req) {
        // 返回 {status:409, code:"ORDER_STATE_CONFLICT", traceId:..., detail:安全消息}
    }

    @ExceptionHandler(Throwable.class)
    ApiResponse<Void> handleUnknown(Throwable t, ...) {
        log.error("uncaught", t);          // 内部完整记录（exception.type/message/stacktrace）
        return ApiResponse.error(INTERNAL_ERROR);  // 对外最少信息，不泄露堆栈
    }
}
```

## 5. 失败路径测试（负向）

```java
@Test
void cancelSettledOrderReturnsStateConflict() {
    // 已结算订单取消 → 409 + ORDER_STATE_CONFLICT，不返回 200
}

@Test
void dependencyTimeoutRetriesWithBound() {
    // 库存超时 → 503 + INVENTORY_UNAVAILABLE，重试有上限且幂等
}

@Test
void unknownExceptionReturnsSafeInternalError() {
    // 未预期异常 → 500 + INTERNAL_ERROR，响应不含堆栈/SQL/路径
}

@Test
void traceIdPropagatesToErrorResponse() {
    // 错误响应携带 traceId，与日志可关联
}
```

## 6. 幂等衔接

- 取消请求使用幂等键（契约设计归 api-contracts）；
- 重试失败路径：查询状态或用同一幂等键，不盲目重提交。
