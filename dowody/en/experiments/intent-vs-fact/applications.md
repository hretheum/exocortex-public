---
id: intent-vs-fact-applications
lang: en
counterpart: ../../../pl/experiments/intent-vs-fact/applications.md
type: applications
slug: intent-vs-fact
label: hypothesis, no evidence
source_hash: 52502ecffcb3841e2aa6689f11d722406d9fa2cb3095cd58cb7265f574483400
publish: true
human_validated: true
provenance: ai_authored
provenance_metadata:
  agent: Claude Sonnet 5.5 (Cowork), text written by hand through exocortex lab applications
  date: '2026-09-29'
---

# Business applications: Intent or fact

Helps a team decide whether a summarising tool needs an extra "fact or plan" field, so that it does not present intentions as finished work.

## Applications

| Application | Who uses it | Result it rests on | Strength of evidence | Conditions and limits |
|---|---|---|---|---|
| Risk and compliance: judging whether summaries written by a model can be trusted | the people responsible for quality and compliance | [results in the dossier](overview.md#s-results) | hypothesis, no evidence | The result concerns English scientific abstracts and specific local models. Without a result there is no reason to assume that a model tells a plan from a fact. |
| Tool choice: deciding whether to add a required "fact or plan" field to claim extraction | a team that builds such a tool | [results in the dossier](overview.md#s-results) | hypothesis, no evidence | Applies to one way of recording this information and to two local models. The result says nothing about other ways. |
| Research organisation: checking your own summaries for intent turned into fact | a team that prepares summaries for others | [results in the dossier](overview.md#s-results) | hypothesis, no evidence | We check our own lab's summaries. We do not carry the conclusion over to summaries from other systems. |

## If we confirm, if we refute

- If we confirm: adding one field to the form means plans are mistaken for finished work less often. A team can make the field standard and check summaries for it.
- If we refute: the field alone does not help. A team does not spend time rolling it out and limits the risk of mixing plan and fact in another way, for example by checking a sample by hand.

## What not to conclude from this

- The corpus is abstracts of arXiv papers. We do not carry the result over to other kinds of text, such as contracts, messages or company reports.
- The experiment measures mistakes between plan and fact. It does not measure cost or processing time.
- The hypothesis card is not frozen yet, so the threshold and the way of rating may still change.

## What to check next

- Freeze the hypothesis card and make the first measurement.
- After the card is frozen and the first run is done, generate this page again, because the result will change.

## For the technically minded: details

- If we confirm: in the blind human-rated sample the share of claims with a swapped mode is lower with the mode field than without it by more than the threshold in the hypothesis card, and both guard metrics stay within their thresholds.
- If we refute: the difference between the variants is smaller than the threshold in the card, or the confidence interval includes zero (H0).
