# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""News domain compiler — newsletter synthesis, topic pages, start.md aggregator.

Full implementation extracted from wiki_compiler.py (F31.6.2 batch 3).
Contains: compile_news_module + all helpers (loaders, writers, aggregator).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import yaml

from exocortex.wiki.util.slugs import _news_slug
from exocortex.wiki.util.coercion import _coerce_jsonb_list
from exocortex.wiki.core.io import _write_with_frontmatter
from exocortex.wiki.core.edges import _load_active_syntheses
from exocortex.wiki.domains.base import _LegacyDomainCompiler

log = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────────────────
# Global constants (moved from wiki_compiler.py header)
# ────────────────────────────────────────────────────────────────────────────

# F8.8.x.H1: hide singletons from by-topic/ — topics with <3 newsletter
# mentions are still queryable via Dataview but no atomic page is written.
NEWS_TOPIC_MIN_MENTIONS = 3

# F8.8.x.A — newsletter morning-brief aggregator (`wiki/news/start.md`).
NEWS_AGGREGATOR_WINDOW_DAYS = 7
NEWS_AGGREGATOR_WINDOW_DAYS_MIN = 1
NEWS_AGGREGATOR_WINDOW_DAYS_MAX = 30
NEWS_AGGREGATOR_TOP_CATEGORIES = 5
NEWS_AGGREGATOR_INSIGHTS_PER_CATEGORY_MAX = 5
NEWS_AGGREGATOR_INSIGHTS_PER_CATEGORY_MIN = 3
NEWS_AGGREGATOR_SPARSE_THRESHOLD = 10  # if window has fewer issues, expand
NEWS_AGGREGATOR_SPARSE_FALLBACK_DAYS = 30
NEWS_AGGREGATOR_RECENCY_HALFLIFE_DAYS = 2.4
NEWS_AGGREGATOR_CONSENSUS_SIM_THRESHOLD = 0.82  # cross-newsletter "same finding"
NEWS_AGGREGATOR_DEDUP_SIM_THRESHOLD = 0.88  # within-category merge
NEWS_AGGREGATOR_NEW_CITED_TOP = 15
NEWS_AGGREGATOR_LATEST_LIMIT = 14
NEWS_AGGREGATOR_COST_STOP_USD = 0.30  # 6× headroom over $0.05 target
NEWS_AGGREGATOR_PROMPT_VERSION = (
    "aggregator-v1.3-pl-anti-anglicism"  # F-newsletter-redesign 2026-05-04
)
NEWS_AGGREGATOR_LLM_MODEL = "claude-haiku-4-5"
# Env-driven as in db/embeddings.py (K12: bge-m3 via llama-swap).
NEWS_AGGREGATOR_EMBED_MODEL = os.environ.get(
    "EXOCORTEX_EMBEDDING_MODEL", "text-embedding-3-small")
# Static newsletter authority (0.0–1.0). Default 0.6 for unknown brands;
# optional `config/news_source_authority.yaml` overrides per-brand.
NEWS_SOURCE_AUTHORITY_DEFAULT = 0.6
NEWS_SOURCE_AUTHORITY: dict[str, float] = {
    "daily dose of ds": 0.9,
    "bytebytego": 0.9,
    "nlp newsletter": 0.85,
    "slow ai": 0.85,
    "human in the loop": 0.8,
    "the rundown ai": 0.7,
    "ai breakfast": 0.7,
    "ai report": 0.65,
    "tldr ai": 0.65,
    "there's an ai for that": 0.6,
    "lenny’s newsletter": 0.8,
    "lennys newsletter": 0.8,
    "one useful thing": 0.8,
    "simon willison": 0.85,
    "stratechery": 0.85,
}
# Component weights (must sum to 1.0).
NEWS_AGGREGATOR_WEIGHTS = {
    "recency": 0.45,
    "consensus": 0.30,
    "cited": 0.15,
    "authority": 0.10,
}

# F8.8.x.A — overridable per-CLI-run; None means "use NEWS_AGGREGATOR_WINDOW_DAYS".
_news_aggregator_window_override: Optional[int] = None

# Bumped from v1 (no thought_id suffix) to v2 (8-char UUID disambiguator).
# Included in by-source/by-topic/by-category/start input_hash payloads
# so a slug format change invalidates every cross-link page in one compile.
_NEWS_SLUG_FORMAT_VERSION = "v2"

# F8.8.x.H2 — topic clusters (closed slugs, open membership). One-shot
# load per compile; missing/empty file = graceful no-op (by-category section
# simply doesn't render). Returns (topic_to_cluster, clusters_by_slug).
_TOPIC_CLUSTERS_CACHE: Optional[tuple[dict[str, dict], dict[str, dict]]] = None

_NEWS_CLUSTER_DEFAULT_EMOJI = "📰"


# ────────────────────────────────────────────────────────────────────────────
# News data loaders
# ────────────────────────────────────────────────────────────────────────────


def _load_news_issues(tenant_id: str, since: Optional[datetime]) -> list[dict]:
    """Pull all newsletter_synthesis thoughts + their raw_source metadata.

    Returns list[dict] z: {thought_id, title, uri, captured_at, body,
    extracted_tags, newsletter_name, sender_email, source_id, raw_metadata}.
    Sorted by captured_at DESC (newest first — convenient for MOCs).
    """
    from exocortex.db import query

    where = ["t.tenant_id = %s", "t.thought_type = 'newsletter_synthesis'"]
    params: list = [tenant_id]
    if since is not None:
        where.append("t.created_at >= %s")
        params.append(since)

    rows = query(
        "SELECT t.id::text AS thought_id, t.body, t.metadata AS t_meta, "
        "       t.created_at, t.extracted_tags, "
        "       t.source_id::text AS source_id, "
        "       rs.uri AS source_uri, rs.metadata AS rs_meta "
        "  FROM thoughts t "
        "  LEFT JOIN raw_sources rs ON rs.id = t.source_id "
        " WHERE " + " AND ".join(where) + " ORDER BY t.created_at DESC",
        *params,
    )
    issues: list[dict] = []
    for r in rows:
        t_meta = r.get("t_meta") or {}
        rs_meta = r.get("rs_meta") or {}
        nl = (r.get("extracted_tags") or {}).get("_newsletter") or {}
        issues.append(
            {
                "thought_id": r["thought_id"],
                "source_id": r.get("source_id"),
                "title": t_meta.get("title") or "(untitled)",
                "uri": t_meta.get("uri") or r.get("source_uri") or "",
                "captured_at": r["created_at"],
                "body": r.get("body") or "",
                "newsletter_name": (
                    nl.get("newsletter_name")
                    or t_meta.get("newsletter_name")
                    or rs_meta.get("sender_name")
                    or "(unknown)"
                ),
                "sender_email": (
                    nl.get("sender_email")
                    or t_meta.get("sender_email")
                    or rs_meta.get("sender_email")
                ),
                "tldr": nl.get("tldr") or t_meta.get("tldr") or "",
                # Defensive: some upstream processors stored these as JSON strings
                # rather than native list[dict]. Coerce both shapes.
                "key_insights": _coerce_jsonb_list(nl.get("key_insights")),
                "cited_sources": _coerce_jsonb_list(nl.get("cited_sources")),
                "topics": [
                    (t.get("value") if isinstance(t, dict) else str(t))
                    for t in (r.get("extracted_tags") or {}).get("topic") or []
                ],
                # F8.8.x.A — raw_sources metadata; aggregator reads `date_header`
                # (RFC 2822) for real recency, since `created_at` collapses on
                # backfill days.
                "raw_metadata": dict(rs_meta),
            }
        )
    return issues


def _news_issue_slug(issue: dict) -> str:
    """Filename-safe slug: {YYYY-MM-DD}-{newsletter-slug}-{title-slug}-{thought_id_short}.

    The 8-char thought_id suffix disambiguates atomic pages with identical
    title (e.g. multiple "🥇Top AI Papers of the Week" issues from
    The Rundown AI). Collisions before fix caused "wrote 2 issues
    (+ 98 unchanged)" each compile forever.
    """
    captured = issue.get("captured_at")
    date = captured.strftime("%Y-%m-%d") if hasattr(captured, "strftime") else "undated"
    nl_slug = _news_slug(issue.get("newsletter_name") or "unknown")
    title_slug = _news_slug(issue.get("title") or "untitled")
    tid_short = (issue.get("thought_id") or "")[:8] or "noid"
    base = f"{date}-{nl_slug}-{title_slug}"[:108]  # 108 + 1 dash + 8 = 117, < 120
    return f"{base}-{tid_short}"


def _top_cited_for_topic(
    tenant_id: str, topic_slug: str, limit: int = 10
) -> list[dict]:
    """Top entities cited from newsletter thoughts tagged with `topic_slug`.

    Returns list of {name, type, mention_count} sorted DESC.
    Traverses `cites` edges (newsletter_thought → entity) and joins on
    extracted_tags->'topic' (JSONB array of {value, confidence, new}).
    Returns [] gracefully when there are 0 citations.
    """
    from exocortex.db import query

    rows = query(
        "SELECT e.canonical_name AS name, e.type AS type, count(*) AS mention_count "
        "  FROM edges ed "
        "  JOIN entities e ON e.id = ed.dst_id AND ed.dst_type = 'entity' "
        "  JOIN thoughts t ON t.id = ed.src_id AND ed.src_type = 'thought' "
        " WHERE ed.type = 'cites' "
        "   AND t.thought_type = 'newsletter_synthesis' "
        "   AND t.tenant_id = %s "
        "   AND t.extracted_tags->'topic' @? %s::jsonpath "
        " GROUP BY e.canonical_name, e.type "
        " ORDER BY mention_count DESC "
        " LIMIT %s",
        tenant_id,
        f'$[*] ? (@.value == "{topic_slug}")',
        limit,
    )
    return [
        {"name": r["name"], "type": r["type"], "mention_count": int(r["mention_count"])}
        for r in rows
    ]


