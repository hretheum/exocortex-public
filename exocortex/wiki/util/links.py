# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.
"""URL and wiki link helpers."""

from __future__ import annotations

from typing import Optional


def _obsidian_advanced_uri(suffix: str) -> Optional[str]:
    """Build obsidian://advanced-uri?vault=<name>&<suffix> or None if no vault name."""
    from exocortex.settings import get_settings

    name = get_settings().vault_name
    if not name:
        return None
    return f"obsidian://advanced-uri?vault={name}&{suffix}"
