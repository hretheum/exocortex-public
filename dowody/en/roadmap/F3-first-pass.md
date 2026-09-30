---
id: F3
lang: en
counterpart: ../../pl/roadmap/F3-first-pass.md
status: doing
provenance: ai_authored
provenance_metadata: {agent: "Claude Opus 5.5 (Cowork)", date: 2026-09-28, human_validated: false}
---

# F3. First full pass through the cycle

[← Roadmap](../02-roadmap.md)

> **Status: in progress** · as of 30 September 2026
>
> 5 of 10 tasks are done (F3.1 to F3.5): the corpus, the set of documents to study, is downloaded and described, the claim extractor works in the lab, the tool for blind rating is checked, and the hypothesis card is frozen. The quick test (F3.6) is in progress: on 30 September the extraction on the tuning sample finished without errors, and the blind rating page waits for the rater. Tasks F3.7 to F3.10 wait for the result of F3.6 and the decision of gate G1.

## In brief

The lab's first experiment tests whether a program that pulls single claims out of a text tells facts apart from plans and suppositions. If it does not, a plan goes on as something already done. We work on about 2500 abstracts (short summaries written by the authors) of scientific papers from arXiv, and on the Polish summaries of these papers written by our engine, the Exocortex program that builds a knowledge graph from documents. Every step, from the hypothesis card to the report, is public.

## Why this phase

A lab makes sense only once it is visible that the whole cycle works from start to finish: from posing a question, through a measurement, to a report that an outsider can check. Instead of building tools in advance, we run one real experiment and note what breaks along the way. The topic matters in practice: when a program summarises a company's plan as something already done, the reader draws wrong conclusions and makes decisions on them. Without this phase the lab would be a set of tools that nobody knows work together.

## Goal

One experiment taken through the whole cycle, from hypothesis card to report, entirely in public view. We chose a topic for which Exocortex already has tools: extracting claims from documents together with whether a sentence describes a fact, a plan, a requirement or a hypothesis. A common mistake of language models is to describe intentions as things already done, and strategy and planning documents are full of intentions.

The corpus (the set of documents we work on) is the abstracts of the arXiv papers, under the CC0 licence, that Exocortex has already downloaded (about 2,500), together with the Polish summaries of these papers written by the engine. In abstracts, facts (what was measured) sit next to hypotheses and announcements (what we propose, what may work), which makes them well suited to this measurement. The summaries add a second question, about our own way of processing texts: whether an intention or a hypothesis turns into a fact when it is summarised. The corpus is at hand, so we do not wait for new documents to be collected. Polish official documents, planned here earlier, remain a candidate for a later experiment.

This experiment is also a test of all the publishing and lab tools. Where something does not work, we fix the tools and record the fix in the experiment log.

## The phase is done when

- the hypothesis card is frozen and published before the first measurement,
- the G1 and (if reached) G2 gate decisions are published together with the results they rest on,
- the report in both languages, the raw data and a script for recomputing the results are in the repository,
- an outsider with nothing but the repository can download the corpus, run the recomputation and get the same numbers.

## Tasks

| Id | Task | Status | Depends on | Estimate |
|---|---|---|---|---|
| [F3.1](F3/F3.1-public-corpus-selection.md) | Choosing a public corpus and checking the legal basis | done | F2.2 | 4 h |
| [F3.2](F3/F3.2-corpus-manifest.md) | Downloading the corpus and the manifest | done | F3.1 | 4 h |
| [F3.3](F3/F3.3-extractor-port.md) | Moving the claim extractor into the lab | done | F2.6 | 1 day |
| [F3.4](F3/F3.4-hypothesis-card.md) | Hypothesis card and preregistration | done | F3.2, F3.3, F2.4 | 2 h |
| [F3.5](F3/F3.5-blind-sample-tool.md) | Tool for blind samples and rating | done | F2.6 | 4 h |
| [F3.6](F3/F3.6-tier-s-and-g1.md) | Quick test and gate G1 | in progress | F3.4, F3.5, F2.9, F2.10 | 1 day |
| [F3.7](F3/F3.7-tier-m-runs.md) | Pilot: configuration matrix | to do | F3.6 (GO) | 1 day |
| [F3.8](F3/F3.8-tier-m-labeling-and-taxonomy.md) | Pilot: rating the blind sample and the error list | to do | F3.7 | 1 day |
| [F3.9](F3/F3.9-judge-calibration.md) | Pilot: calibrating the automatic judge | to do | F3.8 | 4 h |
| [F3.10](F3/F3.10-g2-and-report.md) | Gate G2 and report | to do | F3.8, F3.9 | 4 h |

If G1 ends with a decision other than `GO`, tasks F3.7 to F3.9 are dropped and F3.10 writes the report on the quick test result.