def _related_topics_for_topic(
    tenant_id: str, topic_slug: str, min_cooc: int = 3, limit: int = 10
) -> list[dict]:
    """Topic pairs co-occurring with `topic_slug` across newsletter thoughts.

    Returns list of {topic_slug, cooc_count} sorted DESC. JSONB query on
    extracted_tags->'topic'. Self-pairs filtered out. Returns [] when 0 related.
    """
    from exocortex.db import query

    rows = query(
        "WITH topics_unnest AS ( "
        "  SELECT t.id AS thought_id, "
        "         jsonb_array_elements(t.extracted_tags->'topic')->>'value' AS topic_value "
        "    FROM thoughts t "
        "   WHERE t.tenant_id = %s "
        "     AND t.thought_type = 'newsletter_synthesis' "
        "     AND t.extracted_tags ? 'topic' "
        ") "
        "SELECT b.topic_value AS topic_slug, count(*) AS cooc_count "
        "  FROM topics_unnest a "
        "  JOIN topics_unnest b ON a.thought_id = b.thought_id "
        " WHERE a.topic_value = %s "
        "   AND b.topic_value <> %s "
        " GROUP BY b.topic_value "
        " HAVING count(*) >= %s "
        " ORDER BY cooc_count DESC "
        " LIMIT %s",
        tenant_id,
        topic_slug,
        topic_slug,
        min_cooc,
        limit,
    )
    return [
        {"topic_slug": r["topic_slug"], "cooc_count": int(r["cooc_count"])}
        for r in rows
    ]


def _load_topic_clusters() -> tuple[dict[str, dict], dict[str, dict]]:
    """Read `config/news_topic_clusters.yaml`.

    Returns (topic_to_cluster, clusters_by_slug):
      - topic_to_cluster: {topic_slug: cluster_dict}  for O(1) topic→cluster.
      - clusters_by_slug: {cluster_slug: cluster_dict} for ordered iteration.

    Missing file or empty `clusters: []` returns ({}, {}). All topic keys
    normalised through `_news_slug` to match downstream comparisons.
    """
    global _TOPIC_CLUSTERS_CACHE
    if _TOPIC_CLUSTERS_CACHE is not None:
        return _TOPIC_CLUSTERS_CACHE

    from exocortex.config_loader import resolve_config_path

    cfg_path = resolve_config_path("news_topic_clusters.yaml")
    topic_to_cluster: dict[str, dict] = {}
    clusters_by_slug: dict[str, dict] = {}
    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        _TOPIC_CLUSTERS_CACHE = ({}, {})
        return _TOPIC_CLUSTERS_CACHE
    except Exception as exc:
        logging.warning("[wiki_compiler] cannot parse %s: %r", cfg_path, exc)
        _TOPIC_CLUSTERS_CACHE = ({}, {})
        return _TOPIC_CLUSTERS_CACHE

    for cl in cfg.get("clusters") or []:
        slug = (cl.get("slug") or "").strip()
        if not slug:
            continue
        clusters_by_slug[slug] = cl
        for t in cl.get("topics") or []:
            topic_to_cluster[_news_slug(t)] = cl

    _TOPIC_CLUSTERS_CACHE = (topic_to_cluster, clusters_by_slug)
    return _TOPIC_CLUSTERS_CACHE


def _group_news_by_category(
    issues: list[dict],
    topic_to_cluster: dict[str, dict],
) -> dict[str, list[dict]]:
    """Group issues by cluster slug. One issue may appear under multiple
    clusters (its topics span them). Topics not in any cluster route the
    issue to the `_misc` bucket. De-dup ensures one (cluster, issue) pair.
    """
    out: dict[str, list[dict]] = {}
    for it in issues:
        seen: set[str] = set()
        topics = it.get("topics") or []
        if not topics:
            seen.add("_misc")
            out.setdefault("_misc", []).append(it)
            continue
        had_cluster = False
        for t in topics:
            cl = topic_to_cluster.get(_news_slug(t))
            if cl is None:
                continue
            cluster_slug = cl.get("slug")
            if not cluster_slug or cluster_slug in seen:
                continue
            seen.add(cluster_slug)
            out.setdefault(cluster_slug, []).append(it)
            had_cluster = True
        if not had_cluster:
            seen.add("_misc")
            out.setdefault("_misc", []).append(it)
    return out


def _group_news_by_source(issues: list[dict]) -> dict[str, list[dict]]:
    """Group issues by newsletter_name slug."""
    out: dict[str, list[dict]] = {}
    for it in issues:
        slug = _news_slug(it.get("newsletter_name") or "unknown")
        out.setdefault(slug, []).append(it)
    return out


def _group_news_by_topic(issues: list[dict]) -> dict[str, list[dict]]:
    """Group issues by topic. One issue may appear under multiple topics.

    F8.8.x.H1 — drops singleton topics (mention_count < NEWS_TOPIC_MIN_MENTIONS)
    so the by-topic/ folder stays curated. Singletons still surface via the
    "All topics" Dataview block in _moc.md.
    """
    out: dict[str, list[dict]] = {}
    for it in issues:
        for t in it.get("topics") or []:
            slug = _news_slug(t)
            if slug:
                out.setdefault(slug, []).append(it)
    return {k: v for k, v in out.items() if len(v) >= NEWS_TOPIC_MIN_MENTIONS}


# ────────────────────────────────────────────────────────────────────────────
# News writers
# ────────────────────────────────────────────────────────────────────────────


def _write_news_issue_page(
    news_root: Path,
    issue: dict,
    topic_to_cluster: Optional[dict[str, dict]] = None,
) -> bool:
    """Atomic per-issue page. Returns True if file was written.

    Layout: news_root/src/{source-slug}/{full-slug}.md — atomic source
    pages tucked under news/src/ so the top-level news/ shows only the
    reader-facing artifacts (by-source/, by-topic/, _moc.md). Obsidian
    wikilinks resolve by basename, so [[<slug>]] still works from
    by-source/by-topic MOCs without needing relative paths.
    """
    slug = _news_issue_slug(issue)
    source_slug = _news_slug(issue.get("newsletter_name") or "unknown")
    source_dir = news_root / "src" / source_slug
    source_dir.mkdir(parents=True, exist_ok=True)
    path = source_dir / f"{slug}.md"

    title = issue["title"]
    captured = issue.get("captured_at")
    date = captured.strftime("%Y-%m-%d") if hasattr(captured, "strftime") else ""

    # F8.8.x.A — cluster_slugs derived from topics → clusters_by_slug map.
    # Enables Dataview pivots in start.md without re-querying DB.
    cluster_slugs: list[str] = []
    if topic_to_cluster:
        seen: set[str] = set()
        for t in issue.get("topics") or []:
            cl = topic_to_cluster.get(_news_slug(t))
            if cl:
                cs = cl.get("slug")
                if cs and cs not in seen:
                    cluster_slugs.append(cs)
                    seen.add(cs)

    fm: dict[str, Any] = {
        "type": "newsletter",
        "newsletter_name": issue.get("newsletter_name"),
        "sender_email": issue.get("sender_email"),
        "issue_date": date,
        "topics": list(issue.get("topics") or []),
        "cluster_slugs": cluster_slugs,
        "cited_sources_count": len(issue.get("cited_sources") or []),
        "_synthesis_thought_id": issue.get("thought_id"),
        "_synthesis_source_id": issue.get("source_id"),
    }

    # Compute input_hash from the load-time fields. Re-runs with unchanged
    # synthesis content short-circuit at _write_with_frontmatter.
    hash_payload = json.dumps(
        [
            title,
            issue.get("newsletter_name"),
            date,
            issue.get("tldr"),
            issue.get("key_insights"),
            issue.get("topics"),
            cluster_slugs,
            issue.get("cited_sources"),
        ],
        sort_keys=True,
        default=str,
        ensure_ascii=False,
    ).encode("utf-8")
    fm["_input_hash"] = hashlib.sha256(hash_payload).hexdigest()[:16]

    body = _render_news_issue_body(issue)
    return _write_with_frontmatter(
        str(path),
        fm,
        body,
        source_ids=[issue.get("source_id")] if issue.get("source_id") else [],
    )


def _render_news_issue_body(issue: dict) -> str:
    lines: list[str] = []
    title = issue.get("title") or "(untitled)"
    lines.append(f"# {title}")
    lines.append("")
    sender = issue.get("newsletter_name") or "?"
    if issue.get("sender_email"):
        sender = f"{sender} (`{issue['sender_email']}`)"
    lines.append(f"> Source: **{sender}**")
    if issue.get("uri"):
        lines.append(f"> [Open in Gmail]({issue['uri']})")
    lines.append("")

    lines.append("## TL;DR")
    lines.append(issue.get("tldr") or "_(empty)_")
    lines.append("")

    lines.append("## Key insights")
    if issue.get("key_insights"):
        for it in issue["key_insights"]:
            if isinstance(it, dict):
                insight = it.get("insight") or "?"
                evidence = it.get("evidence") or ""
            else:
                insight = str(it) if it else "?"
                evidence = ""
            lines.append(f"- **{insight}**")
            if evidence:
                lines.append(f"  > {evidence}")
    else:
        lines.append("_(none)_")
    lines.append("")

    lines.append("## Topics")
    topics = issue.get("topics") or []
    if topics:
        # Render topics as Obsidian tags so Dataview/by-topic queries pick them up.
        lines.append(" ".join(f"#news/{_news_slug(t)}" for t in topics))
    else:
        lines.append("_(none)_")
    lines.append("")

    lines.append("## Cited sources")
    cited = issue.get("cited_sources") or []
    if cited:
        for s in cited:
            if isinstance(s, dict):
                name = s.get("name") or "?"
                url = s.get("url") or ""
                stype = s.get("type") or "unknown"
            else:
                name = str(s) if s else "?"
                url = ""
                stype = "unknown"
            if url:
                lines.append(f"- [{name}]({url}) — *{stype}*")
            else:
                lines.append(f"- {name} — *{stype}*")
    else:
        lines.append("_(none)_")
    lines.append("")

    lines.append("## Backlinks")
    lines.append(
        f"- Source MOC: [[by-source/{_news_slug(issue.get('newsletter_name') or 'unknown')}]]"
    )
    if topics:
        topic_links = ", ".join(f"[[by-topic/{_news_slug(t)}|{t}]]" for t in topics)
        lines.append(f"- Topics: {topic_links}")
    return "\n".join(lines) + "\n"


