-- zadanie-6-stanowisko-ekstrakcji.md, M5 — budzet tokenow jako dana per
-- konfiguracja, nie stala zaszyta w kodzie rigu.
--
-- Powod: max_tokens=2048 (ekstrakcja) / 256 (sedzia) byly przeniesione bez
-- zmian z scripts/extract_claims.py, dostrojone pod lokalny qwen3.6. Test
-- M5 na gemini-3.6-flash pokazal `finish_reason=length` (odpowiedz ucieta
-- PRZED wyemitowaniem wywolania narzedzia) nawet na 314-znakowym dokumencie
-- - prawdopodobny narzut tokenow "myslenia" u modeli zdalnych. Zostawienie
-- wspolnego budzetu ukaralaby te modele nieuczciwie (ucinanie, nie jakosc
-- ekstrakcji, decydowaloby o wyniku). Domyslne wartosci ponizej = dokladnie
-- to, co bylo zaszyte na stale wczesniej - zero zmiany zachowania dla juz
-- zaladowanych konfiguracji lokalnych.

ALTER TABLE bench_configs
    ADD COLUMN IF NOT EXISTS max_tokens_extract INT NOT NULL DEFAULT 2048,
    ADD COLUMN IF NOT EXISTS max_tokens_judge   INT NOT NULL DEFAULT 256;
