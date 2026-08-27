# ![resilience](../assets/icons/resilience-light.svg#gh-light-mode-only) ![resilience](../assets/icons/resilience-dark.svg#gh-dark-mode-only) Resilience

> Parent: [`engineering-reliability`](../SKILL.md). Spec for timeout budget, retry, circuit breaker, bulkhead, rate limit, load shedding, backpressure, queue, degradation, health checks, and fault injection.

## What this is

Spec for keeping a service predictable when dependencies slow down, partial failures occur, traffic spikes, or resources saturate. The goal: a local problem must not amplify through retries and queues into a cascade, and the core traffic must get a predictable service.

## How to invoke

```text
使用 $engineering-reliability/resilience 帮我 <做什么>
```

| You say | Agent does |
| --- | --- |
| 设计超时预算 | load `timeout-retry.md`; set entry Deadline; distribute to downstream with remaining budget |
| 设计重试策略 | load `timeout-retry.md` + `dependency-resilience-policy.csv`; define max count, backoff, jitter, idempotency check |
| 加熔断器 | load `overload-isolation.md`; choose policy (count / rate / slow-call); pair with health check |
| 加限流 | load `overload-isolation.md`; define rate + burst + key + scope + 429 + Retry-After |
| 做舱壁隔离 | load `overload-isolation.md`; separate thread / connection / queue pools per dependency |
| 队列与背压 | load `async-resilience.md`; declare capacity, shed policy, DLQ, replay |
| 健康检查 | load `health-readiness.md`; separate liveness (process) and readiness (traffic-ready) |
| 写故障注入实验 | load `resilience-testing.md`; define hypothesis, blast radius, stop condition, success metric |
| 评审韧性策略 | load `resilience-control-catalog.csv` + `resilience-review-checklist.csv` |
| 错误码 / 异常处理怎么配合 | see [`../exception-handling/README.md`](../exception-handling/README.md) — retryable / category / traceId |

## Core principles

- The entry defines the total Deadline; each downstream gets a slice of the remaining budget. Downstream timeout must not exceed the remaining caller time.
- Retry responsibility belongs to the dependent, but retries are bounded. Retry only on idempotent or naturally-safe operations. Never retry a write without an idempotency key.
- Exponential backoff with jitter is the default. Set a max retry count and a max retry budget. When the budget is exhausted, fail fast.
- Circuit breaker opens on confirmed failure rate, not on a single transient error. Pair breaker with a health check so the close is data-driven, not time-driven.
- Bulkhead isolation separates per-dependency pools. One slow dependency must not consume the resources of another.
- Rate limit per user / tenant / API, with sustained rate and burst. Reject with 429 + `Retry-After`. Fairness across tenants is required.
- Load shedding before saturation. Rejecting is cheaper than continuing to degrade.
- Queues and async work are not infinite buffers. Define capacity, oldest-age limit, drop policy, DLQ, replay procedure.
- Health checks are two distinct things: liveness (process is alive) and readiness (ready to take traffic). Do not collapse them.
- Resilience strategy must be verified by fault injection. A protection mechanism not exercised in test is a wish, not a control.
- Numbers (timeouts, retry counts, limits) are determined by load and failure experiments, not by AWS or Google defaults. Defaults are starting points only.
- Retry / breaker / rate limit are runtime; the failure semantics (codes, status, retryable) come from [`../exception-handling/`](../exception-handling/). Resilience strategy must not contradict the public failure contract.

## Quick reference

### Timeout budget split

| Stage | Typical budget | Notes |
| --- | --- | --- |
| connect | tens of ms | exclude DNS / pool wait |
| TLS handshake | tens of ms | reuse sessions when possible |
| pool acquisition | fail fast | do not let callers block on a saturated pool |
| request / write | a few ms | measure, do not assume |
| response / read | the largest slice | dominates in normal operation |
| in-process handling | small slice | serialization, business logic, persistence |
| buffer | 5–15% | jitter and asymmetric tail |

Allocate from entry to leaf; propagate remaining deadline through metadata / header. Never let a child set its own full timeout without seeing the caller's remaining budget.

### Retry decision

