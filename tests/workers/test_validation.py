"""Tests for flip_human_validated (F31.3.5)."""

from __future__ import annotations

import time
from pathlib import Path


from exocortex.workers.validation import flip_human_validated


def _write(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


FRONTMATTER_FALSE = """---
title: Test note
provenance: ai_authored
provenance_metadata:
  agent: claude-opus-4.7
  human_validated: false
---

## Body

Some content.
"""

FRONTMATTER_TRUE = """---
title: Test note
provenance: ai_authored
provenance_metadata:
  agent: claude-opus-4.7
  human_validated: true
---

## Body

Some content.
"""

FRONTMATTER_NONE = """---
title: Test note
provenance: human
---

## Body

Plain note.
"""

WITH_CHECKBOXES = """---
title: Task page
provenance_metadata:
  human_validated: false
---

## Tasks

- [x] task done
- [x] another done
- [ ] pending
"""


def test_flip_false_to_true(tmp_path: Path) -> None:
    f = tmp_path / "note.md"
    _write(f, FRONTMATTER_FALSE)

    result = flip_human_validated(f, True)

    assert result == {"changed": True}
    content = f.read_text(encoding="utf-8")
    assert "human_validated: true" in content
    assert "human_validated: false" not in content


def test_flip_true_to_true_noop(tmp_path: Path) -> None:
    f = tmp_path / "note.md"
    _write(f, FRONTMATTER_TRUE)

    mtime_before = f.stat().st_mtime_ns
    # Sleep beyond filesystem mtime resolution to detect any accidental write.
    time.sleep(0.01)

    result = flip_human_validated(f, True)

    assert result == {"noop": True}
    assert f.stat().st_mtime_ns == mtime_before
    assert f.read_text(encoding="utf-8") == FRONTMATTER_TRUE


def test_missing_field_returns_error(tmp_path: Path) -> None:
    f = tmp_path / "plain.md"
    _write(f, FRONTMATTER_NONE)

    result = flip_human_validated(f, True)

    assert result == {"error": "no_field"}
    assert f.read_text(encoding="utf-8") == FRONTMATTER_NONE


def test_checkbox_count_preserved(tmp_path: Path) -> None:
    f = tmp_path / "tasks.md"
    _write(f, WITH_CHECKBOXES)
    pre_count = WITH_CHECKBOXES.count("[x]")

    result = flip_human_validated(f, True)

    assert result == {"changed": True}
    content = f.read_text(encoding="utf-8")
    assert content.count("[x]") == pre_count
    assert "human_validated: true" in content


def test_flip_true_to_false(tmp_path: Path) -> None:
    f = tmp_path / "note.md"
    _write(f, FRONTMATTER_TRUE)

    result = flip_human_validated(f, False)

    assert result == {"changed": True}
    assert "human_validated: false" in f.read_text(encoding="utf-8")
