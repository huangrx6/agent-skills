---
name: draw-excalidraw
description: >-
  Use for drawing or visualizing architecture, flows, call chains, sequence diagrams, ER/data models,
  state machines, dependency maps, deployment topology, mind maps, wireframes, or other technical visuals.
  Generates editable local .excalidraw files directly from repository/document evidence using the DSH model;
  no secondary cloud AI is required. Includes automatic layout, visual linting, Lucide/brand icons, and optional
  Excalidraw library (.excalidrawlib) integration.
whenToUse: >-
  Trigger when the user asks to draw, diagram, visualize, map architecture/dependencies/data flow, create a
  sequence/flow/ER/state/mind-map/wireframe, convert a design explanation into a visual, or modify an existing
  draw-excalidraw semantic source.
---

# draw-excalidraw

Create **editable Excalidraw scenes from evidence**, not from guessed screenshots or decorative prompt art.
The model owns semantic understanding; the local compiler owns coordinates, spacing, icon embedding, bindings,
and scene serialization.

## Hard rules

1. **Evidence before drawing.** For repository diagrams, inspect the relevant code/config/tests first. Do not turn a directory tree into an architecture diagram unless the user explicitly asks for a directory map.
2. **Semantic source first.** Write a compact `*.draw.json` semantic specification, then compile it. Do not hand-author large native Excalidraw JSON.
3. **No second AI.** This skill must not send diagram prompts or repository content to ProcessOn or any other generative service.
4. **Honor host planning/approval rules.** If the current agent is in plan mode and filesystem mutation is disallowed, do not create output files until the host workflow permits execution.
5. **Prefer clarity over density.** A diagram that needs a legend and zooming to read at normal size is usually too detailed. Split views when necessary.
6. **Use icons as semantic anchors, not decoration.** Prefer one icon per important node type. Do not add icons to every box if they increase noise.
7. **Keep the editable source.** Preserve the `*.draw.json` beside the `.excalidraw` so later user changes can be made semantically and recompiled.

## Workflow

### 1. Choose the diagram type

Read `references/routing.md` when the type is not explicit.

Preferred routes:
- architecture / dependency / topology / dataflow -> graph layout
- flowchart / state -> directed graph layout
- sequence -> sequence layout
- ER -> entity layout
- mindmap -> tree layout
- wireframe -> manual/grid layout

### 2. Choose detail level

Use one of:
- `executive`: 4-10 major nodes, minimal labels
- `standard`: default; enough detail for engineering discussion
- `diagnostic`: deeper call/data paths, only when the task requires debugging or implementation detail

Do not use `diagnostic` merely because the repository is large.

### 3. Build a semantic spec

Use `schemas/diagram-spec.schema.json` as the contract. Typical graph specs contain:
- `type`
- `title`
- `theme`
- `direction`
- `groups`
- `nodes`
- `edges`

Each node should encode **meaning**, not drawing coordinates. Prefer stable IDs derived from domain names.

### 4. Apply the visual system

Read `references/design-system.md` for non-trivial diagrams.
Defaults:
- theme: `technical`
- direction: architecture `LR`, workflows `TB`
- low-saturation semantic colors
- normal/CJK-safe text
- elbow/orthogonal edges when helpful
- generous whitespace
- group boundaries only when they communicate ownership/trust/deployment boundaries

### 5. Use icons intelligently

Built-in providers:
- `lucide:<name>` for generic technical concepts (`database`, `server`, `shield-check`, `cloud`, `user`, `box`, etc.)
- `brand:<name>` for well-known brands from Simple Icons
- `library:<query>` for locally installed `.excalidrawlib` items

If the exact icon name is unknown, search locally:

```bash
node "${DSH_HOME:-$HOME/.dsh}/skills/draw-excalidraw/scripts/draw.mjs" icon search "database"
node "${DSH_HOME:-$HOME/.dsh}/skills/draw-excalidraw/scripts/draw.mjs" icon search "kubernetes" --provider brand
```

For Excalidraw libraries, see `references/libraries.md`.

### 6. Compile

```bash
node "${DSH_HOME:-$HOME/.dsh}/skills/draw-excalidraw/scripts/draw.mjs" build \
  --spec docs/iam-architecture.draw.json \
  --out docs/iam-architecture.excalidraw \
  --preview docs/iam-architecture.svg
```

The compiler performs:
- semantic validation
- CJK-aware text sizing/wrapping
- auto-layout (Dagre by default; ELK for larger/compound graphs)
- standard Excalidraw element generation
- arrow/node bindings
- icon embedding
- group backgrounds
- visual linting
- an approximate SVG preview for quick inspection

### 7. Inspect and refine

After compilation, read the lint output. Fix semantic/layout problems in the `*.draw.json`, not in native element JSON.

Common corrections:
- split an overloaded node
- shorten edge labels
- change `direction`
- move a node into a group
- set `layout.engine` to `elk`
- reduce detail
- remove low-value icons

### 8. Modify existing diagrams

Prefer editing the semantic `*.draw.json` and recompiling. Preserve IDs for nodes/edges so future versions stay stable.
If an old `.excalidraw` exists without semantic source, do not reverse-engineer it unless requested; create a new semantic source from the actual system evidence.

## CLI quick reference

```bash
# Environment/dependency check
node .../scripts/draw.mjs doctor

# Build + preview
node .../scripts/draw.mjs build --spec x.draw.json --out x.excalidraw --preview x.svg

# Lint only
node .../scripts/draw.mjs lint --spec x.draw.json

# Search generic/brand icons
node .../scripts/draw.mjs icon search "cache"
node .../scripts/draw.mjs icon search "postgresql" --provider brand

# Excalidraw official library catalog
node .../scripts/draw.mjs library sync
node .../scripts/draw.mjs library search "AWS"
node .../scripts/draw.mjs library install <catalog-id>
node .../scripts/draw.mjs library items "lambda"
```

## Diagram-specific guidance

Load only what is needed:
- `references/architecture.md`
- `references/flowchart.md`
- `references/sequence.md`
- `references/er.md`
- `references/mindmap.md`
- `references/wireframe.md`

Do not load all references for every diagram.
