---
id: generated-roadmap-status
lang: pl
counterpart: ../../en/generated/roadmap-status.md
generated: true
---

# Stan roadmapy

Strona powstaje automatycznie w laboratorium z nagłówków plików zadań (zadanie [F2.7](../roadmap/F2/F2.7-compile-domain.md)). Nie edytuje się jej ręcznie: stan zmienia się w pliku zadania.

| Faza | Zadań | Zrobione | W toku | Do zrobienia |
|---|---|---|---|---|
| [F2](../roadmap/F2-lab.md) | 10 | 9 | 1 | 0 |
| [F3](../roadmap/F3-first-pass.md) | 10 | 5 | 0 | 5 |
| [F4](../roadmap/F4-reference-card.md) | 4 | 0 | 0 | 4 |
| [F5](../roadmap/F5-radar-and-experiments.md) | 9 | 2 | 1 | 6 |
| [F6](../roadmap/F6-scale-and-collaboration.md) | 6 | 0 | 1 | 5 |
| [F7](../roadmap/F7-public-demo.md) | 6 | 0 | 0 | 6 |
| [F8](../roadmap/F8-interactive-lab.md) | 10 | 1 | 2 | 7 |

## F2. Laboratorium i zapis cyklu

| Id | Zadanie | Stan | Zależy od | Czeka na |
|---|---|---|---|---|
| [F2.1](../roadmap/F2/F2.1-lab-database.md) | Osobna baza i procesy laboratorium | zrobione | — | — |
| [F2.2](../roadmap/F2/F2.2-source-allowlist.md) | Lista dozwolonych źródeł | zrobione | F2.1 | — |
| [F2.3](../roadmap/F2/F2.3-schemas-and-templates.md) | Schematy nagłówków i ostateczne szablony | zrobione | — | — |
| [F2.4](../roadmap/F2/F2.4-hypothesis-processor.md) | Obsługa kart hipotez i prerejestracja | w toku | F2.2, F2.3 | — |
| [F2.5](../roadmap/F2/F2.5-gate-processor.md) | Obsługa decyzji z bramek | zrobione | F2.4 | — |
| [F2.6](../roadmap/F2/F2.6-experiment-tables.md) | Tabele eksperymentów i blokada zbioru kontrolnego | zrobione | F2.1 | — |
| [F2.7](../roadmap/F2/F2.7-compile-domain.md) | Strony wynikowe i stan roadmapy | zrobione | F2.4, F2.5, F2.6 | — |
| [F2.8](../roadmap/F2/F2.8-results-export.md) | Eksport surowych wyników | zrobione | F2.6 | — |
| [F2.9](../roadmap/F2/F2.9-on-demand-jobs.md) | Zadania laboratorium na żądanie | zrobione | F2.6 | — |
| [F2.10](../roadmap/F2/F2.10-blind-rating-interface.md) | Ocenianie na ślepo w interfejsie właściciela | zrobione | F2.6, F3.5 | — |

## F3. Pierwsze pełne przejście cyklu

| Id | Zadanie | Stan | Zależy od | Czeka na |
|---|---|---|---|---|
| [F3.1](../roadmap/F3/F3.1-public-corpus-selection.md) | Wybór korpusu publicznego | zrobione | F2.2 | — |
| [F3.2](../roadmap/F3/F3.2-corpus-manifest.md) | Pobranie korpusu i manifest | zrobione | F3.1 | — |
| [F3.3](../roadmap/F3/F3.3-extractor-port.md) | Ekstraktor twierdzeń w laboratorium | zrobione | F2.6 | — |
| [F3.4](../roadmap/F3/F3.4-hypothesis-card.md) | Karta hipotezy i prerejestracja | zrobione | F3.2, F3.3, F2.4 | — |
| [F3.5](../roadmap/F3/F3.5-blind-sample-tool.md) | Ślepa próba i ocenianie | zrobione | F2.6 | — |
| [F3.6](../roadmap/F3/F3.6-tier-s-and-g1.md) | Szybki test i bramka G1 | do zrobienia | F3.4, F3.5, F2.9, F2.10 | — |
| [F3.7](../roadmap/F3/F3.7-tier-m-runs.md) | Pilot: macierz konfiguracji | do zrobienia | F3.6 | F3.6 |
| [F3.8](../roadmap/F3/F3.8-tier-m-labeling-and-taxonomy.md) | Pilot: ocena ślepej próby i spis błędów | do zrobienia | F3.7 | F3.7 |
| [F3.9](../roadmap/F3/F3.9-judge-calibration.md) | Pilot: kalibracja sędziego automatycznego | do zrobienia | F3.8 | F3.8 |
| [F3.10](../roadmap/F3/F3.10-g2-and-report.md) | Bramka G2 i raport | do zrobienia | F3.8, F3.9 | F3.8, F3.9 |

