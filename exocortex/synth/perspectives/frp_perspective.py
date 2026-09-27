# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

from __future__ import annotations

from typing import Any

from exocortex.synth.perspectives.base import _LegacyWrapper


class FrpPerFrame(_LegacyWrapper):
    """FRP synthesis: one synthesis per Futures Reading frame/lens."""

    _legacy_type = "frp_per_frame"

    @property
    def name(self) -> str:
        return "frp_per_frame"

    def select_thoughts(self, ctx: Any) -> list[Any]:
        from exocortex.synthesizer import _select_thoughts_for_frp_per_frame
        self._ctx = ctx
        return _select_thoughts_for_frp_per_frame(ctx.tenant_id, ctx.perspective_key)


class FrpPerDomain(_LegacyWrapper):
    """FRP synthesis: one synthesis per knowledge domain."""

    _legacy_type = "frp_per_domain"

    @property
    def name(self) -> str:
        return "frp_per_domain"

    def select_thoughts(self, ctx: Any) -> list[Any]:
        from exocortex.synthesizer import _select_thoughts_for_frp_per_domain
        self._ctx = ctx
        return _select_thoughts_for_frp_per_domain(ctx.tenant_id, ctx.perspective_key)


class FrpEvolutionTimeline(_LegacyWrapper):
    """FRP synthesis: evolution timeline across all FRP sessions."""

    _legacy_type = "frp_evolution_timeline"

    @property
    def name(self) -> str:
        return "frp_evolution_timeline"

    def select_thoughts(self, ctx: Any) -> list[Any]:
        from exocortex.synthesizer import _select_thoughts_for_frp_evolution_timeline
        self._ctx = ctx
        return _select_thoughts_for_frp_evolution_timeline(ctx.tenant_id, ctx.perspective_key)


class FrpPerResonance(_LegacyWrapper):
    """FRP synthesis: thoughts grouped by resonance/signal type."""

    _legacy_type = "frp_per_resonance"

    @property
    def name(self) -> str:
        return "frp_per_resonance"

    def select_thoughts(self, ctx: Any) -> list[Any]:
        from exocortex.synthesizer import _select_thoughts_for_frp_per_resonance
        self._ctx = ctx
        return _select_thoughts_for_frp_per_resonance(ctx.tenant_id, ctx.perspective_key)


def setup(registry: Any) -> None:
    registry.register_perspective(FrpPerFrame())
    registry.register_perspective(FrpPerDomain())
    registry.register_perspective(FrpEvolutionTimeline())
    registry.register_perspective(FrpPerResonance())
