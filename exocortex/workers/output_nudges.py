# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31.5.3 — Newsletter output nudges.

Reads the latest active ``gap_radar`` synthesis and emits draft suggestion
``.md`` files for gaps that suggest content output (newsletter / draft /
publish). Pure read-from-DB + write-to-vault; no LLM calls.

Output path: ``{EXOCORTEX_VAULT_PATH}/wiki/news/drafts/_pending/{YYYY-MM-DD}-{slug}.md``.

Note on deployment: synthesizer's systemd unit uses ``ProtectHome=read-only``
because it only reads vault. ``output_nudges`` writes to the vault, so its
systemd unit (when added) must NOT set ``ProtectHome=read-only`` (use
``ProtectHome=tmpfs`` or omit, plus ``ReadWritePaths=`` covering the vault).
"""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path

from exocortex.db import query_one
from exocortex.workers import gap_queries

_OUTPUT_KEYWORDS = ("draft", "newsletter", "opublikuj", "napisz", "artykuł")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    text = (text or "").strip().lower()
    text = _SLUG_RE.sub("-", text).strip("-")
    return text[:60] or "untitled"


def get_latest_gap_radar_synthesis(tenant_id: str) -> dict | None:
    """Return ``content`` JSONB of the active gap_radar synthesis, else None."""
    row = query_one(
        """
        SELECT content
          FROM syntheses
         WHERE perspective_type = 'gap_radar'
           AND tenant_id = %s
           AND superseded_by IS NULL
         ORDER BY created_at DESC
         LIMIT 1
        """,
        tenant_id,
    )
    if not row:
        return None
    content = row.get("content")
    if isinstance(content, dict):
        return content
    return None


def _section_text(content: dict, key: str) -> str:
    """Return a flat string from a synthesis section.

    Sections are either string (``current_state``) or list-of-dicts
    (``recent_decisions``, ``open_problems``, ``next_steps``, ``ownership``).
    """
    val = content.get(key)
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, list):
        parts: list[str] = []
        for item in val:
            if isinstance(item, dict):
                parts.append(" ".join(str(v) for v in item.values() if v))
            elif item:
                parts.append(str(item))
        return "\n".join(parts)
    return str(val)


def _content_mentions_output(content: dict) -> bool:
    """True if any section text contains an output-suggesting keyword."""
    haystack = " ".join(
        _section_text(content, k)
        for k in ("current_state", "recent_decisions", "open_problems",
                  "ownership", "next_steps")
    ).lower()
    return any(kw in haystack for kw in _OUTPUT_KEYWORDS)


def extract_output_suggestions(content: dict) -> list[dict]:
    """Extract draft suggestions from a gap_radar synthesis.

    Strategy: pull cluster-no-synth gaps live from ``gap_queries`` (these are
    the highest-signal candidates for newsletter output). If the synthesis
    content itself mentions output keywords, prefer all cluster gaps;
    otherwise only emit when the synthesis was unambiguous about output.

    Returns list of ``{slug, title, body}``.
    """
    tenant_id = os.environ["TENANT_ID"]
    cluster_gaps = gap_queries.detect_dense_clusters_no_synthesis(
        tenant_id, max_results=20,
    )
    cluster_gaps = [g for g in cluster_gaps if g["type"] == "cluster-no-synth"]

    if not cluster_gaps and not _content_mentions_output(content):
        return []

    suggestions: list[dict] = []
    for gap in cluster_gaps:
        tag = gap["meta"].get("tag") or gap["title"]
        thought_count = gap["meta"].get("thought_count")
        title = f"Newsletter draft: {tag}"
        body_lines = [
            f"Klaster `{tag}` ma {thought_count} myśli i nie ma jeszcze syntezy.",
            "",
            "Sugerowany format: krótki newsletter / draft / artykuł oparty o ten klaster.",
        ]
        if gap.get("thought_ids"):
            body_lines.append("")
            body_lines.append("Przykładowe myśli źródłowe:")
            for tid in gap["thought_ids"]:
                body_lines.append(f"- `{tid}`")
        suggestions.append({
            "slug": _slugify(tag),
            "title": title,
            "body": "\n".join(body_lines),
        })
    return suggestions


def _draft_path(vault_path: str, today: str, slug: str) -> Path:
    return Path(vault_path) / "wiki" / "news" / "drafts" / "_pending" / f"{today}-{slug}.md"


def _render_draft(today: str, suggestion: dict) -> str:
    frontmatter = (
        "---\n"
        "provenance: ai_authored\n"
        "provenance_metadata:\n"
        "  agent: exocortex-gap-radar\n"
        f"  session_date: {today}\n"
        "  human_validated: false\n"
        "status: draft_suggestion\n"
        "gap_source: gap_radar\n"
        "---\n\n"
    )
    body = (
        f"## {suggestion['title']}\n\n"
        f"{suggestion['body']}\n\n"
        "> Sugestia wygenerowana przez Gap Radar. Rozwiń lub odrzuć.\n"
    )
    return frontmatter + body


def emit_draft_suggestions(
    suggestions: list[dict],
    vault_path: str,
    today: str | None = None,
) -> list[Path]:
    """Write one ``.md`` file per suggestion. Idempotent: skip existing files."""
    today_str = today or date.today().isoformat()
    out_dir = Path(vault_path) / "wiki" / "news" / "drafts" / "_pending"
    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for suggestion in suggestions:
        path = _draft_path(vault_path, today_str, suggestion["slug"])
        if path.exists():
            continue
        path.write_text(_render_draft(today_str, suggestion), encoding="utf-8")
        written.append(path)
    return written


def run(dry_run: bool = False) -> int:
    """Read latest gap_radar synth, extract & emit suggestions. Return count."""
    tenant_id = os.environ["TENANT_ID"]
    vault_path = os.environ["EXOCORTEX_VAULT_PATH"]

    content = get_latest_gap_radar_synthesis(tenant_id)
    if content is None:
        if dry_run:
            print("No gap_radar synthesis found — nothing to do.")
        return 0

    suggestions = extract_output_suggestions(content)
    if dry_run:
        for s in suggestions:
            print(f"[dry-run] would write draft: {s['slug']} — {s['title']}")
        return len(suggestions)

    written = emit_draft_suggestions(suggestions, vault_path)
    return len(written)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="F31.5.3 output nudges")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    count = run(dry_run=args.dry_run)
    print(f"Emitted {count} draft suggestions")
