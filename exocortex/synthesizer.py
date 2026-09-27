# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/synthesizer.py — F4.2: per-perspective LLM synthesis (5 sections).
#
# For a perspective (client/project/person/monthly/tag/type) gather source thoughts
# and synthesize a structured 5-section JSON: current_state, recent_decisions,
# open_problems, ownership, next_steps. Append-only: each call writes a new row
# to `syntheses` and supersedes the previous active row for that (perspective_type,
# perspective_key, prompt_version) tuple.
#
# Idempotency: input_hash = SHA256(perspective_type + key + prompt_version
#   + sorted source thought ids + per-thought body_hash). If unchanged → no-op.
#
# Edges-aware (F4.2.4): synth fetches edges referencing source thoughts. Currently
# edges=0; gracefully falls back to thought metadata + extracted_tags. Future-ready.
#
# F3 lessons applied:
#   1. Defensive normalizer at LLM-output reconcile boundary (`_coerce_synthesis`).
#   2. Per-call cost reported via `estimate_cost_usd` (warm-cache marginal vs cold).
#   3. Idempotency hash → re-runs are no-op when nothing changed.

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from exocortex._bootstrap import bootstrap
from exocortex.db import conn, get_tenant_id, query, query_one, _emit_synthesis_edges

logger = logging.getLogger(__name__)

bootstrap()

# Retained for log strings; actual model is selected by llm_router config.
LLM_MODEL = 'claude-haiku-4-5-20251001'
PROMPT_VERSION = 1  # bump → re-LLM all syntheses (input_hash mismatch)
THOUGHT_TYPE = 'work_meeting_note'
TENANT_ID = get_tenant_id()

PERSPECTIVE_TYPES = (
    'client', 'project', 'person', 'monthly', 'tag', 'type',
    # F7.3 — FRP perspectives (source thoughts: thought_type LIKE 'frp_%')
    'frp_per_frame', 'frp_per_domain', 'frp_evolution_timeline',
    'frp_per_resonance', 'frp_monthly',
    # F8.8.x.B — newsletter cluster synthesis (one per news_topic_clusters.yaml cluster).
    # perspective_key = cluster slug. Source thoughts: thought_type='newsletter_synthesis'
    # whose extracted_tags.topic intersects cluster.topics list.
    'news_cluster',
    # F31.1.1 — daily night-shift briefing. Source data is injected by the
    # orchestrator (F31.1.3) via SynthContext.inputs, not selected from `thoughts`.
    'night_shift_briefing',
    # F31.5.2 — weekly Gap Radar synthesis. Source data = output of
    # `gap_queries.run_all_detectors()` formatted as pseudo-thoughts.
    'gap_radar',
    # Corpus perspectives (source: vault_note / backlog_item,
    # NOT work_meeting_note). Own prompt + own tool schema, not the
    # meeting-shaped 5-section one.
    'area_digest', 'backlog_health',
)

# Trigger thresholds — F4.2.5 + F7.3 + F8.8.x.B + F29.4
THRESHOLDS = {
    'client': 3,
    'project': 3,
    'person': 5,
    'monthly': 8,
    'tag': 5,
    'type': 1,
    # FRP — counted in *thoughts* (typically 4-6 thoughts per session)
    'frp_per_frame': 5,
    'frp_per_domain': 5,
    'frp_evolution_timeline': 10,
    'frp_per_resonance': 5,
    'frp_monthly': 5,
    # News cluster — counted in newsletter_synthesis thoughts
    'news_cluster': 3,
    # F31.1.1 — input is orchestrator-injected dict, single pseudo-thought
    'night_shift_briefing': 1,
    # F31.5.2 — gap detectors always return ≥0 gaps; even a single gap is worth
    # surfacing in the weekly briefing.
    'gap_radar': 1,
    # Corpus perspectives. area_digest mirrors client/project
    # (order of magnitude 3); backlog_health is higher because the backlog
    # has more noise per item.
    'area_digest': 3,
    'backlog_health': 10,
}

# FRP thought types (kept in sync with workers/mcp_server.py:_FRP_THOUGHT_TYPES
# + frp_source_scored from F6.3 frp_source processor).
# Passed as a parameter (not inlined) — psycopg3 forbids stray `%` in SQL literal.
_FRP_LIKE_PATTERN = r'frp\_%'

# Truncation budget for compact meeting block in user prompt.
# Action items alone for a meaty Tyrell meeting run ~1500 chars; with overview
# + key_points + header a full block is typically 3-5k chars. Keep most blocks
# intact (cap 4500) and the total prompt under ~120k chars (~30k tokens).
# claude-haiku-4-5 200k context — leaves comfortable headroom for system prompt.
MAX_MEETING_CHARS = 4500
MAX_USER_PROMPT_CHARS = 120_000

# LLM client is owned by llm_router; nothing local to instantiate.


# ───────────────────────────────────────────────── Result dataclass ──

@dataclass
class SynthesisResult:
    perspective_type: str
    perspective_key: str
    status: str  # 'ok' | 'skipped' | 'below-threshold' | 'no-thoughts' | 'error'
    reason: str = ''
    content: dict[str, Any] | None = None
    source_thought_ids: list[str] = field(default_factory=list)
    input_hash: str = ''
    usage: dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0
    synthesis_id: str | None = None  # uuid of new row when persisted
    superseded_id: str | None = None


# ─────────────────────────────────────────── Hashing & idempotency ──

def _thought_body_hash(thought: dict) -> str:
    """Use F3 body_hash from extracted_tags if available; else fall back to body."""
    et = thought.get('extracted_tags') or {}
    bh = et.get('body_hash')
    if bh:
        return bh
    body = thought.get('body') or ''
    return hashlib.sha256(body.encode('utf-8')).hexdigest()[:12]


def compute_input_hash(perspective_type: str, perspective_key: str,
                       source_thoughts: list[dict]) -> str:
    """Stable hash; changes only when source set or any source body changes."""
    parts = [
        f"v{PROMPT_VERSION}",
        perspective_type,
        perspective_key,
    ]
    sigs = [f"{t['id']}:{_thought_body_hash(t)}" for t in source_thoughts]
    parts.append(','.join(sorted(sigs)))
    raw = '|'.join(parts)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]


# ───────────────────────────────────── Source-thought selection ──

def _select_thoughts_for_client(tenant_id: str, key: str) -> list[dict]:
    sql = (
        "SELECT id, body, metadata, extracted_tags, created_at "
        "FROM thoughts "
        "WHERE tenant_id = %s AND thought_type = %s "
        "  AND extracted_tags @> %s::jsonb "
        "ORDER BY created_at"
    )
    return query(sql, tenant_id, THOUGHT_TYPE,
                 json.dumps({'client': [{'value': key}]}))


def _select_thoughts_for_project(tenant_id: str, key: str) -> list[dict]:
    sql = (
        "SELECT id, body, metadata, extracted_tags, created_at "
        "FROM thoughts "
        "WHERE tenant_id = %s AND thought_type = %s "
        "  AND extracted_tags @> %s::jsonb "
        "ORDER BY created_at"
    )
    return query(sql, tenant_id, THOUGHT_TYPE,
                 json.dumps({'project': [{'value': key}]}))


def _select_thoughts_for_person(tenant_id: str, key: str) -> list[dict]:
    """Fallback to metadata.participants/organizer (no edges yet — F4.2.4 graceful)."""
    sql = (
        "SELECT id, body, metadata, extracted_tags, created_at "
        "FROM thoughts "
        "WHERE tenant_id = %s AND thought_type = %s "
        "  AND ( metadata->'participants' @> %s::jsonb "
        "        OR metadata->>'organizer_slug' = %s "
        "        OR metadata->>'organizer' ILIKE %s ) "
        "ORDER BY created_at"
    )
    return query(sql, tenant_id, THOUGHT_TYPE,
                 json.dumps([key]), key, f'%{key}%')


def _select_thoughts_for_monthly(tenant_id: str, key: str) -> list[dict]:
    """key = 'YYYY-MM'. Use metadata.date if present, else created_at."""
    sql = (
        "SELECT id, body, metadata, extracted_tags, created_at "
        "FROM thoughts "
        "WHERE tenant_id = %s AND thought_type = %s "
        "  AND ( substring(coalesce(metadata->>'date', "
        "                           to_char(created_at, 'YYYY-MM-DD')), 1, 7) = %s ) "
        "ORDER BY created_at"
    )
    return query(sql, tenant_id, THOUGHT_TYPE, key)


def _select_thoughts_for_tag(tenant_id: str, key: str) -> list[dict]:
    """Match in extracted_tags.{topic,activity,status,project} OR metadata.tags."""
    sql = (
        "SELECT id, body, metadata, extracted_tags, created_at "
        "FROM thoughts "
        "WHERE tenant_id = %s AND thought_type = %s AND ( "
        "      extracted_tags @> %s::jsonb "
        "   OR extracted_tags @> %s::jsonb "
        "   OR extracted_tags @> %s::jsonb "
        "   OR extracted_tags @> %s::jsonb "
        "   OR metadata->'tags' ? %s "
        ") ORDER BY created_at"
    )
    return query(sql, tenant_id, THOUGHT_TYPE,
                 json.dumps({'topic': [{'value': key}]}),
                 json.dumps({'activity': [{'value': key}]}),
                 json.dumps({'status': [{'value': key}]}),
                 json.dumps({'project': [{'value': key}]}),
                 key)


def _select_thoughts_for_type(tenant_id: str, key: str) -> list[dict]:
    """Type tag = activity axis (e.g. 'presales', 'wks', 'weekly')."""
    sql = (
        "SELECT id, body, metadata, extracted_tags, created_at "
        "FROM thoughts "
        "WHERE tenant_id = %s AND thought_type = %s "
        "  AND extracted_tags @> %s::jsonb "
        "ORDER BY created_at"
    )
    return query(sql, tenant_id, THOUGHT_TYPE,
                 json.dumps({'activity': [{'value': key}]}))


# ──────────────────────────────── Corpus selectors ──
#
# Source = vault_note / backlog_item, NOT work_meeting_note. Deliberately
# NOT parametrized through THOUGHT_TYPE — these axes (section_path, area)
# don't exist on meeting notes and meeting axes (extracted_tags,
# metadata.participants) mostly don't exist on these two types (verified
# empirically before designing).

def _select_thoughts_for_area_digest(tenant_id: str, key: str) -> list[dict]:
    """key = second segment of metadata.section_path (e.g. 'globex')."""
    sql = (
        "SELECT id, body, metadata, extracted_tags, created_at "
        "FROM thoughts "
        "WHERE tenant_id = %s AND thought_type = 'vault_note' "
        "  AND metadata->'section_path'->>1 = %s "
        "ORDER BY created_at"
    )
    return query(sql, tenant_id, key)


def _select_thoughts_for_backlog_health(tenant_id: str, key: str) -> list[dict]:
    """key = metadata.area (e.g. '_second-brain', 'globex', '_router')."""
    sql = (
        "SELECT id, body, metadata, extracted_tags, created_at "
        "FROM thoughts "
        "WHERE tenant_id = %s AND thought_type = 'backlog_item' "
        "  AND metadata->>'area' = %s "
        "ORDER BY created_at"
    )
    return query(sql, tenant_id, key)


