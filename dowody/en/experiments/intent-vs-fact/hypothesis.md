---
type: hypothesis_card
lang: en
counterpart: ../../../pl/experiments/intent-vs-fact/hypothesis.md
slug: intent-vs-fact
version: 1
supersedes: null
tier_target: M
data_class: public
sources: ["../../roadmap/F3-first-pass.md", "corpus.md"]
prereg_hash: null
human_validated: false
---

# Hypothesis: a mandatory mode field reduces the share of claims that present intent as fact

The card of the lab's first experiment, task [F3.4](../../roadmap/F3/F3.4-hypothesis-card.md). The corpus is described in [Corpus of the experiment](corpus.md). Until the owner approves this card it is a draft: it is not frozen and nothing has been measured on its basis.

## Problem

The claim extractor turns text into short sentences with a verbatim quote. We later build summaries, result pages and project cards from such claims. If a claim loses the mode of its source sentence, the authors' plan or conjecture travels on as a fact. In abstracts of scientific papers both kinds of sentence sit side by side: what was measured, and what the authors propose, expect or plan.

Summaries of scientific work written by language models generalise conclusions beyond what the source says more often than human summaries do ([Peters and Chin-Yee, 2025](https://doi.org/10.1098/rsos.241776)). We do not know how often our extractor makes this error, or whether a simple change of the answer schema helps.

## Hypothesis

- H1: adding a mandatory mode field (fact, plan, requirement, hypothesis) to the extraction schema reduces the share of claims with a mode swap compared with the same extractor without that field, on the same abstracts and the same model. H1 is refuted by a difference smaller than 5 percentage points or by a confidence interval of the difference that includes zero.
- H0: the difference is below the threshold or its confidence interval includes zero.

A claim with a mode swap presents as an accomplished fact something the source presents as a plan, a requirement or a hypothesis. In the variant with the mode field a claim counts as a swap only when the rater judged its content a swap and the mode field says "fact". A claim labelled as a hypothesis does not present its content as a fact, even if the sentence itself is in the indicative.

## Metrics

| Role | Metric | Definition | Threshold | Baseline | How computed |
|---|---|---|---|---|---|
| deciding | swap_rate | share of usable claims with a mode swap | a drop of at least 5 percentage points | the variant without the mode field | blind rating; the difference with a bootstrap by document |
| supporting | label_accuracy | share of claims in the mode-field variant whose field matches the source mode according to the rater | no threshold | not applicable | Wilson |
| supporting | other_errors | share of claims with a distorted number or name or another error | no threshold | the variant without the mode field | Wilson |
| guard | failed_share | share of documents for which the model returned no valid answer | at most 5% | not applicable | Wilson |
| guard | usable_per_document | mean number of usable claims per document | at least 70% of the baseline | the variant without the mode field | bootstrap by document |

A usable claim has a quote present verbatim in the document, a separate model pass judged it a claim, and it does not repeat an earlier one. Confidence intervals: the Wilson method for proportions, a bootstrap by document for differences and means (10 000 replicates, seed 20260929, percentiles 2.5 and 97.5). Both variants run on the same documents, so the bootstrap draws documents once for both.

## Samples

| Sample | Size | Sampling method | Seed | Checksum |
|---|---|---|---|---|
| tuning | 20 papers | stratified by relevance score: 5 low, 8 middle, 7 high | 20260929 | 7c6a59ac1189ccf535cac28955395dd0341239314b3af1dd257a91f261ddf700 |
| control (opened once) | 10 papers | stratified: 2 low, 4 middle, 4 high | 20260929 | 0ab29cd2f6f933a037bd79ca028185caacf6fcc8b64e4a42ff17569b8f3290d7 |
| pilot (scale M) | 60 papers | stratified: 15 low, 24 middle, 21 high | 20260929 | 8252184cc8f08dbefbcfb9e0defd94399d0eb1d0d4cc53bcafed2d40d1b183f8 |
| blind (scale M) | 120 claims | from the pilot results, stratified by configuration | 20260930 | made after the pilot run |

The sampling frame is 2473 papers: the corpus without the five papers the extractor was tested on (F3.3). The three samples are disjoint. The lists of papers are in the repository in `lab/corpora/intent-vs-fact/samples/`, and the checksums were computed from the joint checksum of each paper's abstract and summary in `manifest.csv`.

At gate G1 we rate blind every claim of both variants from the tuning sample, and then from the control set. Ten randomly chosen claims appear on the rating page a second time, to check the rater's agreement with themselves.

## Configurations

| Name | Model | Variant | Parameters |
|---|---|---|---|
| qwen36-baseline (baseline) | qwen3.6-35b-a3b | without the mode field | abstract, temperature 0, seed 0, answer through a JSON grammar |
| qwen36-mode | qwen3.6-35b-a3b | with the mode field | as in the baseline |
| gemma4-baseline (scale M) | gemma-4-26b-a4b | without the mode field | as in the baseline |
| gemma4-mode (scale M) | gemma-4-26b-a4b | with the mode field | as in the baseline |
| qwen36-summary-mode (scale M, exploratory) | qwen3.6-35b-a3b | with the mode field | the engine's Polish summary instead of the abstract |

The extractor is the module `exocortex/lab/extractor.py`, and the configurations are recorded in `lab/experiments/intent-vs-fact.yaml`. Both variants ask for the quote first and then for the claim. The mode-field variant differs from the baseline only by one rule in the instructions and one field in the answer schema. Whether a sentence is a claim is judged by the same model in a separate call, and repeats are removed when the similarity of bge-m3 embeddings is at least 0.92. The abbreviation dictionary was built from the corpus (70 entries). Every run records the code commit. Changing the instructions, the schema or the thresholds after the card is frozen requires a new version of the card.

## The assumption everything depends on

The rater can tell from the quote and the text around it whether the source presents a sentence as a fact or as a plan, a requirement or a hypothesis. We measure this instead of assuming it: from the repeated items on the rating page we compute the rater's agreement with themselves. The rating page shows neither the configuration name nor the value of the mode field, so the rater judges the content of the claim alone.

## Gate criteria

- G1 (S to M). Data: the tuning sample and the control set together, if the extractor did not change after the tuning sample was rated. If it changed, only the control set counts. GO when three conditions hold: the baseline has a swap_rate of at least 5% (the problem occurs at all), the swap_rate difference is at least 5 percentage points in favour of the mode-field variant and the upper bound of its confidence interval is below zero, and both guard metrics hold in both variants. If the baseline swap_rate is below 5%, the decision is CLOSED: with this model the problem does not show. If the difference points the right way but its confidence interval includes zero, the decision is NOT-NOW with the return condition: a larger sample. In every other case NO-GO.
- G2 (M to L). Data: the blind sample of the pilot, both models together, about 60 claims per variant. The same conditions as at G1, plus a described result of the automatic judge calibration (F3.9). With a share close to 10% and 60 claims per variant, half the width of the confidence interval of the difference is about 11 percentage points, so the pilot will confirm only a large effect.

## Stopping condition

- If in either variant the model returns no valid answer for more than 20% of the documents of the tuning sample, we end the quick test, fix the extractor and write a new version of the card.
- If the rater's agreement with themselves is below 80%, we describe the G1 result as uncertain and the decision cannot be GO.

## What this method will not detect

- Completeness: whether the most important claims were extracted.
- Errors of interpretation with a correct quote, if the rater does not notice them.
- Weaknesses shared by extraction and by the judgement whether a sentence is a claim, since the same model does both.
- The reverse swap, when a fact is given as a hypothesis. We count it as another error, but it does not decide the gate.
- Fixed habits of a single rater. Agreement between raters cannot be computed before the second expert joins (F6.1).

## Related work

- [Peters and Chin-Yee, 2025](https://doi.org/10.1098/rsos.241776): summaries of scientific work written by ten language models generalised conclusions beyond the source more often than human summaries. They measured whole summaries; we measure single claims and one specific change of the schema.
- [Min et al., 2023](https://aclanthology.org/2023.emnlp-main.741/) (FActScore): a text is split into atomic facts and each is checked against a knowledge source. The approach does not distinguish the mode of sentences.
- [Farkas et al., 2010](https://aclanthology.org/W10-3001/) (CoNLL-2010): detecting uncertain sentences in scientific text. We do not detect uncertainty in the source; we check whether the extracted claim keeps it.
