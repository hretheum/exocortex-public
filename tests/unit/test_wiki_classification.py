# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Unit tests for exocortex/wiki/util/classification.py::_classify_type.

Fifth independent instance of the same root cause (YAML frontmatter
`tags: [meeting, 121]` parses the bare number as int, not str) — found by
running the test for _parse_meeting (wiki/domains/work/__init__.py) one
level deeper into the same call chain."""
from __future__ import annotations

from unittest.mock import patch

from exocortex.classifier import ProjectsConfig
from exocortex.wiki.util.classification import _classify_type, _meeting_slug


def _cfg():
    return ProjectsConfig(clients=[], person_tags={}, type_tags={"121"})


def test_classify_type_coerces_non_string_tags():
    with patch("exocortex.wiki.util.classification._load_projects_cfg",
               return_value=_cfg()):
        assert _classify_type(["meeting", 121], "Gabi 1:1 biweekly") == "121"


def test_classify_type_falls_back_to_title_1on1_detection():
    with patch("exocortex.wiki.util.classification._load_projects_cfg",
               return_value=_cfg()):
        assert _classify_type(["meeting"], "Weekly sync") == "1on1"


def test_meeting_slug_transliterates_polish_diacritics():
    """Same root cause as _safe_slug: ASCII-only regex dropped ó/ł/ś instead
    of transliterating them, e.g. 'Michał' -> 'micha-' not 'michal'."""
    slug = _meeting_slug("2026-08-03", "Rozmowa z Michałem o wdrożeniu", "abcd1234")
    assert "michalem" in slug
    assert "micha-" not in slug
