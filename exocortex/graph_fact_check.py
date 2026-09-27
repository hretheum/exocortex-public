# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# exocortex/graph_fact_check.py — F31.4.2: verify claims against the graph.
#
# Pipeline:
#   1. LLM extracts atomic factual claims from input text (Qwen via llm_router).
#   2. Per claim: pgvector cosine top-K candidates from `thoughts`.
#   3. AGE Cypher pulls `supports` / `contradicts` / `decided_in` edges incident
#      to the candidate set.
#   4. Verdict per claim:
#        contradicts  → any contradicts edge among candidates,
#        supported    → ≥2 supports/decided_in edges among candidates,
#        no_evidence  → otherwise.

from __future__ import annotations

import logging
import os
import re
from typing import Any

from exocortex.db import get_embedding, query
from exocortex.graph_rag import vector_search
from exocortex.settings import get_tenant_id

logger = logging.getLogger(__name__)

AGE_GRAPH = os.environ.get('PG_AGE_GRAPH', 'second_brain')
VECTOR_TOP_K = 10
MAX_CLAIMS = 10
SUPPORT_EDGE_TYPES = ('supports', 'decided_in')
CONTRADICT_EDGE_TYPE = 'contradicts'
_SUPPORT_THRESHOLD = 2

_UUID_RE = re.compile(
    r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
)


_CLAIM_EXTRACTION_SCHEMA = {
    'name': 'extract_claims',
    'description': 'Extract atomic, verifiable factual claims from text.',
    'input_schema': {
        'type': 'object',
        'properties': {
            'claims': {
                'type': 'array',
                'items': {'type': 'string'},
                'description': (
                    f'Up to {MAX_CLAIMS} atomic factual claims. Empty list if '
                    'the text contains no verifiable claims (opinions, questions, '
                    'small talk).'
                ),
            },
        },
        'required': ['claims'],
    },
}


_CLAIM_SYSTEM_PROMPT = (
    "Jesteś analitykiem faktograficznym. Z otrzymanego tekstu wyodrębnij "
    "atomowe, weryfikowalne stwierdzenia (claims). Każde stwierdzenie ma być "
    "samodzielnym zdaniem opisującym pojedynczy fakt — bez opinii, pytań, "
    "życzeń, hipotez. Maksymalnie 10 stwierdzeń. Jeśli tekst nie zawiera "
    "weryfikowalnych faktów, zwróć pustą listę."
)


def _extract_claims(text: str) -> list[str]:
    """Stage 1 — LLM-driven atomic claim extraction.

    Returns up to ``MAX_CLAIMS`` claims; empty list on parse failure or when
    the text contains no verifiable factual content.
    """
    text = (text or '').strip()
    if not text:
        return []
    from exocortex import llm_routing
    llm_routing.initialize()
    from llm_router import call_tool as _router_call_tool

    try:
        tool_input, _usage = _router_call_tool(
            use_case='second_brain.F31_4_2_fact_check_extract',
            system=_CLAIM_SYSTEM_PROMPT,
            user=text,
            schema=_CLAIM_EXTRACTION_SCHEMA,
            max_tokens=1024,
            cache_system=True,
        )
    except Exception as exc:
        logger.warning('graph_fact_check: claim extraction failed: %r', exc)
        return []

    if not isinstance(tool_input, dict):
        return []
    claims = tool_input.get('claims')
    if not isinstance(claims, list):
        return []
    out: list[str] = []
    for c in claims:
        if isinstance(c, str):
            s = c.strip()
            if s:
                out.append(s)
        if len(out) >= MAX_CLAIMS:
            break
    return out


def _vector_candidates(tenant_id: str, claim: str) -> list[dict]:
    """Stage 2 — pgvector top-K candidates for a single claim.

    Delegates to graph_rag.vector_search, which since the thought_chunks
    migration also covers vault_note documents (whose embeddings live on
    thought_chunks, not thoughts.embedding directly) — otherwise fact-
    checking would silently stop finding evidence in vault_note content.
    """
    embedding = get_embedding(claim)
    if embedding is None:
        return []
    return vector_search(tenant_id, embedding, VECTOR_TOP_K)


def _parse_agtype_id(payload: Any) -> str | None:
    if not payload:
        return None
    m = _UUID_RE.search(str(payload))
    return m.group(0) if m else None


