# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# exocortex/mcp_server.py — legacy FastMCP server (stdio transport).
#
# 6 MUST-HAVE tools:
#   1. search_thoughts(query_text, top_k)   — pgvector cosine top-K.
#   2. expand_node(thought_id, ...)         — AGE Cypher graph traversal.
#   3. synthesize(perspective_type, key)    — fetch latest active synthesis.
#   4. find_action_items(owner, client, ...) — parse meeting action_items on demand.
#   5. find_contradictions()                — Cypher MATCH (a)-[:contradicts]->(b).
#   6. ask(question, max_hops)              — full GraphRAG (vector+graph+LLM).
#   7. graph_fact_check(text)               — verify claims against graph (F31.4.2).
#
# Opt-in FRP workflow tools (F7.1):
#   8. query_content_queue(filters, limit)  — score-sorted FRP reading queue.
#   9. create_frp_session(content_id, frame, level, context_note)
#  10. append_session_thought(session_id, thought_type, body, entity_links)
#  11. complete_session(session_id, resonance, tags, signal_today)
#  12. add_revisit(session_id, body, materializes_as_url)
#
# F7.2 — generated FRP content (futures-story-generator integration):
#  13. enqueue_generated_frp_story(title, body, ...) — persist generated story
#       to raw_sources + content_queue + frp_source_scored thought.
#
# Transport: stdio (default for Claude Code MCP integration). Run via:
#   python3.12 workers/mcp_server.py
#
# Requires: Python 3.10+ for `mcp` package (Anthropic MCP SDK).
# All long calls use F5.1 GraphRAGOrchestrator (cached via in-memory dict).

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Make sure repo root is importable when launched via stdio from arbitrary cwd.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from exocortex._bootstrap import bootstrap

bootstrap()

from mcp.server.fastmcp import FastMCP

from exocortex.action_items import parse_action_items
from exocortex.db import (
    add_revisit as _db_add_revisit,
)
from exocortex.db import (
    append_session_thought as _db_append_session_thought,
)
from exocortex.db import (
    complete_session as _db_complete_session,
)
from exocortex.db import (
    create_frp_session as _db_create_frp_session,
)
from exocortex.db import (
    query,
    query_one,
)
from exocortex.graph_rag import (
    GraphRAGOrchestrator,
    graph_expand,
    vector_search,
)
from exocortex.settings import get_tenant_id

TENANT_ID = get_tenant_id()

mcp = FastMCP("second-brain")
_orchestrator: GraphRAGOrchestrator | None = None


def _orch() -> GraphRAGOrchestrator:
    """Lazy-init orchestrator (avoids upfront DB connection at import time)."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = GraphRAGOrchestrator(tenant_id=TENANT_ID)
    return _orchestrator


# ─────────────────────────────────────────────────── Helpers ──

def _slug_from_metadata(metadata: dict | None) -> str:
    """Derive Obsidian wikilink slug from a thought's metadata."""
    from exocortex.llm_utils import slug_from_metadata as _fn
    return _fn(metadata)


def _thought_to_payload(row: dict, body_excerpt_chars: int = 300) -> dict:
    meta = row.get('metadata') or {}
    body = row.get('body') or ''
    return {
        'thought_id': str(row['id']),
        'title': meta.get('title') or '',
        'slug': _slug_from_metadata(meta),
        'wikilink': f"[[{_slug_from_metadata(meta)}]]" if _slug_from_metadata(meta) else '',
        'body_excerpt': body[:body_excerpt_chars],
        'similarity': float(row['sim']) if row.get('sim') is not None else None,
        'thought_type': row.get('thought_type'),
    }


def _log_query_telemetry(*, question: str, source: str, node_ids: list[str],
                         method: str, latency_ms: int | None = None,
                         embedding: list[float] | None = None) -> None:
    """Best-effort F28.1 telemetry from MCP retrieval tools. Never raises."""
    try:
        from exocortex.query_log import log_query
        log_query(
            question=question, source=source, tenant_id=TENANT_ID,
            retrieved_node_ids=node_ids, retrieval_method=method,
            latency_ms=latency_ms, question_embedding=embedding,
        )
    except Exception:  # noqa: BLE001, S110 — telemetry must not break MCP tools
        pass


# ─────────────────────────────────────────────── Tool 1: search ──

