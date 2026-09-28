# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Confidence intervals used by the lab (standard library only).

- Wilson score interval for a proportion.
- Percentile bootstrap by cluster (for example by document) for a ratio of
  sums and for the difference of two such ratios on the same clusters.

Only the standard library is used, so lab/recompute.py can load this file
on a clean clone and get exactly the same numbers as the pages: the
bootstrap draws come from ``random.Random(seed)`` in a fixed order.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence

Z95 = 1.959963984540054  # two-sided 95%
BOOTSTRAP_REPLICATES = 10_000
BOOTSTRAP_SEED = 20260929


def wilson(successes: int, n: int, z: float = Z95) -> tuple[float | None, float | None, float | None]:
    """(proportion, low, high); all None when n == 0."""
    if n == 0:
        return None, None, None
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z / denom * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    low = 0.0 if successes == 0 else max(0.0, centre - half)
    high = 1.0 if successes == n else min(1.0, centre + half)
    return p, low, high


def _percentile(sorted_values: Sequence[float], q: float) -> float:
    """Linear interpolation between order statistics (numpy's default method)."""
    if not sorted_values:
        raise ValueError("no values")
    pos = (len(sorted_values) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_values[lo]
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def _ratio(pairs: Sequence[tuple[float, float]]) -> float | None:
    num = sum(p[0] for p in pairs)
    den = sum(p[1] for p in pairs)
    return num / den if den else None


def bootstrap_ratio(clusters: dict[str, tuple[float, float]], replicates: int = BOOTSTRAP_REPLICATES,
                    seed: int = BOOTSTRAP_SEED) -> tuple[float | None, float | None, float | None]:
    """(estimate, low, high) for sum(numerators) / sum(denominators), resampling clusters.

    ``clusters`` maps a cluster id to (numerator, denominator), for example a
    document to (claims with an error, claims). Replicates whose denominator
    is zero are skipped.
    """
    keys = sorted(clusters)
    if not keys:
        return None, None, None
    estimate = _ratio([clusters[k] for k in keys])
    rng = random.Random(seed)
    values = []
    for _ in range(replicates):
        draw = [clusters[keys[rng.randrange(len(keys))]] for _ in keys]
        r = _ratio(draw)
        if r is not None:
            values.append(r)
    if not values:
        return estimate, None, None
    values.sort()
    return estimate, _percentile(values, 0.025), _percentile(values, 0.975)


def bootstrap_difference(a: dict[str, tuple[float, float]], b: dict[str, tuple[float, float]],
                         replicates: int = BOOTSTRAP_REPLICATES,
                         seed: int = BOOTSTRAP_SEED) -> tuple[float | None, float | None, float | None]:
    """(estimate, low, high) of ratio(b) - ratio(a), resampling the clusters both share.

    Paired design: the same clusters (documents) go through both
    configurations, so every replicate draws one set of clusters and computes
    both ratios on it.
    """
    keys = sorted(set(a) & set(b))
    if not keys:
        return None, None, None
    ra, rb = _ratio([a[k] for k in keys]), _ratio([b[k] for k in keys])
    estimate = rb - ra if ra is not None and rb is not None else None
    rng = random.Random(seed)
    values = []
    for _ in range(replicates):
        draw = [keys[rng.randrange(len(keys))] for _ in keys]
        xa, xb = _ratio([a[k] for k in draw]), _ratio([b[k] for k in draw])
        if xa is not None and xb is not None:
            values.append(xb - xa)
    if not values:
        return estimate, None, None
    values.sort()
    return estimate, _percentile(values, 0.025), _percentile(values, 0.975)


def bootstrap_mean(values: dict[str, float], replicates: int = BOOTSTRAP_REPLICATES,
                   seed: int = BOOTSTRAP_SEED) -> tuple[float | None, float | None, float | None]:
    """(mean, low, high) of per-item values, resampling items."""
    return bootstrap_ratio({k: (v, 1.0) for k, v in values.items()}, replicates, seed)
