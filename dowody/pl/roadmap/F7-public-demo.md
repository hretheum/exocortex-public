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

> **Status: do zrobienia** · stan na 30 września 2026
>
> Żadne z sześciu zadań nie jest jeszcze zaczęte (0 z 6 zrobione). Faza może iść równolegle z F4 do F6, ale zaczyna się po F3, która jest w toku. Pierwszy krok to wybór domeny i źródeł (F7.1). Interfejs demo (F7.4) potrzebuje też usługi pytań z fazy F8, której jeszcze nie ma (F8.3 i F8.4).

## W skrócie

Ta faza ma pokazać w kilka minut, jak wyglądałaby baza wiedzy organizacji zasilana wynikami jej badań. Program czyta raporty i dane z badań, wyciąga z nich ustalenia z dosłownymi cytatami, łączy je między badaniami i prowadzi listę hipotez, których nikt jeszcze nie sprawdził.

## Po co ta faza

W wielu zespołach wiedza z badań leży w osobnych raportach. Kolejny projekt zaczyna od zera, a nikt nie pamięta, które badanie potwierdziło ustalenie z innego, a które mu zaprzeczyło. Demo pokazuje na danych publicznych, jak to wygląda, gdy każde ustalenie ma cytat, widać, ile badań za nim stoi, i widać też pytania, których nikt jeszcze nie sprawdził. Domena ma być zrozumiała bez przygotowania, na przykład korzystanie z komunikacji miejskiej albo praca zdalna. Materiał jakościowy, którego publicznie jest mało, może być wygenerowany, ale jest wtedy oznaczony jako syntetyczny i nie liczy się jako dowód.

## Cel

Pokazać w kilka minut, jak mogłaby wyglądać baza wiedzy organizacyjnej zasilana wynikami badań. Silnik czyta raporty i dane z badań, wyciąga z nich ustalenia z dosłownym cytatem, rozpoznaje, czy zdanie jest ustaleniem, hipotezą, rekomendacją czy planem, łączy ustalenia z różnych badań (potwierdza, przeczy), pokazuje, ile dowodów stoi za każdym ustaleniem, i prowadzi listę hipotez, których nikt jeszcze nie sprawdził.

Odbiorcą są zespoły produktowe, badacze i osoby prowadzące projekty. Po pokazie mają pomyśleć: tak moglibyśmy trzymać wiedzę z naszych projektów, zasilać ją naszymi badaniami ilościowymi i jakościowymi i podejmować decyzje na podstawie dowodów.

Domena ma być ogólna i zrozumiała bez przygotowania, na przykład korzystanie z komunikacji miejskiej albo praca zdalna. Wybór w F7.1. Demo korzysta tylko z danych publicznych. Materiał jakościowy, którego publicznie jest mało, może być wygenerowany, ale wtedy jest wyraźnie oznaczony jako syntetyczny i nie jest liczony jako dowód.

Faza może iść równolegle z F4 do F6, po zakończeniu F3. Zadania są opisane tutaj, bez osobnych plików.

## Faza jest skończona, gdy

Demo jest publiczne w obu językach, przeszło test z co najmniej trzema osobami z grupy docelowej, a instrukcja zasilania własnymi badaniami jest opublikowana.

## Zadania

### F7.1. Domena, źródła i scenariusz pokazu

**Status: do zrobienia** — nie zaczęte; czeka na F3.

Po co: bez wybranej domeny i legalnych źródeł demo nie ma na czym działać, a scenariusz na pięć minut mówi, co pokazujemy i w jakiej kolejności.

Wybór domeny, lista źródeł z podstawą korzystania (raporty z otwartym dostępem, otwarte dane ilościowe, ewentualnie materiał syntetyczny), scenariusz na pięć minut: pytanie, odpowiedź z cytatami, otwarte hipotezy, dodanie nowego badania, zmiana na mapie wiedzy. Gotowe, gdy opis jest opublikowany, a źródła są na liście dozwolonych. Zależy od F3.

### F7.2. Model danych badawczych

**Status: do zrobienia** — nie zaczęte; czeka na F7.1.

Po co: ustala, czym jest badanie, ustalenie i hipoteza otwarta oraz jak się ze sobą łączą, żeby siłę dowodu liczyć jawnie i tak samo dla każdego ustalenia.

Węzły: badanie (metoda ilościowa, jakościowa lub mieszana, wielkość próby, data, źródło), ustalenie (z cytatem i trybem), hipoteza otwarta, rekomendacja, decyzja projektowa. Krawędzie: potwierdza, przeczy, wynika z, uzasadnia. Prosta miara siły dowodu (liczba niezależnych badań, różnorodność metod, wielkość prób), opisana jawnie jako heurystyka. Gotowe, gdy schemat i jego opis są opublikowane. Zależy od F7.1.

### F7.3. Wyciąganie ustaleń i hipotez z raportów

**Status: do zrobienia** — nie zaczęte; czeka na F7.2.

Po co: ekstraktor z F3 wyciąga twierdzenia z tekstu, a tutaj uczy się też rozpoznawać zdania, które są hipotezą do sprawdzenia. To zadanie samo jest eksperymentem z kartą hipotezy i punktem decyzji G1 po szybkim teście.

Ekstraktor z F3 rozszerzony o rozpoznawanie zdań, które można potraktować jako hipotezę badawczą do sprawdzenia. To zadanie samo przechodzi przez cykl: karta hipotezy, szybki test, ocena na ślepej próbie, bramka. Gotowe, gdy decyzja G1 jest opublikowana. Zależy od F7.2.

### F7.4. Interfejs demo

**Status: do zrobienia** — nie zaczęte; czeka na F7.3 i F8.4.

Po co: na publicznej stronie ktoś obcy sam przechodzi scenariusz, zamiast czytać jego opis.

Publiczna strona w obu językach: mapa wiedzy, pytanie z odpowiedzią i cytatami, lista otwartych hipotez, ustalenia sprzeczne, widok jednego badania. Tryb „dodaj własne badanie” działa w piaskownicy, na przykładowych plikach, bez trwałego zapisu. Gotowe, gdy scenariusz z F7.1 da się przejść od początku do końca na stronie publicznej. Pytania i odpowiedzi z cytatami korzystają z usługi i interfejsu z F8.3 i F8.4, zamiast budować drugi. Zależy od F7.3 i F8.4.

### F7.5. Test z odbiorcami

**Status: do zrobienia** — nie zaczęte; czeka na F7.4.

Po co: sprawdza, czy odbiorcy rozumieją, co widzą; bez tego nie wiadomo, czy demo działa poza zespołem, który je zbudował.

Trzy do pięciu osób z grupy docelowej przechodzi scenariusz. Sprawdzamy, czy rozumieją, co widzą, i czy potrafią powiedzieć, jak zasililiby to własnymi badaniami. Ta część też ma kartę hipotezy. Notatki z sesji publikujemy bez danych osobowych. Gotowe, gdy notatki i wnioski są opublikowane. Zależy od F7.4.

### F7.6. Instrukcja zasilania własnymi badaniami

**Status: do zrobienia** — nie zaczęte; czeka na F7.5.

Po co: odpowiada na pytanie, co trzeba mieć, żeby zasilić silnik własnymi badaniami, i co zostaje w organizacji prywatne.

Jakie formaty przyjmuje silnik, szablon raportu z badania, jak wygląda wdrożenie w organizacji i co zostaje u niej prywatne. Wdrożenie u konkretnej organizacji jest osobnym, prywatnym projektem i nie trafia do laboratorium. Gotowe, gdy instrukcja jest opublikowana w obu językach. Zależy od F7.5.
