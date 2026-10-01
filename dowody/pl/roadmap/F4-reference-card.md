---
id: F4
lang: pl
counterpart: ../../en/roadmap/F4-reference-card.md
status: doing
task_status: {F4.1: done, F4.2: doing, F4.3: done}
provenance: ai_authored
provenance_metadata: {agent: "Claude Opus 5.5 (Cowork)", date: 2026-09-27, human_validated: false}
---

# F4. Karta projektu referencyjnego z grafu

[← Roadmapa](../02-roadmap.md)

> **Status: w toku** · stan na 1 października 2026
>
> Dwa z czterech zadań są zrobione (F4.1, F4.3), jedno w toku (F4.2), jedno czeka. Faza korzysta z wyników pierwszego eksperymentu (F3), który jest w toku: karta hipotezy jest zamrożona, ale wyników pomiaru jeszcze nie ma. Model karty (F4.1) jest opublikowany, sprawdzanie uczciwości (F4.3) zatrzymuje przygotowane złe zdania, a kompilator karty (F4.2) pisze już kartę dla eksperymentu zabawkowego; karta pierwszego eksperymentu czeka na jego wyniki.

## W skrócie

Ta faza sprawia, że opis zrealizowanego projektu, potrzebny w ofercie albo przetargu (karta projektu referencyjnego), składa się sam z zapisanych wyników laboratorium. Każde zdanie takiej karty wskazuje, skąd pochodzi, a program odrzuca liczby bez źródła i plany opisane jak dokonane fakty.

## Po co ta faza

Karty referencyjne pisze się zwykle ręcznie i łatwo w nich o zawyżenie: plan zapisany czasem oznajmującym, liczba zapamiętana z rozmowy, słowo „działa” bez daty. Zamawiający nie ma jak tego sprawdzić. Tutaj karta powstaje inaczej. Jeśli ma zdanie o poprawie trafności, kompilator wstawi je tylko wtedy, gdy w zapisanym wyniku eksperymentu jest odpowiadająca mu liczba, i poda przy nim odnośnik do tego wyniku w publicznym repozytorium. Zdanie o stanie („obecnie”) dostanie datę. Zamawiający może więc sprawdzić każdą liczbę samodzielnie.

## Cel

Karta projektu referencyjnego przestaje być pisana ręcznie. Kompilator składa ją z grafu laboratorium: hipoteza z zamrożonej karty, metoda walidacji z opisu eksperymentu, wyniki z tabel, dalszy etap z decyzji na bramkach. Każde zdanie ma odnośnik do źródła w publicznym repozytorium, a tekst przechodzi sprawdzenie, które wyłapuje liczby bez źródła i plany opisane jako fakty.

Zadania są opisane tutaj, bez osobnych plików. Szczegóły ustalimy po F3.

## Faza jest skończona, gdy

Karta dla eksperymentu z F3 jest wygenerowana w obu językach, każda liczba ma odnośnik, sprawdzenie uczciwości przechodzi, a ta sama karta wypełnia przykładowy formularz przetargowy.

## Zadania

### F4.1. Ogólny model karty

**Status: zrobione** — model jest opublikowany: dziewięć sekcji karty referencyjnej w stałej kolejności, a przy każdej dozwolone tryby zdań i miejsca w zapisach laboratorium, z których bierze się jej treść. Istnieje jako plik z danymi (`lab/card-model.yaml`) i jako dokument [Ogólny model karty referencyjnej](../07-card-model.md). Program sprawdza z nim każdą kartę (`exocortex lab card-check`), a pełna karta eksperymentu zabawkowego przechodzi kontrolę. Siedem luk między tym, czego potrzebuje sekcja, a tym, co zapisuje laboratorium, jest opisanych w tym dokumencie jako otwarte decyzje.

Po co: opisuje kartę raz, niezależnie od konkretnego przetargu, żeby te same zapisane wyniki dało się złożyć w różne formularze.

