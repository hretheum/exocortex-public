# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/graph_rag.py — F5.1: GraphRAG orchestrator.
#
# Hybrid retrieval pipeline for natural-language queries over the Second Brain:
#   1. embed question (text-embedding-3-small, 1536d) — same model as ingest.
#   2. vector search top-K thoughts via pgvector cosine.
#   3. graph expand each top-K via AGE Cypher (typed reasoning edges, 1-2 hops).
#   4. RRF fusion: rank_vector + rank_graph_centrality, k=60.
#   5. LLM synthesis: claude-haiku-4-5 with cacheable system prompt + cited sources.
#
# Returns Answer(response, sources, cost_usd, latency_ms). Cache layer is in-memory
# dict keyed by SHA256(question + sorted source_ids); hits are zero-cost replays.
#
# F4 lessons applied:
#   1. system prompt cache_control=ephemeral — F4.2 pattern, ~5min TTL.
#   2. defensive normalizer at LLM-output boundary (sources cited as wikilinks).
#   3. graceful fallback when AGE returns 0 neighbors (vector-only synthesis).

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from exocortex._bootstrap import bootstrap
from exocortex.db import get_embedding, get_tenant_id, query
from exocortex.settings import get_settings

bootstrap()

logger = logging.getLogger(__name__)

# Env-driven as in db/embeddings.py: the question MUST be embedded with the same
# model as ingest, otherwise the vectors do not live in one space.
EMBEDDING_MODEL = os.environ.get('EXOCORTEX_EMBEDDING_MODEL', 'text-embedding-3-small')
TENANT_ID = get_tenant_id()
AGE_GRAPH = os.environ.get('PG_AGE_GRAPH') or get_settings().age_graph

# Edge types relevant for question-answering. Excludes structural-only edges
# (session_contains, revisits) that don't carry semantic context for QA.
GRAPH_EDGES = (
    'attended_meeting', 'classified_as_client', 'classified_as_project',
    'decided_in', 'addresses_problem', 'mentions_person',
    'supports', 'contradicts', 'supersedes', 'derived_from',
    'broader_than', 'narrower_than', 'related_to',
)

# RRF constant; 60 is the canonical value from Cormack/Clarke/Buettcher 2009.
RRF_K = 60

# ── F27.5: provenance-aware ranking ──────────────────────────────
# Multiplicative weight applied to the RRF score so that, all else equal, a
# human-authored doc outranks an unvalidated AI-authored doc. Relevance still
# dominates (a much higher vector rank beats the weight) — provenance only
# tips ties / near-ties. Untagged content is treated as `human` (charitable
# default per docs/architecture/knowledge-boundaries-telemetry-provenance.md).
PROVENANCE_WEIGHT = {
    'human': 1.00,
    'ai_assisted': 1.00,            # human-authored, AI helped → human reviewed
    'ai_extracted': 0.92,           # extracted from a human source, may have errors
    'ai_authored_validated': 0.96,  # AI wrote, human validated
    'ai_authored': 0.70,            # AI wrote, NOT validated → deprioritize
    'ai_answer': 0.65,              # promoted Q&A answer (Phase 3) — lowest until validated
}
_DEFAULT_PROVENANCE_WEIGHT = 1.00


def _meta_get(metadata: dict | None, key: str):
    """Look up `key` on a thought's metadata, transparently falling back to a
    nested `metadata.frontmatter.<key>` (some ingest paths stash the raw parsed
    frontmatter under `frontmatter`)."""
    if not isinstance(metadata, dict):
        return None
    if metadata.get(key) not in (None, ''):
        return metadata.get(key)
    fm = metadata.get('frontmatter')
    if isinstance(fm, dict) and fm.get(key) not in (None, ''):
        return fm.get(key)
    return None


def provenance_of(metadata: dict | None) -> str:
    """Normalized provenance label for a thought's metadata.

    Reads `metadata.provenance` (set by the F27.1 source parser / Claude's
    write-time convention; also checks a nested `metadata.frontmatter.provenance`)
    and folds in `provenance_metadata.human_validated` so `ai_authored` +
    validated maps to the `ai_authored_validated` tier. Missing / unknown →
    'human' (charitable default per the provenance design doc).
    """
    prov = _meta_get(metadata, 'provenance')
    prov = str(prov or '').strip().lower()
    if not prov:
        return 'human'
    if prov == 'ai_authored':
        pm = _meta_get(metadata, 'provenance_metadata') or {}
        if isinstance(pm, dict) and (pm.get('human_validated') is True
                                     or str(pm.get('human_validated')).strip().lower() == 'true'):
            return 'ai_authored_validated'
    return prov


