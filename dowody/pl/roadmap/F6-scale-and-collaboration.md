---
id: F6
lang: pl
counterpart: ../../en/roadmap/F6-scale-and-collaboration.md
status: doing
task_status: {F6.4: doing}
provenance: ai_authored
provenance_metadata: {agent: "Claude Opus 5.5 (Cowork)", date: 2026-09-27, human_validated: false}
---

# F6. Skala i współpraca

[← Roadmapa](../02-roadmap.md)

> **Status: w toku** · stan na 30 września 2026
>
> Zadanie F6.4 (strona laboratorium) jest w toku, pięć pozostałych czeka, zrobionych zadań jeszcze nie ma (0 z 6). Strona lab.exocortex.zone jest opublikowana i odświeża się co godzinę, ale nie aktualizuje się jeszcze od razu po każdej publikacji, a tekst „Jak działa Exocortex R&D” pojawi się na niej po zwolnieniu dokumentu przez bramkę publikacji. Zadania F6.2, F6.5 i F6.6 nie mają niezałatwionych zależności i mogą ruszyć w każdej chwili, a F6.1 i F6.3 czekają na pierwszy eksperyment z F3.

## W skrócie

Ta faza sprawia, że laboratorium przestaje być projektem jednej osoby na jednym serwerze. Dochodzi druga osoba oceniająca wyniki, możliwość wynajęcia mocy obliczeniowej do dużych pomiarów, publiczna strona i trwałe, cytowalne wydania.

## Po co ta faza

Wynik oceniany przez jedną osobę trudno uznać za wiarygodny, bo nie wiadomo, czy ktoś inny oceniłby tak samo. Druga osoba pozwala policzyć zgodność ocen i wzmacnia każdy wynik. Trwały identyfikator DOI pozwala zacytować konkretne wydanie laboratorium, na przykład w ofercie, i mieć pewność, że pod tym odnośnikiem za rok będzie to samo. Strona lab.exocortex.zone to miejsce, do którego można odesłać kogoś, kto chce zobaczyć, co laboratorium robi i z czego wynikają jego wnioski.

## Cel

Laboratorium przestaje być projektem jednej osoby i jednego serwera. Dochodzi drugi ekspert, wynajmowana moc obliczeniowa dla danych publicznych, dokumenty skali L i trwałe, cytowalne wydania.

Zadania są opisane tutaj, bez osobnych plików.

## Faza jest skończona, gdy

Drugi ekspert ma zatwierdzone co najmniej dwie decyzje z bramek i ocenił co najmniej jedną ślepą próbę, istnieje co najmniej jeden dokument skali L, a wydania repozytorium mają numery DOI.

## Zadania

### F6.1. Drugi ekspert

**Status: do zrobienia** — nie zaczęte; czeka na pierwszy eksperyment (F3).

Po co: zgodność ocen dwóch osób pokazuje, na ile wynik zależy od tego, kto oceniał.

Zasady współpracy (pull requesty do repozytorium, zatwierdzanie bramek, ocena ślepych prób), dostęp tylko do odczytu do laboratorium przez MCP (protokół, którym asystenci AI czytają dane z zewnętrznych narzędzi) po HTTP z tokenem ograniczonym do laboratorium. Druga osoba oceniająca pozwala policzyć zgodność oceniających, która wzmacnia każdy wynik. Gotowe, gdy druga osoba oceniła jedną próbę i policzono zgodność. Zależy od F3.

### F6.2. Moc obliczeniowa na żądanie

**Status: do zrobienia** — nie zaczęte; zależność (F2.6) jest zrobiona, więc zadanie może ruszyć w każdej chwili.

Po co: duże macierze konfiguracji liczą się długo na jednym serwerze, a wynajęte GPU (karty graficzne do obliczeń modeli) je przyspieszają; reguła klasy danych pilnuje, żeby dostawały tylko dane publiczne.

Wynajmowane GPU dla dużych macierzy konfiguracji, dopuszczalne wyłącznie dla prób o klasie `public`. Reguła „klasa danych i dozwoleni dostawcy” zapisana w konfiguracji routera modeli (programu, który kieruje wywołania do właściwego modelu), sprawdzana przed każdym wywołaniem. Gotowe, gdy jedna macierz przeszła na wynajętym GPU, a próba z inną klasą danych została odrzucona. Zależy od F2.6.

