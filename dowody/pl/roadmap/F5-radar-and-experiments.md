---
id: F5
lang: pl
counterpart: ../../en/roadmap/F5-radar-and-experiments.md
status: doing
task_status: {F5.1: doing, F5.2: done, F5.3: done, F5.8: done, F5.9: done}
provenance: ai_authored
provenance_metadata: {agent: "Claude Opus 5.5 (Cowork)", date: 2026-09-27, human_validated: false}
---

# F5. Radar okazji i kolejne eksperymenty

[← Roadmapa](../02-roadmap.md)

> **Status: w toku** · stan na 30 września 2026
>
> Cztery z dziewięciu zadań są zrobione (F5.2, F5.3, F5.8, F5.9), jedno w toku (F5.1), cztery czekają. Laboratorium pobiera nowe treści z czterech kanałów, a modele trzech rodzin oceniły dziesięciu kandydatów z radaru; radar ma za sobą pierwszy pełny tydzień z czterech wymaganych. Strony radaru i oceny czekają na przegląd właściciela przed publikacją, a o wyborze kandydatów (bramka G0) decyduje właściciel. Dalej: eksperymenty F5.5 do F5.7, które mają już potrzebne rodzaje eksperymentów.

## W skrócie

Ta faza sprawia, że laboratorium samo podsuwa pomysły na badania, zamiast tylko realizować te, które ktoś wymyślił. Co tydzień przegląda źródła publiczne (prace naukowe, nowe modele, otwarte dane), wskazuje, co warto sprawdzić, a potem przeprowadza kolejne eksperymenty tą samą drogą co pierwszy.

## Po co ta faza

Kto prowadzi badania sam, sprawdza to, co akurat przyszło mu do głowy, i łatwo pomija zmiany w otoczeniu: nowy model, nową pracę, nowy zbiór danych. Radar zamienia to w powtarzalny, cotygodniowy przegląd z odnośnikami do źródeł, a decyzję, co badać, zostawia człowiekowi. Decyzje zapadają w punktach decyzji zwanych bramkami: G0 wybiera, co badać, G1 zapada po szybkim teście, G2 po większym pilocie. Przykłady kolejnych eksperymentów: czy wyszukiwanie w dokumentach działa lepiej, gdy oprócz podobieństwa tekstów korzysta z powiązań w grafie (F5.5), oraz czy lokalne osadzenia (ang. embeddings), czyli liczbowe opisy sensu tekstu, dorównują chmurowym, tak że tekstów nie trzeba wysyłać poza serwer (F5.6).

## Cel

Cykl zaczyna sam podsuwać kandydatów na eksperymenty ze źródeł publicznych, a my przeprowadzamy kolejne eksperymenty, każdy tą samą drogą co w F3.

Zadania są opisane tutaj, bez osobnych plików. Każdy z eksperymentów F5.5 do F5.7 dostanie własny katalog z kartą hipotezy i własną listę zadań, gdy do niego dojdziemy.

## Faza jest skończona, gdy

Radar działa co tydzień od co najmniej miesiąca, a co najmniej dwa kolejne eksperymenty mają opublikowane decyzje G1.

## Zadania

### F5.1. Radar okazji

**Status: w toku** — radar działa co tydzień (niedziela 22:30) i ma za sobą tydzień 2026-W39 (198 prac, 287 hipotez i planów po usunięciu powtórzeń, jedna możliwa sprzeczność, jeden gęsty temat); do zamknięcia brakuje czterech tygodni z rzędu, a nagłych wzrostów jeszcze nie liczy, bo brak czterech tygodni wstecz.

Po co: bez przeglądu pomysły na badania biorą się z przypadku, a radar daje powtarzalną listę kandydatów z odnośnikami do źródeł.

Cotygodniowe zestawienie kandydatów z grafu laboratorium: twierdzenia w trybie hipotezy, nierozstrzygnięte sprzeczności, gęste skupiska tematów bez syntezy, nagłe wzrosty częstości tematów. Każdy kandydat z odnośnikiem do źródła, powtórzenia usuwane przez podobieństwo osadzeń. Strona publikowana w obu językach. Gotowe, gdy radar działa cztery tygodnie z rzędu. Zależy od F2 i F3.3.

### F5.2. Nowe kanały źródłowe

