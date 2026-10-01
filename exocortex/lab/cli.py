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
    if not args.no_pages:
        # through the engine's dispatcher, the one the deployed compile units run (F2.7)
        os.environ.setdefault("LAB_OUT", str(out_dir))
        from exocortex.lab import export
        from exocortex.lab.db import connect as _connect
        from exocortex.wiki_compiler import compile_all

        with _connect() as conn:
            report["export"] = export.export_all(conn, out_dir)
        compile_all(tenant_id(), domain="dowody")
    _print(report)
    return 0


def runners(conn, tenant: str) -> dict:
    """Runner for every experiment kind the lab knows."""
    from exocortex.lab import claims, format_conformity, retrieval, toy

    return {toy.KIND: toy.make_runner(conn, tenant), claims.KIND: claims.make_runner(conn, tenant),
            retrieval.KIND: retrieval.make_runner(conn, tenant),
            format_conformity.KIND: format_conformity.make_runner(conn, tenant)}


def next_run_id(conn, experiment_id: str) -> str:
    import datetime as dt

    day = dt.date.today().isoformat()  # noqa: DTZ011 — local calendar date; an aware date would change behavior
    n = conn.execute("SELECT count(*) AS n FROM exp_runs WHERE experiment_id = %s AND run_id LIKE %s",
                     (experiment_id, f"run-{day}-%")).fetchone()["n"]
    return f"run-{day}-{n + 1}"


def _toy_run(conn, tenant: str, sample: str, *, run_id: str | None = None, hypothesis_version: int = 1,
             queue_only: bool = False) -> tuple[dict, int]:
    """One sample of the toy experiment through the queue; ``queue_only`` leaves the jobs for ``work``."""
    import os

    from exocortex.lab import experiments as ex
    from exocortex.lab import toy

    ids = toy.setup(conn, tenant)
    out = {"command": "toy", **ids}
    run_id = run_id or next_run_id(conn, ids["experiment"])
    try:
        run = ex.create_run(conn, ids["experiment"], run_id, ids["samples"][sample],
                            hypothesis_version=hypothesis_version, code_commit=os.environ.get("EXOCORTEX_COMMIT"))
    except ex.ControlSampleAlreadyOpened as exc:
        return {**out, "refused": str(exc)}, 3
    out.update(run_id=run_id, jobs=ex.enqueue(conn, run, list(ids["configs"].values())))
    if queue_only:
        return {**out, "queued": True}, 0
    summary = ex.work(conn, runners(conn, tenant), owner="toy", run_uuid=run)
    out.update(done=summary.done, failed=summary.failed, model_switches=summary.switches(),
               model_order=summary.models, jobs_by_status=ex.finish_run(conn, run),
               result_ids=toy.compute_metrics(conn, run))
    return out, 0


def _cmd_toy(args: argparse.Namespace) -> int:
    from exocortex.lab import toy
    from exocortex.lab.db import connect, tenant_id

    with connect() as conn:
        tenant = tenant_id()
        if args.action == "run":
            out, code = _toy_run(conn, tenant, args.sample, run_id=args.run_id,
                                 hypothesis_version=args.hypothesis_version, queue_only=args.queue_only)
            _print(out)
            return code
        out = {"command": "toy", **toy.setup(conn, tenant)}
    _print(out)
    return 0


NAME = r"[a-z0-9][a-z0-9-]*"  # no underscore: it separates the parts of a unit instance name


def parse_run_instance(instance: str) -> dict:
    """``<experiment>_<sample>[_<config>.<config>...][_queue]``, the instance name of exocortex-lab-run@.

    The instance also names the container, which allows only letters, digits, ``_``, ``.`` and ``-``, so
    the parts are joined with underscores and configurations with dots. The last part ``queue`` means:
    create the run and enqueue its jobs, leave them for ``exocortex lab work``.
    """
    import re

    parts = instance.split("_")
    queue = len(parts) > 2 and parts[-1] == "queue"
    if queue:
        parts = parts[:-1]
    if len(parts) not in (2, 3) or not all(re.fullmatch(NAME, p) for p in parts[:2]):
        raise ValueError(f"instance {instance!r} is not <experiment>_<sample>[_<config>.<config>][_queue]")
    configs = parts[2].split(".") if len(parts) == 3 else None
    if configs is not None and not all(re.fullmatch(NAME, c) for c in configs):
        raise ValueError(f"instance {instance!r}: bad configuration name")
    return {"experiment": parts[0], "sample": parts[1], "configs": configs, "queue_only": queue}


