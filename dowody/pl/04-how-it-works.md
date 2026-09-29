---
id: how-it-works
lang: pl
counterpart: ../en/04-how-it-works.md
provenance: ai_authored
provenance_metadata:
  agent: Claude Sonnet 5.5 (Cowork)
  date: 2026-09-28
  human_validated: false
---

# Jak działa Exocortex R&D

Ten tekst wyjaśnia bez żargonu, po co jest Exocortex R&D i jak działa. Szczegółowy opis cyklu jest w dokumencie [Jak działa cykl dowodowy](01-cycle.md), a kolejność budowy w [roadmapie](02-roadmap.md).

## Po co jest to laboratorium

Wyniki prac nad sztuczną inteligencją zwykle poznajemy jako gotowy raport. Nie widać w nim, co sprawdzano wcześniej i porzucono, kiedy ustalono próg sukcesu ani czy ustalono go przed pomiarem, czy po zobaczeniu liczb. Exocortex R&D robi odwrotnie: zapisuje i publikuje całą drogę, od zapowiedzi, przez dane i wynik, do raportu. Kto chce, może prześledzić ją i powtórzyć.

Z tego wynikają trzy rzeczy. Wyniki negatywne są publikowane tak samo jak pozytywne, bo też są wynikiem. Każda liczba w raporcie ma źródło. A z zapisu prac da się złożyć rzetelną kartę projektu referencyjnego, na przykład do przetargu, w której każde zdanie wskazuje dowód.

