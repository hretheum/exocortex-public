---
id: cycle
lang: pl
counterpart: ../en/01-cycle.md
provenance: ai_authored
provenance_metadata:
  agent: Claude Opus 5.5 (Cowork)
  date: 2026-09-27
  human_validated: false
---

# Jak działa cykl dowodowy

Ten dokument opisuje, jak jeden pomysł przechodzi od pierwszego sygnału do opublikowanego wyniku. Szczegóły techniczne i kolejność budowy są w [roadmapie](02-roadmap.md).

## Po co to jest

Prowadzimy prace badawczo-rozwojowe nad zastosowaniami AI i chcemy, żeby każdą z nich dało się sprawdzić z zewnątrz. Kto zajrzy do repozytorium, ma zobaczyć, jaka była hipoteza, jak ją mierzyliśmy, jakie warianty porównaliśmy, co wyszło i co postanowiliśmy potem. Przydaje się to w różnych sytuacjach. Jedna z nich to karta projektu referencyjnego w przetargu: komisja pyta tam o hipotezę, metodę walidacji i wyniki, a my możemy wskazać publiczny zapis prac, z którego karta została złożona.

Dwie zasady obowiązują od początku. W laboratorium nie używamy żadnych materiałów od klientów: dane wejściowe pochodzą ze źródeł publicznych albo tworzymy je sami. Wszystko, co laboratorium wytwarza, jest publiczne od razu, po polsku i po angielsku. Projekty klienckie są osobnym światem, zostają prywatne i do laboratorium nie trafiają.

## Trzy miejsca

Vault Obsidiana, katalog `dowody/`. Tu piszemy karty hipotez, notatki z eksperymentów, decyzje podejmowane na bramkach, dokumentację i roadmapę. Człowiek edytuje treść tylko tutaj.

Laboratorium, czyli osobna instancja Exocortexa na domowym serwerze K12. Tu treść trafia do bazy i do grafu powiązań, tu działają skrypty eksperymentów i lokalne modele językowe, tu powstają strony z wynikami. Laboratorium ma własną bazę danych. Prywatny Exocortex, w którym są notatki z pracy zawodowej, stoi obok i nie ma z laboratorium połączenia w żadną stronę.

Publiczne repozytorium na GitHubie. Trafia tu kod silnika i laboratorium, dokumentacja, roadmapa z bieżącym stanem zadań, karty hipotez, surowe wyniki i raporty. Publikacja działa sama, co kwadrans, więc repozytorium zawsze pokazuje stan aktualny, a historia commitów pokazuje, kiedy co powstało.

Między vaultem a repozytorium stoi bramka publikacji. Każdy plik, zanim wyjdzie na zewnątrz, jest sprawdzany: czy nie zawiera nazw ani fragmentów materiałów klienckich, danych osobowych, ukrytych metadanych; czy ma wersję w drugim języku; czy liczby w obu wersjach są takie same. Plik, który nie przejdzie, zostaje w vaulcie, a autor dostaje powiadomienie z powodem.

## Droga jednej hipotezy

1. Sygnał. Raz w tygodniu laboratorium przegląda to, co wpłynęło ze źródeł publicznych: nowe prace naukowe, nowe modele o otwartych wagach, otwarte zbiory danych, luki i sprzeczności we własnej bazie wiedzy laboratorium. Powstaje krótka lista kandydatów, każdy z odnośnikiem do źródła.

2. Wybór. Kandydat odpada, jeśli odpowiedź na którekolwiek z pięciu pytań brzmi „nie”: czy wiadomo, po co to robimy; czy są dane; czy to legalne; czy da się to zmierzyć; czy nie da się tego załatwić prościej, bez AI. Kandydaci, którzy przejdą, dostają ocenę punktową. Pierwszą ocenę wystawia kilka modeli różnych rodzin, każdy osobno. Jeśli ich oceny mocno się różnią, wiadomo, że trzeba się nad kandydatem zastanowić dłużej. Decyzję podejmuje człowiek.

3. Karta hipotezy. Zapisujemy, co dokładnie sprawdzamy, jaki wynik obali hipotezę, którą jedną liczbą rozstrzygamy, co jest punktem odniesienia i na jakich próbach liczymy. Po zatwierdzeniu karta zostaje zamrożona: laboratorium liczy jej sumę kontrolną i publikuje kartę w repozytorium, zanim cokolwiek zostanie policzone. Data tego commita pokazuje, że metody nie dopasowaliśmy do wyniku. Jeśli po drodze zmienimy zdanie, powstaje nowa wersja karty, a poprzednia zostaje widoczna.

