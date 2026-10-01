# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/classifier.py — deterministic meeting classification (F2.1)
#
# Maps a thought row to (client, project, person_tags, type_tags) using
# config/projects.yaml as single source of truth.
#
# Priority (highest → lowest, first hit wins):
#   1. filename slug tokens (vault `_source/work/meeting-notes/<date>-<slug>.md`)
#   2. metadata.title (frontmatter; currently null in DB until F2.5 fix)
#   3. body keyword overlay (only to upgrade *-general → specific sub-project)
#   4. fireflies tags (`metadata.tags`) — as last-resort hint
#
# Unknown / ambiguous slugs are appended to data/discovery/unmapped_slugs.tsv
# for weekly manual review.

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

from exocortex.config_loader import resolve_config_path
from exocortex.settings import get_settings

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / 'config' / 'projects.yaml'


def _default_meetings_dir() -> Path:
    override = os.environ.get('VAULT_MEETINGS_DIR')
    if override:
        return Path(override)
    return get_settings().vault_path / '_source' / 'work' / 'meeting-notes'


# Lazy: resolved on first attribute access so the module can be imported
# without EXOCORTEX_VAULT_PATH being set (test stubs etc.).
def __getattr__(name):
    if name == 'VAULT_MEETINGS_DIR':
        try:
            return _default_meetings_dir()
        except Exception as exc:
            # Surface as AttributeError so `hasattr()` returns False instead
            # of leaking ValidationError from pydantic-settings.
            raise AttributeError(
                f"VAULT_MEETINGS_DIR unavailable: {exc}. "
                "Set EXOCORTEX_VAULT_PATH or VAULT_MEETINGS_DIR."
            ) from exc
    raise AttributeError(name)
DISCOVERY_DIR = REPO_ROOT / 'data' / 'discovery'
UNMAPPED_TSV = DISCOVERY_DIR / 'unmapped_slugs.tsv'

_FRONTMATTER_RE = re.compile(r'^---\n(.*?)\n---', re.DOTALL)
_FILENAME_DATE_RE = re.compile(r'^(\d{4}-\d{2}-\d{2})-(.+)\.md$')
# Fireflies auto-title pattern when meeting has no human title:
# `mar-17-02-00-pm`, `apr-27-11-01-am`, `feb-02-03-31-pm`. Fall through to example-general.
_FIREFLIES_AUTO_TITLE_RE = re.compile(
    r'^(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)-\d{1,2}-\d{2}-\d{2}-(?:am|pm)$',
    re.IGNORECASE,
)
# Word-boundary token match using `-` separators in a slug.
# Ensures `ca` matches `ca-badania` but NOT `ca-kiem` (false positive guard).
def _slug_contains_token(slug: str, token: str) -> bool:
    if not token:
        return False
    pattern = r'(?:^|-)' + re.escape(token.lower()) + r'(?:-|$)'
    return bool(re.search(pattern, slug.lower()))


def _slug_contains_phrase(slug: str, phrase: str) -> bool:
    """For multi-word phrase aliases (e.g. 'wks-acme'), match as substring with hyphen guards."""
    p = phrase.lower()
    s = slug.lower()
    if '-' not in p:
        return _slug_contains_token(s, p)
    pattern = r'(?:^|-)' + re.escape(p) + r'(?:-|$)'
    return bool(re.search(pattern, s))


# ─────────────────────────── Config loading (cached) ───────────────────────────

@dataclass
class Project:
    slug: str
    display_name: str
    aliases: list[str] = field(default_factory=list)
    body_match: list[str] = field(default_factory=list)
    min_meetings: int = 3


@dataclass
class Client:
    slug: str
    display_name: str
    aliases: list[str] = field(default_factory=list)
    type: str = 'external'
    domain: str = 'work'
    projects: list[Project] = field(default_factory=list)

    @property
    def general_project(self) -> Project | None:
        for p in self.projects:
            if p.slug.endswith('-general') or p.slug == 'docmost-internal':
                return p
        return self.projects[-1] if self.projects else None