Laboratorium powstało jako rozwinięcie projektu Exocortex, systemu do zbierania i łączenia wiedzy. Jeśli chcesz o nim poczytać, zacznij od strony [projektu Exocortex](https://exocortex.zone). Tutaj opisujemy tylko to, co dotyczy laboratorium.

## Jak to działa w skrócie

Laboratorium czyta wyłącznie źródła publiczne i nasze własne teksty. Wszystko, co wytwarza, trafia do publicznego repozytorium, czyli publicznej szafy na dokumenty i kod, w której zachowuje się historię każdej zmiany. Zanim cokolwiek tam trafi, przechodzi przez bramkę publikacji. Publikacja odbywa się sama, co 15 minut, więc repozytorium zawsze pokazuje stan aktualny.

![Schemat: laboratorium czyta tylko źródła publiczne, wyniki przechodzą przez bramkę publikacji do publicznego repozytorium, a dane prywatne i klienckie są za murem, poza laboratorium.](img/1-overview.svg)

Dane prywatne i projekty klientów są poza laboratorium, za murem: osobna baza, osobna sieć, brak połączenia w żadną stronę. Dwie zasady obowiązują od początku. Nie używamy żadnych materiałów od klientów, a wszystko, co laboratorium wytwarza, jest publiczne od razu, po polsku i po angielsku.

## Bramka publikacji

Bramka to zestaw automatycznych kontroli. Każdy nowy dokument musi przejść wszystkie pięć.

![Schemat: nowy dokument przechodzi pięć kontroli. Jeśli wszystkie się powiodą, trafia do repozytorium, jeśli nie, czeka na decyzję człowieka.](img/2-gate.svg)

Pierwsza kontrola szuka nazw i danych osobowych, które nie mogą wyjść na zewnątrz, także w ukrytych danych plików. Lista zakazanych nazw jest prywatna, a w repozytorium leżą tylko jej cyfrowe odciski, z których nie da się odczytać żadnej nazwy. Druga porównuje tekst z prywatnym zbiorem i odpowiada wyłącznie „podobny” albo „niepodobny”, żeby nie wyszedł nawet przeredagowany fragment. Trzecia pilnuje, żeby wersja polska i angielska zgadzały się w liczbach, nagłówkach, linkach i tabelach. Czwarta sprawdza budowę pliku. Piąta wyłapuje nawyki typowe dla tekstów pisanych bez namysłu przez model AI, bo dokumenty mają się czytać jak tekst napisany przez człowieka.

Kiedy coś się nie zgadza, plik nie znika. Zostaje tam, gdzie był, autor dostaje powiadomienie z powodem, a decyzję podejmuje człowiek.

Bramkę też trzeba kontrolować. Co noc dostaje zestaw plików z celowo wstawionymi wyciekami i musi zatrzymać każdy z nich. Jeśli któryś przepuści, publikacja staje, dopóki ktoś tego nie naprawi.

## Droga jednej hipotezy

Hipoteza to pytanie, na które chcemy odpowiedzieć liczbą, na przykład: czy ten sposób streszczania artykułów zamienia zamiary autorów w fakty. Każda przechodzi tę samą drogę.

![Schemat: droga hipotezy w siedmiu krokach, od sygnału, przez kartę hipotezy zamrożoną przed pomiarem i dwie bramki, do planu dla dużej organizacji.](img/3-path.svg)

Zaczyna się od sygnału: raz w tygodniu laboratorium przegląda nowe publiczne prace, modele i dane. Kandydat na hipotezę odpada, jeśli na którekolwiek z pięciu pytań odpowiedź brzmi „nie”: czy wiadomo, po co to robimy, czy są dane, czy to legalne, czy da się to zmierzyć i czy nie da się tego załatwić prościej, bez AI. Pierwszą ocenę wystawia kilka modeli różnych rodzin, każdy osobno, ale decyzję podejmuje człowiek.

Sercem całego cyklu jest karta hipotezy. Zapisujemy w niej, co dokładnie sprawdzamy, jaki wynik by nas obalił i którą jedną liczbą rozstrzygniemy. Potem kartę zamrażamy i publikujemy, zanim cokolwiek zostanie policzone. Data publikacji jest dowodem, że metody nie dopasowaliśmy do wyniku. Jeśli zmienimy zdanie, powstaje nowa wersja karty, a poprzednia zostaje widoczna.

Potem są trzy stopnie. Szybki test trwa od kilku godzin do dwóch dni i działa na małej próbie; część próby zostaje zamknięta i otwieramy ją raz, na samym końcu. Większość pomysłów kończy się właśnie tu. Wynik porównujemy z progiem z karty na bramce, gdzie człowiek wybiera: idziemy dalej, kończymy, zmieniamy hipotezę albo odkładamy z zapisanym warunkiem powrotu. Pilot to większa próba oceniana na ślepo przez ludzi, z drugą bramką na końcu. Ostatni stopień to tylko dokument: plan, jak przeprowadzić takie wdrożenie w dużej organizacji, z liczbami wziętymi z pilota.

## Ostatnie hipotezy

Tak wygląda lista hipotez i etap, na którym każda jest dziś.

![Schemat: cztery hipotezy i ich etap na drodze od kandydata do raportu. Jedna jest w przygotowaniu, trzy są planowane.](img/4-hypotheses.svg)

| Hipoteza | Pytanie | Stan |
|---|---|---|
| F3. Zamiar czy fakt | Czy wyciąganie twierdzeń z tekstu odróżnia fakty od zamiarów, hipotez i zapowiedzi, oraz czy streszczenia nie zamieniają zamiaru w fakt. | Przygotowanie: korpus 2478 artykułów gotowy, karta hipotezy przed nami |
| F5.5. Graf a wyszukiwanie | Czy rozwijanie wyników wyszukiwania po powiązaniach między treściami poprawia ich jakość. | Planowana |
| F5.6. Model lokalny czy chmurowy | Czy lokalny model do wyszukiwania podobnych tekstów nie ustępuje chmurowemu na polskim korpusie publicznym. | Planowana |
| F5.7. Wymuszony format odpowiedzi | Czy narzucenie modelowi struktury odpowiedzi eliminuje przypadki, gdy odpowiada prozą zamiast wywołać narzędzie. | Planowana |

Na dziś żadna hipoteza nie ma jeszcze zamrożonej karty ani wyniku. Lista rośnie razem z laboratorium, a każda nowa pozycja dostaje kartę, zanim cokolwiek zostanie zmierzone.

## Architektura

Całość ma pięć warstw. Na wejściu są źródła publiczne, przepuszczane przez listę dozwolonych: nowe źródło to wpis z uzasadnieniem i podstawą prawną, na przykład abstrakty z arXiv, które są udostępniane na zasadach CC0.

![Schemat: architektura w pięciu warstwach. Źródła publiczne wchodzą przez listę dozwolonych do laboratorium z czterema modułami, wyniki przechodzą przez bramkę publikacji do publicznego repozytorium.](img/5-architecture.svg)

W środku jest laboratorium z czterema modułami. Graf wiedzy zamienia teksty na twierdzenia i powiązania między nimi. Modele lokalne działają bez wysyłania danych do chmury. Moduł pomiarów porównuje wiele konfiguracji na tej samej próbie. Zapis cyklu przechowuje karty hipotez, przebiegi i decyzje z bramek. Wyniki wychodzą przez bramkę publikacji do publicznego repozytorium, a z niego powstają strony wynikowe i karta projektu referencyjnego. Rysunek pokazuje architekturę docelową, a to, co już działa, jest zaznaczone na zielono.

## Izolacja laboratorium

Zaufanie do laboratorium opiera się na tym, że nie ma ono dostępu do niczego, czego nie powinno widzieć.

![Schemat: dwa oddzielone światy, prywatny i laboratorium. Do laboratorium wchodzą tylko źródła z listy dozwolonych, a co noc test sprawdza izolację.](img/6-isolation.svg)

Laboratorium ma własną bazę danych i własną, zamkniętą sieć. Z prywatnych dokumentów widzi tylko jeden folder z opublikowanymi tekstami, i to wyłącznie do odczytu. Nawet pomyłka w ustawieniach nie otwiera drogi do prywatnej bazy, bo taka droga po prostu nie istnieje. Poczty ani notatek klientów nie ma na liście dozwolonych źródeł i nie będzie.

Izolację sprawdza test, co noc. Z wnętrza laboratorium próbuje on dotrzeć do prywatnej bazy każdym znanym adresem i sprawdza, czy prywatne foldery są niewidoczne. Wszystkie próby muszą się nie udać, a każda inna odpowiedź jest alarmem.

## Jak sprawdzić wynik

Wynik ma wartość tylko wtedy, gdy da się go sprawdzić bez wiary nam na słowo. Dlatego każdy eksperyment zostawia cztery ślady.

![Schemat: czterostopniowa ścieżka dowodowa, od zapowiedzi, przez dane i wynik, do raportu. Każdy może powtórzyć kroki drugi i trzeci.](img/7-evidence.svg)

Zapowiedź to karta hipotezy z datą i sumą kontrolną. Dane to lista użytych tekstów z sumami kontrolnymi, więc każdy może pobrać dokładnie to samo. Wynik to surowe liczby i skrypt, który je wylicza. Raport to tekst, w którym każde zdanie wskazuje plik albo wiersz danych. Liczba bez źródła nie wchodzi do raportu. Kroki drugi i trzeci może powtórzyć każdy: wystarczy pobrać dane, uruchomić skrypt i porównać liczby z raportem.

Przed naciąganiem wyników chronią nas jeszcze trzy rzeczy: zamrożona karta, zbiór kontrolny otwierany tylko raz i historia w repozytorium, której nikt nie przepisuje. Tekst karty sprawdzamy dodatkowo narzędziem, które wyłapuje zdania opisujące plan tak, jakby był już wykonany.

## Kto co robi

Maszyna robi to, co powtarzalne, a człowiek to, co wymaga decyzji.

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

Stan na 28 września 2026. Rozdzielamy tu trzy rzeczy, żeby nic nie wyglądało na gotowe, choć jeszcze nie jest.

![Schemat: osiem faz roadmapy. Bramka i repozytorium działają, laboratorium i pierwszy eksperyment są w budowie, cztery pozostałe fazy są planowane.](img/8-status.svg)

Działa bramka publikacji z nocnymi testami (F0) oraz mechanizm, który co 15 minut przenosi sprawdzone dokumenty do repozytorium (F1). Samo repozytorium jest jeszcze prywatne. Zmienimy to po siedmiu nocach testu bramki z rzędu i po przeglądzie właściciela projektu, według warunków zapisanych w roadmapie.

W budowie jest laboratorium (F2): ma już własną bazę, izolację sprawdzaną co noc i listę dozwolonych źródeł, a brakuje jeszcze obsługi kart hipotez, decyzji z bramek i tabel eksperymentów. Pierwszy eksperyment (F3) ma gotowy korpus, ale jeszcze niczego nie zmierzył.

Dopiero planujemy kartę projektu referencyjnego składaną z zapisanych wyników (F4), cotygodniowy przegląd źródeł i kolejne eksperymenty (F5), skalowanie i współpracę z drugim ekspertem (F6) oraz publiczne demo (F7). Na razie nie ma tam ani jednego ukończonego zadania.

## Najczęstsze pytania

### Czym różni się Exocortex R&D od Exocortexa

Exocortex to system do zbierania i łączenia wiedzy. Exocortex R&D to laboratorium, które wyrosło z tego projektu i służy do sprawdzania pomysłów dotyczących AI. Laboratorium jest publiczne, a prywatne dane i projekty klientów są od niego całkowicie oddzielone.

### Czy do laboratorium trafiają materiały klientów albo prywatne notatki

Nie, nigdy. Dane wejściowe pochodzą ze źródeł publicznych albo tworzymy je sami. Co noc sprawdzamy testem, że laboratorium nie ma żadnej drogi do prywatnej bazy.

### Skąd wiadomo, że bramka działa

Co noc sprawdzamy ją na plikach z celowo wstawionymi wyciekami. Jeśli choć jeden przejdzie, publikacja staje. Wynik testu jest zapisywany.

### Po co publikować wyniki negatywne

Bo pokazują, że nie wybieramy tylko tego, co wyszło dobrze, i oszczędzają czas komuś, kto chciałby sprawdzić to samo. Wynik negatywny jest wynikiem.

### Kto decyduje, czy hipoteza się potwierdziła

Próg zapisujemy w karcie przed pomiarem, więc liczba rozstrzyga, nie nastrój. Bramkę zatwierdza człowiek, a próbki w pilocie oceniają ludzie na ślepo.

### Czy te dokumenty pisze AI

Pierwsze wersje pisze model AI. Każdy plik ma w nagłówku zapisane, kto go napisał i czy człowiek go przejrzał. Przegląd przez właściciela projektu jest jeszcze przed nami.

### Kiedy repozytorium będzie publiczne

Po siedmiu nocach testu bramki z rzędu i po przeglądzie właściciela. Daty jeszcze nie ma.

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
