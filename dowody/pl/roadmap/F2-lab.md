---
id: F2
lang: pl
counterpart: ../../en/roadmap/F2-lab.md
status: doing
provenance: ai_authored
provenance_metadata: {agent: "Claude Opus 5.5 (Cowork)", date: 2026-09-27, human_validated: false}
---

# F2. Laboratorium i zapis cyklu

[← Roadmapa](../02-roadmap.md)

> **Status: w toku** · stan na 30 września 2026
>
> 9 z 10 zadań jest zrobionych, a 1 jest w toku: F2.4 (obsługa kart hipotez i prerejestracja). Laboratorium działa na serwerze: ma własną bazę odgrodzoną od danych prywatnych, listę dozwolonych źródeł, tabele eksperymentów, procesory kart i decyzji, eksport wyników, zadania na żądanie i ocenianie na ślepo. Do zamknięcia F2.4, a z nią fazy, brakuje przejścia na plikach karty testowej `toy-length`, która czeka na zatwierdzenie przez właściciela. Według wpisu w F2.7 dossier (pełny opis) eksperymentu zabawkowego, czyli próbnego eksperymentu do sprawdzania mechanizmów laboratorium, zostało zatrzymane przez bramkę publikacji (automatyczną kontrolę przed publikacją) i też czeka na przegląd właściciela.

## W skrócie

Faza F2 buduje laboratorium: osobne, odgrodzone miejsce na serwerze, w którym system przyjmuje tylko dozwolone publiczne materiały, zapisuje hipotezy przed sprawdzeniem, prowadzi eksperymenty i składa z wyników strony do przeczytania. Laboratorium nie ma dostępu do niczego prywatnego. Bez niego następne fazy nie miałyby gdzie liczyć ani czego opublikować.

## Po co ta faza

Kolejne fazy planu prac (roadmapy) prowadzą eksperymenty, a wszystko, co z nich wynika, jest publiczne. Potrzebne jest do tego miejsce, które niczego prywatnego nie ujawni, nawet przez pomyłkę, i które zapisuje, kiedy powstała każda hipoteza, jakie progi sukcesu przyjęto i co wyszło. Bez tej fazy nie byłoby ani bezpiecznego miejsca do pracy, ani zapisu, który obcy czytelnik może sprawdzić.

## Cel

Osobna instancja Exocortexa (naszego systemu, który zamienia teksty na sieć powiązań między twierdzeniami), która przyjmuje tylko dozwolone źródła i nie ma dostępu do niczego prywatnego. Uczymy ją rozumieć karty hipotez i decyzje z bramek (punktów kontrolnych, na których człowiek wybiera dalszy krok), zapisywać eksperymenty i ich wyniki, a potem składać z tego strony wynikowe, które publikator, czyli program wysyłający pliki do publicznego repozytorium, wysyła razem z resztą.

## Faza jest skończona, gdy

- test pokazuje, że procesy laboratorium nie mogą połączyć się z prywatną bazą,
- zatwierdzona karta hipotezy w `dowody/` pojawia się w grafie laboratorium z sumą kontrolną (krótkim odciskiem treści), a w repozytorium z zapisem prerejestracji (hipoteza i progi sukcesu zapisane przed pomiarem),
- przykładowy eksperyment przechodzi przez kolejkę, jego wyniki są w tabelach, a strona z dossier (pełnym opisem eksperymentu) i surowe dane są w repozytorium,
- strona ze stanem wszystkich zadań roadmapy generuje się sama.

## Zadania

| Id | Zadanie | Status | Zależy od | Szacunek |
|---|---|---|---|---|
| [F2.1](F2/F2.1-lab-database.md) | Osobna baza i procesy laboratorium | zrobione | – | 4 h |
| [F2.2](F2/F2.2-source-allowlist.md) | Lista dozwolonych źródeł | zrobione | F2.1 | 4 h |
| [F2.3](F2/F2.3-schemas-and-templates.md) | Schematy nagłówków i ostateczne szablony | zrobione | – | 4 h |
| [F2.4](F2/F2.4-hypothesis-processor.md) | Obsługa kart hipotez i prerejestracja | w toku | F2.2, F2.3 | 1 dzień |
| [F2.5](F2/F2.5-gate-processor.md) | Obsługa decyzji z bramek | zrobione | F2.4 | 4 h |
| [F2.6](F2/F2.6-experiment-tables.md) | Tabele eksperymentów i blokada zbioru kontrolnego | zrobione | F2.1 | 1 dzień |
| [F2.7](F2/F2.7-compile-domain.md) | Strony wynikowe i stan roadmapy | zrobione | F2.4, F2.5, F2.6 | 1 dzień |
| [F2.8](F2/F2.8-results-export.md) | Eksport surowych wyników | zrobione | F2.6 | 4 h |
| [F2.9](F2/F2.9-on-demand-jobs.md) | Zadania laboratorium na żądanie | zrobione | F2.6 | 4 h |
| [F2.10](F2/F2.10-blind-rating-interface.md) | Ocenianie na ślepo w interfejsie właściciela | zrobione | F2.6, F3.5 | 1 dzień |
| [F2.11](F2/F2.11-desk-counters-and-tiles.md) | Biurko: liczniki i kafle zamiast tabel | zrobione | F2.10 | 4 h |
