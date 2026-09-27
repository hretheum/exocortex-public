"""paritycheck: compare Polish and English versions of documents.

    python -m tools.paritycheck check dowody
    python -m tools.paritycheck draft dowody/pl/x.md --llm-url URL --model NAME
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import check


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="paritycheck")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="compare every pl/en pair under ROOT")
    c.add_argument("root")
    c.add_argument("--json", action="store_true")
    d = sub.add_parser("draft", help="machine-translate a file that has no pair (marked translation: machine)")
    d.add_argument("file")
    d.add_argument("--glossary", default=None, help="glossary.yaml (default: ROOT/glossary.yaml)")
    d.add_argument("--llm-url", required=True, help="OpenAI-compatible base URL, e.g. http://127.0.0.1:8080/v1")
    d.add_argument("--model", required=True)
    args = ap.parse_args(argv)

    if args.cmd == "check":
        res = check(Path(args.root))
        if args.json:
            print(json.dumps({"pairs": res.pairs, "problems": [p.__dict__ for p in res.problems]}, indent=2))
        else:
            for p in res.problems:
                print(p)
            print(f"paritycheck: {res.pairs} pairs, {len(res.problems)} problems -> {'OK' if res.ok else 'FAIL'}")
        return 0 if res.ok else 1

    from .draft import draft

    out = draft(Path(args.file), args.llm_url, args.model, Path(args.glossary) if args.glossary else None)
    print(f"draft written to {out}; review it and remove 'translation: machine' before publishing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
