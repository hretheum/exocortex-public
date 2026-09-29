---
id: F7
lang: pl
counterpart: ../../en/roadmap/F7-public-demo.md
status: todo
provenance: ai_authored
provenance_metadata: {agent: "Claude Opus 5.5 (Cowork)", date: 2026-09-27, human_validated: false}
---

# F7. Publiczne demo: baza wiedzy z badań

[← Roadmapa](../02-roadmap.md)

## Cel

Pokazać w kilka minut, jak mogłaby wyglądać baza wiedzy organizacyjnej zasilana wynikami badań. Silnik czyta raporty i dane z badań, wyciąga z nich ustalenia z dosłownym cytatem, rozpoznaje, czy zdanie jest ustaleniem, hipotezą, rekomendacją czy planem, łączy ustalenia z różnych badań (potwierdza, przeczy), pokazuje, ile dowodów stoi za każdym ustaleniem, i prowadzi listę hipotez, których nikt jeszcze nie sprawdził.

Odbiorcą są zespoły produktowe, badacze i osoby prowadzące projekty. Po pokazie mają pomyśleć: tak moglibyśmy trzymać wiedzę z naszych projektów, zasilać ją naszymi badaniami ilościowymi i jakościowymi i podejmować decyzje na podstawie dowodów.

Domena ma być ogólna i zrozumiała bez przygotowania, na przykład korzystanie z komunikacji miejskiej albo praca zdalna. Wybór w F7.1. Demo korzysta tylko z danych publicznych. Materiał jakościowy, którego publicznie jest mało, może być wygenerowany, ale wtedy jest wyraźnie oznaczony jako syntetyczny i nie jest liczony jako dowód.

Faza może iść równolegle z F4 do F6, po zakończeniu F3. Zadania są opisane tutaj, bez osobnych plików.

## Faza jest skończona, gdy

Demo jest publiczne w obu językach, przeszło test z co najmniej trzema osobami z grupy docelowej, a instrukcja zasilania własnymi badaniami jest opublikowana.

## Zadania

### F7.1. Domena, źródła i scenariusz pokazu

Wybór domeny, lista źródeł z podstawą korzystania (raporty z otwartym dostępem, otwarte dane ilościowe, ewentualnie materiał syntetyczny), scenariusz na pięć minut: pytanie, odpowiedź z cytatami, otwarte hipotezy, dodanie nowego badania, zmiana na mapie wiedzy. Gotowe, gdy opis jest opublikowany, a źródła są na liście dozwolonych. Zależy od F3.

### F7.2. Model danych badawczych

Węzły: badanie (metoda ilościowa, jakościowa lub mieszana, wielkość próby, data, źródło), ustalenie (z cytatem i trybem), hipoteza otwarta, rekomendacja, decyzja projektowa. Krawędzie: potwierdza, przeczy, wynika z, uzasadnia. Prosta miara siły dowodu (liczba niezależnych badań, różnorodność metod, wielkość prób), opisana jawnie jako heurystyka. Gotowe, gdy schemat i jego opis są opublikowane. Zależy od F7.1.

### F7.3. Wyciąganie ustaleń i hipotez z raportów

Ekstraktor z F3 rozszerzony o rozpoznawanie zdań, które można potraktować jako hipotezę badawczą do sprawdzenia. To zadanie samo przechodzi przez cykl: karta hipotezy, szybki test, ocena na ślepej próbie, bramka. Gotowe, gdy decyzja G1 jest opublikowana. Zależy od F7.2.

### F7.4. Interfejs demo

Publiczna strona w obu językach: mapa wiedzy, pytanie z odpowiedzią i cytatami, lista otwartych hipotez, ustalenia sprzeczne, widok jednego badania. Tryb „dodaj własne badanie” działa w piaskownicy, na przykładowych plikach, bez trwałego zapisu. Gotowe, gdy scenariusz z F7.1 da się przejść od początku do końca na stronie publicznej. Pytania i odpowiedzi z cytatami korzystają z usługi i interfejsu z F8.3 i F8.4, zamiast budować drugi. Zależy od F7.3 i F8.4.

### F7.5. Test z odbiorcami

Trzy do pięciu osób z grupy docelowej przechodzi scenariusz. Sprawdzamy, czy rozumieją, co widzą, i czy potrafią powiedzieć, jak zasililiby to własnymi badaniami. Ta część też ma kartę hipotezy. Notatki z sesji publikujemy bez danych osobowych. Gotowe, gdy notatki i wnioski są opublikowane. Zależy od F7.4.

### F7.6. Instrukcja zasilania własnymi badaniami

Jakie formaty przyjmuje silnik, szablon raportu z badania, jak wygląda wdrożenie w organizacji i co zostaje u niej prywatne. Wdrożenie u konkretnej organizacji jest osobnym, prywatnym projektem i nie trafia do laboratorium. Gotowe, gdy instrukcja jest opublikowana w obu językach. Zależy od F7.5.
