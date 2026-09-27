# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.
# exocortex/sources/claude_sessions.py — ingest of Claude Code transcripts.
#
# Reads ~/.claude/projects/<proj>/<uuid>.jsonl, keeps ONLY the dialogue (user
# prompts + assistant prose — never tool_result/tool_use), runs it through
# fail-closed redaction, and POSTs to Capture API as source_type=claude-session.
# Design rationale + threat model: docs/architecture/ingest-sesji-claude-code.md.
#
# CLI:
#     python3 -m exocortex.sources.claude_sessions --once
#     python3 -m exocortex.sources.claude_sessions --once --dry-run
#     python3 -m exocortex.sources.claude_sessions --once --from /path/to/dir
#     python3 -m exocortex.sources.claude_sessions --once --max-sessions 20

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from exocortex.sources._session_redaction import Verdict, redact

CAPTURE_API_URL = os.environ.get('CAPTURE_API_URL', 'http://localhost:8000').rstrip('/')
CAPTURE_API_TOKEN = os.environ.get('CAPTURE_API_TOKEN', '').strip()
DEFAULT_SESSIONS_DIR = Path.home() / '.claude' / 'projects'
SOURCE_TYPE = 'claude-session'
DEFAULT_TIMEOUT = 30.0

# Only these blocks are dialogue. Everything else in a .jsonl (tool_use,
# tool_result, thinking, attachments, queue-operation, ...) is deliberately
# ignored — see the design doc for why.
_DIALOGUE_ASSISTANT_BLOCK = 'text'


class SessionError(Exception):
    """Non-fatal per-session failure. Adapter logs and skips."""


