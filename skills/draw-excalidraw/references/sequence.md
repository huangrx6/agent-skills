# Sequence diagrams

Use when temporal interaction is the main question.

Semantic shape:
```json
{
  "type": "sequence",
  "participants": [
    {"id":"web","label":"Web","kind":"client"},
    {"id":"auth","label":"Auth Service","kind":"service"}
  ],
  "messages": [
    {"from":"web","to":"auth","label":"POST /login"},
    {"from":"auth","to":"web","label":"token","kind":"return"}
  ]
}
```

Use notes sparingly. Prefer 4-8 participants per view. Split long protocols by phase when needed.
