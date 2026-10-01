# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Clippings-based domain compilers (3d, cook, priv, papers, tc, sb).

Provides compile_work_clippings (used inside WorkDomain pipeline) plus
six independent domain compilers registered in setup().
tc and sb raise NotImplementedError — they are registered so the registry
knows about them but compile() raises as expected.
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from exocortex.wiki.domains.base import _LegacyDomainCompiler

# ── Core helpers ──────────────────────────────────────────────────────────────
# ── Orphan pruning ───────────────────────────────────────────────────────────
#
# The compiler names each page after the slug of its thought's title, so any
# title change orphans the previous file. Nothing ever deleted those: every
# domain inherited a `prune_orphans` stub and runner.compile_all never called
# it. That went unnoticed until a title-loss incident plus a slug fix left 95
# stale files to sweep by hand (2026-08-03).
#
# Pruning is driven by the database rather than by "what this run happened to
# write", so it behaves the same under an incremental (`--since`) compile as
# under a full one.
# Decision logic lives in wiki/util/prune.py — shared with the work domain,
# and worth testing on its own since it is the only code that deletes pages.
from exocortex.wiki.util.prune import (
    _prune_is_plausible,
    _select_orphans,
)


def _clipping_url(md: dict) -> str | None:
    """Prefer a processor-supplied 'source_url' (the content's real origin,
    e.g. an Instagram link for a recipe) over the generic 'uri'. Never
    surface a file:// URI as the page's `url` — that's vault_watcher's
    internal fallback for a source with no real url/uri/source field, not
    something meant for display."""
    url = md.get("source_url") or md.get("uri")
    if isinstance(url, str) and url.startswith("file://"):
        return None
    return url


def compile_work_clippings(tenant_id: str, since: datetime | None) -> None:
    """F6.4.1 — atomic per source in wiki/work/clippings/{slug}.md
    (articles/github/linkedin/twitter that came from F6 capture)."""
    _compile_clippings_module(
        tenant_id,
        since,
        domain="work",
        clipping_thought_types=(
            "article",
            "github_issue_digest",
            "linkedin_post",
            "twitter_thread",
            "youtube_summary",
        ),
        specialized_thought_types={},
        clipping_subdir="clippings",
    )


def _compile_clippings_module(
    tenant_id: str,
    since: datetime | None,
    *,
    domain: str,
    clipping_thought_types: tuple[str, ...],
    specialized_thought_types: dict[str, str],
    clipping_subdir: str = "clippings",
) -> None:
    """F6.4.1 — generic per-domain compile for atomic clipping pages.

    For each thought matching the thought_types in this domain:
      - clipping types → wiki/{domain}/{clipping_subdir}/{slug}.md
      - specialized types (e.g. recipe → recipes/, 3d_model → models/) →
        wiki/{domain}/{specialized_subdir}/{slug}.md

    Idempotent via input_hash check (re-uses _is_unchanged from F4).
    """
    from exocortex.db import query  # lazy: avoid settings at import time
    from exocortex.wiki.core.io import _get_wiki_root, _safe

    wiki_root = _get_wiki_root()
    domain_root = wiki_root / domain
    domain_root.mkdir(parents=True, exist_ok=True)

    if clipping_thought_types:
        (domain_root / clipping_subdir).mkdir(parents=True, exist_ok=True)
    for subdir in specialized_thought_types.values():
        (domain_root / subdir).mkdir(parents=True, exist_ok=True)

    types_in_scope = list(clipping_thought_types) + list(
        specialized_thought_types.keys()
    )
    if not types_in_scope:
        return

    sql = (
        "SELECT id::text, body, thought_type, metadata, "
        "extracted_tags, source_id::text, created_at "
        "FROM thoughts "
        "WHERE tenant_id = %s "
        "AND superseded_by IS NULL "
        "AND thought_type = ANY(%s::text[]) "
        "AND metadata->>'domain' = %s"
    )
    params: list[Any] = [tenant_id, types_in_scope, domain]
    if since is not None:
        sql += " AND created_at >= %s"
        params.append(since)
    sql += " ORDER BY created_at DESC"

    rows = query(sql, *params)
    if not rows:
        print(f"[wiki_compiler] no {domain} clippings to compile")
        return

    by_type: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_type[r["thought_type"]].append(r)

    n_written = 0
    for thought_type, items in by_type.items():
        subdir = specialized_thought_types.get(thought_type, clipping_subdir)
        target_dir = domain_root / subdir
        for r in items:
            n_written += _write_clipping_page(target_dir, r, domain=domain)

    _safe(_write_clippings_moc, domain_root, domain, by_type)
    print(f"[wiki_compiler] {domain}: {n_written} clippings written/updated")

    # Prune here, not in the caller: there are two compile dispatchers —
    # wiki_compiler.compile_all (plain functions; what every deployed unit
    # actually runs) and wiki.runner.compile_all (DomainCompiler registry).
    # Both converge on this function, so this is the one place that covers
    # production. A prune failure must not fail the compile — stale files
    # are untidy, a missing compile is not.
    try:
        _prune_clipping_orphans(
            tenant_id,
            domain=domain,
            clipping_thought_types=clipping_thought_types,
            specialized_thought_types=specialized_thought_types,
            clipping_subdir=clipping_subdir,
        )
    except Exception as exc:  # noqa: BLE001 — never let cleanup break a compile
        print(f"[wiki_compiler] WARN: {domain} prune_orphans failed: {exc!r}")


