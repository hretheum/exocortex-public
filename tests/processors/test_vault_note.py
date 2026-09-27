"""Tests for F33.1 vault_note processor (post thought_chunks migration:
one thought per document, fragments in a separate table)."""
from __future__ import annotations
from unittest.mock import patch

import pytest

from tests.processors._fakedb import FakeConn


def make_source(raw_payload, frontmatter=None, vault_path='_source/work/architecture/foo.md',
                domain='work'):
    return {
        'id': 'src-1',
        'metadata': {
            'raw_payload': raw_payload,
            'frontmatter': frontmatter or {},
            'vault_path': vault_path,
            'domain': domain,
        },
    }


WITH_HEADINGS = """---
title: Diff Machine
tags: [architecture]
---
Intro paragraph before any heading.

# Diff Machine

Top-level overview text.

## Architecture

Details about the architecture, see [[coe-vault-updates]] for more.
"""

NO_FRONTMATTER = """# Standalone note

Just prose, no YAML block at all — this is the norm for 318 of 1620 files,
not an error.

## A section

More text here.
"""

# Two H2 sections, each long enough on its own to survive the merge step
# without being combined into one chunk.
LONG_TWO_SECTIONS = """# Big Document

## First Section

""" + ("Padding sentence to push this section past the merge threshold. " * 10) + """

## Second Section

""" + ("Another padding sentence to push this section past the threshold too. " * 10)


def _patched(source_row, embeddings=None):
    return (
        patch('exocortex.processors.vault_note.fetch_source', return_value=source_row),
        patch('exocortex.processors.vault_note.already_processed', return_value=False),
        patch('exocortex.processors.vault_note.mark_processed'),
        patch('exocortex.processors.vault_note.get_embeddings_batch',
              return_value=embeddings or [[0.1, 0.2]] * 10),
        patch('exocortex.processors.vault_note.query_one', return_value=None),
        patch('exocortex.processors.vault_note._insert_edge', return_value={'id': 'edge-1'}),
    )


def test_process_short_document_merges_to_one_chunk_one_thought():
    """Small fixture: lead + one H2 section, both short — must merge into a
    single chunk, and always exactly one document thought regardless of
    section count."""
    source = make_source(WITH_HEADINGS, frontmatter={'title': 'Diff Machine', 'tags': ['architecture']})
    fake_conn = FakeConn()
    patches = _patched(source)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
         patch('exocortex.processors.vault_note.conn', return_value=fake_conn):
        from exocortex.processors.vault_note import process
        result = process('src-1')

    assert result['status'] == 'ok'
    assert result['created'] is True
    assert result['chunks'] == 1
    assert result['wikilinks_found'] == 1
    assert len(fake_conn.inserted) == 1  # exactly one thoughts row, not one per chunk
    assert len(fake_conn.chunk_inserts) == 1


def test_process_long_document_keeps_sections_as_separate_chunks():
    source = make_source(LONG_TWO_SECTIONS, frontmatter={'title': 'Big Document'})
    fake_conn = FakeConn()
    patches = _patched(source, embeddings=[[0.1, 0.2]] * 5)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
         patch('exocortex.processors.vault_note.conn', return_value=fake_conn):
        from exocortex.processors.vault_note import process
        result = process('src-1')

    assert result['status'] == 'ok'
    assert result['chunks'] == 2
    assert len(fake_conn.inserted) == 1
    assert len(fake_conn.chunk_inserts) == 2


def test_process_file_without_frontmatter_does_not_crash():
    """Mandatory case: 318/1620 files have no frontmatter block at all."""
    source = make_source(NO_FRONTMATTER, frontmatter={})
    fake_conn = FakeConn()
    patches = _patched(source)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
         patch('exocortex.processors.vault_note.conn', return_value=fake_conn):
        from exocortex.processors.vault_note import process
        result = process('src-1')

    assert result['status'] == 'ok'
    assert result['chunks'] >= 1
    assert len(fake_conn.inserted) == 1


def test_process_source_not_found():
    with patch('exocortex.processors.vault_note.fetch_source', return_value=None), \
         patch('exocortex.processors.vault_note.already_processed', return_value=False):
        from exocortex.processors.vault_note import process
        result = process('missing')
    assert result['status'] == 'error'
    assert result['reason'] == 'source_not_found'


def test_process_already_processed_is_skipped():
    source = make_source(WITH_HEADINGS)
    with patch('exocortex.processors.vault_note.fetch_source', return_value=source), \
         patch('exocortex.processors.vault_note.already_processed', return_value=True):
        from exocortex.processors.vault_note import process
        result = process('src-1')
    assert result == {'status': 'skipped', 'reason': 'already_processed', 'source_id': 'src-1'}