@dataclass
class ProjectsConfig:
    clients: list[Client]
    # tag → {person_slug, display_name, aliases: list[str]}. `aliases` are
    # filename-slug tokens (e.g. `121-user-colleague`, `adamn-biweekly`); a slug
    # match classifies the meeting as person-only (client/project = None).
    person_tags: dict[str, dict]
    type_tags: set[str]


_config: ProjectsConfig | None = None
_config_lock = threading.Lock()


def load_config(path: Path = CONFIG_PATH) -> ProjectsConfig:
    """Load and cache config/projects.yaml. Thread-safe.

    Falls back to ``config/projects.example.yaml`` in fresh checkouts where
    the operator hasn't run ``exocortex init`` yet — see F31.8.4.
    """
    global _config
    with _config_lock:
        if _config is not None:
            return _config
        # Honour explicit-path override but transparently fall back to the
        # example file when the default path is missing (fresh checkout).
        # resolve_config_path() handles the exists()/fallback dance.
        if path == CONFIG_PATH:
            path = resolve_config_path('projects.yaml')
        with path.open(encoding='utf-8') as fh:
            raw = yaml.safe_load(fh)
        clients = [
            Client(
                slug=c['slug'],
                display_name=c['display_name'],
                aliases=list(c.get('aliases') or []),
                type=c.get('type', 'external'),
                domain=c.get('domain', 'work'),
                projects=[
                    Project(
                        slug=p['slug'],
                        display_name=p['display_name'],
                        aliases=list(p.get('aliases') or []),
                        body_match=list(p.get('body_match') or []),
                        min_meetings=int(p.get('min_meetings', 3)),
                    )
                    for p in (c.get('projects') or [])
                ],
            )
            for c in (raw.get('clients') or [])
        ]
        _config = ProjectsConfig(
            clients=clients,
            person_tags=dict(raw.get('person_tags') or {}),
            type_tags=set(raw.get('type_tags') or []),
        )
        return _config


def reload_config() -> ProjectsConfig:
    """Force reload — useful for tests / interactive sessions."""
    global _config
    with _config_lock:
        _config = None
    return load_config()


# ─────────────────────────── Vault filename slug index ───────────────────────────

_meeting_id_to_slug: dict[str, str] | None = None
_slug_index_lock = threading.Lock()


def _build_meeting_id_index(meetings_dir: Path | None = None) -> dict[str, str]:
    """Walk vault dir, build {meeting_id: filename_slug}. filename_slug is the
    portion after the YYYY-MM-DD- prefix, without .md."""
    if meetings_dir is None:
        meetings_dir = _default_meetings_dir()
    index: dict[str, str] = {}
    if not meetings_dir.exists():
        return index
    for f in meetings_dir.iterdir():
        if not f.is_file() or not f.name.endswith('.md'):
            continue
        m = _FILENAME_DATE_RE.match(f.name)
        if not m:
            continue
        slug = m.group(2)
        # Read frontmatter for meeting_id.
        try:
            head = f.read_text(encoding='utf-8', errors='ignore')[:2048]
        except OSError:
            continue
        fm = _FRONTMATTER_RE.match(head)
        if not fm:
            continue
        for line in fm.group(1).splitlines():
            line = line.strip()
            if line.startswith('meeting_id:'):
                mid = line.split(':', 1)[1].strip().strip('"\'')
                if mid:
                    index[mid] = slug
                break
    return index


def get_meeting_slug(meeting_id: str) -> str | None:
    """Return filename slug (post-date) for a Fireflies meeting_id, or None."""
    global _meeting_id_to_slug
    with _slug_index_lock:
        if _meeting_id_to_slug is None:
            _meeting_id_to_slug = _build_meeting_id_index()
    return _meeting_id_to_slug.get(meeting_id)


# ─────────────────────────── Core classification ───────────────────────────

