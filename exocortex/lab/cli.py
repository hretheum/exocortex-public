# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Lab jobs: ``exocortex lab <command>`` or ``python -m exocortex.lab <command>``.

Every command prints one JSON document with what it did, so a run on the
server leaves a checkable record in the journal.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence


def _print(doc: dict) -> None:
    print(json.dumps(doc, ensure_ascii=False, indent=2, default=str), flush=True)


def _cmd_corpus_graph(args: argparse.Namespace) -> int:
    from exocortex.lab.corpus_graph import sync_corpus
    from exocortex.lab.db import connect, tenant_id

    embed = None
    if args.embed:
        from exocortex.lab.llm import LabLLM

        llm = LabLLM()
        embed = lambda texts: llm.embed(args.embed_model, texts)  # noqa: E731
    with connect() as conn:
        counts = sync_corpus(conn, tenant_id(), args.corpus, embed=embed)
    _print({"command": "corpus-graph", "corpus": args.corpus, **counts})
    return 0 if counts["checksum_problems"] == 0 else 1


def _cmd_docs_sync(args: argparse.Namespace) -> int:
    from pathlib import Path

    from exocortex.lab.db import connect, tenant_id
    from exocortex.lab.docsync import sync_documents

    with connect() as conn:
        counts = sync_documents(conn, tenant_id(), Path(args.root))
    _print({"command": "docs-sync", **counts})
    return 0


def _cmd_sync(args: argparse.Namespace) -> int:
    """Documents -> graph, hypothesis cards (+ registry), gate decisions; one JSON line per step."""
    import os
    from pathlib import Path

    from exocortex.lab import gates, hypotheses
    from exocortex.lab.db import connect, tenant_id
    from exocortex.lab.docsync import current_documents, sync_documents

    out_dir = Path(args.out or os.environ.get("LAB_OUT", "/lab-out"))
    with connect() as conn:
        tenant = tenant_id()
        report = {"command": "sync", "documents": sync_documents(conn, tenant, Path(args.root))}
        docs = current_documents(conn, tenant)
        report["hypotheses"] = hypotheses.process(conn, tenant, docs, out_dir / "prereg.jsonl")
        report["gates"] = gates.process(conn, tenant, docs)
    _print(report)
    return 0


def runners(conn, tenant: str) -> dict:
    """Runner for every experiment kind the lab knows."""
    from exocortex.lab import toy

    return {toy.KIND: toy.make_runner(conn, tenant)}


def next_run_id(conn, experiment_id: str) -> str:
    import datetime as dt

    day = dt.date.today().isoformat()
    n = conn.execute("SELECT count(*) AS n FROM exp_runs WHERE experiment_id = %s AND run_id LIKE %s",
                     (experiment_id, f"run-{day}-%")).fetchone()["n"]
    return f"run-{day}-{n + 1}"


def _cmd_toy(args: argparse.Namespace) -> int:
    import os

    from exocortex.lab import experiments as ex
    from exocortex.lab import toy
    from exocortex.lab.db import connect, tenant_id

    with connect() as conn:
        tenant = tenant_id()
        ids = toy.setup(conn, tenant)
        out = {"command": "toy", **ids}
        if args.action == "run":
            run_id = args.run_id or next_run_id(conn, ids["experiment"])
            try:
                run = ex.create_run(conn, ids["experiment"], run_id, ids["samples"][args.sample],
                                    hypothesis_version=args.hypothesis_version,
                                    code_commit=os.environ.get("EXOCORTEX_COMMIT"))
            except ex.ControlSampleAlreadyOpened as exc:
                _print({**out, "refused": str(exc)})
                return 3
            out["jobs"] = ex.enqueue(conn, run, list(ids["configs"].values()))
            summary = ex.work(conn, runners(conn, tenant), owner="toy", run_uuid=run)
            out.update(run_id=run_id, done=summary.done, failed=summary.failed, model_switches=summary.switches(),
                       model_order=summary.models, jobs_by_status=ex.finish_run(conn, run),
                       result_ids=toy.compute_metrics(conn, run))
    _print(out)
    return 0


def _cmd_work(args: argparse.Namespace) -> int:
    import socket

    from exocortex.lab import experiments as ex
    from exocortex.lab.db import connect, tenant_id

    with connect() as conn:
        summary = ex.work(conn, runners(conn, tenant_id()), owner=f"{socket.gethostname()}", max_jobs=args.max_jobs)
    _print({"command": "work", "done": summary.done, "failed": summary.failed, "model_switches": summary.switches()})
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="exocortex lab", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("corpus-graph", help="corpus papers as nodes of the lab graph (F3.2)")
    p.add_argument("--corpus", required=True)
    p.add_argument("--embed", action="store_true", help="add embeddings through the model gateway")
    p.add_argument("--embed-model", default="bge-m3")
    p.set_defaults(func=_cmd_corpus_graph)

    p = sub.add_parser("docs-sync", help="the published documents as sources and nodes of the lab graph")
    p.add_argument("--root", default="/vault/_source/dowody")
    p.set_defaults(func=_cmd_docs_sync)

    p = sub.add_parser("sync", help="documents, hypothesis cards and gate decisions into the lab (F2.4, F2.5)")
    p.add_argument("--root", default="/vault/_source/dowody")
    p.add_argument("--out", default=None, help="the lab's output folder (default: $LAB_OUT or /lab-out)")
    p.set_defaults(func=_cmd_sync)

    p = sub.add_parser("toy", help="toy experiment: set up, or run one sample through the queue (F2.6)")
    p.add_argument("action", choices=["setup", "run"])
    p.add_argument("--sample", choices=["tuning", "control"], default="tuning")
    p.add_argument("--hypothesis-version", type=int, default=1)
    p.add_argument("--run-id", default=None)
    p.set_defaults(func=_cmd_toy)

    p = sub.add_parser("work", help="process queued jobs of every experiment, grouped by model")
    p.add_argument("--max-jobs", type=int, default=None)
    p.set_defaults(func=_cmd_work)
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
