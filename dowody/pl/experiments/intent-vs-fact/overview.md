---
id: intent-vs-fact-overview
lang: pl
counterpart: ../../../en/experiments/intent-vs-fact/overview.md
status: preparation
roadmap: F3
stage: 1
tier: S
tagline: "Czy ekstrakcja twierdzeń odróżnia fakt od zamiaru."
updated: 2026-09-28
provenance: ai_authored
provenance_metadata:
  agent: Claude Sonnet 5.5 (Cowork)
  date: 2026-09-28
  human_validated: false
---

# Zamiar czy fakt

## Streszczenie

Modele językowe często opisują to, co dopiero zamierzono, jak rzecz już zrobioną. W abstraktach prac naukowych fakty (co zmierzono) sąsiadują z zapowiedziami i hipotezami (co proponujemy, co może zadziałać), więc dobrze nadają się do sprawdzenia, czy potrafimy te dwie rzeczy rozdzielić. Ten eksperyment ma dwa pytania: czy ekstrakcja twierdzeń z tekstu z obowiązkowym polem trybu rzadziej myli plan z faktem niż ekstrakcja bez niego, oraz czy nasze własne streszczenia nie zamieniają zamiaru w fakt.

Stan na 28 września 2026: korpus jest gotowy (2478 artykułów z arXiv), karta hipotezy jeszcze nie istnieje i niczego nie zmierzono. Ta strona opisuje przygotowanie, a nie wynik.

## Pytanie i hipoteza

Pytanie ogólne: czy da się wiarygodnie odróżnić w tekście zdania o tym, co jest faktem, od zdań o tym, co jest planem, wymogiem, celem albo hipotezą, i czy nasze streszczenia zachowują to rozróżnienie.

Robocza hipoteza z roadmapy (nie jest jeszcze zamrożona):

- H1: dodanie do schematu ekstrakcji obowiązkowego pola trybu (fakt, plan, wymóg, hipoteza) zmniejsza odsetek twierdzeń, które opisują plan, wymóg lub cel jako fakt dokonany.

- H0: różnica między wariantem z polem trybu i bez niego jest mniejsza niż próg zapisany w karcie albo przedział ufności obejmuje zero.

Ostateczne sformułowanie, w tym próg, powstanie w karcie hipotezy ([F3.4](../../roadmap/F3/F3.4-hypothesis-card.md)) i zostanie zamrożone przed pomiarem.

## Prerejestracja

Karta hipotezy jeszcze nie została napisana, więc nie ma sumy kontrolnej ani wpisu w rejestrze prerejestracji. Zasada jest taka: karta zostaje zamrożona i opublikowana, zanim ekstraktor zostanie uruchomiony na korpusie choćby raz poza pięcioma dokumentami testowymi. Wpis w rejestrze ma datę wcześniejszą niż pierwszy przebieg, a skrypt weryfikacyjny potwierdza sumę kontrolną.

Poniżej robocze założenia z roadmapy. Mogą się zmienić do chwili zamrożenia karty, a po niej zmienia je tylko nowa wersja karty.

| Rola | Metryka | Próg |
|---|---|---|
| rozstrzygająca | odsetek twierdzeń z zamianą trybu w ślepej próbie ocenianej przez człowieka | do ustalenia w karcie przed pomiarem |
| ochronna | odsetek fragmentów bez poprawnej odpowiedzi modelu | nie więcej niż 5% |
| ochronna | liczba użytecznych twierdzeń na dokument | nie mniej niż 70% linii bazowej |

Linia bazowa to ten sam ekstraktor bez pola trybu, z tym samym modelem i na tych samych dokumentach. Robocze wielkości prób: strojenie 20 dokumentów, zbiór kontrolny 10 dokumentów i ślepa próba do pilota 120 twierdzeń, wszystkie losowane z zapisanym ziarnem i warstwowo po długości dokumentu.

## Dane

Źródłem są abstrakty artykułów z arXiv, które nasz silnik pobrał i streścił w sierpniu i wrześniu 2026 roku, wraz z polskimi streszczeniami i ustaleniami wygenerowanymi przez silnik. Abstrakty pobraliśmy ponownie z API arXiv, żeby korpus nie zależał od tego, co zapisał silnik. Pełnych tekstów artykułów nie używamy.

Po wyłączeniach rama ma 2478 artykułów: 602 w warstwie niskiej (ocena trafności od 1 do 4), 1005 w średniej (od 5 do 7) i 871 w wysokiej (od 8 do 10). Odpadło osiem pozycji: jedno powtórzenie, dwa abstrakty krótsze niż 50 słów i pięć artykułów zatrzymanych przez bramkę publikacji, bo zawierają nazwę z jej prywatnej listy. Identyfikatory tych pięciu są prywatne, bo wskazywałyby te nazwy.

