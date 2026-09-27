# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/journal_publisher.py — F6.4.2: one-shot publication for email threads.
#
# Reads `email_thread_synthesis` thoughts (emitted by F6.3 email_thread.synthesize)
# and writes one atomic file per thread under
#     vault/_journal/email-summaries/{YYYY-MM-DD}-{thread-slug}.md
#
# Distinct from wiki_compiler:
#   - NO `<!-- GENERATED -->` sentinels — user is free to edit the body.
#   - Append-only: re-running for the same thread appends an "Update" block
#     (synthesis update) below the existing content rather than overwriting.
#   - Frontmatter follows the F6.4.2 convention (sender_email, sender_domain,
#     domains[], client, project, message_count, status, _synthesis_thought_id).
#
# Also updates email_threads.metadata.journal_path so we can find the file
# again on the next run + propagate to F6.4.6 cross-references.

from __future__ import annotations
import argparse
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / 'config' / '.env')

from exocortex.db import (  # noqa: E402
    emit_thread_edges, query, query_one, update_where,
)
from exocortex.email_classifier import classify_email_thread  # noqa: E402

from exocortex.settings import get_settings, get_tenant_id  # noqa: E402

TENANT_ID = get_tenant_id()


def _vault_path() -> Path:
    return get_settings().vault_path


def _journal_dir() -> Path:
    return _vault_path() / '_journal' / 'email-summaries'


def __getattr__(name):
    # Lazy module-level resolution: importing this module without
    # EXOCORTEX_VAULT_PATH must not crash. We surface AttributeError
    # (not ValidationError) so `hasattr()` callers behave correctly.
    if name == 'VAULT_PATH':
        try:
            return _vault_path()
        except Exception as exc:
            raise AttributeError(
                f"VAULT_PATH unavailable: {exc}. Set EXOCORTEX_VAULT_PATH."
            ) from exc
    if name == 'JOURNAL_DIR':
        try:
            return _journal_dir()
        except Exception as exc:
            raise AttributeError(
                f"JOURNAL_DIR unavailable: {exc}. Set EXOCORTEX_VAULT_PATH."
            ) from exc
    raise AttributeError(name)

logger = logging.getLogger('journal_publisher')


# ─────────────────────────── Slug + path helpers ───────────────────────────

def _slugify(text: str, max_len: int = 60) -> str:
    s = re.sub(r'[^\w\s-]', '', text.lower(), flags=re.UNICODE)
    s = re.sub(r'[\s_]+', '-', s).strip('-')
    return s[:max_len].rstrip('-') or 'untitled'


def _journal_path(thread_started: Optional[str], subject: str) -> Path:
    """`{YYYY-MM-DD}-{slug}.md` under JOURNAL_DIR."""
    if thread_started:
        date_part = thread_started.split('T')[0][:10]
    else:
        date_part = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    return JOURNAL_DIR / f'{date_part}-{_slugify(subject)}.md'  # noqa: F821


# ─────────────────────────── Publish one thread ───────────────────────────

def _build_frontmatter(synthesis: dict, thread_row: dict,
                       classification) -> dict[str, Any]:
    md = synthesis.get('metadata') or {}
    thread_meta = thread_row.get('metadata') or {}
    sender = thread_meta.get('sender') or ''
    sender_email_match = re.search(r'<([^>]+)>|([\w.+-]+@[\w.-]+\.\w+)', sender)
    sender_email = ''
    if sender_email_match:
        sender_email = sender_email_match.group(1) or sender_email_match.group(2) or ''
    sender_domain = sender_email.split('@')[-1].lower() if '@' in sender_email else ''

    return {
        'type': 'email-thread-synthesis',
        'thread_id': str(thread_row['id']),
        'gmail_thread_id': md.get('gmail_thread_id'),
        'subject': thread_row.get('subject') or '(no subject)',
        'sender_email': sender_email,
        'sender_name': sender.split('<')[0].strip() if '<' in sender else sender,
        'sender_domain': sender_domain,
        'domains': classification.domains,
        'client': classification.client,
        'project': classification.project,
        'tags': sorted({*(classification.tags or [])}),
        'thread_started': str(thread_row.get('first_message_at') or '')[:10],
        'last_message_at': str(thread_row.get('last_message_at') or ''),
        'message_count': thread_row.get('message_count', 0),
        'status': thread_row.get('status'),
        '_synthesis_thought_id': str(synthesis['id']),
    }


def _render_frontmatter(fm: dict) -> str:
    """Emit YAML frontmatter (with deterministic key order)."""
    return '---\n' + yaml.safe_dump(fm, default_flow_style=False,
                                    allow_unicode=True, sort_keys=False) + '---\n'


