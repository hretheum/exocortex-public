# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/processors/recipe.py — F6.3 recipe normalization.
#
# Two paths:
#   1. Frontmatter from web-clipper template already has structured ingredients
#      + steps + cuisine + servings. Deterministic — no LLM.
#   2. Frontmatter is sparse (Instagram dump, raw web article). Falls back to
#      LLM extraction with strict tool schema.

from __future__ import annotations
import re
from pathlib import Path, PurePosixPath
from typing import Any, Optional

from exocortex.db import query_one
from exocortex.processors._common import (
    TENANT_ID, already_processed, call_tool, conn, emit_thought_for_source,
    estimate_cost_usd, fetch_source, mark_processed, _insert_edge, _upsert_entity,
)

PROCESSOR_NAME = 'recipe.v1'

# Common units we recognize without an LLM.
UNIT_PATTERN = re.compile(
    r'^\s*(?P<amount>\d+(?:[.,]\d+)?(?:\s*[-–/]\s*\d+(?:[.,]\d+)?)?)\s*'
    r'(?P<unit>g|kg|ml|l|łyżka|łyżeczka|łyżek|łyżeczek|szklanka|szklanek|'
    r'cup|cups|tbsp|tsp|oz|lb|szt|sztuk|szczypta|garść)?\s+'
    r'(?P<name>.+?)\s*$',
    re.IGNORECASE,
)


SYSTEM_PROMPT_FALLBACK = """\
You normalize a recipe from raw text into structured data.

Rules:
- ingredients: list of {amount, unit, name} objects. amount may be float or
  null (e.g. "do smaku" → null). unit optional. name in the original language.
- steps: ordered list of strings, one cooking step each, imperative voice.
- cuisine slug: italian, polish, japanese, mexican, indian, chinese, french,
  mediterranean, fusion, or empty.
- servings: integer or null.
- prep_time_min, cook_time_min: integers or null.
"""

TOOL_SCHEMA = {
    'name': 'normalize_recipe',
    'description': 'Extract structured recipe fields from raw text.',
    'input_schema': {
        'type': 'object',
        'properties': {
            'title': {'type': 'string'},
            'cuisine': {'type': 'string'},
            'servings': {'type': ['integer', 'null']},
            'prep_time_min': {'type': ['integer', 'null']},
            'cook_time_min': {'type': ['integer', 'null']},
            'ingredients': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'amount': {'type': ['number', 'null']},
                        'unit': {'type': ['string', 'null']},
                        'name': {'type': 'string'},
                    },
                    'required': ['name'],
                    'additionalProperties': False,
                },
            },
            'steps': {'type': 'array', 'items': {'type': 'string'}},
            'tags': {'type': 'array', 'items': {'type': 'string'}},
        },
        'required': ['title', 'ingredients', 'steps'],
        'additionalProperties': False,
    },
}

TITLE_PLACEHOLDER = '(untitled recipe)'


# ─────────────────────────── Deterministic parsing ───────────────────────────

def _parse_ingredient_line(line: str) -> dict[str, Any]:
    """Best-effort regex parse. Returns {amount, unit, name} with nulls when uncertain."""
    line = line.strip().lstrip('-*•').strip()
    if not line:
        return {}
    m = UNIT_PATTERN.match(line)
    if not m:
        return {'amount': None, 'unit': None, 'name': line}
    amount_raw = m.group('amount').replace(',', '.').strip()
    # Handle range "200-300" → take low end.
    if re.search(r'[-–/]', amount_raw):
        first = re.split(r'[-–/]', amount_raw)[0].strip()
        try:
            amount = float(first)
        except ValueError:
            amount = None
    else:
        try:
            amount = float(amount_raw)
        except ValueError:
            amount = None
    return {
        'amount': amount,
        'unit': (m.group('unit') or None),
        'name': m.group('name').strip(),
    }


def _resolve_title(*, source_title: Optional[str], fm_title: Optional[str],
                   existing_title: Optional[str], llm_title: Optional[str],
                   vault_path: Optional[str]) -> str:
    """Pick a recipe title, preferring stability over a fresh LLM guess.

    Order: explicit title (so renaming a note still propagates) → the title
    we already stored → the LLM's guess → the source note's filename → a
    placeholder. Keeping the stored title ahead of the LLM is the point: a
    2026-08-02 reprocessing run returned no title for 66 of 283 recipes and
    overwrote good stored ones with the placeholder, collapsing all 66 onto
    one filename and leaving 65 recipes with no wiki page. The filename
    fallback matters because these notes carry no `title:` frontmatter —
    the filename IS the title, and is what those 66 were repaired from.
    """
    def clean(v: Optional[str]) -> Optional[str]:
        v = (v or '').strip()
        return v or None

    stored = clean(existing_title)
    if stored and stored == TITLE_PLACEHOLDER:
        stored = None
    from_file = None
    if vault_path:
        from_file = clean(PurePosixPath(vault_path).stem)

    return (clean(source_title) or clean(fm_title) or stored
            or clean(llm_title) or from_file or TITLE_PLACEHOLDER)


