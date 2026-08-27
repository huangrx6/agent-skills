# ![configuration](../assets/icons/configuration-light.svg#gh-light-mode-only) ![configuration](../assets/icons/configuration-dark.svg#gh-dark-mode-only) Configuration

> Parent: [`engineering-quality`](../SKILL.md). Spec for application configuration — classification, schema, source and priority, environment isolation, startup validation, dynamic configuration, hot reload, config center, cache, Feature Flag, Secret separation, change audit, rollout, rollback, drift detection, Kubernetes ConfigMap / Secret, configuration testing.

## What this is

Spec for treating every configuration as a typed, sourced, versioned, validated, rollback-able artifact. Distinguishes Code Constant, Deployment Config, Secret, Dynamic Config, and Feature Flag. Defines schema, source priority, startup validation, dynamic refresh, Feature Flag discipline, change audit, and drift detection.

## How to invoke

```text
使用 $engineering-quality/configuration 帮我 <做什么>
```

| You say | Agent does |
| --- | --- |
| 设计配置体系 | load `config-model.md`; classify by 5 categories; define schema and source priority |
| 写配置 schema | load `config-schema-catalog.csv`; define key, type, unit, required, default, min/max, enum, secret, dynamic, owner |
| 评审我的配置 | load `config-source-precedence.csv`; verify single source of truth + audit + rollback |
| 启动校验 | load `config-model.md` (startup section); fail fast on missing or invalid |
| 接入配置中心 | load `dynamic-configuration.md`; define refresh, version, atomic apply, fail behavior, rollback |
| 设计 Feature Flag | load `feature-flags-secrets.md`; type (Release / Experiment / Operational / Entitlement), owner, expiry, remove plan |
| Secret 管理 | load `feature-flags-secrets.md` (Secret section); Secrets Manager only, rotation, no Git / log |
| 写配置变更流程 | copy `config-change.template.md`; current / proposed / validation / canary / metrics / rollback / cleanup |
| Kubernetes ConfigMap / Secret | load `kubernetes-configuration.md`; refresh semantics, mount mode, owner, validation |
| 漂移检测 | load `change-governance.md`; detect config drift between declared and actual; alert |
| 配置测试 | load `change-governance.md` (testing section); required unit + integration tests for config |
| 跟安全 / 代码风格衔接 | see [`../../engineering-security/secure-coding/README.md`](../../engineering-security/secure-coding/README.md) (Secret security), [`../code-style/README.md`](../code-style/README.md) (config code style) |

## Core principles

- Every configuration has: type, source, version of truth, validation, change model, rollback path. If a config has no rollback, it is a hidden change.
- Five categories are distinct. `Code Constant` lives in code. `Deployment Config` is environment-injected. `Secret` is a Secrets Manager value. `Dynamic Config` is runtime-mutable. `Feature Flag` is targeted, audited, expirable. Mixing them creates incidents.
- A fact has one source. If two sources disagree, you have a bug, not a feature. Define explicit priority and resolve in code, not in documentation.
- Startup must complete full validation. Missing required key, wrong type, value out of range — fail at startup, not at the first request that needs the value.
- Dynamic config declares: refresh trigger, version, atomic apply, partial-failure behavior, rollback, observability. Mutation without observability is dangerous.
- Feature Flag has: owner, targeting, TTL / remove condition. A flag at 100% for months is a permanent branch, not a flag. Permanent branch must be removed.
- Secret is not a config. Secret is in Secrets Manager. Config references it by name. Environment variable is an injection channel, not a secret manager.
- Configuration change is a release event. Audit, canary, metrics, rollback, cleanup. The same discipline as code.
- Kubernetes ConfigMap refresh semantics depend on mount mode (`env`, `volume`, `subPath`). Defaults are not universal; verify per platform.
- Configuration drift between declared and actual is a bug. Detect it; never let it live undetected for weeks.
- Configuration without test is a runtime risk. Required keys have unit tests. Refresh has integration tests.

## Quick reference

### Five categories

| Category | Meaning | Example | Change way |
| --- | --- | --- | --- |
| Code Constant | protocol / algorithm fixed | HTTP status, math | code change |
| Deployment Config | environment parameter | address, thread count, timeout | deployment inject |
| Secret | sensitive credential | password, token, private key | Secrets Manager |
| Dynamic Config | runtime adjustable | rate limit, switch | config center |
| Feature Flag | progressive / experiment / kill switch | new feature toggle | flag platform |

The category decides: change path, rollback path, audit requirement, dynamic update eligibility.

### Configuration naming

```text
<domain>.<component>.<key> = <value>
```

Examples:

- `http.client.payment.timeout_ms`
- `worker.order.concurrency`

Rules:

- Dotted namespace, no abbreviations unless standard.
- Unit in name: `timeout_ms`, `size_bytes`, `concurrency`.
- Avoid ambiguity: `retry_count` vs `retry_total_duration`.

### Schema per key

| Field | Example |
| --- | --- |
| key | `http.client.payment.timeout_ms` |
| type | int / string / bool / duration / enum |
| unit | ms / bytes / count |
| required | true / false |
| default | 200 |
| min / max | 50 / 5000 |
| enum | `["error","warn","info"]` (if applicable) |
| secret | true / false |
| dynamic | true / false |
| owner | team-payments |
| description | one-line |

