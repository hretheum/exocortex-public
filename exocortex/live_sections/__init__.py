# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F16/F17 — Live Sections + Meeting Prep.

F17 (Meeting Prep): deterministic pre-meeting brief — gathers client/project
context, decisions, action items, issues, people. Zero LLM.

F16 (Live Sections): scheduler + runner for self-updating sections in vault
files. Frontmatter `live:` directives with cron/window/event/manual triggers.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from exocortex.db import execute, get_tenant_id, query, query_one
from exocortex.settings import get_settings

logger = logging.getLogger(__name__)


def _resolve_vault_root() -> str:
    """Resolve vault root via Settings (honours EXOCORTEX_VAULT_PATH and the
    VAULT_PATH / SECOND_BRAIN_VAULT_PATH deprecated aliases)."""
    return str(get_settings().vault_path)

# ==========================================================================
# F17 — Meeting Prep (deterministic, no LLM)
# ==========================================================================

MEETING_PREP_DIR = "wiki/work/meetings/prep"


def prepare_meeting_prep(
    *,
    client_slug: str | None = None,
    project_slug: str | None = None,
    person_slug: str | None = None,
    vault_root: str | None = None,
) -> dict:
    """Generate a meeting prep brief for a client/project/person.

    Returns {path, summary, sections: {name: count}}.
    Write path: wiki/work/meetings/prep/{client}-{today}.md
    """
    tenant_id = get_tenant_id()
    today = datetime.now(UTC).date()
    today_str = today.isoformat()

    if vault_root is None:
        vault_root = _resolve_vault_root()

    # Resolve client_slug from project_slug or person_slug
    if not client_slug and project_slug:
        client_slug = _resolve_client_from_project(tenant_id, project_slug)
    if not client_slug and person_slug:
        client_slug = _resolve_client_from_person(tenant_id, person_slug)

    if not client_slug:
        raise ValueError("client_slug required (or project_slug/person_slug to resolve)")

    result = {}

    # ── 1. Recent meetings ─────────────────────────────────────────────
    meetings = query(
        "SELECT t.id, t.created_at::date AS mdate, "
        "  t.metadata->>'title' AS title, t.metadata->>'slug' AS slug "
        "FROM thoughts t "
        "JOIN edges e ON e.src_id = t.id AND e.type = 'classified_as_client' "
        "JOIN entities c ON c.id = e.dst_id AND c.canonical_name = %s "
        "WHERE t.tenant_id = %s AND t.thought_type = 'work_meeting_note' "
        "ORDER BY t.created_at DESC LIMIT 10",
        client_slug, tenant_id,
    )
    result['recent_meetings'] = [
        {'date': str(r['mdate']), 'title': r['title'] or '?',
         'slug': r['slug'] or ''}
        for r in meetings
    ]

    # ── 2. Recent decisions ────────────────────────────────────────────
    decisions = query(
        "SELECT s.content->>'decisions' AS decisions, s.generated_at::date AS gdate "
        "FROM syntheses s "
        "WHERE s.tenant_id = %s AND s.perspective_type IN ('client', 'project') "
        "  AND s.perspective_key = %s "
        "  AND s.superseded_by IS NULL "
        "  AND s.content->>'decisions' IS NOT NULL "
        "  AND s.content->>'decisions' != '' "
        "ORDER BY s.generated_at DESC LIMIT 5",
        tenant_id, client_slug,
    )
    result['decisions'] = [
        {'date': str(r['gdate']), 'text': (r['decisions'] or '')[:300]}
        for r in decisions
    ]

    # ── 3. Open action items (vault owner) ────────────────────────────────────
    from exocortex.action_items import me_owner_slugs, parse_action_items
    action_rows = query(
        "SELECT t.id, t.metadata "
        "FROM thoughts t "
        "JOIN edges e ON e.src_id = t.id AND e.type = 'classified_as_client' "
        "JOIN entities c ON c.id = e.dst_id AND c.canonical_name = %s "
        "WHERE t.tenant_id = %s AND t.thought_type = 'work_meeting_note' "
        "ORDER BY t.created_at DESC LIMIT 50",
        client_slug, tenant_id,
    )
    open_items = []
    for ar in action_rows:
        try:
            items = parse_action_items(ar['metadata'], source_thought_id=str(ar['id']))
        except Exception:  # noqa: BLE001, S112 — skip the bad item and carry on; narrowing would change behavior
            continue
        for it in items:
            if it.status == 'open' and it.owner_slug in me_owner_slugs():
                open_items.append(it.content)
    result['open_action_items'] = open_items[:15]

    # ── 4. Open problems ───────────────────────────────────────────────
    problems = query(
        "SELECT s.content->>'open_problems' AS problems, s.generated_at::date AS gdate "
        "FROM syntheses s "
        "WHERE s.tenant_id = %s AND s.perspective_type IN ('client', 'project') "
        "  AND s.perspective_key = %s "
        "  AND s.superseded_by IS NULL "
        "  AND s.content->>'open_problems' IS NOT NULL "
        "  AND s.content->>'open_problems' != '' "
        "ORDER BY s.generated_at DESC LIMIT 3",
        tenant_id, client_slug,
    )
    result['open_problems'] = [
        {'date': str(r['gdate']), 'text': (r['problems'] or '')[:500]}
        for r in problems
    ]

    # ── 5. Key people ──────────────────────────────────────────────────
    people = query(
        "SELECT p.canonical_name AS slug, count(*) AS n "
        "FROM edges ea "
        "JOIN edges ec ON ec.src_id = ea.src_id AND ec.type = 'classified_as_client' "
        "JOIN entities c ON c.id = ec.dst_id AND c.canonical_name = %s "
        "JOIN entities p ON p.id = ea.dst_id "
        "WHERE ea.tenant_id = %s AND ea.type = 'attended_meeting' "
        "  AND ea.dst_type = 'entity' AND p.type = 'person' "
        "  AND p.canonical_name != ALL(%s) "
        "GROUP BY p.canonical_name ORDER BY n DESC LIMIT 5",
        client_slug, tenant_id,
        list(me_owner_slugs() | {'unknown'}),
    )
    result['key_people'] = [{'slug': r['slug'], 'meetings': int(r['n'])} for r in people]

    # ── 6. Timeline ────────────────────────────────────────────────────
    timeline = query_one(
        "SELECT count(*) AS total, min(t.created_at)::date AS first_d, "
        "  max(t.created_at)::date AS last_d "
        "FROM thoughts t "
        "JOIN edges e ON e.src_id = t.id AND e.type = 'classified_as_client' "
        "JOIN entities c ON c.id = e.dst_id AND c.canonical_name = %s "
        "WHERE t.tenant_id = %s AND t.thought_type = 'work_meeting_note'",
        client_slug, tenant_id,
    )
    if timeline:
        result['timeline'] = {
            'total_meetings': int(timeline['total']),
            'first': str(timeline['first_d']) if timeline['first_d'] else '?',
            'last': str(timeline['last_d']) if timeline['last_d'] else '?',
        }

    # ── Render + Write ─────────────────────────────────────────────────
    markdown = _render_meeting_prep(client_slug, result, today_str)

    prep_dir = Path(vault_root) / MEETING_PREP_DIR
    prep_dir.mkdir(parents=True, exist_ok=True)
    path = prep_dir / f'{client_slug}-{today_str}.md'

    with open(path, 'w') as f:
        f.write(markdown)

    return {
        'path': str(path),
        'summary': f'Brief dla {client_slug}: {len(result["recent_meetings"])} spotkań, {len(result["open_action_items"])} action items',
        'sections': {
            'meetings': len(result['recent_meetings']),
            'decisions': len(result['decisions']),
            'actions': len(result['open_action_items']),
            'problems': len(result['open_problems']),
            'people': len(result['key_people']),
        },
    }