# ───────────────────────────────────────── FRP selectors (F7.3) ──
#
# Source = any thought with thought_type LIKE 'frp_%' (frp_scenario, frp_friction,
# frp_recognition, frp_reflection, frp_impulse, frp_revisit, frp_source_scored).
# Most join through frp_sessions via session_contains edges; per_domain uses
# content_queue.ai_tags->>'domain' until F7.4 lights up signals_domain edges.

_FRP_BASE_COLS = "t.id, t.body, t.metadata, t.extracted_tags, t.created_at, t.thought_type"


def _select_thoughts_for_frp_per_frame(tenant_id: str, key: str) -> list[dict]:
    """key in {'A', 'B', 'C'}. Pulls all FRP thoughts attached to sessions in that frame."""
    sql = (
        f"SELECT {_FRP_BASE_COLS} FROM thoughts t "
        "JOIN edges e ON e.dst_id = t.id AND e.type = 'session_contains' "
        "JOIN frp_sessions s ON s.id = e.src_id "
        "WHERE t.tenant_id = %s AND s.frame = %s "
        "  AND t.thought_type LIKE %s ESCAPE %s "
        "ORDER BY t.created_at"
    )
    return query(sql, tenant_id, key, _FRP_LIKE_PATTERN, '\\')


def _select_thoughts_for_frp_per_domain(tenant_id: str, key: str) -> list[dict]:
    """key = domain string ('work', 'tech', 'personal', ...).

    Pre-F7.4 implementation: walks `frp_sessions.content_id → content_queue.ai_tags->>'domain'`.
    Post-F7.4 will add UNION on `signals_domain` edges from FRP thoughts to non-FRP entities.
    """
    sql = (
        f"SELECT {_FRP_BASE_COLS} FROM thoughts t "
        "JOIN edges e ON e.dst_id = t.id AND e.type = 'session_contains' "
        "JOIN frp_sessions s ON s.id = e.src_id "
        "JOIN content_queue cq ON cq.id = s.content_id "
        "WHERE t.tenant_id = %s AND cq.ai_tags->>'domain' = %s "
        "  AND t.thought_type LIKE %s ESCAPE %s "
        "ORDER BY t.created_at"
    )
    return query(sql, tenant_id, key, _FRP_LIKE_PATTERN, '\\')


def _select_thoughts_for_frp_evolution_timeline(tenant_id: str,
                                                key: str) -> list[dict]:
    """key='all' (only one supported). Returns thoughts from the first 5 + last 5
    frp_sessions (by created_at) so the LLM can compare early vs current practice.
    """
    sessions = query(
        "(SELECT id FROM frp_sessions WHERE tenant_id = %s ORDER BY created_at ASC LIMIT 5) "
        "UNION ALL "
        "(SELECT id FROM frp_sessions WHERE tenant_id = %s ORDER BY created_at DESC LIMIT 5)",
        tenant_id, tenant_id,
    )
    sess_ids = [str(r['id']) for r in sessions]
    if not sess_ids:
        return []
    sql = (
        f"SELECT {_FRP_BASE_COLS} FROM thoughts t "
        "JOIN edges e ON e.dst_id = t.id AND e.type = 'session_contains' "
        "WHERE t.tenant_id = %s AND e.src_id = ANY(%s::uuid[]) "
        "  AND t.thought_type LIKE %s ESCAPE %s "
        "ORDER BY t.created_at"
    )
    return query(sql, tenant_id, sess_ids, _FRP_LIKE_PATTERN, '\\')


def _select_thoughts_for_frp_per_resonance(tenant_id: str,
                                           key: str) -> list[dict]:
    """key = minimum resonance threshold ('3', '4', '5'). Pulls FRP thoughts from
    sessions that scored >= key. Typical use: key='4' for high-resonance pattern mining.
    """
    try:
        min_resonance = int(key)
    except (TypeError, ValueError):
        return []
    if min_resonance < 1 or min_resonance > 5:
        return []
    sql = (
        f"SELECT {_FRP_BASE_COLS} FROM thoughts t "
        "JOIN edges e ON e.dst_id = t.id AND e.type = 'session_contains' "
        "JOIN frp_sessions s ON s.id = e.src_id "
        "WHERE t.tenant_id = %s AND s.resonance >= %s "
        "  AND t.thought_type LIKE %s ESCAPE %s "
        "ORDER BY t.created_at"
    )
    return query(sql, tenant_id, min_resonance, _FRP_LIKE_PATTERN, '\\')


def _select_thoughts_for_frp_monthly(tenant_id: str, key: str) -> list[dict]:
    """key = 'YYYY-MM'. All FRP thoughts created in that month."""
    sql = (
        f"SELECT {_FRP_BASE_COLS} FROM thoughts t "
        "WHERE t.tenant_id = %s "
        "  AND t.thought_type LIKE %s ESCAPE %s "
        "  AND substring(to_char(t.created_at, 'YYYY-MM-DD'), 1, 7) = %s "
        "ORDER BY t.created_at"
    )
    return query(sql, tenant_id, _FRP_LIKE_PATTERN, '\\', key)


# ───────────────────────────────────── News cluster (F8.8.x.B) ──
#
# Source = thoughts with thought_type='newsletter_synthesis' whose
# extracted_tags.topic[].value intersects the cluster's topic list (loaded
# once from config/news_topic_clusters.yaml). One synthesis per cluster slug.

_NEWS_CLUSTERS_CACHE: dict | None = None


def _load_news_clusters() -> dict[str, list[str]]:
    """{cluster_slug: [topic_value, ...]} from config/news_topic_clusters.yaml.

    Cached per-process. Empty dict on missing/invalid file (graceful no-op
    when news yaml absent: discover_perspectives won't surface news_cluster
    targets, single-key runs return 'no-thoughts').
    """
    global _NEWS_CLUSTERS_CACHE
    if _NEWS_CLUSTERS_CACHE is not None:
        return _NEWS_CLUSTERS_CACHE
    from exocortex.config_loader import resolve_config_path
    cfg_path = resolve_config_path('news_topic_clusters.yaml')
    out: dict[str, list[str]] = {}
    try:
        import yaml as _yaml  # lazy: synthesizer's other paths don't need yaml
        cfg = _yaml.safe_load(cfg_path.read_text(encoding='utf-8')) or {}
    except (FileNotFoundError, ImportError, Exception):  # noqa: BLE001
        _NEWS_CLUSTERS_CACHE = {}
        return _NEWS_CLUSTERS_CACHE
    for cl in cfg.get('clusters') or []:
        slug = (cl.get('slug') or '').strip()
        if not slug:
            continue
        topics = [str(t).strip() for t in (cl.get('topics') or []) if str(t).strip()]
        if topics:
            out[slug] = topics
    _NEWS_CLUSTERS_CACHE = out
    return out


def _select_thoughts_for_news_cluster(tenant_id: str, key: str) -> list[dict]:
    """key = cluster slug from news_topic_clusters.yaml.

    Pulls every newsletter_synthesis thought whose extracted_tags.topic[]
    contains at least one of the cluster's member topics. Uses a JSONB
    EXISTS subquery so a single thought matching multiple cluster topics
    still appears once (no DISTINCT needed).
    """
    clusters = _load_news_clusters()
    topics = clusters.get(key)
    if not topics:
        return []
    sql = (
        "SELECT id, body, metadata, extracted_tags, created_at, source_id "
        "FROM thoughts t "
        "WHERE tenant_id = %s "
        "  AND thought_type = 'newsletter_synthesis' "
        "  AND EXISTS ( "
        "    SELECT 1 FROM jsonb_array_elements(t.extracted_tags->'topic') AS topic_obj "
        "    WHERE topic_obj->>'value' = ANY(%s) "
        "  ) "
        "ORDER BY created_at"
    )
    return query(sql, tenant_id, topics)


def _select_gap_radar(tenant_id: str, perspective_key: str) -> list[dict]:
    """F31.5.2 — return gap analysis result as pseudo-thoughts for LLM synthesis.

    Each detected gap is rendered as a thought-like dict so the rest of the
    synthesizer pipeline (input_hash, persist, etc.) works unchanged.
    """
    from exocortex.workers.gap_queries import run_all_detectors
    gaps = run_all_detectors(tenant_id, max_results=30)
    out: list[dict] = []
    for i, g in enumerate(gaps):
        content = (
            f"Typ: {g['type']}. "
            f"Sugerowana akcja: {g['suggested_action']}. "
            f"Wiek: {g['age_days']:.0f} dni."
        )
        out.append({
            'id': f'gap-{i}',
            'title': g['title'],
            'content': content,
            # `body` so compute_input_hash / _thought_body_hash work unchanged.
            'body': content,
            'thought_type': 'gap_finding',
            'provenance': 'ai_authored',
            'tags': [],
            'metadata': {'gap_type': g['type'], 'title': g['title']},
            '_gap': g,  # full Gap dict for downstream consumers
        })
    return out


_SELECTORS = {
    'client': _select_thoughts_for_client,
    'project': _select_thoughts_for_project,
    'person': _select_thoughts_for_person,
    'monthly': _select_thoughts_for_monthly,
    'tag': _select_thoughts_for_tag,
    'type': _select_thoughts_for_type,
    'frp_per_frame': _select_thoughts_for_frp_per_frame,
    'frp_per_domain': _select_thoughts_for_frp_per_domain,
    'frp_evolution_timeline': _select_thoughts_for_frp_evolution_timeline,
    'frp_per_resonance': _select_thoughts_for_frp_per_resonance,
    'frp_monthly': _select_thoughts_for_frp_monthly,
    'news_cluster': _select_thoughts_for_news_cluster,
    'gap_radar': _select_gap_radar,
    'area_digest': _select_thoughts_for_area_digest,
    'backlog_health': _select_thoughts_for_backlog_health,
}


def select_source_thoughts(tenant_id: str, perspective_type: str,
                           perspective_key: str) -> list[dict]:
    if perspective_type not in _SELECTORS:
        raise ValueError(f"Unknown perspective_type: {perspective_type}")
    return _SELECTORS[perspective_type](tenant_id, perspective_key)


# ──────────────────────────────────────────────────── Edges (F4.2.4) ──

def fetch_edges_for_thoughts(tenant_id: str, thought_ids: list[str]) -> list[dict]:
    """Fetch typed edges referencing any source thought (in or out).
    F4 written before F5 starts populating edges; graceful fallback when edges=0."""
    if not thought_ids:
        return []
    sql = (
        "SELECT id, src_id, src_type, dst_id, dst_type, type, confidence "
        "FROM edges "
        "WHERE tenant_id = %s "
        "  AND (src_id = ANY(%s::uuid[]) OR dst_id = ANY(%s::uuid[]))"
    )
    str_ids = [str(tid) for tid in thought_ids]
    try:
        return query(sql, tenant_id, str_ids, str_ids)
    except Exception:
        return []


def _fetch_entities_by_ids(tenant_id: str, entity_ids: list[str]) -> dict[str, dict]:
    """entity_id -> {canonical_name, type}. Empty dict on failure / empty input."""
    if not entity_ids:
        return {}
    try:
        rows = query(
            "SELECT id::text AS id, canonical_name, type "
            "FROM entities WHERE tenant_id = %s AND id = ANY(%s::uuid[])",
            tenant_id, entity_ids,
        )
    except Exception:
        return {}
    return {r['id']: {'canonical_name': r['canonical_name'], 'type': r['type']}
            for r in rows}


