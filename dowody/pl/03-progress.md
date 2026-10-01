---
id: progress
lang: pl
counterpart: ../en/03-progress.md
provenance: ai_authored
provenance_metadata:
  agent: Claude Opus 5.5 (Cowork)
  date: 2026-09-28
  human_validated: false
---

# Stan prac

Dziennik tego, co zrobiono w ramach [roadmapy](02-roadmap.md), od najnowszych wpisów. Na górze jest sekcja „Co dalej”, pod nią dni i wpisy w kolejności od najnowszego. Stan pojedynczych zadań jest w nagłówkach ich plików. Tu zapisujemy, co się zmieniło, co zostało i co wyszło po drodze.

## Co dalej

Kroki właściciela, w tej kolejności: zatwierdzenie karty testowej `toy-length` (karta pierwszego eksperymentu, [F3.4](roadmap/F3/F3.4-hypothesis-card.md), jest już zatwierdzona i zamrożona), a potem przejrzenie kodu i dokumentów oraz oznaczenie przejrzanych plików polem `human_validated`.

Jednostki na żądanie (F2.9) i ocenianie w interfejsie (F2.10) są gotowe, więc szybki test może ruszyć. W interfejsie czeka na zatwierdzenie szkic sekcji o zastosowaniach „Zamiaru czy faktu” (F8.1). Pakiet grafu laboratorium (F8.2) jest w repozytorium w wersji z polskimi streszczeniami i sprawdzony na świeżym klonie.

Prace: szybki test na próbie strojenia i strona oceny na ślepo (F3.6). Niezależnie od pierwszego eksperymentu radar okazji działa co tydzień (F5.1 do F5.3), a rodzaje eksperymentów dla wyszukiwania i formatu odpowiedzi są gotowe (F5.8, F5.9).

Repozytorium główne jest publiczne od 29 września. Strona lab.exocortex.zone (F6.4) działa: zbudowana przez GitHub Actions, z domeną własną i HTTPS, odświeżana co godzinę. Pokazuje dziś trzy dossier hipotez, stan roadmapy i infografiki, a tekst „Jak działa Exocortex R&D” pojawi się, gdy ten dokument zostanie opublikowany.

Równolegle: faza [F8](roadmap/F8-interactive-lab.md), opisana w dokumencie [Interaktywne laboratorium: zastosowania, pytania i GraphRAG](06-interactive-lab-design.md). Pierwsza jest sekcja o zastosowaniach biznesowych na stronie hipotezy (F8.1), potem pytania publiczności zamieniane w hipotezy pochodne (F8.6 do F8.9), a na końcu interfejs GraphRAG: jego pakiet grafu jest zbudowany (F8.2), a usługa i strona pytań (F8.3 do F8.5) wymagają decyzji o hostingu i budżecie.

## 2026-10-01

### Kompilator karty (F4.2) i koniec F4.3

Program, który pisze kartę referencyjną z zapisów laboratorium, działa ([dokument](08-card-compiler.md)). Czyta opublikowane dane eksperymentu i pisze kartę po polsku i po angielsku, w dziewięciu sekcjach modelu karty, z linkiem przy każdym zdaniu do pliku lub jednego wiersza danych. Każde zdanie to albo szablon wypełniony zapisanymi wartościami, albo dosłownie skopiowany fragment karty hipotezy, więc program niczego nie pisze od siebie i nie woła żadnego modelu językowego. Status projektu wynika z ostatniej zatwierdzonej decyzji bramki i nigdy nie jest wyższy; bez decyzji karta nie może powiedzieć GO. Tam, gdzie brakuje danych, karta mówi to wprost. Dla eksperymentu zabawkowego powstaje 60 zdań w każdym języku, każdy link otwiera swoje źródło, a karta przechodzi kontrolę modelu i kontrolę uczciwości. To zamyka F4.3, którego ostatnim warunkiem było przejście karty z kompilatora.

Pierwszy eksperyment ma już przebieg, ale nie ma opublikowanych metryk, więc jego karta mówi, że wyników jeszcze nie opublikowano. Gdy się pojawią, to samo polecenie wytworzy kartę.

