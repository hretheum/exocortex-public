---
id: intent-vs-fact-applications
lang: en
counterpart: ../../../pl/experiments/intent-vs-fact/applications.md
type: applications
slug: intent-vs-fact
label: hypothesis, no evidence
source_hash: f82d368d0efe327e0cfae3eb759569f1ed1818a69b0306af54099eef069cddf0
publish: true
human_validated: true
provenance: ai_authored
provenance_metadata:
  agent: qwen3.6-35b-a3b (lab model gateway), exocortex lab applications
  date: '2026-09-29'
---

# Business applications: Intent or fact

The organisation can decide whether to enforce labelling sentences as fact or intent during information extraction to avoid misleading summaries.

## Applications

| Application | Who uses it | Result it rests on | Strength of evidence | Conditions and limits |
|---|---|---|---|---|
| Risk and compliance: The legal and compliance team uses the tool to verify that reports do not present plans as accomplished facts, which could mislead stakeholders. | Legal and compliance team | [results in the dossier](overview.md#s-results) | hypothesis, no evidence | The tool must clearly distinguish the sentence mode to prevent interpretive errors in regulatory documents. |
| Product design: The product designer can change the search results display interface to separate factual statements from research goals and hypotheses. | Product designer | [results in the dossier](overview.md#s-results) | hypothesis, no evidence | The feature must preserve the distinction across languages, as summaries are generated in a different language than the original. |
| Tool choice: The technical team can choose a claim extractor with a mandatory mode field if high information reliability is required in critical workflows. | Technical team | [results in the dossier](overview.md#s-results) | hypothesis, no evidence | The decision relies on whether adding the mode field reduces the share of incorrect transformations of intent into fact. |

## If we confirm, if we refute

- If we confirm: If the hypothesis is confirmed, the organisation can deploy the extractor with a mode field to production to improve information reliability and compliance with reporting requirements.
- If we refute: If the hypothesis is refuted, the organisation should not invest in modifying the extraction schema for a mode field, as it will not bring the expected quality improvement.

## What not to conclude from this

- One cannot conclude that the method detects the completeness of extracted claims or interpretation errors with correct quotes.
- The results do not apply to the entire arXiv dataset, but only to documents downloaded by the lab engine during a specific period.
- One cannot assess agreement between different raters, as only one person currently provides the rating.

## What to check next

- Check whether adding a mode field to the extraction schema actually reduces the number of claims presenting plans as facts.
- Verify whether the automatic judge from a different model family correctly catches errors and does not generate false alarms in this task.

## For the technically minded: details

- If we confirm: The difference between the variant with the mode field and without it exceeds the threshold written in the hypothesis card, and the confidence interval does not include zero.
- If we refute: The difference between the variant with the mode field and without it is smaller than the threshold written in the hypothesis card, or the confidence interval includes zero.
