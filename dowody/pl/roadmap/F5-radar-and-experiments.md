---
id: F5
lang: pl
counterpart: ../../en/roadmap/F5-radar-and-experiments.md
status: doing
task_status: {F5.2: done}
provenance: ai_authored
provenance_metadata: {agent: "Claude Opus 5.5 (Cowork)", date: 2026-09-27, human_validated: false}
---

# F5. Radar okazji i kolejne eksperymenty

[← Roadmapa](../02-roadmap.md)

## Cel

Cykl zaczyna sam podsuwać kandydatów na eksperymenty ze źródeł publicznych, a my przeprowadzamy kolejne eksperymenty, każdy tą samą drogą co w F3.

Zadania są opisane tutaj, bez osobnych plików. Każdy z eksperymentów F5.5 do F5.7 dostanie własny katalog z kartą hipotezy i własną listę zadań, gdy do niego dojdziemy.

## Faza jest skończona, gdy

Radar działa co tydzień od co najmniej miesiąca, a co najmniej dwa kolejne eksperymenty mają opublikowane decyzje G1.

## Zadania

### F5.1. Radar okazji

Cotygodniowe zestawienie kandydatów z grafu laboratorium: twierdzenia w trybie hipotezy, nierozstrzygnięte sprzeczności, gęste skupiska tematów bez syntezy, nagłe wzrosty częstości tematów. Każdy kandydat z odnośnikiem do źródła, powtórzenia usuwane przez podobieństwo embeddingów. Strona publikowana w obu językach. Gotowe, gdy radar działa cztery tygodnie z rzędu. Zależy od F2 i F3.3.

### F5.2. Nowe kanały źródłowe

Prace naukowe z arXiv (cs.CL, cs.IR, cs.AI, cs.LG, z filtrem tematycznym), wydania modeli o otwartych wagach, otwarte dane publiczne (na przykład portal dane.gov.pl), wydania narzędzi, z których korzystamy. Każdy kanał jako adapter przez Capture API i wpis na liście dozwolonych z podstawą korzystania. Gotowe, gdy wszystkie cztery kanały zasilają graf laboratorium. Zależy od F2.2.

### F5.3. Wybór kandydatów z oceną kilku modeli

Pięć pytań odrzucających i arkusz punktowy (szablon w `templates/`). Pierwszą ocenę wystawiają niezależnie modele trzech różnych rodzin, różnica co najmniej dwóch punktów w którymkolwiek wymiarze oznacza kandydata do dłuższego namysłu. Decyzja człowieka jest zapisywana jako decyzja z bramki G0. Gotowe, gdy dziesięciu kandydatów z radaru przeszło przez ocenę. Zależy od F5.1.

### F5.4. Comiesięczny pomiar nowych modeli

Stałe stanowisko pomiarowe z F3 uruchamiane co miesiąc dla nowych modeli lokalnych. Wynik to publiczna tabela porównawcza w czasie, a zarazem ciągły, powtarzalny dowód pracy badawczej. Gotowe, gdy trzy kolejne miesiące mają opublikowane wyniki. Zależy od F3.

### F5.5. Eksperyment: czy graf poprawia wyszukiwanie

Porównanie wyszukiwania samymi embeddingami z wyszukiwaniem, które dodatkowo rozwija wyniki po krawędziach grafu, oraz porównanie typów krawędzi, które pomagają, z tymi, które szkodzą. Korpus publiczny, zbiór pytań ze złotymi odpowiedziami przygotowany ręcznie. Metryka rozstrzygająca nDCG@10. Gotowe, gdy decyzja G1 jest opublikowana. Zależy od F3 i F5.3.

### F5.6. Eksperyment: lokalny model embeddingów a model chmurowy

Czy lokalny model embeddingów daje wyniki wyszukiwania nie gorsze od modelu chmurowego na polskim korpusie publicznym. Hipoteza równoważności z progiem zapisanym w karcie. Zapytania do modelu chmurowego tylko z tekstami publicznymi. Gotowe, gdy decyzja G1 jest opublikowana. Zależy od F5.5.

### F5.7. Eksperyment: wymuszanie formatu odpowiedzi

Czy wymuszenie struktury odpowiedzi gramatyką (json_schema, GBNF w llama.cpp) eliminuje przypadki, w których model odpowiada prozą zamiast wywołania narzędzia. Metryka: odsetek odpowiedzi zgodnych ze schematem, metryka ochronna: jakość twierdzeń. Gotowe, gdy decyzja G1 jest opublikowana. Zależy od F3.

## Postęp

- 2026-09-29: F5.2. Cztery kanały zasilają graf laboratorium: nowe prace z arXiv w kategoriach cs.CL, cs.IR, cs.AI i cs.LG na tematy laboratorium, modele o otwartych wagach z Hugging Face, nowe zbiory z dane.gov.pl i wydania narzędzi, z których laboratorium korzysta (GitHub). Każdy kanał jest na liście dozwolonych źródeł z podstawą korzystania sprawdzoną u źródła, a zapisujemy tylko metadane i abstrakty. Pobieranie idzie przez osobną bramę, która przyjmuje tylko adresy https z tej listy i trzyma przerwy między zapytaniami; test izolacji sprawdza ją co noc. Pierwsze pobranie na serwerze: 200 prac, 50 modeli, 50 zbiorów danych i 12 wydań, bez błędów. Kanały uruchamia co tydzień zadanie radaru.
