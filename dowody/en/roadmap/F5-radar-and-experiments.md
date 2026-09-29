---
id: F5
lang: en
counterpart: ../../pl/roadmap/F5-radar-and-experiments.md
status: doing
task_status: {F5.1: doing, F5.2: done, F5.3: done}
provenance: ai_authored
provenance_metadata: {agent: "Claude Opus 5.5 (Cowork)", date: 2026-09-27, human_validated: false}
---

# F5. Opportunity radar and further experiments

[← Roadmap](../02-roadmap.md)

## Goal

The cycle starts suggesting experiment candidates from public sources on its own, and we run further experiments, each along the same path as in F3.

The tasks are described here, without separate files. Each of the experiments F5.5 to F5.7 will get its own folder with a hypothesis card and its own task list when we get to it.

## The phase is done when

The radar has run weekly for at least a month, and at least two further experiments have published G1 decisions.

## Tasks

### F5.1. Opportunity radar

A weekly list of candidates from the lab graph: claims in hypothesis mode, unresolved contradictions, dense topic clusters without a synthesis, sudden rises in topic frequency. Each candidate with a link to its source, duplicates removed by embedding similarity. The page is published in both languages. Done when the radar has run four weeks in a row. Depends on F2 and F3.3.

### F5.2. New source channels

Research papers from arXiv (cs.CL, cs.IR, cs.AI, cs.LG, with a topic filter), releases of open-weight models, public open data (for example the dane.gov.pl portal), releases of tools we use. Each channel as an adapter through the Capture API and an allowlist entry with its basis for use. Done when all four channels feed the lab graph. Depends on F2.2.

### F5.3. Selecting candidates with scoring by several models

Five knock-out questions and a scoring sheet (template in `templates/`). The first scoring is done independently by models from three different families; a difference of at least two points in any dimension marks a candidate for more thought. The person's decision is recorded as a G0 gate decision. Done when ten candidates from the radar have been through scoring. Depends on F5.1.

### F5.4. Monthly measurement of new models

The fixed measurement bench from F3 run every month for new local models. The result is a public comparison table over time, and at the same time continuous, repeatable evidence of research work. Done when three consecutive months have published results. Depends on F3.

### F5.5. Experiment: does the graph improve retrieval

A comparison of retrieval with embeddings alone against retrieval that also expands results along graph edges, plus a comparison of the edge types that help against those that hurt. Public corpus, a question set with gold answers prepared by hand. Deciding metric nDCG@10. Done when the G1 decision is published. Depends on F3 and F5.3.

### F5.6. Experiment: local embedding model versus a cloud model

Does the local embedding model give retrieval results no worse than a cloud model on a Polish public corpus. An equivalence hypothesis with a threshold written in the card. Requests to the cloud model only with public texts. Done when the G1 decision is published. Depends on F5.5.

### F5.7. Experiment: forcing the answer format

Does forcing the answer structure with a grammar (json_schema, GBNF in llama.cpp) eliminate cases where the model answers in prose instead of a tool call. Metric: share of answers that match the schema; guard metric: claim quality. Done when the G1 decision is published. Depends on F3.

## Progress

- 2026-09-29: F5.2. Four channels feed the lab graph: new arXiv papers in cs.CL, cs.IR, cs.AI and cs.LG on the lab's topics, open-weight models from Hugging Face, new data sets from dane.gov.pl, and releases of the tools the lab uses (GitHub). Every channel is on the list of allowed sources with a basis for use checked at the source, and only metadata and abstracts are stored. Downloads go through a separate gateway that accepts only https addresses from that list and keeps pauses between requests; the isolation check tests it every night. First download on the server: 200 papers, 50 models, 50 data sets and 12 releases, without errors. The radar job runs the channels every week.
- 2026-09-29: F5.1. The radar runs: a weekly job (Sunday 22:30) downloads the channels, runs the extractor on new papers and compiles the [radar page](../generated/radar.md) in Polish and English. Week 2026-W39: 198 papers, 287 hypotheses and plans after removing repeats, one possible contradiction, one dense topic, 17 new models, data sets and releases. Sudden rises are not computed yet, as there are not four weeks before. The radar skips papers from experiment corpora and items the gate would hold as personal data (one in week 2026-W40). The done condition is four weeks in a row.
- 2026-09-29: F5.3. Ten candidates from the radar of week 2026-W39 went through scoring by models of three families (qwen3.6, gemma-4, gpt-oss), each on its own, with the selection template. Eight have valid answers from all three models, two scorings lack a valid answer from one model. A spread of at least two points in some dimension occurred for eight candidates, and four failed some knock-out question in the scoring of at least one model. The owner makes the G0 decisions. The gate held the radar page for 2026-W39 and the scoring as similar to protected material; they are waiting for review.
