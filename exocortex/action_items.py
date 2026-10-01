# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/action_items.py — on-demand deterministic parser for Fireflies action items.
#
# Reads metadata.action_items (raw markdown stored by scripts/bulk_ingest_vault.py)
# and yields structured ActionItem records. Pure regex, zero LLM, no DB writes.
# Used by F4 wiki_compiler synthesis and F4.4 TODO aggregates.

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from typing import Any

# ─── public types ──────────────────────────────────────────────────────────

@dataclass
class ActionItem:
    owner_slug: str
    owner_name: str
    owner_email: str | None
    owner_is_collective: bool
    content: str
    status: str  # 'open' | 'done'
    timestamp_in_meeting: str | None  # 'MM:SS' or 'HH:MM:SS'
    due_date: str | None              # 'YYYY-MM-DD'
    completion_date: str | None       # 'YYYY-MM-DD'
    inline_tags: list[str] = field(default_factory=list)
    source_thought_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ─── regex constants ───────────────────────────────────────────────────────

_HEADER_RE = re.compile(r'^###\s+(.+?)\s*$', re.MULTILINE)
_ITEM_RE = re.compile(r'^[ \t]*-[ \t]*\[(?P<box>[ xX])\][ \t]*(?P<rest>[^\n]*?)[ \t]*$', re.MULTILINE)
_TIMESTAMP_RE = re.compile(r'\((\d{1,2}:\d{2}(?::\d{2})?)\)')
_DUE_RE = re.compile(r'➕\s*(\d{4}-\d{2}-\d{2})')
_DONE_RE = re.compile(r'✅\s*(\d{4}-\d{2}-\d{2})')
_TAG_RE = re.compile(r'(?<![\w/])#([a-zA-Z][\w-]*)')
# Connectors that split a multi-name header into individuals.
# Keep them simple — header value has been pre-normalised (single spaces).
_NAME_SPLIT_RE = re.compile(r'\s+(?:i|oraz|and|&)\s+', re.IGNORECASE)

# Words whose presence in a header marks the section as a collective bucket.
# Match against deaccented lowercase header. Order matters only for clarity.
_COLLECTIVE_KEYWORDS = (
    'wszyscy', 'wszystkie', 'wszyscy uczestnicy',
    'zespol', 'caly zespol', 'cale zespoly',
    'nieprzypisane',
    'team',  # 'PMA/UX Design Team'
)

# Polish-letter transliteration for slug generation.
_POLISH_MAP = str.maketrans({
    'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n',
    'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z',
    'Ą': 'a', 'Ć': 'c', 'Ę': 'e', 'Ł': 'l', 'Ń': 'n',
    'Ó': 'o', 'Ś': 's', 'Ź': 'z', 'Ż': 'z',
})


# ─── helpers ───────────────────────────────────────────────────────────────

def _slugify(name: str) -> str:
    """Polish-aware slug: 'Adam Nowicki' -> 'adam-nowicki'."""
    if not name:
        return 'unknown'
    s = name.translate(_POLISH_MAP)
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')
    s = s.lower()
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s or 'unknown'


# ─── vault-owner identity ("me") ────────────────────────────────────────────
# Anonymized placeholders live in the public repo; the real display-name(s) are
# injected at deploy time via EXOCORTEX_OWNER_NAMES (settings.owner_names) so the
# identity never lands in git. All "is this mine?" filters (Moje TODO, home
# dashboard, live sections) resolve "me" through here — single source of truth.
_ME_PLACEHOLDER_SLUGS: tuple[str, ...] = ('vault-owner', 'exocortex_user')
_ME_PLACEHOLDER_NAMES: tuple[str, ...] = (
    'Exocortex user', 'vault-owner-name', 'vault-owner-alias',
)


@lru_cache(maxsize=8)
def _me_identity(configured_names: str) -> tuple[frozenset[str], frozenset[str]]:
    """(me_slugs, me_names) from placeholders + comma-separated configured names.

    Pure: takes the config string, never reads env/DB. `_slugify` maps each real
    name to the slug `parse_action_items` produces for it, so filters keyed on
    `owner_slug` recognize the real owner.
    """
    slugs = set(_ME_PLACEHOLDER_SLUGS)
    names = set(_ME_PLACEHOLDER_NAMES)
    for raw in (configured_names or '').split(','):
        n = raw.strip()
        if n:
            names.add(n)
            slugs.add(_slugify(n))
    return frozenset(slugs), frozenset(names)


def _configured_owner_names() -> str:
    # Defensive: a bare import context (no EXOCORTEX_VAULT_PATH etc.) must not
    # crash owner resolution — fall back to placeholders-only when Settings
    # cannot be built (tests, `python -c import`).
    try:
        from exocortex.settings import get_settings
        return get_settings().owner_names
    except Exception:
        return ""


def me_owner_slugs() -> frozenset[str]:
    """Owner slugs that count as the vault owner (placeholders + configured)."""
    return _me_identity(_configured_owner_names())[0]


def me_owner_names() -> frozenset[str]:
    """Owner display-name variants for the vault owner (placeholders + configured)."""
    return _me_identity(_configured_owner_names())[1]


def _is_collective(header: str) -> bool:
    """Return True if header denotes a group rather than an individual.

    Heuristic: deaccent + lowercase, then check for collective keyword tokens.
    Multi-name individuals (e.g. 'Jan Kowalski i Anna Nowak') do NOT
    contain any collective keyword, so they fall through to per-name splitting.
    """
    norm = header.translate(_POLISH_MAP).lower()
    norm_compact = re.sub(r'[^a-z0-9 ]+', ' ', norm)
    norm_compact = re.sub(r'\s+', ' ', norm_compact).strip()
    tokens = norm_compact.split()
    token_set = set(tokens)
    for kw in _COLLECTIVE_KEYWORDS:
        kw_tokens = kw.split()
        if len(kw_tokens) == 1 and kw_tokens[0] in token_set:
            return True
        if len(kw_tokens) > 1 and kw in norm_compact:
            return True
    return False


