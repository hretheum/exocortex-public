# Lessons Learned

## Wiki Compiler Refactor 2026 (F31.6)

### What we gained
- wiki_compiler.py: 8066 → 429 lines (−95%). Each domain lives in its own module.
- Layering rule: `util/*` → `core/*` → `domains/*` — zero circular imports.
- F11.4 invariant (`[x]`/✅ checkbox) extracted into `wiki/core/user_state.py` as a public API with a docstring.
- Easier onboarding: a new domain = a new file in `wiki/domains/`, `setup(registry)` + `_LegacyDomainCompiler`.

### What it cost
- ~16h across 5 batches of domain extraction (iterative work, 1 commit per domain).
- Globals (`DRY_RUN`, `current_run_id`, `_pages_written`) had to stay in wiki_compiler.py, accessed as `_wc.*` through a lazy import — RunContext migration is an F31.6.x followup.
- The top-level import of `exocortex.wiki.core.edges` in the news module pulls in DB/settings at import time — WARNING (pre-existing pattern).

### Pattern to reuse
1. **Byte-invariant baseline before the refactor** — an MD5 snapshot of all wiki files + an idempotency test gate every commit.
2. **Thin wrapper → full implementation** — each domain starts as a `_LegacyDomainCompiler` stub, then the real code is swapped in; tests pass at both steps.
3. **Lazy import for globals** — `import exocortex.wiki_compiler as _wc` inside functions, never at the top level of a domain.

---

## Wiki Compiler audit after the refactor (F31.6.4–F31.6.6, 2026-05-24)

After F31.6.3 was finished, we ran a full code audit — 3 agents (arch, quality, defense) reviewing in parallel. Key findings:

### Main problems found by the audit

**Critical (data loss / security):**
- `clippings.py` used `file_path.write_text()` directly — every `compile_all` overwrote files without preserving user notes. Fix: `_write_with_frontmatter`.
- `news/_top_cited_for_topic`: `topic_slug` interpolated into the query without sanitization. Fix: whitelist regex or a parameterized query.
- `frp/__init__.py`: `_safe_slug(pk) or pk` — an empty sanitization result fell back to the raw value from the DB. Fix: raise ValueError.

**Invariant breach (F11.4 — [x] checkboxes):**
- `work/__init__.py`: an `OSError` while reading an existing file led to a silent `None` and loss of the `[x]` state. No log, no alert. Fix: log.warning + runtime alert.

**Architecture:**
- `core/io.py` imports `wiki_compiler.py` (the facade) cyclically through the lazy `_wc` import — a violation of the layering rule. Fix: RunContext dataclass (F31.6.5.1).
- The synthesis renderers (`_render_synthesis_banner` etc.) were "private" to the `work` domain, but news + frp used them through the facade. Fix: `synthesis_render.py` as a shared module.
- `compile_all` duplicated: a hardcoded list in wiki_compiler.py + a registry-based one in runner.py.

**Code quality:**
- 19/21 files in `wiki/` fail `ruff format --check` — this will block CI once the rule is added.
- O(N²): `set(rel_sids)` computed on every iteration of a list comprehension in work:1939.
- `_obsidian_advanced_uri` copied 1:1 between frp and work.

### Lesson: a post-refactor audit is mandatory, not optional

A large refactor (−95% LOC) exposes pre-existing bugs that were hidden in the monolith. **Workflow:**
1. Refactor with a byte-invariant baseline ✅
2. Full post-audit (arch + quality + security) ✅
3. BLOCKER fixes as separate tickets BEFORE feature work (F31.6.4)
4. Architectural debt as a followup (F31.6.5 RunContext)
5. CI hygiene (F31.6.6 ruff)
