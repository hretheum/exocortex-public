---
id: progress
lang: pl
counterpart: ../en/03-progress.md
provenance: ai_authored
provenance_metadata:
  agent: Claude Opus 5.5 (Cowork)
  date: 2026-09-28
  human_validated: false
---

# Stan prac

Dziennik tego, co zrobiono w ramach [roadmapy](02-roadmap.md), od najnowszych wpisów. Stan pojedynczych zadań jest w nagłówkach ich plików. Tu zapisujemy, co się zmieniło, co zostało i co wyszło po drodze.

## 2026-09-28

Prace nad F0 i F1 wykonywał w nocy agent, bez udziału właściciela. Wszystko, co zrobił, czeka na przejrzenie. Pola `human_validated` pozostają ustawione na `false`.

### F0. Bramka

Skaner `leakgate` sprawdza tekst, pliki z metadanymi (zdjęcia, PDF, dokumenty biurowe), archiwa, paczki Pythona, obrazy kontenerów i metadane commitów. Lista zakazanych nazw ma 11 613 skrótów HMAC. W obrazach kontenerów skaner sprawdza konfigurację oraz pliki, które trafiają tam z repozytorium. Pliki wykonywalne i skompilowany kod Pythona w obrazie są dozwolone, ale ich napisy też są sprawdzane. Autotest podrzuca 73 przypadki i wszystkie są wyłapywane.

Porównanie z korpusem prywatnym (`simcheck`) ma skalibrowany próg dosłownego podobieństwa (0,40). Część semantyczna wymaga modelu embeddingów na serwerze i jeszcze nie jest skalibrowana. Dlatego F0.6 ma status `doing`.

Autotest nocny jest gotowy, ale noce jeszcze się nie liczą: zaczną się po pierwszym uruchomieniu na serwerze i w CI. Stare wydanie paczki na PyPI czeka na usunięcie przez właściciela.

### F1. Repozytorium

Powstało prywatne repozytorium robocze. Kod silnika przeszedł przez eksport z listą dozwolonych ścieżek, a przykładowa konfiguracja została napisana od nowa na fikcyjnych danych. Narzędzie `code_en` znalazło 604 fragmenty z polskim tekstem w komentarzach, docstringach i komunikatach. Zmieniono 341 z nich. Pozostałe były po angielsku i zostały oznaczone przez zbyt czuły detektor, który potem poprawiono. Po drodze usunięto odwołania do prywatnych notatek z zadaniami.

Znany dług: część napisów widocznych dla użytkownika (nagłówki w wiki, odpowiedzi bota) jest nadal po polsku, bo to zachowanie programu, a nie komentarz. Przejście na angielski wymaga obsługi języków w silniku i będzie osobnym zadaniem. Drugi dług to lint: `ruff` zgłasza kilkaset uwag, więc w CI to zadanie informuje, ale nie blokuje.

Obraz i paczka są budowane z listy jawnie wskazanych ścieżek. Paczka 0.2.0 przechodzi bramkę lokalnie. CI na GitHubie uruchomi się po pierwszym wypchnięciu repozytorium i po dodaniu klucza bramki jako sekretu.

Dokumenty mają narzędzia `paritycheck` (zgodność wersji PL i EN) i `humanlint` (nawyki modeli językowych) oraz słownik terminów. Progi `humanlint` ustawiono na podstawie tekstów pisanych przez ludzi. Publikator i jednostki systemd dla serwera są gotowe i przetestowane na lokalnym repozytorium. Pierwsza publikacja przeniosła dokumenty do repozytorium roboczego. Wypchnięcie na GitHuba i uruchomienie na serwerze należą do właściciela.

### Co dalej

Kroki właściciela: usunięcie wydania na PyPI, klucz bramki w sekretach GitHuba, wypchnięcie repozytorium, uruchomienie publikatora i indeksu na serwerze, przejrzenie kodu i dokumentów. Potem siedem nocy autotestu i przełączenie na publiczne według warunków z roadmapy.
