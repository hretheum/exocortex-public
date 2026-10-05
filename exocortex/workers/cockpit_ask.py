# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# exocortex/workers/cockpit_ask.py — F31.3.4
# CockpitAskWorker — drains cockpit_actions_pending rows where the operator
# filled the "Ask the brain" property in Notion and answers each question with
# GraphRAGOrchestrator.answer (query_source='notion_cockpit_ask').
#
# query_log: the worker does NOT write it. The orchestrator writes exactly one
# row per question (latency, tokens, cost included), also when the engine
# fails; the worker only reads query_log to enforce the daily budget.
#
# The answer (or the readable error) goes to cockpit_actions_pending.resolved_value
# and the row's status becomes 'answered', 'error' or 'skipped'. Engine
# failures, timeouts and an exhausted daily budget never raise out of the worker.
#
# Guardrails (F31.3.4 G17–G19):
#   - 0 hardcoded secrets (tokens must come from env)
#   - No direct writes to thoughts/sources (Pattern A); no query_log INSERT here
#   - Empty notion_value → no-op (0 query_log rows, status='skipped')
#   - TENANT_ID resolved from env via exocortex.db.get_tenant_id()

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from exocortex.db import execute, get_tenant_id, query, query_one

if TYPE_CHECKING:
    from exocortex.graph_rag import Answer

log = logging.getLogger(__name__)

QUERY_SOURCE = 'notion_cockpit_ask'
_MAX_REASON_CHARS = 500

_PENDING_SQL = """
    SELECT id, audience_name, page_id, property_name, notion_value
    FROM cockpit_actions_pending
    WHERE status = 'pending'
      AND property_name ILIKE %s
    ORDER BY created_at ASC
"""

_MARK_PROCESSED_SQL = """
    UPDATE cockpit_actions_pending
    SET status = %s, resolved_value = %s::jsonb, processed_at = now()
    WHERE id = %s
"""

# Today's cockpit usage (UTC day). Rows come from GraphRAGOrchestrator.answer.
_USAGE_TODAY_SQL = """
    SELECT count(*) AS questions, COALESCE(sum(cost_usd), 0) AS cost_usd
    FROM query_log
    WHERE tenant_id = %s
      AND source = %s
      AND asked_at >= (date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC')
"""


@dataclass(frozen=True)
class AskLimits:
    """Daily budget and per-question timeout; defaults come from Settings()."""

    max_questions_per_day: int
    max_cost_usd_per_day: float
    timeout_s: float

    @classmethod
    def from_settings(cls) -> AskLimits:
        from exocortex.settings import get_settings

        s = get_settings()
        return cls(
            max_questions_per_day=s.cockpit_ask_max_questions_per_day,
            max_cost_usd_per_day=s.cockpit_ask_max_cost_usd_per_day,
            timeout_s=s.cockpit_ask_timeout_s,
        )


