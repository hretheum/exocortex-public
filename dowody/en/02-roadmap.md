---
id: roadmap
lang: en
counterpart: ../pl/02-roadmap.md
provenance: ai_authored
provenance_metadata:
  agent: Claude Opus 5.5 (Cowork)
  date: 2026-09-27
  human_validated: false
---

# Roadmap

The plan for building the cycle described in [How the evidence cycle works](01-cycle.md). Phases are listed in the order they have to be done. Experiments start in phase F3, once the lab from phase F2 works.

## Rules for all phases

The lab does not use client material. It is not used as data, as examples, or as a source of quotes and names. If a problem resembles something known from professional work, we recreate it on public or generated data and do not say where the idea came from.

Everything the lab produces is public as it happens: code, documentation, this roadmap with the state of tasks, hypothesis cards, results. The repository shows the current state at any moment. This rule does not cover client projects, which stay private and never enter the lab.

Every document is written in Polish and in English in the same commit. Code, comments, docstrings, program messages and commit messages are in English only.

Only container images run on the server, started by Quadlet under rootless Podman. Source code from the repository does not go to the server. Images are built and checked by the gate in CI.

Documents are written so that someone from outside the project can follow them. The publishing gate also checks the text for habits typical of language models.

## How documents are split

Each level has a size limit. Past that limit the content moves to separate files and the level above keeps a short teaser with a link.

| Level | Limit | Contents |
|---|---|---|
| Main document (this one) | about 150 lines | rules, the splitting rule, each phase in a few sentences with a link |
| Phase document | about 200 lines | goal of the phase, condition for finishing it, list of tasks |
| Task document | 25 to 80 lines | one atomic task |

Tasks are described directly in the phase document if there are at most five of them and each fits in a dozen or so lines. Otherwise every task gets its own file, and the phase document holds a table with one sentence per task, its dependencies and a link.

A task is atomic if one person does it in one sitting, at most one working day, and it has one checkable condition for being done. A description longer than 80 lines means the task has to be split. The exception is serial tasks, where the same procedure is repeated over a list of units, for example folder by folder. They have one file with the procedure and a checklist, and each item on the list is atomic.

The limits come from reading time. About 150 to 200 lines take a few to a dozen or so minutes to read, without losing the thread and without scrolling around for context. A task file should be readable in full right before starting the work.

Phases F4 to F7 are broken down to the task level inside the phase documents, without separate files. Their shape depends on what comes out of F3, so detailed files will be written after the second gate of the first experiment.

## Phases

Preparatory work on the publishing infrastructure is run separately and is not described here.

[F2. The lab and the record of the cycle](roadmap/F2-lab.md). A separate lab database with no access to private data, an allowlist of sources, handling of hypothesis cards and gate decisions, experiment tables, and result pages published with everything else.

[F3. First full pass through the cycle](roadmap/F3-first-pass.md). One experiment from hypothesis card to report, on a public corpus of Polish official documents. It repeats the method of extracting claims from text that was developed earlier in Exocortex, this time on data anyone can download.

[F4. Reference project card from the graph](roadmap/F4-reference-card.md). A card compiler that takes content only from recorded results, plus checks on the card text for numbers without a source and for plans described as facts.

[F5. Opportunity radar and further experiments](roadmap/F5-radar-and-experiments.md). A weekly pass over public sources, new channels (open-weight models, research papers, open data) and further hypotheses, including a measurement of whether the graph actually improves retrieval.

[F6. Scale and collaboration](roadmap/F6-scale-and-collaboration.md). Access for a second expert, rented compute for public data, scale L documents, a lab site on lab.exocortex.zone and archiving releases with a DOI.

[F7. Public demo: a knowledge base built from research](roadmap/F7-public-demo.md). A demo for product teams and researchers: the engine reads research reports and data, extracts findings with quotes, links them across studies and keeps a list of hypotheses nobody has tested yet. It should show what an organisational knowledge base fed with one's own research would look like. It can run in parallel with F4 to F6, after F3.

[F8. The interactive lab: applications, questions and GraphRAG](roadmap/F8-interactive-lab.md). Every hypothesis gets a section on business applications, the public can ask a question that becomes a derived hypothesis in the queue after a testability assessment, and the graph can be queried in natural language with citations. The applications section comes first, and the question interface needs a decision on hosting, because GitHub Pages does not run code.

## Where we start

State on 29 September: the repository is public, the lab has its database, queue and first cards, and the site lab.exocortex.zone is published. The first experiment waits for the owner to approve the hypothesis card ([F3.4](roadmap/F3/F3.4-hypothesis-card.md)). The business applications section on the hypothesis page (F8.1) is in progress, followed by public questions (F8.6 to F8.9) and the GraphRAG interface (F8.2 to F8.5) from phase F8.

## Task status

Every task file has `status` (`todo`, `doing`, `done`), `depends_on` and `estimate` in its header. A page summarising the state of all tasks will be generated automatically as part of [F2.7](roadmap/F2/F2.7-compile-domain.md). Until then the state is read from the file headers, and the course of the work is described in the [Progress](03-progress.md) log.
