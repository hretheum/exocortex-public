# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/processors/_common.py — shared helpers for F6.3 processors.

from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from exocortex._bootstrap import bootstrap

bootstrap()

from exocortex.db import (  # noqa: E402
    Jsonb, conn, get_embedding, query_one, update_where,
    _insert_edge, _upsert_entity,
)
from config.models import TagTaxonomy  # noqa: E402
from exocortex.settings import get_tenant_id  # noqa: E402

TENANT_ID = get_tenant_id()
TAXONOMY_PATH = Path(__file__).parent.parent.parent / 'config' / 'tag_taxonomy.yaml'

# Retained for backwards compatibility with code that reads LLM_MODEL directly
# (e.g. log strings). Actual model selection now happens in config/llm_routing.yaml.
LLM_MODEL = 'claude-haiku-4-5-20251001'

_taxonomy: Optional[TagTaxonomy] = None


def load_taxonomy() -> TagTaxonomy:
    global _taxonomy
    if _taxonomy is None:
        with TAXONOMY_PATH.open() as f:
            raw = yaml.safe_load(f) or {}
        _taxonomy = TagTaxonomy.from_yaml(raw)
    return _taxonomy


def taxonomy_vocab_block() -> str:
    """Render taxonomy as a compact vocab listing for cacheable system prompts."""
    tax = load_taxonomy()
    lines: list[str] = []
    for axis in ('client', 'project', 'activity', 'topic', 'status'):
        items = getattr(tax, axis) or []
        lines.append(f'\n## {axis.upper()} ({len(items)} tags)')
        for it in items:
            aliases = it.aliases or []
            alias_str = f' (aliases: {", ".join(aliases)})' if aliases else ''
            lines.append(f"- `{it.tag}` — {it.description}{alias_str}")
    return '\n'.join(lines)


# ─────────────────────────── Source row helpers ───────────────────────────

def fetch_source(source_id: str) -> Optional[dict]:
    """Read a raw_sources row by id (tenant-filtered)."""
    return query_one(
        'SELECT id, source_type, uri, title, author_name, published_at, '
        'source_name, metadata, ingested_at, acquired_at '
        'FROM raw_sources WHERE id = %s AND tenant_id = %s',
        source_id, TENANT_ID,
    )


def patch_metadata(source_id: str, patch: dict) -> None:
    """Merge `patch` into raw_sources.metadata. Read-modify-write."""
    row = query_one('SELECT metadata FROM raw_sources WHERE id = %s', source_id)
    current = (row or {}).get('metadata') or {}
    merged = {**current, **patch}
    update_where('raw_sources', {'metadata': merged}, 'id = %s', source_id)


def already_processed(source_id: str, processor_name: str) -> bool:
    """Check metadata.processors[processor_name] = run_id sentinel."""
    row = query_one('SELECT metadata FROM raw_sources WHERE id = %s', source_id)
    meta = (row or {}).get('metadata') or {}
    return processor_name in (meta.get('processors') or {})


def log_anomaly(source_id: str, processor_name: str, anomaly_type: str,
                detail: Optional[dict] = None) -> None:
    """Best-effort DB-backed anomaly log (F34 — replaces ad-hoc per-processor
    TSV files, e.g. workers/ingest.py's data/discovery/ingest_anomalies.tsv,
    which doesn't survive container rebuilds and isn't queryable). Insert
    failures are swallowed — never block the caller on a diagnostic write."""
    try:
        with conn() as c:
            c.execute(
                'INSERT INTO processor_anomalies '
                '(tenant_id, source_id, processor_name, anomaly_type, detail) '
                'VALUES (%s, %s, %s, %s, %s)',
                (TENANT_ID, source_id, processor_name, anomaly_type, Jsonb(detail or {})),
            )
    except Exception:
        pass


def mark_processed(source_id: str, processor_name: str, output: dict) -> None:
    """Stamp metadata.processors[processor_name] with run timestamp + output summary."""
    row = query_one('SELECT metadata FROM raw_sources WHERE id = %s', source_id)
    meta = (row or {}).get('metadata') or {}
    procs = dict(meta.get('processors') or {})
    procs[processor_name] = {
        'processed_at': datetime.now(timezone.utc).isoformat(),
        'output': output,
    }
    meta['processors'] = procs
    update_where('raw_sources', {'metadata': meta}, 'id = %s', source_id)


# ─────────────────────────── Thought + edge persistence ───────────────────────────

