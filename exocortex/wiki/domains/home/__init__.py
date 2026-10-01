# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Home domain compiler — cross-domain dashboard (_home.md) + pipeline dashboard.

Extracted from wiki_compiler.py in F31.6.2 batch 5+6.
Entry point: compile_home_module(tenant_id, since).

Contains:
- compile_home_module     — entry point: _home.md cross-domain dashboard
- _compute_home_dashboard — all metrics: thoughts/edges/action_items/FRP/cross-domain
- _write_pipeline_dashboard — wiki/_pipeline-status.md
- _write_home_page        — frontmatter + body render
- All data fetchers and section renderers
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from exocortex.wiki.core.io import (
    _get_wiki_root,
    _hash_input,
    _write_with_frontmatter,
)
from exocortex.wiki.domains.base import _LegacyDomainCompiler
from exocortex.wiki.util.dates import _date10

# ── F10 cross-domain home dashboard ───────────────────────────────────────
#
# `compile_home_module` aggregates per-domain signals into a 1-screen
# briefing at `wiki/_home.md`. Deterministic-only (no LLM): re-uses the
# action-items parser (F2.3), syntheses.open_problems (F4), signals_domain
# edges (F7.4), news brief frontmatter (F8.8.x.A) and per-domain thought
# counts. Idempotent via `_input_hash`. Writes USER_NOTES sentinel for
# manual pinned content.

# Per-domain table fixed order (Q1 lock 2026-05-03: priv visible).
_HOME_DOMAINS: tuple[tuple[str, str, str], ...] = (
    ("work", "Work", "🏢"),
    ("news", "News", "📰"),
    ("frp", "FRP", "🔮"),
    ("papers", "Papers", "📚"),
    ("cook", "Cook", "🍽️"),
    ("3d", "3D", "🖨️"),
    ("priv", "Priv", "🔒"),
)


def compile_home_module(tenant_id: str, since: datetime | None) -> None:
    """F10.1 entry point. Compute dashboard metrics + write wiki/_home.md.

    Idempotent via `_input_hash`. Tier=deterministic, $0 LLM.
    """
    wiki_root = _get_wiki_root()
    dashboard = _compute_home_dashboard(tenant_id)
    written = _write_home_page(wiki_root, dashboard)
    pipeline = dashboard.get("pipeline_status", {})
    failure_count = pipeline.get("recent_failures", 0)
    worker_count = len(pipeline.get("workers", {}))
    print(
        f"[wiki_compiler] home: {'wrote' if written else 'unchanged'} _home.md — "
        f"{dashboard['total_thoughts']} thoughts, "
        f"{dashboard['total_edges']} edges, "
        f"{dashboard['work_action_items']['overdue']} overdue items, "
        f"{dashboard['frp_revisits']['due_today_count']} FRP revisits, "
        f"{len(dashboard['cross_domain_signals'])} cross-domain signals, "
        f"{worker_count} pipeline workers ({failure_count} failures)"
    )
    _write_pipeline_dashboard(wiki_root, tenant_id)


def _compute_home_dashboard(tenant_id: str) -> dict:
    """One-shot fetch of all metrics. Returns dict consumed by writer."""
    return {
        "total_thoughts": _home_count_thoughts(tenant_id),
        "total_edges": _home_count_edges(tenant_id),
        "last_compile_run": _home_fetch_last_compile_run(tenant_id),
        "work_action_items": _home_fetch_action_items_summary(tenant_id),
        "today_context": _home_fetch_today_context(tenant_id),
        "frp_revisits": _home_fetch_frp_revisits_due(tenant_id),
        "frp_reading_queue": _home_fetch_frp_reading_queue(tenant_id, limit=5),
        "news_brief_snippet": _home_fetch_news_brief_top_claims(n=3),
        "cross_domain_signals": _home_fetch_cross_domain_signals(
            tenant_id, days=14, limit=5
        ),
        "per_domain_activity": _home_fetch_per_domain_activity(tenant_id, days=7),
        "open_questions": _home_fetch_open_questions(tenant_id, days=30, limit=5),
        "sanity_warnings": _home_read_last_sanity_check(tenant_id),
        "llm_cost_7d": _home_fetch_llm_cost_7d(tenant_id),
        "pipeline_status": _home_fetch_pipeline_status(tenant_id),
        "provider_health": _home_fetch_provider_health(tenant_id),
        "_resurfacing_md_path": str(_get_wiki_root() / "_live" / "resurfacing.md"),
        "_gap_radar_gaps": _fetch_gap_radar_gaps(tenant_id),
    }


def _fetch_gap_radar_gaps(tenant_id: str) -> list[dict]:
    """F31.5.4: Run gap detectors directly at compile time (top 5, no LLM).

    Pure SQL via `exocortex.workers.gap_queries.run_all_detectors`. Sorted by
    age_days descending (oldest/most neglected first). Exceptions → empty list
    (home page must not crash).
    """
    if not tenant_id:
        return []
    try:
        from exocortex.workers.gap_queries import run_all_detectors

        gaps = run_all_detectors(tenant_id, max_results=5)
        gaps.sort(key=lambda g: g.get("age_days", 0), reverse=True)
        return gaps[:5]
    except Exception:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
        return []


def _home_fetch_frp_reading_queue(tenant_id: str, *, limit: int = 5) -> dict:
    """Top N queued FRP items + total queue count.

    Replaces broken Dataview query (file-level type='frp_queue_item' never
    matches because all items are inline in a single `reading-queue.md`).
    Returns {'total': int, 'items': [{title, lead, url, score_total, frame}, ...]}.

    Title fallback chain: metadata.title (RSS adapter rarely stores it, F8.7) →
    URL last-segment slug humanized (e.g. `the-night-the-calamity-came-back` →
    "The Night The Calamity Came Back") → feed_name → '(untitled)'.

    Lead boilerplate strip: removes "Author: X, Y", "Published in Z",
    "SEASON N EPISODE M with host X" prefixes that dominate RSS excerpts
    without carrying any content.
    """
    import re as _re

    from exocortex.db import query, query_one

    def _humanize_url_slug(url: str) -> str:
        if not url:
            return ""
        parts = url.rstrip("/").split("/")
        slug = parts[-1] if parts else ""
        if not slug or "." in slug or slug.isdigit():
            return ""
        words = slug.replace("_", "-").split("-")
        # Drop date-like segments (2026, 04, etc) — chase real title words
        words = [w for w in words if not w.isdigit()]
        return " ".join(w.capitalize() for w in words if w)[:80]

    def _strip_lead_boilerplate(s: str) -> str:
        # "Author: Jane Author, Staff Writer " — strip up to the nearest
        # quote mark (dialogue start) or end-of-line
        s = _re.sub(r'^Author:\s+[^"""]+?(?=["""]|$)', "", s).lstrip()
        # "SEASON N, EPISODE M with host X Click here to listen to this episode "
        s = _re.sub(
            r"^SEASON\s+\d+,?\s+EPISODE\s+\d+.*?(?:Click here to listen to this episode\s+)?",
            "",
            s,
            flags=_re.IGNORECASE,
        ).lstrip()
        # "This episode features 'X' written by Y. Published in Z and read by W. "
        s = _re.sub(
            r"^This episode features.*?(?:Published[^.]+?\.\s*|read by[^.]+?\.\s*)+",
            "",
            s,
            flags=_re.IGNORECASE | _re.DOTALL,
        ).lstrip()
        # "Published on April 29, 2026 " / "Published in March 2026 issue " —
        # also match when there is no trailing period (e.g. "Published on X 2026 In Y")
        s = _re.sub(
            r"^Published\s+(?:on|in)\s+\w+\s+\d+(?:,\s*\d+)?(?:\s+issue)?\s+",
            "",
            s,
            flags=_re.IGNORECASE,
        ).lstrip()
        return s

    def _clean_lead(s: str, *, max_chars: int = 280) -> str:
        if not s:
            return ""
        t = _re.sub(r"<[^>]+>", "", s)
        t = _re.sub(r"\s+", " ", t).strip()
        t = _strip_lead_boilerplate(t)
        return t[:max_chars] + ("…" if len(t) > max_chars else "")

    try:
        rows = query(
            """
            SELECT cq.score_total,
                   cq.ai_tags->>'frame' AS frame,
                   rs.metadata->>'title' AS metadata_title,
                   rs.metadata->>'feed_name' AS feed_name,
                   rs.metadata->>'excerpt' AS excerpt,
                   cq.scenario_sentence,
                   rs.uri
            FROM content_queue cq
            JOIN raw_sources rs ON cq.source_id = rs.id
            WHERE cq.tenant_id = %s AND cq.status = 'queued'
            ORDER BY cq.score_total DESC NULLS LAST, cq.queued_at DESC
            LIMIT %s
            """,
            tenant_id,
            limit,
        )
        total_row = query_one(
            "SELECT count(*) AS n FROM content_queue WHERE tenant_id = %s AND status = 'queued'",
            tenant_id,
        )

        def _resolve_title(r: dict) -> str:
            return (
                (r.get("metadata_title") or "").strip()
                or _humanize_url_slug(r.get("uri") or "")
                or (r.get("feed_name") or "").strip()
                or "(untitled)"
            )[:80]

        return {
            "total": int(total_row["n"]) if total_row else 0,
            "items": [
                {
                    "title": _resolve_title(r),
                    "lead": _clean_lead(
                        r.get("scenario_sentence") or r.get("excerpt") or ""
                    ),
                    "url": r.get("uri") or "",
                    "score_total": r.get("score_total"),
                    "frame": r.get("frame"),
                }
                for r in rows
            ],
        }
    except Exception as _:  # noqa: BLE001
        return {"total": 0, "items": []}


