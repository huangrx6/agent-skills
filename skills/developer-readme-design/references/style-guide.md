# Developer Tooling README Style Guide

## 1. Design intent

A README should look like the front door of a maintained engineering product, not a decorated Markdown document.

The visual identity should communicate:

- engineering maturity
- predictable behavior
- low cognitive load
- clear product boundaries
- deliberate architecture
- easy onboarding

The README should feel closer to a well-designed CLI / runtime / SDK repository than to a personal collection of scripts.

## 2. Visual language

### Preferred

- monochrome or near-monochrome assets
- restrained neutral badges
- consistent spacing between sections
- short paragraphs
- concise tables
- inline code for component / layer labels
- SVG logo and diagrams
- clear hierarchy

### Avoid

- emoji-led headings
- unique emoji for every package
- rainbow badge rows
- decorative horizontal separators after every section
- giant tables that require horizontal scrolling
- nested bullet lists several levels deep
- fake terminal screenshots when a real command block is clearer
- gratuitous screenshots

## 3. Hero specification

Recommended composition:

```text
                [LOGO]

              project-name

      Precise developer-facing tagline.

Short supporting sentence describing purpose,
audience, and the project's main structural advantage.

       [Build] [License] [Runtime]

    Documentation · Architecture · Packages

$ primary-install-command
```

Hero copy should not duplicate the next section word-for-word.

## 4. Badge policy

Hero: 2–4 maximum.

Preferred badge topics:

- build / CI
- package version if meaningful
- license
- runtime requirement

Move per-package CI badges, lint badges, coverage details, and workflow-specific statuses to Development or dedicated docs.

Use a consistent badge style.

## 5. Component presentation

### Table form

```markdown
|   | Component | Purpose | Layer |
|---|---|---|---|
| icon | `component-a` | Short behavior description | `MODEL` |
| icon | `component-b` | Short behavior description | `TOOL` |
```

### Layered form

```text
MODEL
component-a
component-b

TOOL
component-c

DISPLAY
component-d
component-e
```

Do not describe the same component again in a later “what should I install?” section unless that later section introduces workflow-based combinations.

## 6. Icon system

If icons are used, prefer repository-local SVGs.

Recommended properties:

- `viewBox="0 0 24 24"` for small component icons
- stroke-based or simple filled geometry
- one stroke width
- no embedded raster image
- no embedded font dependency
- no scripts
- no external CSS

Possible icon concepts:

- injection → arrow / bolt / input
- approval → shield / gate
- quota → gauge
- layout → panels
- todo → checklist
- notification → bell
- routing → branch / route
- context → layers / database / memory stack

## 7. Architecture diagrams

Use an architecture SVG when it clarifies structure better than text.

Good architecture diagrams show:

- major layers
- component membership
- direction of data flow only when meaningful
- boundaries between independent packages

Do not put every implementation class, command, or configuration option into the root architecture diagram.

If modules are deliberately uncoupled, use grouping without arrows and state the independence principle beneath the diagram.

## 8. Installation design

The recommended path should dominate visually.

Example:

```markdown
## Quick Start

```bash
pi install git:github.com/owner/repo
```

Restart Pi or run `/reload`.
```

Then:

```html
<details>
<summary>Other installation methods</summary>

...

</details>
```

Do not give three methods equal visual weight when one is recommended.

## 9. README information density

Root README should contain enough information to:

- understand the project
- evaluate fit
- install it
- perform first use
- understand high-level architecture
- find deeper docs

Move the following out when they become long:

- exhaustive environment variable reference
- every debug command
- full migration guides
- detailed API reference
- internal design notes
- exhaustive troubleshooting

## 10. Copywriting rules

Use behavior and constraints, not hype.

Strong examples:

- “Intercepts tool calls before execution and applies approval policy.”
- “Reconstructs todo state from the active session branch.”
- “Stores recoverable context payloads in a local content-addressed archive.”

Weak examples:

- “Powerful and flexible.”
- “The ultimate developer experience.”
- “Makes your workflow amazing.”

## 11. Language

Use the language appropriate for the repository's audience.

Do not randomly alternate Chinese and English within one sentence.

English technical labels such as `MODEL`, `TOOL`, `CLI`, package names, APIs, and commands can remain English in a Chinese README.

## 12. Dark / light mode

Prefer SVGs that work in both themes without requiring CSS.

When separate assets are necessary, use `<picture>` with theme-aware source selection only when GitHub rendering supports the chosen technique.

Keep text out of raster images whenever possible.

## 13. Final target

The resulting README should feel:

- intentionally designed
- quickly scannable
- credible
- technically precise
- visually quiet
- recognizably part of a coherent project