def _read_records(path: Path):
    """Yield parsed JSON records, skipping malformed lines without failing."""
    with open(path, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue


def _extract_dialogue(records: list[dict]) -> tuple[str, str | None, str | None]:
    """Return (dialogue_text, ai_title, session_id) from a session's records.

    Dialogue = user prompts (string content) + assistant text blocks, in file
    order, each turn prefixed so the LLM can tell who spoke. tool_result,
    tool_use and thinking are dropped on purpose.
    """
    parts: list[str] = []
    ai_title: str | None = None
    session_id: str | None = None

    for rec in records:
        rtype = rec.get('type')
        if session_id is None:
            session_id = rec.get('sessionId')
        if rtype == 'ai-title':
            ai_title = rec.get('aiTitle') or ai_title
            continue
        if rtype == 'user':
            content = (rec.get('message') or {}).get('content')
            if isinstance(content, str) and content.strip():
                parts.append(f'## Użytkownik\n{content.strip()}')
            # list content on a user record is tool_result — skip entirely.
        elif rtype == 'assistant':
            content = (rec.get('message') or {}).get('content')
            if isinstance(content, list):
                texts = [
                    b.get('text', '') for b in content
                    if isinstance(b, dict) and b.get('type') == _DIALOGUE_ASSISTANT_BLOCK
                ]
                joined = '\n'.join(t for t in texts if t.strip())
                if joined.strip():
                    parts.append(f'## Claude\n{joined.strip()}')

    return '\n\n'.join(parts), ai_title, session_id


@dataclass(frozen=True)
class SessionOutcome:
    """What analysing one session file decided. Exactly one of the states:
    - payload set, verdict clean/redacted  → ingest it;
    - payload None, verdict REFUSE          → fail-closed drop, `reason` set;
    - payload None, has_dialogue False      → nothing to say, skip quietly.
    """
    payload: dict | None
    verdict: Verdict | None
    reason: str
    has_dialogue: bool


def analyze(path: Path) -> SessionOutcome:
    """Single source of truth: read a session, extract dialogue, redact,
    and decide. `run_once` and the dry-run report both go through this, so
    counters and the refusal list can never disagree."""
    records = list(_read_records(Path(path)))
    dialogue, ai_title, session_id = _extract_dialogue(records)

    if not dialogue.strip() or not session_id:
        return SessionOutcome(None, None, '', has_dialogue=False)

    result = redact(dialogue)
    if result.verdict == Verdict.REFUSE:
        # Body is never sent anywhere; only the reason class survives.
        return SessionOutcome(None, Verdict.REFUSE, result.reason, has_dialogue=True)

    title = (ai_title or f'Sesja {session_id[:8]}').strip()[:500]
    payload = {
        'source_type': SOURCE_TYPE,
        'uri': f'claude-session://{session_id}',
        'title': title,
        'source_name': 'Claude Code',
        'metadata': {
            'raw_payload': result.text,
            'redaction_verdict': result.verdict.value,
            'session_id': session_id,
        },
    }
    return SessionOutcome(payload, result.verdict, result.reason, has_dialogue=True)


def build_payload(path: Path) -> dict | None:
    """Capture API payload for one session, or None to skip (no dialogue,
    no session id, or fail-closed refusal). Thin wrapper over `analyze` — the
    returned payload is already redacted, so no raw secret can be inside it."""
    return analyze(path).payload


def post_capture(payload: dict, *, timeout: float = DEFAULT_TIMEOUT) -> dict:
    data = json.dumps(payload).encode('utf-8')
    headers = {'Content-Type': 'application/json'}
    if CAPTURE_API_TOKEN:
        headers['Authorization'] = f'Bearer {CAPTURE_API_TOKEN}'
    req = urllib.request.Request(f'{CAPTURE_API_URL}/capture', data=data,
                                 headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        raise SessionError(f'HTTP {e.code}: {e.read().decode("utf-8", "replace")}') from e
    except urllib.error.URLError as e:
        raise SessionError(f'URLError: {e.reason}') from e


def _iter_session_files(root: Path):
    yield from sorted(root.glob('*/*.jsonl'))


def run_once(root: Path, *, dry_run: bool = False,
             max_sessions: int | None = None) -> dict:
    counts = {'seen': 0, 'created': 0, 'unchanged': 0,
              'refused': 0, 'no_dialogue': 0, 'error': 0}
    for path in _iter_session_files(root):
        if max_sessions and counts['seen'] >= max_sessions:
            break
        counts['seen'] += 1
        try:
            outcome = analyze(path)
        except Exception as exc:  # noqa: BLE001 — one bad file never stops the run
            counts['error'] += 1
            print(f'[claude-session] ERROR {path.name}: {exc!r}', file=sys.stderr)
            continue
        if outcome.verdict == Verdict.REFUSE:
            counts['refused'] += 1
            # Reason class only — never the offending value.
            print(f'  REFUSE   {path.name} — {outcome.reason}')
            continue
        if outcome.payload is None:
            counts['no_dialogue'] += 1
            continue
        if dry_run:
            print(f'  + [{outcome.payload["metadata"]["redaction_verdict"]:8}] '
                  f'{outcome.payload["title"][:70]}')
            counts['created'] += 1
            continue
        try:
            resp = post_capture(outcome.payload)
            counts['created' if resp.get('created') else 'unchanged'] += 1
        except SessionError as exc:
            counts['error'] += 1
            print(f'[claude-session] POST failed {path.name}: {exc}', file=sys.stderr)
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Ingest Claude Code session transcripts.')
    parser.add_argument('--once', action='store_true',
                        help='Single pass over all sessions, then exit.')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be captured; POST nothing.')
    parser.add_argument('--from', dest='root', default=None,
                        help='Sessions dir (default ~/.claude/projects).')
    parser.add_argument('--max-sessions', type=int, default=None,
                        help='Cap sessions per pass (smoke testing).')
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser() if args.root else DEFAULT_SESSIONS_DIR
    if not root.exists():
        print(f'[claude-session] sessions dir not found: {root}', file=sys.stderr)
        return 1

    if not args.once:
        print('[claude-session] only --once is supported. Use a timer for cron.')
        return 2

    counts = run_once(root, dry_run=args.dry_run, max_sessions=args.max_sessions)
    print(f'[claude-session] done. counts={counts}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