def _render_meeting_prep(client_slug: str, data: dict, today: str) -> str:
    """Render meeting prep brief as Markdown."""
    lines = [
        f'# {client_slug.replace("-", " ").title()} — Brief przed spotkaniem ({today})',
        '',
    ]

    # Recent meetings
    lines.append('## 📋 Ostatnie spotkania')
    for m in data.get('recent_meetings', []):
        lines.append(f'- {m["date"]} — {m["title"]}')
    lines.append('')

    # Decisions
    if data.get('decisions'):
        lines.append('## 🎯 Ostatnie decyzje')
        for d in data['decisions']:
            lines.append(f'- **{d["date"]}**: {d["text"]}')
        lines.append('')

    # Action items
    if data.get('open_action_items'):
        lines.append('## ⚡ Otwarte action items (vault owner)')
        for item in data['open_action_items']:
            lines.append(f'- {item}')
        lines.append('')

    # Problems
    if data.get('open_problems'):
        lines.append('## ⚠️ Otwarte problemy')
        for p in data['open_problems']:
            lines.append(f'- **{p["date"]}**: {p["text"]}')
        lines.append('')

    # Key people
    if data.get('key_people'):
        lines.append('## 👥 Kluczowe osoby')
        for p in data['key_people']:
            lines.append(f'- [[{p["slug"]}]] ({p["meetings"]} spotkań)')
        lines.append('')

    # Timeline
    tl = data.get('timeline', {})
    if tl:
        lines.append('## 📊 Timeline')
        lines.append(f'- Pierwsze spotkanie: {tl.get("first", "?")}')
        lines.append(f'- Ostatnie: {tl.get("last", "?")}')
        lines.append(f'- Łącznie: {tl.get("total_meetings", 0)} spotkań')
        lines.append('')

    lines.append(f'> Wygenerowano {datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")}')
    lines.append('')

    return '\n'.join(lines) + '\n'


