# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Recompute the numbers of an experiment's pages from its published CSV files.

Reads dowody/data/<slug>/ (results.csv, judgments.csv, metrics.csv,
datapackage.json), recomputes every metric the lab published for that
experiment with the same code the lab uses (exocortex/lab/stats.py and
metrics.py, loaded as plain files), and compares the two.

Needs only Python 3.10+; nothing to install.

    python lab/recompute.py toy-length

Exit code 0 when every published number is reproduced exactly.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "exocortex" / "lab" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


stats = _load("stats")
# metrics.py imports exocortex.lab.stats: point that name at the file loaded above, so an installed
# copy of the package can never be used instead of this checkout's code
_pkg, _lab = types.ModuleType("exocortex"), types.ModuleType("exocortex.lab")
_pkg.__path__, _lab.__path__, _lab.stats = [], [], stats
sys.modules.update({"exocortex": _pkg, "exocortex.lab": _lab, "exocortex.lab.stats": stats})
metrics = _load("metrics")
retrieval_metrics = _load("retrieval_metrics")
format_conformity_metrics = _load("format_conformity_metrics")


def _rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _float(value: str) -> float | None:
    return None if value in ("", None) else float(value)


def recompute_toy(folder: Path, params: dict) -> list[dict]:
    by_run: dict[str, list[dict]] = {}
    for r in _rows(folder / "results.csv"):
        out = json.loads(r["output"] or "{}")
        lengths = out.get("unit_chars") or []
        by_run.setdefault(r["run_id"], []).append({
            "config": r["config"], "item_id": r["item_id"], "ok": r["ok"] == "true", "chars": out.get("chars"),
            "unit_chars": lengths[0] if lengths else None})
    slug = folder.name
    found = []
    for run_id, rows in sorted(by_run.items()):
        found += metrics.toy_metrics(rows, f"{slug}/{run_id}", int(params.get("long_unit_chars", 120)))
    return found


def recompute_retrieval(folder: Path, params: dict) -> list[dict]:
    """Retrieval metrics from the rankings and gold answers that results.csv keeps with every result."""
    by_run: dict[str, list[dict]] = {}
    for r in _rows(folder / "results.csv"):
        out = json.loads(r["output"] or "{}")
        by_run.setdefault(r["run_id"], []).append({
            "config": r["config"], "item_id": r["item_id"], "ok": r["ok"] == "true",
            "ranking": [e["doc"] for e in out.get("ranking") or []], "gold": out.get("gold") or {}})
    ks, seed, baseline = retrieval_metrics.settings(params)
    found = []
    for run_id, rows in sorted(by_run.items()):
        found += retrieval_metrics.retrieval_metrics(rows, f"{folder.name}/{run_id}", ks, seed, baseline)
    return found


def recompute_format_conformity(folder: Path, params: dict) -> list[dict]:
    """Format conformity metrics from the verdicts and reasons that results.csv keeps with every answer."""
    fm = format_conformity_metrics
    by_run: dict[str, list[dict]] = {}
    for r in _rows(folder / "results.csv"):
        out = json.loads(r["output"] or "{}")
        by_run.setdefault(r["run_id"], []).append({
            "config": r["config"], "item_id": r["item_id"], "verdict": fm.row_verdict(r["ok"] == "true", out),
            "reasons": fm.reason_codes(out)})
    baseline, guard = fm.settings(params)
    found = []
    for run_id, rows in sorted(by_run.items()):
        found += fm.format_metrics(rows, f"{folder.name}/{run_id}", baseline, guard)
    return found


RECOMPUTE = {"toy": recompute_toy, "retrieval": recompute_retrieval,
             "format_conformity": recompute_format_conformity}


def compare(published: list[dict], recomputed: list[dict]) -> list[dict]:
    mine = {m["result_id"]: m for m in recomputed}
    out = []
    for p in published:
        m = mine.get(p["result_id"])
        row = {"result_id": p["result_id"], "status": "missing" if m is None else "ok"}
        if m is not None:
            for key in ("value", "ci_low", "ci_high"):
                a, b = _float(p[key]), m[key]
                if (a is None) != (b is None) or (a is not None and abs(a - b) > 1e-12):
                    row["status"] = "DIFFERENT"
                    row[key] = (p[key], b)
            if str(m["n"]) != p["n"]:
                row["status"] = "DIFFERENT"
                row["n"] = (p["n"], m["n"])
        out.append(row)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("slug")
    ap.add_argument("--data", type=Path, default=ROOT / "dowody" / "data")
    args = ap.parse_args(argv)
    folder = args.data / args.slug
    package = json.loads((folder / "datapackage.json").read_text(encoding="utf-8"))
    kind = package["exocortex"]["kind"]
    if kind not in RECOMPUTE:
        print(f"no recomputation for experiments of kind {kind!r} yet")
        return 2
    published = _rows(folder / "metrics.csv")
    rows = compare(published, RECOMPUTE[kind](folder, package["exocortex"]["params"]))
    for r in rows:
        extra = {k: v for k, v in r.items() if k not in ("result_id", "status")}
        print(f"{r['status']:9} {r['result_id']}" + (f"  {extra}" if extra else ""))
    ok = all(r["status"] == "ok" for r in rows) and bool(rows)
    print(f"{len(rows)} published number(s); " + ("all reproduced exactly" if ok else "NOT all reproduced"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
