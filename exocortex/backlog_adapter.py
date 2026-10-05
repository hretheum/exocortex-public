# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/backlog_adapter.py — F26.1: parse backlog YAML frontmatter and infer Gantt dates.
from __future__ import annotations

import math
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

from exocortex.settings import get_settings

FRONTMATTER_RE = re.compile(r'^---\n(.*?)\n---', re.DOTALL)


def _vault_path() -> Path:
    return get_settings().vault_path


def _backlog_dir() -> Path:
    return _vault_path() / '_ Second Brain' / 'backlog' / '_second-brain'


# How many effective work hours per day (realistic context-switching included)
HOURS_PER_DAY = 6

# Default duration when estimate_hours is missing
DEFAULT_DAYS = 3


def _views() -> dict[str, tuple[Path, str]]:
    return {
        'second-brain': (_backlog_dir(), 'phase'),
    }


def __getattr__(name):
    # Surface AttributeError (not pydantic ValidationError) so `hasattr()`
    # returns False when EXOCORTEX_VAULT_PATH is unset.
    if name == 'VAULT_PATH':
        try:
            return _vault_path()
        except Exception as exc:
            raise AttributeError(
                f"VAULT_PATH unavailable: {exc}. Set EXOCORTEX_VAULT_PATH."
            ) from exc
    if name == 'BACKLOG_DIR':
        try:
            return _backlog_dir()
        except Exception as exc:
            raise AttributeError(
                f"BACKLOG_DIR unavailable: {exc}. Set EXOCORTEX_VAULT_PATH."
            ) from exc
    if name == 'VIEWS':
        try:
            return _views()
        except Exception as exc:
            raise AttributeError(
                f"VIEWS unavailable: {exc}. Set EXOCORTEX_VAULT_PATH."
            ) from exc
    raise AttributeError(name)


# ─────────────────────────── Parsing ───────────────────────────

def parse_frontmatter(filepath: Path) -> dict[str, Any] | None:
    """Extract YAML frontmatter from a markdown file."""
    try:
        text = filepath.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return None

    m = FRONTMATTER_RE.search(text)
    if not m:
        return None

    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None

    if not isinstance(data, dict):
        return None

    return data


def load_backlog_tasks(backlog_dir: Path | None = None) -> dict[str, dict]:
    """Load all backlog tasks from markdown files, keyed by task id."""
    if backlog_dir is None:
        backlog_dir = _backlog_dir()
    tasks: dict[str, dict] = {}

    if not backlog_dir.is_dir():
        return tasks

    for fp in backlog_dir.glob('*.md'):
        fm = parse_frontmatter(fp)
        if not fm:
            continue

        task_id = fm.get('id', '').strip()
        if not task_id:
            continue

        # Normalise fields — handle empty string as None for completed
        completed_val = fm.get('completed')
        if completed_val == '':
            completed_val = None

        task = {
            'id': task_id,
            'title': fm.get('title', task_id),
            'status': fm.get('status', 'pending'),
            'priority': fm.get('priority', 'MED'),
            'phase': fm.get('phase', ''),
            'phase_order': fm.get('phase_order', ''),
            'target_quarter': fm.get('target_quarter', ''),
            'pillar': fm.get('pillar', ''),
            'estimate_hours': _to_float(fm.get('estimate_hours')),
            'actual_hours': _to_float(fm.get('actual_hours')),
            'blocked_by': _to_list(fm.get('blockedBy', fm.get('blocked_by', []))),
            'created': _to_date(fm.get('created')),
            'completed': _to_date(completed_val),
            'projects': _to_list(fm.get('projects', [])),
            'area': fm.get('area', ''),
            'tags': _to_list(fm.get('tags', [])),
            'file_path': str(fp),
            'source': 'backlog',
        }

        tasks[task_id] = task

    return tasks


# ─────────────────────────── Date Inference ─────────────────────

def add_working_days(start: date, days: int) -> date:
    """Add N working days to start, skipping weekends (Sat/Sun)."""
    if days <= 0:
        return start

    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Mon=0 .. Fri=4
            added += 1
    return current