def _resolve_client_from_project(tenant_id: str, project_slug: str) -> str | None:
    """Resolve client_slug from project_slug via classified_as_project edges."""
    row = query_one(
        "SELECT e2.canonical_name FROM edges ep "
        "JOIN edges ec ON ec.src_id = ep.src_id AND ec.type = 'classified_as_client' "
        "JOIN entities e1 ON e1.id = ep.dst_id AND e1.canonical_name = %s "
        "JOIN entities e2 ON e2.id = ec.dst_id "
        "WHERE ep.tenant_id = %s AND ep.type = 'classified_as_project' LIMIT 1",
        project_slug, tenant_id,
    )
    return row['canonical_name'] if row else None


def _resolve_client_from_person(tenant_id: str, person_slug: str) -> str | None:
    """Resolve client_slug from person_slug via attended_meeting edges."""
    row = query_one(
        "SELECT ent.canonical_name FROM edges e "
        "JOIN entities ent ON ent.id = e.dst_id "
        "WHERE e.type = 'classified_as_client' AND e.tenant_id = %s "
        "  AND e.src_id IN ("
        "    SELECT src_id FROM edges "
        "    WHERE type = 'attended_meeting' AND tenant_id = %s "
        "      AND dst_id = (SELECT id FROM entities WHERE canonical_name = %s AND type = 'person')"
        "  ) LIMIT 1",
        tenant_id, tenant_id, person_slug,
    )
    return row['canonical_name'] if row else None

# ==========================================================================
# F16 — Live Sections Scheduler + Runner
# ==========================================================================

import fcntl
import json
import time as _time  # noqa: F401
from collections import defaultdict

from croniter import croniter

_LIVE_SECTION_MIN_INTERVAL_S = 300  # at least 5 min between re-runs of the same section
_EVENT_GRACE_S = 120  # event older than 2 min → skip


def _load_live_sections_registry() -> list[dict]:
    """Load live sections from config/live_sections.yaml registry.

    Registry sections don't have a natural vault file (e.g. _home.md sections).
    Their runtime state (lastRunAt, lastRunSummary) is read from the
    live_section_runs telemetry table.
    """
    import yaml
    registry_path = Path(__file__).resolve().parent.parent / 'config' / 'live_sections.yaml'
    if not registry_path.exists():
        return []

    try:
        cfg = yaml.safe_load(registry_path.read_text(encoding='utf-8')) or {}
    except Exception:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
        logger.warning("Cannot parse config/live_sections.yaml")
        return []

    entries = cfg.get('sections') or []
    if not isinstance(entries, list):
        return []

    sections = []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get('id'):
            continue
        sid = entry['id']
        target = entry.get('target_file', '')

        # Read lastRunAt from telemetry table (best-effort)
        last_run_at = None
        last_summary = ''
        try:
            row = query_one(
                "SELECT started_at, content_after_hash "
                "FROM live_section_runs "
                "WHERE tenant_id = %s AND section_id = %s AND status = 'success' "
                "ORDER BY started_at DESC LIMIT 1",
                get_tenant_id(), sid,
            )
            if row:
                last_run_at = row['started_at'].isoformat() if row.get('started_at') else None
        except Exception:  # noqa: BLE001, S110 — failure is ignored on purpose; narrowing would change behavior
            pass

        sections.append({
            'file_path': target,
            'section_id': sid,
            'instruction': entry.get('instruction', ''),
            'triggers': entry.get('triggers', []),
            'section': entry.get('section', ''),
            'active': entry.get('active', True),
            'lastRunAt': last_run_at,
            'lastRunSummary': last_summary,
            '_registry': True,
        })

    return sections


def scan_vault_for_live_sections(vault_root: str | None = None) -> list[dict]:
    """Scan vault for .md files with `live:` frontmatter + registry YAML.

    Returns merged list of live section configs.
    """
    import yaml

    if vault_root is None:
        vault_root = _resolve_vault_root()
    vault = Path(vault_root)
    sections = []

    for md_file in vault.rglob('*.md'):
        try:
            with open(md_file, 'r') as f:
                content = f.read()
        except (OSError, PermissionError):
            continue

        if not content.startswith('---'):
            continue

        parts = content.split('---', 2)
        if len(parts) < 3:
            continue

        try:
            fm = yaml.safe_load(parts[1])
        except Exception:  # noqa: BLE001, S112 — skip the bad item and carry on; narrowing would change behavior
            continue
        if not isinstance(fm, dict):
            continue

        live_entries = fm.get('live')
        if not isinstance(live_entries, list):
            continue

        rel_path = str(md_file.relative_to(vault))
        for entry in live_entries:
            if not isinstance(entry, dict) or not entry.get('id'):
                continue
            sections.append({
                'file_path': rel_path,
                'section_id': entry['id'],
                'instruction': entry.get('instruction', ''),
                'triggers': entry.get('triggers', []),
                'section': entry.get('section', ''),
                'active': entry.get('active', True),
                'lastRunAt': entry.get('lastRunAt'),
                'lastRunSummary': entry.get('lastRunSummary', ''),
            })

    # Merge registry sections
    registry_sections = _load_live_sections_registry()
    sections.extend(registry_sections)

    return sections