**Status: zrobione** — cztery kanały zasilają graf: prace z arXiv (cs.CL, cs.IR, cs.AI, cs.LG), modele o otwartych wagach z Hugging Face, zbiory z dane.gov.pl i wydania narzędzi z GitHuba; pierwsze pobranie dało 200 prac, 50 modeli, 50 zbiorów danych i 12 wydań, bez błędów.

Po co: radar ma z czego wybierać tylko wtedy, gdy nowe źródła same wpływają do laboratorium, a każde ma sprawdzoną podstawę korzystania.

Prace naukowe z arXiv (cs.CL, cs.IR, cs.AI, cs.LG, z filtrem tematycznym), wydania modeli o otwartych wagach, otwarte dane publiczne (na przykład portal dane.gov.pl), wydania narzędzi, z których korzystamy. Każdy kanał jako adapter przez Capture API (interfejs wczytujący treści do grafu) i wpis na liście dozwolonych z podstawą korzystania. Gotowe, gdy wszystkie cztery kanały zasilają graf laboratorium. Zależy od F2.2.

### F5.3. Wybór kandydatów z oceną kilku modeli

**Status: zrobione** — dziesięciu kandydatów z radaru (tydzień 2026-W39) oceniły osobno modele trzech rodzin (qwen3.6, gemma-4, gpt-oss); rozrzut co najmniej dwóch punktów wystąpił u ośmiu kandydatów, a czterech odpadło na pytaniu odrzucającym u co najmniej jednego modelu; decyzji G0 właściciela jeszcze nie ma.

Po co: gdy niezależne modele oceniają kandydata różnie, wiadomo, że trzeba się nad nim zastanowić, a ostateczna decyzja należy do człowieka.

Pięć pytań odrzucających i arkusz punktowy (szablon w `templates/`). Pierwszą ocenę wystawiają niezależnie modele trzech różnych rodzin, różnica co najmniej dwóch punktów w którymkolwiek wymiarze oznacza kandydata do dłuższego namysłu. Decyzja człowieka jest zapisywana jako decyzja z bramki G0. Gotowe, gdy dziesięciu kandydatów z radaru przeszło przez ocenę. Zależy od F5.1.

### F5.4. Comiesięczny pomiar nowych modeli

**Status: do zrobienia** — nie zaczęte; zależy od F3, która jest w toku.

Po co: nowe modele wychodzą stale, a jednorazowy pomiar szybko się starzeje; miesięczna tabela pokazuje, jak wyniki zmieniają się w czasie.

Stałe stanowisko pomiarowe z F3 uruchamiane co miesiąc dla nowych modeli lokalnych. Wynik to publiczna tabela porównawcza w czasie, a zarazem ciągły, powtarzalny dowód pracy badawczej. Gotowe, gdy trzy kolejne miesiące mają opublikowane wyniki. Zależy od F3.

### F5.5. Eksperyment: czy graf poprawia wyszukiwanie

**Status: do zrobienia** — nie zaczęte; czeka na F3; F5.3 i F5.8 są zrobione.

Po co: odpowiada na pytanie, czy dokładanie powiązań z grafu do wyszukiwania poprawia wyniki, czy wystarczy samo porównywanie tekstów. Wynik pokaże też, które typy powiązań pomagają, a które szkodzą.

Porównanie wyszukiwania samymi osadzeniami z wyszukiwaniem, które dodatkowo rozwija wyniki po krawędziach grafu, oraz porównanie typów krawędzi, które pomagają, z tymi, które szkodzą. Korpus publiczny, zbiór pytań ze złotymi odpowiedziami przygotowany ręcznie. Metryka rozstrzygająca nDCG@10 (miara tego, jak wysoko w pierwszej dziesiątce wyników są właściwe odpowiedzi). Gotowe, gdy decyzja G1 jest opublikowana. Zależy od F3, F5.3 i F5.8.

### F5.6. Eksperyment: lokalny model osadzeń a model chmurowy

**Status: do zrobienia** — nie zaczęte; czeka na F5.5; F5.8 jest zrobione.

Po co: wysyłanie tekstów do chmury kosztuje i wymaga zaufania; jeśli model lokalny wypada nie gorzej, można z niego korzystać bez tego.

