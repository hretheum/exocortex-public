# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Unit tests for F31.5.1 — gap detectors (mocked DB, no real connection)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

os.environ.setdefault("TENANT_ID", "00000000-0000-0000-0000-000000000000")
os.environ.setdefault("EXOCORTEX_VAULT_PATH", "/tmp/exocortex-test-vault")

from exocortex.workers import gap_queries  # noqa: E402


TENANT = "00000000-0000-0000-0000-000000000000"


def _ago(days: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


# ---------------------------------------------------------------------------
# Detector 1 — dense clusters
# ---------------------------------------------------------------------------

def test_dense_clusters_returns_gap_per_unsynthesized_tag():
    """Two tags with >5 thoughts and no synthesis → 2 cluster-no-synth gaps."""
    fake_rows = [
        {
            "tag": "remediation",
            "thought_count": 12,
            "oldest_at": _ago(30),
            "sample_ids": ["uuid-1", "uuid-2", "uuid-3"],
        },
        {
            "tag": "pulse",
            "thought_count": 7,
            "oldest_at": _ago(20),
            "sample_ids": ["uuid-4", "uuid-5", "uuid-6"],
        },
    ]
    with patch("exocortex.workers.gap_queries.query", return_value=fake_rows) as q:
        gaps = gap_queries.detect_dense_clusters_no_synthesis(
            TENANT, min_cluster_size=5, max_results=20,
        )

    q.assert_called_once()
    # Parameter order: tenant, tenant, min_cluster_size, max_results
    args = q.call_args.args
    assert args[1:] == (TENANT, TENANT, 5, 20)

    assert len(gaps) == 2
    assert all(g["type"] == "cluster-no-synth" for g in gaps)
    assert gaps[0]["meta"]["tag"] == "remediation"
    assert gaps[0]["meta"]["thought_count"] == 12
    assert gaps[0]["thought_ids"] == ["uuid-1", "uuid-2", "uuid-3"]
    assert "remediation" in gaps[0]["title"]
    assert "Zsyntetyzuj" in gaps[0]["suggested_action"]
    assert gaps[0]["age_days"] >= 29.0


def test_dense_clusters_handles_empty_result():
    with patch("exocortex.workers.gap_queries.query", return_value=[]):
        gaps = gap_queries.detect_dense_clusters_no_synthesis(TENANT)
    assert gaps == []


# ---------------------------------------------------------------------------
# Detector 2 — no decision
# ---------------------------------------------------------------------------

def test_thoughts_without_decision_returns_one_gap_per_row():
    fake_rows = [
        {
            "thought_id": "obs-1",
            "body": "User churn rośnie tydzień do tygodnia",
            "metadata": {"title": "Churn rośnie"},
            "thought_type": "observation",
            "created_at": _ago(40),
        },
        {
            "thought_id": "obs-2",
            "body": "Marża spadła do 23%",
            "metadata": {},
            "thought_type": "finding",
            "created_at": _ago(20),
        },
        {
            "thought_id": "obs-3",
            "body": "Cykl decyzyjny u klienta to 6 tygodni",
            "metadata": None,
            "thought_type": "observation",
            "created_at": _ago(15),
        },
    ]
    with patch("exocortex.workers.gap_queries.query", return_value=fake_rows) as q:
        gaps = gap_queries.detect_thoughts_without_decision(
            TENANT, min_age_days=14, max_results=20,
        )

    args = q.call_args.args
    assert args[1:] == (TENANT, 14, TENANT, 20)

    assert len(gaps) == 3
    assert all(g["type"] == "no-decision" for g in gaps)
    # Title falls back to metadata.title when present
    assert gaps[0]["title"] == "Churn rośnie"
    # Title falls back to body excerpt when no metadata.title
    assert gaps[1]["title"].startswith("Marża spadła")
    # Title still works when metadata is None
    assert gaps[2]["title"].startswith("Cykl decyzyjny")
    assert gaps[0]["thought_ids"] == ["obs-1"]
    assert gaps[0]["meta"]["thought_type"] == "observation"
    assert gaps[1]["meta"]["thought_type"] == "finding"


# ---------------------------------------------------------------------------
# Detector 3 — unresolved contradictions
# ---------------------------------------------------------------------------

def test_unresolved_contradictions_returns_gap_per_edge():
    fake_rows = [
        {
            "edge_id": "edge-1",
            "src_id": "thought-a",
            "dst_id": "thought-b",
            "body_a": "Klient prosi o feature X",
            "metadata_a": {"title": "Wymaganie X"},
            "body_b": "Architektura nie wspiera X",
            "metadata_b": {"title": "Constraint X"},
            "created_at": _ago(10),
        },
        {
            "edge_id": "edge-2",
            "src_id": "thought-c",
            "dst_id": "thought-d",
            "body_a": "Sprint capacity = 40 pt",
            "metadata_a": None,
            "body_b": "Scope wymaga 80 pt",
            "metadata_b": None,
            "created_at": _ago(5),
        },
    ]
    with patch("exocortex.workers.gap_queries.query", return_value=fake_rows) as q:
        gaps = gap_queries.detect_unresolved_contradictions(TENANT, max_results=20)

    args = q.call_args.args
    assert args[1:] == (TENANT, 20)

    assert len(gaps) == 2
    assert all(g["type"] == "contradiction-unresolved" for g in gaps)
    assert gaps[0]["thought_ids"] == ["thought-a", "thought-b"]
    assert "Wymaganie X" in gaps[0]["title"]
    assert "Constraint X" in gaps[0]["title"]
    assert gaps[0]["meta"]["edge_id"] == "edge-1"
    # Falls back to body excerpt when metadata.title missing
    assert "Sprint capacity" in gaps[1]["title"]


# ---------------------------------------------------------------------------
# Detector 4 — stale orphans
# ---------------------------------------------------------------------------

def test_stale_orphans_returns_one_gap_per_thought():
    fake_rows = [
        {
            "thought_id": "stale-1",
            "body": "Pomysł na integrację z Notion",
            "metadata": {"title": "Notion integracja"},
            "created_at": _ago(60),
            "edge_count": 0,
        },
        {
            "thought_id": "stale-2",
            "body": "TODO: przejrzeć backlog Q3",
            "metadata": {},
            "created_at": _ago(45),
            "edge_count": 1,
        },
        {
            "thought_id": "stale-3",
            "body": "Notatka z konferencji",
            "metadata": {"title": "Konferencja Berlin"},
            "created_at": _ago(35),
            "edge_count": 2,
        },
    ]
    with patch("exocortex.workers.gap_queries.query", return_value=fake_rows) as q:
        gaps = gap_queries.detect_stale_orphans(
            TENANT, min_age_days=30, max_edge_count=2, max_results=20,
        )

    args = q.call_args.args
    assert args[1:] == (TENANT, TENANT, 30, TENANT, 2, 20)

    assert len(gaps) == 3
    assert all(g["type"] == "stale-orphan" for g in gaps)
    assert gaps[0]["title"] == "Notion integracja"
    assert gaps[0]["meta"]["edge_count"] == 0
    assert gaps[1]["meta"]["edge_count"] == 1
    assert gaps[2]["meta"]["edge_count"] == 2
    assert gaps[0]["age_days"] >= 59.0


# ---------------------------------------------------------------------------
# Aggregate runner
# ---------------------------------------------------------------------------

def test_run_all_detectors_aggregates_all_four():
    """run_all_detectors concatenates results from all 4 detectors."""
    with patch(
        "exocortex.workers.gap_queries.detect_dense_clusters_no_synthesis",
        return_value=[gap_queries.Gap(
            type="cluster-no-synth", title="t1", thought_ids=["a"],
            age_days=1.0, suggested_action="x", meta={},
        )],
    ) as d1, patch(
        "exocortex.workers.gap_queries.detect_thoughts_without_decision",
        return_value=[gap_queries.Gap(
            type="no-decision", title="t2", thought_ids=["b"],
            age_days=15.0, suggested_action="x", meta={},
        )],
    ) as d2, patch(
        "exocortex.workers.gap_queries.detect_unresolved_contradictions",
        return_value=[gap_queries.Gap(
            type="contradiction-unresolved", title="t3", thought_ids=["c", "d"],
            age_days=3.0, suggested_action="x", meta={},
        )],
    ) as d3, patch(
        "exocortex.workers.gap_queries.detect_stale_orphans",
        return_value=[gap_queries.Gap(
            type="stale-orphan", title="t4", thought_ids=["e"],
            age_days=40.0, suggested_action="x", meta={},
        )],
    ) as d4:
        gaps = gap_queries.run_all_detectors(TENANT, max_results=10)

    d1.assert_called_once_with(TENANT, max_results=10)
    d2.assert_called_once_with(TENANT, max_results=10)
    d3.assert_called_once_with(TENANT, max_results=10)
    d4.assert_called_once_with(TENANT, max_results=10)

    assert len(gaps) == 4
    types = {g["type"] for g in gaps}
    assert types == {
        "cluster-no-synth", "no-decision",
        "contradiction-unresolved", "stale-orphan",
    }