def _graph_edges_for_candidates(candidate_ids: list[str]) -> list[dict]:
    """Stage 3 — AGE traversal for support/contradict edges.

    Returns rows: {src_id, dst_id, edge_type}. Uses the relational `edges`
    table (authoritative, dual-written with AGE) for a single tenant-scoped
    query rather than per-seed Cypher calls.
    """
    if not candidate_ids:
        return []
    safe_ids = [c for c in candidate_ids if _UUID_RE.fullmatch(c)]
    if not safe_ids:
        return []
    tenant_id = get_tenant_id()
    edge_types = list(SUPPORT_EDGE_TYPES) + [CONTRADICT_EDGE_TYPE]
    sql = (
        "SELECT src_id::text AS src_id, dst_id::text AS dst_id, type AS edge_type "
        "FROM edges "
        "WHERE tenant_id = %s "
        "  AND type = ANY(%s) "
        "  AND (src_id::text = ANY(%s) OR dst_id::text = ANY(%s))"
    )
    try:
        return query(sql, tenant_id, edge_types, safe_ids, safe_ids)
    except Exception as exc:
        logger.warning('graph_fact_check: edge lookup failed: %r', exc)
        return []


def _title_for(meta: dict | None, thought_id: str) -> str:
    if not isinstance(meta, dict):
        return thought_id[:8]
    title = meta.get('title') or meta.get('slug') or meta.get('source_file')
    if title:
        return str(title).rsplit('/', 1)[-1].rsplit('.', 1)[0]
    return thought_id[:8]


def _verdict_for_claim(claim: str, candidates: list[dict]) -> dict:
    """Stage 4 — derive verdict + evidence + sources for a single claim."""
    candidate_ids = [c['id'] for c in candidates]
    cand_by_id = {c['id']: c for c in candidates}
    cand_id_set = set(candidate_ids)

    edges = _graph_edges_for_candidates(candidate_ids)

    contradicting: list[dict] = []
    supporting: list[dict] = []
    for e in edges:
        if e['src_id'] not in cand_id_set and e['dst_id'] not in cand_id_set:
            continue
        if e['edge_type'] == CONTRADICT_EDGE_TYPE:
            contradicting.append(e)
        elif e['edge_type'] in SUPPORT_EDGE_TYPES:
            supporting.append(e)

    def _source_for(thought_id: str) -> dict | None:
        cand = cand_by_id.get(thought_id)
        if cand is None:
            return None
        return {
            'thought_id': thought_id,
            'title': _title_for(cand.get('metadata'), thought_id),
        }

    if contradicting:
        first = contradicting[0]
        src = _source_for(first['src_id']) or _source_for(first['dst_id'])
        return {
            'claim': claim,
            'verdict': 'contradicts',
            'evidence_edges': contradicting[:5],
            'sources': [s for s in [src] if s],
        }

    if len(supporting) >= _SUPPORT_THRESHOLD:
        seen: set[str] = set()
        sources: list[dict] = []
        for e in supporting:
            for tid in (e['src_id'], e['dst_id']):
                if tid in cand_id_set and tid not in seen:
                    s = _source_for(tid)
                    if s:
                        sources.append(s)
                        seen.add(tid)
        return {
            'claim': claim,
            'verdict': 'supported',
            'evidence_edges': supporting[:5],
            'sources': sources[:5],
        }

    return {
        'claim': claim,
        'verdict': 'no_evidence',
        'evidence_edges': [],
        'sources': [],
    }


def graph_fact_check(text: str) -> list[dict]:
    """Extract claims from text and verify each against the knowledge graph.

    Returns list of: {"claim": str, "verdict": "supported"|"contradicts"|"no_evidence",
                      "evidence_edges": list[dict], "sources": list[{"thought_id": str, "title": str}]}
    """
    claims = _extract_claims(text)
    if not claims:
        return []
    tenant_id = get_tenant_id()
    results: list[dict] = []
    for claim in claims:
        candidates = _vector_candidates(tenant_id, claim)
        results.append(_verdict_for_claim(claim, candidates))
    return results


# Performance / cost expectation (informational, not hard SLO):
#   - 5 claims × (1 LLM extract + 5 embeddings + 5 SQL hops) ≈ 2-4 s end-to-end,
#     ~$0.001-0.003 with Qwen on DeepInfra.

__all__ = ['graph_fact_check']
