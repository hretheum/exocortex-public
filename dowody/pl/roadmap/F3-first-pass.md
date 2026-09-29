---
id: F3
lang: pl
counterpart: ../../en/roadmap/F3-first-pass.md
status: doing
provenance: ai_authored
provenance_metadata: {agent: "Claude Opus 5.5 (Cowork)", date: 2026-09-28, human_validated: false}
---

# F3. Pierwsze pełne przejście cyklu

[← Roadmapa](../02-roadmap.md)

## Cel

Jeden eksperyment przeprowadzony przez cały cykl, od karty hipotezy do raportu, w całości na widoku publicznym. Wybraliśmy temat, do którego Exocortex ma gotowe narzędzia: wyciąganie twierdzeń z dokumentów wraz z informacją, czy zdanie opisuje fakt, plan, wymóg czy hipotezę. Częstym błędem modeli językowych jest opisywanie zamierzeń jako rzeczy już zrobionych, a w dokumentach strategicznych i planistycznych jest ich pełno.

Korpusem są abstrakty artykułów z arXiv, które Exocortex już pobrał (około 2500), oraz polskie streszczenia tych artykułów zrobione przez silnik. W abstraktach fakty (co zmierzono) sąsiadują z hipotezami i zapowiedziami (co proponujemy, co może zadziałać), więc dobrze nadają się do tego pomiaru. Streszczenia dają drugie pytanie, o nasz własny potok: czy przy streszczaniu zamiar albo hipoteza nie zamienia się w fakt. Korpus jest pod ręką, więc nie czekamy na zbieranie nowych dokumentów. Polskie dokumenty urzędowe, planowane tu wcześniej, zostają kandydatem na kolejny eksperyment.

Ten eksperyment jest też próbą całej maszynerii z F0 do F2. Tam, gdzie coś nie zadziała, poprawiamy maszynerię, a poprawkę zapisujemy w dzienniku eksperymentu.

## Faza jest skończona, gdy

- karta hipotezy jest zamrożona i opublikowana przed pierwszym pomiarem,
- decyzje z bramek G1 i (jeśli do niej dojdzie) G2 są opublikowane razem z wynikami, na których się opierają,
- raport w obu językach, surowe dane i skrypt do przeliczenia wyników są w repozytorium,
- osoba z zewnątrz może, mając tylko repozytorium, pobrać korpus, uruchomić przeliczenie i dostać te same liczby.

## Zadania

| Id | Zadanie | Zależy od | Szacunek |
|---|---|---|---|
| [F3.1](F3/F3.1-public-corpus-selection.md) | Wybór korpusu publicznego i sprawdzenie podstaw prawnych | F2.2 | 4 h |
| [F3.2](F3/F3.2-corpus-manifest.md) | Pobranie korpusu i manifest | F3.1 | 4 h |
| [F3.3](F3/F3.3-extractor-port.md) | Przeniesienie ekstraktora twierdzeń do laboratorium | F2.6 | 1 dzień |
| [F3.4](F3/F3.4-hypothesis-card.md) | Karta hipotezy i prerejestracja | F3.2, F3.3, F2.4 | 2 h |
| [F3.5](F3/F3.5-blind-sample-tool.md) | Narzędzie do ślepej próby i oceniania | F2.6 | 4 h |
| [F3.6](F3/F3.6-tier-s-and-g1.md) | Szybki test i bramka G1 | F3.4, F3.5 | 1 dzień |
| [F3.7](F3/F3.7-tier-m-runs.md) | Pilot: macierz konfiguracji | F3.6 (GO) | 1 dzień |
| [F3.8](F3/F3.8-tier-m-labeling-and-taxonomy.md) | Pilot: ocena ślepej próby i spis błędów | F3.7 | 1 dzień |
| [F3.9](F3/F3.9-judge-calibration.md) | Pilot: kalibracja sędziego automatycznego | F3.8 | 4 h |
| [F3.10](F3/F3.10-g2-and-report.md) | Bramka G2 i raport | F3.8, F3.9 | 4 h |

Jeśli na G1 zapadnie decyzja inna niż `GO`, zadania F3.7 do F3.9 przepadają, a F3.10 pisze raport z wyniku szybkiego testu.