def _home_count_thoughts(tenant_id: str) -> int:
    from exocortex.db import query_one

    try:
        r = query_one(
            "SELECT count(*) AS n FROM thoughts WHERE tenant_id = %s", tenant_id
        )
        return int(r["n"]) if r else 0
    except Exception as _:  # noqa: BLE001
        return 0


def _home_count_edges(tenant_id: str) -> int:
    from exocortex.db import query_one

    try:
        r = query_one("SELECT count(*) AS n FROM edges WHERE tenant_id = %s", tenant_id)
        return int(r["n"]) if r else 0
    except Exception as _:  # noqa: BLE001
        return 0


def _home_count_recent_meetings(tenant_id: str, days: int = 7) -> int:
    from exocortex.db import query_one

    try:
        r = query_one(
            "SELECT count(*) AS n FROM thoughts "
            "WHERE tenant_id = %s AND thought_type = 'work_meeting_note' "
            "AND created_at >= NOW() - (%s || ' days')::interval",
            tenant_id,
            str(days),
        )
        return int(r["n"]) if r else 0
    except Exception as _:  # noqa: BLE001
        return 0


def _home_fetch_last_compile_run(tenant_id: str) -> dict | None:
    from exocortex.db import query_one

    try:
        return query_one(
            "SELECT id, domain, started_at, finished_at, "
            "       coalesce(array_length(pages_written, 1), 0) AS pages_written_count, "
            "       coalesce(array_length(failed_domains, 1), 0) AS failed_domains_count "
            "FROM compile_runs "
            "WHERE tenant_id = %s AND finished_at IS NOT NULL "
            "ORDER BY finished_at DESC LIMIT 1",
            tenant_id,
        )
    except Exception as _:  # noqa: BLE001
        return None


def _home_fetch_action_items_summary(tenant_id: str) -> dict:
    """Aggregate parsed action items across all work meeting thoughts.

    Returns {open: int, overdue: int, top_overdue: [{...}] (up to 5,
    sorted by due_date ASC, owner=exocortex_user wins ties)}.
    Falls back to {open:0, overdue:0, top_overdue:[]} on parser failure.
    """
    from exocortex.db import query

    try:
        from exocortex.action_items import me_owner_slugs, parse_action_items

        rows = query(
            "SELECT id, metadata FROM thoughts "
            "WHERE tenant_id = %s AND thought_type = 'work_meeting_note'",
            tenant_id,
        )
    except Exception as _:  # noqa: BLE001
        return {"open": 0, "overdue": 0, "top_overdue": [], "parser_failed": True}

    today = datetime.now(UTC).date()
    open_count = 0
    overdue_count = 0
    overdue_records: list[dict] = []
    for r in rows:
        try:
            items = parse_action_items(r["metadata"], source_thought_id=str(r["id"]))
        except Exception as _:  # noqa: BLE001, S112
            continue
        for it in items:
            if it.status != "open":
                continue
            open_count += 1
            if not it.due_date:
                continue
            try:
                d = datetime.strptime(it.due_date, "%Y-%m-%d").date()  # noqa: DTZ007 — naive date parse; an aware one would change behavior
            except ValueError:
                continue
            if d < today:
                overdue_count += 1
                overdue_records.append(
                    {
                        "thought_id": str(r["id"]),
                        "meeting_slug": (r.get("metadata") or {}).get("slug") or "",
                        "meeting_title": (r.get("metadata") or {}).get("title") or "",
                        "owner_slug": it.owner_slug,
                        "owner_name": it.owner_name,
                        "content": it.content,
                        "due_date": it.due_date,
                        "sort_key": (
                            d.toordinal(),
                            0 if it.owner_slug in me_owner_slugs() else 1,
                            it.owner_slug,
                        ),
                    }
                )
    overdue_records.sort(key=lambda x: x["sort_key"])
    return {
        "open": open_count,
        "overdue": overdue_count,
        "top_overdue": overdue_records[:5],
        "parser_failed": False,
    }


def _home_fetch_today_context(tenant_id: str) -> dict:
    """Fetch today's meetings with client/project links and tags.

    Returns {meetings: [{slug, title, clients, projects, tags}, ...]}.
    """
    from exocortex.db import query

    try:
        rows = query(
            """
            SELECT t.id, t.metadata->>'slug' AS slug, t.metadata->>'title' AS title,
                   t.extracted_tags,
                   array_agg(DISTINCT CASE WHEN e.type = 'classified_as_client'
                       THEN ec.canonical_name ELSE NULL END)
                       FILTER (WHERE e.type = 'classified_as_client') AS clients,
                   array_agg(DISTINCT CASE WHEN e.type = 'classified_as_project'
                       THEN ep.canonical_name ELSE NULL END)
                       FILTER (WHERE e.type = 'classified_as_project') AS projects
            FROM thoughts t
            LEFT JOIN edges e ON e.src_id = t.id
                AND e.type IN ('classified_as_client', 'classified_as_project')
            LEFT JOIN entities ec ON ec.id = e.dst_id AND e.type = 'classified_as_client'
            LEFT JOIN entities ep ON ep.id = e.dst_id AND e.type = 'classified_as_project'
            WHERE t.tenant_id = %s
              AND t.thought_type = 'work_meeting_note'
              AND t.created_at::date = CURRENT_DATE
            GROUP BY t.id, t.metadata
            ORDER BY t.created_at
            """,
            tenant_id,
        )
    except Exception as _:  # noqa: BLE001
        return {"meetings": []}

    meetings = []
    for r in rows:
        et = r.get("extracted_tags") or {}
        tags = []
        for axis in ("topic", "activity", "status"):
            for item in et.get(axis) or []:
                if isinstance(item, dict):
                    val = item.get("value")
                    if val:
                        tags.append(val)
                elif isinstance(item, str):
                    tags.append(item)

        clients = [c for c in (r.get("clients") or []) if c]
        projects = [p for p in (r.get("projects") or []) if p]

        meetings.append(
            {
                "slug": r.get("slug") or "",
                "title": r.get("title") or "",
                "clients": clients,
                "projects": projects,
                "tags": tags[:10],
            }
        )

    return {"meetings": meetings}


def _home_fetch_frp_revisits_due(tenant_id: str) -> dict:
    from exocortex.db import query

    try:
        rows = query(
            "SELECT fs.id, fs.frame, fs.revisit_due, fs.created_at, "
            "       cq.scenario_sentence AS scenario, "
            "       rs.title AS source_title, rs.uri AS source_uri "
            "FROM frp_sessions fs "
            "LEFT JOIN content_queue cq ON cq.id = fs.content_id "
            "LEFT JOIN raw_sources rs ON rs.id = cq.source_id "
            "WHERE fs.tenant_id = %s "
            "  AND fs.status = 'active' "
            "  AND fs.revisit_due IS NOT NULL "
            "  AND fs.revisit_due <= CURRENT_DATE "
            "ORDER BY fs.revisit_due ASC LIMIT 10",
            tenant_id,
        )
    except Exception as _:  # noqa: BLE001
        return {"due_today_count": 0, "top_due": []}
    return {
        "due_today_count": len(rows),
        "top_due": [
            {
                "session_id": str(r["id"]),
                "frame": r.get("frame") or "?",
                "revisit_due": _date10(r.get("revisit_due")),
                "created_at": _date10(r.get("created_at")),
                "scenario": (r.get("scenario") or "")[:80],
                "source_title": (r.get("source_title") or "")[:80],
            }
            for r in rows[:5]
        ],
    }