def provenance_weight(metadata: dict | None) -> float:
    return PROVENANCE_WEIGHT.get(provenance_of(metadata), _DEFAULT_PROVENANCE_WEIGHT)

# UUID v4 canonical form. Cypher returns vertex props as JSON strings;
# we extract id with this regex when parsing agtype payloads.
_UUID_RE = re.compile(
    r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
)


# ─────────────────────────────────────────────── Result dataclass ──

@dataclass
class Source:
    thought_id: str
    title: str
    body_excerpt: str
    score: float
    rank_vector: int | None = None
    rank_graph: int | None = None
    edge_path: list[str] = field(default_factory=list)  # human-readable neighbor types
    provenance: str = 'human'  # F27.5: human | ai_assisted | ai_extracted | ai_authored[_validated] | ai_answer


@dataclass
class Answer:
    question: str
    response: str
    sources: list[Source]
    cost_usd: float
    latency_ms: int
    usage: dict[str, Any] = field(default_factory=dict)
    cache_hit: bool = False
    # set when the engine could not answer (e.g. embedding failed); `response`
    # then carries a human-readable placeholder, not an answer
    error: str | None = None
    # id of the query_log row written for this call (None when logging is off or failed)
    query_log_id: str | None = None


# ─────────────────────────────────────────────────────── Cache ──

_query_cache: dict[str, Answer] = {}


def _cache_key(question: str, source_ids: list[str]) -> str:
    payload = question.strip().lower() + '|' + '|'.join(sorted(source_ids))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]


def cache_clear() -> None:
    _query_cache.clear()


# ─────────────────────────────────────────── Vector retrieval ──

def vector_search(tenant_id: str, embedding: list[float],
                  top_k: int = 10) -> list[dict]:
    """Top-K thoughts by cosine similarity. Returns rows with
    id/body/metadata/thought_type/sim.

    Since the thought_chunks migration (schema/36_thought_chunks.sql),
    a thought's semantic content lives in one of two places: directly on
    thoughts.embedding (backlog_item, recipe, work_meeting_note — thought
    already equals document, one embedding is enough) or in thought_chunks
    (vault_note — a document's fragments each have their own embedding;
    thoughts.embedding is NULL for these). This searches both and returns
    the PARENT thought either way, deduplicated — a document matched by
    several chunks appears once, with its best-scoring chunk's similarity.

    A plain top-K per source before combining is still correct: the true
    global top-K result must be in the top-K of whichever single source it
    came from, so taking top_k from each source and re-ranking the union
    can't miss anything the naive single-table version could have found.
    """
    sql = (
        "WITH direct AS ("
        "  SELECT id AS thought_id, 1 - (embedding <=> %s::vector) AS sim"
        "  FROM thoughts"
        "  WHERE tenant_id = %s AND embedding IS NOT NULL"
        "  ORDER BY embedding <=> %s::vector LIMIT %s"
        "), via_chunks AS ("
        "  SELECT tc.thought_id AS thought_id, "
        "         1 - (tc.embedding <=> %s::vector) AS sim"
        "  FROM thought_chunks tc"
        "  JOIN thoughts t ON t.id = tc.thought_id"
        "  WHERE t.tenant_id = %s AND tc.embedding IS NOT NULL"
        "  ORDER BY tc.embedding <=> %s::vector LIMIT %s"
        "), combined AS ("
        "  SELECT thought_id, MAX(sim) AS sim FROM ("
        "    SELECT * FROM direct UNION ALL SELECT * FROM via_chunks"
        "  ) u GROUP BY thought_id"
        ")"
        "SELECT t.id::text AS id, t.body, t.metadata, t.thought_type, c.sim "
        "FROM combined c JOIN thoughts t ON t.id = c.thought_id "
        "ORDER BY c.sim DESC LIMIT %s"
    )
    return query(
        sql,
        embedding, tenant_id, embedding, top_k,   # direct CTE
        embedding, tenant_id, embedding, top_k,   # via_chunks CTE
        top_k,                                    # final LIMIT
    )


