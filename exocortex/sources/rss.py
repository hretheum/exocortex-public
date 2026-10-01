# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/sources/rss.py — F6.2.1 RSS adapter.
#
# Fetches feeds from config/sources.yaml::rss.feeds, POSTs each entry to
# /capture as source_type=rss-frp (or per-feed override). Idempotent — server
# UNIQUE on (tenant_id, source_type, uri) makes re-runs cheap.
#
# CLI:
#     python3 -m workers.sources.rss --once          # one pass over all feeds
#     python3 -m workers.sources.rss --feed 365tomorrows --once  # single feed
#     python3 -m workers.sources.rss --dry-run --once
#
# systemd timer: hourly. See deploy/systemd/second-brain-rss.{service,timer}.

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / 'config' / '.env')

CAPTURE_API_URL = os.environ.get('CAPTURE_API_URL', 'http://localhost:8000').rstrip('/')
CAPTURE_API_TOKEN = os.environ.get('CAPTURE_API_TOKEN', '').strip()
SOURCES_CONFIG = Path(__file__).parent.parent.parent / 'config' / 'sources.yaml'
DEFAULT_TIMEOUT = 30.0


# ─────────────────────────── Config ───────────────────────────

def load_feeds() -> tuple[list[dict], str]:
    """Returns (feeds_list, default_source_type).

    Falls back to ``config/sources.example.yaml`` when the operator-owned
    ``sources.yaml`` doesn't exist (fresh checkout pre-init).
    """
    from exocortex.config_loader import resolve_config_path
    path = resolve_config_path('sources.yaml')
    with path.open() as f:
        cfg = yaml.safe_load(f) or {}
    rss = cfg.get('rss') or {}
    return list(rss.get('feeds') or []), rss.get('default_source_type', 'rss-frp')


# ─────────────────────────── Capture POST ───────────────────────────

class RssError(Exception):
    pass


def post_capture(payload: dict, *, timeout: float = DEFAULT_TIMEOUT) -> dict:
    if not CAPTURE_API_TOKEN:
        raise RssError('CAPTURE_API_TOKEN not set in env')
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
        raise RssError(f'HTTP {e.code}: {body}') from e
    except urllib.error.URLError as e:
        raise RssError(f'URLError: {e.reason}') from e


# ─────────────────────────── Feed → payload ───────────────────────────

def _entry_uri(entry: Any) -> Optional[str]:
    for key in ('link', 'id', 'guid'):
        v = getattr(entry, key, None) or (entry.get(key) if isinstance(entry, dict) else None)
        if v and isinstance(v, str) and v.startswith(('http://', 'https://')):
            return v
    return None


def _entry_published(entry: Any) -> Optional[str]:
    """Best-effort YYYY-MM-DD from feedparser entry."""
    parsed = getattr(entry, 'published_parsed', None) or getattr(entry, 'updated_parsed', None)
    if parsed is None:
        return None
    return time.strftime('%Y-%m-%d', parsed)


def _entry_body(entry: Any) -> tuple[Optional[str], Optional[str]]:
    """Returns (body_text, body_kind) where kind is 'full' or 'excerpt'.

    Prefer entry.content (RSS <content:encoded>) over entry.summary so that
    publishers who syndicate full text get full text into the vault. Fair use
    rationale: publisher implicitly licensed RSS-distributed content for
    syndication; single-user vault storage with attribution preserved
    (entry.link → raw_sources.uri).
    """
    content = getattr(entry, 'content', None)
    if content:
        # feedparser exposes entry.content as a list of FeedParserDict with
        # .value. Take the first element (publishers rarely give multiples).
        first = content[0] if isinstance(content, list) else content
        value = getattr(first, 'value', None) or (first.get('value') if isinstance(first, dict) else None)
        if value and isinstance(value, str) and value.strip():
            return value, 'full'
    summary = getattr(entry, 'summary', None) or getattr(entry, 'description', None)
    if summary and isinstance(summary, str) and summary.strip():
        return summary, 'excerpt'
    return None, None