def _fetch_syntheses_by_ids(tenant_id: str, syn_ids: list[str]) -> dict[str, dict]:
    """synthesis_id -> {perspective_type, perspective_key, content}. Empty on miss."""
    if not syn_ids:
        return {}
    try:
        rows = query(
            "SELECT id::text AS id, perspective_type, perspective_key, content "
            "FROM syntheses WHERE tenant_id = %s AND id = ANY(%s::uuid[])",
            tenant_id, syn_ids,
        )
    except Exception:
        return {}
    return {r['id']: r for r in rows}


def format_edges_for_prompt(edges: list[dict],
                            tenant_id: str | None = None,
                            perspective_type: str | None = None,
                            perspective_key: str | None = None) -> str:
    """Render edges as a semantic, model-readable context block.

    F4.6.2: prior implementation dumped raw UUID-pairs which the LLM cannot
    use. Now we resolve entity/synthesis references and emit a structured
    summary the model can quote in `current_state`/`ownership` reasoning:

      ## Typed reasoning edges (graph context)
      Top meeting co-attendees (attended_meeting):
        - user@example.com — 12 meetings
      Cross-perspective decisions (decided_in from other syntheses):
        - [client/acme] Vendor choice for the mobile app migration (2026-04-12)
      Cross-perspective problems (addresses_problem):
        - [tag/wcag] HIGH: no accessibility audit on the payment forms list
      Mentions in other perspectives' syntheses (mentions_person → this area):
        - person "Exocortex user" mentioned in 4 syntheses: client/acme,
          monthly/2026-04, ...

    Skips its own perspective synthesis (we don't want the LLM echoing what we
    already wrote last run). Caps at MAX_EDGES_PROMPT_CHARS (~3KB).
    """
    if not edges or not tenant_id:
        return ''

    # Bucket edges by type for downstream resolution.
    attended_by_meeting: dict[str, list[str]] = {}  # thought_id -> [person entity_id]
    decided_by_thought: dict[str, list[str]] = {}    # thought_id -> [synthesis_id]
    addresses_by_thought: dict[str, list[str]] = {}
    mentions_synthesis_by_person: dict[str, list[str]] = {}  # entity_id -> [synthesis_id]

    person_ids: set[str] = set()
    syn_ids: set[str] = set()

    for e in edges:
        et = e['type']
        s, d = str(e['src_id']), str(e['dst_id'])
        if et == 'attended_meeting':
            attended_by_meeting.setdefault(s, []).append(d)
            person_ids.add(d)
        elif et == 'decided_in':
            decided_by_thought.setdefault(d, []).append(s)
            syn_ids.add(s)
        elif et == 'addresses_problem':
            addresses_by_thought.setdefault(d, []).append(s)
            syn_ids.add(s)
        elif et == 'mentions_person':
            mentions_synthesis_by_person.setdefault(d, []).append(s)
            person_ids.add(d)
            syn_ids.add(s)

    if not (attended_by_meeting or decided_by_thought
            or addresses_by_thought or mentions_synthesis_by_person):
        return ''

    persons = _fetch_entities_by_ids(tenant_id, list(person_ids))
    syntheses = _fetch_syntheses_by_ids(tenant_id, list(syn_ids))

    own = (perspective_type, perspective_key)

    def _person_label(eid: str) -> str:
        info = persons.get(eid)
        return info['canonical_name'] if info else eid[:8]

    def _syn_label(sid: str) -> str:
        s = syntheses.get(sid)
        if not s:
            return sid[:8]
        return f"{s['perspective_type']}/{s['perspective_key']}"

    lines: list[str] = ['', '## Typed reasoning edges (kontekst grafu)', '']

    # Top attendees across this perspective's source thoughts.
    person_meeting_count: dict[str, int] = {}
    for mid, eids in attended_by_meeting.items():
        for eid in set(eids):
            person_meeting_count[eid] = person_meeting_count.get(eid, 0) + 1
    if person_meeting_count:
        top = sorted(person_meeting_count.items(), key=lambda x: -x[1])[:8]
        lines.append('Top współuczestnicy spotkań w tej perspektywie:')
        for eid, n in top:
            lines.append(f'- {_person_label(eid)} — {n} spotk.')
        lines.append('')

    # Cross-perspective decisions.
    cross_decisions: list[tuple[str, str, str]] = []  # (syn_label, decision_text, source_tid)
    for tid, sids in decided_by_thought.items():
        for sid in set(sids):
            s = syntheses.get(sid)
            if not s:
                continue
            if (s['perspective_type'], s['perspective_key']) == own:
                continue
            content = s.get('content') or {}
            for d in (content.get('recent_decisions') or []):
                if str(d.get('source_thought_id') or '') == tid:
                    text = (d.get('content') or '').strip()
                    if text:
                        cross_decisions.append((_syn_label(sid), text, tid))
                        break  # one decision per synthesis-thought pair is enough
    if cross_decisions:
        lines.append('Cross-perspective decyzje (decided_in z innych syntez):')
        for label, text, _ in cross_decisions[:10]:
            short = text if len(text) <= 180 else text[:177] + '…'
            lines.append(f'- [{label}] {short}')
        if len(cross_decisions) > 10:
            lines.append(f'  …i {len(cross_decisions) - 10} więcej.')
        lines.append('')

    # Cross-perspective problems.
    cross_problems: list[tuple[str, str, str]] = []
    for tid, sids in addresses_by_thought.items():
        for sid in set(sids):
            s = syntheses.get(sid)
            if not s:
                continue
            if (s['perspective_type'], s['perspective_key']) == own:
                continue
            content = s.get('content') or {}
            for p in (content.get('open_problems') or []):
                if str(p.get('source_thought_id') or '') == tid:
                    text = (p.get('content') or '').strip()
                    if text:
                        sev = (p.get('severity') or 'medium').upper()
                        cross_problems.append((_syn_label(sid), f'{sev}: {text}', tid))
                        break
    if cross_problems:
        lines.append('Cross-perspective problemy (addresses_problem):')
        for label, text, _ in cross_problems[:10]:
            short = text if len(text) <= 180 else text[:177] + '…'
            lines.append(f'- [{label}] {short}')
        if len(cross_problems) > 10:
            lines.append(f'  …i {len(cross_problems) - 10} więcej.')
        lines.append('')

    # mentions_person — only when person is the OUTBOUND entity AND synthesis isn't this one.
    if mentions_synthesis_by_person:
        mention_lines: list[str] = []
        for eid, sids in mentions_synthesis_by_person.items():
            others = sorted({_syn_label(sid) for sid in set(sids)
                             if syntheses.get(sid)
                             and (syntheses[sid]['perspective_type'],
                                  syntheses[sid]['perspective_key']) != own})
            if not others:
                continue
            mention_lines.append(
                f'- "{_person_label(eid)}" wzmiankowana w {len(others)} '
                f'syntezach: {", ".join(others[:5])}'
                + (f' …+{len(others) - 5}' if len(others) > 5 else '')
            )
        if mention_lines:
            lines.append('Wzmianki w syntezach innych perspektyw:')
            lines.extend(mention_lines[:10])
            if len(mention_lines) > 10:
                lines.append(f'  …i {len(mention_lines) - 10} więcej osób.')
            lines.append('')

    text = '\n'.join(lines)
    # Cap at ~3KB to stay well within prompt budget.
    MAX_EDGES_CHARS = 3500
    if len(text) > MAX_EDGES_CHARS:
        text = text[:MAX_EDGES_CHARS] + '\n[…edges section truncated for prompt budget…]'
    return text


# ────────────────────────────────────── Action items compaction ──

def compact_action_items(action_items_md: str | None) -> str:
    """Strip timecodes/decorators/inline tags. Format `[x] Owner: content` per line."""
    if not action_items_md:
        return ''
    try:
        from exocortex.action_items import parse_action_items
        items = parse_action_items({'action_items': action_items_md, 'meeting_id': '_synth'})
    except Exception:
        return action_items_md.strip()[:MAX_MEETING_CHARS]

    lines = []
    for it in items:
        box = '[x]' if it.status == 'done' else '[ ]'
        owner = it.owner_name or it.owner_slug or '?'
        lines.append(f"{box} {owner}: {it.content}")
    return '\n'.join(lines)


# ───────────────────────────────────────── Meeting block builder ──

def _meeting_block(thought: dict) -> str:
    meta = thought.get('metadata') or {}
    title = (meta.get('title') or '').strip() or '(no title)'
    meeting_date = meta.get('date') or ''
    if not meeting_date and thought.get('created_at'):
        ca = thought['created_at']
        meeting_date = ca.strftime('%Y-%m-%d') if hasattr(ca, 'strftime') else str(ca)[:10]
    duration = meta.get('duration_minutes') or meta.get('duration') or ''
    n_part = ''
    participants = meta.get('participants') or []
    if participants:
        n_part = f"{len(participants)} uczestników"

    et = thought.get('extracted_tags') or {}
    type_tags = [t.get('value') for t in (et.get('activity') or []) if t.get('value')]

    overview = (meta.get('overview') or '').strip()
    key_points = (meta.get('key_points') or '').strip()
    action_items = compact_action_items(meta.get('action_items'))

    header_bits = [meeting_date, '—', title]
    duration_bits = []
    if duration:
        duration_bits.append(f"{duration} min")
    if n_part:
        duration_bits.append(n_part)
    if duration_bits:
        header_bits.append(f"({', '.join(duration_bits)})")

    parts = [
        "---",
        f"ID: {thought['id']}",
        f"## {' '.join(header_bits)}",
    ]
    if type_tags:
        parts.append(f"Typy: {', '.join(type_tags)}")
    if overview:
        parts.append(f"\n**Overview:**\n{overview}")
    if action_items:
        parts.append(f"\n**Action Items (skondensowane):**\n{action_items}")
    if key_points:
        parts.append(f"\n**Key Points:**\n{key_points}")

    block = '\n'.join(parts)
    if len(block) > MAX_MEETING_CHARS:
        block = block[:MAX_MEETING_CHARS] + '\n[…truncated…]'
    return block


def _perspective_display(perspective_type: str, perspective_key: str) -> str:
    labels = {
        'client': 'klient',
        'project': 'projekt',
        'person': 'osoba',
        'monthly': 'miesiąc',
        'tag': 'tag',
        'type': 'typ spotkania',
        # F7.3 — FRP perspectives
        'frp_per_frame': 'FRP frame',
        'frp_per_domain': 'FRP domena',
        'frp_evolution_timeline': 'FRP ewolucja praktyki',
        'frp_per_resonance': 'FRP rezonans ≥',
        'frp_monthly': 'FRP miesiąc',
        # F8.8.x.B — newsletter cluster
        'news_cluster': 'kategoria newsletterów',
    }
    return f"{labels.get(perspective_type, perspective_type)}={perspective_key}"


# ───────────────────────────────────────── FRP block builder (F7.3) ──