class AskFailed(Exception):
    """A question that got no answer; `code` is a short machine-readable tag."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason[:_MAX_REASON_CHARS]


def graph_rag_ask(question: str) -> Answer:
    """Default ask: GraphRAGOrchestrator.answer, labelled as a cockpit question.

    Lazy import: graph_rag bootstraps config and the LLM router on import.
    """
    from exocortex.graph_rag import GraphRAGOrchestrator

    orchestrator = GraphRAGOrchestrator(tenant_id=get_tenant_id())
    return orchestrator.answer(question, query_source=QUERY_SOURCE)


class CockpitAskWorker:
    """Drains pending 'Ask the brain' rows and answers them with GraphRAG."""

    PROPERTY_PATTERN = '%Zapytaj mózg%'

    def __init__(self, ask_fn: Callable[[str], Answer] | None = None,
                 limits: AskLimits | None = None) -> None:
        self._ask_fn = ask_fn or graph_rag_ask
        self._limits = limits

    @property
    def limits(self) -> AskLimits:
        if self._limits is None:
            self._limits = AskLimits.from_settings()
        return self._limits

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

    def _check_budget(self, tenant_id: str) -> None:
        """Raise AskFailed('daily_limit') when today's budget is used up."""
        limits = self.limits
        row = query_one(_USAGE_TODAY_SQL, tenant_id, QUERY_SOURCE) or {}
        asked = int(row.get('questions') or 0)
        spent = float(row.get('cost_usd') or 0)
        if asked >= limits.max_questions_per_day:
            raise AskFailed(
                'daily_limit',
                f'Dzienny limit pytań z kokpitu wyczerpany: {asked}/'
                f'{limits.max_questions_per_day} (EXOCORTEX_COCKPIT_ASK_MAX_QUESTIONS_PER_DAY). '
                'Spróbuj jutro albo podnieś limit.',
            )
        if spent >= limits.max_cost_usd_per_day:
            raise AskFailed(
                'daily_limit',
                f'Dzienny limit kosztu pytań z kokpitu wyczerpany: ${spent:.4f}/'
                f'${limits.max_cost_usd_per_day:.2f} (EXOCORTEX_COCKPIT_ASK_MAX_COST_USD_PER_DAY). '
                'Spróbuj jutro albo podnieś limit.',
            )

    def _ask(self, question: str) -> Answer:
        """Run ask_fn under the timeout; every failure becomes AskFailed."""
        timeout_s = self.limits.timeout_s
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='cockpit-ask')
        try:
            ans = pool.submit(self._ask_fn, question).result(timeout=timeout_s)
        except FutureTimeoutError:
            raise AskFailed(
                'timeout', f'Silnik nie odpowiedział w {timeout_s:g} s (EXOCORTEX_COCKPIT_ASK_TIMEOUT_S).',
            ) from None
        except Exception as exc:
            raise AskFailed('engine_error', f'Błąd silnika GraphRAG: {type(exc).__name__}: {exc}') from exc
        finally:
            # a timed-out call keeps running in its thread; do not block on it
            pool.shutdown(wait=False)
        if ans.error:
            raise AskFailed('engine_error', f'Błąd silnika GraphRAG: {ans.error}')
        return ans

    @staticmethod
    def _mark(row_id: Any, status: str, payload: dict[str, Any] | None) -> None:
        execute(_MARK_PROCESSED_SQL, status,
                json.dumps(payload, ensure_ascii=False) if payload is not None else None,
                row_id)

    def process_pending(self) -> list[dict[str, Any]]:
        """Process all pending 'Ask the brain' rows; return per-row outcomes."""
        tenant_id = get_tenant_id()
        rows = query(_PENDING_SQL, self.PROPERTY_PATTERN) or []
        outcomes: list[dict[str, Any]] = []

        for row in rows:
            row_id = row['id']
            notion_value = row.get('notion_value')
            question = '' if self._is_empty(notion_value) else self._extract_question(notion_value)

            if self._is_empty(question):
                log.info('cockpit_ask: skipping empty input row id=%s', row_id)
                self._mark(row_id, 'skipped', None)
                outcomes.append({'row_id': row_id, 'status': 'skipped', 'reason': 'empty_input'})
                continue

            try:
                self._check_budget(tenant_id)
                ans = self._ask(question)
            except AskFailed as failed:
                if failed.code == 'engine_error':
                    log.warning('cockpit_ask: row id=%s failed: %s', row_id, failed.reason,
                                exc_info=failed.__cause__ is not None)
                else:
                    log.warning('cockpit_ask: row id=%s not answered: %s', row_id, failed.reason)
                self._mark(row_id, 'error', {'error': failed.reason, 'code': failed.code})
                outcomes.append({
                    'row_id': row_id,
                    'status': 'error',
                    'code': failed.code,
                    'reason': failed.reason,
                })
                continue

            self._mark(row_id, 'answered', {
                'question': question,
                'answer': ans.response,
                'sources': [{'thought_id': s.thought_id, 'title': s.title} for s in ans.sources],
                'query_log_id': ans.query_log_id,
                'cost_usd': ans.cost_usd,
                'latency_ms': ans.latency_ms,
                'cache_hit': ans.cache_hit,
            })
            outcomes.append({
                'row_id': row_id,
                'status': 'ok',
                'query_log_id': ans.query_log_id,
                'latency_ms': ans.latency_ms,
                'cost_usd': ans.cost_usd,
                'retrieved_count': len(ans.sources),
            })

        return outcomes
