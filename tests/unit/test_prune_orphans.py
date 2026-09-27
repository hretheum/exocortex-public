# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Unit tests for orphan pruning in exocortex/wiki/domains/clippings.py.

Background: the wiki compiler writes one file per thought, named after the
slug of its title, and never deleted anything — `prune_orphans` was a `pass`
stub in every domain and `runner.compile_all` never called it. So every title
change left the old file behind forever. A 2026-08-02 incident (66 recipes
lost their titles) plus a 2026-08-03 slug fix (Polish diacritics) left 95
stale files across cook/recipes and work/meetings/src, which had to be swept
by hand.

The decision logic is kept pure and tested exhaustively here because this is
the only part of the compiler that DELETES user-visible files. Two invariants
matter most:
  - never delete a file unless its replacement is already on disk, so a
    thought can never end up with no page at all;
  - refuse to run at all if the deletion looks implausibly large, so a bad
    query can't wipe a directory.
"""
from __future__ import annotations

import pytest

from exocortex.wiki.domains.clippings import _select_orphans, _prune_is_plausible


# ── _select_orphans ────────────────────────────────────────────────────────

def test_renamed_thought_leaves_old_file_as_orphan():
    files = {'stary-tytul.md': 'tid-1', 'nowy-tytul.md': 'tid-1'}
    expected = {'tid-1': 'nowy-tytul.md'}
    assert _select_orphans(files, expected) == ['stary-tytul.md']


def test_keeps_file_when_replacement_not_yet_written():
    """Incremental compile may not have rewritten this thought yet — deleting
    now would leave it with no page at all."""
    files = {'stary-tytul.md': 'tid-1'}
    expected = {'tid-1': 'nowy-tytul.md'}
    assert _select_orphans(files, expected) == []


def test_file_for_vanished_thought_is_orphan():
    files = {'usuniety.md': 'tid-gone', 'zywy.md': 'tid-1'}
    expected = {'tid-1': 'zywy.md'}
    assert _select_orphans(files, expected) == ['usuniety.md']


def test_correctly_named_files_are_kept():
    files = {'a.md': 'tid-1', 'b.md': 'tid-2'}
    expected = {'tid-1': 'a.md', 'tid-2': 'b.md'}
    assert _select_orphans(files, expected) == []


def test_collision_keeps_the_expected_name_only():
    """Two thoughts, one stale name — the file matching its own thought's
    expected name survives."""
    files = {'wspolna.md': 'tid-1', 'wlasna.md': 'tid-2'}
    expected = {'tid-1': 'wlasna.md', 'tid-2': 'wlasna.md'}
    # tid-1's file is named 'wspolna.md' but should be 'wlasna.md', which exists
    assert _select_orphans(files, expected) == ['wspolna.md']


def test_empty_inputs():
    assert _select_orphans({}, {}) == []


# ── _prune_is_plausible (circuit breaker) ──────────────────────────────────

def test_small_absolute_deletion_always_allowed():
    """A tiny directory where most files are stale must not be blocked."""
    assert _prune_is_plausible(n_delete=2, n_total=3) is True


def test_large_proportion_is_refused():
    assert _prune_is_plausible(n_delete=60, n_total=100) is False


def test_realistic_sweep_is_allowed():
    """The actual 2026-08-03 cleanup: 93 stale of 357 keyed files."""
    assert _prune_is_plausible(n_delete=93, n_total=357) is True


def test_deleting_everything_is_refused():
    assert _prune_is_plausible(n_delete=100, n_total=100) is False


def test_nothing_to_do_is_allowed():
    assert _prune_is_plausible(n_delete=0, n_total=0) is True


# ── contract: prune_orphans returns an int and is safe without a DB ────────

@pytest.mark.parametrize('domain_cls_name', [
    'CookDomain', 'ThreeDDomain', 'PrivDomain', 'PapersDomain',
])
def test_prune_orphans_returns_int_without_db(domain_cls_name, tmp_path, monkeypatch):
    """Called against a wiki root with no such directory it must return 0,
    without reaching for the database."""
    import exocortex.wiki.domains.clippings as cl
    from exocortex.wiki.core.context import RunContext

    # patched where it is defined — _prune_clipping_orphans imports it locally
    monkeypatch.setattr('exocortex.wiki.core.io._get_wiki_root', lambda: tmp_path)

    def _boom(*a, **k):
        raise AssertionError('prune_orphans must not query the DB when the '
                             'target directory does not exist')
    monkeypatch.setattr('exocortex.db.query', _boom)

    compiler = getattr(cl, domain_cls_name)()
    assert compiler.prune_orphans(RunContext(tenant_id='t')) == 0


# ── The delete path itself, on real files ─────────────────────────────────
# The pure logic above decides WHAT to delete; these cover the code that
# actually reads frontmatter, globs the directory and unlinks.

def _setup_cook(tmp_path, monkeypatch, files, db_rows, *, dry_run=False):
    """Lay out wiki/cook/recipes/*.md and stub the DB behind it."""
    from exocortex.wiki.core import _state as _wc
    recipes = tmp_path / 'cook' / 'recipes'
    recipes.mkdir(parents=True)
    for name, tid in files.items():
        (recipes / name).write_text(
            f'---\ntype: recipe\ntitle: X\n_thought_id: {tid}\n---\n\nbody\n',
            encoding='utf-8')
    monkeypatch.setattr('exocortex.wiki.core.io._get_wiki_root', lambda: tmp_path)
    monkeypatch.setattr('exocortex.db.query', lambda *a, **k: db_rows)
    monkeypatch.setattr(_wc, 'DRY_RUN', dry_run)
    return recipes


def _row(tid, title):
    return {'id': tid, 'metadata': {'title': title}, 'thought_type': 'recipe'}


def test_delete_path_removes_renamed_file_keeps_current(tmp_path, monkeypatch):
    import exocortex.wiki.domains.clippings as cl
    from exocortex.wiki.core.context import RunContext

    recipes = _setup_cook(
        tmp_path, monkeypatch,
        files={'par-wki-z-serem.md': 'tid-1', 'parowki-z-serem.md': 'tid-1'},
        db_rows=[_row('tid-1', 'Parowki z serem')])

    n = cl.CookDomain().prune_orphans(RunContext(tenant_id='t'))

    assert n == 1
    left = {f.name for f in recipes.glob('*.md')}
    assert left == {'parowki-z-serem.md'}


def test_delete_path_never_touches_files_without_thought_id(tmp_path, monkeypatch):
    """MOC/index pages carry no _thought_id and must survive untouched."""
    import exocortex.wiki.domains.clippings as cl
    from exocortex.wiki.core.context import RunContext

    recipes = _setup_cook(tmp_path, monkeypatch, files={'zywy.md': 'tid-1'},
                          db_rows=[_row('tid-1', 'Zywy')])
    (recipes / '_moc.md').write_text('---\ntype: moc\n---\n', encoding='utf-8')

    n = cl.CookDomain().prune_orphans(RunContext(tenant_id='t'))

    assert n == 0
    assert (recipes / '_moc.md').exists()


def test_dry_run_reports_but_deletes_nothing(tmp_path, monkeypatch):
    import exocortex.wiki.domains.clippings as cl
    from exocortex.wiki.core.context import RunContext

    recipes = _setup_cook(
        tmp_path, monkeypatch,
        files={'stary.md': 'tid-1', 'nowy.md': 'tid-1'},
        db_rows=[_row('tid-1', 'Nowy')], dry_run=True)

    n = cl.CookDomain().prune_orphans(RunContext(tenant_id='t'))

    assert n == 1
    assert len(list(recipes.glob('*.md'))) == 2, 'dry run must not delete'


def test_circuit_breaker_refuses_implausible_sweep(tmp_path, monkeypatch):
    """An empty/bad DB result would orphan every page — refuse, delete none."""
    import exocortex.wiki.domains.clippings as cl
    from exocortex.wiki.core.context import RunContext

    files = {f'r{i}.md': f'tid-{i}' for i in range(30)}
    recipes = _setup_cook(tmp_path, monkeypatch, files=files, db_rows=[])

    n = cl.CookDomain().prune_orphans(RunContext(tenant_id='t'))

    assert n == 0
    assert len(list(recipes.glob('*.md'))) == 30, 'nothing may be deleted'


def test_legacy_compile_path_prunes(tmp_path, monkeypatch):
    """Regression: pruning was first wired only into wiki.runner.compile_all,
    but every deployed unit runs the OTHER dispatcher
    (wiki_compiler.compile_all -> compile_cook_module), so it never ran in
    production. Both dispatchers converge on _compile_clippings_module, so
    the prune must fire from there."""
    import exocortex.wiki.domains.clippings as cl
    from exocortex.wiki.core import _state as _wc

    recipes = tmp_path / 'cook' / 'recipes'
    recipes.mkdir(parents=True)
    for name in ('stary.md', 'nowy.md'):
        (recipes / name).write_text(
            '---\ntype: recipe\ntitle: X\n_thought_id: tid-1\n---\n\nbody\n',
            encoding='utf-8')

    row = {'id': 'tid-1', 'body': 'b', 'thought_type': 'recipe',
           'metadata': {'title': 'Nowy', 'domain': 'cook'},
           'extracted_tags': {}, 'source_id': 'sid-1', 'created_at': None}
    monkeypatch.setattr('exocortex.wiki.core.io._get_wiki_root', lambda: tmp_path)
    monkeypatch.setattr('exocortex.db.query', lambda *a, **k: [row])
    monkeypatch.setattr(_wc, 'DRY_RUN', False)
    monkeypatch.setattr(cl, '_write_clipping_page', lambda *a, **k: 0)
    monkeypatch.setattr(cl, '_write_clippings_moc', lambda *a, **k: None)

    cl.compile_cook_module('t', None)

    assert {f.name for f in recipes.glob('*.md')} == {'nowy.md'}


def test_dry_run_flag_is_read_from_shared_state(tmp_path, monkeypatch):
    """Regression: DRY_RUN was read via `import exocortex.wiki_compiler`, but
    every deployed unit runs `python -m exocortex.wiki_compiler`, so that
    module is __main__ and the plain import binds a SECOND copy whose DRY_RUN
    stays False. A --dry-run compile therefore really deleted files. The
    shared core._state module is the one both sides agree on."""
    import exocortex.wiki.domains.clippings as cl
    import exocortex.wiki_compiler as stale_copy
    from exocortex.wiki.core import _state
    from exocortex.wiki.core.context import RunContext

    recipes = tmp_path / 'cook' / 'recipes'
    recipes.mkdir(parents=True)
    for name in ('stary.md', 'nowy.md'):
        (recipes / name).write_text(
            '---\ntype: recipe\ntitle: X\n_thought_id: tid-1\n---\n\nbody\n',
            encoding='utf-8')
    monkeypatch.setattr('exocortex.wiki.core.io._get_wiki_root', lambda: tmp_path)
    monkeypatch.setattr('exocortex.db.query', lambda *a, **k: [_row('tid-1', 'Nowy')])
    # shared state says dry run; the other copy says otherwise — state must win
    monkeypatch.setattr(_state, 'DRY_RUN', True)
    monkeypatch.setattr(stale_copy, 'DRY_RUN', False)

    cl.CookDomain().prune_orphans(RunContext(tenant_id='t'))

    assert len(list(recipes.glob('*.md'))) == 2, '--dry-run must not delete'
