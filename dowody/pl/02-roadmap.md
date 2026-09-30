---
id: roadmap
lang: pl
counterpart: ../en/02-roadmap.md
provenance: ai_authored
provenance_metadata:
  agent: Claude Opus 5.5 (Cowork)
  date: 2026-09-27
  human_validated: false
---

# Roadmapa

Laboratorium to publiczne miejsce, w którym sprawdzamy pomysły związane z AI i zapisujemy, jak je sprawdziliśmy, tak żeby każdy mógł to zweryfikować. Ta roadmapa mówi, co już działa, a co dopiero budujemy. To plan budowy cyklu opisanego w dokumencie [Jak działa cykl dowodowy](01-cycle.md). Fazy są ułożone w kolejności, w jakiej trzeba je robić. Eksperymenty zaczynamy w fazie F3, gdy działa już laboratorium z fazy F2.

## Gdzie jesteśmy

Stan na 30 września 2026, według statusów w nagłówkach dokumentów faz.

| Faza | Status | W jednym zdaniu |
|---|---|---|
| F2 | w toku | Laboratorium działa: baza, kolejka eksperymentów, karty hipotez, strony wynikowe i ocenianie na ślepo; jedno zadanie, obsługa kart hipotez (F2.4), jest jeszcze w toku. |
| F3 | w toku | Pierwszy eksperyment ma korpus, ekstraktor twierdzeń i zamrożoną kartę hipotezy; szybki test jest w toku (ekstrakcja gotowa, czeka ocena na ślepo), raport jest przed nami. |
| F4 | do zrobienia | Karta projektu referencyjnego składana z zapisanych wyników; nic jeszcze nie zaczęte. |
| F5 | w toku | Radar okazji i cztery kanały źródłowe działają, kandydaci są ocenieni; kolejne eksperymenty czekają. |
| F6 | w toku | Strona lab.exocortex.zone jest opublikowana; drugi ekspert, wynajęta moc obliczeniowa i wydania z DOI czekają. |
| F7 | do zrobienia | Demo bazy wiedzy z badań; nic jeszcze nie zaczęte. |
| F8 | w toku | Nowy tekst „Jak to działa” i pakiet grafu są gotowe; sekcja o zastosowaniach czeka na zatwierdzenie, pytania publiczności jeszcze nie ruszyły. |

Zrobione jest dziewięć z dziesięciu zadań F2, pięć z dziesięciu zadań F3 (wybór i pobranie korpusu, ekstraktor, karta hipotezy z prerejestracją, narzędzie do ślepej próby), pobieranie z czterech kanałów i ocena kandydatów w F5 oraz nowy tekst „Jak to działa” w F8. Następny krok w pierwszym eksperymencie to szybki test na próbie strojenia (F3.6).

## Zasady dla wszystkich faz

Laboratorium nie korzysta z materiałów klientów. Nie służą jako dane, jako przykłady ani jako źródło cytatów i nazw. Jeśli jakiś problem przypomina coś znanego z pracy zawodowej, odtwarzamy go na danych publicznych albo wygenerowanych i nie piszemy, skąd wziął się pomysł.

Wszystko, co powstaje w laboratorium, jest publiczne na bieżąco: kod, dokumentacja, ta roadmapa ze stanem zadań, karty hipotez, wyniki. Repozytorium w każdej chwili pokazuje stan aktualny. Zasada nie dotyczy projektów klienckich, które zostają prywatne i do laboratorium nie trafiają.

Każdy dokument powstaje po polsku i po angielsku w tym samym commicie. Kod, komentarze, docstringi, komunikaty programów i opisy commitów piszemy tylko po angielsku.

Na serwerze działają wyłącznie obrazy kontenerów uruchamiane przez Quadlet w rootless Podmanie. Kod źródłowy z repozytorium nie trafia na serwer. Obrazy budujemy i sprawdzamy bramką w CI.

Dokumenty piszemy tak, żeby zrozumiał je ktoś spoza projektu. Bramka publikacji sprawdza tekst także pod kątem nawyków typowych dla modeli językowych.

## Jak dzielimy dokumenty

Każdy poziom ma limit objętości. Po jego przekroczeniu treść przenosimy do osobnych plików, a na wyższym poziomie zostaje krótka zajawka z linkiem.

| Poziom | Limit | Co zawiera |
|---|---|---|
| Dokument główny (ten) | ok. 150 linii | zasady, reguła podziału, każda faza w kilku zdaniach z linkiem |
| Dokument fazy | ok. 200 linii | cel fazy, warunek jej ukończenia, lista zadań |
| Dokument zadania | 25 do 80 linii | jedno zadanie atomowe |

Zadania opisujemy bezpośrednio w dokumencie fazy, jeśli jest ich najwyżej pięć i każde mieści się w kilkunastu liniach. W pozostałych przypadkach każde zadanie ma własny plik, a dokument fazy zawiera tabelę z jednym zdaniem o zadaniu, zależnościami i linkiem.

Zadanie jest atomowe, jeśli wykonuje je jedna osoba w jednym podejściu, najwyżej w jeden dzień pracy, i ma jeden sprawdzalny warunek ukończenia. Opis dłuższy niż 80 linii oznacza, że zadanie trzeba podzielić. Wyjątkiem są zadania seryjne, czyli ta sama procedura powtarzana na liście jednostek, na przykład katalog po katalogu. Mają jeden plik z procedurą i listą do odhaczania, a atomowa jest każda pozycja listy.

