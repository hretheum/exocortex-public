# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Unit tests for exocortex/workers/ingest.py::build_body.

Same root cause and fix as exocortex/processors/work_meeting_note.py's
build_body (identical duplicated logic, a separate live entry point used
by `exocortex ingest`/scripts/bulk_ingest_vault.py) — YAML frontmatter
`tags: [meeting, 121]` parses the bare number as int, not str."""
from __future__ import annotations

import os

os.environ.setdefault("TENANT_ID", "test-tenant")
os.environ.setdefault("EXOCORTEX_VAULT_PATH", "/tmp")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

from exocortex.workers.ingest import build_body


def test_build_body_coerces_non_string_tags():
    body = build_body({"tags": ["meeting", 121]}, "Title", {})
    assert "Tags: meeting, 121" in body


def test_build_body_coerces_non_string_participants():
    body = build_body({}, "Title", {}, participants=["owner@example.com", 121])
    assert "Participants: owner@example.com, 121" in body
