---
id: F2
lang: en
counterpart: ../../pl/roadmap/F2-lab.md
status: doing
provenance: ai_authored
provenance_metadata: {agent: "Claude Opus 5.5 (Cowork)", date: 2026-09-27, human_validated: false}
---

# F2. The lab and the record of the cycle

[← Roadmap](../02-roadmap.md)

## Goal

A separate Exocortex instance that accepts only allowed sources and has no access to anything private. We teach it to understand hypothesis cards and gate decisions, to record experiments and their results, and then to assemble result pages that the publisher sends to the repository together with everything else.

## The phase is done when

- a test shows that lab processes cannot connect to the private database,
- an approved hypothesis card in `dowody/` appears in the lab graph with a checksum, and in the repository with a preregistration record,
- a sample experiment goes through the queue, its results are in the tables, and a dossier page and raw data are in the repository,
- a page with the state of all roadmap tasks is generated automatically.

## Tasks

| Id | Task | Depends on | Estimate |
|---|---|---|---|
| [F2.1](F2/F2.1-lab-database.md) | Separate database and processes for the lab | – | 4 h |
| [F2.2](F2/F2.2-source-allowlist.md) | Allowlist of sources | F2.1 | 4 h |
| [F2.3](F2/F2.3-schemas-and-templates.md) | Header schemas and final templates | – | 4 h |
| [F2.4](F2/F2.4-hypothesis-processor.md) | Handling hypothesis cards and preregistration | F2.2, F2.3 | 1 day |
| [F2.5](F2/F2.5-gate-processor.md) | Handling gate decisions | F2.4 | 4 h |
| [F2.6](F2/F2.6-experiment-tables.md) | Experiment tables and the control set lock | F2.1 | 1 day |
| [F2.7](F2/F2.7-compile-domain.md) | Result pages and roadmap state | F2.4, F2.5, F2.6 | 1 day |
| [F2.8](F2/F2.8-results-export.md) | Raw results export | F2.6 | 4 h |
| [F2.9](F2/F2.9-on-demand-jobs.md) | Lab jobs on demand | F2.6 | 4 h |
| [F2.10](F2/F2.10-blind-rating-interface.md) | Blind rating in the owner's interface | F2.6, F3.5 | 1 day |
