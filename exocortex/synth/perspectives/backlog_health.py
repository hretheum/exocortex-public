# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""backlog_health perspective: one synthesis per backlog_item
metadata.area (e.g. '_second-brain', 'architecture', '_router')."""
from __future__ import annotations

from typing import Any

from exocortex.synth.perspectives.base import _LegacyWrapper


class BacklogHealth(_LegacyWrapper):
    """Synthesis perspective: health of one backlog area (stale items +
    blocking chains — deliberately one perspective, not two)."""

    _legacy_type = "backlog_health"

    @property
    def name(self) -> str:
        return "backlog_health"

    def select_thoughts(self, ctx: Any) -> list[Any]:
        from exocortex.synthesizer import _select_thoughts_for_backlog_health
        self._ctx = ctx
        return _select_thoughts_for_backlog_health(ctx.tenant_id, ctx.perspective_key)


def setup(registry: Any) -> None:
    registry.register_perspective(BacklogHealth())
