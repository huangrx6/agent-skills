# draw-excalidraw

A local-first DSH Skill that turns semantic diagram specs into editable Excalidraw files.

## What it is

`draw-excalidraw` is intentionally **not another AI service**. DSH inspects the repository/documents and decides what the diagram means. This package handles layout, styling, icon embedding, Excalidraw serialization, and visual linting locally.

Pipeline:

```text
repository / docs / user intent
          ↓
      DSH model
          ↓
 semantic *.draw.json
          ↓
 draw-excalidraw compiler
   ├─ layout
   ├─ style system
   ├─ icon resolution
   ├─ bindings
   └─ visual lint
          ↓
  *.excalidraw + optional *.svg preview
```

## Install

Linux/macOS:

```bash
./install.sh
```

Windows PowerShell:

```powershell
.\install.ps1
```

Or copy this entire directory to:

```text
~/.dsh/skills/draw-excalidraw
```

and run `npm install --omit=dev` in it.

## Icon strategy

### 1. Lucide — default generic icons

Bundled through `@iconify-json/lucide`. Good for database/server/user/security/cache/queue/etc. They are embedded as SVG images inside the `.excalidraw` file, so the resulting file remains portable.

### 2. Simple Icons — brand/product marks

Bundled through `@iconify-json/simple-icons`. Use only when brand identity matters. The Simple Icons project is CC0, but individual brand/trademark rights can still apply; the skill does not treat a brand icon as permission to use a trademark.

### 3. Excalidraw `.excalidrawlib`

The public Excalidraw library ecosystem is supported as an optional local source. The skill can synchronize catalog metadata, install selected libraries, search local items, and clone vector elements into the output scene.

This is deliberately opt-in: cloud/vendor libraries have their own licensing/trademark considerations and mixing too many visual styles harms readability.

## Example

```bash
node scripts/draw.mjs build \
  --spec examples/architecture.json \
  --out /tmp/architecture.excalidraw \
  --preview /tmp/architecture.svg
```

Open `/tmp/architecture.excalidraw` in Excalidraw or a compatible editor.

## Themes

- `technical`: default, low saturation, engineering docs
- `presentation`: slightly stronger visual hierarchy
- `monochrome`: printing/design-review friendly

## Current deliberate boundaries

- SVG preview is a lightweight structural preview, not pixel-identical to Excalidraw's Rough.js rendering.
- `.excalidrawlib` image-based items are skipped unless they are representable using elements in the library payload; vector element libraries work best.
- The compiler prefers semantic recompile over editing raw native JSON.

## Why semantic specs instead of direct native JSON?

Native Excalidraw labels, text fields and arrow bindings have non-trivial invariants. The compiler generates these details consistently, including separate text elements and bidirectional arrow bindings, instead of asking the LLM to reproduce them every time.
