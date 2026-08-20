# ER diagrams

Use entity cards. Put the entity name first and only the fields needed to explain the relationship.

Node example:
```json
{
  "id": "user",
  "label": "iam_user",
  "kind": "database",
  "fields": [
    "PK id bigint",
    "account varchar(64)",
    "role_id bigint FK"
  ]
}
```

Edges should use relationship/cardinality labels only when they add value. Do not dump every column from a large schema unless explicitly asked.
