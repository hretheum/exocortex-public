# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# exocortex/workers/cockpit_ask.py — F31.3.4
# CockpitAskWorker — drains cockpit_actions_pending rows where the operator
# filled the "Ask the brain" property in Notion, runs the question through the
# GraphRAG ask function, and logs the result into query_log
# (source='notion_cockpit_ask').
#
# Guardrails (F31.3.4 G17–G19):
#   - 0 hardcoded secrets (tokens must come from env)
#   - No direct writes to thoughts/sources (Pattern A: only query_log INSERT
#     here; downstream surfaces stay on /capture)
#   - Empty notion_value → no-op (0 query_log rows, status='skipped')
#   - TENANT_ID resolved from env via exocortex.db.get_tenant_id()

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import Any

from exocortex.db import execute, get_tenant_id, query, query_one

log = logging.getLogger(__name__)

_PENDING_SQL = """
    SELECT id, audience_name, page_id, property_name, notion_value
    FROM cockpit_actions_pending
    WHERE status = 'pending'
      AND property_name ILIKE %s
    ORDER BY created_at ASC
"""

_MARK_PROCESSED_SQL = """
    UPDATE cockpit_actions_pending
    SET status = %s, processed_at = now()
    WHERE id = %s
"""

_INSERT_QUERY_LOG_SQL = """
    INSERT INTO query_log
        (tenant_id, source, question, latency_ms, retrieved_count, asked_at)
    VALUES (%s, 'notion_cockpit_ask', %s, %s, %s, now())
    RETURNING id
"""


def _default_ask(question: str) -> dict[str, Any]:
    """Lazy import of graph_rag.ask to keep worker import-light and testable."""
    from exocortex.graph_rag import ask as _ask  # noqa: WPS433 (deliberate lazy import)

    return _ask(question)


class CockpitAskWorker:
    """Drains pending 'Ask the brain' rows and writes results to query_log."""

    PROPERTY_PATTERN = '%Zapytaj mózg%'

    def __init__(self, ask_fn: Callable[[str], Any] | None = None) -> None:
        self._ask_fn = ask_fn or _default_ask

    @staticmethod
    def _is_empty(value: Any) -> bool:
        """None, '', whitespace-only, or empty JSON containers count as empty."""
        if value is None:
            return True
        if isinstance(value, str):
            return value.strip() == ''
        if isinstance(value, (list, dict)):
            return len(value) == 0
        return False

    @staticmethod
    def _extract_question(notion_value: Any) -> str:
        """Notion property payload may already be a string or a JSON blob."""
        if isinstance(notion_value, str):
            return notion_value.strip()
        if isinstance(notion_value, (list, dict)):
            return json.dumps(notion_value, ensure_ascii=False).strip()
        return str(notion_value).strip()

    def _run_ask(self, question: str) -> tuple[int, int]:
        """Run ask_fn, return (latency_ms, retrieved_count)."""
        started = time.monotonic()
        result = self._ask_fn(question)
        latency_ms = int((time.monotonic() - started) * 1000)

        retrieved_count = 0
        if isinstance(result, dict):
            if isinstance(result.get('retrieved_count'), int):
                retrieved_count = result['retrieved_count']
            elif isinstance(result.get('results'), list):
                retrieved_count = len(result['results'])
            elif isinstance(result.get('sources'), list):
                retrieved_count = len(result['sources'])
        return latency_ms, retrieved_count

    def process_pending(self) -> list[dict[str, Any]]:
        """Process all pending 'Ask the brain' rows; return per-row outcomes."""
        tenant_id = get_tenant_id()
        rows = query(_PENDING_SQL, self.PROPERTY_PATTERN) or []
        outcomes: list[dict[str, Any]] = []

        for row in rows:
            row_id = row['id']
            notion_value = row.get('notion_value')

            if self._is_empty(notion_value):
                log.info('cockpit_ask: skipping empty input row id=%s', row_id)
                execute(_MARK_PROCESSED_SQL, 'skipped', row_id)
                outcomes.append({
                    'row_id': row_id,
                    'status': 'skipped',
                    'reason': 'empty_input',
                })
                continue

            question = self._extract_question(notion_value)
            if self._is_empty(question):
                execute(_MARK_PROCESSED_SQL, 'skipped', row_id)
                outcomes.append({
                    'row_id': row_id,
                    'status': 'skipped',
                    'reason': 'empty_input',
                })
                continue

            try:
                latency_ms, retrieved_count = self._run_ask(question)
            except Exception as exc:  # noqa: BLE001 — log and move on
                log.exception('cockpit_ask: ask_fn failed for row id=%s', row_id)
                execute(_MARK_PROCESSED_SQL, 'error', row_id)
                outcomes.append({
                    'row_id': row_id,
                    'status': 'error',
                    'reason': str(exc),
                })
                continue

            log_row = query_one(
                _INSERT_QUERY_LOG_SQL,
                tenant_id, question, latency_ms, retrieved_count,
            )
            query_log_id = log_row['id'] if log_row else None
            execute(_MARK_PROCESSED_SQL, 'answered', row_id)
            outcomes.append({
                'row_id': row_id,
                'status': 'ok',
                'query_log_id': query_log_id,
                'latency_ms': latency_ms,
                'retrieved_count': retrieved_count,
            })

        return outcomes
