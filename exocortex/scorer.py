# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/scorer.py — F6.3 listener: pg_notify('content_acquired') → routing.
#
# Daemon-style. Connects to Postgres, LISTEN content_acquired, and on each
# notification dispatches to the per-source_type processor in
# workers/processors/.
#
# Run modes:
#   python3 -m workers.scorer                      # daemon (LISTEN forever)
#   python3 -m workers.scorer --process SOURCE_ID  # one-shot for testing
#   python3 -m workers.scorer --backfill --limit N # process unprocessed rows
#   python3 -m workers.scorer --routing            # print routing table + exit
#
# systemd: deploy/systemd/second-brain-scorer.service (write-only).

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections.abc import Callable

from exocortex._bootstrap import bootstrap

bootstrap()

import psycopg

from exocortex.db import _conninfo  # type: ignore
from exocortex.settings import get_tenant_id

TENANT_ID = get_tenant_id()

logger = logging.getLogger('scorer')


# ─────────────────────────── Routing table ───────────────────────────
#
# Each entry: source_type → callable(source_id) -> dict.
# Lazy imports keep startup fast and avoid pulling deps for unused processors.

def _lazy(module: str, attr: str) -> Callable[[str], dict]:
    """Return a lambda that imports the processor on first call."""
    fn_holder: dict[str, Callable | None] = {'fn': None}

    def _wrapper(source_id: str) -> dict:
        if fn_holder['fn'] is None:
            mod = __import__(f'exocortex.processors.{module}', fromlist=[attr])
            fn_holder['fn'] = getattr(mod, attr)
        return fn_holder['fn'](source_id)

    _wrapper.__name__ = f'lazy_{module}_{attr}'
    return _wrapper


ROUTING: dict[str, Callable[[str], dict] | None] = {
    'rss-frp':           _lazy('frp_source', 'process'),
    'frp-source':        _lazy('frp_source', 'process'),
    'gmail-thread':      _lazy('email_thread', 'process'),
    'email-thread':      _lazy('email_thread', 'process'),
    'newsletter':        _lazy('newsletter', 'process'),

    'article':           _lazy('article', 'tag_and_summarize'),
    'web-clipping':      _lazy('article', 'tag_and_summarize'),
    'manual-url':        _lazy('article', 'tag_and_summarize'),
    'recipe':            _lazy('recipe', 'process'),
    '3d-model':          _lazy('model_3d', 'process'),
    'github-issue':      _lazy('github', 'process'),
    'twitter-thread':    _lazy('twitter', 'process'),
    'arxiv':             _lazy('arxiv', 'process'),
    'youtube-tutorial':  _lazy('youtube', 'process'),
    'personal-article':  _lazy('article', 'tag_only'),
    'linkedin-post':     _lazy('linkedin', 'process'),
    'notion-cockpit-action': _lazy('cockpit_action', 'process'),
    'vault-note':        _lazy('vault_note', 'process'),
    'vault-backlog':     _lazy('vault_backlog', 'process'),
    'work-meeting-note': _lazy('work_meeting_note', 'process'),
    'claude-session':    _lazy('claude_session', 'process'),
    'quick-note':        None,   # deferred — Claude Routine 09:00 picks these up
}


# ─────────────────────────── Dispatch ───────────────────────────

def dispatch(source_id: str, source_type: str) -> dict:
    handler = ROUTING.get(source_type)
    if handler is None:
        return {'status': 'deferred', 'source_id': source_id,
                'source_type': source_type, 'reason': 'no_routing_or_deferred'}
    try:
        result = handler(source_id)
        # F18: emit live section event after successful processing
        _emit_live_event_hook(source_type, source_id, result)
        return result
    except Exception as exc:  # never crash the listener
        logger.exception('processor error for %s (%s)', source_id, source_type)
        return {'status': 'error', 'source_id': source_id,
                'source_type': source_type, 'reason': repr(exc)}


