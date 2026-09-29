---
id: interactive-lab-design
lang: pl
counterpart: ../en/06-interactive-lab-design.md
provenance: ai_authored
provenance_metadata:
  agent: Claude Sonnet 5.5 (Cowork)
  date: 2026-09-29
  human_validated: false
---

# Interaktywne laboratorium: zastosowania, pytania i GraphRAG

Ten dokument opisuje trzy rozszerzenia strony lab.exocortex.zone: sekcję o zastosowaniach biznesowych na stronie hipotezy, publiczne pytania zamieniane w hipotezy pochodne i interfejs, w którym można zadawać pytania grafowi. Zadania są w fazie [F8](roadmap/F8-interactive-lab.md).

## Zastosowania biznesowe na stronie hipotezy

Odbiorca strony często nie pyta o metodę, tylko o to, co z niej wynika dla jego pracy. Sekcja odpowiada na to bez obiecywania czegokolwiek ponad wyniki. Powstaje z dossier, nie z wyobraźni.

1. Osobny plik `experiments/<slug>/applications.md` w obu językach jest częścią jednostki eksperymentu i wychodzi razem z nią. Strona pokazuje go jako sekcję zaraz po wynikach.
2. Procesor laboratorium składa plik z trzech wejść: dossier (pytanie, wyniki, decyzje z bramek, ograniczenia), krótkiego katalogu ogólnych rodzajów zastosowań (wybór narzędzia, koszt kontra jakość, ryzyko i zgodność, projektowanie produktu, organizacja badań) oraz, dla hipotez jeszcze niesprawdzonych, obu scenariuszy wyniku.
3. Model pisze tylko tekst. Siłę dowodu wylicza reguła ze stanu dossier, nie model. Etykiety: „hipoteza, bez dowodu”, „wstępne”, „potwierdzone na próbie N”, „obalone na próbie N”, „nierozstrzygnięte”.
4. Sprawdzacz odrzuca szkic, jeśli wiersz nie ma odnośnika do wyniku, etykieta różni się od wyliczonej, w tekście jest liczba spoza wyników, nazwa klienta, kwota albo obietnica zysku, albo tekst nie przechodzi kontroli języka.
5. Szkic zatwierdza właściciel polem `human_validated`, jak kartę hipotezy. Zmiana wyniku unieważnia zatwierdzenie i uruchamia nowy szkic.

Kształt sekcji:

| Część | Zawartość |
|---|---|
| Jedno zdanie | co ta hipoteza zmienia dla organizacji |
| Zastosowania | tabela: zastosowanie, kto korzysta, na jakim wyniku się opiera, siła dowodu, warunki i granice |
| Jeśli potwierdzimy, jeśli obalimy | dla hipotez planowanych i w przygotowaniu: co zrobić w każdym z dwóch przypadków |
| Czego z tego nie wolno wyciągać | ograniczenia zwykłym językiem |
| Co sprawdzić dalej | odnośniki do hipotez pochodnych |

Wynik negatywny też ma wartość biznesową, bo mówi, w co nie inwestować. Sekcja mówi to wprost, zamiast pomijać hipotezy obalone.

### Reguła siły dowodu i zatwierdzanie

Etykietę wylicza kod w `exocortex/lab/evidence.py` wyłącznie z plików dossier. Liczy się ostatnia decyzja z bramki zatwierdzona w obu językach (`human_validated: true`).

| Stan dossier | Etykieta |
|---|---|
| brak wyników i brak zatwierdzonej decyzji | hipoteza, bez dowodu |
| są wyniki, nie ma zatwierdzonej decyzji | wstępne |
| decyzja GO i spełnione wszystkie kryteria z tabeli decyzji | potwierdzone na próbie N |
| decyzja NO-GO i co najmniej jedno kryterium niespełnione | obalone na próbie N |
| PIVOT, NOT-NOW, CLOSED albo decyzja wbrew własnym liczbom | nierozstrzygnięte |