def _write_news_by_source_page(
    by_source_dir: Path, slug: str, issues: list[dict]
) -> bool:
    """One MOC per newsletter brand. Lists every issue from that source."""
    if not issues:
        return False
    name = issues[0].get("newsletter_name") or slug
    path = by_source_dir / f"{slug}.md"

    fm: dict[str, Any] = {
        "type": "newsletter-source-moc",
        "newsletter_name": name,
        "issue_count": len(issues),
    }
    payload = json.dumps(
        [
            _NEWS_SLUG_FORMAT_VERSION,
            [
                (i.get("thought_id"), i.get("title"), str(i.get("captured_at")))
                for i in issues
            ],
        ],
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    fm["_input_hash"] = hashlib.sha256(payload).hexdigest()[:16]

    lines = [f"> {len(issues)} issue(s) — auto-generated z newsletter pipeline.", ""]
    lines.append("## Recent issues")
    for it in issues[:25]:
        date = ""
        if hasattr(it.get("captured_at"), "strftime"):
            date = it["captured_at"].strftime("%Y-%m-%d")
        link = f"[[{_news_issue_slug(it)}|{it['title']}]]"
        lines.append(f"- {date} — {link}")
    if len(issues) > 25:
        lines.append("")
        lines.append(f"_(+ {len(issues) - 25} older — Dataview block below shows all)_")
    lines.append("")
    lines.append("## All issues (Dataview)")
    lines.append("```dataview")
    lines.append(
        'TABLE issue_date, length(topics) AS "topics", cited_sources_count AS "cited"'
    )
    lines.append('FROM "wiki/news"')
    lines.append(f'WHERE type = "newsletter" AND newsletter_name = "{name}"')
    lines.append("SORT issue_date DESC")
    lines.append("```")
    return _write_with_frontmatter(
        str(path), fm, "\n".join(lines) + "\n", source_ids=[]
    )


def _write_news_by_topic_page(
    by_topic_dir: Path, slug: str, issues: list[dict], tenant_id: str
) -> bool:
    """One MOC per topic. Lists every issue tagged with that topic.

    Adds (F8.8.x.C) `## Frequently cited` from `cites` edges and
    (F8.8.x.D) `## Related topics` from JSONB co-occurrence query.
    Both deterministic SQL aggregations — zero LLM cost.
    """
    if not issues:
        return False
    path = by_topic_dir / f"{slug}.md"
    # Prefer first-seen capitalized variant for the title.
    label = slug.replace("-", " ")
    for it in issues:
        for t in it.get("topics") or []:
            if _news_slug(t) == slug:
                label = t
                break

    cited_list = _top_cited_for_topic(tenant_id, slug, limit=10)
    related_list = _related_topics_for_topic(tenant_id, slug, min_cooc=3, limit=10)

    fm: dict[str, Any] = {
        "type": "newsletter-topic-moc",
        "title": f"Topic: {label}",
        "topic": label,
        "issue_count": len(issues),
        "cited_count": len(cited_list),
        "related_count": len(related_list),
    }
    payload = json.dumps(
        [
            _NEWS_SLUG_FORMAT_VERSION,
            [(i.get("thought_id"), str(i.get("captured_at"))) for i in issues],
            [(c["name"], c["type"], c["mention_count"]) for c in cited_list],
            [(r["topic_slug"], r["cooc_count"]) for r in related_list],
        ],
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    fm["_input_hash"] = hashlib.sha256(payload).hexdigest()[:16]

    lines = [f"> {len(issues)} newsletter mention(s).", ""]
    lines.append("## Mentions")
    for it in issues[:50]:
        date = ""
        if hasattr(it.get("captured_at"), "strftime"):
            date = it["captured_at"].strftime("%Y-%m-%d")
        nl = it.get("newsletter_name") or "?"
        link = f"[[{_news_issue_slug(it)}|{it['title']}]]"
        lines.append(f"- {date} — *{nl}* — {link}")
    lines.append("")

    if cited_list:
        lines.append("## Frequently cited")
        for c in cited_list:
            lines.append(
                f"- **{c['name']}** ({c['type']}) — {c['mention_count']} newsletter(s)"
            )
        lines.append("")

    if related_list:
        lines.append("## Related topics (cooc ≥3)")
        for r in related_list:
            slug = r["topic_slug"]
            cooc = r["cooc_count"]
            lines.append(f"- [[{slug}]] — {cooc} newsletter(s) together")
        lines.append("")

    lines.append("## Dataview")
    lines.append("```dataview")
    lines.append('TABLE newsletter_name AS "source", issue_date')
    lines.append('FROM "wiki/news"')
    lines.append(f'WHERE type = "newsletter" AND contains(topics, "{label}")')
    lines.append("SORT issue_date DESC")
    lines.append("```")
    return _write_with_frontmatter(
        str(path), fm, "\n".join(lines) + "\n", source_ids=[]
    )


def _write_news_by_category_page(
    by_category_dir: Path,
    slug: str,
    issues: list[dict],
    cluster_meta: Optional[dict],
    topic_mention_counts: dict[str, int],
    synthesis: Optional[dict] = None,
) -> bool:
    """One MOC per cluster. Lists member topics (wikilinks if ≥threshold,
    plain text otherwise) + recent issues + Dataview block.

    cluster_meta is None for the synthetic `_misc` bucket — we render a
    minimal page in that case (no member_topics list, no description).

    synthesis (F8.8.x.B) is the active row from `syntheses` table for
    perspective_type='news_cluster' / perspective_key=slug. When present,
    rendered as banner + 5 sections (emerging consensus / notable claims /
    contradictions / key sources / trends to watch) at the TOP of the body,
    before "Member topics". Source links resolve newsletter slugs in
    `issues` (thought_id → wikilink to atomic per-issue page).
    """
    if not issues:
        return False
    path = by_category_dir / f"{slug}.md"

    is_misc = cluster_meta is None or slug == "_misc"
    label = (cluster_meta or {}).get("label") or (
        "Niesklasyfikowane" if is_misc else slug
    )
    emoji = (cluster_meta or {}).get("emoji") or ("🗂️" if is_misc else "")
    description = (cluster_meta or {}).get("description") or (
        "Newsletter issues whose topics nie pasują do żadnej zdefiniowanej kategorii."
        if is_misc
        else ""
    )
    member_topics_raw = list((cluster_meta or {}).get("topics") or [])
    member_topics = [_news_slug(t) for t in member_topics_raw if _news_slug(t)]

    fm: dict[str, Any] = {
        "type": "newsletter-category-moc",
        "cluster_slug": slug,
        "cluster_label": label,
        "cluster_emoji": emoji,
        "cluster_description": description,
        "member_topics": member_topics,
        "issue_count": len(issues),
    }
    if synthesis and synthesis.get("id"):
        fm["_synthesis_id"] = str(synthesis["id"])
    payload = json.dumps(
        [
            _NEWS_SLUG_FORMAT_VERSION,
            label,
            emoji,
            description,
            sorted(member_topics),
            sorted((i.get("thought_id"), str(i.get("captured_at"))) for i in issues),
            # F8.8.x.B — invalidate cache when synthesis content changes.
            (str(synthesis["id"]) if synthesis and synthesis.get("id") else None),
            (synthesis.get("input_hash") if synthesis else None),
        ],
        sort_keys=True,
        default=str,
        ensure_ascii=False,
    ).encode("utf-8")
    fm["_input_hash"] = hashlib.sha256(payload).hexdigest()[:16]

    heading = f"# {emoji} {label}".strip() if emoji else f"# {label}"
    lines: list[str] = [heading, ""]
    if description:
        lines += [description, ""]
    lines += [
        f"> {len(issues)} newsletter issue(s) — auto-generated z newsletter pipeline.",
        "",
    ]

    # F8.8.x.B — synthesis section AT TOP of body, BEFORE "Member topics".
    # Banner + 5 renamed sections (emerging consensus / notable claims /
    # contradictions / key sources / trends to watch). Skip silently when no
    # synthesis (graceful: page still renders with member_topics + issues).
    if synthesis and synthesis.get("content"):
        # Build thought_id → newsletter issue lookup so source links resolve
        # to atomic per-issue wikilinks (`src/{newsletter}/{slug}`).
        source_meetings: dict[str, dict] = {}
        for it in issues:
            tid = it.get("thought_id")
            if tid:
                source_meetings[str(tid)] = {"slug": _news_issue_slug(it)}
        from exocortex.wiki.domains.synthesis_render import _render_synthesis_banner

        lines += _render_synthesis_banner(
            synthesis,
            len(issues),
            extra=f"kategoria: **{label}**",
        )
        lines += _format_news_synthesis_sections(
            synthesis["content"],
            synthesis,
            source_meetings,
        )

    # Member topics — wikilink to by-topic/{slug} only when threshold met.
    if not is_misc and member_topics:
        lines.append("## Member topics")
        for ts in member_topics:
            mentions = topic_mention_counts.get(ts, 0)
            if mentions >= NEWS_TOPIC_MIN_MENTIONS:
                lines.append(
                    f"- [[../by-topic/{ts}|{ts}]] "
                    f"({mentions} mention{'s' if mentions != 1 else ''})"
                )
            elif mentions > 0:
                lines.append(f"- {ts} ({mentions} mention)")
            else:
                lines.append(f"- {ts} _(no newsletter mentions yet)_")
        lines.append("")

    lines.append("## Recent issues (top 25)")
    sorted_issues = sorted(
        issues,
        key=lambda i: (i.get("captured_at") is None, i.get("captured_at")),
        reverse=True,
    )
    for it in sorted_issues[:25]:
        date = ""
        if hasattr(it.get("captured_at"), "strftime"):
            date = it["captured_at"].strftime("%Y-%m-%d")
        nl = it.get("newsletter_name") or "?"
        link = f"[[{_news_issue_slug(it)}|{it['title']}]]"
        lines.append(f"- {date} — *{nl}* — {link}")
    if len(sorted_issues) > 25:
        lines.append("")
        lines.append(
            f"_(+ {len(sorted_issues) - 25} older — Dataview block below shows all)_"
        )
    lines.append("")

    # Dataview: `any()` over the cluster's member topics. For _misc we skip
    # the block — there is no canonical member list and a `NOT contains`
    # query over union of all clusters would be brittle.
    if not is_misc and member_topics:
        topic_literals = ", ".join(f'"{t}"' for t in member_topics)
        lines += [
            "## All issues (Dataview)",
            "```dataview",
            'TABLE newsletter_name AS "source", issue_date, length(topics) AS "topics"',
            'FROM "wiki/news"',
            f'WHERE type = "newsletter" AND any(topics, (t) => contains(list({topic_literals}), t))',
            "SORT issue_date DESC",
            "```",
        ]
    return _write_with_frontmatter(
        str(path), fm, "\n".join(lines) + "\n", source_ids=[]
    )


# ────────────────────────────────────────────────────────────────────────────
# F8.8.x.B — news_cluster synthesis sections
# ────────────────────────────────────────────────────────────────────────────


def _format_news_synthesis_sections(
    content: dict, syn: dict, source_meetings: dict[str, dict]
) -> list[str]:
    """F8.8.x.B — render the 5-section synthesis with news_cluster semantics.

    Same `content` schema as `_format_synthesis_sections` (current_state /
    recent_decisions / open_problems / ownership / next_steps) but the section
    headers and prose are renamed to match the NEWS_PROMPT_OVERLAY mapping the
    LLM was instructed against:
      current_state    → ## Emerging consensus
      recent_decisions → ## Notable claims
      open_problems    → ## Contradictions / unresolved
      ownership        → ## Key sources cited
      next_steps       → ## Trends to watch

    `source_meetings` maps thought_id → {'slug': newsletter-issue-slug} so
    `[source]` wikilinks resolve to the atomic per-issue page in `news/src/`.
    """
    lines: list[str] = []

    def _link(tid: str) -> str:
        m = source_meetings.get(str(tid))
        if not m:
            return ""
        return f" ([[{m['slug']}|source]])"

    def _link_many(tids: list[str]) -> str:
        good = [_link(t).strip(" ()") for t in tids if _link(t)]
        good = [g for g in good if g]
        if not good:
            return ""
        return " (" + ", ".join(good) + ")"

    cs = (content.get("current_state") or "").strip()
    lines += ["## Emerging consensus", "", cs if cs else "_brak danych_", ""]

    decisions = content.get("recent_decisions") or []
    lines += ["## Notable claims", ""]
    if decisions:
        for d in decisions:
            date_part = d.get("date") or ""
            head = f"- **{date_part}** — " if date_part else "- "
            lines.append(
                f"{head}{d.get('content', '')}{_link(d.get('source_thought_id', ''))}"
            )
    else:
        lines.append("_brak notable claims_")
    lines.append("")

    problems = content.get("open_problems") or []
    if problems:
        lines += ["> [!warning] Contradictions / unresolved questions"]
        for p in problems:
            sev = (p.get("severity") or "medium").upper()
            lines.append(
                f"> - **{sev}**: {p.get('content', '')}"
                f"{_link(p.get('source_thought_id', ''))}"
            )
        lines.append("")
    else:
        lines += [
            "## Contradictions / unresolved",
            "",
            "_brak otwartych sprzeczności_",
            "",
        ]

    ownership = content.get("ownership") or []
    lines += ["## Key sources cited", ""]
    if ownership:
        for o in ownership:
            person = o.get("person") or "?"
            area = o.get("area") or ""
            sids = o.get("source_thought_ids") or []
            lines.append(f"- **{person}** — {area}{_link_many(sids)}")
    else:
        lines.append("_brak danych_")
    lines.append("")

    next_steps = content.get("next_steps") or []
    lines += ["## Trends to watch", ""]
    if next_steps:
        for s in next_steps:
            date_part = s.get("date") or ""
            head = f"- **{date_part}** — " if date_part else "- "
            owner = s.get("owner") or ""
            owner_part = f" _({owner})_" if owner else ""
            lines.append(
                f"{head}{s.get('action', '')}{owner_part}"
                f"{_link(s.get('source_thought_id', ''))}"
            )
    else:
        lines.append("_brak trendów_")
    lines.append("")

    return lines


# ────────────────────────────────────────────────────────────────────────────
# F8.8.x.A — newsletter feed aggregator
#
# Morning-brief writer at `wiki/news/start.md`. Light LLM tier:
# claude-haiku merge per category (5 calls) + text-embedding-3-small
# consensus signal (cached). Pure-deterministic fallback when LLM/embedding
# clients are unreachable so a daily compile never breaks the pipeline.
# ────────────────────────────────────────────────────────────────────────────


def _news_authority(brand: Optional[str]) -> float:
    if not brand:
        return NEWS_SOURCE_AUTHORITY_DEFAULT
    return NEWS_SOURCE_AUTHORITY.get(
        brand.strip().lower(),
        NEWS_SOURCE_AUTHORITY_DEFAULT,
    )


def _parse_news_date_header(s: Any) -> Optional[datetime]:
    """RFC 2822 → tz-aware UTC datetime. Returns None on parse failure."""
    if not s:
        return None
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=timezone.utc)
    try:
        from email.utils import parsedate_to_datetime

        dt = parsedate_to_datetime(str(s))
    except (TypeError, ValueError, IndexError):
        return None
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _news_issue_window_dt(issue: dict) -> Optional[datetime]:
    """Best-effort window timestamp: date_header → captured_at fallback."""
    rs = issue.get("raw_metadata") or {}
    dt = _parse_news_date_header(rs.get("date_header"))
    if dt is not None:
        return dt
    captured = issue.get("captured_at")
    if isinstance(captured, datetime):
        return captured if captured.tzinfo else captured.replace(tzinfo=timezone.utc)
    return None


def _filter_issues_in_window(
    issues: list[dict],
    window_days: int,
    *,
    now: Optional[datetime] = None,
) -> tuple[list[dict], int, bool]:
    """Returns (issues_in_window, effective_window_days, expanded).

    Sparse-week fallback: if filtered count < SPARSE_THRESHOLD, retry with
    SPARSE_FALLBACK_DAYS and flag `expanded=True` so the writer can render a
    banner. Issues without a parseable timestamp are dropped (logged).
    """
    now = now or datetime.now(tz=timezone.utc)

    def _filter(days: int) -> list[dict]:
        cutoff = now - timedelta(days=days)
        out: list[dict] = []
        for it in issues:
            dt = _news_issue_window_dt(it)
            if dt is None:
                continue
            if dt >= cutoff:
                out.append(it)
        return out

    primary = _filter(window_days)
    if (
        len(primary) >= NEWS_AGGREGATOR_SPARSE_THRESHOLD
        or window_days >= NEWS_AGGREGATOR_SPARSE_FALLBACK_DAYS
    ):
        return primary, window_days, False
    fallback = _filter(NEWS_AGGREGATOR_SPARSE_FALLBACK_DAYS)
    if len(fallback) > len(primary):
        return fallback, NEWS_AGGREGATOR_SPARSE_FALLBACK_DAYS, True
    return primary, window_days, False


def _normalize_insight(it: Any) -> Optional[dict]:
    """Coerce a raw `key_insights[i]` (dict or string) → canonical dict."""
    if isinstance(it, dict):
        insight = (it.get("insight") or "").strip()
        evidence = (it.get("evidence") or "").strip()
        cited = it.get("cited_sources") or []
    elif it:
        insight = str(it).strip()
        evidence = ""
        cited = []
    else:
        return None
    if not insight:
        return None
    return {"insight": insight, "evidence": evidence, "cited_sources": list(cited)}


def _explode_insights(issues_in_window: list[dict]) -> list[dict]:
    """Flatten `(issue, insight)` pairs into ranking-ready records."""
    rows: list[dict] = []
    for issue in issues_in_window:
        for raw in issue.get("key_insights") or []:
            ins = _normalize_insight(raw)
            if ins is None:
                continue
            rows.append(
                {
                    "issue": issue,
                    "insight": ins["insight"],
                    "evidence": ins["evidence"],
                    "cited_sources": ins["cited_sources"]
                    or issue.get("cited_sources")
                    or [],
                }
            )
    return rows


def _classify_insight_categories(
    issue: dict,
    topic_to_cluster: dict[str, dict],
) -> list[str]:
    """Cluster slugs an insight inherits from its parent issue's topics.
    Empty list means '_misc' bucket — caller decides if to render it.
    """
    seen: set[str] = set()
    out: list[str] = []
    for t in issue.get("topics") or []:
        cl = topic_to_cluster.get(_news_slug(t))
        if cl:
            cs = cl.get("slug")
            if cs and cs not in seen:
                out.append(cs)
                seen.add(cs)
    return out


def _named_cited_count(cited: list) -> tuple[int, int]:
    """Returns (named, generic) counts. Named = type ∈ {company, product, paper}
    AND non-empty name. Generic = name present but type missing/unknown."""
    named = 0
    generic = 0
    for s in cited or []:
        if isinstance(s, dict):
            name = (s.get("name") or "").strip()
            stype = (s.get("type") or "").strip().lower()
            if not name:
                continue
            if stype in {"company", "product", "paper"}:
                named += 1
            else:
                generic += 1
        elif s:
            generic += 1
    return named, generic


def _embed_texts(
    texts: list[str],
) -> tuple[Optional[list[list[float]]], dict]:
    """Batch text-embedding-3-small in ≤2048-input chunks (API hard limit).
    Returns (vectors_or_None, usage). Failure (no API key, network) →
    (None, {}); caller falls back to deterministic ranking."""
    if not texts:
        return [], {}
    try:
        import openai  # type: ignore
    except Exception:
        return None, {}
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None, {}
    chunk = 2000  # under the 2048 hard cap
    vectors: list[list[float]] = []
    total_tokens = 0
    try:
        client = openai.OpenAI(api_key=api_key)
        for i in range(0, len(texts), chunk):
            batch = texts[i : i + chunk]
            resp = client.embeddings.create(
                model=NEWS_AGGREGATOR_EMBED_MODEL,
                input=batch,
            )
            vectors.extend(d.embedding for d in resp.data)
            total_tokens += getattr(resp.usage, "total_tokens", 0)
        usage = {"embed_input_tokens": total_tokens}
        return vectors, usage
    except Exception as exc:
        logging.warning(
            "[wiki_compiler] news aggregator embedding call failed: %r", exc
        )
        return None, {}


def _cosine(a: list[float], b: list[float]) -> float:
    import math

    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    dot = sum(a[i] * b[i] for i in range(n))
    na = math.sqrt(sum(x * x for x in a[:n]))
    nb = math.sqrt(sum(x * x for x in b[:n]))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _consensus_counts(
    rows: list[dict],
    vectors: Optional[list[list[float]]],
    sim_threshold: float,
) -> list[int]:
    """For each row, count *other* rows with cosine ≥ threshold AND from a
    different newsletter brand. Returns parallel list[int]. None vectors →
    all zeros (consensus signal disabled — fallback ranking remains usable).
    """
    n = len(rows)
    if vectors is None or len(vectors) != n:
        return [0] * n
    brands = [(r["issue"].get("newsletter_name") or "").strip().lower() for r in rows]
    out = [0] * n
    for i in range(n):
        cnt = 0
        for j in range(n):
            if i == j:
                continue
            if brands[i] and brands[j] and brands[i] == brands[j]:
                continue
            if _cosine(vectors[i], vectors[j]) >= sim_threshold:
                cnt += 1
        out[i] = cnt
    return out


def _score_insights(
    rows: list[dict],
    consensus_counts: list[int],
    *,
    now: Optional[datetime] = None,
) -> list[dict]:
    """Augment each row with `score`, `score_components` dict, `consensus_others`,
    `cluster_slugs`. Returns the same list (mutated)."""
    import math

    now = now or datetime.now(tz=timezone.utc)
    halflife = NEWS_AGGREGATOR_RECENCY_HALFLIFE_DAYS
    w = NEWS_AGGREGATOR_WEIGHTS
    for i, r in enumerate(rows):
        dt = _news_issue_window_dt(r["issue"]) or now
        age_days = max(0.0, (now - dt).total_seconds() / 86400.0)
        recency = math.exp(-age_days / halflife) if halflife > 0 else 0.0
        consensus_n = consensus_counts[i] if i < len(consensus_counts) else 0
        consensus = min(consensus_n / 3.0, 1.0)
        named, generic = _named_cited_count(r.get("cited_sources") or [])
        cited_signal = min((named + 0.5 * generic) / 3.0, 1.0)
        authority = _news_authority(r["issue"].get("newsletter_name"))
        score = (
            w["recency"] * recency
            + w["consensus"] * consensus
            + w["cited"] * cited_signal
            + w["authority"] * authority
        )
        r["score"] = score
        r["score_components"] = {
            "recency": round(recency, 4),
            "consensus": round(consensus, 4),
            "cited": round(cited_signal, 4),
            "authority": round(authority, 4),
        }
        r["consensus_others"] = consensus_n
        r["_age_days"] = round(age_days, 2)
    return rows


def _greedy_dedup(
    sorted_rows: list[dict],
    vectors: Optional[list[list[float]]],
    row_index: dict[int, int],
    sim_threshold: float,
    top_n: int,
) -> list[dict]:
    """Within an already-sorted (desc by score) list, drop near-duplicates.
    `row_index` maps id(row) → original embedding index. Output ≤ top_n."""
    out: list[dict] = []
    chosen_vecs: list[list[float]] = []
    chosen_brands: list[str] = []
    for r in sorted_rows:
        if vectors is None:
            out.append(r)
        else:
            idx = row_index.get(id(r))
            v = vectors[idx] if idx is not None and 0 <= idx < len(vectors) else None
            brand = (r["issue"].get("newsletter_name") or "").strip().lower()
            duplicate = False
            if v is not None:
                for cv, cb in zip(chosen_vecs, chosen_brands):
                    if _cosine(v, cv) >= sim_threshold and brand and cb and brand != cb:
                        duplicate = True
                        break
            if duplicate:
                continue
            out.append(r)
            if v is not None:
                chosen_vecs.append(v)
                chosen_brands.append(brand)
        if len(out) >= top_n:
            break
    return out


def _llm_merge_similar_insights(
    candidate_rows: list[dict],
) -> tuple[Optional[list[dict]], dict]:
    """Single batched claude-haiku call. Returns (merged_items_or_None, usage).
    Each merged item: {insight, evidence, cited_sources, source_indices}.
    Failure → (None, {}); caller keeps the deterministic ordering."""
    if not candidate_rows:
        return [], {}
    try:
        from exocortex.processors._common import call_tool
    except Exception:
        return None, {}
    items_for_prompt = [
        {
            "index": i,
            "insight": r["insight"],
            "evidence": (r.get("evidence") or "")[:300],
            "newsletter": r["issue"].get("newsletter_name") or "",
        }
        for i, r in enumerate(candidate_rows)
    ]
    schema = {
        "name": "merge_similar_insights",
        "description": (
            "Group near-duplicate newsletter insights into clusters. Pick the "
            "best-worded insight per cluster, list which input indices it "
            "covers, and keep singletons untouched. Do NOT invent content. "
            "Each emitted insight is split into a short bold `title` (the "
            "thesis) and an optional plain `lead` (1-2 sentence expansion)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "merged": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string",
                                "description": (
                                    "Short bold thesis, max ~80 characters, "
                                    "no trailing punctuation. The single "
                                    "idea a reader will scan. NIE kopiuj "
                                    "całego claim-a — to jest sama teza."
                                ),
                            },
                            "lead": {
                                "type": "string",
                                "description": (
                                    "Optional 1-2 sentence expansion of the "
                                    "title (kontekst, liczby, mechanizm). "
                                    "Empty string when the title alone is "
                                    "self-explanatory. NIE powtarzaj title-u."
                                ),
                            },
                            "evidence": {"type": "string"},
                            "source_indices": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "minItems": 1,
                            },
                        },
                        "required": ["title", "source_indices"],
                    },
                },
            },
            "required": ["merged"],
        },
    }
    system = (
        "Jesteś polskim redaktorem newsletterów AI. "
        "Twoim zadaniem jest grupować bullet points opisujące to samo wydarzenie/finding "
        "(np. ten sam release, papier, statystyka), zachowując singletons bez zmian, "
        "i przepisywać je naturalnym, profesjonalnym językiem polskim. "
        "NIGDY nie wymyślaj treści — łącz tylko TO, co już jest, ale możesz REFORMUŁOWAĆ "
        "dla naturalności języka. "
        "Odpowiadaj wyłącznie przez tool call `merge_similar_insights`. "
        "Próg podobieństwa: gdy dwa insighty mówią o tej samej rzeczy z innym "
        "wording-iem (cosine ≥ {NEWS_AGGREGATOR_DEDUP_SIM_THRESHOLD}), połącz je. "
        "\n\n"
        "JĘZYK — pisz pełnym, naturalnym polskim:\n"
        "  • UNIKAJ anglicismów — tłumacz: track→monitoruj/śledź, deployment→wdrożenie, "
        "roadmap→plan/mapa, post-X→po X, implementation→wdrożenie, "
        "enrollment→zapisy/rekrutacja, convergence→zbieżność, positioning→pozycjonowanie, "
        "release→premiera/wydanie, statement→oświadczenie, scope→zakres, "
        "workforce→pracownicy/kadra, restructure→restrukturyzacja\n"
        "  • Zachowuj angielskie nazwy własne (modele AI, firmy, instytucje) ALE "
        'wprowadzaj je polskim łącznikiem: "ze szpitala Mass General Brigham", '
        'NIE "post Mass General Brigham"; "po decyzji Pentagonu", NIE "post Pentagon"\n'
        '  • Używaj polskich form czasownikowych: "wymuszą" (NIE "będą wymusić"), '
        '"będą cytowane" (NIE "będą cytowane w dyskusji" gdy chodzi o "cytowane"), '
        '"zostaną zignorowane" (NIE "będą zignorowane")\n'
        "  • Nazwy techniczne pozostaw po angielsku tylko gdy są terminami branżowymi "
        'bez polskich odpowiedników (np. "fine-tuning", "tokenizer", "embedding") — '
        'ale "AI deployment" pisz jako "wdrożenie AI"\n'
        "  • PROOFREAD: po napisaniu każdego zdania sprawdź — czy native Polish speaker "
        "powiedziałby tak naturalnie? Jeśli zdanie brzmi jak machine translation z EN, "
        "przepisz.\n"
        "\n"
        "STRUKTURA WYJŚCIA — title + lead:\n"
        "Każdy zwracany insight musi być rozbity na DWA pola:\n"
        "  • `title` — krótka teza po polsku (max ~80 znaków, bez kropki na końcu). "
        "To jest sam claim, który czytelnik przeskanuje wzrokiem. "
        "NIE wpisuj tu długiego zdania z opisem.\n"
        "  • `lead` — opcjonalne 1-2 zdania rozwinięcia po polsku (kontekst, liczby, "
        "mechanizm). Jeśli title jest samowystarczalny — pozostaw `lead` "
        "jako pusty string. NIE powtarzaj treści title-u.\n"
        "\n"
        "Przykład PRAWIDŁOWEGO podziału:\n"
        '  Wejście (z newslettera): "Video generation tools dominują wśród '
        "nowości AI – dwa z trzech najtrędowszych narzędzi (Lumen5, "
        'MagicLight) fokusują się na zamianie tekstu/contentu na video."\n'
        "  Wyjście:\n"
        '    title: "Narzędzia do generowania wideo dominują wśród nowości AI"\n'
        '    lead:  "Dwa z trzech najgorętszych narzędzi (Lumen5, '
        'MagicLight) skupiają się na zamianie tekstu na wideo."\n'
        "\n"
        "Drugi przykład (spolszczony tytuł, EN źródło):\n"
        '  Wejście: "Microsoft drops OpenAI exclusivity through 2032."\n'
        "  Wyjście:\n"
        '    title: "Microsoft rezygnuje z wyłączności OpenAI do 2032 roku"\n'
        '    lead:  ""\n'
        "\n"
        "Trzeci przykład (anti-anglicism reformulation):\n"
        '  Wejście: "Track implementację AI w opiece medycznej post Mass '
        "General Brigham — czy 80% błędy będą wymusić bardziej konserwatywne "
        'deployment czy będą zignorowane."\n'
        "  Wyjście:\n"
        '    title: "Monitoruj wdrażanie AI w opiece zdrowotnej po incydencie w MGB"\n'
        '    lead:  "Czy 80% błędów wymusi bardziej konserwatywne wdrożenia, '
        'czy zostaną zignorowane?"\n'
        "\n"
        "NIGDY nie używaj myślnika ` – ` / ` — ` w title-u jako separatora — "
        "to jest po to, żeby NIE używać heurystyki łamania na myślnikach. "
        "Title to teza, lead to rozwinięcie, oba jako osobne pola, oba po polsku."
    )
    user = json.dumps(
        {"candidates": items_for_prompt},
        ensure_ascii=False,
        sort_keys=True,
    )
    try:
        out, usage = call_tool(
            system,
            user,
            schema,
            max_tokens=1024,
            _use_case="second_brain.F8_8_newsletter_aggregator",
        )
    except Exception as exc:
        logging.warning("[wiki_compiler] news aggregator LLM merge failed: %r", exc)
        return None, {}
    merged_raw = out.get("merged") if isinstance(out, dict) else None
    if not isinstance(merged_raw, list):
        return None, usage or {}
    n = len(candidate_rows)
    merged: list[dict] = []
    for m in merged_raw:
        if not isinstance(m, dict):
            continue
        idx_list = [
            i
            for i in (m.get("source_indices") or [])
            if isinstance(i, int) and 0 <= i < n
        ]
        if not idx_list:
            continue
        # Re-derive cited_sources from source rows (LLM doesn't see them).
        cited_acc: list = []
        for i in idx_list:
            cited_acc.extend(candidate_rows[i].get("cited_sources") or [])
        # Dedup cited by (name, type) tuple.
        seen_keys: set[tuple] = set()
        cited_dedup: list = []
        for c in cited_acc:
            if isinstance(c, dict):
                key = (
                    (c.get("name") or "").strip().lower(),
                    (c.get("type") or "").strip().lower(),
                )
            else:
                key = (str(c).strip().lower(), "")
            if key[0] and key not in seen_keys:
                seen_keys.add(key)
                cited_dedup.append(c)
        # F-newsletter-redesign 2026-05-04: LLM emits title+lead pair.
        # Backward-compat fallback: if LLM ignores schema and emits old
        # `insight` field, treat it as title with empty lead.
        primary_row = candidate_rows[idx_list[0]]
        title = (
            m.get("title") or m.get("insight") or primary_row.get("insight") or ""
        ).strip()
        lead = (m.get("lead") or "").strip()
        # `insight` retained for legacy consumers (high-confidence cross-cat
        # dedup keys, frontmatter export). Renderer prefers title+lead.
        legacy_insight = title if not lead else f"{title} – {lead}"
        merged.append(
            {
                "title": title,
                "lead": lead,
                "insight": legacy_insight,
                "evidence": (
                    m.get("evidence") or primary_row.get("evidence") or ""
                ).strip(),
                "cited_sources": cited_dedup,
                "source_indices": idx_list,
            }
        )
    return merged, usage or {}