@mcp.tool()
def search_thoughts(query_text: str, top_k: int = 10) -> list[dict]:
    """Vector search the user's thoughts by semantic similarity (pgvector cosine, HNSW).

    Returns top-K thoughts with title, slug, wikilink, body excerpt (300 chars),
    similarity score (0-1, higher = better). No graph traversal, no LLM call.

    Use for: quick lookup, broad recall, when you just want the raw matching docs.
    Use `ask` instead for synthesized natural-language answers.

    Args:
        query_text: Natural language query in any language (model is multilingual).
        top_k: How many top hits to return (default 10, max 50).
    """
    import time as _time
    _t0 = _time.time()
    top_k = max(1, min(top_k, 50))
    from exocortex.db import get_embedding
    embedding = get_embedding(query_text)
    if embedding is None:
        _log_query_telemetry(question=query_text, source='mcp_search_thoughts',
                             node_ids=[], method='vector',
                             latency_ms=int((_time.time() - _t0) * 1000))
        return []
    # Delegates to graph_rag.vector_search: since the thought_chunks
    # migration, a vault_note document's embedding lives on its chunks, not
    # on the thought itself — this searches both thoughts.embedding
    # (backlog_item/recipe/work_meeting_note) and thought_chunks
    # (vault_note) and returns the parent thought, deduplicated.
    rows = vector_search(TENANT_ID, embedding, top_k)
    payloads = [_thought_to_payload(r) for r in rows]
    _log_query_telemetry(
        question=query_text, source='mcp_search_thoughts',
        node_ids=[str(r['id']) for r in rows], method='vector',
        latency_ms=int((_time.time() - _t0) * 1000), embedding=embedding,
    )
    return payloads


# ──────────────────────────────────────── Tool 2: expand_node ──

@mcp.tool()
def expand_node(thought_id: str, edge_types: list[str] | None = None,
                max_hops: int = 2, limit: int = 10) -> list[dict]:
    """Graph traversal from a thought: AGE Cypher 1-2 hops over typed edges.

    Returns neighbors with edge_type, neighbor_label (Person/Client/Project/etc),
    neighbor_id (UUID), and hops count.

    Use for: discovering related meetings/people/decisions starting from a known
    thought_id (typically obtained from `search_thoughts` or `ask` sources).

    Args:
        thought_id: UUID of the seed thought.
        edge_types: Optional allow-list. Defaults to all 13 reasoning edges
            (attended_meeting, decided_in, mentions_person, classified_as_*,
            supports, contradicts, supersedes, derived_from, related_to,
            broader_than, narrower_than, addresses_problem).
        max_hops: 1 or 2 (default 2). Higher = wider neighborhood, more noise.
        limit: max neighbors returned (default 10).
    """
    neighbors_dict = graph_expand([thought_id], max_hops=max_hops, limit_per_seed=limit)
    out = neighbors_dict.get(thought_id, [])
    if edge_types:
        allowed = set(edge_types)
        out = [n for n in out if n['edge_type'] in allowed]
    return out


# ──────────────────────────────────────── Tool 3: synthesize ──

@mcp.tool()
def synthesize(perspective_type: str, perspective_key: str) -> dict:
    """Fetch the latest active synthesis (5 sections) for a perspective.

    Re-uses F4 syntheses table — NO new LLM call. Returns the structured
    snapshot generated by the daily cron (current_state, recent_decisions,
    open_problems, ownership, next_steps).

    Use for: "what's the state of acme?" → synthesize('client', 'acme').
    Use `ask` instead for free-form questions.

    Args:
        perspective_type: client | project | person | monthly | tag | type.
        perspective_key: e.g. 'acme', 'acme-omniportal', 'jkowalski',
            '2026-04', 'wcag', 'wks'. Must match an existing synthesis.

    Returns: {perspective_type, perspective_key, content, generated_at,
        synthesis_id, model, llm_cost_usd} or {error: '...'} when not found.
    """
    sql = (
        "SELECT id::text AS id, content, generated_at, model, llm_cost_usd, "
        "       prompt_version, source_thought_ids "
        "FROM syntheses "
        "WHERE tenant_id = %s AND perspective_type = %s AND perspective_key = %s "
        "  AND superseded_by IS NULL "
        "ORDER BY generated_at DESC LIMIT 1"
    )
    row = query_one(sql, TENANT_ID, perspective_type, perspective_key)
    if not row:
        return {
            'error': f"no active synthesis for ({perspective_type}, {perspective_key})",
            'perspective_type': perspective_type,
            'perspective_key': perspective_key,
        }
    src_ids = row.get('source_thought_ids') or []
    return {
        'perspective_type': perspective_type,
        'perspective_key': perspective_key,
        'synthesis_id': row['id'],
        'content': row['content'],
        'generated_at': row['generated_at'].isoformat() if row.get('generated_at') else None,
        'model': row.get('model'),
        'llm_cost_usd': float(row['llm_cost_usd']) if row.get('llm_cost_usd') is not None else None,
        'source_thought_count': len(src_ids),
    }


# ─────────────────────────────────────── Tool 4: action items ──

