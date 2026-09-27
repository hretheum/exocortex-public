# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.
"""Pure scoring module for F31.2 Resurfacing Engine.

Deterministic ranking of candidate thoughts to resurface. Combines SM2 spaced
repetition overdue signal, knowledge-graph proximity, and provenance trust.
No IO, no LLM, no side effects — pure functions only.
"""

from __future__ import annotations

import math


def score_thought(
    thought_id: str,
    sm2_interval: int,
    sm2_repetitions: int,
    sm2_efactor: float,
    days_since_last_surfaced: float,
    edge_count: int,
    provenance: str,
    human_validated: bool,
) -> float:
    """Compute a resurfacing priority score for a single thought.

    Higher score = better candidate to surface today. Returns 0.0 when the
    thought is not yet due according to its SM2 interval.
    """
    if math.isinf(days_since_last_surfaced):
        sm2_score = 1.5
    elif days_since_last_surfaced < sm2_interval:
        sm2_score = 0.0
    else:
        sm2_score = min(days_since_last_surfaced / sm2_interval, 3.0)

    if provenance == "human":
        prov_weight = 1.0
    elif human_validated:
        prov_weight = 0.85
    elif provenance == "ai_extracted":
        prov_weight = 0.80
    else:
        prov_weight = 0.70

    graph_boost = 1.0 + min(edge_count, 5) * 0.1
    orphan_boost = 1.15 if edge_count == 0 else 1.0

    return sm2_score * prov_weight * graph_boost * orphan_boost


def sm2_next_interval(
    interval: int,
    repetitions: int,
    efactor: float,
    recalled: bool,
) -> tuple[int, int, float]:
    """Advance SM2 state after a surfacing event.

    Assumes quality q=4 ("recalled with some hesitation") when ``recalled`` is
    True. Without user feedback we treat every surfacing as a moderate recall.
    """
    q = 4 if recalled else 2
    new_efactor = max(1.3, efactor + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    if repetitions == 0:
        new_interval = 1
    elif repetitions == 1:
        new_interval = 6
    else:
        new_interval = round(interval * new_efactor)
    return new_interval, repetitions + 1, new_efactor