def _home_fetch_news_brief_top_claims(n: int = 3) -> list[dict]:
    """Parse `wiki/news/start.md` body — extract top N category insights
    rendered as `## {label} — N issues, M insights this week` followed by
    `- **{bold claim}** — *cited: ...*. From [[issue-slug|...]].`

    Returns top N by frontmatter `top_categories` order, each with the
    first bold claim from its body section. Falls back to empty list when
    start.md absent or unparseable. Frontmatter is still consulted for
    window totals + insight counts (rendered in pulse intro).
    """
    try:
        wiki_root = _get_wiki_root()
        path = wiki_root / "news" / "start.md"
        if not path.exists():
            return []
        txt = path.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n", txt, re.DOTALL)
        if not m:
            return []
        fm = yaml.safe_load(m.group(1)) or {}
        body = txt[m.end() :]
        cats = fm.get("top_categories") or []
        if not isinstance(cats, list) or not cats:
            return []

        window_total = int(fm.get("total_issues_window") or 0)
        insight_count = int(fm.get("insight_count") or 0)
        last_refresh = str(fm.get("last_refresh") or "")

        # Slice body into ## sections (skip stuff between # title and first ##).
        # Pattern keeps headings + content per section; leading content before
        # any ## is dropped.
        sections: list[tuple[str, str]] = []  # (heading_line, content)
        current_heading: str | None = None
        current_buf: list[str] = []
        for line in body.splitlines():
            if line.startswith("## "):
                if current_heading is not None:
                    sections.append((current_heading, "\n".join(current_buf)))
                current_heading = line[3:].strip()
                current_buf = []
            elif current_heading is not None:
                current_buf.append(line)
        if current_heading is not None:
            sections.append((current_heading, "\n".join(current_buf)))

        # Match ## heading to top_categories. Heading format from
        # `_render_news_start_body`: `{emoji} {label} — N issues, M insights this week`.
        # We can't reliably map slug → label without re-loading clusters, so
        # we walk in `top_categories` order and pick sections in body order
        # 1-1 (clusters are also rendered top-down by score in `top_categories`
        # ordering — see `_render_news_start_body` line 2333+).
        bold_pattern = re.compile(r"^\s*-\s+\*\*(.+?)\*\*", re.MULTILINE)
        out: list[dict] = []
        # Build a heading-by-rank lookup: filter to sections whose heading
        # contains an em dash (those are the category sections; non-category
        # sections like "🔥 High-confidence claims" / "🆕 Newly cited sources"
        # / "📅 Latest issues" / "📊 Issues per category" lack the dash).
        category_sections = [(h, c) for h, c in sections if " — " in h]
        # Strip leading emoji ranges + variation selectors (U+FE0E/F) + ZWJ (U+200D).
        emoji_re = re.compile(
            "^[\U0001f300-\U0001faff\U00002600-\U000027bf\U00002460-\U000024ff‍︎️\\s]+"
        )
        for idx, slug in enumerate(cats[:n]):
            slug_str = str(slug)
            if idx >= len(category_sections):
                break
            heading, content = category_sections[idx]
            label_only = heading.split(" — ", 1)[0].strip()
            label_only = emoji_re.sub("", label_only).strip() or slug_str
            all_claims = bold_pattern.findall(content)
            claims = [c.strip() for c in all_claims if c.strip()]
            for ci, claim in enumerate(claims):
                if claim and len(claim) > 600:
                    claim = claim[:597].rstrip() + "..."
                out.append(
                    {
                        "category": slug_str,
                        "category_label": label_only,
                        "claim": claim,
                        "window_total": window_total,
                        "insight_count": insight_count,
                        "last_refresh": last_refresh,
                        "claim_id": _hash_input(
                            [slug_str, str(ci), claim, fm.get("_input_hash", "")]
                        ),
                    }
                )
        return out
    except Exception as _:  # noqa: BLE001
        return []


def _home_fetch_cross_domain_signals(
    tenant_id: str, days: int, limit: int
) -> list[dict]:
    """`signals_domain` edges (F7.4) — FRP reflections that signal entities from
    other domains. Resolves entity canonical_name + thought slug for rendering.
    """
    from exocortex.db import query

    try:
        rows = query(
            "SELECT e.id AS edge_id, e.src_id, e.dst_id, e.created_at AS edge_created, "
            "       t.metadata AS t_metadata, t.thought_type, "
            "       ent.canonical_name, ent.type AS entity_type "
            "FROM edges e "
            "LEFT JOIN thoughts t ON t.id = e.src_id "
            "LEFT JOIN entities ent ON ent.id = e.dst_id "
            "WHERE e.tenant_id = %s "
            "  AND e.type = 'signals_domain' "
            "  AND e.created_at >= NOW() - (%s || ' days')::interval "
            "ORDER BY e.created_at DESC LIMIT %s",
            tenant_id,
            str(days),
            limit,
        )
    except Exception as _:  # noqa: BLE001
        return []
    out: list[dict] = []
    for r in rows:
        meta = r.get("t_metadata") or {}
        out.append(
            {
                "edge_id": str(r["edge_id"]),
                "src_thought_id": str(r.get("src_id") or ""),
                "thought_slug": meta.get("slug") or "",
                "thought_title": (meta.get("title") or "")[:80],
                "thought_type": r.get("thought_type") or "",
                "entity_name": r.get("canonical_name") or "?",
                "entity_type": r.get("entity_type") or "",
                "edge_created": _date10(r.get("edge_created")),
            }
        )
    return out


def _home_fetch_per_domain_activity(tenant_id: str, days: int = 7) -> dict[str, dict]:
    """Counts per domain (live total + recent delta). Fixed 7-domain set
    so empty domains still appear in table per design § 9.

    Uses metadata.domain for thoughts that carry it explicitly + thought_type
    fallback (e.g. work_meeting_note → work). Domain attribution is best-effort
    — if neither field maps, the thought doesn't count toward any domain.
    """
    from exocortex.db import query

    out: dict[str, dict] = {d: {"count": 0, "delta": 0} for d, _, _ in _HOME_DOMAINS}
    try:
        # Live counts via metadata.domain
        for r in query(
            "SELECT metadata->>'domain' AS d, count(*) AS n "
            "FROM thoughts WHERE tenant_id = %s "
            "GROUP BY metadata->>'domain'",
            tenant_id,
        ):
            d = r.get("d")
            if d in out:
                out[d]["count"] = int(r["n"])
        # Recent deltas
        for r in query(
            "SELECT metadata->>'domain' AS d, count(*) AS n "
            "FROM thoughts WHERE tenant_id = %s "
            "  AND created_at >= NOW() - (%s || ' days')::interval "
            "GROUP BY metadata->>'domain'",
            tenant_id,
            str(days),
        ):
            d = r.get("d")
            if d in out:
                out[d]["delta"] = int(r["n"])
    except Exception as _:  # noqa: BLE001
        return out
    return out


def _home_fetch_open_questions(tenant_id: str, days: int, limit: int) -> list[dict]:
    """Top open_problems from active syntheses (perspective_type=client/project).

    Sorts by (synthesis recency, problem-array-index ASC) — earlier problems
    in the array are more important per the F4 prompt. Renders one top problem
    per synthesis so that no single perspective dominates.
    """
    from exocortex.db import query

    try:
        rows = query(
            "SELECT id, perspective_type, perspective_key, content, generated_at "
            "FROM syntheses "
            "WHERE tenant_id = %s AND superseded_by IS NULL "
            "  AND perspective_type IN ('client', 'project') "
            "  AND generated_at >= NOW() - (%s || ' days')::interval "
            "ORDER BY generated_at DESC LIMIT 50",
            tenant_id,
            str(days),
        )
    except Exception as _:  # noqa: BLE001
        return []
    out: list[dict] = []
    seen_keys: set[str] = set()
    for r in rows:
        if r["perspective_key"] in seen_keys:
            continue
        content = r.get("content") or {}
        problems = content.get("open_problems") or []
        if not isinstance(problems, list) or not problems:
            continue
        first = problems[0]
        if isinstance(first, dict):
            text = (
                first.get("problem")
                or first.get("text")
                or first.get("description")
                or ""
            )
        else:
            text = str(first)
        text = (text or "").strip()
        if not text:
            continue
        out.append(
            {
                "synthesis_id": str(r["id"]),
                "perspective_type": r["perspective_type"],
                "perspective_key": r["perspective_key"],
                "problem": text[:200],
            }
        )
        seen_keys.add(r["perspective_key"])
        if len(out) >= limit:
            break
    return out


