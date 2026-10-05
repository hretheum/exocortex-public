# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/capture_api.py — F6.1.2: FastAPI POST /capture endpoint.
#
# Single-ingestion endpoint for the F6 Generic Content Acquisition Module.
# All sources (RSS adapter, Gmail adapter, Web Clipper, vault watcher,
# Telegram bot, Shortcut bookmarklet) POST here.
#
# Idempotent: ON CONFLICT (tenant_id, source_type, uri) DO NOTHING. Re-POST
# of the same URI returns 200 with the existing source_id (no new row).
#
# After successful INSERT (new row), emits pg_notify('content_acquired',
# json_build_object('source_id', ..., 'source_type', ...)) so F6.3 listener
# (workers/scorer.py) can route to the right processor.
#
# Local run:
#     uvicorn workers.capture_api:app --host 0.0.0.0 --port 8000 --reload
#
# Smoke test (with bearer token from CAPTURE_API_TOKEN env):
#     curl -X POST http://localhost:8000/capture \
#         -H "Authorization: Bearer $CAPTURE_API_TOKEN" \
#         -H "Content-Type: application/json" \
#         -d '{"source_type":"manual-url","uri":"https://example.com/test"}'

from __future__ import annotations

import json
import os
import re
import secrets
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg.errors import UniqueViolation
from pydantic import AnyUrl, BaseModel, Field

from exocortex._bootstrap import bootstrap

bootstrap()

from exocortex.db import capture as capture_db
from exocortex.db import conn, get_pool, query
from exocortex.settings import get_tenant_id

# ─────────────────────────── Config ───────────────────────────

TENANT_ID = get_tenant_id()
CAPTURE_API_TOKEN = os.environ.get('CAPTURE_API_TOKEN', '').strip()

# Allowed source_type values — keeps payload schema sane and forces F6.3 router
# to declare every new type explicitly. New types: bump this list + add a
# processor in workers/processors/.
ALLOWED_SOURCE_TYPES = {
    'rss-frp',
    'gmail-thread',
    'web-clipping',
    'article',
    'recipe',
    '3d-model',
    'github-issue',
    'twitter-thread',
    'arxiv',
    'youtube-tutorial',
    'personal-article',
    'quick-note',
    'manual-url',
    'email-thread',          # alias used by web-clipper email-forward template
    'frp-source',            # web-clipper FRP template
    'generated-frp',         # F7.2.1 — internally generated FRP stories (futures-story-generator)
    'linkedin-post',
    'newsletter',            # F8.8 — industry newsletters from Gmail "Read Later" label
    'notion-task-sync',     # F21 — source Notion DB (exocortex/sources/notion.py)
    'telegram-capture',     # F31.0.3 — captures forwarded via the Telegram bot
    'notion-cockpit-action',  # F31.3.3 — Notion property change via cockpit poller
    'vault-note',            # F33.1 — prose vault docs (architecture, clients, howto, ...)
    'vault-backlog',         # F33.2 — TaskNotes-style backlog/roadmap items
    'work-meeting-note',     # F34 — Fireflies meeting transcripts, replaces workers/ingest.py
    'claude-session',        # ingest of Claude Code transcripts (dialogue only, redacted)
}

EXCERPT_WORDS = 150


# ─────────────────────────── Schemas ───────────────────────────

class CaptureRequest(BaseModel):
    source_type: str = Field(..., description='Discriminator for routing.')
    # AnyUrl accepts http(s)://, file://, gmail-thread://, etc.
    # Vault watcher uses file:// for vault-local notes that have no web origin.
    uri: AnyUrl = Field(..., description='Canonical URL of the source.')
    title: str | None = Field(None, description='Title of the source, if known.')
    author_name: str | None = Field(None)
    published_at: str | None = Field(None, description='ISO date YYYY-MM-DD.')
    source_name: str | None = Field(None, description='Outlet (365tomorrows, Clarkesworld, ...).')
    raw_payload: str | None = Field(
        None, description='Raw HTML or markdown body. If HTML, will be normalized.'
    )
    metadata: dict[str, Any] | None = Field(default_factory=dict)