Podstawa korzystania: abstrakty to metadane arXiv na zasadach CC0 1.0, a streszczenia są wytworem naszego silnika, więc publikujemy je w całości. Pełny opis korpusu, podstawy prawnej i ramy losowania jest w dokumencie [Korpus eksperymentu](corpus.md). Pliki do pobrania są niżej.

## Metoda

Eksperyment przechodzi całą drogę cyklu, w dwóch skalach. Szybki test (skala S) porównuje oba warianty ekstraktora na próbie strojenia i, dopiero po jej ocenie, na zbiorze kontrolnym, który otwieramy raz. Pilot (skala M) rozszerza porównanie na macierz od 4 do 8 konfiguracji: dwa modele lokalne różnych rodzin, schemat z polem trybu i bez niego, przetwarzanie całych dokumentów i fragmentów.

Ocena jest ślepa: człowiek widzi twierdzenie, cytat i fragment dokumentu, ale nie wie, z której konfiguracji pochodzi twierdzenie, a kolejność jest losowa. Przedziały ufności liczymy metodą Wilsona dla proporcji i bootstrapem po dokumentach dla różnic między konfiguracjami. Na końcu pilota kalibrujemy sędziego automatycznego z innej rodziny modeli i sprawdzamy, ile błędów łapie i ile daje fałszywych alarmów.

Kolejność zadań: korpus ([F3.1](../../roadmap/F3/F3.1-public-corpus-selection.md), [F3.2](../../roadmap/F3/F3.2-corpus-manifest.md)), ekstraktor twierdzeń, karta hipotezy, narzędzie do ślepej próby, szybki test z bramką G1, pilot i bramka G2 z raportem.

## Przebiegi

Brak przebiegów. Pierwszy przebieg powstanie po zamrożeniu karty hipotezy. Każdy przebieg dostanie notatkę: model, wariant, parametry, commit kodu, wynik i wszystko, co poszło źle albo wyglądało dziwnie.

## Wyniki

Brak wyników. Wyniki publikujemy tego samego dnia, w którym powstają, także negatywne, razem z przedziałami ufności i odnośnikiem do surowych danych.

## Decyzje z bramek

Nie zapadła jeszcze żadna decyzja. Bramka G1 jest po szybkim teście, a G2 po pilocie. Każda decyzja jest publikowana razem z wynikami, na których się opiera.

## Odstępstwa i historia zmian

| Data | Wersja | Zmiana |
|---|---|---|
| 2026-09-28 | 0.1 | Utworzono dossier. Zamiast polskich dokumentów urzędowych, planowanych początkowo, korpusem są abstrakty z arXiv wraz ze streszczeniami silnika (zmiana planu przed zamrożeniem karty). Zbudowano korpus (F3.1, F3.2). |

## Jak powtórzyć

Dziś można powtórzyć budowę korpusu. Pliki z korpusem i sumami kontrolnymi są do pobrania w sekcji o danych, a listę identyfikatorów zawiera plik manifestu.

1. Pobierz `manifest.csv` i `corpus.jsonl` i porównaj ich sumy SHA-256 z podanymi na tej stronie.

2. Dla dowolnego identyfikatora z manifestu pobierz abstrakt z API arXiv (najwyżej jedno zapytanie co trzy sekundy), znormalizuj białe znaki i policz SHA-256. Wynik powinien zgadzać się z kolumną `abstract_sha256`, chyba że arXiv opublikował od tego czasu nowszą wersję artykułu.

3. Streszczenia są dostępne tylko w pliku korpusu, bo powstały wcześniej w silniku Exocortex. Ich sumy sprawdzisz w kolumnie `summary_sha256`.

Skrypt budujący korpus to `lab/corpus/intent_vs_fact.py` w repozytorium. Powtórzenie pomiarów będzie możliwe po zamrożeniu karty i pierwszych przebiegach.

## Ograniczenia

Ocena trafności odzwierciedla zainteresowania właściciela laboratorium, a nie jakość artykułu. Warstwy mają tylko zapewnić, że w każdej próbie są artykuły z różnych części skali.

Rama to artykuły, które silnik pobrał w ciągu dwóch miesięcy, a nie losowa próba całego arXiv, więc wyniki nie mówią o arXiv jako całości.

Abstrakty są po angielsku, a streszczenia po polsku, więc porównanie zamiaru i faktu idzie między językami. Silnik nie zapisał, który model napisał poszczególne streszczenia.

Do czasu dołączenia drugiego eksperta (F6.1) oceny ślepej próby wystawia jedna osoba, więc nie da się jeszcze policzyć zgodności oceniających.

Metoda nie wykryje kompletności (czy wyciągnięto najważniejsze twierdzenia), błędów interpretacji przy poprawnym cytacie ani słabości wspólnych dla modelu ekstrahującego i oceniającego.

## Źródła

- [Warunki korzystania z API arXiv](https://info.arxiv.org/help/api/tou.html)

- [Licencje arXiv](https://info.arxiv.org/help/license/index.html)

- [Common Pile, arxiv_abstracts](https://huggingface.co/datasets/common-pile/arxiv_abstracts)
