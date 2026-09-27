"""Tests for F34 work_meeting_note processor.

Behavior-preservation focus (docs/refactor/MAPA-ZACHOWANIA.md is the spec):
title/section parsing, body assembly order, and the three idempotency layers
from docs/refactor/IDEMPOTENCJA.md — meeting_id identity beats per-file uri
identity (sync-conflict twins), body_hash gates re-extraction, and (D8) the
processor actually applies updates on real content change instead of the
literal current-production no-op-without---force default.
"""
from __future__ import annotations
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from tests.processors._fakedb import FakeConn

MEETING_A = """---
meeting_id: 2026-06-01-acme-kickoff
title: Acme Kickoff
date: 2026-06-01
duration_minutes: 45
organizer: eof@example.com
participants:
  - "alice@example.com,bob@example.com"
tags: [kickoff]
transcript_url: https://fireflies.ai/x
---

## Overview
We kicked things off.

## Action Items
- [ ] Send follow-up

## Key Points
Budget agreed.

## Notes
General notes.
"""

MEETING_NO_FM = """# 2026-06-02-standup

## Overview
Quick standup, no frontmatter meeting_id.
"""


def make_source(source_id, raw_payload, vault_path):
    """Shape used by manual /capture calls (and this test file's other
    fixtures): raw_payload is the UNTOUCHED original file text, frontmatter
    block included."""
    return {
        'id': source_id,
        'uri': f'file://{vault_path}',
        'metadata': {'raw_payload': raw_payload, 'vault_path': vault_path},
    }


def make_vault_watcher_source(source_id, raw_text, vault_path):
    """Shape actually produced by exocortex/vault_watcher.py::process_file():
    it parses frontmatter itself, sends the parsed dict as
    metadata.frontmatter, and raw_payload is the body with the frontmatter
    block ALREADY STRIPPED. Regression fixture for the bug where
    work_meeting_note.py re-parsed raw_payload for a frontmatter block that
    was no longer there, silently falling back to filename_stem for
    meeting_id — found live on K12 after deploying this processor."""
    from exocortex.vault_watcher import parse_frontmatter as watcher_parse_frontmatter
    fm, body = watcher_parse_frontmatter(raw_text)
    return {
        'id': source_id,
        'uri': f'file://{vault_path}',
        'metadata': {'raw_payload': body, 'frontmatter': fm, 'vault_path': vault_path},
    }


def _real_body_hash(raw_text, participants, filename_stem):
    from exocortex.processors.work_meeting_note import (
        FRONTMATTER_RE, _body_hash, build_body, parse_frontmatter,
        parse_sections, resolve_title,
    )
    fm = parse_frontmatter(raw_text)
    sections = parse_sections(raw_text)
    body_after_fm = FRONTMATTER_RE.sub('', raw_text, count=1).lstrip()
    title = resolve_title(fm, body_after_fm, filename_stem)
    return _body_hash(build_body(fm, title, sections, participants=participants))


def _run(source_row, fake_conn, *, find_existing_result=None, source_id='src-1', force=False):
    """Run process() with every DB/LLM side effect mocked out. Returns
    (result, mock_llm) so callers can assert on re-extraction calls."""
    with ExitStack() as stack:
        p = lambda target, **kw: stack.enter_context(  # noqa: E731
            patch(f'exocortex.processors.work_meeting_note.{target}', **kw))
        p('fetch_source', return_value=source_row)
        p('already_processed', return_value=False)
        p('mark_processed')
        p('log_anomaly')
        p('get_embedding', return_value=[0.1, 0.2])
        p('_insert_edge', return_value={'id': 'edge-1'})
        p('find_existing', return_value=find_existing_result)
        p('classify_meeting', return_value=MagicMock())
        p('emit_meeting_edges', return_value={})
        p('query_one', return_value=None)
        p('conn', return_value=fake_conn)
        mock_llm = p('_run_llm_extraction')

        from exocortex.processors.work_meeting_note import process
        result = process(source_id, force=force)
    return result, mock_llm


def test_process_new_meeting_creates_thought():
    source = make_source('src-1', MEETING_A, '_source/work/meeting-notes/2026-06-01-acme-kickoff.md')
    fake_conn = FakeConn()
    result, mock_llm = _run(source, fake_conn)

    assert result['status'] == 'ok'
    assert result['created'] is True
    assert result['meeting_id'] == '2026-06-01-acme-kickoff'
    assert len(fake_conn.inserted) == 1
    assert len(fake_conn.updated) == 0
    mock_llm.assert_called_once_with(result['thought_id'])


