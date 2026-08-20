# Design system

The target is **technical clarity with Excalidraw character**, not a dense enterprise poster.

## Composition

- Use 16:9-ish or moderately wide canvases for architecture and sequence diagrams.
- Prefer 6-14 primary nodes per view. Above ~20 nodes, consider ELK or split views.
- Maintain large outer margins and visible separation between groups.
- Keep labels short. Put explanations outside the diagram or in a note node.
- Group by ownership/trust/deployment/data boundary, not merely by package folder.

## Semantic color

The compiler uses a restrained palette:
- user/client: cool blue
- service/API: green/blue
- database/state: violet
- cache: orange
- event/queue: amber
- security: pink/red accent
- external: neutral gray

Use color consistently within a diagram. Never encode more than ~6 semantic categories by color.

## Icons

Preferred order:
1. Lucide generic icons for common concepts.
2. Simple Icons for products/brands when brand identity is relevant.
3. Installed Excalidraw library items for cloud/vendor architecture symbols or custom team notation.

Rules:
- One icon per node is usually enough.
- Keep icons monochrome or low-saturation unless a brand logo needs its identity.
- Do not mix three unrelated icon styles in the same view.
- For executive diagrams, icons can replace secondary text; for diagnostic diagrams, labels remain primary.

## Typography

- Default to CJK-safe normal text (font family 2 in native Excalidraw scenes).
- Title: 28-32 px.
- Group label: 18-20 px.
- Node title: 16-18 px.
- Supporting text/edge label: 12-14 px.
- Avoid long paragraphs inside boxes.

## Edges

- primary sync call: solid arrow
- async/event: dashed arrow
- data/storage: solid arrow, optionally labelled with data object
- optional/conditional: dashed or lighter stroke
- avoid bidirectional arrows unless the relationship is genuinely symmetric

Prefer orthogonal routes for architecture/dataflow; use straight/rounded arrows for simple flows.

## Anti-patterns

- one box per source file
- rainbow palettes
- edge labels longer than a short phrase
- arrows crossing through node interiors
- tiny text used to fit more content
- every object inside a container
- brand logos where generic semantic icons are clearer
