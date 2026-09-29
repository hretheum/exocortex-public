---
id: how-it-works
lang: pl
counterpart: ../en/04-how-it-works.md
provenance: ai_authored
provenance_metadata:
  agent: Claude Opus 5.5 (Claude Code)
  date: 2026-09-29
  human_validated: false
---

# Jak działa Exocortex R&D

Kto co tu znajdzie:

- Decydenci i osoby z biznesu: po co jest laboratorium i na jakim etapie są prace.
- Właściciele ryzyka i zgodności: co chroni dane i kto zatwierdza kolejne kroki.
- Zespoły danych i ML: jak prowadzimy eksperymenty i jak powtórzyć wynik. Szczegóły są w blokach „Dla zespołów danych i ML” pod tekstem głównym, pełny opis cyklu w dokumencie [Jak działa cykl dowodowy](01-cycle.md), a kolejność prac w [roadmapie](02-roadmap.md).

## Po co jest to laboratorium

Exocortex R&D to publiczne laboratorium, które sprawdza, czy konkretne pomysły na użycie AI w organizacji działają. Dzięki niemu decyzję o wyborze narzędzia albo o ryzyku wdrożenia możesz oprzeć na sprawdzonym wyniku zamiast na opiniach. To samo dotyczy konkretnego projektu albo produktu: wynik podpowiada, jak ustawić w nim daną funkcję, zanim ktoś ją zbuduje. Publikujemy też wyniki pomysłów, które się nie sprawdziły, bo mówią, w co nie inwestować. Wynikom możesz ufać, bo zasady oceny ogłaszamy, zanim cokolwiek policzymy, a cały zapis prac jest jawny i każdy może go powtórzyć.

Przykład: czy wyszukiwarka dokumentów może działać na modelu AI uruchomionym we własnej infrastrukturze, bez wysyłania tekstów do chmury, i znajdować nie gorzej niż usługa chmurowa? Na to pytanie odpowie hipoteza [Model lokalny czy chmurowy](experiments/local-vs-cloud-embeddings/overview.md). Eksperyment jest zaplanowany i nie ma jeszcze wyniku.

### Dla zespołów danych i ML: czym to się różni od typowego raportu

Wyniki prac nad AI zwykle poznajemy jako gotowy raport. Nie widać w nim, co sprawdzano wcześniej i porzucono, kiedy ustalono próg sukcesu ani czy ustalono go przed pomiarem, czy po zobaczeniu liczb. Tutaj publikujemy całą drogę. Kartę hipotezy z progiem zamrażamy i publikujemy przed pomiarem, a potem dokładamy dane z sumami kontrolnymi, surowe wyniki ze skryptem, który je wylicza, oraz raport, w którym każda liczba ma źródło. Wyniki negatywne publikujemy tak samo jak pozytywne.

## W jakich decyzjach to pomaga

Wynik z laboratorium przydaje się, gdy trzeba wybrać jedno z kilku rozwiązań albo ustawić funkcję w konkretnym produkcie i uzasadnić ten wybór. Poniżej pytania, z którymi przychodzą duże organizacje, i to, co laboratorium już o nich sprawdza albo zaplanowało. Żadne z nich nie ma jeszcze wyniku.

| Chcę | Pytanie, na które szukamy odpowiedzi | Stan |
|---|---|---|
| Zbudować wiedzę organizacji, żeby pracownicy szybko znajdowali odpowiedzi w firmowych dokumentach | Czy wyszukiwanie, które rozwija wyniki po powiązaniach między treściami, znajduje lepiej niż samo wyszukiwanie po znaczeniu? Hipoteza [Graf a wyszukiwanie](experiments/graph-vs-search/overview.md). | zaplanowane |
| Trzymać dokumenty niejawne u siebie i nadal dobrze je wyszukiwać po polsku | Czy model uruchomiony na własnym sprzęcie znajduje nie gorzej niż usługa w chmurze? Hipoteza [Model lokalny czy chmurowy](experiments/local-vs-cloud-embeddings/overview.md). | karta hipotezy w przygotowaniu |
| Streszczać dokumenty organizacji tak, żeby streszczenie nie zamieniało planu w fakt | Czy obowiązkowe pole trybu przy wyciąganiu twierdzeń zmniejsza liczbę takich zamian? Hipoteza [Zamiar czy fakt](experiments/intent-vs-fact/overview.md). | przygotowanie, karta czeka na zatwierdzenie |
| Zbudować asystenta AI, który korzysta z systemów firmy zamiast zgadywać | Czy narzucenie struktury odpowiedzi eliminuje odpowiedzi prozą tam, gdzie program oczekuje wywołania narzędzia? Hipoteza [Wymuszony format odpowiedzi](experiments/enforced-answer-format/overview.md). | zaplanowane |
| Pokazać w przetargu, że projekt referencyjny ma pokrycie w dowodach | Czy kartę projektu referencyjnego da się złożyć z zapisu prac tak, żeby każde zdanie wskazywało dowód? | narzędzie zaplanowane |

