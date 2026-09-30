---
id: F8
lang: pl
counterpart: ../../en/roadmap/F8-interactive-lab.md
status: doing
task_status: {F8.1: doing, F8.2: done, F8.10: done}
provenance: ai_authored
provenance_metadata: {agent: "Claude Sonnet 5.5 (Cowork)", date: 2026-09-29, human_validated: false}
---

# F8. Interaktywne laboratorium: zastosowania, pytania i GraphRAG

[← Roadmapa](../02-roadmap.md)

> **Status: w toku** · stan na 30 września 2026
>
> Dwa z dziesięciu zadań są zrobione (F8.10, nowy tekst „Jak to działa”, i F8.2, pakiet grafu), jedno jest w toku (F8.1), siedem czeka. Szkic sekcji o zastosowaniach dla hipotezy „Zamiar czy fakt” przechodzi sprawdzacz i czeka na zatwierdzenie właściciela, a pakiet grafu (druga wersja, z polskimi streszczeniami silnika) jest w repozytorium i sprawdzony na świeżym klonie. Usługa pytań i jej interfejs (F8.3 do F8.5) wymagają decyzji o hostingu i budżecie, a pytania publiczności (F8.6 do F8.9) nie ruszyły. Test czytania nowego tekstu z dwiema osobami spoza projektu jeszcze się nie odbył.

## W skrócie

Ta faza zamienia stronę laboratorium z czytelni wyników w miejsce, z którym można rozmawiać. Przy każdej hipotezie pojawia się opis, co z niej wynika dla organizacji, każdy może zadać własne pytanie, a cały zgromadzony materiał da się przepytać zwykłym językiem i dostać odpowiedź z cytatami. Ten ostatni mechanizm nazywa się GraphRAG: odpowiedź powstaje z fragmentów odnalezionych w grafie powiązań, a nie z pamięci modelu.

## Po co ta faza

Kto wchodzi na stronę laboratorium, widzi tabele i liczby, ale nie wie, co z nich wynika dla jego pracy, i nie ma jak zapytać o coś, czego nikt nie opisał. Sekcja o zastosowaniach mówi, do jakich decyzji da się wykorzystać wynik i jak mocny jest za nim dowód. Siłę dowodu wylicza reguła, a nie model. Przykład pytania od czytelnika: czy wynik dotyczy też tekstów po polsku. Pytanie trafia do oceny, czy da się je rozstrzygnąć pomiarem na danych publicznych, a jeśli tak, staje się hipotezą pochodną w kolejce, z odnośnikiem do hipotezy, z której wyszło. Odpowiedzi usługi zawsze mają cytaty, a gdy brakuje dowodu, usługa odmawia.

## Cel

Strona laboratorium przestaje być tylko czytelnią wyników. Każda hipoteza mówi, co z niej wynika dla organizacji, publiczność może zadać pytanie, które po ocenie testowalności staje się hipotezą pochodną w kolejce, a graf da się przepytać w języku naturalnym z cytatami. Projekt jest w dokumencie [Interaktywne laboratorium: zastosowania, pytania i GraphRAG](../06-interactive-lab-design.md).

Zadania są opisane tutaj, bez osobnych plików. Pierwszeństwo ma F8.1, potem F8.6 do F8.9, F8.2 jest zrobione, a F8.3 do F8.5 wymagają decyzji o hostingu i budżecie.

## Faza jest skończona, gdy

Każde dossier hipotezy w przygotowaniu albo zakończonej ma zatwierdzoną sekcję o zastosowaniach, co najmniej pięć pytań publiczności przeszło ocenę i ma publiczny status, a interfejs pytań odpowiada z cytatami dla co najmniej jednej hipotezy.

## Zadania

### F8.1. Sekcja o zastosowaniach biznesowych

**Status: w toku** — reguła etykiety, procesor ze sprawdzaczem i sekcja na stronie są gotowe; nowy szkic dla „Zamiaru czy faktu” przechodzi sprawdzacz i czeka na zatwierdzenie właściciela, a warunek ukończenia wymaga zatwierdzonych sekcji dla trzech dossier ze strony.