def hours_to_working_days(hours: float) -> int:
    """Convert estimate_hours to working days."""
    if hours <= 0:
        return 1  # milestone / zero-estimate = 1 day
    return max(1, math.ceil(hours / HOURS_PER_DAY))


def resolve_dates(
    task: dict,
    all_tasks: dict[str, dict],
    _visited: set[str] | None = None,
    _stack: set[str] | None = None,
) -> tuple[date, date]:
    """
    Resolve (start_date, end_date) for a task, considering dependencies.

    - done tasks: start=created, end=completed (or inferred if missing)
    - in-progress: start=created, end=start+estimate
    - pending/blocked: start=max(blocker ends)+1d, end=start+estimate
    - Cycle detection: if cycle found, fallback to created → created+3d
    """
    task_id = task['id']

    # Cycle detection
    if _stack is None:
        _stack = set()
    if _visited is None:
        _visited = set()

    if task_id in _stack:
        # Cycle detected — fallback
        start = task['created'] or date.today()  # noqa: DTZ011 — local calendar date; an aware date would change behavior
        end = add_working_days(start, DEFAULT_DAYS)
        return start, end

    if task_id in _visited:
        # Already resolved (memoised in task dict)
        cached_start = task.get('_resolved_start')
        cached_end = task.get('_resolved_end')
        if cached_start and cached_end:
            return cached_start, cached_end

    _stack.add(task_id)

    status = task['status']
    created = task['created'] or date.today()  # noqa: DTZ011 — local calendar date; an aware date would change behavior
    completed = task['completed']
    estimate_days = hours_to_working_days(task['estimate_hours'] or 0)

    # ── Done / archived tasks (use actual completed date) ─────
    if status in ('done', 'archive', 'complete') and completed:
        start = created
        end = completed
        task['_resolved_start'] = start
        task['_resolved_end'] = end
        _stack.discard(task_id)
        _visited.add(task_id)
        return start, end

    # ── Done/archived but missing completed date ──────────────
    if status in ('done', 'archive', 'complete') and not completed:
        start = created
        end = add_working_days(start, estimate_days)
        task['_resolved_start'] = start
        task['_resolved_end'] = end
        _stack.discard(task_id)
        _visited.add(task_id)
        return start, end

    # ── Deferred ──────────────────────────────────────────────
    if status == 'deferred':
        start = created
        end = add_working_days(start, estimate_days)
        task['_resolved_start'] = start
        task['_resolved_end'] = end
        _stack.discard(task_id)
        _visited.add(task_id)
        return start, end

    # ── Pending / blocked / in-progress — resolve blockers ───
    blocker_ends: list[date] = []
    for blocker_id in task['blocked_by']:
        blocker = all_tasks.get(blocker_id)
        if blocker:
            _, bend = resolve_dates(blocker, all_tasks, _visited, _stack)
            blocker_ends.append(bend)
        # Orphan blocker (not in backlog) — ignored

    if blocker_ends:
        # Start = day after latest blocker ends
        latest_blocker = max(blocker_ends)
        start = latest_blocker + timedelta(days=1)
        # Adjust to working day if blocker ends on weekend
        while start.weekday() >= 5:
            start += timedelta(days=1)
    else:
        start = created

    # End = start + estimate
    end = add_working_days(start, estimate_days)

    task['_resolved_start'] = start
    task['_resolved_end'] = end
    _stack.discard(task_id)
    _visited.add(task_id)

    return start, end


# ─────────────────────────── Public API ────────────────────────

