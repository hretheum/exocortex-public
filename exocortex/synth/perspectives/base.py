# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class PerspectiveType(ABC):
    """Contract for synthesis perspective handlers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Perspective slug, e.g. 'client_review', 'news_cluster'."""

    @abstractmethod
    def select_thoughts(self, ctx: Any) -> list[Any]:
        """Return the thought rows to synthesise for this perspective run."""

    @abstractmethod
    def build_prompt(self, thoughts: list[Any]) -> str:
        """Build the LLM prompt string from selected thoughts."""

    @abstractmethod
    def parse_response(self, response: str) -> dict[str, Any]:
        """Parse raw LLM response text into a dict ready for DB upsert."""


class _LegacyWrapper(PerspectiveType):
    """Thin adapter that delegates to pre-registry synthesizer helper functions.

    Subclasses set ``_legacy_type`` to the PERSPECTIVE_TYPES key used by the
    existing ``synthesizer.py`` functions.  The runner stores SynthContext in
    ``_ctx`` via ``select_thoughts()``; ``build_prompt()`` reads it.

    Not thread-safe — designed for single-threaded CLI use only.
    """

    _legacy_type: str = ""

    def __init__(self) -> None:
        self._ctx: Any = None

    def build_prompt(self, thoughts: list[Any]) -> str:
        if self._ctx is None:
            raise RuntimeError(
                f"{type(self).__name__}.build_prompt() called before select_thoughts(); "
                "call select_thoughts(ctx) first so _ctx is set."
            )
        from exocortex.synthesizer import (
            build_user_prompt,  # lazy — avoids circular import at module load
        )
        return build_user_prompt(
            self._legacy_type,
            self._ctx.perspective_key,
            thoughts,
            getattr(self._ctx, "edges", []),
            tenant_id=getattr(self._ctx, "tenant_id", None),
        )

    def parse_response(self, response: str) -> dict[str, Any]:
        from exocortex.synthesizer import _coerce_synthesis
        return _coerce_synthesis(response)
