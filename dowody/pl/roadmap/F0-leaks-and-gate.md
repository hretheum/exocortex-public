---
id: F0
lang: pl
counterpart: ../../en/roadmap/F0-leaks-and-gate.md
status: doing
provenance: ai_authored
provenance_metadata: {agent: "Claude Opus 5.5 (Cowork)", date: 2026-09-27, human_validated: false}
---

# F0. Zatrzymanie wycieków i bramka publikacji

[← Roadmapa](../02-roadmap.md)

## Cel

Zanim cokolwiek nowego stanie się publiczne, sprawdzamy to, co już jest publiczne, i budujemy mechanizm, który nie przepuści niczego z materiałów klienckich. Zasady projektu zostały spisane później niż część artefaktów Exocortexa (obraz kontenera, paczka Pythona), więc trzeba je z tymi zasadami zestawić i wycofać to, co ich nie spełnia.

Bramka ma trzy warstwy. Skaner tekstu i plików szuka zakazanych nazw, danych osobowych i metadanych. Skaner artefaktów budowanych rozpakowuje paczki i obrazy kontenerów przed wysłaniem. Porównanie z prywatnym korpusem wyłapuje fragmenty przeredagowane tak, że nie zawierają już żadnej nazwy. Całość jest co noc testowana na przypadkach z celowo wstawionymi wyciekami.

## Faza jest skończona, gdy

- żaden wcześniej opublikowany artefakt nie narusza zasad albo został wycofany,
- skaner działa lokalnie przed commitem i w CI przed każdą publikacją,
- nocny test bramki przechodzi w całości co najmniej siedem dni z rzędu.

## Zadania

| Id | Zadanie | Zależy od | Szacunek |
|---|---|---|---|
| [F0.1](F0/F0.1-close-leaking-channels.md) | Wyłączyć publiczny dostęp do artefaktów sprzed zasad i zatrzymać ich automatyczne publikowanie | | 1 h |
| [F0.2](F0/F0.2-exposure-audit.md) | Spisać wszystkie miejsca, gdzie coś z projektu jest publiczne, i sprawdzić każde | F0.1 | 4 h |
| [F0.3](F0/F0.3-denylist.md) | Zbudować prywatną listę zakazanych nazw i jej wersję w postaci skrótów | F0.2 | 4 h |
| [F0.4](F0/F0.4-scanner-text-and-files.md) | Napisać skaner tekstu i plików | F0.3 | 1 dzień |
| [F0.5](F0/F0.5-scanner-build-artifacts.md) | Rozszerzyć skaner na paczki i obrazy kontenerów | F0.4 | 4 h |
| [F0.6](F0/F0.6-similarity-check.md) | Zbudować porównanie z prywatnym korpusem | F0.4 | 1 dzień |
| [F0.7](F0/F0.7-gate-self-test.md) | Zestaw testów bramki uruchamiany co noc | F0.4, F0.5, F0.6 | 1 dzień |

## Dwie decyzje projektowe

Lista zakazanych nazw nie może leżeć w publicznym repozytorium, bo sama byłaby wyciekiem. Repozytorium dostaje tylko skróty HMAC z tajnym kluczem. Zwykłe skróty nie wystarczą: krótką nazwę firmy da się odgadnąć, licząc skróty ze słownika nazw.

Skaner nie wypisuje znalezionego tekstu. Logi CI w publicznym repozytorium są publiczne, więc raport podaje tylko plik, linię, identyfikator reguły i skrót dopasowania.
