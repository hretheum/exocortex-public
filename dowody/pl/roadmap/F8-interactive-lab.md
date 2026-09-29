---
id: F8
lang: pl
counterpart: ../../en/roadmap/F8-interactive-lab.md
status: doing
task_status: {F8.1: doing}
provenance: ai_authored
provenance_metadata: {agent: "Claude Sonnet 5.5 (Cowork)", date: 2026-09-29, human_validated: false}
---

# F8. Interaktywne laboratorium: zastosowania, pytania i GraphRAG

[← Roadmapa](../02-roadmap.md)

## Cel

Strona laboratorium przestaje być tylko czytelnią wyników. Każda hipoteza mówi, co z niej wynika dla organizacji, publiczność może zadać pytanie, które po ocenie testowalności staje się hipotezą pochodną w kolejce, a graf da się przepytać w języku naturalnym z cytatami. Projekt jest w dokumencie [Interaktywne laboratorium: zastosowania, pytania i GraphRAG](../06-interactive-lab-design.md).

Zadania są opisane tutaj, bez osobnych plików. Pierwszeństwo ma F8.1, potem F8.6 do F8.9, a F8.2 do F8.5 wymagają decyzji o hostingu i budżecie.

## Faza jest skończona, gdy

Każde dossier hipotezy w przygotowaniu albo zakończonej ma zatwierdzoną sekcję o zastosowaniach, co najmniej pięć pytań publiczności przeszło ocenę i ma publiczny status, a interfejs pytań odpowiada z cytatami dla co najmniej jednej hipotezy.

## Zadania

### F8.1. Sekcja o zastosowaniach biznesowych

Procesor laboratorium składa plik `experiments/<slug>/applications.md` w obu językach z dossier, katalogu rodzajów zastosowań i, dla hipotez niesprawdzonych, dwóch scenariuszy wyniku. Siłę dowodu wylicza reguła, tekst sprawdza sprawdzacz (odnośnik do wyniku w każdym wierszu, brak liczb spoza wyników, nazw klientów i kwot, kontrola języka), a zatwierdza właściciel. Generator strony pokazuje sekcję zaraz po wynikach. Projekt jest w [dokumencie o interaktywnym laboratorium](../06-interactive-lab-design.md). Gotowe, gdy trzy dossier obecne na stronie mają zatwierdzoną sekcję z etykietami wyliczonymi regułą, a zmiana wyniku unieważnia zatwierdzenie. Zależy od F6.4.

Stan na 29 września: reguła etykiety, skrót źródła, procesor ze sprawdzaczem i sekcja na stronie są gotowe. Szkice dla trzech dossier ze strony powstają na serwerze poleceniem `python -m exocortex.lab applications draft <slug>`, bo tylko tam jest brama do modelu. Potem właściciel zatwierdza każdą sekcję osobno.

### F8.2. Publiczny pakiet grafu

Eksport z grafu laboratorium wyłącznie tego, co publiczne: twierdzenia, dosłowne cytaty, krawędzie i wektory korpusów publicznych, jako wersjonowany plik z sumą kontrolną i skryptem, który odtwarza go z danych. Pakiet przechodzi przez bramkę jak każda publikacja. Gotowe, gdy pakiet jest w repozytorium, a jego odtworzenie z danych daje ten sam skrót. Zależy od F2.8 i F3.2.

### F8.3. Usługa pytań

Mały kontener pod adresem `api.lab.exocortex.zone`, budowany w CI, z pakietem grafu w SQLite z wektorami. Dwa tryby wyszukiwania (wektorowy i po grafie), odpowiedź modelu wyłącznie z odnalezionych fragmentów, cytaty, odmowa przy braku dowodu, limit zapytań na adres, ochrona przed botami, twardy miesięczny budżet z wyłącznikiem i brak zapisu treści pytań. Wybór dostawcy i modelu to decyzje właściciela z dokumentu projektowego. Gotowe, gdy usługa odpowiada z cytatami na dziesięć pytań testowych, odmawia na pytania spoza korpusu i wyłącza się po przekroczeniu budżetu. Zależy od F8.2.

### F8.4. Interfejs pytań

Strona `/ask` i to samo okno przy każdej hipotezie, w obu językach: pole pytania, kafelki sugestii, odpowiedź z cytatami, przełącznik „szukaj” i „graf”, odnośnik do udostępnienia odpowiedzi i przycisk „zgłoś jako pytanie do laboratorium”. Strona jest statyczna i woła interfejs API. Gotowe, gdy scenariusz od kafelka do odpowiedzi z cytatem da się przejść na telefonie i na komputerze, a strona działa z klawiatury i czytnikiem ekranu. Zależy od F8.3.

