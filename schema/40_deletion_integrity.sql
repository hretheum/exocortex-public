-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- schema/40_deletion_integrity.sql — zadanie-13-integralnosc-usuwania.md.
--
-- Dwie zmiany połączone w jedną migrację, żeby nie migrować schematu dwa
-- razy (obie blokują zapis twierdzeń wygenerowanych przez model do grafu).
--
-- ============================================================================
-- Część 1 — gwarancja braku osieroconych krawędzi przy usunięciu myśli
-- ============================================================================
--
-- `edges.dst_id`/`edges.src_id` są polimorficzne (dziś realnie: thought,
-- synthesis jako src; thought, entity — cztery podtypy przez entities.type —
-- i raw_source jako dst), więc zwykły klucz obcy na jednej kolumnie odpada.
-- Jedyna operacja usuwania, jaka istnieje w kodzie, to DELETE FROM thoughts
-- (scripts/extract_claims.py::delete_run, /capture/delete działa wyłącznie
-- na raw_sources i nigdy nie usuwa wierszy — patrz Część 2 niżej). entities,
-- raw_sources i syntheses nie są nigdzie usuwane, więc trigger obejmuje
-- wyłącznie thoughts — rozszerzenie na pozostałe tabele, gdyby kiedyś
-- zaczęły być usuwane, to nowy CREATE TRIGGER z tą samą funkcją, nie zmiana
-- tej migracji.
--
-- Odrzucone warianty:
--   1. FK bezpośrednio na src_id/dst_id — niemożliwe: jedna kolumna nie może
--      referencjonować czterech różnych tabel jednocześnie bez restrukturyzacji.
--   2. Przebieg okresowy (sweep) szukający krawędzi bez odpowiednika w tabeli
--      docelowej — odrzucony: daje sprzątanie EWENTUALNE, nie GWARANCJĘ. Między
--      usunięciem a kolejnym przebiegiem krawędź jest osierocona i czytelna
--      (dokładnie ten stan, który już nieformalnie wykrywa
--      exocortex/wiki/domains/home/__init__.py — zapytanie o osierocone
--      krawędzie istnieje, ale nic ich nie usuwa). Ten brief wymaga gwarancji.
--   3. Rozbicie `edges` na tabele per typ celu (edges_thought, edges_entity, …)
--      z prawdziwymi FK — poprawne architektonicznie, ale jawnie poza zakresem
--      tego zadania (brief: "to jest zmiana o szerszych skutkach niż ten
--      brief" — warunek stopu, nie wybór projektowy).
--
-- Wybrany: trigger, bo działa W TEJ SAMEJ transakcji co DELETE — usunięcie i
-- sprzątnięcie krawędzi albo oba się powiodą, albo oba się cofną. To jest
-- właściwa treść słowa "gwarantuje".

CREATE OR REPLACE FUNCTION fn_cleanup_thought_edges() RETURNS trigger AS $$
BEGIN
  DELETE FROM edges
  WHERE (src_id = OLD.id AND src_type = 'thought')
     OR (dst_id = OLD.id AND dst_type = 'thought');
  RETURN OLD;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tg_cleanup_thought_edges ON thoughts;
CREATE TRIGGER tg_cleanup_thought_edges
  AFTER DELETE ON thoughts
  FOR EACH ROW
  EXECUTE FUNCTION fn_cleanup_thought_edges();

COMMENT ON FUNCTION fn_cleanup_thought_edges IS
    'zadanie-13 — usuwa krawędzie w obu kierunkach (src i dst) przy usunięciu '
    'myśli. Jedyny mechanizm, transakcyjny, obejmuje też usuwanie wsadowe '
    '(DELETE ... WHERE metadata->>''run_id''=X odpala ten trigger raz na wiersz).';

-- ============================================================================
-- Część 3 — ADR-008: cytat wymagany dla twierdzeń
-- ============================================================================
--
-- Dotyczy wyłącznie thought_type='claim' (treść wygenerowana przez model).
-- vault_note/backlog_item/recipe/work_meeting_note są przepisane z plików —
-- bez nowego wymogu, bez zmiany liczby wierszy, bez zmiany constraintu.
--
-- scripts/extract_claims.py NIE wymagał zmiany: check_grounding() już dziś
-- odrzuca pusty/whitespace'owy cytat (`if not quote or not quote.strip():
-- return False`) zanim claim w ogóle dotrze do _write_claim(), więc every
-- wiersz, jaki ten kod kiedykolwiek zapisał, miał cytat. Ten constraint jest
-- siecią bezpieczeństwa na poziomie schematu — zamyka drogę dla KAŻDEGO
-- przyszłego/innego kodu, nie tylko dla dzisiejszego procesora.

ALTER TABLE thoughts ADD CONSTRAINT chk_claim_requires_quote
  CHECK (thought_type <> 'claim' OR (metadata->>'quote' IS NOT NULL AND metadata->>'quote' <> ''));

COMMENT ON CONSTRAINT chk_claim_requires_quote ON thoughts IS
    'ADR-008 (vault: _source/work/architecture/decisions/'
    'ADR-008-twierdzenie-zawsze-z-cytatem.md) — twierdzenie bez cytatu '
    'źródłowego nie może zostać zapisane. Dotyczy wyłącznie thought_type=''claim''.';