@mcp.tool()
def find_action_items(owner: str | None = None, client: str | None = None,
                      status: str = 'open', due_before: str | None = None,
                      limit: int = 50) -> list[dict]:
    """Parse Fireflies action_items from meetings. Optional filters.

    Iterates over meetings (filtered by client when provided), parses each
    meeting's `metadata.action_items` markdown via the F2.3 deterministic regex
    parser. Returns flat list of {owner_name, owner_slug, content, status,
    due_date, completion_date, source_thought_id, source_wikilink}.

    Args:
        owner: Match owner_slug case-insensitively. NOTE the slug convention
            for action_items is the F2.3 polish-aware slugify of the display
            name, NOT the email-derived person-page slug. Examples:
            'vault-owner' (not 'exocortex_user'), 'adam-nowicki' (not
            'jkowalski'), 'radoslaw-wilk' (not 'bwojcik'). None = all owners.
        client: Filter meetings by classified_as_client (e.g. 'acme', 'betabank').
            None = all meetings.
        status: 'open' | 'done' | 'all' (default 'open').
        due_before: YYYY-MM-DD string. Returns only items with due_date <= this.
        limit: max items returned (default 50).
    """
    # Build meeting-selection SQL.
    # Param order matters: psycopg substitutes positional %s in textual order,
    # so JOIN params (which appear before WHERE) must come first.
    join_sql = ''
    join_params: list[Any] = []
    if client:
        join_sql = (
            "JOIN edges e ON e.src_id = t.id AND e.type = 'classified_as_client' "
            "JOIN entities ent ON ent.id = e.dst_id AND ent.canonical_name = %s "
        )
        join_params.append(client)
    sql = (
        "SELECT t.id, t.body, t.metadata FROM thoughts t "
        + join_sql
        + "WHERE t.tenant_id = %s AND t.thought_type = 'work_meeting_note'"
    )
    rows = query(sql, *join_params, TENANT_ID)

    out: list[dict] = []
    owner_lower = owner.lower() if owner else None
    for r in rows:
        meta = r.get('metadata') or {}
        items = parse_action_items(meta, source_thought_id=str(r['id']))
        slug = _slug_from_metadata(meta)
        wikilink = f"[[{slug}]]" if slug else ''
        for it in items:
            if status != 'all' and it.status != status:
                continue
            if owner_lower and it.owner_slug.lower() != owner_lower:
                continue
            if due_before and it.due_date and it.due_date > due_before:
                continue
            payload = it.to_dict()
            payload['source_wikilink'] = wikilink
            out.append(payload)
            if len(out) >= limit:
                return out
    return out


# ─────────────────────────────────── Tool 5: contradictions ──

@mcp.tool()
def find_contradictions() -> list[dict]:
    """Find unresolved `contradicts` edges in the graph.

    Note (F5.2 MVP): the `contradicts` edge type is in the ENUM but not yet
    populated by the synthesizer. Empty result is expected currently — will
    light up in F6+ when synthesis emits contradiction edges.

    Returns: [{src_id, dst_id, src_type, dst_type, created_at}, ...].
    """
    sql = (
        "SELECT src_id::text AS src_id, src_type, "
        "       dst_id::text AS dst_id, dst_type, "
        "       created_at, resolved "
        "FROM edges "
        "WHERE tenant_id = %s AND type = 'contradicts' AND resolved IS NOT TRUE "
        "ORDER BY created_at DESC"
    )
    rows = query(sql, TENANT_ID)
    return [
        {
            'src_id': r['src_id'], 'src_type': r['src_type'],
            'dst_id': r['dst_id'], 'dst_type': r['dst_type'],
            'created_at': r['created_at'].isoformat() if r.get('created_at') else None,
            'resolved': bool(r.get('resolved')),
        }
        for r in rows
    ]


# ────────────────────────────────────────────── Tool 6: ask ──

@mcp.tool()
def ask(question: str, max_hops: int = 2, top_k: int = 10) -> dict:
    """Full GraphRAG: embed → vector → graph expand → RRF → LLM synthesis.

    Returns a synthesized natural-language answer (Polish, by default — the
    system prompt is PL) with `[[meeting-slug]]` wikilink citations, plus the
    list of source thoughts used.

    This is the highest-level tool — when in doubt, use this. For raw retrieval
    without LLM, use `search_thoughts` instead.

    Args:
        question: The natural-language question.
        max_hops: graph expansion depth (1 or 2, default 2).
        top_k: vector search top-K (default 10).

    Returns: {answer, sources, cost_usd, latency_ms, cache_hit}.
    """
    ans = _orch().answer(question, max_hops=max_hops, top_k_vector=top_k,
                         query_source='claude_desktop_mcp')
    return {
        'answer': ans.response,
        'sources': [
            {
                'thought_id': s.thought_id,
                'title': s.title,
                'score': s.score,
                'rank_vector': s.rank_vector,
                'rank_graph': s.rank_graph,
                'edge_path': s.edge_path[:3],
                'provenance': s.provenance,
            }
            for s in ans.sources
        ],
        'cost_usd': ans.cost_usd,
        'latency_ms': ans.latency_ms,
        'cache_hit': ans.cache_hit,
        'usage': ans.usage,
    }


