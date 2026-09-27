# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass  # RunContext imported lazily to avoid cycles


class SectionGenerator(ABC):
    """Contract for live-section generators (wiki sections updated on events)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique section identifier, e.g. 'open_action_items'."""

    @abstractmethod
    def render(self, ctx: Any) -> str:
        """Render section content as a Markdown string.

        `ctx` is a `RunContext`-compatible mapping; typed as Any here to avoid
        a hard import cycle at definition time.
        """