def _cmd_run(args: argparse.Namespace) -> int:
    """Set up an experiment from its spec and run one sample through the queue."""
    import os
    from pathlib import Path

    from exocortex.lab import experiments as ex
    from exocortex.lab import format_conformity, retrieval, specs, toy
    from exocortex.lab.claims import repo_path
    from exocortex.lab.db import connect, tenant_id

    input_errors = (retrieval.RetrievalInputError, format_conformity.FormatInputError)
    if args.instance:
        try:
            inst = parse_run_instance(args.instance)
        except ValueError as exc:
            _print({"command": "run", "refused": str(exc)})
            return 2
        args.experiment, args.sample, args.queue_only = inst["experiment"], inst["sample"], inst["queue_only"]
        args.configs = ",".join(inst["configs"]) if inst["configs"] else args.configs
    if args.experiment == toy.SLUG:  # the toy experiment has no spec file; its samples are tuning and control
        if args.sample not in ("tuning", "control") or args.configs:
            _print({"command": "run", "experiment": toy.SLUG, "refused": "toy-length runs tuning or control, all configurations"})
            return 2
        with connect() as conn:
            out, code = _toy_run(conn, tenant_id(), args.sample, run_id=args.run_id, queue_only=args.queue_only)
        _print({**out, "command": "run"})
        return code
    if not args.spec and not args.experiment:
        _print({"command": "run", "refused": "give --spec, --experiment or --instance"})
        return 2
    try:
        spec_path = Path(args.spec) if args.spec else repo_path(f"lab/experiments/{args.experiment}.yaml")
    except FileNotFoundError:
        _print({"command": "run", "experiment": args.experiment, "refused": "no spec in lab/experiments/"})
        return 2
    try:
        spec = specs.load(spec_path)
    except input_errors as exc:  # a malformed question set, prompt file or corpus: nothing is stored or run
        _print({"command": "run", "experiment": args.experiment or str(spec_path), "refused": exc.source,
                "problems": exc.problems})
        return 2
    with connect() as conn:
        tenant = tenant_id()
        try:
            ids = specs.setup(conn, spec)
        except input_errors as exc:
            _print({"command": "run", "experiment": spec["slug"], "refused": exc.source, "problems": exc.problems})
            return 2
        out = {"command": "run", "experiment": spec["slug"], "sample": args.sample}
        if args.setup_only:
            _print({**out, **ids})
            return 0
        try:
            version, prereg_hash = specs.preregistration(conn, spec)
        except specs.NotPreregistered as exc:
            _print({**out, "refused": str(exc)})
            return 4
        if args.sample not in ids["samples"]:
            _print({**out, "refused": f"no sample {args.sample!r}; the spec has {', '.join(ids['samples'])}"})
            return 2
        names = args.configs.split(",") if args.configs else list(ids["configs"])
        unknown = [n for n in names if n not in ids["configs"]]
        if unknown:
            _print({**out, "refused": f"no configuration {', '.join(unknown)}"})
            return 2
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
        if args.queue_only:
            _print({**out, "queued": True})
            return 0
        summary = ex.work(conn, runners(conn, tenant), owner=f"run:{run_id}", run_uuid=run)
        out.update(done=summary.done, failed=summary.failed, model_switches=summary.switches(),
                   jobs_by_status=ex.finish_run(conn, run))
        if spec["kind"] == retrieval.KIND:  # its numbers come from the rankings, not from claim counts
            out["result_ids"] = retrieval.compute_metrics(conn, run)
            _print(out)
            return 0
        if spec["kind"] == format_conformity.KIND:  # and these from the verdicts on the answers
            out["result_ids"] = format_conformity.compute_metrics(conn, run)
            _print(out)
            return 0
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


