# draw-excalidraw design

## Goal

Give DSH a high-quality local diagramming capability where the model reasons about the system and a deterministic compiler handles the fragile drawing details.

## Architecture

```text
DSH evidence/reasoning
      ↓
semantic *.draw.json
      ↓
router + detail policy
      ↓
layout engine
  ├─ Dagre (default directed graphs)
  ├─ ELK (large/compound graphs)
  ├─ sequence lanes
  ├─ mind-map tree
  └─ manual/grid
      ↓
visual system
  ├─ semantic colors
  ├─ CJK-aware text metrics
  ├─ icon resolver
  ├─ groups/boundaries
  └─ edge conventions
      ↓
standard Excalidraw scene
      ↓
visual lint + SVG structural preview
```

## Why not direct LLM-native Excalidraw JSON?

Native Excalidraw files contain element version fields, separate text elements, image file records, and bidirectional arrow bindings. Those details are repetitive, easy to get wrong, and waste model tokens. The semantic spec is intentionally much smaller and stable.

## Icon architecture

### Built-in generic icons

Lucide is the default because its line style fits Excalidraw well. Icon SVGs are embedded into the scene as image binary files, so the final `.excalidraw` remains self-contained.

### Brand icons

Simple Icons is available through `brand:<slug>`. Use it only when a product identity is meaningful. Generic infrastructure should normally use Lucide instead.

### Excalidraw libraries

`.excalidrawlib` is treated as a curated local extension layer. The public catalog can be searched and selected libraries downloaded on demand. Library vector elements are cloned, translated, scaled, and ID-remapped into the generated scene.

This lets teams maintain their own architecture icon library without changing the compiler.

## Quality policy

The compiler should make a reasonable diagram even from a minimal spec, but the model remains responsible for semantic correctness. Quality is controlled through:

1. stable semantic node/edge IDs
2. restrained themes
3. auto-layout with whitespace
4. icon defaults by node kind
5. edge style by relationship type
6. node/edge binding generation
7. density and overlap linting
8. optional preview inspection

## Iteration model

Keep `<name>.draw.json` next to `<name>.excalidraw`. For future edits, change the semantic source and rebuild. This avoids raw-scene drift and makes user requests such as "add Kafka between A and B" predictable.