4. Szybki test (skala S, od kilku godzin do dwóch dni). Na K12, lokalnymi modelami, na małej próbie. Część próby odkładamy jako zbiór kontrolny i otwieramy go tylko raz, na końcu. Większość pomysłów kończy się na tym etapie.

5. Bramka. Wynik porównujemy z progiem zapisanym w karcie. Możliwe decyzje: idziemy dalej, kończymy, zmieniamy hipotezę, odkładamy z zapisanym warunkiem powrotu albo zamykamy, bo pytanie zostało rozstrzygnięte. Decyzję zatwierdza człowiek i ją też publikujemy. Wyniki negatywne publikujemy razem z opisem, dlaczego nie wyszło.

6. Pilot (skala M, od tygodnia do kilku tygodni). Większa próba oceniana przez ludzi na ślepo, porównanie kilku wariantów, spis typowych błędów, pomiar kosztu i czasu. Wynik musi wypróbować ktoś inny niż autor. Na końcu druga bramka.

7. Plan dla dużej organizacji (skala L). Tego etapu nie wykonujemy. Piszemy dokument, jak przeprowadzić takie wdrożenie dla tysięcy użytkowników, a liczby w nim, na przykład koszt na jednostkę, odsetek przypadków do ręcznej kontroli czy wymagania sprzętowe, bierzemy z pomiarów pilota.

8. Zapis. Każdy krok zostawia ślad w grafie laboratorium i plik w repozytorium. Z tych śladów składane są strony wynikowe i karta projektu referencyjnego. Każde zdanie karty wskazuje, skąd pochodzi. Liczba, której nie da się powiązać z zapisanym wynikiem, do karty nie trafia.

## Co chroni przed wyciekiem

Pierwsza ochrona to rozdzielenie. Laboratorium czyta tylko ze źródeł wpisanych na listę dozwolonych i z katalogu `dowody/`. Do prywatnego Exocortexa nie ma dostępu.

Druga to skaner na każdej publikacji. Sprawdza listę zakazanych nazw (sama lista jest prywatna, repozytorium zna tylko jej skróty kryptograficzne), wykrywa dane osobowe, czyści i sprawdza metadane plików. Paczki i obrazy kontenerów rozpakowuje i skanuje ich zawartość przed wysłaniem do rejestru.

Trzecia to porównanie z prywatnym korpusem. Na K12 sprawdzamy, czy tekst przeznaczony do publikacji nie przypomina żadnego fragmentu materiałów klienckich, także po przeredagowaniu. Z tego porównania wychodzi tylko odpowiedź „podobny” albo „niepodobny”, nic więcej nie opuszcza prywatnej bazy.

Skaner też jest testowany. Co noc dostaje zestaw plików z celowo wstawionymi wyciekami i musi zatrzymać każdy z nich. Jeśli któryś przepuści, publikacja staje, dopóki ktoś tego nie naprawi.

## Co chroni przed naciąganiem wyników

Karta hipotezy jest zamrożona przed pomiarem, a zbiór kontrolny otwierany raz. Bramki zatwierdza człowiek, a historia w repozytorium jest pełna i nikt jej nie przepisuje. W karcie referencyjnej nie ma liczb bez źródła. Tekst karty sprawdzamy dodatkowo narzędziem, które wykrywa zdania opisujące plan tak, jakby był już wykonany.

## Kto co robi

| Czynność | Maszyna | Człowiek |
|---|---|---|
| Zbieranie sygnałów | przegląd źródeł raz w tygodniu | dopisuje własne pomysły |
| Wybór kandydatów | wstępna ocena kilkoma modelami | decyduje |
| Karta hipotezy | podpowiada metryki i wielkość próby | pisze i zatwierdza |
| Eksperyment | uruchamia, liczy, zapisuje | ocenia próbki na ślepo |
| Bramka | zestawia wynik z progiem | decyduje |
| Tłumaczenie | pierwsza wersja lokalnym modelem | poprawia |
| Publikacja | skanuje i publikuje co kwadrans | rozstrzyga zatrzymane pliki |

## Stan na dziś

Większość opisanego cyklu jeszcze nie istnieje. Exocortex ma już sporo potrzebnych elementów: wczytywanie treści do grafu, wykrywanie luk i sprzeczności, lokalne modele, stanowisko do porównywania konfiguracji. Brakuje osobnego laboratorium, bramki publikacji, publicznego repozytorium z bieżącym stanem i obsługi kart hipotez. Kolejność budowy opisuje [roadmapa](02-roadmap.md).
