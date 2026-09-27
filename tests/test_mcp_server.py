# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31.5.2 — tests for the `gap_analysis` MCP tool."""

from __future__ import annotations

import os
from unittest.mock import patch

os.environ.setdefault("TENANT_ID", "00000000-0000-0000-0000-000000000000")
os.environ.setdefault("EXOCORTEX_VAULT_PATH", "/tmp/exocortex-test-vault")


TENANT = "00000000-0000-0000-0000-000000000000"


_FAKE_GAPS = [
    {
        "type": "cluster-no-synth",
        "title": "Klaster 'globex' bez syntezy (8 thoughts)",
        "thought_ids": ["uuid-a", "uuid-b"],
        "age_days": 12.0,
        "suggested_action": "Zsyntetyzuj klaster 'globex'",
        "meta": {"tag": "globex", "thought_count": 8},
    },
    {
        "type": "stale-orphan",
        "title": "Old thought",
        "thought_ids": ["uuid-c"],
        "age_days": 60.0,
        "suggested_action": "Połącz lub archiwizuj",
        "meta": {"edge_count": 0},
    },
    {
        "type": "no-decision",
        "title": "Observation z marca",
        "thought_ids": ["uuid-d"],
        "age_days": 30.0,
        "suggested_action": "Dodaj decyzję",
        "meta": {"thought_type": "observation"},
    },
]


def _call_gap_analysis(**kwargs):
    """Invoke the MCP tool's underlying function (bypass FastMCP wrapper)."""
    from exocortex import mcp_server
    fn = mcp_server.gap_analysis
    fn = getattr(fn, "fn", fn)  # FastMCP @tool may wrap; .fn exposes original
    return fn(**kwargs)


def test_gap_analysis_returns_all_gaps_when_no_filters():
    from exocortex import mcp_server  # noqa: F401 — ensure import resolves
    with patch(
        "exocortex.workers.gap_queries.run_all_detectors",
        return_value=list(_FAKE_GAPS),
    ):
        gaps = _call_gap_analysis()
    assert len(gaps) == 3
    assert {g["type"] for g in gaps} == {
        "cluster-no-synth", "stale-orphan", "no-decision",
    }


def test_gap_analysis_filters_by_type():
    with patch(
        "exocortex.workers.gap_queries.run_all_detectors",
        return_value=list(_FAKE_GAPS),
    ):
        gaps = _call_gap_analysis(type="stale-orphan")
    assert len(gaps) == 1
    assert gaps[0]["type"] == "stale-orphan"
    assert gaps[0]["title"] == "Old thought"


def test_gap_analysis_filters_by_scope():
    """Scope filter keeps gaps whose thought_ids overlap with tag-tagged thoughts."""
    scoped_rows = [{"thought_id": "uuid-a"}, {"thought_id": "uuid-c"}]
    with patch(
        "exocortex.workers.gap_queries.run_all_detectors",
        return_value=list(_FAKE_GAPS),
    ), patch(
        "exocortex.mcp_server.query", return_value=scoped_rows,
    ):
        gaps = _call_gap_analysis(scope=["globex"])

    # uuid-a → cluster gap kept; uuid-c → stale-orphan kept; uuid-d → no-decision dropped.
    types = {g["type"] for g in gaps}
    assert types == {"cluster-no-synth", "stale-orphan"}


def test_gap_analysis_empty_when_no_gaps_detected():
    with patch(
        "exocortex.workers.gap_queries.run_all_detectors",
        return_value=[],
    ):
        gaps = _call_gap_analysis()
    assert gaps == []
