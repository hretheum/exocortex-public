# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/wiki_compiler.py — run as cron daily + pgNotify hooks

"""
L1 → Markdown wiki pages.

Compiles the append-only L1 store into read-only wiki pages (L3).
Every page carries frontmatter with compile_run_id, source_ids, confidence.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from exocortex.db import execute, query_one
from exocortex.wiki.core.edges import (  # noqa: F401
    EdgesIndex,
    _load_active_syntheses,
    _load_edges_index,
)
from exocortex.wiki.core.io import (  # noqa: F401
    _default_wiki_root_str,
    _extract_user_notes,
    _get_wiki_root,
    _hash_input,
    _is_unchanged,
    _parse_yaml_frontmatter,
    _partition_frontmatter,
    _safe,
    _write_with_frontmatter,
    render_frontmatter,
    render_frontmatter_v2,
    write_wiki,
)
from exocortex.wiki.core.user_state import (  # noqa: F401
    _ADD_DATE_RE,
    _DONE_DATE_RE,
    _OPEN_LINE_RE,
    _X_LINE_RE,
    _extract_done_fingerprints,
    _merge_user_done_state,
    _task_fingerprint,
)

# Moved to exocortex.wiki.domains.clippings (F31.6.2)
from exocortex.wiki.domains.clippings import (  # noqa: F401
    _compile_clippings_module,
    _write_clipping_page,
    _write_clippings_moc,
    compile_3d_module,
    compile_cook_module,
    compile_papers_module,
    compile_priv_module,
    compile_sb_module,
    compile_tc_module,
    compile_work_clippings,
)

# Moved to exocortex.wiki.domains.cross_domain (F31.6.2)
from exocortex.wiki.domains.cross_domain import compile_cross_domain

# Moved to exocortex.wiki.domains.live_sections (F31.6.2)
from exocortex.wiki.domains.live_sections import (
    compile_live_sections_dashboard,
)
from exocortex.wiki.util.classification import (  # noqa: F401
    _classify_type,
    _client_display,
    _is_internal,
    _meeting_slug,
    _project_display,
)

# Wiki package imports (F31.6.1 extraction)
from exocortex.wiki.util.coercion import _coerce_jsonb_list  # noqa: F401
from exocortex.wiki.util.dates import (  # noqa: F401
    _date10,
    _iso_week_bounds,
    _offset_iso,
    _strip_pl_accents,
)
from exocortex.wiki.util.slugs import (  # noqa: F401
    _display_from_email,
    _news_slug,
    _re_extract,
    _safe_slug,
    _slug_from_email,
)

SCHEMA_VERSION = "5.0"
VALID_DOMAINS = {'frp', 'work', '3d', 'tc', 'cook', 'priv', 'sb', 'cross', 'papers', 'news', 'home', 'live',
                 'dowody', 'all'}
LLM_MODEL = 'claude-haiku-4-5-20251001'

# F4.3.5 — frontmatter cleanup: system fields are prefixed with `_` so Obsidian
# Properties panel hides them via "Properties to ignore" setting (per-vault).
# User-facing fields stay clean. When a writer adds metadata, route it through
# `_partition_frontmatter()` which puts unknown keys in user space by default
# and known system keys into `_*` prefixed twins.
SYSTEM_FRONTMATTER_KEYS = {
    'source_ids', 'schema_version', 'meeting_id', 'synced_at', 'body_hash',
    'transcript_url', 'input_hash', 'compile_run_id', 'generated_at',
    'synthesis_id', 'synthesis_input_hash', 'synthesis_generated_at',
    'synthesis_prompt_version', 'synthesis_model', 'synthesis_n_meetings',
    'source_id',
}

USER_NOTES_BEGIN = '<!-- USER_NOTES_START -->'
USER_NOTES_END = '<!-- USER_NOTES_END -->'
GENERATED_BEGIN = '<!-- GENERATED_START -->'
GENERATED_END = '<!-- GENERATED_END -->'

# SYNTHESIS_STALE_DAYS, TAG_PAGE_MIN_MEETINGS and LLM_THRESHOLDS live in
# exocortex.wiki.domains.work and are re-imported below (identical values).
# News module constants — moved to exocortex.wiki.domains.news (F31.6.2 batch 3)
# Re-imported here for CLI code (--aggregator-window) that references them.
from exocortex.wiki.domains.news import (  # noqa: F401
    _NEWS_CLUSTER_DEFAULT_EMOJI,
    NEWS_AGGREGATOR_LLM_MODEL,
    NEWS_AGGREGATOR_PROMPT_VERSION,
    NEWS_AGGREGATOR_SPARSE_FALLBACK_DAYS,
    NEWS_AGGREGATOR_SPARSE_THRESHOLD,
    NEWS_AGGREGATOR_WEIGHTS,
    NEWS_AGGREGATOR_WINDOW_DAYS,
    NEWS_AGGREGATOR_WINDOW_DAYS_MAX,
    NEWS_AGGREGATOR_WINDOW_DAYS_MIN,
    NEWS_SOURCE_AUTHORITY,
    NEWS_SOURCE_AUTHORITY_DEFAULT,
    NEWS_TOPIC_MIN_MENTIONS,
    _compile_news_aggregator,
    _compute_news_brief,
    _filter_issues_in_window,
    _format_news_synthesis_sections,
    _load_news_issues,
    _load_topic_clusters,
    _named_cited_count,
    _news_aggregator_window_override,
    _news_authority,
    _news_issue_slug,
    _news_issue_wikilink,
    _news_issue_window_dt,
    _render_news_start_body,
    _score_insights,
    _write_news_issue_page,
    _write_news_moc,
    _write_news_start_page,
    compile_news_module,
)

current_run_id: str | None = None
_pages_written: list[str] = []
_llm_tokens_used: int = 0

# F4.6.6.5 — dry-run mode: when True, _write_with_frontmatter / write_wiki
# compute the diff but skip filesystem writes. Pages that would change are
# still appended to _pages_written so the run summary reports them.
DRY_RUN: bool = False

# F27.3/F27.6 — full-rebuild mode: when True, the domain compiled-view writers
# ignore the `_input_hash` skip (every page rewritten) and prune orphan files
# inside `wiki/work/{domain}/compiled/` that the current run did not produce. Set by the
# `--full-rebuild` CLI flag. Currently scoped to the active domain module.
FULL_REBUILD: bool = False

# Sync module-level state to core/_state so core/io.py reads consistent values
# without importing wiki_compiler (which would create a cycle).
from exocortex.wiki.core import _state as _wc_state


def compile_all(tenant_id: str, domain: str = 'all',
                since: datetime | None = None,
                dry_run: bool = False,
                full_rebuild: bool = False) -> None:
    """Dispatcher: runs per-domain + cross-domain compilation.

    F4.6.6.5/6: `dry_run=True` reports the diff but skips I/O and the
    compile_runs DB row. `since` filters meetings to those with
    created_at >= since (already supported by _load_work_meetings).
    F27.3/F27.6: `full_rebuild=True` forces a from-scratch rebuild of the
    Domain compiled views and prunes orphan files in `wiki/work/{domain}/compiled/`.
    """
    global current_run_id, _llm_tokens_used, DRY_RUN, FULL_REBUILD

    if domain not in VALID_DOMAINS:
        raise ValueError(f"Unknown domain: {domain!r}. Valid: {sorted(VALID_DOMAINS)}")

    # F14 pipeline telemetry
    from exocortex.pipeline_log import log_run_end, log_run_start
    _pl_id = log_run_start('wiki_compiler', domain=domain, dry_run=dry_run, since=str(since) if since else None)
    _pl_counts: dict[str, int] = {}
    _pl_error: str | None = None

    _pages_written.clear()
    _llm_tokens_used = 0
    DRY_RUN = dry_run
    FULL_REBUILD = full_rebuild
    # Sync to _state so core/io.py reads the same values without a cycle.
    _wc_state.DRY_RUN = dry_run
    _wc_state.FULL_REBUILD = full_rebuild
    _wc_state._pages_written = _pages_written

    if dry_run:
        print('[wiki_compiler] DRY RUN — no filesystem changes will be made')
        current_run_id = None
    else:
        started = datetime.now(UTC).isoformat()
        run = query_one(
            'INSERT INTO compile_runs (tenant_id, domain, triggered_by, '
            'schema_version, started_at) VALUES (%s, %s, %s, %s, %s) RETURNING id',
            tenant_id, domain, 'manual', SCHEMA_VERSION, started,
        )
        current_run_id = str(run['id']) if run else None
    _wc_state.current_run_id = current_run_id

    domain_modules = [
        ('frp', compile_frp_module),
        ('work', compile_work_module),
        ('3d', compile_3d_module),
        ('tc', compile_tc_module),
        ('cook', compile_cook_module),
        ('priv', compile_priv_module),
        ('sb', compile_sb_module),
        ('papers', compile_papers_module),
        ('news', compile_news_module),
        ('cross', compile_cross_domain),
        ('home', compile_home_module),
        ('live', compile_live_sections_dashboard),
        # lab result pages (roadmap F2.7); a no-op unless LAB_OUT is set
        ('dowody', compile_dowody_module),
    ]
    failed: list[str] = []
    failure_messages: list[str] = []
    for name, fn in domain_modules:
        if domain not in (name, 'all'):
            continue
        try:
            fn(tenant_id, since)
        except NotImplementedError:
            print(f"[wiki_compiler] WARN: {name} module not implemented — skipped")
            failed.append(name)
            failure_messages.append(f"{name}: not implemented")
        except Exception as exc:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
            print(f"[wiki_compiler] ERROR: {name} module failed: {exc!r}")
            failed.append(name)
            failure_messages.append(f"{name}: {exc!r}")
    if failure_messages:
        _pl_error = "; ".join(failure_messages)[:2000]

    if current_run_id and not dry_run:
        execute(
            'UPDATE compile_runs SET finished_at = %s, pages_written = %s, '
            'failed_domains = %s, llm_tokens_used = %s WHERE id = %s',
            datetime.now(UTC).isoformat(),
            list(_pages_written), failed,
            _llm_tokens_used or None, current_run_id,
        )

    if dry_run:
        print(f'[wiki_compiler] DRY RUN summary: {len(_pages_written)} pages would change')
    _pl_counts['pages_written'] = len(_pages_written)
    _pl_counts['modules'] = len([n for n, _ in domain_modules if domain in (n, 'all')])
    _pl_counts['failed'] = len(failed)
    log_run_end(_pl_id, 'success' if not failed else 'failure', counts=_pl_counts,
                error_message=_pl_error)
    DRY_RUN = False


def compile_dowody_module(tenant_id: str, since: datetime | None = None) -> None:
    from exocortex.lab.pages import compile_module

    compile_module(tenant_id, since)


# Moved to exocortex.wiki.domains.frp (F31.6.2 batch 2)
from exocortex.wiki.domains.frp import (  # noqa: F401
    _FRP_AXIS_LABELS,
    _frp_axis_label,
    _write_frp_moc,
    _write_frp_perspective_pages,
    _write_frp_synthesis_page,
    compile_frp_module,
)

# compile_home_module + home/pipeline helpers — moved to exocortex.wiki.domains.home (F31.6.2)
from exocortex.wiki.domains.home import (  # noqa: F401
    _compute_home_dashboard,
    _write_home_page,
    _write_pipeline_dashboard,
    compile_home_module,
)

# _default_wiki_root_str — moved to exocortex.wiki.core.io (F31.6.1)
# compile_work_module + work helpers — moved to exocortex.wiki.domains.work (F31.6.2 batch 4)
from exocortex.wiki.domains.work import (  # noqa: F401
    _CHECKBOX_LINE_RE,
    _GROUP_BY_CLIENT,
    _INLINE_TAG_RE,
    _ME_OWNER_SLUGS,
    _OWNER_NAME_ALIASES,
    _SELF_EXCLUDE_SLUGS,
    LLM_THRESHOLDS,
    SYNTHESIS_STALE_DAYS,
    TAG_PAGE_MIN_MEETINGS,
    _build_promoted_filter,
    _collect_related_syntheses_for_meetings,
    _ensure_index_stubs,
    _format_synthesis_sections,
    _format_todo_item,
    _humanize_age,
    _is_synthesis_stale,
    _load_promoted_descriptions,
    _load_work_meetings,
    _normalize_action_text_for_filter,
    _obsidian_advanced_uri,
    _parse_meeting,
    _person_email_to_slug,
    _render_client_backlog_section,
    _render_client_body,
    _render_inspirations_section,
    _render_meeting_body,
    _render_monthly_body,
    _render_person_body,
    _render_related_decisions,
    _render_related_problems,
    _render_synthesis_banner,
    _render_tasks_query,
    _resolve_cluster_label,
    _resolve_person_display,
    _scan_meeting_inline_tags,
    _summarize_workdash,
    _synthesis_fm_fields,
    _todo_collect,
    _todo_heading_token,
    _todo_owner_display,
    _todo_owner_regex,
    _vault_root_for_promoted,
    _write_by_tag_pages,
    _write_client_pages,
    _write_meeting_pages,
    _write_moje_todo_static,
    _write_monthly_moc,
    _write_monthly_pages,
    _write_people_moc,
    _write_person_pages,
    _write_projects_moc,
    _write_subproject_pages,
    _write_todo_by_tag_page,
    _write_todo_index,
    _write_todo_pages,
    _write_todo_view_page,
    _write_work_moc,
    compile_work_module,
)

# ── F19 Live Sections Dashboard ───────────────────────────────────────
# compile_live_sections_dashboard — moved to exocortex.wiki.domains.live_sections (F31.6.2)


# _ensure_home_stub, _ensure_index_stubs, _summarize_workdash
# — moved to exocortex.wiki.domains.work (F31.6.2 batch 4)


if __name__ == '__main__':
    import argparse as _argparse

    from exocortex.settings import get_tenant_id as _get_tenant_id

    ap = _argparse.ArgumentParser(prog='exocortex.wiki_compiler')
    ap.add_argument('--tenant', default=_get_tenant_id(),
                    help='Tenant id (default: $EXOCORTEX_TENANT_ID, $TENANT_ID, or "default").')
    ap.add_argument('--domain', default=os.environ.get('COMPILE_DOMAIN', 'all'),
                    choices=sorted(VALID_DOMAINS),
                    help='Domain to compile (default: all).')
    ap.add_argument('--since', default=None,
                    help='YYYY-MM-DD — only LOAD thoughts whose meeting date '
                         '(or created_at fallback) >= since. Aggregate pages '
                         '(clients/people/monthly) will reflect only the '
                         'filtered subset, so use with care for full vault '
                         'compiles. Idiomatic use: small --since (last few days) '
                         'after fresh ingest to limit DB load. For full state '
                         'omit --since.')
    ap.add_argument('--dry-run', action='store_true',
                    help='Compute diff but skip filesystem writes + compile_runs INSERT.')
    ap.add_argument('--full-rebuild', action='store_true',
                    help='Force a from-scratch rebuild of compiled domain views '
                         '(ignores the unchanged-page skip) and prune orphan files '
                         'inside wiki/work/{domain}/compiled/. '
                         'Combine with --dry-run to preview the prune.')
    ap.add_argument(
        '--aggregator-window', type=int, default=None,
        help=(
            'Override the news/start.md aggregator window in days '
            f'(default {NEWS_AGGREGATOR_WINDOW_DAYS}, range '
            f'{NEWS_AGGREGATOR_WINDOW_DAYS_MIN}-{NEWS_AGGREGATOR_WINDOW_DAYS_MAX}). '
            'Sparse-week fallback still applies inside that window.'
        ),
    )
    args = ap.parse_args()

    if not args.tenant:
        print('Error: --tenant or $TENANT_ID required')
        raise SystemExit(2)

    since_dt: datetime | None = None
    if args.since:
        try:
            since_dt = datetime.strptime(args.since, '%Y-%m-%d').replace(tzinfo=UTC)
        except ValueError:
            print(f'Error: --since must be YYYY-MM-DD, got {args.since!r}')
            raise SystemExit(2)

    if args.aggregator_window is not None:
        if not (NEWS_AGGREGATOR_WINDOW_DAYS_MIN <= args.aggregator_window <= NEWS_AGGREGATOR_WINDOW_DAYS_MAX):
            print(
                f'Error: --aggregator-window must be in '
                f'[{NEWS_AGGREGATOR_WINDOW_DAYS_MIN},{NEWS_AGGREGATOR_WINDOW_DAYS_MAX}], '
                f'got {args.aggregator_window!r}'
            )
            raise SystemExit(2)
        _news_aggregator_window_override = args.aggregator_window  # set module global below
        # Module-level rebind so compile_news_module picks it up.
        import sys as _sys
        _sys.modules[__name__]._news_aggregator_window_override = args.aggregator_window  # type: ignore[attr-defined]
        # Also update the news domain module (F31.6.2 — compile_news_module
        # now reads from exocortex.wiki.domains.news._news_aggregator_window_override).
        import exocortex.wiki.domains.news as _news_mod
        _news_mod._news_aggregator_window_override = args.aggregator_window  # type: ignore[attr-defined]


    compile_all(args.tenant, args.domain, since=since_dt, dry_run=args.dry_run,
                full_rebuild=args.full_rebuild)
