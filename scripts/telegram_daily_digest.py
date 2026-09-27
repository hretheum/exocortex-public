#!/usr/bin/env -S python3.12
# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# scripts/telegram_daily_digest.py — F6.4.8 daily digest skript.
#
# One-shot generator of the user's morning brief. Aggregates:
#   1. Overnight email summaries (top N by action_item count) from
#      _journal/email-summaries/.
#   2. FRP queue top item by score (content_queue.status='scored', highest
#      sum of axes).
#   3. Work TODO this-week — top N action items where due_date in next 7 days.
#   4. (future) cross-domain pattern signals.
#
# OUTPUT: prints a Telegram-ready Markdown message to stdout. The user can
# pipe it through their bot, or schedule the whole script via Claude Routine
# for autonomous delivery.
#
# Usage:
#     python3 scripts/telegram_daily_digest.py                 # print to stdout
#     python3 scripts/telegram_daily_digest.py --top 5         # widen lists
#     python3 scripts/telegram_daily_digest.py --since 2026-05-01

from __future__ import annotations
import argparse
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(dotenv_path=Path(__file__).parent.parent / 'config' / '.env')

from exocortex.db import query   # noqa: E402

TENANT_ID = os.environ['TENANT_ID']
VAULT_PATH = Path(os.environ.get('VAULT_PATH', 'os.environ.get('EXOCORTEX_VAULT_PATH', '')')).expanduser()
JOURNAL_DIR = VAULT_PATH / '_journal' / 'email-summaries'

FRONTMATTER_RE = re.compile(r'^---\n(.*?)\n---', re.DOTALL)


# ─────────────────────────── Journal email-summary parsing ───────────────────────────

def _parse_journal_file(path: Path) -> Optional[dict]:
    text = path.read_text(encoding='utf-8', errors='replace')
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None
    body = text[m.end():]
    action_items = re.findall(r'^[ \t]*-[ \t]*\[\s\][ \t]*(?:\(\d{1,2}:\d{2}\))?\s*(.+)$',
                              body, re.MULTILINE)
    fm['_path'] = str(path.relative_to(VAULT_PATH))
    fm['_action_items_count'] = len(action_items)
    fm['_action_items'] = action_items
    return fm


def gather_email_summaries(since: datetime, top: int) -> list[dict]:
    if not JOURNAL_DIR.exists():
        return []
    items = []
    for path in JOURNAL_DIR.glob('*.md'):
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        if mtime < since:
            continue
        parsed = _parse_journal_file(path)
        if parsed is None:
            continue
        items.append(parsed)
    items.sort(key=lambda x: x.get('_action_items_count', 0), reverse=True)
    return items[:top]


# ─────────────────────────── FRP top item ───────────────────────────

def gather_frp_top(top: int = 1) -> list[dict]:
    rows = query(
        '''
        SELECT t.id, t.body, t.metadata->'frp_score' AS score
        FROM thoughts t
        WHERE t.tenant_id = %s
          AND t.thought_type = 'frp_source_scored'
          AND t.superseded_by IS NULL
          AND t.metadata ? 'frp_score'
        ORDER BY (
          (t.metadata->'frp_score'->>'accessibility')::int +
          (t.metadata->'frp_score'->>'consequence')::int -
          ABS((t.metadata->'frp_score'->>'horizon')::int - 5)
        ) DESC
        LIMIT %s
        ''',
        TENANT_ID, top,
    )
    return rows


# ─────────────────────────── Work TODO this-week ───────────────────────────

def gather_work_todo_this_week(top: int = 5) -> list[dict]:
    """Pull thoughts emitting action items with due_date <= now + 7d.

    We don't materialize action_items into DB rows — F2.3 parses on-demand —
    so this is a heuristic: pick recent meetings whose body contains
    `(MM:SS) ...` lines under unfinished `[ ]` checkboxes.
    """
    today = datetime.now(timezone.utc).date()
    week = today + timedelta(days=7)
    rows = query(
        '''
        SELECT id::text, body, metadata->>'title' AS title,
               metadata->>'meeting_id' AS meeting_id, created_at
        FROM thoughts
        WHERE tenant_id = %s
          AND thought_type = 'work_meeting_note'
          AND superseded_by IS NULL
          AND created_at >= %s
        ORDER BY created_at DESC
        LIMIT 50
        ''',
        TENANT_ID, datetime.combine(today - timedelta(days=14), datetime.min.time(),
                                    tzinfo=timezone.utc),
    )
    out = []
    for r in rows:
        body = r.get('body') or ''
        # Crude: count unchecked items.
        n_open = len(re.findall(r'^\s*-\s*\[\s\]', body, re.MULTILINE))
        if n_open == 0:
            continue
        out.append({
            'title': r.get('title') or '(untitled)',
            'meeting_id': r.get('meeting_id'),
            'open_action_items': n_open,
            'created_at': r['created_at'],
        })
        if len(out) >= top:
            break
    return out


# ─────────────────────────── Render Telegram message ───────────────────────────

def render_digest(*, summaries: list[dict], frp_top: list[dict],
                  work_todo: list[dict]) -> str:
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    parts = [f'*Daily brief — {today}*', '']

    if summaries:
        parts += ['*📧 Email summaries (top action-counts):*']
        for s in summaries:
            link = s.get('_path', '?')
            client = s.get('client') or '—'
            n = s.get('_action_items_count', 0)
            parts.append(f'• `{client}`: _{s.get("subject", "?")}_ — {n} action items ({link})')
        parts.append('')
    else:
        parts += ['*📧 Email summaries:* brak nowych w ostatniej dobie.', '']

    if frp_top:
        parts.append('*📖 FRP queue top:*')
        for f in frp_top:
            score = f.get('score') or {}
            parts.append(
                f'• access={score.get("accessibility", "?")}/10 '
                f'horizon={score.get("horizon", "?")}/10 '
                f'consequence={score.get("consequence", "?")}/10 → '
                f'prompt {score.get("suggested_prompt_key", "?")}'
            )
            first_line = (f.get('body') or '').splitlines()[0] if f.get('body') else ''
            if first_line:
                parts.append(f'  {first_line[:80]}')
        parts.append('')
    else:
        parts += ['*📖 FRP queue:* pusta (uruchom RSS adapter).', '']

    if work_todo:
        parts.append('*✅ Work TODO this week:*')
        for w in work_todo:
            parts.append(f'• `{w["open_action_items"]}` open: _{w["title"]}_ '
                         f'({w["created_at"].strftime("%Y-%m-%d")})')
        parts.append('')
    else:
        parts.append('*✅ Work TODO:* brak otwartych w ostatnich 14 dniach.')

    return '\n'.join(parts)


# ─────────────────────────── CLI ───────────────────────────

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='F6.4.8 Telegram daily digest.')
    parser.add_argument('--since', help='ISO date — emails since this date (default: 24h).')
    parser.add_argument('--top', type=int, default=3,
                        help='How many items per section.')
    args = parser.parse_args(argv)

    since_dt = (datetime.fromisoformat(args.since) if args.since
                else datetime.now(timezone.utc) - timedelta(hours=24))
    if since_dt.tzinfo is None:
        since_dt = since_dt.replace(tzinfo=timezone.utc)

    summaries = gather_email_summaries(since=since_dt, top=args.top)
    frp_top = gather_frp_top(top=1)
    work_todo = gather_work_todo_this_week(top=args.top + 2)

    print(render_digest(summaries=summaries, frp_top=frp_top, work_todo=work_todo))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