# ──────────────────────────────────────────── Graph expansion ──

def _parse_agtype_id(payload: str) -> str | None:
    """Extract a UUID from an agtype vertex/edge JSON string."""
    if not payload:
        return None
    m = _UUID_RE.search(payload)
    return m.group(0) if m else None


def graph_expand(seed_thought_ids: list[str], max_hops: int = 2,
                 limit_per_seed: int = 8) -> dict[str, list[dict]]:
    """For each seed thought, traverse 1-2 hops over reasoning edges.

    Returns: {seed_thought_id: [{neighbor_id, neighbor_label, edge_type, hops}, ...]}.

    AGE 1.6.0 Cypher idiosyncrasies:
      - parameters via $$ ... $$ literal (no SQL bind), so we string-interpolate
        the seed UUID; safe because we filter to UUID-only via _UUID_RE.
      - return type tuple `(neighbor agtype, et agtype)` must match RETURN order.
      - 2-hop pattern uses variable-length edges: `-[*1..2]-`.
    """
    out: dict[str, list[dict]] = defaultdict(list)
    if not seed_thought_ids:
        return out

    # AGE 1.6.0 doesn't accept `:type1|type2` syntax inside variable-length
    # patterns `[*1..N]`. Workaround: traverse untyped `[*1..N]` then post-filter
    # edge labels in Python against GRAPH_EDGES allow-list.
    allowed_edges = set(GRAPH_EDGES)
    hop_range = f'1..{max_hops}'

    for sid in seed_thought_ids:
        # Defensive: only forward UUIDs into Cypher.
        if not _UUID_RE.fullmatch(sid):
            continue
        cypher = (
            f"MATCH (t:Thought {{id: '{sid}'}})-[r*{hop_range}]-(neighbor) "
            f"RETURN neighbor, r LIMIT {limit_per_seed * 2}"
        )
        try:
            rows = query(
                f"SELECT * FROM cypher('{AGE_GRAPH}', $$ {cypher} $$) "
                f"AS (neighbor agtype, r agtype)"
            )
        except Exception as exc:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
            # AGE failure is non-fatal; vector-only retrieval still works.
            logger.warning('graph_expand: cypher failed for seed %s: %r', sid, exc)
            continue

        kept = 0
        for row in rows:
            if kept >= limit_per_seed:
                break
            nbr = row.get('neighbor') or ''
            edge_payload = row.get('r') or ''
            nbr_id = _parse_agtype_id(nbr)
            if not nbr_id:
                continue
            # Vertex label.
            label_m = re.search(r'"label":\s*"([^"]+)"', nbr)
            label = label_m.group(1) if label_m else 'Unknown'
            # Variable-length path returns r as a JSON array of edges.
            # Extract all edge labels along the path.
            edge_labels = re.findall(r'"label":\s*"([^"]+)"', edge_payload)
            if not edge_labels:
                continue
            # Filter: at least one edge in the path must be in our allow-list.
            kept_edges = [el for el in edge_labels if el in allowed_edges]
            if not kept_edges:
                continue
            hops = edge_payload.count('::edge') or 1
            edge_type = kept_edges[-1]  # closest edge to neighbor
            out[sid].append({
                'neighbor_id': nbr_id,
                'neighbor_label': label,
                'edge_type': edge_type,
                'hops': hops,
            })
            kept += 1
    return out


# ──────────────────────────────────────────────── RRF fusion ──

