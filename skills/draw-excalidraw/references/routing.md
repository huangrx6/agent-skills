# Routing

Choose the representation from the relationship being communicated, not from keywords alone.

| Intent | Route | Default direction |
|---|---|---|
| components, ownership, services, dependencies | architecture | LR |
| deployment/runtime topology | topology | LR |
| procedural/business/control flow | flowchart | TB |
| runtime interactions over time | sequence | LR participants / TB time |
| entities, tables, keys, relationships | er | LR |
| states and transitions | state | LR |
| data producers/consumers/transforms | dataflow | LR |
| hierarchy, taxonomy, knowledge decomposition | mindmap | LR/tree |
| UI sketch / screen composition | wireframe | manual/grid |

Decision rules:
1. If the user explicitly names a diagram type, follow it unless technically impossible.
2. If time/order between participants is the main point, use sequence.
3. If persistent entities and relationships are the main point, use ER.
4. If ownership/boundaries/dependencies are the main point, use architecture.
5. If steps/conditions are the main point, use flowchart.
6. If hierarchy rather than flow is the main point, use mindmap.
7. When one diagram would mix multiple mental models, produce separate views rather than a single overloaded canvas.
