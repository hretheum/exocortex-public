---
id: F4
lang: pl
counterpart: ../../en/roadmap/F4-reference-card.md
status: todo
provenance: ai_authored
provenance_metadata: {agent: "Claude Opus 5.5 (Cowork)", date: 2026-09-27, human_validated: false}
---

# F4. Karta projektu referencyjnego z grafu

[← Roadmapa](../02-roadmap.md)

## Cel

Karta projektu referencyjnego przestaje być pisana ręcznie. Kompilator składa ją z grafu laboratorium: hipoteza z zamrożonej karty, metoda walidacji z opisu eksperymentu, wyniki z tabel, dalszy etap z decyzji na bramkach. Każde zdanie ma odnośnik do źródła w publicznym repozytorium, a tekst przechodzi sprawdzenie, które wyłapuje liczby bez źródła i plany opisane jako fakty.

Zadania są opisane tutaj, bez osobnych plików. Szczegóły ustalimy po F3.

## Faza jest skończona, gdy

Karta dla eksperymentu z F3 jest wygenerowana w obu językach, każda liczba ma odnośnik, sprawdzenie uczciwości przechodzi, a ta sama karta wypełnia przykładowy formularz przetargowy.

## Zadania

### F4.1. Ogólny model karty

Sekcje karty jako neutralny schemat, niezależny od konkretnego formularza: cel i kontekst, hipoteza, eksperymenty i iteracje, metoda walidacji, wyniki, dalszy etap, co nowego wnosi na tle prac pokrewnych, ryzyka i ograniczenia, sposób weryfikacji. Dla każdej sekcji: z jakich węzłów grafu pochodzi treść. Gotowe, gdy schemat jest opublikowany w obu językach. Zależy od F2.

### F4.2. Kompilator karty

Generuje kartę w markdown, po polsku i po angielsku, z odnośnikiem przy każdym zdaniu do pliku lub wiersza danych w repozytorium. Status projektu wynika z ostatniej zatwierdzonej bramki i nigdy nie jest wyższy. Gotowe, gdy karta dla F3 jest wygenerowana, a każdy odnośnik działa. Zależy od F4.1 i F3.

### F4.3. Sprawdzenie uczciwości tekstu karty

Trzy reguły: zdanie w trybie faktu musi mieć źródło w trybie faktu (klasyfikator trybu z F3), liczba w karcie musi występować w zapisanym wyniku, zdanie o stanie („działa”, „obecnie”) musi mieć datę. Gotowe, gdy sprawdzenie zatrzymuje zestaw przygotowanych błędnych zdań i przepuszcza kartę z F4.2. Zależy od F4.2.

### F4.4. Wypełnianie formularzy przetargowych

Kod generatora, który przenosi sekcje karty do pól konkretnego formularza (na przykład arkusza xlsx), jest publiczny i ogólny. Mapowanie sekcji na pola konkretnego formularza jest prywatne i leży poza repozytorium, bo formularz należy do zamawiającego. Gotowe, gdy generator wypełnia przykładowy, samodzielnie przygotowany formularz. Zależy od F4.2.
