# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Check the preregistration of hypothesis cards from a clone of the repository.

For every entry of dowody/prereg.jsonl: recompute the checksum of the two
card files (the method is described in exocortex/lab/prereg.py), compare
it with the registered one, find the commit that added the entry and its
date, and compare that date with the earliest run of the experiment
(dowody/data/<slug>/runs.csv, or the dates of run notes run-*.md).

Needs only Python 3.10+ and git; nothing to install.

    git clone https://github.com/hretheum/exocortex-public && cd exocortex-public
    python lab/verify_prereg.py

Exit code 0 when every card matches its entry and was registered before
its first run.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("prereg", ROOT / "exocortex" / "lab" / "prereg.py")
prereg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prereg)


def added_in(repo: Path, registry: Path, sha256: str) -> tuple[str, str] | None:
    """(commit, ISO date) of the first commit whose registry contains ``sha256``."""
    try:
        out = subprocess.run(["git", "-C", str(repo), "log", "--reverse", "--format=%H %cI", "-S", sha256, "--",
                              str(registry.relative_to(repo))], capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        return None
    first = out.strip().splitlines()[:1]
    return tuple(first[0].split(" ", 1)) if first else None


def first_run(docs: Path, slug: str, version: int) -> str | None:
    """Earliest date of a run of this hypothesis version, from published data or run notes."""
    dates = []
    runs = docs / "data" / slug / "runs.csv"
    if runs.is_file():
        with runs.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if str(row.get("hypothesis_version")) == str(version) and row.get("created_at"):
                    dates.append(row["created_at"])
    for note in docs.glob(f"*/experiments/{slug}/run-*.md"):
        text = note.read_text(encoding="utf-8")
        if re.search(rf"^hypothesis_version:\s*{version}\s*$", text, re.M):
            m = re.search(r'^date:\s*"?(\d{4}-\d{2}-\d{2})', text, re.M)
            if m:
                dates.append(m.group(1))
    return min(dates) if dates else None


def order(registered_at: str, first: str) -> str:
    """'registered first', 'same day' (a run note gives only a date) or 'RUN FIRST'."""
    import datetime as dt

    reg = dt.datetime.fromisoformat(registered_at).astimezone(dt.timezone.utc)
    if len(first) == 10:
        run_day = dt.date.fromisoformat(first)
        return "registered first" if reg.date() < run_day else "same day" if reg.date() == run_day else "RUN FIRST"
    run = dt.datetime.fromisoformat(first.replace("Z", "+00:00"))
    run = run if run.tzinfo else run.replace(tzinfo=dt.timezone.utc)
    return "registered first" if reg <= run.astimezone(dt.timezone.utc) else "RUN FIRST"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--docs", type=Path, default=ROOT / "dowody", help="the documents folder")
    ap.add_argument("--no-git", action="store_true", help="skip commit dates")
    ap.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = ap.parse_args(argv)
    registry = args.docs / "prereg.jsonl"
    entries = prereg.read_registry(registry)
    rows, ok = [], True
    for result in prereg.verify(args.docs, entries):
        row = {"card": f"{result['slug']} v{result['version']}", "checksum": result["status"],
               "registered_commit": None, "registered_at": None, "first_run": None, "order": "n/a"}
        if not args.no_git:
            found = added_in(ROOT, registry.resolve(), result["sha256"])
            if found:
                row["registered_commit"], row["registered_at"] = found[0][:12], found[1]
        row["first_run"] = first_run(args.docs, result["slug"], result["version"])
        if row["first_run"] and row["registered_at"]:
            row["order"] = order(row["registered_at"], row["first_run"])
        ok = ok and row["checksum"] == "ok" and row["order"] != "RUN FIRST"
        rows.append(row)
    if args.json:
        print(json.dumps({"entries": rows, "ok": ok}, indent=2))
    else:
        print(f"{len(rows)} registered card version(s) in {registry}")
        for r in rows:
            print(f"- {r['card']}: checksum {r['checksum']}; registered {r['registered_at'] or '?'} "
                  f"({r['registered_commit'] or 'commit not found'}); first run {r['first_run'] or 'none yet'}"
                  f" -> {r['order']}")
        print("OK" if ok else "PROBLEMS FOUND")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