def _select_per_category(
    rows_for_category: list[dict],
    vectors: Optional[list[list[float]]],
    row_index: dict[int, int],
    *,
    max_n: int,
    min_n: int,
    enable_llm_merge: bool,
    cost_remaining_usd: float,
) -> tuple[list[dict], float, bool]:
    """Returns (selected_merged_items, cost_used_usd, llm_called)."""
    if not rows_for_category:
        return [], 0.0, False
    sorted_rows = sorted(rows_for_category, key=lambda r: r["score"], reverse=True)
    deduped = _greedy_dedup(
        sorted_rows,
        vectors,
        row_index,
        sim_threshold=NEWS_AGGREGATOR_DEDUP_SIM_THRESHOLD,
        top_n=max_n,
    )
    target_n = max_n if len(rows_for_category) >= 8 else min_n
    deduped = deduped[:target_n]
    if not enable_llm_merge or cost_remaining_usd <= 0:
        # Wrap rows as merged items with single source. No LLM was called,
        # so no title/lead split is available — render whole insight as
        # title (renderer handles `lead == ''` correctly).
        return (
            [
                {
                    "title": r["insight"],
                    "lead": "",
                    "insight": r["insight"],
                    "evidence": r.get("evidence") or "",
                    "cited_sources": r.get("cited_sources") or [],
                    "sources": [r["issue"]],
                    "extras": [],
                    "best_row": r,
                }
                for r in deduped
            ],
            0.0,
            False,
        )
    # LLM merge — only when ≥2 candidates (singleton needs no merge).
    if len(deduped) < 2:
        return (
            [
                {
                    "title": r["insight"],
                    "lead": "",
                    "insight": r["insight"],
                    "evidence": r.get("evidence") or "",
                    "cited_sources": r.get("cited_sources") or [],
                    "sources": [r["issue"]],
                    "extras": [],
                    "best_row": r,
                }
                for r in deduped
            ],
            0.0,
            False,
        )
    merged, usage = _llm_merge_similar_insights(deduped)
    cost = 0.0
    if usage:
        try:
            from exocortex.processors._common import estimate_cost_usd

            cost = estimate_cost_usd(usage)
        except Exception:
            cost = 0.0
    if not merged:
        return (
            [
                {
                    "title": r["insight"],
                    "lead": "",
                    "insight": r["insight"],
                    "evidence": r.get("evidence") or "",
                    "cited_sources": r.get("cited_sources") or [],
                    "sources": [r["issue"]],
                    "extras": [],
                    "best_row": r,
                }
                for r in deduped
            ],
            cost,
            True,
        )
    out: list[dict] = []
    for m in merged[:target_n]:
        idxs = m["source_indices"]
        primary = deduped[idxs[0]]
        extras = [deduped[i]["issue"] for i in idxs[1:]]
        out.append(
            {
                "title": m["title"],
                "lead": m["lead"],
                "insight": m["insight"],
                "evidence": m["evidence"],
                "cited_sources": m["cited_sources"],
                "sources": [primary["issue"]] + extras,
                "extras": extras,
                "best_row": primary,
            }
        )
    return out, cost, True