def _entry_payload(feed_meta: dict, entry: Any, source_type: str) -> Optional[dict]:
    uri = _entry_uri(entry)
    if not uri:
        return None
    title = getattr(entry, 'title', None) or '(untitled)'
    author = getattr(entry, 'author', None)
    body, body_kind = _entry_body(entry)
    metadata: dict[str, Any] = {
        'feed_name': feed_meta.get('name'),
        'feed_url': feed_meta.get('url'),
    }
    if body_kind:
        metadata['body_kind'] = body_kind
    payload: dict[str, Any] = {
        'source_type': source_type,
        'uri': uri,
        'title': str(title)[:500],
        'metadata': metadata,
    }
    if author:
        payload['author_name'] = str(author)[:200]
    published = _entry_published(entry)
    if published:
        payload['published_at'] = published
    if feed_meta.get('source_name'):
        payload['source_name'] = feed_meta['source_name']
    if body:
        # capture_api will normalize HTML → markdown via trafilatura and store
        # both the cleaned text (metadata.excerpt) and the original raw_payload.
        # Cap at 64 KiB matches capture_api server-side limit.
        payload['raw_payload'] = body
    return payload


# ─────────────────────────── Per-feed run ───────────────────────────

def fetch_feed(feed_meta: dict, default_source_type: str, *,
               dry_run: bool = False) -> dict[str, int]:
    import feedparser  # lazy — keeps --help fast
    name = feed_meta.get('name') or feed_meta.get('url')
    url = feed_meta['url']
    source_type = feed_meta.get('source_type') or default_source_type

    from exocortex.source_allowlist import SourceNotAllowed, require_url
    try:
        require_url(url)  # F2.2: no-op unless a lab allowlist is configured
    except SourceNotAllowed as exc:
        print(f'  ! refused by the source allowlist: {exc}')
        return {'fetched': 0, 'created': 0, 'unchanged': 0, 'error': 1}

    print(f'[rss] fetching {name} ({url}) → source_type={source_type}')
    parsed = feedparser.parse(url)
    if parsed.bozo and not parsed.entries:
        print(f'  ! parser error: {parsed.bozo_exception!r}')
        return {'fetched': 0, 'created': 0, 'unchanged': 0, 'error': 1}

    counts = {'fetched': 0, 'created': 0, 'unchanged': 0, 'error': 0,
              'full': 0, 'excerpt': 0}
    for entry in parsed.entries:
        counts['fetched'] += 1
        payload = _entry_payload(feed_meta, entry, source_type)
        if payload is None:
            counts['error'] += 1
            print('  ! skipped (no http(s) link)')
            continue
        kind = (payload.get('metadata') or {}).get('body_kind')
        if kind == 'full':
            counts['full'] += 1
        elif kind == 'excerpt':
            counts['excerpt'] += 1
        if dry_run:
            body_len = len(payload.get('raw_payload') or '')
            print(f'  ? [{kind or "no-body":7s} {body_len:>6d}c] {payload["uri"]} | {payload["title"][:50]}')
            continue
        try:
            resp = post_capture(payload)
        except RssError as e:
            counts['error'] += 1
            print(f'  ! {payload["uri"]}: {e}')
            continue
        if resp.get('created'):
            counts['created'] += 1
            print(f'  + [{kind or "no-body"}] {payload["uri"][:80]}')
        else:
            counts['unchanged'] += 1
    print(f'  = {name}: {counts["fetched"]} items, '
          f'{counts["full"]} full / {counts["excerpt"]} excerpt')
    return counts


# ─────────────────────────── CLI ───────────────────────────

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='F6.2.1 RSS adapter.')
    parser.add_argument('--once', action='store_true',
                        help='Process each feed once, then exit.')
    parser.add_argument('--feed', help='Run only this feed (by name).')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print payloads but do not POST.')
    args = parser.parse_args(argv)

    feeds, default_st = load_feeds()
    if not feeds:
        print('[rss] no feeds configured in config/sources.yaml::rss.feeds')
        return 2

    if args.feed:
        feeds = [f for f in feeds if f.get('name') == args.feed]
        if not feeds:
            print(f'[rss] no feed named {args.feed!r}')
            return 2

    if not args.once:
        # Daemon mode — could be a sleep loop, but systemd timer is cleaner.
        # Keep --once as the only supported mode for now.
        print('[rss] note: this script only supports --once. Use systemd timer for cron.')
        return 2

    totals = {'fetched': 0, 'created': 0, 'unchanged': 0, 'error': 0}
    for feed in feeds:
        c = fetch_feed(feed, default_st, dry_run=args.dry_run)
        for k, v in c.items():
            totals[k] = totals.get(k, 0) + v

    print(f'\n[rss] done. totals={totals}')
    # F14 pipeline telemetry
    from exocortex.pipeline_log import log_run_end, log_run_start
    _pl_id = log_run_start('rss')
    _pl_ok = not totals.get('error')
    log_run_end(_pl_id, 'success' if _pl_ok else 'failure',
                counts=totals,
                error_message=f'RSS: {totals.get("error", 0)} errors' if not _pl_ok else None)
    return 1 if totals['error'] else 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
