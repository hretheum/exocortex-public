#!/usr/bin/env -S python3.12
# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/cross_domain_matcher.py — F8.8.x.G T2.
#
# Thematic inspiration matching: judge each (active client synthesis × active
# news_cluster synthesis) pair via claude-haiku and emit `cross_references`
# edges when the LLM scores the pair >= THRESHOLD.
#
# Idempotency layered (lessons-learned): per-pair sidecar UNIQUE on
# (client_synthesis_id, cluster_synthesis_id, prompt_version) + ON CONFLICT
# DO NOTHING; edges UNIQUE via uq_edges_dedupe; in-process dict cache for the
# duration of the run. The prompt_version key embeds client + cluster
# input_hash so a regenerated synthesis (new id) cleanly invalidates the cache.

from __future__ import annotations

import hashlib
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from exocortex.db import conn, query, query_one
from exocortex.settings import get_tenant_id

load_dotenv(dotenv_path=_REPO_ROOT / 'config' / '.env')

logger = logging.getLogger(__name__)

LLM_MODEL = 'claude-haiku-4-5-20251001'  # log strings only — model selected by llm_router
PROMPT_VERSION = 'v1'
THRESHOLD = 6  # design D4 — score >=6 emits an edge + appears on wiki
TENANT_ID = get_tenant_id()
ACTIVE_CLIENT_WINDOW_DAYS = 90
ACTIVE_CLUSTER_MIN_SOURCES = 5
EDGE_CREATED_BY = 'cross_domain_matcher'


# ─────────────────────────── Scope queries (design D5) ──

def _load_active_clients(tenant_id: str) -> list[dict]:
    sql = """
    SELECT id, perspective_key, content, input_hash
    FROM syntheses
    WHERE tenant_id = %s
      AND perspective_type = 'client'
      AND superseded_by IS NULL
      AND generated_at > NOW() - (%s || ' days')::interval
    ORDER BY perspective_key
    """
    return query(sql, tenant_id, str(ACTIVE_CLIENT_WINDOW_DAYS))


def _load_active_clusters(tenant_id: str) -> list[dict]:
    """Active = synthesis row + at least N source thoughts. `syntheses` has
    no `source_thought_count` column (verified F8.8.x.G T2 pre-flight) — count
    via array_length on `source_thought_ids`."""
    sql = """
    SELECT id, perspective_key, content, input_hash
    FROM syntheses
    WHERE tenant_id = %s
      AND perspective_type = 'news_cluster'
      AND superseded_by IS NULL
      AND coalesce(array_length(source_thought_ids, 1), 0) >= %s
    ORDER BY perspective_key
    """
    return query(sql, tenant_id, ACTIVE_CLUSTER_MIN_SOURCES)


# ─────────────────────────── Prompt building (design D2) ──

SYSTEM_PROMPT_TEXT = (
    "Jesteś analitykiem cross-domain. Twoja praca: ocenić, czy newsletter "
    "cluster (kategoria AI/tech) niesie konkretną inspirację dla bieżącej "
    "pracy z klientem (polski sektor bankowy/retail/ubezpieczenia/itp).\n\n"
    "Skala 0-10 (kotwice):\n"
    "- 0-3: niezwiązane, brak konkretnego wątku\n"
    "- 4-5: ogólny kierunek (np. \"obie strony używają AI\") — za słabe\n"
    "- 6-7: konkretna inspiracja (technika, framework, ryzyko) bezpośrednio "
    "dotyczy aktywnego problemu klienta\n"
    "- 8-10: gotowy precedens / blueprint, można zacytować w rozmowie z klientem\n\n"
    "Output PL, ≤200 znaków `reason`. Cytuj konkretne tematy z obu stron, nie "
    "ogólniki. Jeśli score <6, krótkie zdanie dlaczego nie. Tool use strict — "
    "odpowiadaj wyłącznie przez `judge_cross_domain_match` tool."
)

