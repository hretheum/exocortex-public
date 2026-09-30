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

> **Status: w toku** · stan na 30 września 2026
>
> Zrobione jest 5 z 10 zadań (F3.1 do F3.5): korpus, czyli zbiór dokumentów do badania, jest pobrany i opisany, ekstraktor twierdzeń działa w laboratorium, narzędzie do oceny na ślepo jest sprawdzone, a karta hipotezy jest zamrożona. Szybki test (F3.6) jest w toku: 30 września ekstrakcja na próbie strojenia przeszła bez błędów, a strona oceny na ślepo czeka na oceniającego. Zadania F3.7 do F3.10 czekają na wynik F3.6 i decyzję bramki G1.

## W skrócie

Pierwszy eksperyment laboratorium sprawdza, czy program wyciągający z tekstu pojedyncze twierdzenia odróżnia fakty od planów i przypuszczeń. Jeśli nie odróżnia, plan trafia dalej jako rzecz już zrobiona. Pracujemy na około 2500 abstraktach (krótkich streszczeniach autorów) artykułów naukowych z serwisu arXiv i na polskich streszczeniach tych artykułów, które zrobił nasz silnik, czyli program Exocortex budujący graf wiedzy z dokumentów. Każdy krok, od karty hipotezy do raportu, jest publiczny.

## Po co ta faza

Laboratorium ma sens dopiero wtedy, gdy widać, że cały cykl działa od początku do końca: od postawienia pytania, przez pomiar, po raport, który ktoś z zewnątrz może sprawdzić. Zamiast budować narzędzia na zapas, przeprowadzamy jeden prawdziwy eksperyment i notujemy, co się po drodze psuje. Temat ma praktyczne znaczenie: gdy program streszcza plan firmy jako coś już zrobionego, czytelnik wyciąga błędne wnioski i na ich podstawie podejmuje decyzje. Bez tej fazy laboratorium byłoby zbiorem narzędzi, o których nie wiadomo, czy działają razem.

## Cel

Jeden eksperyment przeprowadzony przez cały cykl, od karty hipotezy do raportu, w całości na widoku publicznym. Wybraliśmy temat, do którego Exocortex ma gotowe narzędzia: wyciąganie twierdzeń z dokumentów wraz z informacją, czy zdanie opisuje fakt, plan, wymóg czy hipotezę. Częstym błędem modeli językowych jest opisywanie zamierzeń jako rzeczy już zrobionych, a w dokumentach strategicznych i planistycznych jest ich pełno.

Korpusem (zbiorem dokumentów, na którym pracujemy) są abstrakty artykułów z arXiv na licencji CC0, które Exocortex już pobrał (około 2500), oraz polskie streszczenia tych artykułów zrobione przez silnik. W abstraktach fakty (co zmierzono) sąsiadują z hipotezami i zapowiedziami (co proponujemy, co może zadziałać), więc dobrze nadają się do tego pomiaru. Streszczenia dają drugie pytanie, o nasz własny sposób przetwarzania tekstów: czy przy streszczaniu zamiar albo hipoteza nie zamienia się w fakt. Korpus jest pod ręką, więc nie czekamy na zbieranie nowych dokumentów. Polskie dokumenty urzędowe, planowane tu wcześniej, zostają kandydatem na kolejny eksperyment.

Ten eksperyment jest też próbą wszystkich narzędzi publikacji i laboratorium. Tam, gdzie coś nie zadziała, poprawiamy narzędzia, a poprawkę zapisujemy w dzienniku eksperymentu.

## Faza jest skończona, gdy

- karta hipotezy jest zamrożona i opublikowana przed pierwszym pomiarem,
- decyzje z bramek G1 i (jeśli do niej dojdzie) G2 są opublikowane razem z wynikami, na których się opierają,
- raport w obu językach, surowe dane i skrypt do przeliczenia wyników są w repozytorium,
- osoba z zewnątrz może, mając tylko repozytorium, pobrać korpus, uruchomić przeliczenie i dostać te same liczby.

## Zadania

| Id | Zadanie | Status | Zależy od | Szacunek |
|---|---|---|---|---|
| [F3.1](F3/F3.1-public-corpus-selection.md) | Wybór korpusu publicznego i sprawdzenie podstaw prawnych | zrobione | F2.2 | 4 h |
| [F3.2](F3/F3.2-corpus-manifest.md) | Pobranie korpusu i manifest | zrobione | F3.1 | 4 h |
| [F3.3](F3/F3.3-extractor-port.md) | Przeniesienie ekstraktora twierdzeń do laboratorium | zrobione | F2.6 | 1 dzień |
| [F3.4](F3/F3.4-hypothesis-card.md) | Karta hipotezy i prerejestracja | zrobione | F3.2, F3.3, F2.4 | 2 h |
| [F3.5](F3/F3.5-blind-sample-tool.md) | Narzędzie do ślepej próby i oceniania | zrobione | F2.6 | 4 h |
| [F3.6](F3/F3.6-tier-s-and-g1.md) | Szybki test i bramka G1 | w toku | F3.4, F3.5, F2.9, F2.10 | 1 dzień |
| [F3.7](F3/F3.7-tier-m-runs.md) | Pilot: macierz konfiguracji | do zrobienia | F3.6 (GO) | 1 dzień |
| [F3.8](F3/F3.8-tier-m-labeling-and-taxonomy.md) | Pilot: ocena ślepej próby i spis błędów | do zrobienia | F3.7 | 1 dzień |
| [F3.9](F3/F3.9-judge-calibration.md) | Pilot: kalibracja sędziego automatycznego | do zrobienia | F3.8 | 4 h |
| [F3.10](F3/F3.10-g2-and-report.md) | Bramka G2 i raport | do zrobienia | F3.8, F3.9 | 4 h |

Jeśli na G1 zapadnie decyzja inna niż `GO`, zadania F3.7 do F3.9 przepadają, a F3.10 pisze raport z wyniku szybkiego testu.
