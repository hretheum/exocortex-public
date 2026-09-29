---
id: progress
lang: pl
counterpart: ../en/03-progress.md
provenance: ai_authored
provenance_metadata:
  agent: Claude Opus 5.5 (Cowork)
  date: 2026-09-28
  human_validated: false
---

# Stan prac

Dziennik tego, co zrobiono w ramach [roadmapy](02-roadmap.md), od najnowszych wpisów. Na górze jest sekcja „Co dalej”, pod nią dni i wpisy w kolejności od najnowszego. Stan pojedynczych zadań jest w nagłówkach ich plików. Tu zapisujemy, co się zmieniło, co zostało i co wyszło po drodze.

## Co dalej

Kroki właściciela, w tej kolejności: przegląd zatrzymań znaczeniowych (strona przeglądu w folderze roboczym), zatwierdzenie karty testowej `toy-length` i karty hipotezy pierwszego eksperymentu ([F3.4](roadmap/F3/F3.4-hypothesis-card.md)), a potem przejrzenie kodu i dokumentów oraz oznaczenie przejrzanych plików polem `human_validated`.

Prace: po zamrożeniu karty szybki test na próbie strojenia i strona oceny na ślepo (F3.6). Niezależnie od pierwszego eksperymentu radar okazji działa co tydzień (F5.1 do F5.3).

Przełączenie repozytorium na publiczne: po siedmiu nocach autotestu z rzędu (licząc od 29 września) i po przeglądzie właściciela, według warunków z roadmapy.

Wdrożenie strony lab.exocortex.zone (F6.4): repozytorium `lab-site-repo` jest utworzone. Zostaje wypchnięcie do niego plików z `lab-site/lab-site-repo/` (workflow jako `.github/workflows/pages.yml`), włączenie GitHub Pages ze źródłem „GitHub Actions” i domeną własną oraz rekord DNS `CNAME` dla `lab`. Strona zbuduje się po upublicznieniu repozytorium głównego, a do tego czasu workflow tylko sprawdza jego widoczność.

## 2026-09-29

### Laboratorium: model, kolejka, karty i strony (F2.4 do F2.8)

Laboratorium ma dwie wąskie drogi na zewnątrz, obie poza swoją wewnętrzną siecią i dostępne dla jego procesów tylko przez gniazda w osobnych wolumenach. Pierwsza prowadzi do lokalnego serwera modeli: przepuszcza trzy wywołania i tylko modele z listy z licencjami. Druga służy do pobierania: przyjmuje tylko adresy https z listy dozwolonych źródeł i trzyma przerwy między zapytaniami, których wymagają ich warunki. Test izolacji sprawdza obie co noc, obok tego, że z sieci laboratorium nie da się połączyć ani z prywatną bazą, ani z internetem. Pierwsza noc przeszła: autotest bramki wyłapał 73 z 73 przypadków, a test izolacji i test end-to-end się powiodły.

W bazie laboratorium są tabele eksperymentów z kolejką, próbami i blokadą zbioru kontrolnego, którą pilnuje sama baza. Eksperyment zabawkowy przeszedł przez całą ścieżkę na serwerze: zadania dwóch konfiguracji wykonały się w dwóch blokach, a drugi odczyt zbioru kontrolnego skończył się odmową. Procesory kart hipotez i decyzji z bramek działają co 15 minut. Zatwierdzona karta dostaje wpis w rejestrze prerejestracji, a publikator przyjmuje ten rejestr tylko wtedy, gdy przybywa w nim wierszy. Laboratorium eksportuje surowe wyniki do plików CSV z opisem kolumn i składa strony wynikowe: stan roadmapy, listę eksperymentów i dossier. Skrypt w repozytorium przelicza liczby ze stron z samych plików CSV.

### Pierwszy eksperyment gotowy do zamrożenia (F3.2 do F3.5)

