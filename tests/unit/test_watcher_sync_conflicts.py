# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Syncthing conflict copies must never be ingested as separate notes.

When two machines edit the same note, Syncthing keeps the loser as
`<name>.sync-conflict-<date>-<device>.md` next to the original. The watcher
matched those with its `*.md` include pattern, so six of them had been
captured as if they were distinct meetings (2026-08-03). They are not new
content — they are a second copy of a note that already exists.
"""
from __future__ import annotations

import pytest

from exocortex.vault_watcher import is_sync_conflict


@pytest.mark.parametrize('name', [
    '2026-05-20-wks-wonkabank.sync-conflict-20260520-204220-N25SQ2Y.md',
    'notatka.sync-conflict-20260101-000000-ABCDEFG.md',
])
def test_conflict_copies_are_recognised(name):
    assert is_sync_conflict(name) is True


@pytest.mark.parametrize('name', [
    '2026-05-20-wks-wonkabank.md',
    'zwykla-notatka.md',
    'sync-conflict-w-tytule-ale-nie-kopia.md',
    'o-konfliktach-synchronizacji.md',
])
def test_ordinary_notes_are_not_touched(name):
    assert is_sync_conflict(name) is False
