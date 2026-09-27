"""humanlint: flag habits of machine-written prose in Markdown files.

    python -m tools.humanlint check dowody            # exit 1 if a file crosses a threshold
    python -m tools.humanlint check dowody --verbose  # also list every match
    python -m tools.humanlint calibrate FILE...       # measure reference texts
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import load_config, run


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="humanlint")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("paths", nargs="+")
    c.add_argument("--verbose", action="store_true")
    c.add_argument("--json", action="store_true")
    k = sub.add_parser("calibrate", help="print measured rates for reference texts (no thresholds applied)")
    k.add_argument("paths", nargs="+")
    k.add_argument("--out", help="write per-file metrics (no text) as JSON")
    args = ap.parse_args(argv)

    reports = run([Path(p) for p in args.paths])
    if args.cmd == "calibrate":
        rows = [{"words": r.words, **r.metrics} for r in reports if r.words >= load_config()["min_words"]]
        summary = {}
        for key in ("hits_per_1000", "bold_mid_per_1000", "dash_per_1000", "same_start_share"):
            vals = sorted(row[key] for row in rows)
            if vals:
                summary[key] = {"max": vals[-1], "p90": vals[int(0.9 * (len(vals) - 1))], "median": vals[len(vals) // 2]}
        out = {"files": len(rows), "summary": summary, "per_file": rows}
        if args.out:
            Path(args.out).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 0

    bad = 0
    if args.json:
        print(json.dumps([{**r.__dict__, "hits": [h.__dict__ for h in r.hits]} for r in reports], indent=2, default=str))
    for r in reports:
        if r.failures and r.exempt is None:
            bad += 1
        if args.json:
            continue
        if r.failures or args.verbose:
            state = "FAIL" if (r.failures and r.exempt is None) else ("EXEMPT" if r.failures else "ok")
            print(f"{state} {r.path} ({r.words} words) {r.metrics}")
            for f in r.failures:
                print(f"    threshold: {f}")
            if r.exempt:
                print(f"    exception: {r.exempt}")
            if r.failures or args.verbose:
                for h in r.hits:
                    print(f"    line {h.line}: {h.rule}: {h.detail}")
    if not args.json:
        print(f"humanlint: {len(reports)} files, {bad} over threshold -> {'FAIL' if bad else 'OK'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
