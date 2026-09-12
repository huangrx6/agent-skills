---
name: obsidian-work-log-release-recorder
description: Use this skill after completing a coding task, deployment task, configuration adjustment, database/script change, release preparation, or meaningful project update when the user wants durable notes in Huangrx6's Obsidian vault. It records only landed, reusable, or release-relevant facts into the correct Project/Area/Resource location and maintains a weekly release note with scripts, configs, deployment paths, validation, rollback, and execution assumptions. Use it whenever the user says to record, summarize, settle,沉淀, 更新知识库, 记到 Obsidian, 写发版文档, or after a task has produced operational knowledge worth keeping. This skill is bound to Huangrx6's specific vault path /Users/huangrx6/Documents/obsidian; cross-machine reuse is limited.
---

# Obsidian Work Log And Release Recorder

This skill turns completed work into durable Obsidian notes. It is intentionally selective: the goal is not to preserve the chat transcript, but to keep the small set of facts that will help the next implementation, release, rollback, or handoff.

## Prerequisites（机器 binding）

This skill is bound to a specific machine and Obsidian vault:

- vault path must be `/Users/huangrx6/Documents/obsidian`
- **cross-machine reuse is limited**: switching machines or vault paths requires re-aligning references

### Mandatory startup checklist

Before writing anything to the vault, you **must**:

1. Load `obsidian-personal-knowledge-base/references/vault-map.md` — the vault's directory map and placement conventions.
2. Load `obsidian-personal-knowledge-base/references/writing-conventions.md` — naming, frontmatter, link, and MOC conventions.
3. Probe the target area with a single-level `ls` (see Location Decision) — `vault-map.md` is a snapshot, not authoritative; file system wins on conflict.

These are hard requirements, not suggestions. If `obsidian-personal-knowledge-base` is not installed, tell the user to install it first and stop. Do not write into the vault based on assumptions about its structure. Do not fork the vault conventions into this skill — when PKB's references change, this skill inherits the change.

## Scope

Reuse the nearest existing project, area, resource note, MOC, or template rather than inventing a parallel structure. When no existing note owns the topic, follow the placement rules in `obsidian-personal-knowledge-base/references/vault-map.md`.

## Trigger Signals

Use this skill when one or more of these are true:

- a task has been completed and produced implementation decisions, scripts, paths, configs, database changes, environment variables, validation steps, rollback steps, or release commands
- the user asks to record work into the personal knowledge base
- the user asks for a weekly release note, release checklist, deployment record, or 发版文档
- a project or area note needs to be updated after code, SQL, config, deployment, or operations work
- a recurring operations process becomes clearer after a task and should be kept for future use

Do not trigger for ordinary explanations, brainstorming, speculative plans, one-off chat summaries, or tiny edits with no future operational value.

## What To Record

Record only landed points. A landed point is something that is now true, was executed, was changed, or is ready to be followed by another person.

Good candidates:

- files, modules, APIs, scripts, SQL files, routes, services, or deployment paths that changed
- commands that were run or must be run during release
- config keys, env vars, ports, server paths, container names, cron jobs, or feature flags that matter
- validation evidence such as build commands, smoke tests, API checks, screenshots, logs, or known skipped checks
- rollback or backup steps
- execution order assumptions, dependencies, preconditions, and risks
- durable design decisions that affect future work

Do not record: raw conversation; every file touched when only a summary matters; failed experiments unless they prevent future mistakes; trivial formatting or local-only noise; secrets, tokens, passwords, or full credentials; speculative plans that were not accepted.

If a detail looks sensitive but operationally important, record the variable or config name and location, not the secret value.

## Location Decision

Choose the narrowest stable home:

- Outcome-driven work with a finish line goes under `01 Projects/<project>/`.
- Long-running responsibilities, delivery systems, or operations knowledge goes under `02 Areas/<area>/`.
- Reusable technical knowledge goes under `03 Resources/<topic>/`.
- Unclear or incomplete capture goes under `00 Inbox/`, but only when there is not enough context to classify safely.

For this skill, resolve paths by **probing**, not from memory.

1. Probe the candidate area before writing (`ls "$VAULT/01 Projects"`, `ls "$VAULT/02 Areas"`, `ls "$VAULT/03 Resources"`).
2. Pick the narrowest existing directory that owns the topic.
3. If the intended directory does not exist, **ask the user where to create it** — do not write into a non-existent path.
4. Update the nearest MOC/index after creating a new durable note.

### Common scenario: AsiaInfo / 内部系统A operations

Release and operations work for 内部系统A (deployment, server paths, package movement, Docker restart, FastAPI backend release, H5/admin frontend release) historically lived at `02 Areas/客户X/03 内部系统A/`.

> ⚠️ **As of 2026-09-11 that directory does not exist — `02 Areas/` is empty.** Probe first; if no matching area exists, tell the user the historical path is gone and ask where the notes should live before creating anything.

## Weekly Release Note

When the task includes release preparation or release-relevant changes, maintain one weekly release note in the most relevant project or area folder.

Default naming:

`发版 - <系统或项目名> - YYYY-Www.md`

Examples: `01 Projects/<项目名>/发版 - <项目名> - 2026-W18.md` or `02 Areas/<领域>/<子主题>/发版 - <系统或项目名> - 2026-W18.md`.

Use ISO week numbering unless the user provides a different release naming convention. If a note for the current week already exists, update it instead of creating another. Probe the parent folder before writing; if it does not exist, ask the user where the release note should live.

## Weekly Release Note Template

Read `references/release-note-template.md` and use its structure unless a nearby existing note has a stronger local convention.

Keep release notes short. Put full scripts or config snippets under `04 发布依赖清单`, but avoid turning the note into a detailed runbook unless the user asks for operational depth.

## Update Workflow

1. Identify the task outcome.
   - Summarize what actually changed or was decided.
   - Separate landed facts from guesses, options, and abandoned attempts.

2. Choose note destinations.
   - Update an existing project/area/resource note first when one already owns the topic.
   - Create the weekly release note only when release-relevant details exist.
   - Update the nearest MOC when a new durable note is created.

3. Write the smallest durable update that stays operational.
   - Compact bullets for work logs; command blocks only when future execution needs exact commands.
   - Explain non-obvious flags, config fields, paths, and ordering assumptions.
   - Record what to run, where, what it affects, and how to verify it.
   - Include skipped validation explicitly, plus backup and rollback steps for release notes when known.

4. Verify link and structure integrity.
   - Ensure new notes are linked from the nearest MOC or parent note.
   - Avoid duplicating the same release instructions in multiple places; cross-link instead.

5. Report back briefly — keep the handoff short; the value is in the notes.
   - Which notes were created or updated.
   - What landed points were recorded.
   - Whether a weekly release note was created or updated.
   - Any assumptions, skipped validation, or missing release details.

## Writing Style

Write like an operations memory, not a diary:

- direct, factual, and easy to scan
- Chinese-first, with English technical terms where they are canonical
- no coaching language such as "第一次", "可以先这样理解", or "接下来我们"
- no inflated summaries; prefer exact commands, paths, and constraints
- no secrets

## Installation

Install via the repo-root `npx skills add huangrx6/agent-skills` (see repo-root [README.md](../../README.md)).

**Install `obsidian-personal-knowledge-base` first** — this skill depends on its `references/vault-map.md` and `references/writing-conventions.md`, and refuses to write when they are unavailable.