def process_live_sections(
    *,
    vault_root: str | None = None,
    trigger_type: str = 'cron',
    event_source: str | None = None,
    event_payload: str | None = None,
) -> dict:
    """Main entry point — scan, check triggers, run due sections.

    Called by:
    - systemd timer (every 15 min) → trigger_type='cron'
    - post-ingest hook → trigger_type='event' with event_source
    - CLI → trigger_type='manual'

    Returns {processed: int, skipped: int, errors: int, results: [...]}
    """
    get_tenant_id()
    now = datetime.now(UTC)

    if vault_root is None:
        vault_root = _resolve_vault_root()

    all_sections = scan_vault_for_live_sections(vault_root)
    due = []
    skipped = 0

    for ls in all_sections:
        if not ls['active']:
            skipped += 1
            continue

        if trigger_type == 'event':
            # Check if this section has matching event trigger
            has_match = False
            for tr in ls.get('triggers', []):
                if (tr.get('type') == 'event' and event_source
                        and _event_matches(tr.get('match', ''), event_source, event_payload)):
                    has_match = True
                    break
            if not has_match:
                skipped += 1
                continue
        elif trigger_type in ('cron', 'window'):
            # Check if any timed trigger is due
            is_due = False
            for tr in ls.get('triggers', []):
                if tr.get('type') in ('cron', 'window') and _is_trigger_due(tr, ls.get('lastRunAt'), now):
                    is_due = True
                    break
            if not is_due:
                skipped += 1
                continue

        # Rate limit — don't re-run within _LIVE_SECTION_MIN_INTERVAL_S
        if ls.get('lastRunAt'):
            try:
                last = datetime.fromisoformat(str(ls['lastRunAt']))
                if (now - last).total_seconds() < _LIVE_SECTION_MIN_INTERVAL_S:
                    skipped += 1
                    continue
            except (ValueError, TypeError):
                pass

        due.append(ls)

    results = []
    errors = 0

    for ls in due:
        try:
            res = _run_live_section(ls, vault_root, now, trigger_type, event_source)
            results.append(res)
        except Exception as exc:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
            logger.error("Live section %s:%s failed: %s", ls['file_path'], ls['section_id'], exc)
            errors += 1
            results.append({'file': ls['file_path'], 'section_id': ls['section_id'], 'status': 'error', 'error': str(exc)})

    return {
        'processed': len(results),
        'skipped': skipped,
        'errors': errors,
        'results': results,
    }


def _run_live_section(
    ls: dict, vault_root: str, now: datetime,
    trigger_type: str, event_source: str | None,
) -> dict:
    """Execute one live section: compute new content, replace H2 section, write back.

    Registry sections (from config/live_sections.yaml) trigger recompilation
    of the relevant domain module instead of direct file editing.
    """
    # Dispatch registry sections to module recompilation
    if ls.get('_registry'):
        return _run_registry_section(ls, now, trigger_type, event_source)

    file_path = Path(vault_root) / ls['file_path']
    section_heading = ls.get('section', '')
    instruction = ls.get('instruction', '')

    # Compute new content
    new_content = _compute_section_content(instruction, ls)

    # Read file
    try:
        with open(file_path, 'r') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                content = f.read()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except Exception:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
        return {'file': ls['file_path'], 'section_id': ls['section_id'], 'status': 'error', 'error': 'Cannot read file'}

    old_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

    # Replace H2 section
    if section_heading:
        new_content_full = _replace_h2_section(content, section_heading, new_content)
    else:
        new_content_full = content  # no section specified → skip

    new_hash = hashlib.sha256(new_content_full.encode()).hexdigest()[:16]
    if old_hash == new_hash:
        return {'file': ls['file_path'], 'section_id': ls['section_id'], 'status': 'skipped', 'reason': 'unchanged'}

    # Atomic write
    try:
        with open(file_path, 'r+') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.seek(0)
                f.write(new_content_full)
                f.truncate()
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except Exception as exc:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
        return {'file': ls['file_path'], 'section_id': ls['section_id'], 'status': 'error', 'error': str(exc)}

    # Update frontmatter lastRunAt
    _update_last_run(file_path, ls['section_id'], now, new_content[:80])

    # Telemetry
    try:
        execute(
            "INSERT INTO live_section_runs "
            "(tenant_id, file_path, section_id, trigger_type, event_source, "
            " status, content_before_hash, content_after_hash, started_at, finished_at) "
            "VALUES (%s, %s, %s, %s, %s, 'success', %s, %s, %s, NOW())",
            get_tenant_id(),
            ls['file_path'], ls['section_id'], trigger_type, event_source,
            old_hash, new_hash, now,
        )
    except Exception:  # noqa: BLE001, S110 — failure is ignored on purpose; narrowing would change behavior
        pass

    return {'file': ls['file_path'], 'section_id': ls['section_id'], 'status': 'success'}