## F4. Karta projektu referencyjnego z grafu

| Id | Zadanie | Stan | Zależy od | Czeka na |
|---|---|---|---|---|
| [F4.1](../roadmap/F4-reference-card.md) | Ogólny model karty | do zrobienia (opis w dokumencie fazy) | F2 | F2 |
| [F4.2](../roadmap/F4-reference-card.md) | Kompilator karty | do zrobienia (opis w dokumencie fazy) | F4 | F4 |
| [F4.3](../roadmap/F4-reference-card.md) | Sprawdzenie uczciwości tekstu karty | do zrobienia (opis w dokumencie fazy) | F4 | F4 |
| [F4.4](../roadmap/F4-reference-card.md) | Wypełnianie formularzy przetargowych | do zrobienia (opis w dokumencie fazy) | F4 | F4 |

## F5. Radar okazji i kolejne eksperymenty

| Id | Zadanie | Stan | Zależy od | Czeka na |
|---|---|---|---|---|
| [F5.1](../roadmap/F5-radar-and-experiments.md) | Radar okazji | w toku (opis w dokumencie fazy) | F2, F3 | F2, F3 |
| [F5.2](../roadmap/F5-radar-and-experiments.md) | Nowe kanały źródłowe | zrobione (opis w dokumencie fazy) | F2 | — |
| [F5.3](../roadmap/F5-radar-and-experiments.md) | Wybór kandydatów z oceną kilku modeli | zrobione (opis w dokumencie fazy) | F5 | — |
| [F5.4](../roadmap/F5-radar-and-experiments.md) | Comiesięczny pomiar nowych modeli | do zrobienia (opis w dokumencie fazy) | F3 | F3 |
| [F5.5](../roadmap/F5-radar-and-experiments.md) | Eksperyment: czy graf poprawia wyszukiwanie | do zrobienia (opis w dokumencie fazy) | F3, F5 | F3, F5 |
| [F5.6](../roadmap/F5-radar-and-experiments.md) | Eksperyment: lokalny model embeddingów a model chmurowy | do zrobienia (opis w dokumencie fazy) | F5 | F5 |
| [F5.7](../roadmap/F5-radar-and-experiments.md) | Eksperyment: wymuszanie formatu odpowiedzi | do zrobienia (opis w dokumencie fazy) | F3, F5 | F3, F5 |
| [F5.8](../roadmap/F5-radar-and-experiments.md) | Rodzaj eksperymentu: wyszukiwanie | do zrobienia (opis w dokumencie fazy) | F2 | F2 |
| [F5.9](../roadmap/F5-radar-and-experiments.md) | Rodzaj eksperymentu: zgodność formatu odpowiedzi | do zrobienia (opis w dokumencie fazy) | F2 | F2 |

## F6. Skala i współpraca

