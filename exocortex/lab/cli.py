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
    from exocortex.lab import claims, toy

    return {toy.KIND: toy.make_runner(conn, tenant), claims.KIND: claims.make_runner(conn, tenant)}


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


def _cmd_run(args: argparse.Namespace) -> int:
    """Set up an experiment from its spec and run one sample through the queue."""
    import os
    from pathlib import Path

    from exocortex.lab import experiments as ex
    from exocortex.lab import specs
    from exocortex.lab.db import connect, tenant_id

    spec = specs.load(Path(args.spec))
    with connect() as conn:
        tenant = tenant_id()
        ids = specs.setup(conn, spec)
        out = {"command": "run", "experiment": spec["slug"], "sample": args.sample}
        if args.setup_only:
            _print({**out, **ids})
            return 0
        try:
            version, prereg_hash = specs.preregistration(conn, spec)
        except specs.NotPreregistered as exc:
            _print({**out, "refused": str(exc)})
            return 4
        names = args.configs.split(",") if args.configs else list(ids["configs"])
        run_id = args.run_id or next_run_id(conn, ids["experiment"])
        try:
            run = ex.create_run(conn, ids["experiment"], run_id, ids["samples"][args.sample],
                                hypothesis_version=version, prereg_hash=prereg_hash,
                                code_commit=os.environ.get("EXOCORTEX_COMMIT"), notes=args.notes)
        except ex.ControlSampleAlreadyOpened as exc:
            _print({**out, "refused": str(exc)})
            return 3
        out["run_id"] = run_id
        out["jobs"] = ex.enqueue(conn, run, [ids["configs"][n] for n in names])
        summary = ex.work(conn, runners(conn, tenant), owner=f"run:{run_id}", run_uuid=run)
        out.update(done=summary.done, failed=summary.failed, model_switches=summary.switches(),
                   jobs_by_status=ex.finish_run(conn, run))
        rows = conn.execute(
            """SELECT c.name, count(*) AS results, count(*) FILTER (WHERE r.ok) AS ok,
                      sum((r.output->'counts'->>'extracted')::int) AS extracted,
                      sum((r.output->'counts'->>'usable')::int) AS usable,
                      sum(r.input_tokens) AS input_tokens, sum(r.output_tokens) AS output_tokens,
                      round(avg(r.latency_ms)) AS mean_latency_ms
               FROM exp_results r JOIN exp_configs c ON c.id = r.config_id WHERE r.run_id = %s
               GROUP BY c.name ORDER BY c.name""", (run,)).fetchall()
        out["by_config"] = [dict(r) for r in rows]
    _print(out)
    return 0


def _document_text(conn, tenant: str, kind: str, corpus: str | None):
    """Resolver of the text a result was computed on, for rating pages."""
    from exocortex.lab.claims import NODE
    from exocortex.lab.docsync import current_documents
    from exocortex.lab.toy import prose

    if kind == "toy":
        docs = {d["rel"]: d["body"] for d in current_documents(conn, tenant)}
        return lambda item_id, output: prose(docs.get(item_id, ""))

    def corpus_text(item_id: str, output: dict) -> str:
        row = conn.execute("""SELECT body FROM thoughts WHERE tenant_id = %s AND thought_type = %s
                              AND metadata->>'corpus' = %s AND metadata->>'arxiv_id' = %s""",
                           (tenant, NODE[output.get("text", "abstract")], corpus, item_id)).fetchone()
        return row["body"] if row else ""

    return corpus_text