def test_document_thought_embedding_always_null():
    """thoughts.embedding must stay NULL for vault_note — semantic search
    lives in thought_chunks now, and embedding the whole document again
    would be redundant (and can exceed the embedding API's length limit)."""
    source = make_source(WITH_HEADINGS)
    fake_conn = FakeConn()
    patches = _patched(source)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
         patch('exocortex.processors.vault_note.conn', return_value=fake_conn):
        from exocortex.processors.vault_note import process
        process('src-1')

    ((_, params),) = fake_conn.inserted.items()
    insert_sql, insert_params = params['sql'], params['params']
    assert 'embedding' in insert_sql
    # Last placeholder before RETURNING corresponds to the embedding column
    # in the INSERT INTO thoughts (...) VALUES (...) statement; the query
    # itself hardcodes NULL rather than binding a parameter for it.
    assert 'VALUES (%s, %s, %s, %s, %s, %s, NULL)' in insert_sql


def test_idempotent_reprocess_updates_document_not_duplicates():
    """Running process() twice must update the SAME document thought, not
    create a second one — the whole point of 'thought = document' identity."""
    source = make_source(WITH_HEADINGS, frontmatter={'title': 'Diff Machine'})
    fake_conn = FakeConn()
    patches = _patched(source)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
         patch('exocortex.processors.vault_note.TENANT_ID', 'tenant-1'), \
         patch('exocortex.processors.vault_note.conn', return_value=fake_conn):
        from exocortex.processors.vault_note import process
        first = process('src-1', force=True)
        assert len(fake_conn.inserted) == 1

        fake_conn.existing_rows[('single', 'tenant-1', 'src-1')] = first['thought_id']

        second = process('src-1', force=True)

    assert first['status'] == 'ok'
    assert second['status'] == 'ok'
    assert first['thought_id'] == second['thought_id']
    assert len(fake_conn.inserted) == 1  # no second INSERT — went through UPDATE
    assert len(fake_conn.updated) == 1


def test_reprocess_with_fewer_sections_does_not_leave_orphan_chunks():
    """Chunks are delete+reinserted on every run, not upserted by index —
    a document that shrinks from N sections to fewer must not leave stale
    trailing chunk rows (the old one-thought-per-chunk design was exactly
    this bug: upsert-by-chunk_index never removed extra old rows)."""
    fake_conn = FakeConn()
    long_source = make_source(LONG_TWO_SECTIONS, frontmatter={'title': 'Big Document'})
    patches = _patched(long_source, embeddings=[[0.1, 0.2]] * 5)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
         patch('exocortex.processors.vault_note.TENANT_ID', 'tenant-1'), \
         patch('exocortex.processors.vault_note.conn', return_value=fake_conn):
        from exocortex.processors.vault_note import process
        first = process('src-1', force=True)
    assert first['chunks'] == 2
    assert len(fake_conn.chunk_inserts) == 2

    short_source = make_source(WITH_HEADINGS, frontmatter={'title': 'Diff Machine'})
    fake_conn.existing_rows[('single', 'tenant-1', 'src-1')] = first['thought_id']
    patches2 = _patched(short_source)
    with patches2[0], patches2[1], patches2[2], patches2[3], patches2[4], patches2[5], \
         patch('exocortex.processors.vault_note.TENANT_ID', 'tenant-1'), \
         patch('exocortex.processors.vault_note.conn', return_value=fake_conn):
        second = process('src-1', force=True)

    assert second['chunks'] == 1
    assert first['thought_id'] in fake_conn.chunk_deletes
    assert len(fake_conn.chunk_inserts) == 1  # not 3 (2 stale + 1 new)


def test_wikilinks_anchor_to_document_thought():
    source = make_source(WITH_HEADINGS, frontmatter={'title': 'Diff Machine'})
    fake_conn = FakeConn()
    patches = _patched(source)
    insert_edge_calls = []
    with patches[0], patches[1], patches[2], patches[3], \
         patch('exocortex.processors.vault_note.query_one', return_value={'id': 'raw-source-x'}), \
         patch('exocortex.processors.vault_note._insert_edge',
               side_effect=lambda c, e: insert_edge_calls.append(e) or {'id': 'edge-1'}), \
         patch('exocortex.processors.vault_note.conn', return_value=fake_conn):
        from exocortex.processors.vault_note import process
        result = process('src-1')

    wikilink_edges = [e for e in insert_edge_calls if e['type'] == 'wikilink_to']
    assert len(wikilink_edges) == 1
    assert wikilink_edges[0]['src_id'] == result['thought_id']


def test_section_path_strips_source_prefix_and_filename():
    from exocortex.processors.vault_note import _section_path
    assert _section_path('_source/work/architecture/exocortex/foo.md') == \
        ['work', 'architecture', 'exocortex']


