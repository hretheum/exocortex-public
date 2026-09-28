---
id: F6
lang: pl
counterpart: ../../en/roadmap/F6-scale-and-collaboration.md
status: todo
provenance: ai_authored
provenance_metadata: {agent: "Claude Opus 5.5 (Cowork)", date: 2026-09-27, human_validated: false}
---

# F6. Skala i współpraca

[← Roadmapa](../02-roadmap.md)

## Cel

Laboratorium przestaje być projektem jednej osoby i jednego serwera. Dochodzi drugi ekspert, wynajmowana moc obliczeniowa dla danych publicznych, dokumenty skali L i trwałe, cytowalne wydania.

Zadania są opisane tutaj, bez osobnych plików.

## Faza jest skończona, gdy

Drugi ekspert ma zatwierdzone co najmniej dwie decyzje z bramek i ocenił co najmniej jedną ślepą próbę, istnieje co najmniej jeden dokument skali L, a wydania repozytorium mają numery DOI.

## Zadania

### F6.1. Drugi ekspert

Zasady współpracy (pull requesty do repozytorium, zatwierdzanie bramek, ocena ślepych prób), dostęp tylko do odczytu do laboratorium przez MCP po HTTP z tokenem ograniczonym do laboratorium. Druga osoba oceniająca pozwala policzyć zgodność oceniających, która wzmacnia każdy wynik. Gotowe, gdy druga osoba oceniła jedną próbę i policzono zgodność. Zależy od F3.

### F6.2. Moc obliczeniowa na żądanie

Wynajmowane GPU dla dużych macierzy konfiguracji, dopuszczalne wyłącznie dla prób o klasie `public`. Reguła „klasa danych i dozwoleni dostawcy” zapisana w konfiguracji routera modeli, sprawdzana przed każdym wywołaniem. Gotowe, gdy jedna macierz przeszła na wynajętym GPU, a próba z inną klasą danych została odrzucona. Zależy od F2.6.

### F6.3. Dokumenty skali L

Generator dokumentu wdrożenia w dużej organizacji z szablonu (`templates/runbook-l.md`), z liczbami wyliczonymi z pomiarów pilota i wzorem przy każdej liczbie. Gotowe, gdy powstał dokument dla eksperymentu, który przeszedł G2. Zależy od F3.10.

### F6.4. Strona laboratorium

Strona lab.exocortex.zone w obu językach (`/en` i `/pl`, adres główny przekierowuje do `/en`), generowana z repozytorium: opis działania, lista hipotez ze statusami, dossier każdej hipotezy (streszczenie, prerejestracja, dane z sumami kontrolnymi i plikami do pobrania, przebiegi, wyniki, decyzje z bramek, odstępstwa, powtórzenie, ograniczenia, sposób cytowania) i stan roadmapy. Strona jest statyczna i działa na GitHub Pages w osobnym, małym repozytorium, bo exocortex.zone zajmuje jedyną stronę Pages repozytorium głównego. Generator jest w katalogu `lab-site/`. Gotowe, gdy strona aktualizuje się sama po każdej publikacji. Zależy od F2.7.

### F6.5. Wydania z DOI

Integracja repozytorium z Zenodo: każde wydanie dostaje trwały identyfikator i archiwalną kopię, którą można zacytować w dokumentach. Gotowe, gdy pierwsze wydanie ma DOI. Zależy od F1.

### F6.6. Kelter jako wykonawca eksperymentów agentowych

Eksperymenty, w których model wykonuje wieloetapowe zadania z narzędziami, uruchamiane w Kelterze. Gotowe, gdy jeden eksperyment agentowy przeszedł przez kolejkę laboratorium. Zależy od F2.6.
