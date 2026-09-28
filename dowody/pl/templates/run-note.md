---
type: run_note
lang: pl
counterpart: ../../en/templates/run-note.md
hypothesis: "<slug>"
hypothesis_version: 1
run_id: "<run-id>"        # run-<data>-<n>, unikalny w ramach hipotezy
date: "<RRRR-MM-DD>"
sample: tuning            # tuning | control | blind
configuration: baseline   # nazwa z tabeli Konfiguracje w karcie
code_commit: null         # commit kodu laboratorium użyty w przebiegu
prereg_hash: null         # przepisany z zatwierdzonej karty
result_ids: []            # wypełnia procesor
human_validated: false
---

# Przebieg <run-id>: <konfiguracja> na <próbka>

## Co uruchomiono

Model, wariant, parametry i wszystko, co różni się od karty. Jeśli nic się nie różni, trzeba to napisać.

## Wynik

| Metryka | Wartość | Przedział ufności | Id wyniku |
|---|---|---|---|

## Co poszło źle albo wyglądało dziwnie

Błędy, restarty, pominięte pozycje i powód. Pusta sekcja znaczy, że nic się nie wydarzyło, a nie że nikt nie sprawdzał.
