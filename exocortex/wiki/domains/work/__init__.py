# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Work domain compiler — meetings, clients, people, tags, TODO, monthly.

Extracted from wiki_compiler.py in F31.6.2 batch 4.
Entry point: compile_work_module(tenant_id, since).

F11.4 invariant: _merge_user_done_state is called in _write_meeting_pages to
preserve user-toggled [x] checkboxes. NEVER remove or bypass that call.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

from exocortex.action_items import me_owner_names, me_owner_slugs
from exocortex.classifier import classify_meeting
from exocortex.classifier import load_config as _load_projects_cfg
from exocortex.integrations import get_internal_domain
from exocortex.settings import get_settings
from exocortex.wiki.core.edges import (
    EdgesIndex,
    _load_active_syntheses,
    _load_edges_index,
)
from exocortex.wiki.core.io import (
    _get_wiki_root,
    _hash_input,
    _safe,
    _write_with_frontmatter,
)
from exocortex.wiki.core.user_state import (
    _merge_user_done_state,
)
from exocortex.wiki.domains.base import _LegacyDomainCompiler
from exocortex.wiki.domains.clippings import compile_work_clippings
from exocortex.wiki.util.classification import (
    _classify_type,
    _client_display,
    _is_internal,
    _meeting_slug,
)
from exocortex.wiki.util.coercion import _coerce_jsonb_list  # noqa: F401
from exocortex.wiki.util.dates import (
    _iso_month_bounds,
    _iso_week_bounds,
    _offset_iso,
    _strip_pl_accents,
)
from exocortex.wiki.util.links import _obsidian_advanced_uri  # noqa: F401
from exocortex.wiki.util.slugs import (
    _display_from_email,
    _re_extract,
    _slug_from_email,
)

log = logging.getLogger(__name__)

# Work-module constants (canonical, sesja 2026-05-01)
SYNTHESIS_STALE_DAYS = 14
TAG_PAGE_MIN_MEETINGS = 5
LLM_THRESHOLDS = {"project": 3, "person": 5, "monthly": 8, "tag": 5, "moc": 50}
SCHEMA_VERSION = "5.0"

# Owner slug aliases — F2.3 polish-aware slug ('vault-owner') vs email-based
# slug ('exocortex_user') refer to the same person.
_ME_OWNER_SLUGS = ("vault-owner", "exocortex_user")

# F11.6 — co-participants aggregations are noise when the user is included.
_SELF_EXCLUDE_SLUGS = frozenset(_ME_OWNER_SLUGS)

# Owner-name aliases injected into the regex for owners whose `### Header`
# variants in meeting pages differ from the parsed display name.
_OWNER_NAME_ALIASES: dict[str, set[str]] = {
    "vault-owner": {"Exocortex user", "vault-owner-name", "vault-owner-alias"},
}

_INLINE_TAG_RE = re.compile(r"#([a-zA-Z][\w-]*)")
_CHECKBOX_LINE_RE = re.compile(r"^\s*-\s*\[[ xX]\]\s+(.+)$")

# Default group-by for per-person / this-week pages — by client wikilink string
_GROUP_BY_CLIENT = "function (task.file.frontmatter?.client || '').replace(/\\[\\[|\\]\\]/g, '') || '_other'"

# F15.3 promoted-descriptions cache (cleared on each compile run by wiki_compiler)
_PROMOTED_MANUAL_REL = "_ Second Brain/backlog/_second-brain/manual"
_promoted_descriptions_cache: Optional[list[str]] = None


# ---------------------------------------------------------------------------
# Domain registration
# ---------------------------------------------------------------------------


class WorkDomain(_LegacyDomainCompiler):
    _legacy_fn_name = "compile_work_module"

    @property
    def name(self) -> str:
        return "work"

    def prune_orphans(self, ctx: Any) -> int:
        from exocortex.wiki.core.io import _get_wiki_root

        try:
            work_root = _get_wiki_root() / "work"
        except OSError:
            return 0
        if not (work_root / "meetings" / "src").exists():
            return 0
        # since=None on purpose: the expected set must cover every meeting,
        # not just the slice an incremental compile happened to touch.
        return _prune_meeting_orphans(
            work_root, _load_work_meetings(None, ctx.tenant_id, None)
        )


def setup(registry: Any) -> None:
    registry.register_compile_domain(WorkDomain())


# ---------------------------------------------------------------------------
# Lazy access to wiki_compiler globals
# ---------------------------------------------------------------------------


def _wc_pages_written() -> list[str]:
    import exocortex.wiki_compiler as _wc

    return _wc._pages_written


def _wc_llm_tokens_used_add(n: int) -> None:
    import exocortex.wiki_compiler as _wc

    _wc._llm_tokens_used += n


# ---------------------------------------------------------------------------
# Synthesis rendering helpers
# ---------------------------------------------------------------------------


def _humanize_age(generated_at: Any) -> str:
    """Return Polish-language relative age, e.g. '3 dni temu' (3 days ago), '2 tyg. temu'."""
    if not generated_at:
        return "?"
    if isinstance(generated_at, str):
        try:
            generated_at = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except ValueError:
            return generated_at
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - generated_at
    days = delta.days
    if days <= 0:
        return "dziś"
    if days == 1:
        return "wczoraj"
    if days < 7:
        return f"{days} dni temu"
    if days < 30:
        return f"{days // 7} tyg. temu"
    if days < 365:
        return f"{days // 30} mies. temu"
    return f"{days // 365} lat temu"


def _is_synthesis_stale(generated_at: Any) -> bool:
    if not generated_at:
        return False
    if isinstance(generated_at, str):
        try:
            generated_at = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except ValueError:
            return False
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - generated_at).days > SYNTHESIS_STALE_DAYS


def _render_synthesis_banner(
    syn: Optional[dict], n_meetings: int, extra: Optional[str] = None
) -> list[str]:
    """Return Markdown lines for the `>[!info] Synteza` banner + stale warning."""
    if not syn:
        return [
            "> [!info] Synteza",
            "> Brak syntezy. Strona ze statystyk + Dataview.",
            "",
        ]
    age = _humanize_age(syn.get("generated_at"))
    bits = [f"wygenerowana z **{n_meetings} spotkań**"]
    if extra:
        bits.append(extra)
    bits.append(f"regeneracja: **{age}**")
    if syn.get("model"):
        bits.append(f"model: `{syn['model']}`")
    lines = [
        "> [!info] Synteza",
        "> " + " · ".join(bits),
        "",
    ]
    if _is_synthesis_stale(syn.get("generated_at")):
        ga = syn["generated_at"]
        if isinstance(ga, str):
            try:
                ga = datetime.fromisoformat(ga.replace("Z", "+00:00"))
            except ValueError:
                ga = None
        if ga is not None:
            if ga.tzinfo is None:
                ga = ga.replace(tzinfo=timezone.utc)
            days = (datetime.now(timezone.utc) - ga).days
        else:
            days = SYNTHESIS_STALE_DAYS + 1
        lines += [
            "> [!warning] Synteza nieaktualna",
            f"> Minęło {days} dni od regeneracji ({SYNTHESIS_STALE_DAYS}+ dni). "
            f"Re-run `python -m scripts.run_synthesizer` lub `compile_all`.",
            "",
        ]
    return lines


def _format_synthesis_sections(
    content: dict, syn: dict, source_meetings: dict[str, dict]
) -> list[str]:
    """Render the 5-section synthesis body."""
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
    lines += ["## Aktualny stan", "", cs if cs else "_brak danych_", ""]

    decisions = content.get("recent_decisions") or []
    lines += ["## Ostatnie decyzje", ""]
    if decisions:
        for d in decisions:
            date_part = d.get("date") or ""
            head = f"- **{date_part}** — " if date_part else "- "
            lines.append(
                f"{head}{d.get('content', '')}{_link(d.get('source_thought_id', ''))}"
            )
    else:
        lines.append("_brak ostatnich decyzji_")
    lines.append("")

    problems = content.get("open_problems") or []
    if problems:
        lines += ["> [!warning] Kluczowe problemy"]
        for p in problems:
            sev = (p.get("severity") or "medium").upper()
            lines.append(
                f"> - **{sev}**: {p.get('content', '')}"
                f"{_link(p.get('source_thought_id', ''))}"
            )
        lines.append("")
    else:
        lines += ["## Kluczowe problemy", "", "_brak otwartych problemów_", ""]

    ownership = content.get("ownership") or []
    lines += ["## Ownership", ""]
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
    lines += ["## Next steps", ""]
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
        lines.append("_brak planowanych kroków_")
    lines.append("")

    return lines


def _render_related_decisions(
    syn_ids: list[str],
    syntheses_by_id: dict[str, dict],
    meeting_index: dict[str, dict],
    *,
    title: str = "Powiązane decyzje",
    limit: int = 10,
) -> list[str]:
    if not syn_ids:
        return []
    seen: set[str] = set()
    items: list[str] = []
    for sid in syn_ids:
        if sid in seen:
            continue
        seen.add(sid)
        syn = syntheses_by_id.get(sid)
        if not syn:
            continue
        ptype = syn.get("perspective_type") or "?"
        pkey = syn.get("perspective_key") or "?"
        content = syn.get("content") or {}
        decisions = content.get("recent_decisions") or []
        for d in decisions[:3]:
            text = (d.get("content") or "").strip()
            if not text:
                continue
            src_tid = str(d.get("source_thought_id") or "")
            link = ""
            m = meeting_index.get(src_tid)
            if m:
                link = f" ([[{m['slug']}|źródło]])"
            items.append(f"- *[{ptype}/{pkey}]* {text}{link}")
            if len(items) >= limit:
                break
        if len(items) >= limit:
            break
    if not items:
        return []
    return [f"## {title}", ""] + items + [""]


def _render_related_problems(
    syn_ids: list[str],
    syntheses_by_id: dict[str, dict],
    meeting_index: dict[str, dict],
    *,
    title: str = "Powiązane problemy",
    limit: int = 10,
) -> list[str]:
    if not syn_ids:
        return []
    seen: set[str] = set()
    items: list[str] = []
    for sid in syn_ids:
        if sid in seen:
            continue
        seen.add(sid)
        syn = syntheses_by_id.get(sid)
        if not syn:
            continue
        ptype = syn.get("perspective_type") or "?"
        pkey = syn.get("perspective_key") or "?"
        content = syn.get("content") or {}
        problems = content.get("open_problems") or []
        for p in problems[:3]:
            text = (p.get("content") or "").strip()
            if not text:
                continue
            sev = (p.get("severity") or "medium").upper()
            src_tid = str(p.get("source_thought_id") or "")
            link = ""
            m = meeting_index.get(src_tid)
            if m:
                link = f" ([[{m['slug']}|źródło]])"
            items.append(f"- **{sev}** *[{ptype}/{pkey}]* {text}{link}")
            if len(items) >= limit:
                break
        if len(items) >= limit:
            break
    if not items:
        return []
    return [f"## {title}", ""] + items + [""]