def _cmd_retrieval(args: argparse.Namespace) -> int:
    """Retrieval experiments (F5.8): check a spec with its corpus and question sets, or summarise a run."""
    from pathlib import Path

    from exocortex.lab import retrieval, specs
    from exocortex.lab.claims import repo_path
    from exocortex.lab.db import connect

    if args.action == "validate":
        try:
            path = Path(args.spec) if args.spec else repo_path(f"lab/experiments/{args.experiment}.yaml")
        except FileNotFoundError:
            _print({"command": "retrieval validate", "refused": "no spec: give --spec or --experiment"})
            return 2
        try:
            spec = specs.load(path)
        except retrieval.RetrievalInputError as exc:
            _print({"command": "retrieval validate", "ok": False, "problems": exc.problems})
            return 1
        except ValueError as exc:
            _print({"command": "retrieval validate", "ok": False, "problems": [str(exc)]})
            return 1
        if spec["kind"] != retrieval.KIND:
            _print({"command": "retrieval validate", "refused": f"the spec is of kind {spec['kind']!r}"})
            return 2
        questions = {s["name"]: len(retrieval.sample_items(spec, s)) for s in spec["samples"]}
        _print({"command": "retrieval validate", "ok": True, "experiment": spec["slug"], "questions": questions,
                "configs": [c["name"] for c in spec["configs"]]})
        return 0
    if not args.experiment:
        _print({"command": "retrieval summary", "refused": "give --experiment"})
        return 2
    with connect() as conn:
        try:
            result = retrieval.summary(conn, args.experiment, args.run)
        except LookupError as exc:
            _print({"command": "retrieval summary", "refused": str(exc)})
            return 2
    _print({"command": "retrieval summary", **result})
    return 0


def _cmd_format_conformity(args: argparse.Namespace) -> int:
    """Format conformity experiments (F5.9): check a spec with its schemas and prompt files, or summarise a run."""
    from pathlib import Path

    from exocortex.lab import format_conformity as fc
    from exocortex.lab import specs
    from exocortex.lab.claims import repo_path
    from exocortex.lab.db import connect

    name = "format_conformity " + args.action
    if args.action == "validate":
        try:
            path = Path(args.spec) if args.spec else repo_path(f"lab/experiments/{args.experiment}.yaml")
        except FileNotFoundError:
            _print({"command": name, "refused": "no spec: give --spec or --experiment"})
            return 2
        try:
            spec = specs.load(path)
        except fc.FormatInputError as exc:
            _print({"command": name, "ok": False, "problems": exc.problems})
            return 1
        except ValueError as exc:
            _print({"command": name, "ok": False, "problems": [str(exc)]})
            return 1
        if spec["kind"] != fc.KIND:
            _print({"command": name, "refused": f"the spec is of kind {spec['kind']!r}"})
            return 2
        items = {s["name"]: len(fc.sample_items(spec, s)) for s in spec["samples"]}
        _print({"command": name, "ok": True, "experiment": spec["slug"], "items": items,
                "configs": [c["name"] for c in spec["configs"]], "guard": (spec.get("params") or {}).get("guard")})
        return 0
    if not args.experiment:
        _print({"command": name, "refused": "give --experiment"})
        return 2
    with connect() as conn:
        try:
            result = fc.summary(conn, args.experiment, args.run)
        except LookupError as exc:
            _print({"command": name, "refused": str(exc)})
            return 2
    _print({"command": name, **result})
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


BLIND_ACTIONS = ("draw", "import", "summary", "publish")


def parse_blind_instance(instance: str) -> dict:
    """``<action>_<experiment>_<sample>[_<argument>]``, the instance name of exocortex-lab-blind@.

    The argument is the action's own: for ``draw`` the run ids (joined with dots; default: the newest run of
    the experiment), for ``import`` the name of the rated page in the experiment's folder (default: the
    sample name), for ``summary`` and ``publish`` the rater (default: the only rater of the sample).
    """
    import re

    parts = instance.split("_")
    if len(parts) not in (3, 4) or parts[0] not in BLIND_ACTIONS or not all(re.fullmatch(NAME, p) for p in parts[1:3]):
        raise ValueError(f"instance {instance!r} is not <draw|import|summary|publish>_<experiment>_<sample>[_<argument>]")
    arg = parts[3] if len(parts) == 4 else None
    if arg is not None and not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", arg):
        raise ValueError(f"instance {instance!r}: bad argument")
    out = {"action": parts[0], "experiment": parts[1], "name": parts[2]}
    if arg and parts[0] == "draw":
        out["runs"] = arg.replace(".", ",")
    elif arg and parts[0] == "import":
        out["page_name"] = arg
    elif arg:
        out["rater"] = arg
    return out


