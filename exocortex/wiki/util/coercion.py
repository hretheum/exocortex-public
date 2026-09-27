# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.
"""JSONB type coercion utilities."""

from __future__ import annotations

import json
from typing import Any


def _coerce_jsonb_list(v: Any) -> list:
    """Defensive coercion: some processors stored list-shaped payloads as
    JSON strings inside JSONB. Accept both shapes; everything else → []."""
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        try:
            parsed = json.loads(v)
        except (ValueError, TypeError):
            return []
        return parsed if isinstance(parsed, list) else []
    return []
