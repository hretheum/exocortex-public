# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# exocortex/processors/work_meeting_note.py — F34 meeting-note processor.
#
# Replaces workers/ingest.py's direct-to-Postgres bulk script. Canonical path:
# vault_watcher POSTs each `_source/work/meeting-notes/*.md` file to Capture
# API (source_type=work-meeting-note) -> scorer.py routes content_acquired
# here, one file at a time.
#
# Parsing/assembly logic (resolve_title, normalize_participants,
# parse_frontmatter, parse_sections, extract_section, build_body) is ported
# 1:1 from workers/ingest.py — behavior is the spec for this refactor.
# The three idempotency layers below interoperate: Capture API content_hash (per file uri, gates whether this
# function runs at all), find_existing() (per meeting_id, resolves identity
# across sync-conflict twin files), body_hash (per assembled body, gates
# whether LLM extraction re-fires).
#
# D8: unlike ingest_file()'s literal production
# default (skip unconditionally unless run with --force), this processor
# always diffs body_hash and updates on real content change. Being invoked
# here already means Capture API detected the file's content changed, which
# is the --force-equivalent precondition — approved deviation from the
# as-deployed (no --force) systemd behavior, not from the code's own design.

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

import yaml

from exocortex.classifier import classify_meeting
from exocortex.db import Jsonb, conn, emit_meeting_edges, get_embedding, query_one
from exocortex.processors._common import (
    TENANT_ID,
    _insert_edge,
    already_processed,
    fetch_source,
    log_anomaly,
    mark_processed,
)

PROCESSOR_NAME = 'work_meeting_note.v1'
THOUGHT_TYPE = 'work_meeting_note'

log = logging.getLogger(__name__)

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-")
EXTRACTED_SECTIONS = ("Overview", "Action Items", "Key Points", "Notes")


# ─────────────────────────── Parsing (ported from workers/ingest.py) ───────────────────────────

def resolve_title(fm: dict, body_after_fm: str, filename_stem: str) -> str:
    """3-level fallback: frontmatter.title → first H1 → date-stripped filename."""
    fm_title = fm.get('title')
    if fm_title is not None and str(fm_title).strip():
        return str(fm_title).strip()
    m = H1_RE.search(body_after_fm)
    if m and m.group(1).strip():
        return m.group(1).strip()
    return DATE_PREFIX_RE.sub('', filename_stem)