def _home_read_last_sanity_check(tenant_id: str) -> dict:
    """Run sanity probes inline — DB queries identical to scripts/sanity_check.py
    but without subprocess overhead.

    Returns counts dict; renderer formats warnings inline.
    """
    from exocortex.db import query_one

    out = {
        "orphan_edges": 0,
        "missing_embeddings": 0,
        "missing_titles": 0,
        "comma_participants": 0,
        "comma_syntheses": 0,
        "comma_entities": 0,
        "stale_syntheses": 0,
        "fetched": True,
    }
    try:
        r = query_one(
            "SELECT count(*) AS n FROM edges e "
            "WHERE e.tenant_id = %s "
            "  AND ( "
            "    (e.src_type = 'entity' AND NOT EXISTS (SELECT 1 FROM entities WHERE id = e.src_id)) "
            "    OR (e.dst_type = 'entity' AND NOT EXISTS (SELECT 1 FROM entities WHERE id = e.dst_id)) "
            "    OR (e.src_type = 'thought' AND NOT EXISTS (SELECT 1 FROM thoughts WHERE id = e.src_id)) "
            "    OR (e.dst_type = 'thought' AND NOT EXISTS (SELECT 1 FROM thoughts WHERE id = e.dst_id)) "
            "  )",
            tenant_id,
        )
        out["orphan_edges"] = int(r["n"]) if r else 0
        r = query_one(
            "SELECT count(*) AS n FROM thoughts WHERE tenant_id = %s AND embedding IS NULL "
            # vault_note documents are NULL by design since the thought_chunks
            # migration — their search embeddings live on thought_chunks, not
            # here (docs/migracje/thought-chunks.md). Excluded so this stays
            # a real data-quality signal instead of a permanent false alarm.
            "AND thought_type != 'vault_note'",
            tenant_id,
        )
        out["missing_embeddings"] = int(r["n"]) if r else 0
        r = query_one(
            "SELECT count(*) AS n FROM thoughts WHERE tenant_id = %s "
            "AND (metadata->>'title' IS NULL OR metadata->>'title' = '')",
            tenant_id,
        )
        out["missing_titles"] = int(r["n"]) if r else 0
        r = query_one(
            "SELECT count(*) AS n FROM syntheses "
            "WHERE tenant_id = %s AND superseded_by IS NULL "
            "  AND generated_at < NOW() - INTERVAL '30 days'",
            tenant_id,
        )
        out["stale_syntheses"] = int(r["n"]) if r else 0
    except Exception as _:  # noqa: BLE001
        out["fetched"] = False
    return out


def _home_fetch_llm_cost_7d(tenant_id: str) -> dict:
    """Last-7d LLM cost roll-up from synthesis_runs."""
    from exocortex.db import query_one

    try:
        r = query_one(
            "SELECT coalesce(sum(total_cost_usd), 0)::numeric(10,4) AS total, "
            "       count(*) AS run_count "
            "FROM synthesis_runs "
            "WHERE tenant_id = %s AND started_at >= NOW() - INTERVAL '7 days'",
            tenant_id,
        )
        return {
            "total_usd": float(r["total"]) if r else 0.0,
            "run_count": int(r["run_count"]) if r else 0,
        }
    except Exception as _:  # noqa: BLE001
        return {"total_usd": 0.0, "run_count": 0}


def _home_fetch_provider_health(tenant_id: str) -> dict:
    """R4 — provider health: error rate, latency, cost per provider (24h)."""
    from exocortex.db import query, query_one

    try:
        rows_24h = query(
            "SELECT provider, model, count(*) AS calls, "
            "  avg(latency_ms)::int AS avg_lat, sum(cost_usd)::numeric(10,4) AS cost "
            "  FROM llm_provider_runs "
            " WHERE tenant_id = %s AND started_at >= NOW() - INTERVAL '24 hours' "
            " GROUP BY provider, model",
            tenant_id,
        )
        err_24h = query(
            "SELECT provider, count(*) AS errors "
            "  FROM provider_errors "
            " WHERE tenant_id = %s AND started_at >= NOW() - INTERVAL '24 hours' "
            " GROUP BY provider",
            tenant_id,
        )
    except Exception as _:  # noqa: BLE001
        return {"providers": [], "fetched": False}

    err_map = {r["provider"]: int(r["errors"]) for r in err_24h}
    providers = []
    for r in rows_24h:
        p = r["provider"]
        errors = err_map.get(p, 0)
        total = int(r["calls"]) + errors
        providers.append(
            {
                "provider": p,
                "model": r["model"] or "?",
                "calls_24h": int(r["calls"]),
                "errors_24h": errors,
                "error_rate_24h": round(errors / total * 100, 1) if total > 0 else 0,
                "errors_1h": 0,
                "error_rate_1h": 0,
                "avg_latency_ms": int(r["avg_lat"]) if r["avg_lat"] else 0,
                "total_cost_usd": float(r["cost"]) if r["cost"] else 0,
            }
        )

    # Circuit detection (R4.7)
    try:
        circ_rows = query(
            "SELECT pe.provider, count(*) AS errors "
            "FROM provider_errors pe "
            "WHERE pe.tenant_id = %s AND pe.started_at >= NOW() - INTERVAL '1 hour' "
            "GROUP BY pe.provider HAVING count(*) >= 3",
            tenant_id,
        )
        for cr in circ_rows:
            p = cr["provider"]
            last_ok = query_one(
                "SELECT 1 FROM llm_provider_runs "
                "WHERE tenant_id = %s AND provider = %s "
                "  AND started_at > (SELECT max(started_at) FROM provider_errors "
                "    WHERE tenant_id = %s AND provider = %s AND started_at >= NOW() - INTERVAL '1 hour')",
                tenant_id,
                p,
                tenant_id,
                p,
            )
            if not last_ok:
                for pv in providers:
                    if pv["provider"] == p:
                        pv["circuit_open"] = True
    except Exception as _:  # noqa: BLE001, S110
        pass

    return {"providers": providers, "fetched": True}


def _home_fetch_pipeline_status(tenant_id: str) -> dict:
    """F14 — recent pipeline run status for _home.md dashboard."""
    from exocortex.db import query, query_one

    try:
        workers = query(
            "SELECT DISTINCT worker FROM pipeline_runs WHERE tenant_id = %s "
            "AND started_at >= NOW() - INTERVAL '48 hours'",
            tenant_id,
        )
        worker_list = sorted(r["worker"] for r in workers)

        last_runs = query(
            "SELECT worker, status, started_at, finished_at, runtime_seconds, "
            "       counts, error_message "
            "FROM pipeline_runs "
            "WHERE tenant_id = %s "
            "AND started_at >= NOW() - INTERVAL '48 hours' "
            "ORDER BY started_at DESC",
            tenant_id,
        )

        failures_24h = query_one(
            "SELECT COUNT(*) AS n FROM pipeline_runs "
            "WHERE tenant_id = %s AND status = 'failure' "
            "AND started_at >= NOW() - INTERVAL '24 hours'",
            tenant_id,
        )

        per_worker: dict[str, dict] = {}
        for w in worker_list:
            wruns = [r for r in last_runs if r["worker"] == w]
            if wruns:
                latest = wruns[0]
                success_count = sum(1 for r in wruns if r["status"] == "success")
                fail_count = sum(1 for r in wruns if r["status"] == "failure")
                per_worker[w] = {
                    "last_status": latest["status"],
                    "last_run": latest["started_at"],
                    "last_runtime": latest.get("runtime_seconds"),
                    "last_error": latest.get("error_message"),
                    "counts": latest.get("counts"),
                    "runs_48h": len(wruns),
                    "success_48h": success_count,
                    "failures_48h": fail_count,
                }
        return {
            "workers": per_worker,
            "worker_count": len(worker_list),
            "recent_failures": int(failures_24h["n"]) if failures_24h else 0,
        }
    except Exception as _:  # noqa: BLE001
        return {"workers": {}, "worker_count": 0, "recent_failures": 0}


# Worker timer definitions: expected frequency used for staleness detection.
_PIPELINE_TIMERS = {
    "wiki_compiler": {"label": "Wiki Compile", "expect_every_h": 24, "emoji": "📄"},
    "synthesizer": {"label": "Synthesizer", "expect_every_h": 24, "emoji": "🧠"},
    "gmail": {"label": "Gmail (newsletter)", "expect_every_h": 6, "emoji": "📧"},
    "rss": {"label": "RSS (FRP stories)", "expect_every_h": 1, "emoji": "📡"},
}


