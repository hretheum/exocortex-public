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
| [F0](../roadmap/F0-leaks-and-gate.md) | 7 | 5 | 2 | 0 |
| [F1](../roadmap/F1-public-repo.md) | 10 | 6 | 4 | 0 |
| [F2](../roadmap/F2-lab.md) | 8 | 5 | 1 | 2 |
| [F3](../roadmap/F3-first-pass.md) | 10 | 4 | 1 | 5 |
| [F4](../roadmap/F4-reference-card.md) | 4 | 0 | 0 | 4 |
| [F5](../roadmap/F5-radar-and-experiments.md) | 7 | 1 | 0 | 6 |
| [F6](../roadmap/F6-scale-and-collaboration.md) | 6 | 0 | 0 | 6 |
| [F7](../roadmap/F7-public-demo.md) | 6 | 0 | 0 | 6 |

## F0. Stopping leaks and the publishing gate

| Id | Task | Status | Depends on | Waits for |
|---|---|---|---|---|
| [F0.1](../roadmap/F0/F0.1-close-leaking-channels.md) | Turn off public access to artifacts made before the rules | in progress | — | — |
| [F0.2](../roadmap/F0/F0.2-exposure-audit.md) | List and check every public place | done | F0.1 | — |
| [F0.3](../roadmap/F0/F0.3-denylist.md) | List of forbidden names and its hashed version | done | F0.2 | — |
| [F0.4](../roadmap/F0/F0.4-scanner-text-and-files.md) | Text and file scanner | done | F0.3 | — |
| [F0.5](../roadmap/F0/F0.5-scanner-build-artifacts.md) | Package and container image scanner | done | F0.4 | — |
| [F0.6](../roadmap/F0/F0.6-similarity-check.md) | Comparison with the private corpus | done | F0.4 | — |
| [F0.7](../roadmap/F0/F0.7-gate-self-test.md) | Nightly gate test | in progress | F0.4, F0.5, F0.6 | — |

## F1. Public repository and continuous publishing

| Id | Task | Status | Depends on | Waits for |
|---|---|---|---|---|
| [F1.1](../roadmap/F1/F1.1-repo-shape-decision.md) | How the public repository is created | done | F0 | — |
| [F1.2](../roadmap/F1/F1.2-create-repos.md) | Rename the current repository and create the new one | in progress | F1.1 | — |
| [F1.3](../roadmap/F1/F1.3-clean-export.md) | Export the code through an allowlist of paths | done | F1.2 | — |
| [F1.4](../roadmap/F1/F1.4-code-to-english-tool.md) | Tool for translating comments and docstrings | done | F1.3 | — |
| [F1.5](../roadmap/F1/F1.5-code-to-english-review.md) | Translation folder by folder | done | F1.4 | — |
| [F1.6](../roadmap/F1/F1.6-clean-builds.md) | Image and package from the clean repository | in progress | F1.3, F0.5 | — |
| [F1.7](../roadmap/F1/F1.7-bilingual-convention.md) | Bilingual convention and parity check | done | F1.2 | — |
| [F1.8](../roadmap/F1/F1.8-human-language-lint.md) | Checking text for language model habits | done | F1.7 | — |
| [F1.9](../roadmap/F1/F1.9-continuous-publisher.md) | Publisher | in progress | F0.7, F1.7, F1.8 | F0.7 |
| [F1.10](../roadmap/F1/F1.10-first-publication.md) | First publication and fixing links | in progress | F1.9 | F1.9 |

## F2. The lab and the record of the cycle

| Id | Task | Status | Depends on | Waits for |
|---|---|---|---|---|
| [F2.1](../roadmap/F2/F2.1-lab-database.md) | Separate database and processes for the lab | done | F1 | — |
| [F2.2](../roadmap/F2/F2.2-source-allowlist.md) | Allowlist of sources | done | F2.1 | — |
| [F2.3](../roadmap/F2/F2.3-schemas-and-templates.md) | Header schemas and final templates | done | F1.7 | — |
| [F2.4](../roadmap/F2/F2.4-hypothesis-processor.md) | Handling hypothesis cards and preregistration | in progress | F2.2, F2.3 | — |
| [F2.5](../roadmap/F2/F2.5-gate-processor.md) | Handling gate decisions | done | F2.4 | — |
| [F2.6](../roadmap/F2/F2.6-experiment-tables.md) | Experiment tables and the control set lock | done | F2.1 | — |
| [F2.7](../roadmap/F2/F2.7-compile-domain.md) | Result pages and roadmap state | to do | F2.4, F2.5, F2.6 | F2.4 |
| [F2.8](../roadmap/F2/F2.8-results-export.md) | Raw results export | to do | F2.6 | — |

## F3. First full pass through the cycle

| Id | Task | Status | Depends on | Waits for |
|---|---|---|---|---|
| [F3.1](../roadmap/F3/F3.1-public-corpus-selection.md) | Choosing a public corpus | done | F2.2 | — |
| [F3.2](../roadmap/F3/F3.2-corpus-manifest.md) | Downloading the corpus and the manifest | done | F3.1 | — |
| [F3.3](../roadmap/F3/F3.3-extractor-port.md) | Claim extractor in the lab | done | F2.6 | — |
| [F3.4](../roadmap/F3/F3.4-hypothesis-card.md) | Hypothesis card and preregistration | in progress | F3.2, F3.3, F2.4 | F2.4 |
| [F3.5](../roadmap/F3/F3.5-blind-sample-tool.md) | Blind sample and rating | done | F2.6 | — |
| [F3.6](../roadmap/F3/F3.6-tier-s-and-g1.md) | Quick test and gate G1 | to do | F3.4, F3.5 | F3.4 |
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
| [F5.1](../roadmap/F5-radar-and-experiments.md) | Opportunity radar | to do (described in the phase document) | F2, F3 | F2, F3 |
| [F5.2](../roadmap/F5-radar-and-experiments.md) | New source channels | done (described in the phase document) | F2 | — |
| [F5.3](../roadmap/F5-radar-and-experiments.md) | Selecting candidates with scoring by several models | to do (described in the phase document) | F5 | F5 |
| [F5.4](../roadmap/F5-radar-and-experiments.md) | Monthly measurement of new models | to do (described in the phase document) | F3 | F3 |
| [F5.5](../roadmap/F5-radar-and-experiments.md) | Experiment: does the graph improve retrieval | to do (described in the phase document) | F3, F5 | F3, F5 |
| [F5.6](../roadmap/F5-radar-and-experiments.md) | Experiment: local embedding model versus a cloud model | to do (described in the phase document) | F5 | F5 |
| [F5.7](../roadmap/F5-radar-and-experiments.md) | Experiment: forcing the answer format | to do (described in the phase document) | F3 | F3 |

## F6. Scale and collaboration

| Id | Task | Status | Depends on | Waits for |
|---|---|---|---|---|
| [F6.1](../roadmap/F6-scale-and-collaboration.md) | Second expert | to do (described in the phase document) | F3 | F3 |
| [F6.2](../roadmap/F6-scale-and-collaboration.md) | Compute on demand | to do (described in the phase document) | F2 | F2 |
| [F6.3](../roadmap/F6-scale-and-collaboration.md) | Scale L documents | to do (described in the phase document) | F3 | F3 |
| [F6.4](../roadmap/F6-scale-and-collaboration.md) | Lab website | to do (described in the phase document) | F2 | F2 |
| [F6.5](../roadmap/F6-scale-and-collaboration.md) | Releases with DOIs | to do (described in the phase document) | F1 | F1 |
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
