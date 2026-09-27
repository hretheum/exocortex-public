# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""zadanie-19 — area_digest perspective: one synthesis per vault_note
section_path[1] area (e.g. 'architecture', 'personal'). See
docs/synteza/PERSPEKTYWY.md for the design and rejected alternatives."""
from __future__ import annotations

from typing import Any

from exocortex.synth.perspectives.base import _LegacyWrapper


class AreaDigest(_LegacyWrapper):
    """Synthesis perspective: state of one vault_note area."""

    _legacy_type = "area_digest"

    @property
    def name(self) -> str:
        return "area_digest"

    def select_thoughts(self, ctx: Any) -> list[Any]:
        from exocortex.synthesizer import _select_thoughts_for_area_digest
        self._ctx = ctx
        return _select_thoughts_for_area_digest(ctx.tenant_id, ctx.perspective_key)


def setup(registry: Any) -> None:
    registry.register_perspective(AreaDigest())