@dataclass
class Classification:
    client: str | None = None        # client slug, e.g. 'acme'
    project: str | None = None       # project slug, e.g. 'acme-kantor'
    person_tags: list[str] = field(default_factory=list)   # person slugs
    type_tags: list[str] = field(default_factory=list)     # type tag slugs
    confidence: str = 'high'            # high | medium | low
    source: str = 'filename'            # filename | title | body | tags | unmapped
    # F3.5 — LLM-augmented signals (from extracted_tags JSONB column).
    # `*_source` = 'none' when extracted_tags missing AND deterministic missed.
    client_source: str = 'none'         # deterministic | llm | both | none
    project_source: str = 'none'        # deterministic | llm | both | none
    topic_tags: list[str] = field(default_factory=list)    # semantic topics (LLM-only)
    activity_tags: list[str] = field(default_factory=list) # activity slugs (LLM, closed vocab)
    status_tags: list[str] = field(default_factory=list)   # operational status (LLM, closed vocab)
    classification_confidence: float = 0.0  # 0.0-1.0; combined det+LLM confidence


def _match_client_in_slug(slug: str, cfg: ProjectsConfig) -> Client | None:
    """First-match: does any client alias appear in the filename slug?"""
    # Sort aliases by length DESC so 'wks-betabank' wins over 'betabank' if both match
    candidates: list[tuple[int, Client, str]] = []
    for c in cfg.clients:
        for alias in c.aliases:
            if _slug_contains_phrase(slug, alias):
                candidates.append((len(alias), c, alias))
    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[0])
    return candidates[0][1]


def _match_project_in_slug_global(slug: str, cfg: ProjectsConfig
                                  ) -> tuple[Client, Project] | None:
    """Reverse derivation: scan ALL projects; first matching alias derives both
    project and its parent client. Resolves cases where the filename slug carries
    the project token but not a client token (e.g. `pulsar-10m-pierwsze-przymiarki`
    → example-project-1; `ca-badania` → hooli-bank/ca-badania; `efx-demo` →
    acme/acme-kantor)."""
    candidates: list[tuple[int, Client, Project]] = []
    for c in cfg.clients:
        for p in c.projects:
            if p.slug.endswith('-general') or p.slug == 'docmost-internal':
                continue  # avoid pulling client via vacuous *-general aliases
            for alias in p.aliases:
                if _slug_contains_phrase(slug, alias):
                    candidates.append((len(alias), c, p))
    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[0])
    return candidates[0][1], candidates[0][2]


def _match_project_in_slug(slug: str, client: Client) -> Project | None:
    """Within a client, find the project whose alias matches the slug."""
    candidates: list[tuple[int, Project]] = []
    for p in client.projects:
        if p.slug.endswith('-general') or p.slug == 'docmost-internal':
            continue  # general is fallback, handled separately
        for alias in p.aliases:
            if _slug_contains_phrase(slug, alias):
                candidates.append((len(alias), p))
    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[0])
    return candidates[0][1]


def _match_project_in_body(overview: str, notes: str, client: Client) -> Project | None:
    """Body overlay: search overview + notes for body_match keywords."""
    text = ((overview or '') + '\n' + (notes or '')).lower()
    if not text.strip():
        return None
    candidates: list[tuple[int, Project]] = []
    for p in client.projects:
        if not p.body_match:
            continue
        for kw in p.body_match:
            if kw.lower() in text:
                candidates.append((len(kw), p))
                break
    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[0])
    return candidates[0][1]


def _classify_tags(meta_tags: list[str], cfg: ProjectsConfig
                   ) -> tuple[list[str], list[str]]:
    """Split fireflies/frontmatter tags into person_tags + type_tags."""
    person_tags: list[str] = []
    type_tags: list[str] = []
    for t in (meta_tags or []):
        tl = str(t).lower().strip()
        if tl in cfg.person_tags:
            slug = cfg.person_tags[tl]['person_slug']
            if slug not in person_tags:
                person_tags.append(slug)
        elif tl in cfg.type_tags:
            if tl not in type_tags:
                type_tags.append(tl)
    return person_tags, type_tags


