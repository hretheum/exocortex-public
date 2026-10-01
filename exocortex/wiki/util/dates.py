# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.
"""Date and string utility functions for wiki compilation."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional


def _iso_week_bounds(today: Optional[Any] = None) -> tuple[str, str]:
    """ISO week boundaries (Monday → Sunday) as YYYY-MM-DD strings."""
    if today is None:
        today = date.today()
    elif isinstance(today, datetime):
        today = today.date()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday.isoformat(), sunday.isoformat()


def _iso_month_bounds(today: Optional[Any] = None) -> tuple[str, str]:
    """Current-month boundaries (1st → last day) as YYYY-MM-DD strings."""
    if today is None:
        today = date.today()
    elif isinstance(today, datetime):
        today = today.date()
    first = today.replace(day=1)
    nxt = (
        first.replace(year=today.year + 1, month=1)
        if today.month == 12
        else first.replace(month=today.month + 1)
    )
    return first.isoformat(), (nxt - timedelta(days=1)).isoformat()


def _offset_iso(iso_date: str, days: int) -> str:
    """Shift YYYY-MM-DD by ±days. Used for Tasks plugin exclusive bounds."""
    y, m, d = (int(x) for x in iso_date.split("-"))
    return (date(y, m, d) + timedelta(days=days)).isoformat()


def _strip_pl_accents(s: str) -> str:
    """Polish-aware deaccent — same map as workers.action_items._slugify."""
    import unicodedata

    from exocortex.action_items import _POLISH_MAP  # noqa: PLC0415

    s2 = s.translate(_POLISH_MAP)
    return unicodedata.normalize("NFKD", s2).encode("ascii", "ignore").decode("ascii")


def _date10(v: Any) -> str:
    """Render a date/datetime to YYYY-MM-DD; '' on falsy."""
    if not v:
        return ""
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d")
    s = str(v)
    return s[:10] if len(s) >= 10 else s
