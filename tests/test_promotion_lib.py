# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# tests/test_promotion_lib.py — F15-R.2 deterministic promotion logic.

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from exocortex.promotion_lib import (
    compute_fingerprint,
    create_promotion_stubs,
    delete_promotion_stubs,
    list_promotion_stubs,
    normalize_action_text,
    slugify,
)

# ── Fixtures ──────────────────────────────────────────────────────────────


def _seed_meeting(vault: Path, slug: str, lines: list[str]) -> Path:
    meetings_dir = vault / 'wiki' / 'work' / 'meetings'
    meetings_dir.mkdir(parents=True, exist_ok=True)
    body_lines = [
        '---',
        f'title: {slug}',
        'date: 2026-02-02',
        '---',
        '',
        '## Action items',
        '',
        '### Exocortex user',
        '',
    ]
    body_lines.extend(lines)
    path = meetings_dir / f'{slug}.md'
    path.write_text('\n'.join(body_lines), encoding='utf-8')
    return path


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    (tmp_path / '_ Second Brain' / 'backlog' / '_second-brain' / 'manual').mkdir(
        parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def meeting_a(vault: Path) -> str:
    slug = '2026-02-02--alpha--abcd1234'
    _seed_meeting(vault, slug, [
        '- [ ] Ustalić zakres MVP do końca tygodnia ➕ 2026-02-02',
        '- [ ] Przygotować estymację dla INITECH Game Q2 (12:34) ➕ 2026-02-02',
        '- [x] Zamknąć stary ticket ✅ 2026-02-15',
    ])
    return slug


@pytest.fixture
def meeting_b(vault: Path) -> str:
    slug = '2026-02-09--beta--ef567890'
    _seed_meeting(vault, slug, [
        '- [ ] Przygotować estymację dla INITECH Game Q2 (08:01) ➕ 2026-02-09',
        '- [ ] Skontaktować się z Igorem o dostępność na demo',
    ])
    return slug


# ── normalize / fingerprint / slugify ─────────────────────────────────────


def test_normalize_strips_date_markers_and_collapses_ws():
    raw = 'Foo bar (12:34) ➕ 2026-02-02 ✅ 2026-02-15'
    assert normalize_action_text(raw) == 'Foo bar (12:34)'


def test_compute_fingerprint_stable_across_date_marker_changes():
    a = compute_fingerprint('m1', 'Foo bar ➕ 2026-02-02')
    b = compute_fingerprint('m1', 'Foo bar ✅ 2026-02-15')
    assert a == b
    # Different meeting → different fingerprint.
    c = compute_fingerprint('m2', 'Foo bar')
    assert a != c


def test_slugify_handles_unicode_and_specials():
    assert slugify('INITECH Game Q2 — Estymacja') == 'initech-game-q2-estymacja'
    assert slugify('  whitespace   only  ') == 'whitespace-only'
    assert slugify('🚀 emoji prefix test') == 'emoji-prefix-test'


# ── create_promotion_stubs ────────────────────────────────────────────────


def test_create_happy_path_makes_parent_and_children(vault, meeting_a):
    res = create_promotion_stubs(
        meeting_slug=meeting_a,
        parent_topic='INITECH Game Q2 estymacja',
        item_descriptions=[
            'Przygotować estymację dla INITECH Game Q2 (12:34)',
        ],
        vault_root=vault,
    )
    assert res['cross_meeting_update'] is False
    assert res['parent_id'] == 'manual-initech-game-q2-estymacja'
    parent_path = Path(res['parent_path'])
    assert parent_path.is_file()
    assert len(res['children_paths']) == 1

    fm = yaml.safe_load(
        parent_path.read_text(encoding='utf-8').split('---', 2)[1])
    assert fm['title'] == 'INITECH Game Q2 estymacja'
    assert fm['children'] == ['initech-game-q2-estymacja-c1']
    assert f'[[{meeting_a}]]' in fm['source_meetings']
    assert fm['status'] == 'pending'
    assert fm['priority'] == 'MED'


def test_create_validates_descriptions_against_meeting(vault, meeting_a):
    with pytest.raises(ValueError, match='not found in meeting'):
        create_promotion_stubs(
            meeting_slug=meeting_a,
            parent_topic='Bogus',
            item_descriptions=['This line never appeared in the meeting'],
            vault_root=vault,
        )


def test_create_rejects_empty_inputs(vault, meeting_a):
    with pytest.raises(ValueError, match='at least one'):
        create_promotion_stubs(
            meeting_slug=meeting_a,
            parent_topic='X',
            item_descriptions=[],
            vault_root=vault,
        )
    with pytest.raises(ValueError, match='priority'):
        create_promotion_stubs(
            meeting_slug=meeting_a,
            parent_topic='X',
            item_descriptions=['Ustalić zakres MVP do końca tygodnia'],
            priority='URGENT',
            vault_root=vault,
        )


def test_cross_meeting_dedupe_appends_source_and_unique_children(
        vault, meeting_a, meeting_b):
    """Same parent_topic across two meetings → one parent, +source_meetings,
    only new fingerprints become new children."""
    create_promotion_stubs(
        meeting_slug=meeting_a, parent_topic='INITECH Game Q2 estymacja',
        item_descriptions=['Przygotować estymację dla INITECH Game Q2 (12:34)'],
        vault_root=vault)
    res = create_promotion_stubs(
        meeting_slug=meeting_b, parent_topic='INITECH Game Q2 estymacja',
        item_descriptions=['Przygotować estymację dla INITECH Game Q2 (08:01)'],
        vault_root=vault)
    assert res['cross_meeting_update'] is True
    assert len(res['children_paths']) == 1   # net-new fingerprint
    parent_text = Path(res['parent_path']).read_text(encoding='utf-8')
    parent_fm = yaml.safe_load(parent_text.split('---', 2)[1])
    assert f'[[{meeting_a}]]' in parent_fm['source_meetings']
    assert f'[[{meeting_b}]]' in parent_fm['source_meetings']
    assert parent_fm['children'] == [
        'initech-game-q2-estymacja-c1', 'initech-game-q2-estymacja-c2']


def test_cross_meeting_repeat_skips_when_fingerprint_exists(vault, meeting_a):
    """Promote same description twice from same meeting → no duplicate."""
    create_promotion_stubs(
        meeting_slug=meeting_a, parent_topic='INITECH estymacja',
        item_descriptions=['Przygotować estymację dla INITECH Game Q2 (12:34)'],
        vault_root=vault)
    res = create_promotion_stubs(
        meeting_slug=meeting_a, parent_topic='INITECH estymacja',
        item_descriptions=['Przygotować estymację dla INITECH Game Q2 (12:34)'],
        vault_root=vault)
    assert res['cross_meeting_update'] is True
    assert res['children_paths'] == []
    assert res['skipped_existing'] == 1


def test_slug_conflict_appends_numeric_suffix(vault, meeting_a):
    """Different parent_topic claiming same base slug ⇒ -2 suffix."""
    create_promotion_stubs(
        meeting_slug=meeting_a, parent_topic='Foo',
        item_descriptions=['Ustalić zakres MVP do końca tygodnia'],
        vault_root=vault)
    res = create_promotion_stubs(
        meeting_slug=meeting_a, parent_topic='Foo',  # same → cross-meeting path
        item_descriptions=['Zamknąć stary ticket'],
        vault_root=vault)
    assert res['cross_meeting_update'] is True

    # Now a *different* parent_topic that slugifies to 'foo' would not happen
    # naturally; we test by hard-feeding suggested_slug='foo' for a new topic.
    res2 = create_promotion_stubs(
        meeting_slug=meeting_a, parent_topic='Different Topic',
        suggested_slug='foo',
        item_descriptions=['Ustalić zakres MVP do końca tygodnia'],
        vault_root=vault)
    assert res2['parent_id'] == 'manual-foo-2'


# ── list / delete ─────────────────────────────────────────────────────────


def test_list_filters_by_meeting_and_parent_only(vault, meeting_a, meeting_b):
    create_promotion_stubs(
        meeting_slug=meeting_a, parent_topic='Topic A',
        item_descriptions=['Ustalić zakres MVP do końca tygodnia'],
        vault_root=vault)
    create_promotion_stubs(
        meeting_slug=meeting_b, parent_topic='Topic B',
        item_descriptions=['Skontaktować się z Igorem o dostępność na demo'],
        vault_root=vault)

    all_stubs = list_promotion_stubs(vault_root=vault)
    assert len(all_stubs) == 4  # 2 parents + 2 children

    parents = list_promotion_stubs(parent_only=True, vault_root=vault)
    assert {s['title'] for s in parents} == {'Topic A', 'Topic B'}

    only_b = list_promotion_stubs(meeting_slug=meeting_b, vault_root=vault)
    assert {s['kind'] for s in only_b} == {'parent', 'child'}
    assert all(f'[[{meeting_b}]]' in s['source_meetings'] for s in only_b)


def test_delete_parent_cascades_to_children(vault, meeting_a):
    res = create_promotion_stubs(
        meeting_slug=meeting_a, parent_topic='Cascade Topic',
        item_descriptions=[
            'Ustalić zakres MVP do końca tygodnia',
            'Przygotować estymację dla INITECH Game Q2 (12:34)',
        ],
        vault_root=vault)
    parent_id = res['parent_id']

    out = delete_promotion_stubs(parent_id, vault_root=vault)
    assert out['kind'] == 'parent'
    assert len(out['deleted_paths']) == 3   # parent + 2 children
    assert list_promotion_stubs(vault_root=vault) == []


def test_delete_child_only_updates_parent(vault, meeting_a):
    res = create_promotion_stubs(
        meeting_slug=meeting_a, parent_topic='Partial Delete',
        item_descriptions=[
            'Ustalić zakres MVP do końca tygodnia',
            'Przygotować estymację dla INITECH Game Q2 (12:34)',
        ],
        vault_root=vault)
    child_id = 'manual-partial-delete-c1'

    out = delete_promotion_stubs(child_id, vault_root=vault)
    assert out['kind'] == 'child'
    assert len(out['deleted_paths']) == 1

    survivors = list_promotion_stubs(vault_root=vault)
    assert len(survivors) == 2  # parent + 1 surviving child
    parent = next(s for s in survivors if s['kind'] == 'parent')
    assert parent['stub_id'] == res['parent_id']

    parent_text = Path(res['parent_path']).read_text(encoding='utf-8')
    parent_fm = yaml.safe_load(parent_text.split('---', 2)[1])
    assert 'partial-delete-c1' not in parent_fm['children']
    assert 'partial-delete-c2' in parent_fm['children']


def test_delete_missing_returns_missing_kind(vault):
    out = delete_promotion_stubs('does-not-exist', vault_root=vault)
    assert out['kind'] == 'missing'
    assert out['deleted_paths'] == []
