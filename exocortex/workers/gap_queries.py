# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31.5.1 — Gap Radar: pure-SQL gap detectors.

Four detectors over ``thoughts`` / ``edges`` / ``syntheses``:

* :func:`detect_dense_clusters_no_synthesis` — tag clusters lacking syntheses.
* :func:`detect_thoughts_without_decision` — old observations with no decision.
* :func:`detect_unresolved_contradictions` — open ``contradicts`` edges.
* :func:`detect_stale_orphans` — old thoughts with few/no edges.

No LLM, no embeddings, no AGE. All queries parameterized, ``tenant_id`` from
``os.environ["TENANT_ID"]`` (never hardcoded).

Schema notes (matches ``schema/01_base.sql``):

* ``edges`` uses ``src_id``/``dst_id`` (not ``source_id``/``target_id``) and
  carries its own ``tenant_id`` column.
* ``thoughts`` has no ``title`` column — title lives in
  ``metadata->>'title'``; body in ``body``.
* Tags live in ``thoughts.metadata->'tags'`` (JSONB array); there is no
  standalone ``tags`` table.
* Syntheses are detected via ``syntheses`` table with
  ``superseded_by IS NULL`` (no ``synthesizes`` edge type exists).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, TypedDict

from exocortex.db import query


class Gap(TypedDict):
    type: str
    title: str
    thought_ids: list[str]
    age_days: float
    suggested_action: str
    meta: dict[str, Any]


def _age_days(ts: datetime | None) -> float:
    if ts is None:
        return 0.0
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    delta = datetime.now(UTC) - ts
    return round(delta.total_seconds() / 86400.0, 2)


def _label(row: dict[str, Any]) -> str:
    meta = row.get("metadata") or {}
    title = (meta.get("title") or "").strip() if isinstance(meta, dict) else ""
    if title:
        return title
    body = (row.get("body") or "").strip()
    if body:
        excerpt = body[:60].replace("\n", " ").strip()
        return excerpt or row["thought_id"][:8]
    return row["thought_id"][:8]


# ---------------------------------------------------------------------------
# Detector 1 — dense tag clusters without synthesis
# ---------------------------------------------------------------------------

_DENSE_CLUSTERS_SQL = """
    WITH tag_thoughts AS (
        SELECT
            jsonb_array_elements_text(t.metadata->'tags')   AS tag,
            t.id                                            AS thought_id,
            t.created_at                                    AS created_at
        FROM thoughts t
        WHERE t.tenant_id = %s
          AND t.superseded_by IS NULL
          AND jsonb_typeof(t.metadata->'tags') = 'array'
    )
    SELECT
        tt.tag                                              AS tag,
        COUNT(DISTINCT tt.thought_id)                       AS thought_count,
        MIN(tt.created_at)                                  AS oldest_at,
        (array_agg(tt.thought_id::text ORDER BY tt.created_at))[1:3]
                                                            AS sample_ids
    FROM tag_thoughts tt
    WHERE NOT EXISTS (
        SELECT 1 FROM syntheses s
        WHERE s.tenant_id = %s
          AND s.perspective_key = tt.tag
          AND s.superseded_by IS NULL
    )
    GROUP BY tt.tag
    HAVING COUNT(DISTINCT tt.thought_id) >= %s
    ORDER BY thought_count DESC
    LIMIT %s
"""


def detect_dense_clusters_no_synthesis(
    tenant_id: str,
    min_cluster_size: int = 5,
    max_results: int = 20,
) -> list[Gap]:
    """Tags with >= ``min_cluster_size`` thoughts and no active synthesis."""
    rows = query(
        _DENSE_CLUSTERS_SQL,
        tenant_id, tenant_id, min_cluster_size, max_results,
    ) or []
    gaps: list[Gap] = []
    for row in rows:
        tag = row["tag"]
        count = int(row["thought_count"])
        sample_ids = [str(x) for x in (row.get("sample_ids") or [])]
        gaps.append(Gap(
            type="cluster-no-synth",
            title=f"Klaster '{tag}' bez syntezy ({count} thoughts)",
            thought_ids=sample_ids,
            age_days=_age_days(row.get("oldest_at")),
            suggested_action=f"Zsyntetyzuj klaster '{tag}'",
            meta={"tag": tag, "thought_count": count},
        ))
    return gaps


# ---------------------------------------------------------------------------
# Detector 2 — observations/findings without a decision
# ---------------------------------------------------------------------------

_NO_DECISION_SQL = """
    SELECT
        t.id::text       AS thought_id,
        t.body           AS body,
        t.metadata       AS metadata,
        t.thought_type   AS thought_type,
        t.created_at     AS created_at
    FROM thoughts t
    WHERE t.tenant_id = %s
      AND t.superseded_by IS NULL
      AND t.thought_type IN ('observation', 'finding')
      AND t.created_at < now() - make_interval(days => %s)
      AND NOT EXISTS (
          SELECT 1 FROM edges e
          WHERE e.src_id = t.id
            AND e.tenant_id = %s
            AND e.type IN ('addresses_problem', 'decided_in')
      )
    ORDER BY t.created_at ASC
    LIMIT %s
"""


