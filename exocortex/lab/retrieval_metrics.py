# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Metrics of retrieval experiments from plain rows (standard library only).

Like metrics.py, this file is loaded as a plain file by lab/recompute.py, so
the numbers of the pages can be recomputed from the published CSV files with
this same code.

A ranking is a list of document ids, best first. Gold answers are a mapping
from document id to a grade: an integer, 0 (judged, not relevant) or more
(relevant, higher is better). A document that is not in the mapping counts
as not relevant.

Definitions, per question (k is a cutoff):

- ``ndcg@10``: DCG of the first 10 documents divided by the DCG of the ideal
  ranking of the gold documents. DCG is the sum of ``grade / log2(rank + 1)``
  over the ranks 1, 2, ... (linear gain). With grades 0 and 1 only this is
  the usual binary nDCG.
- ``recall@k``: the share of the relevant documents (grade above 0) that are
  among the first k.
- ``mrr``: 1 / rank of the first relevant document; 0 when the ranking has
  none. The ranking is the stored one, so its length (the ``depth`` of the
  configuration) bounds the rank that can be found.

A repeated document counts at its first place. When a question has no
relevant document the metric is undefined (None): such a question is left
out of the means and counted in the details. A ranking shorter than k is not
an error: missing places are simply empty.

Over questions, each metric is a mean with a percentile bootstrap interval
(``stats.bootstrap_mean``: 10,000 resamples of the questions, percentiles 2.5
and 97.5), and the difference of two configurations is a paired bootstrap on
the questions they share (``stats.bootstrap_difference``).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence

# lab/recompute.py maps this name to the checkout's stats.py
from exocortex.lab import stats

NDCG_K = 10
DEFAULT_RECALL_K = (10,)
METHOD = "bootstrap-by-question"


def dedupe(ranking: Iterable[str]) -> list[str]:
    """The ranking with every repeated document dropped after its first place."""
    seen: set[str] = set()
    out = []
    for doc in ranking:
        if doc not in seen:
            seen.add(doc)
            out.append(doc)
    return out


def rank_by_score(scores: Mapping[str, float]) -> list[str]:
    """Document ids by falling score; documents with equal scores by id, so a ranking never depends on order."""
    return [doc for doc, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]


def _grades(gold: Mapping[str, float]) -> dict[str, float]:
    for doc, grade in gold.items():
        if isinstance(grade, bool) or grade < 0:
            raise ValueError(f"gold grade of {doc!r} must be a number of at least 0, got {grade!r}")
    return dict(gold)


def _relevant(gold: Mapping[str, float]) -> set[str]:
    return {doc for doc, grade in _grades(gold).items() if grade > 0}


def _check_k(k: int) -> None:
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValueError(f"k must be an integer of at least 1, got {k!r}")


def dcg(grades: Sequence[float]) -> float:
    """Discounted cumulative gain of grades in ranking order: sum of grade / log2(rank + 1)."""
    return sum(grade / math.log2(rank + 1) for rank, grade in enumerate(grades, start=1))


def ndcg_at_k(ranking: Sequence[str], gold: Mapping[str, float], k: int = NDCG_K) -> float | None:
    """nDCG@k of one question; None when the gold has no relevant document."""
    _check_k(k)
    grades = _grades(gold)
    ideal = sorted((g for g in grades.values() if g > 0), reverse=True)[:k]
    best = dcg(ideal)
    if best == 0:
        return None
    return dcg([grades.get(doc, 0) for doc in dedupe(ranking)[:k]]) / best


def recall_at_k(ranking: Sequence[str], gold: Mapping[str, float], k: int = 10) -> float | None:
    """Share of the relevant documents among the first k; None when there are none."""
    _check_k(k)
    relevant = _relevant(gold)
    if not relevant:
        return None
    return len(relevant & set(dedupe(ranking)[:k])) / len(relevant)


def reciprocal_rank(ranking: Sequence[str], gold: Mapping[str, float]) -> float | None:
    """1 / rank of the first relevant document (0.0 if the ranking has none); None when there are none."""
    relevant = _relevant(gold)
    if not relevant:
        return None
    for rank, doc in enumerate(dedupe(ranking), start=1):
        if doc in relevant:
            return 1 / rank
    return 0.0


def metric_names(recall_ks: Sequence[int] = DEFAULT_RECALL_K) -> list[str]:
    return [f"ndcg@{NDCG_K}", *(f"recall@{k}" for k in recall_ks), "mrr"]


