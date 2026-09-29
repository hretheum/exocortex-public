---
id: local-vs-cloud-embeddings-overview
lang: pl
counterpart: ../../../en/experiments/local-vs-cloud-embeddings/overview.md
status: planned
roadmap: F5.6
stage: 0
tier: S
tagline: "Czy lokalny nie ustępuje chmurowemu."
updated: 2026-09-28
provenance: ai_authored
provenance_metadata:
  agent: Claude Sonnet 5.5 (Cowork)
  date: 2026-09-28
  human_validated: false
---

# Model lokalny czy chmurowy

## Streszczenie

Wyszukiwanie tekstów wymaga modelu osadzeń (ang. embeddings). Sprawdzimy, czy model uruchamiany lokalnie daje wyniki wyszukiwania nie gorsze niż model chmurowy na polskim korpusie publicznym. Eksperyment jest planowany i niczego jeszcze nie zmierzono.

## Pytanie i hipoteza

Pytanie: czy lokalny model osadzeń jest równoważny chmurowemu. To hipoteza równoważności: próg dopuszczalnej różnicy zapiszemy w karcie hipotezy przed pomiarem.

## Prerejestracja

Brak karty hipotezy. Karta zostanie zamrożona i opublikowana przed pierwszym pomiarem.

## Dane

Polski korpus publiczny. Do modelu chmurowego wysyłamy wyłącznie teksty publiczne. Źródła trafią na listę dozwolonych z uzasadnieniem i podstawą prawną.

## Metoda

Te same zapytania i ten sam korpus dla obu modeli, porównanie jakości wyszukiwania z przedziałami ufności i test równoważności z progiem z karty. Eksperyment zależy od poprzedniego (F5.5).

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

Ograniczenia zapiszemy w karcie hipotezy. Już dziś wiadomo, że wynik będzie dotyczył konkretnych modeli i jednego korpusu, a modele chmurowe zmieniają się bez uprzedzenia.

## Źródła

Brak.
