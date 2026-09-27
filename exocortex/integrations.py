# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Loads config/integrations.yaml (user-specific integration settings).

Falls back to ``config/integrations.example.yaml`` so the package remains
usable in clean checkouts where the operator has not yet copied the example.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "integrations.yaml"
_EXAMPLE_PATH = Path(__file__).parent.parent / "config" / "integrations.example.yaml"

_warned_missing = False


def _load() -> dict:
    import yaml  # local import keeps test stubs happy when PyYAML is absent

    global _warned_missing
    if _CONFIG_PATH.exists():
        return yaml.safe_load(_CONFIG_PATH.read_text()) or {}
    if _EXAMPLE_PATH.exists():
        return yaml.safe_load(_EXAMPLE_PATH.read_text()) or {}
    if not _warned_missing:
        logger.warning(
            "No integrations config found (expected %s or %s); "
            "internal-domain-dependent features will be disabled.",
            _CONFIG_PATH,
            _EXAMPLE_PATH,
        )
        _warned_missing = True
    return {}


def get_internal_domain() -> Optional[str]:
    return _load().get("internal_domain")
