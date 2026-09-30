# Publiczny pakiet grafu laboratorium Exocortex

Każdy folder `v1-<skrót>` to jedna wersja pakietu. Są w nim twierdzenia, które laboratorium wyciągnęło
z publicznych korpusów, dosłowny cytat każdego twierdzenia z pozycją w dokumencie źródłowym, powiązania
między dokumentami i twierdzeniami oraz osadzenia (ang. embeddings) dokumentów. Plik `latest.json` wskazuje
bieżącą wersję. Starsze wersje zostają w historii repozytorium.

| Plik | Zawartość |
|---|---|
| `documents.csv` | dokumenty: artykuł, rodzaj tekstu (abstrakt albo streszczenie), adres, SHA-256 i długość tekstu |
| `claims.csv` | twierdzenia z eksperymentem, przebiegiem i modelem, który je wyciągnął |
| `quotes.csv` | cytat każdego twierdzenia, dokładnie jak w dokumencie, z pozycją początku i końca |
| `edges.csv` | powiązania z typem i wagą, na przykład twierdzenie `derived_from` dokument |
| `vectors-0001.png`, … | osadzenia: każdy dokument to jeden wiersz pikseli w 8-bitowym obrazie w skali szarości |
| `vectors.csv` | który obraz i wiersz należy do którego dokumentu oraz skala każdego wektora |
| `datapackage.json` | opis kolumn, kluczy i odwołań (Frictionless Data) |
| `manifest.json` | SHA-256 każdego pliku i skrót całego pakietu |

Osadzenie odczytuje się z wiersza pikseli jako `skala × (piksel − 128)` dla każdego piksela wiersza. Obrazy
są zapisane bez kompresji, więc otworzy je każdy czytnik PNG, a te same liczby dają zawsze te same bajty.
Żaden plik nie jest większy niż 2 MiB: większa tabela cytatów albo powiązań jest zapisana w częściach o tych
samych kolumnach (`quotes-0001.csv`, `quotes-0002.csv`), a `datapackage.json` wymienia wszystkie pliki.

Teksty i tytuły dokumentów nie są tu powtórzone. Leżą w `lab/corpora/<korpus>/corpus.jsonl` tego
repozytorium, z tym samym SHA-256, liczonym po zastąpieniu każdego ciągu białych znaków jedną spacją. Pozycje liczą znaki tego
tekstu. Pakiet obejmuje tylko korpusy, których źródło ma w `lab/sources.yaml` zapisaną podstawę do dalszego
udostępniania.

## Jak sprawdzić skrót

Skrót pakietu to SHA-256 wyniku `sha256sum` dla jego plików poza `manifest.json`, wymienionych według nazwy.
Pierwsze 12 znaków skrótu jest w nazwie folderu:

    cd v1-<skrót>
    LC_ALL=C ls | grep -vx manifest.json | xargs sha256sum | sha256sum

Pełne sprawdzenie wymaga tylko Pythona 3.10 lub nowszego, uruchomionego w katalogu głównym repozytorium.
Sprawdza każdą sumę kontrolną i każde odwołanie między plikami, a z `--corpora` także każdy cytat
z tekstem jego dokumentu:

    python lab/graph_package.py verify dowody/data/graph/v1-<skrót> --corpora lab/corpora

Laboratorium buduje pakiet ze swojej bazy poleceniem `python lab/graph_package.py build`. Te same dane dają
zawsze te same bajty, więc ponowna budowa daje ten sam skrót.
