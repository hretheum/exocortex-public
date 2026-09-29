---
type: hypothesis_card
lang: en
counterpart: ../../../pl/experiments/toy-length/hypothesis.md
slug: toy-length
version: 1
supersedes: null
tier_target: S
data_class: public
sources: ["../../roadmap/F2/F2.4-hypothesis-processor.md", "../../roadmap/F2/F2.6-experiment-tables.md"]
prereg_hash: null
human_validated: false
---

# Hypothesis: in the lab's documents the longest sentence exceeds 120 characters more often than the first one

This is a test card. It exercises the lab's machinery: preregistration ([F2.4](../../roadmap/F2/F2.4-hypothesis-processor.md)), gate decisions ([F2.5](../../roadmap/F2/F2.5-gate-processor.md)) and the experiment queue ([F2.6](../../roadmap/F2/F2.6-experiment-tables.md)). Its result is evidence of nothing except that the whole path from card to result works.

## Problem

The toy experiment measures the lab's published documents without a model: it counts characters, words and sentences and picks one sentence by a fixed rule, the first or the longest. The question is trivial on purpose; what matters is going through the whole cycle.

## Hypothesis

- H1: the share of documents in which the chosen sentence has more than 120 characters is higher under the longest-sentence rule than under the first-sentence rule, by at least 20 percentage points.
- H0: the difference is below 20 percentage points or its confidence interval includes zero.

## Metrics

| Role | Metric | Definition | Threshold | Baseline | How computed |
|---|---|---|---|---|---|
| deciding | long_unit_share_difference | difference in the share of documents whose chosen sentence is longer than 120 characters | at least 20 percentage points | the first-sentence rule | bootstrap by document |
| guard | failed_share | share of documents without a result | 0% | not applicable | count |

## Samples

| Sample | Size | Sampling method | Seed | Checksum |
|---|---|---|---|---|
| tuning | 12 documents | stratified by language | 20260929 | recorded in the lab's sample table |
| control (opened once) | 6 documents | stratified by language | 20260929 | recorded in the lab's sample table |

## Configurations

| Name | Model | Variant | Parameters |
|---|---|---|---|
| first-sentence (baseline) | none | first sentence | toy-model-a as a placeholder name |
| longest-sentence | none | longest sentence | toy-model-b as a placeholder name |

## The assumption everything depends on

The documents do not change between drawing the sample and the run. If a document changes, the run fails instead of measuring the new text.

## Gate criteria

- G1: a difference of at least 20 percentage points and a lower bound of the confidence interval above zero. Then GO, otherwise NO-GO.

## Stopping condition

No result for any document.

## What this method will not detect

Anything about the quality of the documents. It measures only the length of mechanically chosen sentences.

## Related work

None: this is a test of the machinery.
