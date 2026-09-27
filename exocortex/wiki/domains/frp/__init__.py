# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.
"""FRP (Futures Reading Protocol) domain compiler.

Full implementation extracted from wiki_compiler.py (F31.6.2 batch 2).
Contains: _FRP_AXIS_LABELS, _frp_axis_label, compile_frp_module,
_write_frp_perspective_pages, _write_frp_synthesis_page, _write_frp_moc.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from exocortex.wiki.domains.base import _LegacyDomainCompiler
from exocortex.wiki.util.links import _obsidian_advanced_uri

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FRP axis label tables
# ---------------------------------------------------------------------------

_FRP_AXIS_LABELS = {
    "accessibility": {
        0: ("dense", "dense / inaccessible"),
        1: ("requires effort", "requires effort"),
        2: ("approachable", "approachable"),
        3: ("breezy", "breezy short read"),
    },
    "horizon": {
        0: ("present", "present / contemporary"),
        1: ("near-future", "near-future (~5 lat)"),
        2: ("mid-future", "mid-future (~20 lat)"),
        3: ("far-future", "far-future / post-singularity"),
    },
    "consequence": {
        0: ("trivial", "trivial / day-in-the-life"),
        1: ("personal stakes", "personal stakes"),
        2: ("group/community", "group / community"),
        3: ("civilizational", "civilizational / existential"),
    },
}


def _frp_axis_label(axis: str, value: Any, *, short: bool = False) -> str:
    if value is None:
        return "—"
    try:
        v = int(value)
    except (TypeError, ValueError):
        return str(value)
    pair = _FRP_AXIS_LABELS.get(axis, {}).get(v)
    if pair is None:
        return str(v)
    return pair[0] if short else pair[1]


# ---------------------------------------------------------------------------
# Main compiler
# ---------------------------------------------------------------------------


def compile_frp_module(tenant_id: str, since: Optional[datetime]) -> None:
    """Compile FRP domain wiki pages: reading-queue, sessions, materializing."""
    import exocortex.wiki_compiler as _wc
    from exocortex.db import query
    from exocortex.wiki.core.io import write_wiki, _default_wiki_root_str
    from exocortex.wiki.core.edges import _load_active_syntheses

    wiki_root = _default_wiki_root_str()
    if not wiki_root.endswith("/"):
        wiki_root += "/"
    frp_dir = Path(wiki_root + "frp/")
    frp_dir.mkdir(parents=True, exist_ok=True)

    source_ids: list[str] = []

    # ── 1. Reading queue ──────────────────────────────────────────────────
    queue_rows = query(
        """
        SELECT cq.id, cq.score_total, cq.score_accessibility, cq.score_horizon,
               cq.score_consequence, cq.suggested_prompt, cq.scenario_sentence,
               cq.ai_tags, cq.queued_at,
               rs.title AS rs_title, rs.uri AS rs_uri,
               rs.source_name AS rs_source_name, rs.author_name AS rs_author_name
        FROM content_queue cq
        LEFT JOIN raw_sources rs ON rs.id = cq.source_id
        WHERE cq.tenant_id = %s AND cq.status = 'queued'
        ORDER BY cq.score_total DESC NULLS LAST, cq.queued_at DESC
    """,
        tenant_id,
    )
    queue = [
        {
            **{
                k: r[k]
                for k in (
                    "id",
                    "score_total",
                    "score_accessibility",
                    "score_horizon",
                    "score_consequence",
                    "suggested_prompt",
                    "scenario_sentence",
                    "ai_tags",
                    "queued_at",
                )
            },
            "raw_sources": {
                "title": r.get("rs_title"),
                "uri": r.get("rs_uri"),
                "source_name": r.get("rs_source_name"),
                "author_name": r.get("rs_author_name"),
            }
            if r.get("rs_uri") or r.get("rs_title")
            else {},
        }
        for r in queue_rows
    ]

    lines: list[str] = ["# FRP — Reading Queue", ""]
    lines += [
        "> [!tip] Quick-start session",
        "> Klik **▶ Start FRP session** pod notką → 3 popupy (frame radio / level radio / context text) → prompt w clipboard → paste do Claude.",
        '> **One-time setup**: Settings → Templater → (1) Template folder location = `_templates`, (2) Template Hotkeys → "Add new hotkey for template" → wybierz `frp-session-prompt` (hotkey opcjonalny — sam fakt rejestracji włącza Advanced URI command). Pełny manual scoring: [[frp-protocol]].',
        "",
        f"> 📅 **Ostatnia aktualizacja:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]
    if not queue:
        lines += ["*Queue is empty.*", ""]
    else:
        high_pri = [it for it in queue if (it.get("score_total") or 0) >= 7]
        low_pri = [it for it in queue if (it.get("score_total") or 0) < 7]
        lines += [
            f"**{len(queue)} items queued** — {len(high_pri)} wysoki priorytet (≥7) · "
            f"{len(low_pri)} niższy (<7, zwinięty)",
            "",
        ]

        def _render_item(item: dict) -> list[str]:
            rs = item.get("raw_sources") or {}
            title = rs.get("title") or item["id"]
            uri = rs.get("uri", "")
            score = item.get("score_total") or 0
            prompt = item.get("suggested_prompt") or ""
            scenario = item.get("scenario_sentence") or ""
            tags = item.get("ai_tags") or {}
            raw_dom = tags.get("domain") if tags else None
            if isinstance(raw_dom, list):
                domain_tags = ", ".join(str(d) for d in raw_dom)
            elif isinstance(raw_dom, str):
                domain_tags = raw_dom
            else:
                domain_tags = ""
            a_val = item.get("score_accessibility")
            h_val = item.get("score_horizon")
            c_val = item.get("score_consequence")
            out = []
            out.append(f"### [{title}]({uri})" if uri else f"### {title}")
            out.append(f"- **Content ID:** `{item.get('id')}`")
            qat = item.get("queued_at")
            if hasattr(qat, "strftime"):
                out.append(f"- **Dodano:** {qat.strftime('%Y-%m-%d')}")
            out.append(f"- **Score:** {score}/9")
            out.append(
                f"    - Accessibility: {a_val if a_val is not None else '—'} "
                f"({_frp_axis_label('accessibility', a_val)})"
            )
            out.append(
                f"    - Horizon: {h_val if h_val is not None else '—'} "
                f"({_frp_axis_label('horizon', h_val)})"
            )
            out.append(
                f"    - Consequence: {c_val if c_val is not None else '—'} "
                f"({_frp_axis_label('consequence', c_val)})"
            )
            if a_val is not None and h_val is not None and c_val is not None:
                summary_bits = [
                    _frp_axis_label("accessibility", a_val, short=True),
                    _frp_axis_label("horizon", h_val, short=True),
                    _frp_axis_label("consequence", c_val, short=True),
                ]
                out.append(f"- **Summary:** {' · '.join(summary_bits)}")
            if prompt:
                out.append(f"- **Prompt:** {prompt}")
            if domain_tags:
                out.append(f"- **Domains:** {domain_tags}")
            if scenario:
                out.append(f"- *{scenario}*")
            if rs.get("source_name"):
                out.append(f"- Source: {rs['source_name']}")
            cta_uri = _obsidian_advanced_uri(
                f"copytext={item.get('id')}"
                "&commandid=templater-obsidian%3A_templates%2Ffrp-session-prompt.md"
            )
            if cta_uri:
                out.append(f"- [▶ Start FRP session]({cta_uri})")
            out.append("")
            return out

        if high_pri:
            lines.append(f"## Wysoki priorytet (≥7) — {len(high_pri)} items")
            lines.append("")
            for item in high_pri:
                lines.extend(_render_item(item))
                source_ids.append(str(item["id"]))

        if low_pri:
            lines.append(f"## Niższy priorytet (<7) — {len(low_pri)} items")
            lines.append("")
            lines.append("<details>")
            lines.append(
                f"<summary>Kliknij żeby rozwinąć ({len(low_pri)} items)</summary>"
            )
            lines.append("")
            for item in low_pri:
                lines.extend(_render_item(item))
                source_ids.append(str(item["id"]))
            lines.append("</details>")
            lines.append("")

    path_q = str(frp_dir / "reading-queue.md")
    write_wiki(path_q, "\n".join(lines), source_ids[:])
    _wc._pages_written.append(path_q)
    source_ids.clear()

    # ── 2. Sessions ───────────────────────────────────────────────────────
    session_rows = query(
        """
        SELECT fs.id, fs.frame, fs.level, fs.resonance, fs.status, fs.context_note,
               fs.created_at, fs.revisit_due, fs.revisited_at,
               cq.scenario_sentence AS cq_scenario_sentence,
               cq.ai_tags AS cq_ai_tags,
               cq.score_total AS cq_score_total,
               rs.title AS rs_title, rs.uri AS rs_uri, rs.source_name AS rs_source_name
        FROM frp_sessions fs
        LEFT JOIN content_queue cq ON cq.id = fs.content_id
        LEFT JOIN raw_sources rs ON rs.id = cq.source_id
        WHERE fs.tenant_id = %s
        ORDER BY fs.created_at DESC
    """,
        tenant_id,
    )
    sessions = [
        {
            **{
                k: r[k]
                for k in (
                    "id",
                    "frame",
                    "level",
                    "resonance",
                    "status",
                    "context_note",
                    "created_at",
                    "revisit_due",
                    "revisited_at",
                )
            },
            "content_queue": {
                "scenario_sentence": r.get("cq_scenario_sentence"),
                "ai_tags": r.get("cq_ai_tags"),
                "score_total": r.get("cq_score_total"),
                "raw_sources": {
                    "title": r.get("rs_title"),
                    "uri": r.get("rs_uri"),
                    "source_name": r.get("rs_source_name"),
                },
            },
        }
        for r in session_rows
    ]

    # Fetch thoughts per session via edges (batch)
    session_thoughts: dict[str, list[dict]] = {}
    if sessions:
        sess_ids = [str(s["id"]) for s in sessions]
        edges = query(
            """
            SELECT src_id, dst_id
            FROM edges
            WHERE tenant_id = %s
              AND src_type = 'frp_session'
              AND type = 'session_contains'
              AND src_id = ANY(%s::uuid[])
        """,
            tenant_id,
            sess_ids,
        )
        thought_ids = [str(e["dst_id"]) for e in edges]
        thoughts_map: dict[str, dict] = {}
        if thought_ids:
            trows = query(
                """
                SELECT id, body, thought_type
                FROM thoughts
                WHERE id = ANY(%s::uuid[])
            """,
                thought_ids,
            )
            thoughts_map = {str(t["id"]): t for t in trows}
        for edge in edges:
            session_thoughts.setdefault(str(edge["src_id"]), []).append(
                thoughts_map.get(str(edge["dst_id"]), {})
            )

    THOUGHT_LABELS = {
        "frp_scenario": "Scenario",
        "frp_friction": "Friction",
        "frp_recognition": "Recognition",
        "frp_impulse": "Impulse",
        "frp_reflection": "Reflection",
        "frp_revisit": "Revisit",
    }
    STATUS_ORDER = ["active", "revisited", "archived"]

    lines = ["# FRP — Sessions", ""]
    if not sessions:
        lines += ["*No sessions yet.*", ""]
    else:
        by_status: dict[str, list] = {s: [] for s in STATUS_ORDER}
        for sess in sessions:
            by_status.setdefault(sess["status"], []).append(sess)

        for status in STATUS_ORDER:
            group = by_status.get(status, [])
            if not group:
                continue
            lines += [f"## {status.capitalize()} ({len(group)})", ""]
            for sess in group:
                cq = sess.get("content_queue") or {}
                rs = cq.get("raw_sources") or {}
                title = rs.get("title") or sess["id"]
                uri = rs.get("uri", "")
                ca = sess.get("created_at")
                date = (
                    ca.strftime("%Y-%m-%d")
                    if hasattr(ca, "strftime")
                    else (str(ca)[:10] if ca else "")
                )
                frame = sess.get("frame") or "?"
                level = sess.get("level") or "?"
                resonance = sess.get("resonance") or "?"
                score = cq.get("score_total")

                lines.append(
                    f"### [{title}]({uri}) — {date}" if uri else f"### {title} — {date}"
                )
                meta_parts = [
                    f"Frame {frame}",
                    f"Level {level}",
                    f"Resonance {resonance}/5",
                ]
                if score is not None:
                    meta_parts.append(f"Score {score}/9")
                lines.append("- " + " · ".join(meta_parts))
                if sess.get("context_note"):
                    lines.append(f"- *{sess['context_note']}*")
                if sess.get("revisit_due"):
                    lines.append(f"- Revisit due: {sess['revisit_due']}")

                for thought in session_thoughts.get(str(sess["id"]), []):
                    ttype = thought.get("thought_type", "")
                    label = THOUGHT_LABELS.get(ttype, ttype)
                    body = thought.get("body", "")
                    if body:
                        lines.append(f"\n**{label}:** {body}")
                if status in ("active", "revisited"):
                    sid = str(sess["id"])
                    append_uri = _obsidian_advanced_uri(
                        f"session_id={sid}"
                        "&commandid=templater-obsidian%3A_templates%2Ffrp-append-thought.md"
                    )
                    if append_uri:
                        lines.append("")
                        lines.append(f"- [➕ Dopisz refleksję]({append_uri})")
                    rd = sess.get("revisit_due")
                    if rd is not None:
                        from datetime import date as _d  # noqa: PLC0415

                        rd_date = rd if isinstance(rd, _d) else None
                        if rd_date and rd_date <= _d.today():
                            revisit_uri = _obsidian_advanced_uri(
                                f"session_id={sid}"
                                "&commandid=templater-obsidian%3A_templates%2Ffrp-revisit.md"
                            )
                            if revisit_uri:
                                lines.append(
                                    f"- [⟳ Add revisit (post-48h)]({revisit_uri})"
                                )
                lines.append("")
                source_ids.append(str(sess["id"]))

    path_s = str(frp_dir / "sessions.md")
    write_wiki(path_s, "\n".join(lines), source_ids[:])
    _wc._pages_written.append(path_s)
    source_ids.clear()

    # ── 3. Materializing signals ──────────────────────────────────────────
    mat_edges = query(
        """
        SELECT src_id, dst_id, created_at
        FROM edges
        WHERE tenant_id = %s AND type = 'materializes_as'
        ORDER BY created_at DESC
    """,
        tenant_id,
    )

    lines = ["# FRP — Materializing Signals", ""]
    if not mat_edges:
        lines += ["*No materializing signals yet.*", ""]
    else:
        thought_ids_mat = [str(e["src_id"]) for e in mat_edges]
        source_ref_ids = [str(e["dst_id"]) for e in mat_edges]

        t_rows = (
            query(
                """
            SELECT id, body, created_at FROM thoughts WHERE id = ANY(%s::uuid[])
        """,
                thought_ids_mat,
            )
            if thought_ids_mat
            else []
        )
        rs_rows = (
            query(
                """
            SELECT id, title, uri FROM raw_sources WHERE id = ANY(%s::uuid[])
        """,
                source_ref_ids,
            )
            if source_ref_ids
            else []
        )
        t_map = {str(r["id"]): r for r in t_rows}
        rs_map = {str(r["id"]): r for r in rs_rows}

        def _date10_local(v: Any) -> str:
            if v is None:
                return ""
            return v.strftime("%Y-%m-%d") if hasattr(v, "strftime") else str(v)[:10]

        for edge in mat_edges:
            t = t_map.get(str(edge["src_id"]), {})
            rs = rs_map.get(str(edge["dst_id"]), {})
            session_date = _date10_local(t.get("created_at"))
            mat_date = _date10_local(edge.get("created_at"))
            real_title = rs.get("title") or rs.get("uri", edge["dst_id"])
            real_uri = rs.get("uri", "")
            days_diff = ""
            if session_date and mat_date:
                try:
                    from datetime import date

                    d = (
                        date.fromisoformat(mat_date) - date.fromisoformat(session_date)
                    ).days
                    days_diff = f" (+{d}d)"
                except ValueError:
                    pass

            lines.append(f"### {mat_date}{days_diff}")
            if t.get("body"):
                lines.append(f"> {t['body']}")
            real_link = f"[{real_title}]({real_uri})" if real_uri else real_title
            lines.append(f"→ **Materialized as:** {real_link}")
            lines.append(f"*(signal: {session_date})*")
            lines.append("")
            source_ids.append(str(edge["src_id"]))

    path_m = str(frp_dir / "materializing.md")
    write_wiki(path_m, "\n".join(lines), source_ids[:])
    _wc._pages_written.append(path_m)

    # ── 4. F7.5 — synthesis-aware perspective pages ───────────────────────
    syntheses = _load_active_syntheses(tenant_id)
    _write_frp_perspective_pages(frp_dir, syntheses)

    # ── 5. F7.5 — Map of Content (after perspective pages so it can list them)
    _write_frp_moc(frp_dir, sessions, queue, mat_edges)


# ---------------------------------------------------------------------------
# Perspective pages helpers
# ---------------------------------------------------------------------------


def _write_frp_perspective_pages(
    frp_dir: Path, syntheses: dict[tuple[str, str], dict]
) -> None:
    """Render the 5 FRP perspective synthesis pages (by-frame / by-domain /
    evolution / by-resonance / monthly)."""
    from exocortex.wiki.util.slugs import _safe_slug

    layout = [
        ("frp_per_frame", "by-frame", "Frame"),
        ("frp_per_domain", "by-domain", "Domena"),
        ("frp_per_resonance", "by-resonance", "Rezonans ≥"),
        ("frp_monthly", "monthly", "Miesiąc"),
    ]
    for ptype, subdir, label in layout:
        target = frp_dir / subdir
        target.mkdir(parents=True, exist_ok=True)
        for (pt, pk), syn in syntheses.items():
            if pt != ptype:
                continue
            slug = _safe_slug(pk)
            if not slug:
                log.warning("Skipping FRP synthesis with unsafe key %r", pk)
                continue
            path = target / f"{slug}.md"
            _write_frp_synthesis_page(
                path, syn, perspective_label=label, perspective_key=pk
            )

    # frp_evolution_timeline → singleton at frp/evolution.md
    syn = syntheses.get(("frp_evolution_timeline", "all"))
    if syn:
        _write_frp_synthesis_page(
            frp_dir / "evolution.md",
            syn,
            perspective_label="Ewolucja praktyki",
            perspective_key="all",
        )


def _write_frp_synthesis_page(
    path: Path, syn: dict, perspective_label: str, perspective_key: str
) -> None:
    """Render one FRP synthesis page: 5-section banner + cross-domain section."""
    import exocortex.wiki_compiler as _wc
    from exocortex.db import query
    from exocortex.wiki.core.io import write_wiki
    from exocortex.wiki.util.slugs import _safe_slug
    from exocortex.wiki.domains.synthesis_render import _render_synthesis_banner

    n_thoughts = len(syn.get("source_thought_ids") or [])
    title = f"FRP — {perspective_label}: {perspective_key}"
    lines: list[str] = [f"# {title}", ""]
    lines += _render_synthesis_banner(
        syn, n_thoughts, extra=f"thoughtów FRP: {n_thoughts}"
    )
    if syn and syn.get("content"):
        lines += _wc._format_synthesis_sections(syn["content"], syn, source_meetings={})

    # F7.5.3 — cross-domain section from signals_domain edges
    src_ids = [str(t) for t in (syn.get("source_thought_ids") or [])]
    if src_ids:
        rows = []
        try:
            rows = query(
                """
                SELECT e.dst_id::text AS entity_id, ent.canonical_name, ent.type
                FROM edges e
                JOIN entities ent ON ent.id = e.dst_id
                WHERE e.tenant_id = (SELECT tenant_id FROM syntheses WHERE id = %s)
                  AND e.type = 'signals_domain'
                  AND e.src_id = ANY(%s::uuid[])
                GROUP BY e.dst_id, ent.canonical_name, ent.type
                ORDER BY ent.type, ent.canonical_name
            """,
                str(syn["id"]),
                src_ids,
            )
        except Exception:
            rows = []
        if rows:
            lines += ["## Powiązane domeny (signals_domain)", ""]
            for r in rows:
                lines.append(
                    f"- `{r['type']}` → [[../work/{r['type']}s/{_safe_slug(r['canonical_name'])}|{r['canonical_name']}]]"
                )
            lines.append("")
        else:
            lines += [
                "## Powiązane domeny (signals_domain)",
                "",
                "_Brak cross-domain edges. Pojawią się gdy `frp_reflection` "
                "przyjdzie z `entity_links` wskazującymi na work/3d/etc entities._",
                "",
            ]

    # Sessions pointer
    lines += [
        "## Sesje w tej perspektywie",
        "",
        "> Pełen tekst thoughtów: [[sessions]]. Sortowanie i filtrowanie via Dataview.",
        "",
    ]
    write_wiki(
        str(path),
        "\n".join(lines),
        source_ids=[str(syn["id"])] if syn and syn.get("id") else [],
    )
    _wc._pages_written.append(str(path))


def _write_frp_moc(
    frp_dir: Path, sessions: list[dict], queue: list[dict], mat_edges: list[dict]
) -> None:
    """Map of Content for FRP — links to all generated FRP pages + Dataview presets."""
    import exocortex.wiki_compiler as _wc
    from exocortex.wiki.core.io import write_wiki

    n_q = len(queue)
    n_s = len(sessions)
    n_m = len(mat_edges)
    by_frame: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_resonance: dict[int, int] = {}
    for s in sessions:
        f = s.get("frame") or "?"
        by_frame[f] = by_frame.get(f, 0) + 1
        st = s.get("status") or "?"
        by_status[st] = by_status.get(st, 0) + 1
        r = s.get("resonance")
        if r is not None:
            by_resonance[int(r)] = by_resonance.get(int(r), 0) + 1

    lines = [
        "# FRP — Map of Content",
        "",
        "> Futures Reading Protocol: praktyka mikrodozowania scenariuszy SF dla treningu strategicznej wyobraźni. Pełen protocol: [[../../docs/frp-protocol|frp-protocol]].",
        "",
        "## Stan",
        "",
        f"- **Reading queue**: {n_q} pozycje — [[reading-queue]]",
        f"- **Sesje**: {n_s} łącznie — [[sessions]]",
        f"- **Materializing signals**: {n_m} — [[materializing]]",
        "",
    ]
    if by_frame:
        lines += ["### Frame distribution", ""]
        for f in sorted(by_frame):
            lines.append(f"- Frame **{f}**: {by_frame[f]}")
        lines.append("")
    if by_status:
        lines += ["### Status", ""]
        for st in ("active", "revisited", "archived"):
            if st in by_status:
                lines.append(f"- {st}: {by_status[st]}")
        lines.append("")
    if by_resonance:
        lines += ["### Resonance", ""]
        for r in sorted(by_resonance.keys(), reverse=True):
            lines.append(f"- Resonance {r}/5: {by_resonance[r]}")
        lines.append("")

    lines += [
        "## Perspektywy syntez",
        "",
        "> Strony renderują się gdy synthesizer wyprodukuje syntezę (`python -m scripts.run_synthesizer --perspective frp_*`). Brak strony = brak syntezy w tym wycinku.",
        "",
        "- [[by-frame/a|Frame A — adaptacja]] · [[by-frame/b|Frame B — pomostowanie]] · [[by-frame/c|Frame C — katalizator]]",
        "- [[by-domain/work|Domena work]] · [[by-domain/tech|tech]] · [[by-domain/personal|personal]]",
        "- [[evolution|Ewolucja praktyki (first 5 vs last 5)]]",
        "- [[by-resonance/3|Rezonans ≥3]] · [[by-resonance/4|≥4]] · [[by-resonance/5|≥5]]",
        "- `monthly/YYYY-MM.md` — synteza per miesiąc (gdy ≥5 thoughtów)",
        "",
        "## Dataview presets",
        "",
        "### 1. Reading queue (top 10, score-sorted)",
        "```dataview",
        "TABLE WITHOUT ID",
        "    file.link AS Page,",
        "    score AS Score",
        'FROM "wiki/frp"',
        'WHERE file.name = "reading-queue"',
        "LIMIT 1",
        "```",
        "",
        "### 2. Active sesje (ostatnie 30 dni)",
        "```dataview",
        "TABLE WITHOUT ID",
        "    file.link AS Sesja,",
        "    frame AS Frame,",
        "    resonance AS Rez,",
        '    revisit_due AS "Revisit"',
        'FROM "wiki/frp"',
        'WHERE _domain = "frp" AND _status = "active"',
        "SORT file.cday DESC",
        "LIMIT 30",
        "```",
        "",
        "### 3. Sesje wymagające revisitu (revisit_due ≤ dziś)",
        "```dataview",
        "TABLE WITHOUT ID",
        "    file.link AS Sesja,",
        '    revisit_due AS "Due",',
        "    frame AS Frame",
        'FROM "wiki/frp"',
        'WHERE _status = "active" AND revisit_due AND date(revisit_due) <= date(today)',
        "SORT revisit_due ASC",
        "```",
        "",
        "### 4. Materializing tracker (impulsy które stały się artefaktami)",
        "```dataview",
        "TABLE WITHOUT ID",
        "    file.link AS Sesja,",
        '    materializes_as AS "Artefakt",',
        '    file.cday AS "Sesja z dnia"',
        'FROM "wiki/frp"',
        "WHERE materializes_as",
        "SORT file.cday DESC",
        "```",
        "",
        "### 5. High-resonance pattern mining (rezonans ≥4)",
        "```dataview",
        "TABLE WITHOUT ID",
        "    file.link AS Sesja,",
        '    eft_anchor AS "EFT anchor",',
        "    frame AS Frame",
        'FROM "wiki/frp"',
        "WHERE resonance AND number(resonance) >= 4",
        "SORT resonance DESC",
        "```",
        "",
        "### 6. Frame distribution (per miesiąc)",
        "```dataview",
        "TABLE WITHOUT ID",
        "    rows.file.link AS Sesje,",
        '    length(rows) AS "Liczba"',
        'FROM "wiki/frp"',
        'WHERE _domain = "frp" AND frame',
        "GROUP BY frame",
        "SORT length(rows) DESC",
        "```",
        "",
    ]
    path = frp_dir / "_moc.md"
    write_wiki(str(path), "\n".join(lines), source_ids=[])
    _wc._pages_written.append(str(path))


# ---------------------------------------------------------------------------
# Domain registration
# ---------------------------------------------------------------------------


class FrpDomain(_LegacyDomainCompiler):
    _legacy_fn_name = "compile_frp_module"

    @property
    def name(self) -> str:
        return "frp"


def setup(registry: Any) -> None:
    registry.register_compile_domain(FrpDomain())
