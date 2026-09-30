---
id: generated-dossier-intent-vs-fact
lang: en
counterpart: ../../../pl/generated/experiments/intent-vs-fact.md
generated: true
---

# Dossier: intent-vs-fact

Dossier of the experiment intent-vs-fact, compiled automatically from the lab graph. The card, configurations and samples are described in the experiment's documents, and the raw data in the data folder.

## Hypothesis card

| Version | State | Approved | Content checksum | Registered | Registered checksum |
|---|---|---|---|---|---|
| 1 | frozen | yes | `0eedfec4ad54411a` | 2026-09-29 | `0eedfec4ad54411a` |

## Configurations

| Name | Model | Provider | Variant |
|---|---|---|---|
| gemma4-baseline | gemma-4-26b-a4b | local | baseline |
| gemma4-mode | gemma-4-26b-a4b | local | mode |
| qwen36-baseline | qwen3.6-35b-a3b | local | baseline |
| qwen36-mode | qwen3.6-35b-a3b | local | mode |
| qwen36-summary-mode | qwen3.6-35b-a3b | local | mode |

## Runs

| Run | Sample | Sample role | Status | Jobs | Code commit | Preregistration checksum |
|---|---|---|---|---|---|---|
| run-2026-09-30-1 | tuning-20 | tuning | done | 40 | `dbe77d51` | `0eedfec4ad54411a` |

## Results

| Result id | Metric | Value | Confidence interval | n | Method |
|---|---|---|---|---|---|

## Gate decisions

None.

## Raw data

CSV files with a description of the columns: [datapackage.json](../../../data/intent-vs-fact/datapackage.json). Recompute: `python lab/recompute.py intent-vs-fact`.
