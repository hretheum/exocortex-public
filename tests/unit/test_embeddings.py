# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Unit tests for exocortex/db/embeddings.py.

Regression coverage: the local embedding server (bge-m3 via llama-swap)
rejects any single input over ~512 tokens with a 500 error ("increase the
physical batch size") — a server-side limit outside this project's reach
(same constraint processors/vault_note.py already works around by chunking
before embedding). Callers that go through the shared
processors/_common.py::emit_thought_for_source path (recipe.py,
work_meeting_note.py, model_3d.py) don't chunk — a long recipe/meeting body
silently lost its embedding (get_embedding swallows the exception, logs a
WARNING, returns None). Surfaced in production (42 occurrences in one
backfill run) once the K12 GPU/llama-swap outage was fixed and requests
started reaching the embedding endpoint at all.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from exocortex.db import embeddings


def _fake_client(embedding_dims=3):
    client = MagicMock()
    resp = MagicMock()
    resp.data = [MagicMock(embedding=[0.1] * embedding_dims, index=0)]
    client.embeddings.create.return_value = resp
    return client, resp


def test_get_embedding_truncates_long_input():
    client, _ = _fake_client()
    with patch("exocortex.db.embeddings._get_openai", return_value=client):
        embeddings.get_embedding("x" * 5000)
    sent = client.embeddings.create.call_args.kwargs["input"]
    assert len(sent) <= embeddings.EMBEDDING_MAX_CHARS


def test_get_embedding_short_input_unaffected():
    client, _ = _fake_client()
    with patch("exocortex.db.embeddings._get_openai", return_value=client):
        embeddings.get_embedding("short recipe body")
    sent = client.embeddings.create.call_args.kwargs["input"]
    assert sent == "short recipe body"


def test_get_embeddings_batch_truncates_every_item():
    client, resp = _fake_client()
    resp.data = [
        MagicMock(embedding=[0.1], index=0),
        MagicMock(embedding=[0.2], index=1),
    ]
    with patch("exocortex.db.embeddings._get_openai", return_value=client):
        embeddings.get_embeddings_batch(["a" * 5000, "short"])
    sent = client.embeddings.create.call_args.kwargs["input"]
    assert all(len(t) <= embeddings.EMBEDDING_MAX_CHARS for t in sent)
    assert sent[1] == "short"


def test_get_embedding_matches_vault_note_chunk_max_chars():
    """The cap must match processors/vault_note.py::CHUNK_MAX_CHARS (900) —
    the already-validated-safe value for this exact server limit, not a new
    guess."""
    from exocortex.processors.vault_note import CHUNK_MAX_CHARS

    assert embeddings.EMBEDDING_MAX_CHARS == CHUNK_MAX_CHARS