Korpus jest w grafie laboratorium: abstrakt i polskie streszczenie każdego z 2478 artykułów, z sumami kontrolnymi zgodnymi z manifestem i z embeddingami. Ekstraktor twierdzeń jest napisany od nowa i przeszedł test na pięciu artykułach w obu wariantach. [Karta hipotezy](experiments/intent-vs-fact/hypothesis.md) ma wylosowane próby, progi i kryteria bramek i czeka na zatwierdzenie; laboratorium nie uruchomi eksperymentu przed jej zamrożeniem. Narzędzie do ślepej próby przeszło test na eksperymencie zabawkowym, a jego przedziały ufności zgadzają się z obliczeniami w innych narzędziach.

### Radar okazji (F5.1 do F5.3)

Laboratorium pobiera cztery kanały sygnałów: nowe prace z arXiv w czterech kategoriach, modele o otwartych wagach, nowe zbiory danych publicznych i wydania narzędzi, z których korzysta. Z nich co tydzień powstaje strona radaru z hipotezami i planami z nowych prac, możliwymi sprzecznościami, gęstymi tematami i nagłymi wzrostami. W pierwszym pełnym tygodniu radar przejrzał 198 prac. Pierwszą ocenę dziesięciu kandydatów wystawiły osobno modele trzech rodzin według szablonu wyboru; decyzja należy do człowieka. Radar pomija artykuły z korpusów eksperymentów i pozycje, które bramka uznałaby za dane osobowe.

### Bramka

Bramka zatrzymała jako podobne do materiałów chronionych obie karty hipotez, pliki danych laboratorium, część stron generowanych (dossier, radar i ocenę za jeden tydzień) oraz dokumenty z równoległej pracy nad stroną laboratorium. Progu nie zmienialiśmy; strona przeglądu czeka na właściciela. Jedno zatrzymanie było słuszne w inny sposób: dane eksperymentu zabawkowego zawierały zdania wycięte z dokumentów i sklejone przez granice linii, co dało trafienie na liście nazw, którego same dokumenty nie dają. Dane zabawkowe zawierają teraz tylko długości.

## 2026-09-28

### Strona laboratorium i dossier hipotez (F6.4, generator gotowy)

Powstał generator statycznej strony lab.exocortex.zone (katalog `lab-site/`): wersje `/en` i `/pl`, opis działania, lista hipotez ze statusami, osobne dossier każdej hipotezy i stan roadmapy z nagłówków plików zadań. Dossier ma budowę krótkiego artykułu: streszczenie, pytanie, prerejestracja, dane z sumami kontrolnymi i plikami do pobrania, metoda, przebiegi, wyniki, decyzje z bramek, odstępstwa, powtórzenie, ograniczenia i źródła. Cztery hipotezy mają dossier w `experiments/<slug>/overview.md`: „Zamiar czy fakt” (w przygotowaniu) i trzy planowane (F5.5 do F5.7). Wdrożenie jeszcze nie ruszyło: exocortex.zone to Astro na GitHub Pages i zajmuje jedyną stronę Pages repozytorium głównego, więc lab.exocortex.zone potrzebuje osobnego małego repozytorium, rekordu DNS i upublicznienia repozytorium głównego. Z dokumentów usunięto też szczegóły infrastruktury, na której działa laboratorium.

### Dokument i infografiki „jak to działa” (Exocortex R&D)

Powstał dokument [Jak działa Exocortex R&D](04-how-it-works.md) po polsku i angielsku oraz osiem infografik w katalogach `img/`: przegląd, bramka publikacji, droga hipotezy, ostatnie hipotezy ze statusami, architektura, izolacja laboratorium, ślad dowodowy i stan prac. Tekst jest pisany dla osoby spoza branży, promuje laboratorium i wspomina o prywatnym Exocortexie tylko jako o projekcie, z którego laboratorium wyrosło. Ta sama treść jest na roboczej stronie projektu, która stanie się podstawą podstrony na exocortex.zone (F6.4).

### Korpus pierwszego eksperymentu (F3.1, F3.2)