Po co: sekcja tłumaczy osobie spoza badań, do jakich decyzji da się wykorzystać wynik i jak mocny jest za nim dowód.

Procesor laboratorium składa plik `experiments/<slug>/applications.md` w obu językach z dossier, katalogu rodzajów zastosowań i, dla hipotez niesprawdzonych, dwóch scenariuszy wyniku. Siłę dowodu wylicza reguła, tekst sprawdza sprawdzacz (odnośnik do wyniku w każdym wierszu, brak liczb spoza wyników, nazw klientów i kwot, kontrola języka), a zatwierdza właściciel. Generator strony pokazuje sekcję zaraz po wynikach. Projekt jest w [dokumencie o interaktywnym laboratorium](../06-interactive-lab-design.md). Gotowe, gdy trzy dossier obecne na stronie mają zatwierdzoną sekcję z etykietami wyliczonymi regułą, a zmiana wyniku unieważnia zatwierdzenie. Zależy od F6.4.

Stan na 29 września: reguła etykiety, skrót źródła, procesor ze sprawdzaczem i sekcja na stronie są gotowe. Szkice dla trzech dossier ze strony powstają na serwerze poleceniem `python -m exocortex.lab applications draft <slug>`, bo tylko tam jest brama do modelu. Potem właściciel zatwierdza każdą sekcję osobno. Stan na 30 września: szkic dla „Zamiaru czy faktu” powstał na serwerze jednostką na żądanie, przechodzi sprawdzacz i czeka na zatwierdzenie w interfejsie właściciela.

### F8.2. Publiczny pakiet grafu

**Status: zrobione** — pakiet jest w repozytorium (`dowody/data/graph/`, wersja `v1-0bcb2ed5a3cd`, 6,6 MB) i przechodzi sprawdzenie `verify` na świeżym klonie; zawiera abstrakty arXiv i polskie streszczenia silnika, 30 września.

Po co: pakiet to wersjonowana, sprawdzalna kopia tego, co w grafie jest publiczne. Usługa pytań ma z czego odpowiadać, a każdy może sprawdzić po sumie kontrolnej, że dane się zgadzają.

Eksport z grafu laboratorium wyłącznie tego, co publiczne: twierdzenia, dosłowne cytaty, krawędzie i wektory korpusów publicznych, jako wersjonowany plik z sumą kontrolną i skryptem, który odtwarza go z danych. Pakiet przechodzi przez bramkę jak każda publikacja. Gotowe, gdy pakiet jest w repozytorium, a jego odtworzenie z danych daje ten sam skrót. Zależy od F2.8 i F3.2.

Stan na 30 września: skrypt `lab/graph_package.py` buduje pakiet z bazy laboratorium, zadaniem uruchamianym na żądanie, i sprawdza go z samych plików. Pierwsza wersja (`v1-675457aaecbd`, 3,4 MB) miała 2478 abstraktów arXiv z osadzeniami (ang. embeddings) i 99 twierdzeń z dosłownymi cytatami. Obecna wersja `v1-0bcb2ed5a3cd` (6,6 MB) ma 4956 dokumentów (2478 abstraktów i 2478 polskich streszczeń silnika), 186 twierdzeń z cytatami i 2664 krawędzie. Zastąpiła pierwszą w repozytorium, a `verify` na świeżym klonie potwierdza jej spójność z korpusem. Format i jego powody są opisane w [dokumencie o interaktywnym laboratorium](../06-interactive-lab-design.md).

### F8.3. Usługa pytań

**Status: do zrobienia** — nie zaczęte; wymaga F8.2 oraz decyzji właściciela o dostawcy modelu, hostingu i miesięcznym budżecie.

Po co: usługa odpowiada na pytania czytelników wyłącznie z odnalezionych fragmentów i podaje cytaty, a przy braku dowodu odmawia; twardy budżet i limity chronią przed kosztami i nadużyciem.