def detect_thoughts_without_decision(
    tenant_id: str,
    min_age_days: int = 14,
    max_results: int = 20,
) -> list[Gap]:
    """Observations/findings older than ``min_age_days`` with no decision edge."""
    rows = query(
        _NO_DECISION_SQL,
        tenant_id, min_age_days, tenant_id, max_results,
    ) or []
    gaps: list[Gap] = []
    for row in rows:
        gaps.append(Gap(
            type="no-decision",
            title=_label(row),
            thought_ids=[row["thought_id"]],
            age_days=_age_days(row.get("created_at")),
            suggested_action="Dodaj decyzję lub przypisz do problemu",
            meta={"thought_type": row.get("thought_type")},
        ))
    return gaps


# ---------------------------------------------------------------------------
# Detector 3 — unresolved contradictions
# ---------------------------------------------------------------------------

_UNRESOLVED_CONTRADICTIONS_SQL = """
    SELECT
        e.id::text         AS edge_id,
        e.src_id::text     AS src_id,
        e.dst_id::text     AS dst_id,
        ta.body            AS body_a,
        ta.metadata        AS metadata_a,
        tb.body            AS body_b,
        tb.metadata        AS metadata_b,
        e.created_at       AS created_at
    FROM edges e
    JOIN thoughts ta ON ta.id = e.src_id
    JOIN thoughts tb ON tb.id = e.dst_id
    WHERE e.tenant_id = %s
      AND e.type = 'contradicts'
      AND e.resolved = FALSE
    ORDER BY e.created_at ASC
    LIMIT %s
"""


def detect_unresolved_contradictions(
    tenant_id: str,
    max_results: int = 20,
) -> list[Gap]:
    """Open ``contradicts`` edges (``resolved = FALSE``)."""
    rows = query(_UNRESOLVED_CONTRADICTIONS_SQL, tenant_id, max_results) or []
    gaps: list[Gap] = []
    for row in rows:
        label_a = _label({
            "thought_id": row["src_id"],
            "body": row.get("body_a"),
            "metadata": row.get("metadata_a"),
        })
        label_b = _label({
            "thought_id": row["dst_id"],
            "body": row.get("body_b"),
            "metadata": row.get("metadata_b"),
        })
        gaps.append(Gap(
            type="contradiction-unresolved",
            title=f"Sprzeczność: '{label_a}' vs '{label_b}'",
            thought_ids=[row["src_id"], row["dst_id"]],
            age_days=_age_days(row.get("created_at")),
            suggested_action="Rozwiąż sprzeczność lub oznacz jako superseded",
            meta={"edge_id": row["edge_id"]},
        ))
    return gaps


# ---------------------------------------------------------------------------
# Detector 4 — stale orphans
# ---------------------------------------------------------------------------

_STALE_ORPHANS_SQL = """
    SELECT
        t.id::text                                       AS thought_id,
        t.body                                           AS body,
        t.metadata                                       AS metadata,
        t.created_at                                     AS created_at,
        (
            SELECT count(*) FROM edges e
            WHERE (e.src_id = t.id OR e.dst_id = t.id)
              AND e.tenant_id = %s
        )                                                AS edge_count
    FROM thoughts t
    WHERE t.tenant_id = %s
      AND t.superseded_by IS NULL
      AND coalesce(t.thought_type, 'generic') <> 'archive'
      AND t.created_at < now() - make_interval(days => %s)
    GROUP BY t.id
    HAVING (
        SELECT count(*) FROM edges e
        WHERE (e.src_id = t.id OR e.dst_id = t.id)
          AND e.tenant_id = %s
    ) <= %s
    ORDER BY t.created_at ASC
    LIMIT %s
"""


def detect_stale_orphans(
    tenant_id: str,
    min_age_days: int = 30,
    max_edge_count: int = 2,
    max_results: int = 20,
) -> list[Gap]:
    """Old, weakly-connected thoughts (<= ``max_edge_count`` edges)."""
    rows = query(
        _STALE_ORPHANS_SQL,
        tenant_id, tenant_id, min_age_days, tenant_id, max_edge_count, max_results,
    ) or []
    gaps: list[Gap] = []
    for row in rows:
        edge_count = int(row.get("edge_count") or 0)
        gaps.append(Gap(
            type="stale-orphan",
            title=_label(row),
            thought_ids=[row["thought_id"]],
            age_days=_age_days(row.get("created_at")),
            suggested_action="Połącz z innymi myślami lub archiwizuj",
            meta={"edge_count": edge_count},
        ))
    return gaps


# ---------------------------------------------------------------------------
# Aggregate runner + CLI
# ---------------------------------------------------------------------------

def run_all_detectors(tenant_id: str, max_results: int = 20) -> list[Gap]:
    """Run all 4 detectors and concatenate results."""
    gaps: list[Gap] = []
    gaps.extend(detect_dense_clusters_no_synthesis(tenant_id, max_results=max_results))
    gaps.extend(detect_thoughts_without_decision(tenant_id, max_results=max_results))
    gaps.extend(detect_unresolved_contradictions(tenant_id, max_results=max_results))
    gaps.extend(detect_stale_orphans(tenant_id, max_results=max_results))
    return gaps


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="F31.5.1 gap detectors")
    parser.add_argument(
        "--type",
        choices=[
            "all",
            "cluster-no-synth",
            "no-decision",
            "contradiction-unresolved",
            "stale-orphan",
        ],
        default="all",
    )
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    tenant_id = os.environ["TENANT_ID"]
    gaps = run_all_detectors(tenant_id, max_results=args.limit)
    if args.type != "all":
        gaps = [g for g in gaps if g["type"] == args.type]
    print(json.dumps(gaps, default=str, indent=2))
