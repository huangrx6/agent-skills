# Architecture diagrams

Model boundaries and responsibilities before implementation details.

Recommended semantic fields:
- node `kind`: `user`, `client`, `api`, `service`, `security`, `database`, `cache`, `queue`, `external`, `worker`, `gateway`
- node `group`: ownership/deployment/trust boundary
- edge `kind`: `call`, `async`, `data`, `dependency`

Prefer layers such as client -> edge/gateway -> application -> state/external systems when the system actually follows them.
Do not invent layers merely for symmetry.

For repository analysis, identify real entry points, cross-module calls, persistence, caches/queues, external integrations, and major configuration boundaries.
