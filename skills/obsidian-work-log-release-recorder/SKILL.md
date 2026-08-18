---
name: obsidian-work-log-release-recorder
description: Use this skill after completing a coding task, deployment task, configuration adjustment, database/script change, release preparation, or meaningful project update when the user wants durable notes in Huangrx6's Obsidian vault. It records only landed, reusable, or release-relevant facts into the correct Project/Area/Resource location and maintains a weekly release note with scripts, configs, deployment paths, validation, rollback, and execution assumptions. Use it whenever the user says to record, summarize, settle,沉淀, 更新知识库, 记到 Obsidian, 写发版文档, or after a task has produced operational knowledge worth keeping. This skill is bound to Huangrx6's specific vault path /Users/huangrx6/Documents/obsidian; cross-machine reuse is limited.
---

# Obsidian Work Log And Release Recorder

This skill turns completed work into durable Obsidian notes. It is intentionally selective: the goal is not to preserve the chat transcript, but to keep the small set of facts that will help the next implementation, release, rollback, or handoff.

## Prerequisites（机器 binding）

This skill is bound to a specific machine and Obsidian vault:

- vault path must be `/Users/huangrx6/Documents/obsidian`
- depends on `obsidian-personal-knowledge-base` skill for vault structure conventions (`references/vault-map.md`, `references/writing-conventions.md`)
- **cross-machine reuse is limited**: switching machines or vault paths requires re-aligning references

## Scope

Use this skill with the Obsidian vault at:

`/Users/huangrx6/Documents/obsidian`

Use the existing `obsidian-personal-knowledge-base` skill conventions when writing in that vault:

- read `references/vault-map.md` before choosing a location if the destination is not obvious
- read `references/writing-conventions.md` before creating or heavily editing notes
- reuse the nearest existing project, area, resource note, MOC, or template rather than inventing a parallel structure

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

Do not record:

- raw conversation
- every file touched when only a summary matters
- failed experiments unless they prevent future mistakes
- trivial formatting, typo fixes, or local-only noise
- secrets, tokens, passwords, private keys, cookies, or full credentials
- speculative plans that were not accepted or implemented

If a detail looks sensitive but operationally important, record the variable or config name and location, not the secret value.

## Location Decision

Choose the narrowest stable home:

- Outcome-driven work with a finish line goes under `01 Projects/<project>/`.
- Long-running responsibilities, delivery systems, or operations knowledge goes under `02 Areas/<area>/`.
- Reusable technical knowledge goes under `03 Resources/<topic>/`.
- Unclear or incomplete capture goes under `00 Inbox/`, but only when there is not enough context to classify safely.

For Huangrx6's current work, the common default for AsiaInfo delivery and release operations is:

- `02 Areas/亚信/00 MOC - 亚信项目与运维.md`
- `02 Areas/亚信/03 灵犀助手/资源笔记 - 灵犀助手部署与发布.md`

Prefer updating those notes when the work is about 灵犀助手 deployment, release, server paths, package movement, Docker restart, FastAPI backend release, H5/admin frontend release, or related operational scripts.

## Weekly Release Note

When the task includes release preparation or release-relevant changes, maintain one weekly release note in the most relevant project or area folder.

Default naming:

`发版 - <系统或项目名> - YYYY-Www.md`

Examples:

- `02 Areas/亚信/03 灵犀助手/发版 - 灵犀助手 - 2026-W18.md`
- `01 Projects/<项目名>/发版 - <项目名> - 2026-W18.md`

Use ISO week numbering unless the user provides a different release naming convention. If a note for the current week already exists, update it instead of creating another.

## Weekly Release Note Template

Use this structure unless a nearby existing note has a stronger local convention:

````markdown
---
type: review
status: active
area:
project:
created: YYYY-MM-DD
tags:
  - 发版
---

# 发版 - <系统或项目名> - YYYY-Www

敬畏每一行代码，敬畏每一次变更。通过结构化、可验证、可回溯的方式，降低发布风险，保障系统稳定。

## 01 基本信息

| 项目 | 内容 |
| --- | --- |
| 发布名称 |  |
| 发布类型 | 常规发布 |
| 发布时间 | 待确认 |
| 发布申请人 | 待确认 |
| 核心协同成员 | 运维 - 待确认；开发 - 待确认；测试 - 待确认 |

## 02 版本内容

| 需求类型 | 需求详情 |
| --- | --- |
| 新增 |  |
| 优化 |  |
| 修改 |  |

## 03 变更影响

| 分类 | 是否涉及 |
| --- | --- |
| 数据库变更 |  |
| 服务端配置变更 |  |
| 服务端代码变更 |  |
| H5 前端代码变更 |  |
| PC 前端代码变更 |  |
| 运营侧前端代码变更 |  |

## 04 发布依赖清单

| 分类 | 内容 |
| --- | --- |
| SQL 脚本 |  |
| YML 配置 |  |
| Nginx 配置 |  |

## 05 发布服务清单

| 服务分类 | 服务名称 | 服务描述 |
| --- | --- | --- |
| 前端 |  |  |
| 后端 |  |  |

## 06 发布执行步骤

注意：

- 上传相关打包文件到内网主机。
- 部署前先行备份原来的服务包。
- SQL 执行前备份相关表或数据库。
- 配置文件修改前备份相关配置文件。

执行步骤：

1. 
````

Keep release notes short. Put full scripts or config snippets under `04 发布依赖清单`, but avoid turning the note into a detailed runbook unless the user asks for operational depth.

## Update Workflow

1. Identify the task outcome.
   - Summarize what actually changed or was decided.
   - Separate landed facts from guesses, options, and abandoned attempts.

2. Choose note destinations.
   - Update an existing project/area/resource note first when one already owns the topic.
   - Create the weekly release note only when release-relevant details exist.
   - Update the nearest MOC when a new durable note is created.

3. Write the smallest durable update.
   - Add compact bullets for work logs.
   - Add command blocks only when future execution needs exact commands.
   - Explain non-obvious command flags, config fields, paths, and ordering assumptions.

4. Preserve operational usefulness.
   - Record what to run, where to run it, what it affects, and how to verify it.
   - Include skipped validation explicitly when relevant.
   - Include backup and rollback steps for release notes whenever they are known.

5. Verify link and structure integrity.
   - Ensure new notes are linked from the nearest MOC or parent note.
   - Avoid duplicating the same release instructions in multiple places; cross-link instead.

## Writing Style

Write like an operations memory, not a diary:

- direct, factual, and easy to scan
- Chinese-first, with English technical terms where they are canonical
- no coaching language such as "第一次", "可以先这样理解", or "接下来我们"
- no inflated summaries; prefer exact commands, paths, and constraints
- no secrets

## Output To User

After updating the vault, report:

- which Obsidian notes were created or updated
- what landed points were recorded
- whether a weekly release note was created or updated
- any assumptions, skipped validation, or missing release details

Keep the handoff short. The value is in the notes.

## Installation

Install via the repo-root `npx skills add huangrx6/agent-skills` (see repo-root [README.md](../../README.md)). After installing:

1. Confirm your vault path matches `/Users/huangrx6/Documents/obsidian`
2. Install `obsidian-personal-knowledge-base` first if not already installed — this skill depends on its `references/vault-map.md` and `references/writing-conventions.md`
3. Agent will read both skills' references when triggered to write release notes
