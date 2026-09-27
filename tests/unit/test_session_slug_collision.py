# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Regression: distinct Claude Code sessions with the same ai-title (e.g. many
'Review X security vulnerabilities') collapsed onto one filename because the
slug was derived from the title alone. 162 thoughts produced only 148 pages —
14 sessions overwrote each other. Session pages must carry a per-thought
suffix, like meeting pages do."""
from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


def _thought(tid, title):
    return {
        "id": tid, "body": f"# {title}\ntresc", "thought_type": "claude_session",
        "metadata": {"title": title, "domain": "sb", "uri": f"claude-session://{tid}",
                     "session_id": tid, "redaction_verdict": "clean"},
        "extracted_tags": {}, "source_id": f"src-{tid[:4]}",
        "created_at": datetime(2026, 8, 4),
    }


def test_same_title_distinct_sessions_get_distinct_pages():
    import exocortex.wiki_compiler as wc
    from exocortex.wiki.domains import clippings as cl

    tmp = Path(tempfile.mkdtemp())
    rows = [_thought("11111111-aaaa-bbbb-cccc-000000000001",
                     "Review A2A endpoint for security vulnerabilities"),
            _thought("22222222-aaaa-bbbb-cccc-000000000002",
                     "Review A2A endpoint for security vulnerabilities")]
    with patch("exocortex.db.query", return_value=rows), \
         patch("exocortex.wiki.core.io._get_wiki_root", return_value=tmp):
        wc.DRY_RUN = False
        wc._wc_state.DRY_RUN = False
        from exocortex.wiki_compiler import compile_sb_module
        compile_sb_module("test", None)

    pages = list((tmp / "sb" / "sessions").glob("*.md"))
    assert len(pages) == 2, f"identyczny tytul, 2 sesje -> 2 strony, jest {len(pages)}"