def _write_pipeline_dashboard(wiki_root: Path, tenant_id: str) -> None:
    """F14+ — daily observability dashboard at wiki/_pipeline.md."""
    import exocortex.wiki_compiler as _wc
    from exocortex.db import query as _db_query

    now = datetime.now(UTC)

    # Last 48h of pipeline runs
    runs = _db_query(
        "SELECT worker, status, started_at, finished_at, runtime_seconds, "
        "counts, error_message, cost_usd "
        "FROM pipeline_runs WHERE tenant_id = %s "
        "AND started_at >= NOW() - INTERVAL '48 hours' "
        "ORDER BY started_at DESC",
        tenant_id,
    )

    # Per-worker: latest run, expected vs actual gaps
    workers: dict[str, dict] = {}
    for r in runs:
        w = r["worker"]
        if w not in workers:
            workers[w] = {
                "last_run": r["started_at"],
                "last_status": r["status"],
                "last_error": r.get("error_message"),
                "last_runtime": r.get("runtime_seconds"),
                "last_counts": r.get("counts"),
                "runs_48h": 0,
                "success_48h": 0,
                "failures_48h": 0,
                "total_cost": 0.0,
            }
        workers[w]["runs_48h"] += 1
        if r["status"] == "success":
            workers[w]["success_48h"] += 1
        else:
            workers[w]["failures_48h"] += 1
        if r.get("cost_usd"):
            workers[w]["total_cost"] += float(r["cost_usd"])

    # Staleness check: when should a worker have last run?
    for wk, wd in workers.items():
        timer = _PIPELINE_TIMERS.get(wk, {})
        expect_h = timer.get("expect_every_h")
        if expect_h and wd.get("last_run"):
            age_h = (now - wd["last_run"]).total_seconds() / 3600
            wd["age_h"] = age_h
            wd["max_ok_h"] = expect_h * 1.5  # 50% grace period
            wd["stale"] = age_h > wd["max_ok_h"]
        else:
            wd["stale"] = False
            wd["age_h"] = None

    # Missing workers: timers that haven't run at all
    known = set(workers.keys())
    expected = set(_PIPELINE_TIMERS.keys())
    missing = expected - known

    # Build markdown
    lines = [
        "# ⚙️ Pipeline Status",
        "",
        f"> **Generated:** {now.strftime('%Y-%m-%d %H:%M UTC')}",
        f"> **Pipeline runs (48h):** {len(runs)} total across {len(workers)} workers",
        "",
    ]

    # ── Timer table ──
    lines += [
        "## ⏱️ Timers",
        "",
        "| Worker | Last run | Status | 48h runs | OK/Fail | Age |",
        "|--------|----------|--------|----------|---------|-----|",
    ]
    for wk in sorted(set(list(workers.keys()) + list(missing))):
        t = _PIPELINE_TIMERS.get(
            wk, {"label": wk, "emoji": "❓", "expect_every_h": None}
        )
        w = workers.get(wk)
        if w is None:
            lines.append(
                f"| {t['emoji']} {t['label']} | — | 🔴 **no data** | 0 | — | — |"
            )
        else:
            last = (
                w["last_run"].strftime("%m-%d %H:%M")
                if hasattr(w["last_run"], "strftime")
                else str(w["last_run"])[:11]
            )
            status = "✅" if w["last_status"] == "success" else "❌"
            if w.get("stale"):
                age_str = f"🔴 {w['age_h']:.0f}h (max {w['max_ok_h']:.0f}h)"
            elif w.get("age_h") and w["age_h"] < 1:
                age_str = f"🟢 {w['age_h'] * 60:.0f}min"
            else:
                age_str = f"🟢 {w['age_h']:.0f}h" if w.get("age_h") else "—"
            lines.append(
                f"| {t['emoji']} {t['label']} | {last} | {status} | "
                f"{w['runs_48h']} | {w['success_48h']}/{w['failures_48h']} | {age_str} |"
            )
    lines.append("")

    # ── This morning (compile + synth) ──
    lines += ["## 🌅 Dziś rano", ""]
    compile_runs = [r for r in runs if r["worker"] == "wiki_compiler"]
    synth_runs = [r for r in runs if r["worker"] == "synthesizer"]
    if compile_runs:
        cr = compile_runs[0]
        counts = cr.get("counts") or {}
        rt = cr.get("runtime_seconds") or 0
        ts = (
            cr["started_at"].strftime("%H:%M")
            if hasattr(cr["started_at"], "strftime")
            else ""
        )
        lines.append(
            f"- 📄 **Wiki compile**: {cr['status']} · {ts} · runtime {rt:.0f}s"
        )
        if counts:
            lines.append(f"  - {counts}")
    if synth_runs:
        sr = synth_runs[0]
        cost = sr.get("cost_usd") or 0
        lines.append(f"- 🧠 **Synthesizer**: {sr['status']} · cost ${cost:.4f}")
    if not compile_runs and not synth_runs:
        lines.append(
            "_Brak danych z dzisiejszego poranka — compile jeszcze nie przebiegł._"
        )
    lines.append("")

    # ── Recent errors ──
    failures = [r for r in runs if r["status"] == "failure"]
    if failures:
        lines += ["## 🚨 Ostatnie błędy", ""]
        for f in failures[:5]:
            ts = (
                f["started_at"].strftime("%m-%d %H:%M")
                if hasattr(f["started_at"], "strftime")
                else ""
            )
            lines.append(
                f"- ❌ **{f['worker']}** {ts}: `{(f.get('error_message') or '?')[:200]}`"
            )
        lines.append("")

    # ── R4 — LLM Provider Health ──
    ph_data = _home_fetch_provider_health(tenant_id)
    if ph_data.get("providers"):
        lines += [
            "## 🤖 LLM Providers (24h)",
            "",
            "| Provider | Model | Calls | Errors | Error% | p50 | Cost |",
            "|----------|-------|-------|--------|--------|-----|------|",
        ]
        for pv in ph_data["providers"]:
            er = pv["error_rate_24h"]
            flag = "🔴" if er > 30 else "🟡" if er > 10 else "🟢"
            lines.append(
                f"| {pv['provider']} | {pv['model']} | {pv['calls_24h']} | "
                f"{pv['errors_24h']} | {flag} {er}% | "
                f"{pv['avg_latency_ms']}ms | ${pv['total_cost_usd']:.4f} |"
            )
        lines.append("")
        for pv in ph_data["providers"]:
            if pv.get("circuit_open"):
                lines.append(
                    f"> ⚠️ **{pv['provider']}** circuit OPEN — "
                    f"auto-recovery in progress. Router will probe next call."
                )
                lines.append("")
        # Cache hit rate
        from exocortex.db import query

        try:
            cache_rows = query(
                "SELECT sum(cache_creation_input_tokens) AS write_tok, "
                "  sum(cache_read_input_tokens) AS read_tok, sum(input_tokens) AS total_input "
                "FROM llm_provider_runs "
                "WHERE tenant_id = %s AND started_at >= NOW() - INTERVAL '24 hours' "
                "  AND provider = 'anthropic'",
                tenant_id,
            )
            for cr in cache_rows:
                read_t = int(cr["read_tok"] or 0)
                total_t = int(cr["total_input"] or 0)
                if total_t > 0:
                    hit_pct = round(read_t / total_t * 100, 1)
                    save_est = round((read_t * 0.90) / 1_000_000, 4)
                    lines.append(
                        f"> 💾 **Prompt cache (Anthropic, 24h)**: "
                        f"{read_t} cache read tokens, {hit_pct}% hit rate, "
                        f"~${save_est} saved"
                    )
                    lines.append("")
        except Exception as _:  # noqa: BLE001, S110
            pass

    # ── LLM cost ──
    total_cost = sum(wd.get("total_cost", 0) for wd in workers.values())
    if total_cost > 0:
        lines += [
            "## 💰 LLM cost (48h)",
            "",
            f"- **Total**: ${total_cost:.4f}",
            "- **Per worker**:",
        ]
        for wk in sorted(workers.keys()):
            wc = workers[wk].get("total_cost", 0)
            if wc > 0:
                t = _PIPELINE_TIMERS.get(wk, {"emoji": "❓"})
                lines.append(f"  - {t['emoji']} {wk}: ${wc:.4f}")
        lines.append("")

    body = "\n".join(lines)
    path = wiki_root / "_pipeline.md"
    fm = {
        "type": "pipeline-dashboard",
        "last_refresh": now.isoformat(),
        "total_workers": len(workers),
        "missing_workers": len(missing),
        "failure_count": len(failures),
    }
    fm["input_hash"] = _hash_input({"_body": body, "_fm_keys": sorted(fm.keys())})
    if _write_with_frontmatter(str(path), fm, body, []):
        _wc._pages_written.append(str(path))


# _date10 — moved to exocortex.wiki.util.dates (F31.6.1)