arXiv jest na liście dozwolonych źródeł laboratorium. Korpus eksperymentu „zamiar czy fakt” ma 2478 artykułów: abstrakt pobrany na nowo z arXiv i polskie streszczenie zrobione przez silnik. Pięć artykułów odpadło, bo bramka publikacji znalazła w nich nazwę ze swojej prywatnej listy; ich identyfikatory zostają prywatne. Budowa korpusu na dwóch maszynach dała identyczne sumy kontrolne. Korpus jest w repozytorium i w laboratorium. Kolejność w tym pliku jest teraz taka: na górze „Co dalej”, pod nią wpisy od najnowszego.

### Zamknięte F0.6, laboratorium rusza (F2.1, F2.2)

Właściciel zaakceptował zmierzone wartości porównania z korpusem prywatnym w miejsce pierwotnego warunku, więc F0.6 jest zamknięte. Laboratorium działa na serwerze w sieci, z której nie da się dostać do prywatnej instancji, co co noc sprawdza osobny test. Do laboratorium trafia tylko to, co jest na publicznej liście dozwolonych źródeł; na razie to nasze własne dokumenty. Przy okazji CI testuje teraz router modeli z repozytorium zamiast starszego wydania z PyPI i nie przebudowuje obrazów przy każdej publikacji dokumentów.

### Przegląd i próg z kalibracji (F0.6)

Właściciel przejrzał listę 112 akapitów bliskich materiałom chronionym. Dwanaście przepisaliśmy, bo zdradzały szczegóły operacyjne, a resztę zatwierdził jako wspólny temat. Bramka ma teraz stronę przeglądu z linkami i cytatami oraz zatwierdzanie przejrzanych akapitów, więc zatrzymany plik da się zwolnić bez obniżania progu. Działa próg z kalibracji, 0,8584. Powiadomienie o zatrzymaniu podpowiada, jak uruchomić przegląd.

### Zawężony korpus chroniony (F0.6)

Po decyzji właściciela korpus chroniony obejmuje tylko materiały klienckie i prywatne. Porównanie znaczeniowe działa teraz dobrze: przy 5% fałszywych alarmów przepuszcza około 5% parafraz, wcześniej 15 do 17%. Przy okazji wyszło, że 36 ze 100 opublikowanych plików ma akapity bliskie materiałom chronionym, głównie klienckim i prywatnym materiałom produktowym. Repozytorium jest prywatne, więc nic nie wyszło na zewnątrz. Te pliki są na prywatnej liście i właściciel przegląda je w pierwszej kolejności przed przełączeniem. Do czasu przeglądu działa próg 0,93.

### Sprawdzenie dwustopniowe (F0.6)

Lokalny model oceniający kandydatów nie poprawił wyniku: przepuszcza 17% parafraz i zatrzymuje co trzeci opublikowany plik. Przyczyna nie leży w metodzie, tylko w zakresie korpusu prywatnego. Nasze dokumenty są najbliżej notatek o samym Exocorteksie, a streszczenia artykułów najbliżej streszczeń newsletterów. W obu przypadkach to ta sama treść, ale nie materiał kliencki. Porównanie odróżni wyciek od zbieżności tematu dopiero wtedy, gdy korpus chroniony będzie obejmował to, czego naprawdę nie wolno opublikować. Na razie działa zwykły próg 0,93.

### Miary względne i zmiana korpusu F3

Sprawdziliśmy dwie miary względne, które miały lepiej odróżniać parafrazę od tekstu na ten sam temat. Obie wypadły gorzej od zwykłego podobieństwa: przepuszczają ponad dwa razy więcej parafraz i zatrzymują więcej naszych dokumentów. Hipotezę odrzuciliśmy, liczby są w pliku zadania F0.6. Kalibracja porównuje teraz wszystkie trzy miary przy każdym uruchomieniu i sprawdza wynik na odłożonej połówce danych.

Korpus F3 zmienił się z polskich dokumentów urzędowych na abstrakty artykułów z arXiv, które Exocortex już pobrał, razem z polskimi streszczeniami zrobionymi przez silnik. Nie trzeba czekać na zbieranie dokumentów, a eksperyment dostaje drugie pytanie: czy nasze streszczenia zamieniają hipotezy w fakty.

### Kalibracja porównania z korpusem prywatnym (F0.6)

