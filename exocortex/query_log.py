# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/query_log.py — F28.1: query telemetry (Phase 1, logging only).
#
# Logs every question asked of the knowledge system to the `query_log` table
# (schema/24_query_log.sql). Phase 1 = telemetry/analytics only — no Question
# entities in the graph (Phase 2), no answer promotion (Phase 3).
#
# Design constraints:
#   - BEST-EFFORT: a logging failure must NEVER break the query path. Every call
#     is wrapped in a broad try/except → warn-and-continue.
#   - MINIMAL: one INSERT per query. No reads. No graph writes.
#   - Embedding is OPTIONAL: callers may pass a pre-computed embedding (the
#     GraphRAG path already has one), otherwise we skip it (don't spend an API
#     call just for telemetry).
#
# See: docs/architecture/knowledge-boundaries-telemetry-provenance.md (Part 2).

from __future__ import annotations

import logging
import os
from typing import Any, Iterable

logger = logging.getLogger(__name__)

# Whether telemetry logging is enabled. Default ON. Set QUERY_LOG_ENABLED=off to
# disable (e.g. in tests or if the table isn't present yet on a given env).
_ENABLED = os.environ.get('QUERY_LOG_ENABLED', 'on').strip().lower() not in (
    'off', '0', 'false', 'no',
)


def _vec_literal(embedding: Iterable[float] | None) -> str | None:
    """pgvector text literal, or None. Mirrors workers/db/pool.py::_adapt_value."""
    if embedding is None:
        return None
    try:
        return '[' + ','.join(repr(float(x)) for x in embedding) + ']'
    except Exception:
        return None


def log_query(
    *,
    question: str,
    source: str,
    tenant_id: str,
    scope: list[str] | None = None,
    retrieved_node_ids: list[str] | None = None,
    retrieval_method: str | None = None,
    latency_ms: int | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    cost_usd: float | None = None,
    question_embedding: Iterable[float] | None = None,
    user_id: str | None = None,
    token_hash: str | None = None,
    conversation_id: str | None = None,
    status: str = 'logged',
) -> str | None:
    """Insert one row into `query_log`. Returns the new row id (str) or None.

    Best-effort: never raises. `source` is the channel/tool that asked
    (`'graph_rag'`, `'claude_desktop_mcp'`, `'graph_rag_api'`, `'graph_rag_cli'`,
    `'mcp_search_thoughts'`, ...). `scope` defaults to ['internal'] (the agency
    scope) when None — matches the schema default.
    """
    if not _ENABLED or not question or not (question := question.strip()):
        return None

    node_ids = [str(n) for n in (retrieved_node_ids or []) if n]
    retrieved_count = len(node_ids)
    emb = _vec_literal(question_embedding)

    sql = (
        "INSERT INTO query_log ("
        "  tenant_id, question, question_embedding, source, user_id, token_hash,"
        "  scope, retrieved_node_ids, retrieved_count, retrieval_method,"
        "  latency_ms, tokens_in, tokens_out, cost_usd, conversation_id, status"
        ") VALUES ("
        "  %s, %s, %s::vector, %s, %s, %s,"
        "  COALESCE(%s, ARRAY['internal']::text[]), %s::uuid[], %s, %s,"
        "  %s, %s, %s, %s, %s, %s"
        ") RETURNING id::text AS id"
    )
    params: tuple[Any, ...] = (
        tenant_id, question, emb, source, user_id, token_hash,
        scope, node_ids, retrieved_count, retrieval_method,
        latency_ms, tokens_in, tokens_out, cost_usd, conversation_id, status,
    )

    try:
        # Import lazily so this module is importable even without DB env.
        from exocortex.db import query_one
        row = query_one(sql, *params)
        return row['id'] if row else None
    except Exception as exc:  # noqa: BLE001 — telemetry must not break callers
        logger.warning('query_log.log_query failed (non-fatal): %r', exc)
        return None