class CaptureResponse(BaseModel):
    source_id: str
    created: bool
    excerpt: str | None = None


# F32 — lifecycle endpoints (obsidian-exocortex-capture plugin). raw_sources
# has no hard delete: thoughts.source_id / content_queue.source_id reference
# it with the default RESTRICT action, so removing a row the moment anything
# cites it would fail — and even where it wouldn't, it would silently orphan
# the citing rows. deleted_at (schema/32_capture_lifecycle.sql) marks a source
# as gone without touching what already points at it.
class CaptureDeleteRequest(BaseModel):
    source_type: str = Field(..., description='Same discriminator used at capture time.')
    uri: AnyUrl = Field(..., description='Canonical URL of the source being removed.')


class CaptureDeleteResponse(BaseModel):
    source_id: str | None = None
    deleted: bool = Field(
        ..., description='False when no matching, still-live row existed — '
                          'idempotent, not an error (re-deleting is a no-op).')


class CaptureRenameRequest(BaseModel):
    source_type: str = Field(..., description='Same discriminator used at capture time.')
    old_uri: AnyUrl = Field(..., description='Current canonical URL on record.')
    new_uri: AnyUrl = Field(..., description='URL the source is now known by.')
    metadata: dict[str, Any] | None = Field(
        None, description='Shallow-merged into existing metadata (e.g. refreshed '
                          'vault_path) — omit to leave metadata untouched.')


class CaptureRenameResponse(BaseModel):
    source_id: str | None = None
    renamed: bool = Field(
        ..., description='False when old_uri had no matching, still-live row — '
                         'idempotent, not an error.')


class BatchCaptureRequest(BaseModel):
    items: list[CaptureRequest] = Field(
        ..., min_length=1, max_length=500,
        description='Chunk size is the CALLER\'s concern (rate limiting, resumability '
                   'across a large first index) — this endpoint just bounds one '
                   'request\'s memory/lock footprint.')


class BatchCaptureResult(BaseModel):
    uri: str
    source_id: str | None = None
    created: bool = False
    excerpt: str | None = None
    error: str | None = Field(
        None, description='Set instead of source_id when this ONE item failed — '
                          'the rest of the batch still runs. A 1600-file first '
                          'index cannot be allowed to die on one malformed file.')


class BatchCaptureResponse(BaseModel):
    results: list[BatchCaptureResult]
    created_count: int
    total: int


class GraphExpandRequest(BaseModel):
    thought_id: str = Field(..., description='UUID of the seed thought.')
    max_hops: int = Field(2, ge=1, le=3, description='Graph expansion depth (1-3).')
    limit: int = Field(20, ge=1, le=50, description='Max neighbors to return.')


class GraphNode(BaseModel):
    id: str
    title: str
    label: str


class GraphEdge(BaseModel):
    source: str
    target: str
    type: str


class GraphExpandResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


# ─────────────────────────── HTML → markdown ───────────────────────────

_TRAFILATURA = None


def _extract_text(payload: str) -> tuple[str, str | None]:
    """HTML → plaintext markdown. Returns (markdown, title_guess).

    Lazy-imports trafilatura so workers without payload normalization don't
    pay the import cost.
    """
    global _TRAFILATURA
    if _TRAFILATURA is None:
        import trafilatura  # type: ignore
        _TRAFILATURA = trafilatura
    if not payload:
        return '', None

    looks_like_html = bool(re.search(r'<\s*(html|body|article|div|p)\b', payload, re.IGNORECASE))
    if not looks_like_html:
        return payload, None

    extracted = _TRAFILATURA.extract(
        payload,
        include_comments=False,
        include_tables=False,
        favor_recall=True,
        output_format='markdown',
    )
    title = None
    try:
        meta = _TRAFILATURA.extract_metadata(payload)
        if meta is not None:
            title = getattr(meta, 'title', None)
    except Exception:  # noqa: BLE001, S110 — failure is ignored on purpose; narrowing would change behavior
        pass
    return (extracted or '').strip(), title


