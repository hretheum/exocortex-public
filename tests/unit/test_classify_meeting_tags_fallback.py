# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Unit tests for exocortex/classifier.py::classify_meeting — step 4
("Fireflies tags fallback"). Sixth independent instance of the same root
cause (YAML frontmatter tags containing a bare int) found by sweeping the
codebase for every `.lower()` call reachable from raw metadata.tags."""
from __future__ import annotations

from exocortex.classifier import Client, ProjectsConfig, classify_meeting


def _cfg():
    return ProjectsConfig(
        clients=[Client(slug="acme", display_name="Acme")],
        person_tags={},
        type_tags=set(),
    )


def test_classify_meeting_tags_fallback_coerces_non_string_tags():
    thought = {"metadata": {"tags": [999, "acme"]}}
    cls = classify_meeting(thought, _cfg())
    assert cls.client == "acme"
    assert cls.source == "tags"
