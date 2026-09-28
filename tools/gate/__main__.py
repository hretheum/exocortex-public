"""Container entrypoint for the publishing gate.

Every setting comes from the environment, so Quadlet units only choose the
command. Paths default to the mount points used by the units in
deploy/gate/quadlet/.

    publish       one publisher run (sparse checkout of the documents only)
    simcheck      serve the similarity index on 127.0.0.1
    build-index   rebuild the index from the private corpus, keep thresholds
    calibrate     calibrate simcheck thresholds and apply them
    selftest      plant canaries; set the lock file if one slips through
    export DIR    copy the deployment files shipped in the image to DIR
                  (quadlet/, systemd/, gate.env.example, README.md)
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys
from pathlib import Path

DEPLOY_DIR = Path(os.environ.get("GATE_QUADLET_DIR", "/opt/gate/deploy"))
# Published documents would match themselves; working notes in the private
# folder quote the public ones; arXiv paper summaries compiled by the engine
# are public texts and serve as calibration negatives. None of these is
# client material.
DEFAULT_EXCLUDE = "*/dowody/*,dowody/*,*/dowody-prywatne/robocze/*,dowody-prywatne/robocze/*,wiki/papers/*"


def env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name, default)
    if value is not None and value.strip().lower() in ("", "none", "unset"):
        return None
    return value


def state_dir() -> Path:
    p = Path(env("GATE_STATE", "/state"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def index_link() -> Path:
    return Path(env("GATE_INDEX", "/index")) / "current"


def cmd_publish() -> int:
    from tools.publisher.core import Settings, ensure_checkout, log, notify, publish

    repo = Path(env("GATE_REPO", "/repo"))
    url = env("GATE_REPO_URL")
    branch = env("GATE_BRANCH", "main")
    subdir = env("GATE_SUBDIR", "dowody")
    if not url:
        print("GATE_REPO_URL is not set", file=sys.stderr)
        return 2
    ensure_checkout(repo, url, branch, subdir)
    state = state_dir()
    s = Settings(
        source=Path(env("GATE_SOURCE", "/source")),
        repo=repo,
        subdir=subdir,
        lock_file=state / "gate.lock",
        log_file=state / "runs.jsonl",
        simcheck_url=env("GATE_SIMCHECK_URL", "http://127.0.0.1:8099"),
        push=env("GATE_PUSH", "1") == "1",
        branch=branch,
        dry_run=env("GATE_DRY_RUN", "0") == "1",
    )
    if env("GATE_AUTHOR"):
        s.author = env("GATE_AUTHOR")
    res = publish(s)
    log(res, s.log_file)
    channel = None if s.dry_run else notify(res)
    print(json.dumps({**res.to_dict(), "notified": channel}))
    return {"ok": 0, "nothing": 0, "held-only": 0, "locked": 3}.get(res.status, 1)


def cmd_simcheck() -> int:
    from tools.simcheck.server import serve

    link = index_link()
    if not link.exists():
        print(f"no index at {link}; run build-index first", file=sys.stderr)
        return 2
    serve(link, "127.0.0.1", int(env("GATE_SIMCHECK_PORT", "8099")))
    return 0


def cmd_build_index() -> int:
    from tools.simcheck.core import Embedder, Index, iter_dir_texts, iter_postgres_texts

    root = Path(env("GATE_INDEX", "/index"))
    root.mkdir(parents=True, exist_ok=True)
    sources = []
    corpus = env("SIMCHECK_CORPUS_DIR", "/corpus")
    exclude = [p for p in (env("SIMCHECK_EXCLUDE", DEFAULT_EXCLUDE) or "").split(",") if p]
    if corpus and Path(corpus).is_dir() and any(Path(corpus).iterdir()):
        sources.append(iter_dir_texts([Path(corpus)], exclude))
    dsn = env("SIMCHECK_PG_DSN")
    if dsn:
        sources.append(iter_postgres_texts(dsn, env("SIMCHECK_PG_QUERY", "SELECT id, body FROM thoughts WHERE body IS NOT NULL")))
    if not sources:
        print("no corpus: set SIMCHECK_CORPUS_DIR (mounted) and/or SIMCHECK_PG_DSN", file=sys.stderr)
        return 2
    url = env("SIMCHECK_EMBED_URL")
    embedder = Embedder(url, env("SIMCHECK_EMBED_MODEL", "bge-m3")) if url else None
    index = Index.build((t for src in sources for t in src), embedder)
    link = index_link()
    previous = link.resolve() if link.exists() else None
    if previous is not None:
        # calibrated thresholds belong to the deployment, not to one build
        index.thresholds = dict(Index.load(previous).thresholds)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = root / f"index-{stamp}"
    n = 1
    while target.exists():  # never overwrite the index that is being served
        target = root / f"index-{stamp}-{n}"
        n += 1
    index.save(target)
    if previous is not None and (previous / "calibration.json").exists():
        shutil.copy2(previous / "calibration.json", target / "calibration.json")
    tmp = root / "current.tmp"
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    tmp.symlink_to(target.name)
    os.replace(tmp, link)
    for old in sorted(root.glob("index-*"))[:-2]:
        shutil.rmtree(old, ignore_errors=True)
    print(json.dumps({"paragraphs": len(index.sigs), "semantic": index.vectors is not None,
                      "thresholds": index.thresholds, "index": target.name}))
    return 0


def cmd_calibrate() -> int:
    """Calibrate and (by default) apply simcheck thresholds.

    Negatives: the published documents in the checkout plus the folders in
    SIMCHECK_CALIBRATION_PUBLIC. The engine docs baked into the image are not
    used: they were written from notes that are part of the private corpus.
    SIMCHECK_CALIBRATION_FROM=<report.json> applies an earlier report without
    recomputing it (for example after reading it with SIMCHECK_CALIBRATION_APPLY=0).
    """
    from tools.simcheck.calibrate import apply, calibrate
    from tools.simcheck.core import Index

    link = index_link()
    from_report = env("SIMCHECK_CALIBRATION_FROM")
    if from_report:
        res = json.loads(Path(from_report).read_text(encoding="utf-8"))
        apply(link.resolve(), res)
        print(json.dumps({"applied": from_report, "literal": res["literal"]["threshold"],
                          "semantic": res.get("semantic", {}).get("threshold")}))
        return 0
    private = [Path(p) for p in (env("SIMCHECK_CALIBRATION_PRIVATE", env("SIMCHECK_CORPUS_DIR", "/corpus")) or "").split(",") if p]
    public = [Path(p) for p in (env("SIMCHECK_CALIBRATION_PUBLIC") or "").split(",") if p]
    repo_docs = Path(env("GATE_REPO", "/repo")) / env("GATE_SUBDIR", "dowody")
    if repo_docs.is_dir():
        public.append(repo_docs)
    rw_url, rw_model = env("SIMCHECK_REWRITE_URL"), env("SIMCHECK_REWRITE_MODEL")
    exclude = [p for p in (env("SIMCHECK_EXCLUDE", DEFAULT_EXCLUDE) or "").split(",") if p]
    res = calibrate(Index.load(link.resolve()), private, public, int(env("SIMCHECK_CALIBRATION_SAMPLE", "200")), 7,
                    (rw_url, rw_model) if rw_url and rw_model else None, exclude=exclude,
                    fa_budget=float(env("SIMCHECK_FA_BUDGET", "0.05") or "0.05"))
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    out = state_dir() / f"simcheck-calibration-{stamp}.json"
    out.write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
    applied = env("SIMCHECK_CALIBRATION_APPLY", "1") == "1"
    if applied:
        apply(link.resolve(), res)
    summary = {k: res[k] for k in ("sample", "negatives", "negatives_in_corpus")}
    for layer in ("literal", "semantic"):
        if layer in res:
            summary[layer] = {k: res[layer][k] for k in ("threshold", "policy", "false_alarm_rate", "miss_rate")}
    summary["report"] = str(out)
    summary["applied"] = applied
    print(json.dumps(summary))
    return 0


def cmd_selftest() -> int:
    from tools.leakgate.__main__ import main as leakgate_main

    state = state_dir()
    args = ["selftest", "--lock-file", str(state / "gate.lock"), "--results", str(state / "selftest.json")]
    private = env("LEAKGATE_PRIVATE_CASES", "/run/secrets/leakgate_private_cases")
    if private and Path(private).is_file():
        args += ["--private-cases", private]
    return leakgate_main(args)


def cmd_export(out: str) -> int:
    dst = Path(out)
    shutil.copytree(DEPLOY_DIR, dst, dirs_exist_ok=True)
    for f in sorted(p.relative_to(dst) for p in dst.rglob("*") if p.is_file()):
        print(f)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    handlers = {"publish": cmd_publish, "simcheck": cmd_simcheck, "build-index": cmd_build_index,
                "calibrate": cmd_calibrate, "selftest": cmd_selftest}
    if cmd == "export":
        return cmd_export(rest[0] if rest else "/out")
    if cmd not in handlers:
        print(__doc__, file=sys.stderr)
        return 2
    return handlers[cmd]()


if __name__ == "__main__":
    sys.exit(main())
