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

> **Status: in progress** · as of September 30, 2026
>
> 9 of 10 tasks are done and 1 is in progress: F2.4 (handling hypothesis cards and preregistration). The lab runs on the server: it has its own database walled off from private data, an allowlist of sources, experiment tables, processors for cards and decisions, results export, jobs on demand and blind rating. To close F2.4, and with it the phase, the path on the files of the test card `toy-length` is missing, and that card waits for the owner's approval. According to the entry in F2.7, the dossier (the full description) of the toy experiment, a trial experiment used to check the lab's mechanisms, was held by the publication gate (the automatic check before publishing) and also waits for the owner's review.

## In short

Phase F2 builds the lab: a separate, walled-off place on the server where the system accepts only allowed public material, records hypotheses before testing them, runs experiments and assembles the results into pages that can be read. The lab has no access to anything private. Without it, the later phases would have nowhere to run and nothing to publish.

## Why this phase

The later phases of the plan (the roadmap) run experiments, and everything that comes out of them is public. That needs a place that cannot leak anything private, even by mistake, and that records when each hypothesis was written, which success thresholds were chosen and what came out. Without this phase there would be neither a safe place to work nor a record that an outside reader can check.

## Goal

A separate Exocortex instance (our system that turns texts into a network of links between claims) that accepts only allowed sources and has no access to anything private. We teach it to understand hypothesis cards and gate decisions (checkpoints where a person chooses the next step), to record experiments and their results, and then to assemble result pages that the publisher, a program that sends files to the public repository, sends together with everything else.

## The phase is done when

- a test shows that lab processes cannot connect to the private database,
- an approved hypothesis card in `dowody/` appears in the lab graph with a checksum (a short fingerprint of the content), and in the repository with a preregistration record (the hypothesis and success thresholds written down before the measurement),
- a sample experiment goes through the queue, its results are in the tables, and a dossier page (the full description of the experiment) and raw data are in the repository,
- a page with the state of all roadmap tasks is generated automatically.

## Tasks

| Id | Task | Status | Depends on | Estimate |
|---|---|---|---|---|
| [F2.1](F2/F2.1-lab-database.md) | Separate database and processes for the lab | done | – | 4 h |
| [F2.2](F2/F2.2-source-allowlist.md) | Allowlist of sources | done | F2.1 | 4 h |
| [F2.3](F2/F2.3-schemas-and-templates.md) | Header schemas and final templates | done | – | 4 h |
| [F2.4](F2/F2.4-hypothesis-processor.md) | Handling hypothesis cards and preregistration | in progress | F2.2, F2.3 | 1 day |
| [F2.5](F2/F2.5-gate-processor.md) | Handling gate decisions | done | F2.4 | 4 h |
| [F2.6](F2/F2.6-experiment-tables.md) | Experiment tables and the control set lock | done | F2.1 | 1 day |
| [F2.7](F2/F2.7-compile-domain.md) | Result pages and roadmap state | done | F2.4, F2.5, F2.6 | 1 day |
| [F2.8](F2/F2.8-results-export.md) | Raw results export | done | F2.6 | 4 h |
| [F2.9](F2/F2.9-on-demand-jobs.md) | Lab jobs on demand | done | F2.6 | 4 h |
| [F2.10](F2/F2.10-blind-rating-interface.md) | Blind rating in the owner's interface | done | F2.6, F3.5 | 1 day |
| [F2.11](F2/F2.11-desk-counters-and-tiles.md) | Desk: counters and tiles instead of tables | done | F2.10 | 4 h |