def _frp_thought_block(thought: dict) -> str:
    """Compact rendering for FRP thoughts (no overview/action_items/key_points
    structure — just thought_type + body, optionally enriched with story metadata
    when the thought is a frp_source_scored).
    """
    meta = thought.get('metadata') or {}
    body = (thought.get('body') or '').strip()
    ttype = thought.get('thought_type', 'frp_unknown')
    created = thought.get('created_at')
    date = created.strftime('%Y-%m-%d') if hasattr(created, 'strftime') else str(created)[:10]
    title = (meta.get('title') or '').strip()
    eft_anchor = meta.get('eft_anchor') or ''
    domain = meta.get('story_domain') or meta.get('domain') or ''
    frp_score = meta.get('frp_score') or {}

    header_bits = [date, '—', f"`{ttype}`"]
    if title:
        header_bits.extend(['—', title])

    parts = [
        '---',
        f"ID: {thought['id']}",
        f"## {' '.join(header_bits)}",
    ]
    if eft_anchor:
        parts.append(f"EFT anchor: `{eft_anchor}`")
    if domain:
        parts.append(f"Domena: {domain}")
    if frp_score:
        parts.append(
            f"Score: a={frp_score.get('accessibility')}/3 "
            f"h={frp_score.get('horizon')}/3 "
            f"c={frp_score.get('consequence')}/3 "
            f"frame={frp_score.get('frame', '?')} "
            f"prompt={frp_score.get('suggested_prompt_key', '?')}"
        )
    if body:
        parts.append(f"\n{body}")

    block = '\n'.join(parts)
    if len(block) > MAX_MEETING_CHARS:
        block = block[:MAX_MEETING_CHARS] + '\n[…truncated…]'
    return block


_FRP_PROMPT_OVERLAY = """
Kontekst: to perspektywa FRP (Futures Reading Protocol — praktyka mikrodozowania scenariuszy SF dla treningu strategicznej wyobraźni). Źródłem są thoughts typu `frp_*`:
- `frp_source_scored` — historia z queue, ze score 3-osiowym (accessibility/horizon/consequence) + frame (A/B/C) + suggested_prompt_key.
- `frp_scenario` — jednozdaniowe what-if z lektury.
- `frp_friction` — tarcie / koszt / sprzeczność widziana w scenariuszu.
- `frp_recognition` — gdzie w obecnej praktyce widać już zalążek tej sytuacji.
- `frp_reflection` — refleksja per pytanie (EFT / Pattern Library / Strategic Assumption).
- `frp_impulse` — konkretny krok, który chcę podjąć w wyniku lektury.
- `frp_revisit` — 48h później: czy impulse się utrzymał, zmutował, zgasł.

Mapowanie 5 sekcji na FRP (Option A — bez nowego schematu):
- `current_state` — jaki dominujący wzorzec / ramka / domena zaznacza się w tej perspektywie? Co użytkownik *nie może przestać o tym myśleć* (frequent eft_anchor)?
- `recent_decisions` — strategiczne assumptions (z `frp_reflection` Q3) które użytkownik ostatnio zwerbalizował. To NIE są decyzje biznesowe — to load-bearing beliefs o świecie zawodowym ("X must be true for Y to be impossible").
- `open_problems` — blind spoty + sprzeczności widoczne w gradiencie. Gdzie wyobraźnia jest cienka? Gdzie użytkownik argumentuje ze sobą sam (Q3 z lutego ↔ Q3 z kwietnia)?
- `ownership` — rzadko applicable dla FRP (większość refleksji nie dotyczy konkretnych osób). Pomiń jeśli nie widzisz wyraźnych ownership signals — pusta lista jest OK.
- `next_steps` — recommended next microdoses (DOMAIN/ROLE/SITUATION combos) + konkretne impulsy z `frp_impulse` które jeszcze się nie zmaterializowały (`materializes_as_url` brak na revisit).

Wszystkie pozostałe reguły system promptu (PL only, bez halucynacji, source_thought_id z `ID:`, faktografia) obowiązują niezmienne.
"""


def _is_frp_perspective(perspective_type: str) -> bool:
    return perspective_type.startswith('frp_')


# ───────────────────────────── News block builder (F8.8.x.B) ──

def _news_thought_block(thought: dict) -> str:
    """Compact rendering for newsletter_synthesis thoughts. Uses the structured
    fields (`tldr`, `key_insights`, topics) from metadata + body excerpt — the
    full body is mostly markdown the synthesizer would have to re-summarise
    anyway. Stays under MAX_MEETING_CHARS via head-truncate on body."""
    meta = thought.get('metadata') or {}
    et = thought.get('extracted_tags') or {}
    nl = et.get('_newsletter') or {}
    title = (meta.get('title') or '').strip() or '(no title)'
    captured = thought.get('created_at')
    date = captured.strftime('%Y-%m-%d') if hasattr(captured, 'strftime') else str(captured)[:10]
    newsletter = (
        nl.get('newsletter_name')
        or meta.get('newsletter_name')
        or '(unknown newsletter)'
    )
    sender = nl.get('sender_email') or meta.get('sender_email') or ''
    tldr = (nl.get('tldr') or meta.get('tldr') or '').strip()
    topics = [
        (t.get('value') if isinstance(t, dict) else str(t))
        for t in (et.get('topic') or [])
        if (t.get('value') if isinstance(t, dict) else str(t))
    ]

    def _coerce_list(v: Any) -> list:
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            try:
                p = json.loads(v)
                return p if isinstance(p, list) else []
            except (ValueError, TypeError):
                return []
        return []

    insights_raw = _coerce_list(nl.get('key_insights'))
    insights: list[str] = []
    for it in insights_raw[:5]:
        if isinstance(it, dict):
            txt = it.get('insight') or it.get('text') or it.get('content') or ''
            ev = it.get('evidence') or ''
            if txt:
                line = f"- **{txt.strip()}**"
                if ev:
                    line += f" — _evidence:_ {str(ev).strip()}"
                insights.append(line)
        elif isinstance(it, str):
            s = it.strip()
            if s:
                insights.append(f"- {s}")
    cited_raw = _coerce_list(nl.get('cited_sources'))
    cited: list[str] = []
    for it in cited_raw[:8]:
        if isinstance(it, dict):
            name = it.get('name') or it.get('source') or ''
            if name:
                cited.append(str(name).strip())
        elif isinstance(it, str):
            s = it.strip()
            if s:
                cited.append(s)

    parts = [
        '---',
        f"ID: {thought['id']}",
        f"## {date} — {newsletter} — {title}",
    ]
    if sender:
        parts.append(f"Sender: `{sender}`")
    if topics:
        parts.append(f"Topics: {', '.join(topics)}")
    if tldr:
        parts.append(f"\n**TL;DR:** {tldr}")
    if insights:
        parts.append('\n**Key insights:**')
        parts.extend(insights)
    if cited:
        parts.append(f"\n**Cited sources:** {', '.join(cited)}")

    block = '\n'.join(parts)
    if len(block) > MAX_MEETING_CHARS:
        block = block[:MAX_MEETING_CHARS] + '\n[…truncated…]'
    return block


_NEWS_PROMPT_OVERLAY = """
Kontekst: to perspektywa kategorii newsletterów (F8.8.x.B). Źródłem są thoughts typu `newsletter_synthesis` — gotowe streszczenia AI-newsletterów (TL;DR + key_insights + cited_sources + topics z 5-osi taxonomy). Każdy issue już raz przeszedł przez LLM podczas processora `email_thread.synthesize` / `newsletter`, więc DOSTAJESZ syntezy syntez — nie surowe maile. Zadanie: wytopić timeless category-level signal across N tygodni.

Mapowanie 5 sekcji na newsletter cluster (Option A — bez nowego schematu):
- `current_state` → **emerging consensus**: jaki dominujący narrative przewija się przez N+ newsletters w tej kategorii? Co użytkownik *NIE może już ignorować* gdy 5 niezależnych źródeł powtarza tę samą tezę? 1-3 akapity.
- `recent_decisions` → **notable claims**: konkretne fakty / liczby / decyzje cytowane w newsletters z `source_thought_id` z `ID:` powyżej (np. "OpenAI ogłosił X w Q2 2026", "Anthropic raised $Y", "Llama 4 osiągnął Z na benchmark W"). NIE są to decyzje the user — są to stwierdzenia ze świata zewnętrznego, które warto pamiętać. `date` = data newslettera.
- `open_problems` → **contradictions / unresolved questions**: gdzie newsletters się ze sobą NIE zgadzają? Gdzie autor X mówi "AI agents are ready" a autor Y mówi "production is fragile"? Severity = high gdy jeden newsletter wprost obala tezę innego, medium gdy są napięcia, low gdy nice-to-watch.
- `ownership` → **key authors / sources cited**: TOP people / brandy / firmy które najczęściej pojawiają się jako cytowane lub jako autorzy newsletterów w tej kategorii. `person` = "Imię Nazwisko" lub brand ("Anthropic", "Cursor"), `area` = czego są jakim głosem ("publishes weekly recap", "frequently quoted on X").
- `next_steps` → **trends to watch**: co na horyzoncie użytkownik powinien obserwować w tej kategorii? Konkretne tematy które zaczęły rosnąć, products które właśnie wystartowały, regulacje które są w trakcie. `owner` typowo pusty (to nie są action items dla użytkownika — to signal).

Wszystkie pozostałe reguły system promptu (PL only, bez halucynacji, source_thought_id z `ID:`, faktografia) obowiązują niezmienne. NIE wymyślasz autorów ani dat — jeśli newsletter nie cytuje źródła, pomijasz item.
"""


def _is_news_perspective(perspective_type: str) -> bool:
    return perspective_type == 'news_cluster'


def _build_gap_radar_prompt(thoughts: list[dict], perspective_key: str) -> str:
    """F31.5.2 — prompt for weekly Gap Radar synthesis.

    Asks for a short Polish narrative + top gaps + total count in JSON.
    """
    gap_lines = '\n'.join(
        f"- {t.get('title', '(no title)')}: {t.get('content', '')}"
        for t in thoughts[:30]
    )
    return (
        "Jesteś asystentem analizy luk w wiedzy. Na podstawie poniższych "
        "zidentyfikowanych luk:\n\n"
        f"{gap_lines}\n\n"
        "Napisz krótki raport (po polsku, maks. 5 zdań) wskazujący:\n"
        "1. Najważniejszą lukę do wypełnienia i dlaczego\n"
        "2. Konkretne sugerowane działanie\n"
        "3. Potencjalną wartość po wypełnieniu luki\n\n"
        "Format: JSON z polami: narrative_pl (string), "
        "top_gaps (list of {type, title, suggested_action}), "
        "total_gaps_count (int)"
    )


def _area_thought_block(t: dict) -> str:
    meta = t.get('metadata') or {}
    title = meta.get('title') or '(bez tytułu)'
    path = meta.get('vault_path') or ''
    body = (t.get('body') or '').strip().replace('\n', ' ')
    if len(body) > 300:
        body = body[:300] + '…'
    return f"- ID: {t['id']}\n  Tytuł: {title}\n  Ścieżka: {path}\n  Treść: {body}"