def _newly_cited_sources(
    rows_in_window: list[dict],
    all_rows: list[dict],
    top_n: int,
) -> list[dict]:
    """First-appearance-this-week named entities (vs full corpus baseline).
    Returns list of {name, type, count, sample_issue}."""
    baseline_names: set[str] = set()
    for r in all_rows:
        for s in r.get("cited_sources") or []:
            if isinstance(s, dict):
                name = (s.get("name") or "").strip().lower()
                if name:
                    baseline_names.add(name)
    seen_in_window: dict[str, dict] = {}
    for r in rows_in_window:
        for s in r.get("cited_sources") or []:
            if not isinstance(s, dict):
                continue
            name = (s.get("name") or "").strip()
            if not name:
                continue
            key = name.lower()
            entry = seen_in_window.setdefault(
                key,
                {
                    "name": name,
                    "type": (s.get("type") or "unknown").strip(),
                    "count": 0,
                    "sample_issue": r["issue"],
                },
            )
            entry["count"] += 1
    # New = appears in window but NOT in baseline. With our dataset
    # `all_rows == rows_in_window + others`, but the contract still holds:
    # baseline includes window, so "new" relative to ALL is overly strict.
    # We instead emit names that appeared first inside the window — proxy.
    # For F8.8.x.A this is fine; future enhancement = explicit baseline cut.
    out = sorted(
        seen_in_window.values(),
        key=lambda e: (-e["count"], e["name"].lower()),
    )
    # Keep all (proxy) but cap.
    return out[:top_n]