Wynik z laboratorium mówi, co działa na zmierzonych danych publicznych. Nie zastępuje pilota na danych Twojej organizacji, ale pokazuje, od czego zacząć i jak go zaplanować, żeby dało się go sprawdzić.

Każda hipoteza dostanie na swojej stronie sekcję o zastosowaniach biznesowych: kto może skorzystać z wyniku, na jakim wyniku to się opiera i jak mocny jest dowód. Siłę dowodu wylicza stała reguła ze stanu prac, więc hipoteza bez wyniku jest wprost opisana jako „hipoteza, bez dowodu”. Każdą wersję tej sekcji zatwierdza właściciel projektu. Sekcję właśnie budujemy.

Z zapisu prac da się też złożyć kartę projektu referencyjnego, na przykład do przetargu, w której każde zdanie wskazuje dowód. Narzędzie, które składa taką kartę, jest zaplanowane.

## Z jakimi problemami przychodzą zespoły produktowe

Pytania zmieniają się razem z odpowiedzialnością. Product manager pyta o jedną funkcję, lider obszaru o całą ścieżkę użytkownika, a head of product o portfel pomysłów i o to, jak uzasadnić decyzje zarządowi. Przy każdym pytaniu jest to, co laboratorium ma dziś: metoda albo hipoteza, która jest już na liście.

| Kto pyta | Problem, z którym przychodzi | Co laboratorium może sprawdzić | Co dziś mamy |
|---|---|---|---|
| Product manager | Chcę dodać do aplikacji mobilnej wyszukiwanie albo asystenta, ale nie wiem, czy użytkownicy dostaną odpowiedzi, którym mogą ufać. | Jaka część odpowiedzi jest poprawna i oparta na źródle, oceniona na ślepo przez ludzi, zanim funkcja trafi do użytkowników? | pilot z oceną na ślepo i spisem typowych błędów; kalibracja sędziego automatycznego jest zaplanowana |
| Product manager | Chcę zbadać potencjał funkcji, zanim ktoś ją zbuduje. | Co musi być prawdą, żeby funkcja miała sens, i jaki wynik małego testu ją obali? | karta hipotezy z progiem zamrożonym przed pomiarem i szybki test trwający od kilku godzin do dwóch dni |
| Product manager | Funkcja nie może wysyłać danych użytkownika do zewnętrznej usługi. | Czy model uruchomiony na własnym serwerze daje jakość nie gorszą niż usługa w chmurze? Test dotyczy serwera. Modelu działającego na telefonie nie sprawdzamy. | hipoteza [Model lokalny czy chmurowy](experiments/local-vs-cloud-embeddings/overview.md), karta w przygotowaniu |
| Product manager | Nie wiem, co pokazać użytkownikowi, gdy model się myli albo odpowie w złym formacie. | Jak często model odpowiada prozą zamiast strukturą, której oczekuje aplikacja, i jakie błędy zdarzają się najczęściej? | hipoteza [Wymuszony format odpowiedzi](experiments/enforced-answer-format/overview.md), zaplanowana; spis typowych błędów w każdym pilocie |
| Lider obszaru (senior albo group product manager) | Odpowiadam za ścieżkę, w której użytkownik szuka informacji, i chcę wiedzieć, co poprawi wyszukiwanie w pierwszej kolejności. | Czy rozwijanie wyników po powiązaniach między treściami poprawia wyszukiwanie ponad samo wyszukiwanie po znaczeniu? | hipoteza [Graf a wyszukiwanie](experiments/graph-vs-search/overview.md), zaplanowana |
| Lider obszaru | Mam więcej pomysłów na funkcje AI niż zespół do ich zbudowania. | Które pomysły da się tanio zmierzyć i obalić, a które odpadają, zanim ktokolwiek zacznie pracę? | pięć pytań odrzucających, arkusz punktowy i cotygodniowy przegląd nowych prac i modeli |
| Lider obszaru | Potrzebuję miary sukcesu funkcji AI, która nie pogorszy reszty produktu. | Jaka miara rozstrzyga o sukcesie i jaka miara ochronna nie może spaść? | karta hipotezy wymaga miary rozstrzygającej i miary ochronnej |
| Head of product | Zarząd pyta, w co inwestujemy w AI i skąd wiemy, że to działa. | Jak prowadzić portfel pomysłów z bramkami, na których zapada decyzja o dalszym kroku albo o zatrzymaniu? | cykl dowodowy z dwiema bramkami; decyzje publikujemy razem z wynikami |
| Head of product | Muszę zdecydować, czy budować własne rozwiązanie, czy użyć modelu z chmury. | Ile jakości traci się przy przejściu na własny model i czy własny sprzęt to wytrzyma? | ta sama hipoteza [Model lokalny czy chmurowy](experiments/local-vs-cloud-embeddings/overview.md) mierzy jakość i wykonalność osobno |
| Head of product | Muszę pokazać audytowi i działowi ryzyka, jak podjęliśmy decyzję o funkcji AI. | Czy niezależna osoba odtworzy z zapisu prac, dlaczego wybrano to rozwiązanie? | jawny zapis cyklu z kartą hipotezy i decyzjami z bramek |
| Head of product | Chcę jednego standardu oceny funkcji AI dla wszystkich moich zespołów. | Czy wspólny szablon karty hipotezy, notatki z przebiegu i decyzji z bramki wystarcza, żeby zespoły oceniały funkcje tak samo? | szablony tych trzech dokumentów |