Limity wynikają z czasu czytania. Około 150 do 200 linii czyta się w kilka do kilkunastu minut, bez gubienia wątku i bez przewijania w poszukiwaniu kontekstu. Plik zadania ma dać się przeczytać w całości tuż przed rozpoczęciem pracy.

Fazy F4 do F8 są rozpisane do poziomu zadań w dokumentach faz, bez osobnych plików. Kształt faz F4 do F7 zależy od tego, co wyjdzie w F3, więc szczegółowe pliki powstaną po drugiej bramce pierwszego eksperymentu.

## Fazy

Prace przygotowawcze nad infrastrukturą publikacji prowadzimy osobno i nie opisujemy ich tutaj.

[F2. Laboratorium i zapis cyklu](roadmap/F2-lab.md). Osobna baza laboratorium bez dostępu do danych prywatnych, lista dozwolonych źródeł, obsługa kart hipotez i decyzji z bramek, tabele eksperymentów, zadania uruchamiane na żądanie, ocenianie na ślepo w interfejsie właściciela i strony wynikowe publikowane razem z resztą.

[F3. Pierwsze pełne przejście cyklu](roadmap/F3-first-pass.md). Jeden eksperyment od karty hipotezy do raportu, na publicznym korpusie: około 2500 abstraktów prac z arXiv na licencji CC0 i polskich streszczeń tych prac, które napisał silnik. Powtarzamy w nim metodę ekstrakcji twierdzeń z tekstu, rozwijaną wcześniej w Exocortexie, tym razem na danych, które każdy może pobrać.

[F4. Karta projektu referencyjnego z grafu](roadmap/F4-reference-card.md). Kompilator karty, który bierze treść wyłącznie z zapisanych wyników, oraz sprawdzanie tekstu karty pod kątem liczb bez źródła i planów opisanych jako fakty. Na końcu generator, który przenosi kartę do formularza przetargowego.

[F5. Radar okazji i kolejne eksperymenty](roadmap/F5-radar-and-experiments.md). Cotygodniowy przegląd źródeł publicznych, nowe kanały (modele o otwartych wagach, prace naukowe, otwarte dane) i kolejne hipotezy: czy graf poprawia wyszukiwanie, czy lokalne osadzenia (ang. embeddings), czyli liczbowe opisy sensu tekstu, dorównują chmurowym i czy wymuszony format odpowiedzi eliminuje odpowiedzi prozą. Do tego wybór kandydatów z oceną kilku modeli i comiesięczny pomiar nowych modeli.

[F6. Skala i współpraca](roadmap/F6-scale-and-collaboration.md). Dostęp dla drugiego eksperta, wynajmowana moc obliczeniowa dla danych publicznych, dokumenty skali L (plany wdrożenia w dużej organizacji), strona laboratorium na lab.exocortex.zone, archiwizacja wydań z numerem DOI (trwałym identyfikatorem do cytowania) i uruchamianie eksperymentów agentowych w Kelterze, naszym otwartym środowisku do uruchamiania agentów.

[F7. Publiczne demo: baza wiedzy z badań](roadmap/F7-public-demo.md). Pokaz dla zespołów produktowych i badaczy: silnik czyta raporty i dane z badań, wyciąga ustalenia z cytatami, łączy je między badaniami i prowadzi listę hipotez, których nikt jeszcze nie sprawdził. Ma pokazać, jak wyglądałaby baza wiedzy organizacyjnej zasilana własnymi badaniami. Może iść równolegle z F4 do F6, po F3.

[F8. Interaktywne laboratorium: zastosowania, pytania i GraphRAG](roadmap/F8-interactive-lab.md). Każda hipoteza dostaje sekcję o zastosowaniach biznesowych, publiczność może zadać pytanie, które po ocenie testowalności staje się hipotezą pochodną w kolejce, a graf da się przepytać w języku naturalnym z cytatami (mechanizm GraphRAG). Pierwszeństwo ma sekcja o zastosowaniach, a interfejs pytań wymaga decyzji o hostingu, bo GitHub Pages nie uruchamia kodu.

## Co dalej

Właściciel ma do zatwierdzenia kartę próbnego eksperymentu zabawkowego (sprawdzającego samą maszynerię), sekcję o zastosowaniach „Zamiaru czy faktu” (F8.1) i decyzje o kandydatach z radaru (F5.3). Trwa szybki test pierwszego eksperymentu (F3.6). Usługa pytań (F8.3 do F8.5) czeka na decyzję o hostingu i budżecie, a pytania publiczności (F8.6 do F8.9) jeszcze nie ruszyły.

## Stan zadań

Stan każdego zadania jest w nagłówku jego pliku (`status`: `todo`, `doing`, `done`, obok `depends_on` i `estimate`). W fazach opisanych w jednym dokumencie (F4 do F8) stan zadań jest w polu `task_status` w nagłówku dokumentu fazy, a zadanie bez wpisu jest do zrobienia. W tych fazach stan jest też zapisany słowami pod nagłówkiem każdego zadania. Zestawienie wszystkich zadań składa automatycznie laboratorium ([F2.7](roadmap/F2/F2.7-compile-domain.md)) i pokazuje strona lab.exocortex.zone. Przebieg prac jest opisany w dzienniku [Stan prac](03-progress.md).