Do rozstrzygnięcia przez właściciela: czy sekcja Wyniki ma pokazywać wszystkie zapisane metryki, czy tylko te, na których opiera się decyzja bramki; brzmienie stanów projektu dla odbiorcy; czy zdanie w Wynikach może wskazywać plik, gdy nie ma wiersza danych; oraz gdzie i kiedy publikować wygenerowane karty.

### Model karty i sprawdzanie uczciwości (F4.1, F4.3)

Ogólny model karty jest opublikowany ([dokument](07-card-model.md)): dziewięć sekcji karty referencyjnej w stałej kolejności, a dla każdej: na co odpowiada, jakie tryby zdań dopuszcza i skąd w zapisach laboratorium bierze się jej treść. Każde zdanie karty niesie trzy pola: tryb (fakt, plan, wymóg albo hipoteza), źródło (plik albo jeden wiersz pliku z danymi) i, dla zdań o stanie bieżącym, datę. Program sprawdza karty z modelem, a pełna karta eksperymentu zabawkowego toy-length, zbudowana wyłącznie na jego opublikowanych wynikach, przechodzi kontrolę. Siedem luk między tym, czego potrzebuje sekcja, a tym, co zapisuje laboratorium, jest opisanych jako otwarte decyzje.

Sprawdzanie uczciwości tekstu karty (F4.3) też działa jako program, na przygotowanych rekordach zdań. Pilnuje trzech reguł: zdanie w trybie faktu musi mieć źródło w trybie faktu, liczba musi występować w zapisanym wyniku (w opisanej tolerancji zaokrągleń), a zdanie o stanie bieżącym musi mieć datę. Zatrzymuje wszystkie 48 przygotowanych złych zdań, 24 po polsku i 24 po angielsku, a karta wzorcowa przechodzi. Ostatnia część warunku ukończenia, przejście karty wygenerowanej przez kompilator, czeka na F4.2.

Do rozstrzygnięcia przez właściciela: otwarte decyzje modelu karty, tolerancja zaokrągleń i lista słów-kluczy stanu bieżącego oraz to, która konfiguracja modelu z F3 ma rozpoznawać tryby zdań karty.

### Dwa nowe rodzaje eksperymentów: wyszukiwanie i format odpowiedzi (F5.8, F5.9)

Kolejka eksperymentów mierzy teraz cztery rodzaje. Rodzaj „wyszukiwanie” (F5.8) przyjmuje zestaw pytań z ręcznie przygotowanymi wzorcowymi odpowiedziami, porządkuje dokumenty wybranym modelem osadzeń (ang. embeddings), opcjonalnie rozszerza ranking po krawędziach grafu i podaje nDCG@10, recall@k oraz MRR z przedziałami bootstrapowymi, a do tego różnice parami między konfiguracjami. Rodzaj „format odpowiedzi” (F5.9) sprawdza mechanicznie, czy odpowiedź modelu zgadza się z zapisanym schematem, podaje odsetek zgodnych odpowiedzi z przedziałami Wilsona (zakresami niepewności odsetka) i różnicę między konfiguracjami oraz wskazuje eksperyment na twierdzeniach dla miary kontrolnej (jakość twierdzeń). Dla każdego rodzaju przykładowy eksperyment przeszedł przez kolejkę, a osobny skrypt oparty tylko na bibliotece standardowej odtworzył każdą opublikowaną liczbę (36 dla wyszukiwania, 8 dla formatu).

Do rozstrzygnięcia przez właściciela: wzorcowe odpowiedzi dla wyszukiwania pochodzą z przygotowanych plików, więc strona oceny z F2.10 nie jest jeszcze podpięta do tego rodzaju; skala ocen 0 do 3 z liniowym zyskiem w nDCG; sposób, w jaki tryb gramatyki trafia do serwera modeli; czy brak odpowiedzi liczyć jako niezgodność; a prawdziwe wyszukiwanie po grafie potrzebuje krawędzi między artykułami, których korpus jeszcze nie ma.

## 2026-09-30

### Biurko: liczniki w menu i kafle zamiast szerokich tabel (F2.11)