N to najmniejsza liczność spośród wyników wskazanych przez decyzję, wzięta z pliku `metrics.csv` w danych eksperymentu. Etykieta nie obiecuje więc więcej niż najsłabszy wynik. Jeśli któregoś wyniku albo jego liczności brakuje, szkic nie powstaje.

Szkic ma w nagłówku etykietę, skrót źródła (`source_hash`, SHA-256 z wyników, decyzji, karty, przebiegów oraz pól `status` i `stage`), `publish: false` i `human_validated: false`. Właściciel zatwierdza każdą sekcję osobno: ustawia `publish: true` i `human_validated: true` w obu wersjach. Oba pola zostają w nagłówku, a sprawdzacz odrzuca plik, w którym tylko jedno z nich ma wartość `true`. Strona liczy ten sam skrót z publicznego dossier i pokazuje sekcję tylko wtedy, gdy się zgadza. Po zmianie wyniku zamiast sekcji widać krótką informację, że sekcja jest aktualizowana, a laboratorium składa nowy szkic poleceniem `python -m exocortex.lab applications draft <slug>`.

## Pytania publiczności i hipotezy pochodne

Zalecam nazwę „hipoteza pochodna” (ang. derived hypothesis), a zgłoszenie użytkownika nazywać „pytaniem”, dopóki nie przejdzie oceny. Pytanie jest wejściem, a hipoteza pochodna jest tym, co dostaje kartę, prerejestrację i decyzje z bramek. Ma pole `parent` (hipoteza macierzysta) i pole `kind`.

| Rodzaj | Znaczenie | Przykład |
|---|---|---|
| pomocnicza | podważa założenie, na którym stoi wynik macierzysty | czy na wynik wpłynęła jakość streszczeń prac |
| rozszerzająca | ta sama metoda, inny zakres | inny język albo inny korpus |
| powtórzenie | ta sama metoda na nowych danych | nowa próba dokumentów |
| wyjaśnienie alternatywne | inny mechanizm tłumaczy wynik | długość dokumentu zamiast pola trybu |

Przykład: hipoteza zostaje obalona, a streszczenia prac po polsku bywają średnie. Pytanie „czy wynik zależał od jakości streszczeń” jest hipotezą pomocniczą. Da się ją sprawdzić, bo te same dokumenty można streścić modelem najwyższej klasy i porównać wynik z pierwotnym.

Droga pytania:

1. Wejście: formularz zgłoszeń GitHub przy hipotezie. W pierwszej wersji bez własnego serwera, bo przycisk „Zadaj pytanie” otwiera formularz z wybraną hipotezą. Zgłoszenia są publiczne z założenia.
2. Filtr wstępny: dane osobowe, materiały klienckie, spam, długość i język. Zgłoszenie z takimi treściami nie idzie dalej.
3. Ocena testowalności przez procesor laboratorium według szablonu z [F5.3](roadmap/F5-radar-and-experiments.md): czy da się to rozstrzygnąć pomiarem na danych publicznych, jaka metryka, jaki próg, jaki koszt i jak to się wiąże z hipotezą macierzystą. Wynik: werdykt `testable`, `needs-rephrase`, `not-testable`, `duplicate` albo `out-of-scope` z uzasadnieniem, klasa kosztu (S, M, L) i szkic karty hipotezy pochodnej.
4. Duplikaty: podobieństwo do istniejących pytań i hipotez łączy zgłoszenia i zlicza poparcia.
5. Decyzja człowieka: G0 właściciela, tak jak dla kandydatów z radaru. Pytania publiczności są drugim źródłem kandydatów obok prac z arXiv. Zatwierdzona hipoteza pochodna wchodzi do kolejki i przechodzi ten sam cykl: karta, prerejestracja, test, bramki.
6. Publiczna strona „Pytania”: każde pytanie z numerem, statusem i powodem, także odrzucone. Autor dostaje odpowiedź w zgłoszeniu.

Kolejność w kolejce wynika z wyniku oceny, liczby poparć, kosztu i tego, jak bardzo pytanie dotyczy wyniku negatywnego hipotezy macierzystej. Laboratorium nic nie uruchamia na danych zgłaszającego i używa wyłącznie danych publicznych.

## Interfejs GraphRAG