def _write_clipping_page(target_dir: Path, thought: dict, *, domain: str) -> int:
    """Write one atomic clipping page. Returns 1 if written, 0 if unchanged."""
    # Read run state from core._state, NOT from exocortex.wiki_compiler:
    # deployed units run `python -m exocortex.wiki_compiler`, so that module
    # is __main__ and a plain `import exocortex.wiki_compiler` here binds a
    # SECOND copy whose DRY_RUN stays False. _state is the shared one.
    from exocortex.wiki.core import _state as _wc
    from exocortex.wiki.core.io import (
        _hash_input,
        _is_unchanged,
        _partition_frontmatter,
        render_frontmatter_v2,
    )
    from exocortex.wiki.util.slugs import _safe_slug

    md = thought.get("metadata") or {}
    title = (md.get("title") or "").strip() or "(untitled)"
    slug = _safe_slug(title) or str(thought["id"])[:8]
    # Sessions reuse ai-titles heavily ("Review X security vulnerabilities"),
    # so the title-slug alone collides — append a per-thought suffix, like
    # meeting pages do. Other clipping types have distinctive titles.
    if thought["thought_type"] == "claude_session":
        slug = f"{slug}-{str(thought['id']).replace('-', '')[:8]}"

    fm = {
        "type": thought["thought_type"],
        "domain": domain,
        "title": title,
        "url": _clipping_url(md),
        "created_at": thought["created_at"].isoformat()
        if thought.get("created_at")
        else None,
        "_thought_id": str(thought["id"]),
        "_source_id": str(thought.get("source_id") or ""),
        "_compile_run_id": _wc.current_run_id,
    }
    # Type-specific frontmatter enrichment.
    if thought["thought_type"] == "recipe":
        fm.update(
            {
                k: md.get(k)
                for k in ("cuisine", "servings", "prep_time_min", "cook_time_min")
                if md.get(k) is not None
            }
        )
    elif thought["thought_type"] == "arxiv_paper":
        fm["relevance_score"] = md.get("relevance_score")
    elif thought["thought_type"] == "claude_session":
        for k in ("session_id", "redaction_verdict", "decision_count",
                  "mistake_count"):
            if md.get(k) is not None:
                fm[k] = md.get(k)
    elif thought["thought_type"] == "3d_model":
        for k in (
            "layer_height_mm",
            "infill_pct",
            "supports",
            "material",
            "print_time_min",
            "designer",
        ):
            if md.get(k) is not None:
                fm[k] = md.get(k)

    content = (thought.get("body") or "").strip() + "\n"
    fm_clean = _partition_frontmatter(fm)
    full_content = render_frontmatter_v2(fm_clean) + "\n" + content
    new_hash = _hash_input(full_content)

    file_path = target_dir / f"{slug}.md"
    if file_path.exists() and _is_unchanged(file_path, new_hash):
        return 0
    if _wc.DRY_RUN:
        _wc._pages_written.append(str(file_path))
        return 1
    tmp = file_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(full_content)
    os.replace(tmp, file_path)
    _wc._pages_written.append(str(file_path))
    return 1