JUDGE_TOOL = {
    'name': 'judge_cross_domain_match',
    'description': 'Ocena czy newsletter cluster niesie konkretną inspirację dla aktywnej pracy klienta.',
    'input_schema': {
        'type': 'object',
        'properties': {
            'relevance_score': {
                'type': 'integer',
                'minimum': 0,
                'maximum': 10,
                'description': '0-10 wg skali w system prompt.',
            },
            'reason': {
                'type': 'string',
                'maxLength': 200,
                'description': 'Krótkie uzasadnienie po polsku ≤200 znaków, cytuje konkretne tematy.',
            },
        },
        'required': ['relevance_score', 'reason'],
        'additionalProperties': False,
    },
}


def build_system_prompt() -> list[dict]:
    return [{'type': 'text', 'text': SYSTEM_PROMPT_TEXT, 'cache_control': {'type': 'ephemeral'}}]


def _format_problems(items: list[dict] | None, limit: int) -> str:
    out: list[str] = []
    for it in (items or [])[:limit]:
        if not isinstance(it, dict):
            continue
        sev = (it.get('severity') or '').strip()
        content = (it.get('content') or '').strip()
        if not content:
            continue
        prefix = f"[{sev}] " if sev else ''
        out.append(f"- {prefix}{content}")
    return '\n'.join(out) if out else '(brak)'


def _format_next_steps(items: list[dict] | None, limit: int) -> str:
    out: list[str] = []
    for it in (items or [])[:limit]:
        if not isinstance(it, dict):
            continue
        action = (it.get('action') or '').strip()
        if not action:
            continue
        date = (it.get('date') or '').strip()
        prefix = f"[{date}] " if date else ''
        out.append(f"- {prefix}{action}")
    return '\n'.join(out) if out else '(brak)'


def _format_decisions(items: list[dict] | None, limit: int) -> str:
    out: list[str] = []
    for it in (items or [])[:limit]:
        if not isinstance(it, dict):
            continue
        content = (it.get('content') or '').strip()
        if not content:
            continue
        date = (it.get('date') or '').strip()
        prefix = f"[{date}] " if date else ''
        out.append(f"- {prefix}{content}")
    return '\n'.join(out) if out else '(brak)'


def build_user_prompt(client: dict, cluster: dict) -> str:
    cc = client.get('content') or {}
    kc = cluster.get('content') or {}
    return (
        f"KLIENT: {client['perspective_key']}\n"
        f"Aktualny stan: {(cc.get('current_state') or '').strip()}\n"
        f"Problemy:\n{_format_problems(cc.get('open_problems'), 5)}\n"
        f"Następne kroki:\n{_format_next_steps(cc.get('next_steps'), 5)}\n\n"
        f"NEWSLETTER CLUSTER: {cluster['perspective_key']}\n"
        f"Aktualny stan: {(kc.get('current_state') or '').strip()}\n"
        f"Decyzje:\n{_format_decisions(kc.get('recent_decisions'), 3)}\n"
        f"Problemy:\n{_format_problems(kc.get('open_problems'), 3)}\n"
        f"Następne kroki:\n{_format_next_steps(kc.get('next_steps'), 3)}\n\n"
        f"Oceń relevance i napisz reason po polsku."
    )


# ─────────────────────────── LLM judge + defensive normalizer ──

def _coerce_score(raw: Any) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return max(0, min(10, raw))
    if isinstance(raw, float):
        try:
            return max(0, min(10, int(raw)))
        except (ValueError, OverflowError):
            return None
    if isinstance(raw, str):
        try:
            return max(0, min(10, int(raw.strip())))
        except (TypeError, ValueError):
            return None
    return None


def _coerce_reason(raw: Any) -> str:
    if not isinstance(raw, str):
        raw = str(raw or '')
    raw = raw.strip()
    if len(raw) > 200:
        # CHECK constraint enforces server-side; trim defensively.
        raw = raw[:200]
    return raw