def _run_registry_section(
    ls: dict, now: datetime,
    trigger_type: str, event_source: str | None,
) -> dict:
    """Execute a registry live section by triggering domain module recompilation.

    Registry sections (from config/live_sections.yaml) don't edit files directly.
    Instead they trigger recompilation of the relevant wiki module.
    """
    sid = ls['section_id']
    target = ls.get('file_path', '')
    old_hash = ''
    new_hash = ''

    # Map section_id → compiler domain.
    domain_map = {
        'home-news-pulse': 'home',
        'home-today': 'home',
        'acme-dashboard': 'acme',   # F21.5 — ACME Notion dashboard
        'acme-projects-dashboard': 'acme-projects',  # F30 — per-project pages
    }
    domain = domain_map.get(sid, 'home')

    try:
        if domain == 'acme':
            # F21.5 — recompile only the ACME Notion dashboard block in
            # wiki/work/clients/acme.md (splices into the USER_NOTES region,
            # preserves the rest of the page).
            from exocortex.wiki_compiler import compile_acme_dashboard
            changed = compile_acme_dashboard(get_tenant_id(), since=None)
        elif domain == 'acme-projects':
            # F30 — regenerate wiki/work/projects/acme/{slug}.md ×12 +
            # _index.md. No partial section splice — full file rewrites
            # with USER_NOTES markers preserved by the compiler itself.
            from exocortex.compile_acme_projects import compile_acme_projects
            result = compile_acme_projects()
            changed = result.get('written', 0) > 0
        else:
            from exocortex.wiki_compiler import compile_home_module
            compile_home_module(get_tenant_id(), since=None)
            changed = True
    except Exception as exc:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
        logger.error("Registry section %s recompile failed: %s", sid, exc)
        return {
            'file': target, 'section_id': sid,
            'status': 'error', 'error': str(exc),
        }

    # Telemetry
    try:
        execute(
            "INSERT INTO live_section_runs "
            "(tenant_id, file_path, section_id, trigger_type, event_source, "
            " status, content_before_hash, content_after_hash, started_at, finished_at) "
            "VALUES (%s, %s, %s, %s, %s, 'success', %s, %s, %s, NOW())",
            get_tenant_id(),
            target, sid, trigger_type, event_source,
            old_hash, new_hash, now,
        )
    except Exception:  # noqa: BLE001, S110 — failure is ignored on purpose; narrowing would change behavior
        pass

    return {'file': target, 'section_id': sid,
            'status': 'success' if (domain != 'acme' or changed) else 'skipped'}