def _collect_related_syntheses_for_meetings(
    meeting_ids: list[str],
    edges: EdgesIndex,
    syntheses_by_id: dict[str, dict],
    *,
    own_perspective: tuple[str, str] | None = None,
) -> list[str]:
    sids: list[str] = []
    seen: set[str] = set()
    for mid in meeting_ids:
        for sid in edges.decided_in_by_meeting.get(mid, []):
            if sid in seen:
                continue
            syn = syntheses_by_id.get(sid)
            if not syn:
                continue
            if (
                own_perspective
                and (syn.get("perspective_type"), syn.get("perspective_key"))
                == own_perspective
            ):
                continue
            seen.add(sid)
            sids.append(sid)
        for sid in edges.addresses_problem_by_meeting.get(mid, []):
            if sid in seen:
                continue
            syn = syntheses_by_id.get(sid)
            if not syn:
                continue
            if (
                own_perspective
                and (syn.get("perspective_type"), syn.get("perspective_key"))
                == own_perspective
            ):
                continue
            seen.add(sid)
            sids.append(sid)

    def _key(sid: str) -> str:
        ga = (syntheses_by_id.get(sid) or {}).get("generated_at")
        if hasattr(ga, "isoformat"):
            return ga.isoformat()
        return str(ga) if ga else ""

    sids.sort(key=_key, reverse=True)
    return sids


def _synthesis_fm_fields(syn: Optional[dict]) -> dict:
    if not syn:
        return {}
    out = {
        "synthesis_id": str(syn["id"]),
        "synthesis_input_hash": syn.get("input_hash"),
        "synthesis_generated_at": (
            syn["generated_at"].isoformat()
            if hasattr(syn.get("generated_at"), "isoformat")
            else syn.get("generated_at")
        ),
        "synthesis_prompt_version": syn.get("prompt_version"),
        "synthesis_model": syn.get("model"),
    }
    return {k: v for k, v in out.items() if v is not None}


def _person_email_to_slug(email: str) -> str:
    return _slug_from_email(email)


def _resolve_person_display(slug: str, email: str) -> str:
    cfg = _load_projects_cfg()
    for tag, info in cfg.person_tags.items():
        if info.get("person_slug") == slug and info.get("display_name"):
            return info["display_name"]
    return _display_from_email(email)


# ---------------------------------------------------------------------------
# Meeting parsing and loading
# ---------------------------------------------------------------------------


def _parse_meeting(row: dict) -> dict:
    """thoughts row -> normalized meeting dict."""
    if "id" in row and not isinstance(row["id"], str):
        row["id"] = str(row["id"])
    ca = row.get("created_at")
    if ca is not None and not isinstance(ca, str):
        row["created_at"] = ca.isoformat() if hasattr(ca, "isoformat") else str(ca)
    body = row.get("body") or ""
    meta = row.get("metadata") or {}

    title = _re_extract(r"^Meeting:\s*(.+)$", body) or "(untitled)"
    date = (
        _re_extract(r"^Date:\s*(\d{4}-\d{2}-\d{2})", body)
        or (row.get("created_at") or "")[:10]
    )

    organizer_email = meta.get("organizer")
    participants_emails = list(meta.get("participants") or [])
    if organizer_email and organizer_email not in participants_emails:
        participants_emails.insert(0, organizer_email)

    # Coerced once at the source (not just str() at each downstream `.lower()`
    # call): this `tags` list is stored verbatim into the meeting dict
    # ("tags" key below) and re-consumed by _write_by_tag_pages and
    # wiki/domains/home — fixing it here closes off every consumer at once
    # instead of patching each call site as it crashes.
    tags = [str(t) for t in (meta.get("tags") or [])]

    cfg = _load_projects_cfg()
    cls = classify_meeting(row, cfg)
    if cls.client:
        projects = [cls.client]
        primary_project = cls.project or cls.client
    else:
        client_slugs = {c.slug for c in cfg.clients} | {
            a for c in cfg.clients for a in c.aliases
        }
        projects = [t for t in tags if str(t).lower() in client_slugs]
        primary_project = projects[0] if projects else None

    mtype = cls.type_tags[0] if cls.type_tags else _classify_type(tags, title)

    _internal_domain = get_internal_domain()
    is_external = bool(_internal_domain) and any(
        e and e.split("@")[-1].lower() != _internal_domain for e in participants_emails
    )

    participants_clean = [e for e in participants_emails if e]

    et = row.get("extracted_tags") or {}

    def _axis_values(axis_name: str) -> list[str]:
        items = et.get(axis_name) if isinstance(et, dict) else None
        if not isinstance(items, list):
            return []
        out: list[str] = []
        for it in items:
            if isinstance(it, dict) and it.get("value"):
                out.append(str(it["value"]).strip().lower())
            elif isinstance(it, str):
                out.append(it.strip().lower())
        return [v for v in out if v]

    return {
        "thought_id": row["id"],
        "title": title.strip(),
        "date": date,
        "month": date[:7] if date else "",
        "duration_minutes": float(meta.get("duration_minutes") or 0),
        "organizer_email": organizer_email,
        "organizer_slug": _slug_from_email(organizer_email)
        if organizer_email
        else None,
        "participants_emails": participants_clean,
        "participants_slugs": [_slug_from_email(e) for e in participants_clean],
        "tags": tags,
        "projects": projects,
        "primary_project": primary_project,
        "client_slug": cls.client,
        "project_slug": cls.project,
        "person_tags": list(cls.person_tags),
        "type_tags": list(cls.type_tags),
        "topic_tags": list(cls.topic_tags),
        "status_tags": _axis_values("status"),
        "extracted_topic_axis": _axis_values("topic"),
        "extracted_activity_axis": _axis_values("activity"),
        "extracted_project_axis": _axis_values("project"),
        "classification_source": cls.source,
        "classification_confidence": cls.confidence,
        "meeting_type": mtype,
        "is_external": is_external,
        "transcript_url": meta.get("transcript_url"),
        "source_id": row["id"],
        "meeting_id": meta.get("meeting_id"),
        "slug": _meeting_slug(date, title, row["id"]),
        "overview": meta.get("overview"),
        "action_items": meta.get("action_items"),
        "key_points": meta.get("key_points"),
        "notes": meta.get("notes"),
    }


def _load_work_meetings(_db, tenant_id: str, since: Optional[datetime]) -> list[dict]:
    from exocortex.db import query

    if since is None:
        rows = query(
            "SELECT id, body, metadata, extracted_tags, created_at FROM thoughts "
            "WHERE tenant_id = %s AND thought_type = %s ORDER BY created_at",
            tenant_id,
            "work_meeting_note",
        )
    else:
        since_date = since.date().isoformat()
        rows = query(
            "SELECT id, body, metadata, extracted_tags, created_at FROM thoughts "
            "WHERE tenant_id = %s AND thought_type = %s "
            "  AND ( "
            "    coalesce("
            "      (regexp_match(body, '^Date: (\\d{4}-\\d{2}-\\d{2})', 'm'))[1], "
            "      to_char(created_at, 'YYYY-MM-DD') "
            "    ) >= %s "
            "  ) "
            "ORDER BY created_at",
            tenant_id,
            "work_meeting_note",
            since_date,
        )
    return [_parse_meeting(r) for r in rows]


# ---------------------------------------------------------------------------
# Meeting page rendering
# ---------------------------------------------------------------------------


def _render_meeting_body(m: dict) -> str:
    lines: list[str] = []
    if m.get("transcript_url"):
        lines += [f"[Transcript →]({m['transcript_url']})", ""]
    lines += ["## Metadata", f"- **Data:** {m['date']}"]
    if m.get("duration_minutes"):
        lines.append(f"- **Czas:** {int(round(m['duration_minutes']))} min")
    if m.get("organizer_slug"):
        lines.append(f"- **Organizator:** [[{m['organizer_slug']}]]")
    if m.get("participants_slugs"):
        plist = ", ".join(f"[[{s}]]" for s in m["participants_slugs"])
        lines.append(f"- **Uczestnicy:** {plist}")
    if m.get("projects"):
        plist = ", ".join(f"[[{p}]]" for p in m["projects"])
        lines.append(f"- **Projekty:** {plist}")

    section_titles = [
        ("overview", "Overview"),
        ("key_points", "Key Points"),
        ("action_items", "Action Items"),
        ("notes", "Notes"),
    ]
    for key, heading in section_titles:
        content = m.get(key)
        if content:
            lines += ["", f"## {heading}", "", content]
    return "\n".join(lines)


def _prune_meeting_orphans(work_root: Path, meetings: list[dict]) -> int:
    """Delete meeting pages a rename left behind. Returns how many.

    Expected filenames come from the compiler's own `meetings` list, not from
    a second reimplementation of the slug rule — those two drifting apart
    would mean judging a live page against the wrong name and deleting it.

    Pages holding ticked action items are never deleted. The compiler merges
    those `[x]` marks forward from the existing file on each rebuild, so after
    a rename the orphan is the only copy and removing it would destroy them.
    Those are reported for a human instead.
    """
    from exocortex.wiki.core import _state as _wc
    from exocortex.wiki.util.prune import (
        _prune_is_plausible,
        _select_orphans,
        has_user_state,
    )

    src = work_root / "meetings" / "src"
    if not src.exists():
        return 0

    expected = {
        str(m["thought_id"]).replace("-", "")[:8]: f"{m['slug']}.md"
        for m in meetings
        if m.get("thought_id") and m.get("slug")
    }
    files_by_name = {}
    for f in src.glob("*.md"):
        m = re.search(r"--([0-9a-f]{8})\.md$", f.name)
        if m:  # anything else predates this naming scheme — not ours to judge
            files_by_name[f.name] = m.group(1)
    if not files_by_name:
        return 0

    # Only the rename case. A meeting page whose thought is absent must be
    # left alone: everything older than ~May 2026 has no thought left in the
    # database (267 of 453 pages), so there the page is the only surviving
    # record of a meeting that really happened — and all 18 pages carrying
    # ticked action items are among them.
    orphans = _select_orphans(files_by_name, expected, orphan_when_record_gone=False)
    if not orphans:
        return 0
    if not _prune_is_plausible(n_delete=len(orphans), n_total=len(files_by_name)):
        print(
            f"[wiki_compiler] meetings: REFUSED to prune {len(orphans)} of "
            f"{len(files_by_name)} pages — that looks wrong, not stale"
        )
        return 0

    n = 0
    for name in orphans:
        path = src / name
        if has_user_state(path):
            print(
                f"[wiki_compiler] meetings: KEEPING orphan {name} — it has "
                "ticked action items that exist nowhere else; move them to the "
                "current page and delete it by hand"
            )
            continue
        if _wc.DRY_RUN:
            print(f"[wiki_compiler] meetings: would prune {path}")
            n += 1
            continue
        try:
            path.unlink()
            n += 1
        except OSError as exc:
            print(f"[wiki_compiler] meetings: could not prune {name}: {exc!r}")
    if n:
        verb = "would prune" if _wc.DRY_RUN else "pruned"
        print(f"[wiki_compiler] meetings: {verb} {n} orphaned pages")
    return n


