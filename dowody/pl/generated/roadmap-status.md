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
| [F0](../roadmap/F0-leaks-and-gate.md) | 7 | 5 | 2 | 0 |
| [F1](../roadmap/F1-public-repo.md) | 10 | 6 | 4 | 0 |
| [F2](../roadmap/F2-lab.md) | 8 | 5 | 1 | 2 |
| [F3](../roadmap/F3-first-pass.md) | 10 | 4 | 1 | 5 |
| [F4](../roadmap/F4-reference-card.md) | 4 | 0 | 0 | 4 |
| [F5](../roadmap/F5-radar-and-experiments.md) | 7 | 1 | 0 | 6 |
| [F6](../roadmap/F6-scale-and-collaboration.md) | 6 | 0 | 0 | 6 |
| [F7](../roadmap/F7-public-demo.md) | 6 | 0 | 0 | 6 |

## F0. Zatrzymanie wycieków i bramka publikacji

| Id | Zadanie | Stan | Zależy od | Czeka na |
|---|---|---|---|---|
| [F0.1](../roadmap/F0/F0.1-close-leaking-channels.md) | Wyłączyć publiczny dostęp do artefaktów sprzed zasad | w toku | — | — |
| [F0.2](../roadmap/F0/F0.2-exposure-audit.md) | Spisać i sprawdzić wszystkie publiczne miejsca | zrobione | F0.1 | — |
| [F0.3](../roadmap/F0/F0.3-denylist.md) | Lista zakazanych nazw i jej wersja w skrótach | zrobione | F0.2 | — |
| [F0.4](../roadmap/F0/F0.4-scanner-text-and-files.md) | Skaner tekstu i plików | zrobione | F0.3 | — |
| [F0.5](../roadmap/F0/F0.5-scanner-build-artifacts.md) | Skaner paczek i obrazów kontenerów | zrobione | F0.4 | — |
| [F0.6](../roadmap/F0/F0.6-similarity-check.md) | Porównanie z prywatnym korpusem | zrobione | F0.4 | — |
| [F0.7](../roadmap/F0/F0.7-gate-self-test.md) | Test bramki uruchamiany co noc | w toku | F0.4, F0.5, F0.6 | — |

## F1. Publiczne repozytorium i ciągła publikacja

| Id | Zadanie | Stan | Zależy od | Czeka na |
|---|---|---|---|---|
| [F1.1](../roadmap/F1/F1.1-repo-shape-decision.md) | Jak powstaje publiczne repozytorium | zrobione | F0 | — |
| [F1.2](../roadmap/F1/F1.2-create-repos.md) | Przemianować obecne repozytorium i założyć nowe | w toku | F1.1 | — |
| [F1.3](../roadmap/F1/F1.3-clean-export.md) | Eksport kodu przez listę dozwolonych ścieżek | zrobione | F1.2 | — |
| [F1.4](../roadmap/F1/F1.4-code-to-english-tool.md) | Narzędzie do tłumaczenia komentarzy i docstringów | zrobione | F1.3 | — |
| [F1.5](../roadmap/F1/F1.5-code-to-english-review.md) | Tłumaczenie katalog po katalogu | zrobione | F1.4 | — |
| [F1.6](../roadmap/F1/F1.6-clean-builds.md) | Obraz i paczka z czystego repozytorium | w toku | F1.3, F0.5 | — |
| [F1.7](../roadmap/F1/F1.7-bilingual-convention.md) | Konwencja dwujęzyczna i test parzystości | zrobione | F1.2 | — |
| [F1.8](../roadmap/F1/F1.8-human-language-lint.md) | Sprawdzanie tekstu pod kątem nawyków modeli językowych | zrobione | F1.7 | — |
| [F1.9](../roadmap/F1/F1.9-continuous-publisher.md) | Publikator | w toku | F0.7, F1.7, F1.8 | F0.7 |
| [F1.10](../roadmap/F1/F1.10-first-publication.md) | Pierwsza publikacja i poprawa odnośników | w toku | F1.9 | F1.9 |

## F2. Laboratorium i zapis cyklu

