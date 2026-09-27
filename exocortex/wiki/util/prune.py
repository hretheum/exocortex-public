# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.
"""Shared decision logic for deleting pages the compiler no longer expects.

Kept separate from any one domain because this is the only part of the wiki
compiler that DELETES user-visible files, and it is worth testing on its own.
Pruning is driven by the database rather than by "what this run happened to
write", so it behaves the same under an incremental (`--since`) compile as
under a full one.
"""

from __future__ import annotations

from pathlib import Path

# Deleting more than this share of a directory means the inputs are wrong, not
# that the directory is that stale — refuse rather than wipe it. Small absolute
# counts are always allowed so tiny directories aren't blocked by the ratio.
_PRUNE_MAX_SHARE = 0.4
_PRUNE_ALWAYS_OK = 10


def _select_orphans(
    files_by_name: dict,
    expected_by_key: dict,
    *,
    orphan_when_record_gone: bool = True,
) -> list:
    """Names to delete, given on-disk files and the DB's expected filenames.

    `files_by_name` maps filename → the key identifying its record;
    `expected_by_key` maps that key → the filename it should have now. A file
    is an orphan when the record has a different expected name **that already
    exists on disk** — that condition keeps an incremental compile from
    deleting a page before its replacement has been written.

    `orphan_when_record_gone` decides the other case: a file whose record is
    absent from the database. For pages the database can always regenerate
    that means stale, and deleting is right. It is NOT right where the page
    outlives its record — meeting pages older than ~May 2026 have no thought
    left in the database at all (267 of 453 when this was written), so there
    the page is the only surviving copy of a meeting that really happened.
    """
    orphans = []
    for name, key in files_by_name.items():
        want = expected_by_key.get(key)
        if want is None:
            if orphan_when_record_gone:
                orphans.append(name)
        elif want != name and want in files_by_name:
            orphans.append(name)
    return orphans


def _prune_is_plausible(*, n_delete: int, n_total: int) -> bool:
    """Guard against a bad query wiping a directory."""
    if n_delete <= _PRUNE_ALWAYS_OK:
        return True
    return n_delete / n_total <= _PRUNE_MAX_SHARE if n_total else False


def has_user_state(path: Path) -> bool:
    """True if the page holds something the user typed that the DB does not.

    Meeting pages carry action items the user ticks off by hand; the compiler
    merges those `[x]` marks forward from the existing file on every rebuild
    (`_merge_user_done_state`, guarded by an explicit DO-NOT-BYPASS comment).
    A renamed meeting therefore leaves its ticks behind in the orphan, which
    is then the ONLY copy — deleting it would destroy them. Such a file is
    reported for a human instead of being pruned.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.lstrip().startswith(("- [x]", "* [x]", "- [X]", "* [X]")):
                    return True
    except OSError:
        # Unreadable means "do not touch", not "safe to delete".
        return True
    return False
