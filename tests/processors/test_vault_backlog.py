"""Tests for F33.2 vault_backlog processor."""
from __future__ import annotations
from unittest.mock import patch

from tests.processors._fakedb import FakeConn


def make_source(frontmatter, vault_path='_source/backlog/globex-roadmap/P2-002.md'):
    return {
        'id': 'src-1',
        'metadata': {
            'raw_payload': '---\n...\n---\nbody',
            'frontmatter': frontmatter,
            'vault_path': vault_path,
        },
    }


REAL_SHAPE_FRONTMATTER = {
    'id': 'P2-002',
    'title': 'Multi-DS core v1',
    'description': 'Build the shared core for multiple design systems.',
    'area': '[[globex]]',
    'status': 'done',
    'priority': 'HIGH',
    'phase': 'Q2-26',
    'blockedBy': ['P2-028', 'Q4-P5-multi-ds-core-architecture'],
    'completed': '',
    'estimate_hours': 8,
    'bau_hours': 0,
    'cost_category': 'ds-audit',
}


def _patched(source_row, resolve_map=None):
    resolve_map = resolve_map or {}

    def fake_resolve(ticket_id):
        return resolve_map.get(ticket_id)

    return (
        patch('exocortex.processors.vault_backlog.fetch_source', return_value=source_row),
        patch('exocortex.processors.vault_backlog.already_processed', return_value=False),
        patch('exocortex.processors.vault_backlog.mark_processed'),
        patch('exocortex.processors.vault_backlog.get_embedding', return_value=[0.1, 0.2]),
        patch('exocortex.processors.vault_backlog._upsert_entity', return_value='project-globex'),
        patch('exocortex.processors.vault_backlog._insert_edge', return_value={'id': 'edge-1'}),
        patch('exocortex.processors.vault_backlog._resolve_backlog_id', side_effect=fake_resolve),
    )


def test_process_extracts_structured_fields():
    source = make_source(REAL_SHAPE_FRONTMATTER)
    fake_conn = FakeConn()
    p = _patched(source)
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6], \
         patch('exocortex.processors.vault_backlog.conn', return_value=fake_conn):
        from exocortex.processors.vault_backlog import process
        result = process('src-1')

    assert result['status'] == 'ok'
    assert result['ticket_id'] == 'P2-002'
    assert result['area_edge'] is True
    assert result['blocked_by_found'] == 2
    assert len(fake_conn.inserted) == 1
    inserted_body = next(iter(fake_conn.inserted.values()))['params'][2]
    assert inserted_body == 'Multi-DS core v1\nBuild the shared core for multiple design systems.'


def test_blockedby_unresolved_is_skipped_not_error():
    """Forward references (blocker not ingested yet) must not fail the item."""
    source = make_source(REAL_SHAPE_FRONTMATTER)
    fake_conn = FakeConn()
    p = _patched(source, resolve_map={})  # nothing resolves
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6], \
         patch('exocortex.processors.vault_backlog.conn', return_value=fake_conn):
        from exocortex.processors.vault_backlog import process
        result = process('src-1')

    assert result['status'] == 'ok'
    assert result['blocked_by_found'] == 2
    assert result['blocked_by_resolved'] == 0


def test_blockedby_resolves_when_target_already_processed():
    source = make_source(REAL_SHAPE_FRONTMATTER)
    fake_conn = FakeConn()
    p = _patched(source, resolve_map={'P2-028': 'thought-existing-1'})
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6], \
         patch('exocortex.processors.vault_backlog.conn', return_value=fake_conn):
        from exocortex.processors.vault_backlog import process
        result = process('src-1')

    assert result['blocked_by_resolved'] == 1


def test_empty_blockedby_and_no_area():
    fm = {'id': 'F1.1.1', 'title': 'Some task', 'blockedBy': [], 'area': None}
    source = make_source(fm)
    fake_conn = FakeConn()
    p = _patched(source)
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6], \
         patch('exocortex.processors.vault_backlog.conn', return_value=fake_conn):
        from exocortex.processors.vault_backlog import process
        result = process('src-1')

    assert result['status'] == 'ok'
    assert result['area_edge'] is False
    assert result['blocked_by_found'] == 0


def test_completed_as_empty_string_normalizes_to_none():
    fm = dict(REAL_SHAPE_FRONTMATTER, completed='')
    source = make_source(fm)
    fake_conn = FakeConn()
    p = _patched(source)
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6], \
         patch('exocortex.processors.vault_backlog.conn', return_value=fake_conn):
        from exocortex.processors.vault_backlog import process
        process('src-1')
    inserted_meta = next(iter(fake_conn.inserted.values()))['params'][5]
    assert inserted_meta.obj['completed'] is None


def test_process_source_not_found():
    with patch('exocortex.processors.vault_backlog.fetch_source', return_value=None), \
         patch('exocortex.processors.vault_backlog.already_processed', return_value=False):
        from exocortex.processors.vault_backlog import process
        result = process('missing')
    assert result['status'] == 'error'
    assert result['reason'] == 'source_not_found'


def test_idempotent_reprocess_updates_not_duplicates():
    source = make_source(REAL_SHAPE_FRONTMATTER)
    fake_conn = FakeConn()
    p = _patched(source)
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6], \
         patch('exocortex.processors.vault_backlog.TENANT_ID', 'tenant-1'), \
         patch('exocortex.processors.vault_backlog.conn', return_value=fake_conn):
        from exocortex.processors.vault_backlog import process
        first = process('src-1', force=True)
        fake_conn.existing_rows[('single', 'tenant-1', 'src-1')] = first['thought_id']
        second = process('src-1', force=True)

    assert first['thought_id'] == second['thought_id']
    assert len(fake_conn.inserted) == 1
    assert len(fake_conn.updated) == 1


def test_strip_wikilink():
    from exocortex.processors.vault_backlog import _strip_wikilink
    assert _strip_wikilink('[[globex]]') == 'globex'
    assert _strip_wikilink('[[coe-roadmap|CoE Roadmap]]') == 'coe-roadmap'
    assert _strip_wikilink('plain-area') == 'plain-area'
    assert _strip_wikilink(None) is None


def test_as_list_handles_shapes_seen_in_real_data():
    from exocortex.processors.vault_backlog import _as_list
    assert _as_list([]) == []
    assert _as_list(None) == []
    assert _as_list(['P2-028', 'P2-030']) == ['P2-028', 'P2-030']
    assert _as_list('P2-028') == ['P2-028']