def publish_thread(synthesis_thought: dict, *, dry_run: bool = False) -> dict:
    """Render one thread's journal file. Append-only on re-runs."""
    md = synthesis_thought.get('metadata') or {}
    email_thread_id = md.get('email_thread_id')
    if not email_thread_id:
        return {'status': 'error', 'reason': 'synthesis_missing_email_thread_id',
                'thought_id': str(synthesis_thought['id'])}

    thread_row = query_one(
        'SELECT id, subject, message_count, first_message_at, last_message_at, '
        'status, summary_thought_id, metadata '
        'FROM email_threads WHERE id = %s',
        email_thread_id,
    )
    if thread_row is None:
        return {'status': 'error', 'reason': 'thread_row_not_found',
                'thought_id': str(synthesis_thought['id'])}

    thread_meta = thread_row.get('metadata') or {}
    sender = thread_meta.get('sender') or ''
    classification = classify_email_thread(
        sender=sender,
        subject=thread_row.get('subject') or '',
        body_excerpt=(synthesis_thought.get('body') or '')[:2000],
        recipients=[
            *(thread_meta.get('recipients_to') or '').split(','),
            *(thread_meta.get('recipients_cc') or '').split(','),
        ],
    )

    fm = _build_frontmatter(synthesis_thought, thread_row, classification)
    file_path = _journal_path(fm.get('thread_started') or '', fm['subject'])

    body = synthesis_thought.get('body') or ''
    new_block = (
        '\n\n<!-- synthesis update '
        f'{datetime.now(timezone.utc).isoformat()} -->\n'
        f'{body}\n'
    )

    if dry_run:
        return {'status': 'dry_run', 'path': str(file_path),
                'classification': classification.__dict__}

    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)  # noqa: F821

    if file_path.exists():
        # Append-only update.
        existing = file_path.read_text(encoding='utf-8')
        # Replace frontmatter (it carries the latest message_count + status),
        # keep the user-edited body intact, append new synthesis block.
        body_part = re.sub(r'^---\n.*?\n---\n', '', existing, count=1, flags=re.DOTALL)
        new_content = _render_frontmatter(fm) + body_part + new_block
        action = 'updated'
    else:
        new_content = _render_frontmatter(fm) + body
        action = 'created'

    file_path.write_text(new_content, encoding='utf-8')

    # Update email_threads.metadata.journal_path so we can find the file.
    new_thread_meta = {**thread_meta, 'journal_path': str(file_path.relative_to(VAULT_PATH))}  # noqa: F821
    update_where('email_threads', {'metadata': new_thread_meta},
                 'id = %s', str(thread_row['id']))

    # Edges: thread → person/client/project.
    edge_counts = emit_thread_edges(
        str(thread_row['id']), classification,
        sender_email=fm.get('sender_email'),
        recipients=[
            *(thread_meta.get('recipients_to') or '').split(','),
            *(thread_meta.get('recipients_cc') or '').split(','),
        ],
        tenant_id=TENANT_ID,
    )

    return {
        'status': 'ok',
        'action': action,
        'path': str(file_path.relative_to(VAULT_PATH)),  # noqa: F821
        'thread_id': str(thread_row['id']),
        'classification': classification.__dict__,
        'edges': edge_counts,
    }


# ─────────────────────────── Bulk run ───────────────────────────

def publish_all(*, since: Optional[datetime] = None,
                limit: int = 200, dry_run: bool = False) -> dict:
    sql = (
        "SELECT id, body, metadata "
        "FROM thoughts "
        "WHERE tenant_id = %s "
        "  AND thought_type = 'email_thread_synthesis' "
        "  AND superseded_by IS NULL"
    )
    params = [TENANT_ID]
    if since is not None:
        sql += ' AND created_at >= %s'
        params.append(since)
    sql += ' ORDER BY created_at DESC LIMIT %s'
    params.append(limit)

    rows = query(sql, *params)
    counts = {'fetched': len(rows), 'created': 0, 'updated': 0,
              'dry_run': 0, 'error': 0}
    for r in rows:
        result = publish_thread(r, dry_run=dry_run)
        action = result.get('action') or result.get('status') or ''
        counts[action] = counts.get(action, 0) + 1
        if action == 'error':
            logger.warning('thread %s: %s', r['id'], result.get('reason'))
        else:
            logger.info('  %s %s', action, result.get('path'))
    return counts


# ─────────────────────────── CLI ───────────────────────────

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='F6.4.2 journal publisher.')
    parser.add_argument('--since', help='ISO date — only publish threads with synthesis after this date.')
    parser.add_argument('--limit', type=int, default=200)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format='%(asctime)s %(levelname)-7s %(name)s %(message)s',
    )

    since_dt = None
    if args.since:
        since_dt = datetime.fromisoformat(args.since.replace('Z', '+00:00'))

    counts = publish_all(since=since_dt, limit=args.limit, dry_run=args.dry_run)
    print(f'[journal_publisher] done. counts={counts}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