def _match_person_in_slug(slug: str, cfg: ProjectsConfig) -> str | None:
    """Return person_slug if filename slug matches any person_tag alias.

    Used to mark meetings like `121-user-colleague`, `adamn-biweekly`,
    `tomasz-l-bi-weekly` as person-only (no client/project)."""
    candidates: list[tuple[int, str]] = []
    for tag, info in cfg.person_tags.items():
        for alias in [tag] + list(info.get('aliases') or []):
            if _slug_contains_phrase(slug, alias):
                candidates.append((len(alias), info['person_slug']))
    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[0])
    return candidates[0][1]


# ─────────────────────────── F3.5 — LLM signals from extracted_tags ───────────────────────────

# Confidence thresholds per dimension. Values come from `wiki-tag-extraction-analysis.md`
# experiment + reconcile() weighting in extract_tags_batch.py.
_LLM_THRESHOLD = {
    'client': 0.7,    # closed vocab, deterministic almost always wins; LLM only as fallback
    'project': 0.7,   # LLM augments when deterministic misses sub-project
    'activity': 0.7,  # closed vocab, multi-tag
    'topic': 0.6,     # dynamic vocab, lower bar (new tags allowed)
    'status': 0.7,    # closed vocab, multi-label OK
}


def _read_llm_tags(thought: dict) -> dict[str, list[dict]]:
    """Fetch `extracted_tags` from a thought (DB row OR thought dict).

    Returns {axis: [{value, source, confidence, new}, ...]} for the 5 axes.
    Empty dict when there is no data (older pre-batch thoughts or failed extraction).
    """
    et = thought.get('extracted_tags')
    if not et or not isinstance(et, dict):
        return {}
    if et.get('error'):
        return {}
    out: dict[str, list[dict]] = {}
    for axis in ('client', 'project', 'activity', 'topic', 'status'):
        items = et.get(axis) or []
        if isinstance(items, list):
            out[axis] = items
    return out


def _high_conf_values(items: list[dict], threshold: float) -> list[str]:
    """Return slugs above threshold, ordered by confidence DESC, deduplicated."""
    seen: set[str] = set()
    out: list[str] = []
    for it in sorted(items, key=lambda x: -float(x.get('confidence', 0))):
        if float(it.get('confidence', 0)) < threshold:
            continue
        v = it.get('value')
        if not v or v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


