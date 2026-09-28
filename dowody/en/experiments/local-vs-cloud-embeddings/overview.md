---
id: local-vs-cloud-embeddings-overview
lang: en
counterpart: ../../../pl/experiments/local-vs-cloud-embeddings/overview.md
status: planned
roadmap: F5.6
stage: 0
tier: S
tagline: "Is local as good as cloud."
updated: 2026-09-28
provenance: ai_authored
provenance_metadata:
  agent: Claude Sonnet 5.5 (Cowork)
  date: 2026-09-28
  human_validated: false
---

# Local or cloud model

## Abstract

Text search needs an embedding model. We will test whether a model run locally gives search results no worse than a cloud model on a Polish public corpus. The experiment is planned and nothing has been measured yet.

## Question and hypothesis

The question: is a local embedding model equivalent to a cloud one. This is an equivalence hypothesis: the threshold for an acceptable difference will be written in the hypothesis card before the measurement.

## Preregistration

There is no hypothesis card. The card will be frozen and published before the first measurement.

## Data

A Polish public corpus. We send only public texts to the cloud model. The sources will go on the allowlist with a reason and a legal basis.

## Method

The same queries and the same corpus for both models, a comparison of search quality with confidence intervals and an equivalence test with the threshold from the card. The experiment depends on the previous one (F5.5).

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

We will write the limitations in the hypothesis card. It is already known that the result will concern specific models and one corpus, and that cloud models change without notice.

## References

None.