# ─────────────────────────────── Tool 7: graph_fact_check ──

@mcp.tool()
def graph_fact_check(text: str) -> list[dict]:
    """Verify factual claims in text against the knowledge graph.

    Pipeline: LLM extracts atomic claims → pgvector candidates per claim →
    AGE / `edges` lookup for supports / contradicts / decided_in → verdict.

    Returns a list of per-claim records:
        {'claim': str,
         'verdict': 'supported' | 'contradicts' | 'no_evidence',
         'evidence_edges': [{'src_id', 'dst_id', 'edge_type'}, ...],
         'sources':       [{'thought_id', 'title'}, ...]}

    Empty list when the text has no verifiable claims or claim extraction fails.
    """
    from exocortex.graph_fact_check import graph_fact_check as _gfc
    return _gfc(text)


# ─────────────────────────────────────── F7.1: FRP workflow ──

_FRP_THOUGHT_TYPES = {
    'frp_scenario', 'frp_friction', 'frp_recognition',
    'frp_reflection', 'frp_impulse', 'frp_revisit',
}


@mcp.tool()
def query_content_queue(min_score: int | None = None,
                        domain: str | None = None,
                        source_type: str | None = None,
                        status: str = 'queued',
                        limit: int = 10) -> list[dict]:
    """Score-sorted FRP reading queue (content_queue). Returns items DESC by score_total.

    Each row includes the joined raw_source metadata (uri, title, source_name,
    source_type, author_name, published_at) plus the FRP score breakdown
    (accessibility, horizon, consequence, total) and ai_tags JSON
    (typically {domain, frame, suggested_prompt_key} populated by the F6.3
    frp_source scorer).

    Args:
        min_score: filter score_total >= N (0-9, default None = no filter).
        domain: filter ai_tags->>'domain' (e.g. 'work', 'tech', 'culture').
        source_type: filter raw_sources.source_type (e.g. 'rss-frp', 'arxiv').
        status: 'queued' | 'reading' | 'used' | 'skipped' | 'all' (default 'queued').
        limit: max rows (default 10, max 50).
    """
    limit = max(1, min(limit, 50))
    where = ['cq.tenant_id = %s']
    params: list[Any] = [TENANT_ID]
    if status != 'all':
        where.append('cq.status = %s')
        params.append(status)
    if min_score is not None:
        where.append('cq.score_total >= %s')
        params.append(min_score)
    if domain:
        where.append("cq.ai_tags->>'domain' = %s")
        params.append(domain)
    if source_type:
        where.append('rs.source_type = %s')
        params.append(source_type)
    sql = (
        "SELECT cq.id::text AS content_id, cq.source_id::text AS source_id, "
        "       cq.score_accessibility, cq.score_horizon, cq.score_consequence, "
        "       cq.score_total, cq.ai_tags, cq.suggested_prompt, cq.scenario_sentence, "
        "       cq.status, cq.queued_at, "
        "       rs.uri, rs.title, rs.source_name, rs.source_type, "
        "       rs.author_name, rs.published_at "
        "FROM content_queue cq "
        "LEFT JOIN raw_sources rs ON rs.id = cq.source_id "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY cq.score_total DESC NULLS LAST, cq.queued_at DESC "
        "LIMIT %s"
    )
    params.append(limit)
    rows = query(sql, *params)
    out: list[dict] = []
    for r in rows:
        out.append({
            'content_id': r['content_id'],
            'source_id': r['source_id'],
            'uri': r.get('uri'),
            'title': r.get('title'),
            'source_name': r.get('source_name'),
            'source_type': r.get('source_type'),
            'author_name': r.get('author_name'),
            'published_at': r['published_at'].isoformat() if r.get('published_at') else None,
            'score': {
                'accessibility': r.get('score_accessibility'),
                'horizon': r.get('score_horizon'),
                'consequence': r.get('score_consequence'),
                'total': r.get('score_total'),
            },
            'ai_tags': r.get('ai_tags') or {},
            'suggested_prompt': r.get('suggested_prompt'),
            'scenario_sentence': r.get('scenario_sentence'),
            'status': r.get('status'),
            'queued_at': r['queued_at'].isoformat() if r.get('queued_at') else None,
        })
    return out


