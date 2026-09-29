# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Checks shared with the publishing gate, for lab processors and pages.

- ``validate``: header validation with the same JSON Schemas as the gate
  (tools/docschema);
- ``personal_data``: the gate's personal-data rules (tools/leakgate/pii.py),
  so a lab page can leave out a line the gate would hold.

In a checkout the tools sit next to the package; in the engine image the
needed files are copied to /opt/exocortex/tools. The path is appended, never
prepended, so it cannot shadow the installed package.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _tools_root(marker: str = "docschema/core.py") -> Path | None:
    for root in (Path(__file__).resolve().parents[2], Path("/opt/exocortex")):
        if (root / "tools" / marker).is_file():
            return root
    return None


def _import_tools(marker: str) -> None:
    root = _tools_root(marker)
    if root is None:
        raise RuntimeError(f"tools/{marker} not found")
    if str(root) not in sys.path:
        sys.path.append(str(root))


def personal_data(text: str) -> list[str]:
    """Rule ids of personal data the gate would find in ``text`` (e-mail, phone, id numbers, names)."""
    _import_tools("leakgate/pii.py")
    from tools.leakgate.pii import detect

    return sorted({rule for _, rule, _, _ in detect(text, [], [])})


def validate(rel: str, text: str) -> list[str]:
    """Problems in the header of one document, as 'field: message' strings."""
    _import_tools("docschema/core.py")
    from tools.docschema.core import validate_text

    return [f"{e.field}: {e.message}" for e in validate_text(rel, text)]