def _excerpt(text: str, max_words: int = EXCERPT_WORDS) -> str | None:
    if not text:
        return None
    words = text.split()
    if len(words) <= max_words:
        return text.strip()
    return ' '.join(words[:max_words]).strip() + '…'


# ─────────────────────────── Auth ───────────────────────────

bearer = HTTPBearer(auto_error=False)


def require_token(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:  # noqa: B008 — FastAPI Depends() default is the framework idiom
    if not CAPTURE_API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='CAPTURE_API_TOKEN not configured on server',
        )
    if creds is None or creds.scheme.lower() != 'bearer':
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Missing bearer token',
            headers={'WWW-Authenticate': 'Bearer'},
        )
    if not secrets.compare_digest(creds.credentials, CAPTURE_API_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Invalid bearer token',
        )


# ─────────────────────────── App ───────────────────────────

app = FastAPI(
    title='Second Brain — Capture API',
    description='F6.1.2 single-ingestion endpoint for content acquisition.',
    version='0.1.0',
)


@app.post('/mcp')
def mcp_dispatch(req: dict, _: None = Depends(require_token)) -> Any:
    """Dynamic MCP tool dispatch for the desktop app."""
    tool = req.get('tool', '')
    args = req.get('args', {}) or {}

    if tool == 'search_thoughts':
        from exocortex.mcp_server import search_thoughts as _fn
        return _fn(**args)

    if tool == 'fetch_today_context':
        return _fetch_today_context()

    if tool == 'get_recent_activity':
        return _get_recent_activity()

    raise HTTPException(status_code=404, detail=f'Unknown tool: {tool}')


def _fetch_today_context() -> dict:
    """Today's meetings with client/project links."""
    return capture_db.fetch_today_context(get_tenant_id())


def _get_recent_activity() -> dict:
    """Action items with due dates for the activity feed."""
    return capture_db.get_recent_activity(get_tenant_id())


@app.get('/stats')
def get_stats():
    """Public stats — no auth required."""
    return capture_db.get_stats()


@app.get('/health')
def health() -> dict[str, Any]:
    """Cheap liveness probe — no DB call."""
    return {'status': 'ok', 'auth_configured': bool(CAPTURE_API_TOKEN)}


@app.get('/health/db')
def health_db(_: None = Depends(require_token)) -> dict[str, Any]:
    """Auth-gated readiness probe — touches the pool."""
    pool = get_pool()
    return {'status': 'ok', 'pool_size': pool.max_size}


@app.get('/health/modules')
def health_modules(response: Response) -> dict[str, Any]:
    """Registry introspection — no auth, no DB. F31-MS-P1.3.

    Reports counts of currently loaded extension-point handlers from the
    module-level Registry singleton. If the registry import or attribute
    access fails, returns HTTP 503 with status=degraded.
    """
    try:
        from exocortex.core.registry import registry as _reg
        counts = {
            'perspectives': len(_reg.perspectives),
            'mcp_tools': len(_reg.mcp_tools),
            'compile_domains': len(_reg.compile_domains),
            'capture_processors': len(_reg.capture_processors),
            'live_sections': len(_reg.live_sections),
            'sinks': len(_reg.sinks),
        }
        return {
            'status': 'ok',
            'registry': counts,
            'total_modules': sum(counts.values()),
        }
    except Exception as exc:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {'status': 'degraded', 'error': f'{type(exc).__name__}: {exc}'}


