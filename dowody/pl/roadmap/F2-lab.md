---
id: F2
lang: pl
counterpart: ../../en/roadmap/F2-lab.md
status: todo
provenance: ai_authored
provenance_metadata: {agent: "Claude Opus 5.5 (Cowork)", date: 2026-09-27, human_validated: false}
---

# F2. Laboratorium i zapis cyklu

[← Roadmapa](../02-roadmap.md)

## Cel

Osobna instancja Exocortexa, która przyjmuje tylko dozwolone źródła i nie ma dostępu do niczego prywatnego. Uczymy ją rozumieć karty hipotez i decyzje z bramek, zapisywać eksperymenty i ich wyniki, a potem składać z tego strony wynikowe, które publikator wysyła do repozytorium razem z resztą.

## Faza jest skończona, gdy

- test pokazuje, że procesy laboratorium nie mogą połączyć się z prywatną bazą,
- zatwierdzona karta hipotezy w `dowody/` pojawia się w grafie laboratorium z sumą kontrolną, a w repozytorium z zapisem prerejestracji,
- przykładowy eksperyment przechodzi przez kolejkę, jego wyniki są w tabelach, a strona z dossier i surowe dane są w repozytorium,
- strona ze stanem wszystkich zadań roadmapy generuje się sama.

## Zadania

| Id | Zadanie | Zależy od | Szacunek |
|---|---|---|---|
| [F2.1](F2/F2.1-lab-database.md) | Osobna baza i procesy laboratorium | F1 | 4 h |
| [F2.2](F2/F2.2-source-allowlist.md) | Lista dozwolonych źródeł | F2.1 | 4 h |
| [F2.3](F2/F2.3-schemas-and-templates.md) | Schematy nagłówków i ostateczne szablony | F1.7 | 4 h |
| [F2.4](F2/F2.4-hypothesis-processor.md) | Obsługa kart hipotez i prerejestracja | F2.2, F2.3 | 1 dzień |
| [F2.5](F2/F2.5-gate-processor.md) | Obsługa decyzji z bramek | F2.4 | 4 h |
| [F2.6](F2/F2.6-experiment-tables.md) | Tabele eksperymentów i blokada zbioru kontrolnego | F2.1 | 1 dzień |
| [F2.7](F2/F2.7-compile-domain.md) | Strony wynikowe i stan roadmapy | F2.4, F2.5, F2.6 | 1 dzień |
| [F2.8](F2/F2.8-results-export.md) | Eksport surowych wyników | F2.6 | 4 h |
