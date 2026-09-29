---
id: F1
lang: pl
counterpart: ../../en/roadmap/F1-public-repo.md
status: doing
provenance: ai_authored
provenance_metadata: {agent: "Claude Opus 5.5 (Cowork)", date: 2026-09-27, human_validated: false}
---

# F1. Publiczne repozytorium i ciągła publikacja

[← Roadmapa](../02-roadmap.md)

## Cel

Jedno publiczne repozytorium, w którym w każdej chwili widać cały mechanizm: kod silnika i laboratorium, dokumentację, roadmapę ze stanem zadań i wyniki. Powstaje od nowa, z czystą historią, z eksportu kodu przez listę dozwolonych ścieżek. Obecne repozytorium zostaje prywatne jako miejsce pracy nad instancją prywatną.

Po drodze kod dostaje angielskie komentarze i docstringi, dokumenty dostają pary PL i EN, a na serwerze zaczyna działać publikator, który co kwadrans przenosi zmiany z vaulta do repozytorium przez bramkę z F0.

## Faza jest skończona, gdy

- repozytorium jest publiczne i niezalogowany użytkownik widzi kod, dokumenty w obu językach i roadmapę,
- obraz kontenera i paczka są budowane z tego repozytorium i przechodzą skaner przed wysłaniem,
- zmiana w vaulcie pojawia się w repozytorium najpóźniej po 30 minutach, a plik, który nie przechodzi bramki, zostaje zatrzymany z powiadomieniem,
- odnośniki na exocortex.zone i w metadanych paczki prowadzą do działającego repozytorium.

## Zadania

| Id | Zadanie | Zależy od | Szacunek |
|---|---|---|---|
| [F1.1](F1/F1.1-repo-shape-decision.md) | Zdecydować, jak powstaje publiczne repozytorium | F0 | 1 h |
| [F1.2](F1/F1.2-create-repos.md) | Przemianować obecne repozytorium i założyć nowe publiczne | F1.1 | 2 h |
| [F1.3](F1/F1.3-clean-export.md) | Eksport kodu przez listę dozwolonych ścieżek | F1.2 | 1 dzień |
| [F1.4](F1/F1.4-code-to-english-tool.md) | Narzędzie do tłumaczenia komentarzy i docstringów | F1.3 | 4 h |
| [F1.5](F1/F1.5-code-to-english-review.md) | Tłumaczenie katalog po katalogu (zadanie seryjne) | F1.4 | seria, ok. 1 h na katalog |
| [F1.6](F1/F1.6-clean-builds.md) | Budowanie obrazu i paczki z czystego repozytorium | F1.3, F0.5 | 4 h |
| [F1.7](F1/F1.7-bilingual-convention.md) | Konwencja dwujęzyczna, słownik terminów, test parzystości | F1.2 | 1 dzień |
| [F1.8](F1/F1.8-human-language-lint.md) | Sprawdzanie tekstu pod kątem nawyków modeli językowych | F1.7 | 4 h |
| [F1.9](F1/F1.9-continuous-publisher.md) | Publikator | F0.7, F1.7, F1.8 | 1 dzień |
| [F1.10](F1/F1.10-first-publication.md) | Pierwsza publikacja i poprawa odnośników | F1.9 | 2 h |
| [F1.11](F1/F1.11-publication-classes.md) | Klasy publikacji i klasyfikacja ścieżek | F1.9 | 4 h |
| [F1.12](F1/F1.12-atomic-units.md) | Jednostki publikacji i pomijanie całych eksperymentów | F1.11 | 1 dzień |
| [F1.13](F1/F1.13-docs-exemption.md) | Wyłączenie dokumentacji projektu z testów bezpieczeństwa | F1.11 | 4 h |
| [F1.14](F1/F1.14-quarantine-store.md) | Baza kwarantanny, zatwierdzenia i lista wyłączeń | F1.12, F1.13 | 1 dzień |
| [F1.15](F1/F1.15-gate-desk.md) | Biurko przeglądu: usługa webowa i jednostka Quadlet | F1.14 | 2 dni |
| [F1.16](F1/F1.16-review-assistant.md) | Asystent przeglądu: podpowiedzi zamiast setek pozycji (tylko jeśli po F1.15 zostaje więcej niż ok. 20 pozycji dziennie) | F1.15 | 3 dni |
