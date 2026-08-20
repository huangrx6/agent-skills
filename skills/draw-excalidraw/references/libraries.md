# Excalidraw libraries

Excalidraw has a public `.excalidrawlib` ecosystem. This skill does **not** bundle the whole ecosystem.
Instead it maintains a local library directory and can synchronize the official catalog on demand.

## Why optional libraries

- many library items are domain/vendor specific
- some cloud/vendor marks have separate trademark/license conditions
- loading thousands of components makes routing noisier
- a small curated local set produces better diagrams

## Commands

```bash
# fetch/refresh public catalog metadata
node .../scripts/draw.mjs library sync

# search catalog metadata
node .../scripts/draw.mjs library search "AWS"

# download one library by catalog id
node .../scripts/draw.mjs library install <id>

# search items in installed .excalidrawlib files
node .../scripts/draw.mjs library items "lambda"
```

You may also copy your own `.excalidrawlib` files into:
- `libraries/user/`
- or `libraries/official/`

## In semantic specs

Use:
```json
"icon": { "provider": "library", "name": "lambda" }
```

Library item search uses the library item name, text inside the item, and library filename. If an item contains unsupported embedded image files that are not present in the library data, the compiler will skip that item and fall back to a generic icon.

Keep a consistent visual language: do not mix AWS hand-drawn library items, Lucide line icons, and multiple unrelated vendor packs unless the diagram genuinely needs them.
