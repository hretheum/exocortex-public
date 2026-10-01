# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.
"""Slug and email utility functions for wiki filenames."""

from __future__ import annotations

import re
import unicodedata

# Polish-letter transliteration so diacritics survive as ASCII instead of
# being dropped by the ASCII-only slug regex (o-acute/l-stroke etc. would otherwise
# vanish along with the hyphen meant to replace them, e.g. "maslem" spelled with l-stroke -> "mas-em").
_POLISH_MAP = str.maketrans({
    'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n',
    'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z',
})


def _slug_component(s: str) -> str:
    """Lowercase, transliterate Polish diacritics, kebab-case. No length cap."""
    s = (s or "").strip().lower()
    s = s.translate(_POLISH_MAP)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _safe_slug(s: str) -> str:
    """Lowercase-kebab slug for filenames, capped at 60 chars (mirrors
    _news_slug) so a long scraped title can't blow past filesystem filename
    limits (OSError(36, 'File name too long') on a 459-char recipe title
    pulled verbatim from an Instagram caption). Returns empty string for
    empty input."""
    return _slug_component(s)[:60].rstrip("-")


def _news_slug(s: str) -> str:
    """Lowercase-kebab slug, ASCII-only, max 60 chars. Mirrors processor logic."""
    return _slug_component(s)[:60] or "unknown"


def _re_extract(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text or "", re.MULTILINE)
    return m.group(1).strip() if m else None


def _slug_from_email(email: str | None) -> str:
    """p.wilk@example.com -> wilk-p ; john@example.com -> john."""
    if not email or "@" not in email:
        return "unknown"
    local = email.split("@", 1)[0].lower()
    parts = [p for p in re.split(r"[._\-]+", local) if p]
    if len(parts) >= 2:
        first = parts[0]
        last = parts[-1]
        first_initial = first if len(first) == 1 else first[0]
        slug = f"{last}-{first_initial}"
    elif parts:
        slug = parts[0]
    else:
        return "unknown"
    slug = re.sub(r"[^a-z0-9\-]+", "-", slug).strip("-")
    return slug or "unknown"


def _display_from_email(email: str | None) -> str:
    """p.wilk@example.com -> 'P. Wilk' ; john@example.com -> 'John'."""
    if not email or "@" not in email:
        return email or "Unknown"
    local = email.split("@", 1)[0]
    parts = [p for p in re.split(r"[._\-]+", local) if p]
    if len(parts) >= 2:
        first = parts[0]
        last = parts[-1].capitalize()
        prefix = f"{first[0].upper()}." if len(first) == 1 else first.capitalize()
        return f"{prefix} {last}"
    return parts[0].capitalize() if parts else email
