---
name: developer-readme-design
description: Design, rewrite, or review GitHub READMEs for developer tooling, CLI, SDK, runtime, infrastructure, agent extensions, plugin suites, and monorepos. Use when a README should feel modern, restrained, technical, spacious, consistent, and production-grade rather than like a personal toolbox, emoji-heavy list, or SaaS landing page.
license: MIT
compatibility: GitHub Markdown; optimized for Pi Coding Agent and Agent Skills-compatible harnesses.
metadata:
  category: documentation
  style: developer-tooling
  version: "1.0.0"
---

# Developer README Design

Use this skill to turn a repository README into a mature developer-tooling landing page with strong information architecture and a restrained visual system.

## Core aesthetic

Target this design language:

- monochrome
- restrained
- technical
- spacious
- consistent
- developer-first
- infrastructure / CLI / SDK / runtime quality

Avoid:

- emoji as the primary icon system
- badge walls
- colorful marketing sections
- “personal toolbox” / Awesome List aesthetics
- excessive ASCII art
- SaaS landing-page copy
- repetitive feature lists
- invented claims, benchmarks, compatibility, or installation steps

## Required workflow

### 1. Inspect before rewriting

Before changing content, inspect the available repository material when tools allow it:

- current `README.md`
- repository tree
- package / extension manifests
- install commands
- package names and component boundaries
- existing assets
- docs / contributing files
- CI and release metadata when relevant

Treat repository content as authoritative. Do not invent facts to make the README look better.

If the user only provided README text and no repository access, work strictly from that material and clearly avoid unsupported claims.

### 2. Diagnose information architecture

Identify only material problems, such as:

- unclear first screen
- duplicated sections
- too many badges
- excessive installation detail before value proposition
- components listed without meaningful grouping
- architecture hidden in prose
- detailed reference material occupying the root README
- inconsistent visual language

Do not produce criticism for its own sake.

### 3. Choose the page structure

Default to:

1. Hero
2. Why / Core Value
3. Components / Packages / Extensions
4. Quick Start
5. Architecture
6. Usage
7. Alternative Installation / Configuration
8. Development
9. Documentation / Contributing
10. License

Adapt this ordering to the project. Remove sections that add no new information.

### 4. Design the Hero

The first screen should answer within seconds:

1. What is this?
2. Why would a developer use it?
3. How do I start?

Prefer:

- project logo
- project name
- precise one-line tagline
- one short supporting sentence
- 2–4 restrained badges maximum
- primary install / start command
- a few navigation links only if useful

Do not put the full feature catalog, project history, or every CI workflow in the Hero.

### 5. Build a coherent component system

If the project has natural layers, make those layers part of the visual language.

Examples:

- `MODEL`
- `TOOL`
- `RUNTIME`
- `STORAGE`
- `DISPLAY`
- `CLI`
- `SDK`
- `CORE`

Prefer concise component descriptions based on behavior rather than marketing claims.

Do not use emoji as a permanent icon system. If icons are useful, recommend or create consistent SVG icons instead.

### 6. Keep GitHub rendering constraints in mind

Use Markdown as the primary format.

Small amounts of GitHub-safe HTML are acceptable for:

- centered Hero content
- `<picture>` / `<source>` / `<img>`
- `<details>` / `<summary>`
- simple tables

Do not rely on:

- JavaScript
- `<style>`
- external CSS
- CSS classes / IDs for layout
- complex inline styling

Use SVG files for visual identity, icons, diagrams, and other elements that genuinely need design.

### 7. Use SVG intentionally

When visual assets would materially improve the README, use or recommend:

```text
assets/
├── logo.svg
├── logo-dark.svg
├── architecture.svg
└── icons/
    ├── component-a.svg
    └── component-b.svg
```

SVG design principles:

- geometric
- simple
- mostly monochrome
- consistent stroke / viewBox
- readable at small sizes
- no unnecessary illustration
- works on GitHub light and dark themes

If components are intentionally independent, an architecture diagram may intentionally omit connecting arrows.

### 8. Make Quick Start genuinely quick

The recommended installation path should normally be one short code block plus one next step.

Put secondary installation methods, platform notes, advanced configuration, troubleshooting, and migration details under `<details>` or in dedicated docs when appropriate.

### 9. Remove duplication

Each major fact should be explained once.

If a later section repeats the component list, replace it with new value such as workflow-oriented combinations:

```text
Safer execution
component-a + component-b

Long-running sessions
component-c + component-d

Terminal UX
component-e + component-f
```

### 10. Write like developer infrastructure

Prefer precise operational copy.

Prefer:

> Routes tasks through quick, standard, or strict workflows.

Over:

> A powerful next-generation workflow engine that supercharges productivity.

Avoid unsupported superlatives such as “ultimate”, “revolutionary”, “blazing fast”, or “best-in-class”.

### 11. Keep the root README focused

The root README is an entry point, not a complete reference manual.

Move detailed material to package READMEs or `docs/` when appropriate.

A good root README should be understandable by scanning for 1–3 minutes and usable after a 5–10 minute read.

### 12. Review before finishing

Load and apply [references/quality-checklist.md](references/quality-checklist.md) before finalizing.

For the complete visual and structural specification, consult [references/style-guide.md](references/style-guide.md).

## Editing behavior

When the user asks to **rewrite / redesign / improve** a README and repository editing is available:

1. inspect the project;
2. directly update `README.md`;
3. create SVG assets only when they materially improve the page;
4. preserve factual correctness;
5. keep links and commands valid;
6. summarize the important changes after editing.

When the user asks only for **review /方案 /建议**, do not modify files; return the prioritized design plan.

When the user explicitly asks for a **README only**, do not create unrelated project files.

## Input template

If project requirements are unclear, use [assets/project-brief-template.md](assets/project-brief-template.md) as an internal checklist. Do not force the user to fill every field when repository inspection can answer them.
