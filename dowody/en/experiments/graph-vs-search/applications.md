---
id: graph-vs-search-applications
lang: en
counterpart: ../../../pl/experiments/graph-vs-search/applications.md
type: applications
slug: graph-vs-search
label: hypothesis, no evidence
source_hash: 93c3d9725815d2425ffc4ebdb5b99c08030caf427fab7ee109c58abf6faa5fa0
publish: true
human_validated: true
provenance: ai_authored
provenance_metadata:
  agent: qwen3.6-35b-a3b (lab model gateway), exocortex lab applications
  date: '2026-09-29'
---

# Business applications: Graph and search

The experiment is planned and has not measured anything yet. Below we describe which decisions its result could support and which it could not.

## Applications

| Application | Who uses it | Result it rests on | Strength of evidence | Conditions and limits |
|---|---|---|---|---|
| Choosing the search method for a company document base | a team that builds or maintains search over documents | [results in the dossier](overview.md#s-results) | hypothesis, no evidence | nDCG@10 decides, on one public corpus and one hand-made set of questions. Without a result there is no reason to change the method. |
| Deciding which types of links in the graph to use in search | a product team and a solution architect | [results in the dossier](overview.md#s-results) | hypothesis, no evidence | Applies only to the link types used in the study. The result says nothing about other types. |

## If we confirm, if we refute

- If we confirm: expanding results along the graph gives a higher nDCG@10 than embeddings alone. Then it is worth considering as the default method for similar corpora, with the link types that do not help switched off.
- If we refute: embeddings alone are enough and there is no reason to add graph expansion to search.

## What not to conclude from this

- The result concerns one public corpus and one hand-made set of questions. We do not carry it over to other data without a separate check.
- The experiment measures the quality of results. It does not measure cost, response time or the effort of maintaining the graph.

## What to check next

- Repeat the measurement on a second corpus before anyone bases a rollout decision on the result.
- After the hypothesis card is frozen and the first run is done, generate this page again, because the result will change.