def _augment_with_llm(c: Classification, llm_tags: dict[str, list[dict]]) -> Classification:
    """Merge LLM signals into a Classification. Mutates AND returns the same instance.

    Rules:
    - client/project: deterministic takes precedence. LLM provides a fallback when
      det misses, or a `_source` flag when both agree. Conflicts (det vs LLM differ)
      are already resolved in extract_tags_batch.reconcile() — here we read the
      reconciled result.
    - topic/activity/status: LLM-only (no deterministic counterpart).
    - confidence: deterministic high → 1.0; deterministic medium → 0.7;
      LLM-only → max LLM conf.
    """
    if not llm_tags:
        # No LLM data — set source flags based on deterministic alone.
        c.client_source = 'deterministic' if c.client else 'none'
        c.project_source = 'deterministic' if c.project else 'none'
        c.classification_confidence = {'high': 1.0, 'medium': 0.7, 'low': 0.4}.get(
            c.confidence, 0.5) if c.client else 0.0
        return c

    # CLIENT — reconcile result: extract_tags_batch stored deterministic+slug first
    # when both agree, and added LLM as second on conflict. Read values + sources.
    llm_client_items = llm_tags.get('client') or []
    llm_client_top = _high_conf_values(llm_client_items, _LLM_THRESHOLD['client'])
    llm_client_value = llm_client_top[0] if llm_client_top else None

    if c.client and llm_client_value:
        c.client_source = 'both' if c.client == llm_client_value else 'deterministic'
    elif c.client:
        c.client_source = 'deterministic'
    elif llm_client_value:
        c.client = llm_client_value
        c.client_source = 'llm'
        if c.source == 'unmapped':
            c.source = 'llm'
            c.confidence = 'medium'
    else:
        c.client_source = 'none'

    # PROJECT — same logic. LLM can supply the project when det = {client}-general.
    llm_project_items = llm_tags.get('project') or []
    llm_project_top = _high_conf_values(llm_project_items, _LLM_THRESHOLD['project'])
    llm_project_value = llm_project_top[0] if llm_project_top else None

    if c.project and llm_project_value:
        # Det project = `{client}-general` is a fallback; the LLM is more precise → upgrade.
        if c.project.endswith('-general') and llm_project_value != c.project:
            # Upgrade only when the LLM project belongs to the same client.
            if c.client and llm_project_value.startswith(c.client + '-'):
                c.project = llm_project_value
                c.project_source = 'llm'
            else:
                c.project_source = 'deterministic'
        else:
            c.project_source = 'both' if c.project == llm_project_value else 'deterministic'
    elif c.project:
        c.project_source = 'deterministic'
    elif llm_project_value:
        c.project = llm_project_value
        c.project_source = 'llm'
    else:
        c.project_source = 'none'

    # TOPIC / ACTIVITY / STATUS — czysty LLM signal.
    c.topic_tags = _high_conf_values(llm_tags.get('topic') or [], _LLM_THRESHOLD['topic'])
    c.activity_tags = _high_conf_values(llm_tags.get('activity') or [], _LLM_THRESHOLD['activity'])
    c.status_tags = _high_conf_values(llm_tags.get('status') or [], _LLM_THRESHOLD['status'])

    # Combined confidence: deterministic high = 1.0; LLM-only = max LLM conf.
    if c.client_source in ('deterministic', 'both'):
        c.classification_confidence = {'high': 1.0, 'medium': 0.7, 'low': 0.4}.get(
            c.confidence, 0.5)
    elif c.client_source == 'llm' and llm_client_items:
        c.classification_confidence = float(llm_client_items[0].get('confidence', 0.6))
    else:
        c.classification_confidence = 0.0

    return c


