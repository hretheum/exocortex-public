# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Header validation for lab processors: the same JSON Schemas as the gate.

The validator lives in tools/docschema (used by CI and the publisher). In
a checkout it sits next to the package; in the engine image it is copied to
/opt/exocortex/tools. The path is appended, never prepended, so it cannot
shadow the installed package.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _tools_root() -> Path | None:
    for root in (Path(__file__).resolve().parents[2], Path("/opt/exocortex")):
        if (root / "tools" / "docschema" / "core.py").is_file():
            return root
    return None


def validate(rel: str, text: str) -> list[str]:
    """Problems in the header of one document, as 'field: message' strings."""
    root = _tools_root()
    if root is None:
        raise RuntimeError("tools/docschema not found: header validation is not available")
    if str(root) not in sys.path:
        sys.path.append(str(root))
    from tools.docschema.core import validate_text

    return [f"{e.field}: {e.message}" for e in validate_text(rel, text)]