def _backlog_thought_block(t: dict) -> str:
    meta = t.get('metadata') or {}
    ticket = meta.get('ticket_id') or '(brak id)'
    status = meta.get('status') or '(brak)'
    priority = meta.get('priority') or ''
    blocked_by = meta.get('blocked_by_ids') or []
    body = (t.get('body') or '').strip().replace('\n', ' ')
    if len(body) > 200:
        body = body[:200] + '…'
    blocked_str = f", blokowane przez: {', '.join(blocked_by)}" if blocked_by else ''
    return (f"- ID: {t['id']}\n  Ticket: {ticket}  Status: {status}  "
           f"Priorytet: {priority}{blocked_str}\n  Utworzono: {t.get('created_at')}\n  Treść: {body}")


def _build_area_digest_prompt(thoughts: list[dict], perspective_key: str,
                              edges: list[dict] | None = None) -> str:
    """Prompt for `area_digest` (vault_note aggregated per
    section_path[1]). NOT the meeting-shaped 5-section prompt — this
    perspective has no participants/decisions in the meeting sense."""
    ids = {str(t['id']) for t in thoughts}
    wikilink_count = sum(
        1 for e in (edges or [])
        if e.get('type') == 'wikilink_to'
        and (str(e.get('src_id')) in ids or str(e.get('dst_id')) in ids)
    )
    blocks = '\n'.join(_area_thought_block(t) for t in thoughts[:40])
    return (
        f"Obszar: {perspective_key}\n"
        f"Liczba dokumentów: {len(thoughts)}\n"
        f"Wikilinki dotykające ten obszar: {wikilink_count}\n\n"
        f"Dokumenty:\n\n{blocks}\n\n"
        "---\n\nWywołaj narzędzie `area_digest_synthesis` z polami: "
        "stan_dzis, dokumenty_wyrozniajace_sie, powiazania."
    )


def _build_backlog_health_prompt(thoughts: list[dict], perspective_key: str,
                                 edges: list[dict] | None = None) -> str:
    """Prompt for `backlog_health` (backlog_item aggregated
    per metadata.area). Backlog and blocker chains in a single perspective."""
    tickets_here = {(t.get('metadata') or {}).get('ticket_id') for t in thoughts}
    blocker_counts: dict[str, int] = {}
    for t in thoughts:
        for blocker in ((t.get('metadata') or {}).get('blocked_by_ids') or []):
            blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1
    top_blockers = sorted(blocker_counts.items(), key=lambda kv: -kv[1])[:5]
    blockers_line = (
        ', '.join(f"{tid} (blokuje {n})" for tid, n in top_blockers)
        if top_blockers else '(brak)'
    )
    blocks = '\n'.join(_backlog_thought_block(t) for t in thoughts[:60])
    return (
        f"Obszar backlogu: {perspective_key}\n"
        f"Liczba pozycji: {len(thoughts)}\n"
        f"Ticketów w tym obszarze: {len(tickets_here)}\n"
        f"Najczęściej wskazywani blokerzy (ticket_id: ile pozycji blokuje): {blockers_line}\n\n"
        f"Pozycje backlogu:\n\n{blocks}\n\n"
        "---\n\nWywołaj narzędzie `backlog_health_synthesis` z polami: "
        "stan_dzis, zaleglosci, lancuchy_blokad."
    )


AREA_DIGEST_SYSTEM_PROMPT = (
    "Jesteś asystentem przeglądu dokumentacji roboczej. Dostajesz dokumenty "
    "z jednego obszaru vaulta (nie transkrypty spotkań — dokumenty: notatki, "
    "ADR-y, plany, briefy). Piszesz PO POLSKU, faktograficznie, wyłącznie "
    "z dostarczonej treści — bez wymyślania. Dokumenty nie mają uczestników "
    "ani przypisanych właścicieli zadań — nie zmyślaj ich.\n\n"
    "Wywołaj narzędzie `area_digest_synthesis` z trzema polami:\n"
    "- stan_dzis: 2-4 zdania, co ten obszar dokumentuje i jakie ustalenia "
    "widać w treści.\n"
    "- dokumenty_wyrozniajace_sie: do 5 pozycji {tytul, powod} — czym dany "
    "dokument się wyróżnia (najdłuższy, zawiera decyzję, sprzeczność z innym "
    "dokumentem itd.).\n"
    "- powiazania: do 3 krótkich zdań o silnie połączonych dokumentach "
    "(na podstawie liczby wikilinków)."
)

BACKLOG_HEALTH_SYSTEM_PROMPT = (
    "Jesteś asystentem przeglądu backlogu zadań. Dostajesz pozycje backlogu "
    "z jednego obszaru (ticket_id, status, priorytet, blokady). Piszesz PO "
    "POLSKU, faktograficznie, wyłącznie z dostarczonej treści.\n\n"
    "Wywołaj narzędzie `backlog_health_synthesis` z trzema polami:\n"
    "- stan_dzis: 2-3 zdania — rozkład statusów, czy coś rzuca się w oczy.\n"
    "- zaleglosci: do 5 pozycji {ticket, opis} ze statusem pending/"
    "in-progress/open o najwyższym priorytecie lub najstarszych.\n"
    "- lancuchy_blokad: do 3 pozycji {ticket, blokuje_ile, opis} — tickety, "
    "które SAME blokują najwięcej innych (patrz 'Najczęściej wskazywani "
    "blokerzy' w danych wejściowych)."
)

AREA_DIGEST_TOOL = {
    'name': 'area_digest_synthesis',
    'description': 'Synteza stanu jednego obszaru dokumentacji (vault_note).',
    'input_schema': {
        'type': 'object',
        'properties': {
            'stan_dzis': {'type': 'string'},
            'dokumenty_wyrozniajace_sie': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'tytul': {'type': 'string'},
                        'powod': {'type': 'string'},
                    },
                    'required': ['tytul', 'powod'],
                    'additionalProperties': False,
                },
            },
            'powiazania': {'type': 'array', 'items': {'type': 'string'}},
        },
        'required': ['stan_dzis', 'dokumenty_wyrozniajace_sie', 'powiazania'],
        'additionalProperties': False,
    },
}

BACKLOG_HEALTH_TOOL = {
    'name': 'backlog_health_synthesis',
    'description': 'Synteza kondycji jednego obszaru backlogu (backlog_item).',
    'input_schema': {
        'type': 'object',
        'properties': {
            'stan_dzis': {'type': 'string'},
            'zaleglosci': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'ticket': {'type': 'string'},
                        'opis': {'type': 'string'},
                    },
                    'required': ['ticket', 'opis'],
                    'additionalProperties': False,
                },
            },
            'lancuchy_blokad': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'ticket': {'type': 'string'},
                        'blokuje_ile': {'type': 'integer'},
                        'opis': {'type': 'string'},
                    },
                    'required': ['ticket', 'blokuje_ile', 'opis'],
                    'additionalProperties': False,
                },
            },
        },
        'required': ['stan_dzis', 'zaleglosci', 'lancuchy_blokad'],
        'additionalProperties': False,
    },
}


def build_user_prompt(perspective_type: str, perspective_key: str,
                      source_thoughts: list[dict], edges: list[dict],
                      tenant_id: str | None = None) -> str:
    if perspective_type == 'gap_radar':
        return _build_gap_radar_prompt(source_thoughts, perspective_key)
    if perspective_type == 'area_digest':
        return _build_area_digest_prompt(source_thoughts, perspective_key, edges)
    if perspective_type == 'backlog_health':
        return _build_backlog_health_prompt(source_thoughts, perspective_key, edges)
    is_frp = _is_frp_perspective(perspective_type)
    is_news = _is_news_perspective(perspective_type)
    if is_frp:
        block_fn = _frp_thought_block
    elif is_news:
        block_fn = _news_thought_block
    else:
        block_fn = _meeting_block
    blocks = [block_fn(t) for t in source_thoughts]
    first_date = source_thoughts[0].get('metadata', {}).get('date') or ''
    last_date = source_thoughts[-1].get('metadata', {}).get('date') or ''
    if not first_date and source_thoughts[0].get('created_at'):
        first_date = str(source_thoughts[0]['created_at'])[:10]
    if not last_date and source_thoughts[-1].get('created_at'):
        last_date = str(source_thoughts[-1]['created_at'])[:10]

    if is_frp:
        item_label = 'thoughtów FRP'
    elif is_news:
        item_label = 'newsletter issues'
    else:
        item_label = 'spotkań'
    header = (
        f"Perspektywa: {_perspective_display(perspective_type, perspective_key)}\n"
        f"Liczba {item_label}: {len(source_thoughts)}\n"
        f"Okres: {first_date} → {last_date}\n"
    )
    edges_section = format_edges_for_prompt(
        edges, tenant_id=tenant_id,
        perspective_type=perspective_type, perspective_key=perspective_key,
    )
    body_lines = [header]
    if is_frp:
        body_lines.append(_FRP_PROMPT_OVERLAY)
    elif is_news:
        body_lines.append(_NEWS_PROMPT_OVERLAY)
    if edges_section:
        body_lines.append(edges_section)
    if is_frp:
        section_label = 'Thoughty FRP (chronologicznie, najstarsze pierwsze):'
    elif is_news:
        section_label = 'Newsletter issues (chronologicznie, najstarsze pierwsze):'
    else:
        section_label = 'Spotkania (chronologicznie, najstarsze pierwsze):'
    body_lines.append(f'\n{section_label}\n')
    body_lines.extend(blocks)
    body_lines.append('\n---\n\nWywołaj narzędzie `synthesize` z 5 sekcjami zgodnie z system promptem.')

    full = '\n'.join(body_lines)
    if len(full) > MAX_USER_PROMPT_CHARS:
        # Drop oldest items until we fit (keep header + overlay + edges + most recent).
        keep_blocks = blocks
        if is_frp:
            overlay = _FRP_PROMPT_OVERLAY
        elif is_news:
            overlay = _NEWS_PROMPT_OVERLAY
        else:
            overlay = ''
        while len('\n'.join([header, overlay, edges_section, '\n'.join(keep_blocks)])) > MAX_USER_PROMPT_CHARS \
                and len(keep_blocks) > 1:
            keep_blocks = keep_blocks[1:]
        body_lines = [header]
        if is_frp:
            body_lines.append(_FRP_PROMPT_OVERLAY)
        elif is_news:
            body_lines.append(_NEWS_PROMPT_OVERLAY)
        if edges_section:
            body_lines.append(edges_section)
        dropped = len(blocks) - len(keep_blocks)
        body_lines.append(f'\n[…starsze {dropped} {item_label} pominięte z powodu budżetu tokenów…]')
        body_lines.append(f'\n{section_label}\n')
        body_lines.extend(keep_blocks)
        body_lines.append('\n---\n\nWywołaj narzędzie `synthesize` z 5 sekcjami zgodnie z system promptem.')
        full = '\n'.join(body_lines)
    return full


# ────────────────────────────────────────── System prompt + tool ──

