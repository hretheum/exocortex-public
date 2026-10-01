---
id: F5
lang: en
counterpart: ../../pl/roadmap/F5-radar-and-experiments.md
status: doing
task_status: {F5.1: doing, F5.2: done, F5.3: done, F5.8: done, F5.9: done}
provenance: ai_authored
provenance_metadata: {agent: "Claude Opus 5.5 (Cowork)", date: 2026-09-27, human_validated: false}
---

# F5. Opportunity radar and further experiments

[← Roadmap](../02-roadmap.md)

> **Status: in progress** · as of 30 September 2026
>
> Four of the nine tasks are done (F5.2, F5.3, F5.8, F5.9), one is in progress (F5.1), four are waiting. The lab pulls new content from four channels, and models from three families have scored ten candidates from the radar; the radar has the first full week behind it, out of the four required. The radar pages and the scores wait for the owner's review before publication, and the owner decides which candidates go forward (gate G0). Next: the experiments F5.5 to F5.7, which now have the experiment kinds they need.

## In short

This phase makes the lab suggest ideas for research on its own, instead of only carrying out the ones somebody thought of. Every week it goes through public sources (research papers, new models, open data), points out what is worth testing, and then runs further experiments along the same path as the first one.

## Why this phase

Someone who does research alone tests whatever happens to come to mind, and easily misses changes in the surroundings: a new model, a new paper, a new dataset. The radar turns this into a repeatable weekly pass with links to sources, and leaves the decision about what to study to a person. Decisions are made at decision points called gates: G0 chooses what to study, G1 comes after a quick test, G2 after a larger pilot. Examples of the further experiments: whether retrieval over documents works better when, besides text similarity, it uses the links in the graph (F5.5), and whether local embeddings, that is numerical descriptions of what a text means, match cloud ones, so that texts need not be sent outside the server (F5.6).

## Goal

The cycle starts suggesting experiment candidates from public sources on its own, and we run further experiments, each along the same path as in F3.

The tasks are described here, without separate files. Each of the experiments F5.5 to F5.7 will get its own folder with a hypothesis card and its own task list when we get to it.

## The phase is done when

The radar has run weekly for at least a month, and at least two further experiments have published G1 decisions.

## Tasks

### F5.1. Opportunity radar

**Status: in progress** — the radar runs every week (Sunday 22:30) and has week 2026-W39 behind it (198 papers, 287 hypotheses and plans after removing duplicates, one possible contradiction, one dense topic); four weeks in a row are still needed to close it, and it does not count sudden rises yet, because there are no four weeks of history.

Why: without a regular pass, ideas for research come by chance, and the radar gives a repeatable list of candidates with links to sources.

A weekly list of candidates from the lab graph: claims in hypothesis mode, unresolved contradictions, dense topic clusters without a synthesis, sudden rises in topic frequency. Each candidate with a link to its source, duplicates removed by embedding similarity. The page is published in both languages. Done when the radar has run four weeks in a row. Depends on F2 and F3.3.

### F5.2. New source channels

**Status: done** — four channels feed the graph: arXiv papers (cs.CL, cs.IR, cs.AI, cs.LG), open-weight models from Hugging Face, datasets from dane.gov.pl and releases of the tools we use from GitHub; the first pull gave 200 papers, 50 models, 50 datasets and 12 releases, with no errors.

Why: the radar has something to choose from only when new sources flow into the lab by themselves, each with a checked basis for use.

Research papers from arXiv (cs.CL, cs.IR, cs.AI, cs.LG, with a topic filter), releases of open-weight models, public open data (for example the dane.gov.pl portal), releases of tools we use. Each channel as an adapter through the Capture API (the interface that loads content into the graph) and an allowlist entry with its basis for use. Done when all four channels feed the lab graph. Depends on F2.2.

### F5.3. Selecting candidates with scoring by several models

**Status: done** — ten candidates from the radar (week 2026-W39) were scored separately by models from three families (qwen3.6, gemma-4, gpt-oss); a spread of at least two points appeared for eight candidates, and four dropped out on a screening question for at least one model; the owner's G0 decisions do not exist yet.

Why: when independent models score a candidate differently, it is a sign to think about it longer, and the final decision belongs to a person.

Five knock-out questions and a scoring sheet (template in `templates/`). The first scoring is done independently by models from three different families; a difference of at least two points in any dimension marks a candidate for more thought. The person's decision is recorded as a G0 gate decision. Done when ten candidates from the radar have been through scoring. Depends on F5.1.

### F5.4. Monthly measurement of new models

**Status: to do** — not started; depends on F3, which is in progress.

Why: new models keep coming out and a single measurement soon goes stale; a monthly table shows how results change over time.

The fixed measurement bench from F3 run every month for new local models. The result is a public comparison table over time, and at the same time continuous, repeatable evidence of research work. Done when three consecutive months have published results. Depends on F3.

### F5.5. Experiment: does the graph improve retrieval

**Status: to do** — not started; waits for F3; F5.3 and F5.8 are done.

Why: it answers whether adding links from the graph to retrieval improves the results, or comparing texts alone is enough. The result will also show which link types help and which hurt.

A comparison of retrieval with embeddings alone against retrieval that also expands results along graph edges, plus a comparison of the edge types that help against those that hurt. Public corpus, a question set with gold answers prepared by hand. Deciding metric nDCG@10 (a measure of how high in the top ten results the right answers appear). Done when the G1 decision is published. Depends on F3, F5.3 and F5.8.

### F5.6. Experiment: local embedding model versus a cloud model

