# ![architecture](../assets/icons/architecture-light.svg#gh-light-mode-only) ![architecture](../assets/icons/architecture-dark.svg#gh-dark-mode-only) Architecture

> Parent: [`engineering-architecture`](../SKILL.md). Produces system-level decisions: boundaries, style, deployment, ADR.

## What this is

Spec for the structural decisions of a software system — module/service boundaries, architecture style choice, deployment topology, ADR template, architecture review. Inputs are business drivers and quality attributes; outputs are documents and checklists that survive across teams and time.

## How to invoke

```text
使用 $engineering-architecture/architecture 帮我 <做什么>
```

| You say | Agent does |
| --- | --- |
| 帮我做架构设计 | run `architecture-workflow.md`: system context → constraints → quality attributes → boundaries → style → deployment → risks → ADR |
| 评审这个架构 | load `architecture-review-checklist.csv` (ARCH-001…013) + `quality-attribute-scenarios.csv` + `architecture-risk-register.csv` |
| 我要选单体还是微服务 | start from `architecture-styles.md`; do not default to microservices |
| 写一份 ADR | copy `adr.template.md`, fill context/decisions/consequences |
| 写一份架构 brief | copy `architecture-brief.template.md` |
| 我要拆服务 | check `boundaries-modularity.md` first; do not split by table or layer |

## Core principles

- Business drivers and quality attributes drive architecture. The tech stack does not define business boundaries.
- Default to modular monolith. Split only when there is evidence — independent deploy, independent scale, fault isolation, team autonomy, or stable business boundary.
- Service boundaries follow stable business capability and data ownership, not tables or controllers.
- Every piece of business data has exactly one canonical owner; cross-boundary access goes through contracts, never direct reads.
- Synchronous call chains stay short. Long cross-fault-domain workflows are re-designed, not chained.
- Async is for time-decoupling, peak-shaving, broadcast, or workflow — never for hiding unclear ownership or inconsistent consistency.
- Architecture must define failure modes, degradation boundaries, recovery paths, and capacity ceilings — not only the happy path.
- Security, privacy, multi-tenant isolation enter at boundary design, not before launch.
- Observability, deployability, rollbackability are architectural qualities, not post-launch operations work.
- Important decisions are traceable: write ADRs; mark superseded ones, do not delete history.
- Diagrams answer questions; delete or auto-generate what nobody maintains.
- Architecture evolves with the system. Delete or auto-generate what cannot be verified.

## Quick reference

### Architecture style decision

| Need | Style | Why |
| --- | --- | --- |
| One team, MVP, evolving boundaries | modular monolith | low ops cost, local transactions, fast iteration |
| Independent scale for one capability | service split + event bus | scale that capability without scaling the rest |
| Two write paths with very different read shapes | CQRS | separate write model from read model |
| Domain event sourcing for audit/replay | event sourcing | reconstruct any state from event log |
| Background work, retry, DLQ | queue worker | decouple processing from request |
| Burst workloads, no provisioned capacity | serverless | pay per use, scale to zero |
| Sync internal calls with strong contracts | gRPC | type-safe, low-latency, streaming |

Full guide: [`../references/architecture/architecture-styles.md`](../references/architecture/architecture-styles.md).

### Boundary priority order

1. Stable business capability
2. Different domain language and rules
3. Data ownership and transaction boundaries
4. Change frequency
5. Independent scale needs
6. Fault isolation
7. Compliance and security isolation
8. Team autonomy

Full guide: [`../references/architecture/boundaries-modularity.md`](../references/architecture/boundaries-modularity.md).

### Quality attribute scenarios

Every quality attribute becomes a concrete scenario with: source, stimulus, environment, artifact, response, measure, priority. "High performance" is not a valid requirement; "P99 ≤ 800ms under 5x current peak" is.

Template: [`../assets/architecture/quality-attribute-scenarios.csv`](../assets/architecture/quality-attribute-scenarios.csv).

