# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.
"""User-state preservation for wiki pages.

CRITICAL — F11.4 SAFETY GUARD:
  This module is the sole guardian of the F11.4 invariant:
  "the user toggled hundreds of [x] markers by hand — painstaking work, immutable".

  Every function here MUST preserve verbatim [x] checkbox states that the
  user has manually set. Never reorder, strip, or re-render [x] items.
  Content-based fingerprint matching (not position-based) ensures DB
  re-renders with different ordering still respect user toggles.

  Pre/post invariant: count([x] in merged output) >= count([x] in existing_body).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional


# Regex patterns for task line parsing
_X_LINE_RE = re.compile(r"^(\s*- )\[[xX]\]\s+(.+?)\s*$", re.MULTILINE)
_OPEN_LINE_RE = re.compile(r"^(\s*- )\[ \]\s+(.+?)\s*$", re.MULTILINE)
_DONE_DATE_RE = re.compile(r"\s+✅\s*\d{4}-\d{2}-\d{2}")
_ADD_DATE_RE = re.compile(r"\s+➕\s*\d{4}-\d{2}-\d{2}")


def _task_fingerprint(content: str) -> str:
    """Normalize task line content for content-based matching across DB re-renders.

    Strips date markers (✅, ➕), collapses whitespace. Used to detect user-toggled
    [x] on a task line even if DB-rendered version (with date stamps, ordering)
    differs slightly. F11.4 SAFETY constraint preservation.
    """
    s = _DONE_DATE_RE.sub("", content)
    s = _ADD_DATE_RE.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def _extract_done_fingerprints(body: str) -> set[str]:
    """Return set of task content fingerprints marked [x] in existing body."""
    return {_task_fingerprint(m.group(2)) for m in _X_LINE_RE.finditer(body)}


def _merge_user_done_state(new_body: str, existing_body: Optional[str]) -> str:
    """Preserve user-toggled [x] markers from existing meeting page when
    re-rendering body from DB state. Per F11.4 SAFETY constraint:
    'the user toggled hundreds of [x] markers by hand — painstaking work, immutable'.

    Strategy: content-based fingerprint match (NOT position-based, because DB
    re-ingest may change task ordering). Each task line in new_body with [ ]
    whose fingerprint matches one in existing_body's [x] set → flip to [x],
    appending today's ✅ stamp if missing.
    """
    if not existing_body:
        return new_body
    done_fps = _extract_done_fingerprints(existing_body)
    if not done_fps:
        return new_body
    today = datetime.now(timezone.utc).date().isoformat()

    def _flip(m: re.Match) -> str:
        indent_marker, content = m.group(1), m.group(2)
        if _task_fingerprint(content) not in done_fps:
            return m.group(0)  # not user-toggled, keep [ ]
        # User had [x] — preserve. Append ✅ stamp if missing.
        if "✅" not in content:
            return f"{indent_marker}[x] {content} ✅ {today}"
        return f"{indent_marker}[x] {content}"

    return _OPEN_LINE_RE.sub(_flip, new_body)
