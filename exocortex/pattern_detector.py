# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31.1.2 — Emergent pattern detector.

Detects "what is new / returning / spiking" by comparing a recent time window
against a longer baseline window. Two signals:

1. Term frequency spike — tags from ``thoughts.extracted_tags`` in the window
   vs. baseline. Emits when ``spike_ratio = freq_now / freq_baseline >= 3.0``.
2. Embedding drift — cosine distance between centroid of ``thoughts.embedding``
   vectors in the window vs. baseline. Emits when ``drift_score >= 0.3``.

Output rows feed F31.1.1 ``night_shift_briefing`` synthesis.
"""
from __future__ import annotations

import argparse
import json
import math
from typing import Any

from exocortex.db import query

SPIKE_THRESHOLD = 3.0
DRIFT_THRESHOLD = 0.3
_TAG_AXES = ("client", "project", "activity", "topic", "status")


def _extract_terms(extracted_tags: Any) -> list[str]:
    """Flatten ``extracted_tags`` JSONB into a list of term strings.

    Handles two shapes:
      * Real schema: ``{axis: [{value, confidence, ...}, ...]}`` over 5 axes.
      * Spec shorthand: ``{"tags": ["term1", "term2"]}``.
    """
    if not extracted_tags or not isinstance(extracted_tags, dict):
        return []
    terms: list[str] = []
    flat = extracted_tags.get("tags")
    if isinstance(flat, list):
        terms.extend(str(t) for t in flat if t)
    for axis in _TAG_AXES:
        items = extracted_tags.get(axis) or []
        if not isinstance(items, list):
            continue
        for it in items:
            if isinstance(it, dict) and it.get("value"):
                terms.append(str(it["value"]))
            elif isinstance(it, str):
                terms.append(it)
    return terms


def _parse_vector(raw: Any) -> list[float] | None:
    """Parse pgvector textual representation ``'[0.1,0.2,...]'`` into floats."""
    if raw is None:
        return None
    if isinstance(raw, list):
        try:
            return [float(x) for x in raw]
        except (TypeError, ValueError):
            return None
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s or s in ("[]", "()"):
        return None
    s = s.strip("[]()")
    try:
        return [float(x) for x in s.split(",") if x.strip()]
    except ValueError:
        return None


def _centroid(vectors: list[list[float]]) -> list[float] | None:
    if not vectors:
        return None
    dim = len(vectors[0])
    sums = [0.0] * dim
    n = 0
    for v in vectors:
        if len(v) != dim:
            continue
        for i, x in enumerate(v):
            sums[i] += x
        n += 1
    if n == 0:
        return None
    return [s / n for s in sums]


def _cosine_distance(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    sim = dot / (na * nb)
    sim = max(-1.0, min(1.0, sim))
    return 1.0 - sim


def _frequencies_for_window(hours: int) -> tuple[dict[str, int], int]:
    """Return ``(term -> count, total_thoughts_with_tags)`` for last ``hours``."""
    sql = (
        "SELECT extracted_tags FROM thoughts "
        f"WHERE created_at >= NOW() - INTERVAL '{int(hours)} hours' "
        "AND extracted_tags IS NOT NULL"
    )
    rows = query(sql)
    counts: dict[str, int] = {}
    total = 0
    for row in rows or []:
        terms = _extract_terms(row.get("extracted_tags"))
        if not terms:
            continue
        total += 1
        for t in terms:
            counts[t] = counts.get(t, 0) + 1
    return counts, total


def _embeddings_for_window(hours: int) -> list[list[float]]:
    sql = (
        "SELECT embedding::text AS embedding FROM thoughts "
        f"WHERE created_at >= NOW() - INTERVAL '{int(hours)} hours' "
        "AND embedding IS NOT NULL"
    )
    rows = query(sql)
    out: list[list[float]] = []
    for row in rows or []:
        vec = _parse_vector(row.get("embedding"))
        if vec:
            out.append(vec)
    return out


def detect_patterns(window_hours: int = 24, baseline_days: int = 30) -> list[dict]:
    """Return list of emergent-pattern records.

    Each item: ``{term, frequency_now, frequency_baseline, raw_baseline, spike_ratio, drift_score}``.
    """
    results: list[dict] = []

    baseline_hours = baseline_days * 24
    now_counts, _ = _frequencies_for_window(window_hours)
    base_counts, _ = _frequencies_for_window(baseline_hours)

    if now_counts:
        # Normalise baseline to a per-window expectation so spike_ratio is comparable.
        scale = window_hours / baseline_hours if baseline_hours > 0 else 1.0
        for term, freq_now in now_counts.items():
            raw_base = base_counts.get(term, 0)
            expected = max(raw_base * scale, 1.0)
            spike_ratio = freq_now / expected
            if spike_ratio >= SPIKE_THRESHOLD:
                results.append(
                    {
                        "term": term,
                        "frequency_now": int(freq_now),
                        "frequency_baseline": float(expected),
                        "raw_baseline": int(raw_base),
                        "spike_ratio": float(spike_ratio),
                        "drift_score": 0.0,
                    }
                )

    embs_now = _embeddings_for_window(window_hours)
    embs_base = _embeddings_for_window(baseline_hours)
    centroid_now = _centroid(embs_now)
    centroid_base = _centroid(embs_base)
    if centroid_now is not None and centroid_base is not None:
        drift = _cosine_distance(centroid_now, centroid_base)
        if drift >= DRIFT_THRESHOLD:
            top_terms = [
                t for t, _ in sorted(now_counts.items(), key=lambda x: x[1], reverse=True)[:8]
            ]
            results.append(
                {
                    "term": "_embedding_drift",
                    "frequency_now": len(embs_now),
                    "frequency_baseline": float(len(embs_base)),
                    "spike_ratio": 0.0,
                    "drift_score": float(drift),
                    "top_terms": top_terms,
                }
            )

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect emergent patterns (term spike + embedding drift)."
    )
    parser.add_argument("--window", type=int, default=24, help="Window in hours.")
    parser.add_argument(
        "--baseline", type=int, default=30, help="Baseline window in days."
    )
    args = parser.parse_args()
    print(json.dumps(detect_patterns(args.window, args.baseline)))


if __name__ == "__main__":
    main()
