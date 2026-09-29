---
id: generated-roadmap-status
lang: en
counterpart: ../../pl/generated/roadmap-status.md
generated: true
---

# Roadmap status

This page is built automatically in the lab from the headers of the task files (task [F2.7](../roadmap/F2/F2.7-compile-domain.md)). It is not edited by hand: the status changes in the task file.

| Phase | Tasks | Done | In progress | To do |
|---|---|---|---|---|
| [F2](../roadmap/F2-lab.md) | 10 | 9 | 1 | 0 |
| [F3](../roadmap/F3-first-pass.md) | 10 | 5 | 0 | 5 |
| [F4](../roadmap/F4-reference-card.md) | 4 | 0 | 0 | 4 |
| [F5](../roadmap/F5-radar-and-experiments.md) | 9 | 2 | 1 | 6 |
| [F6](../roadmap/F6-scale-and-collaboration.md) | 6 | 0 | 1 | 5 |
| [F7](../roadmap/F7-public-demo.md) | 6 | 0 | 0 | 6 |
| [F8](../roadmap/F8-interactive-lab.md) | 10 | 1 | 2 | 7 |

## F2. The lab and the record of the cycle

| Id | Task | Status | Depends on | Waits for |
|---|---|---|---|---|
| [F2.1](../roadmap/F2/F2.1-lab-database.md) | Separate database and processes for the lab | done | — | — |
| [F2.2](../roadmap/F2/F2.2-source-allowlist.md) | Allowlist of sources | done | F2.1 | — |
| [F2.3](../roadmap/F2/F2.3-schemas-and-templates.md) | Header schemas and final templates | done | — | — |
| [F2.4](../roadmap/F2/F2.4-hypothesis-processor.md) | Handling hypothesis cards and preregistration | in progress | F2.2, F2.3 | — |
| [F2.5](../roadmap/F2/F2.5-gate-processor.md) | Handling gate decisions | done | F2.4 | — |
| [F2.6](../roadmap/F2/F2.6-experiment-tables.md) | Experiment tables and the control set lock | done | F2.1 | — |
| [F2.7](../roadmap/F2/F2.7-compile-domain.md) | Result pages and roadmap state | done | F2.4, F2.5, F2.6 | — |
| [F2.8](../roadmap/F2/F2.8-results-export.md) | Raw results export | done | F2.6 | — |
| [F2.9](../roadmap/F2/F2.9-on-demand-jobs.md) | Lab jobs on demand | done | F2.6 | — |
| [F2.10](../roadmap/F2/F2.10-blind-rating-interface.md) | Blind rating in the owner's interface | done | F2.6, F3.5 | — |

## F3. First full pass through the cycle

| Id | Task | Status | Depends on | Waits for |
|---|---|---|---|---|
| [F3.1](../roadmap/F3/F3.1-public-corpus-selection.md) | Choosing a public corpus | done | F2.2 | — |
| [F3.2](../roadmap/F3/F3.2-corpus-manifest.md) | Downloading the corpus and the manifest | done | F3.1 | — |
| [F3.3](../roadmap/F3/F3.3-extractor-port.md) | Claim extractor in the lab | done | F2.6 | — |
| [F3.4](../roadmap/F3/F3.4-hypothesis-card.md) | Hypothesis card and preregistration | done | F3.2, F3.3, F2.4 | — |
| [F3.5](../roadmap/F3/F3.5-blind-sample-tool.md) | Blind sample and rating | done | F2.6 | — |
| [F3.6](../roadmap/F3/F3.6-tier-s-and-g1.md) | Quick test and gate G1 | to do | F3.4, F3.5, F2.9, F2.10 | — |
| [F3.7](../roadmap/F3/F3.7-tier-m-runs.md) | Pilot: configuration matrix | to do | F3.6 | F3.6 |
| [F3.8](../roadmap/F3/F3.8-tier-m-labeling-and-taxonomy.md) | Pilot: rating the blind sample and the error list | to do | F3.7 | F3.7 |
| [F3.9](../roadmap/F3/F3.9-judge-calibration.md) | Pilot: calibrating the automatic judge | to do | F3.8 | F3.8 |
| [F3.10](../roadmap/F3/F3.10-g2-and-report.md) | Gate G2 and report | to do | F3.8, F3.9 | F3.8, F3.9 |

## F4. Reference project card from the graph

| Id | Task | Status | Depends on | Waits for |
|---|---|---|---|---|
| [F4.1](../roadmap/F4-reference-card.md) | General card model | to do (described in the phase document) | F2 | F2 |
| [F4.2](../roadmap/F4-reference-card.md) | Card compiler | to do (described in the phase document) | F4 | F4 |
| [F4.3](../roadmap/F4-reference-card.md) | Honesty check for the card text | to do (described in the phase document) | F4 | F4 |
| [F4.4](../roadmap/F4-reference-card.md) | Filling in tender forms | to do (described in the phase document) | F4 | F4 |

