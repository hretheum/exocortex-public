# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

from __future__ import annotations

from typing import Any

from exocortex.synth.perspectives.base import _LegacyWrapper


class MeetingSummary(_LegacyWrapper):
    """Synthesis perspective: meetings grouped by meeting type (1on1, design-review, etc.)."""

    _legacy_type = "type"

    @property
    def name(self) -> str:
        return "meeting_summary"

    def select_thoughts(self, ctx: Any) -> list[Any]:
        from exocortex.synthesizer import _select_thoughts_for_type
        self._ctx = ctx
        return _select_thoughts_for_type(ctx.tenant_id, ctx.perspective_key)


def setup(registry: Any) -> None:
    registry.register_perspective(MeetingSummary())