| Id | Zadanie | Stan | Zależy od | Czeka na |
|---|---|---|---|---|
| [F2.1](../roadmap/F2/F2.1-lab-database.md) | Osobna baza i procesy laboratorium | zrobione | F1 | — |
| [F2.2](../roadmap/F2/F2.2-source-allowlist.md) | Lista dozwolonych źródeł | zrobione | F2.1 | — |
| [F2.3](../roadmap/F2/F2.3-schemas-and-templates.md) | Schematy nagłówków i ostateczne szablony | zrobione | F1.7 | — |
| [F2.4](../roadmap/F2/F2.4-hypothesis-processor.md) | Obsługa kart hipotez i prerejestracja | w toku | F2.2, F2.3 | — |
| [F2.5](../roadmap/F2/F2.5-gate-processor.md) | Obsługa decyzji z bramek | zrobione | F2.4 | — |
| [F2.6](../roadmap/F2/F2.6-experiment-tables.md) | Tabele eksperymentów i blokada zbioru kontrolnego | zrobione | F2.1 | — |
| [F2.7](../roadmap/F2/F2.7-compile-domain.md) | Strony wynikowe i stan roadmapy | do zrobienia | F2.4, F2.5, F2.6 | F2.4 |
| [F2.8](../roadmap/F2/F2.8-results-export.md) | Eksport surowych wyników | do zrobienia | F2.6 | — |

## F3. Pierwsze pełne przejście cyklu

| Id | Zadanie | Stan | Zależy od | Czeka na |
|---|---|---|---|---|
| [F3.1](../roadmap/F3/F3.1-public-corpus-selection.md) | Wybór korpusu publicznego | zrobione | F2.2 | — |
| [F3.2](../roadmap/F3/F3.2-corpus-manifest.md) | Pobranie korpusu i manifest | zrobione | F3.1 | — |
| [F3.3](../roadmap/F3/F3.3-extractor-port.md) | Ekstraktor twierdzeń w laboratorium | zrobione | F2.6 | — |
| [F3.4](../roadmap/F3/F3.4-hypothesis-card.md) | Karta hipotezy i prerejestracja | w toku | F3.2, F3.3, F2.4 | F2.4 |
| [F3.5](../roadmap/F3/F3.5-blind-sample-tool.md) | Ślepa próba i ocenianie | zrobione | F2.6 | — |
| [F3.6](../roadmap/F3/F3.6-tier-s-and-g1.md) | Szybki test i bramka G1 | do zrobienia | F3.4, F3.5 | F3.4 |
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
| [F5.1](../roadmap/F5-radar-and-experiments.md) | Radar okazji | do zrobienia (opis w dokumencie fazy) | F2, F3 | F2, F3 |
| [F5.2](../roadmap/F5-radar-and-experiments.md) | Nowe kanały źródłowe | zrobione (opis w dokumencie fazy) | F2 | — |
| [F5.3](../roadmap/F5-radar-and-experiments.md) | Wybór kandydatów z oceną kilku modeli | do zrobienia (opis w dokumencie fazy) | F5 | F5 |
| [F5.4](../roadmap/F5-radar-and-experiments.md) | Comiesięczny pomiar nowych modeli | do zrobienia (opis w dokumencie fazy) | F3 | F3 |
| [F5.5](../roadmap/F5-radar-and-experiments.md) | Eksperyment: czy graf poprawia wyszukiwanie | do zrobienia (opis w dokumencie fazy) | F3, F5 | F3, F5 |
| [F5.6](../roadmap/F5-radar-and-experiments.md) | Eksperyment: lokalny model embeddingów a model chmurowy | do zrobienia (opis w dokumencie fazy) | F5 | F5 |
| [F5.7](../roadmap/F5-radar-and-experiments.md) | Eksperyment: wymuszanie formatu odpowiedzi | do zrobienia (opis w dokumencie fazy) | F3 | F3 |

## F6. Skala i współpraca

| Id | Zadanie | Stan | Zależy od | Czeka na |
|---|---|---|---|---|
| [F6.1](../roadmap/F6-scale-and-collaboration.md) | Drugi ekspert | do zrobienia (opis w dokumencie fazy) | F3 | F3 |
| [F6.2](../roadmap/F6-scale-and-collaboration.md) | Moc obliczeniowa na żądanie | do zrobienia (opis w dokumencie fazy) | F2 | F2 |
| [F6.3](../roadmap/F6-scale-and-collaboration.md) | Dokumenty skali L | do zrobienia (opis w dokumencie fazy) | F3 | F3 |
| [F6.4](../roadmap/F6-scale-and-collaboration.md) | Strona laboratorium | do zrobienia (opis w dokumencie fazy) | F2 | F2 |
| [F6.5](../roadmap/F6-scale-and-collaboration.md) | Wydania z DOI | do zrobienia (opis w dokumencie fazy) | F1 | F1 |
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