def _cmd_blind(args: argparse.Namespace) -> int:
    import os
    from pathlib import Path

    from exocortex.lab import blind
    from exocortex.lab.db import connect, tenant_id
    from exocortex.lab.docs import split_front

    out_dir = Path(os.environ.get("LAB_OUT", "/lab-out"))
    with connect() as conn:
        tenant = tenant_id()
        exp = conn.execute("SELECT id, kind, params FROM experiments WHERE slug = %s", (args.experiment,)).fetchone()
        if exp is None:
            _print({"command": "blind", "error": f"no experiment {args.experiment}"})
            return 2
        exp_id = str(exp["id"])
        report: dict = {"command": f"blind {args.action}", "experiment": args.experiment, "sample": args.name}
        if args.action == "draw":
            runs = [r["id"] for r in conn.execute(
                "SELECT id FROM exp_runs WHERE experiment_id = %s AND run_id = ANY(%s)",
                (exp_id, args.runs.split(","))).fetchall()]
            candidates = blind.units(conn, [str(r) for r in runs],
                                     _document_text(conn, tenant, exp["kind"], exp["params"].get("corpus")))
            sample_id = blind.draw(conn, exp_id, args.name, candidates, args.seed, args.size, args.repeats)
            folder = out_dir / "blind" / args.experiment
            folder.mkdir(parents=True, exist_ok=True)
            for lang, other in (("pl", "en"), ("en", "pl")):
                counterpart = f"../../../{other}/experiments/{args.experiment}/{args.name}.md"
                (folder / f"{args.name}.{lang}.md").write_text(
                    blind.render(conn, sample_id, lang, args.experiment, counterpart), encoding="utf-8")
            report.update(runs=len(runs), candidates=len(candidates), sample_id=sample_id,
                          pages=str(folder))
        else:
            sample = conn.execute("SELECT id FROM exp_samples WHERE experiment_id = %s AND name = %s",
                                  (exp_id, args.name)).fetchone()
            if sample is None:
                _print({**report, "error": "no such sample"})
                return 2
            sample_id = str(sample["id"])
            if args.action == "import":
                text = Path(args.page).read_text(encoding="utf-8")
                front, _ = split_front(text)
                if front.get("rating_complete") is not True or not front.get("rater"):
                    _print({**report, "refused": "the page is not marked rating_complete: true with a rater"})
                    return 3
                _, items = blind.read_page(text, front.get("lang", "pl"))
                report["stored"] = blind.store(conn, sample_id, str(front["rater"]), items)
                report["summary"] = blind.summary(conn, sample_id, str(front["rater"]))
            elif args.action == "summary":
                report["summary"] = blind.summary(conn, sample_id, args.rater)
            elif args.action == "publish":
                for lang, other in (("pl", "en"), ("en", "pl")):
                    target = out_dir / lang / "generated" / "experiments" / args.experiment / f"{args.name}.md"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    counterpart = f"../../../../{other}/generated/experiments/{args.experiment}/{args.name}.md"
                    target.write_text(blind.rated_page(conn, sample_id, args.rater, lang, args.experiment, counterpart),
                                      encoding="utf-8")
                report["published"] = str(out_dir / "{pl,en}/generated/experiments" / args.experiment)
    _print(report)
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

    p = sub.add_parser("run", help="set up an experiment from its spec and run one sample through the queue")
    p.add_argument("--spec", required=True, help="lab/experiments/<slug>.yaml")
    p.add_argument("--sample", required=False, default=None)
    p.add_argument("--configs", default=None, help="comma-separated configuration names (default: all)")
    p.add_argument("--run-id", default=None)
    p.add_argument("--notes", default=None)
    p.add_argument("--setup-only", action="store_true", help="create the experiment, configurations and samples")
    p.set_defaults(func=_cmd_run)

    p = sub.add_parser("blind", help="blind samples: draw, import ratings, summary, publish (F3.5)")
    p.add_argument("action", choices=["draw", "import", "summary", "publish"])
    p.add_argument("--experiment", required=True)
    p.add_argument("--name", required=True, help="name of the blind sample, e.g. blind-tuning")
    p.add_argument("--runs", default="", help="draw: comma-separated run ids whose results are rated")
    p.add_argument("--seed", type=int, default=20260930)
    p.add_argument("--size", type=int, default=None, help="draw: number of units (default: all)")
    p.add_argument("--repeats", type=int, default=0, help="draw: units shown twice, for rater consistency")
    p.add_argument("--page", default=None, help="import: the rated page")
    p.add_argument("--rater", default=None, help="summary, publish: the rater's pseudonym")
    p.set_defaults(func=_cmd_blind)

    p = sub.add_parser("work", help="process queued jobs of every experiment, grouped by model")
    p.add_argument("--max-jobs", type=int, default=None)
    p.set_defaults(func=_cmd_work)
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
