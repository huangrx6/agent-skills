# Performance & Capacity

> Parent: [`engineering-reliability`](../SKILL.md). Spec for performance and capacity — target, workload model, throughput / concurrency / tail latency, budget, benchmark, load / stress / spike / soak testing, bottleneck analysis, profiling, capacity model, autoscaling, regression and cost efficiency.

## What this is

Spec for using repeatable experiments to answer: how much work can the system handle, at what P95 / P99, what is the first bottleneck, how much headroom on failure, and when capacity will saturate next. Covers targets, workload model, benchmark, load test, profile, capacity plan, autoscaling, regression detection.

## How to invoke

```text
使用 $engineering-reliability/performance-capacity 帮我 <做什么>
```

| You say | Agent does |
| --- | --- |
| 做性能目标 | load `performance-model.md`; define P50 / P95 / P99 per user journey; per-tenant quota |
| 建负载模型 | load `performance-model.md`; identify work unit; write normalized workload |
| 写性能预算 | copy `performance-budget.csv` schema; latency / throughput / error / resource per endpoint |
| 跑负载测试 | load `load-testing.md`; warm-up → ramp-up → steady-state → ramp-down; collect percentiles |
| 找瓶颈 | load `bottleneck-profiling.md`; profile, trace, query plan; one change at a time |
| 容量规划 | load `capacity-planning.md`; build capacity-model.csv; headroom rule; forecast |
| 写容量评审 | load `capacity-model.csv` + `performance-budget.csv`; gap analysis |
| 准备大促 / 峰值 | combine load + spike + capacity; pre-warm; shed plan |
| 跟踪性能回归 | load `performance-budget.csv`; CI gates on P95 / error budget burn |
| 评估重计算服务 (AI / OCR / VLM) | load `ai-document-workloads.md`; throughput in tokens / pages / images |
| 跟可观测性 / 韧性衔接 | see [`../observability/README.md`](../observability/README.md) (latency / error / saturation metrics), [`../resilience/README.md`](../resilience/README.md) (load shedding) |

## Core principles

- Mean latency does not replace tail latency. P99 reflects the worst user experience and is the first signal of queueing and nonlinear degradation.
- Throughput unit must match the system. `requests/s`, `documents/min`, `pages/s`, `messages/s`, `tokens/s`, `MB/s`, `images/s`. Never mix requests of different cost in one QPS.
- Workload model first, then test. Real production mixes read / write, long / short, hot key / cold, large / small. A model that uses only one shape is fiction.
- Establish a baseline before changing anything. Compare runs against the baseline; never "it feels faster" without numbers.
- One variable at a time. Change one of: code, config, data, environment, then re-measure. Multi-variable runs tell you nothing.
- Find the first saturation point. Stress testing means increasing load until something breaks, then identifying the bottleneck — not pushing the system to 10× for show.
- Profile, trace, query plan. Do not guess. CPU / memory / GC / IO / network / DB / queue: each layer has its own evidence.
- Headroom is required. Production capacity is `peak_observed × (1 + headroom)`. Headroom is explicit in the capacity model, not implicit.
- Performance budget is a contract, enforced in CI. "We want P99 ≤ 800ms" without CI gate is a wish.
- Performance regresses silently. Add regression detection: any change that breaks budget fails CI.
- Numbers are project-specific. AWS / Google / Netflix defaults are starting points. Your workload, hardware, version, config, and telemetry are facts.
- AI / OCR / VLM workloads have their own model. They are throughput-bound on model inference, not on I/O. Use `ai-document-workloads.md` to model correctly.

## Quick reference

### Performance target

| Aspect | Define |
| --- | --- |
| User journey | e.g. order creation |
| Percentile | P50 / P95 / P99 |
| Budget | P99 ≤ 800 ms under 5× current peak |
| Per-tenant SLA | if multi-tenant |
| Error budget | 0.1% (99.9% SLO) |

### Normalized work unit

| Cost dimension | Examples |
| --- | --- |
| CPU | ms per request |
| I/O | pages, bytes, rows |
| Token / model | tokens, images, pages |
| Queue | messages |
| Storage | bytes, files |

