"""Module-level telemetry sink. See ARCHITECTURE.md sec 8.

The sink is fired post-success, exceptions inside the sink are swallowed and
written to stderr — telemetry must NEVER block or fail a consumer call.
"""

from __future__ import annotations

import sys
import traceback
from typing import Callable

from llm_router.types import Usage

TelemetrySink = Callable[[Usage], None]

_sink: TelemetrySink | None = None


def set_telemetry_sink(sink: TelemetrySink | None) -> None:
    """Install (or clear) the post-call telemetry sink. Idempotent."""
    global _sink
    _sink = sink


def get_telemetry_sink() -> TelemetrySink | None:
    return _sink


def emit(usage: Usage) -> None:
    """Internal — called from API layer after every successful call."""
    sink = _sink
    if sink is None:
        return
    try:
        sink(usage)
    except Exception:
        traceback.print_exc(file=sys.stderr)