SYSTEM_PROMPT_TEXT = """Jesteś asystentem knowledge management the user — solution architecta w EFI (example.com). Otrzymujesz historię spotkań (Overview, Action Items skondensowane, Key Points) i opis perspektywy (klient/projekt/osoba/miesiąc/tag/typ). Twoim zadaniem jest zsyntetyzowanie 5-sekcyjnej struktury.

Reguły ogólne:
- Output WYŁĄCZNIE po polsku (input bywa mieszany PL/EN — to OK).
- Każda sekcja może być pusta jeśli brak danych — NIE wymyślasz, NIE halucynujesz.
- Każda sekcja: 3-7 itemów typowo, ≤ 200 słów łącznie.
- W polach `source_thought_id` / `source_thought_ids` używaj UUID-a wziętego z `ID:` powyżej spotkania (NIE wymyślaj).
- Nazwiska w formacie "Imię Nazwisko" jeśli widoczne, fallback do owner_slug / emaila.
- BEZ cytatu transkryptu — synteza, nie kopiowanie.
- Faktografia. Tylko z dostarczonych spotkań.

Sekcja `## Typed reasoning edges (kontekst grafu)` (jeśli obecna):
- To kontekst z grafu typowanych krawędzi: top współuczestnicy spotkań,
  decyzje/problemy z innych syntez (perspektyw klient/projekt/osoba/miesiąc/tag),
  oraz wzmianki o osobach.
- Używaj tego kontekstu w `current_state` żeby umiejscowić aktualną perspektywę
  ("X jest też kluczowa dla projektu Y" — gdy widzisz cross-perspective decyzję).
- NIE kopiuj decyzji/problemów dosłownie do `recent_decisions`/`open_problems` —
  źródłem dla TYCH sekcji są spotkania w bloku poniżej (musi być source_thought_id
  z `ID:`). Edges to kontekst tła, nie dane wejściowe.

Sekcje — co dokładnie ekstrahować:

1. `current_state` — 1-3 akapity opisujące gdzie jesteśmy DZIŚ z tej perspektywy: kluczowe inicjatywy, fazy projektów, statusy finansowe/decyzyjne, zmiany kontekstu.

2. `recent_decisions` — decyzje już PODJĘTE (nie planowane): kierunek, budżet, alokacja, wybór technologii, zmiana modelu współpracy. Zwykle jest ich sporo w 5-25 spotkaniach. `date`: YYYY-MM-DD lub pusty string. `severity` nie dotyczy.

3. `open_problems` — nierozwiązane problemy / ryzyka / pending items. `severity`: 'high' (blocker, deadline na karku, finansowe ryzyko), 'medium' (work-in-progress z wątpliwościami), 'low' (nice-to-have, future).

4. `ownership` — KTO jest odpowiedzialny za co. KLUCZOWA sekcja — wykorzystaj sekcje "Action Items" w spotkaniach (linie `[ ] Imię Nazwisko: zadanie`) ORAZ wzmianki w Overview ("X prowadzi Y", "Z odpowiada za..."). Group by person, area = obszar/projekt/temat. NIE zostawiaj pustej listy jeśli widzisz akcje przypisane konkretnym osobom — minimum 2-5 ownerów typowo.

5. `next_steps` — co należy ZROBIĆ (otwarte action items + planowane akcje). Wykorzystaj `[ ]` (open) action items z poszczególnych spotkań ORAZ planowane kroki z Overview. Pomijaj `[x]` (done). NIE zostawiaj pustej listy gdy widzisz otwarte action items — minimum 3-5 itemów typowo. `date`: termin (YYYY-MM-DD) lub pusty string. `owner`: imię z action item lub pusty.

Wywołaj narzędzie `synthesize` z 5 polami: current_state, recent_decisions, open_problems, ownership, next_steps."""


def build_system_prompt() -> list[dict]:
    return [{
        'type': 'text',
        'text': SYSTEM_PROMPT_TEXT,
        'cache_control': {'type': 'ephemeral'},
    }]


SYNTHESIZE_TOOL = {
    'name': 'synthesize',
    'description': 'Generuje strukturalną 5-sekcyjną syntezę dla danej perspektywy.',
    'input_schema': {
        'type': 'object',
        'properties': {
            'current_state': {
                'type': 'string',
                'description': '1-3 akapity faktograficznego opisu gdzie jesteśmy dziś. Może być pusty.',
            },
            'recent_decisions': {
                'type': 'array',
                'description': 'Lista decyzji (max 7).',
                'items': {
                    'type': 'object',
                    'properties': {
                        'date': {'type': 'string', 'description': 'YYYY-MM-DD lub pusty string.'},
                        'content': {'type': 'string', 'description': 'Krótki opis (1-2 zdania).'},
                        'source_thought_id': {'type': 'string',
                                              'description': 'UUID źródłowego thought (z `ID:` w prompcie).'},
                    },
                    'required': ['date', 'content', 'source_thought_id'],
                    'additionalProperties': False,
                },
            },
            'open_problems': {
                'type': 'array',
                'description': 'Lista nierozwiązanych problemów / ryzyk (max 7).',
                'items': {
                    'type': 'object',
                    'properties': {
                        'severity': {'type': 'string', 'enum': ['high', 'medium', 'low']},
                        'content': {'type': 'string'},
                        'source_thought_id': {'type': 'string'},
                    },
                    'required': ['severity', 'content', 'source_thought_id'],
                    'additionalProperties': False,
                },
            },
            'ownership': {
                'type': 'array',
                'description': 'Kto za co odpowiedzialny (max 7).',
                'items': {
                    'type': 'object',
                    'properties': {
                        'person': {'type': 'string', 'description': 'Imię Nazwisko lub slug.'},
                        'area': {'type': 'string', 'description': 'Co dana osoba prowadzi.'},
                        'source_thought_ids': {'type': 'array', 'items': {'type': 'string'}},
                    },
                    'required': ['person', 'area'],
                    'additionalProperties': False,
                },
            },
            'next_steps': {
                'type': 'array',
                'description': 'Lista akcji do wykonania (max 7).',
                'items': {
                    'type': 'object',
                    'properties': {
                        'date': {'type': 'string', 'description': 'YYYY-MM-DD lub pusty string.'},
                        'action': {'type': 'string'},
                        'owner': {'type': 'string', 'description': 'Imię Nazwisko / slug / pusty string.'},
                        'source_thought_id': {'type': 'string'},
                    },
                    'required': ['date', 'action', 'owner', 'source_thought_id'],
                    'additionalProperties': False,
                },
            },
        },
        'required': ['current_state', 'recent_decisions', 'open_problems', 'ownership', 'next_steps'],
        'additionalProperties': False,
    },
}


# ─────────────────────────── LLM call + defensive normalizer ──

def _coerce_str(v: Any, default: str = '') -> str:
    if v is None:
        return default
    if isinstance(v, str):
        return v
    return str(v)


def _coerce_list(v: Any) -> list:
    if isinstance(v, list):
        return v
    return []


def _coerce_int(v: Any, default: int = 0) -> int:
    """Defensive int coercion (LLM tool-calls occasionally emit
    non-numeric strings for integer fields despite the declared schema)."""
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _normalize_decisions(items: Any) -> list[dict]:
    out = []
    for it in _coerce_list(items):
        if not isinstance(it, dict):
            continue
        out.append({
            'date': _coerce_str(it.get('date')),
            'content': _coerce_str(it.get('content')),
            'source_thought_id': _coerce_str(it.get('source_thought_id')),
        })
    return out


def _normalize_problems(items: Any) -> list[dict]:
    out = []
    for it in _coerce_list(items):
        if not isinstance(it, dict):
            continue
        sev = _coerce_str(it.get('severity'), 'medium')
        if sev not in ('high', 'medium', 'low'):
            sev = 'medium'
        out.append({
            'severity': sev,
            'content': _coerce_str(it.get('content')),
            'source_thought_id': _coerce_str(it.get('source_thought_id')),
        })
    return out


def _normalize_ownership(items: Any) -> list[dict]:
    out = []
    for it in _coerce_list(items):
        if not isinstance(it, dict):
            continue
        out.append({
            'person': _coerce_str(it.get('person')),
            'area': _coerce_str(it.get('area')),
            'source_thought_ids': [_coerce_str(x) for x in _coerce_list(it.get('source_thought_ids'))],
        })
    return out


def _normalize_next_steps(items: Any) -> list[dict]:
    out = []
    for it in _coerce_list(items):
        if not isinstance(it, dict):
            continue
        out.append({
            'date': _coerce_str(it.get('date')),
            'action': _coerce_str(it.get('action')),
            'owner': _coerce_str(it.get('owner')),
            'source_thought_id': _coerce_str(it.get('source_thought_id')),
        })
    return out


def _coerce_gap_radar(raw: dict) -> dict:
    """Normalizer for gap_radar LLM output ({narrative_pl, top_gaps, total_gaps_count})."""
    if not isinstance(raw, dict):
        raw = {}
    top_gaps = raw.get('top_gaps') or []
    if not isinstance(top_gaps, list):
        top_gaps = []
    return {
        'narrative_pl': _coerce_str(raw.get('narrative_pl')),
        'top_gaps': [
            {
                'type': str(g.get('type', '')),
                'title': str(g.get('title', '')),
                'suggested_action': str(g.get('suggested_action', '')),
            }
            for g in top_gaps if isinstance(g, dict)
        ],
        'total_gaps_count': int(raw.get('total_gaps_count') or 0),
    }


def _coerce_area_digest(raw: dict) -> dict:
    """Normalizer for area_digest LLM output."""
    if not isinstance(raw, dict):
        raw = {}
    docs = raw.get('dokumenty_wyrozniajace_sie') or []
    if not isinstance(docs, list):
        docs = []
    powiazania = raw.get('powiazania') or []
    if not isinstance(powiazania, list):
        powiazania = []
    return {
        'stan_dzis': _coerce_str(raw.get('stan_dzis')),
        'dokumenty_wyrozniajace_sie': [
            {'tytul': _coerce_str(d.get('tytul')), 'powod': _coerce_str(d.get('powod'))}
            for d in docs if isinstance(d, dict)
        ],
        'powiazania': [_coerce_str(p) for p in powiazania if isinstance(p, (str, int, float))],
    }


def _coerce_backlog_health(raw: dict) -> dict:
    """Normalizer for backlog_health LLM output."""
    if not isinstance(raw, dict):
        raw = {}
    zaleglosci = raw.get('zaleglosci') or []
    if not isinstance(zaleglosci, list):
        zaleglosci = []
    chains = raw.get('lancuchy_blokad') or []
    if not isinstance(chains, list):
        chains = []
    return {
        'stan_dzis': _coerce_str(raw.get('stan_dzis')),
        'zaleglosci': [
            {'ticket': _coerce_str(z.get('ticket')), 'opis': _coerce_str(z.get('opis'))}
            for z in zaleglosci if isinstance(z, dict)
        ],
        'lancuchy_blokad': [
            {
                'ticket': _coerce_str(c.get('ticket')),
                'blokuje_ile': _coerce_int(c.get('blokuje_ile')),
                'opis': _coerce_str(c.get('opis')),
            }
            for c in chains if isinstance(c, dict)
        ],
    }


def _coerce_synthesis(raw: dict) -> dict:
    """Defensive normalizer at LLM-output reconcile boundary (F3 lesson)."""
    if not isinstance(raw, dict):
        raw = {}
    return {
        'current_state': _coerce_str(raw.get('current_state')),
        'recent_decisions': _normalize_decisions(raw.get('recent_decisions')),
        'open_problems': _normalize_problems(raw.get('open_problems')),
        'ownership': _normalize_ownership(raw.get('ownership')),
        'next_steps': _normalize_next_steps(raw.get('next_steps')),
    }


