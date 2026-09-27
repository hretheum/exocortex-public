# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31.5.2 — gap_radar perspective.

Thin legacy-wrapper that delegates selection/prompt-building to
``exocortex.synthesizer`` (`_select_gap_radar` + `_build_gap_radar_prompt`).
The legacy synthesizer handles persistence and idempotency.
"""
from __future__ import annotations

from typing import Any

from exocortex.synth.perspectives.base import _LegacyWrapper


class GapRadar(_LegacyWrapper):
    """Weekly Gap Radar synthesis driven by F31.5.1 gap detectors."""

    _legacy_type = "gap_radar"

    @property
    def name(self) -> str:
        return "gap_radar"

    def select_thoughts(self, ctx: Any) -> list[Any]:
        from exocortex.synthesizer import _select_gap_radar
        self._ctx = ctx
        return _select_gap_radar(ctx.tenant_id, ctx.perspective_key)


def setup(registry: Any) -> None:
    registry.register_perspective(GapRadar())