| Id | Zadanie | Stan | Zależy od | Czeka na |
|---|---|---|---|---|
| [F6.1](../roadmap/F6-scale-and-collaboration.md) | Drugi ekspert | do zrobienia (opis w dokumencie fazy) | F3 | F3 |
| [F6.2](../roadmap/F6-scale-and-collaboration.md) | Moc obliczeniowa na żądanie | do zrobienia (opis w dokumencie fazy) | F2 | F2 |
| [F6.3](../roadmap/F6-scale-and-collaboration.md) | Dokumenty skali L | do zrobienia (opis w dokumencie fazy) | F3 | F3 |
| [F6.4](../roadmap/F6-scale-and-collaboration.md) | Strona laboratorium | w toku (opis w dokumencie fazy) | F2 | F2 |
| [F6.5](../roadmap/F6-scale-and-collaboration.md) | Wydania z DOI | do zrobienia (opis w dokumencie fazy) | — | — |
| [F6.6](../roadmap/F6-scale-and-collaboration.md) | Kelter jako wykonawca eksperymentów agentowych | do zrobienia (opis w dokumencie fazy) | F2 | F2 |

## F7. Publiczne demo: baza wiedzy z badań

| Id | Zadanie | Stan | Zależy od | Czeka na |
|---|---|---|---|---|
| [F7.1](../roadmap/F7-public-demo.md) | Domena, źródła i scenariusz pokazu | do zrobienia (opis w dokumencie fazy) | F3 | F3 |
| [F7.2](../roadmap/F7-public-demo.md) | Model danych badawczych | do zrobienia (opis w dokumencie fazy) | F7 | F7 |
| [F7.3](../roadmap/F7-public-demo.md) | Wyciąganie ustaleń i hipotez z raportów | do zrobienia (opis w dokumencie fazy) | F7 | F7 |
| [F7.4](../roadmap/F7-public-demo.md) | Interfejs demo | do zrobienia (opis w dokumencie fazy) | F7 | F7 |
| [F7.5](../roadmap/F7-public-demo.md) | Test z odbiorcami | do zrobienia (opis w dokumencie fazy) | F7 | F7 |
| [F7.6](../roadmap/F7-public-demo.md) | Instrukcja zasilania własnymi badaniami | do zrobienia (opis w dokumencie fazy) | F7 | F7 |

## F8. Interaktywne laboratorium: zastosowania, pytania i GraphRAG

| Id | Zadanie | Stan | Zależy od | Czeka na |
|---|---|---|---|---|
| [F8.1](../roadmap/F8-interactive-lab.md) | Sekcja o zastosowaniach biznesowych | w toku (opis w dokumencie fazy) | F6 | F6 |
| [F8.2](../roadmap/F8-interactive-lab.md) | Publiczny pakiet grafu | w toku (opis w dokumencie fazy) | F2 | F2 |
| [F8.3](../roadmap/F8-interactive-lab.md) | Usługa pytań | do zrobienia (opis w dokumencie fazy) | F8 | F8 |
| [F8.4](../roadmap/F8-interactive-lab.md) | Interfejs pytań | do zrobienia (opis w dokumencie fazy) | F8 | F8 |
| [F8.5](../roadmap/F8-interactive-lab.md) | Kafelki sugestii | do zrobienia (opis w dokumencie fazy) | F8 | F8 |
| [F8.6](../roadmap/F8-interactive-lab.md) | Wejście pytań publiczności | do zrobienia (opis w dokumencie fazy) | F6 | F6 |
| [F8.7](../roadmap/F8-interactive-lab.md) | Ocena testowalności pytań | do zrobienia (opis w dokumencie fazy) | F8 | F8 |
| [F8.8](../roadmap/F8-interactive-lab.md) | Hipotezy pochodne | do zrobienia (opis w dokumencie fazy) | F8 | F8 |
| [F8.9](../roadmap/F8-interactive-lab.md) | Strona „Pytania” i powiązania w dossier | do zrobienia (opis w dokumencie fazy) | F8 | F8 |
| [F8.10](../roadmap/F8-interactive-lab.md) | Przepisanie tekstu „Jak to działa” dla odbiorcy biznesowego | zrobione (opis w dokumencie fazy) | — | — |
