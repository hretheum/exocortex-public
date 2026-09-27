# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""_iso_month_bounds backs the wiki 'this month' TODO view (action items from
meetings held in the current calendar month)."""
from __future__ import annotations

from datetime import date, datetime

from exocortex.wiki.util.dates import _iso_month_bounds


def test_regular_month():
    assert _iso_month_bounds(date(2026, 8, 4)) == ("2026-08-01", "2026-08-31")


def test_february_non_leap():
    assert _iso_month_bounds(date(2026, 2, 15)) == ("2026-02-01", "2026-02-28")


def test_february_leap():
    assert _iso_month_bounds(date(2024, 2, 10)) == ("2024-02-01", "2024-02-29")


def test_december_wraps_year():
    assert _iso_month_bounds(date(2026, 12, 31)) == ("2026-12-01", "2026-12-31")


def test_accepts_datetime():
    assert _iso_month_bounds(datetime(2026, 8, 4, 13, 30)) == (
        "2026-08-01",
        "2026-08-31",
    )
