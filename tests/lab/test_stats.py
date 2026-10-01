# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Confidence intervals of the lab against known values and independent code."""
from __future__ import annotations

import random

import pytest

from exocortex.lab import stats


def test_wilson_matches_published_values():
    # Newcombe (1998), Statistics in Medicine 17:857-872, table I: 81/263 -> 0.2553 to 0.3662
    _p, lo, hi = stats.wilson(81, 263)
    assert round(lo, 4) == 0.2553 and round(hi, 4) == 0.3662
    # 15/148 -> 0.0624 to 0.1605 (same table)
    _, lo, hi = stats.wilson(15, 148)
    assert round(lo, 4) == 0.0624 and round(hi, 4) == 0.1605
    assert stats.wilson(0, 10)[1] == 0.0 and stats.wilson(10, 10)[2] == 1.0
    assert stats.wilson(0, 0) == (None, None, None)


def test_bootstrap_is_deterministic_and_brackets_the_estimate():
    clusters = {f"d{i}": (float(i % 3 == 0), 1.0 + i % 2) for i in range(30)}
    one = stats.bootstrap_ratio(clusters)
    two = stats.bootstrap_ratio(dict(reversed(list(clusters.items()))))
    assert one == two
    est, lo, hi = one
    assert lo < est < hi


def test_paired_difference_of_identical_configs_is_zero():
    a = {f"d{i}": (float(i % 4 == 0), 2.0) for i in range(20)}
    assert stats.bootstrap_difference(a, dict(a)) == (0.0, 0.0, 0.0)


def test_percentile_uses_linear_interpolation():
    assert stats._percentile([0.0, 10.0], 0.25) == 2.5
    assert stats._percentile([1.0, 2.0, 3.0], 0.5) == 2.0


def test_wilson_agrees_with_statsmodels():
    sm = pytest.importorskip("statsmodels.stats.proportion")
    for k, n in ((0, 20), (3, 20), (17, 120), (60, 120), (119, 120)):
        _, lo, hi = stats.wilson(k, n)
        ref_lo, ref_hi = sm.proportion_confint(k, n, alpha=0.05, method="wilson")
        assert abs(lo - ref_lo) < 1e-9 and abs(hi - ref_hi) < 1e-9, (k, n)


def test_cluster_bootstrap_agrees_with_an_independent_numpy_implementation():
    np = pytest.importorskip("numpy")
    rng = random.Random(3)
    a = {f"d{i}": (float(rng.randint(0, 4)), float(rng.randint(4, 9))) for i in range(25)}
    b = {k: (max(0.0, v[0] - rng.randint(0, 2)), v[1]) for k, v in a.items()}
    keys = sorted(a)
    na = np.array([a[k] for k in keys])
    nb = np.array([b[k] for k in keys])
    g = np.random.default_rng(11)
    idx = g.integers(0, len(keys), size=(20000, len(keys)))
    diffs = nb[idx, 0].sum(1) / nb[idx, 1].sum(1) - na[idx, 0].sum(1) / na[idx, 1].sum(1)
    ref_lo, ref_hi = np.percentile(diffs, [2.5, 97.5])
    est, lo, hi = stats.bootstrap_difference(a, b)
    assert abs(est - (nb[:, 0].sum() / nb[:, 1].sum() - na[:, 0].sum() / na[:, 1].sum())) < 1e-12
    # different random streams: the bounds agree within Monte Carlo error
    assert abs(lo - ref_lo) < 0.01 and abs(hi - ref_hi) < 0.01, (lo, ref_lo, hi, ref_hi)
