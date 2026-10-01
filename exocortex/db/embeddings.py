# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/db/embeddings.py — embedding generation via OpenAI-compatible API.
#
# Endpoint and model are configurable via env, so a local deployment can
# compute vectors locally (bge-m3 via llama-swap, 1024d) instead of calling OpenAI:
#   OPENAI_BASE_URL=http://127.0.0.1:8080/v1   (standard OpenAI SDK variable)
#   OPENAI_API_KEY=<dummy>                      (llama-swap does not check the key)
#   EXOCORTEX_EMBEDDING_MODEL=bge-m3
# Without these variables nothing changes: OpenAI text-embedding-3-small (1536d).
# NOTE: the vector column dimension in the schema must match the model
# (migration 31 changes 1536 -> 1024 for bge-m3).

from __future__ import annotations

import logging
import os

from openai import OpenAI

EMBEDDING_MODEL = os.environ.get('EXOCORTEX_EMBEDDING_MODEL', 'text-embedding-3-small')

# Mirrors processors/vault_note.py::CHUNK_MAX_CHARS — the local embedding
# server (bge-m3 via llama-swap) rejects any single input over ~512 tokens
# with a 500 error ("increase the physical batch size"), a server-side limit
# outside this project's reach. vault_note.py already chunks around this;
# callers that don't (recipe.py, work_meeting_note.py, model_3d.py via
# emit_thought_for_source) would otherwise silently lose the embedding on any
# long body — truncating here protects every caller uniformly.
EMBEDDING_MAX_CHARS = 900

_openai: OpenAI | None = None


def _get_openai() -> OpenAI:
    global _openai
    if _openai is None:
        _openai = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
    return _openai


def get_embedding(text: str) -> list[float] | None:
    """Generate 1536-dim embedding via text-embedding-3-small. Returns None on error."""
    text = text.strip()[:EMBEDDING_MAX_CHARS]
    if not text:
        return None
    try:
        response = _get_openai().embeddings.create(model=EMBEDDING_MODEL, input=text)
        return response.data[0].embedding
    except Exception as e:
        logging.warning('[embeddings] embedding error: %s', e)
        return None


def get_embeddings_batch(texts: list[str]) -> list[list[float] | None]:
    """Generate embeddings for a batch of texts in a single API call."""
    clean = [t.strip()[:EMBEDDING_MAX_CHARS] for t in texts]
    if not any(clean):
        return [None] * len(texts)
    try:
        response = _get_openai().embeddings.create(model=EMBEDDING_MODEL, input=clean)
        embs = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
        return [e if clean[i] else None for i, e in enumerate(embs)]
    except Exception as e:
        logging.warning('[embeddings] batch embedding error: %s', e)
        return [None] * len(texts)
