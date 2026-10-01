# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/promotion_lib.py — F15-R.2: shared library for MCP-driven manual
# promotion of meeting action-items to TaskNotes backlog stubs.
#
# Public API (used by workers/mcp_server.py — F15-R.3):
#   create_promotion_stubs(meeting_slug, parent_topic, item_descriptions, ...)
#   delete_promotion_stubs(stub_id, ...)
#   list_promotion_stubs(meeting_slug=None, parent_only=False, ...)
#   normalize_action_text(text)            — re-export of wiki_compiler logic
#   compute_fingerprint(meeting_slug, raw_line)
#
# Design (deterministic, zero-LLM):
#   * `item_descriptions` MUST match `[ ]` / `[x]` lines in meeting page
#     post-normalize → ValueError on mismatch (defensive validation).
#   * Cross-meeting dedupe: existing `suggested_slug` ⇒ append [[meeting]] to
#     parent's `source_meetings`, only add children with unseen fingerprints.
#   * Slug conflict (different parent_topic): append `-2`, `-3`, ...
#   * F11.4 invariant: NEVER modifies wiki/work/meetings/*.md.

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

import yaml

# ── Paths ─────────────────────────────────────────────────────────────────
from exocortex.settings import get_settings
from exocortex.wiki_compiler import _normalize_action_text_for_filter


def _default_vault() -> Path:
    return get_settings().vault_path


_MEETINGS_REL = 'wiki/work/meetings'
_MANUAL_REL = '_ Second Brain/backlog/_second-brain/manual'

# ── Shared regex (mirrored across detector/acceptor/wiki_compiler) ────────

_FM_RE = re.compile(r'\A---\n(.*?)\n---\n?(.*)', re.DOTALL)
_OPEN_LINE_RE = re.compile(r'^\s*-\s*\[[ x]\]\s+(.+?)$',
                           re.IGNORECASE | re.MULTILINE)


# ── Public re-exports + small helpers ─────────────────────────────────────

def normalize_action_text(text: str) -> str:
    """Strip ✅/➕ date markers and collapse whitespace.

    Same shape as the wiki_compiler / detector / acceptor implementation —
    re-exported here so callers don't need to know about the historic split.
    """
    return _normalize_action_text_for_filter(text or '')


def compute_fingerprint(meeting_slug: str, raw_line: str) -> str:
    """`{meeting-slug}:{md5(normalize(raw_line))[:8]}` — F15.3 contract.

    Stable across re-renders (date markers stripped) so that `[ ]` → `[x]`
    flips do not invalidate the fingerprint."""
    norm = normalize_action_text(raw_line)
    digest = hashlib.md5(norm.encode('utf-8')).hexdigest()[:8]
    return f'{meeting_slug}:{digest}'


def slugify(text: str) -> str:
    """ASCII-only, lowercase, dash-separated. Strips diacritics / emoji."""
    if not text:
        return ''
    s = unicodedata.normalize('NFKD', text)
    s = s.encode('ascii', errors='ignore').decode('ascii')
    s = s.lower()
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s or 'item'


def _today_iso() -> str:
    return datetime.now(UTC).date().isoformat()


def _wikilink(slug: str) -> str:
    if slug.startswith('[[') and slug.endswith(']]'):
        return slug
    return f'[[{slug}]]'


def _vault_root(override: Path | None) -> Path:
    return Path(override).expanduser() if override else _default_vault()


def _manual_dir(vault_root: Path | None) -> Path:
    return _vault_root(vault_root) / _MANUAL_REL


def _meeting_path(vault_root: Path | None, slug: str) -> Path:
    return _vault_root(vault_root) / _MEETINGS_REL / f'{slug}.md'


# ── YAML helpers (wikilink-friendly dumper) ───────────────────────────────

class _WikilinkDumper(yaml.SafeDumper):
    pass


def _repr_str(dumper: yaml.SafeDumper, value: str) -> yaml.ScalarNode:
    if value.startswith('[[') and value.endswith(']]'):
        return dumper.represent_scalar(
            'tag:yaml.org,2002:str', value, style='"')
    return dumper.represent_scalar('tag:yaml.org,2002:str', value)


