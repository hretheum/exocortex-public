# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Unit tests for exocortex/wiki/domains/work/__init__.py::_parse_meeting.

Regression coverage: same root cause as work_meeting_note.py's fixed
TypeError (YAML frontmatter `tags: [meeting, 121]` parses the bare number
as int, not str) — a fourth independent code path. Confirmed live in
production right after deploying the first three fixes:
[wiki_compiler] ERROR: work module failed:
AttributeError("'int' object has no attribute 'lower'")
"""
from __future__ import annotations

import os
from unittest.mock import patch

os.environ.setdefault("TENANT_ID", "test-tenant")

from exocortex.classifier import Classification, ProjectsConfig
from exocortex.wiki.domains.work import _parse_meeting


def _row():
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "created_at": "2026-07-29T10:00:00",
        "body": "Meeting: Gabi 1:1 biweekly\nDate: 2026-07-29",
        "metadata": {"tags": ["meeting", 121], "participants": []},
    }


def test_parse_meeting_coerces_non_string_tags_when_no_client_match():
    """cls.client is falsy -> hits the `t.lower() in client_slugs` branch."""
    cfg = ProjectsConfig(clients=[], person_tags={}, type_tags=set())
    with patch("exocortex.wiki.domains.work._load_projects_cfg", return_value=cfg), \
         patch("exocortex.wiki.domains.work.classify_meeting",
               return_value=Classification(client=None)):
        meeting = _parse_meeting(_row())
    assert meeting["projects"] == []


def test_parse_meeting_stores_tags_as_strings_for_downstream_consumers():
    """The meeting dict's own "tags" key is re-consumed later by
    _write_by_tag_pages (work/__init__.py) and wiki/domains/home — both
    call .lower() on each item directly. Coercing once here, not at every
    downstream call site, is the actual fix."""
    cfg = ProjectsConfig(clients=[], person_tags={}, type_tags=set())
    with patch("exocortex.wiki.domains.work._load_projects_cfg", return_value=cfg), \
         patch("exocortex.wiki.domains.work.classify_meeting",
               return_value=Classification(client=None)):
        meeting = _parse_meeting(_row())
    assert meeting["tags"] == ["meeting", "121"]
    assert all(isinstance(t, str) for t in meeting["tags"])
