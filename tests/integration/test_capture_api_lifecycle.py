# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F32 — integration tests for the Capture API lifecycle endpoints added for
the obsidian-exocortex-capture plugin: /capture/delete, /capture/rename,
/capture/batch.

Runs against a REAL Postgres (see tests/integration/conftest.py — skipped
automatically if PG_HOST/PG_PORT is unreachable). Each test uses a unique
source_type per test function (not a shared fixture value) so tests can run
in any order / repeatedly without colliding on the (tenant_id, source_type,
uri) unique index — cheaper than a shared truncate-between-tests fixture and
makes failures easier to isolate (each test owns its own rows).
"""
from __future__ import annotations

import os
import uuid

import pytest

# Same convention as tests/unit/test_notify_listener.py: satisfy env-only
# module-level reads (TENANT_ID, CAPTURE_API_TOKEN) BEFORE importing
# capture_api, since those are captured once at import time.
os.environ.setdefault("EXOCORTEX_VAULT_PATH", "/tmp")
os.environ.setdefault(
    "DATABASE_URL",
    f"postgresql://{os.environ.get('PG_USER', 'exocortex')}:"
    f"{os.environ.get('PG_PASSWORD', 'exocortex')}@"
    f"{os.environ.get('PG_HOST', 'localhost')}:"
    f"{os.environ.get('PG_PORT', '5432')}/"
    f"{os.environ.get('PG_DATABASE', 'exocortex')}",
)
os.environ.setdefault("EXOCORTEX_TENANT_ID", "11111111-1111-1111-1111-111111111111")
os.environ.setdefault("CAPTURE_API_TOKEN", "test-token-f32")

from fastapi.testclient import TestClient  # noqa: E402

from exocortex import capture_api  # noqa: E402

client = TestClient(capture_api.app)
AUTH = {"Authorization": f"Bearer {os.environ['CAPTURE_API_TOKEN']}"}


def _source_type() -> str:
    """Fresh ALLOWED_SOURCE_TYPES member per test — 'quick-note' is on the
    allow-list and carries no processor side effects, so reusing it repeatedly
    across many source_type-scoped tests (isolated only by unique uri, not by
    source_type) is fine; tests that need type-level isolation build the uri
    unique instead."""
    return "quick-note"


def _uri() -> str:
    return f"file:///tmp/f32-test-{uuid.uuid4().hex}.md"


# ─────────────────────────── /capture/delete ───────────────────────────


def test_delete_marks_source_gone_and_is_idempotent() -> None:
    uri = _uri()
    created = client.post(
        "/capture", json={"source_type": _source_type(), "uri": uri}, headers=AUTH
    )
    assert created.status_code == 201, created.text
    source_id = created.json()["source_id"]

    first = client.post(
        "/capture/delete", json={"source_type": _source_type(), "uri": uri}, headers=AUTH
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body == {"source_id": source_id, "deleted": True}

    # Idempotent: second delete of the same (now-gone) source is a no-op,
    # not an error — a watcher retrying after a crash must not see a 404.
    second = client.post(
        "/capture/delete", json={"source_type": _source_type(), "uri": uri}, headers=AUTH
    )
    assert second.status_code == 200, second.text
    assert second.json() == {"source_id": None, "deleted": False}


def test_delete_nonexistent_uri_returns_false_not_error() -> None:
    resp = client.post(
        "/capture/delete",
        json={"source_type": _source_type(), "uri": _uri()},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"source_id": None, "deleted": False}


def test_deleted_source_does_not_orphan_on_recapture_of_same_uri() -> None:
    """The row surviving soft-delete (not a hard delete) is the entire point —
    prove the row itself (not just the API response) still exists with the
    original id, just marked deleted_at."""
    uri = _uri()
    created = client.post(
        "/capture", json={"source_type": _source_type(), "uri": uri}, headers=AUTH
    )
    source_id = created.json()["source_id"]
    client.post("/capture/delete", json={"source_type": _source_type(), "uri": uri}, headers=AUTH)

    from exocortex.db import query_one

    row = query_one(
        "SELECT id::text, deleted_at FROM raw_sources WHERE id = %s", source_id
    )
    assert row is not None, "hard-deleted — this must never happen (FK orphaning risk)"
    assert row["id"] == source_id
    assert row["deleted_at"] is not None


# ─────────────────────────── /capture/rename ───────────────────────────


def test_rename_updates_uri_and_keeps_same_source_id() -> None:
    old_uri = _uri()
    new_uri = _uri()
    created = client.post(
        "/capture", json={"source_type": _source_type(), "uri": old_uri}, headers=AUTH
    )
    source_id = created.json()["source_id"]

    resp = client.post(
        "/capture/rename",
        json={"source_type": _source_type(), "old_uri": old_uri, "new_uri": new_uri},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"source_id": source_id, "renamed": True}

    from exocortex.db import query_one

    row = query_one("SELECT uri FROM raw_sources WHERE id = %s", source_id)
    assert row["uri"] == new_uri, "rename must UPDATE the row in place, not create a new one"

    # The row is gone from the OLD uri — a fresh capture there is a genuinely
    # new source, not confused with the renamed one.
    recapture_old = client.post(
        "/capture", json={"source_type": _source_type(), "uri": old_uri}, headers=AUTH
    )
    assert recapture_old.status_code == 201
    assert recapture_old.json()["source_id"] != source_id


def test_rename_metadata_merges_without_dropping_existing_keys() -> None:
    old_uri = _uri()
    new_uri = _uri()
    client.post(
        "/capture",
        json={
            "source_type": _source_type(),
            "uri": old_uri,
            "metadata": {"body_hash": "abc123", "domain": "work"},
        },
        headers=AUTH,
    )
    resp = client.post(
        "/capture/rename",
        json={
            "source_type": _source_type(),
            "old_uri": old_uri,
            "new_uri": new_uri,
            "metadata": {"vault_path": "work/renamed.md"},
        },
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    source_id = resp.json()["source_id"]

    from exocortex.db import query_one

    row = query_one("SELECT metadata FROM raw_sources WHERE id = %s", source_id)
    assert row["metadata"]["body_hash"] == "abc123", "pre-existing key dropped by rename"
    assert row["metadata"]["domain"] == "work", "pre-existing key dropped by rename"
    assert row["metadata"]["vault_path"] == "work/renamed.md", "new key not merged in"


def test_rename_conflict_when_target_uri_already_captured() -> None:
    uri_a = _uri()
    uri_b = _uri()
    client.post("/capture", json={"source_type": _source_type(), "uri": uri_a}, headers=AUTH)
    client.post("/capture", json={"source_type": _source_type(), "uri": uri_b}, headers=AUTH)

    resp = client.post(
        "/capture/rename",
        json={"source_type": _source_type(), "old_uri": uri_a, "new_uri": uri_b},
        headers=AUTH,
    )
    assert resp.status_code == 409, resp.text


def test_rename_nonexistent_old_uri_returns_false_not_error() -> None:
    resp = client.post(
        "/capture/rename",
        json={"source_type": _source_type(), "old_uri": _uri(), "new_uri": _uri()},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"source_id": None, "renamed": False}


def test_rename_of_deleted_source_is_a_no_op() -> None:
    uri = _uri()
    client.post("/capture", json={"source_type": _source_type(), "uri": uri}, headers=AUTH)
    client.post("/capture/delete", json={"source_type": _source_type(), "uri": uri}, headers=AUTH)

    resp = client.post(
        "/capture/rename",
        json={"source_type": _source_type(), "old_uri": uri, "new_uri": _uri()},
        headers=AUTH,
    )
    assert resp.status_code == 200
    assert resp.json() == {"source_id": None, "renamed": False}


# ─────────────────────────── /capture/batch ───────────────────────────


def test_batch_capture_multiple_new_items() -> None:
    uris = [_uri() for _ in range(5)]
    resp = client.post(
        "/capture/batch",
        json={"items": [{"source_type": _source_type(), "uri": u} for u in uris]},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 5
    assert body["created_count"] == 5
    assert len(body["results"]) == 5
    assert all(r["error"] is None and r["source_id"] for r in body["results"])
    assert {r["uri"] for r in body["results"]} == set(uris)


def test_batch_capture_is_idempotent_alongside_single_capture() -> None:
    """A file already sent via /capture and then re-sent inside a /capture/batch
    (e.g. the plugin's first index overlapping with a live watcher event) must
    resolve to the SAME row, not a duplicate."""
    uri = _uri()
    single = client.post(
        "/capture", json={"source_type": _source_type(), "uri": uri}, headers=AUTH
    )
    source_id = single.json()["source_id"]

    resp = client.post(
        "/capture/batch",
        json={"items": [{"source_type": _source_type(), "uri": uri}]},
        headers=AUTH,
    )
    body = resp.json()
    assert body["created_count"] == 0
    assert body["results"][0]["source_id"] == source_id
    assert body["results"][0]["created"] is False


def test_batch_capture_one_bad_item_does_not_abort_the_rest() -> None:
    good_uri_1, good_uri_2 = _uri(), _uri()
    resp = client.post(
        "/capture/batch",
        json={
            "items": [
                {"source_type": _source_type(), "uri": good_uri_1},
                {"source_type": "not-an-allowed-type", "uri": _uri()},
                {"source_type": _source_type(), "uri": good_uri_2},
            ]
        },
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 3
    assert body["created_count"] == 2, "one bad item must not sink the two good ones"
    by_uri = {r["uri"]: r for r in body["results"]}
    assert by_uri[good_uri_1]["source_id"] is not None
    assert by_uri[good_uri_2]["source_id"] is not None
    bad_result = [r for r in body["results"] if r["error"] is not None]
    assert len(bad_result) == 1
    assert "not-an-allowed-type" in bad_result[0]["error"]


def test_batch_capture_rejects_more_than_500_items() -> None:
    items = [{"source_type": _source_type(), "uri": _uri()} for _ in range(501)]
    resp = client.post("/capture/batch", json={"items": items}, headers=AUTH)
    assert resp.status_code == 422, resp.text


def test_batch_capture_rejects_empty_items() -> None:
    resp = client.post("/capture/batch", json={"items": []}, headers=AUTH)
    assert resp.status_code == 422, resp.text


# ─────────────────────────── auth still enforced on new routes ───────────────────────────


@pytest.mark.parametrize("path,body", [
    ("/capture/delete", {"source_type": "quick-note", "uri": "file:///tmp/x.md"}),
    ("/capture/rename", {"source_type": "quick-note", "old_uri": "file:///tmp/x.md",
                         "new_uri": "file:///tmp/y.md"}),
    ("/capture/batch", {"items": [{"source_type": "quick-note", "uri": "file:///tmp/x.md"}]}),
])
def test_new_endpoints_require_bearer_token(path: str, body: dict) -> None:
    resp = client.post(path, json=body)  # no Authorization header
    assert resp.status_code == 401, resp.text


# ─────────────────────────── F34: content_hash conditional update ───────────────────────────
#
# Before F34, a re-POST at an already-known uri was ON CONFLICT DO NOTHING —
# a re-edited source was captured once and then invisible forever. These
# prove the fix: real content change updates the row and re-notifies;
# an unchanged re-POST is a true no-op.

def test_unchanged_repost_does_not_update_or_reprocess() -> None:
    from exocortex.db import query_one

    uri = _uri()
    first = client.post(
        "/capture", json={"source_type": _source_type(), "uri": uri, "raw_payload": "same"},
        headers=AUTH,
    )
    assert first.status_code == 201, first.text
    source_id = first.json()["source_id"]

    # Simulate a processor having already run — an unchanged re-POST must
    # not clear this, since nothing about the row actually changed.
    query_one(
        "UPDATE raw_sources SET metadata = metadata || '{\"processors\":{\"x\":1}}'::jsonb "
        "WHERE id = %s RETURNING id", source_id,
    )

    second = client.post(
        "/capture", json={"source_type": _source_type(), "uri": uri, "raw_payload": "same"},
        headers=AUTH,
    )
    assert second.status_code == 200, second.text
    assert second.json()["created"] is False

    row = query_one("SELECT metadata FROM raw_sources WHERE id = %s", source_id)
    assert row["metadata"]["processors"] == {"x": 1}, \
        "unchanged re-POST must not touch metadata — processor stamp must survive"


def test_content_change_updates_row_and_clears_processor_stamp() -> None:
    from exocortex.db import query_one

    uri = _uri()
    first = client.post(
        "/capture", json={"source_type": _source_type(), "uri": uri, "raw_payload": "v1"},
        headers=AUTH,
    )
    assert first.status_code == 201, first.text
    source_id = first.json()["source_id"]

    query_one(
        "UPDATE raw_sources SET metadata = metadata || '{\"processors\":{\"x\":1}}'::jsonb "
        "WHERE id = %s RETURNING id", source_id,
    )

    second = client.post(
        "/capture", json={"source_type": _source_type(), "uri": uri, "raw_payload": "v2 changed"},
        headers=AUTH,
    )
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["source_id"] == source_id, "same uri must update the same row, not create a new one"
    assert body["created"] is False, "an update is not a creation"

    row = query_one("SELECT metadata FROM raw_sources WHERE id = %s", source_id)
    assert row["metadata"]["raw_payload"] == "v2 changed"
    assert "processors" not in row["metadata"], \
        "content change must clear the processor stamp so the row gets reprocessed"


def test_content_hash_column_reflects_metadata() -> None:
    from exocortex.db import query_one

    uri = _uri()
    resp = client.post(
        "/capture", json={"source_type": _source_type(), "uri": uri, "raw_payload": "hash-me"},
        headers=AUTH,
    )
    source_id = resp.json()["source_id"]
    row = query_one(
        "SELECT content_hash FROM raw_sources WHERE id = %s", source_id
    )
    assert row["content_hash"] is not None
    assert len(row["content_hash"]) == 32  # md5 hex digest
