# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/processors/youtube.py — F6.3 YouTube transcript summary.
#
# Tries to fetch the transcript via youtube-transcript-api (no API key required).
# If transcripts disabled or library missing, falls back to title + description
# from the web-clipper frontmatter (lower quality, but still useful).

from __future__ import annotations
import re
from typing import Optional

from exocortex.processors._common import (
    already_processed, call_tool, emit_thought_for_source, estimate_cost_usd,
    fetch_source, mark_processed,
)

PROCESSOR_NAME = 'youtube.v1'

SYSTEM_PROMPT = """\
You summarize a YouTube tutorial/talk transcript into a structured note for a
personal knowledge OS.
"""

TOOL_SCHEMA = {
    'name': 'summarize_youtube',
    'input_schema': {
        'type': 'object',
        'properties': {
            'summary_pl': {'type': 'string', 'description': '3-5 sentence Polish summary.'},
            'key_takeaways': {'type': 'array', 'items': {'type': 'string'}},
            'chapters': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'timestamp_min': {'type': 'integer'},
                        'title': {'type': 'string'},
                    },
                    'required': ['title'],
                    'additionalProperties': False,
                },
            },
            'topic_tags': {'type': 'array', 'items': {'type': 'string'}},
        },
        'required': ['summary_pl'],
        'additionalProperties': False,
    },
}

VIDEO_ID_RE = re.compile(r'(?:v=|youtu\.be/|/embed/)([A-Za-z0-9_-]{11})')


def _video_id(uri: str) -> Optional[str]:
    m = VIDEO_ID_RE.search(uri)
    return m.group(1) if m else None


def _fetch_transcript(video_id: str) -> Optional[str]:
    """Fetch transcript via youtube-transcript-api. Returns concatenated text or None."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore
    except ImportError:
        return None
    try:
        items = YouTubeTranscriptApi.get_transcript(video_id, languages=['pl', 'en'])
    except Exception:
        return None
    return ' '.join(it.get('text', '') for it in items)


def transcript_summary(source_id: str, *, force: bool = False) -> dict:
    if not force and already_processed(source_id, PROCESSOR_NAME):
        return {'status': 'skipped', 'reason': 'already_processed', 'source_id': source_id}
    source = fetch_source(source_id)
    if source is None:
        return {'status': 'error', 'reason': 'source_not_found', 'source_id': source_id}

    video_id = _video_id(source['uri'])
    transcript = _fetch_transcript(video_id) if video_id else None

    meta = source.get('metadata') or {}
    body_chunk = transcript or meta.get('raw_payload') or meta.get('excerpt') or ''
    if not body_chunk or len(body_chunk) < 100:
        return {'status': 'error', 'reason': 'no_transcript_or_body', 'source_id': source_id}

    user_prompt = (
        f'TITLE: {source.get("title") or ""}\n'
        f'URL: {source["uri"]}\n'
        f'TRANSCRIPT_OR_BODY:\n{body_chunk[:12000]}'
    )
    tool_input, usage = call_tool(SYSTEM_PROMPT, user_prompt, TOOL_SCHEMA, max_tokens=1024,
                                  _use_case='second_brain.F6_youtube_processor')
    cost = estimate_cost_usd(usage)

    parts = [f'# {source.get("title") or "YouTube"}',
             f'URL: {source["uri"]}',
             '\n## Streszczenie', tool_input['summary_pl']]
    if tool_input.get('key_takeaways'):
        parts.append('\n## Najważniejsze wnioski')
        parts.extend(f'- {t}' for t in tool_input['key_takeaways'])
    if tool_input.get('chapters'):
        parts.append('\n## Rozdziały')
        for ch in tool_input['chapters']:
            ts = ch.get('timestamp_min')
            ts_s = f'[{ts:02d}:00] ' if ts is not None else ''
            parts.append(f'- {ts_s}{ch["title"]}')

    thought_id = emit_thought_for_source(
        source_id=source_id, body='\n'.join(parts),
        thought_type='youtube_summary',
        domain=meta.get('domain') or 'work',
        metadata={'title': source.get('title'), 'uri': source['uri'],
                  'transcript_available': transcript is not None},
        extracted_tags={
            'extracted_at': _iso_now(),
            'extracted_by': PROCESSOR_NAME,
            'topic': [{'value': str(t), 'confidence': 0.8, 'new': True}
                      for t in (tool_input.get('topic_tags') or [])],
        },
    )
    out = {'status': 'ok', 'source_id': source_id, 'thought_id': thought_id,
           'has_transcript': transcript is not None,
           'cost_usd': round(cost, 6)}
    mark_processed(source_id, PROCESSOR_NAME, out)
    return out


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


process = transcript_summary
