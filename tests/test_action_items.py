# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# tests/test_action_items.py — fixtures derived from real Fireflies output.

from __future__ import annotations

from exocortex.action_items import ActionItem, parse_action_items


def _by_owner(items: list[ActionItem], slug: str) -> list[ActionItem]:
    return [it for it in items if it.owner_slug == slug]


def test_empty_inputs_return_empty_list():
    assert parse_action_items(None) == []
    assert parse_action_items({}) == []
    assert parse_action_items({'action_items': None}) == []
    assert parse_action_items({'action_items': ''}) == []
    assert parse_action_items('') == []


def test_open_item_with_due_date_and_tags():
    raw = (
        "### Marek Borowski\n\n"
        "- [ ] #initech #presales Ustalić termin spotkania z Igorem (38:48) ➕ 2026-02-02\n"
    )
    items = parse_action_items({'action_items': raw}, source_thought_id='abc-1')
    assert len(items) == 1
    it = items[0]
    assert it.owner_slug == 'pilaszek-maciej' or it.owner_slug == 'maciej-pilaszek'
    # We standardise on first-last ordering as written in the header.
    assert it.owner_slug == 'maciej-pilaszek'
    assert it.owner_name == 'Marek Borowski'
    assert it.owner_is_collective is False
    assert it.status == 'open'
    assert it.timestamp_in_meeting == '38:48'
    assert it.due_date == '2026-02-02'
    assert it.completion_date is None
    assert set(it.inline_tags) == {'initech', 'presales'}
    assert 'Ustalić termin spotkania z Igorem' in it.content
    assert '#initech' not in it.content and '➕' not in it.content
    assert it.source_thought_id == 'abc-1'


def test_done_item_with_completion_date():
    raw = (
        "### Exocortex user\n\n"
        "- [x] Przygotować wariantowe propozycje gry (26:01) ✅ 2026-02-25\n"
    )
    items = parse_action_items({'action_items': raw})
    assert len(items) == 1
    it = items[0]
    assert it.status == 'done'
    assert it.owner_slug == 'vault-owner'
    assert it.completion_date == '2026-02-25'
    assert it.due_date is None
    assert it.timestamp_in_meeting == '26:01'
    assert it.content.startswith('Przygotować wariantowe')


def test_polish_diacritics_in_slug():
    raw = (
        "### Ewa Mazurek-Kos\n\n"
        "- [ ] Coś tam (00:01)\n"
        "### Karol Wróbel\n\n"
        "- [ ] Inne coś (00:02)\n"
    )
    items = parse_action_items({'action_items': raw})
    slugs = sorted({it.owner_slug for it in items})
    assert slugs == ['lukasz-gluch', 'paulina-trofimiak-gladkowska']


def test_collective_wszyscy_uczestnicy():
    raw = (
        "### Wszyscy uczestnicy\n\n"
        "- [ ] #acme #presales Zapoznanie się z dokumentem (12:51) ➕ 2026-02-17\n"
        "### Cały zespół\n\n"
        "- [ ] Coś dla zespołu (00:30)\n"
        "### Zespół Omniportal\n\n"
        "- [ ] Konkretne dla projektu (01:00)\n"
        "### Nieprzypisane / do rozstrzygnięcia\n\n"
        "- [ ] Open question (02:00)\n"
    )
    items = parse_action_items({'action_items': raw})
    assert len(items) == 4
    assert all(it.owner_slug == '_collective' for it in items)
    assert all(it.owner_is_collective for it in items)
    names = {it.owner_name for it in items}
    assert 'Wszyscy uczestnicy' in names
    assert 'Cały zespół' in names
    assert 'Zespół Omniportal' in names
    assert any('Nieprzypisane' in n for n in names)


def test_multi_name_owner_splits_into_individuals():
    raw = (
        "### Adam Nowicki i Exocortex user\n\n"
        "- [x] Udostępnić licencję (23:04) ✅ 2026-02-25\n"
    )
    items = parse_action_items({'action_items': raw})
    assert len(items) == 2
    slugs = sorted(it.owner_slug for it in items)
    assert slugs == ['vault-owner', 'adam-nowicki']
    assert all(it.status == 'done' for it in items)
    assert all(it.completion_date == '2026-02-25' for it in items)
    assert all(it.owner_is_collective is False for it in items)