Menu biurka pokazuje przy „Queue” i „Ocena na ślepo”, ile czeka na decyzję i ile twierdzeń na ocenę; liczniki odświeżają się po każdej akcji i po powrocie na kartę, a przy zerze znikają. Na ekranie oceny ocenione pozycje przechodzą do zwiniętej listy, z której można zmienić ocenę. Szerokie tabele na biurku i na stronie laboratorium stają się kaflami: jeden wiersz to jeden kafel z tytułem z pierwszej kolumny i parami „nagłówek: wartość”. Tabela metryk karty „Zamiar czy fakt” miała na stronie 799 pikseli w polu 724 i ucinała ostatnią kolumnę; teraz mieści się przy 1280 i 400 pikselach, także w motywie ciemnym. Przy okazji dwa testy bramki, które po wyłączeniu porównania semantycznego dla wyników laboratorium wciąż go oczekiwały, sprawdzają teraz nową regułę.

### Pakiet grafu z polskimi streszczeniami opublikowany, F8.2 zrobione

Druga wersja pakietu (`v1-0bcb2ed5a3cd`, 6,6 MB): 4956 dokumentów (2478 abstraktów i 2478 polskich streszczeń silnika), 186 twierdzeń z cytatami, 2664 krawędzie. Zastąpiła pierwszą wersję w repozytorium. Polecenie `verify` na świeżym klonie repozytorium przechodzi, więc zadanie ma status „zrobione”.

### Szybki test pierwszego eksperymentu: ekstrakcja gotowa, czeka ocena (F3.6)

Ekstrakcja na próbie strojenia (20 dokumentów, model qwen3.6-35b-a3b) przeszła bez błędów w obu wariantach: 20 z 20 dokumentów, 194 twierdzenia bez pola trybu i 193 z polem trybu, razem 377 twierdzeń nadających się do oceny. Strona oceny na ślepo jest wylosowana (10 powtórek do sprawdzenia zgodności oceniającego z samym sobą, jak wymaga karta) i czeka na oceniającego na ekranie „Ocena na ślepo”. Po ocenie próby strojenia otworzymy zbiór kontrolny, a potem powstanie decyzja G1. Zadanie ma status „w toku”.

### Roadmapa napisana dla obcego czytelnika

Każdy plik roadmapy ma teraz na górze widoczny blok statusu (zrobione, w toku albo do zrobienia, z opisem, co dokładnie jest gotowe i na co zadanie czeka), krótkie „W skrócie” i „Po co” pisane bez żargonu. Pliki faz mają w tabeli kolumnę „Status”, a dokument główny sekcję „Gdzie jesteśmy”. Opis pierwszego eksperymentu w dokumencie głównym poprawiono: korpus to abstrakty z arXiv, a nie dokumenty urzędowe.

### Dane laboratorium bez porównania z korpusem prywatnym

Wykrywacz podobieństwa wstrzymywał tabele i wyniki eksperymentów, bo prywatny korpus zawiera te same publiczne artykuły, więc porównanie znajdowało artykuł obok niego samego. Dane laboratorium (`data/**`) mają teraz własną klasę: skan literalny zostaje, porównanie semantyczne odpada. Laboratorium czyta wyłącznie źródła z listy dozwolonych, a nocny test izolacji pilnuje, że nie sięga do instancji prywatnej. Strony ręcznie napisane w vaulcie zachowują dotychczasowe sprawdzenia.

### Polskie streszczenia w pakiecie grafu (F8.2)

Właściciel zdecydował 30 września, że streszczenia i kluczowe ustalenia, które silnik napisał po polsku z abstraktów CC0, wchodzą do pakietu grafu razem z nimi. Są to własne wyniki silnika i są już opublikowane w całości w `lab/corpora/intent-vs-fact/corpus.jsonl`, więc pakiet niczego nie ujawnia ponad to, co jest publiczne. W `lab/sources.yaml` jest osobny wpis `corpus_summary` z podstawą udostępniania, a test pilnuje, że podstawa jest zapisana dla obu rodzajów tekstu. Opis w dokumencie projektowym (06) jest poprawiony. Kolejny krok: przebudowa pakietu (wersja 2), zatwierdzenie na biurku i sprawdzenie na świeżym klonie.

