---
type: hypothesis_card
lang: en
counterpart: ../../../pl/experiments/local-vs-cloud-embeddings/hypothesis.md
slug: local-vs-cloud-embeddings
version: 1
supersedes: null
tier_target: M
data_class: public
sources: ["../../roadmap/F5-radar-and-experiments.md"]
prereg_hash: null
human_validated: false
---

# Hypothesis: a local embedding model is not worse than a cloud one by more than Δ in nDCG@10

The card of experiment [F5.6](../../roadmap/F5-radar-and-experiments.md). Until the owner approves this card it is a draft: it is not frozen and nothing has been measured on its basis. The value of Δ and the sample sizes will be set after the tuning sample but before the main sample is opened, and only once they are written in can the card be frozen.

## Problem

Search by meaning needs an embedding model, a model that turns text into a numerical description of its sense. It can be run on your own hardware or rented as a cloud service. The choice matters to any company that keeps confidential documents or does not want to send them outside the organization. We do not know how much search quality in Polish is lost by moving to a local model, or whether that difference matters in practice.

We are not asking which model is better in general. We are asking whether the local model is good enough for the decision to stay on your own hardware to rest on search quality. Caution alone is not enough.

## Hypothesis

- H1: a local embedding model is not worse than the cloud one by more than Δ in nDCG@10, on the same questions and the same public Polish corpus. H1 is supported when the lower bound of the 95% confidence interval of the difference (local minus cloud) is above −Δ.
- H0: the difference is worse than −Δ, or its confidence interval includes −Δ.

The test is one-sided: a local model that turns out better supports H1. Δ is written as a number before the main sample is opened and derived from an anchor that does not depend on the local model's result (see Metrics). Feasibility on your own hardware is a separate condition and is not part of H1.

## Metrics

| Role | Metric | Definition | Threshold | Baseline | How computed |
|---|---|---|---|---|---|
| deciding | ndcg10_diff | difference in nDCG@10, local minus cloud, computed in pairs per question | lower bound of the 95% interval above −Δ | the cloud model | bootstrap over questions |
| supporting | recall100_diff | difference in recall@100, local minus cloud | no threshold | the cloud model | bootstrap over questions |
| supporting | cloud_drift | largest difference in nDCG@10 between three runs of the cloud model on different days | Δ must be larger | the same cloud model | bootstrap over questions |
| supporting | bm25_gap | difference in nDCG@10, cloud model minus BM25 | derives Δ | BM25 | bootstrap over questions |
| guard (feasibility) | query_p95 | 95th percentile of one query time of the local model on K12 | at most 500 ms | not applicable | percentile over three runs |
| guard (feasibility) | index_time | time to index the whole corpus on K12 | at most 6 hours | not applicable | median over three runs |

Δ is half the value of bm25_gap measured on the tuning sample, provided that it is larger than cloud_drift. If bm25_gap is smaller than twice cloud_drift, the test set does not tell a good model from a simple reference point and the decision is CLOSED. We write Δ as a number in the card before freezing and do not change it afterwards.

Confidence intervals: bootstrap over questions (10,000 repetitions, seed 20260929, percentiles 2.5 and 97.5). Both models run on the same questions, so the resampling is shared.

## Samples

| Sample | Size | Sampling method | Seed | Checksum |
|---|---|---|---|---|
| tuning | 100 questions | random from the corpus questions | 20260929 | set before freezing |
| control (opened once) | 100 questions | random, disjoint from tuning | 20260929 | set before freezing |
| main | N questions | the rest, disjoint from both | 20260930 | set before freezing |

N is set after the spread of differences is measured on the tuning sample, but before the main sample is opened. For the half-width of the interval not to exceed Δ/2 we need N ≥ (2·1.96·σ/Δ)², where σ is the standard deviation of the nDCG@10 difference over questions, measured on the tuning sample. If the corpus has fewer questions than the formula requires, we describe the result as able to rule out only large differences.

