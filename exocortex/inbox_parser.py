# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/inbox_parser.py — run as cron every 6 hours

"""
Parses inbox.md blocks and ingests to L1.
Supports: FRP_SESSION, FRP_REVISIT, WORK_DECISION,
           PRINT_LOG, TC_NOTE, COOK_NOTE, PRIV_NOTE, SB_NOTE
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

from exocortex.db import (
    add_revisit,
    append_session_thought,
    complete_session,
    create_frp_session,
    find_session_by_date,
    ingest_note,
    ingest_print_log,
    ingest_source,
)


def process_inbox(tenant_id: str,
                  inbox_path: str | None = None) -> None:
    """
    Parses inbox.md blocks and ingests to L1.
    Supports: FRP_SESSION, FRP_REVISIT, WORK_DECISION,
              PRINT_LOG, TC_NOTE, COOK_NOTE, PRIV_NOTE, SB_NOTE
    """
    if inbox_path is None:
        inbox_path = os.environ.get('INBOX_PATH')
        if not inbox_path:
            raise ValueError("inbox_path not provided and INBOX_PATH env var not set")
    content = Path(inbox_path).read_text(encoding='utf-8')
    blocks = parse_blocks(content)

    for block in blocks:
        btype = block.get('type')

        if btype == 'FRP_SESSION':
            result = ingest_source(block['source_url'], tenant_id)
            sess = create_frp_session(
                result['content_id'],
                block['frame'], int(block['level']),
                context_note=block.get('context_note'),
                tenant_id=tenant_id
            )
            for ttype, body in extract_thoughts(block).items():
                append_session_thought(sess['session_id'],
                                       ttype, body,
                                       tenant_id=tenant_id)
            complete_session(
                sess['session_id'],
                int(block['resonance']),
                extract_tags(block),
                block.get('signal_today', '').lower() == 'true',
                tenant_id=tenant_id
            )

        elif btype == 'FRP_REVISIT':
            session_id = find_session_by_date(
                block['session_ref'], tenant_id)
            add_revisit(session_id, block['body'],
                        block.get('materializes'),
                        tenant_id=tenant_id)

        elif btype == 'WORK_DECISION':
            ingest_note(
                body=format_decision(block),
                domain='work',
                thought_type='work_decision',
                metadata={'project': block.get('project')},
                entity_links=build_person_links(
                    block.get('people_involved', '')),
                tenant_id=tenant_id
            )

        elif btype == 'PRINT_LOG':
            ingest_print_log(block, tenant_id=tenant_id)

        elif btype == 'TC_NOTE':
            ingest_note(
                body=block.get('body', ''),
                domain='tc',
                thought_type=f"tc_{block.get('subtype', 'note')}",
                metadata={'project': block.get('project'), 'status': block.get('status')},
                tenant_id=tenant_id,
            )

        elif btype == 'COOK_NOTE':
            ingest_note(
                body=block.get('body', ''),
                domain='cook',
                thought_type=f"cook_{block.get('subtype', 'note')}",
                metadata={'dish': block.get('dish'), 'rating': block.get('rating')},
                tenant_id=tenant_id,
            )

        elif btype == 'PRIV_NOTE':
            ingest_note(
                body=block.get('body', ''),
                domain='priv',
                thought_type=f"priv_{block.get('subtype', 'note')}",
                metadata={'context': block.get('context')},
                tenant_id=tenant_id,
            )

        elif btype == 'SB_NOTE':
            ingest_note(
                body=block.get('body', ''),
                domain='sb',
                thought_type=f"sb_{block.get('subtype', 'note')}",
                metadata={'area': block.get('area')},
                tenant_id=tenant_id,
            )

    archive_processed_blocks(inbox_path)


def parse_blocks(content: str) -> list[dict]:
    """Parse ---TYPE--- delimited blocks from inbox.md."""
    pattern = r'---(\w+)---\n(.*?)(?=\n---\w|$)'
    matches = re.findall(pattern, content, re.DOTALL)
    blocks = []
    for block_type, block_body in matches:
        block = {'type': block_type}
        for line in block_body.strip().split('\n'):
            if ':' in line:
                key, _, value = line.partition(':')
                block[key.strip().lower()] = value.strip()
        blocks.append(block)
    return blocks


def extract_thoughts(block: dict) -> dict:
    """Extract thought type → body mappings from an FRP session block."""
    thoughts = {}
    mapping = {
        'scenario': 'frp_scenario',
        'friction': 'frp_friction',
        'recognition': 'frp_recognition',
        'impulse': 'frp_impulse',
    }
    for key, ttype in mapping.items():
        if key in block:
            thoughts[ttype] = block[key]
    # Reflection includes prompt reference
    if 'reflection' in block:
        thoughts['frp_reflection'] = block['reflection']
    return thoughts


def extract_tags(block: dict) -> dict:
    """Extract domain/tech/change_type tags from block."""
    return {
        'domain': [t.strip() for t in block.get('tags_domain', '').split(',') if t.strip()],
        'tech': [t.strip() for t in block.get('tags_tech', '').split(',') if t.strip()],
    }


def format_decision(block: dict) -> str:
    """Format a work decision block into a structured thought body."""
    parts = []
    if block.get('context'):
        parts.append(f"Context: {block['context']}")
    if block.get('decision'):
        parts.append(f"Decision: {block['decision']}")
    if block.get('rationale'):
        parts.append(f"Rationale: {block['rationale']}")
    if block.get('alternatives_rejected'):
        parts.append(f"Alternatives rejected: {block['alternatives_rejected']}")
    return '\n'.join(parts)


def build_person_links(people_str: str) -> list[dict]:
    """Build entity links for people involved."""
    return [
        {'entity_canonical_name': name.strip(),
         'entity_type': 'person',
         'edge_type': 'attended_meeting'}
        for name in people_str.split(',') if name.strip()
    ]



def archive_processed_blocks(inbox_path: str) -> None:
    """Move processed blocks to archive (clear inbox)."""
    archive_path = inbox_path.replace('.md', f'_archived_{datetime.now().strftime("%Y%m%d_%H%M%S")}.md')
    Path(inbox_path).rename(archive_path)
    Path(inbox_path).write_text(
        "<!-- /inbox/sessions_raw.md — the only file you edit manually -->\n"
        "<!-- Cron every 6h: worker parses and ingests to L1 -->\n"
        "<!-- Blocks delimited by ---TYPE--- -->\n\n",
        encoding='utf-8'
    )




if __name__ == '__main__':
    import os

    from exocortex.settings import get_tenant_id
    tenant = get_tenant_id()
    inbox = os.environ.get('INBOX_PATH')
    process_inbox(tenant, inbox)