def test_process_source_not_found():
    with patch('exocortex.processors.work_meeting_note.fetch_source', return_value=None), \
         patch('exocortex.processors.work_meeting_note.already_processed', return_value=False):
        from exocortex.processors.work_meeting_note import process
        result = process('missing')
    assert result == {'status': 'error', 'reason': 'source_not_found', 'source_id': 'missing'}


def test_process_already_processed_is_skipped():
    source = make_source('src-1', MEETING_A, '_source/work/meeting-notes/x.md')
    with patch('exocortex.processors.work_meeting_note.fetch_source', return_value=source), \
         patch('exocortex.processors.work_meeting_note.already_processed', return_value=True):
        from exocortex.processors.work_meeting_note import process
        result = process('src-1')
    assert result == {'status': 'skipped', 'reason': 'already_processed', 'source_id': 'src-1'}


def test_existing_meeting_unchanged_body_updates_but_skips_reextraction():
    """D8: invocation here already means content_hash (layer 1) changed at
    the raw_sources level — but layer 3 (body_hash) can still find the
    *assembled meeting body* unchanged (e.g. only an unrelated metadata field
    differed). Must update the row, must NOT pay for re-extraction."""
    source = make_source('src-1', MEETING_A, '_source/work/meeting-notes/x.md')
    same_hash = _real_body_hash(MEETING_A, ['alice@example.com', 'bob@example.com'], 'x')
    fake_conn = FakeConn()

    result, mock_llm = _run(
        source, fake_conn,
        find_existing_result={'id': 'thought-existing', 'body_hash': same_hash},
    )

    assert result['status'] == 'ok'
    assert result['created'] is False
    assert result['body_unchanged'] is True
    assert 'thought-existing' in fake_conn.updated
    mock_llm.assert_not_called()


def test_existing_meeting_changed_body_updates_and_reextracts():
    source = make_source('src-1', MEETING_A, '_source/work/meeting-notes/x.md')
    fake_conn = FakeConn()

    result, mock_llm = _run(
        source, fake_conn,
        find_existing_result={'id': 'thought-existing', 'body_hash': 'stale000000'},
    )

    assert result['created'] is False
    assert result['body_unchanged'] is False
    assert 'thought-existing' in fake_conn.updated
    mock_llm.assert_called_once_with('thought-existing')


def test_sync_conflict_twin_resolves_to_same_thought_not_a_duplicate():
    """Layer 2 (meeting_id) must win over layer 1 (uri): two different
    source_ids/uris carrying the same meeting_id coalesce into one thought,
    matching the M2 baseline (5 files -> 4 thoughts)."""
    twin_a = make_source('src-A', MEETING_A, '_source/work/meeting-notes/a.md')
    twin_b = make_source('src-B', MEETING_A, '_source/work/meeting-notes/a.sync-conflict.md')
    fake_conn = FakeConn()

    first, _ = _run(twin_a, fake_conn, find_existing_result=None, source_id='src-A')
    assert first['created'] is True
    thought_id = first['thought_id']

    real_hash = _real_body_hash(MEETING_A, ['alice@example.com', 'bob@example.com'], 'a')
    second, _ = _run(
        twin_b, fake_conn,
        find_existing_result={'id': thought_id, 'body_hash': real_hash},
        source_id='src-B',
    )

    assert second['created'] is False
    assert second['thought_id'] == thought_id
    assert second['meeting_id'] == first['meeting_id']
    assert len(fake_conn.inserted) == 1  # still exactly one thought overall


def test_vault_watcher_shaped_source_resolves_real_meeting_id_not_filename():
    """Regression for the K12 incident: with a real vault_watcher-shaped
    payload (frontmatter stripped from raw_payload, parsed dict in
    metadata.frontmatter), meeting_id must come from the frontmatter's real
    Fireflies ULID, not fall back to the filename stem."""
    source = make_vault_watcher_source(
        'src-1', MEETING_A, '_source/work/meeting-notes/some-other-filename.md',
    )
    fake_conn = FakeConn()
    result, _ = _run(source, fake_conn)

    assert result['meeting_id'] == '2026-06-01-acme-kickoff'
    assert result['meeting_id'] != 'some-other-filename'