### Zadania laboratorium na żądanie (F2.9)

Na serwerze działają nowe jednostki: próba jednej próbki eksperymentu (`exocortex-lab-run@<eksperyment>_<próbka>`, także w wersji, która tylko dodaje zadania do kolejki), przerabianie kolejki po modelach (`exocortex-lab-work`, z zegarem nocnym, który jest w repozytorium, ale nie jest włączony) i kroki ślepej oceny (`exocortex-lab-blind@<krok>_<eksperyment>_<próbka>`: losowanie, wczytanie ocen, podsumowanie, publikacja). Zainstalowana jest też jednostka szkiców sekcji o zastosowaniach. Nowe jednostki mają tę samą sieć i sekrety co radar i nie mają drogi do pobierania. W opisie wdrożenia jest zasada: każde zadanie cykliczne da się uruchomić ręcznie jednym poleceniem, a test w repozytorium sprawdza, że każdy zegar ma taki odpowiednik opisany w dokumentacji. Eksperyment zabawkowy przeszedł na serwerze przez `run`, `work` i `blind`. Po drodze wyszedł błąd: eksperyment zabawkowy za każdym razem losował próbki od nowa z bieżących dokumentów, a te zmieniły się od pierwszego losowania, więc każda jego próba kończyła się błędem. Teraz używa zapisanych próbek. Nocny test izolacji nadal przechodzi. Zadanie jest ukończone.

### Ocenianie na ślepo w interfejsie właściciela (F2.10)

Interfejs właściciela ma ekran „Ocena na ślepo”: jedno twierdzenie naraz, z cytatem i fragmentem tekstu wokół niego, bez nazwy konfiguracji, w losowej kolejności z losowania. Są przyciski kategorii i trybu w źródle, pole komentarza, klawisze (1 do 8, Enter, strzałki) i wznawianie: każda ocena zapisuje się od razu, a po przerwie ekran wraca do pierwszej nieocenionej pozycji. Nagłówek pokazuje tylko, ile pozycji ocenione, a ile zostało. Interfejs nie ma dostępu do bazy laboratorium. Czyta stronę oceny, którą przygotowało laboratorium, a po zakończeniu oceny zaznaczenia trafiają na stronę w Obsidianie. Laboratorium wczytuje ją tym samym kodem co stronę wypełnioną ręcznie, która zostaje drogą zapasową. Na eksperymencie zabawkowym 4 twierdzenia i 2 powtórzenia zostały ocenione w interfejsie (oceny testowe agenta, nie ocena treści), a te same oceny zaznaczone ręcznie na stronie dały identyczne wyniki: udziały, przedziały Wilsona, różnice z bootstrapem i zgodność oceniającego z samym sobą. Zadanie jest ukończone.

### Szkic sekcji o zastosowaniach „Zamiaru czy faktu” czeka na zatwierdzenie (F8.1)

Po zamrożeniu karty zmieniła się suma źródeł sekcji, więc strona hipotezy pokazuje, że sekcja jest aktualizowana. Laboratorium wygenerowało na serwerze nowy szkic (model qwen3.6-35b-a3b, za pierwszym podejściem) i szkic przechodzi pełny sprawdzacz. Czeka w interfejsie właściciela jako nowy szkic z laboratorium. Do dokumentów trafi dopiero po zatwierdzeniu i publikacji, i tylko jeśli jego tekst się nie zmienił. Zadanie F8.1 zostaje w toku do tego zatwierdzenia.

### Lżejszy zapis pakietu grafu (F8.2)

Dopóki pierwsza wersja pakietu czekała na przegląd, każda publikacja zajmowała bramce prawie 20 minut, bo porównanie znaczeniowe przetwarzało wektory zapisane szesnastkowo jako tekst. Wektory są teraz w obrazach PNG w skali szarości, po jednym wierszu pikseli na dokument, z tymi samymi liczbami 8-bitowymi. Tytuły, podobnie jak teksty, zostają w pliku korpusu. Nowa wersja `v1-675457aaecbd` ma 3,4 MB zamiast 6,1 MB i zastąpiła poprzednią w katalogu laboratorium, a dwie budowy z tych samych danych dały ten sam skrót. Każdy wektor zachowuje w tym zapisie podobieństwo kosinusowe co najmniej 0,998 do pełnego.