Laboratorium nie bada użytkowników Twojej aplikacji. Nie zmierzy, jak zachowa się Twój produkt ani jak zmieni się wykorzystanie funkcji. Daje sprawdzony wynik na danych publicznych, metodę pilota do przeprowadzenia u siebie i wzór karty hipotezy, dzięki któremu kryterium sukcesu jest zapisane przed pomiarem.

## Jak to działa w skrócie

Laboratorium korzysta wyłącznie ze źródeł publicznych i naszych własnych tekstów, a wszystko, co wytwarza, możesz od razu przeczytać. Trafia to do publicznego repozytorium, czyli publicznej szafy na dokumenty i kod, w której zachowuje się historię każdej zmiany. Zanim cokolwiek tam trafi, przechodzi przez bramkę publikacji. Publikacja odbywa się sama, co 15 minut, więc repozytorium zawsze pokazuje stan aktualny.

![Schemat: laboratorium czyta tylko źródła publiczne, wyniki przechodzą przez bramkę publikacji do publicznego repozytorium, a dane prywatne i klienckie są za murem, poza laboratorium.](img/1-overview.svg)

Dane prywatne i projekty klientów są poza laboratorium, za murem: osobna baza, osobna sieć, brak połączenia w żadną stronę. Dwie zasady obowiązują od początku. Nie używamy żadnych materiałów od klientów, a wszystko, co laboratorium wytwarza, jest publiczne od razu, po polsku i po angielsku.

## Co chroni przed wyciekiem

Żaden plik nie trafia do publicznego repozytorium bez automatycznych kontroli, a o każdym zatrzymanym pliku decyduje człowiek. Te kontrole nazywamy bramką publikacji. Każdy nowy dokument musi przejść wszystkie pięć.

![Schemat: nowy dokument przechodzi pięć kontroli. Jeśli wszystkie się powiodą, trafia do repozytorium, jeśli nie, czeka na decyzję człowieka.](img/2-gate.svg)

Pierwsza kontrola szuka nazw i danych osobowych, które nie mogą wyjść na zewnątrz, także w ukrytych danych plików. Lista zakazanych nazw jest prywatna, a w repozytorium leżą tylko jej cyfrowe odciski, z których nie da się odczytać żadnej nazwy. Druga porównuje tekst z prywatnym zbiorem i odpowiada wyłącznie „podobny” albo „niepodobny”, żeby nie wyszedł nawet przeredagowany fragment. Trzecia pilnuje, żeby wersja polska i angielska zgadzały się w liczbach, nagłówkach, linkach i tabelach. Czwarta sprawdza budowę pliku. Piąta wyłapuje nawyki typowe dla tekstów pisanych bez namysłu przez model AI, bo dokumenty mają się czytać jak tekst napisany przez człowieka.

Kiedy coś się nie zgadza, plik nie znika. Zostaje tam, gdzie był, autor dostaje powiadomienie z powodem, a decyzję podejmuje człowiek.

