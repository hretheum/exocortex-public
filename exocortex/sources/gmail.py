# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/sources/gmail.py — F6.2.2 thread adapter + F8.8 newsletter adapter.
#
# Two modes (config/sources.yaml::gmail.mode):
#
#   "newsletter" (F8.8, default 2026-05-03+) — per-message ingestion of
#     industry newsletters labelled `Read Later`. Body extracted (HTML →
#     trafilatura via capture_api), POSTed as source_type=newsletter.
#     Read-only consumer; never modifies the Gmail mailbox.
#
#   "thread" (F6.2.2 legacy) — per-thread aggregation for work email
#     (label `_to-process`). Upserts email_threads row + POSTs source_type=
#     gmail-thread with snippets only. Kept as a code path; current config
#     points the label/mode at "newsletter" (per F8.8 scope decision).
#
# OAuth token is in ~/.config/second-brain/gmail_token.json (chmod 600), minted
# by scripts/gmail_oauth_setup.py — that script is the one-time interactive
# setup; this module is non-interactive.
#
# CLI:
#     python3 -m workers.sources.gmail --once             # mode from config
#     python3 -m workers.sources.gmail --once --mode newsletter
#     python3 -m workers.sources.gmail --once --mode thread --label _to-process
#     python3 -m workers.sources.gmail --once --query "newer_than:7d label:'Read Later'"
#     python3 -m workers.sources.gmail --once --max-messages 5
#     python3 -m workers.sources.gmail --once --dry-run

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / 'config' / '.env')

from exocortex.settings import get_tenant_id  # noqa: E402

CAPTURE_API_URL = os.environ.get('CAPTURE_API_URL', 'http://localhost:8000').rstrip('/')
CAPTURE_API_TOKEN = os.environ.get('CAPTURE_API_TOKEN', '').strip()
TENANT_ID = get_tenant_id()
SOURCES_CONFIG = Path(__file__).parent.parent.parent / 'config' / 'sources.yaml'

DEFAULT_CONFIG_DIR = Path.home() / '.config' / 'second-brain'
DEFAULT_TOKEN_PATH = DEFAULT_CONFIG_DIR / 'gmail_token.json'

GMAIL_THREAD_URL = 'https://mail.google.com/mail/u/0/#all/{thread_id}'
QUIESCENT_AFTER = timedelta(hours=24)


# ─────────────────────────── Config ───────────────────────────

def load_gmail_cfg() -> dict:
    """Falls back to ``config/sources.example.yaml`` in fresh checkouts."""
    from exocortex.config_loader import resolve_config_path
    path = resolve_config_path('sources.yaml')
    with path.open() as f:
        cfg = yaml.safe_load(f) or {}
    return cfg.get('gmail') or {}


# ─────────────────────────── Capture POST ───────────────────────────

class GmailError(Exception):
    pass


