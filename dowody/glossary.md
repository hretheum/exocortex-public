# Słownik / Glossary

Te same terminy tłumaczymy wszędzie tak samo. The same terms are translated the same way everywhere.

| PL | EN | Definicja | Definition |
|---|---|---|---|
| bramka | gate | Sprawdzenie, które zatrzymuje plik przed publikacją, jeśli znajdzie w nim coś niedozwolonego. | A check that stops a file before publication if it finds something that is not allowed. |
| bramka publikacji (leakgate) | publishing gate (leakgate) | Skaner porównujący pliki, obrazy i metadane commitów z haszowaną listą zakazanych nazw i wzorcami danych osobowych. | The scanner that compares files, images and commit metadata with a hashed denylist and personal-data patterns. |
| lista zakazanych nazw | denylist | Nazwy klientów, osób i projektów, które nie mogą trafić do publicznych artefaktów. W repozytorium są tylko ich skróty HMAC. | Client, person and project names that must not reach public artifacts. The repository holds only their HMAC hashes. |
| kanarek | canary | Sztuczny zakazany ciąg podrzucany celowo, żeby sprawdzić, czy bramka go złapie. | An artificial forbidden string planted on purpose to test that the gate catches it. |
| flaga blokady | lock flag | Plik tworzony, gdy autotest bramki zawiedzie; dopóki istnieje, nic nie jest publikowane. | A file created when the gate self-test fails; while it exists, nothing is published. |
| porównanie z korpusem prywatnym (simcheck) | private corpus comparison (simcheck) | Sprawdzenie, czy tekst nie jest zbyt podobny do materiałów prywatnych, także po przeredagowaniu. | A check that the text is not too similar to private material, including after rewording. |
| publikator | publisher | Proces na serwerze, który co kwadrans przenosi zmienione dokumenty z vaulta do repozytorium, jeśli przeszły wszystkie sprawdzenia. | A process on the server that every fifteen minutes moves changed documents from the vault to the repository if they pass every check. |
| karta hipotezy | hypothesis card | Jednostronicowy opis hipotezy, sposobu jej sprawdzenia i progu, przy którym uznajemy ją za potwierdzoną albo odrzuconą. | A one-page description of a hypothesis, how it will be tested, and the threshold at which it counts as confirmed or rejected. |
| zbiór kontrolny | control set | Ustalony z góry zestaw przypadków, na którym porównuje się wyniki przed zmianą i po niej. | A set of cases fixed in advance, used to compare results before and after a change. |
| przebieg | run | Jedno wykonanie eksperymentu albo procesu z zapisanymi wejściami, wersjami i wynikiem. | One execution of an experiment or process with its inputs, versions and result recorded. |
| dowód | evidence | Zapisany, sprawdzalny wynik, do którego można wrócić i który ktoś inny może powtórzyć. | A recorded, checkable result that one can come back to and that someone else can repeat. |
| karta referencyjna | reference card | Opis zrealizowanego projektu przygotowany na potrzeby oferty lub przetargu. | A description of a completed project prepared for a bid or tender. |
