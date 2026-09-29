---
id: intent-vs-fact-applications
lang: pl
counterpart: ../../../en/experiments/intent-vs-fact/applications.md
type: applications
slug: intent-vs-fact
label: hipoteza, bez dowodu
source_hash: 52502ecffcb3841e2aa6689f11d722406d9fa2cb3095cd58cb7265f574483400
publish: true
human_validated: true
provenance: ai_authored
provenance_metadata:
  agent: Claude Sonnet 5.5 (Cowork), text written by hand through exocortex lab applications
  date: '2026-09-29'
---

# Zastosowania biznesowe: Zamiar czy fakt

Pomaga zdecydować, czy narzędzie streszczające teksty potrzebuje dodatkowego pola "fakt czy plan", żeby nie przedstawiać zamiarów jak rzeczy zrobionych.

## Zastosowania

| Zastosowanie | Kto korzysta | Wynik, na którym się opiera | Siła dowodu | Warunki i granice |
|---|---|---|---|---|
| Ryzyko i zgodność: ocena, czy można ufać streszczeniom przygotowanym przez model | osoby odpowiedzialne za jakość i zgodność | [wyniki w dossier](overview.md#s-results) | hipoteza, bez dowodu | Wynik dotyczy angielskich streszczeń naukowych i konkretnych modeli lokalnych. Bez wyniku nie ma podstaw, żeby uznać, że model odróżnia plan od faktu. |
| Wybór narzędzia: decyzja, czy dodać do wyciągania twierdzeń obowiązkowe pole "fakt czy plan" | zespół, który buduje takie narzędzie | [wyniki w dossier](overview.md#s-results) | hipoteza, bez dowodu | Dotyczy jednego sposobu zapisu tej informacji i dwóch modeli lokalnych. O innych sposobach wynik nic nie mówi. |
| Organizacja badań: kontrola własnych streszczeń pod kątem zamiany zamiaru w fakt | zespół, który przygotowuje streszczenia dla innych | [wyniki w dossier](overview.md#s-results) | hipoteza, bez dowodu | Sprawdzamy streszczenia naszego laboratorium. Nie przenosimy wniosku na streszczenia z innych systemów. |

## Jeśli potwierdzimy, jeśli obalimy

- Jeśli potwierdzimy: dodanie jednego pola do formularza sprawia, że rzadziej mylimy plan z rzeczą zrobioną. Zespół może wprowadzić to pole jako standard i kontrolować streszczenia pod tym kątem.
- Jeśli obalimy: samo pole nie pomaga. Zespół nie traci czasu na jego wdrażanie i ogranicza ryzyko pomyłek między planem a faktem inaczej, na przykład ręczną kontrolą próbki.

## Czego z tego nie wolno wyciągać

- Korpus to abstrakty artykułów z arXiv. Nie przenosimy wyniku na inne rodzaje tekstu, na przykład umowy, wiadomości czy raporty firmowe.
- Eksperyment mierzy pomyłki między planem a faktem. Nie mierzy kosztu ani czasu przetwarzania.
- Karta hipotezy nie jest jeszcze zamrożona, więc próg i sposób oceny mogą się jeszcze zmienić.

## Co sprawdzić dalej

- Zamrozić kartę hipotezy i zrobić pierwszy pomiar.
- Po zamrożeniu karty i pierwszym przebiegu wygenerować tę stronę od nowa, bo zmieni się wynik.

## Dla dociekliwych: szczegóły techniczne

- Jeśli potwierdzimy: w ślepej próbie ocenianej przez człowieka odsetek twierdzeń z zamianą trybu jest niższy w wariancie z polem trybu niż bez niego o więcej niż próg z karty hipotezy, a obie metryki ochronne mieszczą się w progach.
- Jeśli obalimy: różnica między wariantami jest mniejsza niż próg z karty albo przedział ufności obejmuje zero (H0).