def classify_meeting(thought: dict, cfg: ProjectsConfig | None = None
                     ) -> Classification:
    """Main entry point. `thought` is a row from `thoughts` table (dict).

    Returns Classification with:
      - client: client slug (None if unknown)
      - project: project slug (None if no client)
      - person_tags: list of person slugs from `metadata.tags`
      - type_tags: list of type tags from `metadata.tags`
      - confidence: high/medium/low based on match source
      - source: filename/title/body/tags/unmapped
    """
    cfg = cfg or load_config()
    meta = thought.get('metadata') or {}
    meeting_id = meta.get('meeting_id')
    title = (meta.get('title') or '').strip()
    overview = meta.get('overview') or ''
    notes = meta.get('notes') or ''
    meta_tags = list(meta.get('tags') or [])

    person_tags, type_tags = _classify_tags(meta_tags, cfg)

    # 1. Filename slug (highest priority)
    slug = get_meeting_slug(meeting_id) if meeting_id else None
    client: Client | None = None
    project: Project | None = None
    source = 'unmapped'
    confidence = 'low'

    # 1a. Person-only slug (1-on-1 / biweekly meetings) — `121-user-colleague`,
    #     `adamn-biweekly`, `tomasz-l-bi-weekly`. These meetings have NO external
    #     client and SHOULD NOT be filed under example-company sub-projects. Add the
    #     person to person_tags and leave client/project = None so renderer
    #     treats it as person-only.
    person_only_match = False
    if slug:
        ps = _match_person_in_slug(slug, cfg)
        if ps:
            if ps not in person_tags:
                person_tags.append(ps)
            source = 'filename-person'
            confidence = 'high'
            person_only_match = True

    if slug and not person_only_match:
        client = _match_client_in_slug(slug, cfg)
        if client:
            source = 'filename'
            confidence = 'high'
            project = _match_project_in_slug(slug, client)
        else:
            # 1b. Reverse derivation: project alias hit → derive client.
            derived = _match_project_in_slug_global(slug, cfg)
            if derived:
                client, project = derived
                source = 'filename-project'
                confidence = 'high'

    # 2. Title (frontmatter, currently null until F2.5)
    if client is None and not person_only_match and title:
        title_slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
        client = _match_client_in_slug(title_slug, cfg)
        if client:
            source = 'title'
            confidence = 'high'
            project = _match_project_in_slug(title_slug, client)
        else:
            derived = _match_project_in_slug_global(title_slug, cfg)
            if derived:
                client, project = derived
                source = 'title-project'
                confidence = 'high'

    # 3. Body overlay (layer B): if we have a client but no specific sub-project
    if client is not None and project is None:
        body_proj = _match_project_in_body(overview, notes, client)
        if body_proj is not None:
            project = body_proj
            if source == 'filename':
                source = 'filename+body'

    # 4. Fireflies tags fallback (last resort) — `metadata.tags` as a client hint
    if client is None and not person_only_match and meta_tags:
        for t in meta_tags:
            tl = str(t).lower().strip()
            for c in cfg.clients:
                if tl == c.slug or tl in c.aliases:
                    client = c
                    source = 'tags'
                    confidence = 'medium'
                    break
            if client:
                break

    # 5. Fireflies auto-title pattern fallback (e.g. `mar-17-02-00-pm`):
    #    no meaningful name → assign to example-company (internal catch-all).
    if client is None and not person_only_match and slug \
            and _FIREFLIES_AUTO_TITLE_RE.match(slug):
        for c in cfg.clients:
            if c.slug == 'example-company':
                client = c
                source = 'fallback-auto-title'
                confidence = 'low'
                break

    # Fallback project = {client}-general
    if client is not None and project is None:
        project = client.general_project

    # Autodiscovery: log only truly unmapped meetings (no person-only match either).
    if client is None and not person_only_match:
        _log_unmapped(meeting_id=meeting_id, slug=slug, title=title, tags=meta_tags)

    classification = Classification(
        client=client.slug if client else None,
        project=project.slug if project else None,
        person_tags=person_tags,
        type_tags=type_tags,
        confidence=confidence,
        source=source,
    )

    # F3.5 — augment with LLM signals from extracted_tags JSONB (no-op when missing).
    return _augment_with_llm(classification, _read_llm_tags(thought))


# ─────────────────────────── Autodiscovery (unmapped slugs) ───────────────────────────

_unmapped_lock = threading.Lock()
_unmapped_seen: set[str] = set()


def _suggest_match(slug: str | None, title: str) -> str:
    """Cheap heuristic for human review: first non-date hyphen-token from slug or title."""
    candidate = slug or re.sub(r'[^a-z0-9]+', '-', (title or '').lower()).strip('-')
    if not candidate:
        return ''
    tokens = [t for t in candidate.split('-') if t and not t.isdigit()]
    return tokens[0] if tokens else ''


def _log_unmapped(meeting_id: str | None, slug: str | None,
                  title: str, tags: list[str]) -> None:
    """Append unmapped meeting to data/discovery/unmapped_slugs.tsv. Idempotent within process."""
    key = meeting_id or slug or title
    if not key:
        return
    with _unmapped_lock:
        if key in _unmapped_seen:
            return
        _unmapped_seen.add(key)
        DISCOVERY_DIR.mkdir(parents=True, exist_ok=True)
        write_header = not UNMAPPED_TSV.exists()
        with UNMAPPED_TSV.open('a', encoding='utf-8') as fh:
            if write_header:
                fh.write('timestamp\tmeeting_id\tslug\ttitle\ttags\tsuggested\n')
            fh.write('\t'.join([
                datetime.now(UTC).isoformat(timespec='seconds'),
                meeting_id or '',
                slug or '',
                title.replace('\t', ' ').replace('\n', ' '),
                ','.join(str(t) for t in tags),
                _suggest_match(slug, title),
            ]) + '\n')