def emit_thought_for_source(source_id: str, body: str, thought_type: str,
                            domain: str,
                            metadata: Optional[dict] = None,
                            extracted_tags: Optional[dict] = None) -> str:
    """Insert a thought row + acquired_from edge → raw_source. Returns thought_id.

    Idempotent: if a thought with the same source_id + thought_type already
    exists (= we already processed this source), update it instead.
    """
    full_meta = {'domain': domain, **(metadata or {})}
    embedding = get_embedding(body)

    with conn() as c:
        existing = c.execute(
            'SELECT id FROM thoughts '
            'WHERE tenant_id = %s AND source_id = %s AND thought_type = %s '
            'LIMIT 1',
            (TENANT_ID, source_id, thought_type),
        ).fetchone()

        if existing:
            tid = str(existing['id'])
            c.execute(
                'UPDATE thoughts SET body = %s, metadata = %s, embedding = %s '
                'WHERE id = %s',
                (
                    body,
                    Jsonb(full_meta),
                    '[' + ','.join(repr(float(x)) for x in (embedding or [])) + ']'
                    if embedding else None,
                    tid,
                ),
            )
            if extracted_tags:
                c.execute('UPDATE thoughts SET extracted_tags = %s WHERE id = %s',
                          (Jsonb(extracted_tags), tid))
        else:
            row = c.execute(
                'INSERT INTO thoughts (tenant_id, source_id, body, thought_type, '
                'author, metadata, embedding, extracted_tags) '
                'VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id',
                (
                    TENANT_ID, source_id, body, thought_type, 'agent:processor',
                    Jsonb(full_meta),
                    '[' + ','.join(repr(float(x)) for x in (embedding or [])) + ']'
                    if embedding else None,
                    Jsonb(extracted_tags or {}),
                ),
            ).fetchone()
            tid = str(row['id'])

        # acquired_from edge: thought ← raw_source.
        _insert_edge(c, {
            'tenant_id': TENANT_ID,
            'src_id': tid, 'src_type': 'thought',
            'dst_id': source_id, 'dst_type': 'raw_source',
            'type': 'acquired_from',
            'created_by': 'processor',
        })

        # mentions_person edges from extracted entities (persons axis).
        for entity_name in (extracted_tags or {}).get('_entities_person') or []:
            entity_id = _upsert_entity(c, entity_name, 'person', TENANT_ID)
            _insert_edge(c, {
                'tenant_id': TENANT_ID,
                'src_id': tid, 'src_type': 'thought',
                'dst_id': entity_id, 'dst_type': 'person',
                'type': 'mentions_person',
                'created_by': 'processor',
            })

    return tid


# ─────────────────────────── LLM tool-call helper ───────────────────────────

# Anthropic native schema is `{name, description, input_schema}`. Some legacy
# call sites in this repo use OpenAI-style `parameters` instead — normalize.
def _normalize_schema(schema: dict) -> dict:
    if 'input_schema' in schema:
        return schema
    if 'parameters' in schema:
        return {
            'name': schema['name'],
            'description': schema.get('description', ''),
            'input_schema': schema['parameters'],
        }
    return schema


def call_tool(system_prompt: str, user_prompt: str, tool_schema: dict,
              *, max_tokens: int = 1024,
              cache_system: bool = True,
              _use_case: str = 'second_brain.default') -> tuple[dict, dict]:
    """Single LLM tool call routed via llm_router. Returns (tool_input, usage_dict).

    The `_use_case` kwarg selects routing/pricing per `config/llm_routing.yaml`.
    Legacy callers without `_use_case` land on `second_brain.default` which
    routes to DeepInfra Qwen with Anthropic fallback.

    The returned `usage_dict` mirrors the pre-router shape (input_tokens /
    output_tokens / cache_creation_input_tokens / cache_read_input_tokens) so
    existing `estimate_cost_usd` callers keep working without changes — but
    the authoritative cost lives in the router's telemetry sink (already
    persisted to llm_provider_runs).
    """
    from exocortex import llm_routing
    llm_routing.initialize()
    from llm_router import call_tool as _router_call_tool

    schema = _normalize_schema(tool_schema)
    tool_input, usage = _router_call_tool(
        use_case=_use_case,
        system=system_prompt,
        user=user_prompt,
        schema=schema,
        max_tokens=max_tokens,
        cache_system=cache_system,
    )
    legacy_usage = {
        'input_tokens': usage.input_tokens,
        'output_tokens': usage.output_tokens,
        'cache_creation_input_tokens': usage.cache_creation_input_tokens,
        'cache_read_input_tokens': usage.cache_read_input_tokens,
        # Augmenting fields (router-aware callers can read these).
        '_provider': usage.provider,
        '_model': usage.model,
        '_cost_usd': usage.cost_usd,
        '_latency_ms': usage.latency_ms,
        '_use_case': usage.use_case,
        '_fallback_chain': list(usage.fallback_chain),
    }
    return tool_input, legacy_usage


from exocortex.llm_utils import estimate_cost_usd  # noqa: F401 - re-exported for processor compatibility

# ── Legacy compat (F31-CLN-01): estimate_cost_usd moved to llm_utils ──