def _write_home_page(wiki_root: Path, dashboard: dict) -> bool:
    """Render markdown + atomic write via _write_with_frontmatter."""
    import exocortex.wiki_compiler as _wc

    # NOTE: `last_compile_run` is intentionally excluded from the hash payload —
    # every `compile_home_module` run inserts its own compile_runs row, which
    # would self-invalidate the hash on every cron tick. The compile-run
    # banner is rendered inline from `dashboard['last_compile_run']` and
    # only mutates the file when content-bearing fields below change.
    payload = json.dumps(
        [
            _wc.SCHEMA_VERSION,
            # F10.5 render-format bump — invalidates _home.md once when format changes,
            # without affecting other pages. v3 = pinned-callout reworded; v4 =
            # Today section uses a Tasks plugin live query (respects user-toggled [x]
            # in real time) + Reading queue as a static table from DB content_queue; v5 = Today
            # filter "heading includes vault owner" (per-owner scope), Reading queue table
            # 4-col with lead column, section ordering configurable via
            # `config/home_sections.yaml`.
            "home-format-v7.1-author-strip-tightened-quote-boundary",
            # Section order from yaml — invalidates _home.md when the user reorders.
            "|".join(_load_home_section_order()),
            # Today's client/project/tag context from today's meetings.
            sorted(
                [
                    (
                        m.get("slug") or "",
                        sorted(m.get("clients") or []),
                        sorted(m.get("projects") or []),
                        sorted(m.get("tags") or []),
                    )
                    for m in (
                        (dashboard.get("today_context") or {}).get("meetings") or []
                    )
                ]
            )
            if dashboard.get("today_context")
            else [],
            dashboard["work_action_items"]["open"],
            dashboard["work_action_items"]["overdue"],
            sorted(
                [a["thought_id"] for a in dashboard["work_action_items"]["top_overdue"]]
            ),
            dashboard["frp_revisits"]["due_today_count"],
            sorted([s["session_id"] for s in dashboard["frp_revisits"]["top_due"]]),
            sorted([c["claim_id"] for c in dashboard["news_brief_snippet"]]),
            len(dashboard["cross_domain_signals"]),
            sorted([s["edge_id"] for s in dashboard["cross_domain_signals"]]),
            sorted([q["synthesis_id"] for q in dashboard["open_questions"]]),
            {d: a["count"] for d, a in dashboard["per_domain_activity"].items()},
            {d: a["delta"] for d, a in dashboard["per_domain_activity"].items()},
            sorted(
                [
                    (
                        g.get("type", ""),
                        g.get("title", ""),
                        int(g.get("age_days", 0)),
                    )
                    for g in (dashboard.get("_gap_radar_gaps") or [])
                ]
            ),
            hashlib.sha256(
                json.dumps(
                    dashboard["sanity_warnings"], sort_keys=True, default=str
                ).encode()
            ).hexdigest()[:8],
        ],
        sort_keys=True,
        default=str,
        ensure_ascii=False,
    ).encode("utf-8")
    input_hash = hashlib.sha256(payload).hexdigest()[:16]

    fm: dict[str, Any] = {
        "type": "home",
        "title": "🧭 Wiki — Home",
        "live": None,  # F16 — placeholder for live section config
        "last_refresh": datetime.now(UTC).isoformat(),
        "total_active_thoughts": dashboard["total_thoughts"],
        "total_edges": dashboard["total_edges"],
        "total_domains_active": sum(
            1 for a in dashboard["per_domain_activity"].values() if a["count"] > 0
        ),
        "recent_activity_window_days": 7,
        "work_open_action_items": dashboard["work_action_items"]["open"],
        "work_overdue_action_items": dashboard["work_action_items"]["overdue"],
        "frp_revisits_due_today": dashboard["frp_revisits"]["due_today_count"],
        "news_issues_in_window": (
            dashboard["news_brief_snippet"][0].get("window_total", 0)
            if dashboard["news_brief_snippet"]
            else 0
        ),
        "news_insight_count": (
            dashboard["news_brief_snippet"][0].get("insight_count", 0)
            if dashboard["news_brief_snippet"]
            else 0
        ),
        "cross_domain_signal_count": len(dashboard["cross_domain_signals"]),
        "home_llm_cost_usd": 0.0,
        "home_llm_calls": 0,
        "operational_warnings": (
            dashboard["sanity_warnings"].get("orphan_edges", 0)
            + dashboard["sanity_warnings"].get("missing_embeddings", 0)
            + dashboard["sanity_warnings"].get("missing_titles", 0)
            + dashboard["sanity_warnings"].get("stale_syntheses", 0)
        ),
        "_input_hash": input_hash,
    }
    body = _render_home_body(dashboard)
    path = wiki_root / "_home.md"
    written = _write_with_frontmatter(str(path), fm, body, source_ids=[])
    if written:
        _wc._pages_written.append(str(path))
    return written


def _render_section_today(d: dict) -> list[str]:
    from exocortex.wiki.domains.work import _render_tasks_query

    today = datetime.now(UTC).date()
    weekday_pl = [
        "poniedziałek",
        "wtorek",
        "środa",
        "czwartek",
        "piątek",
        "sobota",
        "niedziela",
    ][today.weekday()]
    lines = [
        f"## ⚡ Dziś ({weekday_pl} {today.isoformat()})",
        "",
    ]

    # ── Today's context: clients, projects, tags ──
    tc = d.get("today_context", {}) or {}
    today_meetings = tc.get("meetings") or []

    if today_meetings:
        all_clients: list[str] = []
        all_projects: list[str] = []
        all_tags: list[str] = []
        seen_clients: set[str] = set()
        seen_projects: set[str] = set()
        seen_tags: set[str] = set()

        for m in today_meetings:
            for c in m.get("clients") or []:
                if c.lower() not in seen_clients:
                    seen_clients.add(c.lower())
                    all_clients.append(c)
            for p in m.get("projects") or []:
                if p.lower() not in seen_projects:
                    seen_projects.add(p.lower())
                    all_projects.append(p)
            for t in m.get("tags") or []:
                if t.lower() not in seen_tags:
                    seen_tags.add(t.lower())
                    all_tags.append(t)

        if all_clients:
            client_links = " · ".join(f"[[{c}]]" for c in all_clients)
            lines.append(f"**Klienci**: {client_links}")
        if all_projects:
            project_links = " · ".join(f"[[{p}]]" for p in all_projects)
            lines.append(f"**Projekty**: {project_links}")
        if all_tags:
            tag_links = " ".join(f"#{t}" for t in all_tags)
            lines.append(f"**Tagi**: {tag_links}")
        if all_clients or all_projects or all_tags:
            lines.append("")

    # Tasks query limited to the current month (e.g. 2026-05 = 8 files).
    # A full scan of 219 files is too slow for the home page.
    # Full list: [[work/TODO/Moje TODO|My TODO]].
    current_month = today.strftime("%Y-%m")
    lines += [
        "### Aktywne",
        "",
        _render_tasks_query(
            filters=[
                f"filename includes {current_month}",
                "heading includes vault owner",
            ],
            sort="due",
            group_by=None,
            limit=20,
            extra=["short mode"],
        ),
        "",
        f"_Zakres: spotkania {current_month}. Pełna lista: [[work/TODO/Moje TODO|Moje TODO]]._",
        "",
    ]

    rv = d["frp_revisits"]
    if rv["due_today_count"] == 0:
        lines.append("- **FRP revisit due dziś**: brak")
    else:
        lines.append(
            f"- **FRP revisit due dziś**: **{rv['due_today_count']}** "
            f"(top {len(rv['top_due'])}):"
        )
        for s in rv["top_due"]:
            scenario = s["scenario"] or s["source_title"] or "(brak opisu)"
            lines.append(
                f"  - `{s['revisit_due']}` · frame={s['frame']} · {scenario[:80]} "
                f"(sesja {s['created_at']})"
            )
    lines.append("")
    return lines


def _render_section_news_pulse(d: dict) -> list[str]:
    lines = ["## 📰 Newsletter pulse — last 7 days", ""]
    snippet = d["news_brief_snippet"]
    if not snippet:
        lines += [
            ("> _Newsletter pipeline nieaktywny lub `wiki/news/start.md` brak — "
            "patrz [[news/_moc|news/_moc]] gdy `compile_news_module` zostanie "
            "uruchomiony._"),
            "",
        ]
    else:
        n0 = snippet[0]
        # Group claims by category
        from collections import OrderedDict

        categories: dict[str, list[str]] = OrderedDict()
        for c in snippet:
            label = c.get("category_label") or c["category"]
            claim = c.get("claim") or ""
            if claim:
                categories.setdefault(label, []).append(claim)
        lines += [
            (f"> Skrót z [[news/start|news/start]] (auto-refresh każde compile). "
            f"**{n0['window_total']} issues**, **{n0['insight_count']} insights**. "
            f"Top insighty per kategoria:"),
            "",
        ]
        for label, claims in categories.items():
            # Nested bullets (tight, no blank lines): Obsidian drops list-item
            # continuation after the first blank-separated paragraph, so multi-
            # insight categories rendered the first claim indented and the rest
            # flush-left. Sub-bullets indent every claim consistently.
            lines.append(f"- 🧠 **{label}**")
            for claim in claims:
                lines.append(f"  - {claim}")
            lines.append("")
        lines += ["_Pełna analiza: [[news/start|news/start.md]]._", ""]
    return lines