## Reference index

| File | When to load |
| --- | --- |
| [`../references/architecture/architecture-workflow.md`](../references/architecture/architecture-workflow.md) | Full architecture design process |
| [`../references/architecture/architecture-styles.md`](../references/architecture/architecture-styles.md) | Choosing modular monolith / microservices / layered / event-driven / CQRS / event sourcing / queue / serverless |
| [`../references/architecture/boundaries-modularity.md`](../references/architecture/boundaries-modularity.md) | Module, Bounded Context, service, team boundaries |
| [`../references/architecture/integration-distributed.md`](../references/architecture/integration-distributed.md) | Sync / async calls, workflows, distributed failure |
| [`../references/architecture/data-ownership-consistency.md`](../references/architecture/data-ownership-consistency.md) | Data ownership, read models, cache, consistency |
| [`../references/architecture/quality-attributes.md`](../references/architecture/quality-attributes.md) | Availability, performance, scale, security, maintainability |
| [`../references/architecture/deployment-evolution.md`](../references/architecture/deployment-evolution.md) | Deploy units, fault domains, rollout, legacy modernization |
| [`../references/architecture/documentation-adrs.md`](../references/architecture/documentation-adrs.md) | ADR writing and lifecycle |
| [`../references/architecture/review-governance.md`](../references/architecture/review-governance.md) | Review checklist and exception governance |
| [`../references/architecture/standards-sources.md`](../references/architecture/standards-sources.md) | ISO/IEC 42010, ISO/IEC 25010, C4, OWASP, AWS / Azure guides |

## Asset index

| File | Purpose |
| --- | --- |
| [`../assets/architecture/adr.template.md`](../assets/architecture/adr.template.md) | ADR skeleton — context, drivers, options, decision, consequences, validation, revisit trigger |
| [`../assets/architecture/architecture-brief.template.md`](../assets/architecture/architecture-brief.template.md) | Lightweight architecture brief |
| [`../assets/architecture/architecture-decision-matrix.csv`](../assets/architecture/architecture-decision-matrix.csv) | Style preference matrix (style, preferWhen, avoidWhen, keyBenefits, keyCosts, evidenceRequired) |
| [`../assets/architecture/quality-attribute-scenarios.csv`](../assets/architecture/quality-attribute-scenarios.csv) | Quality attribute scenarios template |
| [`../assets/architecture/architecture-risk-register.csv`](../assets/architecture/architecture-risk-register.csv) | Risk register template |
| [`../assets/architecture/architecture-review-checklist.csv`](../assets/architecture/architecture-review-checklist.csv) | ARCH-001…013 review checklist |

## Validation

```bash
uv run scripts/architecture/validate_architecture_catalog.py \
  --decision ../assets/architecture/architecture-decision-matrix.csv \
  --quality ../assets/architecture/quality-attribute-scenarios.csv \
  --risk ../assets/architecture/architecture-risk-register.csv \
  --review ../assets/architecture/architecture-review-checklist.csv \
  --adr ../assets/architecture/adr.template.md \
  --brief ../assets/architecture/architecture-brief.template.md

uv run python -m unittest discover -s scripts/architecture/tests
```

## Worked example

See [`../examples/architecture/adr-001.example.md`](../examples/architecture/adr-001.example.md) — modular monolith + settlement queue decision with full ADR structure: drivers, alternatives, consequences, risks, validation, revisit trigger.

[`../examples/architecture/architecture-brief.example.md`](../examples/architecture/architecture-brief.example.md) — full NovaPay architecture brief covering 11 sections with self-check against ARCH-001…013.

[`../examples/architecture/qa-scenarios.example.md`](../examples/architecture/qa-scenarios.example.md) — 4 quality attribute scenarios with priority and measurable response.

[`../examples/architecture/risk-register.example.csv`](../examples/architecture/risk-register.example.csv) — concrete risk register rows with mitigation and owner.