### F6.3. Dokumenty skali L

**Status: do zrobienia** — nie zaczęte; czeka na F3.10 (raport z pierwszego eksperymentu), która też jeszcze nie ruszyła.

Po co: duża organizacja pyta nie o wynik z laboratorium, lecz o to, co będzie przy tysiącach użytkowników: koszt, zapotrzebowanie na sprzęt. Dokument skali L odpowiada liczbami wyliczonymi z pomiarów pilota, ze wzorem przy każdej.

Generator dokumentu wdrożenia w dużej organizacji z szablonu (`templates/runbook-l.md`), z liczbami wyliczonymi z pomiarów pilota i wzorem przy każdej liczbie. Gotowe, gdy powstał dokument dla eksperymentu, który przeszedł G2. Zależy od F3.10.

### F6.4. Strona laboratorium

**Status: w toku** — strona jest opublikowana (osobne repozytorium, GitHub Actions, domena własna, HTTPS) i odświeża się co godzinę; brakuje budowy wywoływanej każdą publikacją oraz tekstu „Jak działa”, który czeka na zwolnienie przez bramkę publikacji.

Po co: bez strony wyniki są rozrzucone po plikach w repozytorium, a strona składa je w czytelne dossier hipotez dla kogoś, kto nie zna projektu.

Strona lab.exocortex.zone w obu językach (`/en` i `/pl`, adres główny przekierowuje do `/en`), generowana z repozytorium: opis działania, lista hipotez ze statusami, dossier każdej hipotezy (streszczenie, prerejestracja, dane z sumami kontrolnymi i plikami do pobrania, przebiegi, wyniki, decyzje z bramek, odstępstwa, powtórzenie, ograniczenia, sposób cytowania) i stan roadmapy. Strona jest statyczna i działa na GitHub Pages w osobnym, małym repozytorium, bo exocortex.zone zajmuje jedyną stronę Pages repozytorium głównego. Generator jest w katalogu `lab-site/`. Gotowe, gdy strona aktualizuje się sama po każdej publikacji. Zależy od F2.7.

### F6.5. Wydania z DOI

**Status: do zrobienia** — nie zaczęte; zadanie nie ma zależności.

Po co: DOI, czyli stały identyfikator archiwalnej kopii (taki jak przy publikacjach naukowych), pozwala zacytować konkretne wydanie i wrócić do niego po latach.

Integracja repozytorium z Zenodo: każde wydanie dostaje trwały identyfikator i archiwalną kopię, którą można zacytować w dokumentach. Gotowe, gdy pierwsze wydanie ma DOI.

### F6.6. Kelter jako wykonawca eksperymentów agentowych

**Status: do zrobienia** — nie zaczęte; zależność (F2.6) jest zrobiona, więc zadanie może ruszyć w każdej chwili.

Po co: część badań dotyczy modeli, które samodzielnie planują i wykonują kolejne kroki z użyciem narzędzi (agentów), a do tego potrzebny jest wykonawca inny niż pojedyncze zapytanie do modelu. Kelter to nasze otwarte środowisko do uruchamiania takich agentów.

Eksperymenty, w których model wykonuje wieloetapowe zadania z narzędziami, uruchamiane w Kelterze. Gotowe, gdy jeden eksperyment agentowy przeszedł przez kolejkę laboratorium. Zależy od F2.6.

## Postęp

- 2026-09-29: F6.4. Strona lab.exocortex.zone jest opublikowana z osobnego repozytorium `lab-site-repo` przez GitHub Actions, z domeną własną i HTTPS, i odświeża się co godzinę. Pokazuje trzy dossier hipotez, stan roadmapy i infografiki. Tekst „Jak działa Exocortex R&D” pojawi się po zwolnieniu dokumentu przez bramkę; do tego czasu strona pokazuje infografiki z informacją. Warunek ukończenia (aktualizacja po każdej publikacji) jest spełniony w postaci budowy co godzinę; zostaje uzupełnienie o budowę wywoływaną publikacją.
