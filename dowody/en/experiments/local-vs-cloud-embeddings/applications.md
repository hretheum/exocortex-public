---
id: local-vs-cloud-embeddings-applications
lang: en
counterpart: ../../../pl/experiments/local-vs-cloud-embeddings/applications.md
type: applications
slug: local-vs-cloud-embeddings
label: hypothesis, no evidence
source_hash: 022624d5f3cd02bc6880acb2a4f4a8f83bf187ce93a4aeb4b00cf6dae19d24e6
publish: true
human_validated: true
provenance: ai_authored
provenance_metadata:
  agent: qwen3.6-35b-a3b (lab model gateway), exocortex lab applications
  date: '2026-09-29'
---

# Business applications: Local or cloud model

Helps a team decide whether a model run in-house is enough for searching Polish documents, or whether to stay with a cloud one.

## Applications

| Application | Who uses it | Result it rests on | Strength of evidence | Conditions and limits |
|---|---|---|---|---|
| Choosing the embedding model for search over Polish documents | a team that chooses or changes the embedding model in a search system | [results in the dossier](overview.md#s-results) | hypothesis, no evidence | The decision rests on comparing both models on the same questions and the same set of public Polish documents, with a tolerance set before the measurement. Applies only to the models that were checked. |
| Deciding whether embeddings can be computed on your own hardware | the IT department and the people responsible for data | [results in the dossier](overview.md#s-results) | hypothesis, no evidence | Needs two things at once: quality must not be worse by more than the agreed tolerance, and the model must run on the target hardware in a reasonable time. Cloud models change without notice, so the result describes the versions used in the study. |

## If we confirm, if we refute

- If we confirm: the model run in-house is good enough to replace the cloud one for documents like these. A team can consider it instead of the cloud one, and a separate feasibility test still decides about the hardware.
- If we refute: the model run in-house does noticeably worse. For documents like these a team stays with the cloud model.

## What not to conclude from this

- The result concerns specific models and one public Polish corpus. We do not carry it over to other models or other data.
- The experiment measures search quality and technical feasibility on one machine. It does not measure cost or how stable a cloud model is over time.
- An "inconclusive" result (the interval includes the threshold) means the sample was too small. We do not treat it as a refutation.

## What to check next

- Repeat the measurement on a second corpus before anyone bases a rollout decision on the result.
- After the hypothesis card is frozen and the first run is done, generate this page again, because the result will change.

## For the technically minded: details

- If we confirm: the local model is not worse than the cloud one by more than the frozen threshold. Then it is a credible alternative to the cloud one on a corpus of a similar kind, and a separate feasibility measurement still decides about your own hardware.
- If we refute: the local model is worse than the cloud one by more than the frozen threshold. For this task we stay with the cloud model.
