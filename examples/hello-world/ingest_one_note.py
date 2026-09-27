#!/usr/bin/env python3
# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31.9.4 — Ingest a single note into Exocortex.

Reads ``note.md`` from this directory, POSTs it to the capture API as a
``quick-note`` source, then inserts the corresponding ``thoughts`` row with
an OpenAI embedding so the GraphRAG retriever can find it.

The shortcut (inline thought insert) exists because the default
``docker-compose.yml`` stack does not run the F6.3 scorer daemon — and
even if it did, ``quick-note`` is deferred routing.  For the 5-minute
quickstart we want a deterministic ingest path; production setups would
run a processor or the Claude Routine 09:00 picker.

Usage::

    python examples/hello-world/ingest_one_note.py
    # → ✓ thought_id=<uuid> ingested with embedding
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

try:
    import httpx
except ImportError:
    sys.exit("Missing dependency: pip install httpx  (or: pip install -e .)")

from exocortex.db import conn
from exocortex.db.embeddings import get_embedding
from exocortex.settings import get_tenant_id

NOTE_PATH = Path(__file__).resolve().parent / "note.md"
CAPTURE_URL = os.environ.get("CAPTURE_URL", "http://localhost:8000/capture")
CAPTURE_API_TOKEN = os.environ.get("CAPTURE_API_TOKEN", "dev-token")


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body_markdown). Empty dict if no frontmatter."""
    if not text.startswith("---\n"):
        return {}, text
    try:
        _, fm_raw, body = text.split("---\n", 2)
    except ValueError:
        return {}, text
    # tiny YAML subset — enough for the title/date/type pairs we care about
    fm: dict = {}
    for line in fm_raw.splitlines():
        if ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm, body.lstrip("\n")


def main() -> int:
    if not NOTE_PATH.exists():
        print(f"note not found: {NOTE_PATH}", file=sys.stderr)
        return 1

    raw = NOTE_PATH.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(raw)
    title = frontmatter.get("title") or "Hello-world note"

    # 1. Register in raw_sources via capture API (canonical Pattern A entry).
    payload = {
        "source_type": "quick-note",
        "uri": f"file://{NOTE_PATH}",
        "title": title,
        "raw_payload": body,
        "metadata": {"example": "hello-world", **frontmatter},
    }
    headers = {}
    if CAPTURE_API_TOKEN:
        headers["Authorization"] = f"Bearer {CAPTURE_API_TOKEN}"

    resp = httpx.post(CAPTURE_URL, json=payload, headers=headers, timeout=10.0)
    if resp.status_code not in (200, 201):
        print(f"capture API failed: {resp.status_code} {resp.text}", file=sys.stderr)
        return 2
    source_id = resp.json()["source_id"]
    print(f"  raw_sources row: {source_id}")

    # 2. Generate embedding (requires OPENAI_API_KEY).
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set — cannot embed the note.", file=sys.stderr)
        return 3
    embedding = get_embedding(body)
    if embedding is None:
        print("embedding generation failed (check OPENAI_API_KEY)", file=sys.stderr)
        return 4

    # 3. Insert thought + acquired_from edge to raw_sources.
    tenant_id = get_tenant_id()
    embedding_literal = "[" + ",".join(repr(float(x)) for x in embedding) + "]"
    metadata = {"title": title, "example": "hello-world", **frontmatter}
    with conn() as c:
        existing = c.execute(
            "SELECT id FROM thoughts WHERE tenant_id = %s AND source_id = %s",
            (tenant_id, source_id),
        ).fetchone()
        if existing:
            thought_id = str(existing["id"])
            print(f"  thought already exists: {thought_id} (re-run idempotent)")
        else:
            row = c.execute(
                """
                INSERT INTO thoughts (tenant_id, source_id, body, thought_type,
                                       author, metadata, embedding)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
                RETURNING id
                """,
                (
                    tenant_id,
                    source_id,
                    body,
                    "quick_note",
                    "agent:hello-world-example",
                    json.dumps(metadata),
                    embedding_literal,
                ),
            ).fetchone()
            thought_id = str(row["id"])
            c.execute(
                """
                INSERT INTO edges (tenant_id, src_id, src_type, dst_id, dst_type,
                                    type, created_by)
                VALUES (%s, %s, 'thought', %s, 'raw_source', 'acquired_from',
                        'hello-world-example')
                """,
                (tenant_id, thought_id, source_id),
            )

    print(f"✓ thought_id={thought_id} ingested with embedding")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