Sekcje karty jako neutralny schemat, niezależny od konkretnego formularza: cel i kontekst, hipoteza, eksperymenty i iteracje, metoda walidacji, wyniki, dalszy etap, co nowego wnosi na tle prac pokrewnych, ryzyka i ograniczenia, sposób weryfikacji. Dla każdej sekcji: z jakich węzłów grafu pochodzi treść. Gotowe, gdy schemat jest opublikowany w obu językach. Zależy od F2.

### F4.2. Kompilator karty

**Status: w toku** — kompilator działa: `exocortex lab card-compile <eksperyment>` pisze kartę po polsku i po angielsku z opublikowanych zapisów laboratorium, w dziewięciu sekcjach modelu karty, z linkiem przy każdym zdaniu do pliku lub jednego wiersza danych. Status projektu wynika z ostatniej zatwierdzonej decyzji bramki i nigdy nie jest wyższy. Dla eksperymentu zabawkowego powstaje 60 zdań w każdym języku, każdy link otwiera swoje źródło, a karta przechodzi kontrolę modelu i kontrolę uczciwości. Zobacz [Kompilator karty referencyjnej](../08-card-compiler.md). Z warunku ukończenia zostaje karta pierwszego eksperymentu (F3), który nie ma jeszcze opublikowanych wyników.

Po co: bez kompilatora karta musiałaby powstawać ręcznie, a kompilator gwarantuje, że karta i zapisane wyniki się zgadzają.

Generuje kartę w markdown, po polsku i po angielsku, z odnośnikiem przy każdym zdaniu do pliku lub wiersza danych w repozytorium. Status projektu wynika z ostatniej zatwierdzonej bramki i nigdy nie jest wyższy. Gotowe, gdy karta dla F3 jest wygenerowana, a każdy odnośnik działa. Zależy od F4.1 i F3.

### F4.3. Sprawdzenie uczciwości tekstu karty

**Status: zrobione** — kontrola działa jako `exocortex lab honesty` i pilnuje trzech reguł: zdanie w trybie faktu musi mieć źródło w trybie faktu, liczba musi występować w zapisanym wyniku, a zdanie o stanie bieżącym musi mieć datę. Zatrzymuje wszystkie 48 przygotowanych złych zdań, po polsku i po angielsku, a karta napisana przez kompilator (F4.2) dla eksperymentu zabawkowego przechodzi bez uwag. Gdy pierwszy eksperyment będzie miał wyniki, jego karta przejdzie przez tę samą kontrolę.

Po co: to sprawdzenie zatrzymuje zdania, które brzmią pewniej, niż pozwalają dowody, zanim karta trafi do zamawiającego.

Trzy reguły: zdanie w trybie faktu musi mieć źródło w trybie faktu (klasyfikator trybu z F3, czyli program rozpoznający, czy zdanie opisuje fakt, plan, wymóg czy hipotezę), liczba w karcie musi występować w zapisanym wyniku, zdanie o stanie („działa”, „obecnie”) musi mieć datę. Gotowe, gdy sprawdzenie zatrzymuje zestaw przygotowanych błędnych zdań i przepuszcza kartę z F4.2. Zależy od F4.2.

### F4.4. Wypełnianie formularzy przetargowych

**Status: do zrobienia** — nie zaczęte; czeka na F4.2.

Po co: karta jest użyteczna w przetargu dopiero wtedy, gdy da się ją przenieść do formularza zamawiającego. Generator jest publiczny, a mapowanie na konkretny formularz zostaje prywatne, bo formularz należy do zamawiającego.

Kod generatora, który przenosi sekcje karty do pól konkretnego formularza (na przykład arkusza xlsx), jest publiczny i ogólny. Mapowanie sekcji na pola konkretnego formularza jest prywatne i leży poza repozytorium, bo formularz należy do zamawiającego. Gotowe, gdy generator wypełnia przykładowy, samodzielnie przygotowany formularz. Zależy od F4.2.