Poprzednia kalibracja dała złe progi, bo część tekstów publicznych, na których sprawdzaliśmy fałszywe alarmy, była kopią notatek z korpusu prywatnego. Chodziło o dokumentację silnika, napisaną na podstawie notatek z vaulta. Same opublikowane dokumenty nie pasowały do niczego. Teraz negatywami są opublikowane dokumenty i streszczenia 2486 artykułów z arXiv. Streszczenia są publiczne, więc wyłączyliśmy je z korpusu prywatnego, a indeks przebudowaliśmy (65 415 akapitów).

Wynik: warstwa dosłowna działa bez zarzutu, a znaczeniowa słabo. Przy 5% fałszywych alarmów przepuszcza 12% akapitów przepisanych przez model, a przy jej skalibrowanym progu co piąty opublikowany plik zostałby zatrzymany. Nie ma jeszcze sposobu, żeby człowiek zwolnił zatrzymany plik. Dlatego do czasu decyzji działa próg 0,93, który nie zatrzymuje żadnego z obecnych dokumentów. Warunek ukończenia F0.6 w obecnym brzmieniu jest przy tej metodzie nieosiągalny. F0.6 zostaje w toku.

Przy okazji wyszedł błąd we wdrożeniu: nocna aktualizacja obrazu restartowała usługę porównania, a gdy w tym samym momencie kończyło się inne zadanie, zatrzymywał się cały pod i usługa nie wstawała. Pod ma teraz politykę „nie zatrzymuj”, a usługa kończy się poprawnie na sygnał. Wszystkie zadania bramki da się też uruchomić na żądanie, bez czekania na noc, a każdy workflow w GitHubie ma przycisk ręcznego uruchomienia.

### Serwer, CI i test end-to-end

Kroki z listy wykonano razem z właścicielem. Klucz bramki jest w sekretach GitHuba, a repozytorium jest wypchnięte. Na serwerze jako Quadlet działają publikator (co 15 minut), nocna przebudowa indeksu i nocny autotest. Autotest na serwerze wyłapał 73 z 73 przypadków. Próba z plikiem zawierającym dane osobowe skończyła się wstrzymaniem, próba blokady zatrzymała publikator, a powiadomienie dotarło przez Telegram.

CI na GitHubie przechodzi w całości, poza lintem, który tylko informuje. Walidacja schematu bazy działa na prawdziwym obrazie bazy. Obrazy silnika, bazy i bramki trafiają do GHCR dopiero po skanie.

Test end-to-end (wczytanie notatek, synteza, kompilacja wiki, pytanie GraphRAG z cytatami) wcześniej nigdy nie przeszedł. Wymagał płatnego klucza API i miał kilka błędów w samym teście. Teraz działa w dwóch miejscach. W CI zamiast modelu odpowiada atrapa serwera, więc test nie potrzebuje klucza i sprawdza przepływ danych. Na serwerze ten sam test biegnie co noc o 01:15 z prawdziwym lokalnym modelem, na jednorazowej bazie trzymanej w pamięci. Pierwszy przebieg na serwerze znalazł błąd: lokalny model czasem odpowiada zwykłym tekstem zamiast wywołaniem narzędzia i pytanie GraphRAG kończyło się wyjątkiem. Router modeli przyjmuje teraz taką odpowiedź, jeśli narzędzie ma jedno wymagane pole tekstowe. Drugi przebieg przeszedł w 25 sekund.

Przy okazji wyszło, że świeża baza nie ma grafu AGE, bo nie tworzy go żadna migracja. Obraz bazy tworzy go teraz przy pierwszym uruchomieniu. Test stosu `docker compose` uruchamia się już tylko ręcznie, bo produkcja działa na Quadletach.

Znany dług: przykładowa wtyczka ACME ma perspektywę syntezy, której program nie wywołuje, a jej zapytanie czyta nieistniejącą kolumnę. Test korzysta teraz ze zwykłej perspektywy tagu. Ekstrakcja tagów przez model jest pomijana, bo moduł `scripts.extract_tags_batch` nie trafił do eksportu. Trzy testy jednostkowe są wyłączone w CI.