def _write_meeting_pages(work_root: Path, meetings: list[dict]) -> None:
    written, skipped = 0, 0
    meetings_src = work_root / "meetings" / "src"
    meetings_src.mkdir(parents=True, exist_ok=True)
    pages_written = _wc_pages_written()
    for m in meetings:
        path = meetings_src / f"{m['slug']}.md"

        fm: dict = {
            "title": m["title"],
            "date": m["date"],
            "duration_minutes": int(round(m["duration_minutes"]))
            if m["duration_minutes"]
            else None,
            "type": "meeting",
            "domain": "work",
            "meeting_type": m["meeting_type"],
            "client": f"[[{m['client_slug']}]]" if m.get("client_slug") else None,
            "project": f"[[{m['project_slug']}]]"
            if m.get("project_slug")
            else (f"[[{m['primary_project']}]]" if m["primary_project"] else None),
            "clients": [f"[[{p}]]" for p in m["projects"]] or None,
            "person_tags": [f"[[{s}]]" for s in (m.get("person_tags") or [])] or None,
            "type_tags": list(m.get("type_tags") or []) or None,
            "topic_tags": list(m.get("topic_tags") or []) or None,
            "participants": [f"[[{s}]]" for s in m["participants_slugs"]],
            "organizer": f"[[{m['organizer_slug']}]]" if m["organizer_slug"] else None,
            "participant_count": len(m["participants_slugs"]),
            "is_external": m["is_external"],
            "tags": sorted(set(["work"] + (m["tags"] or []))),
            "transcript_url": m["transcript_url"],
            "source_id": m["source_id"],
            "meeting_id": m.get("meeting_id"),
        }
        fm = {k: v for k, v in fm.items() if v is not None}
        body = _render_meeting_body(m)

        # F11.4 SAFETY — preserve user-toggled [x] from existing file before write.
        # _merge_user_done_state is imported from exocortex.wiki.core.user_state.
        # DO NOT remove or bypass this call.
        existing_body: Optional[str] = None
        if path.exists():
            try:
                existing_text = path.read_text(encoding="utf-8")
                fm_match = re.match(r"^---\n.*?\n---\n", existing_text, re.DOTALL)
                existing_body = (
                    existing_text[fm_match.end() :] if fm_match else existing_text
                )
            except (OSError, UnicodeDecodeError):
                log.warning("Cannot read existing page %s — treating as new", path)
                existing_body = None
        body = _merge_user_done_state(body, existing_body)

        fm["input_hash"] = _hash_input(
            {**fm, "_body_sig": hashlib.sha256(body.encode()).hexdigest()[:16]}
        )
        if _write_with_frontmatter(str(path), fm, body, [m["source_id"]]):
            pages_written.append(str(path))
            written += 1
        else:
            skipped += 1
    print(f"[wiki_compiler] meetings: wrote {written}, skipped {skipped} unchanged")


# ---------------------------------------------------------------------------
# Client pages
# ---------------------------------------------------------------------------


def _resolve_cluster_label(cluster_slug: str) -> tuple[str, str]:
    """(emoji, label) for a cluster slug, falling back to title-case + 📰."""
    from exocortex.wiki.domains.news import (
        _NEWS_CLUSTER_DEFAULT_EMOJI,
        _load_topic_clusters,
    )

    _, clusters_by_slug = _load_topic_clusters()
    entry = clusters_by_slug.get(cluster_slug)
    if entry:
        return (
            (entry.get("emoji") or _NEWS_CLUSTER_DEFAULT_EMOJI).strip(),
            (entry.get("label") or cluster_slug.replace("-", " ").title()).strip(),
        )
    return _NEWS_CLUSTER_DEFAULT_EMOJI, cluster_slug.replace("-", " ").title()


def _render_inspirations_section(
    client_slug: str, inspirations: list[dict], *, top_n: int = 5
) -> list[str]:
    if not inspirations:
        return []

    top = inspirations[:top_n]
    lines: list[str] = [
        "<!-- GENERATED: cross-domain-matches -->",
        "## Inspiracje z newsletterów",
        "",
        "> [!info] Cross-domain matches od claude-haiku-4-5, threshold ≥6/10. Refresh daily.",
        "",
    ]
    for ins in top:
        cluster_slug = ins["cluster_slug"]
        score = ins["relevance_score"]
        reason = ins["reason"] or "(brak uzasadnienia)"
        emoji, label = _resolve_cluster_label(cluster_slug)
        lines.append(
            f"### {emoji} [[../../news/by-category/{cluster_slug}|{label}]] — {score}/10"
        )
        lines.append(reason)
        lines.append("")
    lines.append("<!-- /GENERATED: cross-domain-matches -->")
    lines.append("")
    return lines


def _render_client_backlog_section(client: str) -> list[str]:
    return [
        "## Plan długoterminowy (backlog)",
        "",
        "> Long-term initiatives z [[_ Second Brain/backlog/_view-second-brain|Backlog Kanban]]. "
        "Operational follow-ups → patrz Spotkania niżej.",
        "",
        "```dataview",
        "TABLE WITHOUT ID",
        '  file.link AS "Task",',
        '  status AS "Status",',
        '  estimate_hours AS "Hours",',
        '  priority AS "Priority"',
        'FROM "_ Second Brain/backlog/_second-brain"',
        f'WHERE (contains(string(file.path), "{client}")',
        f'   OR contains(string(tags), "{client}")',
        f'   OR contains(string(client), "{client}")',
        f'   OR contains(string(file.outlinks), "{client}"))',
        '  AND status != "done"',
        '  AND status != "deferred"',
        "SORT priority DESC, status ASC",
        "```",
        "",
    ]


def _render_client_body(
    client: str,
    meetings: list[dict],
    fm: dict,
    syn: Optional[dict],
    meeting_index: dict[str, dict],
    related_decision_lines: Optional[list[str]] = None,
    related_problem_lines: Optional[list[str]] = None,
    inspiration_lines: Optional[list[str]] = None,
) -> str:
    fm.get("project_display") or _client_display(client)
    lines: list[str] = []
    lines += _render_synthesis_banner(syn, len(meetings), extra=f"klient: **{client}**")

    if syn and syn.get("content"):
        lines += _format_synthesis_sections(syn["content"], syn, meeting_index)

    if related_decision_lines:
        lines += related_decision_lines
    if related_problem_lines:
        lines += related_problem_lines

    if inspiration_lines:
        lines += inspiration_lines

    lines += _render_client_backlog_section(client)

    sub_projects = fm.get("sub_projects") or []
    if sub_projects:
        lines += ["## Sub-projekty", ""]
        for sp in sub_projects:
            lines.append(f"- {sp}")
        lines.append("")

    lines += [
        "## Statystyki",
        "",
        f"- **Spotkań:** {fm['meeting_count']}",
        f"- **Okres:** {fm['first_meeting']} → {fm['last_meeting']}",
        f"- **Łączny czas:** {fm['duration_total_minutes']} min",
        "",
    ]

    lines += [
        "## Spotkania",
        "",
        "```dataview",
        "TABLE WITHOUT ID",
        '  file.link AS "Spotkanie",',
        '  date AS "Data",',
        '  duration_minutes AS "Min",',
        '  participant_count AS "Uczest."',
        'FROM "wiki/work/meetings/src"',
        f"WHERE contains(clients, [[{client}]])",
        "SORT date DESC",
        "```",
    ]
    return "\n".join(lines)


def _write_client_pages(
    work_root: Path,
    meetings: list[dict],
    syntheses: dict[tuple[str, str], dict],
    meeting_index: dict[str, dict],
    edges_index: Optional["EdgesIndex"] = None,
    syntheses_by_id: Optional[dict[str, dict]] = None,
) -> None:
    by_client: dict[str, list[dict]] = defaultdict(list)
    for m in meetings:
        key = m.get("client_slug") or (
            m["projects"][0] if m.get("projects") else "_unassigned"
        )
        by_client[key].append(m)

    pages_written = _wc_pages_written()
    written, skipped = 0, 0
    for client, ms in by_client.items():
        ms_sorted = sorted(ms, key=lambda x: x["date"], reverse=True)
        dated = [m["date"] for m in ms_sorted if m["date"]]
        first = min(dated) if dated else None
        last = max(dated) if dated else None
        total_min = sum(m["duration_minutes"] for m in ms_sorted)
        types = sorted({m["meeting_type"] for m in ms_sorted})

        cnt: Counter[str] = Counter()
        for m in ms_sorted:
            for s in m["participants_slugs"]:
                if s and s != "unknown" and s not in me_owner_slugs():
                    cnt[s] += 1
        top = [s for s, _ in cnt.most_common(5)]

        sub_projs = sorted(
            {
                m["project_slug"]
                for m in ms_sorted
                if m.get("project_slug")
                and not m["project_slug"].endswith("-general")
                and m["project_slug"] != "docmost-internal"
            }
        )
        sub_proj_links = [
            f"[[projects/{client}/{sp.split('-', 1)[1] if sp.startswith(client + '-') else sp}|{sp}]]"
            for sp in sub_projs
        ]

        syn = syntheses.get(("client", client))

        related_dec_lines: list[str] = []
        related_prob_lines: list[str] = []
        rel_sids: list[str] = []
        if edges_index and syntheses_by_id:
            entity_meeting_ids = [str(m["thought_id"]) for m in ms_sorted]
            rel_sids = _collect_related_syntheses_for_meetings(
                entity_meeting_ids,
                edges_index,
                syntheses_by_id,
                own_perspective=("client", client),
            )
            related_dec_lines = _render_related_decisions(
                rel_sids, syntheses_by_id, meeting_index
            )
            related_prob_lines = _render_related_problems(
                rel_sids, syntheses_by_id, meeting_index
            )

        inspirations: list[dict] = []
        if edges_index is not None:
            inspirations = list(edges_index.inspirations_by_client_slug.get(client, []))
        inspiration_lines = _render_inspirations_section(client, inspirations)
        inspiration_payload = [
            (
                ins["cluster_slug"],
                ins["relevance_score"],
                hashlib.sha256((ins.get("reason") or "").encode("utf-8")).hexdigest()[
                    :12
                ],
            )
            for ins in inspirations[:5]
        ]

        fm: dict = {
            "type": "client",
            "domain": "work",
            "client": client,
            "project": client,
            "project_display": _client_display(client),
            "title": _client_display(client),
            "meeting_count": len(ms_sorted),
            "first_meeting": first,
            "last_meeting": last,
            "duration_total_minutes": int(round(total_min)),
            "top_participants": [f"[[{s}]]" for s in top],
            "sub_projects": sub_proj_links,
            "meeting_types": types,
            "tags": ["work", "client", client],
        }
        fm.update(_synthesis_fm_fields(syn))
        fm["input_hash"] = _hash_input(
            {
                **fm,
                "_meetings": sorted(m["slug"] for m in ms_sorted),
                "_related_syntheses": rel_sids,
                "_inspirations": inspiration_payload,
                "_render_version": "f8.8.x.g",
            }
        )

        path = work_root / "clients" / f"{client}.md"
        body = _render_client_body(
            client,
            ms_sorted,
            fm,
            syn,
            meeting_index,
            related_dec_lines,
            related_prob_lines,
            inspiration_lines,
        )
        if _write_with_frontmatter(
            str(path), fm, body, [m["source_id"] for m in ms_sorted]
        ):
            pages_written.append(str(path))
            written += 1
        else:
            skipped += 1
    print(f"[wiki_compiler] clients: wrote {written}, skipped {skipped} unchanged")


# ---------------------------------------------------------------------------
# Sub-project pages
# ---------------------------------------------------------------------------


