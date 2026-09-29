# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31.2.3 — Resurfacing Engine daily cron worker.

Selects 3-5 overdue thoughts, scores them via :mod:`resurfacing_scoring`,
writes ``wiki/_live/resurfacing.md`` with wikilinks, and advances per-thought
SM2 state. Pattern A: reads ``thoughts``/``edges``, writes only
``resurfacing_state`` and a single vault file. No LLM, no embeddings.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from exocortex.db import execute, get_tenant_id, query
from exocortex.workers.resurfacing_scoring import score_thought, sm2_next_interval

log = logging.getLogger(__name__)

MIN_SURFACE = 3
MAX_SURFACE = 5
CANDIDATE_LIMIT = 200
NO_REPEAT_DAYS = 7

# G10 — candidates are either never surfaced or surfaced > 7 days ago, and
# their thought is still current (no superseding revision).
_CANDIDATES_SQL = """
    SELECT
        t.id::text                                   AS thought_id,
        t.body                                       AS body,
        t.metadata                                   AS metadata,
        COALESCE(r.sm2_interval, 1)                  AS sm2_interval,
        COALESCE(r.sm2_repetitions, 0)               AS sm2_repetitions,
        COALESCE(r.sm2_efactor, 2.5)                 AS sm2_efactor,
        r.last_surfaced_at                           AS last_surfaced_at,
        (
            SELECT count(*) FROM edges e
            WHERE (e.src_id = t.id OR e.dst_id = t.id)
              AND e.tenant_id = %s
        )                                            AS edge_count
    FROM thoughts t
    LEFT JOIN resurfacing_state r ON r.thought_id = t.id
    WHERE t.tenant_id = %s
      AND t.superseded_by IS NULL
      AND (r.last_surfaced_at IS NULL
           OR r.last_surfaced_at < now() - interval '%s days')
    ORDER BY COALESCE(r.last_surfaced_at, t.created_at) ASC
    LIMIT %s
"""

_UPSERT_STATE_SQL = """
    INSERT INTO resurfacing_state (
        thought_id, tenant_id,
        sm2_interval, sm2_repetitions, sm2_efactor,
        last_surfaced_at, next_surface_at, surface_count
    )
    VALUES (%s, %s, %s, %s, %s, now(), now() + (%s || ' days')::interval, 1)
    ON CONFLICT (thought_id) DO UPDATE SET
        sm2_interval     = EXCLUDED.sm2_interval,
        sm2_repetitions  = EXCLUDED.sm2_repetitions,
        sm2_efactor      = EXCLUDED.sm2_efactor,
        last_surfaced_at = now(),
        next_surface_at  = now() + (%s || ' days')::interval,
        surface_count    = resurfacing_state.surface_count + 1
"""


def _vault_path() -> Path:
    """Resolve vault root from EXOCORTEX_VAULT_PATH (required at runtime)."""
    raw = os.environ.get("EXOCORTEX_VAULT_PATH")
    if not raw:
        raise RuntimeError(
            "EXOCORTEX_VAULT_PATH is not set; refusing to guess vault root."
        )
    return Path(raw)


def _days_since(last: Optional[datetime]) -> float:
    if last is None:
        return float("inf")
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - last
    return delta.total_seconds() / 86400.0


def _wikilink_for(row: dict[str, Any]) -> str:
    """Build a `[[target|label]]` line for a surfaced thought.

    Prefers ``metadata.vault_path`` / ``metadata.file_path`` when present so
    Obsidian resolves to the original note; otherwise falls back to the title,
    and finally to a body excerpt — keeping the live file readable even for
    thoughts that were never tied to a vault file.
    """
    meta = row.get("metadata") or {}
    vault_path = meta.get("vault_path") or meta.get("file_path")
    title = (meta.get("title") or "").strip()
    body = (row.get("body") or "").strip()
    label = title or (body[:60].replace("\n", " ").strip()) or row["thought_id"][:8]

    if vault_path:
        target = str(vault_path).removesuffix(".md")
        return f"- [[{target}|{label}]]"
    if title:
        return f"- [[{title}]]"
    return f"- [[{label}]]"


