# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Metrics of format conformity experiments from plain rows (standard library only).

Like metrics.py and retrieval_metrics.py, this file is loaded as a plain file by lab/recompute.py, so the
numbers of the pages can be recomputed from the published CSV files with this same code.

One row is one job of one configuration on one item, with a verdict:

- ``conforming``: the answer is one JSON value that matches the schema, with nothing else in it;
- ``non_conforming``: there is an answer, and it does not (``reasons`` lists why, by code);
- ``no_answer``: the model returned nothing (a result with ``ok`` false);
- ``None``: the job has no result at all (it ended in an error in the queue); a *failed job*.

Definitions:

- ``conforming_share`` per configuration: conforming answers divided by answered items (conforming plus
  non-conforming), with the Wilson score interval (``stats.wilson``, 95%). Items with no answer and failed jobs
  are counted in the details, not in the share: a share of "answers that match" is about answers.
- ``conforming_share_difference`` for a pair of configurations ``a`` and ``b``: the share of ``b`` minus the
  share of ``a`` on the items that both answered, with the Newcombe (1998) interval for paired proportions
  (method 10, built from the two Wilson intervals and a correction for the correlation of the two answers to
  the same item). Why this method: the two configurations answer the same items, so their outcomes are
  paired and an interval for independent samples would be too wide or too narrow; shares near 0 or 1 are
  what this experiment is about, and the method stays inside [-1, 1] and does not collapse when every item
  agrees (where a bootstrap draws the same number every time); it needs no random draws, so the numbers are
  exactly reproducible; and it is built from the same Wilson intervals as the shares next to it.
- ``guard``: an explicit reference to a metric of a claims experiment (the guard metric, claim quality). It is
  carried as a row without a value (method ``reference``), because the number is computed by the claims kind,
  not here.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

# lab/recompute.py maps this name to the checkout's stats.py
from exocortex.lab import stats

CONFORMING, NON_CONFORMING, NO_ANSWER = "conforming", "non_conforming", "no_answer"
VERDICTS = (CONFORMING, NON_CONFORMING, NO_ANSWER)
METRIC = "conforming_share"
DIFFERENCE = "conforming_share_difference"
METHOD = "wilson"
DIFFERENCE_METHOD = "newcombe-paired"
GUARD_METHOD = "reference"


def _wilson(successes: int, n: int, z: float) -> tuple[float, float, float]:
    p, low, high = stats.wilson(successes, n, z)
    if p is None or low is None or high is None:
        raise ValueError("no items")
    return p, low, high


def newcombe_paired(both: int, only_a: int, only_b: int, neither: int,
                    z: float = stats.Z95) -> tuple[float | None, float | None, float | None]:
    """(share_b - share_a, low, high) for paired outcomes, Newcombe (1998) method 10.

    The four counts are the items both configurations got right (``both``), only a (``only_a``), only b
    (``only_b``) and neither. All None when there are no items.
    """
    for count in (both, only_a, only_b, neither):
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError(f"counts must be integers of at least 0, got {count!r}")
    n = both + only_a + only_b + neither
    if n == 0:
        return None, None, None
    # first = b, second = a: the table is [[both, only_b], [only_a, neither]]
    p1, l1, u1 = _wilson(both + only_b, n, z)
    p2, l2, u2 = _wilson(both + only_a, n, z)
    marginals = (both + only_b) * (only_a + neither) * (both + only_a) * (only_b + neither)
    cross = both * neither - only_b * only_a
    if marginals == 0:
        phi = 0.0
    else:
        if cross > n / 2:
            corrected = cross - n / 2
        elif cross >= 0:
            corrected = 0.0
        else:
            corrected = float(cross)
        phi = corrected / math.sqrt(marginals)
    delta = p1 - p2
    down_b, down_a = p1 - l1, u2 - p2  # distances to the lower limits of the two Wilson intervals
    up_b, up_a = u1 - p1, p2 - l2
    low = delta - math.sqrt(max(0.0, down_b * down_b + down_a * down_a - 2 * phi * down_b * down_a))
    high = delta + math.sqrt(max(0.0, up_b * up_b + up_a * up_a - 2 * phi * up_b * up_a))
    return delta, max(-1.0, low), min(1.0, high)


def row_verdict(ok: bool | None, output: Mapping | None) -> str | None:
    """Verdict of a stored result: None without a result, ``no_answer`` for a result that is not ok, else the
    verdict the runner stored in the output (which must be one of the two answer verdicts)."""
    if ok is None:
        return None
    if not ok:
        return NO_ANSWER
    verdict = (output or {}).get("verdict")
    if verdict not in (CONFORMING, NON_CONFORMING):
        raise ValueError(f"a result that is ok must carry the verdict conforming or non_conforming, got {verdict!r}")
    return str(verdict)


def reason_codes(output: Mapping | None) -> list[str]:
    """Reason codes stored with an answer, each once."""
    return sorted({str(r["code"]) for r in (output or {}).get("reasons") or []})