def test_vault_watcher_shaped_sync_conflict_twins_still_dedupe():
    """Same regression, but for the case that actually cascaded on K12:
    two vault_watcher-shaped twin files with different filenames but the
    same frontmatter meeting_id must still resolve to one thought."""
    twin_a = make_vault_watcher_source(
        'src-A', MEETING_A, '_source/work/meeting-notes/acme-kickoff.md',
    )
    twin_b = make_vault_watcher_source(
        'src-B', MEETING_A, '_source/work/meeting-notes/acme-kickoff.sync-conflict-X.md',
    )
    fake_conn = FakeConn()

    first, _ = _run(twin_a, fake_conn, find_existing_result=None, source_id='src-A')
    assert first['created'] is True
    assert first['meeting_id'] == '2026-06-01-acme-kickoff'

    second, _ = _run(
        twin_b, fake_conn,
        find_existing_result={'id': first['thought_id'], 'body_hash': first['thought_id'] and 'irrelevant'},
        source_id='src-B',
    )
    assert second['meeting_id'] == first['meeting_id']


def test_meeting_id_falls_back_to_filename_stem_without_frontmatter():
    source = make_source('src-1', MEETING_NO_FM, '_source/work/meeting-notes/2026-06-02-standup.md')
    fake_conn = FakeConn()
    result, _ = _run(source, fake_conn)
    assert result['meeting_id'] == '2026-06-02-standup'


def test_normalize_participants_splits_comma_joined_and_logs_anomaly():
    from exocortex.processors.work_meeting_note import normalize_participants
    with patch('exocortex.processors.work_meeting_note.log_anomaly') as mock_log:
        result = normalize_participants(
            ['alice@example.com,bob@example.com'], source_id='src-1', vault_path='x.md',
        )
    assert result == ['alice@example.com', 'bob@example.com']
    mock_log.assert_called_once()
    args, _ = mock_log.call_args
    assert args[0] == 'src-1'
    assert args[2] == 'comma_joined_participants'


def test_normalize_participants_dedupes_case_insensitively():
    from exocortex.processors.work_meeting_note import normalize_participants
    with patch('exocortex.processors.work_meeting_note.log_anomaly'):
        result = normalize_participants(
            ['Alice@example.com', 'alice@example.com'], source_id='src-1', vault_path='x.md',
        )
    assert result == ['Alice@example.com']


def test_resolve_title_fallback_chain():
    from exocortex.processors.work_meeting_note import resolve_title
    assert resolve_title({'title': ' Real Title '}, '# H1 Title\n', '2026-01-01-slug') == 'Real Title'
    assert resolve_title({}, '# H1 Title\n', '2026-01-01-slug') == 'H1 Title'
    assert resolve_title({}, 'no heading here', '2026-01-01-slug') == 'slug'


def test_build_body_coerces_non_string_tags():
    """Regression test: YAML frontmatter `tags: [meeting, 121]` parses the
    bare number as int, not str — production crash on
    file:///vault/_source/work/meeting-notes/121/kzielinski/2026-07-29-gabi-biweekly.md
    (TypeError: sequence item 1: expected str instance, int found)."""
    from exocortex.processors.work_meeting_note import build_body
    body = build_body({'tags': ['meeting', 121]}, 'Title', {})
    assert 'Tags: meeting, 121' in body


def test_build_body_coerces_non_string_participants():
    """Same defensive coercion for participants — same join pattern,
    same latent risk if frontmatter ever yields a non-string entry."""
    from exocortex.processors.work_meeting_note import build_body
    body = build_body({}, 'Title', {}, participants=['owner@example.com', 121])
    assert 'Participants: owner@example.com, 121' in body


def test_build_body_section_order_matches_legacy():
    """workers/ingest.py assembles overview, key_points, action_items, notes —
    NOT the EXTRACTED_SECTIONS extraction order (Overview, Action Items, Key
    Points, Notes). MAPA-ZACHOWANIA.md flags this; must be preserved exactly."""
    from exocortex.processors.work_meeting_note import build_body
    sections = {
        'overview': 'OV', 'action_items': 'AI', 'key_points': 'KP', 'notes': 'NT',
    }
    body = build_body({}, 'Title', sections)
    assert body.index('## Overview') < body.index('## Key Points') \
        < body.index('## Action Items') < body.index('## Notes')