Użytkownik widzi stronę `/ask` i to samo okno przy każdej hipotezie:

1. Pole pytania w języku naturalnym, a nad nim 8 kafelków sugestii dla wybranej hipotezy, na przykład „Co znaleźliśmy”, „Dlaczego wynik jest negatywny”, „Które dokumenty dały największy rozrzut”, „Co to znaczy dla mojej organizacji”, „Jak to odtworzyć”, „Co sprawdzimy dalej”.
2. Odpowiedź z cytatami: twierdzenie, dokument źródłowy i dosłowny cytat. Gdy w korpusie nie ma dowodu, odpowiedź brzmi „tego nie mamy” zamiast zgadywania.
3. Przełącznik „szukaj” i „graf”, czyli dwa tryby wyszukiwania na tym samym pytaniu. Pokazuje różnicę i jest praktycznym odpowiednikiem eksperymentu F5.5.
4. Przy odpowiedzi „tego nie mamy” przycisk „zgłoś jako pytanie do laboratorium”, który wprowadza pytanie do drogi z poprzedniej sekcji.

Kafelki powstają przy budowie strony z dossier i grafu: szablony pytań dla każdego typu hipotezy oraz pytania z sekcji o ograniczeniach. Każdy kafelek jest próbnie zadawany usłudze i zostaje tylko wtedy, gdy odpowiedź ma cytaty i przechodzi sprawdzenie. Właściciel może dopisać kafelki ręcznie.

Architektura ma jeden kierunek przepływu: laboratorium, bramka, publiczny pakiet grafu, usługa pytań. Usługa nigdy nie widzi bazy laboratorium ani sieci prywatnej. Dostaje tylko to, co jest już publiczne (twierdzenia, cytaty, krawędzie i wektory korpusów publicznych) jako wersjonowany plik z sumą kontrolną w repozytorium. Model odpowiada wyłącznie z odnalezionych fragmentów.

GitHub Pages nie uruchamia kodu po stronie serwera, więc pytania wymagają osobnej usługi. Trzy warianty:

| Wariant | Opis | Ocena |
|---|---|---|
| A. Funkcja brzegowa | strona zostaje statyczna, interfejs API to funkcja u dostawcy brzegowego | tanio, ale ciasny limit pamięci na indeks wektorowy |
| B. Mały kontener u dostawcy | usługa z obrazu budowanego w CI, pakiet grafu w SQLite z wektorami, model przez API z miesięcznym limitem | zalecane |
| C. Serwer laboratorium za tunelem | usługa na tym samym serwerze co laboratorium | odrzucone, bo łamie zasadę izolacji |

Zalecam wariant B. Strona zostaje na GitHub Pages, a z Pages wychodzi tylko interfejs API pod adresem `api.lab.exocortex.zone`, więc odejście od Pages jest częściowe. Zabezpieczenia: limit zapytań na adres z anonimizacją, ochrona przed botami po stronie dostawcy, twardy miesięczny budżet modelu z wyłącznikiem, brak zapisu treści pytań poza świadomym zgłoszeniem i brak śledzenia. Publiczna usługa używa modelu przez API tylko na tekstach publicznych, zgodnie z regułą klasy danych z [F6.2](roadmap/F6-scale-and-collaboration.md).

### Publiczny pakiet grafu

Usługa pytań dostaje graf jako pakiet w repozytorium: folder `dowody/data/graph/v1-<skrót>/` z plikami CSV i dwoma opisami. Pakiet buduje skrypt `lab/graph_package.py` z bazy laboratorium, na żądanie. Do repozytorium trafia przez bramkę jak każda publikacja, w całości albo wcale.

| Plik | Zawartość |
|---|---|
| `documents.csv` | dokumenty korpusów publicznych: artykuł, rodzaj tekstu, tytuł, adres, SHA-256 i długość tekstu |
| `claims.csv` | twierdzenia z zakończonych przebiegów eksperymentów, tylko te z dosłownym cytatem |
| `quotes.csv` | cytat każdego twierdzenia, dokładnie jak w dokumencie, z pozycją początku i końca |
| `edges.csv` | powiązania z typem i wagą, na przykład twierdzenie `derived_from` dokument |
| `vectors.csv` | osadzenia (ang. embeddings) dokumentów |
| `datapackage.json` | opis kolumn, kluczy i odwołań w formacie Frictionless Data |
| `manifest.json` | SHA-256 każdego pliku i skrót całego pakietu |

