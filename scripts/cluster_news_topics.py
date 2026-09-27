#!/usr/bin/env -S python3.12
# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# scripts/cluster_news_topics.py — F8.8.x.H2.1: cluster newsletter topics
# into 7-9 top-level categories via claude-haiku-4-5.
#
# Inputs: thoughts.extracted_tags->'topic' rollup over thought_type=
#         'newsletter_synthesis' (~311 distinct slugs).
# LLM: claude-haiku-4-5-20251001, strict tool use (`propose_clusters`),
#      cacheable system prompt (5 min ephemeral), F5.3 pattern.
# Output: config/news_topic_clusters.yaml (closed cluster slugs, open
#         membership — see Q1/Q2/Q3 locks 2026-05-03).
# Cache: data/discovery/cluster_runs/{taxonomy_hash}.json (full prompt
#        + response, reproducibility for review).
#
# Q1 (closed slugs): to add a new top-level cluster, edit YAML by hand;
#   --update only re-assigns currently-unmapped topics to existing slugs.
# Q2 (open membership): future newsletter topics get LLM-classified into
#   the existing slugs (or _misc fallthrough).
# Q3 (scope): news axis only. Does NOT touch config/tag_taxonomy.yaml.

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from exocortex.db import query

load_dotenv(dotenv_path=_REPO_ROOT / 'config' / '.env')

logger = logging.getLogger(__name__)

LLM_MODEL = 'claude-haiku-4-5-20251001'
TENANT_ID = os.environ.get('TENANT_ID')

OUTPUT_YAML = _REPO_ROOT / 'config' / 'news_topic_clusters.yaml'
CACHE_DIR = _REPO_ROOT / 'data' / 'discovery' / 'cluster_runs'

PROMPT_VERSION = '1'


# ─────────────────────────────────────── Topic rollup SQL ──

def fetch_topic_rollup(tenant_id: str) -> list[dict]:
    """All distinct topic slugs across newsletter_synthesis thoughts with
    mention counts and one sample title (most recent thought)."""
    sql = """
    SELECT
        (te.value->>'value')::text AS slug,
        COUNT(*)                   AS mentions,
        (array_agg(th.metadata->>'title' ORDER BY th.created_at DESC))[1:1]
                                   AS sample_titles
    FROM thoughts th,
         LATERAL jsonb_array_elements(th.extracted_tags->'topic') AS te(value)
    WHERE th.tenant_id = %s
      AND th.thought_type = 'newsletter_synthesis'
    GROUP BY (te.value->>'value')::text
    ORDER BY mentions DESC, slug
    """
    return query(sql, tenant_id)


def taxonomy_hash(rows: list[dict]) -> str:
    """Stable hash so cached runs invalidate when topic distribution changes."""
    payload = json.dumps(
        [{'slug': r['slug'], 'mentions': r['mentions']} for r in rows],
        sort_keys=True, ensure_ascii=False,
    ).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()[:12]


# ─────────────────────────────────────── Cache (full run) ──

def cache_path(tax_hash: str) -> Path:
    return CACHE_DIR / f'{tax_hash}.json'


def load_cached_run(tax_hash: str) -> dict | None:
    p = cache_path(tax_hash)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        logger.warning('cache file %s corrupted, ignoring', p)
        return None


def save_cached_run(tax_hash: str, payload: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path(tax_hash).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding='utf-8',
    )


# ─────────────────────────────────────── LLM clustering ──

CLUSTER_TOOL = {
    'name': 'propose_clusters',
    'description': (
        'Propose 7-9 top-level clusters that organize the given newsletter '
        'topic slugs into navigable categories. Each topic must be assigned '
        'to exactly one cluster (or to _misc if it does not fit cleanly).'
    ),
    'input_schema': {
        'type': 'object',
        'properties': {
            'clusters': {
                'type': 'array',
                'description': '7-9 top-level cluster definitions.',
                'items': {
                    'type': 'object',
                    'properties': {
                        'slug': {
                            'type': 'string',
                            'description': 'kebab-case identifier (e.g. ai-foundations).',
                        },
                        'label': {
                            'type': 'string',
                            'description': 'Human-readable English label (e.g. "AI Foundations").',
                        },
                        'emoji': {
                            'type': 'string',
                            'description': 'Single emoji glyph for visual nav.',
                        },
                        'description': {
                            'type': 'string',
                            'description': '1-2 sentence English description of what the cluster contains.',
                        },
                        'topics': {
                            'type': 'array',
                            'items': {'type': 'string'},
                            'description': 'List of input topic slugs assigned to this cluster.',
                        },
                    },
                    'required': ['slug', 'label', 'emoji', 'description', 'topics'],
                    'additionalProperties': False,
                },
            },
            'misc_topics': {
                'type': 'array',
                'items': {'type': 'string'},
                'description': 'Topic slugs that do not fit any cluster (will land in _misc).',
            },
        },
        'required': ['clusters'],
        'additionalProperties': False,
    },
}


