---
id: generated-dossier-intent-vs-fact-smoke
lang: pl
counterpart: ../../../en/generated/experiments/intent-vs-fact-smoke.md
generated: true
---

# Dossier: intent-vs-fact-smoke

Dossier eksperymentu intent-vs-fact-smoke, złożone automatycznie z grafu laboratorium. Karta, konfiguracje i próby są opisane w dokumentach eksperymentu, a surowe dane w katalogu danych.

## Karta hipotezy

bez karty.

## Konfiguracje

| Nazwa | Model | Dostawca | Wariant |
|---|---|---|---|
| qwen36-abstract-baseline | qwen3.6-35b-a3b | local | baseline |
| qwen36-abstract-mode | qwen3.6-35b-a3b | local | mode |
| qwen36-summary-baseline | qwen3.6-35b-a3b | local | baseline |
| qwen36-summary-mode | qwen3.6-35b-a3b | local | mode |

## Przebiegi

| Przebieg | Próba | Rola próby | Stan | Zadania | Commit kodu | Suma z prerejestracji |
|---|---|---|---|---|---|---|
| run-2026-09-29-1 | test-5 | test | done | 20 | `c6826401` | — |

## Wyniki

| Id wyniku | Metryka | Wartość | Przedział ufności | n | Metoda |
|---|---|---|---|---|---|

## Decyzje z bramek

Brak.

## Surowe dane

Pliki CSV z opisem kolumn: [datapackage.json](../../../data/intent-vs-fact-smoke/datapackage.json). Przeliczenie: `python lab/recompute.py intent-vs-fact-smoke`.