Mały kontener pod adresem `api.lab.exocortex.zone`, budowany w CI, z pakietem grafu z F8.2 przeniesionym do SQLite z wektorami. Dwa tryby wyszukiwania (wektorowy i po grafie), odpowiedź modelu wyłącznie z odnalezionych fragmentów, cytaty, odmowa przy braku dowodu, limit zapytań na adres, ochrona przed botami, twardy miesięczny budżet z wyłącznikiem i brak zapisu treści pytań. Wybór dostawcy i modelu to decyzje właściciela z dokumentu projektowego. Gotowe, gdy usługa odpowiada z cytatami na dziesięć pytań testowych, odmawia na pytania spoza korpusu i wyłącza się po przekroczeniu budżetu. Zależy od F8.2: bieżącą wersję pakietu w `dowody/data/graph/` wskazuje `latest.json`, teksty i tytuły dokumentów są w `lab/corpora/`, a przed użyciem usługa sprawdza pakiet poleceniem `python lab/graph_package.py verify`.

### F8.4. Interfejs pytań

**Status: do zrobienia** — nie zaczęte; czeka na F8.3.

Po co: strona i okno pytania przy hipotezie pozwalają osobie bez wiedzy technicznej zadać pytanie i zobaczyć odpowiedź z cytatami.

Strona `/ask` i to samo okno przy każdej hipotezie, w obu językach: pole pytania, kafelki sugestii, odpowiedź z cytatami, przełącznik „szukaj” i „graf”, odnośnik do udostępnienia odpowiedzi i przycisk „zgłoś jako pytanie do laboratorium”. Strona jest statyczna i woła interfejs API. Gotowe, gdy scenariusz od kafelka do odpowiedzi z cytatem da się przejść na telefonie i na komputerze, a strona działa z klawiatury i czytnikiem ekranu. Zależy od F8.3.

### F8.5. Kafelki sugestii

**Status: do zrobienia** — nie zaczęte; czeka na F8.3.

Po co: puste pole pytania zniechęca, więc kafelki podpowiadają, o co można zapytać; każdy jest wcześniej sprawdzony, więc nie prowadzi do odpowiedzi bez cytatów.

Generator kafelków przy budowie strony: szablony pytań dla każdego rodzaju hipotezy i pytania z sekcji o ograniczeniach, każde próbnie zadane usłudze. Kafelek zostaje tylko wtedy, gdy odpowiedź ma cytaty i przechodzi sprawdzenie, a właściciel może dopisać własne. Gotowe, gdy każda hipoteza z dossier ma co najmniej sześć kafelków, które przeszły próbę. Zależy od F8.3.

### F8.6. Wejście pytań publiczności

**Status: do zrobienia** — nie zaczęte; zależy od F6.4, która jest w toku (strona działa).

Po co: daje czytelnikowi drogę do zadania pytania ze strony hipotezy, a filtr wstępny chroni przed danymi osobowymi i spamem.

Formularz zgłoszeń GitHub w repozytorium i przycisk „Zadaj pytanie” na stronie hipotezy, który otwiera go z wybraną hipotezą. Filtr wstępny odrzuca dane osobowe, materiały klienckie i spam, zanim zgłoszenie trafi do oceny. Gotowe, gdy zgłoszenie z formularza pojawia się w kolejce laboratorium, a zgłoszenie z danymi osobowymi jest zatrzymane. Zależy od F6.4.

### F8.7. Ocena testowalności pytań

**Status: do zrobienia** — nie zaczęte; czeka na F8.6, zależność F5.3 jest zrobiona.

Po co: nie każde pytanie da się rozstrzygnąć pomiarem; ocena mówi, które da się rozstrzygnąć, ile by to kosztowało i czy takie pytanie już nie padło.

Procesor laboratorium ocenia każde pytanie według szablonu `templates/question-assessment.md` (na bazie szablonu wyboru z F5.3): czy rozstrzyga je pomiar na danych publicznych, jaka metryka i próg, jaki koszt (S, M, L), jak łączy się z hipotezą macierzystą. Wynik to werdykt `testable`, `needs-rephrase`, `not-testable`, `duplicate` albo `out-of-scope` z uzasadnieniem i szkic karty hipotezy pochodnej. Podobieństwo do istniejących pytań łączy powtórzenia i zlicza poparcia. Gotowe, gdy dziesięć pytań, także celowo złych, dostało poprawne werdykty według ręcznej oceny właściciela. Zależy od F8.6 i F5.3.

