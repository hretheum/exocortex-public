# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Shared TypedDict shapes for cross-module data contracts.

These are structural contracts only — no ORM, no business logic. Modules that
currently return plain ``dict`` can optionally adopt these for better type
safety and IDE autocompletion.
"""

from __future__ import annotations

from typing import NotRequired, TypedDict


class EntityDict(TypedDict):
    """Returned by _fetch_entities_by_ids / entity lookups."""
    id: str
    canonical_name: str
    type: str
    created_at: NotRequired[str]
    updated_at: NotRequired[str]


class SynthesisDict(TypedDict):
    """Returned by _fetch_syntheses_by_ids."""
    id: str
    perspective_type: str
    perspective_key: str
    content: str
    status: str
    version: NotRequired[int]
    created_at: NotRequired[str]
    superseded_by: NotRequired[str | None]


class ThoughtPayload(TypedDict):
    """Shape returned by _thought_to_payload for MCP tools."""
    id: str
    body: NotRequired[str]
    title: NotRequired[str]
    slug: NotRequired[str]
    thought_type: NotRequired[str]
    source_type: NotRequired[str]
    metadata: NotRequired[dict]
    created_at: NotRequired[str]


class LegacyUsageDict(TypedDict):
    """Usage dict constructed by call_llm / call_tool for LLM router responses."""
    input_tokens: int
    output_tokens: int
    _provider: str
    _model: str
    _cost_usd: float
    _finish_reason: NotRequired[str]
    _cached_input_tokens: NotRequired[int]