def settings(params: Mapping | None) -> tuple[str | None, dict | None]:
    """(baseline configuration, guard reference) from the experiment's params.

    ``baseline``: the configuration every other one is compared with; without it, every pair is.
    ``guard``: ``{experiment, metric}``, a reference to a metric of a claims experiment, or None.
    """
    params = params or {}
    guard = params.get("guard")
    if guard is not None:
        if (not isinstance(guard, Mapping) or set(guard) != {"experiment", "metric"}
                or not all(isinstance(guard[k], str) and guard[k] for k in guard)):
            raise ValueError(f"guard must be a mapping with the text fields experiment and metric, got {guard!r}")
        guard = {"experiment": guard["experiment"], "metric": guard["metric"]}
    baseline = params.get("baseline")
    if baseline is not None and not isinstance(baseline, str):
        raise ValueError(f"baseline must be a configuration name, got {baseline!r}")
    return baseline, guard


def format_metrics(rows: Sequence[Mapping], prefix: str, baseline: str | None = None,
                   guard: Mapping | None = None) -> list[dict]:
    """Format conformity metrics of one run.

    ``rows``: one per job with ``config``, ``item_id``, ``verdict`` (see the module docstring) and, for an
    answer, ``reasons`` (codes). ``prefix``: "<experiment>/<run>". Per configuration one row with the share of
    conforming answers and its Wilson interval; per pair of configurations one row with the paired difference
    ``b - a`` and its Newcombe interval; with ``guard``, one reference row.
    """
    per_config: dict[str, dict] = {}
    for r in sorted(rows, key=lambda r: (r["config"], r["item_id"])):
        cfg = per_config.setdefault(r["config"], {"answers": {}, "no_answer": 0, "failed_jobs": 0, "reasons": {}})
        verdict = r["verdict"]
        if verdict is None:
            cfg["failed_jobs"] += 1
        elif verdict == NO_ANSWER:
            cfg["no_answer"] += 1
        elif verdict in (CONFORMING, NON_CONFORMING):
            if r["item_id"] in cfg["answers"]:
                raise ValueError(f"item {r['item_id']!r} has two results in configuration {r['config']!r}")
            cfg["answers"][r["item_id"]] = verdict == CONFORMING
            for code in sorted(set(r.get("reasons") or ())):
                cfg["reasons"][code] = cfg["reasons"].get(code, 0) + 1
        else:
            raise ValueError(f"unknown verdict {verdict!r}; known: {', '.join(VERDICTS)} or None")
    out: list[dict] = []
    for name in sorted(per_config):
        cfg = per_config[name]
        answers = cfg["answers"]
        conforming = sum(answers.values())
        value, low, high = stats.wilson(conforming, len(answers))
        out.append({"result_id": f"{prefix}/{name}/{METRIC}", "config": name, "metric": METRIC, "value": value,
                    "ci_low": low, "ci_high": high, "n": len(answers), "method": METHOD,
                    "details": {"conforming": conforming, "non_conforming": len(answers) - conforming,
                                "no_answer": cfg["no_answer"], "failed_jobs": cfg["failed_jobs"],
                                "reasons": dict(sorted(cfg["reasons"].items()))}})
    configs = sorted(per_config)
    if baseline is not None and baseline not in per_config:
        raise ValueError(f"baseline {baseline!r} is not a configuration of the run: {', '.join(configs)}")
    pairs = ([(baseline, b) for b in configs if b != baseline] if baseline is not None
             else [(a, b) for i, a in enumerate(configs) for b in configs[i + 1:]])
    for a, b in pairs:
        va, vb = per_config[a]["answers"], per_config[b]["answers"]
        shared = sorted(set(va) & set(vb))
        table = {"both": sum(va[q] and vb[q] for q in shared), "only_a": sum(va[q] and not vb[q] for q in shared),
                 "only_b": sum(vb[q] and not va[q] for q in shared),
                 "neither": sum(not va[q] and not vb[q] for q in shared)}
        d, low, high = newcombe_paired(table["both"], table["only_a"], table["only_b"], table["neither"])
        out.append({"result_id": f"{prefix}/diff/{b}_minus_{a}/{METRIC}", "config": None, "metric": DIFFERENCE,
                    "value": d, "ci_low": low, "ci_high": high, "n": len(shared), "method": DIFFERENCE_METHOD,
                    "details": {"a": a, "b": b, "difference": "b - a", **table}})
    if guard is not None:
        ref = f"{guard['experiment']}/{guard['metric']}"
        out.append({"result_id": f"{prefix}/guard/{ref}", "config": None, "metric": f"guard:{ref}", "value": None,
                    "ci_low": None, "ci_high": None, "n": 0, "method": GUARD_METHOD,
                    "details": {"guard": {"experiment": guard["experiment"], "metric": guard["metric"]},
                                "computed_here": False}})
    return out