def _existing_images(source_id: str) -> list:
    """Image filenames already archived for this source's recipe thought."""
    row = query_one(
        "SELECT metadata->'images' AS images FROM thoughts "
        'WHERE tenant_id = %s AND source_id = %s AND thought_type = %s '
        'LIMIT 1',
        TENANT_ID, source_id, 'recipe',
    )
    images = (row or {}).get('images')
    return [str(i) for i in images] if isinstance(images, list) else []


def _archive_source_images(body: Optional[str], vault_path: Optional[str],
                           referer: Optional[str]) -> list:
    """Download the note's images into an `_attachments/` folder beside it.

    Kept next to the source note because that tree is already synced both
    ways — no new Syncthing folder — and the vault watcher ignores anything
    that is not a .md, so dropping files there cannot re-trigger ingest.
    The note itself is never rewritten, for the same reason.
    """
    if not vault_path:
        return []
    try:
        from exocortex import media
        from exocortex.settings import get_settings

        dest = get_settings().vault_path / Path(vault_path).parent / '_attachments'
        return media.archive_images(body, dest, referer=referer)
    except Exception as exc:  # noqa: BLE001 — pictures never block a recipe
        print(f'[recipe] WARN: image archiving failed for {vault_path}: {exc!r}')
        return []


def _existing_title(source_id: str) -> Optional[str]:
    """Title already stored for this source's recipe thought, if any."""
    row = query_one(
        "SELECT metadata->>'title' AS title FROM thoughts "
        'WHERE tenant_id = %s AND source_id = %s AND thought_type = %s '
        'LIMIT 1',
        TENANT_ID, source_id, 'recipe',
    )
    return (row or {}).get('title')


def _resolve_source_url(fm: dict) -> Optional[str]:
    """The recipe's real origin (Instagram link, book title, etc.) — some
    web-clipper variants write it to frontmatter 'source' rather than
    'url'/'uri' (the fields vault_watcher checks before falling back to the
    local file:// path). Note 'source' means something different elsewhere
    in the vault (work_meeting_note's note-taking integration name) — this
    reading is recipe-specific."""
    value = fm.get("source")
    if isinstance(value, str):
        value = value.strip()
    return value or None


def _normalize_from_frontmatter(fm_ingredients: list, fm_steps: list) -> tuple[list[dict], list[str]]:
    """Convert web-clipper frontmatter ingredients/steps to canonical shape."""
    ingredients = []
    for item in fm_ingredients or []:
        if isinstance(item, dict):
            ingredients.append({
                'amount': item.get('amount'),
                'unit': item.get('unit'),
                'name': item.get('name') or str(item),
            })
        else:
            parsed = _parse_ingredient_line(str(item))
            if parsed:
                ingredients.append(parsed)
    steps = [str(s).strip() for s in (fm_steps or []) if str(s).strip()]
    return ingredients, steps


# ─────────────────────────── Public API ───────────────────────────