def rrf_fuse(vector_hits: list[dict],
             graph_neighbors: dict[str, list[dict]],
             k: int = RRF_K) -> list[dict]:
    """Reciprocal Rank Fusion: combine vector ranks with graph centrality ranks.

    score(thought) = sum_method 1/(k + rank_method(thought))

    - Method 1 (vector): rank from `vector_hits` order (1-indexed).
    - Method 2 (graph): rank from graph centrality, where centrality(thought) =
      number of seeds it appears as a neighbor of (across all seeds). Higher
      centrality → better rank.

    Returns: vector_hits enriched with `rrf_score`, `rank_vector`, `rank_graph`,
    `edge_path`, sorted by rrf_score desc. Vector-only thoughts retain
    rank_graph=None.

    Note: graph_neighbors are *neighbors* of seeds, not seeds themselves. We
    boost a seed's score when ITS neighbors are dense, AND we surface frequently-
    co-occurring neighbors as additional candidates (added with body=None until
    resolved by caller).
    """
    # Compute graph centrality per thought_id seen as neighbor.
    centrality: dict[str, int] = defaultdict(int)
    edge_paths: dict[str, list[str]] = defaultdict(list)
    for seed_id, neighbors in graph_neighbors.items():
        for n in neighbors:
            nbr_id = n['neighbor_id']
            centrality[nbr_id] += 1
            tag = f"{n['edge_type']}@{n['hops']}h via {seed_id[:8]}"
            edge_paths[nbr_id].append(tag)
        # The seed itself gets centrality bonus per # outbound neighbors found.
        centrality[seed_id] = max(centrality[seed_id], len(neighbors))

    # Rank by graph centrality (descending; ties → identical rank).
    graph_ranked = sorted(centrality.items(), key=lambda kv: (-kv[1], kv[0]))
    graph_rank_of: dict[str, int] = {tid: i + 1 for i, (tid, _c) in enumerate(graph_ranked)}

    # Build fused score per thought.
    scored: dict[str, dict[str, Any]] = {}
    for i, hit in enumerate(vector_hits):
        tid = hit['id']
        v_rank = i + 1
        g_rank = graph_rank_of.get(tid)
        base = 1.0 / (k + v_rank)
        if g_rank is not None:
            base += 1.0 / (k + g_rank)
        # F27.5: scale by provenance tier (human ≥ validated AI > unvalidated AI).
        prov = provenance_of(hit.get('metadata'))
        weight = PROVENANCE_WEIGHT.get(prov, _DEFAULT_PROVENANCE_WEIGHT)
        scored[tid] = {
            **hit,
            'rrf_score': base * weight,
            'rrf_score_raw': base,
            'rank_vector': v_rank,
            'rank_graph': g_rank,
            'provenance': prov,
            'provenance_weight': weight,
            'edge_path': edge_paths.get(tid, []),
        }

    # Sort by weighted score; tie-break on raw score then provenance weight then id
    # for deterministic ordering.
    return sorted(
        scored.values(),
        key=lambda r: (-r['rrf_score'], -r['rrf_score_raw'], -r['provenance_weight'], r['id']),
    )


# ─────────────────────────────────────────────── LLM synthesis ──
#
# F31.8.2: the system prompt now lives in a Jinja2 template at
# ``exocortex/prompts/graph_rag/system_prompt.md.j2`` rendered with values
# from ``config/graph_rag.yaml`` (fallback: ``graph_rag.example.yaml``).
# The rendering helpers live in :mod:`exocortex.graph_rag_prompt`.

# Schema for llm_router.call_tool — GraphRAG returns a single prose response.
GRAPHRAG_SCHEMA = {
    'name': 'graphrag_answer',
    'description': 'Answer a question based on retrieved sources from the Second Brain knowledge base',
    'input_schema': {
        'type': 'object',
        'properties': {
            'response': {
                'type': 'string',
                'description': 'Answer in Polish, citing sources as [[slug]] wikilinks. Be concise (1-3 paragraphs or bullet list). If sources are insufficient, say so explicitly.',
            },
        },
        'required': ['response'],
    },
}


def build_system_prompt() -> str:
    """Return system prompt as plain string.

    Delegates to :func:`exocortex.graph_rag_prompt.build_system_prompt`, which
    renders the bundled Jinja2 template with the user's ``config/graph_rag.yaml``.
    llm_router applies cache_control automatically when cache_system=True.
    """
    from exocortex.graph_rag_prompt import build_system_prompt as _build
    return _build()


def _slug_from_metadata(metadata: dict | None) -> str:
    """Extract Obsidian-readable slug from thought metadata."""
    from exocortex.llm_utils import slug_from_metadata as _fn
    return _fn(metadata)


