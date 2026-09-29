# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Radar channel items become allowlisted sources and signal nodes (F5.2)."""
from __future__ import annotations

import uuid

import pytest

from exocortex.lab import signals
from tests.lab.conftest import ROOT, needs_engine

pytestmark = needs_engine


def test_items_become_sources_and_nodes_through_the_allowlist(conn, tenant, monkeypatch):
    from exocortex.source_allowlist import SourceNotAllowed

    monkeypatch.setenv("EXOCORTEX_SOURCE_ALLOWLIST", str(ROOT / "lab" / "sources.yaml"))
    tag = uuid.uuid4().hex[:8]
    items = [signals.Item("models", "hf-model", f"https://huggingface.co/org/m-{tag}", f"org/m-{tag}", "body", "2026-09-20",
                          {"license": "mit"}),
             signals.Item("tools", "tool-release", f"https://api.github.com/repos/a/b/releases/tags/{tag}", "a/b v1", "b",
                          "2026-09-21",
                          {})]
    counts = signals.ingest(conn, tenant, items, embed=lambda texts: [[0.5] * 1024 for _ in texts])
    assert counts == {"models": {"items": 1, "new": 1}, "tools": {"items": 1, "new": 1}}
    assert signals.ingest(conn, tenant, items)["models"]["new"] == 0
    row = conn.execute("SELECT metadata FROM thoughts WHERE thought_type = 'signal' AND metadata->>'uri' = %s",
                       (items[0].uri,)).fetchone()
    assert row["metadata"]["license"] == "mit" and row["metadata"]["channel"] == "models"
    with pytest.raises(SourceNotAllowed):
        signals.ingest(conn, tenant, [signals.Item("x", "email", "mailto:someone@example.com", "t", "b")])