# ─────────────────────────── CLI / smoke test ───────────────────────────

def _smoke_test() -> None:
    """Run classifier on all meetings in DB, print before/after F3.5 distribution."""
    from collections import Counter

    from exocortex.db import query

    cfg = load_config()
    print(f'Loaded {len(cfg.clients)} clients, '
          f'{sum(len(c.projects) for c in cfg.clients)} projects, '
          f'{len(cfg.person_tags)} person_tags, '
          f'{len(cfg.type_tags)} type_tags')

    # F3.5: include extracted_tags. Backward-compatible — empty {} when not yet extracted.
    rows = query("""
        SELECT id, body, thought_type, metadata, extracted_tags
        FROM thoughts
        WHERE thought_type = 'work_meeting_note'
        ORDER BY metadata->>'meeting_date'
    """)
    print(f'Total work_meeting_note: {len(rows)}\n')

    by_client: Counter = Counter()
    by_project: Counter = Counter()
    by_source: Counter = Counter()
    by_client_source: Counter = Counter()
    by_project_source: Counter = Counter()
    topic_counter: Counter = Counter()
    activity_counter: Counter = Counter()
    status_counter: Counter = Counter()
    unmapped: list[tuple[str, str]] = []
    with_llm = 0

    for row in rows:
        c = classify_meeting(row, cfg)
        by_client[c.client or '<unmapped>'] += 1
        by_project[c.project or '<none>'] += 1
        by_source[c.source] += 1
        by_client_source[c.client_source] += 1
        by_project_source[c.project_source] += 1
        for t in c.topic_tags:
            topic_counter[t] += 1
        for a in c.activity_tags:
            activity_counter[a] += 1
        for s in c.status_tags:
            status_counter[s] += 1
        if (row.get('extracted_tags') or {}).get('batch_run_id'):
            with_llm += 1
        if c.client is None:
            slug = get_meeting_slug((row.get('metadata') or {}).get('meeting_id') or '')
            unmapped.append((slug or '?', str(row['id'])[:8]))

    print(f'Thoughts with LLM extracted_tags: {with_llm}/{len(rows)}\n')
    print('=== By client ===')
    for k, v in sorted(by_client.items(), key=lambda x: -x[1]):
        print(f'  {k:32s} {v:>4d}')
    print('\n=== By source (deterministic) ===')
    for k, v in by_source.items():
        print(f'  {k:20s} {v:>4d}')
    print('\n=== By client_source (F3.5) ===')
    for k, v in by_client_source.items():
        print(f'  {k:20s} {v:>4d}')
    print('\n=== By project_source (F3.5) ===')
    for k, v in by_project_source.items():
        print(f'  {k:20s} {v:>4d}')
    print('\n=== Top projects ===')
    for k, v in by_project.most_common(20):
        print(f'  {k:32s} {v:>4d}')
    if topic_counter:
        print('\n=== Top topics (F3.5, LLM-only) ===')
        for k, v in topic_counter.most_common(15):
            print(f'  {k:32s} {v:>4d}')
    if activity_counter:
        print('\n=== Top activities (F3.5) ===')
        for k, v in activity_counter.most_common(10):
            print(f'  {k:32s} {v:>4d}')
    if status_counter:
        print('\n=== Top status (F3.5) ===')
        for k, v in status_counter.most_common(10):
            print(f'  {k:32s} {v:>4d}')
    if unmapped:
        print(f'\n=== Unmapped ({len(unmapped)}) — first 20 ===')
        for slug, tid in unmapped[:20]:
            print(f'  [{tid}] {slug}')


if __name__ == '__main__':
    _smoke_test()
