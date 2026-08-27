# Observability

> Parent: [`engineering-reliability`](../SKILL.md). Spec for OpenTelemetry-based observability — metrics / traces / logs correlation, SLI / SLO, Golden Signals, sampling, dashboards, alerts, telemetry governance, cost control.

## What this is

Spec for making a system answer without manual logging or code changes: is it normal, who is affected, which layer failed, which version / config / dependency is involved. The goal: engineers can debug and operate the system from telemetry alone, and the system can detect and warn on real user impact.

## How to invoke

```text
使用 $engineering-reliability/observability 帮我 <做什么>
```

| You say | Agent does |
| --- | --- |
| 帮新服务做可观测性设计 | run workflow in `otel-model.md`: Resource identity → signals → SLI/SLO → sampling → dashboard → alert |
| 定义 SLI / SLO | load `metrics-sli-slo.md`; define numerator, denominator, window, scope, exclusion |
| 设计 metric | load `otel-model.md`; low-cardinality labels only; high-cardinality data in traces/logs |
| 加 tracing | load `tracing-alerting.md`; instrument inbound, outbound, DB, queue, key internal ops |
| 写告警 | load `tracing-alerting.md`; alert on user-impacting symptom, not internal failure rate |
| 控制 telemetry 成本 | load `telemetry-governance.md`; cap series / sample traces / log volume |
| 治理 telemetry 漂移 | load `telemetry-signal-catalog.csv`; remove unused metrics; cap cardinality |
| 评审可观测性方案 | load `observability-review-checklist.csv` + `sli-catalog.csv` + `alert-policy.csv` |
| 跟韧性 / 日志衔接 | see [`../resilience/README.md`](../resilience/README.md) (resilience metrics), [`../logging/README.md`](../logging/README.md) (log format) |

## Core principles

- Start from user journeys to define SLI / SLO, then design signals. "High availability" is not a valid requirement; "99.9% successful order creation in 28 days" is.
- Resource identity must be consistent. `service.name` is required; `service.namespace` / `service.version` / `deployment.environment.name` / `service.instance.id` as needed. Untyped data defeats correlation.
- Three core signals: metrics (trend / SLO / alert), traces (per-request causality), logs (event diagnosis). Profiles optional, used for hotspot diagnosis. All three carry the same `trace_id` and `service.*` Resource.
- Metric labels must be low cardinality. `order_id`, `user_id`, `merchant_ref` belong in trace / log attributes, not in metric labels. Cap series per service.
- Trace span names use templates, not actual IDs. `GET /v1/orders/{orderId}`, never `GET /v1/orders/123`. Otherwise high cardinality breaks aggregation.
- Sampling: errors 100% retained, slow traces high retention, normal traces 1–10%. Sampling must be a real plan, not default.
- Alert on user impact, not internal failure rate. "5xx > 1% for 5 minutes" is not enough; "order creation SLO burn rate over 14.4×" is.
- Dashboard has owner and use. Delete or auto-generate dashboards nobody maintains.
- Telemetry is a budgeted resource. Cap series, trace volume, log volume. Telemetry failure does not block the business.
- Card limits are enforced in code, not by convention. CI rejects new high-cardinality labels.
- Trace sampling is consistent across services. A trace started at the edge stays correlated even if some services downsample.

## Quick reference

### Golden Signals (user services)

| Signal | What | Example |
| --- | --- | --- |
| latency | request duration | P50 / P95 / P99 |
| traffic | request volume | requests / s, QPS |
| errors | failure rate | 5xx / 4xx, timeout, exception |
| saturation | resource usage | CPU, queue, connection pool |

For infrastructure: USE (utilization / saturation / errors).

### SLI definition

| Aspect | Define |
| --- | --- |
| numerator | the success measure |
| denominator | the total legitimate attempts |
| window | 28 days for SLO, 5 min / 1 h for burn |
| scope | user journey, region, tenant, or service |
| exclusion | synthetic probes, cancelled, internal health |
| source | metric, log, or trace |

### Alert policy

| Severity | Trigger | Response |
| --- | --- | --- |
| PAGE | user-impacting SLO burn (multi-window) | on-call investigates within SLA |
| TICKET | backlog / capacity approaching limit | scheduled review |
| INFO | new deployment, SLO reset | log only |

Do not alert on single transient spikes. Use burn-rate based alerting.

### Telemetry budget

| Resource | Soft cap | Hard cap |
| --- | --- | --- |
| metric series / service | 3 000 | 5 000 |
| trace sample rate | 1–10% normal, 100% error | bounded collector queue |
| log volume / day / instance | 1 GB | 2 GB |
| log line size | 4 KB | 16 KB (truncate beyond) |
| collector queue | bounded | drop with counter + self-metric |

Telemetry failure does not block business. Always have a bounded queue, drop counter, and self-metric on the collector.

### Cardinality discipline

| Field type | Example | Use in metric? | Where it goes |
| --- | --- | --- | --- |
| Status / route / dependency | `2xx` / `POST /v1/orders` | yes | metric label |
| Region / environment | `prod` / `us-east-1` | yes | metric label |
| Order / user / merchant ID | `ord_123` | no | trace / log attribute |
| Tenant ID (small) | tenant A–F | yes (≤ 100) | metric label |
| Tenant ID (large) | thousands | no | trace / log attribute |

## Reference index

| File | When to load |
| --- | --- |
| [`../references/observability/otel-model.md`](../references/observability/otel-model.md) | Resource identity, signals, semantic conventions, sampling |
| [`../references/observability/metrics-sli-slo.md`](../references/observability/metrics-sli-slo.md) | Golden Signals, USE, SLI definition, SLO and error budget |
| [`../references/observability/tracing-alerting.md`](../references/observability/tracing-alerting.md) | Span strategy, sampling, alert design, dashboard organization |
| [`../references/observability/telemetry-governance.md`](../references/observability/telemetry-governance.md) | Cost control, cardinality caps, schema evolution |
| [`../references/observability/standards-sources.md`](../references/observability/standards-sources.md) | OpenTelemetry, Google SRE, Prometheus |

## Asset index

| File | Purpose |
| --- | --- |
| [`../assets/observability/sli-catalog.csv`](../assets/observability/sli-catalog.csv) | SLI catalog with numerator / denominator / window |
| [`../assets/observability/telemetry-signal-catalog.csv`](../assets/observability/telemetry-signal-catalog.csv) | Signal catalog with cardinality policy |
| [`../assets/observability/alert-policy.csv`](../assets/observability/alert-policy.csv) | Alert policy catalog |
| [`../assets/observability/observability-review-checklist.csv`](../assets/observability/observability-review-checklist.csv) | Observability review checks |

## Validation

```bash
uv run scripts/observability/validate_observability.py --assets ../assets/observability/

uv run python -m unittest discover -s scripts/observability/tests
```

## Worked example

[`../examples/observability/observability-design.example.md`](../examples/observability/observability-design.example.md) — order service observability design: SLI/SLO for "order creation availability / latency", metric design (low-cardinality labels only), trace span coverage (inbound / outbound / DB / queue), burn-rate based alerting, dashboard organization, telemetry budget, and a fault-injection validation step ("payment slow") to confirm signals explain real problems.
