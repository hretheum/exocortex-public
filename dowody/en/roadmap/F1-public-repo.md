---
id: F1
lang: en
counterpart: ../../pl/roadmap/F1-public-repo.md
status: doing
provenance: ai_authored
provenance_metadata: {agent: "Claude Opus 5.5 (Cowork)", date: 2026-09-27, human_validated: false}
---

# F1. Public repository and continuous publishing

[← Roadmap](../02-roadmap.md)

## Goal

One public repository that shows the whole mechanism at any moment: the engine and lab code, the documentation, the roadmap with the state of tasks, and the results. It is created from scratch, with a clean history, from an export of the code through an allowlist of paths. The current repository stays private as the place where work on the private instance happens.

Along the way the code gets English comments and docstrings, documents get PL and EN pairs, and a publisher starts running on K12 that moves changes from the vault to the repository through the F0 gate every fifteen minutes.

## The phase is done when

- the repository is public and an anonymous user can see the code, the documents in both languages and the roadmap,
- the container image and the package are built from this repository and pass the scanner before they are pushed,
- a change in the vault shows up in the repository within 30 minutes at the latest, and a file that fails the gate is held with a notification,
- links on exocortex.zone and in the package metadata lead to a working repository.

## Tasks

| Id | Task | Depends on | Estimate |
|---|---|---|---|
| [F1.1](F1/F1.1-repo-shape-decision.md) | Decide how the public repository is created | F0 | 1 h |
| [F1.2](F1/F1.2-create-repos.md) | Rename the current repository and create the new public one | F1.1 | 2 h |
| [F1.3](F1/F1.3-clean-export.md) | Export the code through an allowlist of paths | F1.2 | 1 day |
| [F1.4](F1/F1.4-code-to-english-tool.md) | Tool for translating comments and docstrings | F1.3 | 4 h |
| [F1.5](F1/F1.5-code-to-english-review.md) | Translation folder by folder (serial task) | F1.4 | series, about 1 h per folder |
| [F1.6](F1/F1.6-clean-builds.md) | Build the image and the package from the clean repository | F1.3, F0.5 | 4 h |
| [F1.7](F1/F1.7-bilingual-convention.md) | Bilingual convention, glossary, parity check | F1.2 | 1 day |
| [F1.8](F1/F1.8-human-language-lint.md) | Checking text for language model habits | F1.7 | 4 h |
| [F1.9](F1/F1.9-continuous-publisher.md) | Publisher on K12 | F0.7, F1.7, F1.8 | 1 day |
| [F1.10](F1/F1.10-first-publication.md) | First publication and fixing links | F1.9 | 2 h |
