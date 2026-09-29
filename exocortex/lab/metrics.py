# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Metrics of lab experiments from plain rows (standard library only).

The lab computes these from its tables; lab/recompute.py computes them from
the published CSV files with this same code, so both give identical numbers.
"""

from __future__ import annotations

from exocortex.lab import stats  # lab/recompute.py maps this name to the checkout's stats.py


def toy_metrics(rows: list[dict], prefix: str, long_unit: int) -> list[dict]:
    """Toy experiment metrics of one run.

    ``rows``: one per result with config, item_id, ok, chars and unit_chars
    (length of the chosen sentence, None when there is none). ``prefix``:
    "<experiment>/<run>".
    """
    by_config: dict[str, dict] = {}
    for r in sorted(rows, key=lambda r: (r["config"], r["item_id"])):
        cfg = by_config.setdefault(r["config"], {"chars": {}, "long": {}})
        if r["ok"]:
            cfg["chars"][r["item_id"]] = float(r["chars"])
            long = r["unit_chars"] is not None and r["unit_chars"] > long_unit
            cfg["long"][r["item_id"]] = (1.0 if long else 0.0, 1.0)
    out = []
    for name, cfg in sorted(by_config.items()):
        mean, lo, hi = stats.bootstrap_mean(cfg["chars"])
        out.append({"result_id": f"{prefix}/{name}/mean_chars", "config": name, "metric": "mean_chars",
                    "value": mean, "ci_low": lo, "ci_high": hi, "n": len(cfg["chars"]),
                    "method": "bootstrap-by-item", "details": {}})
        k = int(sum(v[0] for v in cfg["long"].values()))
        p, lo, hi = stats.wilson(k, len(cfg["long"]))
        out.append({"result_id": f"{prefix}/{name}/long_unit_share", "config": name, "metric": "long_unit_share",
                    "value": p, "ci_low": lo, "ci_high": hi, "n": len(cfg["long"]), "method": "wilson",
                    "details": {"successes": k}})
    names = sorted(by_config)
    if len(names) == 2:
        a, b = by_config[names[0]]["long"], by_config[names[1]]["long"]
        d, lo, hi = stats.bootstrap_difference(a, b)
        out.append({"result_id": f"{prefix}/diff/long_unit_share", "config": None,
                    "metric": "long_unit_share_difference", "value": d, "ci_low": lo, "ci_high": hi,
                    "n": len(set(a) & set(b)), "method": "bootstrap-by-item",
                    "details": {"a": names[0], "b": names[1], "difference": "b - a"}})
    return out