def _normalize_judgment(tool_input: Any) -> dict | None:
    """LLM occasionally drops/coerces fields (F3 lesson). Return None if score
    can't be coerced — caller skips persistence."""
    if not isinstance(tool_input, dict):
        return None
    score = _coerce_score(tool_input.get('relevance_score'))
    if score is None:
        return None
    reason = _coerce_reason(tool_input.get('reason'))
    if not reason:
        reason = '(brak uzasadnienia z LLM)'
    return {'relevance_score': score, 'reason': reason}


def _system_prompt_text() -> str:
    blocks = build_system_prompt()
    if isinstance(blocks, list):
        return ''.join(b.get('text', '') for b in blocks if isinstance(b, dict))
    return str(blocks)


def _call_llm(user_text: str) -> tuple[dict | None, dict]:
    from exocortex import llm_routing
    llm_routing.initialize()
    from llm_router import call_tool as _router_call_tool
    from llm_router.exceptions import ProviderError

    try:
        tool_input, usage = _router_call_tool(
            use_case='second_brain.F8_cross_domain_matcher',
            system=_system_prompt_text(),
            user=user_text,
            schema=JUDGE_TOOL,
            max_tokens=512,
            cache_system=True,
        )
    except ProviderError as exc:
        logger.warning('cross_domain_matcher: provider chain exhausted: %s', exc)
        return None, {
            'input_tokens': 0, 'output_tokens': 0,
            'cache_creation_input_tokens': 0, 'cache_read_input_tokens': 0,
            '_cost_usd': 0.0,
        }
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
    return _normalize_judgment(tool_input), legacy_usage


def _estimate_cost_usd(usage: dict) -> float:
    """Router-aware: prefer router-computed `_cost_usd`."""
    if '_cost_usd' in usage and usage['_cost_usd'] is not None:
        return float(usage['_cost_usd'])
    return (
        usage.get('input_tokens', 0) * 1.00
        + usage.get('cache_creation_input_tokens', 0) * 1.25
        + usage.get('cache_read_input_tokens', 0) * 0.10
    ) / 1_000_000 + (usage.get('output_tokens', 0) * 5.00) / 1_000_000


# ─────────────────────────── Idempotency / cache ──

def _idempotency_key(client: dict, cluster: dict) -> str:
    """SHA256(prompt_version | client_id | client_input_hash | cluster_id |
    cluster_input_hash)[:16]. Stored in `prompt_version` column on the sidecar
    row so each row is keyed by a single string.

    When either side regenerates, input_hash changes → new sidecar key →
    cache miss → fresh judge call.
    """
    payload = '|'.join([
        PROMPT_VERSION,
        str(client['id']),
        client.get('input_hash') or '',
        str(cluster['id']),
        cluster.get('input_hash') or '',
    ])
    return f"{PROMPT_VERSION}:{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def _existing_match(client_id: str, cluster_id: str, prompt_version_key: str) -> dict | None:
    sql = """
    SELECT id, edge_id, relevance_score, reason, llm_cost_usd
    FROM cross_domain_matches
    WHERE client_synthesis_id = %s
      AND cluster_synthesis_id = %s
      AND prompt_version = %s
    LIMIT 1
    """
    return query_one(sql, client_id, cluster_id, prompt_version_key)


def _cumulative_cost_24h(tenant_id: str) -> float:
    """F4.6.3-style guard. Sum sidecar llm_cost_usd over the last 24h."""
    row = query_one(
        "SELECT coalesce(sum(llm_cost_usd), 0)::float AS c "
        "FROM cross_domain_matches "
        "WHERE tenant_id = %s AND judged_at > NOW() - INTERVAL '24 hours'",
        tenant_id,
    )
    return float(row['c']) if row else 0.0


# ─────────────────────────── Persistence ──

