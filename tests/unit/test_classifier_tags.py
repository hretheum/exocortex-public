# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Unit tests for exocortex/classifier.py::_classify_tags.

Regression coverage: same root cause as work_meeting_note.py's fixed
TypeError (YAML frontmatter `tags: [meeting, 121]` parses the bare number
as int, not str) — a third, independent code path (alongside
work_meeting_note.py and scripts/extract_tags_batch.py) that assumes
meta_tags is list[str] without coercion. Surfaced in production
(thought 6214561a, AttributeError: 'int' object has no attribute 'lower')
right after deploying the first two fixes."""
from __future__ import annotations

from unittest.mock import patch

from exocortex.classifier import ProjectsConfig, _classify_tags, _log_unmapped


def _cfg():
    return ProjectsConfig(
        clients=[],
        person_tags={"kzielinski": {"person_slug": "gabi"}},
        type_tags={"121"},
    )


def test_classify_tags_coerces_non_string_tags():
    person_tags, type_tags = _classify_tags(["kzielinski", 121], _cfg())
    assert person_tags == ["gabi"]
    assert type_tags == ["121"]


def test_classify_tags_string_tags_unaffected():
    person_tags, type_tags = _classify_tags(["kzielinski", "121"], _cfg())
    assert person_tags == ["gabi"]
    assert type_tags == ["121"]


def test_log_unmapped_coerces_non_string_tags(tmp_path):
    """_log_unmapped receives the same raw meta_tags as _classify_tags —
    same crash class ('\\t'.join(tags) on a non-string tag)."""
    discovery_dir = tmp_path / "discovery"
    tsv_path = discovery_dir / "unmapped_slugs.tsv"
    with patch("exocortex.classifier.DISCOVERY_DIR", discovery_dir), \
         patch("exocortex.classifier.UNMAPPED_TSV", tsv_path), \
         patch("exocortex.classifier._unmapped_seen", set()):
        _log_unmapped(meeting_id="m1", slug="s1", title="T",
                      tags=["meeting", 121])
    assert "meeting,121" in tsv_path.read_text()
