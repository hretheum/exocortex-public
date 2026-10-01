---
id: card-compiler
lang: pl
counterpart: ../en/08-card-compiler.md
provenance: ai_authored
provenance_metadata:
  agent: Claude Code (cloud session)
  date: 2026-10-01
  human_validated: false
---

# Kompilator karty referencyjnej

Karta referencyjna opisuje zakończony projekt na potrzeby oferty lub przetargu. Ten dokument wyjaśnia program, który pisze takie karty z zapisów laboratorium: co czyta, co zapisuje i dlaczego wytworzonej przez niego karcie można ufać. To zadanie F4.2 fazy [F4](roadmap/F4-reference-card.md). Kształt karty opisuje dokument [Ogólny model karty referencyjnej](07-card-model.md).

## Po co

Karta pisana ręcznie z czasem rozmija się z faktami. Liczba jest zapamiętana źle, plan zapisany tak, jakby był wykonany, projekt nazwany sukcesem, zanim ktokolwiek o tym zdecydował. Kupujący nie ma jak tego sprawdzić. Kompilator usuwa rękę człowieka z tego procesu: bierze kartę wyłącznie z plików, które laboratorium już opublikowało, a obok każdego zdania wstawia odsyłacz do pliku albo wiersza danych, z którego zdanie pochodzi. Czytelnik może otworzyć każdy odsyłacz i zobaczyć źródło.

## Jak to działa

Program nazywa się `exocortex lab card-compile` i dostaje nazwę eksperymentu. Czyta kartę hipotezy (po polsku i po angielsku), tabele przebiegów, prób, konfiguracji i metryk, rejestr prerejestracji oraz decyzje z bramek, jeśli jakieś są. Potem zapisuje kartę dwa razy, po polsku i po angielsku, w dziewięciu sekcjach, które zawsze występują w tej samej kolejności.

Każde zdanie powstaje jednym z dwóch sposobów. Albo jest wzorem zdania wypełnionym wartościami z danych, na przykład: „W przebiegu X na próbie Y metryka Z wyniosła 0,083, przedział ufności od 0,015 do 0,354.” Albo jest fragmentem karty hipotezy przepisanym słowo w słowo. Program nie wywołuje modelu językowego i niczego nie pisze od siebie.

Jeśli czegoś brakuje, karta mówi to wprost. Dla eksperymentu, który został uruchomiony, ale jeszcze niezmierzony, sekcja Wyniki zawiera po jednym zdaniu na przebieg: „nie opublikowano dla niego żadnej metryki” z datą. Luki nigdy nie wypełnia domysłem.

## Status projektu

Status na karcie wynika z ostatniej decyzji bramki zatwierdzonej przez człowieka i nigdy nie jest od niej wyższy. Jeśli żadna bramka jeszcze nie zdecydowała, status to „zamrożona” (karta hipotezy jest zarejestrowana i nie zmieniła się od rejestracji) albo „szkic”. Karta bez decyzji nie może powiedzieć GO. Testy sprawdzają to wprost.

Decyzja bramki liczy się tylko wtedy, gdy istnieją obie wersje językowe i są zgodne, człowiek zatwierdził obie, dotyczy bieżącej wersji karty, a wyniki, które wskazuje, istnieją w danych. W przeciwnym razie karta wymienia dokument i mówi, dlaczego go nie zastosowano.

## Uczciwe liczby

Liczba, która jest zmierzonym wynikiem, jest pokazana tak, jak ją zapisano, rozsądnie zaokrąglona. Liczba, która jest tylko ustawieniem, na przykład próg, ziarno losowania albo rozmiar próby, jest pokazana w formacie kodu, więc nie da się jej wziąć za wynik. Zdanie o stanie bieżącym zawsze ma datę.

Po zapisaniu program uruchamia na własnym wyniku dwie kontrole: czy karta zgadza się z modelem i czy jakieś zdanie nie brzmi pewniej, niż pozwalają dowody. Obie muszą niczego nie znaleźć.

## Przykład

Dla eksperymentu zabawkowego, który sprawdza maszynerię laboratorium, program zapisuje po 60 zdań w każdym języku. Wiersz o statusie brzmi: „Stan na 2026-10-01: status projektu to szkic: karta hipotezy nie jest zamrożona.” Jeden z wyników brzmi: „W przebiegu `run-2026-09-29-1` na próbie `tuning-12` (rola: strojenie) metryka `long_unit_share` dla konfiguracji `longest-sentence` wyniosła 0,833 (przedział ufności od 0,552 do 0,953, n = 12, metoda `wilson`).” Obok jest odsyłacz do dokładnej linii pliku z metrykami.

## Czego jeszcze nie robi

- Pierwszy prawdziwy eksperyment nie ma jeszcze wyników, więc nie ma dla niego karty. Gdy wyniki się pojawią, to samo polecenie ją wytworzy.
- Program niczego nie publikuje. Karty trafiają do wskazanego folderu. Decyzja, gdzie karty są publikowane i kiedy się je odświeża, pozostaje otwarta.
- Sekcja Wyniki pokazuje każdą zapisaną metrykę. Czy ma pokazywać tylko wyniki, na których opiera się decyzja bramki, to otwarte pytanie w modelu karty.
