---
type: hypothesis_card
lang: pl
counterpart: ../../../en/experiments/toy-length/hypothesis.md
slug: toy-length
version: 1
supersedes: null
tier_target: S
data_class: public
sources: ["../../roadmap/F2/F2.4-hypothesis-processor.md", "../../roadmap/F2/F2.6-experiment-tables.md"]
prereg_hash: null
human_validated: false
---

# Hipoteza: w dokumentach laboratorium najdłuższe zdanie częściej niż pierwsze przekracza 120 znaków

To karta testowa. Służy do sprawdzenia maszynerii laboratorium: prerejestracji ([F2.4](../../roadmap/F2/F2.4-hypothesis-processor.md)), decyzji z bramek ([F2.5](../../roadmap/F2/F2.5-gate-processor.md)) i kolejki eksperymentów ([F2.6](../../roadmap/F2/F2.6-experiment-tables.md)). Jej wynik nie jest dowodem niczego poza tym, że cała droga od karty do wyniku działa.

## Problem

Eksperyment zabawkowy mierzy opublikowane dokumenty laboratorium bez udziału modelu: liczy znaki, słowa i zdania oraz wybiera jedno zdanie według stałej reguły, pierwsze albo najdłuższe. Pytanie jest błahe z założenia, bo liczy się przejście przez cały cykl.

## Hipoteza

- H1: odsetek dokumentów, w których wybrane zdanie ma ponad 120 znaków, jest wyższy przy regule najdłuższego zdania niż przy regule pierwszego zdania, o co najmniej 20 punktów procentowych.
- H0: różnica jest mniejsza niż 20 punktów procentowych albo jej przedział ufności obejmuje zero.

## Metryki

| Rola | Metryka | Definicja | Próg | Linia bazowa | Jak liczona |
|---|---|---|---|---|---|
| rozstrzygająca | long_unit_share_difference | różnica odsetka dokumentów z wybranym zdaniem dłuższym niż 120 znaków | co najmniej 20 punktów procentowych | reguła pierwszego zdania | bootstrap po dokumentach |
| ochronna | failed_share | odsetek dokumentów bez wyniku | 0% | nie dotyczy | liczba |

## Próby

| Próba | Liczność | Sposób losowania | Ziarno | Suma kontrolna |
|---|---|---|---|---|
| strojenie | 12 dokumentów | warstwowo według języka | 20260929 | zapisana w tabeli prób laboratorium |
| kontrolna (otwierana raz) | 6 dokumentów | warstwowo według języka | 20260929 | zapisana w tabeli prób laboratorium |

## Konfiguracje

| Nazwa | Model | Wariant | Parametry |
|---|---|---|---|
| first-sentence (linia bazowa) | brak | pierwsze zdanie | toy-model-a jako nazwa zastępcza |
| longest-sentence | brak | najdłuższe zdanie | toy-model-b jako nazwa zastępcza |

## Założenie, od którego wszystko zależy

Dokumenty nie zmieniają się między wylosowaniem próby a przebiegiem. Jeśli dokument się zmieni, przebieg kończy się błędem zamiast liczyć nowy tekst.

## Kryteria bramek

- G1: różnica co najmniej 20 punktów procentowych i dolna granica przedziału ufności powyżej zera. Wtedy GO, inaczej NO-GO.

## Warunek przerwania

Brak wyniku dla któregokolwiek dokumentu.

## Czego ta metoda nie wykryje

Niczego o jakości dokumentów. Mierzy tylko długość zdań wybranych mechanicznie.

## Prace pokrewne

Brak: to test maszynerii.
