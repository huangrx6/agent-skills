# ![secure-coding](../assets/icons/secure-coding-light.svg#gh-light-mode-only) ![secure-coding](../assets/icons/secure-coding-dark.svg#gh-dark-mode-only) Secure Coding

> Parent: [`engineering-security`](../SKILL.md). Spec for threat modeling, input validation, output encoding, injection defense, authentication / authorization, secrets, cryptography, dangerous APIs, dependencies, security testing, and AI-assisted code security audit.

## What this is

Spec for what every developer and AI Agent must answer when writing code: which inputs are untrusted, which dangerous interpreters or sensitive operations data flows into, where validation / encoding / parameterization / authorization / limit is required, which APIs must not be used directly, and which security requirements must be proved by tests and static checks. The spec gives executable controls, not a checklist of OWASP / CWE entries.

## How to invoke

```text
使用 $engineering-security/secure-coding 帮我 <做什么>
```

| You say | Agent does |
| --- | --- |
| 评审代码找安全风险 | load `security-workflow.md`; do diff-based review; check Source / Sink / Control / bypass / resource / authz / error / dependency |
| 做威胁建模 | load `security-workflow.md`; identify assets, trust boundary, Source, Sink, control placement, failure mode |
| 加输入验证 | load `input-output-injection.md`; syntax + semantic; allowlist preferred |
| 修 SQL / NoSQL 注入 | load `input-output-injection.md`; require parameterized query; user-supplied sort / table / column must use allowlist mapping |
| 修 XSS / HTML 注入 | load `input-output-injection.md`; output encoding by context (HTML / attr / URL / JS / CSS) |
| 设计认证 / 授权 | load `authentication-authorization.md`; check (subject, action, resource, tenant, context); default deny |
| 管密钥 | load `secrets-crypto-data.md`; Secrets Manager, rotation, no Git / log / example |
| 防 SSRF | load `files-network-parsing.md`; allowlist target, block private / link-local / metadata IP, handle redirect, DNS rebinding |
| 文件上传安全 | load `files-network-parsing.md`; allowlist extension, real type, size, random storage name |
| 反序列化 | load `files-network-parsing.md`; prefer JSON / Proto; never native deserialize untrusted |
| 危险 API 评审 | load `dangerous-apis-runtime.md`; ban eval / shell=true / disable TLS verify / temp auth bypass |
| 依赖漏洞 | load `dependencies-supply-chain.md`; CI scan, allowlist, lockfile, license |
| 写安全测试 | load `security-testing-review.md`; negative paths, BOLA, IDOR, replay, CSRF, CORS |
| AI 生成代码审查 | load `ai-assisted-secure-coding.md`; cross-check generated code against all rules |
| 安全 exception | copy `security-exception.template.md`; record reason, owner, expiration, fix plan |
| 评审 PR | load `security-review-checklist.csv` (28 checks, including blockers) |

## Core principles

- Untrusted data entering a dangerous interpreter or sensitive operation must be validated, encoded, parameterized, or authorized. There is no other option.
- Default deny. Every new endpoint / field / handler / message consumer must declare its permission. Do not inherit "public by default".
- Trust boundary is a code shape: validate at the boundary, do not re-validate inside after data crosses a domain boundary.
- Parameterized query is the only safe path to a database. ORM raw query must keep parameter binding. User-supplied sort / table / column must use allowlist mapping, not string concatenation.
- Output encoding depends on context. HTML escape is not JS escape. Use the right encoder for HTML / attribute / URL / JavaScript / CSS / JSON in HTML.
- Allowlist is the primary control. Blacklist is supplementary detection, never the boundary.
- Dangerous APIs are banned by default: `eval`, `exec`, runtime expression engines, unsafe deserialization, `shell=true`, disable TLS verification, trust-all CORS with credentials, temporary auth bypass. Use requires security review.
- Secrets never enter Git, logs, examples, test fixtures. Environment variable is an injection channel, not a secret manager. Rotate when leaked; rewriting history does not undo leak.
- Authentication and authorization are separate concerns. AuthN answers "who is this". AuthZ answers "may this (subject) do (action) on (resource) for (tenant) in (context)". Check both, every request.
- Client-side UI hiding is not authorization. A button hidden in the UI is still a request the server must reject.
- High-risk operations (payment, permission change, key change, account state) require re-auth, anti-replay, idempotency, step-up authorization, dual control, audit, transaction limits.
- Dependency vulnerabilities are CI gate. Known critical CVE in production fails the build.
- AI-generated code must be cross-checked against the same rules. The Agent is the author, not the auditor.
- Fuzzing and security tests prove the control. SAST proves the rule. Neither replaces the other.

## Quick reference

### Source / Sink / Control

| Concept | What it is | Question |
| --- | --- | --- |
| Source | untrusted data input | where does it enter? |
| Sink | dangerous interpreter / sensitive operation | where does it land? |
| Control | validation, encoding, parameterization, authorization, limit | is there a control on the path? |
| Bypass | way to skip the control | can the control be bypassed? |
| Resource | CPU, memory, file, connection, money | what is the resource limit? |
| Authz | per-request, per-resource, per-tenant | is authz enforced for each item? |
| Error | sanitized response, full internal log | does error leak implementation? |
| Dependency | new package or new version | is the new dependency reviewed? |

### Banned-by-default APIs