@mcp.tool()
def create_frp_session(content_id: str, frame: str, level: int,
                       context_note: str | None = None) -> dict:
    """Open a new FRP session anchored to a queued content item.

    Per docs/frp-protocol.md: each reading instantiates exactly one session.
    The session is the graph anchor — all subsequent thoughts (scenario,
    friction, recognition, reflection, impulse, revisit) attach to it via
    `session_contains` edges.

    Args:
        content_id: UUID of the content_queue row (from query_content_queue).
        frame: 'A' (Adaptation) | 'B' (Bridging) | 'C' (Catalysis) — which
            of the 3 FRP frames the reader picked for this session.
        level: 1 | 2 | 3 — depth tier (L1 quick scan, L2 standard, L3 deep).
        context_note: optional one-sentence current professional context.

    Returns: {session_id} or {error}.
    """
    if frame not in ('A', 'B', 'C'):
        return {'error': f"frame must be one of A,B,C — got {frame!r}"}
    if level not in (1, 2, 3):
        return {'error': f"level must be 1, 2, or 3 — got {level!r}"}
    res = _db_create_frp_session(
        content_id=content_id, frame=frame, level=level,
        context_note=context_note, tenant_id=TENANT_ID,
    )
    return {'session_id': str(res['session_id'])}


@mcp.tool()
def append_session_thought(session_id: str, thought_type: str, body: str,
                           entity_links: list[dict] | None = None) -> dict:
    """Append a thought to a FRP session (auto-creates session_contains edge).

    Each FRP step (scenario / friction / recognition / reflection / impulse /
    revisit) is one thought row. The session_contains edge attaches it to
    its session anchor. Optional entity_links create typed edges from the
    thought to canonical entities (people, clients, projects, concepts) —
    F7.4 will use this to emit signals_domain edges for cross-domain links.

    Args:
        session_id: UUID of the open frp_session.
        thought_type: one of frp_scenario, frp_friction, frp_recognition,
            frp_reflection, frp_impulse, frp_revisit.
        body: the user's own text for this step (PL or EN).
        entity_links: optional list of {entity_canonical_name, entity_type,
            edge_type} dicts. Each one upserts an entity row and creates a
            thought→entity edge. Example: [{'entity_canonical_name': 'acme',
            'entity_type': 'client', 'edge_type': 'mentions_client'}].

    Returns: {thought_id} or {error}.
    """
    if thought_type not in _FRP_THOUGHT_TYPES:
        return {
            'error': f"thought_type must be one of {sorted(_FRP_THOUGHT_TYPES)} "
                     f"— got {thought_type!r}",
        }
    res = _db_append_session_thought(
        session_id=session_id, thought_type=thought_type, body=body,
        entity_links=entity_links, tenant_id=TENANT_ID,
    )
    return {'thought_id': str(res['thought_id'])}


@mcp.tool()
def complete_session(session_id: str, resonance: int,
                     tags: dict | None = None,
                     signal_today: bool = False) -> dict:
    """Finalise a FRP session: record resonance, schedule 48h revisit, mark queue 'used'.

    Per docs/frp-protocol.md step 5 ("Resonance Loop"): a finished session
    needs a 1-5 resonance score. complete_session also sets
    revisit_due = (NOW + 48h)::date so the daily revisit cron can surface it,
    and updates the linked content_queue row's ai_tags + status='used'.

    Args:
        session_id: UUID of the active session.
        resonance: 1 (no signal) to 5 (strong signal) — required.
        tags: optional override / supplement for content_queue.ai_tags
            (e.g. {'domain': 'work', 'frame': 'B'}). Defaults to {}.
        signal_today: when True, marks every session_contains thought with
            metadata.signal_today='true' (for the "something striking stuck
            with me today" capture flow).

    Returns: {ok, session_id, revisit_due} or {error}.
    """
    if resonance not in (1, 2, 3, 4, 5):
        return {'error': f"resonance must be 1-5 — got {resonance!r}"}
    _db_complete_session(
        session_id=session_id, resonance=resonance, tags=tags or {},
        signal_today=signal_today, tenant_id=TENANT_ID,
    )
    row = query_one(
        'SELECT revisit_due, status FROM frp_sessions WHERE id = %s',
        session_id,
    )
    # Auto-compile the FRP wiki so the session shows up immediately in
    # wiki/frp/sessions.md after protocol close (instead of waiting for the daily cron
    # 04:00 UTC). ~2-3s overhead, defensive try/except — DB state is the
    # source of truth, a compile failure must NOT roll back session close.
    compile_status = 'skipped'
    try:
        from exocortex.wiki_compiler import compile_frp_module
        compile_frp_module(TENANT_ID, since=None)
        compile_status = 'ok'
    except Exception as exc:  # noqa: BLE001
        compile_status = f'failed: {exc!s}'

    return {
        'ok': True,
        'session_id': session_id,
        'revisit_due': row['revisit_due'].isoformat() if row and row.get('revisit_due') else None,
        'status': row.get('status') if row else None,
        'wiki_compile': compile_status,
    }