def _replace_h2_section(content: str, heading: str, replacement: str) -> str:
    """Replace content of H2 section identified by `heading` (e.g. '## Aktywne')."""
    # Normalize heading — strip leading '## ' if present
    h2 = heading.removeprefix('## ').strip()
    pattern = re.compile(
        rf'^(## {re.escape(h2)}\s*\n)(.*?)(?=\n## |\n# |\Z)',
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(content)
    if not match:
        # Section doesn't exist — append after frontmatter
        parts = content.split('---', 2)
        if len(parts) >= 3:
            # Insert after last frontmatter line
            fm_end = content.index('---', content.index('---') + 3) + 3
            return content[:fm_end] + f'\n\n## {h2}\n\n{replacement}\n' + content[fm_end:]
        else:
            return content + f'\n\n## {h2}\n\n{replacement}\n'

    heading_line = match.group(1)
    match.group(2)
    start = match.start()
    end = match.end()
    return content[:start] + heading_line + replacement + content[end:]


def _update_last_run(file_path: Path, section_id: str, now: datetime, summary: str) -> None:
    """Update lastRunAt in frontmatter `live:` array. Best-effort."""
    import yaml
    try:
        with open(file_path, 'r+') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                content = f.read()
                if not content.startswith('---'):
                    return
                parts = content.split('---', 2)
                if len(parts) < 3:
                    return
                fm = yaml.safe_load(parts[1])
                if not isinstance(fm, dict):
                    return
                live_entries = fm.get('live', [])
                for entry in live_entries:
                    if entry.get('id') == section_id:
                        entry['lastRunAt'] = now.isoformat()
                        entry['lastRunSummary'] = summary
                        break
                new_fm = yaml.dump(fm, allow_unicode=True, sort_keys=False)
                new_content = '---\n' + new_fm + '---\n' + parts[2]
                f.seek(0)
                f.write(new_content)
                f.truncate()
                f.flush()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except Exception:  # noqa: BLE001, S110 — failure is ignored on purpose; narrowing would change behavior
        pass


def _compute_section_content(instruction: str, ls: dict) -> str:
    """Compute new content for a live section based on instruction.

    Currently supports:
    - 'action-items' / 'Moje TODO' → render active action items
    - 'provider-health' → render provider health table
    - 'pipeline' → render pipeline status
    - Otherwise → placeholder
    """
    tid = get_tenant_id()

    if 'action' in instruction.lower() or 'todo' in instruction.lower():
        from exocortex.action_items import me_owner_slugs, parse_action_items
        rows = query(
            "SELECT id, metadata FROM thoughts "
            "WHERE tenant_id = %s AND thought_type = 'work_meeting_note' "
            "AND created_at >= NOW() - INTERVAL '30 days'",
            tid,
        )
        items = []
        for r in rows:
            try:
                for it in parse_action_items(r['metadata']):
                    if it.status == 'open' and it.owner_slug in me_owner_slugs():
                        items.append(it.content)
            except Exception:  # noqa: BLE001, S112 — skip the bad item and carry on; narrowing would change behavior
                continue
        return '\n'.join(f'- {i}' for i in items[:20]) + '\n'

    if 'provider' in instruction.lower() or 'llm' in instruction.lower():
        lines = ['| Provider | Model | Error% |', '|----------|-------|--------|']
        try:
            rows = query(
                "SELECT provider, model, count(*) AS calls "
                "FROM llm_provider_runs "
                "WHERE tenant_id = %s AND started_at >= NOW() - INTERVAL '24 hours' "
                "GROUP BY provider, model",
                tid,
            )
            err_rows = query(
                "SELECT provider, count(*) AS errors "
                "FROM provider_errors "
                "WHERE tenant_id = %s AND started_at >= NOW() - INTERVAL '24 hours' "
                "GROUP BY provider",
                tid,
            )
            err_map = {r['provider']: int(r['errors']) for r in err_rows}
            for r in rows:
                p = r['provider']
                errors = err_map.get(p, 0)
                total = int(r['calls']) + errors
                er = round(errors / total * 100, 1) if total > 0 else 0
                flag = '🔴' if er > 30 else '🟡' if er > 10 else '🟢'
                lines.append(f'| {p} | {r["model"] or "?"} | {flag} {er}% |')
        except Exception:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
            lines.append('| — | — | — |')
        return '\n'.join(lines) + '\n'

    if 'pipeline' in instruction.lower():
        lines = ['| Worker | Status | 24h OK | 24h Fail |', '|--------|--------|--------|----------|']
        try:
            rows = query(
                "SELECT worker, status, "
                "  count(*) FILTER (WHERE status = 'success') AS ok, "
                "  count(*) FILTER (WHERE status != 'success') AS fail "
                "FROM pipeline_runs "
                "WHERE tenant_id = %s AND started_at >= NOW() - INTERVAL '24 hours' "
                "GROUP BY worker, status",
                tid,
            )
            workers = defaultdict(lambda: {'ok': 0, 'fail': 0})
            for r in rows:
                w = workers[r['worker']]
                w['ok'] += int(r['ok'])
                w['fail'] += int(r['fail'])
            for wk, st in sorted(workers.items()):
                icon = '✅' if st['fail'] == 0 else '❌'
                lines.append(f'| {wk} | {icon} | {st["ok"]} | {st["fail"]} |')
        except Exception:  # noqa: BLE001, S110 — failure is ignored on purpose; narrowing would change behavior
            pass
        return '\n'.join(lines) + '\n'

    return f'_Live section: {instruction}_\n'


def _is_trigger_due(trigger: dict, last_run: str | None, now: datetime) -> bool:
    """Check if a timed trigger is due."""
    ttype = trigger.get('type', '')

    if ttype == 'cron':
        expr = trigger.get('expression', '')
        if not expr:
            return False
        try:
            c = croniter(expr, now)
            prev = c.get_prev(datetime)
            if last_run:
                try:
                    last = datetime.fromisoformat(str(last_run))
                    return prev > last and (now - prev).total_seconds() < _EVENT_GRACE_S
                except (ValueError, TypeError):
                    return True
            return True
        except Exception:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
            return False

    if ttype == 'window':
        start_str = trigger.get('start', trigger.get('startTime', ''))
        end_str = trigger.get('end', trigger.get('endTime', ''))
        if not start_str or not end_str:
            return False
        try:
            start_h, start_m = map(int, start_str.split(':'))
            end_h, end_m = map(int, end_str.split(':'))
            now_min = now.hour * 60 + now.minute
            start_min = start_h * 60 + start_m
            end_min = end_h * 60 + end_m

            if not (start_min <= now_min < end_min):
                return False

            # Check if already run today
            if last_run:
                last = datetime.fromisoformat(str(last_run))
                if last.date() == now.date():
                    return False
            return True
        except Exception:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
            return False

    return False


_EVENT_ROUTING_SYSTEM_PROMPT = """\
You are a routing classifier. Your job: decide which live sections (tracks)
might be relevant to incoming events.

RULES:
- Prefer false positives over false negatives. If in doubt, include the track.
- A track is relevant if the event content plausibly affects what the track shows.
- Ignore tracks whose match criteria clearly doesn't relate to the event.
- Be conservative — most events should match 0-2 tracks.

Output: JSON object with "candidates" array of {eventIndex, trackIndex} pairs.\
"""


def _build_event_routing_prompt(events: list[dict], tracks: list[dict]) -> str:
    """Build Pass1 classifier prompt: list events + tracks for batch matching."""
    lines = ["# Events"]
    for i, ev in enumerate(events):
        source = ev['data'].get('source', 'unknown')
        payload = ev['data'].get('payload', '')[:500]
        lines.append(f"{i}. [{source}] {payload}")

    lines.append("")
    lines.append("# Tracks")
    for i, t in enumerate(tracks):
        tr_match = []
        for tr in t.get('triggers', []):
            if tr.get('type') == 'event':
                tr_match.append(tr.get('match', ''))
        criteria = '; '.join(tr_match) or '(no event criteria)'
        lines.append(f"{i}. {t['section_id']} ({t.get('file_path', '')}): {criteria}")

    return '\n'.join(lines)


def _event_classify_batch(events: list[dict], tracks: list[dict]) -> list[dict]:
    """Pass1: batch LLM classifier for event→track matching.

    Falls back to simple substring matching if LLM call fails.
    Returns list of {eventIndex, trackIndex} candidates.
    """
    if not tracks or not events:
        return []

    # Try LLM classifier
    try:
        # Use the _common.call_tool wrapper which works correctly
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from exocortex.processors._common import call_tool

        tool_schema: dict = {
            'name': 'classify_events',
            'description': 'Match events to relevant tracks',
            'parameters': {
                'type': 'object',
                'properties': {
                    'candidates': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'eventIndex': {'type': 'integer'},
                                'trackIndex': {'type': 'integer'},
                            },
                            'required': ['eventIndex', 'trackIndex'],
                        },
                    },
                },
                'required': ['candidates'],
            },
        }

        prompt = _build_event_routing_prompt(events, tracks)
        tool_input, _usage = call_tool(
            system_prompt=_EVENT_ROUTING_SYSTEM_PROMPT,
            user_prompt=prompt,
            tool_schema=tool_schema,
            max_tokens=500,
            _use_case='second_brain.F20_event_routing',
        )
        candidates = tool_input.get('candidates', []) if isinstance(tool_input, dict) else []
        if candidates:
            logger.info(
                "F20 Pass1: %d events × %d tracks → %d candidates (LLM)",
                len(events), len(tracks), len(candidates),
            )
            return candidates
    except Exception as exc:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
        logger.warning("F20 Pass1 LLM failed, falling back to substring: %s", exc)

    # Fallback: simple substring matching (one event at a time)
    candidates = []
    for ei, ev in enumerate(events):
        source = ev['data'].get('source', '')
        payload = ev['data'].get('payload', '') or ''
        for ti, track in enumerate(tracks):
            for tr in track.get('triggers', []):
                if tr.get('type') == 'event':
                    match_criteria = tr.get('match', '')
                    if _event_matches(match_criteria, source, payload):
                        candidates.append({'eventIndex': ei, 'trackIndex': ti})
                        break

    logger.info(
        "F20 Pass1 fallback: %d events × %d tracks → %d candidates (substring)",
        len(events), len(tracks), len(candidates),
    )
    return candidates


