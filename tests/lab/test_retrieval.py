# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Experiment kind ``retrieval`` through the queue on a real database (roadmap task F5.8): the toy experiment from
run to export, checked against a calculation that shares no code with the lab; refusals; the graph index."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import uuid

import pytest
import yaml

from exocortex.lab import experiments as ex
from exocortex.lab import retrieval as R
from exocortex.lab import specs
from tests.lab.conftest import ROOT, needs_engine
from tests.unit.test_lab_retrieval import good_spec, make_root

TOY = ROOT / "lab" / "experiments" / "toy-retrieval.yaml"


def _independent():
    spec = importlib.util.spec_from_file_location("independent_retrieval_check",
                                                  ROOT / "lab" / "independent_retrieval_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _toy_spec(tmp_path, slug):
    spec = yaml.safe_load(TOY.read_text(encoding="utf-8"))
    spec["slug"] = slug
    path = tmp_path / f"{slug}.yaml"
    path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    return path


def _main(capsys, argv):
    from exocortex.lab.cli import main

    code = main(argv)
    return code, json.loads(capsys.readouterr().out)


@pytest.fixture()
def cli_env(monkeypatch, lab_url, tenant):
    monkeypatch.setenv("DATABASE_URL", lab_url)
    return tenant


def test_toy_retrieval_goes_through_the_queue_and_matches_the_independent_calculation(
        conn, cli_env, slug, tmp_path, capsys):
    from exocortex.lab import export
    from exocortex.lab.pages import dossier_page

    spec_path = _toy_spec(tmp_path, slug)
    code, out = _main(capsys, ["run", "--spec", str(spec_path), "--sample", "test-12", "--queue-only"])
    assert code == 0 and out["queued"] is True and out["jobs"] == 60  # 12 questions x 5 configurations
    run_id = out["run_id"]
    assert conn.execute("SELECT status FROM exp_runs r JOIN experiments e ON e.id = r.experiment_id "
                        "WHERE e.slug = %s", (slug,)).fetchone()["status"] == "queued"

    code, out = _main(capsys, ["work"])
    assert code == 0 and out["failed"] == 0
    mine = [r for r in out["finished_runs"] if r["experiment"] == slug]
    assert len(mine) == 1 and mine[0]["kind"] == "retrieval" and mine[0]["status"] == "done"
    assert len(mine[0]["result_ids"]) == 36  # 5 configurations x 4 metrics + 4 differences to the baseline x 4

    code, summary = _main(capsys, ["retrieval", "summary", "--experiment", slug])
    assert code == 0 and summary["run"] == run_id and summary["jobs"] == {"done": 60}
    assert set(summary["configs"]) == {"embeddings", "embeddings-16", "graph-all", "graph-cites", "graph-related"}
    assert set(summary["configs"]["embeddings"]) == {"ndcg@10", "recall@5", "recall@10", "mrr"}
    assert len(summary["differences"]) == 16 and {d["a"] for d in summary["differences"]} == {"embeddings"}
    # the expansion along the edges that help (cites) beats embeddings alone; the misleading edges do not
    by = summary["configs"]
    assert by["graph-cites"]["recall@10"]["value"] > by["embeddings"]["recall@10"]["value"]
    assert by["graph-related"]["recall@10"]["value"] < by["embeddings"]["recall@10"]["value"]
    assert by["embeddings-16"]["ndcg@10"]["value"] < by["embeddings"]["ndcg@10"]["value"]

    # the numbers of the summary are exactly those of a calculation with the standard library alone
    check = _independent()
    export_dir = tmp_path / "out"
    exp = conn.execute("SELECT id, slug, kind, params FROM experiments WHERE slug = %s", (slug,)).fetchone()
    changed = export.export_experiment(conn, dict(exp), export_dir)
    assert f"data/{slug}/results.csv" in changed and export.export_experiment(conn, dict(exp), export_dir) == []
    found, problems = check.recompute(export_dir / "data" / slug, ROOT / "lab" / "corpora" / "toy-retrieval")
    assert problems == [] and len(found) == 36
    for config, metrics in by.items():
        for metric, entry in metrics.items():
            assert (entry["value"], entry["ci_low"], entry["ci_high"], entry["n"]) == found[entry["result_id"]], \
                (config, metric)
    for d in summary["differences"]:
        assert (d["value"], d["ci_low"], d["ci_high"], d["n"]) == found[d["result_id"]]

    data = export_dir / "data" / slug
    package = json.loads((data / "datapackage.json").read_text())
    assert package["exocortex"]["kind"] == "retrieval" and package["exocortex"]["params"]["baseline"] == "embeddings"
    for script, args in (("independent_retrieval_check.py", [str(data), str(ROOT / "lab/corpora/toy-retrieval")]),
                         ("recompute.py", [slug, "--data", str(export_dir / "data")])):
        proc = subprocess.run([sys.executable, str(ROOT / "lab" / script), *args], capture_output=True, text=True,
                              cwd=tmp_path, check=False)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "36 published number(s); all reproduced exactly" in proc.stdout

    page = dossier_page(conn, slug, "en", True)
    for result_id in mine[0]["result_ids"]:
        assert f"`{result_id}`" in page
    assert "bootstrap-by-question" in page and "toy-hash-16" in page
    assert dossier_page(conn, slug, "pl", True).count(f"`{slug}/{run_id}/") == 36


def test_a_run_without_the_queue_stores_its_metrics_and_a_subset_of_configurations_works(
        conn, cli_env, slug, tmp_path, capsys):
    spec_path = _toy_spec(tmp_path, slug)
    code, out = _main(capsys, ["run", "--spec", str(spec_path), "--sample", "tuning-6",
                               "--configs", "embeddings,graph-cites"])
    assert code == 0 and out["done"] == 12 and out["failed"] == 0 and len(out["result_ids"]) == 4 * 2 + 4
    assert out["jobs_by_status"] == {"done": 12}
    code, summary = _main(capsys, ["retrieval", "summary", "--experiment", slug, "--run", out["run_id"]])
    assert code == 0 and set(summary["configs"]) == {"embeddings", "graph-cites"}
    code, refused = _main(capsys, ["retrieval", "summary", "--experiment", slug, "--run", "run-1999-01-01-1"])
    assert code == 2 and "no run run-1999-01-01-1" in refused["refused"]
    code, refused = _main(capsys, ["run", "--spec", str(spec_path), "--sample", "nope"])
    assert code == 2 and "no sample" in refused["refused"]


def test_the_unit_instance_name_runs_the_toy_experiment(conn, cli_env, tmp_path, monkeypatch, capsys):
    # the instance form the systemd unit uses, for a spec the image carries (lab/experiments/toy-retrieval.yaml)
    code, out = _main(capsys, ["run", "--instance", "toy-retrieval_tuning-6_embeddings.graph-cites"])
    assert code == 0 and out["experiment"] == "toy-retrieval" and out["done"] == 12 and len(out["result_ids"]) == 12


def _patched_repo(monkeypatch, tmp_path, **kw):
    """A corpus folder of this test's own: the kind finds corpora and models.yaml through repo_path."""
    root = make_root(tmp_path, **kw)
    (root / "lab" / "models.yaml").write_text((ROOT / "lab" / "models.yaml").read_text(encoding="utf-8"),
                                              encoding="utf-8")
    monkeypatch.setattr(R, "repo_path", lambda rel: root / rel)
    return root


def _offline_spec(slug):
    spec = good_spec()
    spec["slug"] = slug
    spec["configs"] = [c for c in spec["configs"] if c["model"].startswith("toy-hash")]
    return spec


def test_malformed_questions_are_refused_and_nothing_is_stored(conn, cli_env, slug, tmp_path, monkeypatch, capsys):
    _patched_repo(monkeypatch, tmp_path, questions_a="question_id,question,gold\nq1,Which fruit?,d1:7\nq1,Again?,zz\n")
    path = tmp_path / "spec.yaml"
    path.write_text(yaml.safe_dump(_offline_spec(slug)), encoding="utf-8")
    code, out = _main(capsys, ["run", "--spec", str(path), "--sample", "tuning-2"])
    assert code == 2 and out["refused"] == str(path)
    assert any("outside 0 to 3" in p for p in out["problems"]) and any("not in the corpus" in p for p in out["problems"])
    assert conn.execute("SELECT count(*) AS n FROM experiments WHERE slug = %s", (slug,)).fetchone()["n"] == 0


def test_a_question_set_changed_after_the_sample_was_stored_is_refused(conn, slug, tmp_path, monkeypatch):
    root = _patched_repo(monkeypatch, tmp_path)
    spec = _offline_spec(slug)
    specs.setup(conn, spec)
    specs.setup(conn, spec)  # the same members: idempotent
    (root / "lab/corpora/c1/questions-a.csv").write_text(
        "question_id,question,gold\nq1,Which fruit?,d1;d2\nq2,Which boat?,d3\n", encoding="utf-8")  # d2 lost its grade 2
    with pytest.raises(ex.SampleMismatch):
        specs.setup(conn, spec)


def test_a_question_that_no_longer_matches_its_checksum_fails_its_jobs_and_is_counted(
        conn, slug, tmp_path, monkeypatch, tenant):
    root = _patched_repo(monkeypatch, tmp_path)
    spec = _offline_spec(slug)
    ids = specs.setup(conn, spec)
    conn.execute("UPDATE exp_sample_items SET payload = jsonb_set(payload, '{question}', '\"tampered\"') "
                 "WHERE sample_id = %s AND item_id = 'q2'", (ids["samples"]["tuning-2"],))
    run = ex.create_run(conn, ids["experiment"], "run-2026-09-30-1", ids["samples"]["tuning-2"])
    assert ex.enqueue(conn, run, list(ids["configs"].values())) == 6  # 2 questions x 3 configurations
    summary = ex.work(conn, {R.KIND: R.make_runner(conn, tenant, root=root)}, owner="test", run_uuid=run)
    assert (summary.done, summary.failed) == (3, 6)  # q2 fails twice per configuration: 2 attempts
    assert ex.finish_run(conn, run) == {"done": 3, "error": 3}
    assert conn.execute("SELECT status FROM exp_runs WHERE id = %s", (run,)).fetchone()["status"] == "failed"
    ids_stored = R.compute_metrics(conn, run)
    mrr = conn.execute("SELECT n, details FROM exp_metrics WHERE result_id = %s",
                       (f"{slug}/run-2026-09-30-1/embeddings/mrr",)).fetchone()
    assert mrr["n"] == 1 and mrr["details"] == {"failed": 1, "undefined": 0}
    assert R.compute_metrics(conn, run) == ids_stored  # idempotent


# -- the graph index ---------------------------------------------------------------------

class FakeGateway:
    """Stands in for the lab gateway client: questions and the documents of another model, by text."""

    url = "unix:/run/lab-llm/gateway.sock"

    def __init__(self, vectors):
        self.vectors, self.calls = vectors, []

    def embed(self, model, texts):
        self.calls.append((model, list(texts)))
        return [self.vectors[t] for t in texts]


def _basis(i):
    return [1.0 if k == i else 0.0 for k in range(1024)]


@needs_engine
def test_graph_index_uses_stored_embeddings_edges_between_papers_and_the_gateway_for_other_models(conn, tenant):
    from exocortex.lab.db import insert_edge, upsert_thought

    corpus = "g-" + uuid.uuid4().hex[:8]
    papers = {"p1": "alpha", "p2": "beta", "p3": "gamma", "p4": "delta"}

    def node(paper, kind, body, embedding=None):
        meta = {"corpus": corpus, "arxiv_id": paper, "text": kind}
        return upsert_thought(conn, tenant, source_id=None, thought_type=f"corpus_{kind}", body=body, metadata=meta,
                              key=f"{corpus}:{paper}:{kind}", embedding=embedding)[0]

    abstract = {p: node(p, "abstract", word, _basis(i)) for i, (p, word) in enumerate(papers.items())}
    summary = {p: node(p, "summary", word + " summary") for p, word in papers.items()}
    insert_edge(conn, tenant, abstract["p1"], "thought", abstract["p2"], "thought", "cites")
    insert_edge(conn, tenant, abstract["p2"], "thought", abstract["p3"], "thought", "related_to")
    insert_edge(conn, tenant, abstract["p3"], "thought", summary["p4"], "thought", "cites")  # to the other text
    for p in papers:  # abstract and summary of one paper are one document: no edge between documents
        insert_edge(conn, tenant, summary[p], "thought", abstract[p], "thought", "derived_from")

    loaded = R.load_graph_corpus(conn, tenant, corpus)
    assert loaded.texts == papers and loaded.stored_model == "bge-m3" and set(loaded.stored) == set(papers)
    assert loaded.edges == [("p1", "p2", "cites"), ("p2", "p3", "related_to"), ("p3", "p4", "cites")]
    assert loaded.stored["p2"] == _basis(1)
    assert R.load_graph_corpus(conn, tenant, corpus, "summary").texts["p4"] == "delta summary"
    with pytest.raises(RuntimeError, match="no abstract nodes"):
        R.load_graph_corpus(conn, tenant, "missing-" + corpus)

    gateway = FakeGateway({"qp1": _basis(0), "qp3": _basis(2), **{w: _basis(3 - i) for i, w in enumerate(papers.values())}})
    runner = R.make_runner(conn, tenant, llm=gateway)
    params = {"corpus": corpus}  # index: graph is the default

    def run(question_text, gold, model, cfg_params):
        q = R.Question("q", question_text, gold)
        job, item = {"config": {"name": "c", "model": model, "provider": "local", "params": cfg_params},
                     "experiment": {"slug": "x", "kind": "retrieval", "params": params}}, {
            "item_id": "q", "content_sha256": R.content_sha256(q), "stratum": None,
            "payload": {"question": q.text, "gold": q.gold}}
        return runner(job, item)["output"]["ranking"]

    # bge-m3: the stored embeddings are used, only the question goes to the gateway
    plain = run("qp1", {"p1": 1}, "bge-m3", {})
    assert next(e["doc"] for e in plain) == "p1" and gateway.calls == [("bge-m3", ["qp1"])]
    expanded = {e["doc"]: e for e in run("qp1", {"p1": 1}, "bge-m3", {"expansion": {"seed_k": 1}})}
    assert expanded["p2"]["via"] == "expansion:cites" and expanded["p2"]["score"] == 0.5
    chosen = {e["doc"]: e for e in run("qp3", {"p3": 1}, "bge-m3",
                                       {"expansion": {"seed_k": 1, "edge_types": ["cites"], "direction": "out"}})}
    assert chosen["p4"]["via"] == "expansion:cites" and chosen["p2"]["via"] == "embedding"  # related_to not followed
    with pytest.raises(RuntimeError, match="no edge of type supports"):
        run("qp1", {"p1": 1}, "bge-m3", {"expansion": {"edge_types": ["supports"]}})
    with pytest.raises(RuntimeError, match="not in corpus"):
        run("qp1", {"p9": 1}, "bge-m3", {})
    assert all(model == "bge-m3" and texts == ["qp1"] or texts == ["qp3"] for model, texts in gateway.calls)

    # another model: the documents are embedded through the gateway, once
    other = run("qp1", {"p1": 1}, "other-embedder", {})
    embedded = [c for c in gateway.calls if c[0] == "other-embedder"]
    assert embedded[0][1] == list(papers.values()) and next(e["doc"] for e in other) == "p4"  # its vectors are mirrored
    run("qp3", {"p3": 1}, "other-embedder", {})
    assert len([c for c in gateway.calls if c[0] == "other-embedder" and c[1] == list(papers.values())]) == 1
