---
id: local-vs-cloud-embeddings-applications
lang: pl
counterpart: ../../../en/experiments/local-vs-cloud-embeddings/applications.md
type: applications
slug: local-vs-cloud-embeddings
label: hipoteza, bez dowodu
source_hash: 022624d5f3cd02bc6880acb2a4f4a8f83bf187ce93a4aeb4b00cf6dae19d24e6
publish: true
human_validated: true
provenance: ai_authored
provenance_metadata:
  agent: qwen3.6-35b-a3b (lab model gateway), exocortex lab applications
  date: '2026-09-29'
---

# Zastosowania biznesowe: Model lokalny czy chmurowy

Pomaga zdecydować, czy do wyszukiwania po polskich dokumentach wystarczy model uruchamiany u siebie, czy trzeba zostać przy chmurowym.

## Zastosowania

| Zastosowanie | Kto korzysta | Wynik, na którym się opiera | Siła dowodu | Warunki i granice |
|---|---|---|---|---|
| Wybór modelu osadzeń (ang. embeddings) do wyszukiwania po polskich dokumentach | zespół, który wybiera lub zmienia model osadzeń w wyszukiwarce | [wyniki w dossier](overview.md#s-results) | hipoteza, bez dowodu | Decyzja opiera się na porównaniu obu modeli na tych samych pytaniach i tym samym polskim zbiorze publicznych dokumentów, z tolerancją ustaloną przed pomiarem. Dotyczy tylko sprawdzonych modeli. |
| Decyzja, czy osadzenia można liczyć na własnym sprzęcie | dział IT i osoby odpowiedzialne za dane | [wyniki w dossier](overview.md#s-results) | hipoteza, bez dowodu | Wymaga dwóch rzeczy naraz: jakość nie może być gorsza o więcej niż ustalona tolerancja, a model musi działać na docelowym sprzęcie w rozsądnym czasie. Modele chmurowe zmieniają się bez uprzedzenia, więc wynik opisuje wersje użyte w badaniu. |

## Jeśli potwierdzimy, jeśli obalimy

- Jeśli potwierdzimy: model uruchamiany u siebie jest wystarczająco dobry, żeby zastąpić chmurowy przy takich dokumentach. Zespół może go rozważyć zamiast chmurowego, a o sprzęcie rozstrzyga jeszcze osobny test wykonalności.
- Jeśli obalimy: model uruchamiany u siebie wypada zauważalnie gorzej. Dla takich dokumentów zespół zostaje przy modelu chmurowym.

## Czego z tego nie wolno wyciągać

- Wynik dotyczy konkretnych modeli i jednego polskiego korpusu publicznego. Nie przenosimy go na inne modele ani inne dane.
- Eksperyment mierzy jakość wyszukiwania oraz wykonalność techniczną na jednym sprzęcie. Nie mierzy kosztów ani stabilności modelu chmurowego w czasie.
- Wynik „brak rozstrzygnięcia” (przedział obejmuje próg) oznacza, że próba była za mała. Nie traktujemy go jako obalenia.

## Co sprawdzić dalej

- Powtórzyć pomiar na drugim korpusie, zanim ktokolwiek oprze o wynik decyzję wdrożeniową.
- Po zamrożeniu karty hipotezy i pierwszym przebiegu wygenerować tę stronę od nowa, bo zmieni się wynik.

## Dla dociekliwych: szczegóły techniczne

- Jeśli potwierdzimy: lokalny model nie jest gorszy od chmurowego o więcej niż zamrożony próg. Wtedy jest wiarygodną alternatywą dla chmurowego na korpusie o podobnym charakterze, a o własnym sprzęcie rozstrzyga jeszcze osobny pomiar wykonalności.
- Jeśli obalimy: lokalny model jest gorszy o więcej niż zamrożony próg. Dla tego zadania zostajemy przy modelu chmurowym.
