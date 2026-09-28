"""python -m tools.docschema check dowody"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .core import validate_tree


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="docschema")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("root")
    args = ap.parse_args(argv)
    checked, errors = validate_tree(Path(args.root))
    for e in errors:
        print(e)
    print(f"docschema: {checked} files with a schema, {len(errors)} errors -> {'OK' if not errors else 'FAIL'}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