| Operation | Retry? | Why |
| --- | --- | --- |
| Idempotent GET / HEAD | Yes | naturally safe |
| Idempotent POST with idempotency key | Yes | deduped on server side |
| POST without idempotency key | No (or only on 5xx with backoff) | risk of double execution |
| Non-idempotent state change | No | never silently retry |
| Dependency timeout / 503 | Yes if `retryable=true` in error code registry | bounded by retry budget |
| Dependency 4xx | No | client error is not transient |

### Circuit breaker

| Policy | Open trigger | Half-open probe |
| --- | --- | --- |
| Count | N failures in window | one call after cooldown |
| Rate | failure rate ≥ threshold | small batch after cooldown |
| Slow-call | slow-call rate ≥ threshold | one call after cooldown |

Pair every breaker with a fallback: cached data, degraded response, fast-fail with `DEPENDENCY_UNAVAILABLE` code.

### Rate limit

| Aspect | Define |
| --- | --- |
| Rate | requests per second (sustained) |
| Burst | token-bucket burst size |
| Key | user / tenant / IP / API |
| Scope | per-instance or global |
| Reject | 429 + `Retry-After` |
| Recovery | quota reset, fall-back to lower priority |

### Load shedding

Define:

- Trigger signals (CPU, memory, queue age, dependency latency, pool wait).
- Priority order (reject lowest-value work first).
- Reject shape (429 for over-limit; 503 for dependency-failure fast-fail).
- Self-protection (drop DEBUG logs, drop low-priority metrics).

### Health check

| Type | Question | When to fail |
| --- | --- | --- |
| Liveness | Is the process alive? | Process hung, deadlock, OOM imminent |
| Readiness | Should this instance take traffic? | Dependency unavailable, cache cold, warming up, draining |

Do not include external dependencies in liveness. Liveness failure kills the process; readiness failure just removes it from the load balancer.

## Reference index

| File | When to load |
| --- | --- |
| [`../references/resilience/timeout-retry.md`](../references/resilience/timeout-retry.md) | Deadline, timeouts, retry policy, idempotency contract |
| [`../references/resilience/overload-isolation.md`](../references/resilience/overload-isolation.md) | Rate limit, load shedding, circuit breaker, bulkhead |
| [`../references/resilience/async-resilience.md`](../references/resilience/async-resilience.md) | Queue, DLQ, replay, idempotent consumer, backpressure |
| [`../references/resilience/health-readiness.md`](../references/resilience/health-readiness.md) | Liveness / readiness / startup / shutdown |
| [`../references/resilience/observability-runbooks.md`](../references/resilience/observability-runbooks.md) | Metrics, alerts, runbooks for resilience events |
| [`../references/resilience/resilience-testing.md`](../references/resilience/resilience-testing.md) | Fault injection, chaos, blast radius, stop condition |
| [`../references/resilience/standards-sources.md`](../references/resilience/standards-sources.md) | AWS Builders' Library, Google SRE, Azure Patterns, Netflix |

## Asset index

| File | Purpose |
| --- | --- |
| [`../assets/resilience/dependency-resilience-policy.csv`](../assets/resilience/dependency-resilience-policy.csv) | Per-dependency resilience policy |
| [`../assets/resilience/resilience-control-catalog.csv`](../assets/resilience/resilience-control-catalog.csv) | Resilience control catalog |
| [`../assets/resilience/resilience-review-checklist.csv`](../assets/resilience/resilience-review-checklist.csv) | Resilience review checks |
| [`../assets/resilience/failure-injection-plan.template.md`](../assets/resilience/failure-injection-plan.template.md) | Failure injection plan template |

## Validation

```bash
uv run scripts/resilience/validate_resilience.py --assets ../assets/resilience/

uv run python -m unittest discover -s scripts/resilience/tests
```

## Worked example

[`../examples/resilience/resilience-design.example.md`](../examples/resilience/resilience-design.example.md) — order service resilience design: timeout budget split across gateway → service → DB / payment, retry policy per dependency (idempotency key required for non-idempotent writes), circuit breaker with cached fallback, rate limit per tenant, queue with oldest-age drop and DLQ, fault injection for "payment slow" with success criteria.
