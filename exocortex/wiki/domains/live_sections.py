# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Live sections dashboard domain compiler."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from exocortex.wiki.domains.base import _LegacyDomainCompiler


def compile_live_sections_dashboard(tenant_id: str, since: Optional[datetime]) -> None:
    """Generate wiki/_live-sections.md showing live section status."""
    import exocortex.wiki_compiler as _wc
    from exocortex.wiki.core.io import (
        _get_wiki_root,
        _hash_input,
        _write_with_frontmatter,
    )

    wiki_root = _get_wiki_root()
    sections: list[dict] = []
    try:
        from exocortex.live_sections import (
            scan_all_live_sections,
            get_live_section_history,
        )

        sections = scan_all_live_sections() or []
    except Exception as exc:
        logging.warning("[wiki_compiler] live sections scan failed: %r", exc)
    now = datetime.now(timezone.utc)

    lines = [
        "> Auto-aktualizujące się sekcje wiki. Uruchamiane przez cron, eventy,",
        "> lub manualnie przez MCP tool `trigger_live_section`. Timer: co 5 min.",
        "",
    ]

    if not sections:
        lines += ["_Brak aktywnych live sections._", ""]
    else:
        # Active sections table
        lines += ["## Aktywne sekcje", ""]
        lines += [
            "| Sekcja | Plik | Ostatnio | Status | Triggery |",
            "|--------|------|----------|--------|----------|",
        ]
        for s in sorted(sections, key=lambda x: x["section_id"]):
            sid = s["section_id"]
            file_path = s.get("file_path", "")
            last_emoji = "⏳"
            if s.get("lastRunAt"):
                try:
                    last_dt = datetime.fromisoformat(
                        str(s["lastRunAt"]).replace("Z", "+00:00")
                    )
                    delta = now - last_dt
                    if delta.total_seconds() < 600:
                        last_emoji = "🟢"
                    elif delta.total_seconds() < 3600:
                        last_emoji = "🟡"
                    else:
                        last_emoji = "🔴"
                except (ValueError, TypeError):
                    pass

            last_str = s.get("lastRunAt") or ""
            if len(last_str) > 16:
                last_str = last_str[:16].replace("T", " ")

            is_active = s.get("active", True)
            status_icon = "✅" if is_active else "⏸"

            triggers = []
            for tr in s.get("triggers", []):
                ttype = tr.get("type", "?")
                if ttype == "cron":
                    triggers.append(f"`{tr.get('expression', '?')}`")
                elif ttype == "window":
                    triggers.append(
                        f"window:{tr.get('start', tr.get('startTime', ''))}-{tr.get('end', tr.get('endTime', ''))}"
                    )
                elif ttype == "event":
                    triggers.append(f"event:{tr.get('match', '?')}")
                else:
                    triggers.append(ttype)
            trigger_str = " · ".join(triggers) or "manual"

            lines.append(
                f"| `{sid}` | `{file_path}` | {last_emoji} {last_str} | {status_icon} {s.get('last_status', '?')} | {trigger_str} |"
            )
        lines.append("")

        # Recent runs table
        lines += ["## Ostatnie uruchomienia", ""]
        lines += [
            "| Data | Sekcja | Trigger | Wynik |",
            "|------|--------|---------|-------|",
        ]
        seen = 0
        for s in sorted(sections, key=lambda x: x["section_id"]):
            try:
                history = get_live_section_history(s["section_id"], limit=3)
            except Exception:
                history = []
            for h in history:
                started = h.get("started_at", "")
                if len(started) > 16:
                    started = started[:16].replace("T", " ")
                status = "✅" if h["status"] == "success" else "❌"
                event_str = h.get("event", "") or h.get("trigger", "")
                lines.append(
                    f"| {started} | `{s['section_id']}` | {event_str} | {status} {h['status']} |"
                )
                seen += 1
                if seen >= 20:
                    break
            if seen >= 20:
                break
        if seen == 0:
            lines += ["| — | — | — | Brak historii |"]
        lines.append("")

    body = "\n".join(lines).rstrip() + "\n"
    fm = {
        "type": "live-sections",
        "title": "Live Sections",
        "last_refresh": now.isoformat(),
        "total_sections": len(sections),
        "_input_hash": _hash_input(
            [str(len(sections))]
            + [s["section_id"] + str(s.get("lastRunAt", "")) for s in sections]
        ),
    }
    path = wiki_root / "_live-sections.md"
    written = _write_with_frontmatter(str(path), fm, body, source_ids=[])
    if written:
        _wc._pages_written.append(str(path))
    print(
        f"[wiki_compiler] live: {'wrote' if written else 'unchanged'} "
        f"_live-sections.md — {len(sections)} sections"
    )


class LiveSectionsDomain(_LegacyDomainCompiler):
    _legacy_fn_name = "compile_live_sections_dashboard"

    @property
    def name(self) -> str:
        return "live"


def setup(registry: Any) -> None:
    registry.register_compile_domain(LiveSectionsDomain())
