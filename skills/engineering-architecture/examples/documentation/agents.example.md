# AGENTS.md（NovaPay · L0 执行指令）

> 只放执行指令，不存项目知识。知识在 PROJECT_CONTEXT.md 与 docs/。

## Before work

1. Read `PROJECT_CONTEXT.md`.
2. Read `docs/index.md`.
3. Read only the canonical docs relevant to the task.
4. Check target directory for more specific Agent instructions.
5. Verify docs against code/Schema when they conflict.

## Development

- Setup: `cd novapay-server && mvn test`
- Frontend: `cd novapay-apps && pnpm dev`
- Lint/format: `mvn spotless:check`

## Guardrails

- Do not commit secrets or production data.
- Do not change generated files directly.
- Do not write other modules' tables directly.

## Documentation workflow

Before finishing any material change:

1. Inspect the final diff.
2. Run documentation impact analysis (`python3 docs/../scripts/doc_impact.py` per repo conventions).
3. Update existing canonical docs before creating new docs.
4. Run documentation validator.
5. Include "Documentation impact" in the final summary.