def _write_subproject_pages(
    work_root: Path,
    meetings: list[dict],
    syntheses: dict[tuple[str, str], dict],
    meeting_index: dict[str, dict],
    edges_index: Optional["EdgesIndex"] = None,
    syntheses_by_id: Optional[dict[str, dict]] = None,
) -> None:
    cfg = _load_projects_cfg()
    project_min: dict[str, int] = {}
    project_display: dict[str, str] = {}
    project_client: dict[str, str] = {}
    for c in cfg.clients:
        for p in c.projects:
            project_min[p.slug] = p.min_meetings
            project_display[p.slug] = p.display_name
            project_client[p.slug] = c.slug

    by_subproj: dict[str, list[dict]] = defaultdict(list)
    for m in meetings:
        ps = m.get("project_slug")
        if not ps:
            continue
        if ps.endswith("-general") or ps == "docmost-internal":
            continue
        by_subproj[ps].append(m)

    pages_written = _wc_pages_written()
    written, skipped = 0, 0
    for proj_slug, ms in by_subproj.items():
        threshold = project_min.get(proj_slug, LLM_THRESHOLDS["project"])
        if len(ms) < threshold:
            continue
        ms_sorted = sorted(ms, key=lambda x: x["date"], reverse=True)
        client_slug = project_client.get(proj_slug, proj_slug.split("-")[0])
        sub_slug = (
            proj_slug.split("-", 1)[1]
            if proj_slug.startswith(client_slug + "-")
            else proj_slug
        )

        dated = [m["date"] for m in ms_sorted if m["date"]]
        total_min = sum(m["duration_minutes"] for m in ms_sorted)

        syn = syntheses.get(("project", proj_slug))

        related_dec_lines: list[str] = []
        related_prob_lines: list[str] = []
        rel_sids: list[str] = []
        if edges_index and syntheses_by_id:
            entity_meeting_ids = [str(m["thought_id"]) for m in ms_sorted]
            rel_sids = _collect_related_syntheses_for_meetings(
                entity_meeting_ids,
                edges_index,
                syntheses_by_id,
                own_perspective=("project", proj_slug),
            )
            related_dec_lines = _render_related_decisions(
                rel_sids, syntheses_by_id, meeting_index
            )
            related_prob_lines = _render_related_problems(
                rel_sids, syntheses_by_id, meeting_index
            )

        fm: dict = {
            "type": "sub-project",
            "domain": "work",
            "client": client_slug,
            "project": proj_slug,
            "project_display": project_display.get(proj_slug, proj_slug),
            "title": project_display.get(proj_slug, proj_slug),
            "meeting_count": len(ms_sorted),
            "first_meeting": min(dated) if dated else None,
            "last_meeting": max(dated) if dated else None,
            "duration_total_minutes": int(round(total_min)),
            "tags": ["work", "sub-project", client_slug, proj_slug],
        }
        fm.update(_synthesis_fm_fields(syn))
        fm["input_hash"] = _hash_input(
            {
                **fm,
                "_meetings": sorted(m["slug"] for m in ms_sorted),
                "_related_syntheses": rel_sids,
            }
        )

        body_lines = [
            f"> Sub-projekt klienta [[{client_slug}]] (`{proj_slug}`)",
            "",
        ]
        body_lines += _render_synthesis_banner(
            syn, len(ms_sorted), extra=f"projekt: **{proj_slug}**"
        )
        if syn and syn.get("content"):
            body_lines += _format_synthesis_sections(syn["content"], syn, meeting_index)
        if related_dec_lines:
            body_lines += related_dec_lines
        if related_prob_lines:
            body_lines += related_prob_lines

        body_lines += [
            "## Statystyki",
            "",
            f"- **Spotkań:** {len(ms_sorted)}",
            f"- **Okres:** {fm['first_meeting']} → {fm['last_meeting']}",
            f"- **Łączny czas:** {fm['duration_total_minutes']} min",
            "",
            "## Spotkania",
            "",
            "```dataview",
            "TABLE WITHOUT ID",
            '  file.link AS "Spotkanie",',
            '  date AS "Data",',
            '  duration_minutes AS "Min"',
            'FROM "wiki/work/meetings/src"',
            f'WHERE project = "[[{proj_slug}]]"',
            "SORT date DESC",
            "```",
        ]
        body = "\n".join(body_lines)

        path = work_root / "projects" / client_slug / f"{sub_slug}.md"
        if _write_with_frontmatter(
            str(path), fm, body, [m["source_id"] for m in ms_sorted]
        ):
            pages_written.append(str(path))
            written += 1
        else:
            skipped += 1
    print(f"[wiki_compiler] sub-projects: wrote {written}, skipped {skipped} unchanged")


# ---------------------------------------------------------------------------
# By-tag pages
# ---------------------------------------------------------------------------


def _write_by_tag_pages(
    work_root: Path,
    meetings: list[dict],
    syntheses: dict[tuple[str, str], dict],
    meeting_index: dict[str, dict],
) -> None:
    NOISE_TAGS = {"meeting", "group", "work"}
    by_tag: dict[str, list[dict]] = defaultdict(list)
    for m in meetings:
        seen: set[str] = set()
        if m.get("meeting_type") and m["meeting_type"] != "unspecified":
            seen.add(m["meeting_type"].lower())
        axis_sources = (
            m.get("topic_tags") or [],
            m.get("type_tags") or [],
            m.get("status_tags") or [],
            m.get("extracted_topic_axis") or [],
            m.get("extracted_activity_axis") or [],
            m.get("extracted_project_axis") or [],
        )
        for source in axis_sources:
            for t in source:
                if t:
                    seen.add(t.strip().lower())
        for t in m.get("tags") or []:
            if not t:
                continue
            tl = t.strip().lower()
            if tl in NOISE_TAGS:
                continue
            seen.add(tl)
        for t in seen:
            by_tag[t].append(m)

    pages_written = _wc_pages_written()
    written, skipped = 0, 0
    for tag, ms in by_tag.items():
        if len(ms) < TAG_PAGE_MIN_MEETINGS:
            continue
        ms_sorted = sorted(ms, key=lambda x: x["date"], reverse=True)
        dated = [m["date"] for m in ms_sorted if m["date"]]
        clients = sorted(
            {m.get("client_slug") for m in ms_sorted if m.get("client_slug")}
        )

        cnt: Counter[str] = Counter()
        for m in ms_sorted:
            for s in m["participants_slugs"]:
                if s and s != "unknown" and s not in me_owner_slugs():
                    cnt[s] += 1
        top_owners = [s for s, _ in cnt.most_common(5)]

        syn = syntheses.get(("tag", tag)) or syntheses.get(("type", tag))

        fm: dict = {
            "type": "by-tag",
            "domain": "work",
            "tag": tag,
            "meeting_count": len(ms_sorted),
            "first_meeting": min(dated) if dated else None,
            "last_meeting": max(dated) if dated else None,
            "top_owners": [f"[[{s}]]" for s in top_owners],
            "related_clients": [f"[[{c}]]" for c in clients],
            "tags": ["work", "by-tag", tag],
        }
        fm.update(_synthesis_fm_fields(syn))
        fm["input_hash"] = _hash_input(
            {**fm, "_meetings": sorted(m["slug"] for m in ms_sorted)}
        )

        owners_lines = (
            [f"- [[{s}]]" for s in top_owners] if top_owners else ["- _brak danych_"]
        )
        body_parts = [
            f"# #{tag}",
            "",
        ]
        body_parts += _render_synthesis_banner(
            syn, len(ms_sorted), extra=f"tag: **{tag}**"
        )
        if syn and syn.get("content"):
            body_parts += _format_synthesis_sections(syn["content"], syn, meeting_index)

        body_parts += [
            "## Statystyki",
            "",
            f"- **Spotkań:** {len(ms_sorted)}",
            f"- **Okres:** {fm['first_meeting']} → {fm['last_meeting']}",
            f"- **Klienci:** {', '.join(f'[[{c}]]' for c in clients) or '_brak_'}",
            "",
            "## Top owners",
            "",
        ]
        body_parts.extend(owners_lines)
        body_parts += [
            "",
            "## Spotkania",
            "",
            "```dataview",
            "TABLE WITHOUT ID",
            '  file.link AS "Spotkanie",',
            '  date AS "Data",',
            '  client AS "Klient"',
            'FROM "wiki/work/meetings/src"',
            f'WHERE contains(tags, "{tag}") OR meeting_type = "{tag}" '
            f'OR contains(topic_tags, "{tag}") OR contains(type_tags, "{tag}") '
            f'OR contains(status_tags, "{tag}")',
            "SORT date DESC",
            "```",
        ]
        body = "\n".join(body_parts)

        path = work_root / "by-tag" / f"{tag}.md"
        if _write_with_frontmatter(
            str(path), fm, body, [m["source_id"] for m in ms_sorted]
        ):
            pages_written.append(str(path))
            written += 1
        else:
            skipped += 1
    print(f"[wiki_compiler] by-tag: wrote {written}, skipped {skipped} unchanged")


# ---------------------------------------------------------------------------
# TODO pages
# ---------------------------------------------------------------------------


def _todo_collect(meetings: list[dict]) -> list[dict]:
    from exocortex.action_items import parse_action_items

    out: list[dict] = []
    for m in meetings:
        meta = {
            "action_items": m.get("action_items"),
            "meeting_id": m.get("thought_id"),
        }
        items = parse_action_items(meta, source_thought_id=m.get("thought_id"))
        for it in items:
            out.append({"item": it.to_dict(), "meeting": m})
    return out


def _todo_owner_regex(slug: str, names: set[str]) -> str:
    extras = set(_OWNER_NAME_ALIASES.get(slug, set()))
    if slug in me_owner_slugs():
        extras |= me_owner_names()
    variants: set[str] = set()
    for n in names | extras:
        if not n:
            continue
        v = n.strip()
        variants.add(v.lower())
        variants.add(_strip_pl_accents(v).lower())
        parts = v.split()
        if len(parts) > 1:
            variants.add(parts[-1].lower())
            variants.add(_strip_pl_accents(parts[-1]).lower())
    sorted_variants = sorted(variants, key=lambda v: (-len(v), v))
    escaped = [re.escape(v) for v in sorted_variants if v]
    return "^(" + "|".join(escaped) + ")$" if escaped else "^$"


def _vault_root_for_promoted() -> Path:
    return get_settings().vault_path


