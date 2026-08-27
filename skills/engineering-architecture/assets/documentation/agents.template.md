# AGENTS.md

## Before work

1. Read `PROJECT_CONTEXT.md`.
2. Read `docs/index.md`.
3. Read only the canonical documents relevant to the current task.
4. Check whether the target directory has more specific Agent instructions.
5. Verify documentation against code/Schema when they conflict.

## Development

- Setup:
- Test:
- Lint:
- Format:

## Guardrails

- Do not commit secrets or production data.
- Do not change generated files directly.
- Do not introduce new cross-module dependencies without checking architecture boundaries.

## Documentation workflow

Before finishing any material change:

1. Inspect the final diff.
2. Run documentation impact analysis.
3. Update existing canonical docs before creating new docs.
4. Create an ADR only for significant decisions.
5. Update `PROJECT_CONTEXT.md` only when stable project-level facts changed.
6. Update `docs/working-agreements.md` only for explicit durable project agreements.
7. Create a handoff only when work remains unfinished across sessions.
8. Run documentation validation.

Keep this file concise. Detailed project knowledge belongs in `PROJECT_CONTEXT.md` and `docs/`.