def _persist_match(tenant_id: str, client: dict, cluster: dict,
                   judgment: dict, prompt_version_key: str,
                   llm_cost: float) -> dict:
    """Insert sidecar row; if score >= THRESHOLD, also insert edge and
    backfill `edge_id` on the sidecar row. Idempotent via UNIQUE."""
    edge_id: str | None = None
    inserted = False
    sidecar_id: str | None = None

    with conn() as c:
        # Reserve sidecar row first so the (rare) edge insert that fails for
        # an unrelated reason still leaves a logged judgment.
        sidecar_row = c.execute(
            """
            INSERT INTO cross_domain_matches (
              tenant_id, client_synthesis_id, cluster_synthesis_id,
              prompt_version, relevance_score, reason, llm_cost_usd
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (client_synthesis_id, cluster_synthesis_id, prompt_version)
            DO NOTHING
            RETURNING id
            """,
            [
                tenant_id, client['id'], cluster['id'],
                prompt_version_key,
                int(judgment['relevance_score']),
                judgment['reason'],
                round(float(llm_cost), 6),
            ],
        ).fetchone()

        if sidecar_row is None:
            # ON CONFLICT — concurrent run inserted before us. Re-read the
            # existing row; nothing else to do.
            existing = c.execute(
                "SELECT id, edge_id FROM cross_domain_matches "
                "WHERE client_synthesis_id = %s AND cluster_synthesis_id = %s "
                "  AND prompt_version = %s",
                [client['id'], cluster['id'], prompt_version_key],
            ).fetchone()
            return {
                'sidecar_id': existing['id'] if existing else None,
                'edge_id': existing.get('edge_id') if existing else None,
                'inserted': False,
                'edge_emitted': False,
            }

        sidecar_id = sidecar_row['id']
        inserted = True

        if judgment['relevance_score'] >= THRESHOLD:
            confidence = round(judgment['relevance_score'] / 10.0, 2)
            edge_row = c.execute(
                """
                INSERT INTO edges (tenant_id, src_id, src_type, dst_id, dst_type,
                                   type, confidence, created_by)
                VALUES (%s, %s, 'synthesis', %s, 'synthesis',
                        'cross_references', %s, %s)
                ON CONFLICT (tenant_id, src_id, dst_id, type) DO NOTHING
                RETURNING id
                """,
                [
                    tenant_id, client['id'], cluster['id'],
                    confidence, EDGE_CREATED_BY,
                ],
            ).fetchone()

            if edge_row is None:
                # Edge already existed (re-run after manual purge of sidecar) —
                # fetch its id so we can backfill.
                edge_existing = c.execute(
                    "SELECT id FROM edges "
                    "WHERE tenant_id = %s AND src_id = %s AND dst_id = %s "
                    "  AND type = 'cross_references'",
                    [tenant_id, client['id'], cluster['id']],
                ).fetchone()
                edge_id = edge_existing['id'] if edge_existing else None
            else:
                edge_id = edge_row['id']

            if edge_id is not None:
                c.execute(
                    "UPDATE cross_domain_matches SET edge_id = %s WHERE id = %s",
                    [edge_id, sidecar_id],
                )

    return {
        'sidecar_id': sidecar_id,
        'edge_id': edge_id,
        'inserted': inserted,
        'edge_emitted': edge_id is not None,
    }


# ─────────────────────────── Public API ──