@app.post('/graph/expand', response_model=GraphExpandResponse)
def graph_expand_endpoint(req: GraphExpandRequest, _: None = Depends(require_token)) -> dict:
    """Graph traversal via edges table (works for thoughts AND entities)."""
    import re
    _UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')

    if not _UUID_RE.fullmatch(req.thought_id):
        raise HTTPException(status_code=400, detail='Invalid UUID')

    seed = req.thought_id
    limit = min(req.limit, 50)

    # 1-hop: direct edges from/to seed
    rows = query(
        """
        SELECT src_id, dst_id, type FROM edges
        WHERE (src_id = %s OR dst_id = %s)
        LIMIT %s
        """,
        seed, seed, limit * 2,
    )

    node_ids: set[str] = {seed}
    edges: list[dict] = []
    seen_edges: set[str] = set()

    for r in rows:
        src = str(r['src_id'])
        dst = str(r['dst_id'])
        etype = r['type']
        ekey = f"{src}|{dst}|{etype}"
        if ekey in seen_edges:
            continue
        seen_edges.add(ekey)
        node_ids.add(src)
        node_ids.add(dst)
        edges.append({'source': src, 'target': dst, 'type': etype})

    # 2-hop if requested and we have room
    if req.max_hops >= 2 and len(edges) < limit:
        hop1_ids = node_ids - {seed}
        if hop1_ids:
            hop1_list = list(hop1_ids)
            rows2 = query(
                """
                SELECT src_id, dst_id, type FROM edges
                WHERE (src_id = ANY(%s::uuid[]) OR dst_id = ANY(%s::uuid[]))
                  AND src_id != %s AND dst_id != %s
                LIMIT %s
                """,
                hop1_list, hop1_list, seed, seed, limit,
            )
            for r in rows2:
                src = str(r['src_id'])
                dst = str(r['dst_id'])
                etype = r['type']
                ekey = f"{src}|{dst}|{etype}"
                if ekey in seen_edges:
                    continue
                seen_edges.add(ekey)
                node_ids.add(src)
                node_ids.add(dst)
                edges.append({'source': src, 'target': dst, 'type': etype})

    # Resolve names for all node IDs
    nodes: list[dict] = []
    info_map: dict[str, dict] = {}

    if node_ids:
        node_list = list(node_ids)
        for r in query(
            "SELECT id, canonical_name, type FROM entities WHERE id = ANY(%s::uuid[])",
            node_list,
        ):
            info_map[str(r['id'])] = {'title': r['canonical_name'], 'type': r['type']}

        missing = node_ids - set(info_map.keys())
        if missing:
            missing_list = list(missing)
            for r in query(
                "SELECT id, metadata, thought_type FROM thoughts WHERE id = ANY(%s::uuid[])",
                missing_list,
            ):
                meta = r.get('metadata') or {}
                info_map[str(r['id'])] = {
                    'title': meta.get('title') or (r.get('thought_type') or 'Thought'),
                    'type': r.get('thought_type') or 'Thought',
                }

    for nid in node_ids:
        info = info_map.get(nid, {})
        nodes.append({
            'id': nid,
            'title': info.get('title', nid[:8]),
            'label': 'Focus' if nid == seed else info.get('type', 'Thought'),
        })

    return {'nodes': nodes, 'edges': edges}