def _render_section_cross_domain(d: dict) -> list[str]:
    lines = [
        "## 🌐 Cross-domain signals (top 5, last 14d)",
        "",
        ("> `signals_domain` edges — FRP refleksje sygnalizujące entities z "
        "innych domen (z F7.4)."),
        "",
    ]
    cds = d["cross_domain_signals"]
    if not cds:
        lines += [
            ("_Brak `signals_domain` edges (last 14d). FRP refleksje z "
            "`entity_links` nie odbyły się ostatnio lub jeszcze nie ma "
            "cross-domain"
            " aktywności._"),
            "",
        ]
    else:
        for s in cds:
            slug = s["thought_slug"]
            if slug:
                src_link = f"[[frp/sessions#{slug}|{slug[:50]}]]"
            else:
                src_link = s["thought_title"] or s["src_thought_id"][:8]
            lines.append(
                f"- {src_link} → **{s['entity_name']}** "
                f"({s['entity_type']}) — _{s['edge_created']}_"
            )
        lines.append("")
    return lines


def _render_section_per_domain(d: dict) -> list[str]:
    lines = [
        "## 🔥 Co się dzieje per domena (recent 7d)",
        "",
        "| Domena | Thoughts | Recent (7d) |",
        "|---|---|---|",
    ]
    for slug, label, icon in _HOME_DOMAINS:
        a = d["per_domain_activity"].get(slug) or {"count": 0, "delta": 0}
        cnt = a["count"]
        delta = a["delta"]
        cnt_str = str(cnt) if cnt else "_(empty)_"
        delta_str = f"+{delta}" if delta else "_(quiet)_"
        lines.append(f"| {icon} [[{slug}/_moc\\|{label}]] | {cnt_str} | {delta_str} |")
    lines.append("")
    return lines


def _render_section_open_questions(d: dict) -> list[str]:
    lines = [
        "## ❓ Open questions (z work syntheses, last 30d)",
        "",
        ("> Top 5 `open_problems` z aktywnych syntheses (perspective_type="
        "client/project), sortowane po recency."),
        "",
    ]
    oq = d["open_questions"]
    if not oq:
        lines += ["_Brak otwartych problemów w syntheses (last 30d)._", ""]
    else:
        for q in oq:
            ptype = q["perspective_type"]
            pkey = q["perspective_key"]
            if ptype == "client":
                link = f"[[work/clients/{pkey}|{pkey}]]"
            else:
                link = (
                    f"[[work/projects/{pkey.split('/')[0]}/{pkey.split('/')[-1]}|{pkey}]]"
                    if "/" in pkey
                    else f"[[work/{pkey}|{pkey}]]"
                )
            lines.append(f"- **[{ptype}/{pkey}]** {q['problem']} — _z {link}_")
        lines.append("")
    return lines


def _render_section_reading_queue(d: dict) -> list[str]:
    # NOTE: the previous Dataview query `WHERE type = "frp_queue_item"` returned 0 rows
    # because all items are inline in a single `wiki/frp/reading-queue.md`, NOT in per-item
    # files. Static rendering from DB content_queue ORDER BY score_total DESC.
    rq = d["frp_reading_queue"]
    lines = ["## 🎯 Reading queue (FRP top 5)", ""]
    if rq["total"] == 0:
        lines += [
            ("_Queue jest pusta — RSS adapter (`second-brain-rss.timer`) nie "
            "znalazł nowych historii w ostatnim runie lub wszystkie items mają "
            "status≠queued._"),
            "",
        ]
    else:
        lines += [
            (f"> **{rq['total']} items queued** — pełna lista + ▶ Start FRP session: "
            f"[[frp/reading-queue|reading-queue]]"),
            "",
            "| # | Pozycja & lead | Score | Frame |",
            "|---|---|---|---|",
        ]
        for idx, it in enumerate(rq["items"], 1):
            title = it["title"].replace("|", "\\|")
            lead = (it.get("lead") or "").replace("|", "\\|")
            url = it["url"]
            head = (
                f"[{title}]({url})"
                if url and url.startswith(("http://", "https://"))
                else title
            )
            cell = f"**{head}**<br/>_{lead}_" if lead else f"**{head}**"
            score = it["score_total"] if it["score_total"] is not None else "—"
            frame = it["frame"] or "—"
            lines.append(f"| {idx} | {cell} | {score}/9 | {frame} |")
        lines.append("")
    return lines


def _render_section_operacyjne(d: dict) -> list[str]:
    lines = ["## 🛠️ Operacyjne", ""]
    sw = d["sanity_warnings"]
    warning_count = (
        sw.get("orphan_edges", 0)
        + sw.get("missing_embeddings", 0)
        + sw.get("missing_titles", 0)
        + sw.get("stale_syntheses", 0)
    )
    # Heuristic interpretation of warnings:
    # - orphan_edges + missing_embeddings + missing_titles below ~20 each = housekeeping noise.
    # - stale_syntheses > 0 is a re-run hint (synth daily cron has stalled or skipped that key).
    # - Any single counter ≥ 50 escalates to red flag investigation.
    housekeeping_only = (
        sw.get("stale_syntheses", 0) == 0
        and sw.get("missing_titles", 0) == 0
        and max(sw.get("orphan_edges", 0), sw.get("missing_embeddings", 0)) < 20
    )
    any_red = (
        max(
            sw.get("orphan_edges", 0),
            sw.get("missing_embeddings", 0),
            sw.get("missing_titles", 0),
            sw.get("stale_syntheses", 0),
        )
        >= 50
    )
    if not sw.get("fetched"):
        lines.append(
            "- ⚠️ **Sanity check niedostępny** — `python3 scripts/sanity_check.py` "
            "zwrócił błąd lub jeszcze nie odbył się."
        )
    elif warning_count == 0:
        lines.append("- ✅ **Sanity check**: brak warningów.")
    else:
        bits = []
        if sw["orphan_edges"]:
            bits.append(f"{sw['orphan_edges']} orphan edges")
        if sw["missing_embeddings"]:
            bits.append(f"{sw['missing_embeddings']} missing embeddings")
        if sw["missing_titles"]:
            bits.append(f"{sw['missing_titles']} missing titles")
        if sw["stale_syntheses"]:
            bits.append(f"{sw['stale_syntheses']} stale syntheses (>30d)")
        if any_red:
            flag = "🔴 Działanie wymagane — uruchom `python3 scripts/sanity_check.py` i investigate spike"
        elif housekeeping_only:
            flag = "✅ OK (housekeeping non-critical)"
        else:
            flag = "⚠️ Sprawdź `python3 scripts/sanity_check.py`"
        lines.append(f"- **{warning_count} warnings**: {', '.join(bits)} — {flag}")

    lcr = d["last_compile_run"]
    if lcr:
        ftime = lcr.get("finished_at")
        ftime_str = (
            ftime.strftime("%Y-%m-%d %H:%M UTC")
            if hasattr(ftime, "strftime")
            else str(ftime)[:16]
        )
        # Age of the last compile run, used to classify cron health.
        age_hours: float | None = None
        if hasattr(ftime, "tzinfo"):
            ft = ftime if ftime.tzinfo else ftime.replace(tzinfo=UTC)
            age_hours = (datetime.now(UTC) - ft).total_seconds() / 3600.0
        if age_hours is None:
            run_flag = "⚠️ timestamp nieczytelny"
        elif age_hours < 24:
            run_flag = "✅ świeże (<24h)"
        elif age_hours < 48:
            run_flag = "⚠️ stale (24-48h)"
        else:
            run_flag = "🔴 cron broken (>48h) — sprawdź `systemctl status second-brain-compile.timer`"
        lines.append(
            f"- 📅 **Last compile run**: {ftime_str} (domain={lcr['domain']}, "
            f"pages_written={lcr['pages_written_count']}, "
            f"failed_domains={lcr['failed_domains_count']}) — {run_flag}"
        )
    else:
        lines.append(
            "- 📅 **Last compile run**: brak recordów w `compile_runs` — "
            "🔴 cron prawdopodobnie nigdy nie ruszył"
        )

    cost = d["llm_cost_7d"]
    cost_total = float(cost.get("total_usd", 0.0) or 0.0)
    if cost_total < 5.0:
        cost_flag = "✅ normal (<$5/7d)"
    elif cost_total < 15.0:
        cost_flag = "⚠️ above typical ($5-15/7d) — review `synthesis_runs.cli_args`"
    else:
        cost_flag = "🔴 spike investigate (>$15/7d) — check for runaway re-synth"
    lines.append(
        f"- 💰 **Last 7d LLM cost** (synthesis_runs): "
        f"${cost_total:.4f} cumulative ({cost['run_count']} runs) — {cost_flag}"
    )
    lines.append("")

    # F14 — pipeline status
    pl = d.get("pipeline_status", {})
    workers = pl.get("workers", {})
    if workers:
        fail_count = pl.get("recent_failures", 0)
        status_emoji = "🟢" if fail_count == 0 else "🔴" if fail_count > 2 else "🟡"
        lines.append(
            f"- ⚙️ **Pipeline (48h)** — {len(workers)} workers, {fail_count} failures {status_emoji}"
        )
        for wname in sorted(workers.keys()):
            w = workers[wname]
            icon = "✅" if w["last_status"] == "success" else "❌"
            runtime = f"{w['last_runtime']:.0f}s" if w.get("last_runtime") else "?"
            lines.append(
                f"  - {icon} **{wname}** — {runtime} ago (48h: {w['runs_48h']} runs, {w['success_48h']} ok, {w['failures_48h']} fail)"
            )
            if w.get("last_error"):
                lines.append(f"    - Error: `{w['last_error'][:120]}`")
    lines.append("")
    return lines