@mcp.tool()
def enqueue_generated_frp_story(title: str, body: str,
                                eft_anchor: str | None = None,
                                year: int | None = None,
                                role: str | None = None,
                                situation: str | None = None,
                                domain: str | None = None,
                                frame: str = 'B',
                                suggested_prompt_key: str = 'P2.1') -> dict:
    """Persist a futures-story-generator output as a curated FRP queue item.

    Used by the `futures-story-generator` agent (`.claude/agents/`) so that
    Claude-generated Business Sci-Fi stories enter the same content_queue
    that RSS-acquired SF lands in. Curated → max-score (3/3/3 = 9 total),
    no LLM scoring round trip.

    Creates three rows in one call:
    - `raw_sources` with `source_type='generated-frp'` (idempotent ON CONFLICT
      on (tenant_id, source_type, uri) — uri is a synthetic
      `urn:generated-frp:{slug}` token).
    - `content_queue` with score 3/3/3 + `ai_tags` carrying frame/domain/anchor.
    - `frp_source_scored` thought (so wiki_compiler picks it up alongside
      RSS-derived FRP sources) plus the standard `acquired_from` edge.

    Args:
        title: short story title (used as thought H1 + raw_sources.title).
        body: full story text (~280-320 words for Halicki Practical Futures).
        eft_anchor: kebab-case Polish keyword (the Futures Gradient index key).
        year, role, situation, domain: optional Halicki story metadata
            mirrored into the thought metadata for downstream synthesis.
        frame: A | B | C — defaults to 'B' (Bridging) which is the typical
            Halicki Business Sci-Fi register.
        suggested_prompt_key: prompt id from docs/reflection-prompts.md
            (P1.1, P2.1, P3.3, ...). Defaults to 'P2.1'.

    Returns: {content_id, source_id, thought_id, uri} or {error}.
    """
    if frame not in ('A', 'B', 'C'):
        return {'error': f"frame must be one of A,B,C — got {frame!r}"}
    if not title or not body:
        return {'error': "title and body are required"}

    import hashlib
    import json as _json

    from exocortex.db import conn
    from exocortex.processors._common import emit_thought_for_source

    # Synthetic stable URI — keeps idempotency via UNIQUE (tenant, source_type, uri).
    digest = hashlib.sha256(body.encode('utf-8')).hexdigest()[:16]
    uri = f'urn:generated-frp:{digest}'

    # Upsert raw_source (ON CONFLICT DO NOTHING then SELECT).
    with conn() as c:
        c.execute(
            'INSERT INTO raw_sources (tenant_id, uri, source_type, title, '
            '  source_name, metadata) '
            'VALUES (%s, %s, %s, %s, %s, %s::jsonb) '
            'ON CONFLICT (tenant_id, source_type, uri) DO NOTHING',
            (TENANT_ID, uri, 'generated-frp', title, 'futures-story-generator',
             _json.dumps({
                 'eft_anchor': eft_anchor, 'year': year, 'role': role,
                 'situation': situation, 'domain': domain,
             })),
        )
        rs = c.execute(
            'SELECT id FROM raw_sources WHERE tenant_id = %s AND source_type = %s '
            'AND uri = %s',
            (TENANT_ID, 'generated-frp', uri),
        ).fetchone()
    source_id = str(rs['id'])

    frp_score = {
        'accessibility': 3, 'horizon': 3, 'consequence': 3,
        'frame': frame, 'suggested_prompt_key': suggested_prompt_key,
    }

    # Upsert content_queue (idempotent — one queue row per generated story).
    with conn() as c:
        existing = c.execute(
            'SELECT id FROM content_queue WHERE tenant_id = %s AND source_id = %s '
            'LIMIT 1',
            (TENANT_ID, source_id),
        ).fetchone()
        if existing:
            content_id = str(existing['id'])
        else:
            cq = c.execute(
                'INSERT INTO content_queue (tenant_id, source_id, status, ai_tags, '
                '  score_accessibility, score_horizon, score_consequence, '
                '  suggested_prompt) '
                'VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s) '
                'RETURNING id',
                (TENANT_ID, source_id, 'queued',
                 _json.dumps({**frp_score, 'eft_anchor': eft_anchor,
                              'domain': domain}),
                 3, 3, 3, suggested_prompt_key),
            ).fetchone()
            content_id = str(cq['id'])

    # Emit the frp_source_scored thought (re-use processor helper for the
    # acquired_from edge + extracted_tags wiring).
    body_for_thought = (
        f'# {title}\n'
        f'Source: futures-story-generator (generated-frp)\n\n'
        f'## Score (curated)\n'
        f'**FRP score**: accessibility=3/3, horizon=3/3, consequence=3/3. '
        f'**Frame**: {frame}. **Suggested prompt**: {suggested_prompt_key}.\n'
        f"_Curated max score — bypasses LLM scoring._\n\n"
        f'## Story\n{body}'
    )
    extracted_tags = {
        'extracted_at': __import__('datetime').datetime.now(
            __import__('datetime').timezone.utc).isoformat(),
        'extracted_by': 'futures-story-generator',
        'topic': [],
        '_frp_score': frp_score,
    }
    thought_id = emit_thought_for_source(
        source_id=source_id, body=body_for_thought,
        thought_type='frp_source_scored', domain='frp',
        metadata={
            'title': title, 'uri': uri, 'frp_score': frp_score,
            'eft_anchor': eft_anchor, 'year': year, 'role': role,
            'situation': situation, 'story_domain': domain,
        },
        extracted_tags=extracted_tags,
    )

    return {
        'content_id': content_id,
        'source_id': source_id,
        'thought_id': str(thought_id),
        'uri': uri,
    }