def _event_matches(match_criteria: str, event_source: str, event_payload: str | None) -> bool:
    """Check if an event trigger matches. Simple substring match."""
    if not match_criteria or not event_source:
        return False
    return event_source.lower() in match_criteria.lower() or match_criteria.lower() in event_source.lower()


def emit_live_event(event_source: str, event_payload: str | None = None) -> None:
    """Emit a live section event — called from post-ingest hooks.

    Writes event to events file for the scheduler to pick up.
    """
    vault_root = _resolve_vault_root()
    events_dir = Path(vault_root) / '.live_section_events'
    events_dir.mkdir(parents=True, exist_ok=True)

    event_id = datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')
    event_file = events_dir / f'{event_id}.json'
    with open(event_file, 'w') as f:
        json.dump({
            'id': event_id,
            'source': event_source,
            'payload': event_payload,
            'created_at': datetime.now(UTC).isoformat(),
        }, f)

    logger.info("Live section event emitted: %s → %s", event_source, event_file)


def process_live_events(vault_root: str | None = None) -> int:
    """Process pending live section event files. Called by scheduler.

    F20: uses batch LLM classification (Pass1) to decide which tracks are
    relevant, then runs only matched sections (Pass2 deterministic).
    Falls back to simple substring matching if LLM call fails.
    """
    if vault_root is None:
        vault_root = _resolve_vault_root()
    events_dir = Path(vault_root) / '.live_section_events'
    if not events_dir.exists():
        return 0

    processed = 0
    now = datetime.now(UTC)
    event_files = sorted(events_dir.glob('*.json'))

    if not event_files:
        return 0

    # Collect valid events within grace window
    events: list[dict] = []
    for ev_file in event_files:
        try:
            with open(ev_file) as f:
                ev = json.load(f)
        except Exception:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
            ev_file.unlink(missing_ok=True)
            continue

        try:
            created = datetime.fromisoformat(ev['created_at'])
            if (now - created).total_seconds() > _EVENT_GRACE_S:
                ev_file.unlink(missing_ok=True)
                continue
        except (ValueError, KeyError):
            ev_file.unlink(missing_ok=True)
            continue

        events.append({'file': ev_file, 'data': ev})

    if not events:
        return 0

    # Get all tracks with event triggers
    all_sections = scan_vault_for_live_sections(vault_root)
    event_tracks = [
        s for s in all_sections
        if s.get('active', True) and any(
            tr.get('type') == 'event'
            for tr in s.get('triggers', [])
        )
    ]

    # F20: Pass1 — batch LLM classifier (fallback to substring)
    candidates = _event_classify_batch(events, event_tracks)

    # Process each candidate
    for c in candidates:
        ev_idx = c.get('eventIndex', c.get('event_index', 0))
        track_idx = c.get('trackIndex', c.get('track_index', 0))

        if ev_idx >= len(events) or track_idx >= len(event_tracks):
            continue

        ev = events[ev_idx]
        event_tracks[track_idx]

        result = process_live_sections(
            vault_root=vault_root,
            trigger_type='event',
            event_source=ev['data']['source'],
            event_payload=ev['data'].get('payload'),
        )
        processed += result['processed']

    # Delete processed event files
    for ev in events:
        ev['file'].unlink(missing_ok=True)

    return processed