### F8.8. Hipotezy pochodne

**Status: do zrobienia** — nie zaczęte; czeka na F8.7 i F2.4 (w toku).

Po co: zamienia dobre pytanie w pełnoprawną hipotezę z kartą i prerejestracją, powiązaną z hipotezą, z której wyszła.

Schemat karty hipotezy dostaje pola `parent` i `kind` (pomocnicza, rozszerzająca, powtórzenie, wyjaśnienie alternatywne). Pytanie z werdyktem `testable` idzie do decyzji G0 właściciela obok kandydatów z radaru, a zatwierdzona hipoteza pochodna przechodzi zwykły cykl: karta, prerejestracja, test, bramki. Kolejność w kolejce wynika z oceny, poparć, kosztu i wagi wyniku macierzystego. Gotowe, gdy jedna hipoteza pochodna ma kartę z odnośnikiem do macierzystej i wpis w rejestrze prerejestracji. Zależy od F8.7 i F2.4.

### F8.9. Strona „Pytania” i powiązania w dossier

**Status: do zrobienia** — nie zaczęte; czeka na F8.8.

Po co: pokazuje publicznie, co stało się z każdym pytaniem, także odrzuconym, i dlaczego, a autor dostaje odpowiedź.

Publiczna strona „Pytania” z listą wszystkich pytań, ich statusem i powodem werdyktu, także odrzuconych, oraz sekcja „hipotezy pochodne” i blok „zadaj pytanie” w dossier hipotezy macierzystej. Autor dostaje odpowiedź w zgłoszeniu. Gotowe, gdy co najmniej pięć pytań ma publiczny status, a dossier pokazuje swoje hipotezy pochodne. Zależy od F8.8.

### F8.10. Przepisanie tekstu „Jak to działa” dla odbiorcy biznesowego

**Status: zrobione** — tekst w obu językach jest przepisany, a właściciel oznaczył zadanie jako wykonane; na stronie pojawi się po zwolnieniu dokumentu przez bramkę publikacji, a test czytania z dwiema osobami spoza projektu, wymagany przez warunek ukończenia, jeszcze się nie odbył.

Po co: żeby osoba z biznesu po minucie czytania wiedziała, co daje jej laboratorium.

Tekst „Jak to działa” w obu językach opisuje mechanizm, a nie cel. Sekcja „Po co jest to laboratorium” jest najważniejsza: ma w kilku zdaniach powiedzieć osobie z biznesu, co ona z tego ma, bez pojęć takich jak próg sukcesu czy pomiar. Przepisujemy ją od strony odbiorcy: jakie decyzje (wybór narzędzia, koszt, ryzyko) da się podjąć na dowodach zamiast na opiniach, i jeden krótki przykład z prawdziwego dossier. Reszta tekstu przechodzi ten sam test: każda sekcja zaczyna się od tego, co z niej wynika dla czytelnika. Szczegóły techniczne nie znikają, bo dla wiarygodności są potrzebne: trafiają do wyraźnie oznaczonych ramek „Dla technicznych” (dla osób z działów danych i uczenia maszynowego po stronie klienta, które chcą zrozumieć, jak to jest zrobione), zwijanych albo umieszczonych pod tekstem głównym. Ilustracje zostają. Tekst główny musi się bronić sam, bez czytania ramek. Gotowe, gdy dwie osoby spoza projektu, jedna po polsku i jedna po angielsku, po minucie czytania pierwszej sekcji potrafią własnymi słowami powiedzieć, do czego służy laboratorium, a tekst przechodzi sprawdzenie języka i parytetu. Nie zależy od pozostałych zadań tej fazy.

Stan na 29 września: tekst w obu językach jest przepisany i opublikowany, a właściciel oznaczył zadanie jako wykonane. Test z dwiema osobami spoza projektu nie został przeprowadzony.
