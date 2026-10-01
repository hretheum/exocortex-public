# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# exocortex/processors/vault_note.py — F33.1 vault-note processor.
#
# For prose documents under `_source/work/{architecture,clients,globex,
# tooling,diff-machine,howto}` — the ~500 files that don't fit the
# meeting-transcript pipeline. No LLM call: this is deterministic extraction
# (section_path, title, frontmatter tags, wikilinks) plus embeddings, unlike
# article.py's LLM-based tag_and_summarize.
#
# Unit of meaning vs unit of search (see schema/36_thought_chunks.sql):
# a document is ONE thought (one graph node, one wiki page, one synthesis
# item) — thoughts.embedding is always NULL for vault_note. Fragments for
# semantic search live in thought_chunks (schema/36_...sql), each with its
# own embedding + a FK back to the parent thought. Splitting on every
# markdown heading (the pre-migration design) put 399 documents into 4684
# thoughts, median fragment 303 chars — formatting granularity, not meaning.
# Chunking here splits ONLY on H2 and merges adjacent sections up to a
# minimum length (see _merge_sections_to_chunks) instead.
#
# CHUNK_MAX_CHARS exists because the local embedding server (bge-m3 via
# llama-swap, out of this project's reach — see task boundaries) rejects
# any single input over roughly ~512 tokens with a 500 error ("increase the
# physical batch size"). A first pass merging ONLY up to a minimum (no
# ceiling) left 801/1639 chunks (49%) with embedding=NULL — every section
# without an H2 heading nearby, or every long section on its own, silently
# unsearchable. Oversized sections are now split further (paragraph
# boundaries, or a hard character window as a last resort for a single
# giant paragraph) before the min-merge pass, and the merge pass itself
# never merges past the ceiling either.

from __future__ import annotations

import re
from typing import Any, Optional

from exocortex.db import Jsonb, conn, get_embeddings_batch, query_one
from exocortex.processors._common import (
    TENANT_ID,
    _insert_edge,
    already_processed,
    fetch_source,
    mark_processed,
)

PROCESSOR_NAME = 'vault_note.v1'

CHUNK_MIN_CHARS = 500
# Margin under the embedding server's ~512-token ceiling. Empirically tuned
# against the real K12 vault_note corpus (not guessed): 1400 chars still
# left 28% of chunks failing to embed (Polish-heavy technical prose runs
# closer to ~2.4 chars/token than the ~3 initially assumed); see
# docs/migracje/thought-chunks.md for the tuning trail.
CHUNK_MAX_CHARS = 900

# Mirrors exocortex/vault_watcher.py::FRONTMATTER_RE — same convention, kept
# local rather than imported since vault_watcher is a script entry point,
# not a library module other code should depend on.
_FRONTMATTER_RE = re.compile(r'^---\n(.*?)\n---\n?', re.DOTALL)
_H2_RE = re.compile(r'^##\s+(.*)$', re.MULTILINE)
_WIKILINK_RE = re.compile(r'\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]')


def _strip_frontmatter(raw: str) -> str:
    m = _FRONTMATTER_RE.match(raw)
    return raw[m.end():] if m else raw


def _section_path(vault_path: str) -> list[str]:
    """`_source/work/architecture/exocortex/foo.md` -> ['work','architecture','exocortex']."""
    parts = [p for p in vault_path.split('/') if p]
    if parts and parts[0] == '_source':
        parts = parts[1:]
    return parts[:-1]  # drop the filename itself


def _guess_title(body: str, frontmatter: dict, vault_path: str) -> str:
    h1 = re.search(r'^#\s+(.+)$', body, re.MULTILINE)
    if h1:
        return h1.group(1).strip()
    if frontmatter.get('title'):
        return str(frontmatter['title'])
    stem = vault_path.rsplit('/', 1)[-1]
    return re.sub(r'\.md$', '', stem)


def _extract_wikilinks(body: str) -> list[str]:
    seen: list[str] = []
    for m in _WIKILINK_RE.finditer(body):
        target = m.group(1).strip()
        if target and target not in seen:
            seen.append(target)
    return seen


def _split_by_h2(body: str) -> list[tuple[Optional[str], str]]:
    """Split into (heading_or_None, section_text) at H2 boundaries ONLY —
    H1/H3-H6 headings stay embedded inside whichever section contains them
    (or the lead section, for content before the first H2). No H2 at all ->
    the whole document is one section."""
    matches = list(_H2_RE.finditer(body))
    if not matches:
        stripped = body.strip()
        return [(None, stripped)] if stripped else []

    sections: list[tuple[Optional[str], str]] = []
    lead = body[:matches[0].start()].strip()
    if lead:
        sections.append((None, lead))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        heading = m.group(1).strip()
        text = body[start:end].strip()
        sections.append((heading, f'{heading}\n{text}' if text else heading))
    return sections