Czy lokalny model osadzeń daje wyniki wyszukiwania nie gorsze od modelu chmurowego na polskim korpusie publicznym. Hipoteza równoważności z progiem zapisanym w karcie. Zapytania do modelu chmurowego tylko z tekstami publicznymi. Gotowe, gdy decyzja G1 jest opublikowana. Zależy od F5.5 i F5.8.

### F5.7. Eksperyment: wymuszanie formatu odpowiedzi

**Status: do zrobienia** — nie zaczęte; czeka na F3; F5.9 jest zrobione.

Po co: model czasem odpowiada prozą zamiast wywołać narzędzie, co psuje automatyczne przetwarzanie odpowiedzi; eksperyment sprawdza, czy z góry zapisany kształt odpowiedzi to eliminuje.

Czy wymuszenie struktury odpowiedzi gramatyką, czyli z góry zapisanym kształtem odpowiedzi (json_schema, GBNF w llama.cpp) eliminuje przypadki, w których model odpowiada prozą zamiast wywołania narzędzia. Metryka: odsetek odpowiedzi zgodnych ze schematem, metryka ochronna: jakość twierdzeń. Gotowe, gdy decyzja G1 jest opublikowana. Zależy od F3 i F5.9.

### F5.8. Rodzaj eksperymentu: wyszukiwanie

**Status: zrobione** — rodzaj eksperymentu „wyszukiwanie” (`retrieval`) działa i jest w repozytorium (1 października 2026): zestaw pytań z ręcznie przygotowanymi wzorcowymi odpowiedziami, czytany ściśle; konfiguracje wyszukiwania (same osadzenia, rozszerzanie po krawędziach grafu, wybrane typy krawędzi, inny model osadzeń przez bramkę laboratorium); miary nDCG@10, recall@k i MRR z przedziałami bootstrapowymi oraz różnicami parami; strony wyników i eksport jak dla innych rodzajów. Przykładowy eksperyment przeszedł przez kolejkę na małym korpusie (60 zadań), a osobny skrypt odtworzył wszystkie 36 opublikowanych liczb. Jedna różnica względem opisu: wzorcowe odpowiedzi pochodzą z ręcznie przygotowanych plików, bo strona oceny z F2.10 nie jest jeszcze podpięta do tego rodzaju.

Po co: kolejka eksperymentów mierzy dziś tylko dwa rodzaje, a bez rodzaju „wyszukiwanie” nie da się uruchomić eksperymentów F5.5 i F5.6.

Kolejka eksperymentów zna dziś rodzaj twierdzeń i zabawkowy. Eksperymenty F5.5 i F5.6 mierzą wyszukiwanie, więc potrzebują własnego rodzaju: zbiór pytań ze złotymi odpowiedziami przygotowany ręcznie (oceny w interfejsie z F2.10), konfiguracje wyszukiwania (same osadzenia, osadzenia z rozwinięciem po krawędziach grafu, wybrane typy krawędzi, inny model osadzeń), metryki nDCG@10, recall@k i MRR z przedziałami bootstrapowymi (zakresami niepewności wyniku) po pytaniach, strony wynikowe i eksport jak w F2.7 i F2.8. Gotowe, gdy eksperyment zabawkowy tego rodzaju przechodzi przez kolejkę na małym korpusie, a jego liczby zgadzają się z niezależnym obliczeniem. Zależy od F2.6, F2.8 i F2.10.

### F5.9. Rodzaj eksperymentu: zgodność formatu odpowiedzi

**Status: zrobione** — rodzaj eksperymentu „zgodność formatu odpowiedzi” (`format_conformity`) działa i jest w repozytorium (1 października 2026): ścisły walidator odpowiedzi względem zapisanego schematu, odsetek zgodnych odpowiedzi z przedziałami Wilsona, różnica między konfiguracjami oraz odwołanie do eksperymentu na twierdzeniach dla miary kontrolnej (jakość twierdzeń), którą liczy sam ten eksperyment. Przykładowy eksperyment przeszedł przez kolejkę, a osobny skrypt odtworzył wszystkie 8 opublikowanych liczb.

Po co: eksperyment F5.7 mierzy zgodność odpowiedzi ze schematem mechanicznie, bez oceny człowieka, a kolejka nie ma jeszcze takiego rodzaju.