Kontrole też są sprawdzane. Co noc dostają zestaw plików z celowo wstawionymi wyciekami i muszą zatrzymać każdy z nich. Jeśli któryś przejdzie, publikacja staje, dopóki ktoś tego nie naprawi.

## Izolacja laboratorium

Laboratorium nie ma dostępu do danych klientów ani prywatnych notatek i nie może go uzyskać nawet przez pomyłkę.

![Schemat: dwa oddzielone światy, prywatny i laboratorium. Do laboratorium wchodzą tylko źródła z listy dozwolonych, a co noc test sprawdza izolację.](img/6-isolation.svg)

Laboratorium ma własną bazę danych i własną, zamkniętą sieć. Z prywatnych dokumentów widzi tylko jeden folder z opublikowanymi tekstami, i to wyłącznie do odczytu. Nawet pomyłka w ustawieniach nie otwiera drogi do prywatnej bazy, bo taka droga po prostu nie istnieje. Poczty ani notatek klientów nie ma na liście dozwolonych źródeł i nie będzie.

Izolację sprawdza test, co noc. Z wnętrza laboratorium próbuje on dotrzeć do prywatnej bazy każdym znanym adresem i sprawdza, czy prywatne foldery są niewidoczne. Wszystkie próby muszą się nie udać, a każda inna odpowiedź jest alarmem.

## Droga jednej hipotezy

O każdym kolejnym kroku decyduje człowiek, a większość pomysłów odpada wcześnie, po krótkim teście. Hipoteza to pytanie, na które chcemy odpowiedzieć liczbą, na przykład: czy ten sposób streszczania artykułów zamienia zamiary autorów w fakty.

![Schemat: droga hipotezy w siedmiu krokach, od sygnału, przez kartę hipotezy zamrożoną przed pomiarem i dwie bramki, do planu dla dużej organizacji.](img/3-path.svg)

Pomysły przychodzą z cotygodniowego przeglądu nowych publicznych prac, modeli i danych. Pomysł odpada, jeśli nie wiadomo, po co go sprawdzać, nie ma danych, nie jest legalny, nie da się go zmierzyć albo da się go załatwić prościej, bez AI. Zanim cokolwiek policzymy, zapisujemy i publikujemy kartę hipotezy: co sprawdzamy i jaki wynik by nas obalił. Potem są trzy stopnie: szybki test na małej próbie, na którym kończy się większość pomysłów, pilot na większej próbie oceniany przez ludzi i na końcu plan wdrożenia w dużej organizacji, oparty na liczbach z pilota. Po szybkim teście i po pilocie człowiek decyduje, czy idziemy dalej.

### Dla zespołów danych i ML: jak to jest zrobione

Kandydatów wstępnie ocenia kilka modeli różnych rodzin, każdy osobno. Duży rozrzut ocen oznacza, że nad kandydatem trzeba się zastanowić dłużej. Decyzję podejmuje człowiek.

Karta hipotezy zawiera to, co dokładnie sprawdzamy, wynik, który obali hipotezę, jedną liczbę rozstrzygającą, punkt odniesienia i próby. Po zatwierdzeniu laboratorium liczy sumę kontrolną karty i publikuje ją, zanim cokolwiek zostanie policzone. Data publikacji pokazuje, że metody nie dopasowaliśmy do wyniku. Zmiana zdania oznacza nową wersję karty, a poprzednia zostaje widoczna.

Szybki test (skala S) trwa od kilku godzin do dwóch dni i działa na lokalnych modelach. Część próby odkładamy jako zbiór kontrolny i otwieramy ją tylko raz, na końcu. Na bramce wynik porównujemy z progiem z karty, a człowiek wybiera: idziemy dalej, kończymy, zmieniamy hipotezę, odkładamy z zapisanym warunkiem powrotu albo zamykamy, bo pytanie jest rozstrzygnięte. Pilot (skala M) to większa próba oceniana przez ludzi na ślepo, porównanie kilku wariantów, spis typowych błędów, koszt i czas. Wynik pilota musi wypróbować ktoś inny niż autor, a na końcu jest druga bramka. Skala L to tylko dokument: plan wdrożenia dla tysięcy użytkowników z liczbami z pilota.

## Ostatnie hipotezy

Tu widać, co laboratorium sprawdza teraz. Żadna hipoteza nie ma jeszcze wyniku.

![Schemat: cztery hipotezy i ich etap na drodze od kandydata do raportu. Jedna jest w przygotowaniu, trzy są planowane.](img/4-hypotheses.svg)

