# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

from __future__ import annotations

from typing import Any

from exocortex.synth.perspectives.base import _LegacyWrapper


class DecisionLog(_LegacyWrapper):
    """Synthesis perspective: decisions clustered by tag/topic."""

    _legacy_type = "tag"

    @property
    def name(self) -> str:
        return "decision_log"

    def select_thoughts(self, ctx: Any) -> list[Any]:
        from exocortex.synthesizer import _select_thoughts_for_tag
        self._ctx = ctx
        return _select_thoughts_for_tag(ctx.tenant_id, ctx.perspective_key)


def setup(registry: Any) -> None:
    registry.register_perspective(DecisionLog())