def _write_clippings_moc(
    domain_root: Path, domain: str, by_type: dict[str, list[dict]]
) -> None:
    """F6.4.4 — per-domain news/clippings MOC with Dataview query views."""
    # Read run state from core._state, NOT from exocortex.wiki_compiler:
    # deployed units run `python -m exocortex.wiki_compiler`, so that module
    # is __main__ and a plain `import exocortex.wiki_compiler` here binds a
    # SECOND copy whose DRY_RUN stays False. _state is the shared one.
    from exocortex.wiki.core import _state as _wc
    from exocortex.wiki.core.io import _hash_input, _is_unchanged, render_frontmatter_v2

    moc_path = domain_root / "clippings" / "_moc.md"
    if not (domain_root / "clippings").exists():
        return

    lines = [
        f"# {domain.capitalize()} — Clippings",
        "",
        "> Discovery views for content captured via F6 acquisition (articles, "
        "github issues, linkedin posts, twitter threads, youtube summaries, "
        "arxiv papers). One file per source under `clippings/`.",
        "",
        "## Wszystkie clippings (najnowsze)",
        "",
        "```dataview",
        'TABLE WITHOUT ID file.link AS "Tytuł", type, url, created_at',
        f'FROM "{domain}/clippings"',
        "WHERE type != null",
        "SORT created_at DESC",
        "LIMIT 50",
        "```",
        "",
    ]
    for thought_type, items in sorted(by_type.items()):
        lines += [
            f"## {thought_type} ({len(items)})",
            "",
            "```dataview",
            'TABLE WITHOUT ID file.link AS "Tytuł", url, created_at',
            f'FROM "{domain}/clippings"',
            f'WHERE type = "{thought_type}"',
            "SORT created_at DESC",
            "LIMIT 25",
            "```",
            "",
        ]
    full_content = (
        render_frontmatter_v2(
            {
                "_compile_run_id": _wc.current_run_id,
                "type": "moc",
                "domain": domain,
            }
        )
        + "\n"
        + "\n".join(lines)
        + "\n"
    )
    new_hash = _hash_input(full_content)
    if moc_path.exists() and _is_unchanged(moc_path, new_hash):
        return
    if _wc.DRY_RUN:
        _wc._pages_written.append(str(moc_path))
        return
    tmp = moc_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(full_content)
    os.replace(tmp, moc_path)
    _wc._pages_written.append(str(moc_path))


