# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Unit tests for exocortex/processors/recipe.py::_resolve_title.

Regression: a mass reprocessing run on 2026-08-02 wiped the title of 66 of
283 recipes. The LLM extraction path re-derived `title` on every run and
`title` was not a required field in TOOL_SCHEMA, so a run that returned no
title overwrote the good stored one with '(untitled recipe)'. All 66 then
compiled to the same filename, overwriting each other — 65 recipes ended up
with no wiki page at all.

Two defences, both covered here:
  1. A stored non-placeholder title wins over a fresh LLM guess, so
     reprocessing can no longer lose or drift a title.
  2. The source note's filename is a deterministic fallback ahead of the
     placeholder — for these notes the filename IS the title (they carry no
     `title:` frontmatter), which is exactly what the 66 were repaired from.
Explicit titles still win, so renaming a note in the vault still propagates.
"""
from __future__ import annotations

from exocortex.processors.recipe import _resolve_title


def _call(**kw):
    base = dict(source_title=None, fm_title=None, existing_title=None,
                llm_title=None, vault_path=None)
    return _resolve_title(**{**base, **kw})


def test_stored_title_wins_over_llm_guess():
    """The incident: reprocessing must not let a fresh LLM guess replace a
    title we already have."""
    assert _call(existing_title='Łosoś z fetą i pistacjami',
                 llm_title='Salmon with feta') == 'Łosoś z fetą i pistacjami'


def test_stored_placeholder_does_not_block_a_real_llm_title():
    assert _call(existing_title='(untitled recipe)',
                 llm_title='Kluski śląskie carbonara') == 'Kluski śląskie carbonara'


def test_explicit_source_title_wins_over_stored():
    """A rename in the vault must still propagate."""
    assert _call(source_title='Nowa nazwa', existing_title='Stara nazwa',
                 llm_title='LLM guess') == 'Nowa nazwa'


def test_frontmatter_title_wins_over_stored():
    assert _call(fm_title='Z frontmattera', existing_title='Stara') == 'Z frontmattera'


def test_vault_filename_used_when_llm_returns_nothing():
    """Exactly the 66-recipe failure: no explicit title, no stored title,
    LLM returned none — the filename is the title for these notes."""
    assert _call(vault_path='_source/prv/kukbuk/Łosoś z fetą i pistacjami.md') == (
        'Łosoś z fetą i pistacjami'
    )


def test_llm_title_wins_over_vault_filename():
    assert _call(llm_title='Prawdziwy tytuł',
                 vault_path='_source/prv/kukbuk/Untitled.md') == 'Prawdziwy tytuł'


def test_placeholder_only_as_last_resort():
    assert _call() == '(untitled recipe)'


def test_blank_values_are_ignored():
    assert _call(source_title='  ', fm_title='', llm_title='Realny') == 'Realny'


def test_title_is_required_in_tool_schema():
    """Cheap complement to the fallback chain — make the model actually try."""
    from exocortex.processors.recipe import TOOL_SCHEMA
    assert 'title' in TOOL_SCHEMA['input_schema']['required']


# ── Wiring: _resolve_title is only useful if normalize() actually feeds it ──
# the stored title. These cover the incident end-to-end, not just the helper.

def _run_normalize(*, stored, fm, tool_title, mp):
    """Drive normalize() with the DB/LLM boundaries stubbed, return the
    metadata handed to emit_thought_for_source."""
    from exocortex.processors import recipe as r

    captured = {}

    def _emit(**kw):
        captured.update(kw)
        return 'tid-1'

    source = {
        'id': 'src-1',
        'uri': 'https://example.com/x',
        'title': None,
        'metadata': {
            'frontmatter': fm,
            'raw_payload': 'Instagram caption long enough to pass the guard. ' * 3,
            'vault_path': '_source/prv/kukbuk/Nazwa z pliku.md',
        },
    }
    mp.setattr(r, 'already_processed', lambda *a, **k: False)
    mp.setattr(r, 'fetch_source', lambda *a, **k: source)
    mp.setattr(r, '_existing_title', lambda *a, **k: stored)
    mp.setattr(r, '_existing_images', lambda *a, **k: [])
    mp.setattr(r, '_archive_source_images', lambda *a, **k: [])
    mp.setattr(r, 'emit_thought_for_source', _emit)
    mp.setattr(r, 'mark_processed', lambda *a, **k: None)
    mp.setattr(r, 'estimate_cost_usd', lambda *a, **k: 0.0)
    mp.setattr(r, '_upsert_entity', lambda *a, **k: 'ent-1')
    mp.setattr(r, '_insert_edge', lambda *a, **k: None)

    class _Conn:
        def __enter__(self): return object()
        def __exit__(self, *a): return False
    mp.setattr(r, 'conn', lambda *a, **k: _Conn())
    mp.setattr(r, 'call_tool', lambda *a, **k: (
        {'title': tool_title, 'ingredients': [{'name': 'sól'}], 'steps': ['wymieszaj']},
        {},
    ))

    r.normalize('src-1', force=True)
    return captured['metadata']


def test_normalize_llm_path_keeps_stored_title(monkeypatch):
    """The incident path: reprocessing must not let the LLM overwrite a
    title we already have."""
    md = _run_normalize(stored='Łosoś z fetą i pistacjami', fm={},
                        tool_title='Salmon with feta', mp=monkeypatch)
    assert md['title'] == 'Łosoś z fetą i pistacjami'


def test_normalize_llm_path_falls_back_to_filename(monkeypatch):
    """No stored title and the LLM returned none — the source filename is
    the title for these notes, never the placeholder."""
    md = _run_normalize(stored=None, fm={}, tool_title=None, mp=monkeypatch)
    assert md['title'] == 'Nazwa z pliku'


def test_normalize_frontmatter_path_keeps_stored_title(monkeypatch):
    """Deterministic path is wired to the same resolver."""
    md = _run_normalize(
        stored='Zapisany tytuł',
        fm={'ingredients': ['1 g sól'], 'steps': ['wymieszaj']},
        tool_title=None, mp=monkeypatch)
    assert md['title'] == 'Zapisany tytuł'


# ── Archived images ────────────────────────────────────────────────────────
# Recipe photos are signed Instagram URLs that die in 4-5 days, so they are
# downloaded once at ingest. The rule that matters: a later reprocessing, when
# those URLs are already dead, must NOT drop the images we already have —
# same failure shape as the title loss this file's other tests cover.

def _run_with_images(*, stored_images, archived, mp, tool_title='Danie'):
    from exocortex.processors import recipe as r

    captured = {}
    source = {
        'id': 'src-1', 'uri': 'https://example.com/x', 'title': None,
        'metadata': {
            'frontmatter': {},
            'raw_payload': '![](https://cdn.example.com/a.jpg)\n' + 'x' * 80,
            'vault_path': '_source/prv/kukbuk/Danie.md',
        },
    }
    mp.setattr(r, 'already_processed', lambda *a, **k: False)
    mp.setattr(r, 'fetch_source', lambda *a, **k: source)
    mp.setattr(r, '_existing_title', lambda *a, **k: None)
    mp.setattr(r, '_existing_images', lambda *a, **k: stored_images)
    mp.setattr(r, 'emit_thought_for_source',
               lambda **kw: (captured.update(kw), 'tid-1')[1])
    mp.setattr(r, 'mark_processed', lambda *a, **k: None)
    mp.setattr(r, 'estimate_cost_usd', lambda *a, **k: 0.0)
    mp.setattr(r, '_upsert_entity', lambda *a, **k: 'e')
    mp.setattr(r, '_insert_edge', lambda *a, **k: None)
    mp.setattr(r, '_archive_source_images', lambda *a, **k: archived)

    class _Conn:
        def __enter__(self): return object()
        def __exit__(self, *a): return False
    mp.setattr(r, 'conn', lambda *a, **k: _Conn())
    mp.setattr(r, 'call_tool', lambda *a, **k: (
        {'title': tool_title, 'ingredients': [{'name': 'sol'}], 'steps': ['mieszaj']}, {}))

    r.normalize('src-1', force=True)
    return captured


def test_downloaded_image_lands_in_metadata_and_body(monkeypatch):
    cap = _run_with_images(stored_images=[], archived=['abc123.jpg'], mp=monkeypatch)
    assert cap['metadata']['images'] == ['abc123.jpg']
    assert '![[abc123.jpg]]' in cap['body'], 'the wiki page must show the photo'


def test_reprocessing_keeps_images_when_urls_are_dead(monkeypatch):
    """The signature expired, so nothing downloads — the already-archived
    photo must survive rather than be overwritten with an empty list."""
    cap = _run_with_images(stored_images=['stare.jpg'], archived=[], mp=monkeypatch)
    assert cap['metadata']['images'] == ['stare.jpg']
    assert '![[stare.jpg]]' in cap['body']


def test_no_images_anywhere_leaves_body_clean(monkeypatch):
    cap = _run_with_images(stored_images=[], archived=[], mp=monkeypatch)
    assert cap['metadata']['images'] == []
    assert '![[' not in cap['body']