### Source priority

1. Code default (compile-time fallback)
2. Local config file (`config.local.yaml` — git-ignored)
3. Environment variable (deploy-time)
4. ConfigMap / config file (deploy-time)
5. Config center (runtime dynamic)

Each layer must override only what it has explicit reason to override. Higher-numbered layers win; document each override.

### Startup validation

| Failure | Behavior |
| --- | --- |
| Required key missing | fail startup with clear key name |
| Type mismatch | fail startup, log offending key + actual + expected |
| Enum value not allowed | fail startup, list allowed values |
| Out of range | fail startup with range |
| Secret reference not resolvable | fail startup, not at first request |

### Dynamic config refresh

| Aspect | Define |
| --- | --- |
| Trigger | push / poll / event |
| Version | monotonic, stored with value |
| Atomicity | all-or-nothing per refresh; no partial state |
| Failure behavior | keep last known good, alert, do not crash |
| Rollback | revert to last known good version, automated if safety threshold hit |
| Audit | who changed what, when, why |
| Observability | metric on refresh count, age of last successful refresh, drift |

### Feature Flag discipline

| Type | Use | Example |
| --- | --- | --- |
| Release | progressive rollout of new feature | new payment channel 1% → 100% |
| Experiment | A/B test | compare two algorithms |
| Operational Kill Switch | emergency stop | pause a dependency call |
| Entitlement | feature gating by plan | premium feature for paid plan |

Each flag must have: key, owner, purpose, `created_at`, targeting, default, expiry / remove condition. A flag at 100% with no remove plan is permanent technical debt.

Flag lifecycle: `create → dark launch → canary → rollout → 100% → remove flag and dead code`. Removal is mandatory, not optional.

### Secret management

| Aspect | Rule |
| --- | --- |
| Storage | Secrets Manager / Vault / platform Secret |
| Injection | env var or SDK read at startup; not in code |
| Access | minimal permission; per service and per environment |
| Rotation | support rotation without restart; double-key overlap period |
| Audit | who read which Secret when |
| Verification | test that Secret does not appear in log / config export / error |

Kubernetes Secret `base64` is encoding, not encryption. Use platform encryption provider.

### ConfigMap / Secret in Kubernetes

| Mount mode | Refresh |
| --- | --- |
| `env` | on pod restart only |
| `volume` | sync every ~60s (kubelet) |
| `subPath` | on pod restart only |

Verify against the actual platform; do not assume. For dynamic update, use a config center, not ConfigMap.

### Configuration drift detection

| Drift | Detection |
| --- | --- |
| declared key missing in runtime | metric on missing required key at startup |
| actual value differs from declared | periodic snapshot + diff + alert |
| historical change without audit | config change audit log completeness check |
| no-owner key in code | grep / static scan |

## Reference index

| File | When to load |
| --- | --- |
| [`../references/configuration/config-model.md`](../references/configuration/config-model.md) | 5 categories, schema, naming, source priority, startup validation |
| [`../references/configuration/dynamic-configuration.md`](../references/configuration/dynamic-configuration.md) | Refresh trigger, version, atomicity, rollback, observability |
| [`../references/configuration/feature-flags-secrets.md`](../references/configuration/feature-flags-secrets.md) | Feature Flag types / lifecycle / removal; Secret management |
| [`../references/configuration/change-governance.md`](../references/configuration/change-governance.md) | Audit, canary, metrics, rollback, drift detection, testing |
| [`../references/configuration/kubernetes-configuration.md`](../references/configuration/kubernetes-configuration.md) | ConfigMap / Secret mount mode, refresh semantics, ownership |
| [`../references/configuration/standards-sources.md`](../references/configuration/standards-sources.md) | Kubernetes Docs, OWASP Secret Management, 12-Factor, Vault |

## Asset index

| File | Purpose |
| --- | --- |
| [`../assets/configuration/config-schema-catalog.csv`](../assets/configuration/config-schema-catalog.csv) | Configuration schema catalog |
| [`../assets/configuration/config-source-precedence.csv`](../assets/configuration/config-source-precedence.csv) | Source priority and override rules |
| [`../assets/configuration/dynamic-config-policy.csv`](../assets/configuration/dynamic-config-policy.csv) | Dynamic config refresh and rollback policy |
| [`../assets/configuration/config-review-checklist.csv`](../assets/configuration/config-review-checklist.csv) | Configuration review checks |
| [`../assets/configuration/config-change.template.md`](../assets/configuration/config-change.template.md) | Configuration change template (key / owner / current / proposed / validation / canary / metrics / rollback / cleanup) |

## Validation

```bash
uv run scripts/configuration/validate_configuration.py --assets ../assets/configuration/

uv run python -m unittest discover -s scripts/configuration/tests
```

## Worked example

[`../examples/configuration/configuration-design.example.md`](../examples/configuration/configuration-design.example.md) — end-to-end configuration design for a payment service: 5-category classification (Code Constant / Deployment Config / Secret / Dynamic Config / Feature Flag), schema entries with units and ranges, source priority chain, startup validation behavior, dynamic refresh contract, Feature Flag lifecycle, and a configuration change template for a rate-limit adjustment with canary and rollback.