_WikilinkDumper.add_representer(str, _repr_str)


def _render_yaml(data: dict) -> str:
    body = yaml.dump(
        data, Dumper=_WikilinkDumper, default_flow_style=False,
        allow_unicode=True, sort_keys=False, width=10_000)
    return f'---\n{body}---\n'


def _parse_fm(text: str) -> tuple[dict, str]:
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}, m.group(2)
    return (fm if isinstance(fm, dict) else {}), m.group(2)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(content, encoding='utf-8')
    tmp.rename(path)


# ── Meeting validation ────────────────────────────────────────────────────

def _load_meeting_lines(meeting_path: Path) -> set[str]:
    """Return set of normalized `[ ]`/`[x]` action-item lines in the meeting.

    Matches the body only (frontmatter stripped). Used to validate that a
    caller-provided description actually exists in the meeting page (so we
    never create a stub for hallucinated text)."""
    if not meeting_path.is_file():
        raise FileNotFoundError(f'meeting not found: {meeting_path}')
    text = meeting_path.read_text(encoding='utf-8')
    _, body = _parse_fm(text)
    out: set[str] = set()
    for m in _OPEN_LINE_RE.finditer(body):
        norm = normalize_action_text(m.group(1))
        if norm:
            out.add(norm)
    return out


def _resolve_slug(manual_dir: Path, parent_topic: str,
                  suggested_slug: str | None) -> tuple[str, bool]:
    """Determine a unique slug.

    Returns (slug, is_existing_match).
      * `is_existing_match=True` ⇒ slug already points at a parent stub with
        the same `title` (cross-meeting dedupe path).
      * `is_existing_match=False` ⇒ either slug is new or we appended a
        numeric suffix because another parent_topic claimed the base slug.
    """
    base = suggested_slug or slugify(parent_topic)
    if not base:
        raise ValueError(f'cannot derive slug from parent_topic={parent_topic!r}')

    # Walk base, base-2, base-3, ... — return first slot that is either empty
    # or hosts a parent stub whose title matches `parent_topic`.
    candidate = base
    suffix = 2
    while True:
        path = manual_dir / f'{candidate}.md'
        if not path.exists():
            return candidate, False
        fm, _ = _parse_fm(path.read_text(encoding='utf-8'))
        existing_title = (fm.get('title') or '').strip()
        if existing_title == parent_topic.strip():
            return candidate, True
        candidate = f'{base}-{suffix}'
        suffix += 1


# ── Stub renderers ────────────────────────────────────────────────────────

def _build_parent_fm(slug: str, parent_topic: str, priority: str,
                     source_meetings: list[str], children: list[str]) -> dict:
    today = _today_iso()
    return {
        'title': parent_topic,
        'id': f'manual-{slug}',
        'description': parent_topic,
        'subject': parent_topic,
        'status': 'pending',
        'priority': priority,
        'phase': 'manual',
        'phase_order': '900',
        'projects': [],
        'blockedBy': [],
        'tags': ['manual', 'task', 'phase-manual', 'promoted-from-todo'],
        'created': today,
        'promoted_at': today,
        'source_meetings': source_meetings,
        'children': children,
    }


def _render_parent_body(slug: str, parent_topic: str, priority: str,
                        children_ids: list[str],
                        source_meetings: list[str]) -> str:
    today = _today_iso()
    lines = [
        '',
        f'# {parent_topic}',
        '',
        f'**Status**: `pending` · **Priority**: `{priority}` · '
        f'**Promoted**: `{today}`',
        '',
        '## Children',
        '',
    ]
    for cid in children_ids:
        lines.append(f'- [[{cid}]]')
    lines += ['', '## Source meetings', '']
    for sm in source_meetings:
        lines.append(f'- {sm}')
    lines += ['', '<!-- USER_NOTES -->', '']
    return '\n'.join(lines)


