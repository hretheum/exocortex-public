# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/vault_watcher.py — F6.1.5: watch vault folders + POST → /capture.
#
# Two run modes:
#   --once     : process every matching file under VAULT_PATH once, exit.
#                Used for initial seed + ad-hoc reprocessing.
#   (default)  : watchdog event loop, runs forever. Driven by launchd plist
#                deploy/launchd/com.exocortex_user.second-brain.vault-watcher.plist
#
# Idempotency:
#   - Capture API enforces UNIQUE on (tenant_id, source_type, uri) and, since
#     F34 (schema/34_capture_content_hash.sql), UPDATEs the row (and
#     re-notifies downstream processors) whenever content actually changed —
#     a re-POST with the same uri is a true no-op ONLY when content_hash
#     matches; a genuinely edited file DOES update and reprocess.
#   - Watcher also keeps an in-memory hash cache to short-circuit before the
#     network call when content didn't change (modified events fire often
#     for things like Obsidian Sync touching mtime) — a local, in-process
#     optimization on top of, not instead of, the server-side content_hash
#     check above.
#
# uri convention: file:// path so capture API stores something stable for the
# UNIQUE constraint and so users can click-through in Obsidian.

from __future__ import annotations
import argparse
import fnmatch
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / 'config' / '.env')

from exocortex.settings import get_settings  # noqa: E402

CAPTURE_API_URL = os.environ.get('CAPTURE_API_URL', 'http://localhost:8000').rstrip('/')
CAPTURE_API_TOKEN = os.environ.get('CAPTURE_API_TOKEN', '').strip()
SOURCES_CONFIG = Path(__file__).parent.parent / 'config' / 'sources.yaml'


def _vault_path() -> Path:
    return get_settings().vault_path


def __getattr__(name):
    # Lazy module-level resolution: importing this module without
    # EXOCORTEX_VAULT_PATH must not crash. Access to VAULT_PATH triggers
    # settings validation; if env is missing we surface AttributeError
    # (not ValidationError) so `hasattr()` callers behave correctly.
    if name == 'VAULT_PATH':
        try:
            return _vault_path()
        except Exception as exc:
            raise AttributeError(
                f"VAULT_PATH unavailable: {exc}. Set EXOCORTEX_VAULT_PATH."
            ) from exc
    raise AttributeError(name)


# Module-level VAULT_PATH for within-module use (Python __getattr__ only fires
# for external attribute lookups, not for globals() lookups inside the module).
# Protected so that importing without env set is still safe.
try:
    VAULT_PATH: Path = _vault_path()
except Exception:
    VAULT_PATH = None  # type: ignore[assignment]

FRONTMATTER_RE = re.compile(r'^---\n(.*?)\n---', re.DOTALL)


# ─────────────────────────── Config ───────────────────────────

def load_config() -> dict:
    """Falls back to ``config/sources.example.yaml`` in fresh checkouts."""
    from exocortex.config_loader import resolve_config_path
    path = resolve_config_path('sources.yaml')
    with path.open() as f:
        return yaml.safe_load(f) or {}


def get_watch_rules(cfg: dict) -> list[dict]:
    return list(cfg.get('vault_watch', {}).get('watch') or [])


def get_default_source_type(cfg: dict) -> str:
    return cfg.get('vault_watch', {}).get('default_source_type', 'quick-note')


# ─────────────────────────── File matching ───────────────────────────

# Syncthing keeps the losing side of a concurrent edit as
# `<name>.sync-conflict-<YYYYMMDD>-<HHMMSS>-<device>.md` next to the original.
# Those matched the `*.md` include patterns and were captured as if they were
# separate notes — six meeting copies had been ingested that way (2026-08-03).
# The timestamp+device shape is Syncthing's own, so a note the user happens to
# name "sync-conflict-..." is not caught by this.
_SYNC_CONFLICT_RE = re.compile(r'\.sync-conflict-\d{8}-\d{6}-', re.IGNORECASE)


def is_sync_conflict(name: str) -> bool:
    """True for a Syncthing conflict copy — a duplicate, never new content."""
    return bool(_SYNC_CONFLICT_RE.search(name or ''))


