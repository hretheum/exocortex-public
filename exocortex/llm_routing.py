# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/llm_routing.py — bootstrap llm_router for second-brain.
#
# - Resolves config/llm_routing.yaml relative to repo root, or the file named
#   by EXOCORTEX_LLM_ROUTING (e.g. config/llm_routing.selfhosted.yaml).
# - Wires telemetry sink → llm_provider_runs table (privacy-preserving:
#   Usage never carries prompt content).
# - Idempotent: subsequent calls are no-ops, safe to call from every entry
#   point (workers, scripts, processors).

from __future__ import annotations

import logging
import os
from pathlib import Path

from llm_router import (
    Usage,
)
from llm_router import (
    set_routing_config as _set_routing_config,
)
from llm_router import (
    set_telemetry_sink as _set_telemetry_sink,
)

_logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_ROUTING_PATH = _REPO_ROOT / 'config' / 'llm_routing.yaml'

_initialized: bool = False


def _telemetry_sink(usage: Usage) -> None:
    """Persist a Usage record into llm_provider_runs.

    Sink errors must NOT bubble into the caller (router catches them already,
    but be defensive here too)."""
    try:
        # Local import to avoid an import cycle at module load.
        from exocortex.db import conn as _conn
    except Exception:  # pragma: no cover  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
        _logger.warning('llm_routing: db import failed, telemetry skipped')
        return

    from exocortex.settings import get_tenant_id

    tenant_id = get_tenant_id()
    if not tenant_id or tenant_id == 'default':
        # Skip telemetry when caller relies on the default fallback — keeps
        # the DB clean of bootstrap noise during fresh installs.
        return

    try:
        with _conn() as c:
            c.execute(
                'INSERT INTO llm_provider_runs '
                '(tenant_id, use_case, provider, model, input_tokens, output_tokens, '
                ' cache_creation_input_tokens, cache_read_input_tokens, cost_usd, '
                ' latency_ms, started_at, fallback_chain) '
                'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                (
                    tenant_id,
                    usage.use_case,
                    usage.provider,
                    usage.model,
                    int(usage.input_tokens),
                    int(usage.output_tokens),
                    int(usage.cache_creation_input_tokens),
                    int(usage.cache_read_input_tokens),
                    float(usage.cost_usd),
                    int(usage.latency_ms),
                    usage.started_at,
                    list(usage.fallback_chain),
                ),
            )
    except Exception as exc:  # pragma: no cover - defensive only  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
        _logger.warning('llm_routing: telemetry insert failed: %r', exc)


def initialize(routing_path: Path | None = None) -> None:
    """Load routing yaml + install telemetry sink. Idempotent."""
    global _initialized
    if _initialized:
        return
    env_path = os.environ.get('EXOCORTEX_LLM_ROUTING', '').strip()
    path = routing_path or (Path(env_path) if env_path else _DEFAULT_ROUTING_PATH)
    if env_path and not routing_path and not path.is_absolute() and not path.exists():
        path = _REPO_ROOT / path
    if env_path and not routing_path and not path.exists():
        raise FileNotFoundError(f'EXOCORTEX_LLM_ROUTING points to a missing file: {path}')
    if not path.exists():
        _logger.warning('llm_routing: %s not found, skipping setup', path)
        _initialized = True
        return
    _set_routing_config(path)
    _set_telemetry_sink(_telemetry_sink)

    # R4 — register provider error hook for health monitoring
    try:
        import llm_router.router as _rr

        from exocortex.provider_telemetry import on_provider_error as _error_hook
        # the vendored llm_router (0.1.2) has no on_provider_error hook: nothing in the
        # router reads this attribute, so provider errors do not reach the hook yet
        _rr.on_provider_error = _error_hook  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001, S110 — failure is ignored on purpose; narrowing would change behavior
        pass

    _initialized = True


# Auto-initialize on import. Each entry point that imports this module gets
# a configured router. Importing from workers/processors/_common.py covers
# all F6.3 processors + cross-domain matcher; explicit imports in synthesizer
# / scripts cover the rest.
initialize()