@mcp.tool()
def add_revisit(session_id: str, body: str,
                materializes_as_url: str | None = None) -> dict:
    """Add a revisit thought to a session (typically 48h after completion).

    Per docs/frp-protocol.md: the revisit captures whether the original
    impulse held, mutated, or fizzled. Inserts a frp_revisit thought,
    emits a `revisits` edge thought→session, updates session.status to
    'revisited' and revisited_at=NOW. When materializes_as_url is given
    (the impulse turned into a real artifact — blog post, PR, deck),
    creates a raw_source row and a `materializes_as` edge thought→raw_source.

    Args:
        session_id: UUID of the original frp_session.
        body: user's revisit reflection text.
        materializes_as_url: optional URL of the artifact the impulse became.

    Returns: {thought_id} or {error}.
    """
    res = _db_add_revisit(
        session_id=session_id, body=body,
        materializes_as_url=materializes_as_url, tenant_id=TENANT_ID,
    )
    return {'thought_id': str(res['thought_id'])}


# ───────────────────────────────────── F15-R.3 promotion tools ──
# WRITE authorization: these tools modify the vault (create/delete files
# under `_ Second Brain/backlog/_second-brain/manual/`). Second precedent
# after the FRP write tools (create_frp_session / append_session_thought).
# Deterministic / zero-LLM — implementation lives in workers.promotion_lib.


@mcp.tool()
def promote_action_items(meeting_slug: str, parent_topic: str,
                         item_descriptions: list[str],
                         suggested_slug: str | None = None,
                         priority: str = 'MED') -> dict:
    """Promote N action items from a meeting page to a backlog stub.

    Creates one parent stub + N child stubs in
    `_ Second Brain/backlog/_second-brain/manual/`. Each child carries a
    `source_fingerprint` so wiki_compiler hides the original `[ ]` line from
    TODO views (F15.3). Cross-meeting dedupe: when a parent stub with the
    same `parent_topic` already exists under `suggested_slug`, the meeting
    is appended to its `source_meetings` and only children with new
    fingerprints are added.

    Args:
        meeting_slug: meeting filename without `.md`
            (e.g. `2026-02-02--initech-game-briefing--8b321662`).
        parent_topic: human-readable title for the parent stub.
        item_descriptions: text of each `[ ]`/`[x]` line you want to
            promote. Each MUST match a line in the meeting page after
            normalization (date markers stripped, whitespace collapsed) —
            mismatches raise ValueError.
        suggested_slug: optional override; defaults to slugify(parent_topic).
            Numeric suffix (`-2`, `-3`) is appended on conflict with another
            parent_topic.
        priority: 'LOW' | 'MED' | 'HIGH' (default 'MED').

    Returns: {parent_id, parent_path, children_paths, fingerprints,
        cross_meeting_update, skipped_existing?}.

    Raises:
        ValueError: empty descriptions / unknown priority / description not
            found in the meeting page.
        FileNotFoundError: meeting page missing.

    F11.4 invariant: this tool NEVER modifies wiki/work/meetings/*.md.
    """
    from exocortex.promotion_lib import create_promotion_stubs
    return create_promotion_stubs(
        meeting_slug=meeting_slug, parent_topic=parent_topic,
        item_descriptions=item_descriptions, suggested_slug=suggested_slug,
        priority=priority,
    )


@mcp.tool()
def unpromote(stub_id: str) -> dict:
    """Delete a promotion stub. Items reappear in TODO views on next compile.

    Args:
        stub_id: either bare slug (`initech-game-q2-roadmap`) or full id
            (`manual-initech-game-q2-roadmap`). Child ids look like
            `…-c1` / `manual-…-c1`. Deleting a parent cascades to every
            child; deleting a child only removes that file and trims the
            parent's `children:` list.

    Returns: {deleted_paths: [...], kind: 'parent' | 'child' | 'missing'}.
    """
    from exocortex.promotion_lib import delete_promotion_stubs
    return delete_promotion_stubs(stub_id)