### F8.5. Kafelki sugestii

Generator kafelków przy budowie strony: szablony pytań dla każdego rodzaju hipotezy i pytania z sekcji o ograniczeniach, każde próbnie zadane usłudze. Kafelek zostaje tylko wtedy, gdy odpowiedź ma cytaty i przechodzi sprawdzenie, a właściciel może dopisać własne. Gotowe, gdy każda hipoteza z dossier ma co najmniej sześć kafelków, które przeszły próbę. Zależy od F8.3.

### F8.6. Wejście pytań publiczności

Formularz zgłoszeń GitHub w repozytorium i przycisk „Zadaj pytanie” na stronie hipotezy, który otwiera go z wybraną hipotezą. Filtr wstępny odrzuca dane osobowe, materiały klienckie i spam, zanim zgłoszenie trafi do oceny. Gotowe, gdy zgłoszenie z formularza pojawia się w kolejce laboratorium, a zgłoszenie z danymi osobowymi jest zatrzymane. Zależy od F6.4.

### F8.7. Ocena testowalności pytań

Procesor laboratorium ocenia każde pytanie według szablonu `templates/question-assessment.md` (na bazie szablonu wyboru z F5.3): czy rozstrzyga je pomiar na danych publicznych, jaka metryka i próg, jaki koszt (S, M, L), jak łączy się z hipotezą macierzystą. Wynik to werdykt `testable`, `needs-rephrase`, `not-testable`, `duplicate` albo `out-of-scope` z uzasadnieniem i szkic karty hipotezy pochodnej. Podobieństwo do istniejących pytań łączy powtórzenia i zlicza poparcia. Gotowe, gdy dziesięć pytań, także celowo złych, dostało poprawne werdykty według ręcznej oceny właściciela. Zależy od F8.6 i F5.3.

### F8.8. Hipotezy pochodne

Schemat karty hipotezy dostaje pola `parent` i `kind` (pomocnicza, rozszerzająca, powtórzenie, wyjaśnienie alternatywne). Pytanie z werdyktem `testable` idzie do decyzji G0 właściciela obok kandydatów z radaru, a zatwierdzona hipoteza pochodna przechodzi zwykły cykl: karta, prerejestracja, test, bramki. Kolejność w kolejce wynika z oceny, poparć, kosztu i wagi wyniku macierzystego. Gotowe, gdy jedna hipoteza pochodna ma kartę z odnośnikiem do macierzystej i wpis w rejestrze prerejestracji. Zależy od F8.7 i F2.4.

### F8.9. Strona „Pytania” i powiązania w dossier

Publiczna strona „Pytania” z listą wszystkich pytań, ich statusem i powodem werdyktu, także odrzuconych, oraz sekcja „hipotezy pochodne” i blok „zadaj pytanie” w dossier hipotezy macierzystej. Autor dostaje odpowiedź w zgłoszeniu. Gotowe, gdy co najmniej pięć pytań ma publiczny status, a dossier pokazuje swoje hipotezy pochodne. Zależy od F8.8.

### F8.10. Przepisanie tekstu „Jak to działa” dla odbiorcy biznesowego

Tekst „Jak to działa” w obu językach opisuje mechanizm, a nie cel. Sekcja „Po co jest to laboratorium” jest najważniejsza: ma w kilku zdaniach powiedzieć osobie z biznesu, co ona z tego ma, bez pojęć takich jak próg sukcesu czy pomiar. Przepisujemy ją od strony odbiorcy: jakie decyzje (wybór narzędzia, koszt, ryzyko) da się podjąć na dowodach zamiast na opiniach, i jeden krótki przykład z prawdziwego dossier. Reszta tekstu przechodzi ten sam test: każda sekcja zaczyna się od tego, co z niej wynika dla czytelnika. Szczegóły techniczne nie znikają, bo dla wiarygodności są potrzebne: trafiają do wyraźnie oznaczonych ramek „Dla technicznych” (dla osób z działów danych i uczenia maszynowego po stronie klienta, które chcą zrozumieć, jak to jest zrobione), zwijanych albo umieszczonych pod tekstem głównym. Ilustracje zostają. Tekst główny musi się bronić sam, bez czytania ramek. Gotowe, gdy dwie osoby spoza projektu, jedna po polsku i jedna po angielsku, po minucie czytania pierwszej sekcji potrafią własnymi słowami powiedzieć, do czego służy laboratorium, a tekst przechodzi sprawdzenie języka i parytetu. Nie zależy od pozostałych zadań tej fazy.
