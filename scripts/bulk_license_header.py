#!/usr/bin/env python3
# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31.10.1 — bulk-update Python license headers to Apache 2.0 + Commons Clause.

For each .py file under exocortex/, tests/, examples/:
  - If file already contains "Apache 2.0" in its first 10 lines → skip.
  - Else if first non-shebang/encoding/docstring lines contain a "Licence: MIT"
    style banner → replace the contiguous comment block with the new header.
  - Else → insert the new header after the optional shebang line, optional
    encoding cookie, and optional module docstring.

Idempotent: re-running on a freshly updated tree is a no-op.
"""
from __future__ import annotations

import re
import sys
import tokenize
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOTS = ["exocortex", "tests", "examples", "scripts", "config"]

NEW_HEADER = (
    "# © 2026 Eryk Orłowski and Exocortex contributors.\n"
    "# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.\n"
)

SKIP_PARTS = {"__pycache__", ".egg-info"}
OLD_HEADER_RE = re.compile(r"^#.*(Licence|License): MIT")


def _iter_py_files() -> list[Path]:
    files: list[Path] = []
    for root in ROOTS:
        for path in (REPO / root).rglob("*.py"):
            if any(part in SKIP_PARTS or part.endswith(".egg-info") for part in path.parts):
                continue
            files.append(path)
    return sorted(files)


def _already_has_apache(text: str) -> bool:
    for line in text.splitlines()[:10]:
        if "Apache 2.0" in line:
            return True
    return False


def _replace_or_insert(text: str) -> str | None:
    """Return new text, or None if nothing changed."""
    if _already_has_apache(text):
        return None

    lines = text.splitlines(keepends=True)
    if not lines:
        # empty __init__.py — just drop a header in
        return NEW_HEADER + "\n"

    # Find the "header zone": optional shebang + encoding cookie. Comments
    # that look like an existing license banner belong to the OLD header
    # and should be replaced; the module docstring (if any) must stay AFTER
    # the new header.
    i = 0
    n = len(lines)

    # shebang
    if i < n and lines[i].startswith("#!"):
        i += 1
    # PEP-263 encoding cookie (only on line 1 or 2)
    if i < n and re.match(r"#.*coding[:=]", lines[i]):
        i += 1

    insert_at = i
    # If the very next line matches the old MIT banner, eat just THAT
    # line.  Some files follow the banner with a non-license comment
    # ("# workers/_bootstrap.py — ...") that must be preserved — so we
    # never greedy-eat the whole comment block.
    if i < n and OLD_HEADER_RE.match(lines[i]):
        i += 1

    # Replacement = lines[:insert_at] + NEW_HEADER + (blank if not docstring) + lines[i:]
    head = "".join(lines[:insert_at])
    tail = "".join(lines[i:])

    # If tail starts with a docstring, glue with a single blank line for
    # PEP-257 readability.  Otherwise also one blank line so the header
    # doesn't collide visually with code.
    sep = "" if tail.startswith("\n") else "\n"

    new_text = head + NEW_HEADER + sep + tail
    if new_text == text:
        return None
    return new_text


def main() -> int:
    files = _iter_py_files()
    changed: list[Path] = []
    skipped_apache = 0
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            print(f"  ! skipping non-utf8 file: {f}")
            continue
        new = _replace_or_insert(text)
        if new is None:
            if _already_has_apache(text):
                skipped_apache += 1
            continue
        f.write_text(new, encoding="utf-8")
        changed.append(f)

    print(f"scanned {len(files)} .py files")
    print(f"  - {skipped_apache} already had Apache 2.0 header (skipped)")
    print(f"  - {len(changed)} updated")
    for c in changed[:20]:
        print(f"     ✓ {c.relative_to(REPO.parent.parent)}")
    if len(changed) > 20:
        print(f"     ... and {len(changed) - 20} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
