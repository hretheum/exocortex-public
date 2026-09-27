# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Provenance source-id lists ran to hundreds of entries on MOC pages and buried
the Obsidian Properties panel. Nothing reads them back, so _partition_frontmatter
collapses the list to a single _source_count."""
from __future__ import annotations

from exocortex.processors.newsletter import TOOL_SCHEMA
from exocortex.wiki.core.io import _partition_frontmatter


def test_source_ids_list_becomes_count():
    out = _partition_frontmatter({"type": "x", "source_ids": ["a", "b", "c"]})
    assert out == {"type": "x", "_source_count": 3}


def test_prefixed_source_ids_also_collapses():
    out = _partition_frontmatter({"type": "x", "_source_ids": ["a", "b"]})
    assert "_source_ids" not in out and out["_source_count"] == 2


def test_empty_source_ids_is_zero():
    out = _partition_frontmatter({"type": "x", "source_ids": []})
    assert out["_source_count"] == 0


def test_newsletter_schema_requires_industry_relevant():
    # Non-industry newsletters (D2C marketing etc.) are filtered out; the LLM
    # must always return the relevance verdict.
    schema = TOOL_SCHEMA["input_schema"]
    assert "industry_relevant" in schema["required"]
    assert schema["properties"]["industry_relevant"]["type"] == "boolean"
