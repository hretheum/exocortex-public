# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Independent recomputation of the numbers of a retrieval experiment (roadmap task F5.8).

Uses only the standard library and none of the lab's code: not the metrics
(exocortex/lab/retrieval_metrics.py), not the bootstrap (exocortex/lab/stats.py),
not the question set parser. The gold answers come from the hand-made question
files in the corpus folder; the rankings come from results.csv. From these it
computes nDCG@10, recall@k and MRR per question, their means with 10,000
bootstrap resamples (percentiles 2.5 and 97.5, ``random.Random(seed)``), and
the paired differences between configurations, and compares every value with
metrics.csv. Equality is exact, not "close".

    python lab/independent_retrieval_check.py dowody/data/toy-retrieval lab/corpora/toy-retrieval

Exit code 0 when every published number is reproduced exactly.
"""

from __future__ import annotations

import csv
import json
import math
import random
import sys
from pathlib import Path

REPLICATES = 10_000
DEFAULT_SEED = 20260929


def read_questions(corpus: Path) -> dict[str, dict[str, int]]:
    """Gold answers by question id from every questions*.csv of the corpus folder."""
    gold: dict[str, dict[str, int]] = {}
    for path in sorted(corpus.glob("questions*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                entries = {}
                for part in row["gold"].split(";"):
                    doc, _, grade = part.strip().partition(":")
                    entries[doc] = int(grade) if grade else 1
                gold[row["question_id"]] = entries
    return gold


def ndcg10(ranking: list[str], gold: dict[str, int]) -> float:
    ideal = sorted((g for g in gold.values() if g > 0), reverse=True)[:10]
    best = sum(g / math.log2(rank + 1) for rank, g in enumerate(ideal, start=1))
    seen: list[str] = []
    for doc in ranking:
        if doc not in seen:
            seen.append(doc)
    got = sum(gold.get(doc, 0) / math.log2(rank + 1) for rank, doc in enumerate(seen[:10], start=1))
    return got / best


def recall(ranking: list[str], gold: dict[str, int], k: int) -> float:
    relevant = {d for d, g in gold.items() if g > 0}
    seen: list[str] = []
    for doc in ranking:
        if doc not in seen:
            seen.append(doc)
    return len(relevant & set(seen[:k])) / len(relevant)


def mrr(ranking: list[str], gold: dict[str, int]) -> float:
    relevant = {d for d, g in gold.items() if g > 0}
    seen: list[str] = []
    for doc in ranking:
        if doc not in seen:
            seen.append(doc)
    for rank, doc in enumerate(seen, start=1):
        if doc in relevant:
            return 1 / rank
    return 0.0


def percentile(values: list[float], q: float) -> float:
    pos = (len(values) - 1) * q
    low, high = math.floor(pos), math.ceil(pos)
    return values[low] if low == high else values[low] + (values[high] - values[low]) * (pos - low)


def mean_interval(values: dict[str, float], seed: int) -> tuple[float, float, float]:
    keys = sorted(values)
    rng = random.Random(seed)
    means = []
    for _ in range(REPLICATES):
        picked = [values[keys[rng.randrange(len(keys))]] for _ in keys]
        means.append(sum(picked) / float(len(picked)))
    means.sort()
    return sum(values[k] for k in keys) / float(len(keys)), percentile(means, 0.025), percentile(means, 0.975)


def difference_interval(a: dict[str, float], b: dict[str, float], seed: int) -> tuple[float, float, float]:
    keys = sorted(set(a) & set(b))
    rng = random.Random(seed)
    diffs = []
    for _ in range(REPLICATES):
        picked = [keys[rng.randrange(len(keys))] for _ in keys]
        diffs.append(sum(b[k] for k in picked) / float(len(picked)) - sum(a[k] for k in picked) / float(len(picked)))
    diffs.sort()
    estimate = sum(b[k] for k in keys) / float(len(keys)) - sum(a[k] for k in keys) / float(len(keys))
    return estimate, percentile(diffs, 0.025), percentile(diffs, 0.975)


def recompute(data: Path, corpus: Path) -> tuple[dict[str, tuple[float, float, float, int]], list[str]]:
    """({result id: (value, low, high, n)}, problems) from results.csv, the question files and the params."""
    package = json.loads((data / "datapackage.json").read_text(encoding="utf-8"))
    params = package["exocortex"]["params"]
    ks = params.get("recall_k", [10])
    ks = [ks] if isinstance(ks, int) else list(ks)
    seed = params.get("bootstrap_seed", DEFAULT_SEED)
    baseline = params.get("baseline")
    gold = read_questions(corpus)
    problems: list[str] = []
    per_run: dict[str, dict[str, dict[str, dict[str, float]]]] = {}
    with (data / "results.csv").open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row["ok"] != "true":
                continue
            output = json.loads(row["output"])
            ranking = [entry["doc"] for entry in output["ranking"]]
            answers = gold[row["item_id"]]
            if {d: int(g) for d, g in output["gold"].items()} != answers:
                problems.append(f"{row['run_id']}/{row['config']}/{row['item_id']}: the stored gold differs from the file")
            values = per_run.setdefault(row["run_id"], {}).setdefault(row["config"], {})
            values.setdefault("ndcg@10", {})[row["item_id"]] = ndcg10(ranking, answers)
            for k in ks:
                values.setdefault(f"recall@{k}", {})[row["item_id"]] = recall(ranking, answers, k)
            values.setdefault("mrr", {})[row["item_id"]] = mrr(ranking, answers)
    slug = data.name
    found: dict[str, tuple[float, float, float, int]] = {}
    for run, configs in per_run.items():
        names = sorted(configs)
        for name in names:
            for metric, values in configs[name].items():
                found[f"{slug}/{run}/{name}/{metric}"] = (*mean_interval(values, seed), len(values))
        pairs = ([(baseline, b) for b in names if b != baseline] if baseline
                 else [(a, b) for i, a in enumerate(names) for b in names[i + 1:]])
        for a, b in pairs:
            for metric in configs[a]:
                va, vb = configs[a][metric], configs[b][metric]
                found[f"{slug}/{run}/diff/{b}_minus_{a}/{metric}"] = (*difference_interval(va, vb, seed),
                                                                      len(set(va) & set(vb)))
    return found, problems


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print(__doc__.split("\n\n")[2].strip())
        return 2
    data, corpus = Path(args[0]), Path(args[1])
    found, problems = recompute(data, corpus)
    with (data / "metrics.csv").open(encoding="utf-8", newline="") as fh:
        published = list(csv.DictReader(fh))
    wrong = 0
    for row in published:
        mine = found.get(row["result_id"])
        if mine is None:
            print(f"missing   {row['result_id']}")
            wrong += 1
            continue
        theirs = (float(row["value"]), float(row["ci_low"]), float(row["ci_high"]), int(row["n"]))
        status = "ok" if theirs == mine else "DIFFERENT"
        wrong += status != "ok"
        print(f"{status:9} {row['result_id']}" + ("" if status == "ok" else f"  published {theirs}, recomputed {mine}"))
    for problem in problems:
        print(f"PROBLEM   {problem}")
    ok = not wrong and not problems and bool(published)
    print(f"{len(published)} published number(s); " + ("all reproduced exactly" if ok else "NOT all reproduced"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