def _blind_page(root, experiment: str, name: str):
    """The rated page ``{pl,en}/experiments/<experiment>/<name>.md`` in the documents tree (Polish first)."""
    for lang in ("pl", "en"):
        p = root / lang / "experiments" / experiment / f"{name}.md"
        if p.is_file():
            return p
    return None


def _cmd_blind(args: argparse.Namespace) -> int:
    import os
    from pathlib import Path

    from exocortex.lab import blind
    from exocortex.lab.db import connect, tenant_id
    from exocortex.lab.docs import split_front

    if args.instance:
        try:
            inst = parse_blind_instance(args.instance)
        except ValueError as exc:
            _print({"command": "blind", "refused": str(exc)})
            return 2
        args.action, args.experiment, args.name = inst["action"], inst["experiment"], inst["name"]
        args.runs = inst.get("runs", args.runs)
        args.rater = inst.get("rater", args.rater)
        if args.action == "import" and not args.page:
            page = _blind_page(Path(args.root), args.experiment, inst.get("page_name", args.name))
            if page is None:
                _print({"command": "blind import", "experiment": args.experiment, "sample": args.name,
                        "refused": "no rated page in {pl,en}/experiments/<experiment>/ of the documents tree"})
                return 2
            args.page = str(page)
    if not (args.action and args.experiment and args.name):
        _print({"command": "blind", "refused": "give the action, --experiment and --name, or --instance"})
        return 2
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
            if args.runs:
                runs = [r["id"] for r in conn.execute(
                    "SELECT id FROM exp_runs WHERE experiment_id = %s AND run_id = ANY(%s)",
                    (exp_id, args.runs.split(","))).fetchall()]
            else:  # the newest finished run of the experiment
                runs = [r["id"] for r in conn.execute(
                    """SELECT id FROM exp_runs WHERE experiment_id = %s AND status = 'done'
                       ORDER BY created_at DESC LIMIT 1""", (exp_id,)).fetchall()]
            if not runs:
                _print({**report, "refused": "no such run (or no finished run) of the experiment"})
                return 2
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
            if args.action in ("summary", "publish") and not args.rater:
                raters = [r["rater"] for r in conn.execute(
                    "SELECT DISTINCT rater FROM exp_judgments WHERE sample_id = %s ORDER BY rater", (sample_id,))]
                if len(raters) != 1:
                    _print({**report, "refused": "name the rater", "raters": raters})
                    return 2
                args.rater = raters[0]
                report["rater"] = args.rater
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


def _cmd_signals(args: argparse.Namespace) -> int:
    """Download the radar channels through the fetch gateway and put them into the lab graph (F5.2)."""
    from exocortex.lab import signals
    from exocortex.lab.db import connect, tenant_id

    fetch = signals.LabFetch()
    chosen = args.channels.split(",") if args.channels else list(signals.CHANNELS)
    items, errors = [], {}
    for name in chosen:
        try:
            func = signals.CHANNELS[name]
            items += func(fetch, days=args.days) if name == "arxiv" else func(fetch)
        except Exception as exc:  # noqa: BLE001 - one broken channel must not stop the others
            errors[name] = f"{type(exc).__name__}: {str(exc)[:200]}"
    embed = None
    if args.embed:
        from exocortex.lab.llm import LabLLM

        llm = LabLLM()
        embed = lambda texts: llm.embed("bge-m3", texts)  # noqa: E731
    with connect() as conn:
        counts = signals.ingest(conn, tenant_id(), items, embed=embed)
    _print({"command": "signals", "channels": counts, "errors": errors})
    return 1 if errors else 0