def _high_confidence_claims(
    merged_per_category: dict[str, list[dict]],
) -> list[dict]:
    """Cross-category list of insights cited by ≥2 different newsletters
    (after merge). Sorted by `len(sources)` desc, then score."""
    flat: list[dict] = []
    for cat_slug, items in merged_per_category.items():
        for m in items:
            unique_brands = {
                (issue.get("newsletter_name") or "").strip().lower()
                for issue in m["sources"]
            }
            unique_brands.discard("")
            if len(unique_brands) >= 2:
                flat.append(
                    {
                        "title": m.get("title") or m.get("insight") or "",
                        "lead": m.get("lead") or "",
                        "insight": m["insight"],
                        "evidence": m.get("evidence") or "",
                        "cited_sources": m.get("cited_sources") or [],
                        "sources": m["sources"],
                        "category_slug": cat_slug,
                        "score": m.get("best_row", {}).get("score", 0.0),
                    }
                )
    flat.sort(key=lambda x: (-len(x["sources"]), -x["score"]))
    return flat


def _compute_news_brief(
    issues: list[dict],
    clusters_by_slug: dict[str, dict],
    *,
    window_days: int = NEWS_AGGREGATOR_WINDOW_DAYS,
    enable_llm: bool = True,
) -> dict:
    """Aggregate per-category top insights for `wiki/news/start.md`.

    Returns a dict consumed by `_render_news_start_body` + frontmatter.
    Stays cheap: pure deterministic + 1 embedding batch + ≤5 claude-haiku
    merge calls. Cost-stop guard aborts further LLM merges once budget hits.
    """
    issues_in_window, effective_days, expanded = _filter_issues_in_window(
        issues,
        window_days,
    )
    topic_to_cluster: dict[str, dict] = {}
    for cs, cl in (clusters_by_slug or {}).items():
        for t in cl.get("topics") or []:
            topic_to_cluster[_news_slug(t)] = cl
    rows = _explode_insights(issues_in_window)
    embed_texts = [(r["insight"] + " " + (r.get("evidence") or ""))[:400] for r in rows]
    vectors, embed_usage = (
        _embed_texts(embed_texts) if (enable_llm and rows) else (None, {})
    )
    consensus_counts = _consensus_counts(
        rows,
        vectors,
        NEWS_AGGREGATOR_CONSENSUS_SIM_THRESHOLD,
    )
    _score_insights(rows, consensus_counts)
    row_index = {id(r): i for i, r in enumerate(rows)}
    # Cross-category single-assignment: when a row matches multiple clusters
    # (issue has topics across different clusters), pin it to its strongest
    # cluster (the one with the most matching topics; ties → first match in
    # cluster_slugs order). Without this, the same insight appears in every
    # matching category and dominates start.md rendering.
    rows_per_category: dict[str, list[dict]] = {}
    cluster_topic_counts: dict[str, dict[str, int]] = {}
    for cs, cl in (clusters_by_slug or {}).items():
        cluster_topic_counts[cs] = {
            _news_slug(t): 1 for t in (cl.get("topics") or []) if _news_slug(t)
        }
    for r in rows:
        cluster_slugs = _classify_insight_categories(r["issue"], topic_to_cluster)
        if not cluster_slugs:
            rows_per_category.setdefault("_misc", []).append(r)
            continue
        # Score each candidate cluster by # of matching issue topics.
        issue_topic_slugs = [
            _news_slug(t) for t in (r["issue"].get("topics") or []) if _news_slug(t)
        ]
        best = cluster_slugs[0]
        best_score = -1
        for cs in cluster_slugs:
            score = sum(
                1 for ts in issue_topic_slugs if ts in cluster_topic_counts.get(cs, {})
            )
            if score > best_score:
                best_score = score
                best = cs
        rows_per_category.setdefault(best, []).append(r)
    category_counts = sorted(
        ((cs, len(rs)) for cs, rs in rows_per_category.items() if cs != "_misc"),
        key=lambda x: (-x[1], x[0]),
    )
    top_categories = [cs for cs, _ in category_counts[:NEWS_AGGREGATOR_TOP_CATEGORIES]]
    cost_remaining = NEWS_AGGREGATOR_COST_STOP_USD
    cost_total = 0.0
    llm_calls = 0
    merged_per_category: dict[str, list[dict]] = {}
    # Cross-category insight-text dedup: once an insight is rendered in
    # category A, drop it from B/C/D even if it had a sibling row there.
    # Keyed by lowercased+whitespace-collapsed insight prefix.
    seen_globally: set[str] = set()
    for cs in top_categories:
        items, cost, called = _select_per_category(
            rows_per_category.get(cs, []),
            vectors,
            row_index,
            max_n=NEWS_AGGREGATOR_INSIGHTS_PER_CATEGORY_MAX,
            min_n=NEWS_AGGREGATOR_INSIGHTS_PER_CATEGORY_MIN,
            enable_llm_merge=enable_llm and cost_remaining > 0,
            cost_remaining_usd=cost_remaining,
        )
        cost_total += cost
        cost_remaining = max(0.0, NEWS_AGGREGATOR_COST_STOP_USD - cost_total)
        if called:
            llm_calls += 1
        deduped: list[dict] = []
        for m in items:
            key = " ".join((m.get("insight") or "").lower().split())[:120]
            if not key or key in seen_globally:
                continue
            seen_globally.add(key)
            deduped.append(m)
        merged_per_category[cs] = deduped
    # _misc summary count only — not rendered as section by default.
    misc_rows = rows_per_category.get("_misc") or []
    other_categories = [
        (cs, n) for cs, n in category_counts[NEWS_AGGREGATOR_TOP_CATEGORIES:]
    ]
    high_confidence = _high_confidence_claims(merged_per_category)
    new_cited = _newly_cited_sources(rows, rows, NEWS_AGGREGATOR_NEW_CITED_TOP)

    issue_count = len({i.get("thought_id") for i in issues_in_window})
    insight_count = len(rows)
    cited_total = sum(len(r.get("cited_sources") or []) for r in rows)

    return {
        "window_days": effective_days,
        "requested_window_days": window_days,
        "expanded": expanded,
        "issue_count": issue_count,
        "insight_count": insight_count,
        "cited_source_count": cited_total,
        "top_categories": top_categories,
        "other_categories": other_categories,
        "merged_per_category": merged_per_category,
        "high_confidence": high_confidence,
        "new_cited_sources": new_cited,
        "misc_count": len({id(r["issue"]) for r in misc_rows}),
        "issues_in_window": issues_in_window,
        "rows": rows,
        "cost_total_usd": round(cost_total, 4),
        "llm_calls": llm_calls,
        "embed_usage": embed_usage,
        "clusters_by_slug": clusters_by_slug or {},
    }


