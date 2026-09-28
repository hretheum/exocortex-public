---
id: graph-vs-search-overview
lang: pl
counterpart: ../../../en/experiments/graph-vs-search/overview.md
status: planned
roadmap: F5.5
stage: 0
tier: S
tagline: "Czy powiązania poprawiają wyniki."
updated: 2026-09-28
provenance: ai_authored
provenance_metadata:
  agent: Claude Sonnet 5.5 (Cowork)
  date: 2026-09-28
  human_validated: false
---

# Graf a wyszukiwanie

## Streszczenie

Wyszukiwanie tekstów zwykle opiera się na osadzeniach, czyli liczbowych opisach znaczenia zdania. Sprawdzimy, czy rozwinięcie wyników po powiązaniach w grafie wiedzy poprawia ich jakość, i które typy powiązań pomagają, a które szkodzą. Eksperyment jest planowany i niczego jeszcze nie zmierzono.

## Pytanie i hipoteza

Pytanie: czy wyszukiwanie, które dodatkowo rozwija wyniki po krawędziach grafu, daje lepsze wyniki niż samo wyszukiwanie po osadzeniach, i czy wszystkie typy krawędzi pomagają w równym stopniu. Hipoteza i próg powstaną w karcie hipotezy.

## Prerejestracja

Brak karty hipotezy. Karta zostanie zamrożona i opublikowana przed pierwszym pomiarem.

## Dane

Planowany jest korpus publiczny i ręcznie przygotowany zbiór pytań ze złotymi odpowiedziami. Źródła trafią na listę dozwolonych z uzasadnieniem i podstawą prawną.

## Metoda

Porównanie wyszukiwania samymi osadzeniami z wyszukiwaniem, które rozwija wyniki po krawędziach grafu, oraz porównanie typów krawędzi. Metryką rozstrzygającą będzie nDCG@10. Eksperyment zależy od ukończenia pierwszego eksperymentu (F3) i wyboru kandydatów (F5.3).

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

Ograniczenia zapiszemy w karcie hipotezy. Już dziś wiadomo, że wynik będzie dotyczył jednego korpusu i jednego zbioru pytań przygotowanego ręcznie.

## Źródła

Brak.