A normalized unit lets you predict capacity at higher or lower scale without re-measuring every endpoint.

### Load test phases

| Phase | Purpose |
| --- | --- |
| warm-up | JIT, cache, pool warm |
| ramp-up | reach target load gradually |
| steady-state | measure percentile / error / resource at target |
| ramp-down | graceful recovery check |
| recovery | post-load state matches pre-load |

### Load test type

| Type | Purpose | Duration |
| --- | --- | --- |
| Load | validate SLO at target | steady-state minutes |
| Stress | find first saturation and failure mode | ramp to 3–5× target |
| Spike | test autoscaling / shedding / cold start | short bursts |
| Soak | detect memory leak / drift / periodic issue | hours |

### Capacity model

| Column | Example |
| --- | --- |
| service | order-service |
| work_unit | create_order |
| sustained_per_instance | 200 / s |
| peak_observed | 800 / s |
| headroom | 30% |
| max_capacity | 1 200 / s |
| bottleneck | DB connection pool at 60% |
| forecast_method | weekly growth + seasonal |

A service is at capacity when its bottleneck is at 70% under peak (configurable). Plan expansion at 60% to give lead time.

### Bottleneck identification

| Symptom | Where to look |
| --- | --- |
| P99 grows under load | queue, lock, GC, downstream |
| CPU saturated, low throughput | thread pool / event loop saturation |
| Memory grows | leak, unbounded cache, fragmentation |
| DB latency up | slow query, lock, connection pool, replicas lag |
| Network RTT up | DNS, pool exhaustion, MTU, TLS handshake |
| Queue backlog grows | consumer throughput, dependency outage, retry storm |

## Reference index

| File | When to load |
| --- | --- |
| [`../references/performance-capacity/performance-model.md`](../references/performance-capacity/performance-model.md) | Tail latency, throughput unit, normalized work unit, model steps |
| [`../references/performance-capacity/load-testing.md`](../references/performance-capacity/load-testing.md) | Load / Stress / Spike / Soak; phases; what to measure |
| [`../references/performance-capacity/bottleneck-profiling.md`](../references/performance-capacity/bottleneck-profiling.md) | CPU / memory / GC / IO / network / DB / queue; one variable at a time |
| [`../references/performance-capacity/capacity-planning.md`](../references/performance-capacity/capacity-planning.md) | Capacity model, headroom, forecast, lead time |
| [`../references/performance-capacity/ai-document-workloads.md`](../references/performance-capacity/ai-document-workloads.md) | AI / OCR / VLM throughput model (tokens / pages / images) |
| [`../references/performance-capacity/standards-sources.md`](../references/performance-capacity/standards-sources.md) | Google SRE, AWS Builders' Library, Netflix |

## Asset index

| File | Purpose |
| --- | --- |
| [`../assets/performance-capacity/performance-budget.csv`](../assets/performance-capacity/performance-budget.csv) | Per-endpoint performance budget |
| [`../assets/performance-capacity/load-test-scenarios.csv`](../assets/performance-capacity/load-test-scenarios.csv) | Load / stress / spike / soak scenarios |
| [`../assets/performance-capacity/capacity-model.csv`](../assets/performance-capacity/capacity-model.csv) | Capacity model template |
| [`../assets/performance-capacity/performance-experiment.template.md`](../assets/performance-capacity/performance-experiment.template.md) | Single-variable experiment plan |
| [`../assets/performance-capacity/performance-review-checklist.csv`](../assets/performance-capacity/performance-review-checklist.csv) | Performance review checks |

## Validation

```bash
uv run scripts/performance-capacity/validate_performance_capacity.py \
  --assets ../assets/performance-capacity/

uv run python -m unittest discover -s scripts/performance-capacity/tests
```

## Worked example

[`../examples/performance-capacity/performance-capacity.example.md`](../examples/performance-capacity/performance-capacity.example.md) — order service end-to-end: P99 ≤ 800ms under 5× peak, normalized work unit definition, Load / Stress / Spike / Soak plans, bottleneck from DB pool to cache, capacity model with 30% headroom, 6-month forecast based on weekly growth, regression detection in CI.