def post_capture(payload: dict, *, timeout: float = 30.0) -> dict:
    if not CAPTURE_API_TOKEN:
        raise GmailError('CAPTURE_API_TOKEN not set in env')
    req = urllib.request.Request(
        f'{CAPTURE_API_URL}/capture',
        method='POST',
        headers={
            'Authorization': f'Bearer {CAPTURE_API_TOKEN}',
            'Content-Type': 'application/json',
        },
        data=json.dumps(payload).encode('utf-8'),
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        raise GmailError(f'HTTP {e.code}: {body}') from e
    except urllib.error.URLError as e:
        raise GmailError(f'URLError: {e.reason}') from e


# ─────────────────────────── OAuth client ───────────────────────────

def _build_client(token_path: Path):
    """Return a google-api-python-client `gmail.users` resource."""
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise GmailError(
            f'google-api-python-client missing ({exc}); '
            'pip install google-api-python-client google-auth-oauthlib'
        ) from exc

    if not token_path.exists():
        raise GmailError(
            f'no Gmail token at {token_path}. '
            'Run: python3 scripts/gmail_oauth_setup.py'
        )

    creds = Credentials.from_authorized_user_file(str(token_path))
    return build('gmail', 'v1', credentials=creds, cache_discovery=False)


# ─────────────────────────── Gmail → payload ───────────────────────────

def _list_thread_ids(svc, label: str, max_results: int = 100) -> list[str]:
    """Returns thread IDs that have the label on any message."""
    res = svc.users().threads().list(
        userId='me', labelIds=[label_id_for(svc, label)],
        maxResults=max_results,
    ).execute()
    return [t['id'] for t in (res.get('threads') or [])]


def label_id_for(svc, label_name: str) -> str:
    """Resolve label name → label id. Gmail API expects ids in queries."""
    res = svc.users().labels().list(userId='me').execute()
    for lab in res.get('labels') or []:
        if lab['name'].lower() == label_name.lower() or lab['id'] == label_name:
            return lab['id']
    raise GmailError(f'no Gmail label matching {label_name!r}')


def _header(headers: list[dict], name: str) -> Optional[str]:
    name_l = name.lower()
    for h in headers:
        if h.get('name', '').lower() == name_l:
            return h.get('value')
    return None


def _fetch_thread(svc, thread_id: str) -> dict:
    """Get full thread payload — used for subject + sender/recipient extraction."""
    return svc.users().threads().get(userId='me', id=thread_id, format='metadata').execute()


def _thread_payload(thread: dict) -> dict[str, Any]:
    """Build capture_api payload from a Gmail thread."""
    messages = thread.get('messages') or []
    first = messages[0] if messages else {}
    last = messages[-1] if messages else {}
    first_headers = (first.get('payload') or {}).get('headers') or []
    last_headers = (last.get('payload') or {}).get('headers') or []

    subject = _header(first_headers, 'Subject') or '(no subject)'
    sender = _header(first_headers, 'From')
    recipients_to = _header(last_headers, 'To') or ''
    recipients_cc = _header(last_headers, 'Cc') or ''

    # Gmail returns internalDate as ms-since-epoch as a string.
    def _ts(msg: dict) -> Optional[str]:
        v = msg.get('internalDate')
        if not v:
            return None
        return datetime.fromtimestamp(int(v) / 1000, tz=timezone.utc).isoformat()

    snippets = [
        {
            'message_id': m.get('id'),
            'snippet': (m.get('snippet') or '')[:500],
            'from': _header((m.get('payload') or {}).get('headers') or [], 'From'),
            'date': _ts(m),
        }
        for m in messages
    ]

    return {
        'gmail_thread_id': thread['id'],
        'subject': subject,
        'sender': sender,
        'recipients_to': recipients_to,
        'recipients_cc': recipients_cc,
        'message_count': len(messages),
        'first_message_at': _ts(first) if first else None,
        'last_message_at': _ts(last) if last else None,
        'snippets': snippets,
    }


# ─────────────────────────── DB upserts ───────────────────────────

def upsert_email_thread(payload: dict) -> dict:
    """Upsert email_threads row keyed on (tenant_id, gmail_thread_id).

    Returns the row dict (created flag derived from xmax).
    """
    from exocortex.db import conn  # lazy
    with conn() as c:
        # Use INSERT … ON CONFLICT … DO UPDATE so we always get the row back
        # AND we update message_count + last_message_at as the thread grows.
        row = c.execute(
            '''
            INSERT INTO email_threads
                (tenant_id, gmail_thread_id, subject, message_count,
                 first_message_at, last_message_at, status, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, 'active', %s::jsonb)
            ON CONFLICT (tenant_id, gmail_thread_id) DO UPDATE
                SET subject          = EXCLUDED.subject,
                    message_count    = EXCLUDED.message_count,
                    first_message_at = COALESCE(email_threads.first_message_at,
                                                EXCLUDED.first_message_at),
                    last_message_at  = EXCLUDED.last_message_at,
                    metadata         = EXCLUDED.metadata,
                    updated_at       = NOW()
            RETURNING id, status, last_message_at,
                      (xmax = 0) AS created
            ''',
            (
                TENANT_ID,
                payload['gmail_thread_id'],
                payload['subject'],
                payload['message_count'],
                payload.get('first_message_at'),
                payload.get('last_message_at'),
                json.dumps({
                    'sender': payload.get('sender'),
                    'recipients_to': payload.get('recipients_to'),
                    'recipients_cc': payload.get('recipients_cc'),
                    'snippets': payload.get('snippets'),
                }),
            ),
        ).fetchone()
    return dict(row)


def mark_quiescent_threads_ready() -> int:
    """Bulk-update active threads quiescent for QUIESCENT_AFTER → ready_for_synthesis.

    Returns the number of rows transitioned.
    """
    from exocortex.db import execute  # lazy
    cutoff = datetime.now(timezone.utc) - QUIESCENT_AFTER
    return execute(
        "UPDATE email_threads SET status = 'ready_for_synthesis', updated_at = NOW() "
        "WHERE tenant_id = %s AND status = 'active' AND last_message_at < %s",
        TENANT_ID, cutoff,
    )


# ─────────────────────────── F8.8 Newsletter mode ───────────────────────────

GMAIL_MESSAGE_URL = 'https://mail.google.com/mail/u/0/#all/{message_id}'


def _decode_part(part: dict) -> str:
    """Decode a Gmail message part body. Returns empty string if no data.

    Gmail bodies are base64url-encoded. multipart/* parts contain children
    in `parts`; leaf parts have `body.data`.
    """
    import base64
    body = part.get('body') or {}
    data = body.get('data')
    if not data:
        return ''
    # Gmail uses URL-safe base64 with possible missing padding.
    pad = '=' * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(data + pad).decode('utf-8', errors='replace')
    except Exception:
        return ''


def _extract_message_body(payload: dict) -> tuple[str, str]:
    """Walk message payload, return (body_text, mime_kind).

    mime_kind is 'html' if any text/html part found (preferred — capture_api
    will run trafilatura), otherwise 'plain' if text/plain. Empty string if
    neither.
    """
    # Prefer text/html; collect text/plain as fallback.
    html_chunks: list[str] = []
    plain_chunks: list[str] = []

    def _walk(p: dict) -> None:
        mt = (p.get('mimeType') or '').lower()
        if mt == 'text/html':
            html_chunks.append(_decode_part(p))
        elif mt == 'text/plain':
            plain_chunks.append(_decode_part(p))
        for child in (p.get('parts') or []):
            _walk(child)

    _walk(payload or {})
    if html_chunks:
        return ('\n'.join(c for c in html_chunks if c), 'html')
    if plain_chunks:
        return ('\n'.join(c for c in plain_chunks if c), 'plain')
    return ('', '')


def _parse_from_header(value: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Split RFC 2822 From header into (display_name, email_addr).

    Examples:
      "Foo Bar <foo@example.com>" → ("Foo Bar", "foo@example.com")
      "foo@example.com"           → (None, "foo@example.com")
    """
    if not value:
        return (None, None)
    import re
    m = re.match(r'^\s*"?([^"<]*?)"?\s*<([^>]+)>\s*$', value)
    if m:
        name = m.group(1).strip() or None
        return (name, m.group(2).strip())
    if '@' in value:
        return (None, value.strip())
    return (value.strip() or None, None)


def _newsletter_payload(svc, msg_id: str) -> Optional[dict[str, Any]]:
    """Fetch one Gmail message and build a /capture payload.

    Returns None if the message has no usable body (rare — newsletter
    senders almost always include text/html).
    """
    msg = svc.users().messages().get(userId='me', id=msg_id, format='full').execute()
    headers = (msg.get('payload') or {}).get('headers') or []
    subject = _header(headers, 'Subject') or '(no subject)'
    from_raw = _header(headers, 'From')
    sender_name, sender_email = _parse_from_header(from_raw)
    list_id = _header(headers, 'List-Id')
    list_unsub = _header(headers, 'List-Unsubscribe')
    date_hdr = _header(headers, 'Date')

    body, kind = _extract_message_body(msg.get('payload') or {})
    if not body:
        return None

    # internalDate is ms since epoch, string.
    ts_iso: Optional[str] = None
    internal = msg.get('internalDate')
    if internal:
        try:
            ts_iso = datetime.fromtimestamp(
                int(internal) / 1000, tz=timezone.utc
            ).isoformat()
        except Exception:
            ts_iso = None

    payload: dict[str, Any] = {
        'source_type': 'newsletter',
        'uri': GMAIL_MESSAGE_URL.format(message_id=msg_id),
        'title': str(subject)[:500],
        'metadata': {
            'gmail_message_id': msg_id,
            'gmail_thread_id': msg.get('threadId'),
            'sender_email': sender_email,
            'sender_name': sender_name,
            'list_id': list_id,
            'list_unsubscribe_present': bool(list_unsub),
            'date_header': date_hdr,
            'mime_kind': kind,
        },
        'raw_payload': body[:64 * 1024],  # capture_api caps at 64 KiB anyway
    }
    if sender_name:
        payload['author_name'] = str(sender_name)[:200]
    if ts_iso:
        payload['published_at'] = ts_iso[:10]
    if list_id:
        # Strip <...> wrapper from List-Id to use as source_name.
        clean = list_id.strip()
        if clean.startswith('<') and clean.endswith('>'):
            clean = clean[1:-1]
        payload['source_name'] = clean[:200]
    elif sender_name:
        payload['source_name'] = sender_name[:200]
    return payload


def _list_message_ids(svc, *, query: Optional[str], label: Optional[str],
                      max_results: int) -> list[str]:
    """List Gmail message IDs matching query and/or label.

    Gmail API caps `maxResults` at 500 per page; we paginate up to
    `max_results` total.
    """
    label_ids = [label_id_for(svc, label)] if label else None
    out: list[str] = []
    page_token: Optional[str] = None
    while True:
        kwargs: dict[str, Any] = {
            'userId': 'me',
            'maxResults': min(500, max_results - len(out)),
        }
        if query:
            kwargs['q'] = query
        if label_ids:
            kwargs['labelIds'] = label_ids
        if page_token:
            kwargs['pageToken'] = page_token
        res = svc.users().messages().list(**kwargs).execute()
        out.extend(m['id'] for m in (res.get('messages') or []))
        page_token = res.get('nextPageToken')
        if not page_token or len(out) >= max_results:
            break
    return out[:max_results]


def fetch_newsletters_once(*, label: Optional[str], query: Optional[str],
                           dry_run: bool, max_messages: int) -> dict[str, int]:
    """F8.8 newsletter mode: per-message ingestion."""
    cfg = load_gmail_cfg()
    token_path = Path(cfg.get('oauth_token_path') or DEFAULT_TOKEN_PATH).expanduser()
    print(f'[gmail-newsletter] using token {token_path}')
    svc = _build_client(token_path)

    msg_ids = _list_message_ids(svc, query=query, label=label, max_results=max_messages)
    print(f'[gmail-newsletter] {len(msg_ids)} messages '
          f'(query={query!r} label={label!r} max={max_messages})')

    counts = {'fetched': 0, 'created': 0, 'unchanged': 0, 'no_body': 0, 'error': 0}
    for mid in msg_ids:
        counts['fetched'] += 1
        try:
            payload = _newsletter_payload(svc, mid)
        except Exception as exc:
            counts['error'] += 1
            print(f'  ! gmail get {mid}: {exc!r}')
            continue
        if payload is None:
            counts['no_body'] += 1
            print(f'  ~ {mid} (no usable body)')
            continue
        if dry_run:
            sender = (payload.get('metadata') or {}).get('sender_email') or '?'
            kind = (payload.get('metadata') or {}).get('mime_kind') or '?'
            body_len = len(payload.get('raw_payload') or '')
            print(f'  ? [{kind:5s} {body_len:>6d}c {sender[:30]:30s}] {payload["title"][:55]}')
            continue
        try:
            resp = post_capture(payload)
        except GmailError as exc:
            counts['error'] += 1
            print(f'  ! POST /capture {mid}: {exc}')
            continue
        if resp.get('created'):
            counts['created'] += 1
            print(f'  + {payload["title"][:60]}')
        else:
            counts['unchanged'] += 1
    return counts


# ─────────────────────────── Main loop ───────────────────────────

def fetch_once(*, label: str, dry_run: bool = False,
               max_threads: int = 100) -> dict[str, int]:
    cfg = load_gmail_cfg()
    token_path = Path(cfg.get('oauth_token_path') or DEFAULT_TOKEN_PATH).expanduser()

    print(f'[gmail] using token {token_path}')
    svc = _build_client(token_path)
    thread_ids = _list_thread_ids(svc, label, max_results=max_threads)
    print(f'[gmail] {len(thread_ids)} threads with label={label!r}')

    counts = {'fetched': 0, 'upserted': 0, 'created_capture': 0,
              'unchanged_capture': 0, 'error': 0}

    for tid in thread_ids:
        counts['fetched'] += 1
        try:
            thread = _fetch_thread(svc, tid)
        except Exception as exc:
            counts['error'] += 1
            print(f'  ! thread {tid}: {exc!r}')
            continue

        payload = _thread_payload(thread)
        if dry_run:
            print(f'  ? {payload["subject"][:60]} ({payload["message_count"]} msg)')
            continue

        # 1. DB upsert (email_threads row)
        try:
            row = upsert_email_thread(payload)
            counts['upserted'] += 1
        except Exception as exc:
            counts['error'] += 1
            print(f'  ! email_threads upsert {tid}: {exc!r}')
            continue

        # 2. capture API POST
        capture_payload: dict[str, Any] = {
            'source_type': 'gmail-thread',
            'uri': GMAIL_THREAD_URL.format(thread_id=tid),
            'title': payload['subject'][:500],
            'metadata': {
                'gmail_thread_id': tid,
                'email_thread_id': str(row['id']),
                'message_count': payload['message_count'],
                'sender': payload.get('sender'),
                'first_message_at': payload.get('first_message_at'),
                'last_message_at': payload.get('last_message_at'),
                'snippets': payload.get('snippets'),
            },
        }
        try:
            resp = post_capture(capture_payload)
        except GmailError as exc:
            counts['error'] += 1
            print(f'  ! POST /capture {tid}: {exc}')
            continue

        if resp.get('created'):
            counts['created_capture'] += 1
            print(f'  + {payload["subject"][:60]}')
        else:
            counts['unchanged_capture'] += 1

    if not dry_run:
        transitioned = mark_quiescent_threads_ready()
        print(f'[gmail] {transitioned} thread(s) transitioned active → ready_for_synthesis')
    return counts


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description='F6.2.2 thread / F8.8 newsletter Gmail adapter.')
    parser.add_argument('--once', action='store_true',
                        help='Single fetch + upsert pass, then exit.')
    parser.add_argument('--mode', choices=('newsletter', 'thread'),
                        help='Override gmail.mode from sources.yaml.')
    parser.add_argument('--label', help='Override gmail.label from sources.yaml.')
    parser.add_argument('--query',
                        help='Gmail q-syntax filter (newsletter mode). '
                             'Default: gmail.backfill_query from sources.yaml.')
    parser.add_argument('--max-threads', type=int, default=100,
                        help='Max threads per pass — thread mode (default 100).')
    parser.add_argument('--max-messages', type=int, default=200,
                        help='Max messages per pass — newsletter mode (default 200).')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print payloads but do not upsert or POST.')
    args = parser.parse_args(argv)

    if not args.once:
        print('[gmail] only --once is supported. Use systemd timer for cron.')
        return 2

    cfg = load_gmail_cfg()
    mode = args.mode or cfg.get('mode') or 'thread'

    try:
        if mode == 'newsletter':
            label = args.label or cfg.get('label') or 'Read Later'
            query = args.query or cfg.get('backfill_query')
            counts = fetch_newsletters_once(
                label=label, query=query, dry_run=args.dry_run,
                max_messages=args.max_messages,
            )
        elif mode == 'thread':
            label = args.label or cfg.get('label') or '_to-process'
            counts = fetch_once(label=label, dry_run=args.dry_run,
                                max_threads=args.max_threads)
        else:
            print(f'[gmail] unknown mode: {mode!r}', file=sys.stderr)
            return 2
    except GmailError as exc:
        print(f'[gmail] {exc}', file=sys.stderr)
        return 2

    print(f'\n[gmail] mode={mode} done. counts={counts}')
    # F14 pipeline telemetry
    from exocortex.pipeline_log import log_run_end, log_run_start
    _pl_id = log_run_start('gmail', mode=mode, max_messages=args.max_messages)
    _pl_ok = not counts.get('error')
    log_run_end(_pl_id, 'success' if _pl_ok else 'failure',
                counts=counts,
                error_message=f'Gmail {mode}: {counts.get("error", 0)} errors' if not _pl_ok else None)
    return 1 if counts.get('error') else 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