SYSTEM_PROMPT_TEXT = """\
Jesteś ekspertem od taksonomii semantycznej dla newsletter knowledge base
designera/managera AI. Twoje zadanie: pogrupować ~311 unikalnych topic
slugów (extracted z `newsletter_synthesis` thoughts) w 7-9 top-level
nawigacyjnych klastrów, na podstawie audytu w `docs/pub/2026-05-03-topic-taxonomy-audit.md`.

ZASADY:
1. **7-9 klastrów** to docelowy fanout (nie hardcode N=7 — jeśli dane wymagają,
   możesz zaproponować 8 lub 9, np. dzieląc AI Foundations na "AI Core" + "AI Tooling").
2. **Każdy topic slug w wejściu powinien być przypisany dokładnie do jednego
   klastra** (lub do `misc_topics` jeśli faktycznie nie pasuje). NIE duplikuj
   slugów między klastrami.
3. **Pokrycie** — celuj w >85% topiców w klastrach (resztę do `misc_topics`).
   Nie wciskaj na siłę — `misc` jest legitymny dla deep-tech singletons
   (b-trees, lsm-trees, jvm-internals) i editorial residue (decision, contradiction).
4. **Slug naming**: kebab-case, descriptive ale krótkie. Audit §4 proponuje:
   - `ai-foundations` (core LLM/agent/prompt/RAG technology)
   - `automation-workflow` (automation/integration/orchestration)
   - `engineering-infrastructure` (api/deployment/cloud/k8s/databases)
   - `governance-risk-security` (gdpr/compliance/cybersecurity/ai-safety)
   - `product-strategy-business` (positioning/pricing/enterprise/partnerships)
   - `design-ux` (design-system/user-research/figma/wcag)
   - `society-labor-ethics` (hiring/layoffs/parasocial/digital-equity)
   To są SUGESTIE — możesz je przyjąć, zmienić nazewnictwo, lub zaproponować inny podział
   jeśli dane uzasadniają. Audit §6 wskazuje że `mcp` family mógłby być oddzielny micro-cluster.
5. **Emoji** — pojedynczy glyph, intuicyjny dla labela.
6. **Description** — 1-2 zdania po angielsku, opisuje "co tu znajdę".

OUTPUT FORMAT: wywołaj tool `propose_clusters` z `clusters[]` i opcjonalnie
`misc_topics[]`. NIE pisz nic poza tool call.

WAŻNE — KAŻDY topic z input listy MUSI być przypisany albo do `clusters[].topics`
albo do `misc_topics`. Brak duplikatów. Brak nowych slugów których nie ma w input.
"""


def build_system_prompt() -> list[dict]:
    return [{
        'type': 'text',
        'text': SYSTEM_PROMPT_TEXT,
        'cache_control': {'type': 'ephemeral'},
    }]


def build_user_prompt(rows: list[dict]) -> str:
    lines = [
        f'Zadanie: pogrupuj poniższe {len(rows)} unikalnych topic slugów w 7-9 klastrów.',
        '',
        'Format wejścia: `<mentions>×  <slug>` (sortowane DESC po mentions).',
        '',
        '```',
    ]
    for r in rows:
        lines.append(f"{r['mentions']:>3}×  {r['slug']}")
    lines.append('```')
    lines.append('')
    lines.append('Wywołaj `propose_clusters` z 7-9 klastrów + `misc_topics` dla nie-pasujących.')
    return '\n'.join(lines)