| Hipoteza | Pytanie | Stan |
|---|---|---|
| Zamiar czy fakt | Czy wyciąganie twierdzeń z tekstu odróżnia fakty od zamiarów, hipotez i zapowiedzi, oraz czy streszczenia nie zamieniają zamiaru w fakt. | Przygotowanie: 2478 artykułów gotowych, karta hipotezy czeka na zatwierdzenie |
| Graf a wyszukiwanie | Czy rozwijanie wyników wyszukiwania po powiązaniach między treściami poprawia ich jakość. | Planowana |
| Model lokalny czy chmurowy | Czy lokalny model do wyszukiwania podobnych tekstów nie ustępuje chmurowemu na polskim korpusie publicznym. | Karta hipotezy w przygotowaniu |
| Wymuszony format odpowiedzi | Czy narzucenie modelowi struktury odpowiedzi eliminuje przypadki, gdy odpowiada prozą zamiast wywołać narzędzie. | Planowana |

Karta pierwszej hipotezy jest napisana i czeka na zatwierdzenie przez właściciela projektu. Dopiero po jej zamrożeniu laboratorium uruchomi eksperyment. Każda nowa pozycja na liście też dostaje kartę, zanim cokolwiek zostanie zmierzone.

## Architektura

Ta sekcja pokazuje zespołom danych i ML, skąd laboratorium bierze dane i którędy wyniki wychodzą na zewnątrz. Całość ma pięć warstw. Na wejściu są źródła publiczne, przepuszczane przez listę dozwolonych: nowe źródło to wpis z uzasadnieniem i podstawą prawną, na przykład abstrakty z arXiv, które są udostępniane na zasadach CC0.

![Schemat: architektura w pięciu warstwach. Źródła publiczne wchodzą przez listę dozwolonych do laboratorium z czterema modułami, wyniki przechodzą przez bramkę publikacji do publicznego repozytorium.](img/5-architecture.svg)

W środku jest laboratorium z czterema modułami. Graf wiedzy zamienia teksty na twierdzenia i powiązania między nimi. Modele lokalne działają bez wysyłania danych do chmury. Moduł pomiarów porównuje wiele konfiguracji na tej samej próbie. Zapis cyklu przechowuje karty hipotez, przebiegi i decyzje z bramek. Wyniki wychodzą przez bramkę publikacji do publicznego repozytorium, a z niego powstają strony wynikowe i karta projektu referencyjnego. Rysunek pokazuje architekturę docelową, a to, co już działa, jest zaznaczone na zielono.

## Jak sprawdzić wynik

Każdy wynik da się sprawdzić bez wierzenia nam na słowo. Dlatego każdy eksperyment zostawia cztery ślady.

![Schemat: czterostopniowa ścieżka dowodowa, od zapowiedzi, przez dane i wynik, do raportu. Każdy może powtórzyć kroki drugi i trzeci.](img/7-evidence.svg)

Zapowiedź to karta hipotezy z datą i sumą kontrolną. Dane to lista użytych tekstów z sumami kontrolnymi, więc każdy może pobrać dokładnie to samo. Wynik to surowe liczby i skrypt, który je wylicza. Raport to tekst, w którym każde zdanie wskazuje plik albo wiersz danych. Liczba bez źródła nie wchodzi do raportu.

### Dla zespołów danych i ML: jak powtórzyć wynik

Kroki drugi i trzeci może powtórzyć każdy: wystarczy pobrać dane, uruchomić skrypt i porównać liczby z raportem. Przed naciąganiem wyników chronią jeszcze zamrożona karta, zbiór kontrolny otwierany tylko raz i historia w repozytorium, której nikt nie przepisuje. Tekst karty sprawdzamy dodatkowo narzędziem, które wyłapuje zdania opisujące plan tak, jakby był już wykonany.

## Kto co robi

Każdą decyzję podejmuje człowiek, a maszyna robi to, co powtarzalne.

| Czynność | Maszyna | Człowiek |
|---|---|---|
| Zbieranie sygnałów | przegląd źródeł raz w tygodniu | dopisuje własne pomysły |
| Wybór kandydatów | wstępna ocena kilkoma modelami | decyduje |
| Karta hipotezy | podpowiada metryki i wielkość próby | pisze i zatwierdza |
| Eksperyment | uruchamia, liczy, zapisuje | ocenia próbki na ślepo |
| Bramka | zestawia wynik z progiem | decyduje |
| Tłumaczenie | pierwsza wersja lokalnym modelem | poprawia |
| Publikacja | skanuje i publikuje co 15 minut | rozstrzyga zatrzymane pliki |

