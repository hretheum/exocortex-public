---
id: enforced-answer-format-overview
lang: pl
counterpart: ../../../en/experiments/enforced-answer-format/overview.md
status: planned
roadmap: F5.7
stage: 0
tier: S
tagline: "Czy struktura eliminuje odpowiedzi prozą."
updated: 2026-09-28
provenance: ai_authored
provenance_metadata:
  agent: Claude Sonnet 5.5 (Cowork)
  date: 2026-09-28
  human_validated: false
---

# Wymuszony format odpowiedzi

## Streszczenie

Czasem model odpowiada prozą tam, gdzie program oczekuje wywołania narzędzia. Sprawdzimy, czy wymuszenie struktury odpowiedzi gramatyką eliminuje takie przypadki i czy nie psuje jakości twierdzeń. Eksperyment jest planowany i niczego jeszcze nie zmierzono.

## Pytanie i hipoteza

Pytanie: czy wymuszenie struktury odpowiedzi gramatyką (schemat JSON, gramatyka GBNF w llama.cpp) eliminuje przypadki, w których model odpowiada prozą zamiast wywołać narzędzie. Hipoteza i próg powstaną w karcie hipotezy.

## Prerejestracja

Brak karty hipotezy. Karta zostanie zamrożona i opublikowana przed pierwszym pomiarem.

## Dane

Dane z pierwszego eksperymentu (F3), czyli publiczny korpus abstraktów i konfiguracje modeli lokalnych.

## Metoda

Porównanie odpowiedzi z wymuszoną strukturą i bez niej. Metryką rozstrzygającą będzie odsetek odpowiedzi zgodnych ze schematem, a metryką ochronną jakość twierdzeń. Eksperyment zależy od pierwszego eksperymentu (F3).

## Przebiegi

Brak przebiegów. Pierwszy przebieg powstanie po zamrożeniu karty hipotezy. Każdy przebieg dostanie notatkę: model, wariant, parametry, commit kodu, wynik i wszystko, co poszło źle albo wyglądało dziwnie.

## Wyniki

Brak wyników. Wyniki publikujemy tego samego dnia, w którym powstają, także negatywne, razem z przedziałami ufności i odnośnikiem do surowych danych.

## Decyzje z bramek

Nie zapadła jeszcze żadna decyzja. Bramka G1 jest po szybkim teście, a G2 po pilocie. Każda decyzja jest publikowana razem z wynikami, na których się opiera.

## Odstępstwa i historia zmian

| Data | Wersja | Zmiana |
|---|---|---|
| 2026-09-28 | 0.1 | Utworzono dossier planowanego eksperymentu. |

## Jak powtórzyć

Nie dotyczy, dopóki nie ma przebiegów.

## Ograniczenia

Ograniczenia zapiszemy w karcie hipotezy. Już dziś wiadomo, że wynik będzie dotyczył konkretnych modeli lokalnych i konkretnego oprogramowania do ich uruchamiania.

## Źródła

Brak.