def get_gantt_entries(
    view: str = 'second-brain',
    team: list[str] | None = None,
    phases: list[str] | None = None,
    statuses: list[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict]:
    """
    Load backlog tasks, resolve dates, return Gantt-ready entries.

    Args:
        view: Named view ('second-brain')
              Determines folder and group_by field.
        team: list of person names (not used for backlog — all tasks are personal)
        phases: list of phase IDs (e.g. ['F26', 'F25'] or ['Q3-26', 'Q4-26'])
        statuses: list of statuses (e.g. ['pending', 'in-progress'])
        date_from/date_to: filter by end date

    Returns:
        List of Gantt entries with resolved dates.
    """
    backlog_dir, group_by = _views().get(view, (_backlog_dir(), 'phase'))
    tasks = load_backlog_tasks(backlog_dir)

    # Resolve dates for all tasks (handles dependencies)
    visited: set[str] = set()
    for task in tasks.values():
        resolve_dates(task, tasks, visited)

    # Build entries
    entries: list[dict] = []
    for task in tasks.values():
        start = task.get('_resolved_start')
        end = task.get('_resolved_end')
        if not start or not end:
            continue

        # Apply filters
        if phases and task['phase'] not in phases:
            continue
        if statuses and task['status'] not in statuses:
            continue
        if date_from and end < date_from:
            continue
        if date_to and start > date_to:
            continue

        # Strip wiki links from projects for display
        projects = [p.strip('[]') for p in task['projects']]

        entries.append({
            'id': task['id'],
            'title': task['title'],
            'status': task['status'],
            'priority': task['priority'],
            'phase': task['phase'],
            'phase_order': task['phase_order'],
            'target_quarter': task['target_quarter'],
            'pillar': task['pillar'],
            'projects': projects,
            'start': start.isoformat(),
            'end': end.isoformat(),
            'estimate_hours': task['estimate_hours'],
            'actual_hours': task['actual_hours'],
            'blocked_by': task['blocked_by'],
            'source': 'backlog',
            'file_path': task['file_path'],
            'group_by': group_by,
        })

    # Sort by phase_order (numeric), then start date, then id
    entries.sort(key=lambda e: (
        _safe_int(e.get('phase_order', '')),
        e['start'],
        e['id'],
    ))

    return entries


def _safe_int(val: str) -> int:
    """Convert string to int safely, return 0 if invalid."""
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0


# ─────────────────────────── Helpers ───────────────────────────

def _to_float(val: Any) -> float | None:
    """Convert value to float, return None if invalid."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _to_date(val: Any) -> date | None:
    """Convert value to date, return None if invalid."""
    if val is None:
        return None
    s = str(val).strip().strip("'\"")
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def _to_list(val: Any) -> list[str]:
    """Convert value to list of strings."""
    if val is None:
        return []
    if isinstance(val, str):
        return [val] if val.strip() else []
    if isinstance(val, (list, tuple)):
        return [str(v).strip() for v in val if str(v).strip()]
    return [str(val)]


# ─────────────────────────── Mermaid Gantt Builder ─────────────

STATUS_MERMAID: dict[str, str] = {
    'pending': '',
    'in-progress': 'active,',
    'blocked': 'crit,',
    'done': 'done,',
    'deferred': 'crit,',
}


def build_mermaid_gantt(entries: list[dict], group_by: str) -> str:
    """Build Mermaid Gantt diagram text from entries."""
    if not entries:
        return 'gantt\n    title No tasks found\n'

    # Determine date range
    starts = [e['start'] for e in entries]
    ends = [e['end'] for e in entries]
    min(starts)
    max(ends)

    lines = [
        'gantt',
        '    title Project Timeline',
        '    dateFormat  YYYY-MM-DD',
        '    axisFormat  %b %d',
        '',
    ]

    # Group entries
    groups: dict[str, list[dict]] = {}
    for e in entries:
        key = e.get(group_by, 'Other') or 'Other'
        groups.setdefault(key, []).append(e)

    # Sort groups (quarters chronologically, phases alphabetically)
    def _group_sort_key(k: str) -> tuple:
        if group_by == 'target_quarter':
            # Q3 2026, Q4 2026, Q1 2027, Q2 2027
            m = re.match(r'Q(\d)\s+(\d{4})', k)
            if m:
                q, y = int(m.group(1)), int(m.group(2))
                return (y, q)
            return (9999, 99)
        return (k,)

    for group_key in sorted(groups.keys(), key=_group_sort_key):
        lines.append(f'    section {group_key}')
        for e in groups[group_key]:
            status_prefix = STATUS_MERMAID.get(e['status'], '')
            task_id = e['id'].replace('.', '_').replace('-', '_')
            title = e['title'].replace(':', ' ').replace(',', ' ')
            lines.append(
                f'        {title} :{status_prefix}{task_id}, {e["start"]}, {e["end"]}'
            )
        lines.append('')

    return '\n'.join(lines)