def _render_news_start_body(brief: dict) -> str:
    """Render `wiki/news/start.md` body — flat chronological stream, newest first."""
    lines: list[str] = []
    n_issues = brief["issue_count"]
    n_insights = brief["insight_count"]
    n_cited = brief["cited_source_count"]
    days = brief["window_days"]
    requested = brief["requested_window_days"]
    expanded = brief["expanded"]
    brand_count = len(
        {
            (i.get("newsletter_name") or "").strip().lower()
            for i in brief["issues_in_window"]
            if i.get("newsletter_name")
        }
    )

    lines.append(f"# 📰 Newsletter Inbox — last {days} days")
    lines.append("")
    last_refresh = datetime.now(ZoneInfo("Europe/Warsaw")).strftime("%Y-%m-%d %H:%M %Z")
    summary = (
        f"> **last refresh {last_refresh}** · "
        f"**{n_issues} issues** · **{n_insights} insights** · "
        f"**{n_cited} cited sources** · {brand_count} newsletter brands"
    )
    lines.append(summary)
    lines.append(
        "> _Auto-generated. See [[_moc|news MOC]] · "
        "[[by-source/_moc|by source]] · [[by-category|all categories]]._"
    )
    lines.append("")
    if expanded:
        lines.append(
            f"> ⚠️ Showing last {days} days (sparse {requested}-day window — "
            f"fewer than {NEWS_AGGREGATOR_SPARSE_THRESHOLD} issues)."
        )
        lines.append("")

    # F8.8.x.A — per-category insight sections (consumed by _home news_pulse).
    # Heading format: `{emoji} {label} — N issues, M insights this week`
    # with `- **{insight}**` bullets. _home_fetch_news_brief_top_claims
    # parses these sections to populate the home dashboard pulse widget.
    merged = brief.get("merged_per_category") or {}
    clusters = brief.get("clusters_by_slug") or {}
    top_cats = brief.get("top_categories") or []
    if merged and top_cats:
        for cs in top_cats:
            items = merged.get(cs) or []
            if not items:
                continue
            cluster_meta = clusters.get(cs) or {}
            label = cluster_meta.get("label") or cs
            emoji = cluster_meta.get("emoji") or ""
            heading = f"{emoji} {label}".strip() if emoji else label
            issue_ids: set[str] = set()
            for m in items:
                for src in m.get("sources") or []:
                    tid = src.get("thought_id")
                    if tid:
                        issue_ids.add(str(tid))
            issue_n = len(issue_ids)
            insight_n = len(items)
            lines.append(
                f"## {heading} — {issue_n} issues, {insight_n} insights this week"
            )
            lines.append("")
            for item in items[:NEWS_AGGREGATOR_INSIGHTS_PER_CATEGORY_MAX]:
                insight_text = (item.get("insight") or "").strip()
                if insight_text:
                    lines.append(f"- **{insight_text}**")
            lines.append("")

    if not brief["issues_in_window"]:
        lines.append(
            f"No newsletter activity in last {days} days. See [[_moc|all-time MOC]]."
        )
        lines.append("")
    else:
        sorted_issues = sorted(
            brief["issues_in_window"],
            key=lambda i: (
                _news_issue_window_dt(i) or datetime.min,
                i.get("title", ""),
            ),
            reverse=True,
        )
        for issue in sorted_issues:
            title = (issue.get("title") or "untitled").strip()
            source = (issue.get("newsletter_name") or "unknown").strip()
            link = _news_issue_wikilink(issue)
            dt = _news_issue_window_dt(issue)
            date_str = dt.strftime("%Y-%m-%d") if dt else ""

            lines.append(f"## {title}")
            lines.append("")
            lines.append(f"*{source}* · {link} · `{date_str}`")
            lines.append("")

            insights = issue.get("key_insights") or []
            for ins in insights[:3]:
                ins_text = (ins.get("insight") or str(ins)).strip()
                if not ins_text:
                    continue
                lines.append(f"> {ins_text}")
            lines.append("")

            cited = issue.get("cited_sources") or []
            if cited:
                names = [c.get("name", "") for c in cited if c.get("name")]
                if names:
                    lines.append(f"*{', '.join(names[:5])}*")
                    lines.append("")

            lines.append("---")
            lines.append("")

    if brief["high_confidence"]:
        lines.append("## 🔥 High-confidence claims (≥2 newsletters)")
        lines.append("")
        lines.append(
            "> Insights where 2+ different newsletters reported a semantically-similar "
            "finding — strong signal."
        )
        lines.append("")
        for hc in brief["high_confidence"][:8]:
            claim_title = hc.get("title") or hc.get("insight") or hc.get("claim") or ""
            lines.append(f"- **{claim_title}**")
            source_names = []
            for s in hc.get("sources") or []:
                if isinstance(s, dict):
                    name = s.get("newsletter_name") or "?"
                    source_names.append(name)
                elif isinstance(s, str):
                    source_names.append(s)
            if source_names:
                lines.append(f"  {' · '.join(source_names[:3])}")
            lines.append("")

    if brief["new_cited_sources"]:
        lines.append("## 💡 Newly cited sources")
        lines.append("")
        names = []
        for s in (brief["new_cited_sources"] or [])[:10]:
            if isinstance(s, dict):
                names.append(s.get("name", str(s)))
            else:
                names.append(str(s))
        if names:
            lines.append(f"{', '.join(names)}")
        lines.append("")

    # Dataview block for historical drill-down
    lines.append("## All issues in window (Dataview)")
    lines.append("")
    lines.append("```dataview")
    lines.append(
        'TABLE date AS "Date", newsletter_name AS "Source", length(file.outlinks) AS "Refs"'
    )
    lines.append('FROM "wiki/news/src"')
    lines.append('WHERE type = "newsletter-issue"')
    lines.append("SORT date DESC")
    lines.append("LIMIT 50")
    lines.append("```")
    return "\n".join(lines) + "\n"


def _format_cited_inline(cited: list, max_n: int = 3) -> str:
    """Pretty-print top N named cited entities for an inline insight bullet."""
    out: list[str] = []
    for s in cited or []:
        if isinstance(s, dict):
            name = (s.get("name") or "").strip()
            if name:
                out.append(name)
        elif s:
            out.append(str(s))
        if len(out) >= max_n:
            break
    return ", ".join(out)


def _news_issue_wikilink(issue: dict) -> str:
    """`[[<slug>|<newsletter> YYYY-MM-DD]]` rendering."""
    slug = _news_issue_slug(issue)
    nl = issue.get("newsletter_name") or "?"
    dt = _news_issue_window_dt(issue)
    date = dt.strftime("%Y-%m-%d") if dt else ""
    label = f"{nl} {date}".strip()
    return f"[[{slug}|{label}]]"


def _write_news_start_page(news_root: Path, brief: dict) -> bool:
    """Write `wiki/news/start.md` (idempotent via `_input_hash`).

    Brief dict comes from `_compute_news_brief`. Hash payload covers the
    window + every issue inside it + cluster slugs + ranking weights + LLM
    model, so:
      - new issue inside window → hash flips,
      - issue ages out → tuple drops → hash flips,
      - cluster taxonomy change → hash flips,
      - in-window-only body change → hash flips (issue body_hash differs),
      - out-of-window edits → no-op (correct: window-bounded view).
    """
    path = news_root / "start.md"
    issues_in_window = brief["issues_in_window"]

    issue_tuples = sorted(
        [
            (
                it.get("thought_id"),
                hashlib.sha256(
                    (it.get("body") or "").encode("utf-8"),
                ).hexdigest()[:16]
                if it.get("body")
                else "",
                (
                    _news_issue_window_dt(it).isoformat()
                    if _news_issue_window_dt(it)
                    else ""
                ),
            )
            for it in issues_in_window
        ]
    )
    payload = json.dumps(
        [
            _NEWS_SLUG_FORMAT_VERSION,
            # F-newsletter-redesign 2026-05-04 — Layout B + LLM-driven
            # title+lead structure (tool schema bump, NOT a heuristic).
            # Bumps hash so first compile rewrites `start.md` once.
            "news-start-format-v4-title-lead",
            brief["window_days"],
            issue_tuples,
            sorted((brief["clusters_by_slug"] or {}).keys()),
            NEWS_AGGREGATOR_WEIGHTS,
            NEWS_AGGREGATOR_LLM_MODEL,
            NEWS_AGGREGATOR_PROMPT_VERSION,
        ],
        sort_keys=True,
        default=str,
        ensure_ascii=False,
    ).encode("utf-8")
    input_hash = hashlib.sha256(payload).hexdigest()[:16]

    fm: dict[str, Any] = {
        "type": "newsletter-feed-aggregator",
        "window_days": brief["window_days"],
        "requested_window_days": brief["requested_window_days"],
        "expanded_window": brief["expanded"],
        "last_window_days": brief["window_days"],
        "last_refresh": datetime.now(timezone.utc).isoformat(),
        "total_issues_window": brief["issue_count"],
        "insight_count": brief["insight_count"],
        "cited_source_count": brief["cited_source_count"],
        "top_categories": list(brief["top_categories"]),
        "aggregator_cost_usd": brief["cost_total_usd"],
        "aggregator_llm_calls": brief["llm_calls"],
        "_input_hash": input_hash,
    }
    body = _render_news_start_body(brief)
    return _write_with_frontmatter(str(path), fm, body, source_ids=[])


