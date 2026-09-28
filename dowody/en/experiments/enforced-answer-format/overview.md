---
id: enforced-answer-format-overview
lang: en
counterpart: ../../../pl/experiments/enforced-answer-format/overview.md
status: planned
roadmap: F5.7
stage: 0
tier: S
tagline: "Does structure end prose answers."
updated: 2026-09-28
provenance: ai_authored
provenance_metadata:
  agent: Claude Sonnet 5.5 (Cowork)
  date: 2026-09-28
  human_validated: false
---

# Enforced answer format

## Abstract

Sometimes a model replies in prose where a program expects a tool call. We will test whether forcing the structure of the answer with a grammar eliminates such cases and whether it harms the quality of claims. The experiment is planned and nothing has been measured yet.

## Question and hypothesis

The question: does forcing the structure of the answer with a grammar (a JSON schema, a GBNF grammar in llama.cpp) eliminate the cases where the model replies in prose instead of calling a tool. The hypothesis and the threshold will be set in the hypothesis card.

## Preregistration

There is no hypothesis card. The card will be frozen and published before the first measurement.

## Data

Data from the first experiment (F3): the public corpus of abstracts and the configurations of local models.

## Method

A comparison of answers with and without the enforced structure. The deciding metric will be the share of answers that conform to the schema, and the guard metric the quality of claims. The experiment depends on the first experiment (F3).

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

We will write the limitations in the hypothesis card. It is already known that the result will concern specific local models and specific software for running them.

## References

None.
