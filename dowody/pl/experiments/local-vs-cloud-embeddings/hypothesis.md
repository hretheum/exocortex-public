---
type: hypothesis_card
lang: pl
counterpart: ../../../en/experiments/local-vs-cloud-embeddings/hypothesis.md
slug: local-vs-cloud-embeddings
version: 1
supersedes: null
tier_target: M
data_class: public
sources: ["../../roadmap/F5-radar-and-experiments.md"]
prereg_hash: null
human_validated: false
---

# Hipoteza: lokalny model osadzeń (ang. embeddings) nie jest gorszy od chmurowego o więcej niż Δ w nDCG@10

Karta eksperymentu [F5.6](../../roadmap/F5-radar-and-experiments.md). Dopóki właściciel nie zatwierdzi tej karty, jest ona projektem: nie jest zamrożona i nic nie zostało na jej podstawie zmierzone. Wartość Δ i liczności prób powstaną po próbie strojenia, ale przed otwarciem próby głównej, i dopiero po ich wpisaniu karta może zostać zamrożona.

## Problem

Wyszukiwanie po znaczeniu wymaga modelu osadzeń (ang. embeddings), czyli modelu, który zamienia tekst na liczbowy opis sensu. Można go uruchomić na własnym sprzęcie albo wynająć jako usługę chmurową. Wybór ma znaczenie dla każdej firmy, która trzyma dokumenty niejawne albo nie chce wysyłać ich poza organizację. Nie wiemy, ile jakości wyszukiwania po polsku kosztuje przejście na model lokalny ani czy ta różnica ma praktyczne znaczenie.

Nie pytamy, który model jest lepszy w ogóle. Pytamy, czy lokalny model jest wystarczająco dobry, żeby decyzja o zostaniu na własnym sprzęcie miała uzasadnienie w jakości wyszukiwania. Sama ostrożność nie wystarcza.

## Hipoteza

- H1: lokalny model osadzeń nie jest gorszy od chmurowego o więcej niż Δ w nDCG@10, na tych samych zapytaniach i tym samym polskim korpusie publicznym. H1 potwierdza dolna granica 95% przedziału ufności różnicy (lokalny minus chmurowy) powyżej −Δ.
- H0: różnica jest gorsza niż −Δ albo jej przedział ufności obejmuje −Δ.

Test jest jednostronny: lokalny model, który wypadnie lepiej, potwierdza H1. Δ jest zapisane liczbą przed otwarciem próby głównej i wyprowadzone z kotwicy niezależnej od wyniku lokalnego modelu (patrz Metryki). Wykonalność na własnym sprzęcie jest osobnym warunkiem i nie wchodzi do H1.

## Metryki

| Rola | Metryka | Definicja | Próg | Linia bazowa | Jak liczona |
|---|---|---|---|---|---|
| rozstrzygająca | ndcg10_diff | różnica nDCG@10, lokalny minus chmurowy, liczona parami po zapytaniach | dolna granica 95% przedziału powyżej −Δ | model chmurowy | bootstrap po zapytaniach |
| pomocnicza | recall100_diff | różnica recall@100, lokalny minus chmurowy | bez progu | model chmurowy | bootstrap po zapytaniach |
| pomocnicza | cloud_drift | największa różnica nDCG@10 między trzema przebiegami modelu chmurowego w różnych dniach | Δ musi być większe | ten sam model chmurowy | bootstrap po zapytaniach |
| pomocnicza | bm25_gap | różnica nDCG@10, model chmurowy minus BM25 | wyprowadza Δ | BM25 | bootstrap po zapytaniach |
| ochronna (wykonalność) | query_p95 | 95. percentyl czasu jednego zapytania lokalnego modelu na K12 | nie więcej niż 500 ms | nie dotyczy | percentyl z trzech przebiegów |
| ochronna (wykonalność) | index_time | czas zaindeksowania całego korpusu na K12 | nie więcej niż 6 godzin | nie dotyczy | mediana z trzech przebiegów |

Δ to połowa wartości bm25_gap zmierzonej na próbie strojenia, pod warunkiem że jest większe niż cloud_drift. Jeśli bm25_gap jest mniejszy niż dwukrotność cloud_drift, zbiór testowy nie odróżnia dobrego modelu od prostego punktu odniesienia i decyzja brzmi CLOSED. Wartość Δ zapisujemy liczbą w karcie przed zamrożeniem i już jej nie zmieniamy.

Przedziały ufności: bootstrap po zapytaniach (10 000 powtórzeń, ziarno 20260929, percentyle 2,5 i 97,5). Oba modele działają na tych samych zapytaniach, więc losowanie jest wspólne.

## Próby

| Próba | Liczność | Sposób losowania | Ziarno | Suma kontrolna |
|---|---|---|---|---|
| strojenie | 100 zapytań | losowo z zapytań korpusu | 20260929 | powstanie przed zamrożeniem |
| kontrolna (otwierana raz) | 100 zapytań | losowo, rozłącznie ze strojeniem | 20260929 | powstanie przed zamrożeniem |
| główna | N zapytań | reszta, rozłącznie z obiema | 20260930 | powstanie przed zamrożeniem |

Liczność N wyznaczamy po pomiarze rozrzutu różnic na próbie strojenia, ale przed otwarciem próby głównej. Żeby półszerokość przedziału nie przekraczała Δ/2, potrzeba N ≥ (2·1,96·σ/Δ)², gdzie σ to odchylenie standardowe różnicy nDCG@10 po zapytaniach, zmierzone na strojeniu. Jeśli korpus ma mniej zapytań, niż wynika ze wzoru, wynik opisujemy jako zdolny wykluczyć tylko duże różnice.