def find_rule(path: Path, rules: list[dict]) -> Optional[dict]:
    """Return the first rule whose path is a prefix of `path` and a pattern matches."""
    try:
        path.relative_to(VAULT_PATH)  # noqa: F821
    except ValueError:
        return None
    for rule in rules:
        rule_dir = VAULT_PATH / rule['path']  # noqa: F821
        try:
            path.relative_to(rule_dir)
        except ValueError:
            continue
        patterns = rule.get('include_patterns') or ['*.md']
        if any(fnmatch.fnmatch(path.name, p) for p in patterns):
            if is_sync_conflict(path.name):
                return None
            return rule
    return None


def parse_frontmatter(text: str) -> tuple[dict, str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        fm = {}
    body = text[m.end():].lstrip('\n')
    return fm, body


def body_hash(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]


# ─────────────────────────── Capture POST ───────────────────────────

class WatcherError(Exception):
    pass


def post_capture(payload: dict, *, timeout: float = 15.0) -> dict:
    if not CAPTURE_API_TOKEN:
        raise WatcherError('CAPTURE_API_TOKEN not set in env')
    req = urllib.request.Request(
        f'{CAPTURE_API_URL}/capture',
        method='POST',
        headers={
            'Authorization': f'Bearer {CAPTURE_API_TOKEN}',
            'Content-Type': 'application/json',
        },
        # default=str: unquoted YAML dates (e.g. `date: 2026-10-20`) parse as
        # datetime.date, not str — json.dumps chokes on those without a
        # fallback. str() on a date/datetime gives its ISO form, matching
        # what a quoted frontmatter value would have produced anyway.
        data=json.dumps(payload, default=str).encode('utf-8'),
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        raise WatcherError(f'HTTP {e.code}: {body}') from e
    except urllib.error.URLError as e:
        raise WatcherError(f'URLError: {e.reason}') from e


# ─────────────────────────── Per-file processing ───────────────────────────

# In-memory hash cache to skip re-POSTs when only mtime changed (common with
# Obsidian Sync / iCloud Drive touch). Keyed by absolute path string.
_HASH_CACHE: dict[str, str] = {}


def process_file(path: Path, rule: dict, default_source_type: str,
                 *, force: bool = False) -> dict[str, Any]:
    text = path.read_text(encoding='utf-8', errors='replace')
    bh = body_hash(text)
    cache_key = str(path)
    if not force and _HASH_CACHE.get(cache_key) == bh:
        return {'status': 'cache_skip', 'path': str(path)}

    fm, raw_body = parse_frontmatter(text)
    source_type = (
        fm.get('source_type')
        or rule.get('source_type')
        or default_source_type
    )

    # uri: prefer frontmatter url (web-clipper sets this), else file://
    uri = fm.get('url') or fm.get('uri') or path.as_uri()

    payload: dict[str, Any] = {
        'source_type': source_type,
        'uri': uri,
        'metadata': {
            'vault_path': str(path.relative_to(VAULT_PATH)),  # noqa: F821
            'body_hash': bh,
            'frontmatter': fm,
            'domain': fm.get('domain') or rule.get('domain'),
        },
    }

    title = fm.get('title')
    if title:
        payload['title'] = str(title)
    author = fm.get('author') or fm.get('author_name')
    if author:
        payload['author_name'] = str(author)
    published = fm.get('published') or fm.get('published_at') or fm.get('date')
    if published:
        # Best-effort ISO date — capture API accepts string.
        payload['published_at'] = str(published)
    source_name = fm.get('source_name') or fm.get('source')
    if source_name:
        payload['source_name'] = str(source_name)

    if raw_body.strip():
        payload['raw_payload'] = raw_body

    try:
        resp = post_capture(payload)
    except WatcherError as e:
        return {'status': 'error', 'path': str(path), 'error': str(e)}

    _HASH_CACHE[cache_key] = bh
    return {
        'status': 'created' if resp.get('created') else 'unchanged',
        'path': str(path.relative_to(VAULT_PATH)),  # noqa: F821
        'source_id': resp.get('source_id'),
        'source_type': source_type,
    }


# ─────────────────────────── Once mode ───────────────────────────

def run_once(*, force: bool = False) -> int:
    cfg = load_config()
    rules = get_watch_rules(cfg)
    default = get_default_source_type(cfg)

    seen: set[Path] = set()
    counts = {'created': 0, 'unchanged': 0, 'cache_skip': 0, 'error': 0, 'unmatched': 0}

    for rule in rules:
        rule_dir = VAULT_PATH / rule['path']  # noqa: F821
        if not rule_dir.exists():
            print(f'[watcher] skip missing dir: {rule_dir}')
            continue
        for path in sorted(rule_dir.rglob('*.md')):
            if path in seen:
                continue
            seen.add(path)
            matched_rule = find_rule(path, rules)
            if matched_rule is None:
                counts['unmatched'] += 1
                continue
            result = process_file(path, matched_rule, default, force=force)
            counts[result['status']] = counts.get(result['status'], 0) + 1
            status_marker = {
                'created': '+', 'unchanged': '·', 'cache_skip': '=',
                'error': '!', 'unmatched': '?',
            }.get(result['status'], '?')
            extra = result.get('error', '') or result.get('source_type', '')
            print(f'  {status_marker} {result.get("path", path)} [{extra}]')

    print(f'\n[watcher] done. counts={counts}')
    return 1 if counts['error'] else 0


# ─────────────────────────── Daemon mode (watchdog) ───────────────────────────

def run_daemon() -> int:
    try:
        from watchdog.observers import Observer
    except ImportError as exc:
        print(f'[watcher] watchdog missing ({exc}); pip install watchdog')
        return 2

    cfg = load_config()
    rules = get_watch_rules(cfg)
    default = get_default_source_type(cfg)

    # Initial sync — pick up files added while daemon was down.
    print('[watcher] initial sync (one-shot)…')
    run_once()

    handler = _Handler(rules, default)
    observer = Observer()
    for rule in rules:
        rule_dir = VAULT_PATH / rule['path']  # noqa: F821
        if not rule_dir.exists():
            print(f'[watcher] skip missing dir: {rule_dir}')
            continue
        observer.schedule(handler, str(rule_dir), recursive=True)
        print(f'[watcher] watching {rule_dir}  (source_type={rule.get("source_type")})')
    observer.start()
    print('[watcher] daemon running. Ctrl-C to stop.')
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    return 0


try:
    from watchdog.events import FileSystemEventHandler as _FSEHBase
except ImportError:  # watchdog optional for --once
    class _FSEHBase:  # type: ignore[no-redef]
        pass


class _Handler(_FSEHBase):
    """Watchdog event handler. Inherits FileSystemEventHandler so that
    Observer.dispatch_events() can call handler.dispatch(event) — without the
    base class, watchdog's dispatcher AttributeErrors and the daemon thread
    dies silently."""

    def __init__(self, rules: list[dict], default_source_type: str):
        super().__init__()
        self._rules = rules
        self._default = default_source_type

    def on_created(self, event):  # type: ignore[no-untyped-def]
        self._handle(event)

    def on_modified(self, event):  # type: ignore[no-untyped-def]
        self._handle(event)

    def _handle(self, event) -> None:  # type: ignore[no-untyped-def]
        if getattr(event, 'is_directory', False):
            return
        path = Path(event.src_path)
        if path.suffix.lower() != '.md':
            return
        rule = find_rule(path, self._rules)
        if rule is None:
            return
        # Brief debounce — Obsidian writes, then immediately writes again on
        # save (twice within 50 ms is normal).
        time.sleep(0.2)
        try:
            result = process_file(path, rule, self._default)
        except Exception as exc:  # noqa: BLE001 — never crash the watcher
            print(f'  ! {path}: {exc!r}')
            return
        if result['status'] in ('error', 'created'):
            print(f'  {result["status"][0].upper()} {result.get("path", path)}: '
                  f'{result.get("error") or result.get("source_id")}')


# ─────────────────────────── CLI ───────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description='F6.1.5 vault watcher.')
    parser.add_argument('--once', action='store_true',
                        help='Process every matching file once, then exit.')
    parser.add_argument('--force', action='store_true',
                        help='Ignore in-memory hash cache (still server-idempotent).')
    args = parser.parse_args()

    vault_path = _vault_path()
    if not vault_path.exists():
        print(f'[watcher] VAULT_PATH does not exist: {vault_path}', file=sys.stderr)
        return 2

    if args.once:
        return run_once(force=args.force)
    return run_daemon()


if __name__ == '__main__':
    raise SystemExit(main())
