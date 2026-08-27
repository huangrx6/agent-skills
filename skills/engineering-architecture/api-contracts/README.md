# API Contracts

> Parent: [`engineering-architecture`](../SKILL.md). Spec for API style selection, resource modeling, schemas, error responses, versioning, governance.

## What this is

Spec for designing and governing API contracts — REST / gRPC / GraphQL / WebSocket / SSE / Webhook / JSON-RPC / Event. Covers style selection, resource modeling, schemas, error responses, versioning, compatibility, security, and contract testing.

## How to invoke

```text
使用 $engineering-architecture/api-contracts 帮我 <做什么>
```

| You say | Agent does |
| --- | --- |
| 选 API 风格 | run `api-style-selection.md` against scenario; load `api-style-selection.csv` decision matrix |
| 评审 OpenAPI/Proto/GraphQL Schema | load `api-review-checklist.csv` + `api-rule-catalog.csv` |
| 写 REST 资源 | load `resource-http-semantics.md`; use `openapi.template.yaml` |
| 写 GraphQL Schema | load `graphql.md`; use `graphql-schema.template.graphql` |
| 写 gRPC Proto | load `grpc-protobuf.md` |
| 写 Webhook 规范 | load `events-webhooks.md` |
| 写 Realtime/SSE/WebSocket | load `realtime-streaming.md` |
| 评估破坏性变更 | use `compatibility-change-matrix.csv`; plan migration + dual-run + sunset |
| 错误响应怎么定 | load `api-error-contract.md` in `engineering-reliability/exception-handling/` |
| 测试契约变更 | load `specification-testing-governance.md`; require contract tests in CI |

## Core principles

- Choose style by interaction model and org capability, not by fashion. REST, gRPC, GraphQL, SSE, WebSocket, Webhook each have a different fit.
- Resources use plural nouns in URI; business actions use command resources (`POST /orders/{id}/cancellations`), not `POST /cancel`.
- HTTP status expresses protocol semantics; a stable error code expresses specific business reason. Never wrap failure in 200.
- Versions are stable identifiers, not timestamps or display names. New optional fields are compatible; field type or meaning changes are not.
- A single style per resource set. Mixing verbs in URI and GraphQL mutation, or REST body and gRPC status codes, produces ambiguous contracts.
- Cache keys must include every identity/tenant/language/version dimension that changes the representation.
- Webhook receivers verify signature, expect retry, dedupe by event ID, validate against replay attacks.
- Streaming endpoints declare message order, backpressure, and recovery boundaries.
- Idempotency is a contract property, not a client behavior. Designate the idempotency key and document TTL.

## Quick reference

### Style decision matrix

| Scenario | Preferred style |
| --- | --- |
| Public API, resource lifecycle, CRUD, broad clients | REST + OpenAPI |
| Internal services, low latency, strong typing | gRPC + Protobuf |
| Multi-frontend, aggregate reads, field-level selection | GraphQL |
| Browser one-way push, progress, notification | SSE |
| Bidirectional, low-latency collaboration, game | WebSocket |
| AI / generative output, chunked results | HTTP Streaming or SSE |
| Domain fact broadcast, multiple consumers, replay | Event / Pub-Sub |
| Cross-org async notification | Webhook |
| Ops or tool commands | JSON-RPC or simple RPC |

Full matrix: [`../assets/api-contracts/api-style-selection.csv`](../assets/api-contracts/api-style-selection.csv).

### Compatibility matrix

| Change | Compatibility | Handling |
| --- | --- | --- |
| Add optional request/response field | COMPATIBLE | old clients ignore |
| Add error code | CONDITIONAL | clients have UNKNOWN branch |
| Remove endpoint | BREAKING | Sunset Header + notice |
| Shorten field length | BREAKING | new version + dual-run |
| Tighten required fields | BREAKING | new version + compat fill |

Full matrix: [`../assets/api-contracts/compatibility-change-matrix.csv`](../assets/api-contracts/compatibility-change-matrix.csv).

### HTTP status semantic for errors

| Status | When |
| --- | --- |
| 400 | syntactic / structural error |
| 401 | no valid credential |
| 403 | identified, no permission |
| 404 | resource absent (or hidden for security) |
| 409 | state conflict / version / duplicate |
| 422 | structure valid, semantics rejected |
| 429 | rate limit; return `Retry-After` |
| 500 | uncaught server defect |
| 502 | invalid upstream response |
| 503 | temporary unavailable / overloaded |
| 504 | upstream timeout |

Full status map: [`../assets/api-contracts/http-operation-status-map.csv`](../assets/api-contracts/http-operation-status-map.csv).

## Reference index

