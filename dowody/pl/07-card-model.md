---
id: card-model
lang: pl
counterpart: ../en/07-card-model.md
provenance: ai_authored
provenance_metadata:
  agent: Claude Code (cloud session)
  date: 2026-10-01
  human_validated: false
---

# Ogólny model karty referencyjnej

Karta referencyjna opisuje zrealizowany projekt na potrzeby oferty albo przetargu. Ten dokument opisuje taką kartę raz, niezależnie od konkretnego formularza: jakie ma sekcje, na co odpowiada każda z nich i skąd w zapisach laboratorium bierze się ich treść. Ten sam opis istnieje jako plik z danymi, [lab/card-model.yaml](https://github.com/hretheum/exocortex-public/blob/main/lab/card-model.yaml), a program sprawdza z nim każdą kartę. To jest zadanie F4.1 fazy [F4](roadmap/F4-reference-card.md).

## Po co

Kartę pisaną ręcznie łatwo napompować. Plan trafia do niej w czasie teraźniejszym, liczba pochodzi z pamięci, a „działa” nie ma daty. Zamawiający nie może niczego z tego sprawdzić. Tutaj karta powstaje z zapisów laboratorium, a każde zdanie mówi, jakiego jest rodzaju i skąd pochodzi. Żeby to było możliwe, karta potrzebuje najpierw stałego kształtu, który nie zmienia się od przetargu do przetargu. Ten model jest takim kształtem. Korzysta z niego program, który składa karty (zadanie F4.2), i sprawdzenie, które zatrzymuje zdania brzmiące pewniej, niż pozwalają dowody (zadanie F4.3).

## Dziewięć sekcji

Karta ma te sekcje, zawsze w tej kolejności. Każda ma tytuł w obu językach.

| Sekcja | Na co odpowiada | Dozwolone tryby zdań | Skąd pochodzi treść |
|---|---|---|---|
| Cel i kontekst | Jaki problem rozwiązywano i w ramach jakiej większej pracy | fakt, wymóg | sekcja „Problem” karty hipotezy; zadanie z mapy drogowej, które karta wskazuje; tytuł eksperymentu |
| Hipoteza | Co dokładnie zapowiedziano z góry i w której wersji karty | hipoteza, fakt | H1 i H0 z karty hipotezy; stan i wersja karty; rejestr prerejestracji |
| Eksperymenty i iteracje | Co uruchomiono, na jakich próbach i ustawieniach, ile razy | fakt | tabela przebiegów, konfiguracji, prób i wyników dla poszczególnych dokumentów; notatki z przebiegów; wcześniejsze wersje karty |
| Metoda walidacji | Jak sprawdzano hipotezę | fakt, wymóg | sekcje karty o metrykach, próbach i kryteriach bramek; sposób losowania każdej próby; metoda statystyczna każdej liczby; ślepe oceny ludzi |
| Wyniki | Co pokazały pomiary | tylko fakt | wiersze tabeli wyników (każda liczba z przedziałem ufności i licznością próby); wyniki, na których opiera się decyzja z bramki |
| Dalszy etap | Co dalej i pod jakim warunkiem | plan, wymóg, fakt | ostatnia zatwierdzona decyzja z bramki; kryteria bramek i warunek przerwania z karty; otwarte zadania z mapy drogowej |
| Co nowego wnosi na tle prac pokrewnych | Na jakich znanych pracach to się opiera albo czym się od nich różni | fakt, hipoteza | sekcja „Prace pokrewne” karty hipotezy |
| Ryzyka i ograniczenia | Czego wynik nie pokazuje i co mogłoby go podważyć | fakt, hipoteza | sekcje karty o głównym założeniu, o tym, czego metoda nie wykryje, i o warunku przerwania; metryki ochronne; dokumenty bez wyniku; liczność prób |
| Sposób weryfikacji | Jak czytelnik powtórzy każdą liczbę bez dostępu do laboratorium | fakt | polecenie przeliczenia opublikowane razem z danymi; sprawdzenie prerejestracji; wersja kodu każdego przebiegu; paczka grafu |

Najsurowsza jest sekcja Wyniki: zdanie może tam być tylko faktem i musi wskazywać wiersz danych, nigdy fragment tekstu.

## Trzy pola przy każdym zdaniu

Każde zdanie karty niesie trzy informacje. To je czyta sprawdzenie uczciwości (F4.3).

1. **Tryb.** Jeden z czterech: fakt, plan, wymóg, hipoteza. To te same cztery tryby, których używa ekstraktor laboratorium w pierwszym eksperymencie (F3). Każda sekcja dopuszcza tylko niektóre z nich; plan w sekcji Wyniki zostanie odrzucony.
2. **Źródło.** Albo plik w publicznym repozytorium, opcjonalnie z nagłówkiem w tym pliku, albo jeden wiersz pliku z danymi (CSV albo JSON w wierszach), wskazany wartościami jego kolumn. Program sprawdza, czy plik istnieje, czy nagłówek w nim jest i czy wartości wskazują dokładnie jeden wiersz. Zdanie bez źródła zostanie odrzucone.
3. **Data przy zdaniach o stanie bieżącym.** Każde zdanie mówi, czy opisuje stan bieżący („jest szkicem”, „nie ma jeszcze decyzji”). Jeśli tak, musi mieć datę, w której było prawdziwe. Pozostałe zdania nie mają daty.

## Skąd pochodzi treść

Model wymienia tylko to, co laboratorium już zapisuje. Nic nie zostało dodane na potrzeby karty. Laboratorium prowadzi trzy rodzaje zapisów.

- **Węzły grafu.** Opublikowane dokumenty laboratorium, wersje kart hipotez, zastosowane decyzje z bramek, prace z korpusu (ich streszczenia z arXiv i streszczenia silnika) oraz sygnały z radaru. Prace z korpusu mogą mieć też osadzenia (ang. embeddings), ale karta z nich nie korzysta.
- **Powiązania między węzłami.** Laboratorium zapisuje cztery rodzaje: węzeł pochodzi ze źródła (acquired_from), karta albo streszczenie powstały z dokumentu (derived_from), nowsza wersja karty zastępuje starszą (supersedes), a decyzja z bramki rozstrzyga wersję karty (decides).
- **Tabele poza grafem.** Eksperymenty, konfiguracje, próby, przebiegi, wyniki dla poszczególnych dokumentów, liczby cytowane na stronach pod stałymi identyfikatorami wyników, ślepe oceny ludzi, wersje kart i decyzje z bramek. Są publikowane jako pliki CSV obok dokumentów, więc każdy może przeliczyć liczby.

Test sprawdza, czy każda nazwa w modelu naprawdę występuje w kodzie albo w migracjach bazy, które ją definiują, i czy każdy rodzaj powiązania jest dozwolony przez bazę. Tam, gdzie sekcja potrzebowałaby czegoś, czego laboratorium nie zapisuje, model niczego nie wymyśla: luka jest zapisana jako otwarta decyzja (niżej).

## Przykład: eksperyment zabawkowy

Plik [lab/cards/toy-length.en.yaml](https://github.com/hretheum/exocortex-public/blob/main/lab/cards/toy-length.en.yaml) to pełna karta eksperymentu zabawkowego toy-length. Ten eksperyment sprawdza maszynerię laboratorium, a nie prawdziwe pytanie: porównuje dwie stałe reguły wyboru zdania z dokumentu. Każda liczba w karcie pochodzi z opublikowanych danych eksperymentu, na przykład:

> On the control sample (run run-2026-09-29-2, 6 documents) the difference was 0.667, confidence interval 0.333 to 1.000.

To zdanie ma tryb „fakt”, nie dotyczy stanu bieżącego, a jego źródłem jest wiersz z tym identyfikatorem wyniku w pliku `dowody/data/toy-length/metrics.csv`. Zdanie o stanie bieżącym wygląda tak:

> No gate decision has been recorded for this experiment.

Jego źródłem jest sekcja „Gate decisions” w dossier eksperymentu, a jego data to 1 października 2026.

Wybraliśmy kartę zabawkową, bo to jedyny eksperyment zabawkowy z opublikowanymi wynikami. Drugi, toy-retrieval, nie ma jeszcze w repozytorium plików z wynikami. Przykładowa karta jest po angielsku; wersję polską złoży kompilator (F4.2).

## Jak sprawdzić kartę

```
python -m exocortex.lab.card_model lab/cards/toy-length.en.yaml
```

Program wypisuje „ok” albo po jednym wierszu na każdy problem, z dokładnym miejscem problemu, na przykład `sections[4].statements[0].source: required field is missing`. Liczba w nawiasie to pozycja na liście, liczona od zera. To samo sprawdzenie działa jako `exocortex lab card-check`.

## Otwarte decyzje

Te pytania czekają na decyzję właściciela. Każde wynika z luki między tym, czego potrzebuje sekcja, a tym, co laboratorium dziś zapisuje.

1. **Karta i jej zadanie z mapy drogowej.** Dziś łączy je tylko lista ścieżek w nagłówku karty. Rodzaj powiązania do tego celu istnieje w bazie, ale laboratorium go nie zapisuje.
2. **Eksperymenty i przebiegi w grafie.** Są wierszami tabel, a nie węzłami. Karta dociera do nich przez nazwę eksperymentu i wersję karty; żadne powiązanie nie łączy przebiegu z wersją karty.
3. **Notatki z przebiegów.** Są opublikowanymi dokumentami ze sprawdzanym nagłówkiem, ale nic nie wczytuje ich do grafu ani nie łączy z przebiegami.
4. **Z których przebiegów może pochodzić wynik.** Tabela wyników zawiera wszystkie przebiegi, także strojenie i przebiegi na zmienionej próbie. Model nie ogranicza jeszcze wyników do przebiegów, które wskazuje decyzja z bramki.
5. **Jak opisać status projektu.** Wersja karty ma stan (szkic, zamrożona, GO, NO-GO, PIVOT, NOT-NOW, CLOSED). Nie ma uzgodnionego opisu tych stanów dla zamawiającego.
6. **Prace pokrewne.** Dziś to tylko swobodny tekst w karcie. Laboratorium zna prace naukowe, ale nic nie łączy z nimi karty.
7. **Siła dowodu.** Laboratorium wylicza etykietę (brak, wstępny, potwierdzony, obalony, nierozstrzygnięty) według stałej reguły, ale jej nie zapisuje. Otwarte jest, czy karta wylicza ją od nowa, czy etykieta jest zapisywana razem z wersją karty.

## Czego ten model nie robi

Nie pisze kart; zrobi to kompilator (F4.2). Nie ocenia, czy zdanie brzmi pewniej niż jego źródło; to zadanie sprawdzenia uczciwości (F4.3). Nie zna żadnego formularza przetargowego; przenoszenie sekcji do formularza zamawiającego to zadanie F4.4.
