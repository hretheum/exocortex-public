---
id: generated-dossier-intent-vs-fact
lang: pl
counterpart: ../../../en/generated/experiments/intent-vs-fact.md
generated: true
---

# Dossier: intent-vs-fact

Dossier eksperymentu intent-vs-fact, złożone automatycznie z grafu laboratorium. Karta, konfiguracje i próby są opisane w dokumentach eksperymentu, a surowe dane w katalogu danych.

## Karta hipotezy

| Wersja | Stan | Zatwierdzona | Suma kontrolna treści | Zarejestrowana | Suma w rejestrze |
|---|---|---|---|---|---|
| 1 | zamrożona | tak | `0eedfec4ad54411a` | 2026-09-29 | `0eedfec4ad54411a` |

## Konfiguracje

| Nazwa | Model | Dostawca | Wariant |
|---|---|---|---|
| gemma4-baseline | gemma-4-26b-a4b | local | baseline |
| gemma4-mode | gemma-4-26b-a4b | local | mode |
| qwen36-baseline | qwen3.6-35b-a3b | local | baseline |
| qwen36-mode | qwen3.6-35b-a3b | local | mode |
| qwen36-summary-mode | qwen3.6-35b-a3b | local | mode |

## Przebiegi

| Przebieg | Próba | Rola próby | Stan | Zadania | Commit kodu | Suma z prerejestracji |
|---|---|---|---|---|---|---|
| run-2026-09-30-1 | tuning-20 | tuning | done | 40 | `dbe77d51` | `0eedfec4ad54411a` |

## Wyniki

| Id wyniku | Metryka | Wartość | Przedział ufności | n | Metoda |
|---|---|---|---|---|---|

## Decyzje z bramek

Brak.

## Surowe dane

Pliki CSV z opisem kolumn: [datapackage.json](../../../data/intent-vs-fact/datapackage.json). Przeliczenie: `python lab/recompute.py intent-vs-fact`.