# ── F19 helpers for Live Sections UI ──────────────────────────────────


def scan_all_live_sections() -> list[dict]:
    """Return merged list of all live sections (vault + registry) with status.

    Used by MCP `list_live_sections` and wiki_compiler dashboard.
    """
    sections = scan_vault_for_live_sections()
    tid = get_tenant_id()

    # Enrich with last run status from telemetry
    for s in sections:
        sid = s['section_id']
        try:
            row = query_one(
                "SELECT status, started_at, content_after_hash "
                "FROM live_section_runs "
                "WHERE tenant_id = %s AND section_id = %s "
                "ORDER BY started_at DESC LIMIT 1",
                tid, sid,
            )
            if row:
                if s.get('lastRunAt') is None and row.get('started_at'):
                    s['lastRunAt'] = row['started_at'].isoformat()
                s['last_status'] = row.get('status', '?')
        except Exception:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
            s.setdefault('last_status', '?')

        s.setdefault('last_status', '?')
        s.setdefault('lastRunAt', '')

    return sections


def get_live_section_history(section_id: str, limit: int = 10) -> list[dict]:
    """Return recent execution history for a live section."""
    try:
        rows = query(
            "SELECT trigger_type, event_source, status, "
            "  started_at, finished_at, error_message "
            "FROM live_section_runs "
            "WHERE tenant_id = %s AND section_id = %s "
            "ORDER BY started_at DESC LIMIT %s",
            get_tenant_id(), section_id, limit,
        )
        return [
            {
                'trigger': r['trigger_type'],
                'event': r.get('event_source') or '',
                'status': r['status'],
                'started_at': r['started_at'].isoformat() if r.get('started_at') else '',
                'error': r.get('error_message') or '',
            }
            for r in rows
        ]
    except Exception:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
        return []


def run_live_section_by_id(section_id: str) -> dict:
    """Find and execute a live section by ID (manual trigger).

    Used by MCP `trigger_live_section` tool.
    """
    sections = scan_vault_for_live_sections()
    match = None
    for s in sections:
        if s['section_id'] == section_id:
            match = s
            break

    if not match:
        return {'status': 'error', 'error': f'Section {section_id!r} not found'}

    vault_root = _resolve_vault_root()
    from datetime import datetime
    now = datetime.now(UTC)

    try:
        res = _run_live_section(match, vault_root, now, 'manual', None)
        return {
            'section_id': section_id,
            'status': res.get('status', 'error'),
            'file': res.get('file', ''),
            'error': res.get('error', ''),
        }
    except Exception as exc:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
        return {'section_id': section_id, 'status': 'error', 'error': str(exc)}