def _build_user_prompt(question: str, fused_hits: list[dict],
                       max_chars_per_source: int = 1500) -> str:
    parts = [f"Question: {question}", "", "Sources (top-K po RRF fusion):", ""]
    for i, hit in enumerate(fused_hits, 1):
        meta = hit.get('metadata') or {}
        slug = _slug_from_metadata(meta) or f"thought-{hit['id'][:8]}"
        title = (meta.get('title') or 'untitled').strip()
        body = (hit.get('body') or '').strip()
        if len(body) > max_chars_per_source:
            body = body[:max_chars_per_source] + '... [truncated]'
        edge_summary = ''
        if hit.get('edge_path'):
            edge_summary = ' | edges: ' + ', '.join(hit['edge_path'][:3])
        parts.append(
            f"--- Source {i} (rrf={hit['rrf_score']:.4f}, "
            f"v_rank={hit.get('rank_vector')}, g_rank={hit.get('rank_graph')}"
            f"{edge_summary}) ---"
        )
        parts.append(f"id: {hit['id']}")
        parts.append(f"slug: {slug}")
        parts.append(f"title: {title}")
        parts.append(f"body: {body}")
        parts.append("")
    return '\n'.join(parts)


def call_llm(question: str, fused_hits: list[dict]) -> tuple[str, dict]:
    """Call LLM via llm_router with routing, fallback, cost stop, and telemetry."""
    from exocortex import llm_routing
    llm_routing.initialize()
    from llm_router import call_tool as _router_call_tool

    user_text = _build_user_prompt(question, fused_hits)
    tool_input, usage = _router_call_tool(
        use_case='second_brain.F5_graphrag_query',
        system=build_system_prompt(),
        user=user_text,
        schema=GRAPHRAG_SCHEMA,
        max_tokens=2048,
        cache_system=True,
    )
    text = tool_input.get('response', '') if isinstance(tool_input, dict) else str(tool_input)
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
    return text, legacy_usage


def estimate_cost_usd(usage: dict) -> float:
    """Router-aware cost — re-exported from llm_utils (F31-CLN-01)."""
    from exocortex.llm_utils import estimate_cost_usd as _fn
    return _fn(usage)


# ─────────────────────────────────────────────── Orchestrator ──

