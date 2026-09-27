# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

from __future__ import annotations

from typing import Any

from exocortex.synth.perspectives.base import _LegacyWrapper


class FrpSession(_LegacyWrapper):
    """FRP synthesis: monthly aggregate across all FRP sessions in a period."""

    _legacy_type = "frp_monthly"

    @property
    def name(self) -> str:
        return "frp_session"

    def select_thoughts(self, ctx: Any) -> list[Any]:
        from exocortex.synthesizer import _select_thoughts_for_frp_monthly
        self._ctx = ctx
        return _select_thoughts_for_frp_monthly(ctx.tenant_id, ctx.perspective_key)


def setup(registry: Any) -> None:
    registry.register_perspective(FrpSession())