def _do_capture(c, req: CaptureRequest) -> tuple[dict, int]:
    """Single-item capture against an ALREADY-OPEN connection `c`.

    Extracted verbatim from the original inline `/capture` body (F32) so
    `/capture/batch` can share one connection across many items instead of
    opening a pool connection per file. Behaviour is byte-for-byte identical
    to before the split — this is a pure extraction, not a rewrite. Returns
    (response_dict, http_status_code); raises HTTPException for the caller
    to handle (single endpoint lets it propagate, batch endpoint catches it
    per-item so one bad file doesn't abort a 1600-file first index).
    """
    if req.source_type not in ALLOWED_SOURCE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Unknown source_type: {req.source_type}. '
                   f'Allowed: {sorted(ALLOWED_SOURCE_TYPES)}',
        )

    uri_str = str(req.uri)

    # F2.2: a lab deployment accepts only sources on its allowlist.
    from exocortex.source_allowlist import SourceNotAllowed, require_capture
    try:
        require_capture(req.source_type, uri_str)
    except SourceNotAllowed as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f'Source not allowed: {exc}') from exc

    extracted_text = ''
    title_guess = None
    if req.raw_payload:
        try:
            extracted_text, title_guess = _extract_text(req.raw_payload)
        except Exception as exc:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
            # Don't block the capture on extractor errors — keep raw_payload
            # in metadata so the F6.3 processor can retry with a different lib.
            extracted_text = req.raw_payload
            title_guess = None
            print(f'[capture_api] extractor error for {uri_str}: {exc!r}')

    excerpt = _excerpt(extracted_text)
    title = req.title or title_guess

    metadata = dict(req.metadata or {})
    if extracted_text:
        metadata.setdefault('extracted_chars', len(extracted_text))
        metadata.setdefault('excerpt', excerpt)
    if req.raw_payload:
        # Keep raw_payload bounded — F6.3 processor will fetch full content via
        # uri if needed. Anything bigger than 64 KiB is dropped here.
        if len(req.raw_payload) <= 64 * 1024:
            metadata.setdefault('raw_payload', req.raw_payload)
        else:
            metadata.setdefault('raw_payload_truncated', True)
            metadata.setdefault('raw_payload', req.raw_payload[:64 * 1024])

    # Upsert on (tenant_id, source_type, uri). F34: a re-POST at a known uri
    # used to be ON CONFLICT DO NOTHING — a re-edited source was captured
    # once and then invisible to every processor forever after. Now it
    # updates IF AND ONLY IF content_hash (generated from metadata, see
    # schema/34_capture_content_hash.sql) actually differs — an unchanged
    # re-POST still does nothing. `xmax = 0` distinguishes a genuine INSERT
    # from an UPDATE for the `created` field without a second query.
    #
    # metadata = EXCLUDED.metadata on update deliberately replaces the old
    # dict wholesale (not merged) — this drops any `processors` stamp a
    # processor previously wrote there, which is required: a content
    # change must make already_processed() false again so the row gets
    # reprocessed, not permanently skipped.
    row = c.execute(
        '''
        INSERT INTO raw_sources
            (tenant_id, uri, title, author_name, published_at,
             source_name, source_type, metadata)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (tenant_id, source_type, uri) DO UPDATE SET
            title = EXCLUDED.title,
            author_name = EXCLUDED.author_name,
            published_at = EXCLUDED.published_at,
            source_name = EXCLUDED.source_name,
            metadata = EXCLUDED.metadata,
            ingested_at = NOW()
        WHERE raw_sources.content_hash IS DISTINCT FROM EXCLUDED.content_hash
        RETURNING id, (xmax = 0) AS created
        ''',
        (
            TENANT_ID,
            uri_str,
            title,
            req.author_name,
            req.published_at,
            req.source_name,
            req.source_type,
            json.dumps(metadata),
        ),
    ).fetchone()

    if row:
        source_id = str(row['id'])
        created = bool(row['created'])
        # Notify F6.3 listener — fires on a genuine insert AND on a real
        # content change; an unchanged re-POST returns no row above, so
        # this line is never reached for it.
        payload = json.dumps({'source_id': source_id, 'source_type': req.source_type})
        c.execute('SELECT pg_notify(%s, %s)', ('content_acquired', payload))
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    else:
        existing = c.execute(
            'SELECT id FROM raw_sources '
            'WHERE tenant_id = %s AND source_type = %s AND uri = %s',
            (TENANT_ID, req.source_type, uri_str),
        ).fetchone()
        if existing is None:
            # Race condition — should be impossible given autocommit + FK.
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail='ON CONFLICT fired but no existing row found',
            )
        source_id = str(existing['id'])
        created = False
        status_code = status.HTTP_200_OK

    return {'source_id': source_id, 'created': created, 'excerpt': excerpt}, status_code


@app.post('/capture', response_model=CaptureResponse, status_code=status.HTTP_201_CREATED)
def capture(req: CaptureRequest, response: Response, _: None = Depends(require_token)) -> dict:
    with conn() as c:
        result, status_code = _do_capture(c, req)
    response.status_code = status_code
    return result


