"""python -m tools.code_en extract <paths> --out f.json | apply f.json | check <paths>"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .extract import apply, extract


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="code_en")
    p.add_argument("--root", default=".")
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract", help="write Polish fragments to a JSON file for translation")
    e.add_argument("paths", nargs="+")
    e.add_argument("--out", required=True)
    a = sub.add_parser("apply", help="apply translated fragments")
    a.add_argument("fragments")
    c = sub.add_parser("check", help="exit 1 if any Polish fragment remains")
    c.add_argument("paths", nargs="+")
    args = p.parse_args(argv)
    root = Path(args.root).resolve()
    if args.cmd == "extract":
        items = extract([Path(x).resolve() for x in args.paths], root)
        Path(args.out).write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{len(items)} fragments in {len({i['file'] for i in items})} files")
        return 0
    if args.cmd == "apply":
        items = json.loads(Path(args.fragments).read_text(encoding="utf-8"))
        report = apply(items, root)
        print(f"applied {sum(report.values())} fragments in {len(report)} files")
        return 0
    if args.cmd == "check":
        items = extract([Path(x).resolve() for x in args.paths], root)
        for it in items:
            print(f"{it['file']}: {it['kind']}: {it['raw'][:80]!r}")
        print(f"{len(items)} Polish fragments", file=sys.stderr)
        return 1 if items else 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