def _read_thought_id(path: Path) -> str | None:
    """`_thought_id` from a page's frontmatter, or None for hand-written or
    aggregate pages (MOC, index) that carry no thought identity."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for _ in range(40):
                line = fh.readline()
                if not line:
                    break
                if line.startswith("_thought_id:"):
                    return line.split(":", 1)[1].strip().strip("'\"") or None
    except OSError:
        return None
    return None


def _prune_clipping_orphans(
    tenant_id: str,
    *,
    domain: str,
    clipping_thought_types: tuple,
    specialized_thought_types: dict,
    clipping_subdir: str = "clippings",
) -> int:
    """Delete pages superseded by a rename, or left behind by a vanished
    thought. Returns the number deleted (0 if there is nothing to do)."""
    # Read run state from core._state, NOT from exocortex.wiki_compiler:
    # deployed units run `python -m exocortex.wiki_compiler`, so that module
    # is __main__ and a plain `import exocortex.wiki_compiler` here binds a
    # SECOND copy whose DRY_RUN stays False. _state is the shared one.
    from exocortex.wiki.core import _state as _wc
    from exocortex.wiki.core.io import _get_wiki_root
    from exocortex.wiki.util.slugs import _safe_slug

    types_in_scope = list(clipping_thought_types) + list(specialized_thought_types)
    if not types_in_scope:
        return 0

    dirs: dict[str, Path] = {}
    try:
        domain_root = _get_wiki_root() / domain
    except OSError:
        # No reachable wiki root means nothing was compiled, so nothing to
        # prune. (_get_wiki_root creates the directory as a side effect and
        # can fail where the compile itself would have failed first.)
        return 0
    for t in clipping_thought_types:
        dirs[t] = domain_root / clipping_subdir
    for t, subdir in specialized_thought_types.items():
        dirs[t] = domain_root / subdir
    # Nothing compiled here yet — say so without touching the database.
    if not any(d.exists() for d in dirs.values()):
        return 0

    from exocortex.db import query

    rows = query(
        "SELECT id::text, metadata, thought_type FROM thoughts "
        "WHERE tenant_id = %s AND superseded_by IS NULL "
        "AND thought_type = ANY(%s::text[]) AND metadata->>'domain' = %s",
        tenant_id,
        types_in_scope,
        domain,
    )

    # Expected filename per thought, grouped by the directory it belongs in.
    expected_per_dir: dict[Path, dict] = defaultdict(dict)
    for r in rows:
        target = dirs.get(r["thought_type"])
        if target is None:
            continue
        title = ((r["metadata"] or {}).get("title") or "").strip() or "(untitled)"
        slug = _safe_slug(title) or str(r["id"])[:8]
        expected_per_dir[target][str(r["id"])] = f"{slug}.md"

    n_deleted = 0
    for target in {d for d in dirs.values() if d.exists()}:
        files_by_name = {}
        for f in target.glob("*.md"):
            tid = _read_thought_id(f)
            if tid:
                files_by_name[f.name] = tid
        if not files_by_name:
            continue
        orphans = _select_orphans(files_by_name, expected_per_dir.get(target, {}))
        if not orphans:
            continue
        if not _prune_is_plausible(n_delete=len(orphans), n_total=len(files_by_name)):
            print(
                f"[wiki_compiler] {domain}: REFUSED to prune {len(orphans)} of "
                f"{len(files_by_name)} pages in {target} — that looks wrong, "
                "not stale; skipping (nothing deleted)"
            )
            continue
        for name in orphans:
            if _wc.DRY_RUN:
                print(f"[wiki_compiler] {domain}: would prune {target / name}")
                n_deleted += 1
                continue
            try:
                (target / name).unlink()
                n_deleted += 1
            except OSError as exc:
                print(f"[wiki_compiler] {domain}: could not prune {name}: {exc!r}")
    if n_deleted:
        verb = "would prune" if _wc.DRY_RUN else "pruned"
        print(f"[wiki_compiler] {domain}: {verb} {n_deleted} orphaned pages")
    return n_deleted


# ── Stub domain functions ─────────────────────────────────────────────────────


# Which thought types land in which subdirectory, per domain. Compiling and
# pruning MUST read the same config — if they disagreed, pruning would judge a
# page against the wrong expected name and delete a live one.
_DOMAIN_CONFIG: dict[str, dict] = {
    "3d": {
        "clipping_thought_types": ("article", "youtube_summary"),
        "specialized_thought_types": {"3d_model": "models"},
    },
    "cook": {
        "clipping_thought_types": ("article",),
        "specialized_thought_types": {"recipe": "recipes"},
    },
    "priv": {
        "clipping_thought_types": ("article",),
        "specialized_thought_types": {},
    },
    "papers": {
        "clipping_thought_types": (),
        "specialized_thought_types": {"arxiv_paper": "papers"},
    },
    "sb": {
        "clipping_thought_types": (),
        "specialized_thought_types": {"claude_session": "sessions"},
    },
}


class _ClippingsDomain(_LegacyDomainCompiler):
    """Legacy compile wrapper plus DB-driven orphan pruning, for the domains
    whose pages are written by `_compile_clippings_module`."""

    def prune_orphans(self, ctx: Any) -> int:
        return _prune_clipping_orphans(
            ctx.tenant_id, domain=self.name, **_DOMAIN_CONFIG[self.name]
        )


def compile_3d_module(tenant_id: str, since: datetime | None) -> None:
    """Compile 3D Printing domain wiki pages."""
    _compile_clippings_module(tenant_id, since, domain="3d", **_DOMAIN_CONFIG["3d"])


def compile_tc_module(tenant_id: str, since: datetime | None) -> None:
    """Compile TalentCanvas domain wiki pages."""
    raise NotImplementedError


def compile_cook_module(tenant_id: str, since: datetime | None) -> None:
    """Compile Cookbook domain wiki pages."""
    _compile_clippings_module(tenant_id, since, domain="cook", **_DOMAIN_CONFIG["cook"])


def compile_priv_module(tenant_id: str, since: datetime | None) -> None:
    """Compile Personal domain wiki pages."""
    _compile_clippings_module(tenant_id, since, domain="priv", **_DOMAIN_CONFIG["priv"])


def compile_sb_module(tenant_id: str, since: datetime | None) -> None:
    """Compile Second Brain meta domain — currently Claude Code session distils."""
    _compile_clippings_module(tenant_id, since, domain="sb", **_DOMAIN_CONFIG["sb"])


def compile_papers_module(tenant_id: str, since: datetime | None) -> None:
    """F6.4.1 — compile papers domain (arxiv-only)."""
    _compile_clippings_module(tenant_id, since, domain="papers", **_DOMAIN_CONFIG["papers"])


# ── DomainCompiler subclasses ─────────────────────────────────────────────────


class ThreeDDomain(_ClippingsDomain):
    _legacy_fn_name = "compile_3d_module"

    @property
    def name(self) -> str:
        return "3d"


class TcDomain(_LegacyDomainCompiler):
    _legacy_fn_name = "compile_tc_module"

    @property
    def name(self) -> str:
        return "tc"


class CookDomain(_ClippingsDomain):
    _legacy_fn_name = "compile_cook_module"

    @property
    def name(self) -> str:
        return "cook"


class PrivDomain(_ClippingsDomain):
    _legacy_fn_name = "compile_priv_module"

    @property
    def name(self) -> str:
        return "priv"


class SbDomain(_ClippingsDomain):
    _legacy_fn_name = "compile_sb_module"

    @property
    def name(self) -> str:
        return "sb"


class PapersDomain(_ClippingsDomain):
    _legacy_fn_name = "compile_papers_module"

    @property
    def name(self) -> str:
        return "papers"


def setup(registry: Any) -> None:
    for domain in (
        ThreeDDomain(),
        TcDomain(),
        CookDomain(),
        PrivDomain(),
        SbDomain(),
        PapersDomain(),
    ):
        registry.register_compile_domain(domain)