## 2026-09-29

### Pierwsza budowa pakietu grafu (F8.2)

Laboratorium ma zadanie uruchamiane na żądanie, które buduje pakiet grafu ze swojej bazy do katalogu, z którego czyta publikator. Pierwsza budowa dała wersję `v1-9f3e6a3ae962` o rozmiarze 6,1 MB: 2478 abstraktów z osadzeniami o 1024 wymiarach i 99 twierdzeń z dosłownymi cytatami z przebiegu próbnego ekstraktora. Druga budowa z tych samych danych dała ten sam skrót. Poza pakietem zostały polskie streszczenia (2478) i 87 twierdzeń z nich wyciągniętych, bo w `lab/sources.yaml` nie ma dla nich zapisanej podstawy dalszego udostępniania. Pakiet przechodzi teraz przez bramkę jak każda publikacja.

### Skrypt pakietu grafu: budowa i sprawdzenie (F8.2)

Skrypt `lab/graph_package.py` buduje pakiet z bazy laboratorium i sprawdza go z samych plików. Sprawdzenie wymaga tylko Pythona: liczy sumy kontrolne i skrót całego pakietu oraz sprawdza każde odwołanie między plikami, a z tekstami korpusów także każdy cytat. Testy pokazują, że dwie budowy z tych samych danych dają identyczne bajty. Pokazują też, że sprawdzenie wykrywa uszkodzony plik i odwołanie do nieistniejącego dokumentu, a korpus bez zapisanej podstawy dalszego udostępniania zostaje pominięty. Podstawa dla abstraktów arXiv (CC0) jest zapisana w `lab/sources.yaml`.

### Format publicznego pakietu grafu (F8.2)

Pakiet grafu laboratorium ma ustalony format. Zawiera dokumenty korpusów publicznych bez powtarzania ich tekstów, które leżą już w repozytorium, oraz twierdzenia z dosłownymi cytatami i ich pozycjami w dokumencie. Do tego dochodzą powiązania z typem i wagą oraz osadzenia (ang. embeddings) dokumentów zapisane jako liczby 8-bitowe. Całość opisuje plik w formacie Frictionless Data z sumami kontrolnymi. Dla 2478 abstraktów pakiet powinien zająć około 6 MB, więc mieści się w repozytorium bez dodatkowych narzędzi. Wybory i ich powody są opisane w [dokumencie o interaktywnym laboratorium](06-interactive-lab-design.md).

### Tekst „Jak to działa” przepisany dla odbiorcy biznesowego (F8.10)

Tekst w obu językach zaczyna się od tego, co czytelnik z biznesu z tego ma, a szczegóły techniczne są w ramkach dla zespołów danych i uczenia maszynowego pod tekstem głównym. Właściciel oznaczył zadanie jako wykonane. Test czytania z dwiema osobami spoza projektu, przewidziany w warunku ukończenia, nie został przeprowadzony.

### Karta pierwszego eksperymentu zamrożona (F3.4)

Właściciel zatwierdził kartę hipotezy „Zamiar czy fakt" w obu językach, a laboratorium zamroziło ją i zapisało prerejestrację. Wpis jest w repozytorium, a skrypt weryfikacyjny na świeżym klonie potwierdza jego sumę. Pierwszy przebieg na korpusie jeszcze się nie odbył, więc kolejność (karta przed pomiarem) jest zachowana. Zadanie F3.4 jest ukończone. Przed szybkim testem (F3.6) brakuje jednostek na żądanie (F2.9) i oceniania w interfejsie (F2.10).

### Mechanizmy potrzebne pierwszemu eksperymentowi (F2.9, F2.10, F5.8, F5.9)