def _cmd_radar(args: argparse.Namespace) -> int:
    """The week's opportunity radar page from the lab graph (F5.1)."""
    import datetime as dt
    import os
    from pathlib import Path

    from exocortex.lab import radar
    from exocortex.lab.db import connect, tenant_id
    from exocortex.lab.llm import LabLLM

    day = dt.date.fromisoformat(args.date) if args.date else None
    with connect() as conn:
        result = radar.run(conn, tenant_id(), LabLLM(), Path(os.environ.get("LAB_OUT", "/lab-out")), day=day,
                           model=args.model, extract=not args.no_extract)
    _print({"command": "radar", **result})
    return 0


def _cmd_triage(args: argparse.Namespace) -> int:
    """First scoring of the week's radar candidates by three model families (F5.3)."""
    import datetime as dt
    import os
    from pathlib import Path

    from exocortex.lab import triage
    from exocortex.lab.db import connect, tenant_id
    from exocortex.lab.llm import LabLLM

    day = dt.date.fromisoformat(args.date) if args.date else None
    with connect() as conn:
        result = triage.run(conn, tenant_id(), LabLLM(), Path(os.environ.get("LAB_OUT", "/lab-out")), day=day,
                            limit=args.limit)
    _print({"command": "triage", **result})
    return 0


def _cmd_applications(args: argparse.Namespace) -> int:
    """Draft or check the business applications section of a hypothesis page (F8.1)."""
    import os
    from pathlib import Path

    from exocortex.lab import applications

    root = Path(args.root)
    lab_data = Path(os.environ["LAB_OUT"]) / "data" if os.environ.get("LAB_OUT") else None
    data = Path(args.data) if args.data else (lab_data if lab_data and lab_data.is_dir() else root / "data")
    scanner, missing = (None, "names: not checked (--skip-name-check)") if args.skip_name_check \
        else applications.name_scanner()
    if args.action == "check":
        rep = applications.check(root, args.slug, data, scanner=scanner, scanner_missing=missing)
        _print({"command": "applications check", "slug": args.slug, "ok": rep.ok, "problems": rep.problems})
        return 0 if rep.ok else 1
    from exocortex.lab.llm import LabLLM

    result = applications.draft(root, args.slug, LabLLM(), data=data, out=Path(args.out) if args.out else None,
                                model=args.model, attempts=args.attempts, force=args.force, scanner=scanner,
                                scanner_missing=missing)
    _print({"command": "applications draft", **result})
    return 1 if "refused" in result else 0


def _cmd_card_check(args: argparse.Namespace) -> int:
    """Check reference cards against the general card model (F4.1); no database needed."""
    from pathlib import Path

    from exocortex.lab import card_model

    cards = {p: [str(x) for x in card_model.check_file(Path(p))] for p in args.cards}
    _print({"command": "card-check", "cards": cards})
    return 1 if any(cards.values()) else 0


def _cmd_card_compile(args: argparse.Namespace) -> int:
    """Compile the reference card of an experiment from its published files (F4.2); no database needed."""
    from pathlib import Path

    from exocortex.lab import card_compiler

    try:
        compiled = card_compiler.compile_card(
            args.slug, out=Path(args.out) if args.out else None, root=Path(args.root) if args.root else None,
            as_of=args.as_of, base_url=args.base_url)
    except card_compiler.CompileError as exc:
        _print({"command": "card-compile", "experiment": args.slug, "error": str(exc)})
        return 2
    _print(card_compiler.report(compiled))
    return 0 if compiled.ok else 1


def _cmd_work(args: argparse.Namespace) -> int:
    import socket

    from exocortex.lab import experiments as ex
    from exocortex.lab import format_conformity, retrieval, toy
    from exocortex.lab.db import connect, tenant_id

    with connect() as conn:
        summary = ex.work(conn, runners(conn, tenant_id()), owner=f"{socket.gethostname()}", max_jobs=args.max_jobs)
        finished = ex.finish_open_runs(conn)
        for run in finished:
            if run["kind"] == toy.KIND:  # the toy experiment's metrics, as `toy run` stores them
                run["result_ids"] = toy.compute_metrics(conn, run["id"])
            elif run["kind"] == retrieval.KIND:
                run["result_ids"] = retrieval.compute_metrics(conn, run["id"])
            elif run["kind"] == format_conformity.KIND:
                run["result_ids"] = format_conformity.compute_metrics(conn, run["id"])
    _print({"command": "work", "done": summary.done, "failed": summary.failed, "model_switches": summary.switches(),
            "finished_runs": [{k: v for k, v in r.items() if k != "id"} for r in finished]})
    return 0