def _compile_news_aggregator(
    news_root: Path,
    issues: list[dict],
    clusters_by_slug: Optional[dict[str, dict]],
    *,
    window_days: int = NEWS_AGGREGATOR_WINDOW_DAYS,
) -> bool:
    """F8.8.x.A entry point. Returns True iff start.md was rewritten."""
    if (
        window_days < NEWS_AGGREGATOR_WINDOW_DAYS_MIN
        or window_days > NEWS_AGGREGATOR_WINDOW_DAYS_MAX
    ):
        raise ValueError(
            f"window_days must be in [{NEWS_AGGREGATOR_WINDOW_DAYS_MIN},"
            f"{NEWS_AGGREGATOR_WINDOW_DAYS_MAX}], got {window_days!r}"
        )
    brief = _compute_news_brief(
        issues,
        clusters_by_slug or {},
        window_days=window_days,
        enable_llm=True,
    )
    written = _write_news_start_page(news_root, brief)
    print(
        f"[wiki_compiler] news/start.md: {'wrote' if written else 'unchanged'} — "
        f"{brief['issue_count']} issues in {brief['window_days']}d window, "
        f"{brief['insight_count']} insights, {brief['llm_calls']} LLM merges, "
        f"cost ${brief['cost_total_usd']:.4f}"
    )
    return written


def _write_news_moc(
    news_root: Path,
    issues: list[dict],
    sources: dict,
    topics: dict,
    categories: Optional[dict[str, list[dict]]] = None,
    clusters_by_slug: Optional[dict[str, dict]] = None,
) -> bool:
    """Top-level wiki/news/_moc.md z 4 Dataview presets + F8.8.x.H2 Categories."""
    path = news_root / "_moc.md"
    categories = categories or {}
    clusters_by_slug = clusters_by_slug or {}

    fm: dict[str, Any] = {
        "type": "newsletter-moc",
        "issue_count": len(issues),
        "source_count": len(sources),
        "topic_count": len(topics),
        "category_count": len(categories),
    }
    payload = json.dumps(
        [
            len(issues),
            len(sources),
            len(topics),
            sorted((slug, len(items)) for slug, items in categories.items()),
            sorted(clusters_by_slug.keys()),
        ],
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    fm["_input_hash"] = hashlib.sha256(payload).hexdigest()[:16]

    lines = [
        "# Newsletter MOC",
        "",
        f"> {len(issues)} newsletter issues from {len(sources)} sources, "
        f"{len(topics)} topics, {len(categories)} categories. "
        f"Updated daily by `compile_news_module`.",
        "",
    ]

    # F8.8.x.H2: Categories block — ordered by yaml `clusters` list, then
    # `_misc` last. Closed slugs (Q1 lock) so we render the full cluster
    # list even when a category has 0 issues for transparency.
    if categories or clusters_by_slug:
        lines.append("## Categories")
        for cluster_slug, cluster_meta in clusters_by_slug.items():
            cat_issues = categories.get(cluster_slug) or []
            label = cluster_meta.get("label") or cluster_slug
            emoji = cluster_meta.get("emoji") or ""
            heading = f"{emoji} {label}".strip() if emoji else label
            topic_count = len(cluster_meta.get("topics") or [])
            lines.append(
                f"- [[by-category/{cluster_slug}|{heading}]] "
                f"({len(cat_issues)} issue{'s' if len(cat_issues) != 1 else ''}, "
                f"{topic_count} topics)"
            )
        if "_misc" in categories:
            misc_count = len(categories["_misc"])
            lines.append(
                f"- [[by-category/_misc|🗂️ Niesklasyfikowane]] "
                f"({misc_count} issue{'s' if misc_count != 1 else ''})"
            )
        lines.append("")

    lines += [
        f"## Recent issues (last {NEWS_AGGREGATOR_LATEST_LIMIT} days)",
        "```dataview",
        'TABLE newsletter_name AS "source", issue_date, length(topics) AS "topics"',
        'FROM "wiki/news"',
        f'WHERE type = "newsletter" AND date(issue_date) >= date(today) - dur({NEWS_AGGREGATOR_LATEST_LIMIT} days)',
        "SORT issue_date DESC",
        "LIMIT 30",
        "```",
        "",
        f"## Top topics (≥{NEWS_TOPIC_MIN_MENTIONS} newsletter mentions)",
        "```dataview",
        "TABLE issue_count",
        'FROM "wiki/news/by-topic"',
        'WHERE type = "newsletter-topic-moc"',
        "SORT issue_count DESC",
        "LIMIT 15",
        "```",
        "",
        "## Newsletter sources tracker",
        "```dataview",
        'TABLE issue_count AS "issues"',
        'FROM "wiki/news/by-source"',
        'WHERE type = "newsletter-source-moc"',
        "SORT issue_count DESC",
        "```",
        "",
        "## All issues (table)",
        "```dataview",
        'TABLE newsletter_name AS "source", issue_date, cited_sources_count AS "cited"',
        'FROM "wiki/news"',
        'WHERE type = "newsletter"',
        "SORT issue_date DESC",
        "```",
        "",
        "## All topics (Dataview, including singletons)",
        "```dataview",
        'TABLE length(rows) AS "mentions"',
        'FROM "wiki/news"',
        'WHERE type = "newsletter"',
        "FLATTEN topics AS t",
        "GROUP BY t",
        "SORT length(rows) DESC",
        "```",
    ]
    return _write_with_frontmatter(
        str(path), fm, "\n".join(lines) + "\n", source_ids=[]
    )


# ────────────────────────────────────────────────────────────────────────────
# Entry point
# ────────────────────────────────────────────────────────────────────────────


def compile_news_module(tenant_id: str, since: Optional[datetime]) -> None:
    """F8.8.5 — Compile newsletter synthesis pages in wiki/news/."""
    from exocortex.wiki.core.io import _get_wiki_root

    wiki_root = _get_wiki_root()
    news_root = wiki_root / "news"
    news_root.mkdir(parents=True, exist_ok=True)
    by_source_dir = news_root / "by-source"
    by_topic_dir = news_root / "by-topic"
    by_source_dir.mkdir(parents=True, exist_ok=True)
    by_topic_dir.mkdir(parents=True, exist_ok=True)

    issues = _load_news_issues(tenant_id, since)
    print(f"[wiki_compiler] news: loaded {len(issues)} newsletter issues")

    # F8.8.x.H2 — load topic clusters once per compile.
    topic_to_cluster, clusters_by_slug = _load_topic_clusters()

    counts = {
        "issues_written": 0,
        "issues_skipped": 0,
        "sources_written": 0,
        "topics_written": 0,
        "categories_written": 0,
        "aggregator_written": 0,
    }
    for issue in issues:
        if _write_news_issue_page(news_root, issue, topic_to_cluster):
            counts["issues_written"] += 1
        else:
            counts["issues_skipped"] += 1

    sources = _group_news_by_source(issues)
    for slug, brand_issues in sources.items():
        if _write_news_by_source_page(by_source_dir, slug, brand_issues):
            counts["sources_written"] += 1

    topics = _group_news_by_topic(issues)
    for slug, topic_issues in topics.items():
        if _write_news_by_topic_page(by_topic_dir, slug, topic_issues, tenant_id):
            counts["topics_written"] += 1

    # F8.8.x.H2 — by-category writers. Threshold (≥3) re-used from
    # _group_news_by_topic so member-topic wikilinks resolve only when the
    # by-topic/ page was actually written.
    categories: dict[str, list[dict]] = {}
    if clusters_by_slug:
        by_category_dir = news_root / "by-category"
        by_category_dir.mkdir(parents=True, exist_ok=True)
        categories = _group_news_by_category(issues, topic_to_cluster)
        # mention_count snapshot from raw all-topic histogram (NOT topics
        # dict, which already drops singletons — we still want to label
        # below-threshold member topics with their real count).
        mention_counts: dict[str, int] = {}
        for it in issues:
            for t in it.get("topics") or []:
                slug = _news_slug(t)
                if slug:
                    mention_counts[slug] = mention_counts.get(slug, 0) + 1

        # F8.8.x.B — load active news_cluster syntheses once for all by-category
        # pages. {cluster_slug: synthesis_row}. Empty when synthesizer hasn't
        # run yet (graceful — by-category pages still render without banner).
        all_syntheses = _load_active_syntheses(tenant_id)
        news_syntheses: dict[str, dict] = {
            pkey: syn
            for (ptype, pkey), syn in all_syntheses.items()
            if ptype == "news_cluster"
        }

        for cluster_slug, cat_issues in categories.items():
            cluster_meta = clusters_by_slug.get(cluster_slug)
            if _write_news_by_category_page(
                by_category_dir,
                cluster_slug,
                cat_issues,
                cluster_meta,
                mention_counts,
                synthesis=news_syntheses.get(cluster_slug),
            ):
                counts["categories_written"] += 1

    _write_news_moc(
        news_root,
        issues,
        sources,
        topics,
        categories=categories,
        clusters_by_slug=clusters_by_slug,
    )

    # F8.8.x.A — final pass: morning-brief aggregator at wiki/news/start.md.
    # Light LLM tier (~$0.05/run) for cross-newsletter dedup. Idempotent via
    # `_input_hash` over (window_days, sorted issue tuples, cluster keys,
    # weights, model). Non-fatal: aggregator failure is logged + swallowed
    # so atomic/source/topic/category writers stay green.
    import exocortex.wiki.domains.news as _news_mod

    window_days = (
        _news_mod._news_aggregator_window_override or NEWS_AGGREGATOR_WINDOW_DAYS
    )
    try:
        if _compile_news_aggregator(
            news_root,
            issues,
            clusters_by_slug,
            window_days=window_days,
        ):
            counts["aggregator_written"] = 1
    except Exception as exc:
        logging.warning("[wiki_compiler] news aggregator failed: %r", exc)

    print(
        f"[wiki_compiler] news: wrote {counts['issues_written']} issues "
        f"(+ {counts['issues_skipped']} unchanged), "
        f"{counts['sources_written']} sources, "
        f"{counts['topics_written']} topics, "
        f"{counts['categories_written']} categories, "
        f"{counts['aggregator_written']} aggregator, _moc.md"
    )


# ────────────────────────────────────────────────────────────────────────────
# Domain registry
# ────────────────────────────────────────────────────────────────────────────


class NewsDomain(_LegacyDomainCompiler):
    _legacy_fn_name = "compile_news_module"

    @property
    def name(self) -> str:
        return "news"


def setup(registry: Any) -> None:
    registry.register_compile_domain(NewsDomain())