### Noc z 27 na 28 września: F0, F1 i pierwsze zadanie F2

Prace nad F0 i F1 wykonywał w nocy agent, bez udziału właściciela. Wszystko, co zrobił, czeka na przejrzenie. Pola `human_validated` pozostają ustawione na `false`.

#### F0. Bramka

Skaner `leakgate` sprawdza tekst, pliki z metadanymi (zdjęcia, PDF, dokumenty biurowe), archiwa, paczki Pythona, obrazy kontenerów i metadane commitów. Lista zakazanych nazw ma 11 613 skrótów HMAC. W obrazach kontenerów skaner sprawdza konfigurację oraz pliki, które trafiają tam z repozytorium. Pliki wykonywalne i skompilowany kod Pythona w obrazie są dozwolone, ale ich napisy też są sprawdzane. Autotest podrzuca 73 przypadki i wszystkie są wyłapywane.

Porównanie z korpusem prywatnym (`simcheck`) ma skalibrowany próg dosłownego podobieństwa (0,40). Część semantyczna wymaga modelu embeddingów na serwerze i jeszcze nie jest skalibrowana. Dlatego F0.6 ma status `doing`.

Autotest nocny jest gotowy, ale noce jeszcze się nie liczą: zaczną się po pierwszym uruchomieniu na serwerze i w CI. Stare wydanie paczki na PyPI czeka na usunięcie przez właściciela.

#### F1. Repozytorium

Powstało prywatne repozytorium robocze. Kod silnika przeszedł przez eksport z listą dozwolonych ścieżek, a przykładowa konfiguracja została napisana od nowa na fikcyjnych danych. Narzędzie `code_en` znalazło 604 fragmenty z polskim tekstem w komentarzach, docstringach i komunikatach. Zmieniono 341 z nich. Pozostałe były po angielsku i zostały oznaczone przez zbyt czuły detektor, który potem poprawiono. Po drodze usunięto odwołania do prywatnych notatek z zadaniami.

Znany dług: część napisów widocznych dla użytkownika (nagłówki w wiki, odpowiedzi bota) jest nadal po polsku, bo to zachowanie programu, a nie komentarz. Przejście na angielski wymaga obsługi języków w silniku i będzie osobnym zadaniem. Drugi dług to lint: `ruff` zgłasza kilkaset uwag, więc w CI to zadanie informuje, ale nie blokuje.

Obraz i paczka są budowane z listy jawnie wskazanych ścieżek. Paczka 0.2.0 przechodzi bramkę lokalnie. CI na GitHubie uruchomi się po pierwszym wypchnięciu repozytorium i po dodaniu klucza bramki jako sekretu.

Dokumenty mają narzędzia `paritycheck` (zgodność wersji PL i EN) i `humanlint` (nawyki modeli językowych) oraz słownik terminów. Progi `humanlint` ustawiono na podstawie tekstów pisanych przez ludzi. Publikator i reszta bramki działają jako rootless pod Podmana uruchamiany przez Quadlet, z własnego obrazu kontenera, i są przetestowane na lokalnym repozytorium. Na serwer nie trafia kod źródłowy: publikator trzyma tylko częściowy klon z folderem dokumentów, a pliki Quadlet pochodzą z obrazu. Zadania silnika też przepisano na Quadlet. Jeden krok uruchamiał skrypt z dysku serwera (korekta językowa stron wiki) i został usunięty, dopóki nie dostanie własnego obrazu. Pierwsza publikacja przeniosła dokumenty do repozytorium roboczego. Wypchnięcie na GitHuba i uruchomienie na serwerze należą do właściciela.

#### F2. Pierwsze zadanie

Zadanie F2.3 nie wymaga serwera, więc zostało zrobione od razu po F1. Nagłówki kart hipotez, notatek z przebiegów, decyzji z bramek i plików zadań mają schematy JSON. Skrypt `docschema` sprawdza je w CI i w publikatorze, a błąd wskazuje plik, pole i powód. Doszedł szablon notatki z przebiegu, a README opisuje układ katalogów eksperymentów.