def _render_section_quick_nav(d: dict) -> list[str]:
    lines = [
        "## 🗂️ Quick nav",
        "",
        ("- Per-domain MOCs: "
        "[[work/_moc|Work]] · [[news/_moc|News]] · [[frp/_moc|FRP]] · "
        "[[papers/_moc|Papers]] · [[cook/_moc|Cook]] · [[3d/_moc|3D]] · "
        "[[priv/_moc|Priv]]"),
        "- Cross-domain index: [[_index/people|People]] · [[_index/recent|Recent]]",
        "- Source corpus: `_source/` · `_inbox/`",
        "",
    ]
    return lines


def _render_section_pinned(d: dict) -> list[str]:
    # USER_NOTES_START/END sentinels are appended by `_write_with_frontmatter`
    # AFTER the GENERATED section. The heading + callout below live inside the GENERATED
    # block (re-rendered on every compile); the text points the user to
    # edit inside the sentinels (preserved on rerun, F10.1 Q2 lock).
    # NOTE: we do NOT write the literals `<!-- USER_NOTES_START -->` /
    # `<!-- USER_NOTES_END -->` into the callout text, because `_extract_user_notes`
    # matches these markers with a regex and would capture the inner content. We use
    # descriptive "USER_NOTES_START" wording in plain text.
    return [
        "## 📌 Pinned (manual)",
        "",
        "> [!info] Jak przypiąć",
        ("> Edytuj plik w **Edit view** (Obsidian). Twój content wpisz "
        "_pomiędzy_ markerami `USER_NOTES_START` a `USER_NOTES_END` "
        "(HTML-komentarze, znajdziesz je tuż pod tym blokiem). Następne "
        "compile zachowa Twoje notatki — sentinele są preserve-on-rerun "
        "(F10.1 Q2 lock)."),
        "",
    ]


def _render_section_resurfacing(d: dict) -> list[str]:
    """F31.2.4: 'Coming back to you' — passthrough wikilinks from wiki/_live/resurfacing.md.

    Pure: reads only the file, no DB. No file / no links → [] (section hidden).
    """
    resurfacing_path = d.get("_resurfacing_md_path")
    if not resurfacing_path:
        return []
    try:
        content = Path(resurfacing_path).read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return []
    wikilinks = re.findall(r"\[\[([^\]]+)\]\]", content)
    if not wikilinks:
        return []
    lines = ["## 🔄 Wraca do ciebie", ""]
    for wl in wikilinks:
        lines.append(f"- [[{wl}]]")
    lines.append("")
    return lines


_GAP_RADAR_TYPE_EMOJI = {
    "cluster-no-synth": "📚",
    "no-decision": "❓",
    "contradiction-unresolved": "⚡",
    "stale-orphan": "🕸️",
}


def _render_section_gap_radar(d: dict) -> list[str]:
    """F31.5.4: '🎯 Gap Radar' — top-5 gaps from run_all_detectors (pure SQL)."""
    lines = ["## 🎯 Gap Radar", ""]
    gaps = d.get("_gap_radar_gaps") or []
    if not gaps:
        lines += ["_Brak wykrytych luk lub synthesis starsza niż 8 dni._", ""]
        return lines
    for gap in gaps[:5]:
        emoji = _GAP_RADAR_TYPE_EMOJI.get(gap.get("type", ""), "🎯")
        age = int(gap.get("age_days", 0))
        action = gap.get("suggested_action", "")
        title = gap.get("title", "")
        lines.append(f"- {emoji} **{title}** — {action} ({age}d)")
    lines.append("")
    return lines


# Section ID → renderer mapping. User can reorder/disable sections via
# config/home_sections.yaml without code changes.
_HOME_SECTION_RENDERERS = {
    "today": _render_section_today,
    "resurfacing": _render_section_resurfacing,
    "gap_radar": _render_section_gap_radar,
    "news_pulse": _render_section_news_pulse,
    "cross_domain": _render_section_cross_domain,
    "per_domain": _render_section_per_domain,
    "open_questions": _render_section_open_questions,
    "reading_queue": _render_section_reading_queue,
    "operacyjne": _render_section_operacyjne,
    "quick_nav": _render_section_quick_nav,
    "pinned": _render_section_pinned,
}

_DEFAULT_HOME_SECTION_ORDER = [
    "today",
    "resurfacing",
    "gap_radar",
    "news_pulse",
    "cross_domain",
    "per_domain",
    "open_questions",
    "reading_queue",
    "operacyjne",
    "quick_nav",
    "pinned",
]


def _load_home_section_order() -> list[str]:
    """Load section order from config/home_sections.yaml or use default.

    Yaml format::

        sections:
          - today
          - news_pulse
          - reading_queue       # reorder, omit, or duplicate freely
          # - quick_nav          # commented out = hidden

    Unknown ids are skipped with a warning. Empty/missing config = default order.
    """
    try:
        import yaml as _yaml

        cfg_path = (
            Path(__file__).resolve().parent.parent.parent.parent.parent
            / "config"
            / "home_sections.yaml"
        )
        if not cfg_path.exists():
            return list(_DEFAULT_HOME_SECTION_ORDER)
        cfg = _yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        sections = cfg.get("sections") or []
        order: list[str] = []
        for entry in sections:
            sid = entry if isinstance(entry, str) else (entry or {}).get("id")
            if sid in _HOME_SECTION_RENDERERS:
                order.append(sid)
            elif sid:
                logging.warning(
                    "[wiki_compiler] unknown home section id=%r, skipping", sid
                )
        return order or list(_DEFAULT_HOME_SECTION_ORDER)
    except Exception as exc:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
        logging.warning(
            "[wiki_compiler] failed to load home_sections.yaml (%r), using default", exc
        )
        return list(_DEFAULT_HOME_SECTION_ORDER)


def _render_home_body(d: dict) -> str:
    """Multi-section markdown rendering. Section order configurable via
    `config/home_sections.yaml`. Header (counts banner) always first."""
    lines: list[str] = []

    # Header — always the first section (NOT configurable via yaml)
    active_doms = sum(1 for a in d["per_domain_activity"].values() if a["count"] > 0)
    last_refresh = datetime.now(ZoneInfo("Europe/Warsaw")).strftime("%Y-%m-%d %H:%M %Z")
    lines += [
        (f"> **last refresh {last_refresh}** · "
        f"**{d['total_thoughts']} thoughts** · **{d['total_edges']} edges** · "
        f"{active_doms} domeny aktywne"),
        "",
    ]

    # Per-section dispatch
    for sid in _load_home_section_order():
        renderer = _HOME_SECTION_RENDERERS.get(sid)
        if renderer is None:
            continue
        lines.extend(renderer(d))

    return "\n".join(lines).rstrip() + "\n"


class HomeDomain(_LegacyDomainCompiler):
    _legacy_fn_name = "compile_home_module"

    @property
    def name(self) -> str:
        return "home"


def setup(registry: Any) -> None:
    registry.register_compile_domain(HomeDomain())
