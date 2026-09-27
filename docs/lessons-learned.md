# Lessons Learned

## Wiki Compiler Refactor 2026 (F31.6)

### Co zyskano
- wiki_compiler.py: 8066 → 429 linii (−95%). Każda domena w osobnym module.
- Layering rule: `util/*` → `core/*` → `domains/*` — zero circular imports.
- F11.4 invariant (`[x]`/✅ checkbox) wydzielony do `wiki/core/user_state.py` jako public API z docstringiem.
- Łatwiejszy onboarding: nowa domena = nowy plik w `wiki/domains/`, `setup(registry)` + `_LegacyDomainCompiler`.

### Co kosztowało
- ~16h na 5 batchy domain extraction (praca iteracyjna, 1 commit/domenę).
- Globals (`DRY_RUN`, `current_run_id`, `_pages_written`) musiały pozostać w wiki_compiler.py jako `_wc.*` dostęp przez lazy import — RunContext migration to F31.6.x followup.
- Top-level import `exocortex.wiki.core.edges` w news module ciągnie DB/settings at import time — WARNING (pre-existing pattern).

### Wzorzec do reużycia
1. **Byte-invariant baseline przed refaktorem** — snapshot MD5 wszystkich plików wiki + idempotency test = gating każdego commitu.
2. **Thin wrapper → full implementation** — każde domain zaczyna od `_LegacyDomainCompiler` stub, potem swap in real code, testy przechodzą oba kroki.
3. **Lazy import dla globals** — `import exocortex.wiki_compiler as _wc` wewnątrz funkcji, nigdy na top-level domeny.

---

## Audit Wiki Compilera po refaktorze (F31.6.4–F31.6.6, 2026-05-24)

Po ukończeniu F31.6.3 przeprowadzono kompleksowy audyt kodu — 3 agenty (arch, quality, defense) w równoległym przeglądzie. Kluczowe wnioski:

### Główne problemy wykryte przez audyt

**Krytyczne (data loss / security):**
- `clippings.py` używał `file_path.write_text()` bezpośrednio — każdy `compile_all` nadpisywał pliki bez zachowania notatek użytkownika. Fix: `_write_with_frontmatter`.
- `news/_top_cited_for_topic`: `topic_slug` interpolowany do zapytania bez sanityzacji. Fix: whitelist regex lub parametryzowane zapytanie.
- `frp/__init__.py`: `_safe_slug(pk) or pk` — pusty wynik sanityzacji fallback do surowej wartości z DB. Fix: raise ValueError.

**Invariant breach (F11.4 — [x] checkboxes):**
- `work/__init__.py`: `OSError` przy odczycie istniejącego pliku prowadził do silent `None` i utraty stanu `[x]`. Brak logu, brak alertu. Fix: log.warning + runtime alert.

**Architektura:**
- `core/io.py` cyklicznie importuje `wiki_compiler.py` (fasada) przez lazy `_wc` import — naruszenie layering rule. Fix: RunContext dataclass (F31.6.5.1).
- Renderery syntezy (`_render_synthesis_banner` itp.) były "prywatne" w domenie `work`, ale news + frp używały ich przez fasadę. Fix: `synthesis_render.py` jako shared module.
- `compile_all` zduplikowany: hardcoded list w wiki_compiler.py + registry-based w runner.py.

**Jakość kodu:**
- 19/21 plików `wiki/` nie przechodzi `ruff format --check` — zablokuje CI po dodaniu reguły.
- O(N²): `set(rel_sids)` obliczany przy każdej iteracji list comprehension w work:1939.
- `_obsidian_advanced_uri` skopiowana 1:1 między frp a work.

### Lekcja: audyt post-refactor to obowiązek, nie opcja

Duży refaktor (−95% LOC) ujawnia preexisting bugs które były ukryte w monoliście. **Workflow:**
1. Refaktor z byte-invariant baseline ✅
2. Komprehensywny post-audit (arch + quality + security) ✅
3. BLOCKER fixes jako osobne tickety PRZED feature work (F31.6.4)
4. Architectural debt jako followup (F31.6.5 RunContext)
5. CI hygiene (F31.6.6 ruff)