| API | Why | Required if used |
| --- | --- | --- |
| `eval` / `exec` / `new Function` | arbitrary code execution | security review |
| Runtime expression engines (EL, SpEL, OGNL, Jinja, Velocity) | template injection | security review + sandbox |
| Native deserialization of untrusted input | RCE | signature + allowlist + sandbox |
| `shell=true` / `sh -c <user>` / `cmd.exe /c <user>` | command injection | none — use array + fixed executable |
| Disable TLS verification / trust-all cert | MITM | never |
| Global CORS allow all with credentials | credential theft | never |
| Temporary auth bypass | privilege escalation | security exception with expiration |
| `unsafe deserialization` (Java / Python pickle) | RCE | never on untrusted input |

### Output encoding by context

| Context | Control |
| --- | --- |
| HTML text | HTML entity encoding |
| HTML attribute | attribute-safe + quoted |
| URL parameter | URL component encoding |
| JavaScript | JS context-safe; prefer not to inline |
| CSS | CSS context-safe; prefer no untrusted values |
| JSON in HTML | safe serializer + correct script-embedding policy |

### Sensitive data classification

| Class | Example | Action |
| --- | --- | --- |
| SECRET | password, API key, token, private key, signing key | drop from logs / errors / traces; Secrets Manager; rotation |
| SENSITIVE | card_number, SSN, id_card | mask; encrypt at rest; access control; retention |
| PII | email, phone | retain with retention; access control; purpose limit |
| PUBLIC | request_id, user_id, order_id | retain |

### Release gate (blocker list)

| Check | Severity |
| --- | --- |
| credential committed | BLOCKER |
| known exploitable critical CVE in dependency | BLOCKER |
| missing authz on protected operation | BLOCKER |
| raw SQL / command injection pattern | BLOCKER |
| TLS verify disabled | BLOCKER |
| unrestricted file path / SSRF target | BLOCKER |
| unsafe deserialization of untrusted input | BLOCKER |
| cross-tenant data access | BLOCKER |
| security bypass left enabled | BLOCKER |

## Reference index

| File | When to load |
| --- | --- |
| [`../references/secure-coding/security-workflow.md`](../references/secure-coding/security-workflow.md) | Source / Sink / Control / resource / authz / error / dependency review |
| [`../references/secure-coding/input-output-injection.md`](../references/secure-coding/input-output-injection.md) | Input validation, SQL / NoSQL / OS / template / LDAP / XPath / header, output encoding |
| [`../references/secure-coding/authentication-authorization.md`](../references/secure-coding/authentication-authorization.md) | Authn, authz, session / cookie, token, sensitive operation |
| [`../references/secure-coding/secrets-crypto-data.md`](../references/secure-coding/secrets-crypto-data.md) | Secret management, cryptography, TLS, sensitive data |
| [`../references/secure-coding/files-network-parsing.md`](../references/secure-coding/files-network-parsing.md) | File upload, path traversal, SSRF, redirect, XML, deserialization |
| [`../references/secure-coding/dangerous-apis-runtime.md`](../references/secure-coding/dangerous-apis-runtime.md) | Process, temp file, reflection, native / unsafe, random, integer, parser config |
| [`../references/secure-coding/dependencies-supply-chain.md`](../references/secure-coding/dependencies-supply-chain.md) | Vulnerability scan, secret scan, license, lockfile, SBOM |
| [`../references/secure-coding/web-browser-security.md`](../references/secure-coding/web-browser-security.md) | CSRF, CORS, CSP, cookie, session |
| [`../references/secure-coding/security-testing-review.md`](../references/secure-coding/security-testing-review.md) | Diff-based review, negative paths, SAST, fuzz, security exception, release gate |
| [`../references/secure-coding/ai-assisted-secure-coding.md`](../references/secure-coding/ai-assisted-secure-coding.md) | AI-generated code review, prompt-injection awareness, dependency verification |
| [`../references/secure-coding/standards-sources.md`](../references/secure-coding/standards-sources.md) | OWASP ASVS / Cheat Sheet, NIST SSDF, CWE, OWASP LLMVS |

## Asset index

| File | Purpose |
| --- | --- |
| [`../assets/secure-coding/security-control-catalog.csv`](../assets/secure-coding/security-control-catalog.csv) | Security controls catalog |
| [`../assets/secure-coding/taint-source-sink-catalog.csv`](../assets/secure-coding/taint-source-sink-catalog.csv) | Source / Sink / control catalog |
| [`../assets/secure-coding/security-review-checklist.csv`](../assets/secure-coding/security-review-checklist.csv) | Security review checklist |
| [`../assets/secure-coding/security-impact-rules.csv`](../assets/secure-coding/security-impact-rules.csv) | Path pattern → which security checks to run |
| [`../assets/secure-coding/security-exception.template.md`](../assets/secure-coding/security-exception.template.md) | Security exception template |

## Validation

```bash
uv run scripts/secure-coding/validate_secure_coding.py --assets ../assets/secure-coding/
uv run scripts/secure-coding/security_impact.py \
  --rules ../assets/secure-coding/security-impact-rules.csv \
  <changed-path>

uv run python -m unittest discover -s scripts/secure-coding/tests
```

## Worked example

[`../examples/secure-coding/security-review.example.md`](../examples/secure-coding/security-review.example.md) — concrete PR review for an order-cancellation endpoint: trust boundary identification, Source / Sink table, control placement, 6 negative-path tests (BOLA, IDOR, replay, dependency timeout, internal-leak, CSRF), and a security exception with expiration for one accepted deviation.