def _build_child_fm(slug: str, child_idx: int, raw_line: str, priority: str,
                    meeting_slug: str, fingerprint: str) -> dict:
    today = _today_iso()
    return {
        'title': raw_line[:200],
        'id': f'manual-{slug}-c{child_idx}',
        'description': raw_line[:300],
        'subject': raw_line[:120],
        'status': 'pending',
        'priority': priority,
        'phase': 'manual',
        'phase_order': f'9{child_idx:02d}',
        'projects': [],
        'blockedBy': [],
        'parent': f'[[manual-{slug}]]',
        'tags': ['manual', 'task', 'phase-manual', 'promoted-from-todo',
                 'child'],
        'created': today,
        'promoted_at': today,
        'source_meeting': _wikilink(meeting_slug),
        'source_fingerprint': fingerprint,
    }


def _render_child_body(slug: str, raw_line: str, meeting_slug: str) -> str:
    return (
        '\n'
        f'# {raw_line[:120]}\n'
        '\n'
        f'**Parent**: [[manual-{slug}]]\n'
        f'**Source**: {_wikilink(meeting_slug)}\n'
        '\n'
        '## Original action item\n'
        '\n'
        f'> {raw_line}\n'
        '\n'
        '<!-- USER_NOTES -->\n'
    )


# ── Public API ────────────────────────────────────────────────────────────

def create_promotion_stubs(
    meeting_slug: str,
    parent_topic: str,
    item_descriptions: list[str],
    suggested_slug: str | None = None,
    priority: str = 'MED',
    vault_root: Path | None = None,
) -> dict:
    """Materialize a parent + per-item child stubs in `manual/`.

    Cross-meeting path: when `suggested_slug` (or slugify(parent_topic))
    already exists with the same title, append [[meeting_slug]] to the
    existing parent's `source_meetings` and create only children whose
    fingerprints are not yet present.

    Args:
      meeting_slug: meeting page filename without `.md`.
      parent_topic: human-readable topic name (rendered as title/H1).
      item_descriptions: each MUST match a `[ ]`/`[x]` line in the meeting
        page (post-normalize). Order is preserved → child indices.
      suggested_slug: optional override. Defaults to `slugify(parent_topic)`.
      priority: 'LOW' | 'MED' | 'HIGH'. Defaults to 'MED'.
      vault_root: override vault path (tests).

    Returns:
      dict with keys parent_path, children_paths, parent_id, fingerprints,
      cross_meeting_update.

    Raises:
      ValueError: empty descriptions, unknown priority, or any description
        that does not match a meeting line.
      FileNotFoundError: meeting page missing.
    """
    if not item_descriptions:
        raise ValueError('item_descriptions must contain at least one entry')
    if priority not in ('LOW', 'MED', 'HIGH'):
        raise ValueError(f'priority must be LOW/MED/HIGH, got {priority!r}')

    manual_dir = _manual_dir(vault_root)
    manual_dir.mkdir(parents=True, exist_ok=True)

    meeting_lines = _load_meeting_lines(_meeting_path(vault_root, meeting_slug))

    # Defensive validation: every description must already live in the meeting.
    normalized: list[str] = []
    for desc in item_descriptions:
        norm = normalize_action_text(desc)
        if not norm:
            raise ValueError('item description normalises to empty string')
        if norm not in meeting_lines:
            raise ValueError(
                f'description not found in meeting {meeting_slug}: {desc!r}')
        normalized.append(norm)

    slug, is_existing = _resolve_slug(manual_dir, parent_topic, suggested_slug)
    fingerprints = [compute_fingerprint(meeting_slug, n) for n in normalized]
    meeting_link = _wikilink(meeting_slug)

    if is_existing:
        return _append_to_existing_parent(
            manual_dir=manual_dir, slug=slug, priority=priority,
            meeting_slug=meeting_slug, meeting_link=meeting_link,
            normalized_lines=normalized, fingerprints=fingerprints)

    return _create_fresh_parent(
        manual_dir=manual_dir, slug=slug, parent_topic=parent_topic,
        priority=priority, meeting_link=meeting_link, meeting_slug=meeting_slug,
        normalized_lines=normalized, fingerprints=fingerprints)


