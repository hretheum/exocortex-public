---
type: hypothesis_card
lang: pl
counterpart: ../../../en/experiments/intent-vs-fact/hypothesis.md
slug: intent-vs-fact
version: 1
supersedes: null
tier_target: M
data_class: public
sources: ["../../roadmap/F3-first-pass.md", "corpus.md"]
prereg_hash: null
human_validated: true
---

# Hipoteza: obowiązkowe pole trybu zmniejsza odsetek twierdzeń, które przedstawiają zamiar jako fakt

Karta pierwszego eksperymentu laboratorium, zadanie [F3.4](../../roadmap/F3/F3.4-hypothesis-card.md). Korpus opisuje dokument [Korpus eksperymentu](corpus.md). Dopóki właściciel nie zatwierdzi tej karty, jest ona projektem: nie jest zamrożona i nic nie zostało na jej podstawie zmierzone.

## Problem

Ekstraktor twierdzeń zamienia tekst na krótkie zdania z dosłownym cytatem. Z takich twierdzeń składamy potem streszczenia, strony wynikowe i karty projektów. Jeśli twierdzenie zgubi tryb zdania źródłowego, plan albo przypuszczenie autorów idzie dalej jako fakt. W abstraktach artykułów naukowych oba rodzaje zdań stoją obok siebie: to, co zmierzono, i to, co autorzy proponują, czego się spodziewają albo co planują.

