---
id: intent-vs-fact-corpus
lang: en
counterpart: ../../../pl/experiments/intent-vs-fact/corpus.md
provenance: ai_authored
provenance_metadata:
  agent: Claude Opus 5.5 (Cowork)
  date: 2026-09-28
  human_validated: false
---

# The corpus of the "intent or fact" experiment

The corpus description for the first lab experiment ([F3](../../roadmap/F3-first-pass.md), task [F3.1](../../roadmap/F3/F3.1-public-corpus-selection.md)). The experiment checks whether extracting claims from text correctly tells facts apart from intentions, hypotheses and announcements, and whether our summaries turn an intention into a fact.

## Source

arXiv papers that Exocortex downloaded and summarised in August and September 2026. The engine has 2486 paper pages; after removing one paper stored in two versions, 2485 distinct ids remain. For each paper the engine holds a Polish summary, a list of key findings and a relevance score from 1 to 10.

Two texts per paper go into the corpus:

| Text | Where from | Language |
|---|---|---|
| Abstract | the arXiv API, downloaded again in F3.2, with the paper version and the download date | English |
| Summary and findings | the Exocortex database, with the model version and the summary date | Polish |

We do not use the full texts of the papers.

## Basis for use

- **Abstracts.** arXiv makes descriptive metadata of papers available under CC0 1.0 ([arXiv API terms of use](https://info.arxiv.org/help/api/tou.html), [arXiv licences](https://info.arxiv.org/help/license/index.html)). The arXiv pages do not name abstracts explicitly, but the API returns them as metadata, and public collections of abstracts treat them as CC0 ([Common Pile, arxiv_abstracts](https://huggingface.co/datasets/common-pile/arxiv_abstracts)). The abstracts go into the repository together with the manifest. If arXiv clarifies this differently, only the ids and the download script will stay in the repository.
- **Summaries.** They are output of our engine, so we publish them in full, with the version of the model that wrote them.
- **API terms.** At most one request every three seconds and one connection at a time. The lab does not present itself as a project supported by arXiv.

## Sampling frame

A paper enters the frame if it has a valid arXiv id, an abstract available from the API and a summary in the engine. Excluded are withdrawn papers (the abstract says so), abstracts shorter than 50 words, and duplicates: of several versions, the newest stays.

Strata by the relevance score the engine gave:

| Stratum | Score | Papers |
|---|---|---|
| low | 1 to 4 | 603 |
| middle | 5 to 7 | 1010 |
| high | 8 to 10 | 873 |

The numbers refer to the 2486 pages before the exclusions. After the exclusions in F3.2 the frame has 2478 papers: 602 in the low stratum, 1005 in the middle and 871 in the high. Left out were one duplicate, two abstracts shorter than 50 words and five papers held by the publishing gate because they contain a name from its private list. The ids of these five are private, because they would point at the names. From the frame we draw three disjoint stratified sets: the tuning sample, the control set and the pilot sample. Their sizes and the random seed are set by the hypothesis card ([F3.4](../../roadmap/F3/F3.4-hypothesis-card.md)) before anyone sees results. The control set stays closed until the end of the experiment.

## Notes

The abstracts are in English and the summaries in Polish, so the comparison of intent and fact runs across languages. The relevance score reflects the interests of the lab's owner, not the quality of the paper; the strata only make sure that every sample has papers from different parts of that scale.
