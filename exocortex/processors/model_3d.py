# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/processors/model_3d.py — F6.3 3D model print params extraction.
#
# Most of the work is done by the web-clipper template (frontmatter already has
# layer_height_mm, infill_pct, supports, material, files). This processor:
#   1. Validates + normalizes those fields.
#   2. Falls back to LLM extraction when frontmatter is missing.
#   3. Emits printer/material entities for cross-model queries.

from __future__ import annotations

from exocortex.processors._common import (
    TENANT_ID,
    _insert_edge,
    _upsert_entity,
    already_processed,
    call_tool,
    conn,
    emit_thought_for_source,
    estimate_cost_usd,
    fetch_source,
    mark_processed,
)

PROCESSOR_NAME = 'model_3d.v1'

SYSTEM_PROMPT = """\
You extract 3D-print parameters from a model listing page (Printables,
Thingiverse, MakerWorld, etc.).
"""

TOOL_SCHEMA = {
    'name': 'extract_print_params',
    'input_schema': {
        'type': 'object',
        'properties': {
            'designer': {'type': 'string'},
            'files': {'type': 'array', 'items': {'type': 'string'}},
            'layer_height_mm': {'type': ['number', 'null']},
            'infill_pct': {'type': ['integer', 'null']},
            'supports': {'type': 'string', 'enum': ['none', 'partial', 'tree', 'standard']},
            'material': {'type': 'array', 'items': {'type': 'string'}},
            'print_time_min': {'type': ['integer', 'null']},
            'use_case_tags': {'type': 'array', 'items': {'type': 'string'}},
        },
        'additionalProperties': False,
    },
}


def extract_print_params(source_id: str, *, force: bool = False) -> dict:
    if not force and already_processed(source_id, PROCESSOR_NAME):
        return {'status': 'skipped', 'reason': 'already_processed', 'source_id': source_id}
    source = fetch_source(source_id)
    if source is None:
        return {'status': 'error', 'reason': 'source_not_found', 'source_id': source_id}

    meta = source.get('metadata') or {}
    fm = meta.get('frontmatter') or {}

    cost = 0.0
    if fm.get('files') and fm.get('material'):
        # Frontmatter path — no LLM.
        params = {
            'designer': fm.get('designer'),
            'files': fm.get('files') or [],
            'layer_height_mm': fm.get('layer_height_mm'),
            'infill_pct': fm.get('infill_pct'),
            'supports': fm.get('supports') or 'none',
            'material': fm.get('material') or [],
            'print_time_min': fm.get('print_time_min'),
            'use_case_tags': fm.get('tags') or [],
        }
        mode = 'frontmatter'
    else:
        body = (meta.get('raw_payload') or meta.get('excerpt') or '').strip()
        if not body or len(body) < 50:
            return {'status': 'error', 'reason': 'no_body', 'source_id': source_id}
        user_prompt = (
            f'TITLE: {source.get("title") or ""}\n'
            f'URL: {source["uri"]}\n\n'
            f'PAGE:\n{body[:8000]}'
        )
        params, usage = call_tool(SYSTEM_PROMPT, user_prompt, TOOL_SCHEMA, max_tokens=512,
                                  _use_case='second_brain.F6_3d_model_processor')
        cost = estimate_cost_usd(usage)
        mode = 'llm'

    parts = [f'# {source.get("title") or "3D model"}',
             f'URL: {source["uri"]}']
    if params.get('designer'):
        parts.append(f'Designer: {params["designer"]}')
    parts.append('\n## Parametry druku')
    if params.get('layer_height_mm'):
        parts.append(f'- Layer height: {params["layer_height_mm"]} mm')
    if params.get('infill_pct'):
        parts.append(f'- Infill: {params["infill_pct"]}%')
    if params.get('supports'):
        parts.append(f'- Supports: {params["supports"]}')
    if params.get('material'):
        parts.append(f'- Materiał: {", ".join(params["material"])}')
    if params.get('print_time_min'):
        parts.append(f'- Czas druku: {params["print_time_min"]} min')
    if params.get('files'):
        parts.append('\n## Pliki')
        parts.extend(f'- {f}' for f in params['files'])

    thought_id = emit_thought_for_source(
        source_id=source_id, body='\n'.join(parts),
        thought_type='3d_model', domain='3d',
        metadata={'title': source.get('title'), 'uri': source['uri'], **params},
        extracted_tags={
            'extracted_at': _iso_now(),
            'extracted_by': PROCESSOR_NAME,
            'topic': [{'value': str(t), 'confidence': 0.85, 'new': False}
                      for t in (params.get('use_case_tags') or [])],
        },
    )
    # Material entities → enables queries like "all models printed in PETG".
    with conn() as c:
        for mat in (params.get('material') or []):
            entity_id = _upsert_entity(c, mat.upper(), 'material', TENANT_ID)
            _insert_edge(c, {
                'tenant_id': TENANT_ID,
                'src_id': thought_id, 'src_type': 'thought',
                'dst_id': entity_id, 'dst_type': 'material',
                'type': 'printed_with',
                'created_by': 'processor:model_3d',
            })
    out = {'status': 'ok', 'mode': mode, 'source_id': source_id,
           'thought_id': thought_id, 'cost_usd': round(cost, 6)}
    mark_processed(source_id, PROCESSOR_NAME, out)
    return out


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


process = extract_print_params
