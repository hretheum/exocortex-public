# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

from __future__ import annotations

from typing import Any

from exocortex.synth.perspectives.base import _LegacyWrapper


class PersonProfile(_LegacyWrapper):
    """Synthesis perspective: one synthesis per person mentioned across meetings."""

    _legacy_type = "person"

    @property
    def name(self) -> str:
        return "person_profile"

    def select_thoughts(self, ctx: Any) -> list[Any]:
        from exocortex.synthesizer import _select_thoughts_for_person
        self._ctx = ctx
        return _select_thoughts_for_person(ctx.tenant_id, ctx.perspective_key)


def setup(registry: Any) -> None:
    registry.register_perspective(PersonProfile())
