---
id: generated-dossier-intent-vs-fact-smoke
lang: en
counterpart: ../../../pl/generated/experiments/intent-vs-fact-smoke.md
generated: true
---

# Dossier: intent-vs-fact-smoke

Dossier of the experiment intent-vs-fact-smoke, compiled automatically from the lab graph. The card, configurations and samples are described in the experiment's documents, and the raw data in the data folder.

## Hypothesis card

no card.

## Configurations

| Name | Model | Provider | Variant |
|---|---|---|---|
| qwen36-abstract-baseline | qwen3.6-35b-a3b | local | baseline |
| qwen36-abstract-mode | qwen3.6-35b-a3b | local | mode |
| qwen36-summary-baseline | qwen3.6-35b-a3b | local | baseline |
| qwen36-summary-mode | qwen3.6-35b-a3b | local | mode |

## Runs

| Run | Sample | Sample role | Status | Jobs | Code commit | Preregistration checksum |
|---|---|---|---|---|---|---|
| run-2026-09-29-1 | test-5 | test | done | 20 | `c6826401` | — |

## Results

| Result id | Metric | Value | Confidence interval | n | Method |
|---|---|---|---|---|---|

## Gate decisions

None.

## Raw data

CSV files with a description of the columns: [datapackage.json](../../../data/intent-vs-fact-smoke/datapackage.json). Recompute: `python lab/recompute.py intent-vs-fact-smoke`.