def question_values(ranking: Sequence[str], gold: Mapping[str, float],
                    recall_ks: Sequence[int] = DEFAULT_RECALL_K) -> dict[str, float | None]:
    """Every metric of one question, by metric name."""
    out: dict[str, float | None] = {f"ndcg@{NDCG_K}": ndcg_at_k(ranking, gold, NDCG_K)}
    for k in recall_ks:
        out[f"recall@{k}"] = recall_at_k(ranking, gold, k)
    out["mrr"] = reciprocal_rank(ranking, gold)
    return out


def settings(params: Mapping | None) -> tuple[list[int], int, str | None]:
    """(recall cutoffs, bootstrap seed, baseline configuration) from the experiment's params.

    ``recall_k``: one integer or a list, default 10. ``bootstrap_seed``: the seed the hypothesis card
    or the spec declares, default the lab's (stats.BOOTSTRAP_SEED). ``baseline``: the configuration every
    other one is compared with; without it, every pair is.
    """
    params = params or {}
    raw = params.get("recall_k", list(DEFAULT_RECALL_K))
    ks = list(raw) if isinstance(raw, (list, tuple)) else [raw]
    for k in ks:
        _check_k(k)
    if len(set(ks)) != len(ks):
        raise ValueError(f"recall_k has a repeated cutoff: {ks}")
    seed = params.get("bootstrap_seed", stats.BOOTSTRAP_SEED)
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError(f"bootstrap_seed must be an integer, got {seed!r}")  # noqa: TRY004
    return ks, seed, params.get("baseline")


def retrieval_metrics(rows: list[dict], prefix: str, recall_ks: Sequence[int] = DEFAULT_RECALL_K,
                      seed: int = stats.BOOTSTRAP_SEED, baseline: str | None = None,
                      replicates: int = stats.BOOTSTRAP_REPLICATES) -> list[dict]:
    """Retrieval metrics of one run.

    ``rows``: one per result with config, item_id (the question), ok, ranking (document ids) and gold
    (document id to grade). ``prefix``: "<experiment>/<run>". Per configuration and metric one row with
    the mean over questions and its bootstrap interval; per pair of configurations and metric one row
    with the difference ``b - a`` and its paired bootstrap interval. A failed result (ok false) counts
    in the details, not in the means.
    """
    names = metric_names(recall_ks)
    per_config: dict[str, dict] = {}
    for r in sorted(rows, key=lambda r: (r["config"], r["item_id"])):
        cfg = per_config.setdefault(r["config"], {"values": {m: {} for m in names}, "failed": 0,
                                                  "undefined": {m: 0 for m in names}})
        if not r["ok"]:
            cfg["failed"] += 1
            continue
        for metric, value in question_values(r["ranking"], r["gold"], recall_ks).items():
            if value is None:
                cfg["undefined"][metric] += 1
            else:
                cfg["values"][metric][r["item_id"]] = value
    out = []
    for name in sorted(per_config):
        cfg = per_config[name]
        for metric in names:
            values = cfg["values"][metric]
            mean, lo, hi = stats.bootstrap_mean(values, replicates, seed)
            details = {"failed": cfg["failed"], "undefined": cfg["undefined"][metric]}
            if metric != "mrr":
                details["k"] = int(metric.split("@")[1])
            out.append({"result_id": f"{prefix}/{name}/{metric}", "config": name, "metric": metric, "value": mean,
                        "ci_low": lo, "ci_high": hi, "n": len(values), "method": METHOD, "details": details})
    configs = sorted(per_config)
    if baseline is not None and baseline not in per_config:
        raise ValueError(f"baseline {baseline!r} is not a configuration of the run: {', '.join(configs)}")
    pairs = ([(baseline, b) for b in configs if b != baseline] if baseline is not None
             else [(a, b) for i, a in enumerate(configs) for b in configs[i + 1:]])
    for a, b in pairs:
        for metric in names:
            va = {q: (v, 1.0) for q, v in per_config[a]["values"][metric].items()}
            vb = {q: (v, 1.0) for q, v in per_config[b]["values"][metric].items()}
            d, lo, hi = stats.bootstrap_difference(va, vb, replicates, seed)
            out.append({"result_id": f"{prefix}/diff/{b}_minus_{a}/{metric}", "config": None,
                        "metric": f"{metric}_difference", "value": d, "ci_low": lo, "ci_high": hi,
                        "n": len(set(va) & set(vb)), "method": METHOD,
                        "details": {"a": a, "b": b, "difference": "b - a"}})
    return out
