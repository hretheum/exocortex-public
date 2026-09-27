-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- K12: embeddingi liczone lokalnie przez bge-m3 (llama-swap, 127.0.0.1:8080),
-- ktory zwraca wektory 1024-wymiarowe — zamiast OpenAI text-embedding-3-small
-- (1536d). Wdrozenie K12 startuje z pusta baza (zadnych policzonych wektorow),
-- wiec zmiana typu kolumn jest natychmiastowa i bezstratna. Indeks HNSW
-- przezywa ALTER TYPE (przebudowa na pustej tabeli = no-op).
--
-- Gdyby przyszle wdrozenie mialo JUZ policzone wektory 1536d: ta migracja
-- wymaga wczesniejszego wyzerowania kolumn (stare wektory i tak sa bezuzyteczne
-- po zmianie modelu — wektory z roznych modeli nie zyja w jednej przestrzeni).

ALTER TABLE thoughts  ALTER COLUMN embedding          TYPE VECTOR(1024);
ALTER TABLE query_log ALTER COLUMN question_embedding TYPE VECTOR(1024);
