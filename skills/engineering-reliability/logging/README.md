# Logging

> Parent: [`engineering-reliability`](../SKILL.md). Spec for application logging — event selection, level, responsibility boundary, structured fields, JSON Lines, double-stream output, context injection, stdout/stderr, trace correlation, exception logging, sensitive data, rotation, retention, cost control.

## What this is

Spec for application logging that supports diagnosis, correlation, monitoring, and audit without duplicates, leaks, injection, format drift, unbounded growth, disk exhaustion, or cost runaway. Defines what to log, what not to log, level semantics, single-point-of-record responsibility, structured fields, format, and lifecycle.

## How to invoke

```text
使用 $engineering-reliability/logging 帮我 <做什么>
```

| You say | Agent does |
| --- | --- |
| 写应用日志规范 | load `logging-model.md` + `format-output.md`; produce event catalog, field catalog, format schema, sensitive policy, storage policy |
| 评审我的日志 | load `log-event-catalog.csv` + `log-event-fields.csv` + `log-format-schema.csv` + `sensitive-field-policy.csv` + `log-storage-policy.csv`; check 5 minimal assertions + governance |
| 设计日志事件 | copy event row format; define eventName, defaultLevel, responsibilityBoundary, requiredFields |
| 加日志上下文注入 | load `implementation-patterns.md`; HTTP/RPC/queue entry sets trace_id, request_id |
| 统一错误出口 | load `implementation-patterns.md`; one global handler, no repeated stack printing in middle layers |
| 异步有界队列 + 丢弃策略 | load `governance.md`; bounded queue, drop DEBUG first, never drop ERROR or audit |
| 动态调级 | load `governance.md`; runtime level config, audit, default rollback |
| 防止日志泄密 | load `sensitive-data.md`; classify field by sensitivity, drop or mask |
| 滚动 / 保留 / 清理 | load `rotation-retention.md`; define trigger, compression, retention, remote archive, disk protection |
| 跟 trace / 异常衔接 | see [`../observability/README.md`](../observability/README.md) (trace_id), [`../exception-handling/README.md`](../exception-handling/README.md) (exception fields) |

## Core principles

- Record only events that have at least one of: aid diagnosis, express key state change, support capacity / stability / business analysis, or are a security or compliance audit evidence. Do not record "in case it is useful later".
- One event is recorded at the boundary that owns the final outcome. Middle layers add context and propagate; they do not re-print. The global exception handler is the only place that prints the final failure log for a request.
- Default format: UTF-8 JSON Lines. One event per line. No ANSI color in production. Mixed text/JSON in the same stream is forbidden.
- Each log has the same Resource identity as the service: `service.name` is required; `service.version`, `deployment.environment.name`, `service.instance.id` as needed.
- Time is UTC, RFC 3339, ms precision. `timestamp` is event time; `observed_timestamp` is collector time when there is meaningful delay.
- Levels reflect operational impact, not whether code entered `catch`. `WARN` for expected business failure, `ERROR` for anomaly, never `ERROR` for a 4xx. No `FATAL` level — use `ERROR` + dedicated event + non-zero exit.
- Severity numbers follow OpenTelemetry: TRACE=1 / DEBUG=5 / INFO=9 / WARN=13 / ERROR=17. No ad-hoc mapping.
- Fields are typed. Same field name never switches between string / number / object. `duration_ms` not `duration`. Empty string and missing field have different semantics.
- Sensitive fields are dropped or masked at the logger boundary, not by collector rules. Patterns like `password`, `*token*`, `card_number` go in `sensitive-field-policy.csv`.
- Logging is asynchronous with a bounded queue. Drop on overflow with priority (DEBUG first, then INFO, never ERROR, never audit). Drop counter must be visible as a metric.
- One rotation owner per stream. App, OS, container runtime, and platform do not rotate the same file together.
- Logs are a budget. `schema.version` is recorded. Breaking change to field type or name requires a migration plan.
- Telemetry failure does not block business. Log platform outage degrades the app, never crashes it.

## Quick reference

### Five-piece logging spec

| Piece | What it answers | Where it lives |
| --- | --- | --- |
| Event catalog | which events exist, at which level, by which boundary | `log-event-catalog.csv` |
| Field catalog | which fields, types, classification, required | `log-event-fields.csv` |
| Format schema | log event shape and required fields | `log-format-schema.csv` |
| Storage policy | output target, rotation, retention, owner | `log-storage-policy.csv` |
| Sensitive policy | which patterns drop, mask, retain | `sensitive-field-policy.csv` |

### Level vs response

