# Code Style

> Parent: [`engineering-quality`](../SKILL.md). Spec for language-agnostic code style plus per-language adaptation — naming, formatting, file organization, file headers, comments, API documentation, design principles, function and type design, dependencies, security, concurrency, performance, testing, version control, code review.

## What this is

Spec for the code style a team agrees on — naming, formatting, file organization, file headers, comments, design principles, function / type / module design, dependency hygiene, concurrency, performance, testing, code review. Includes a language-agnostic main spec and per-language appendices (Java / Go / Python / JS / TS / C# / C/C++ / Rust / SQL).

## How to invoke

```text
使用 $engineering-quality/code-style 帮我 <做什么>
```

| You say | Agent does |
| --- | --- |
| 建立代码规范 | start with `repository-layout.md`; write project profile → main spec → language appendix |
| 评审命名 | load `naming-and-api.md` + `naming-convention-catalog.csv`; check domain meaning, no generic names |
| 评审文件头 | load `file-metadata-versioning.md` + `file-header-policy.csv`; check SPDX, author metadata policy |
| 评审注释 / 文档 | load `comments-documentation.md`; check why-not-what, public API docs, TODO policy |
| 评审实现质量 | load `implementation-quality.md`; check function / type / module design, side effects, boundaries |
| 看设计模式 | load `design-principles-patterns.md` + `design-pattern-catalog.csv`; check fit, not fashion |
| 看多语言附录 | load `language-adaptation.md`; per-language naming / format / tooling baseline |
| 评审代码评审清单 | load `code-review-checklist.csv`; cover naming, comments, tests, security, error handling |
| 看规范完整度自查 | load `standard-completeness-checklist.csv`; ensure all 9 sections of main spec covered |
| 跟安全 / 配置衔接 | see [`../../engineering-security/secure-coding/README.md`](../../engineering-security/secure-coding/README.md) (secure coding rules), [`../configuration/README.md`](../configuration/README.md) (config classification) |

## Core principles

- Naming expresses domain meaning, not implementation. `OrderPaid`, not `OrderDataObj`. `cancelOrder` is a command; `OrderPaid` is an event.
- One concept, one name across code, API, config, database, documentation. Different names for the same concept confuse readers and break search.
- Style must be enforced by tools, not memory. `prettier` / `gofmt` / `black` / `ruff` / `clang-format` decide. Human review does not.
- The main spec is language-agnostic. Per-language appendices handle case / format / tooling. The appendix respects language ecosystem; do not force cross-language uniformity that breaks idioms.
- Public API name is a compatibility contract. Renaming a public API requires a deprecation path.
- File headers, copyright, author metadata are policy, not boilerplate. Choose one rule and apply it consistently.
- Comments explain why, not what. A comment that paraphrases the next line is noise. A comment that documents intent, invariant, or trap is value.
- One function does one thing. A function whose name contains "and" is a candidate to split. A function with side effects in a getter is a bug.
- Type names express role, not technology. `OrderRepository`, not `OrderDAOImpl`. Implementations should be named by strategy, not by interface name suffix.
- Test names express pre-condition / behavior / expected outcome. `test1` is a maintenance bug.
- Boolean names form a decidable proposition. `isEnabled`, `hasPermission`, `canRetry`, not `disableFlag`.
- Units in identifiers. `timeoutMs`, `sizeBytes`, `amountCents`. Better still, use a value object.
- Dependencies are a budget, not a buffet. Each new dependency adds risk. Use allowlist + lockfile.
- Code review covers design, function, complexity, tests, naming, comments, style, documentation. It is not style nits only.

## Quick reference

### Naming by kind

| Object | Pattern | Example |
| --- | --- | --- |
| Type | noun / noun phrase, role | `Order`, `OrderPaid`, `CancelOrder` |
| Function / method | verb / verb phrase, action + result | `cancelOrder`, `findActiveOrders` |
| Variable | business meaning + lifecycle + unit | `pendingOrderIds`, `timeoutMs` |
| Constant | stable concept, not local immutability | `MAX_RETRY_COUNT` |
| Exception | cause, language-convention suffix | `OrderNotFoundException` |
| Event | past-tense fact | `OrderPaid`, `RequestCompleted` |
| Command | intent | `CancelOrder` |
| Query | read intent, no side effects | `getActiveOrders` |

### Boolean name shape

```text
isEnabled
hasPermission
canRetry
shouldRefresh
```

Avoid: `notDisabled`, `disableFlag`, `flag1`.

### Unit in identifier

```text
timeoutMs
sizeBytes
amountCents
createdAtUtc
```

Better: value object `Timeout`, `Bytes`, `Cents` so type system enforces unit.

### Test name shape

```text
givenExpiredToken_whenRefreshing_thenReject
refresh_rejects_expired_token
TestRefresh_ExpiredToken_ReturnsError
```

Forbidden: `test1`, `works`, `normalCase`.

### File header (SPDX)

```text
// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Acme Inc.
```

Author / creation-time / modification-time are policy decisions. If kept, use canonical format. Do not mix styles.

### Main spec 9 sections

`standard-completeness-checklist.csv` covers:

1. Naming
2. Formatting, files, layout, imports
3. File organization, modules, generated code
4. File header, license, author, version metadata
5. Comments, API docs, TODO, examples
6. Design principles, patterns
7. Function and type design
8. Dependencies, configuration, security, concurrency, performance
9. Testing, version control, code review

Each rule has `[must / should / may]` and `automatable / review-only / compliance` so the spec is enforceable.

### Language baseline (minimal)

| Language | Formatter | Linter | Min version | Naming |
| --- | --- | --- | --- | --- |
| Java | Spotless / google-java-format | Checkstyle | 17 LTS | type PascalCase, method camelCase, package lowercase |
| Go | gofmt | go vet | 1.21 | exported names + comments, no `Impl` suffix |
| Python | ruff format | ruff | 3.11 | module / function snake_case, type PascalCase |
| JavaScript / TypeScript | Prettier | ESLint + typescript-eslint | Node 20 / TS 5 | variable / function camelCase, type / class PascalCase |
| C# | dotnet format | Roslyn analyzers | .NET 8 | PascalCase public, camelCase local |
| Rust | rustfmt | clippy | 1.70 | standard |
| SQL | sqlfluff | sqlfluff | per engine | snake_case objects, uppercase keywords |

`language-adaptation.md` has the full baseline.

## Reference index

| File | When to load |
| --- | --- |
| [`../references/code-style/repository-layout.md`](../references/code-style/repository-layout.md) | Main spec vs language appendix vs project profile separation |
| [`../references/code-style/naming-and-api.md`](../references/code-style/naming-and-api.md) | Naming rules, booleans, types, functions, files, tests, public API |
| [`../references/code-style/formatting-and-files.md`](../references/code-style/formatting-and-files.md) | Encoding, line width, indentation, imports, layout |
| [`../references/code-style/comments-documentation.md`](../references/code-style/comments-documentation.md) | Why-not-what, public API docs, TODO / FIXME policy |
| [`../references/code-style/design-principles-patterns.md`](../references/code-style/design-principles-patterns.md) | SOLID / KISS / YAGNI / pattern fit vs fashion |
| [`../references/code-style/implementation-quality.md`](../references/code-style/implementation-quality.md) | Function / type / module design, side effects, boundaries |
| [`../references/code-style/file-metadata-versioning.md`](../references/code-style/file-metadata-versioning.md) | File header, SPDX, author / version policy |
| [`../references/code-style/testing-review.md`](../references/code-style/testing-review.md) | Test naming, coverage, review checklist |
| [`../references/code-style/language-adaptation.md`](../references/code-style/language-adaptation.md) | Per-language baseline and overrides |
| [`../references/code-style/standards-sources.md`](../references/code-style/standards-sources.md) | EditorConfig, language style guides, SemVer, Google review practices |

## Asset index

| File | Purpose |
| --- | --- |
| [`../assets/code-style/naming-convention-catalog.csv`](../assets/code-style/naming-convention-catalog.csv) | Naming rules catalog |
| [`../assets/code-style/file-header-policy.csv`](../assets/code-style/file-header-policy.csv) | File header / SPDX / author policy |
| [`../assets/code-style/design-pattern-catalog.csv`](../assets/code-style/design-pattern-catalog.csv) | Pattern fit / risk catalog |
| [`../assets/code-style/code-review-checklist.csv`](../assets/code-style/code-review-checklist.csv) | Code review checklist |
| [`../assets/code-style/standard-completeness-checklist.csv`](../assets/code-style/standard-completeness-checklist.csv) | Main spec 9-section completeness |
| [`../assets/code-style/editorconfig.template`](../assets/code-style/editorconfig.template) | EditorConfig baseline |
| [`../assets/code-style/source-file-header.template.txt`](../assets/code-style/source-file-header.template.txt) | Source file header template |

## Validation

```bash
uv run scripts/code-style/validate_code_standard.py \
  ../assets/code-style/naming-convention-catalog.csv \
  --header-policy ../assets/code-style/file-header-policy.csv \
  --pattern-catalog ../assets/code-style/design-pattern-catalog.csv \
  --review-checklist ../assets/code-style/code-review-checklist.csv \
  --standard-completeness ../assets/code-style/standard-completeness-checklist.csv

uv run python -m unittest discover -s scripts/code-style/tests
```

## Worked example

[`../examples/code-style/coding-standards.md`](../examples/code-style/coding-standards.md) — full main spec with 9 sections, each rule marked `[must / should / may]` and `automatable / review-only / compliance`.

[`../examples/code-style/coding-standards-java.md`](../examples/code-style/coding-standards-java.md) — Java language appendix: Spotless config, Checkstyle rules, naming table, persistence rules, test stack.

[`../examples/code-style/project-profile.md`](../examples/code-style/project-profile.md) — project profile template: stack, modules, dependencies, common commands.