def _cmd_honesty(args: argparse.Namespace) -> int:
    from pathlib import Path

    from exocortex.lab import honesty

    data = [Path(d) for d in (args.data or ["dowody/data"])]
    report, code = honesty.run(Path(args.card), data, Path(args.modes) if args.modes else None)
    _print(report)
    return code


def build_parser() -> argparse.ArgumentParser:
    import os

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
    p.add_argument("--no-pages", action="store_true", help="skip the data export and the result pages")
    p.set_defaults(func=_cmd_sync)

    p = sub.add_parser("toy", help="toy experiment: set up, or run one sample through the queue (F2.6)")
    p.add_argument("action", choices=["setup", "run"])
    p.add_argument("--sample", choices=["tuning", "control"], default="tuning")
    p.add_argument("--hypothesis-version", type=int, default=1)
    p.add_argument("--run-id", default=None)
    p.add_argument("--queue-only", action="store_true", help="create the run and enqueue its jobs for `work`")
    p.set_defaults(func=_cmd_toy)

    p = sub.add_parser("run", help="set up an experiment from its spec and run one sample through the queue")
    p.add_argument("--spec", default=None, help="lab/experiments/<slug>.yaml")
    p.add_argument("--experiment", default=None, help="the slug; the spec comes from lab/experiments/<slug>.yaml")
    p.add_argument("--instance", default=None,
                   help="<experiment>_<sample>[_<config>.<config>][_queue], the instance of an exocortex-lab-run@ unit")
    p.add_argument("--sample", required=False, default=None)
    p.add_argument("--configs", default=None, help="comma-separated configuration names (default: all)")
    p.add_argument("--run-id", default=None)
    p.add_argument("--notes", default=None)
    p.add_argument("--setup-only", action="store_true", help="create the experiment, configurations and samples")
    p.add_argument("--queue-only", action="store_true", help="create the run and enqueue its jobs for `work`")
    p.set_defaults(func=_cmd_run)

    p = sub.add_parser("retrieval", help="retrieval experiments: check a spec and its question sets, summary of a run (F5.8)")
    p.add_argument("action", choices=["validate", "summary"])
    p.add_argument("--spec", default=None, help="validate: lab/experiments/<slug>.yaml")
    p.add_argument("--experiment", default=None, help="the slug (validate: its spec comes from lab/experiments/)")
    p.add_argument("--run", default=None, help="summary: the run id (default: the newest finished run)")
    p.set_defaults(func=_cmd_retrieval)

    p = sub.add_parser("format_conformity", aliases=["format-conformity"],
                       help="format conformity experiments: check a spec, its schemas and prompt files, summary of a run (F5.9)")
    p.add_argument("action", choices=["validate", "summary"])
    p.add_argument("--spec", default=None, help="validate: lab/experiments/<slug>.yaml")
    p.add_argument("--experiment", default=None, help="the slug (validate: its spec comes from lab/experiments/)")
    p.add_argument("--run", default=None, help="summary: the run id (default: the newest finished run)")
    p.set_defaults(func=_cmd_format_conformity)

    p = sub.add_parser("blind", help="blind samples: draw, import ratings, summary, publish (F3.5)")
    p.add_argument("action", nargs="?", choices=BLIND_ACTIONS)
    p.add_argument("--experiment", default=None)
    p.add_argument("--name", default=None, help="name of the blind sample, e.g. blind-tuning")
    p.add_argument("--instance", default=None,
                   help="<action>_<experiment>_<sample>[_<argument>], the instance of an exocortex-lab-blind@ unit")
    p.add_argument("--root", default="/vault/_source/dowody", help="import --instance: the documents tree")
    p.add_argument("--runs", default=os.environ.get("LAB_BLIND_RUNS", ""),
                   help="draw: comma-separated run ids whose results are rated (default: the newest finished run)")
    p.add_argument("--seed", type=int, default=int(os.environ.get("LAB_BLIND_SEED") or 20260930))
    p.add_argument("--size", type=int, default=int(os.environ["LAB_BLIND_SIZE"]) if os.environ.get("LAB_BLIND_SIZE") else None,
                   help="draw: number of units (default: all)")
    p.add_argument("--repeats", type=int, default=int(os.environ.get("LAB_BLIND_REPEATS") or 0),
                   help="draw: units shown twice, for rater consistency")
    p.add_argument("--page", default=None, help="import: the rated page")
    p.add_argument("--rater", default=os.environ.get("LAB_BLIND_RATER") or None,
                   help="summary, publish: the rater's pseudonym (default: the only rater of the sample)")
    p.set_defaults(func=_cmd_blind)

    p = sub.add_parser("signals", help="radar channels into the lab graph (F5.2)")
    p.add_argument("--channels", default=None, help="comma-separated: arxiv, models, open-data, tools (default: all)")
    p.add_argument("--days", type=int, default=7, help="arxiv: papers from the last N days")
    p.add_argument("--embed", action="store_true", help="add embeddings through the model gateway")
    p.set_defaults(func=_cmd_signals)

    p = sub.add_parser("radar", help="the week's opportunity radar page (F5.1)")
    p.add_argument("--date", default=None, help="a day of the week to compile (default: today)")
    p.add_argument("--model", default="qwen3.6-35b-a3b")
    p.add_argument("--no-extract", action="store_true", help="do not run the extractor on new papers")
    p.set_defaults(func=_cmd_radar)

    p = sub.add_parser("triage", help="score the week's radar candidates with three model families (F5.3)")
    p.add_argument("--date", default=None)
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=_cmd_triage)

    p = sub.add_parser("applications", help="business applications section of a hypothesis page (F8.1)")
    p.add_argument("action", choices=["draft", "check"])
    p.add_argument("slug", help="the experiment folder under {pl,en}/experiments/")
    p.add_argument("--root", default="/vault/_source/dowody", help="the documents tree")
    p.add_argument("--data", default=None, help="exported data (default: $LAB_OUT/data if present, else <root>/data)")
    p.add_argument("--out", default=None, help="draft: the documents tree to write into (default: --root)")
    p.add_argument("--model", default="qwen3.6-35b-a3b", help="a model from lab/models.yaml")
    p.add_argument("--attempts", type=int, default=2, help="draft: model calls before giving up")
    p.add_argument("--force", action="store_true", help="draft: redraft even if the section is current")
    p.add_argument("--skip-name-check", action="store_true",
                   help="do not load the gate's denylist (check then fails; draft records it as not run)")
    p.set_defaults(func=_cmd_applications)

    p = sub.add_parser("card-check", help="check reference cards against the general card model (F4.1)")
    p.add_argument("cards", nargs="+", help="card files, e.g. lab/cards/toy-length.en.yaml")
    p.set_defaults(func=_cmd_card_check)

    p = sub.add_parser("card-compile", help="compile the reference card of an experiment (F4.2); exit 1 if a check fails")
    p.add_argument("slug", help="experiment slug, e.g. toy-length")
    p.add_argument("--out", default=None, help="output folder (default: a new temporary folder)")
    p.add_argument("--root", default=None, help="repository root (default: this checkout)")
    p.add_argument("--as-of", default=None, help="date of statements about the current state, YYYY-MM-DD (default: today)")
    p.add_argument("--base-url", default="https://github.com/hretheum/exocortex-public/blob/main/",
                   help="prefix of the links next to the sentences")
    p.set_defaults(func=_cmd_card_compile)

    p = sub.add_parser("honesty", help="honesty check of a reference card's sentences (F4.3); exit 1 on violations")
    p.add_argument("card", help="sentence records, JSON Lines or a JSON list (exocortex/lab/honesty.py: Sentence)")
    p.add_argument("--data", action="append", default=None,
                   help="experiment folder with metrics.csv/results.csv, or a folder of them (repeatable; "
                        "default dowody/data)")
    p.add_argument("--modes", help="mode classifier output, JSON Lines {text, mode}; without it the compiler's labels")
    p.set_defaults(func=_cmd_honesty)

    p = sub.add_parser("work", help="process queued jobs of every experiment, grouped by model")
    p.add_argument("--max-jobs", type=int, default=None)
    p.set_defaults(func=_cmd_work)
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