Wybory i ich powody:

1. Pakiet nie powtarza tekstów dokumentów. Są już w repozytorium w plikach korpusów (`lab/corpora/`), a pakiet wskazuje je identyfikatorem i sumą SHA-256. Repozytorium nie trzyma więc dwóch kopii tych samych tekstów, a bramka nie porównuje ich drugi raz przy każdej nowej wersji pakietu.
2. Osadzenia modelu bge-m3 mają 1024 wymiary. Pakiet zapisuje każdą współrzędną jako liczbę 8-bitową z jedną skalą na wektor, szesnastkowo, czyli 2 KB na dokument zamiast 4 KB liczb 32-bitowych. Na danych laboratorium każdy wektor zachowuje w tym zapisie podobieństwo kosinusowe co najmniej 0,998 do pełnego wektora, a pełne wektory zostają w bazie laboratorium. Zapis jest tekstowy, bo bramka przepuszcza tylko pliki, które potrafi przeczytać. Żaden plik nie jest większy niż 2 MiB, więc większa tabela, dziś wektory, ma kilka części o tych samych kolumnach.
3. Budowa jest deterministyczna co do bajtu: stała kolejność wierszy, stały zapis liczb i brak daty budowy w plikach. Te same dane dają ten sam skrót. Nazwa folderu to pierwsze 12 znaków skrótu, a `latest.json` wskazuje bieżącą wersję. Nowa wersja zastępuje poprzednią w drzewie repozytorium, a starsze zostają w historii.
4. Do pakietu wchodzą tylko rodzaje tekstu, dla których źródło ma w `lab/sources.yaml` zapisaną podstawę dalszego udostępniania (pole `redistribution`). Dziś to abstrakty arXiv na licencji CC0. Polskie streszczenia silnika takiego wpisu nie mają, więc zostają poza pakietem. Poza pakietem są też dokumenty laboratorium, karty, decyzje z bramek i sygnały radaru, bo nie są korpusami. Twierdzenia z danymi osobowymi laboratorium pomija już przy budowie.
5. Sprawdzenie wymaga tylko Pythona. Polecenie `python lab/graph_package.py verify` liczy sumy kontrolne i skrót oraz sprawdza każde odwołanie między plikami. Z opcją `--corpora` porównuje też każdy cytat z tekstem korpusu.

## Miejsce na roadmapie

Powstaje faza [F8](roadmap/F8-interactive-lab.md) z dziewięcioma zadaniami. [F7.4](roadmap/F7-public-demo.md) (interfejs demo bazy wiedzy z badań) zależy teraz od F8.4, żeby nie budować drugiego interfejsu pytań.

Kolejność: pierwszeństwo ma sekcja o zastosowaniach biznesowych (F8.1), która nie wymaga żadnej zmiany w hostingu. Dalej pytania publiczności (F8.6 do F8.9), bo działają na samym GitHubie, a na końcu interfejs GraphRAG (F8.2 do F8.5), który wymaga decyzji o hostingu i budżecie.

## Decyzje właściciela

1. Nazwa obiektu: „hipoteza pochodna” z rodzajami (zalecane) czy „subhipoteza”.
2. Hosting interfejsu API: mały kontener u dostawcy (zalecane), funkcja brzegowa albo odłożenie.
3. Model dla publicznych odpowiedzi: przez API z miesięcznym limitem (trzeba podać kwotę) czy tylko model lokalny, wtedy bez publicznego dostępu.
4. Wejście pytań: formularz GitHub (zalecane na start, wymaga konta) czy własny formularz na stronie.
5. Zatwierdzanie sekcji o zastosowaniach: każda wersja przez właściciela (zalecane) czy publikacja po samym sprawdzeniu.
