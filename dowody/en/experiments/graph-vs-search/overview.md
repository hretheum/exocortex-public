---
id: graph-vs-search-overview
lang: en
counterpart: ../../../pl/experiments/graph-vs-search/overview.md
status: planned
roadmap: F5.5
stage: 0
tier: S
tagline: "Do connections improve results."
updated: 2026-09-28
provenance: ai_authored
provenance_metadata:
  agent: Claude Sonnet 5.5 (Cowork)
  date: 2026-09-28
  human_validated: false
---

# Graph and search

## Abstract

Text search usually relies on embeddings, numerical descriptions of the meaning of a sentence. We will test whether expanding results along the connections in a knowledge graph improves their quality, and which types of connection help and which hurt. The experiment is planned and nothing has been measured yet.

## Question and hypothesis

The question: does search that additionally expands results along the edges of the graph give better results than search by embeddings alone, and do all types of edge help equally. The hypothesis and the threshold will be set in the hypothesis card.

## Preregistration

There is no hypothesis card. The card will be frozen and published before the first measurement.

## Data

A public corpus and a hand-made set of questions with gold answers are planned. The sources will go on the allowlist with a reason and a legal basis.

## Method

A comparison of search by embeddings alone with search that expands results along the edges of the graph, and a comparison of edge types. The deciding metric will be nDCG@10. The experiment depends on the first experiment (F3) being finished and on the selection of candidates (F5.3).

## Runs

No runs yet. The first run will appear once the hypothesis card is frozen. Every run gets a note: model, variant, parameters, code commit, result and anything that went wrong or looked odd.

## Results

No results yet. We publish results on the day they are produced, negative ones too, with confidence intervals and a link to the raw data.

## Gate decisions

No decision has been made yet. Gate G1 comes after the quick test and G2 after the pilot. Every decision is published together with the results it rests on.

## Deviations and change log

| Date | Version | Change |
|---|---|---|
| 2026-09-28 | 0.1 | Dossier of a planned experiment created. |

## How to reproduce

Not applicable until there are runs.

## Limitations

We will write the limitations in the hypothesis card. It is already known that the result will concern one corpus and one hand-made set of questions.

## References

None.
