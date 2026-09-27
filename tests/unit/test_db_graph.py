# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Unit tests for exocortex/db/graph.py::_age_label.

Regression coverage: 'ingredient' (recipe.py) was missing from _AGE_LABEL,
crashing every recipe-ingredient edge insert with ValueError. A prior commit
(f2362ca) already flagged this exact class of gap for 'client'/'email_thread'/
'material' (and an even earlier one for 'project') — this test enumerates
every entity_type actually passed as `dst_type` in production code so a
future addition can't silently repeat the pattern.
"""
from __future__ import annotations

import os

os.environ.setdefault("TENANT_ID", "test-tenant")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

import pytest

from exocortex.db.graph import _age_label

# Every entity_type literal passed as the 3rd arg to _upsert_entity() that is
# ALSO reused as `dst_type` in the matching _insert_edge() call — i.e. types
# that get their own AGE node label instead of falling back to the generic
# 'entity' (which newsletter.py's topic/newsletter entities use instead).
KNOWN_ENTITY_DST_TYPES = ["project", "person", "client", "material", "ingredient"]

# Table-level src_type/dst_type literals used directly (db/ingest.py,
# cross_domain_matcher.py) — same class of gap as KNOWN_ENTITY_DST_TYPES,
# just for first-class tables instead of entities sub-types. 'synthesis' was
# missing (exocortex.synthesizer edge emit error, surfaced once the K12
# GPU/llama-swap outage was fixed and synth could finally reach this code).
KNOWN_TABLE_NODE_TYPES = ["thought", "raw_source", "synthesis"]


@pytest.mark.parametrize("node_type", KNOWN_ENTITY_DST_TYPES + KNOWN_TABLE_NODE_TYPES)
def test_age_label_covers_every_entity_dst_type_in_use(node_type):
    """Every entity_type actually used as dst_type in production code must
    resolve without raising — this is the exact bug class that crashed
    recipe.py's ingredient edges (ValueError: Invalid AGE node type)."""
    assert _age_label(node_type)


def test_age_label_rejects_unknown_lowercase_type():
    with pytest.raises(ValueError):
        _age_label("not_a_real_type")


def test_age_label_accepts_camelcase_fallback():
    assert _age_label("SomeNewLabel") == "SomeNewLabel"