def _normalize_action_text_for_filter(content: str) -> str:
    s = re.sub(r"\s+✅\s*\d{4}-\d{2}-\d{2}", "", content)
    s = re.sub(r"\s+➕\s*\d{4}-\d{2}-\d{2}", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _load_promoted_descriptions(vault_root: Optional[Path] = None) -> list[str]:
    global _promoted_descriptions_cache
    if _promoted_descriptions_cache is not None:
        return _promoted_descriptions_cache
    root = vault_root or _vault_root_for_promoted()
    manual_dir = root / _PROMOTED_MANUAL_REL
    out: list[str] = []
    if not manual_dir.is_dir():
        _promoted_descriptions_cache = out
        return out
    for p in sorted(manual_dir.glob("*.md")):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        m = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
        if not m:
            continue
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            continue
        if not isinstance(fm, dict):
            continue
        if "source_fingerprint" not in fm:
            continue
        raw = fm.get("description") or fm.get("title") or fm.get("subject") or ""
        if isinstance(raw, str) and raw.strip():
            out.append(_normalize_action_text_for_filter(raw))
    _promoted_descriptions_cache = out
    return out


def _build_promoted_filter() -> Optional[str]:
    items = _load_promoted_descriptions()
    if not items:
        return None
    arr_literal = json.dumps(items, ensure_ascii=False)
    js = (
        f"(function(t){{"
        f"const P=new Set({arr_literal});"
        f"const n=s=>s"
        f".replace(/\\s+✅\\s*\\d{{4}}-\\d{{2}}-\\d{{2}}/g,'')"
        f".replace(/\\s+➕\\s*\\d{{4}}-\\d{{2}}-\\d{{2}}/g,'')"
        f".replace(/\\s+/g,' ').trim();"
        f"return !P.has(n(t.description||''));"
        f"}})(task)"
    )
    return f"filter by function {js}"


def _render_tasks_query(
    *,
    scope: str = "wiki/work/meetings",
    filters: list[str],
    sort: Optional[str] = "due",
    group_by: Optional[
        str
    ] = "function task.file.frontmatter?.client?.includes('client/') || task.file.frontmatter?.client || '_other'",
    limit: Optional[int] = None,
    done: bool = False,
    done_after: Optional[str] = None,
    done_before: Optional[str] = None,
    extra: Optional[list[str]] = None,
    hide: Optional[list[str]] = None,
) -> str:
    lines = ["```tasks"]
    lines.append("done" if done else "not done")
    lines.append(f"path includes {scope}")
    if done_after:
        lines.append(f"done after {done_after}")
    if done_before:
        lines.append(f"done before {done_before}")
    for f in filters or []:
        lines.append(f)
    for f in extra or []:
        lines.append(f)
    if not done:
        promoted_filter = _build_promoted_filter()
        if promoted_filter:
            lines.append(promoted_filter)
    if sort:
        lines.append(f"sort by {sort}")
    if group_by:
        lines.append(f"group by {group_by}")
    if limit:
        lines.append(f"limit {limit}")
    for h in hide or []:
        lines.append(f"hide {h}")
    lines.append("```")
    return "\n".join(lines)


def _write_todo_view_page(
    path: Path,
    *,
    title: str,
    tags: list[str],
    filters_active: list[str],
    filters_done: list[str],
    group_by_active: Optional[str] = _GROUP_BY_CLIENT,
    group_by_done: Optional[str] = None,
    recently_window: str = "30 days ago",
    recently_label: str = "Ostatnio wykonane (30 dni)",
    extra_frontmatter: Optional[dict] = None,
    intro: Optional[str] = None,
    archive_limit: int = 200,
    owner_split: bool = False,
) -> None:
    fm: dict = {
        "type": "todo-tasks-view",
        "domain": "work",
        "tags": tags,
    }
    if extra_frontmatter:
        fm.update(extra_frontmatter)

    body_lines = [
        "> [!info] Live counts",
        "> Renderowane przez Tasks plugin. Zaznaczenie checkbox w wyniku "
        "aktualizuje source meeting page.",
        "",
    ]
    if intro:
        body_lines += [intro, ""]

    if owner_split:
        # Split active tasks by owner heading (### Person). "Mine" = the heading
        # contains a full (multi-word) owner name, so a colleague who merely
        # shares a first name is not miscounted. Config-driven via me_owner_names();
        # no real identity in the public repo.
        _full = sorted(n.strip().lower() for n in me_owner_names() if " " in n.strip())
        _arr = "[" + ", ".join("'" + n.replace("'", "\\'") + "'" for n in _full) + "]"
        _is_mine = f"{_arr}.some(n => (task.heading || '').toLowerCase().includes(n))"
        active_part = [
            "## 📌 Moje",
            "",
            _render_tasks_query(
                filters=filters_active + [f"filter by function {_is_mine}"],
                sort="due",
                group_by=group_by_active,
            ),
            "",
            "## 👥 Pozostałe",
            "",
            _render_tasks_query(
                filters=filters_active + [f"filter by function !({_is_mine})"],
                sort="due",
                group_by=group_by_active,
            ),
        ]
    else:
        active_part = [
            "## Aktywne",
            "",
            _render_tasks_query(
                filters=filters_active,
                sort="due",
                group_by=group_by_active,
            ),
        ]
    body_lines += active_part + [
        "",
        f"## {recently_label}",
        "",
        "> [!success]- Recently completed",
    ]
    recently_block = _render_tasks_query(
        filters=filters_done,
        done=True,
        done_after=recently_window,
        sort="done reverse",
        group_by=group_by_done,
        limit=50,
    )
    body_lines += ["> " + line for line in recently_block.split("\n")]

    body_lines += [
        "",
        "## Archiwum",
        "",
        "> [!example]- Pełne archiwum (wszystkie done)",
    ]
    archive_block = _render_tasks_query(
        filters=filters_done,
        done=True,
        sort="done reverse",
        group_by='function (task.file.frontmatter?.client || "").replace(/\\[\\[|\\]\\]/g, "") || "_other"',
        limit=archive_limit,
    )
    body_lines += ["> " + line for line in archive_block.split("\n")]

    body = "\n".join(body_lines)
    body_for_hash = re.sub(
        r"^> Ostatnia aktualizacja:.*\n?", "", body, flags=re.MULTILINE
    )
    fm["input_hash"] = _hash_input(
        {
            "_body": body_for_hash,
            "_fm_keys": sorted(k for k in fm if not k.startswith("_")),
        }
    )

    if _write_with_frontmatter(str(path), fm, body, []):
        _wc_pages_written().append(str(path))


def _write_moje_todo_static(
    path: Path,
    meetings: list[dict],
    tenant_id: str,
) -> None:
    from exocortex.action_items import parse_action_items
    from exocortex.db import query as _query

    datetime.now(timezone.utc).strftime("%Y-%m")
    now = datetime.now(timezone.utc)

    client_map: dict[str, str] = {}
    project_map: dict[str, str] = {}
    try:
        edge_rows = _query(
            "SELECT ed.src_id::text AS tid, e.canonical_name, ed.type "
            "  FROM edges ed JOIN entities e ON e.id = ed.dst_id "
            " WHERE ed.tenant_id = %s "
            "   AND ed.type IN ('classified_as_client', 'classified_as_project')",
            tenant_id,
        )
        for er in edge_rows:
            if er["type"] == "classified_as_client":
                client_map.setdefault(er["tid"], er["canonical_name"])
            else:
                project_map.setdefault(er["tid"], er["canonical_name"])
    except Exception:
        pass

    active_items: list[dict] = []
    overdue_items: list[dict] = []
    today = now.date()

    for m in meetings:
        meta = m.get("metadata", {}) or {}
        mtg_client = client_map.get(m["thought_id"], "")
        mtg_project = project_map.get(m["thought_id"], "")
        if mtg_client and mtg_project.startswith(f"{mtg_client}-"):
            mtg_project = mtg_project[len(mtg_client) + 1 :]

        tag_lines: dict[str, list[str]] = {}
        ai_md = m.get("action_items") or meta.get("action_items", "") or ""
        for line in ai_md.split("\n"):
            mch = _CHECKBOX_LINE_RE.match(line.strip())
            if mch:
                text = mch.group(1)
                tags = [t for t in re.findall(r"#([\w-]+)", text)]
                key = text.lower().replace("#", "").strip()[:60]
                tag_lines[key] = tags

        try:
            items = parse_action_items(ai_md, source_thought_id=m["thought_id"])
        except Exception:
            continue

        for it in items:
            if it.status != "open":
                continue
            if it.owner_slug not in me_owner_slugs():
                continue

            key = it.content.lower().replace("#", "").strip()[:60]
            tags = tag_lines.get(key, [])

            item_due = None
            if it.due_date:
                try:
                    item_due = datetime.strptime(it.due_date, "%Y-%m-%d").date()
                except ValueError:
                    pass

            entry = {
                "content": it.content,
                "client": mtg_client,
                "project": mtg_project,
                "tags": tags,
                "due_date": it.due_date or "",
                "meeting_slug": meta.get("slug", ""),
                "overdue": item_due is not None and item_due < today,
            }

            if entry["overdue"]:
                overdue_items.append(entry)
            else:
                active_items.append(entry)

    lines = [
        "# Moje TODO",
        "",
        f"> Ostatnia aktualizacja: {now.strftime('%Y-%m-%d %H:%M UTC')}",
        f"> Aktywne: {len(active_items)} · Overdue: {len(overdue_items)}",
        "",
    ]

    if overdue_items:
        lines += ["## ⚠️ Overdue", ""]
        for ti in overdue_items:
            lines.append(_format_todo_item(ti))
        lines.append("")

    lines += ["## ⚡ Aktywne", ""]
    for ti in active_items:
        lines.append(_format_todo_item(ti))
    lines.append("")

    lines += [
        "## 🔗 Inne widoki TODO",
        "",
        "- [[clients/|Per klient]]",
        "- [[people/|Per osoba]]",
        "- [[this-month|Ten miesiąc]]",
        "",
    ]

    body = "\n".join(lines)
    fm_data: dict[str, Any] = {
        "type": "todo-static-view",
        "domain": "work",
        "tags": ["work", "todo"],
        "input_hash": hashlib.sha256(body.encode()).hexdigest()[:16],
    }
    _write_with_frontmatter(str(path), fm_data, body, source_ids=[])


def _format_todo_item(ti: dict) -> str:
    prefix_parts = []
    if ti.get("client"):
        client_name = ti["client"].replace("-", " ").title()
        prefix_parts.append(f"[[../clients/{ti['client']}|{client_name}]]")
    if ti.get("project"):
        prefix_parts.append(
            f"[[../clients/{ti['client']}#{ti['project']}|{ti['project']}]]"
        )
    tags = ti.get("tags", [])
    tag_str = " " + " ".join(f"#{t}" for t in tags[:4]) if tags else ""
    due = f" 📅 {ti['due_date']}" if ti.get("due_date") else ""
    overdue = " 🔴" if ti.get("overdue") else ""
    prefix = " · ".join(prefix_parts)
    return f"- {prefix}: {ti['content']}{due}{overdue}{tag_str}"


def _scan_meeting_inline_tags(meetings: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for m in meetings:
        ai = m.get("action_items") or ""
        if not ai or "#" not in ai:
            continue
        for line in ai.splitlines():
            cb = _CHECKBOX_LINE_RE.match(line)
            if not cb:
                continue
            for t in _INLINE_TAG_RE.findall(cb.group(1)):
                counts[t.lower()] += 1
    return dict(counts)


def _write_todo_by_tag_page(by_tag_dir: Path, tag: str, count: int) -> None:
    fm: dict = {
        "type": "todo-by-tag-view",
        "domain": "work",
        "tag": tag,
        "task_count": count,
        "tags": ["work", "todo", "by-tag", tag],
    }

    body_lines = [
        f"# Tasks: #{tag}",
        "",
        "> [!info] Live counts",
        "> Renderowane przez Tasks plugin. Zaznaczenie checkbox aktualizuje "
        "source meeting page. Próg widoczności: ≥3 wystąpienia.",
        "",
        "## Aktywne",
        "",
        _render_tasks_query(
            filters=[f"tags include #{tag}"],
            sort="due",
            group_by="happens",
        ),
        "",
        "## Ostatnio wykonane (30 dni)",
        "",
        "> [!success]- Recently completed",
    ]
    recently_block = _render_tasks_query(
        filters=[f"tags include #{tag}"],
        done=True,
        done_after="30 days ago",
        sort="done reverse",
        group_by=None,
        limit=50,
    )
    body_lines += ["> " + line for line in recently_block.split("\n")]

    body_lines += [
        "",
        "## Archiwum",
        "",
        "> [!example]- Pełne archiwum (wszystkie done)",
    ]
    archive_block = _render_tasks_query(
        filters=[f"tags include #{tag}"],
        done=True,
        sort="done reverse",
        group_by=None,
        limit=200,
    )
    body_lines += ["> " + line for line in archive_block.split("\n")]

    body = "\n".join(body_lines)
    fm["input_hash"] = _hash_input(
        {
            "_body": body,
            "_fm_keys": sorted(k for k in fm if not k.startswith("_")),
            "_count": count,
        }
    )

    path = by_tag_dir / f"{tag}.md"
    if _write_with_frontmatter(str(path), fm, body, []):
        _wc_pages_written().append(str(path))


def _todo_owner_display(slug: str, names: set[str]) -> str:
    if slug in me_owner_slugs():
        return "Exocortex user"
    if slug == "_collective":
        return "Zespół / wszyscy"
    if names:
        return sorted(names, key=lambda n: (-len(n), n))[0]
    return slug.replace("-", " ").title()


def _todo_heading_token(slug: str, names: set[str]) -> str:
    if names:
        candidate = sorted(names, key=lambda n: (-len(n), n))[0]
        first = candidate.strip().split()[0] if candidate.strip() else ""
        if first:
            return first
    parts = slug.split("-")
    return parts[0].title() if parts else slug


def _write_todo_pages(work_root: Path, meetings: list[dict], tenant_id: str) -> None:
    entries = _todo_collect(meetings)

    owner_names: dict[str, set[str]] = defaultdict(set)
    seen_owners: set[str] = set()
    seen_clients: set[str] = set()
    for e in entries:
        slug = e["item"].get("owner_slug") or ""
        if slug:
            owner_names[slug].add(e["item"].get("owner_name") or "")
            seen_owners.add(slug)
        cs = e["meeting"].get("client_slug")
        if cs:
            seen_clients.add(cs)

    week_start, week_end = _iso_week_bounds()

    _write_moje_todo_static(
        work_root / "TODO" / "Moje TODO.md",
        meetings,
        tenant_id,
    )

    month_start, month_end = _iso_month_bounds()
    # "This month" = action items from meetings HELD this month. Fireflies items
    # carry no due date (0/4136 on the wiki), so a due-date filter matches nothing;
    # filter by the meeting page's `date` frontmatter instead. Needs Tasks "custom
    # searches" (JS) enabled; the frontmatter value is a quoted ISO string.
    _mdate = "String(task.file.frontmatter?.date || '').slice(0, 10)"
    _in_month = (
        f"filter by function {_mdate} >= '{month_start}' "
        f"&& {_mdate} <= '{month_end}'"
    )

    _write_todo_view_page(
        work_root / "TODO" / "this-month.md",
        title=f"TODO — ten miesiąc ({month_start} → {month_end})",
        tags=["work", "todo", "this-month"],
        filters_active=[_in_month],
        filters_done=[_in_month],
        recently_window=_offset_iso(month_start, -1),
        recently_label=f"Done w tym miesiącu ({month_start} → {month_end})",
        owner_split=True,
    )

    written_people = 0
    for slug in sorted(seen_owners):
        if slug in me_owner_slugs() or slug == "_collective":
            continue
        names = owner_names.get(slug, set())
        token = _todo_heading_token(slug, names)
        person_filter = f"heading includes {token}"
        display = _todo_owner_display(slug, names)
        _write_todo_view_page(
            work_root / "TODO" / "people" / f"{slug}.md",
            title=f"TODO — {display}",
            tags=["work", "todo", slug],
            filters_active=[person_filter],
            filters_done=[person_filter],
            extra_frontmatter={
                "person_slug": slug,
                "person_name": display,
            },
        )
        written_people += 1

    collective_filter = (
        "filter by function (task.heading || '').toLowerCase()"
        ".match(/^(wszyscy|zespol|zespół|nieprzypisane|team)$/i)"
    )
    _write_todo_view_page(
        work_root / "TODO" / "people" / "_collective.md",
        title="TODO — Zespół / wszyscy",
        tags=["work", "todo", "_collective"],
        filters_active=[collective_filter],
        filters_done=[collective_filter],
    )

    written_clients = 0
    for cs in sorted(seen_clients):
        client_filter = (
            f"filter by function (task.file.frontmatter?.client || '').includes('{cs}')"
        )
        _write_todo_view_page(
            work_root / "TODO" / "clients" / f"{cs}.md",
            title=f"TODO — {_client_display(cs)}",
            tags=["work", "todo", cs],
            filters_active=[client_filter],
            filters_done=[client_filter],
            group_by_active="heading",
            extra_frontmatter={"client_slug": cs},
        )
        written_clients += 1

    by_tag_dir = work_root / "TODO" / "by-tag"
    by_tag_dir.mkdir(parents=True, exist_ok=True)
    tag_counts = _scan_meeting_inline_tags(meetings)
    eligible_tags = sorted(
        ((t, c) for t, c in tag_counts.items() if c >= 3),
        key=lambda tc: (-tc[1], tc[0]),
    )
    written_tags = 0
    for tag, count in eligible_tags:
        _write_todo_by_tag_page(by_tag_dir, tag, count)
        written_tags += 1

    _write_todo_index(
        work_root,
        week_start,
        week_end,
        written_people=written_people,
        written_clients=written_clients,
        top_tags=[(t, c) for t, c in eligible_tags[:10]],
    )

    print(
        f"[wiki_compiler] TODO: index + exocortex_user + this-month + "
        f"_collective + {written_people} people + {written_clients} clients "
        f"+ {written_tags} by-tag"
    )


def _write_todo_index(
    work_root: Path,
    week_start: str,
    week_end: str,
    *,
    written_people: int,
    written_clients: int,
    top_tags: Optional[list[tuple[str, int]]] = None,
) -> None:
    fm: dict = {
        "type": "todo-moc",
        "domain": "work",
        "tags": ["work", "todo", "moc"],
    }
    top_tags = top_tags or []

    body_lines = [
        "# TODO — index",
        "",
        "> Live stats z Tasks plugin (nie cache). "
        f"Tydzień: **{week_start} → {week_end}**.",
        "",
        "## Quick links",
        "",
        "- [[Moje TODO]]",
        "- [[this-month|Ten miesiąc]]",
        "- [[people/_collective|Zespół / wszyscy]]",
        "",
        "> [!info] Long-term initiatives",
        "> Większe projekty / F-phase plan → "
        "[[_ Second Brain/backlog/_view-second-brain|Backlog Kanban]]. "
        "TODO = operational z meetingów, Backlog = długoterminowe inicjatywy. "
        "Patrz [[_ Second Brain/backlog/_README|backlog/_README]].",
        "",
    ]
    if top_tags:
        body_lines.append("## Top tags")
        body_lines.append("")
        for t, c in top_tags:
            body_lines.append(f"- [[by-tag/{t}|#{t}]] — {c}")
        body_lines.append("")
    body_lines += [
        "## Sumarycznie (open per owner)",
        "",
        _render_tasks_query(
            filters=[],
            sort="",
            group_by="function (task.heading || '_no_owner')",
            hide=["everything"],
            extra=["short mode"],
        ),
        "",
        "## Per klient",
        "",
        "```dataview",
        'TABLE WITHOUT ID file.link AS "Klient"',
        'FROM "wiki/work/TODO/clients"',
        'WHERE type = "todo-tasks-view"',
        "SORT file.name ASC",
        "```",
        "",
        "## Per osoba (top 30)",
        "",
        "```dataview",
        'TABLE WITHOUT ID file.link AS "Osoba"',
        'FROM "wiki/work/TODO/people"',
        'WHERE type = "todo-tasks-view"',
        "SORT file.name ASC",
        "LIMIT 30",
        "```",
        "",
        "## Overdue (live)",
        "",
        _render_tasks_query(
            filters=["due before today"],
            sort="due",
            group_by=_GROUP_BY_CLIENT,
            limit=30,
        ),
        "",
        "## Done last 7 days (live)",
        "",
        _render_tasks_query(
            filters=[],
            done=True,
            done_after="7 days ago",
            sort="done reverse",
            group_by=None,
            limit=20,
        ),
        "",
        "## Without owner",
        "",
        _render_tasks_query(
            filters=[
                "filter by function (task.heading || '').toLowerCase()"
                ".match(/^(wszyscy|zespol|zespół|nieprzypisane|team)$/i)"
            ],
            sort="due",
            group_by=_GROUP_BY_CLIENT,
            limit=30,
        ),
        "",
        "## Bez due-date",
        "",
        _render_tasks_query(
            filters=["no due date"],
            sort=None,
            group_by="function (task.heading || '_no_owner')",
            limit=50,
        ),
        "",
        "## High-priority (#urgent)",
        "",
        _render_tasks_query(
            filters=["tags include #urgent"],
            sort="due",
            group_by=_GROUP_BY_CLIENT,
        ),
    ]
    body = "\n".join(body_lines)
    fm["input_hash"] = _hash_input(
        {
            "_body": body,
            "_fm_keys": sorted(k for k in fm if not k.startswith("_")),
            "_counts": {"people": written_people, "clients": written_clients},
        }
    )

    path = work_root / "TODO" / "index.md"
    if _write_with_frontmatter(str(path), fm, body, []):
        _wc_pages_written().append(str(path))


# ---------------------------------------------------------------------------
# Person pages
# ---------------------------------------------------------------------------


def _render_person_body(
    slug: str,
    email: str,
    meetings: list[dict],
    fm: dict,
    syn: Optional[dict],
    meeting_index: dict[str, dict],
    related_decision_lines: Optional[list[str]] = None,
    related_problem_lines: Optional[list[str]] = None,
    co_meeting_lines: Optional[list[str]] = None,
) -> str:
    lines: list[str] = []
    lines += _render_synthesis_banner(
        syn, len(meetings), extra=f"osoba: **{email or slug}**"
    )
    if syn and syn.get("content"):
        lines += _format_synthesis_sections(syn["content"], syn, meeting_index)
    if related_decision_lines:
        lines += related_decision_lines
    if related_problem_lines:
        lines += related_problem_lines
    if co_meeting_lines:
        lines += co_meeting_lines

    lines += [
        "## Statystyki",
        "",
        f"- **Email:** {email}",
        f"- **Spotkań:** {fm['meeting_count']}",
        f"- **Okres:** {fm['first_seen']} → {fm['last_seen']}",
        "",
    ]

    lines += [
        "## Spotkania",
        "",
        "```dataview",
        "TABLE WITHOUT ID",
        '  file.link AS "Spotkanie",',
        '  date AS "Data",',
        '  client AS "Klient",',
        '  participant_count AS "Osób"',
        'FROM "wiki/work/meetings/src"',
        f"WHERE contains(participants, [[{slug}]])",
        "SORT date DESC",
        "```",
    ]
    return "\n".join(lines)


def _write_person_pages(
    work_root: Path,
    meetings: list[dict],
    syntheses: dict[tuple[str, str], dict],
    meeting_index: dict[str, dict],
    edges_index: Optional["EdgesIndex"] = None,
    syntheses_by_id: Optional[dict[str, dict]] = None,
) -> None:
    garbage_skipped = sum(
        1 for (ptype, pkey) in syntheses if ptype == "person" and "," in pkey
    )
    if garbage_skipped:
        print(
            f"[wiki_compiler] people: skipped {garbage_skipped} comma-separated "
            f"synthesis keys (F4.6.5 pending fix)"
        )

    by_person: dict[str, list[dict]] = defaultdict(list)
    person_emails: dict[str, str] = {}
    for m in meetings:
        for slug, email in zip(m["participants_slugs"], m["participants_emails"]):
            if not slug:
                continue
            by_person[slug].append(m)
            person_emails.setdefault(slug, email)

    pages_written = _wc_pages_written()
    written, skipped = 0, 0
    for slug, ms in by_person.items():
        email = person_emails.get(slug, "")
        ms_sorted = sorted(ms, key=lambda x: x["date"], reverse=True)
        dated = [m["date"] for m in ms_sorted if m["date"]]
        first = min(dated) if dated else None
        last = max(dated) if dated else None
        total_min = sum(m["duration_minutes"] for m in ms_sorted)
        projects_set = sorted({p for m in ms_sorted for p in m["projects"]})

        co: Counter[str] = Counter()
        for m in ms_sorted:
            for s in m["participants_slugs"]:
                if s and s != slug and s not in me_owner_slugs():
                    co[s] += 1
        co_part = [s for s, _ in co.most_common(5)]

        is_internal = _is_internal(email)
        person_domain = (
            email.split("@", 1)[-1].lower() if email and "@" in email else ""
        )

        if "," in email or "," in slug:
            syn = None
        else:
            syn = syntheses.get(("person", email)) or syntheses.get(("person", slug))

        related_dec_lines: list[str] = []
        related_prob_lines: list[str] = []
        co_meeting_lines: list[str] = []
        rel_sids: list[str] = []
        mentioning_sids: list[str] = []
        if edges_index and syntheses_by_id:
            entity_meeting_ids = [str(m["thought_id"]) for m in ms_sorted]
            rel_sids = _collect_related_syntheses_for_meetings(
                entity_meeting_ids,
                edges_index,
                syntheses_by_id,
                own_perspective=("person", email) if email else ("person", slug),
            )
            mentioning_sids = list(
                edges_index.mentions_synthesis_by_person.get(slug, [])
            )
            set(mentioning_sids)

            related_dec_lines = _render_related_decisions(
                rel_sids, syntheses_by_id, meeting_index
            )
            related_prob_lines = _render_related_problems(
                rel_sids, syntheses_by_id, meeting_index
            )

            mention_only_sids = [
                sid for sid in mentioning_sids if sid not in set(rel_sids)
            ]
            if mention_only_sids:
                mention_lines = _render_related_decisions(
                    mention_only_sids,
                    syntheses_by_id,
                    meeting_index,
                    title="Wzmiankowane decyzje (z innych perspektyw)",
                    limit=8,
                )
                if mention_lines:
                    related_dec_lines = related_dec_lines + mention_lines

            if co_part:
                co_meeting_lines = ["## Wspólne meetings", ""]
                for s, n in co.most_common(5):
                    co_meeting_lines.append(f"- [[{s}]] — {n} wspólnych spotkań")
                co_meeting_lines.append("")

        fm: dict = {
            "type": "person",
            "domain": "work",
            "person": slug,
            "title": _resolve_person_display(slug, email),
            "person_display": _resolve_person_display(slug, email),
            "person_email": email,
            "person_domain": person_domain,
            "is_internal": is_internal,
            "meeting_count": len(ms_sorted),
            "first_seen": first,
            "last_seen": last,
            "projects": [f"[[{p}]]" for p in projects_set],
            "co_participants": [f"[[{s}]]" for s in co_part],
            "total_minutes_together": int(round(total_min)),
            "tags": ["work", "person", "internal" if is_internal else "external"],
        }
        fm.update(_synthesis_fm_fields(syn))
        fm["input_hash"] = _hash_input(
            {
                **fm,
                "_meetings": sorted(m["slug"] for m in ms_sorted),
                "_related_syntheses": rel_sids,
                "_mention_syntheses": mentioning_sids,
            }
        )

        path = work_root / "people" / f"{slug}.md"
        body = _render_person_body(
            slug,
            email,
            ms_sorted,
            fm,
            syn,
            meeting_index,
            related_dec_lines,
            related_prob_lines,
            co_meeting_lines,
        )
        if _write_with_frontmatter(
            str(path), fm, body, [m["source_id"] for m in ms_sorted]
        ):
            pages_written.append(str(path))
            written += 1
        else:
            skipped += 1
    print(f"[wiki_compiler] people: wrote {written}, skipped {skipped} unchanged")


# ---------------------------------------------------------------------------
# Monthly pages
# ---------------------------------------------------------------------------


def _render_monthly_body(
    month: str,
    meetings: list[dict],
    fm: dict,
    syn: Optional[dict],
    meeting_index: dict[str, dict],
    related_decision_lines: Optional[list[str]] = None,
    related_problem_lines: Optional[list[str]] = None,
) -> str:
    lines: list[str] = []

    nav = []
    if fm.get("prev_month"):
        nav.append(f"← {fm['prev_month']}")
    if fm.get("next_month"):
        nav.append(f"{fm['next_month']} →")
    if nav:
        lines += [" · ".join(nav), ""]

    lines += _render_synthesis_banner(syn, len(meetings), extra=f"miesiąc: **{month}**")
    if syn and syn.get("content"):
        lines += _format_synthesis_sections(syn["content"], syn, meeting_index)
    if related_decision_lines:
        lines += related_decision_lines
    if related_problem_lines:
        lines += related_problem_lines

    lines += [
        "## Statystyki",
        "",
        f"- **Spotkań:** {fm['meeting_count']}",
        f"- **Łączny czas:** {fm['duration_total_minutes']} min",
        "",
    ]

    lines += [
        "## Spotkania",
        "",
        "```dataview",
        "TABLE WITHOUT ID",
        '  file.link AS "Spotkanie",',
        '  date AS "Data",',
        '  client AS "Klient",',
        '  duration_minutes AS "Min"',
        'FROM "wiki/work/meetings/src"',
        f'WHERE type = "meeting" AND startswith(string(date), "{month}")',
        "SORT date DESC",
        "```",
    ]
    return "\n".join(lines)


def _write_monthly_pages(
    work_root: Path,
    meetings: list[dict],
    syntheses: dict[tuple[str, str], dict],
    meeting_index: dict[str, dict],
    edges_index: Optional["EdgesIndex"] = None,
    syntheses_by_id: Optional[dict[str, dict]] = None,
) -> None:
    by_month: dict[str, list[dict]] = defaultdict(list)
    for m in meetings:
        if m["month"]:
            by_month[m["month"]].append(m)

    months_sorted = sorted(by_month.keys())
    pages_written = _wc_pages_written()
    written, skipped = 0, 0
    for i, month in enumerate(months_sorted):
        ms = by_month[month]
        prev_m = months_sorted[i - 1] if i > 0 else None
        next_m = months_sorted[i + 1] if i + 1 < len(months_sorted) else None

        total_min = sum(m["duration_minutes"] for m in ms)
        projects = sorted({p for m in ms for p in m["projects"]})
        cnt: Counter[str] = Counter()
        for m in ms:
            for s in m["participants_slugs"]:
                if s and s != "unknown" and s not in me_owner_slugs():
                    cnt[s] += 1
        top = [s for s, _ in cnt.most_common(5)]

        year, mn = month.split("-") if "-" in month else ("0", "0")
        syn = syntheses.get(("monthly", month))

        related_dec_lines: list[str] = []
        related_prob_lines: list[str] = []
        rel_sids: list[str] = []
        if edges_index and syntheses_by_id:
            entity_meeting_ids = [str(m["thought_id"]) for m in ms]
            rel_sids = _collect_related_syntheses_for_meetings(
                entity_meeting_ids,
                edges_index,
                syntheses_by_id,
                own_perspective=("monthly", month),
            )
            related_dec_lines = _render_related_decisions(
                rel_sids,
                syntheses_by_id,
                meeting_index,
                title="Decyzje miesiąca (z innych perspektyw)",
            )
            related_prob_lines = _render_related_problems(
                rel_sids,
                syntheses_by_id,
                meeting_index,
                title="Problemy zgłoszone w tym miesiącu",
            )

        fm: dict = {
            "type": "monthly",
            "domain": "work",
            "title": month,
            "month": month,
            "year": int(year),
            "month_num": int(mn),
            "meeting_count": len(ms),
            "duration_total_minutes": int(round(total_min)),
            "projects": [f"[[{p}]]" for p in projects],
            "top_participants": [f"[[{s}]]" for s in top],
            "prev_month": f"[[{prev_m}]]" if prev_m else None,
            "next_month": f"[[{next_m}]]" if next_m else None,
            "tags": ["work", "monthly", year],
        }
        fm.update(_synthesis_fm_fields(syn))
        fm = {k: v for k, v in fm.items() if v is not None}
        fm["input_hash"] = _hash_input(
            {
                **fm,
                "_meetings": sorted(m["slug"] for m in ms),
                "_related_syntheses": rel_sids,
            }
        )

        path = work_root / "monthly" / f"{month}.md"
        body = _render_monthly_body(
            month, ms, fm, syn, meeting_index, related_dec_lines, related_prob_lines
        )
        if _write_with_frontmatter(str(path), fm, body, [m["source_id"] for m in ms]):
            pages_written.append(str(path))
            written += 1
        else:
            skipped += 1
    print(f"[wiki_compiler] monthly: wrote {written}, skipped {skipped} unchanged")


# ---------------------------------------------------------------------------
# MOC pages
# ---------------------------------------------------------------------------


def _write_work_moc(work_root: Path, meetings: list[dict]) -> None:
    fm: dict = {
        "type": "moc",
        "domain": "work",
        "moc_of": "work",
        "total_count": len(meetings),
        "input_hash": _hash_input(sorted(m["slug"] for m in meetings)),
    }
    body_lines = ["# Work — Dashboard", ""]
    if len(meetings) > LLM_THRESHOLDS["moc"]:
        try:
            summary, tokens = _summarize_workdash(meetings)
            _wc_llm_tokens_used_add(tokens)
            body_lines += [f"> {summary}", ""]
        except Exception as e:
            logging.warning("[wiki_compiler] workdash LLM failed: %r", e)

    body_lines += [
        "## Top klienci",
        "",
        "```dataview",
        "TABLE WITHOUT ID",
        '  file.link AS "Klient",',
        '  meeting_count AS "Spotkań",',
        '  duration_total_minutes AS "Min",',
        '  last_meeting AS "Ostatnie"',
        'FROM "wiki/work/clients"',
        'WHERE type = "client" AND !startswith(file.name, "_")',
        "SORT meeting_count DESC",
        "LIMIT 10",
        "```",
        "",
        "## Najczęściej spotykani (top 15)",
        "",
        "```dataview",
        "TABLE WITHOUT ID",
        '  file.link AS "Osoba",',
        '  meeting_count AS "Spotkań",',
        '  is_internal AS "Wewn.",',
        '  last_seen AS "Ostatnio"',
        'FROM "wiki/work/people"',
        'WHERE type = "person"',
        "SORT meeting_count DESC",
        "LIMIT 15",
        "```",
        "",
        "## Ostatnie 30 dni",
        "",
        "```dataview",
        "TABLE WITHOUT ID",
        '  file.link AS "Spotkanie",',
        '  date AS "Data",',
        '  client AS "Klient",',
        '  participant_count AS "Osób"',
        'FROM "wiki/work/meetings/src"',
        'WHERE type = "meeting" AND date >= date(today) - dur(30 days)',
        "SORT date DESC",
        "```",
        "",
        "## Aktywność miesięczna",
        "",
        "```dataview",
        "TABLE WITHOUT ID",
        '  file.link AS "Miesiąc",',
        '  meeting_count AS "Spotkań",',
        '  duration_total_minutes AS "Min"',
        'FROM "wiki/work/monthly"',
        'WHERE type = "monthly"',
        "SORT month DESC",
        "LIMIT 12",
        "```",
    ]
    path = work_root / "_moc.md"
    if _write_with_frontmatter(
        str(path), fm, "\n".join(body_lines), [m["source_id"] for m in meetings]
    ):
        _wc_pages_written().append(str(path))


def _write_projects_moc(work_root: Path, meetings: list[dict]) -> None:
    clients = sorted(
        {
            m.get("client_slug") or (m["projects"][0] if m.get("projects") else None)
            for m in meetings
        }
        - {None}
    )
    fm: dict = {
        "type": "moc",
        "domain": "work",
        "moc_of": "client",
        "total_count": len(clients),
        "input_hash": _hash_input(list(clients)),
    }
    body = (
        "# Klienci\n\n"
        "```dataview\n"
        "TABLE WITHOUT ID\n"
        '  file.link AS "Klient",\n'
        '  meeting_count AS "Spotkań",\n'
        '  first_meeting AS "Od",\n'
        '  last_meeting AS "Do",\n'
        '  meeting_types AS "Typy"\n'
        'FROM "wiki/work/clients"\n'
        'WHERE type = "client" AND !startswith(file.name, "_")\n'
        "SORT meeting_count DESC\n"
        "```\n"
    )
    path = work_root / "clients" / "_moc.md"
    if _write_with_frontmatter(str(path), fm, body, [m["source_id"] for m in meetings]):
        _wc_pages_written().append(str(path))


def _write_people_moc(work_root: Path, meetings: list[dict]) -> None:
    people: set[str] = set()
    for m in meetings:
        for s in m["participants_slugs"]:
            if s:
                people.add(s)
    fm: dict = {
        "type": "moc",
        "domain": "work",
        "moc_of": "person",
        "total_count": len(people),
        "input_hash": _hash_input(sorted(people)),
    }
    body = (
        "# Osoby\n\n"
        "## Wewnętrzne (EFI)\n\n"
        "```dataview\n"
        "TABLE WITHOUT ID\n"
        '  file.link AS "Osoba",\n'
        '  meeting_count AS "Spotkań",\n'
        '  projects AS "Projekty",\n'
        '  last_seen AS "Ostatnio"\n'
        'FROM "wiki/work/people"\n'
        'WHERE type = "person" AND is_internal = true\n'
        "SORT meeting_count DESC\n"
        "```\n\n"
        "## Zewnętrzne\n\n"
        "```dataview\n"
        "TABLE WITHOUT ID\n"
        '  file.link AS "Osoba",\n'
        '  person_domain AS "Org.",\n'
        '  meeting_count AS "Spotkań",\n'
        '  projects AS "Projekty",\n'
        '  last_seen AS "Ostatnio"\n'
        'FROM "wiki/work/people"\n'
        'WHERE type = "person" AND is_internal = false\n'
        "SORT meeting_count DESC\n"
        "```\n"
    )
    path = work_root / "people" / "_moc.md"
    if _write_with_frontmatter(str(path), fm, body, [m["source_id"] for m in meetings]):
        _wc_pages_written().append(str(path))


def _write_monthly_moc(work_root: Path, meetings: list[dict]) -> None:
    months = sorted({m["month"] for m in meetings if m.get("month")})
    fm: dict = {
        "type": "moc",
        "domain": "work",
        "moc_of": "monthly",
        "total_count": len(months),
        "input_hash": _hash_input(months),
    }
    body = (
        "# Miesiące\n\n"
        "```dataview\n"
        "TABLE WITHOUT ID\n"
        '  file.link AS "Miesiąc",\n'
        '  meeting_count AS "Spotkań",\n'
        '  duration_total_minutes AS "Min",\n'
        '  projects AS "Projekty"\n'
        'FROM "wiki/work/monthly"\n'
        'WHERE type = "monthly"\n'
        "SORT month DESC\n"
        "```\n"
    )
    path = work_root / "monthly" / "_moc.md"
    if _write_with_frontmatter(str(path), fm, body, [m["source_id"] for m in meetings]):
        _wc_pages_written().append(str(path))


# ---------------------------------------------------------------------------
# _ensure_index_stubs (called by compile_work_module)
# ---------------------------------------------------------------------------


def _ensure_index_stubs(wiki_root: Path) -> None:
    idx = wiki_root / "_index"
    idx.mkdir(parents=True, exist_ok=True)

    p_people = idx / "people.md"
    if not p_people.exists():
        fm: dict = {
            "type": "index",
            "index_of": "people",
            "schema_version": SCHEMA_VERSION,
            "input_hash": _hash_input(["_index_people_stub"]),
        }
        body = (
            "# All People (cross-domain)\n\n"
            "```dataview\n"
            "TABLE WITHOUT ID\n"
            '  file.link AS "Osoba",\n'
            '  domain AS "Domena",\n'
            '  meeting_count AS "Spotkań",\n'
            '  last_seen AS "Ostatnio"\n'
            'FROM "wiki/work/people"\n'
            'WHERE type = "person"\n'
            "SORT meeting_count DESC\n"
            "```\n"
        )
        if _write_with_frontmatter(str(p_people), fm, body, []):
            _wc_pages_written().append(str(p_people))

    p_recent = idx / "recent.md"
    if not p_recent.exists():
        fm = {
            "type": "index",
            "index_of": "recent",
            "schema_version": SCHEMA_VERSION,
            "input_hash": _hash_input(["_index_recent_stub"]),
        }
        body = (
            "# Recent Activity (cross-domain)\n\n"
            "```dataview\n"
            "TABLE WITHOUT ID\n"
            '  file.link AS "Wpis",\n'
            "  type,\n"
            "  domain,\n"
            "  date\n"
            'FROM "wiki"\n'
            "WHERE date AND date >= date(today) - dur(30 days)\n"
            "SORT date DESC\n"
            "```\n"
        )
        if _write_with_frontmatter(str(p_recent), fm, body, []):
            _wc_pages_written().append(str(p_recent))

    p_tags = idx / "tags.md"
    if not p_tags.exists():
        fm = {
            "type": "index",
            "index_of": "tags",
            "schema_version": SCHEMA_VERSION,
            "input_hash": _hash_input(["_index_tags_stub"]),
        }
        body = "# Tags\n\nUżyj Obsidian tag pane (sidebar po prawej).\n"
        if _write_with_frontmatter(str(p_tags), fm, body, []):
            _wc_pages_written().append(str(p_tags))


# ---------------------------------------------------------------------------
# LLM summarizer (work dashboard only)
# ---------------------------------------------------------------------------


_WORKDASH_SUMMARY_SCHEMA = {
    "name": "workdash_summary",
    "description": "Zwięzłe podsumowanie aktywności zawodowej (2-4 zdania).",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
        },
        "required": ["summary"],
        "additionalProperties": False,
    },
}


