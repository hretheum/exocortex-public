---
type: runbook_l
lang: pl
counterpart: ../../en/templates/runbook-l.md
hypothesis: "<slug>"
variant: L-a            # L-a własna infrastruktura | L-b chmura w UE | L-c hybryda według klasy danych
source_results: []      # identyfikatory wyników z pilota, z których policzono liczby
human_validated: false
---

# Wdrożenie w dużej organizacji: <nazwa rozwiązania>

Dokument opisuje, jak przeprowadzić wdrożenie. Nie jest zapisem wdrożenia. Każda liczba ma wzór i odnośnik do wyniku z pilota.

## 1. Cel, zakres i czego dokument nie obejmuje

## 2. Parametry skali

| Parametr | Zmierzone w pilocie | Wolumen docelowy | Wynik w skali | Wzór |
|---|---|---|---|---|
| koszt na jednostkę | | | budżet roczny | |
| odsetek przypadków do ręcznej kontroli | | | przypadki miesięcznie, etaty | |
| opóźnienie (95. percentyl) | | | wymagania sprzętowe | |
| wielkość indeksu i grafu | | | pamięć, dysk | |

## 3. Architektura

Opis wybranego wariantu i porównanie z pozostałymi dwoma: koszt, kontrola nad danymi, czas wdrożenia, zależność od dostawcy.

## 4. Dane i zgodność z przepisami

Klasyfikacja danych, podstawa prawna przetwarzania, ocena skutków dla ochrony danych, okresy przechowywania, klasa ryzyka według AI Act z uzasadnieniem.

## 5. Bezpieczeństwo

Wstrzykiwanie poleceń, wyprowadzanie danych przez narzędzia, uprawnienia do zakresów wiedzy według ról, dzienniki i audyt.

## 6. Utrzymanie modeli

Rejestr modeli i promptów, testy jakości w CI na zbiorze regresyjnym z pilota, monitorowanie jakości i dryfu, procedura zmiany modelu, udział człowieka.

## 7. Organizacja

Podział odpowiedzialności, role, szkolenia, właściciel biznesowy, wsparcie.

## 8. Wdrażanie etapami

Fale z grupą kontrolną, wskaźniki z parami równoważącymi, metryki ochronne, kryteria przejścia między falami.

## 9. Uzasadnienie biznesowe

Porównanie wariantów, w tym wariantu, w którym niczego nie zmieniamy, koszty w horyzoncie kilku lat, scenariusz ostrożny z niższymi korzyściami i wyższymi kosztami oraz okres zwrotu.

## 10. Ryzyka, warunek przerwania, plan wycofania