def _use_case_for_perspective(perspective_type: str) -> str:
    """Map perspective_type → llm_router use_case key (config/llm_routing.yaml)."""
    return f'second_brain.F4_synthesis_{perspective_type}'


def _system_prompt_text() -> str:
    """build_system_prompt() returns the Anthropic-native cache_control block list;
    llm_router takes a plain string and applies cache_control itself."""
    blocks = build_system_prompt()
    if isinstance(blocks, list):
        return ''.join(b.get('text', '') for b in blocks if isinstance(b, dict))
    return str(blocks)


# Per-perspective max_tokens overrides — large-output perspectives need bigger
# Qwen budget so the JSON tool_call doesn't truncate mid-string. Without these
# bumps, news_cluster (~150 source thoughts) and monthly (~30+) regularly
# exhaust the 4096 default → llm_router fallback to anthropic kicks in (works
# but loses Qwen cost advantage). 8192 keeps Qwen happy path; if a future
# perspective needs more, router fallback still saves the call.
_MAX_TOKENS_BY_PERSPECTIVE = {
    'news_cluster': 8192,
    'monthly': 8192,
    'tag': 8192,
    'type': 8192,
    'frp_evolution_timeline': 8192,
}
_DEFAULT_MAX_TOKENS = 4096


def _max_tokens_for(perspective_type: str) -> int:
    return _MAX_TOKENS_BY_PERSPECTIVE.get(perspective_type, _DEFAULT_MAX_TOKENS)


def call_llm(perspective_type: str, perspective_key: str,
             source_thoughts: list[dict], edges: list[dict],
             tenant_id: str | None = None) -> tuple[dict, dict]:
    from exocortex import llm_routing
    llm_routing.initialize()
    from llm_router import call_tool as _router_call_tool

    user_text = build_user_prompt(perspective_type, perspective_key,
                                  source_thoughts, edges, tenant_id=tenant_id)
    # area_digest/backlog_health get their OWN tool schema and
    # system prompt (not the meeting-shaped SYNTHESIZE_TOOL / SYSTEM_PROMPT_TEXT
    # gap_radar reuses via prompt-only override) — these perspectives have no
    # participants/decisions/ownership, forcing them through the 5-section
    # schema would either produce empty required fields or invite the model
    # to invent them.
    if perspective_type == 'area_digest':
        tool = AREA_DIGEST_TOOL
        system_text = AREA_DIGEST_SYSTEM_PROMPT
    elif perspective_type == 'backlog_health':
        tool = BACKLOG_HEALTH_TOOL
        system_text = BACKLOG_HEALTH_SYSTEM_PROMPT
    else:
        tool = SYNTHESIZE_TOOL
        system_text = _system_prompt_text()
    schema = {
        'name': tool['name'],
        'description': tool.get('description', ''),
        'input_schema': tool['input_schema'],
    }
    tool_input, usage = _router_call_tool(
        use_case=_use_case_for_perspective(perspective_type),
        system=system_text,
        user=user_text,
        schema=schema,
        max_tokens=_max_tokens_for(perspective_type),
        cache_system=True,
    )
    legacy_usage = {
        'input_tokens': usage.input_tokens,
        'output_tokens': usage.output_tokens,
        'cache_creation_input_tokens': usage.cache_creation_input_tokens,
        'cache_read_input_tokens': usage.cache_read_input_tokens,
        '_provider': usage.provider,
        '_model': usage.model,
        '_cost_usd': usage.cost_usd,
        '_latency_ms': usage.latency_ms,
        '_use_case': usage.use_case,
        '_fallback_chain': list(usage.fallback_chain),
    }
    return tool_input, legacy_usage


def estimate_cost_usd(usage: dict) -> float:
    """Router-aware cost — re-exported from llm_utils for backward compat (F31-CLN-01)."""
    from exocortex.llm_utils import estimate_cost_usd as _fn
    return _fn(usage)


# ─────────────────────────────────── Persistence (append-only) ──

def get_active_synthesis(tenant_id: str, perspective_type: str,
                         perspective_key: str) -> dict | None:
    sql = (
        "SELECT id, input_hash, generated_at, content "
        "FROM syntheses "
        "WHERE tenant_id = %s AND perspective_type = %s "
        "  AND perspective_key = %s AND prompt_version = %s "
        "  AND superseded_by IS NULL "
        "ORDER BY generated_at DESC LIMIT 1"
    )
    return query_one(sql, tenant_id, perspective_type, perspective_key, PROMPT_VERSION)


def persist_synthesis(tenant_id: str, perspective_type: str, perspective_key: str,
                      content: dict, source_thought_ids: list[str], input_hash: str,
                      usage: dict, cost_usd: float,
                      previous_id: str | None = None) -> str:
    """Append-only persist. When `previous_id` is set: supersede the old active row
    BEFORE inserting the new one (otherwise the partial UNIQUE on active rows fires).
    Both ops run in one transaction; the superseded_by FK is DEFERRABLE INITIALLY
    DEFERRED so the UPDATE can target a uuid the INSERT hasn't produced yet."""
    import uuid as _uuid
    new_id = str(_uuid.uuid4())
    tokens = (usage.get('input_tokens', 0) + usage.get('output_tokens', 0)
              + usage.get('cache_creation_input_tokens', 0)
              + usage.get('cache_read_input_tokens', 0))
    # F29.5 fix: persist the model the llm_router ACTUALLY used (from
    # `usage._model`), not the legacy synthesizer default `LLM_MODEL`. The default
    # is wrong post-router (the routing config picks per-use-case), and the
    # default was leaking into provenance banners on wiki pages.
    actual_model = usage.get('_model') or LLM_MODEL
    with conn() as c:
        with c.transaction():
            if previous_id:
                c.execute("UPDATE syntheses SET superseded_by = %s WHERE id = %s",
                          (new_id, str(previous_id)))
            c.execute("""
                INSERT INTO syntheses (
                    id, tenant_id, perspective_type, perspective_key, content,
                    source_thought_ids, input_hash, llm_tokens_used, llm_cost_usd,
                    model, prompt_version
                ) VALUES (%s, %s, %s, %s, %s::jsonb, %s::uuid[], %s, %s, %s, %s, %s)
            """, (
                new_id, tenant_id, perspective_type, perspective_key,
                json.dumps(content), source_thought_ids, input_hash,
                tokens, round(cost_usd, 6),
                actual_model, PROMPT_VERSION,
            ))
            # F4.6.1: emit decided_in / addresses_problem / mentions_person edges
            # in the same transaction (PG + AGE dual-write idempotent — no rollback risk).
            try:
                _emit_synthesis_edges(c, new_id, content, tenant_id)
            except Exception as exc:  # noqa: BLE001 — never block synthesis persist
                logger.warning("edge emit error for %s: %r", new_id[:8], exc)
    return new_id


# ───────────────────────────── Public API: synthesize() ──

def synthesize(perspective_type: str, perspective_key: str,
               source_thoughts: list[dict] | None = None, *,
               tenant_id: str | None = None,
               dry_run: bool = False,
               force: bool = False) -> SynthesisResult:
    """Synthesize a perspective. Idempotent — skips when input_hash unchanged.

    Args:
      source_thoughts: optional pre-fetched list. If None, selected from DB.
      force: bypass idempotency check, always re-LLM.
    """
    tenant_id = tenant_id or TENANT_ID
    if not tenant_id:
        return SynthesisResult(perspective_type, perspective_key, 'error',
                               reason='no tenant_id (set TENANT_ID env or pass arg)')
    if perspective_type not in PERSPECTIVE_TYPES:
        return SynthesisResult(perspective_type, perspective_key, 'error',
                               reason=f'unknown perspective_type: {perspective_type}')

    if source_thoughts is None:
        source_thoughts = select_source_thoughts(tenant_id, perspective_type, perspective_key)

    if not source_thoughts:
        return SynthesisResult(perspective_type, perspective_key, 'no-thoughts',
                               reason='0 matching source thoughts')

    threshold = THRESHOLDS.get(perspective_type, 1)
    if len(source_thoughts) < threshold:
        return SynthesisResult(
            perspective_type, perspective_key, 'below-threshold',
            reason=f'only {len(source_thoughts)} thoughts (threshold={threshold})',
            source_thought_ids=[str(t['id']) for t in source_thoughts],
        )

    # F31.5.2 — gap_radar pseudo-thoughts use synthetic ids (e.g. "gap-0");
    # the real underlying thought UUIDs come from each gap's `thought_ids` list.
    if perspective_type == 'gap_radar':
        _real_ids: list[str] = []
        for t in source_thoughts:
            for tid in ((t.get('_gap') or {}).get('thought_ids') or []):
                if tid not in _real_ids:
                    _real_ids.append(str(tid))
        source_ids = _real_ids
    else:
        source_ids = [str(t['id']) for t in source_thoughts]
    input_hash = compute_input_hash(perspective_type, perspective_key, source_thoughts)

    existing = get_active_synthesis(tenant_id, perspective_type, perspective_key)
    if existing and existing['input_hash'] == input_hash and not force:
        return SynthesisResult(
            perspective_type, perspective_key, 'skipped',
            reason='input_hash matches active synthesis',
            content=existing['content'],
            source_thought_ids=source_ids,
            input_hash=input_hash,
            synthesis_id=str(existing['id']),
        )

    # F4.6.2 — edges-aware: load typed reasoning edges + entity/synthesis names
    # so the LLM can quote cross-perspective context in its synthesis.
    edges = fetch_edges_for_thoughts(tenant_id, source_ids)

    try:
        llm_raw, usage = call_llm(perspective_type, perspective_key,
                                  source_thoughts, edges, tenant_id=tenant_id)
    except Exception as exc:
        return SynthesisResult(perspective_type, perspective_key, 'error',
                               reason=repr(exc),
                               source_thought_ids=source_ids,
                               input_hash=input_hash)

    # gap_radar / area_digest / backlog_health each have their own JSON shape
    # that differs from the meeting-shaped 5-section schema _coerce_synthesis
    # enforces (see call_llm — each also gets its own tool schema + prompt).
    if perspective_type == 'gap_radar':
        content = _coerce_gap_radar(llm_raw)
    elif perspective_type == 'area_digest':
        content = _coerce_area_digest(llm_raw)
    elif perspective_type == 'backlog_health':
        content = _coerce_backlog_health(llm_raw)
    else:
        content = _coerce_synthesis(llm_raw)
    cost = estimate_cost_usd(usage)

    new_id = None
    if not dry_run:
        new_id = persist_synthesis(
            tenant_id, perspective_type, perspective_key,
            content, source_ids, input_hash,
            usage, cost,
            previous_id=str(existing['id']) if existing else None,
        )

    return SynthesisResult(
        perspective_type=perspective_type,
        perspective_key=perspective_key,
        status='ok',
        content=content,
        source_thought_ids=source_ids,
        input_hash=input_hash,
        usage=usage,
        cost_usd=cost,
        synthesis_id=new_id,
        superseded_id=str(existing['id']) if existing else None,
    )


# ────────────────── Bulk discovery: find all perspectives to synthesize ──