**Status: to do** — not started; waits for F5.5; F5.8 is done.

Why: sending texts to the cloud costs money and needs trust; if the local model does no worse, it can be used without that.

Does the local embedding model give retrieval results no worse than a cloud model on a Polish public corpus. An equivalence hypothesis with a threshold written in the card. Requests to the cloud model only with public texts. Done when the G1 decision is published. Depends on F5.5 and F5.8.

### F5.7. Experiment: forcing the answer format

**Status: to do** — not started; waits for F3; F5.9 is done.

Why: a model sometimes answers in prose instead of calling a tool, which breaks the automatic processing of answers; the experiment checks whether an answer format written down in advance removes that.

Does forcing the answer structure with a grammar, that is an answer format written down in advance (json_schema, GBNF in llama.cpp) eliminate cases where the model answers in prose instead of a tool call. Metric: share of answers that match the schema; guard metric: claim quality. Done when the G1 decision is published. Depends on F3 and F5.9.

### F5.8. Experiment kind: retrieval

**Status: done** — the `retrieval` experiment kind works and is in the repository (1 October 2026): a question set with hand-made gold answers, read strictly; retrieval configurations (embeddings alone, expansion along graph edges, chosen edge types, another embedding model through the lab gateway); the metrics nDCG@10, recall@k and MRR with bootstrap intervals and paired differences; result pages and export as for the other kinds. A toy experiment went through the queue on a small corpus (60 jobs) and a separate script reproduced all 36 published numbers. One difference from the description: the gold answers come from hand-prepared files, because the rating page from F2.10 is not wired to this kind yet.

Why: the experiment queue today measures only two kinds, and without a "retrieval" kind experiments F5.5 and F5.6 cannot be run.

The experiment queue today knows the claims kind and the toy kind. Experiments F5.5 and F5.6 measure retrieval, so they need a kind of their own: a question set with gold answers prepared by hand (ratings in the interface from F2.10), retrieval configurations (embeddings alone, embeddings with expansion along graph edges, chosen edge types, another embedding model), the metrics nDCG@10, recall@k and MRR with bootstrap intervals (ranges of uncertainty of the result) over questions, and result pages and export as in F2.7 and F2.8. Done when a toy experiment of this kind goes through the queue on a small corpus and its numbers match an independent calculation. Depends on F2.6, F2.8 and F2.10.

### F5.9. Experiment kind: answer format conformity

**Status: done** — the `format_conformity` experiment kind works and is in the repository (1 October 2026): a strict validator of answers against a written-down schema, the share of conforming answers with Wilson intervals, the difference between configurations, and a reference to the claims experiment for the guard metric (claim quality), which that experiment computes itself. A toy experiment went through the queue and a separate script reproduced all 8 published numbers.

Why: experiment F5.7 measures conformity of answers to a schema mechanically, without a human rating, and the queue does not have such a kind yet.

Experiment F5.7 measures mechanically whether the model's answer matches a schema, with no human rating. It needs an experiment kind with a schema validator, the share of conforming answers with Wilson intervals (ranges of uncertainty of a share) and an explicit link to the claims kind for the guard metric (claim quality). Done when a toy experiment of this kind goes through the queue and the numbers match an independent calculation. Depends on F2.6.

## Progress

- 2026-10-01: F5.8 and F5.9. Two new experiment kinds work. Retrieval (F5.8) ranks documents with a chosen embedding model against hand-made gold answers, optionally expands the ranking along graph edges, and reports nDCG@10, recall@k and MRR with bootstrap intervals and paired differences. Answer format (F5.9) checks mechanically whether an answer matches a written-down schema and reports the share of conforming answers with Wilson intervals. In both, a toy experiment went through the queue and a separate script using only the standard library reproduced every published number (36 and 8). Left for the owner: wiring the rating page from F2.10 as the source of retrieval gold answers, the grade scale and gain in nDCG, and how the grammar mode reaches the model server.
- 2026-09-29: F5.2. Four channels feed the lab graph: new arXiv papers in cs.CL, cs.IR, cs.AI and cs.LG on the lab's topics, open-weight models from Hugging Face, new data sets from dane.gov.pl, and releases of the tools the lab uses (GitHub). Every channel is on the list of allowed sources with a basis for use checked at the source, and only metadata and abstracts are stored. Downloads go through a separate gateway that accepts only https addresses from that list and keeps pauses between requests; the isolation check tests it every night. First download on the server: 200 papers, 50 models, 50 data sets and 12 releases, without errors. The radar job runs the channels every week.
- 2026-09-29: F5.1. The radar runs: a weekly job (Sunday 22:30) downloads the channels, runs the extractor on new papers and compiles the [radar page](../generated/radar.md) in Polish and English. Week 2026-W39: 198 papers, 287 hypotheses and plans after removing repeats, one possible contradiction, one dense topic, 17 new models, data sets and releases. Sudden rises are not computed yet, as there are not four weeks before. The radar skips papers from experiment corpora and items the gate would hold as personal data (one in week 2026-W40). The done condition is four weeks in a row.
- 2026-09-29: F5.3. Ten candidates from the radar of week 2026-W39 went through scoring by models of three families (qwen3.6, gemma-4, gpt-oss), each on its own, with the selection template. Eight have valid answers from all three models, two scorings lack a valid answer from one model. A spread of at least two points in some dimension occurred for eight candidates, and four failed some knock-out question in the scoring of at least one model. The owner makes the G0 decisions. The gate held the radar page for 2026-W39 and the scoring as similar to protected material; they are waiting for review.
