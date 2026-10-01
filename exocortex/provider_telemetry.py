# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""R4 — Provider error telemetry. Registers as router's on_provider_error hook.

Called by the router on every provider failure during the fallback chain.
Inserts into provider_errors table for dashboard + health monitoring.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


def on_provider_error(
    *,
    provider: str,
    model: str,
    use_case: str,
    status: int,
    error_type: str,
    error_message: str,
    latency_ms: int,
    fallback_chain: list[str],
) -> None:
    """Insert a provider error row. Called from llm_router's except block."""
    try:
        from exocortex.db import execute, get_tenant_id

        execute(
            "INSERT INTO provider_errors "
            "(tenant_id, provider, model, use_case, status, error_type, "
            " error_message, fallback_chain, latency_ms, started_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            get_tenant_id(),
            provider,
            model,
            use_case,
            status,
            error_type,
            error_message[:500],
            fallback_chain or [],
            latency_ms,
            datetime.now(UTC),
        )
    except Exception as exc:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
        logger.debug("Failed to persist provider error: %s", exc)