## F5. Opportunity radar and further experiments

| Id | Task | Status | Depends on | Waits for |
|---|---|---|---|---|
| [F5.1](../roadmap/F5-radar-and-experiments.md) | Opportunity radar | in progress (described in the phase document) | F2, F3 | F2, F3 |
| [F5.2](../roadmap/F5-radar-and-experiments.md) | New source channels | done (described in the phase document) | F2 | — |
| [F5.3](../roadmap/F5-radar-and-experiments.md) | Selecting candidates with scoring by several models | done (described in the phase document) | F5 | — |
| [F5.4](../roadmap/F5-radar-and-experiments.md) | Monthly measurement of new models | to do (described in the phase document) | F3 | F3 |
| [F5.5](../roadmap/F5-radar-and-experiments.md) | Experiment: does the graph improve retrieval | to do (described in the phase document) | F3, F5 | F3, F5 |
| [F5.6](../roadmap/F5-radar-and-experiments.md) | Experiment: local embedding model versus a cloud model | to do (described in the phase document) | F5 | F5 |
| [F5.7](../roadmap/F5-radar-and-experiments.md) | Experiment: forcing the answer format | to do (described in the phase document) | F3, F5 | F3, F5 |
| [F5.8](../roadmap/F5-radar-and-experiments.md) | Experiment kind: retrieval | to do (described in the phase document) | F2 | F2 |
| [F5.9](../roadmap/F5-radar-and-experiments.md) | Experiment kind: answer format conformity | to do (described in the phase document) | F2 | F2 |

## F6. Scale and collaboration

| Id | Task | Status | Depends on | Waits for |
|---|---|---|---|---|
| [F6.1](../roadmap/F6-scale-and-collaboration.md) | Second expert | to do (described in the phase document) | F3 | F3 |
| [F6.2](../roadmap/F6-scale-and-collaboration.md) | Compute on demand | to do (described in the phase document) | F2 | F2 |
| [F6.3](../roadmap/F6-scale-and-collaboration.md) | Scale L documents | to do (described in the phase document) | F3 | F3 |
| [F6.4](../roadmap/F6-scale-and-collaboration.md) | Lab website | in progress (described in the phase document) | F2 | F2 |
| [F6.5](../roadmap/F6-scale-and-collaboration.md) | Releases with DOIs | to do (described in the phase document) | — | — |
| [F6.6](../roadmap/F6-scale-and-collaboration.md) | Kelter as the runner for agent experiments | to do (described in the phase document) | F2 | F2 |

## F7. Public demo: a knowledge base built from research

| Id | Task | Status | Depends on | Waits for |
|---|---|---|---|---|
| [F7.1](../roadmap/F7-public-demo.md) | Domain, sources and the demo script | to do (described in the phase document) | F3 | F3 |
| [F7.2](../roadmap/F7-public-demo.md) | Research data model | to do (described in the phase document) | F7 | F7 |
| [F7.3](../roadmap/F7-public-demo.md) | Extracting findings and hypotheses from reports | to do (described in the phase document) | F7 | F7 |
| [F7.4](../roadmap/F7-public-demo.md) | Demo interface | to do (described in the phase document) | F7 | F7 |
| [F7.5](../roadmap/F7-public-demo.md) | Test with the audience | to do (described in the phase document) | F7 | F7 |
| [F7.6](../roadmap/F7-public-demo.md) | Guide to feeding it with your own research | to do (described in the phase document) | F7 | F7 |

## F8. The interactive lab: applications, questions and GraphRAG

| Id | Task | Status | Depends on | Waits for |
|---|---|---|---|---|
| [F8.1](../roadmap/F8-interactive-lab.md) | Business applications section | in progress (described in the phase document) | F6 | F6 |
| [F8.2](../roadmap/F8-interactive-lab.md) | Public graph package | in progress (described in the phase document) | F2 | F2 |
| [F8.3](../roadmap/F8-interactive-lab.md) | Question service | to do (described in the phase document) | F8 | F8 |
| [F8.4](../roadmap/F8-interactive-lab.md) | Question interface | to do (described in the phase document) | F8 | F8 |
| [F8.5](../roadmap/F8-interactive-lab.md) | Suggestion tiles | to do (described in the phase document) | F8 | F8 |
| [F8.6](../roadmap/F8-interactive-lab.md) | Public question intake | to do (described in the phase document) | F6 | F6 |
| [F8.7](../roadmap/F8-interactive-lab.md) | Question testability assessment | to do (described in the phase document) | F8 | F8 |
| [F8.8](../roadmap/F8-interactive-lab.md) | Derived hypotheses | to do (described in the phase document) | F8 | F8 |
| [F8.9](../roadmap/F8-interactive-lab.md) | The Questions page and links in the dossier | to do (described in the phase document) | F8 | F8 |
| [F8.10](../roadmap/F8-interactive-lab.md) | Rewriting "How it works" for a business reader | done (described in the phase document) | — | — |