def _normalize_clusters(raw: dict, input_slugs: set[str] | None = None
                        ) -> tuple[list[dict], list[str]]:
    """Defensive normalizer at LLM-output boundary (F3 lesson).

    Coerces LLM output shape variations and enforces 3 invariants:
    1. Each input slug appears in exactly one place (cluster topics OR misc).
    2. No output slug is hallucinated (must be in input_slugs if provided).
    3. Within a cluster, no duplicate topic strings.

    LLM occasionally returns `topics` as list[dict] (e.g. {slug: '...', why: '...'})
    instead of list[str] — coerce both shapes. Cross-cluster duplicates are
    resolved in favor of the FIRST cluster the slug appears in (LLM ordering
    typically matches strength-of-fit). Hallucinated slugs are dropped silently
    (logged in coverage_report). Input slugs not assigned anywhere fall through
    to misc."""
    def _coerce_to_str(t: Any) -> str | None:
        if isinstance(t, str):
            return t.strip() or None
        if isinstance(t, dict):
            slug = t.get('slug') or t.get('value') or t.get('topic')
            if isinstance(slug, str):
                return slug.strip() or None
        return None

    clusters_out: list[dict] = []
    seen_globally: set[str] = set()
    for cl in raw.get('clusters') or []:
        if not isinstance(cl, dict):
            continue
        topics_raw = cl.get('topics') or []
        topics: list[str] = []
        topics_seen: set[str] = set()
        for t in topics_raw:
            slug = _coerce_to_str(t)
            if slug is None:
                continue
            if input_slugs is not None and slug not in input_slugs:
                continue  # drop hallucinations
            if slug in topics_seen:
                continue  # within-cluster dedupe
            if slug in seen_globally:
                continue  # cross-cluster dedupe (first cluster wins)
            topics_seen.add(slug)
            seen_globally.add(slug)
            topics.append(slug)
        clusters_out.append({
            'slug': str(cl.get('slug') or '').strip(),
            'label': str(cl.get('label') or '').strip(),
            'emoji': str(cl.get('emoji') or '').strip(),
            'description': str(cl.get('description') or '').strip(),
            'topics': topics,
        })

    misc: list[str] = []
    misc_seen: set[str] = set()
    for t in raw.get('misc_topics') or []:
        slug = _coerce_to_str(t)
        if slug is None:
            continue
        if input_slugs is not None and slug not in input_slugs:
            continue
        if slug in seen_globally or slug in misc_seen:
            continue
        misc.append(slug)
        misc_seen.add(slug)

    if input_slugs is not None:
        for slug in sorted(input_slugs - seen_globally - misc_seen):
            misc.append(slug)
            misc_seen.add(slug)

    return clusters_out, misc


def call_llm(rows: list[dict]) -> tuple[dict, dict]:
    """Returns (raw_tool_input, usage)."""
    from exocortex import llm_routing
    llm_routing.initialize()
    from llm_router import call_tool as _router_call_tool

    sys_blocks = build_system_prompt()
    sys_text = ''.join(b.get('text', '') for b in sys_blocks if isinstance(b, dict))
    tool_input, usage = _router_call_tool(
        use_case='second_brain.F8_8_news_cluster',
        system=sys_text,
        user=build_user_prompt(rows),
        schema=CLUSTER_TOOL,
        max_tokens=8192,
        cache_system=True,
    )
    legacy_usage = {
        'input_tokens': usage.input_tokens,
        'output_tokens': usage.output_tokens,
        'cache_creation_input_tokens': usage.cache_creation_input_tokens,
        'cache_read_input_tokens': usage.cache_read_input_tokens,
        '_provider': usage.provider,
        '_model': usage.model,
        '_cost_usd': usage.cost_usd,
        '_latency_ms': usage.latency_ms,
        '_use_case': usage.use_case,
        '_fallback_chain': list(usage.fallback_chain),
    }
    return dict(tool_input), legacy_usage


def estimate_cost_usd(usage: dict) -> float:
    """Router-aware: prefer router-computed `_cost_usd`."""
    if '_cost_usd' in usage and usage['_cost_usd'] is not None:
        return float(usage['_cost_usd'])
    return (
        usage.get('input_tokens', 0) * 1.00
        + usage.get('cache_creation_input_tokens', 0) * 1.25
        + usage.get('cache_read_input_tokens', 0) * 0.10
    ) / 1_000_000 + (usage.get('output_tokens', 0) * 5.00) / 1_000_000