@mcp.tool()
def list_promoted(meeting_slug: str | None = None,
                  parent_only: bool = False) -> list[dict]:
    """Enumerate promotion stubs currently in `manual/`.

    Args:
        meeting_slug: keep only stubs whose `source_meeting(s)` references
            this slug (parent's list or child's single value).
        parent_only: drop child stubs from the result.

    Returns: [{stub_id, slug, kind, title, status, priority,
        source_meetings, parent, source_fingerprint, path}].
    """
    from exocortex.promotion_lib import list_promotion_stubs
    return list_promotion_stubs(
        meeting_slug=meeting_slug, parent_only=parent_only)




# ── F19 — Live Sections UI ──────────────────────────────────────────────

@mcp.tool()
def list_live_sections() -> list[dict]:
    """List all live sections with their state.

    Returns a list of dicts: {id, file, section, active, last_run, triggers, status}.
    """
    from exocortex.live_sections import scan_all_live_sections
    sections = scan_all_live_sections()
    return [
        {
            'id': s['section_id'],
            'file': s.get('file_path', ''),
            'section': s.get('section', ''),
            'active': s.get('active', True),
            'last_run': s.get('lastRunAt', ''),
            'status': s.get('last_status', '?'),
            'triggers': [
                {'type': t.get('type', '?'),
                 'detail': t.get('expression') or t.get('match') or
                           (f'{t.get("start", t.get("startTime", ""))}-{t.get("end", t.get("endTime", ""))}')}
                for t in s.get('triggers', [])
            ],
        }
        for s in sections
    ]


@mcp.tool()
def trigger_live_section(section_id: str) -> dict:
    """Run a live section immediately (manual trigger).

    Args:
        section_id: section ID (e.g. 'home-news-pulse')

    Returns:
        {section_id, status, file, error}
    """
    from exocortex.live_sections import run_live_section_by_id
    return run_live_section_by_id(section_id)


# ──────────────────────────────────────────── Tool: gap_analysis ──

@mcp.tool()
def gap_analysis(
    scope: list[str] | None = None,
    type: str | None = None,
    max_results: int = 20,
) -> list[dict]:
    """Return knowledge gaps detected in the graph (F31.5.2).

    Runs all four F31.5.1 detectors:
      - cluster-no-synth: dense tag clusters lacking syntheses
      - no-decision: old observations/findings with no decision edge
      - contradiction-unresolved: open `contradicts` edges
      - stale-orphan: old weakly-connected thoughts

    Args:
        scope: Optional tag/domain filter (e.g. ["globex"]). Keeps gaps whose
            thought_ids overlap with thoughts tagged with any of these tags
            (read from `thoughts.metadata->'tags'`). If None, full graph.
        type: Optional filter — one of:
            cluster-no-synth | no-decision | contradiction-unresolved | stale-orphan
        max_results: Max gaps per detector (default 20).

    Returns:
        List of Gap dicts: {type, title, thought_ids, age_days, suggested_action, meta}
    """
    import time as _time

    from exocortex.workers.gap_queries import run_all_detectors

    _t0 = _time.time()
    gaps: list[dict] = [dict(g) for g in run_all_detectors(TENANT_ID, max_results=max_results)]

    if type:
        gaps = [g for g in gaps if g['type'] == type]

    if scope:
        scoped_ids: set[str] = set()
        for tag in scope:
            rows = query(
                "SELECT id::text AS thought_id FROM thoughts "
                "WHERE tenant_id = %s "
                "  AND superseded_by IS NULL "
                "  AND jsonb_typeof(metadata->'tags') = 'array' "
                "  AND metadata->'tags' ? %s",
                TENANT_ID, tag,
            ) or []
            scoped_ids.update(r['thought_id'] for r in rows)
        gaps = [g for g in gaps if any(tid in scoped_ids for tid in g['thought_ids'])]

    all_ids: list[str] = []
    for g in gaps:
        all_ids.extend(g.get('thought_ids') or [])
    _log_query_telemetry(
        question=f'gap_analysis(scope={scope},type={type})',
        source='mcp_gap_analysis', node_ids=all_ids, method='gap_detectors',
        latency_ms=int((_time.time() - _t0) * 1000),
    )
    return gaps


# ────────────────────────────────────────────────────── main ──

if __name__ == '__main__':
    # FastMCP stdio transport — Claude Code launches us as a subprocess and
    # speaks JSON-RPC over stdin/stdout. Logs go to stderr (FastMCP default).
    mcp.run()