def _create_fresh_parent(*, manual_dir: Path, slug: str, parent_topic: str,
                         priority: str, meeting_link: str, meeting_slug: str,
                         normalized_lines: list[str],
                         fingerprints: list[str]) -> dict:
    children_ids = [f'{slug}-c{i + 1}' for i in range(len(normalized_lines))]
    parent_path = manual_dir / f'{slug}.md'
    children_paths: list[str] = []

    parent_fm = _build_parent_fm(
        slug=slug, parent_topic=parent_topic, priority=priority,
        source_meetings=[meeting_link], children=children_ids)
    parent_body = _render_parent_body(
        slug=slug, parent_topic=parent_topic, priority=priority,
        children_ids=children_ids, source_meetings=[meeting_link])
    _atomic_write(parent_path, _render_yaml(parent_fm) + parent_body)

    for idx, (raw, fp) in enumerate(zip(normalized_lines, fingerprints),
                                    start=1):
        child_id = f'{slug}-c{idx}'
        cpath = manual_dir / f'{child_id}.md'
        cfm = _build_child_fm(
            slug=slug, child_idx=idx, raw_line=raw, priority=priority,
            meeting_slug=meeting_slug, fingerprint=fp)
        cbody = _render_child_body(
            slug=slug, raw_line=raw, meeting_slug=meeting_slug)
        _atomic_write(cpath, _render_yaml(cfm) + cbody)
        children_paths.append(str(cpath))

    return {
        'parent_path': str(parent_path),
        'children_paths': children_paths,
        'parent_id': f'manual-{slug}',
        'fingerprints': fingerprints,
        'cross_meeting_update': False,
    }


def _append_to_existing_parent(*, manual_dir: Path, slug: str, priority: str,
                               meeting_slug: str, meeting_link: str,
                               normalized_lines: list[str],
                               fingerprints: list[str]) -> dict:
    parent_path = manual_dir / f'{slug}.md'
    fm, body = _parse_fm(parent_path.read_text(encoding='utf-8'))

    # Source meetings: append unique.
    sm = list(fm.get('source_meetings') or [])
    if meeting_link not in sm:
        sm.append(meeting_link)
    fm['source_meetings'] = sm

    # Existing fingerprints: scan child files (source-of-truth).
    existing_fps: set[str] = set()
    existing_indices: list[int] = []
    for child_path in manual_dir.glob(f'{slug}-c*.md'):
        try:
            cfm, _ = _parse_fm(child_path.read_text(encoding='utf-8'))
        except OSError:
            continue
        fp = cfm.get('source_fingerprint')
        if fp:
            existing_fps.add(fp)
        # Extract numeric suffix so we can append from max+1.
        m = re.match(rf'^{re.escape(slug)}-c(\d+)$', child_path.stem)
        if m:
            existing_indices.append(int(m.group(1)))

    next_idx = (max(existing_indices) + 1) if existing_indices else 1

    children_ids = list(fm.get('children') or [])
    children_paths: list[str] = []
    skipped_existing = 0

    for raw, fp in zip(normalized_lines, fingerprints):
        if fp in existing_fps:
            skipped_existing += 1
            continue
        child_id = f'{slug}-c{next_idx}'
        cpath = manual_dir / f'{child_id}.md'
        cfm = _build_child_fm(
            slug=slug, child_idx=next_idx, raw_line=raw, priority=priority,
            meeting_slug=meeting_slug, fingerprint=fp)
        cbody = _render_child_body(
            slug=slug, raw_line=raw, meeting_slug=meeting_slug)
        _atomic_write(cpath, _render_yaml(cfm) + cbody)
        children_paths.append(str(cpath))
        if child_id not in children_ids:
            children_ids.append(child_id)
        existing_fps.add(fp)
        next_idx += 1

    fm['children'] = children_ids
    _atomic_write(parent_path, _render_yaml(fm) + body)

    return {
        'parent_path': str(parent_path),
        'children_paths': children_paths,
        'parent_id': fm.get('id') or f'manual-{slug}',
        'fingerprints': fingerprints,
        'cross_meeting_update': True,
        'skipped_existing': skipped_existing,
    }


