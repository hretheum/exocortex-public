---
type: gate_decision
lang: pl
counterpart: ../../en/templates/gate-decision.md
hypothesis: "<slug>"
hypothesis_version: 1
gate: G1                # G0 | G1 | G2
decision: null          # GO | NO-GO | PIVOT | NOT-NOW | CLOSED
date: "<RRRR-MM-DD>"
approved_by: []
return_condition: null  # wymagane przy NOT-NOW
result_ids: []          # identyfikatory wyników, na których opiera się decyzja
human_validated: false  # bez true procesor ignoruje decyzję
---

# Bramka <G?>: <hipoteza>

## Kryteria z karty hipotezy (bez zmian)

| Kryterium | Próg | Wynik | Przedział ufności | Id wyniku | Spełnione |
|---|---|---|---|---|---|

## Metryki ochronne

| Metryka | Granica | Wynik | Spełnione |
|---|---|---|---|

## Błędy

Główne klasy błędów z licznościami. Czy da się je usunąć zmianą promptu, schematu albo filtra, czy wynikają z samego podejścia.

## Decyzja

Decyzja i uzasadnienie w kilku zdaniach. Jeśli decyzja idzie wbrew liczbom, napisać to wprost i dlaczego.

## Co dalej

Przy GO zakres następnej skali. Przy PIVOT, co zmienia nowa wersja karty. Przy NO-GO, czego się dowiedzieliśmy.