def estimate_cost_pre_call(rows: list[dict]) -> float:
    """Cheap upper-bound estimate so --cost-stop guards a runaway request.

    Rough calc: input ≈ system_prompt (~2.5k tok) + topic list (4 chars/tok,
    avg 25 chars/row including count → ~6 tok/row → 311×6 ≈ 1.9k tok).
    Output worst case: 8192 tok cap. → ~2.5+1.9 = ~4.4k input + 8.2k output."""
    input_tok = 2500 + len(rows) * 7
    output_tok = 8192
    return (input_tok * 1.00 + output_tok * 5.00) / 1_000_000


# ─────────────────────────────────────── YAML output ──

def write_yaml(clusters: list[dict], misc: list[str], rows: list[dict],
               tax_hash: str, llm_cost: float, llm_usage: dict) -> None:
    OUTPUT_YAML.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'clusters': [
            {
                'slug': cl['slug'],
                'label': cl['label'],
                'emoji': cl['emoji'],
                'description': cl['description'],
                'topics': sorted(cl['topics']),
            }
            for cl in clusters
        ],
        'misc_topics': sorted(misc),
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'generated_by': 'scripts/cluster_news_topics.py',
        'prompt_version': PROMPT_VERSION,
        'taxonomy_hash': tax_hash,
        'llm_model': LLM_MODEL,
        'llm_cost_usd': round(llm_cost, 4),
        'llm_usage': llm_usage,
        'input_topic_count': len(rows),
    }
    header = (
        f'# Generated by scripts/cluster_news_topics.py at '
        f"{payload['generated_at']}.\n"
        f'# Reviewed before commit — hand-edit cluster slugs/labels as needed.\n'
        f'# Schema: clusters[].{{slug, label, emoji, description, topics[]}}.\n'
        f'# Topics not in any cluster fall through to wiki/news/by-category/_misc.md.\n'
        f'# Closed slugs (Q1 lock 2026-05-03) — to add a new cluster, edit this file by hand.\n'
        f'# Open membership — periodic --update re-runs LLM to assign new topics to existing clusters.\n'
        f'# Scope (Q3 lock 2026-05-03): news axis only — does NOT touch config/tag_taxonomy.yaml.\n'
        f'\n'
    )
    body = yaml.safe_dump(
        payload, allow_unicode=True, sort_keys=False, default_flow_style=False,
        width=100,
    )
    OUTPUT_YAML.write_text(header + body, encoding='utf-8')
    logger.info('wrote %s (clusters=%d, misc=%d)',
                OUTPUT_YAML, len(clusters), len(misc))


def coverage_report(clusters: list[dict], misc: list[str],
                    rows: list[dict]) -> dict:
    """Compute how many input topics are mapped vs unmapped."""
    input_slugs = {r['slug'] for r in rows}
    cluster_slugs: set[str] = set()
    duplicate_assignments: list[str] = []
    for cl in clusters:
        for t in cl['topics']:
            if t in cluster_slugs:
                duplicate_assignments.append(t)
            cluster_slugs.add(t)

    mapped_in_clusters = cluster_slugs & input_slugs
    mapped_misc = set(misc) & input_slugs
    fully_mapped = mapped_in_clusters | mapped_misc
    unmapped = input_slugs - fully_mapped
    hallucinated = (cluster_slugs | set(misc)) - input_slugs

    pct = round(100.0 * len(mapped_in_clusters) / len(input_slugs), 1) if input_slugs else 0.0
    return {
        'input_topics': len(input_slugs),
        'in_clusters': len(mapped_in_clusters),
        'in_misc': len(mapped_misc),
        'unmapped': len(unmapped),
        'duplicate_assignments': sorted(duplicate_assignments),
        'hallucinated_slugs': sorted(hallucinated),
        'cluster_pct': pct,
        'unmapped_examples': sorted(unmapped)[:15],
    }


# ─────────────────────────────────────── Main flow ──

