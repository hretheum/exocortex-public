# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Processor(ABC):
    """Contract for capture-pipeline processors (one per source_type)."""

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Identifier matching the `source_type` column in the `sources` table."""

    @abstractmethod
    def process(self, source_id: int) -> dict[str, Any]:
        """Process a raw source row and return a dict suitable for PG upsert.

        Must be idempotent — called on re-ingestion without side-effects.
        """
