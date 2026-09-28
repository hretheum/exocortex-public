"""python -m tools.publisher run --source DIR --repo DIR [options]"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import Settings, log, notify, publish


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="publisher")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="one publishing run")
    r.add_argument("--source", required=True, help="vault folder to publish (e.g. .../_source/dowody)")
    r.add_argument("--repo", required=True, help="working copy of the public repository")
    r.add_argument("--subdir", default="dowody")
    r.add_argument("--lock-file", default=None, help="gate lock flag; nothing is published while it exists")
    r.add_argument("--log-file", default=None, help="append one JSON line per run")
    r.add_argument("--simcheck-url", default=None, help="simcheck service, e.g. http://127.0.0.1:8099")
    r.add_argument("--push", action="store_true")
    r.add_argument("--branch", default="main")
    r.add_argument("--author", default=None, help='"Name <email>" for publisher commits')
    r.add_argument("--hashes", default=None, help="hashed denylist (default: tools/leakgate/data/denylist.hmac.json)")
    r.add_argument("--dry-run", action="store_true", help="run the checks, change nothing")
    r.add_argument("--lab-source", default=None, help="the lab's output folder (registry, generated pages, data)")
    args = ap.parse_args(argv)

    s = Settings(
        source=Path(args.source).expanduser(),
        repo=Path(args.repo).expanduser(),
        subdir=args.subdir,
        lock_file=Path(args.lock_file).expanduser() if args.lock_file else None,
        log_file=Path(args.log_file).expanduser() if args.log_file else None,
        simcheck_url=args.simcheck_url,
        push=args.push,
        branch=args.branch,
        dry_run=args.dry_run,
        hashes=Path(args.hashes).expanduser() if args.hashes else None,
        lab_source=Path(args.lab_source).expanduser() if args.lab_source else None,
    )
    if args.author:
        s.author = args.author
    res = publish(s)
    log(res, s.log_file)
    channel = None if args.dry_run else notify(res)
    out = res.to_dict()
    out["notified"] = channel
    print(json.dumps(out, indent=2))
    return {"ok": 0, "nothing": 0, "held-only": 0, "locked": 3}.get(res.status, 1)


if __name__ == "__main__":
    sys.exit(main())