@dataclass
class GraphRAGOrchestrator:
    tenant_id: str
    embedding_model: str = EMBEDDING_MODEL

    def _log_telemetry(self, ans: Answer, *, source: str, method: str,
                       embedding: list[float] | None,
                       conversation_id: str | None = None) -> str | None:
        """Best-effort write to query_log (F28.1). Never raises; returns the row id."""
        try:
            from exocortex.query_log import log_query
            usage = ans.usage or {}
            return log_query(
                question=ans.question,
                source=source,
                tenant_id=self.tenant_id,
                retrieved_node_ids=[s.thought_id for s in ans.sources],
                retrieval_method=method,
                latency_ms=ans.latency_ms,
                tokens_in=usage.get('input_tokens'),
                tokens_out=usage.get('output_tokens'),
                cost_usd=ans.cost_usd,
                question_embedding=embedding,
                conversation_id=conversation_id,
            )
        except Exception:  # telemetry is non-fatal
            logger.warning('graph_rag telemetry log failed (non-fatal)', exc_info=True)
            return None

    def answer(self, question: str, max_hops: int = 2, top_k_vector: int = 10,
               top_k_final: int = 8, use_cache: bool = True,
               query_source: str = 'graph_rag',
               conversation_id: str | None = None) -> Answer:
        """End-to-end query: embed → vector → graph → RRF → LLM.

        `query_source` labels the channel/tool for telemetry (`query_log.source`):
        e.g. 'claude_desktop_mcp' from the MCP `ask` tool, 'graph_rag_cli' from
        the CLI, 'graph_rag_api' from the HTTP endpoint. Defaults to 'graph_rag'.

        This is the only place a GraphRAG question is written to `query_log`:
        exactly one row per non-empty question, including when a pipeline step
        raises (the row then has retrieval_method='error' and the exception
        propagates to the caller). Logging is best-effort, failures are swallowed.
        """
        t0 = time.time()
        question = question.strip()
        if not question:
            return Answer(question=question, response='', sources=[],
                          cost_usd=0.0, latency_ms=0)

        embedding: list[float] | None = None
        try:
            embedding = get_embedding(question)
            ans, method = self._run_pipeline(
                question, embedding, t0, max_hops=max_hops,
                top_k_vector=top_k_vector, top_k_final=top_k_final,
                use_cache=use_cache,
            )
        except Exception as exc:
            failed = Answer(question=question, response='', sources=[],
                            cost_usd=0.0, latency_ms=int((time.time() - t0) * 1000),
                            error=f'{type(exc).__name__}: {exc}')
            self._log_telemetry(failed, source=query_source, method='error',
                                embedding=embedding, conversation_id=conversation_id)
            raise
        ans.query_log_id = self._log_telemetry(
            ans, source=query_source, method=method,
            embedding=embedding, conversation_id=conversation_id)
        return ans

    def _run_pipeline(self, question: str, embedding: list[float] | None,
                      t0: float, *, max_hops: int, top_k_vector: int,
                      top_k_final: int, use_cache: bool) -> tuple[Answer, str]:
        """Steps 2-5 of `answer`; returns (answer, retrieval_method for query_log)."""
        if embedding is None:
            return Answer(question=question, response='[error: embedding failed]',
                          sources=[], cost_usd=0.0,
                          latency_ms=int((time.time() - t0) * 1000),
                          error='embedding failed'), 'none'

        # Step 2: vector search
        vector_hits = vector_search(self.tenant_id, embedding, top_k=top_k_vector)

        # Cache lookup uses sorted vector hit ids — same retrieval set means
        # same answer (assuming taxonomy hasn't shifted between calls).
        seed_ids = [h['id'] for h in vector_hits]
        ckey = _cache_key(question, seed_ids)
        if use_cache and ckey in _query_cache:
            cached = _query_cache[ckey]
            return Answer(
                question=cached.question, response=cached.response,
                sources=cached.sources, cost_usd=0.0,
                latency_ms=int((time.time() - t0) * 1000),
                usage=cached.usage, cache_hit=True,
            ), 'cache'

        # Step 3: graph expand
        graph_neighbors = graph_expand(seed_ids, max_hops=max_hops)

        # Step 4: RRF fusion
        fused = rrf_fuse(vector_hits, graph_neighbors)[:top_k_final]

        # Step 5: LLM synthesis
        if not fused:
            return Answer(question=question,
                          response='Brak źródeł w bazie pasujących do pytania.',
                          sources=[], cost_usd=0.0,
                          latency_ms=int((time.time() - t0) * 1000)), 'hybrid'

        response_text, usage = call_llm(question, fused)
        cost = estimate_cost_usd(usage)

        sources = [
            Source(
                thought_id=h['id'],
                title=(h.get('metadata') or {}).get('title') or '',
                body_excerpt=(h.get('body') or '')[:200],
                score=h['rrf_score'],
                rank_vector=h.get('rank_vector'),
                rank_graph=h.get('rank_graph'),
                edge_path=h.get('edge_path', []),
                provenance=h.get('provenance') or provenance_of(h.get('metadata')),
            )
            for h in fused
        ]

        ans = Answer(
            question=question, response=response_text, sources=sources,
            cost_usd=cost, latency_ms=int((time.time() - t0) * 1000),
            usage=usage, cache_hit=False,
        )
        if use_cache:
            _query_cache[ckey] = ans
        return ans, 'hybrid'


# ──────────────────────────────── F27.5/F28.3: scope-aware search ──

def _client_scope_of(metadata: dict | None) -> list[str]:
    """Normalized `client_scope` list for a thought. Missing → ['internal']
    (agency scope) per docs/architecture/knowledge-boundaries-telemetry-provenance.md."""
    cs = _meta_get(metadata, 'client_scope')
    if isinstance(cs, str):
        cs = [cs]
    if isinstance(cs, (list, tuple)) and cs:
        norm = [str(x).strip().lower() for x in cs if str(x).strip()]
        return norm or ['internal']
    return ['internal']


