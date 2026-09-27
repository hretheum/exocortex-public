# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# llm_utils.py — Shared utilities for LLM cost estimation and metadata extraction.
# Extracted from synthesizer.py, _common.py, mcp_server.py, graph_rag.py (F31-CLN-01).

from __future__ import annotations


def estimate_cost_usd(usage: dict) -> float:
    """Router-aware cost: prefer router-computed `_cost_usd` when present,
    fallback to claude-haiku-4-5 pricing for legacy callers."""
    if '_cost_usd' in usage and usage['_cost_usd'] is not None:
        return float(usage['_cost_usd'])
    return (
        usage.get('input_tokens', 0) * 1.0 / 1_000_000
        + usage.get('output_tokens', 0) * 5.0 / 1_000_000
        + usage.get('cache_creation_input_tokens', 0) * 1.25 / 1_000_000
        + usage.get('cache_read_input_tokens', 0) * 0.10 / 1_000_000
    )


def slug_from_metadata(metadata: dict | None) -> str:
    """Derive Obsidian wikilink slug from a thought's metadata.

    Order of precedence: explicit `slug` field → `source_file` basename →
    title slugified via the F2.3 Polish-aware slugifier.
    """
    if not metadata:
        return ''
    slug = metadata.get('slug') or metadata.get('source_file') or ''
    if slug:
        return slug.rsplit('/', 1)[-1].rsplit('.', 1)[0]
    title = (metadata.get('title') or '').strip()
    if not title:
        return ''
    from exocortex.action_items import _slugify
    return _slugify(title)