Data: public texts only. Only texts from the public corpus go to the cloud model. The proposed corpus is the Polish benchmark [PIRB](https://arxiv.org/abs/2402.13350); the benchmark code is licensed under Apache-2.0, but the project page does not state the licences of the individual datasets, so each subset is added to the allowed-sources list only after its licence is checked and the reasoning is recorded.

## Configurations

| Name | Model | Variant | Parameters |
|---|---|---|---|
| local | bge-m3 (`lab/models.yaml`, MIT licence) | dense embeddings | 1024 dimensions, up to 8192 tokens, run on K12 |
| cloud | text-embedding-3-large (OpenAI), identifier and query date recorded on every run | dense embeddings | 3072 dimensions, service default parameters, three runs on different days |
| bm25 (reference point) | BM25 | keyword search | library default parameters, recorded in the configuration |

The same corpus, the same questions, the same way of splitting text into chunks and the same similarity measure for both models. Every run records the code commit, the model version and the date. Changing the model, the chunking, the measure or the thresholds after the card is frozen requires a new version of the card. Before the first run we must check that the cloud service's terms allow publishing the comparison results and record that in `lab/models.yaml` together with its basis.

## The assumption everything depends on

The set of questions and gold answers tells better search from worse well. We measure this instead of assuming it: if the cloud model does not beat BM25 by a visible margin (bm25_gap at least twice cloud_drift), the test has nothing to derive a sensible Δ from and the experiment ends with the decision CLOSED. We draw no conclusion about the models in that case.

## Gate criteria

- G1 (S to M). Data: the tuning and control samples. First we check the assumption: bm25_gap at least twice cloud_drift, otherwise CLOSED. Then quality: GO when the lower bound of the 95% interval of ndcg10_diff is above −Δ. NOT-NOW with a condition for return (a larger sample) when the interval crosses −Δ and the central estimate of the difference is above −Δ. NO-GO when the upper bound of the interval is below −Δ or the central estimate lies below −Δ. Feasibility is described separately: query_p95 and index_time either met or not met, without affecting the quality decision. The published result has two independent rows: one for quality and one for feasibility.
- G2 (M to L). Data: the main sample. The same conditions as G1. In addition the drift of the cloud model is described and, if available, the result repeated on a second corpus. GO at G2 permits the wording "the local model is not worse by more than Δ on this corpus", never "the local model is as good".

## Stopping condition

- If the cloud service returns errors for more than 5% of questions in any run, we stop the measurement, describe the cause and write a new version of the card.
- If the licence of any corpus subset rules out publishing the results, we exclude it before the measurement. After the measurement we remove nothing.
- If the cloud service's terms do not allow publishing the comparison, we stop before the first run and choose another cloud model in a new version of the card.

## What this method will not detect

- Results on the vocabulary of a specific company: a public corpus does not replace its documents.
- Behaviour on documents longer than the chunks used in the test.
- Costs and legal requirements when choosing between a local and a cloud model. We measure search quality and technical feasibility.
- Changes in the cloud model after the day of measurement. We measure drift only within a window of a few days.
- Weaknesses common to both models, for example wrong gold answers in the corpus.

## Related work

- [Dadas et al., 2024 (PIRB)](https://arxiv.org/abs/2402.13350): a test set for comparing Polish retrieval models. They compare many models on many datasets; we ask one question about the non-inferiority of a local model with a threshold frozen in advance and a separate feasibility measurement.
- [Chen et al., 2024 (BGE M3-Embedding)](https://arxiv.org/abs/2402.03216): the model we check on the local side.
- [Muennighoff et al., 2023 (MTEB)](https://arxiv.org/abs/2210.07316): a broad set of embedding tests. We do not compare rankings; we test one hypothesis with a one-sided threshold.
- Schuirmann, 1987: the classic equivalence and non-inferiority tests, from which we take a one-sided test with a margin.