def _hard_split(text: str, max_chars: int) -> list[str]:
    """Last-resort fixed-width split when no paragraph boundary helps (a
    single paragraph alone still over max_chars)."""
    return [text[i:i + max_chars] for i in range(0, len(text), max_chars)] or ['']


def _split_oversized_section(heading: Optional[str], text: str,
                             max_chars: int = CHUNK_MAX_CHARS,
                             ) -> list[tuple[Optional[str], str]]:
    """A single H2 section can be longer than max_chars on its own — split
    it by paragraph (blank-line) boundaries, greedily grouping paragraphs
    up to max_chars, falling back to a hard character window only for a
    single paragraph that's still too big by itself. Every piece keeps the
    same heading — they're still logically one section."""
    if len(text) <= max_chars:
        return [(heading, text)]
    pieces: list[tuple[Optional[str], str]] = []
    cur = ''
    for para in re.split(r'\n\n+', text):
        if len(para) > max_chars:
            if cur:
                pieces.append((heading, cur))
                cur = ''
            pieces.extend((heading, piece) for piece in _hard_split(para, max_chars))
            continue
        candidate = f'{cur}\n\n{para}' if cur else para
        if cur and len(candidate) > max_chars:
            pieces.append((heading, cur))
            cur = para
        else:
            cur = candidate
    if cur:
        pieces.append((heading, cur))
    return pieces


def _cap_oversized_sections(sections: list[tuple[Optional[str], str]],
                            max_chars: int = CHUNK_MAX_CHARS,
                            ) -> list[tuple[Optional[str], str]]:
    out: list[tuple[Optional[str], str]] = []
    for heading, text in sections:
        out.extend(_split_oversized_section(heading, text, max_chars))
    return out


def _merge_sections_to_chunks(sections: list[tuple[Optional[str], str]],
                              min_chars: int = CHUNK_MIN_CHARS,
                              max_chars: int = CHUNK_MAX_CHARS,
                              ) -> list[tuple[Optional[str], str]]:
    """Greedily merge adjacent sections until each chunk is at least
    min_chars long, never exceeding max_chars. The raw per-H2 split alone
    still puts many single-paragraph sections under threshold; a trailing
    under-threshold remainder merges BACKWARD into the previous (already-
    closed) chunk — but only if that still fits under max_chars — rather
    than standing alone as a too-short final chunk. A document with zero or
    one section (already under threshold, or with no H2 headings at all)
    stays as its own single chunk (oversized ones already split by
    _cap_oversized_sections before this runs)."""
    if len(sections) <= 1:
        return sections

    merged: list[tuple[Optional[str], str]] = []
    cur_heading, cur_text = sections[0]
    for heading, text in sections[1:]:
        candidate_len = len(cur_text) + 2 + len(text)
        if len(cur_text) < min_chars and candidate_len <= max_chars:
            cur_text = f'{cur_text}\n\n{text}'
        else:
            merged.append((cur_heading, cur_text))
            cur_heading, cur_text = heading, text

    if merged and len(cur_text) < min_chars and \
            len(merged[-1][1]) + 2 + len(cur_text) <= max_chars:
        prev_heading, prev_text = merged.pop()
        merged.append((prev_heading, f'{prev_text}\n\n{cur_text}'))
    else:
        merged.append((cur_heading, cur_text))
    return merged


def _resolve_wikilink_target(target: str) -> Optional[tuple[str, str]]:
    """Best-effort: match a [[link]] target to an already-captured raw_source
    by filename stem. Returns (id, 'raw_source') or None — unresolved links
    (not yet ingested, or pointing outside the vault) are common and not an
    error."""
    stem = target.rsplit('/', 1)[-1]
    row = query_one(
        "SELECT id FROM raw_sources WHERE tenant_id = %s "
        "AND metadata->>'vault_path' LIKE %s ORDER BY ingested_at DESC LIMIT 1",
        TENANT_ID, f'%/{stem}.md',
    )
    if row:
        return str(row['id']), 'raw_source'
    return None