def discover_perspectives(tenant_id: str) -> list[tuple[str, str, int]]:
    """Returns list of (perspective_type, perspective_key, source_count) for all
    perspectives present in the corpus that meet their threshold."""
    found: list[tuple[str, str, int]] = []

    # client / project / activity (=type) / topic|status (=tag) — extracted_tags axes
    # F4.6.6.7: 'metadata-tag' axis reads legacy `metadata.tags` (Fireflies tags + F2.2
    # TYPE_TAGS: wks/weekly/presales/internal/1on1/wow/leadership) that the F3 LLM tagger
    # did not carry over to extracted_tags.{topic,activity,status}. Symmetric with
    # _select_thoughts_for_tag, which reads from 5 sources (4 extracted_tags axes + metadata.tags).
    axes_query = """
        SELECT axis, value, count(*) AS n FROM (
            SELECT 'client' AS axis, jsonb_array_elements(extracted_tags->'client')->>'value' AS value FROM thoughts WHERE tenant_id = %s AND thought_type = %s
            UNION ALL
            SELECT 'project', jsonb_array_elements(extracted_tags->'project')->>'value' FROM thoughts WHERE tenant_id = %s AND thought_type = %s
            UNION ALL
            SELECT 'activity', jsonb_array_elements(extracted_tags->'activity')->>'value' FROM thoughts WHERE tenant_id = %s AND thought_type = %s
            UNION ALL
            SELECT 'topic', jsonb_array_elements(extracted_tags->'topic')->>'value' FROM thoughts WHERE tenant_id = %s AND thought_type = %s
            UNION ALL
            SELECT 'status', jsonb_array_elements(extracted_tags->'status')->>'value' FROM thoughts WHERE tenant_id = %s AND thought_type = %s
            UNION ALL
            SELECT 'metadata-tag', jsonb_array_elements_text(metadata->'tags') FROM thoughts WHERE tenant_id = %s AND thought_type = %s AND jsonb_typeof(metadata->'tags') = 'array'
        ) t
        WHERE value IS NOT NULL AND value <> ''
        GROUP BY axis, value
    """
    rows = query(axes_query,
                 tenant_id, THOUGHT_TYPE,
                 tenant_id, THOUGHT_TYPE,
                 tenant_id, THOUGHT_TYPE,
                 tenant_id, THOUGHT_TYPE,
                 tenant_id, THOUGHT_TYPE,
                 tenant_id, THOUGHT_TYPE)
    # 'tag' perspective collapses topic/status/metadata-tag into one keyspace.
    # Aggregate counts across axes for the same key, then take the max (rather than sum)
    # — the same meeting may be reachable from multiple axes for the same tag, so
    # `_select_thoughts_for_tag` will deduplicate via OR-ed predicates. Using max gives
    # the per-axis count, which is a safe lower bound for the true source count.
    tag_counts: dict[str, int] = {}
    for r in rows:
        n = int(r['n'])
        axis, value = r['axis'], r['value']
        if axis == 'client' and n >= THRESHOLDS['client']:
            found.append(('client', value, n))
        elif axis == 'project' and n >= THRESHOLDS['project']:
            found.append(('project', value, n))
        elif axis == 'activity' and n >= THRESHOLDS['type']:
            found.append(('type', value, n))
        elif axis in ('topic', 'status', 'metadata-tag'):
            tag_counts[value] = max(tag_counts.get(value, 0), n)
    for value, n in tag_counts.items():
        if n >= THRESHOLDS['tag']:
            found.append(('tag', value, n))

    # person — metadata.participants
    person_rows = query("""
        SELECT person, count(*) AS n FROM (
            SELECT jsonb_array_elements_text(metadata->'participants') AS person
            FROM thoughts WHERE tenant_id = %s AND thought_type = %s
              AND jsonb_typeof(metadata->'participants') = 'array'
        ) t
        WHERE person IS NOT NULL AND person <> ''
        GROUP BY person
    """, tenant_id, THOUGHT_TYPE)
    for r in person_rows:
        if int(r['n']) >= THRESHOLDS['person']:
            found.append(('person', r['person'], int(r['n'])))

    # monthly — distinct YYYY-MM from metadata.date or created_at
    month_rows = query("""
        SELECT month, count(*) AS n FROM (
            SELECT substring(coalesce(metadata->>'date',
                                      to_char(created_at, 'YYYY-MM-DD')), 1, 7) AS month
            FROM thoughts WHERE tenant_id = %s AND thought_type = %s
        ) t
        WHERE month IS NOT NULL
        GROUP BY month
    """, tenant_id, THOUGHT_TYPE)
    for r in month_rows:
        if int(r['n']) >= THRESHOLDS['monthly']:
            found.append(('monthly', r['month'], int(r['n'])))

    # ─────────── corpus perspectives (vault_note / backlog_item) ──
    area_rows = query("""
        SELECT metadata->'section_path'->>1 AS area, count(*) AS n
        FROM thoughts WHERE tenant_id = %s AND thought_type = 'vault_note'
        GROUP BY area
    """, tenant_id)
    for r in area_rows:
        if r['area'] and int(r['n']) >= THRESHOLDS['area_digest']:
            found.append(('area_digest', r['area'], int(r['n'])))

    backlog_area_rows = query("""
        SELECT metadata->>'area' AS area, count(*) AS n
        FROM thoughts WHERE tenant_id = %s AND thought_type = 'backlog_item'
        GROUP BY area
    """, tenant_id)
    for r in backlog_area_rows:
        if r['area'] and int(r['n']) >= THRESHOLDS['backlog_health']:
            found.append(('backlog_health', r['area'], int(r['n'])))

    # ─────────── F7.3 — FRP perspectives ─────────────────────────────────
    # frp_per_frame — count thoughts per (session.frame). Skipped quietly when
    # any of the FRP / content_queue tables don't exist (legacy schemas).
    try:
        frame_rows = query("""
            SELECT s.frame AS frame, count(*) AS n FROM thoughts t
            JOIN edges e ON e.dst_id = t.id AND e.type = 'session_contains'
            JOIN frp_sessions s ON s.id = e.src_id
            WHERE t.tenant_id = %s
              AND t.thought_type LIKE %s ESCAPE %s
              AND s.frame IS NOT NULL
            GROUP BY s.frame
        """, tenant_id, _FRP_LIKE_PATTERN, '\\')
        for r in frame_rows:
            if int(r['n']) >= THRESHOLDS['frp_per_frame']:
                found.append(('frp_per_frame', r['frame'], int(r['n'])))
    except Exception as exc:
        logging.warning('[synthesizer] frp_per_frame discovery skipped: %s', exc)

    # frp_per_domain — content_queue.ai_tags->>'domain' until F7.4 lights up signals_domain.
    try:
        dom_rows = query("""
            SELECT cq.ai_tags->>'domain' AS domain, count(*) AS n FROM thoughts t
            JOIN edges e ON e.dst_id = t.id AND e.type = 'session_contains'
            JOIN frp_sessions s ON s.id = e.src_id
            JOIN content_queue cq ON cq.id = s.content_id
            WHERE t.tenant_id = %s
              AND t.thought_type LIKE %s ESCAPE %s
              AND cq.ai_tags->>'domain' IS NOT NULL
              AND cq.ai_tags->>'domain' <> ''
            GROUP BY cq.ai_tags->>'domain'
        """, tenant_id, _FRP_LIKE_PATTERN, '\\')
        for r in dom_rows:
            if int(r['n']) >= THRESHOLDS['frp_per_domain']:
                found.append(('frp_per_domain', r['domain'], int(r['n'])))
    except Exception as exc:
        logging.warning('[synthesizer] frp_per_domain discovery skipped: %s', exc)

    # frp_evolution_timeline — single 'all' key when the corpus is large enough.
    try:
        sess_count = query_one(
            "SELECT count(*) AS n FROM frp_sessions WHERE tenant_id = %s",
            tenant_id,
        )
        if sess_count and int(sess_count['n']) >= 10:
            thought_count = query_one("""
                SELECT count(*) AS n FROM thoughts t
                JOIN edges e ON e.dst_id = t.id AND e.type = 'session_contains'
                WHERE t.tenant_id = %s
                  AND t.thought_type LIKE %s ESCAPE %s
            """, tenant_id, _FRP_LIKE_PATTERN, '\\')
            n = int(thought_count['n']) if thought_count else 0
            if n >= THRESHOLDS['frp_evolution_timeline']:
                found.append(('frp_evolution_timeline', 'all', n))
    except Exception as exc:
        logging.warning('[synthesizer] frp_evolution_timeline discovery skipped: %s', exc)

    # frp_per_resonance — discover one perspective per resonance bucket (3, 4, 5),
    # using "thoughts attached to sessions with resonance >= K" as the count.
    try:
        for min_r in (3, 4, 5):
            res_count = query_one("""
                SELECT count(*) AS n FROM thoughts t
                JOIN edges e ON e.dst_id = t.id AND e.type = 'session_contains'
                JOIN frp_sessions s ON s.id = e.src_id
                WHERE t.tenant_id = %s
                  AND t.thought_type LIKE %s ESCAPE %s
                  AND s.resonance >= %s
            """, tenant_id, _FRP_LIKE_PATTERN, '\\', min_r)
            n = int(res_count['n']) if res_count else 0
            if n >= THRESHOLDS['frp_per_resonance']:
                found.append(('frp_per_resonance', str(min_r), n))
    except Exception as exc:
        logging.warning('[synthesizer] frp_per_resonance discovery skipped: %s', exc)

    # frp_monthly — distinct YYYY-MM from FRP thoughts' created_at.
    try:
        frp_month_rows = query("""
            SELECT month, count(*) AS n FROM (
                SELECT substring(to_char(created_at, 'YYYY-MM-DD'), 1, 7) AS month
                FROM thoughts WHERE tenant_id = %s
                  AND thought_type LIKE %s ESCAPE %s
            ) t
            WHERE month IS NOT NULL
            GROUP BY month
        """, tenant_id, _FRP_LIKE_PATTERN, '\\')
        for r in frp_month_rows:
            if int(r['n']) >= THRESHOLDS['frp_monthly']:
                found.append(('frp_monthly', r['month'], int(r['n'])))
    except Exception as exc:
        logging.warning('[synthesizer] frp_monthly discovery skipped: %s', exc)

    # ─────────── F8.8.x.B — news_cluster perspectives ─────────────────────
    # One synthesis per cluster slug with ≥THRESHOLDS['news_cluster'] member
    # newsletter_synthesis thoughts. Source list comes from yaml; per-cluster
    # count uses the same JSONB EXISTS query as _select_thoughts_for_news_cluster.
    try:
        clusters = _load_news_clusters()
        for cluster_slug, topics in clusters.items():
            if not topics:
                continue
            row = query_one("""
                SELECT count(*) AS n FROM thoughts t
                WHERE t.tenant_id = %s
                  AND t.thought_type = 'newsletter_synthesis'
                  AND EXISTS (
                    SELECT 1 FROM jsonb_array_elements(t.extracted_tags->'topic') AS topic_obj
                    WHERE topic_obj->>'value' = ANY(%s)
                  )
            """, tenant_id, topics)
            n = int(row['n']) if row else 0
            if n >= THRESHOLDS['news_cluster']:
                found.append(('news_cluster', cluster_slug, n))
    except Exception as exc:
        logging.warning('[synthesizer] news_cluster discovery skipped: %s', exc)

    return sorted(found, key=lambda x: (x[0], x[1]))