## Gdzie jesteśmy

Stan na 29 września 2026. Oddzielamy to, co działa, od tego, co jest w budowie, i od samych planów.

![Schemat: sześć faz roadmapy. Laboratorium i pierwszy eksperyment są w budowie, cztery pozostałe fazy są planowane.](img/8-status.svg)

Rysunek pokazuje fazy roadmapy, a bieżący stan zadań jest w [roadmapie](02-roadmap.md).

Działają kontrole przed publikacją z nocnymi testami i publikacja co 15 minut. Repozytorium jest publiczne od 29 września, a strona lab.exocortex.zone pokazuje dossier hipotez i stan prac. Laboratorium ma własną bazę, izolację sprawdzaną co noc, listę dozwolonych źródeł, kolejkę eksperymentów i pierwsze karty hipotez. Co tydzień przegląda nowe publiczne prace (F5).

W budowie jest pierwszy eksperyment (F3): jego karta czeka na zatwierdzenie i nic jeszcze nie zostało zmierzone. W budowie jest też sekcja o zastosowaniach biznesowych na stronach hipotez (F8).

Dopiero planujemy kartę projektu referencyjnego składaną z zapisanych wyników (F4), kolejne eksperymenty (F5), współpracę z drugim ekspertem (F6) i publiczne demo (F7).

## Najczęstsze pytania

### Czym różni się Exocortex R&D od Exocortexa

Exocortex to system do zbierania i łączenia wiedzy. Exocortex R&D to laboratorium, które wyrosło z tego projektu i służy do sprawdzania pomysłów dotyczących AI. Laboratorium jest publiczne, a prywatne dane i projekty klientów są od niego całkowicie oddzielone. O samym Exocortexie możesz przeczytać na stronie [projektu Exocortex](https://exocortex.zone).

### Czy do laboratorium trafiają materiały klientów albo prywatne notatki

Nie, nigdy. Dane wejściowe pochodzą ze źródeł publicznych albo tworzymy je sami. Co noc sprawdzamy testem, że laboratorium nie ma żadnej drogi do prywatnej bazy.

### Skąd wiadomo, że bramka działa

Co noc sprawdzamy ją na plikach z celowo wstawionymi wyciekami. Jeśli choć jeden przejdzie, publikacja staje. Wynik testu jest zapisywany.

### Po co publikować wyniki negatywne

Bo pokazują, że nie wybieramy tylko tego, co wyszło dobrze, i oszczędzają czas komuś, kto chciałby sprawdzić to samo. Wynik negatywny jest wynikiem.

### Kto decyduje, czy hipoteza się potwierdziła

Próg zapisujemy w karcie przed pomiarem, więc o wyniku rozstrzyga liczba ustalona z góry. Bramkę zatwierdza człowiek, a próbki w pilocie oceniają ludzie na ślepo.

### Czy te dokumenty pisze AI

Pierwsze wersje pisze model AI. Każdy plik ma w nagłówku zapisane, kto go napisał i czy człowiek go przejrzał. Przegląd przez właściciela projektu jest jeszcze przed nami.

### Czy repozytorium jest już publiczne

Tak, od 29 września 2026, razem ze stroną lab.exocortex.zone.

## Słowniczek

| Pojęcie | Co znaczy |
|---|---|
| laboratorium | Miejsce, w którym sprawdzamy pomysły dotyczące AI. Nie ma dostępu do danych prywatnych. |
| repozytorium | Publiczna szafa na dokumenty i kod z historią każdej zmiany. |
| bramka publikacji | Zestaw kontroli, który zatrzymuje plik, jeśli znajdzie w nim coś niedozwolonego. |
| hipoteza | Pytanie, na które odpowiadamy liczbą. |
| karta hipotezy | Jednostronicowy opis hipotezy, sposobu sprawdzenia i progu, przy którym uznajemy ją za potwierdzoną albo odrzuconą. |
| zbiór kontrolny | Część próby odłożona z góry i otwarta tylko raz, na końcu. |
| suma kontrolna | Krótki cyfrowy odcisk pliku. Zmiana choćby jednego znaku zmienia odcisk. |
| ocena na ślepo | Ocena, w której oceniający nie wie, który wariant ocenia. |
| wynik negatywny | Wynik, który nie potwierdził hipotezy. Publikujemy go tak samo jak pozostałe. |
| lista dozwolonych źródeł | Spis miejsc, z których laboratorium może czytać, każde z uzasadnieniem. |
