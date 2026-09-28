---
id: intent-vs-fact-corpus
lang: pl
counterpart: ../../../en/experiments/intent-vs-fact/corpus.md
provenance: ai_authored
provenance_metadata:
  agent: Claude Opus 5.5 (Cowork)
  date: 2026-09-28
  human_validated: false
---

# Korpus eksperymentu „zamiar czy fakt”

Opis korpusu dla pierwszego eksperymentu laboratorium ([F3](../../roadmap/F3-first-pass.md), zadanie [F3.1](../../roadmap/F3/F3.1-public-corpus-selection.md)). Eksperyment sprawdza, czy wyciąganie twierdzeń z tekstu poprawnie odróżnia fakty od zamiarów, hipotez i zapowiedzi, oraz czy nasze streszczenia nie zamieniają zamiaru w fakt.

## Źródło

Artykuły z arXiv, które Exocortex pobrał i streścił w sierpniu i wrześniu 2026 roku. Silnik ma 2486 stron artykułów; po usunięciu jednego artykułu zapisanego w dwóch wersjach zostaje 2485 różnych identyfikatorów. Każdy artykuł ma w silniku polskie streszczenie i listę najważniejszych ustaleń oraz ocenę trafności od 1 do 10.

Do korpusu idą dwa teksty na artykuł:

| Tekst | Skąd | Język |
|---|---|---|
| Abstrakt | API arXiv, pobrany na nowo w F3.2, z wersją artykułu i datą pobrania | angielski |
| Streszczenie i ustalenia | baza Exocortexa, z wersją modelu i datą streszczenia | polski |

Pełnych tekstów artykułów nie używamy.

## Podstawa korzystania

- **Abstrakty.** arXiv udostępnia opisowe metadane artykułów na zasadach CC0 1.0 ([warunki korzystania z API arXiv](https://info.arxiv.org/help/api/tou.html), [licencje arXiv](https://info.arxiv.org/help/license/index.html)). Strony arXiv nie wymieniają abstraktów z nazwy, ale API zwraca je jako metadane, a publiczne zbiory abstraktów traktują je jako CC0 ([Common Pile, arxiv_abstracts](https://huggingface.co/datasets/common-pile/arxiv_abstracts)). Abstrakty trafią do repozytorium razem z manifestem. Jeśli arXiv wyjaśni to inaczej, w repozytorium zostaną tylko identyfikatory i skrypt pobierający.
- **Streszczenia.** Są wytworem naszego silnika, więc publikujemy je w całości, z wersją modelu, który je zrobił.
- **Warunki API.** Najwyżej jedno zapytanie co trzy sekundy i jedno połączenie naraz. Laboratorium nie przedstawia się jako projekt wspierany przez arXiv.

## Rama losowania

Artykuł wchodzi do ramy, jeśli ma poprawny identyfikator arXiv, abstrakt dostępny w API i streszczenie w silniku. Odpadają artykuły wycofane (abstrakt mówi o wycofaniu), abstrakty krótsze niż 50 słów i powtórzenia: z kilku wersji zostaje najnowsza.

Warstwy według oceny trafności nadanej przez silnik:

| Warstwa | Ocena | Artykuły |
|---|---|---|
| niska | 1 do 4 | 603 |
| średnia | 5 do 7 | 1010 |
| wysoka | 8 do 10 | 873 |

Liczby dotyczą 2486 stron sprzed usunięcia powtórzenia i zmienią się po wyłączeniach z F3.2. Z ramy losujemy warstwowo trzy rozłączne zbiory: próbę strojenia, zbiór kontrolny i próbę do pilota. Ich wielkość i ziarno losowania ustala karta hipotezy ([F3.4](../../roadmap/F3/F3.4-hypothesis-card.md)), zanim ktokolwiek zobaczy wyniki. Zbiór kontrolny jest zamknięty do końca eksperymentu.

## Uwagi

Abstrakty są po angielsku, a streszczenia po polsku, więc porównanie zamiaru i faktu idzie między językami. Ocena trafności odzwierciedla zainteresowania właściciela laboratorium, a nie jakość artykułu; warstwy mają tylko zapewnić, że w każdej próbie są artykuły z różnych części tej skali.
