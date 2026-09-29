---
id: generated-dossier-toy-length
lang: en
counterpart: ../../../pl/generated/experiments/toy-length.md
generated: true
---

# Dossier: toy-length

Dossier of the experiment toy-length, compiled automatically from the lab graph. The card, configurations and samples are described in the experiment's documents, and the raw data in the data folder.

## Hypothesis card

| Version | State | Approved | Content checksum | Registered | Registered checksum |
|---|---|---|---|---|---|
| 1 | draft | no | `775d72ace67b796a` | — | — |

## Configurations

| Name | Model | Provider | Variant |
|---|---|---|---|
| first-sentence | toy-model-a | none | first |
| longest-sentence | toy-model-b | none | longest |

## Runs

| Run | Sample | Sample role | Status | Jobs | Code commit | Preregistration checksum |
|---|---|---|---|---|---|---|
| run-2026-09-29-1 | tuning-12 | tuning | done | 24 | `c6826401` | — |
| run-2026-09-29-2 | control-6 | control | done | 12 | `c6826401` | — |
| run-2026-09-29-3 | tuning-12 | tuning | done | 24 | `00152bf2` | — |
| run-2026-09-29-4 | tuning-12 | tuning | done | 24 | `00152bf2` | — |

## Results

| Result id | Metric | Value | Confidence interval | n | Method |
|---|---|---|---|---|---|
| `toy-length/run-2026-09-29-1/diff/long_unit_share` | long_unit_share_difference | 0.750 | 0.500 – 1.000 | 12 | bootstrap-by-item |
| `toy-length/run-2026-09-29-1/first-sentence/long_unit_share` | long_unit_share | 0.083 | 0.015 – 0.354 | 12 | wilson |
| `toy-length/run-2026-09-29-1/first-sentence/mean_chars` | mean_chars | 2521.500 | 969.498 – 4691.027 | 12 | bootstrap-by-item |
| `toy-length/run-2026-09-29-1/longest-sentence/long_unit_share` | long_unit_share | 0.833 | 0.552 – 0.953 | 12 | wilson |
| `toy-length/run-2026-09-29-1/longest-sentence/mean_chars` | mean_chars | 2521.500 | 969.498 – 4691.027 | 12 | bootstrap-by-item |
| `toy-length/run-2026-09-29-2/diff/long_unit_share` | long_unit_share_difference | 0.667 | 0.333 – 1.000 | 6 | bootstrap-by-item |
| `toy-length/run-2026-09-29-2/first-sentence/long_unit_share` | long_unit_share | 0.167 | 0.030 – 0.564 | 6 | wilson |
| `toy-length/run-2026-09-29-2/first-sentence/mean_chars` | mean_chars | 3044.333 | 772.000 – 6893.167 | 6 | bootstrap-by-item |
| `toy-length/run-2026-09-29-2/longest-sentence/long_unit_share` | long_unit_share | 0.833 | 0.436 – 0.970 | 6 | wilson |
| `toy-length/run-2026-09-29-2/longest-sentence/mean_chars` | mean_chars | 3044.333 | 772.000 – 6893.167 | 6 | bootstrap-by-item |
| `toy-length/run-2026-09-29-3/diff/long_unit_share` | long_unit_share_difference | 0.000 | 0.000 – 0.000 | 2 | bootstrap-by-item |
| `toy-length/run-2026-09-29-3/first-sentence/long_unit_share` | long_unit_share | 0.000 | 0.000 – 0.658 | 2 | wilson |
| `toy-length/run-2026-09-29-3/first-sentence/mean_chars` | mean_chars | 273.500 | 202.000 – 345.000 | 2 | bootstrap-by-item |
| `toy-length/run-2026-09-29-3/longest-sentence/long_unit_share` | long_unit_share | 0.000 | 0.000 – 0.658 | 2 | wilson |
| `toy-length/run-2026-09-29-3/longest-sentence/mean_chars` | mean_chars | 273.500 | 202.000 – 345.000 | 2 | bootstrap-by-item |
| `toy-length/run-2026-09-29-4/diff/long_unit_share` | long_unit_share_difference | 0.000 | 0.000 – 0.000 | 2 | bootstrap-by-item |
| `toy-length/run-2026-09-29-4/first-sentence/long_unit_share` | long_unit_share | 0.000 | 0.000 – 0.658 | 2 | wilson |
| `toy-length/run-2026-09-29-4/first-sentence/mean_chars` | mean_chars | 273.500 | 202.000 – 345.000 | 2 | bootstrap-by-item |
| `toy-length/run-2026-09-29-4/longest-sentence/long_unit_share` | long_unit_share | 0.000 | 0.000 – 0.658 | 2 | wilson |
| `toy-length/run-2026-09-29-4/longest-sentence/mean_chars` | mean_chars | 273.500 | 202.000 – 345.000 | 2 | bootstrap-by-item |

## Gate decisions

None.

## Raw data

CSV files with a description of the columns: [datapackage.json](../../../data/toy-length/datapackage.json). Recompute: `python lab/recompute.py toy-length`.