def run(*, cost_stop: float, dry_run: bool, force: bool, debug: bool) -> dict:
    if not TENANT_ID:
        raise SystemExit('TENANT_ID not set in env')

    rows = fetch_topic_rollup(TENANT_ID)
    logger.info('topic rollup: %d distinct slugs (newsletter_synthesis)', len(rows))
    if not rows:
        raise SystemExit('No newsletter_synthesis topics found — nothing to cluster.')

    tax_hash = taxonomy_hash(rows)
    logger.info('taxonomy_hash=%s', tax_hash)

    input_slugs = {r['slug'] for r in rows}

    cached = None if force else load_cached_run(tax_hash)
    if cached:
        logger.info('cache HIT: reusing run from %s', cached.get('generated_at'))
        clusters, misc = _normalize_clusters(cached['llm_response'], input_slugs)
        llm_cost = float(cached.get('llm_cost_usd') or 0.0)
        llm_usage = cached.get('llm_usage') or {}
    else:
        est = estimate_cost_pre_call(rows)
        logger.info('pre-call cost estimate: $%.4f (cap $%.2f)', est, cost_stop)
        if est > cost_stop:
            raise SystemExit(
                f'pre-call cost estimate ${est:.4f} exceeds cost-stop ${cost_stop:.2f}. '
                f'Raise --cost-stop or shrink input.'
            )

        if dry_run:
            logger.info('[dry-run] would call LLM with %d topics', len(rows))
            return {'dry_run': True, 'topic_count': len(rows), 'taxonomy_hash': tax_hash}

        logger.info('calling LLM (model=%s)…', LLM_MODEL)
        raw, usage = call_llm(rows)
        llm_cost = estimate_cost_usd(usage)
        llm_usage = usage
        logger.info('LLM call done: $%.4f (in=%d, out=%d, cache_w=%d, cache_r=%d)',
                    llm_cost, usage['input_tokens'], usage['output_tokens'],
                    usage['cache_creation_input_tokens'], usage['cache_read_input_tokens'])
        clusters, misc = _normalize_clusters(raw, input_slugs)

        save_cached_run(tax_hash, {
            'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'taxonomy_hash': tax_hash,
            'prompt_version': PROMPT_VERSION,
            'llm_model': LLM_MODEL,
            'llm_response': raw,
            'llm_usage': usage,
            'llm_cost_usd': round(llm_cost, 4),
            'input_topics': [{'slug': r['slug'], 'mentions': r['mentions']} for r in rows],
        })

    if dry_run:
        logger.info('[dry-run] skipping YAML write')
    else:
        write_yaml(clusters, misc, rows, tax_hash, llm_cost, llm_usage)

    coverage = coverage_report(clusters, misc, rows)
    summary = {
        'taxonomy_hash': tax_hash,
        'cluster_count': len(clusters),
        'cluster_slugs': [cl['slug'] for cl in clusters],
        'topic_count': coverage['input_topics'],
        'topics_in_clusters': coverage['in_clusters'],
        'topics_in_misc': coverage['in_misc'],
        'unmapped_topics': coverage['unmapped'],
        'cluster_coverage_pct': coverage['cluster_pct'],
        'duplicate_assignments': coverage['duplicate_assignments'],
        'hallucinated_slugs': coverage['hallucinated_slugs'],
        'unmapped_examples': coverage['unmapped_examples'],
        'llm_cost_usd': round(llm_cost, 4),
        'output_path': str(OUTPUT_YAML) if not dry_run else '<dry-run>',
        'cache_path': str(cache_path(tax_hash)),
    }
    logger.info('summary: %s', json.dumps(summary, ensure_ascii=False))
    return summary


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description='Cluster newsletter topics into 7-9 top-level categories via LLM.')
    parser.add_argument('--cost-stop', type=float, default=5.0,
                        help='cumulative LLM cost cap (USD, default: 5.0)')
    parser.add_argument('--dry-run', action='store_true',
                        help='emit summary without LLM call or YAML write')
    parser.add_argument('--force', action='store_true',
                        help='ignore cached run and re-call LLM')
    parser.add_argument('--update', action='store_true',
                        help='reserved for Phase 2.5: re-cluster only unmapped topics '
                             '(NOT IMPLEMENTED — current behavior is full re-cluster)')
    parser.add_argument('--debug', action='store_true', help='DEBUG logging')
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format='%(asctime)s %(levelname)-7s %(name)s %(message)s',
    )

    if args.update:
        logger.warning('--update flag reserved for Phase 2.5; behaving as full re-cluster')

    summary = run(
        cost_stop=args.cost_stop,
        dry_run=args.dry_run,
        force=args.force,
        debug=args.debug,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    _cli()