Streszczenia prac naukowych robione przez modele językowe częściej niż ludzkie uogólniają wnioski ponad to, co mówi źródło ([Peters i Chin-Yee, 2025](https://doi.org/10.1098/rsos.241776)). Nie wiemy, jak często taki błąd popełnia nasz ekstraktor ani czy pomaga prosta zmiana schematu odpowiedzi.

## Hipoteza

- H1: dodanie do schematu ekstrakcji obowiązkowego pola trybu (fakt, plan, wymóg, hipoteza) zmniejsza odsetek twierdzeń z zamianą trybu w porównaniu z tym samym ekstraktorem bez tego pola, na tych samych abstraktach i tym samym modelu. H1 obala różnica mniejsza niż 5 punktów procentowych albo przedział ufności różnicy, który obejmuje zero.
- H0: różnica jest mniejsza niż próg albo jej przedział ufności obejmuje zero.

Twierdzenie z zamianą trybu przedstawia jako fakt dokonany coś, co źródło przedstawia jako plan, wymóg albo hipotezę. W wariancie z polem trybu twierdzenie liczy się jako zamiana tylko wtedy, gdy oceniający uznał jego treść za zamianę, a pole trybu ma wartość „fakt”. Twierdzenie oznaczone jako hipoteza nie podaje treści jako faktu, nawet jeśli samo zdanie jest w trybie oznajmującym.

## Metryki

| Rola | Metryka | Definicja | Próg | Linia bazowa | Jak liczona |
|---|---|---|---|---|---|
| rozstrzygająca | swap_rate | odsetek użytecznych twierdzeń z zamianą trybu | spadek o co najmniej 5 punktów procentowych | wariant bez pola trybu | ocena na ślepo; różnica z bootstrapem po dokumentach |
| pomocnicza | label_accuracy | odsetek twierdzeń wariantu z polem trybu, w których pole zgadza się z trybem źródła według oceniającego | bez progu | nie dotyczy | Wilson |
| pomocnicza | other_errors | odsetek twierdzeń z przekręconą liczbą lub nazwą albo z innym błędem | bez progu | wariant bez pola trybu | Wilson |
| ochronna | failed_share | odsetek dokumentów, dla których model nie zwrócił poprawnej odpowiedzi | nie więcej niż 5% | nie dotyczy | Wilson |
| ochronna | usable_per_document | średnia liczba użytecznych twierdzeń na dokument | nie mniej niż 70% linii bazowej | wariant bez pola trybu | bootstrap po dokumentach |

Użyteczne twierdzenie ma cytat obecny dosłownie w dokumencie, osobny przebieg modelu uznał je za twierdzenie i nie jest powtórzeniem wcześniejszego. Przedziały ufności: metoda Wilsona dla proporcji, bootstrap po dokumentach dla różnic i średnich (10 000 powtórzeń, ziarno 20260929, percentyle 2,5 i 97,5). Oba warianty działają na tych samych dokumentach, więc bootstrap losuje dokumenty raz dla obu.

## Próby

| Próba | Liczność | Sposób losowania | Ziarno | Suma kontrolna |
|---|---|---|---|---|
| strojenie | 20 artykułów | warstwowo według oceny trafności: 5 niska, 8 średnia, 7 wysoka | 20260929 | 7c6a59ac1189ccf535cac28955395dd0341239314b3af1dd257a91f261ddf700 |
| kontrolna (otwierana raz) | 10 artykułów | warstwowo: 2 niska, 4 średnia, 4 wysoka | 20260929 | 0ab29cd2f6f933a037bd79ca028185caacf6fcc8b64e4a42ff17569b8f3290d7 |
| pilot (skala M) | 60 artykułów | warstwowo: 15 niska, 24 średnia, 21 wysoka | 20260929 | 8252184cc8f08dbefbcfb9e0defd94399d0eb1d0d4cc53bcafed2d40d1b183f8 |
| ślepa (skala M) | 120 twierdzeń | z wyników pilota, warstwowo według konfiguracji | 20260930 | powstanie po przebiegu pilota |

Rama losowania to 2473 artykuły: korpus bez pięciu artykułów, na których sprawdzano ekstraktor (F3.3). Trzy próby są rozłączne. Listy artykułów leżą w repozytorium w `lab/corpora/intent-vs-fact/samples/`, a sumy kontrolne policzono ze wspólnej sumy abstraktu i streszczenia każdego artykułu z pliku `manifest.csv`.

Na bramce G1 oceniamy na ślepo wszystkie twierdzenia obu wariantów z próby strojenia, a potem ze zbioru kontrolnego. Dziesięć losowo wybranych twierdzeń pojawia się na stronie oceny drugi raz, żeby sprawdzić zgodność oceniającego z samym sobą.

## Konfiguracje

| Nazwa | Model | Wariant | Parametry |
|---|---|---|---|
| qwen36-baseline (linia bazowa) | qwen3.6-35b-a3b | bez pola trybu | abstrakt, temperatura 0, ziarno 0, odpowiedź przez gramatykę JSON |
| qwen36-mode | qwen3.6-35b-a3b | z polem trybu | jak w linii bazowej |
| gemma4-baseline (skala M) | gemma-4-26b-a4b | bez pola trybu | jak w linii bazowej |
| gemma4-mode (skala M) | gemma-4-26b-a4b | z polem trybu | jak w linii bazowej |
| qwen36-summary-mode (skala M, poznawczo) | qwen3.6-35b-a3b | z polem trybu | polskie streszczenie silnika zamiast abstraktu |

Ekstraktor to moduł `exocortex/lab/extractor.py`, a konfiguracje są zapisane w `lab/experiments/intent-vs-fact.yaml`. Oba warianty proszą najpierw o cytat, potem o twierdzenie. Wariant z polem trybu różni się od linii bazowej tylko jedną regułą w instrukcji i jednym polem w schemacie odpowiedzi. Oceny, czy zdanie jest twierdzeniem, dokonuje ten sam model w osobnym wywołaniu, a powtórzenia usuwamy, gdy podobieństwo embeddingów bge-m3 wynosi co najmniej 0,92. Słownik skrótów zbudowano z korpusu (70 pozycji). Każdy przebieg zapisuje commit kodu. Zmiana instrukcji, schematu albo progów po zamrożeniu karty wymaga nowej wersji karty.

## Założenie, od którego wszystko zależy

Oceniający potrafi na podstawie cytatu i fragmentu tekstu wokół niego rozpoznać, czy źródło przedstawia zdanie jako fakt, czy jako plan, wymóg albo hipotezę. Mierzymy to zamiast zakładać: z powtórzonych pozycji na stronie oceny liczymy zgodność oceniającego z samym sobą. Na stronie oceny nie ma nazwy konfiguracji ani wartości pola trybu, więc oceniający ocenia samą treść twierdzenia.

## Kryteria bramek

- G1 (S do M). Dane: próba strojenia i zbiór kontrolny razem, jeśli po ocenie próby strojenia ekstraktor się nie zmienił. Jeśli się zmienił, liczy się tylko zbiór kontrolny. GO, gdy spełnione są trzy warunki: linia bazowa ma swap_rate co najmniej 5% (problem w ogóle występuje), różnica swap_rate wynosi co najmniej 5 punktów procentowych na korzyść wariantu z polem trybu, a górna granica jej przedziału ufności jest poniżej zera, obie metryki ochronne są spełnione w obu wariantach. Jeśli linia bazowa ma swap_rate poniżej 5%, decyzja brzmi CLOSED: przy tym modelu problemu nie widać. Jeśli różnica ma właściwy kierunek, ale przedział ufności obejmuje zero, decyzja brzmi NOT-NOW z warunkiem powrotu: większa próba. W pozostałych przypadkach NO-GO.
- G2 (M do L). Dane: ślepa próba pilota, oba modele razem, około 60 twierdzeń na wariant. Warunki takie same jak na G1, a do tego opisany wynik kalibracji sędziego automatycznego (F3.9). Przy odsetku bliskim 10% i 60 twierdzeniach na wariant połowa szerokości przedziału ufności różnicy wynosi około 11 punktów procentowych, więc pilot potwierdzi tylko duży efekt.

## Warunek przerwania

- Jeśli w którymkolwiek wariancie model nie zwraca poprawnej odpowiedzi dla więcej niż 20% dokumentów próby strojenia, kończymy szybki test, poprawiamy ekstraktor i piszemy nową wersję karty.
- Jeśli zgodność oceniającego z samym sobą wynosi mniej niż 80%, wynik G1 opisujemy jako niepewny i decyzja nie może brzmieć GO.

## Czego ta metoda nie wykryje

- Kompletności: czy wyciągnięto najważniejsze twierdzenia.
- Błędów interpretacji przy poprawnym cytacie, jeśli oceniający ich nie zauważy.
- Słabości wspólnych dla ekstrakcji i oceny, czy zdanie jest twierdzeniem, bo obie robi ten sam model.
- Zamiany odwrotnej, gdy fakt zostaje podany jako hipoteza. Zliczamy ją jako inny błąd, ale o bramce nie rozstrzyga.
- Stałych nawyków jednego oceniającego. Zgodności między oceniającymi nie policzymy przed dołączeniem drugiego eksperta (F6.1).

## Prace pokrewne

- [Peters i Chin-Yee, 2025](https://doi.org/10.1098/rsos.241776): streszczenia prac naukowych robione przez dziesięć modeli językowych częściej niż ludzkie uogólniały wnioski ponad źródło. Mierzyli całe streszczenia; my mierzymy pojedyncze twierdzenia i jedną konkretną zmianę schematu.
- [Min i in., 2023](https://aclanthology.org/2023.emnlp-main.741/) (FActScore): tekst jest rozbijany na elementarne fakty, a każdy z nich jest sprawdzany ze źródłem wiedzy. Trybu zdań to podejście nie rozróżnia.
- [Farkas i in., 2010](https://aclanthology.org/W10-3001/) (CoNLL-2010): wykrywanie zdań niepewnych w tekstach naukowych. My nie wykrywamy niepewności w źródle, tylko sprawdzamy, czy wyciągnięte twierdzenie ją zachowuje.
