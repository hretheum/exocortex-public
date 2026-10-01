# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Unit tests for F31.5.3 — output_nudges (mocked DB + tmp_path vault)."""

from __future__ import annotations

import os
from unittest.mock import patch

os.environ.setdefault("TENANT_ID", "00000000-0000-0000-0000-000000000000")
os.environ.setdefault("EXOCORTEX_VAULT_PATH", "/tmp/exocortex-test-vault-nudges")

from exocortex.workers import output_nudges

TENANT = "00000000-0000-0000-0000-000000000000"


_GAP_RADAR_CONTENT = {
    "current_state": "Pojawiło się kilka klastrów bez syntezy. Warto rozważyć newsletter.",
    "recent_decisions": [],
    "open_problems": [
        {"title": "Klaster remediation bez syntezy", "severity": "medium"},
    ],
    "ownership": [],
    "next_steps": [
        {"title": "Napisz draft o remediation", "owner": "", "date": ""},
    ],
}

_GAP_RADAR_NO_OUTPUT_HINT = {
    "current_state": "Wszystko stabilne.",
    "recent_decisions": [],
    "open_problems": [],
    "ownership": [],
    "next_steps": [],
}

_FAKE_CLUSTER_GAPS = [
    {
        "type": "cluster-no-synth",
        "title": "Klaster 'remediation' bez syntezy (12 thoughts)",
        "thought_ids": ["uuid-1", "uuid-2", "uuid-3"],
        "age_days": 30.0,
        "suggested_action": "Zsyntetyzuj klaster 'remediation'",
        "meta": {"tag": "remediation", "thought_count": 12},
    },
    {
        "type": "cluster-no-synth",
        "title": "Klaster 'pulse' bez syntezy (7 thoughts)",
        "thought_ids": ["uuid-4", "uuid-5", "uuid-6"],
        "age_days": 20.0,
        "suggested_action": "Zsyntetyzuj klaster 'pulse'",
        "meta": {"tag": "pulse", "thought_count": 7},
    },
]


# ---------------------------------------------------------------------------
# get_latest_gap_radar_synthesis
# ---------------------------------------------------------------------------

def test_get_latest_gap_radar_returns_content_on_hit():
    with patch(
        "exocortex.workers.output_nudges.query_one",
        return_value={"content": _GAP_RADAR_CONTENT},
    ) as q:
        out = output_nudges.get_latest_gap_radar_synthesis(TENANT)

    q.assert_called_once()
    # tenant_id passed as positional param
    assert q.call_args.args[1] == TENANT
    assert out == _GAP_RADAR_CONTENT


def test_get_latest_gap_radar_returns_none_on_miss():
    with patch("exocortex.workers.output_nudges.query_one", return_value=None):
        out = output_nudges.get_latest_gap_radar_synthesis(TENANT)
    assert out is None


# ---------------------------------------------------------------------------
# extract_output_suggestions
# ---------------------------------------------------------------------------

def test_extract_output_suggestions_uses_cluster_gaps():
    with patch(
        "exocortex.workers.output_nudges.gap_queries.detect_dense_clusters_no_synthesis",
        return_value=_FAKE_CLUSTER_GAPS,
    ):
        suggestions = output_nudges.extract_output_suggestions(_GAP_RADAR_CONTENT)

    assert len(suggestions) == 2
    slugs = [s["slug"] for s in suggestions]
    assert slugs == ["remediation", "pulse"]
    assert "remediation" in suggestions[0]["title"].lower()
    assert "12" in suggestions[0]["body"]
    assert "uuid-1" in suggestions[0]["body"]


def test_extract_output_suggestions_empty_when_no_clusters_and_no_keyword():
    with patch(
        "exocortex.workers.output_nudges.gap_queries.detect_dense_clusters_no_synthesis",
        return_value=[],
    ):
        suggestions = output_nudges.extract_output_suggestions(_GAP_RADAR_NO_OUTPUT_HINT)
    assert suggestions == []


# ---------------------------------------------------------------------------
# emit_draft_suggestions
# ---------------------------------------------------------------------------

def test_emit_draft_suggestions_writes_files_with_frontmatter(tmp_path):
    suggestions = [
        {"slug": "remediation", "title": "Newsletter draft: remediation",
         "body": "Body text."},
    ]
    written = output_nudges.emit_draft_suggestions(
        suggestions, str(tmp_path), today="2026-05-24",
    )

    assert len(written) == 1
    path = written[0]
    assert path.exists()
    assert path.name == "2026-05-24-remediation.md"
    assert path.parent == tmp_path / "wiki" / "news" / "drafts" / "_pending"

    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "provenance: ai_authored" in text
    assert "agent: exocortex-gap-radar" in text
    assert "session_date: 2026-05-24" in text
    assert "human_validated: false" in text
    assert "status: draft_suggestion" in text
    assert "gap_source: gap_radar" in text
    assert "## Newsletter draft: remediation" in text
    assert "Body text." in text
    assert "Sugestia wygenerowana przez Gap Radar" in text


def test_emit_draft_suggestions_is_idempotent(tmp_path):
    suggestions = [
        {"slug": "remediation", "title": "X", "body": "Y"},
    ]
    first = output_nudges.emit_draft_suggestions(
        suggestions, str(tmp_path), today="2026-05-24",
    )
    second = output_nudges.emit_draft_suggestions(
        suggestions, str(tmp_path), today="2026-05-24",
    )
    assert len(first) == 1
    assert second == []
    files = list((tmp_path / "wiki" / "news" / "drafts" / "_pending").iterdir())
    assert len(files) == 1


# ---------------------------------------------------------------------------
# run() integration (mocked DB + tmp vault)
# ---------------------------------------------------------------------------

def test_run_dry_run_does_not_write_files(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("EXOCORTEX_VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("TENANT_ID", TENANT)
    with patch(
        "exocortex.workers.output_nudges.query_one",
        return_value={"content": _GAP_RADAR_CONTENT},
    ), patch(
        "exocortex.workers.output_nudges.gap_queries.detect_dense_clusters_no_synthesis",
        return_value=_FAKE_CLUSTER_GAPS,
    ):
        count = output_nudges.run(dry_run=True)

    assert count == 2
    captured = capsys.readouterr()
    assert "would write" in captured.out
    # No files created
    pending = tmp_path / "wiki" / "news" / "drafts" / "_pending"
    assert not pending.exists() or not any(pending.iterdir())


def test_run_writes_files_when_not_dry(tmp_path, monkeypatch):
    monkeypatch.setenv("EXOCORTEX_VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("TENANT_ID", TENANT)
    with patch(
        "exocortex.workers.output_nudges.query_one",
        return_value={"content": _GAP_RADAR_CONTENT},
    ), patch(
        "exocortex.workers.output_nudges.gap_queries.detect_dense_clusters_no_synthesis",
        return_value=_FAKE_CLUSTER_GAPS,
    ):
        count = output_nudges.run(dry_run=False)

    assert count == 2
    pending = tmp_path / "wiki" / "news" / "drafts" / "_pending"
    files = sorted(p.name for p in pending.iterdir())
    assert len(files) == 2
    assert any("remediation" in f for f in files)
    assert any("pulse" in f for f in files)


def test_run_returns_zero_when_no_synthesis(tmp_path, monkeypatch):
    monkeypatch.setenv("EXOCORTEX_VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("TENANT_ID", TENANT)
    with patch(
        "exocortex.workers.output_nudges.query_one",
        return_value=None,
    ):
        count = output_nudges.run(dry_run=False)
    assert count == 0