def match_pair(client_synthesis_id: str, cluster_synthesis_id: str,
               *, force: bool = False, dry_run: bool = False,
               tenant_id: str | None = None,
               _client_row: dict | None = None,
               _cluster_row: dict | None = None) -> dict:
    """Single pair judge. Cache-aware: returns cached judgment unless force=True.

    `_client_row` / `_cluster_row` are private hints — passed by `match_all` to
    avoid re-fetching the synthesis content for every pair.
    """
    tid = tenant_id or TENANT_ID
    if not tid:
        raise SystemExit('TENANT_ID not set in env')

    client = _client_row or query_one(
        "SELECT id, perspective_key, content, input_hash FROM syntheses WHERE id = %s",
        client_synthesis_id,
    )
    cluster = _cluster_row or query_one(
        "SELECT id, perspective_key, content, input_hash FROM syntheses WHERE id = %s",
        cluster_synthesis_id,
    )
    if client is None or cluster is None:
        raise ValueError(f"synthesis not found (client={client_synthesis_id}, cluster={cluster_synthesis_id})")

    pv_key = _idempotency_key(client, cluster)

    if not force:
        cached = _existing_match(client['id'], cluster['id'], pv_key)
        if cached is not None:
            logger.info('cache hit %s × %s → %d/10 (sidecar=%s)',
                        client['perspective_key'], cluster['perspective_key'],
                        cached['relevance_score'], cached['id'])
            return {
                'client': client['perspective_key'],
                'cluster': cluster['perspective_key'],
                'relevance_score': cached['relevance_score'],
                'reason': cached['reason'],
                'edge_id': cached['edge_id'],
                'cache_hit': True,
                'cost_usd': 0.0,
                'persisted': False,
                'edge_emitted': cached['edge_id'] is not None,
            }

    user_text = build_user_prompt(client, cluster)

    if dry_run:
        logger.info('[dry-run] would judge %s × %s (prompt_version=%s, %d chars user prompt)',
                    client['perspective_key'], cluster['perspective_key'],
                    pv_key, len(user_text))
        return {
            'client': client['perspective_key'],
            'cluster': cluster['perspective_key'],
            'relevance_score': None,
            'reason': '<dry-run>',
            'cache_hit': False,
            'cost_usd': 0.0,
            'persisted': False,
            'edge_emitted': False,
            'prompt_version': pv_key,
        }

    judgment, usage = _call_llm(user_text)
    cost = _estimate_cost_usd(usage)

    if judgment is None:
        logger.error('judgment normalization failed for %s × %s — skipping persist',
                     client['perspective_key'], cluster['perspective_key'])
        return {
            'client': client['perspective_key'],
            'cluster': cluster['perspective_key'],
            'relevance_score': None,
            'reason': '<llm-malformed>',
            'cache_hit': False,
            'cost_usd': cost,
            'persisted': False,
            'edge_emitted': False,
        }

    persist_result = _persist_match(tid, client, cluster, judgment, pv_key, cost)

    logger.info('judged %s × %s → %d/10 (cost=$%.4f, edge=%s, "%s")',
                client['perspective_key'], cluster['perspective_key'],
                judgment['relevance_score'], cost,
                'yes' if persist_result['edge_emitted'] else 'no',
                judgment['reason'][:80])

    return {
        'client': client['perspective_key'],
        'cluster': cluster['perspective_key'],
        'relevance_score': judgment['relevance_score'],
        'reason': judgment['reason'],
        'edge_id': persist_result['edge_id'],
        'cache_hit': False,
        'cost_usd': cost,
        'persisted': persist_result['inserted'],
        'edge_emitted': persist_result['edge_emitted'],
        'prompt_version': pv_key,
    }


