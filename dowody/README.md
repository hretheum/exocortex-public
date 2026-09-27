# Dowody / Evidence

Publiczny zapis prac badawczo-rozwojowych nad AI prowadzonych w laboratorium Exocortexa: jak działa cykl, co planujemy, jakie hipotezy sprawdzamy i co z tego wychodzi. Każdy dokument jest po polsku i po angielsku.

A public record of AI research and development in the Exocortex lab: how the cycle works, what we plan, which hypotheses we test and what comes out of them. Every document exists in Polish and in English.

| | Polski | English |
|---|---|---|
| Jak działa cykl / How the cycle works | [pl/01-cycle.md](pl/01-cycle.md) | [en/01-cycle.md](en/01-cycle.md) |
| Roadmapa / Roadmap | [pl/02-roadmap.md](pl/02-roadmap.md) | [en/02-roadmap.md](en/02-roadmap.md) |
| Stan prac / Progress | [pl/03-progress.md](pl/03-progress.md) | [en/03-progress.md](en/03-progress.md) |
| Szablony / Templates | [pl/templates/](pl/templates/) | [en/templates/](en/templates/) |

## Jak są ułożone pliki / How the files are organised

Każdy dokument ma dwie wersje o tej samej nazwie pliku: w `pl/` i w `en/`. W nagłówku pliku pole `lang` mówi, która to wersja, a `counterpart` wskazuje ścieżkę do pary. Linki są zwykłymi linkami Markdown ze ścieżkami względnymi, więc działają i w Obsidianie, i na GitHubie. Te same terminy tłumaczymy wszędzie tak samo; lista jest w [glossary.yaml](glossary.yaml). Przed publikacją skrypt `paritycheck` porównuje obie wersje: nagłówki, liczby, linki, tabele i pola `id`, `status`, `depends_on`. Plik bez pary albo z rozbieżnością nie zostanie opublikowany.

Every document has two versions with the same file name: in `pl/` and in `en/`. In the file header, `lang` says which version it is and `counterpart` gives the path to its pair. Links are plain Markdown links with relative paths, so they work both in Obsidian and on GitHub. The same terms are translated the same way everywhere; the list is in [glossary.yaml](glossary.yaml). Before publication the `paritycheck` script compares both versions: headings, numbers, links, tables and the `id`, `status` and `depends_on` fields. A file without a pair, or with a mismatch, is not published.
