# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# domain/__init__.py — Public API for the domain layer.
#
# Re-exports entities from entities.py and TypedDicts from exocortex/types.py
# so callers can do ``from exocortex.domain import Thought, SynthesisResult``.

from __future__ import annotations

from exocortex.domain.entities import (
    Answer,
    Classification,
    Source,
    SynthesisResult,
    Thought,
)

__all__ = [
    "Answer",
    "Classification",
    "Source",
    "SynthesisResult",
    "Thought",
]