def match_all(*, dry_run: bool = False, cost_stop_usd: float = 5.0,
              missing_only: bool = True, force: bool = False,
              client_filter: str | None = None,
              cluster_filter: str | None = None,
              tenant_id: str | None = None) -> dict:
    """Batch judge. By default 12 × 8 = 96 pairs. Layered idempotency: in-process
    set of `(client_id, cluster_id, prompt_version)` keys to skip already-judged
    pairs in the same run; sidecar UNIQUE handles cross-run dedup.

    `cost_stop_usd` aborts further LLM calls once cumulative SPEND IN THIS RUN
    exceeds the cap. A separate 24h pre-flight guard checks total recent cost
    before the loop and aborts with exit code 3 if already over.
    """
    tid = tenant_id or TENANT_ID
    if not tid:
        raise SystemExit('TENANT_ID not set in env')

    cumulative_24h = _cumulative_cost_24h(tid)
    if cumulative_24h >= cost_stop_usd:
        logger.error('cost-stop pre-flight: 24h cumulative cost $%.4f >= $%.2f cap; aborting',
                     cumulative_24h, cost_stop_usd)
        return {
            'aborted': True,
            'reason': 'cost_stop_pre_flight',
            'cumulative_cost_24h': cumulative_24h,
            'cost_stop_usd': cost_stop_usd,
            'judged': 0,
            'cache_hits': 0,
            'edges_emitted': 0,
            'total_cost_usd': 0.0,
        }

    clients = _load_active_clients(tid)
    clusters = _load_active_clusters(tid)

    if client_filter:
        clients = [c for c in clients if c['perspective_key'] == client_filter]
    if cluster_filter:
        clusters = [c for c in clusters if c['perspective_key'] == cluster_filter]

    if not clients:
        logger.warning('no active client syntheses (filter=%s)', client_filter)
    if not clusters:
        logger.warning('no active cluster syntheses (filter=%s)', cluster_filter)

    n_pairs = len(clients) * len(clusters)
    logger.info('match_all: %d clients × %d clusters = %d pairs (dry_run=%s, missing_only=%s, force=%s)',
                len(clients), len(clusters), n_pairs, dry_run, missing_only, force)

    judged = 0
    cache_hits = 0
    edges_emitted = 0
    skipped_existing = 0
    malformed = 0
    total_cost = 0.0
    aborted = False
    seen_keys: set[tuple[str, str, str]] = set()

    for client in clients:
        for cluster in clusters:
            key = (str(client['id']), str(cluster['id']), _idempotency_key(client, cluster))
            if key in seen_keys:
                continue
            seen_keys.add(key)

            if missing_only and not force:
                existing = _existing_match(client['id'], cluster['id'], key[2])
                if existing is not None:
                    skipped_existing += 1
                    continue

            if not dry_run and total_cost >= cost_stop_usd:
                logger.warning('cost-stop in-run: $%.4f >= $%.2f, halting at %s × %s',
                               total_cost, cost_stop_usd,
                               client['perspective_key'], cluster['perspective_key'])
                aborted = True
                break

            try:
                result = match_pair(
                    str(client['id']), str(cluster['id']),
                    force=force, dry_run=dry_run, tenant_id=tid,
                    _client_row=client, _cluster_row=cluster,
                )
            except Exception:
                logger.exception('match_pair failed: %s × %s — skipping',
                                 client['perspective_key'], cluster['perspective_key'])
                malformed += 1
                continue

            if result.get('cache_hit'):
                cache_hits += 1
            elif result.get('relevance_score') is None and not dry_run:
                malformed += 1
            else:
                judged += 1
                total_cost += result.get('cost_usd', 0.0) or 0.0
                if result.get('edge_emitted'):
                    edges_emitted += 1

        if aborted:
            break

    summary = {
        'aborted': aborted,
        'pairs_total': n_pairs,
        'judged': judged,
        'cache_hits': cache_hits,
        'skipped_existing': skipped_existing,
        'malformed': malformed,
        'edges_emitted': edges_emitted,
        'total_cost_usd': round(total_cost, 4),
        'cumulative_cost_24h_pre': round(cumulative_24h, 4),
        'prompt_version': PROMPT_VERSION,
        'threshold': THRESHOLD,
        'finished_at': datetime.now(UTC).isoformat(),
    }
    logger.info('summary: %s', json.dumps(summary, ensure_ascii=False))
    return summary


# ─────────────────────────── Module CLI shim ──

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)-7s %(name)s %(message)s',
    )
    print(json.dumps(match_all(dry_run=True, missing_only=True),
                     indent=2, ensure_ascii=False))
