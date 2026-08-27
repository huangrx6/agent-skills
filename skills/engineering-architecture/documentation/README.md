# ![documentation](../assets/icons/documentation-light.svg#gh-light-mode-only) ![documentation](../assets/icons/documentation-dark.svg#gh-dark-mode-only) Engineering Documentation

> Parent: [`engineering-architecture`](../SKILL.md). Spec for a documentation system that serves both humans and AI Agents — README, AGENTS.md, PROJECT_CONTEXT, docs/index, ADR, Handoff, lifecycle.

## What this is

Spec for an engineering documentation system designed to serve both humans and AI Agents. Defines the four-layer model (L0 agent instructions / L1 stable project snapshot / L2 navigation / L3 reference), canonical sources, document types, ADRs, Handoffs, lifecycle, and AI-specific concerns (AGENTS.md, doc impact routing).

## How to invoke

```text
使用 $engineering-architecture/documentation 帮我 <做什么>
```

| You say | Agent does |
| --- | --- |
| 给新项目搭文档体系 | copy the 4-layer model from `information-architecture.md`; create `README.md` + `AGENTS.md` + `PROJECT_CONTEXT.md` + `docs/index.md` |
| 写 PROJECT_CONTEXT | copy `project-context.template.md`; keep ≤ 200 lines, link to canonical docs |
| 写 docs/index | copy `docs-index.template.md`; organize by "I want to ... → read this" |
| 写 AGENTS.md | copy `agents.template.md`; keep only mandatory instructions, not knowledge |
| 写 ADR | copy `decision.template.md`; load `decision-records.md` for state machine |
| 写 Handoff | copy `handoff.template.md`; set `expires_or_close_when` |
| 评审文档结构 | load `documentation-review-checklist.csv` + `document-type-policy.csv` + `document-impact-rules.csv` |
| 任务完成该更新哪个文档 | run `scripts/documentation/doc_impact.py <path> --rules document-impact-rules.csv` |
| 建立 working agreements | copy `working-agreements.template.md`; keep only automatable or stable rules |
| 评估文档自动化 | load `docs-as-code-automation.md`; link-check, spell-check, freshness, link from code |

## Core principles

- A fact has one canonical source. README, PROJECT_CONTEXT, code comments, and docs do not duplicate the same fact.
- README is the human entry point — what it is, who for, how to start, where to read more. AGENTS.md is the Agent entry point — instructions it must execute. PROJECT_CONTEXT is the stable project snapshot. docs/index is the question-oriented navigation. Each file has one job; do not merge.
- AGENTS.md only contains instructions the Agent must execute, not knowledge it should know. Knowledge goes in references/ that the Agent loads on demand.
- ADRs record important decisions (reversibility, multi-team, security/perf/reliability impact, alternatives, why). Not every change is ADR-worthy. Superseded ADRs are kept and marked, not deleted.
- Handoff is for unfinished cross-session / cross-person work. It must have an `expires_or_close_when` so it does not become permanent.
- Document type has a fixed state enum. Long-doc: `draft / active / deprecated / superseded / archived`. ADR: `Proposed / Accepted / Rejected / Superseded`. Handoff: `active / blocked / completed / abandoned`. Do not mix values across types.
- New content goes to a canonical source first. If the topic already has a doc, update it. If not, decide whether it is a new audience / owner / lifecycle before creating a new file.
- Docs evolve with the system. Review is event-driven, not calendar-driven. Trigger: new service, breaking API change, data owner change, new SLO, etc.
- `last_reviewed` is not a checkbox. Do not auto-update it just to make CI green.
- Error in AI-retrievable docs is worse than missing docs. Delete or archive what is no longer current.

## Quick reference

### 4-layer model

| Layer | File | Reader | Job |
| --- | --- | --- | --- |
| L0 | `AGENTS.md` | AI Agent | Instructions to execute |
| L1 | `PROJECT_CONTEXT.md` | Human + AI | Stable project snapshot + knowledge routing |
| L2 | `docs/index.md` | Human + AI | Question-oriented navigation |
| L3 | `docs/**` | Human + AI | Reference material |

Full layout: [`../references/documentation/information-architecture.md`](../references/documentation/information-architecture.md).

### Document lifecycle

| Status (long-doc) | Meaning |
| --- | --- |
| `draft` | WIP, not yet reviewable |
| `active` | current truth |
| `deprecated` | will be removed; do not use for new work |
| `superseded` | replaced by another doc; kept for history |
| `archived` | historical record only; not authoritative |

ADR states: `Proposed` / `Accepted` / `Rejected` / `Superseded` (uses `supersedes` / `superseded_by` fields).
Handoff states: `active` / `blocked` / `completed` / `abandoned` (uses `expires_or_close_when`).

### When to create vs update

| Signal | Action |
| --- | --- |
| Same topic fact changes | Update existing doc |
| New topic, new audience, new owner, new lifecycle | Create new doc |
| One doc already answers multiple unrelated questions | Refactor (split or add `index.md` in that directory) |
| Decision is hard to reverse, multi-team, multi-alternative, significant impact | Write ADR |
| Unfinished work to hand off | Write Handoff with `expires_or_close_when` |
| Doc is wrong and no historical value | Delete |
| Doc is wrong but explains the past | Mark `superseded` |

Full guide: [`../references/documentation/document-lifecycle.md`](../references/documentation/document-lifecycle.md).

### Documentation owner rules

`document-type-policy.csv` maps each document type to its owner and canonical location:

| Type | Owner | Location |
| --- | --- | --- |
| PROJECT_CONTEXT | platform team | repo root |
| Architecture overview | architecture team | `docs/architecture/overview.md` |
| ADR | decision owner | `docs/architecture/decisions/` |
| API / Contract | API owner | `docs/contracts/` |
| Data ownership | data owner | `docs/data/` |
| Runbook | service owner | `docs/operations/runbooks/` |
| Working agreements | team | `docs/working-agreements.md` |
| Handoff | handoff owner | `docs/handoffs/active/` |

### AI completion: doc impact routing

When a task touches the codebase, run `doc_impact.py` against the changed paths to find which doc areas must be reviewed for update:

```bash
uv run scripts/documentation/doc_impact.py \
  --rules ../assets/documentation/document-impact-rules.csv \
  <changed-path-1> <changed-path-2> ...
```

| Change | Docs to review |
| --- | --- |
| New service / module | PROJECT_CONTEXT, architecture |
| API breaking change | contracts, migration guide |
| New config key | development / configuration |
| Data owner change | data/ownership, architecture |
| New SLO / alert | operations |
| New team rule | AGENTS / working-agreements |
| Major architecture decision | ADR + architecture overview |

## Reference index

| File | When to load |
| --- | --- |
| [`../references/documentation/information-architecture.md`](../references/documentation/information-architecture.md) | 4-layer model, README vs AGENTS vs PROJECT_CONTEXT vs docs/index |
| [`../references/documentation/document-types.md`](../references/documentation/document-types.md) | Overview / How-to / Reference / Tutorial / Runbook / Working agreement |
| [`../references/documentation/document-lifecycle.md`](../references/documentation/document-lifecycle.md) | Status enum, when to update vs create vs delete, superseded rule |
| [`../references/documentation/decision-records.md`](../references/documentation/decision-records.md) | ADR writing, supersede relationship, when an ADR is justified |
| [`../references/documentation/handoffs-current-state.md`](../references/documentation/handoffs-current-state.md) | Handoff template and `expires_or_close_when` |
| [`../references/documentation/working-agreements-memory.md`](../references/documentation/working-agreements-memory.md) | What belongs in working-agreements vs personal preference |
| [`../references/documentation/task-completion-synthesis.md`](../references/documentation/task-completion-synthesis.md) | What to update after a task, AI behavior |
| [`../references/documentation/ai-context-agents.md`](../references/documentation/ai-context-agents.md) | AGENTS.md scope, Codex layered instructions, byte budget |
| [`../references/documentation/docs-as-code-automation.md`](../references/documentation/docs-as-code-automation.md) | Link check, freshness, automated generation |
| [`../references/documentation/standards-sources.md`](../references/documentation/standards-sources.md) | AGENTS.md / Skills / Diátaxis / C4 / ADR sources |

## Asset index

| File | Purpose |
| --- | --- |
| [`../assets/documentation/project-context.template.md`](../assets/documentation/project-context.template.md) | PROJECT_CONTEXT.md skeleton (≤ 200 lines) |
| [`../assets/documentation/docs-index.template.md`](../assets/documentation/docs-index.template.md) | docs/index.md question-oriented navigation |
| [`../assets/documentation/agents.template.md`](../assets/documentation/agents.template.md) | AGENTS.md instruction-only skeleton |
| [`../assets/documentation/decision.template.md`](../assets/documentation/decision.template.md) | ADR skeleton |
| [`../assets/documentation/handoff.template.md`](../assets/documentation/handoff.template.md) | Handoff skeleton with `expires_or_close_when` |
| [`../assets/documentation/working-agreements.template.md`](../assets/documentation/working-agreements.template.md) | Working-agreements skeleton |
| [`../assets/documentation/project-documentation-tree.template.txt`](../assets/documentation/project-documentation-tree.template.txt) | Recommended directory tree |
| [`../assets/documentation/document-type-policy.csv`](../assets/documentation/document-type-policy.csv) | Document type → owner / canonical location |
| [`../assets/documentation/document-impact-rules.csv`](../assets/documentation/document-impact-rules.csv) | Path pattern → which docs to review |
| [`../assets/documentation/documentation-review-checklist.csv`](../assets/documentation/documentation-review-checklist.csv) | Doc review checks |

## Validation

```bash
uv run scripts/documentation/validate_documentation_system.py \
  --assets ../assets/documentation/ \
  --project <path-to-PROJECT_CONTEXT.md>   # optional

uv run scripts/documentation/doc_impact.py \
  --rules ../assets/documentation/document-impact-rules.csv \
  <changed-path>

uv run python -m unittest discover -s scripts/documentation/tests
```

## Worked example

[`../examples/documentation/project-context.example.md`](../examples/documentation/project-context.example.md) — completed PROJECT_CONTEXT (10 sections: Purpose, Repo Map, Tech, Architecture, Vocabulary, Invariants, Common Commands, Canonical Docs, Sharp Edges, Maintenance).

[`../examples/documentation/docs-index.example.md`](../examples/documentation/docs-index.example.md) — docs/index with "I want to ..." navigation and ownership table.

[`../examples/documentation/agents.example.md`](../examples/documentation/agents.example.md) — AGENTS.md showing what belongs and what does not.

[`../examples/documentation/doc-tree.example.md`](../examples/documentation/doc-tree.example.md) — full documentation tree populated per `project-documentation-tree.template.txt`.

[`../examples/documentation/README.md`](../examples/documentation/README.md) — overview of the documentation example set.