Eksperyment F5.7 mierzy mechanicznie, czy odpowiedź modelu zgadza się ze schematem, bez oceny człowieka. Potrzebuje rodzaju eksperymentu z walidatorem schematu, liczeniem odsetka zgodnych odpowiedzi z przedziałami Wilsona (zakresami niepewności odsetka) i jawnym połączeniem z rodzajem twierdzeń dla metryki ochronnej (jakość twierdzeń). Gotowe, gdy eksperyment zabawkowy tego rodzaju przechodzi przez kolejkę, a liczby zgadzają się z niezależnym obliczeniem. Zależy od F2.6.

## Postęp

- 2026-10-01: F5.8 i F5.9. Działają dwa nowe rodzaje eksperymentów. Wyszukiwanie (F5.8) porządkuje dokumenty wybranym modelem osadzeń (ang. embeddings) względem ręcznie przygotowanych wzorcowych odpowiedzi, opcjonalnie rozszerza ranking po krawędziach grafu i podaje nDCG@10, recall@k oraz MRR z przedziałami bootstrapowymi i różnicami parami. Format odpowiedzi (F5.9) sprawdza mechanicznie, czy odpowiedź zgadza się z zapisanym schematem, i podaje odsetek zgodnych odpowiedzi z przedziałami Wilsona. W obu przykładowy eksperyment przeszedł przez kolejkę, a osobny skrypt oparty tylko na bibliotece standardowej odtworzył każdą opublikowaną liczbę (36 i 8). Do rozstrzygnięcia przez właściciela: podpięcie strony oceny z F2.10 jako źródła wzorcowych odpowiedzi dla wyszukiwania, skala ocen i zysk w nDCG oraz sposób, w jaki tryb gramatyki trafia do serwera modeli.
- 2026-09-29: F5.2. Cztery kanały zasilają graf laboratorium: nowe prace z arXiv w kategoriach cs.CL, cs.IR, cs.AI i cs.LG na tematy laboratorium, modele o otwartych wagach z Hugging Face, nowe zbiory z dane.gov.pl i wydania narzędzi, z których laboratorium korzysta (GitHub). Każdy kanał jest na liście dozwolonych źródeł z podstawą korzystania sprawdzoną u źródła, a zapisujemy tylko metadane i abstrakty. Pobieranie idzie przez osobną bramę, która przyjmuje tylko adresy https z tej listy i trzyma przerwy między zapytaniami; test izolacji sprawdza ją co noc. Pierwsze pobranie na serwerze: 200 prac, 50 modeli, 50 zbiorów danych i 12 wydań, bez błędów. Kanały uruchamia co tydzień zadanie radaru.
- 2026-09-29: F5.1. Radar działa: zadanie tygodniowe (niedziela 22:30) pobiera kanały, uruchamia ekstraktor na nowych pracach i składa [stronę radaru](../generated/radar.md) po polsku i po angielsku. Tydzień 2026-W39: 198 prac, 287 hipotez i planów po usunięciu powtórzeń, jedna możliwa sprzeczność, jeden gęsty temat, 17 nowych modeli, zbiorów i wydań. Nagłych wzrostów jeszcze nie liczymy, bo brak czterech tygodni wstecz. Radar pomija artykuły z korpusów eksperymentów i pozycje, które bramka zatrzymałaby jako dane osobowe (w tygodniu 2026-W40 jedną). Warunek ukończenia to cztery tygodnie z rzędu.
- 2026-09-29: F5.3. Dziesięciu kandydatów z radaru z tygodnia 2026-W39 przeszło przez ocenę modeli trzech rodzin (qwen3.6, gemma-4, gpt-oss), każdy osobno, według szablonu wyboru. Osiem ma poprawne odpowiedzi wszystkich trzech modeli, dwie oceny mają brak poprawnej odpowiedzi jednego modelu. Rozrzut co najmniej dwóch punktów w którymś wymiarze wystąpił u ośmiu kandydatów, a czterech odpadło na którymś pytaniu odrzucającym w ocenie co najmniej jednego modelu. Decyzje G0 podejmuje właściciel. Strony radaru za 2026-W39 i oceny bramka zatrzymała jako podobne do materiałów chronionych; czekają na przegląd.