def _split_owners(header: str) -> list[str]:
    """Split a non-collective header into individual owner names.

    Returns a list of one or more owner names. Trims and squeezes whitespace.
    """
    cleaned = re.sub(r'\s+', ' ', header).strip()
    parts = _NAME_SPLIT_RE.split(cleaned)
    return [p.strip() for p in parts if p.strip()]


def _strip_decorations(rest: str) -> tuple[str, str | None, str | None, str | None, list[str]]:
    """Pull timestamp / due / done / tags out of the line; return clean content.

    Order of stripping does not matter — patterns do not overlap.
    Returns (content, timestamp, due_date, completion_date, tags).
    """
    timestamp = None
    due = None
    done = None
    tags: list[str] = []

    m = _TIMESTAMP_RE.search(rest)
    if m:
        timestamp = m.group(1)
        rest = rest[:m.start()] + rest[m.end():]

    m = _DUE_RE.search(rest)
    if m:
        due = m.group(1)
        rest = rest[:m.start()] + rest[m.end():]

    m = _DONE_RE.search(rest)
    if m:
        done = m.group(1)
        rest = rest[:m.start()] + rest[m.end():]

    for tm in _TAG_RE.finditer(rest):
        tags.append(tm.group(1))
    rest = _TAG_RE.sub('', rest)

    # Remove leftover priority emoji and excess whitespace.
    rest = rest.replace('🔼', '').replace('⏫', '').replace('🔽', '')
    content = re.sub(r'\s+', ' ', rest).strip(' \t-•·,;:')
    return content, timestamp, due, done, tags


# ─── public API ────────────────────────────────────────────────────────────

def parse_action_items(
    metadata: dict | str | None,
    *,
    source_thought_id: str | None = None,
) -> list[ActionItem]:
    """Parse Fireflies action-items markdown into structured records.

    Accepts either a thought metadata dict (uses ``metadata['action_items']``)
    or the raw action-items string directly. Returns ``[]`` when input is
    missing or empty. Does not raise on malformed lines — they are skipped.
    """
    if metadata is None:
        return []
    if isinstance(metadata, dict):
        raw = metadata.get('action_items')
        if source_thought_id is None:
            # Fireflies thoughts use 'meeting_id' as their stable identifier;
            # callers that pass dict + thought_id arg take precedence.
            source_thought_id = metadata.get('meeting_id')
    else:
        raw = metadata
    if not raw or not isinstance(raw, str):
        return []

    items: list[ActionItem] = []

    # Walk through the text by splitting on H3 headers. Anything before the
    # first header has no owner, so we skip it (Fireflies always emits a header).
    sections = _split_by_header(raw)
    for header, body in sections:
        is_collective = _is_collective(header)
        if is_collective:
            owners = [(header.strip(), True)]
        else:
            owners = [(name, False) for name in _split_owners(header)] or [(header.strip(), False)]

        for line_match in _ITEM_RE.finditer(body):
            box = line_match.group('box').lower()
            status = 'done' if box == 'x' else 'open'
            content, ts, due, done_date, tags = _strip_decorations(line_match.group('rest'))
            if not content:
                continue
            for owner_name, collective in owners:
                slug = '_collective' if collective else _slugify(owner_name)
                items.append(ActionItem(
                    owner_slug=slug,
                    owner_name=owner_name,
                    owner_email=None,
                    owner_is_collective=collective,
                    content=content,
                    status=status,
                    timestamp_in_meeting=ts,
                    due_date=due,
                    completion_date=done_date,
                    inline_tags=tags,
                    source_thought_id=str(source_thought_id) if source_thought_id else None,
                ))

    return items


def parse_email_actions(synthesis_thought: dict) -> list[ActionItem]:
    """F6.4.7 — adapter for email_thread_synthesis thoughts.

    F6.3 email_thread.synthesize emits a thought whose body contains a
    `## Action items` section followed by `### {Owner}` blocks in the same
    format that parse_action_items already understands. This adapter extracts
    that section and runs the existing parser, returning records labelled with
    the thought's id.
    """
    if not synthesis_thought:
        return []
    body = synthesis_thought.get('body') or ''
    if not body:
        return []

    # Slice out only the "## Action items" section (case-insensitive header).
    section_match = re.search(
        r'(?im)^##\s+action\s+items\s*$(.*?)(?=^##\s|\Z)',
        body, re.MULTILINE | re.DOTALL,
    )
    if not section_match:
        return []
    section_body = section_match.group(1)

    return parse_action_items(
        section_body,
        source_thought_id=str(synthesis_thought.get('id') or ''),
    )


def _split_by_header(text: str) -> Iterable[tuple[str, str]]:
    """Yield (header, body) tuples split on '### Header' lines."""
    indices: list[tuple[int, int, str]] = []
    for m in _HEADER_RE.finditer(text):
        indices.append((m.start(), m.end(), m.group(1)))
    if not indices:
        return []
    out: list[tuple[str, str]] = []
    for i, (_, end, header) in enumerate(indices):
        body_start = end
        body_end = indices[i + 1][0] if i + 1 < len(indices) else len(text)
        out.append((header, text[body_start:body_end]))
    return out