def _build_markdown(rows: list[dict[str, Any]]) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "---",
        f"generated_at: {generated_at}",
        "source: resurfacing_worker",
        "---",
        "",
        "## Wraca do ciebie",
        "",
    ]
    if not rows:
        lines.append("<!-- no candidates today -->")
    else:
        lines.extend(_wikilink_for(r) for r in rows)
    lines.append("")
    return "\n".join(lines)


def _select_top(scored: list[tuple[dict[str, Any], float]]) -> list[dict[str, Any]]:
    """Pick top N where MIN_SURFACE <= N <= MAX_SURFACE, taking what we have."""
    scored.sort(key=lambda x: x[1], reverse=True)
    eligible = [(r, s) for r, s in scored if s > 0.0]
    take = min(MAX_SURFACE, max(MIN_SURFACE, len(eligible)))
    take = min(take, len(eligible))
    return [r for r, _ in eligible[:take]]


def run(dry_run: bool = False) -> dict[str, Any]:
    tenant_id = get_tenant_id()
    candidates = query(
        _CANDIDATES_SQL,
        tenant_id, tenant_id, NO_REPEAT_DAYS, CANDIDATE_LIMIT,
    ) or []

    if not candidates:
        log.info("resurfacing: 0 candidates (nothing overdue)")
        if not dry_run:
            _write_live_file([])
        return {"candidates": 0, "surfaced": 0, "dry_run": dry_run}

    started = time.monotonic()
    scored: list[tuple[dict[str, Any], float]] = []
    for row in candidates:
        meta = row.get("metadata") or {}
        provenance = (meta.get("provenance") or "ai_authored").strip() or "ai_authored"
        human_validated = bool(meta.get("human_validated", False))
        score = score_thought(
            thought_id=row["thought_id"],
            sm2_interval=int(row["sm2_interval"]),
            sm2_repetitions=int(row["sm2_repetitions"]),
            sm2_efactor=float(row["sm2_efactor"]),
            days_since_last_surfaced=_days_since(row.get("last_surfaced_at")),
            edge_count=int(row["edge_count"]),
            provenance=provenance,
            human_validated=human_validated,
        )
        scored.append((row, score))
    elapsed_ms = (time.monotonic() - started) * 1000.0
    log.info("scored %d candidates in %.0fms", len(scored), elapsed_ms)

    top = _select_top(scored)

    if dry_run:
        for row in top:
            score = next(s for r, s in scored if r["thought_id"] == row["thought_id"])
            log.info(
                "would surface: %s (score=%.3f) — %s",
                row["thought_id"], score,
                (row.get("metadata") or {}).get("title")
                or (row.get("body") or "")[:40],
            )
        return {
            "candidates": len(candidates),
            "surfaced": len(top),
            "dry_run": True,
        }

    _write_live_file(top)
    for row in top:
        new_interval, new_reps, new_efactor = sm2_next_interval(
            interval=int(row["sm2_interval"]),
            repetitions=int(row["sm2_repetitions"]),
            efactor=float(row["sm2_efactor"]),
            recalled=True,
        )
        execute(
            _UPSERT_STATE_SQL,
            row["thought_id"], tenant_id,
            new_interval, new_reps, new_efactor,
            str(new_interval),  # next_surface_at on INSERT
            str(new_interval),  # next_surface_at on UPDATE
        )

    log.info("resurfacing: surfaced %d thoughts", len(top))
    return {
        "candidates": len(candidates),
        "surfaced": len(top),
        "dry_run": False,
    }


def _write_live_file(rows: list[dict[str, Any]]) -> Path:
    vault = _vault_path()
    live_dir = vault / "wiki" / "_live"
    live_dir.mkdir(parents=True, exist_ok=True)
    target = live_dir / "resurfacing.md"
    target.write_text(_build_markdown(rows), encoding="utf-8")
    return target


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    _dry = "--dry-run" in sys.argv
    result = run(dry_run=_dry)
    log.info("resurfacing result: %s", result)