def test_wikilink_extraction_dedupes_and_strips_aliases():
    from exocortex.processors.vault_note import _extract_wikilinks
    body = "See [[foo]] and [[foo|Foo Bar]] and [[bar#section]]."
    assert _extract_wikilinks(body) == ['foo', 'bar']


def test_split_by_h2_ignores_h1_and_h3_as_boundaries():
    from exocortex.processors.vault_note import _split_by_h2
    body = "# Title\n\nIntro.\n\n### Not a boundary\n\nMore intro.\n\n## Real Section\n\nBody.\n"
    sections = _split_by_h2(body)
    assert len(sections) == 2
    assert sections[0][0] is None
    assert '### Not a boundary' in sections[0][1]
    assert sections[1][0] == 'Real Section'


def test_split_by_h2_no_headings_is_one_section():
    from exocortex.processors.vault_note import _split_by_h2
    assert len(_split_by_h2("Just plain prose.\n\nNo headings here.")) == 1


def test_merge_sections_short_sections_combine_into_one_chunk():
    from exocortex.processors.vault_note import _merge_sections_to_chunks
    sections = [(None, 'a' * 100), ('B', 'b' * 100), ('C', 'c' * 100)]
    chunks = _merge_sections_to_chunks(sections, min_chars=500)
    assert len(chunks) == 1
    assert len(chunks[0][1]) == 300 + 4  # + 2 '\n\n' separators (2 chars each)


def test_merge_sections_trailing_remainder_merges_backward():
    from exocortex.processors.vault_note import _merge_sections_to_chunks
    sections = [(None, 'a' * 600), ('B', 'b' * 50), ('C', 'c' * 50)]
    chunks = _merge_sections_to_chunks(sections, min_chars=500)
    assert len(chunks) == 1  # trailing B+C (100 chars) merges into the first chunk


def test_merge_sections_keeps_chunks_already_above_threshold_separate():
    from exocortex.processors.vault_note import _merge_sections_to_chunks
    sections = [(None, 'a' * 600), ('B', 'b' * 600)]
    chunks = _merge_sections_to_chunks(sections, min_chars=500)
    assert len(chunks) == 2


def test_merge_sections_never_merges_past_max_chars():
    """Regression for the K12 finding: merging with only a minimum (no
    ceiling) left 49% of chunks over the embedding server's real token
    limit, silently unsearchable. A trailing under-threshold remainder
    that WOULD fit backward still merges (small enough); one that would
    push the previous chunk over max_chars must stand alone instead."""
    from exocortex.processors.vault_note import _merge_sections_to_chunks
    sections = [(None, 'a' * 600), ('B', 'b' * 600), ('C', 'c' * 400)]
    chunks = _merge_sections_to_chunks(sections, min_chars=500, max_chars=1000)
    # B(600) + C(400) + 2 separator chars = 1002 > 1000 -> merging C backward
    # into B would breach the ceiling, so C stands alone despite being < min.
    assert len(chunks) == 3
    assert all(len(text) <= 1000 for _, text in chunks)


def test_split_oversized_section_splits_by_paragraph():
    from exocortex.processors.vault_note import _split_oversized_section
    text = '\n\n'.join(['p' * 400, 'q' * 400, 'r' * 400])  # 1200+ chars total
    pieces = _split_oversized_section('Heading', text, max_chars=900)
    assert len(pieces) >= 2
    assert all(len(t) <= 900 for _, t in pieces)
    assert all(h == 'Heading' for h, _ in pieces)


def test_split_oversized_section_hard_splits_single_giant_paragraph():
    from exocortex.processors.vault_note import _split_oversized_section
    text = 'x' * 2500  # one paragraph, no blank lines, way over the ceiling
    pieces = _split_oversized_section(None, text, max_chars=1000)
    assert len(pieces) == 3
    assert all(len(t) <= 1000 for _, t in pieces)
    assert ''.join(t for _, t in pieces) == text


def test_split_oversized_section_leaves_short_section_untouched():
    from exocortex.processors.vault_note import _split_oversized_section
    assert _split_oversized_section('H', 'short text', max_chars=1000) == \
        [('H', 'short text')]


def test_cap_oversized_sections_only_expands_the_big_one():
    from exocortex.processors.vault_note import _cap_oversized_sections
    sections = [(None, 'short'), ('Big', 'p' * 900 + '\n\n' + 'q' * 900)]
    capped = _cap_oversized_sections(sections, max_chars=1000)
    assert capped[0] == (None, 'short')
    assert len(capped) == 3  # short section untouched + big one split into 2
    assert all(len(t) <= 1000 for _, t in capped)