| File | When to load |
| --- | --- |
| [`../references/api-contracts/api-style-selection.md`](../references/api-contracts/api-style-selection.md) | Choosing among REST / gRPC / GraphQL / SSE / WebSocket / Webhook / Event |
| [`../references/api-contracts/resource-http-semantics.md`](../references/api-contracts/resource-http-semantics.md) | REST resource modeling, URI design, methods, status codes, headers, conditional requests |
| [`../references/api-contracts/schema-and-payloads.md`](../references/api-contracts/schema-and-payloads.md) | OpenAPI, JSON Schema, request/response payload patterns |
| [`../references/api-contracts/idempotency-concurrency-async.md`](../references/api-contracts/idempotency-concurrency-async.md) | Idempotency keys, concurrency tokens, async request patterns |
| [`../references/api-contracts/collections-and-batch.md`](../references/api-contracts/collections-and-batch.md) | Pagination, filtering, sorting, batch operations |
| [`../references/api-contracts/versioning-compatibility.md`](../references/api-contracts/versioning-compatibility.md) | Versioning strategies and breaking-change classification |
| [`../references/api-contracts/grpc-protobuf.md`](../references/api-contracts/grpc-protobuf.md) | gRPC service definitions, error codes, deadlines, streaming |
| [`../references/api-contracts/graphql.md`](../references/api-contracts/graphql.md) | GraphQL schema, resolvers, N+1, cost analysis |
| [`../references/api-contracts/realtime-streaming.md`](../references/api-contracts/realtime-streaming.md) | SSE, WebSocket, HTTP streaming, backpressure, recovery |
| [`../references/api-contracts/events-webhooks.md`](../references/api-contracts/events-webhooks.md) | Async events, Webhook signatures, retry, dedupe, replay |
| [`../references/api-contracts/json-rpc.md`](../references/api-contracts/json-rpc.md) | JSON-RPC for tools and command APIs |
| [`../references/api-contracts/security-privacy.md`](../references/api-contracts/security-privacy.md) | Authn / authz / OAuth / API key / mTLS / data classification |
| [`../references/api-contracts/specification-testing-governance.md`](../references/api-contracts/specification-testing-governance.md) | Design-first vs code-first, contract tests, governance |
| [`../references/api-contracts/standards-sources.md`](../references/api-contracts/standards-sources.md) | RFC 9110 / 9111 / 9457 / OpenAPI / AsyncAPI / Protobuf |

## Asset index

| File | Purpose |
| --- | --- |
| [`../assets/api-contracts/openapi.template.yaml`](../assets/api-contracts/openapi.template.yaml) | OpenAPI 3.1 baseline skeleton |
| [`../assets/api-contracts/graphql-schema.template.graphql`](../assets/api-contracts/graphql-schema.template.graphql) | GraphQL schema skeleton |
| [`../assets/api-contracts/api-style-selection.csv`](../assets/api-contracts/api-style-selection.csv) | Style decision matrix |
| [`../assets/api-contracts/api-rule-catalog.csv`](../assets/api-contracts/api-rule-catalog.csv) | API design rules |
| [`../assets/api-contracts/api-review-checklist.csv`](../assets/api-contracts/api-review-checklist.csv) | API review checks |
| [`../assets/api-contracts/compatibility-change-matrix.csv`](../assets/api-contracts/compatibility-change-matrix.csv) | Breaking-change classification |
| [`../assets/api-contracts/http-operation-status-map.csv`](../assets/api-contracts/http-operation-status-map.csv) | HTTP status code map |
| [`../assets/api-contracts/api-change-proposal.template.md`](../assets/api-contracts/api-change-proposal.template.md) | Template for proposing an API change |

## Validation

```bash
uv run scripts/api-contracts/validate_api_contract_catalog.py \
  ../assets/api-contracts/api-rule-catalog.csv \
  --compatibility ../assets/api-contracts/compatibility-change-matrix.csv \
  --status-map ../assets/api-contracts/http-operation-status-map.csv \
  --review ../assets/api-contracts/api-review-checklist.csv \
  --styles ../assets/api-contracts/api-style-selection.csv \
  --openapi ../assets/api-contracts/openapi.template.yaml \
  --graphql ../assets/api-contracts/graphql-schema.template.graphql \
  --change-proposal ../assets/api-contracts/api-change-proposal.template.md

uv run python -m unittest discover -s scripts/api-contracts/tests
```

## Worked example

See [`../examples/api-contracts/contract-brief.example.md`](../examples/api-contracts/contract-brief.example.md) — six scenarios on a single system, each choosing a different style (REST / Webhook / gRPC / GraphQL / WebSocket / Pub-Sub), with full resource modeling, HTTP status, error response, and compatibility matrix.