Dane: tylko teksty publiczne. Do modelu chmurowego trafiają wyłącznie teksty z korpusu publicznego. Proponowany korpus to polski zbiór [PIRB](https://arxiv.org/abs/2402.13350); kod benchmarku ma licencję Apache-2.0, ale strona projektu nie podaje licencji poszczególnych zbiorów, więc każdy podzbiór trafia na listę dozwolonych źródeł dopiero po sprawdzeniu jego licencji i zapisaniu uzasadnienia.

## Konfiguracje

| Nazwa | Model | Wariant | Parametry |
|---|---|---|---|
| lokalny | bge-m3 (`lab/models.yaml`, licencja MIT) | osadzenia gęste | 1024 wymiary, długość do 8192 tokenów, uruchamiany na K12 |
| chmurowy | text-embedding-3-large (OpenAI), identyfikator i data zapytań zapisywane przy każdym przebiegu | osadzenia gęste | 3072 wymiary, domyślne parametry usługi, trzy przebiegi w różnych dniach |
| bm25 (punkt odniesienia) | BM25 | wyszukiwanie po słowach | parametry domyślne biblioteki, zapisane w konfiguracji |

Ten sam korpus, te same zapytania, ten sam sposób dzielenia tekstu na fragmenty i ta sama miara podobieństwa w obu modelach. Każdy przebieg zapisuje commit kodu, wersję modelu i datę. Zmiana modelu, dzielenia tekstu, miary albo progów po zamrożeniu karty wymaga nowej wersji karty. Przed pierwszym przebiegiem trzeba sprawdzić, czy warunki usługi chmurowej dopuszczają publikację wyników porównania, i zapisać to w `lab/models.yaml` razem z podstawą.

## Założenie, od którego wszystko zależy

Zbiór zapytań i złotych odpowiedzi dobrze odróżnia lepsze wyszukiwanie od gorszego. Mierzymy to zamiast zakładać: jeśli model chmurowy nie wygrywa z BM25 z zauważalnym zapasem (bm25_gap co najmniej dwukrotnie większy niż cloud_drift), test nie ma z czego wyprowadzić sensownego Δ i eksperyment kończy się decyzją CLOSED. Żadnego wniosku o modelach wtedy nie wyciągamy.

## Kryteria bramek

- G1 (S do M). Dane: próba strojenia i próba kontrolna. Najpierw sprawdzamy założenie: bm25_gap co najmniej dwukrotnie większy niż cloud_drift, w przeciwnym razie CLOSED. Potem jakość: GO, gdy dolna granica 95% przedziału ndcg10_diff jest powyżej −Δ. NOT-NOW z warunkiem powrotu (większa próba), gdy przedział przecina −Δ, a punkt centralny różnicy jest powyżej −Δ. NO-GO, gdy górna granica przedziału jest poniżej −Δ albo punkt centralny leży poniżej −Δ. Wykonalność opisujemy osobno: query_p95 i index_time spełnione albo niespełnione, bez wpływu na decyzję jakościową. Opublikowany wynik ma dwa niezależne wiersze: jeden dla jakości i jeden dla wykonalności.
- G2 (M do L). Dane: próba główna. Warunki takie same jak na G1. Do tego opisany dryf modelu chmurowego i, jeśli dostępny, wynik powtórzony na drugim korpusie. GO na G2 dopuszcza sformułowanie „lokalny model nie jest gorszy o więcej niż Δ na tym korpusie”, nigdy „lokalny jest tak samo dobry”.

## Warunek przerwania

- Jeśli usługa chmurowa zwraca błędy dla więcej niż 5% zapytań w którymkolwiek przebiegu, kończymy pomiar, opisujemy przyczynę i piszemy nową wersję karty.
- Jeśli licencja któregokolwiek podzbioru korpusu wyklucza publikację wyników, wyłączamy go przed pomiarem. Po pomiarze nic już nie usuwamy.
- Jeśli warunki usługi chmurowej nie dopuszczają publikacji wyniku porównania, kończymy przed pierwszym przebiegiem i wybieramy inny model chmurowy w nowej wersji karty.

## Czego ta metoda nie wykryje

- Wyników na słownictwie konkretnej firmy: korpus publiczny nie zastąpi jej dokumentów.
- Zachowania na dokumentach dłuższych niż fragmenty użyte w teście.
- Kosztów i wymagań prawnych przy wyborze między modelem lokalnym a chmurowym. Mierzymy jakość wyszukiwania i wykonalność techniczną.
- Zmian modelu chmurowego po dniu pomiaru. Dryf mierzymy tylko w oknie kilku dni.
- Słabości wspólnych dla obu modeli, na przykład błędnych złotych odpowiedzi w korpusie.

## Prace pokrewne

- [Dadas i in., 2024 (PIRB)](https://arxiv.org/abs/2402.13350): zbiór testowy do porównywania polskich modeli wyszukiwania. Porównują wiele modeli na wielu zbiorach; my zadajemy jedno pytanie o nie-gorszość lokalnego modelu z wcześniej zamrożonym progiem i osobnym pomiarem wykonalności.
- [Chen i in., 2024 (BGE M3-Embedding)](https://arxiv.org/abs/2402.03216): model, który sprawdzamy po stronie lokalnej.
- [Muennighoff i in., 2023 (MTEB)](https://arxiv.org/abs/2210.07316): szeroki zestaw testów osadzeń. My nie porównujemy rankingów, tylko sprawdzamy jedną hipotezę z jednostronnym progiem.
- Schuirmann, 1987: klasyczne testy równoważności i nie-gorszości, z których bierzemy jednostronny test z marginesem.