@app.post('/capture/batch', response_model=BatchCaptureResponse)
def capture_batch(req: BatchCaptureRequest, _: None = Depends(require_token)) -> dict:
    """F32 — bulk ingestion for a first index (~1600 files is the reference
    scale). One connection shared across the whole chunk (autocommit=True on
    the pool, see db/pool.py — each `c.execute()` commits independently, so a
    failure on item N never poisons item N+1's transaction, and a chunk that
    gets interrupted mid-way has already durably committed everything before
    the interruption; the caller/plugin re-POSTs the same chunk and every
    already-captured item is a no-op via the same ON CONFLICT as /capture)."""
    results: list[dict] = []
    created_count = 0
    with conn() as c:
        for item in req.items:
            uri_str = str(item.uri)
            try:
                result, _code = _do_capture(c, item)
            except HTTPException as exc:
                results.append({'uri': uri_str, 'error': str(exc.detail)})
                continue
            except Exception as exc:  # noqa: BLE001 — one bad file must not sink the batch
                results.append({'uri': uri_str, 'error': f'{type(exc).__name__}: {exc}'})
                continue
            if result['created']:
                created_count += 1
            results.append({'uri': uri_str, **result})
    return {'results': results, 'created_count': created_count, 'total': len(req.items)}


@app.post('/capture/delete', response_model=CaptureDeleteResponse)
def capture_delete(req: CaptureDeleteRequest, _: None = Depends(require_token)) -> dict:
    """F32 — mark a source as gone (soft delete, see schema/32_capture_lifecycle.sql).
    Idempotent: deleting an already-deleted or never-existing (source_type, uri)
    returns deleted=False, not an error — a watcher re-sending a delete event
    after a crash must not get a scary 404."""
    with conn() as c:
        row = c.execute(
            '''
            UPDATE raw_sources SET deleted_at = NOW()
            WHERE tenant_id = %s AND source_type = %s AND uri = %s
              AND deleted_at IS NULL
            RETURNING id
            ''',
            (TENANT_ID, req.source_type, str(req.uri)),
        ).fetchone()
    if row is None:
        return {'source_id': None, 'deleted': False}
    return {'source_id': str(row['id']), 'deleted': True}


@app.post('/capture/rename', response_model=CaptureRenameResponse)
def capture_rename(req: CaptureRenameRequest, _: None = Depends(require_token)) -> dict:
    """F32 — same row, new uri (see schema/32_capture_lifecycle.sql: rename is
    a plain UPDATE, no new column needed for it). Renaming keeps the row's id,
    so every thought/edge that already cites this source stays valid — the
    alternative (delete old + capture new) would silently sever that history.
    Only touches LIVE rows (deleted_at IS NULL); renaming something already
    marked gone is not a supported operation — delete-then-recapture is the
    correct sequence for that case."""
    old_uri_str = str(req.old_uri)
    new_uri_str = str(req.new_uri)
    metadata_sql = (
        "metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb" if req.metadata else None
    )
    with conn() as c:
        try:
            if metadata_sql:
                row = c.execute(
                    f'''
                    UPDATE raw_sources SET uri = %s, {metadata_sql}
                    WHERE tenant_id = %s AND source_type = %s AND uri = %s
                      AND deleted_at IS NULL
                    RETURNING id
                    ''',
                    (new_uri_str, json.dumps(req.metadata), TENANT_ID,
                     req.source_type, old_uri_str),
                ).fetchone()
            else:
                row = c.execute(
                    '''
                    UPDATE raw_sources SET uri = %s
                    WHERE tenant_id = %s AND source_type = %s AND uri = %s
                      AND deleted_at IS NULL
                    RETURNING id
                    ''',
                    (new_uri_str, TENANT_ID, req.source_type, old_uri_str),
                ).fetchone()
        except UniqueViolation as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f'new_uri already captured for this source_type: {new_uri_str}',
            ) from exc
    if row is None:
        return {'source_id': None, 'renamed': False}
    return {'source_id': str(row['id']), 'renamed': True}