def _emit_live_event_hook(source_type: str, source_id: str, result: dict) -> None:
    """F18: emit live section event after successful content processing.

    Best-effort — never crashes the main listener loop.
    """
    if result.get('status') != 'success':
        return
    try:
        import json

        from exocortex.live_sections import emit_live_event
        emit_live_event(
            event_source=f"{source_type}_processed",
            event_payload=json.dumps({
                'source_id': source_id,
                'source_type': source_type,
                'status': result.get('status', 'success'),
            }),
        )
    except Exception:
        pass


# ─────────────────────────── LISTEN loop ───────────────────────────

def run_listener() -> int:
    """Connect, LISTEN content_acquired, dispatch each notification."""
    logger.info('starting LISTEN content_acquired')
    while True:
        try:
            with psycopg.connect(_conninfo(), autocommit=True) as conn:
                conn.execute('LISTEN content_acquired')
                logger.info('connected, waiting for notifications')
                # generator-style notify loop with periodic timeout for Ctrl-C resp.
                gen = conn.notifies(timeout=30.0)
                for n in gen:
                    try:
                        payload = json.loads(n.payload)
                    except Exception:
                        logger.warning('bad payload: %r', n.payload)
                        continue
                    source_id = payload.get('source_id')
                    source_type = payload.get('source_type')
                    if not source_id or not source_type:
                        logger.warning('payload missing fields: %r', payload)
                        continue
                    logger.info('notify: %s %s', source_type, source_id[:8])
                    result = dispatch(source_id, source_type)
                    logger.info('dispatch result: %s', result)
        except KeyboardInterrupt:
            logger.info('SIGINT — exiting')
            return 0
        except Exception:
            logger.exception('listener crashed; reconnecting in 5s')
            time.sleep(5)


# ─────────────────────────── Backfill mode ───────────────────────────

def backfill(limit: int = 50) -> int:
    """Find rows in raw_sources that don't have a processor stamp + dispatch them.

    Useful after enabling a new processor or after a downtime window.
    """
    from exocortex.db import query

    rows = query(
        '''
        SELECT id::text AS id, source_type
        FROM raw_sources
        WHERE tenant_id = %s
          AND NOT (metadata ? 'processors')
          AND source_type = ANY(%s::text[])
        ORDER BY ingested_at ASC
        LIMIT %s
        ''',
        TENANT_ID,
        list(ROUTING.keys()),
        limit,
    )
    logger.info('backfill: %d unprocessed rows', len(rows))
    for r in rows:
        result = dispatch(r['id'], r['source_type'])
        logger.info('  %s %s → %s', r['source_type'], r['id'][:8], result.get('status'))
    return 0


# ─────────────────────────── CLI ───────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='F6.3 content acquisition scorer.')
    parser.add_argument('--process', metavar='SOURCE_ID',
                        help='Process one specific source_id, then exit.')
    parser.add_argument('--backfill', action='store_true',
                        help='Process unprocessed rows once, then exit.')
    parser.add_argument('--limit', type=int, default=50,
                        help='Backfill row limit.')
    parser.add_argument('--routing', action='store_true',
                        help='Print the routing table and exit.')
    parser.add_argument('--debug', action='store_true', help='DEBUG-level logging.')
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format='%(asctime)s %(levelname)-7s %(name)s %(message)s',
    )

    if args.routing:
        for st, h in sorted(ROUTING.items()):
            print(f'  {st:20s} → {h.__name__ if h else "(deferred)"}')
        return 0

    if args.process:
        from exocortex.db import query_one
        row = query_one('SELECT source_type FROM raw_sources WHERE id = %s', args.process)
        if row is None:
            print(f'no source with id {args.process}', file=sys.stderr)
            return 2
        result = dispatch(args.process, row['source_type'])
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get('status') in ('ok', 'skipped', 'deferred') else 1

    if args.backfill:
        return backfill(args.limit)

    return run_listener()


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