def _summarize_workdash(meetings: list[dict]) -> tuple[str, int]:
    """Generate 2-4 sentence overall summary for the Work dashboard.

    Routed through llm_router (not a direct Anthropic client) so it shares
    the same local-only path — K12: 127.0.0.1:8080 — as every other LLM
    call in the codebase. This used to be the one call site that bypassed
    llm_router entirely (legacy, predates it); since fixed.
    """
    proj_counter: Counter[str] = Counter()
    type_counter: Counter[str] = Counter()
    for m in meetings:
        for p in m["projects"]:
            proj_counter[p] += 1
        type_counter[m["meeting_type"] or "unspecified"] += 1
    top_projects = ", ".join(f"{p}({n})" for p, n in proj_counter.most_common(8))
    top_types = ", ".join(f"{t}({n})" for t, n in type_counter.most_common(6))
    dates = sorted([m["date"] for m in meetings if m.get("date")])
    period = f"{dates[0]} → {dates[-1]}" if dates else "?"

    from exocortex import llm_routing
    llm_routing.initialize()
    from llm_router import call_tool as _router_call_tool

    tool_input, usage = _router_call_tool(
        use_case="second_brain.F31_wiki_workdash_summary",
        system=(
            "Jesteś asystentem knowledge management. Piszesz zwięzłe podsumowania "
            "całokształtu pracy danej osoby na podstawie statystyk spotkań. "
            "Odpowiadasz zawsze po polsku. Bądź konkretny i faktyczny — bez ozdobników. "
            "Wywołaj narzędzie `workdash_summary` z polem summary."
        ),
        user=(
            f"Napisz podsumowanie aktywności zawodowej w 2-4 zdaniach.\n"
            f"Okres: {period}\n"
            f"Łącznie spotkań: {len(meetings)}\n"
            f"Top projekty: {top_projects}\n"
            f"Typy spotkań: {top_types}\n\n"
            f"Skup się na: dominujących obszarach, kierunkach, intensywności pracy."
        ),
        schema=_WORKDASH_SUMMARY_SCHEMA,
        max_tokens=400,
        cache_system=False,
    )
    summary = (tool_input.get("summary") or "").strip()
    tokens = usage.input_tokens + usage.output_tokens
    return summary, tokens


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def compile_work_module(tenant_id: str, since: Optional[datetime]) -> None:
    """Compile Work domain wiki — atomic file model (v2).

    Generates 1 file per meeting + aggregated entity pages (projects, people,
    monthly) + 4 MOCs + cross-domain stubs. Wikilinks in YAML enable Obsidian
    Dataview to JOIN across files.
    """
    import exocortex.wiki_compiler as _wc

    meetings = _load_work_meetings(None, tenant_id, since)
    if not meetings:
        print("[wiki_compiler] no work meetings to compile")
        return

    wiki_root = _get_wiki_root()
    work_root = wiki_root / "work"
    for sub in (
        "meetings",
        "clients",
        "projects",
        "people",
        "monthly",
        "decisions",
        "by-tag",
        "TODO",
        "TODO/people",
        "TODO/clients",
    ):
        (work_root / sub).mkdir(parents=True, exist_ok=True)

    syntheses = _load_active_syntheses(tenant_id)
    syntheses_by_id = {str(s["id"]): s for s in syntheses.values()}
    edges_index = _load_edges_index(tenant_id)
    meeting_index = {str(m["thought_id"]): m for m in meetings}
    print(
        f"[wiki_compiler] loaded {len(syntheses)} active syntheses "
        f"across {len({k[0] for k in syntheses})} perspective types"
    )

    _safe(_write_meeting_pages, work_root, meetings)

    # Only on a full compile. With `since` set, `meetings` holds just the recent
    # slice, so every page outside that window would look orphaned — the one way
    # this could delete live pages wholesale.
    if since is None:
        _safe(_prune_meeting_orphans, work_root, meetings)

    _safe(
        _write_client_pages,
        work_root,
        meetings,
        syntheses,
        meeting_index,
        edges_index,
        syntheses_by_id,
    )
    _safe(
        _write_subproject_pages,
        work_root,
        meetings,
        syntheses,
        meeting_index,
        edges_index,
        syntheses_by_id,
    )
    _safe(
        _write_person_pages,
        work_root,
        meetings,
        syntheses,
        meeting_index,
        edges_index,
        syntheses_by_id,
    )
    _safe(
        _write_monthly_pages,
        work_root,
        meetings,
        syntheses,
        meeting_index,
        edges_index,
        syntheses_by_id,
    )
    _safe(_write_by_tag_pages, work_root, meetings, syntheses, meeting_index)

    _safe(_write_todo_pages, work_root, meetings, tenant_id)
    _safe(_write_work_moc, work_root, meetings)
    _safe(_write_projects_moc, work_root, meetings)
    _safe(_write_people_moc, work_root, meetings)
    _safe(_write_monthly_moc, work_root, meetings)
    _safe(_ensure_index_stubs, wiki_root)

    _safe(compile_work_clippings, tenant_id, since)

    page_hashes = sorted(_wc._pages_written)
    run_hash = hashlib.sha256("|".join(page_hashes).encode()).hexdigest()[:16]
    if _wc.current_run_id:
        from exocortex.db import execute

        try:
            execute(
                "UPDATE compile_runs SET input_hash = %s WHERE id = %s",
                run_hash,
                _wc.current_run_id,
            )
        except Exception as e:
            logging.warning("[wiki_compiler] failed to persist input_hash: %r", e)
