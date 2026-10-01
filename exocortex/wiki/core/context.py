# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.
"""RunContext — execution context passed to domain compilers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RunContext:
    """Execution context for a single wiki compile run."""

    tenant_id: str
    since: datetime | None = None
    dry_run: bool = False
    full_rebuild: bool = False
    current_run_id: str | None = None
    pages_written: list = field(default_factory=list)
    llm_tokens_used: int = 0
