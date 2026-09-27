---
provenance: ai_authored
provenance_metadata:
  agent: claude-opus-4.7
  session_date: 2026-05-24
  human_validated: false
  session_context: "F31.9.4 — hello-world quickstart fixture (single note)"
title: Cypher quick notes
date: 2026-05-23
type: quick_note
---

I learned today that Cypher MATCH clauses can chain through edge types
(e.g., `MATCH (a)-[:contradicts]->(b)`). Apache AGE supports this within
Postgres, which is interesting because it lets me use vector and graph
queries against the same table. The downside is AGE 1.6 lags behind the
official Neo4j Cypher spec — no `CALL { ... }` subqueries, no list
comprehensions, no procedural extensions beyond the built-ins.

The takeaway: AGE is good enough for relationship traversal driven by
typed edges (which is the bulk of GraphRAG retrieval), but you cannot
just paste arbitrary Cypher from a Neo4j tutorial and expect it to run.