def delete_promotion_stubs(stub_id: str,
                           vault_root: Path | None = None) -> dict:
    """Delete a parent (cascading to all children) or a single child.

    Accepts either the bare slug (`initech-game-q2-roadmap`) or the full id form
    (`manual-initech-game-q2-roadmap`). Child ids look like `…-c3` /
    `manual-…-c3`.

    Returns: {'deleted_paths': [...], 'kind': 'parent'|'child'|'missing'}.
    """
    manual_dir = _manual_dir(vault_root)
    bare = stub_id.removeprefix('manual-')
    target = manual_dir / f'{bare}.md'

    if not target.is_file():
        return {'deleted_paths': [], 'kind': 'missing'}

    fm, _ = _parse_fm(target.read_text(encoding='utf-8'))
    deleted: list[str] = []

    parent_link = fm.get('parent')
    if isinstance(parent_link, str) and parent_link.strip().startswith('[['):
        # Child stub — remove only this file and update parent's children list.
        target.unlink()
        deleted.append(str(target))
        # Strip wikilink wrapper to find parent slug.
        parent_id = parent_link.strip().strip('[]')
        parent_slug = parent_id.removeprefix('manual-')
        ppath = manual_dir / f'{parent_slug}.md'
        if ppath.is_file():
            pfm, pbody = _parse_fm(ppath.read_text(encoding='utf-8'))
            children_ids = list(pfm.get('children') or [])
            child_id = bare  # e.g. initech-game-c3
            children_ids = [c for c in children_ids if c != child_id]
            pfm['children'] = children_ids
            _atomic_write(ppath, _render_yaml(pfm) + pbody)
        return {'deleted_paths': deleted, 'kind': 'child'}

    # Parent stub — cascade to every `{bare}-c*.md` child.
    target.unlink()
    deleted.append(str(target))
    for child_path in sorted(manual_dir.glob(f'{bare}-c*.md')):
        child_path.unlink()
        deleted.append(str(child_path))
    return {'deleted_paths': deleted, 'kind': 'parent'}


def list_promotion_stubs(meeting_slug: str | None = None,
                         parent_only: bool = False,
                         vault_root: Path | None = None) -> list[dict]:
    """Enumerate stubs in `manual/`.

    Filters:
      * `meeting_slug` — keep stubs whose `source_meeting(s)` mentions slug.
      * `parent_only` — drop child stubs.
    """
    manual_dir = _manual_dir(vault_root)
    if not manual_dir.is_dir():
        return []

    out: list[dict] = []
    target_link = _wikilink(meeting_slug) if meeting_slug else None
    for path in sorted(manual_dir.glob('*.md')):
        try:
            fm, _ = _parse_fm(path.read_text(encoding='utf-8'))
        except OSError:
            continue
        if not isinstance(fm, dict) or not fm.get('id'):
            continue

        kind = 'child' if 'source_fingerprint' in fm else 'parent'
        if parent_only and kind == 'child':
            continue

        sources: list[str] = []
        if kind == 'parent':
            sources = list(fm.get('source_meetings') or [])
        else:
            single = fm.get('source_meeting')
            if isinstance(single, str):
                sources = [single]

        if target_link and target_link not in sources:
            continue

        out.append({
            'stub_id': fm.get('id'),
            'slug': path.stem,
            'kind': kind,
            'title': fm.get('title') or path.stem,
            'status': fm.get('status') or 'pending',
            'priority': fm.get('priority') or 'MED',
            'source_meetings': sources,
            'parent': fm.get('parent') if kind == 'child' else None,
            'source_fingerprint': fm.get('source_fingerprint'),
            'path': str(path),
        })
    return out