| Level | Use |
| --- | --- |
| DEBUG | diagnostic branch / dev detail; off or sampled in production |
| INFO | normal key state change / lifecycle / successful outcome |
| WARN | operation continues but recovered, retried, degraded, conflict, anomaly trend |
| ERROR | operation finally failed; needs investigation, alert, human attention |

### Common patterns

| Pattern | Where to log |
| --- | --- |
| Entry / exit | request boundary middleware |
| Business operation | declarative interceptor; one place, not per function |
| Dependency call | outbound client, with retry and outcome |
| Failure | global exception handler only |
| Expected business failure | WARN + stable code, no stack |
| Unexpected exception | ERROR + full stack (depth-limited) + traceId |

### Sensitive data

| Pattern | Classification | Action |
| --- | --- | --- |
| `password`, `*pass*`, `*secret*` | SECRET | DROP |
| `*token*`, `*api_key*` | SECRET | DROP |
| `card_number`, `*ssn*`, `*id_card*` | SENSITIVE | MASK |
| `email`, `phone` | PII | RETAIN with retention policy |
| `request_id`, `user_id` | PUBLIC | retain |

### Double-stream output

| Stream | Format | Use | Restriction |
| --- | --- | --- | --- |
| Human-readable (console) | one-line text | local dev, on-call ad-hoc | off in production or no ANSI |
| Machine-readable (JSON file / OTLP) | JSON Lines | ingestion, alert, query | the only machine contract |

Two streams must use the same event and same fields. Do not duplicate the same JSON event into multiple JSON files.

### Disk protection

| Trigger | Action |
| --- | --- |
| 70% disk | warn |
| 85% disk | drop oldest DEBUG / TRACE; emit metric |
| 95% disk | drop more aggressively; page on-call |
| Hard cap | refuse to write new archive; alert |

Audit log is a separate storage with reserved capacity, not part of the same budget as debug logs.

## Reference index

| File | When to load |
| --- | --- |
| [`../references/logging/logging-model.md`](../references/logging/logging-model.md) | Event selection, single-point responsibility, level, exception fields |
| [`../references/logging/format-output.md`](../references/logging/format-output.md) | JSON Lines default, double-stream, timestamps, fields, sizes |
| [`../references/logging/structured-fields.md`](../references/logging/structured-fields.md) | Field catalog, schema.version, type discipline, units |
| [`../references/logging/sensitive-data.md`](../references/logging/sensitive-data.md) | Field classification, drop / mask / retain, audit vs diagnostic |
| [`../references/logging/implementation-patterns.md`](../references/logging/implementation-patterns.md) | Context injection, unified event recording, unified error exit, async + bounded queue |
| [`../references/logging/governance.md`](../references/logging/governance.md) | Dynamic level, sampling, cost control, ownership |
| [`../references/logging/rotation-retention.md`](../references/logging/rotation-retention.md) | One owner per stream, time + size, compression, retention, remote archive, container specifics |
| [`../references/logging/testing-review.md`](../references/logging/testing-review.md) | Required 5 minimal assertions + extended checks |

## Asset index

| File | Purpose |
| --- | --- |
| [`../assets/logging/log-event-catalog.csv`](../assets/logging/log-event-catalog.csv) | Canonical event catalog |
| [`../assets/logging/log-event-fields.csv`](../assets/logging/log-event-fields.csv) | Field catalog with types and classification |
| [`../assets/logging/log-format-schema.csv`](../assets/logging/log-format-schema.csv) | Format schema |
| [`../assets/logging/log-storage-policy.csv`](../assets/logging/log-storage-policy.csv) | Output target, rotation, retention |
| [`../assets/logging/sensitive-field-policy.csv`](../assets/logging/sensitive-field-policy.csv) | Sensitive field patterns and actions |

## Validation

```bash
uv run scripts/logging/validate_logging_catalog.py \
  ../assets/logging/log-event-catalog.csv \
  --format-schema ../assets/logging/log-format-schema.csv \
  --event-fields ../assets/logging/log-event-fields.csv \
  --storage-policy ../assets/logging/log-storage-policy.csv \
  --sensitive-policy ../assets/logging/sensitive-field-policy.csv

uv run python -m unittest discover -s scripts/logging/tests
```

## Worked example

[`../examples/logging/logging-spec.example.md`](../examples/logging/logging-spec.example.md) — order service five-piece: event catalog (6 events), field catalog (with classification), storage policy (stdout + JSON file), sensitive policy (drop password, mask card_number), required 3 assertions (JSON valid / required fields present / sensitive not present) plus 4 extended checks (rotation, audit downgrade, double-stream consistency, dynamic level rollback).