def search_with_scope(question: str, scope: list[str] | None = None,
                      top_k_vector: int = 20, top_k_final: int = 10,
                      max_hops: int = 2, tenant_id: str | None = None) -> list[dict]:
    """Retrieval-only search with provenance-aware ranking + optional scope filter.

    Returns a ranked list of dicts:
      {thought_id, path, title, slug, provenance, provenance_weight, score,
       rank_vector, rank_graph, client_scope, body_excerpt}

    `scope`: if given, only return thoughts whose `client_scope` intersects it
    (out-of-scope nodes are dropped at the retrieval layer — they cannot leak
    even if the question would otherwise surface them). `None` = no filter
    (personal/agency full view). This is the building block F28.3 will wrap with
    a token check; standalone it powers smoke tests + ad-hoc ranked lookup.
    """
    tid = tenant_id or TENANT_ID
    q = (question or '').strip()
    if not q:
        return []
    embedding = get_embedding(q)
    if embedding is None:
        return []
    vector_hits = vector_search(tid, embedding, top_k=top_k_vector)
    if scope is not None:
        scope_set = {str(s).strip().lower() for s in scope}
        vector_hits = [
            h for h in vector_hits
            if scope_set & set(_client_scope_of(h.get('metadata')))
        ]
    if not vector_hits:
        return []
    seed_ids = [h['id'] for h in vector_hits]
    graph_neighbors = graph_expand(seed_ids, max_hops=max_hops)
    fused = rrf_fuse(vector_hits, graph_neighbors)[:top_k_final]
    out = []
    for h in fused:
        meta = h.get('metadata') or {}
        slug = _slug_from_metadata(meta)
        path = meta.get('source_file') or meta.get('path') or (f"{slug}.md" if slug else '')
        out.append({
            'thought_id': h['id'],
            'path': path,
            'title': (meta.get('title') or '').strip(),
            'slug': slug,
            'provenance': h.get('provenance') or provenance_of(meta),
            'provenance_weight': h.get('provenance_weight', provenance_weight(meta)),
            'score': h['rrf_score'],
            'rank_vector': h.get('rank_vector'),
            'rank_graph': h.get('rank_graph'),
            'client_scope': _client_scope_of(meta),
            'body_excerpt': (h.get('body') or '')[:200],
        })
    return out


# ────────────────────────────────────────────────────────── CLI ──

def _cli() -> None:
    import argparse
    parser = argparse.ArgumentParser(description='GraphRAG query CLI')
    parser.add_argument('question', help='Natural language query')
    parser.add_argument('--top-k', type=int, default=10, help='Vector search top-K (default: 10)')
    parser.add_argument('--hops', type=int, default=2, help='Max graph hops (default: 2)')
    parser.add_argument('--no-cache', action='store_true', help='Bypass in-memory cache')
    parser.add_argument('--json', action='store_true', help='Emit JSON instead of human format')
    args = parser.parse_args()

    orch = GraphRAGOrchestrator(tenant_id=TENANT_ID)
    ans = orch.answer(args.question, max_hops=args.hops, top_k_vector=args.top_k,
                      use_cache=not args.no_cache, query_source='graph_rag_cli')

    if args.json:
        print(json.dumps({
            'question': ans.question,
            'response': ans.response,
            'sources': [
                {'thought_id': s.thought_id, 'title': s.title, 'score': s.score,
                 'rank_vector': s.rank_vector, 'rank_graph': s.rank_graph,
                 'edge_path': s.edge_path[:3], 'provenance': s.provenance}
                for s in ans.sources
            ],
            'cost_usd': ans.cost_usd, 'latency_ms': ans.latency_ms,
            'cache_hit': ans.cache_hit, 'usage': ans.usage,
        }, indent=2, ensure_ascii=False))
        return

    print(f'\n=== Answer ===\n{ans.response}\n')
    print(f'=== Sources (top {len(ans.sources)}) ===')
    for s in ans.sources:
        print(f'  [{s.score:.4f}] v={s.rank_vector} g={s.rank_graph} '
              f'{s.title or s.thought_id[:8]}')
        if s.edge_path:
            print(f'      edges: {", ".join(s.edge_path[:3])}')
    print(f'\nlatency_ms={ans.latency_ms}  cost_usd=${ans.cost_usd:.4f}  '
          f'cache_hit={ans.cache_hit}  usage={ans.usage}')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    _cli()