def normalize_participants(raw, *, source_id: str, vault_path: str) -> list[str]:
    """Coerce `participants` frontmatter to a clean list of single-email strings.

    Fixes the source-quality issue where Fireflies sometimes emits a single
    string with comma-separated emails (`"a@x,b@y,c@z"`) inside a 1-item list,
    instead of a 3-item list. Splits and logs the anomaly via log_anomaly()
    (F34 — DB-backed, replaces the old per-repo TSV file) so it stays
    auditable across container rebuilds.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    cleaned: list[str] = []
    anomalies: list[tuple[str, int]] = []
    for entry in raw:
        if entry is None:
            continue
        s = str(entry).strip()
        if not s:
            continue
        if ',' in s:
            parts = [e.strip() for e in s.split(',') if e.strip()]
            anomalies.append((s, len(parts)))
            cleaned.extend(parts)
        else:
            cleaned.append(s)
    for original, n_parts in anomalies:
        log_anomaly(source_id, PROCESSOR_NAME, 'comma_joined_participants', {
            'vault_path': vault_path, 'raw': original, 'split_into': n_parts,
        })
    seen: set[str] = set()
    deduped: list[str] = []
    for e in cleaned:
        key = e.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)
    return deduped


def parse_frontmatter(text: str) -> dict:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}


def extract_section(text: str, name: str) -> str | None:
    """Extract '## NAME' content. Stops at next non-bold '## ' header or EOF.
    (Notes' '## **bold**' subsections are kept as part of Notes content.)"""
    start = re.search(rf'^## {re.escape(name)}\s*$\n', text, re.MULTILINE)
    if not start:
        return None
    rest = text[start.end():]
    end = re.search(r'^## (?!\*\*)', rest, re.MULTILINE)
    content = rest[:end.start()] if end else rest
    content = content.strip()
    return content or None


def parse_sections(text: str) -> dict[str, str]:
    body = FRONTMATTER_RE.sub('', text, count=1).lstrip()
    out: dict[str, str] = {}
    for name in EXTRACTED_SECTIONS:
        content = extract_section(body, name)
        if content:
            out[name.lower().replace(' ', '_')] = content
    return out


def build_body(fm: dict, title: str, sections: dict[str, str],
               participants: list[str] | None = None) -> str:
    parts = [f'Meeting: {title}']
    if fm.get('date'):
        parts.append(f"Date: {fm['date']}")
    if fm.get('duration_minutes'):
        parts.append(f"Duration: {int(fm['duration_minutes'])} min")
    if fm.get('organizer'):
        parts.append(f"Organizer: {fm['organizer']}")
    if participants is None:
        participants = fm.get('participants') or []
    if participants:
        parts.append(f"Participants: {', '.join(str(p) for p in participants)}")
    tags = fm.get('tags') or []
    if tags:
        parts.append(f"Tags: {', '.join(str(t) for t in tags)}")
    if fm.get('transcript_url'):
        parts.append(f"Transcript: {fm['transcript_url']}")

    for key in ('overview', 'key_points', 'action_items', 'notes'):
        if sections.get(key):
            heading = key.replace('_', ' ').title()
            parts.append(f'\n## {heading}\n{sections[key]}')
    return '\n'.join(parts)


def _body_hash(body: str) -> str:
    return hashlib.sha256(body.encode('utf-8')).hexdigest()[:12]


# ─────────────────────────── Idempotency layer 2: meeting_id identity ───────────────────────────

def find_existing(meeting_id: str) -> dict | None:
    """Layer 2: resolve a thought by meeting_id,
    independent of which raw_sources row (uri) triggered this call. Coalesces
    sync-conflict twin files that carry the same meeting_id into one thought."""
    row = query_one(
        "SELECT id, metadata->>'body_hash' AS body_hash "
        'FROM thoughts WHERE tenant_id = %s AND thought_type = %s '
        "AND metadata->>'meeting_id' = %s LIMIT 1",
        TENANT_ID, THOUGHT_TYPE, meeting_id,
    )
    return {'id': str(row['id']), 'body_hash': row['body_hash']} if row else None


def _upsert_thought(source_id: str, existing_id: str | None, body: str,
                    metadata: dict) -> tuple[str, bool]:
    """Insert or update the thought, plus an acquired_from edge to THIS
    raw_source (idempotent — a second sync-conflict twin for the same meeting
    adds a second edge to the same thought, not a duplicate thought)."""
    embedding = get_embedding(body)
    emb_literal = (
        '[' + ','.join(repr(float(x)) for x in embedding) + ']' if embedding else None
    )
    with conn() as c:
        if existing_id:
            c.execute(
                'UPDATE thoughts SET body = %s, metadata = %s, embedding = %s WHERE id = %s',
                (body, Jsonb(metadata), emb_literal, existing_id),
            )
            tid, created = existing_id, False
        else:
            row = c.execute(
                'INSERT INTO thoughts (tenant_id, source_id, body, thought_type, '
                'author, metadata, embedding) VALUES (%s, %s, %s, %s, %s, %s, %s) '
                'RETURNING id',
                (TENANT_ID, source_id, body, THOUGHT_TYPE, 'agent:processor',
                 Jsonb(metadata), emb_literal),
            ).fetchone()
            tid, created = str(row['id']), True
        _insert_edge(c, {
            'tenant_id': TENANT_ID,
            'src_id': tid, 'src_type': 'thought',
            'dst_id': source_id, 'dst_type': 'raw_source',
            'type': 'acquired_from',
            'created_by': 'processor:work_meeting_note',
        })
    return tid, created


def _emit_edges(thought_id: str, metadata: dict) -> None:
    try:
        et = query_one('SELECT extracted_tags FROM thoughts WHERE id = %s', thought_id) or {}
        thought_for_classify = {
            'id': thought_id,
            'metadata': metadata,
            'extracted_tags': et.get('extracted_tags') or {},
        }
        cls = classify_meeting(thought_for_classify)
        emit_meeting_edges(thought_id, metadata, cls, TENANT_ID)
    except Exception:  # never block processing
        log.exception('edge emit error for thought %s', thought_id[:8])


def _run_llm_extraction(thought_id: str) -> None:
    try:
        # scripts/extract_tags_batch.py is not in the public repository; the ImportError is handled below
        from scripts.extract_tags_batch import (  # type: ignore[import-not-found]
            extract_tags_for_thought,
        )
    except ImportError:
        log.warning('LLM extraction unavailable; skipping')
        return
    try:
        extract_tags_for_thought(thought_id)
    except Exception:  # never block processing
        log.exception('LLM extraction error for thought %s', thought_id[:8])


# ─────────────────────────── Entry point ───────────────────────────

def process(source_id: str, *, force: bool = False) -> dict[str, Any]:
    if not force and already_processed(source_id, PROCESSOR_NAME):
        return {'status': 'skipped', 'reason': 'already_processed', 'source_id': source_id}

    source = fetch_source(source_id)
    if not source:
        return {'status': 'error', 'reason': 'source_not_found', 'source_id': source_id}

    meta = source.get('metadata') or {}
    vault_path = meta.get('vault_path') or source.get('uri') or ''
    filename_stem = re.sub(r'\.md$', '', vault_path.rsplit('/', 1)[-1])
    raw = meta.get('raw_payload') or ''

    # vault_watcher.py already parses frontmatter itself and sends the parsed
    # dict as metadata.frontmatter, with raw_payload = the body AFTER
    # stripping the frontmatter block — re-parsing raw_payload here would
    # always find nothing and silently fall back to filename_stem for
    # meeting_id, breaking both find_existing() identity resolution and
    # sync-conflict-twin dedup. Only fall back to parsing raw_payload
    # ourselves when frontmatter isn't present in metadata at all (e.g. a
    # manual /capture call that sent the untouched original file text).
    fm = meta.get('frontmatter')
    if fm is None:
        fm = parse_frontmatter(raw)
    sections = parse_sections(raw)
    body_after_fm = FRONTMATTER_RE.sub('', raw, count=1).lstrip()
    title = resolve_title(fm, body_after_fm, filename_stem)

    meeting_id = fm.get('meeting_id') or filename_stem
    existing = find_existing(meeting_id)

    participants_clean = normalize_participants(
        fm.get('participants'), source_id=source_id, vault_path=vault_path,
    )
    body = build_body(fm, title, sections, participants=participants_clean)
    body_hash = _body_hash(body)
    metadata = {
        'domain': 'work',
        'title': title,
        'meeting_id': meeting_id,
        'source': fm.get('source', 'fireflies'),
        'transcript_url': fm.get('transcript_url'),
        'organizer': fm.get('organizer'),
        'participants': participants_clean,
        'tags': fm.get('tags') or [],
        'meeting_type': fm.get('meeting_type'),
        'duration_minutes': fm.get('duration_minutes'),
        'synced_at': str(fm.get('synced_at', '')),
        'overview': sections.get('overview'),
        'action_items': sections.get('action_items'),
        'key_points': sections.get('key_points'),
        'notes': sections.get('notes'),
        'body_hash': body_hash,
    }

    body_unchanged = existing is not None and existing.get('body_hash') == body_hash
    thought_id, created = _upsert_thought(
        source_id, existing['id'] if existing else None, body, metadata,
    )

    if not body_unchanged:
        _run_llm_extraction(thought_id)
    _emit_edges(thought_id, metadata)

    output = {
        'status': 'ok', 'source_id': source_id, 'thought_id': thought_id,
        'meeting_id': meeting_id, 'created': created, 'body_unchanged': body_unchanged,
    }
    mark_processed(source_id, PROCESSOR_NAME, output)
    return output
