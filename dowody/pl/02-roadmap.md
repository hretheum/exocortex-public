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

Plan budowy cyklu opisanego w dokumencie [Jak działa cykl dowodowy](01-cycle.md). Fazy są ułożone w kolejności, w jakiej trzeba je robić. Eksperymenty zaczynamy dopiero w fazie F3, bo wcześniej musi działać bramka publikacji i publiczne repozytorium. Skoro wszystko ma być jawne od pierwszego dnia, najpierw trzeba mieć pewność, że na zewnątrz nie wyjdzie nic, co nie powinno.

## Zasady dla wszystkich faz

Laboratorium nie korzysta z materiałów klientów. Nie służą jako dane, jako przykłady ani jako źródło cytatów i nazw. Jeśli jakiś problem przypomina coś znanego z pracy zawodowej, odtwarzamy go na danych publicznych albo wygenerowanych i nie piszemy, skąd wziął się pomysł.

Wszystko, co powstaje w laboratorium, jest publiczne na bieżąco: kod, dokumentacja, ta roadmapa ze stanem zadań, karty hipotez, wyniki. Repozytorium w każdej chwili pokazuje stan aktualny. Zasada nie dotyczy projektów klienckich, które zostają prywatne i do laboratorium nie trafiają.

Każdy dokument powstaje po polsku i po angielsku w tym samym commicie. Kod, komentarze, docstringi, komunikaty programów i opisy commitów piszemy tylko po angielsku.

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

Fazy F4 do F7 są rozpisane do poziomu zadań w dokumentach faz, bez osobnych plików. Ich kształt zależy od tego, co wyjdzie w F3, więc szczegółowe pliki powstaną po drugiej bramce pierwszego eksperymentu.

## Fazy

[F0. Zatrzymanie wycieków i bramka publikacji](roadmap/F0-leaks-and-gate.md). Sprawdzamy, co z wcześniej opublikowanych artefaktów nie spełnia nowych zasad, i wycofujemy to. Budujemy skaner, który sprawdza każdą publikację, oraz zestaw testów, który co noc sprawdza sam skaner. Bez tej fazy nie publikujemy niczego.

[F1. Publiczne repozytorium i ciągła publikacja](roadmap/F1-public-repo.md). Zakładamy czyste publiczne repozytorium z kodem silnika, laboratorium i dokumentacją. Kod przechodzi na angielskie komentarze, dokumenty dostają pary PL i EN, a publikator co kwadrans przenosi zmiany z vaulta do repozytorium przez bramkę. Pierwszą publikacją są ten dokument i opis cyklu.

[F2. Laboratorium i zapis cyklu](roadmap/F2-lab.md). Osobna baza laboratorium bez dostępu do danych prywatnych, lista dozwolonych źródeł, obsługa kart hipotez i decyzji z bramek, tabele eksperymentów i strony wynikowe publikowane razem z resztą.

[F3. Pierwsze pełne przejście cyklu](roadmap/F3-first-pass.md). Jeden eksperyment od karty hipotezy do raportu, na publicznym korpusie polskich dokumentów urzędowych. Powtarzamy w nim metodę ekstrakcji twierdzeń z tekstu, rozwijaną wcześniej w Exocortexie, tym razem na danych, które każdy może pobrać.

[F4. Karta projektu referencyjnego z grafu](roadmap/F4-reference-card.md). Kompilator karty, który bierze treść wyłącznie z zapisanych wyników, oraz sprawdzanie tekstu karty pod kątem liczb bez źródła i planów opisanych jako fakty.

[F5. Radar okazji i kolejne eksperymenty](roadmap/F5-radar-and-experiments.md). Cotygodniowy przegląd źródeł publicznych, nowe kanały (modele o otwartych wagach, prace naukowe, otwarte dane) i kolejne hipotezy, w tym pomiar, czy graf rzeczywiście poprawia wyszukiwanie.

[F6. Skala i współpraca](roadmap/F6-scale-and-collaboration.md). Dostęp dla drugiego eksperta, wynajmowana moc obliczeniowa dla danych publicznych, dokumenty skali L, strona laboratorium na exocortex.zone i archiwizacja wydań z numerem DOI.

[F7. Publiczne demo: baza wiedzy z badań](roadmap/F7-public-demo.md). Pokaz dla zespołów produktowych i badaczy: silnik czyta raporty i dane z badań, wyciąga ustalenia z cytatami, łączy je między badaniami i prowadzi listę hipotez, których nikt jeszcze nie sprawdził. Ma pokazać, jak wyglądałaby baza wiedzy organizacyjnej zasilana własnymi badaniami. Może iść równolegle z F4 do F6, po F3.

## Od czego zaczynamy

Od [F0.1](roadmap/F0/F0.1-close-leaking-channels.md), jeszcze dziś. Potem po kolei F0.2 do F0.7, bo bez działającej i przetestowanej bramki nie ma czego publikować. Następnie F1 aż do [F1.10](roadmap/F1/F1.10-first-publication.md), czyli pierwszej publikacji tych dokumentów. Od tego momentu repozytorium pokazuje plan i jego realizację na bieżąco, a F2 i F3 są budowane już na widoku.

## Kiedy repozytorium staje się publiczne

Repozytorium powstaje od początku tak, jakby było publiczne, ale do chwili przełączenia pozostaje prywatne. Przełączamy je, kiedy spełnione są wszystkie warunki:

- nocny autotest bramki przechodzi przez siedem nocy z rzędu, na serwerze i w CI (warunek ukończenia F0),
- porównanie z korpusem prywatnym działa na serwerze z indeksem zbudowanym z całego korpusu i ma skalibrowany próg semantyczny (F0.6),
- stare wydanie paczki na PyPI jest usunięte (F0.1),
- właściciel przejrzał kod po tłumaczeniu komentarzy oraz dokumenty i oznaczył zaakceptowane pliki polem `human_validated` (F1.5, F1.10),
- pierwszy przebieg CI na GitHubie kończy się sukcesem, razem z bramką na paczce i obrazie (F1.6).

Wtedy zamieniamy nazwy repozytoriów, zmieniamy widoczność, włączamy stronę dokumentacji i publiczne obrazy w GHCR, a na koniec sprawdzamy linki. To zamyka F1. Moment przełączenia wypada między F1.10 a F2.1. Dalej nie czekamy, bo F2 i F3 mają powstawać na widoku. Warunki odpowiadają temu, co może pójść źle: bramka, która czasem nie działa, podobieństwo do materiałów prywatnych, którego skaner nazw nie widzi, stare artefakty i tekst, którego nikt nie przeczytał.

## Stan zadań

Każdy plik zadania ma w nagłówku pola `status` (`todo`, `doing`, `done`), `depends_on` i `estimate`. Strona z zestawieniem stanu wszystkich zadań powstanie automatycznie w ramach [F2.7](roadmap/F2/F2.7-compile-domain.md). Do tego czasu stan sprawdza się w nagłówkach plików, a przebieg prac jest opisany w dzienniku [Stan prac](03-progress.md).
