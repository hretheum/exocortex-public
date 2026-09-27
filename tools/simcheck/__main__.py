"""python -m tools.simcheck build-index | check | serve | calibrate"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import Embedder, Index, iter_dir_texts, iter_postgres_texts


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="simcheck")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build-index")
    b.add_argument("--dir", action="append", default=[], help="private corpus folder (repeatable)")
    b.add_argument("--pg-dsn", default=None, help="private Postgres DSN")
    b.add_argument("--pg-query", default="SELECT id, body FROM thoughts WHERE body IS NOT NULL")
    b.add_argument("--embed-url", default=None, help="OpenAI-compatible base URL for embeddings")
    b.add_argument("--embed-model", default="bge-m3")
    b.add_argument("--out", required=True)
    c = sub.add_parser("check")
    c.add_argument("--index", required=True)
    c.add_argument("files", nargs="+")
    s = sub.add_parser("serve")
    s.add_argument("--index", required=True)
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8099)
    k = sub.add_parser("calibrate")
    k.add_argument("--index", required=True)
    k.add_argument("--private-dir", action="append", required=True)
    k.add_argument("--public-dir", action="append", required=True)
    k.add_argument("--sample", type=int, default=200)
    k.add_argument("--seed", type=int, default=20260928)
    k.add_argument("--rewrite-url", default=None)
    k.add_argument("--rewrite-model", default=None)
    k.add_argument("--apply", action="store_true")
    k.add_argument("--out", default=None, help="write the calibration report (keep it private)")
    args = p.parse_args(argv)

    if args.cmd == "build-index":
        sources = []
        if args.dir:
            sources.append(iter_dir_texts([Path(d) for d in args.dir]))
        if args.pg_dsn:
            sources.append(iter_postgres_texts(args.pg_dsn, args.pg_query))
        embedder = Embedder(args.embed_url, args.embed_model) if args.embed_url else None
        index = Index.build((t for src in sources for t in src), embedder)
        index.save(Path(args.out))
        print(f"indexed {len(index.sigs)} paragraphs, semantic={'yes' if index.vectors is not None else 'no'}")
        return 0
    if args.cmd == "check":
        index = Index.load(Path(args.index))
        worst = 0
        for f in args.files:
            r = index.check(Path(f).read_text(encoding="utf-8", errors="ignore"))
            print(json.dumps({"file": f, **r.to_dict()}))
            worst = max(worst, int(r.similar))
        return worst
    if args.cmd == "serve":
        from .server import serve

        serve(Path(args.index), args.host, args.port)
        return 0
    if args.cmd == "calibrate":
        from .calibrate import apply, calibrate

        index = Index.load(Path(args.index))
        rewriter = (args.rewrite_url, args.rewrite_model) if args.rewrite_url and args.rewrite_model else None
        res = calibrate(index, [Path(d) for d in args.private_dir], [Path(d) for d in args.public_dir], args.sample, args.seed, rewriter)
        if args.out:
            Path(args.out).write_text(json.dumps(res, indent=2))
        print(json.dumps({k: v for k, v in res.items() if k in ("sample", "negatives")} | {
            "literal": {k: res["literal"][k] for k in ("threshold", "false_alarm_rate", "miss_rate")}}))
        if args.apply:
            apply(Path(args.index), res)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