def normalize(source_id: str, *, force: bool = False) -> dict:
    if not force and already_processed(source_id, PROCESSOR_NAME):
        return {'status': 'skipped', 'reason': 'already_processed', 'source_id': source_id}

    source = fetch_source(source_id)
    if source is None:
        return {'status': 'error', 'reason': 'source_not_found', 'source_id': source_id}

    meta = source.get('metadata') or {}
    fm = meta.get('frontmatter') or {}
    source_url = _resolve_source_url(fm)
    stored_title = _existing_title(source_id)
    vault_path = meta.get('vault_path')
    # Signed CDN URLs die in 4-5 days, so archive now and keep what we already
    # have: a later run finds the URLs dead and would otherwise drop them.
    images = _existing_images(source_id) or _archive_source_images(
        meta.get('raw_payload'), vault_path, source_url)

    # Path 1: web-clipper already filled structured fields.
    fm_ingredients = fm.get('ingredients')
    fm_steps = fm.get('steps')
    cost = 0.0

    if fm_ingredients and fm_steps:
        ingredients, steps = _normalize_from_frontmatter(fm_ingredients, fm_steps)
        cuisine = fm.get('cuisine') or ''
        servings = _safe_int(fm.get('servings'))
        prep_time = _safe_int(fm.get('prep_time_min'))
        cook_time = _safe_int(fm.get('cook_time_min'))
        title = _resolve_title(source_title=source.get('title'),
                               fm_title=fm.get('title'),
                               existing_title=stored_title,
                               llm_title=None, vault_path=vault_path)
        tags = fm.get('tags') or []
        mode = 'frontmatter'
    else:
        # Path 2: LLM extraction.
        body = (meta.get('raw_payload') or meta.get('excerpt') or source.get('title') or '').strip()
        if not body or len(body) < 50:
            out = {'status': 'error', 'reason': 'no_body', 'source_id': source_id}
            return out

        user_prompt = (
            f'TITLE: {source.get("title") or ""}\n'
            f'URL: {source["uri"]}\n\n'
            f'BODY:\n{body[:8000]}'
        )
        tool_input, usage = call_tool(SYSTEM_PROMPT_FALLBACK, user_prompt,
                                      TOOL_SCHEMA, max_tokens=2048,
                                      _use_case='second_brain.F6_recipe_processor')
        cost = estimate_cost_usd(usage)
        ingredients = tool_input.get('ingredients') or []
        steps = tool_input.get('steps') or []
        cuisine = tool_input.get('cuisine') or ''
        servings = tool_input.get('servings')
        prep_time = tool_input.get('prep_time_min')
        cook_time = tool_input.get('cook_time_min')
        title = _resolve_title(source_title=source.get('title'),
                               fm_title=fm.get('title'),
                               existing_title=stored_title,
                               llm_title=tool_input.get('title'),
                               vault_path=vault_path)
        tags = tool_input.get('tags') or []
        mode = 'llm'

    # Body for thought (Polish title cards make the wiki readable).
    parts = [f'# {title}']
    if source_url:
        parts.append(f'URL: {source_url}')
    for img in images:
        parts.append(f'\n![[{img}]]')
    if cuisine:
        parts.append(f'Kuchnia: {cuisine}')
    if servings:
        parts.append(f'Porcji: {servings}')
    if prep_time:
        parts.append(f'Przygotowanie: {prep_time} min')
    if cook_time:
        parts.append(f'Gotowanie: {cook_time} min')
    parts.append('\n## Składniki')
    for ing in ingredients:
        amount = ing.get('amount')
        unit = ing.get('unit') or ''
        name = ing.get('name', '')
        head = f'{amount} {unit}'.strip() if amount else ''
        parts.append(f'- {head} {name}'.strip())
    parts.append('\n## Kroki')
    for i, step in enumerate(steps, 1):
        parts.append(f'{i}. {step}')

    extracted_tags = {
        'extracted_at': _iso_now(),
        'extracted_by': PROCESSOR_NAME,
        'topic': [{'value': str(t), 'confidence': 0.85, 'new': False} for t in tags],
        '_recipe': {
            'cuisine': cuisine,
            'servings': servings,
            'prep_time_min': prep_time,
            'cook_time_min': cook_time,
            'ingredient_count': len(ingredients),
        },
    }

    thought_id = emit_thought_for_source(
        source_id=source_id,
        body='\n'.join(parts),
        thought_type='recipe',
        domain='cook',
        metadata={
            'title': title,
            'uri': source['uri'],
            'source_url': source_url,
            'images': images,
            'cuisine': cuisine,
            'servings': servings,
            'prep_time_min': prep_time,
            'cook_time_min': cook_time,
            'ingredients_normalized': ingredients,
            'steps': steps,
        },
        extracted_tags=extracted_tags,
    )

    # Ingredient entities — enable cross-recipe queries ("co mogę ugotować z X").
    with conn() as c:
        for ing in ingredients:
            name = ing.get('name', '').strip().lower()
            if not name or len(name) > 80:
                continue
            entity_id = _upsert_entity(c, name, 'ingredient', TENANT_ID)
            _insert_edge(c, {
                'tenant_id': TENANT_ID,
                'src_id': thought_id, 'src_type': 'thought',
                'dst_id': entity_id, 'dst_type': 'ingredient',
                'type': 'related_to',
                'created_by': 'processor:recipe',
            })

    out = {
        'status': 'ok',
        'mode': mode,
        'source_id': source_id,
        'thought_id': thought_id,
        'ingredient_count': len(ingredients),
        'step_count': len(steps),
        'cost_usd': round(cost, 6),
    }
    mark_processed(source_id, PROCESSOR_NAME, out)
    return out


# ─────────────────────────── Helpers ───────────────────────────

def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _safe_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


process = normalize