def _upsert_document_thought(source_id: str, body: str, domain: str,
                             metadata: dict) -> tuple[str, bool]:
    """One thought per document, keyed by (tenant_id, source_id,
    thought_type) — the standard single-thought-per-source shape, now that
    chunking no longer needs to fan a document out into multiple thoughts
    rows. embedding is always NULL: semantic search over vault_note content
    goes through thought_chunks (see graph_rag.vector_search)."""
    full_meta = {'domain': domain, **metadata}
    with conn() as c:
        existing = c.execute(
            "SELECT id FROM thoughts WHERE tenant_id = %s AND source_id = %s "
            "AND thought_type = 'vault_note' LIMIT 1",
            (TENANT_ID, source_id),
        ).fetchone()
        if existing:
            tid = str(existing['id'])
            c.execute(
                'UPDATE thoughts SET body = %s, metadata = %s, embedding = NULL WHERE id = %s',
                (body, Jsonb(full_meta), tid),
            )
            created = False
        else:
            row = c.execute(
                'INSERT INTO thoughts (tenant_id, source_id, body, thought_type, '
                'author, metadata, embedding) VALUES (%s, %s, %s, %s, %s, %s, NULL) '
                'RETURNING id',
                (TENANT_ID, source_id, body, 'vault_note', 'agent:processor', Jsonb(full_meta)),
            ).fetchone()
            tid = str(row['id'])
            created = True
        _insert_edge(c, {
            'tenant_id': TENANT_ID,
            'src_id': tid, 'src_type': 'thought',
            'dst_id': source_id, 'dst_type': 'raw_source',
            'type': 'acquired_from',
            'created_by': 'processor:vault_note',
        })
    return tid, created


def _replace_chunks(thought_id: str,
                    chunks: list[tuple[int, Optional[str], str, Optional[list[float]]]],
                    ) -> int:
    """Delete all of this thought's existing chunks, insert the fresh set.
    Delete+reinsert rather than upsert-by-chunk_index: chunk COUNT can
    legitimately shrink between runs (content edited down), and upserting
    by index would leave stale trailing rows behind forever — exactly the
    orphan-row bug the old one-thought-per-chunk design was prone to."""
    with conn() as c:
        c.execute('DELETE FROM thought_chunks WHERE thought_id = %s', (thought_id,))
        for idx, heading, text, embedding in chunks:
            emb_literal = (
                '[' + ','.join(repr(float(x)) for x in embedding) + ']' if embedding else None
            )
            c.execute(
                'INSERT INTO thought_chunks '
                '(tenant_id, thought_id, chunk_index, heading, body, embedding) '
                'VALUES (%s, %s, %s, %s, %s, %s)',
                (TENANT_ID, thought_id, idx, heading, text, emb_literal),
            )
    return len(chunks)


def process(source_id: str, *, force: bool = False) -> dict[str, Any]:
    if not force and already_processed(source_id, PROCESSOR_NAME):
        return {'status': 'skipped', 'reason': 'already_processed', 'source_id': source_id}

    source = fetch_source(source_id)
    if not source:
        return {'status': 'error', 'reason': 'source_not_found', 'source_id': source_id}

    meta = source.get('metadata') or {}
    frontmatter = meta.get('frontmatter') or {}
    vault_path = meta.get('vault_path') or source.get('uri') or ''
    raw = meta.get('raw_payload') or ''
    body = _strip_frontmatter(raw)

    title = _guess_title(body, frontmatter, vault_path)
    section_path = _section_path(vault_path)
    wikilinks = _extract_wikilinks(body)
    sections = _cap_oversized_sections(_split_by_h2(body))
    chunks = _merge_sections_to_chunks(sections)

    if not chunks:
        return {'status': 'skipped', 'reason': 'empty_body', 'source_id': source_id}

    domain = meta.get('domain') or 'work'
    doc_metadata = {
        'vault_path': vault_path,
        'section_path': section_path,
        'title': title,
        'tags': frontmatter.get('tags'),
        'type': frontmatter.get('type'),
        'status': frontmatter.get('status'),
    }
    thought_id, created = _upsert_document_thought(source_id, body, domain, doc_metadata)

    embeddings = get_embeddings_batch([text for _, text in chunks])
    chunk_rows = [
        (idx, heading, text, embedding)
        for idx, ((heading, text), embedding) in enumerate(zip(chunks, embeddings))
    ]
    n_chunks = _replace_chunks(thought_id, chunk_rows)

    # Wikilinks describe the document as a whole, now anchored to the single
    # document thought (previously: the first chunk, as a proxy for "the
    # document" — no longer needed now that there's exactly one thought).
    wikilink_edges = 0
    if wikilinks:
        with conn() as c:
            for target in wikilinks:
                resolved = _resolve_wikilink_target(target)
                if resolved is None:
                    continue
                dst_id, dst_type = resolved
                if _insert_edge(c, {
                    'tenant_id': TENANT_ID,
                    'src_id': thought_id, 'src_type': 'thought',
                    'dst_id': dst_id, 'dst_type': dst_type,
                    'type': 'wikilink_to',
                    'created_by': 'processor:vault_note',
                }) is not None:
                    wikilink_edges += 1

    output = {
        'status': 'ok', 'source_id': source_id, 'thought_id': thought_id,
        'created': created, 'chunks': n_chunks,
        'wikilinks_found': len(wikilinks), 'wikilinks_resolved': wikilink_edges,
    }
    mark_processed(source_id, PROCESSOR_NAME, output)
    return output
