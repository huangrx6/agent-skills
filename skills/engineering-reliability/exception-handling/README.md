# Exception Handling

> Parent: [`engineering-reliability`](../SKILL.md). Spec for failure classification, error code registry, exception mapping, unified API error response, global exception handler, async failure, and testing.

## What this is

Spec for how a backend system recognizes, classifies, maps, and reports failures — from the moment a failure happens to the moment the caller sees the response. Produces stable error semantics, clean error contract, and testable failure paths.

## How to invoke

```text
使用 $engineering-reliability/exception-handling 帮我 <做什么>
```

| You say | Agent does |
| --- | --- |
| 设计错误码体系 | load `failure-model.md`; create `error-code-registry.csv`; route by `category` |
| 评审我的错误处理 | load `error-code-registry.csv` + `exception-mapping.csv`; cross-check category and HTTP status |
| 写统一错误响应 | load `api-error-contract.md`; use RFC 9457 + extend with `code` and `traceId` |
| 写全局异常处理器 | load `failure-model.md` (global handler section); rule: identify → map → trace → safe response → log |
| 异步任务失败处理 | load `async-failures.md`; declare retry / DLQ / idempotency / outbox |
| 重试策略 | also see [`../resilience/README.md`](../resilience/README.md) for timeout and budget |
| 写失败路径测试 | load `testing-review.md`; require: 4xx vs 5xx, idempotency, traceId propagation, internal info leak |
| 错误码与 API 契约怎么对齐 | error code is in `error-code-registry.csv`; HTTP status and body are in `api-error-contract.md` |

## Core principles

- Classify failure first, code second. Categories: `INPUT` / `BUSINESS` / `AUTH` / `CONFLICT` / `RATE_LIMIT` / `DEPENDENCY` / `SYSTEM`. No category → no public code.
- One canonical error-code registry. No scattered codes in controllers or business code. Each entry has: `code`, `title`, `httpStatus`, `category`, `retryable`, `publicDetail`, `owner`, `introducedVersion`, `deprecatedVersion`.
- HTTP status expresses protocol semantics; `code` expresses specific business reason. Never wrap failure in 200. Never pretend server defects as 4xx.
- Use RFC 9457 `application/problem+json` for response shape. Extend with `code` and `traceId`. Standard fields are immutable; extensions are project-registered.
- Caller branches on `code`, not on natural language. Caller must not parse `detail` or `title`.
- Catch only when the current layer can recover, compensate, convert to a domain exception, or release a resource. Do not catch just to log and rethrow.
- Wrap with original cause. Do not discard context or stack. Do not wrap multiple times with the same semantic.
- One final-exception-handler per entry boundary. The handler maps to a code, sets a status, propagates `traceId`, sanitizes internal info, and logs. Do not handle business logic in the handler.
- Resource cleanup uses `finally` / `defer` / `with`. Cleanup that also fails must keep the original failure as the primary exception.
- Expected business failure is `WARN` + stable code, not `ERROR` with stack. Anomalies are `ERROR` with stack.
- Errors in async work (queue, schedule) require their own contract: retry policy, DLQ, idempotency, outbox, observability.

## Quick reference

### Failure category

| category | Meaning | Default response | Default level |
| --- | --- | --- | --- |
| `INPUT` | syntax / type / range / missing | accurate 4xx, no retry | WARN |
| `BUSINESS` | legal request violates domain rule | stable business code, no stack | WARN |
| `AUTH` | identity missing, expired, or no permission | accurate denial, no internal detail | WARN |
| `CONFLICT` | version / lock / duplicate / state | 409, retry only when safe | WARN |
| `RATE_LIMIT` | exceeded frequency / quota | 429 + `Retry-After` | WARN |
| `DEPENDENCY` | DB / cache / RPC / queue / storage failed | normalized, hide impl detail | ERROR |
| `SYSTEM` | invariant broken / uncaught | 500 / INTERNAL_ERROR, log full | ERROR |

Cancellation and timeout do not have an independent public category: upstream cancellation produces no public error; downstream timeout goes under `DEPENDENCY`.

### Stable error code requirements

- Unique within declared scope.
- Stable semantics after release.
- Independent of localized message.
- No user ID / order ID / timestamp / implementation name in the code.
- Recorded with default status, retryable, owner, lifecycle.
- After deprecation, never re-allocated.

Recommended names: `INVALID_REQUEST` / `INVALID_ARGUMENT` / `UNAUTHENTICATED` / `PERMISSION_DENIED` / `RESOURCE_NOT_FOUND` / `ORDER_STATE_CONFLICT` / `RATE_LIMITED` / `DEPENDENCY_UNAVAILABLE` / `DEPENDENCY_TIMEOUT` / `INTERNAL_ERROR`.

### Global exception handler checklist

1. Identify the registered expected failure.
2. Map to public `code` and HTTP status.
3. Propagate `traceId` / `spanId` / `correlationId`.
4. Generate unified, safe response.
5. Strip internal implementation detail and sensitive data.
6. Map unknown failure to `INTERNAL_ERROR`.
7. Preserve runtime-required terminate-process behavior.

### Async failure contract

Each async work item declares:

- Retry policy (count, backoff, max budget, jitter).
- Idempotency key and TTL.
- Dead-letter destination and replay procedure.
- Visibility (status, attempts, last error, lag).
- Owner and lifecycle.

## Reference index

| File | When to load |
| --- | --- |
| [`../references/exception-handling/failure-model.md`](../references/exception-handling/failure-model.md) | Failure categories, capture rules, wrapping, global handler |
| [`../references/exception-handling/api-error-contract.md`](../references/exception-handling/api-error-contract.md) | Error code rules, HTTP status semantics, RFC 9457 response |
| [`../references/exception-handling/async-failures.md`](../references/exception-handling/async-failures.md) | Queue, schedule, callback failure handling |
| [`../references/exception-handling/resilience.md`](../references/exception-handling/resilience.md) | Cross-cut with resilience — retry and idempotency contract |
| [`../references/exception-handling/testing-review.md`](../references/exception-handling/testing-review.md) | Required failure path tests |

## Asset index

| File | Purpose |
| --- | --- |
| [`../assets/exception-handling/error-code-registry.csv`](../assets/exception-handling/error-code-registry.csv) | Canonical error code registry |
| [`../assets/exception-handling/exception-mapping.csv`](../assets/exception-handling/exception-mapping.csv) | Internal exception → public code mapping |

## Validation

```bash
uv run scripts/exception-handling/validate_error_catalog.py \
  ../assets/exception-handling/error-code-registry.csv \
  --mapping ../assets/exception-handling/exception-mapping.csv

uv run python -m unittest discover -s scripts/exception-handling/tests
```

## Worked example

[`../examples/exception-handling/error-contract.example.md`](../examples/exception-handling/error-contract.example.md) — order cancellation scenario: failure classification, error code registry rows, exception mapping rows, global handler pseudocode, and four required failure-path tests (state conflict, dependency timeout retry bound, uncaught exception, traceId propagation).