def test_item_without_timestamp():
    raw = (
        "### Anna Nowak\n\n"
        "- [ ] Potwierdzić skład osób uczestniczących w spotkaniu\n"
    )
    items = parse_action_items({'action_items': raw})
    assert len(items) == 1
    assert items[0].timestamp_in_meeting is None
    assert items[0].status == 'open'
    assert items[0].content.startswith('Potwierdzić skład')


def test_hh_mm_ss_timestamp():
    raw = (
        "### Exocortex user\n\n"
        "- [ ] Długie spotkanie (01:07:32)\n"
    )
    items = parse_action_items({'action_items': raw})
    assert items[0].timestamp_in_meeting == '01:07:32'


def test_priority_emoji_stripped():
    raw = (
        "### Dymitr Saganowski\n\n"
        "- [ ] #umbrella #presales Przygotować wycenę (14:30) 🔼 ➕ 2026-02-09\n"
    )
    items = parse_action_items({'action_items': raw})
    assert len(items) == 1
    it = items[0]
    assert '🔼' not in it.content
    assert it.due_date == '2026-02-09'
    assert it.timestamp_in_meeting == '14:30'
    assert set(it.inline_tags) == {'umbrella', 'presales'}


def test_mixed_open_done_in_one_meeting():
    raw = (
        "### Exocortex user\n\n"
        "- [x] Pierwsze (10:00) ✅ 2026-02-25\n"
        "- [ ] Drugie #urgent (20:00) ➕ 2026-03-01\n"
        "### Marek Borowski\n\n"
        "- [ ] Trzecie (30:00)\n"
    )
    items = parse_action_items({'action_items': raw})
    assert len(items) == 3
    eryk_items = _by_owner(items, 'vault-owner')
    assert len(eryk_items) == 2
    statuses = sorted(it.status for it in eryk_items)
    assert statuses == ['done', 'open']
    open_eryk = [it for it in eryk_items if it.status == 'open'][0]
    assert open_eryk.inline_tags == ['urgent']
    assert open_eryk.due_date == '2026-03-01'


def test_source_thought_id_from_metadata_meeting_id():
    raw = "### Exocortex user\n\n- [ ] Coś (10:00)\n"
    items = parse_action_items({'action_items': raw, 'meeting_id': 'mtg-xyz'})
    assert items[0].source_thought_id == 'mtg-xyz'

    items_override = parse_action_items(
        {'action_items': raw, 'meeting_id': 'mtg-xyz'},
        source_thought_id='override-id',
    )
    assert items_override[0].source_thought_id == 'override-id'


def test_raw_string_input_supported():
    raw = "### Exocortex user\n\n- [ ] Coś (10:00)\n"
    items = parse_action_items(raw, source_thought_id='id-1')
    assert len(items) == 1
    assert items[0].source_thought_id == 'id-1'


def test_malformed_lines_are_skipped():
    raw = (
        "### Exocortex user\n\n"
        "- [ ] Valid item (10:00)\n"
        "- [ ]\n"  # empty after checkbox -> skipped
        "Random prose without bullet -- ignored\n"
        "- [?] not a checkbox -- ignored\n"
        "- [ ] Another valid (20:00)\n"
    )
    items = parse_action_items({'action_items': raw})
    assert len(items) == 2
    assert items[0].content.startswith('Valid')
    assert items[1].content.startswith('Another')


def test_no_header_returns_empty():
    raw = "- [ ] Bez nagłówka (10:00)\n"
    assert parse_action_items({'action_items': raw}) == []


def test_to_dict_serialisable():
    raw = "### Exocortex user\n\n- [ ] Item (10:00)\n"
    items = parse_action_items({'action_items': raw})
    d = items[0].to_dict()
    assert d['owner_slug'] == 'vault-owner'
    assert d['status'] == 'open'
    assert isinstance(d['inline_tags'], list)