Przegląd gotowości przed pierwszym eksperymentem pokazał cztery luki, które nie są specyficzne dla „Zamiaru czy faktu", tylko dla każdego eksperymentu. Do roadmapy doszły: F2.9 (jednostki `run`, `work` i `blind` na serwerze, każde zadanie na żądanie), F2.10 (ocenianie na ślepo w interfejsie właściciela zamiast strony w Obsidianie), F5.8 (rodzaj eksperymentu „wyszukiwanie" dla F5.5 i F5.6) oraz F5.9 (rodzaj „zgodność formatu" dla F5.7). F3.6 zależy teraz od F2.9 i F2.10. Kalibracja sędziego (F3.9), spis błędów (F3.8) i raport (F3.10) już są na roadmapie.

### Eksport surowych wyników zamknięty (F2.8)

Na świeżym klonie repozytorium z GitHuba skrypt `lab/recompute.py` odtworzył z samych plików CSV wszystkie 10 liczb eksperymentu zabawkowego, tych samych, które pokazuje jego dossier. Brakujący dotąd opis danych (`datapackage.json`) jest już opublikowany, więc zadanie jest skończone.

### Sekcja o zastosowaniach biznesowych (F8.1)

Laboratorium ma polecenie, które składa sekcję „Zastosowania biznesowe” dla hipotezy w obu językach, i sprawdzacz, który ją odrzuca, gdy wiersz tabeli nie wskazuje wyniku z dossier, etykieta nie jest wyliczona regułą, w tekście jest liczba spoza wyników, nazwa z listy bramki, kwota, waluta albo obietnica zysku, wersje językowe nie są parą albo tekst nie przechodzi kontroli języka. Model pisze tylko tekst. Etykietę siły dowodu i skrót źródła wstawia kod, według reguły opisanej w [dokumencie o interaktywnym laboratorium](06-interactive-lab-design.md). Strona pokazuje sekcję zaraz po wynikach, ale tylko zatwierdzoną i ze zgodnym skrótem. Po zmianie wyniku pokazuje informację, że sekcja jest aktualizowana, a bez pliku wygląda jak dotąd. Zostało uruchomienie szkiców dla trzech dossier na serwerze i ich zatwierdzenie przez właściciela, więc zadanie ma stan „w toku”.

### Projekt interaktywnego laboratorium i aktualizacja roadmapy (F8, F6.4, F7.4)

Nowa faza F8 zbiera trzy rozszerzenia strony: sekcję o zastosowaniach biznesowych, składaną z dossier z etykietą siły dowodu wyliczaną regułą, pytania publiczności oceniane pod kątem testowalności i zamieniane w hipotezy pochodne (rodzaje: pomocnicza, rozszerzająca, powtórzenie, wyjaśnienie alternatywne) oraz interfejs GraphRAG z kafelkami sugestii, cytatami i odmową przy braku dowodu. Interfejs pytań wymaga osobnej usługi, bo GitHub Pages nie uruchamia kodu; zalecany jest mały kontener z interfejsem API pod osobną subdomeną, przy stronie zostającej na Pages. F7.4 korzysta teraz z interfejsu F8.4, a F6.4 ma stan „w toku”, bo strona działa, a brakuje budowy wywoływanej publikacją.

### Pierwsza publikacja strony lab.exocortex.zone (F6.4)

Po przełączeniu repozytorium na publiczne budowa strony padała na braku tekstu „Jak działa”, który nie był jeszcze opublikowany. Generator nie wymaga już tego tekstu: strona pokazuje wtedy infografiki z informacją, że opis jest w trakcie publikacji, a dwa testy pilnują budowy bez dokumentów. Strona jest opublikowana pod adresem lab.exocortex.zone z ważnym certyfikatem.

### Laboratorium: model, kolejka, karty i strony (F2.4 do F2.8)

Laboratorium ma dwie wąskie drogi na zewnątrz, obie poza swoją wewnętrzną siecią i dostępne dla jego procesów tylko przez gniazda w osobnych wolumenach. Pierwsza prowadzi do lokalnego serwera modeli: przepuszcza trzy wywołania i tylko modele z listy z licencjami. Druga służy do pobierania: przyjmuje tylko adresy https z listy dozwolonych źródeł i trzyma przerwy między zapytaniami, których wymagają ich warunki. Test izolacji sprawdza obie co noc, obok tego, że z sieci laboratorium nie da się połączyć ani z prywatną bazą, ani z internetem. Pierwsza noc przeszła: test izolacji i test end-to-end się powiodły.

W bazie laboratorium są tabele eksperymentów z kolejką, próbami i blokadą zbioru kontrolnego, którą pilnuje sama baza. Eksperyment zabawkowy przeszedł przez całą ścieżkę na serwerze: zadania dwóch konfiguracji wykonały się w dwóch blokach, a drugi odczyt zbioru kontrolnego skończył się odmową. Procesory kart hipotez i decyzji z bramek działają co 15 minut. Zatwierdzona karta dostaje wpis w rejestrze prerejestracji, a publikator przyjmuje ten rejestr tylko wtedy, gdy przybywa w nim wierszy. Laboratorium eksportuje surowe wyniki do plików CSV z opisem kolumn i składa strony wynikowe: stan roadmapy, listę eksperymentów i dossier. Skrypt w repozytorium przelicza liczby ze stron z samych plików CSV.

### Pierwszy eksperyment gotowy do zamrożenia (F3.2 do F3.5)

Korpus jest w grafie laboratorium: abstrakt i polskie streszczenie każdego z 2478 artykułów, z sumami kontrolnymi zgodnymi z manifestem i z embeddingami. Ekstraktor twierdzeń jest napisany od nowa i przeszedł test na pięciu artykułach w obu wariantach. [Karta hipotezy](experiments/intent-vs-fact/hypothesis.md) ma wylosowane próby, progi i kryteria bramek i czeka na zatwierdzenie; laboratorium nie uruchomi eksperymentu przed jej zamrożeniem. Narzędzie do ślepej próby przeszło test na eksperymencie zabawkowym, a jego przedziały ufności zgadzają się z obliczeniami w innych narzędziach.

### Radar okazji (F5.1 do F5.3)

Laboratorium pobiera cztery kanały sygnałów: nowe prace z arXiv w czterech kategoriach, modele o otwartych wagach, nowe zbiory danych publicznych i wydania narzędzi, z których korzysta. Z nich co tydzień powstaje strona radaru z hipotezami i planami z nowych prac, możliwymi sprzecznościami, gęstymi tematami i nagłymi wzrostami. W pierwszym pełnym tygodniu radar przejrzał 198 prac. Pierwszą ocenę dziesięciu kandydatów wystawiły osobno modele trzech rodzin według szablonu wyboru; decyzja należy do człowieka. Radar pomija artykuły z korpusów eksperymentów i pozycje, które bramka uznałaby za dane osobowe.

## 2026-09-28

### Strona laboratorium i dossier hipotez (F6.4, generator gotowy)

Powstał generator statycznej strony lab.exocortex.zone (katalog `lab-site/`): wersje `/en` i `/pl`, opis działania, lista hipotez ze statusami, osobne dossier każdej hipotezy i stan roadmapy z nagłówków plików zadań. Dossier ma budowę krótkiego artykułu: streszczenie, pytanie, prerejestracja, dane z sumami kontrolnymi i plikami do pobrania, metoda, przebiegi, wyniki, decyzje z bramek, odstępstwa, powtórzenie, ograniczenia i źródła. Cztery hipotezy mają dossier w `experiments/<slug>/overview.md`: „Zamiar czy fakt” (w przygotowaniu) i trzy planowane (F5.5 do F5.7). Wdrożenie jeszcze nie ruszyło: exocortex.zone to Astro na GitHub Pages i zajmuje jedyną stronę Pages repozytorium głównego, więc lab.exocortex.zone potrzebuje osobnego małego repozytorium, rekordu DNS i upublicznienia repozytorium głównego. Z dokumentów usunięto też szczegóły infrastruktury, na której działa laboratorium.

### Dokument i infografiki „jak to działa” (Exocortex R&D)

Powstał dokument [Jak działa Exocortex R&D](04-how-it-works.md) po polsku i angielsku oraz osiem infografik w katalogach `img/`: przegląd, bramka publikacji, droga hipotezy, ostatnie hipotezy ze statusami, architektura, izolacja laboratorium, ślad dowodowy i stan prac. Tekst jest pisany dla osoby spoza branży, promuje laboratorium i wspomina o prywatnym Exocortexie tylko jako o projekcie, z którego laboratorium wyrosło. Ta sama treść jest na roboczej stronie projektu, która stanie się podstawą podstrony na exocortex.zone (F6.4).

### Korpus pierwszego eksperymentu (F3.1, F3.2)

arXiv jest na liście dozwolonych źródeł laboratorium. Korpus eksperymentu „zamiar czy fakt” ma 2478 artykułów: abstrakt pobrany na nowo z arXiv i polskie streszczenie zrobione przez silnik. Pięć artykułów odpadło, bo bramka publikacji znalazła w nich nazwę ze swojej prywatnej listy; ich identyfikatory zostają prywatne. Budowa korpusu na dwóch maszynach dała identyczne sumy kontrolne. Korpus jest w repozytorium i w laboratorium. Kolejność w tym pliku jest teraz taka: na górze „Co dalej”, pod nią wpisy od najnowszego.

### Laboratorium rusza (F2.1, F2.2)

Laboratorium działa na serwerze w sieci, z której nie da się dostać do prywatnej instancji, co co noc sprawdza osobny test. Do laboratorium trafia tylko to, co jest na publicznej liście dozwolonych źródeł; na razie to nasze własne dokumenty. Przy okazji CI testuje teraz router modeli z repozytorium zamiast starszego wydania z PyPI i nie przebudowuje obrazów przy każdej publikacji dokumentów.

### Zmiana korpusu F3

Korpus F3 zmienił się z polskich dokumentów urzędowych na abstrakty artykułów z arXiv, które Exocortex już pobrał, razem z polskimi streszczeniami zrobionymi przez silnik. Nie trzeba czekać na zbieranie dokumentów, a eksperyment dostaje drugie pytanie: czy nasze streszczenia zamieniają hipotezy w fakty.

### CI i test end-to-end

CI na GitHubie przechodzi w całości, poza lintem, który tylko informuje. Walidacja schematu bazy działa na prawdziwym obrazie bazy. Obrazy silnika, bazy i bramki trafiają do GHCR dopiero po skanie.

Test end-to-end (wczytanie notatek, synteza, kompilacja wiki, pytanie GraphRAG z cytatami) wcześniej nigdy nie przeszedł. Wymagał płatnego klucza API i miał kilka błędów w samym teście. Teraz działa w dwóch miejscach. W CI zamiast modelu odpowiada atrapa serwera, więc test nie potrzebuje klucza i sprawdza przepływ danych. Na serwerze ten sam test biegnie co noc o 01:15 z prawdziwym lokalnym modelem, na jednorazowej bazie trzymanej w pamięci. Pierwszy przebieg na serwerze znalazł błąd: lokalny model czasem odpowiada zwykłym tekstem zamiast wywołaniem narzędzia i pytanie GraphRAG kończyło się wyjątkiem. Router modeli przyjmuje teraz taką odpowiedź, jeśli narzędzie ma jedno wymagane pole tekstowe. Drugi przebieg przeszedł w 25 sekund.

Przy okazji wyszło, że świeża baza nie ma grafu AGE, bo nie tworzy go żadna migracja. Obraz bazy tworzy go teraz przy pierwszym uruchomieniu. Test stosu `docker compose` uruchamia się już tylko ręcznie, bo produkcja działa na Quadletach.

Znany dług: przykładowa wtyczka ACME ma perspektywę syntezy, której program nie wywołuje, a jej zapytanie czyta nieistniejącą kolumnę. Test korzysta teraz ze zwykłej perspektywy tagu. Ekstrakcja tagów przez model jest pomijana, bo moduł `scripts.extract_tags_batch` nie trafił do eksportu. Trzy testy jednostkowe są wyłączone w CI.

### Pierwsze zadanie F2 (F2.3)

Zadanie F2.3 nie wymaga serwera, więc zostało zrobione od razu, w nocy z 27 na 28 września. Nagłówki kart hipotez, notatek z przebiegów, decyzji z bramek i plików zadań mają schematy JSON. Skrypt `docschema` sprawdza je w CI i w publikatorze, a błąd wskazuje plik, pole i powód. Doszedł szablon notatki z przebiegu, a README opisuje układ katalogów eksperymentów.
