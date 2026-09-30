# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Experiment kind ``format_conformity`` through the queue on a real database (roadmap task F5.9): the toy
experiment from run to export, checked against a calculation that shares no code with the lab; refusals; failed
jobs and empty replies in the numbers."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys

import pytest
import yaml

from exocortex.lab import experiments as ex
from exocortex.lab import format_conformity as F
from exocortex.lab import format_conformity_metrics as fm
from exocortex.lab import specs
from tests.lab.conftest import ROOT
from tests.unit.test_lab_format_conformity import good_spec, make_root

TOY = ROOT / "lab" / "experiments" / "toy-format.yaml"
CORPUS = ROOT / "lab" / "corpora" / "toy-format"


def _independent():
    spec = importlib.util.spec_from_file_location("independent_format_check", ROOT / "lab" / "independent_format_check.py")
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


def test_toy_format_goes_through_the_queue_and_matches_the_independent_calculation(
        conn, cli_env, slug, tmp_path, capsys):
    from exocortex.lab import export
    from exocortex.lab.pages import dossier_page

    spec_path = _toy_spec(tmp_path, slug)
    code, out = _main(capsys, ["run", "--spec", str(spec_path), "--sample", "test-36", "--queue-only"])
    assert code == 0 and out["queued"] is True and out["jobs"] == 144  # 36 prompts x 4 configurations
    run_id = out["run_id"]
    assert conn.execute("SELECT status FROM exp_runs r JOIN experiments e ON e.id = r.experiment_id "
                        "WHERE e.slug = %s", (slug,)).fetchone()["status"] == "queued"

    code, out = _main(capsys, ["work"])
    assert code == 0 and out["failed"] == 0
    mine = [r for r in out["finished_runs"] if r["experiment"] == slug]
    assert len(mine) == 1 and mine[0]["kind"] == "format_conformity" and mine[0]["status"] == "done"
    assert len(mine[0]["result_ids"]) == 8  # 4 configurations + 3 differences to the baseline + 1 guard reference

    code, summary = _main(capsys, ["format_conformity", "summary", "--experiment", slug])
    assert code == 0 and summary["run"] == run_id and summary["jobs"] == {"done": 144}
    assert set(summary["configs"]) == {"free", "schema-forced", "grammar-forced", "free-sparse"}
    assert all(set(m) == {"conforming_share"} for m in summary["configs"].values())
    assert len(summary["differences"]) == 3 and {d["a"] for d in summary["differences"]} == {"free"}
    assert summary["guard"] == {"experiment": "intent-vs-fact", "metric": "usable_per_document", "computed_here": False,
                                "result_id": f"{slug}/{run_id}/guard/intent-vs-fact/usable_per_document"}
    by = summary["configs"]
    # forcing the format removes most of what goes wrong in free answers; the grammar removes all of it
    assert by["grammar-forced"]["conforming_share"]["value"] == 1.0 and by["grammar-forced"]["conforming_share"]["ci_high"] == 1.0
    assert by["free"]["conforming_share"]["value"] < by["schema-forced"]["conforming_share"]["value"] < 1.0
    free = by["free"]["conforming_share"]
    assert free["n"] == 36 and free["method"] == "wilson" and free["details"]["failed_jobs"] == 0
    assert free["details"]["reasons"].keys() >= {"not_json", "code_fence", "text_around_json", "truncated"}
    sparse = by["free-sparse"]["conforming_share"]
    assert sparse["n"] + sparse["details"]["no_answer"] == 36 and sparse["details"]["no_answer"] > 0
    forced = next(d for d in summary["differences"] if d["b"] == "grammar-forced")
    assert forced["value"] > 0.5 and forced["ci_low"] > 0 and forced["method"] == "newcombe-paired"

    # the numbers of the summary are exactly those of a calculation with the standard library alone
    check = _independent()
    export_dir = tmp_path / "out"
    exp = conn.execute("SELECT id, slug, kind, params FROM experiments WHERE slug = %s", (slug,)).fetchone()
    changed = export.export_experiment(conn, dict(exp), export_dir)
    assert f"data/{slug}/results.csv" in changed and export.export_experiment(conn, dict(exp), export_dir) == []
    found, problems = check.recompute(export_dir / "data" / slug, CORPUS)
    assert problems == [] and len(found) == 8
    for config, metrics in by.items():
        for metric, entry in metrics.items():
            assert (entry["value"], entry["ci_low"], entry["ci_high"], entry["n"]) == found[entry["result_id"]][:4], \
                (config, metric)
    for d in summary["differences"]:
        assert (d["value"], d["ci_low"], d["ci_high"], d["n"]) == found[d["result_id"]][:4]

    data = export_dir / "data" / slug
    package = json.loads((data / "datapackage.json").read_text())
    assert package["exocortex"]["kind"] == "format_conformity" and package["exocortex"]["params"]["baseline"] == "free"
    assert package["exocortex"]["params"]["guard"] == {"experiment": "intent-vs-fact", "metric": "usable_per_document"}
    for script, args in (("independent_format_check.py", [str(data), str(CORPUS)]),
                         ("recompute.py", [slug, "--data", str(export_dir / "data")])):
        proc = subprocess.run([sys.executable, str(ROOT / "lab" / script), *args], capture_output=True, text=True,
                              cwd=tmp_path, check=False)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "8 published number(s); all reproduced exactly" in proc.stdout

    page = dossier_page(conn, slug, "en", True)
    for result_id in mine[0]["result_ids"]:
        assert f"`{result_id}`" in page
    assert "newcombe-paired" in page and "guard:intent-vs-fact/usable_per_document" in page and "toy-answerer" in page
    assert dossier_page(conn, slug, "pl", True).count(f"`{slug}/{run_id}/") == 8


def test_a_corrupted_result_is_not_reproduced_by_the_independent_calculation(conn, cli_env, slug, tmp_path, capsys):
    from exocortex.lab import export

    spec_path = _toy_spec(tmp_path, slug)
    assert _main(capsys, ["run", "--spec", str(spec_path), "--sample", "tuning-6"])[0] == 0
    exp = conn.execute("SELECT id, slug, kind, params FROM experiments WHERE slug = %s", (slug,)).fetchone()
    export.export_experiment(conn, dict(exp), tmp_path / "out")
    data = tmp_path / "out" / "data" / slug
    check = _independent()
    assert check.main([str(data), str(CORPUS)]) == 0
    text = (data / "results.csv").read_text(encoding="utf-8")
    (data / "results.csv").write_text(text.replace('""verdict"": ""conforming""', '""verdict"": ""non_conforming""', 1),
                                      encoding="utf-8")
    assert check.main([str(data), str(CORPUS)]) == 1  # the stored verdict is not what its answer gives


def test_a_run_without_the_queue_stores_its_metrics_and_a_subset_of_configurations_works(
        conn, cli_env, slug, tmp_path, capsys):
    spec_path = _toy_spec(tmp_path, slug)
    code, out = _main(capsys, ["run", "--spec", str(spec_path), "--sample", "tuning-6",
                               "--configs", "free,grammar-forced"])
    assert code == 0 and out["done"] == 12 and out["failed"] == 0 and len(out["result_ids"]) == 2 + 1 + 1
    assert out["jobs_by_status"] == {"done": 12}
    code, summary = _main(capsys, ["format_conformity", "summary", "--experiment", slug, "--run", out["run_id"]])
    assert code == 0 and set(summary["configs"]) == {"free", "grammar-forced"}
    code, refused = _main(capsys, ["format_conformity", "summary", "--experiment", slug, "--run", "run-1999-01-01-1"])
    assert code == 2 and "no run run-1999-01-01-1" in refused["refused"]
    code, refused = _main(capsys, ["format_conformity", "summary", "--experiment", "toy-retrieval"])
    assert code == 2 and "no experiment of kind format_conformity" in refused["refused"]
    code, refused = _main(capsys, ["run", "--spec", str(spec_path), "--sample", "nope"])
    assert code == 2 and "no sample" in refused["refused"]


def test_the_unit_instance_name_runs_the_toy_experiment(conn, cli_env, capsys):
    # the instance form the systemd unit uses, for a spec the image carries (lab/experiments/toy-format.yaml)
    code, out = _main(capsys, ["run", "--instance", "toy-format_tuning-6_free.schema-forced"])
    assert code == 0 and out["experiment"] == "toy-format" and out["done"] == 12 and len(out["result_ids"]) == 2 + 1 + 1


def test_newcombe_without_correlation_is_the_hybrid_score_interval_of_statsmodels():
    # cross product 2 lies between 0 and n/2, so the correlation correction is 0 and the interval is the
    # Newcombe-Wilson interval for independent proportions, which statsmodels computes
    statsmodels = pytest.importorskip("statsmodels.stats.proportion")
    d, low, high = fm.newcombe_paired(both=2, only_a=4, only_b=1, neither=3)
    reference = statsmodels.confint_proportions_2indep(3, 10, 6, 10, method="newcomb", compare="diff")
    assert d == pytest.approx(-0.3)
    assert low == pytest.approx(reference[0], abs=1e-12) and high == pytest.approx(reference[1], abs=1e-12)


def _patched_repo(monkeypatch, tmp_path, **kw):
    """A corpus folder of this test's own: the kind finds corpora, specs and models.yaml through repo_path."""
    root = make_root(tmp_path, **kw)
    (root / "lab" / "models.yaml").write_text((ROOT / "lab" / "models.yaml").read_text(encoding="utf-8"),
                                              encoding="utf-8")
    monkeypatch.setattr(F, "repo_path", lambda rel: root / rel)
    return root


def _offline_spec(slug):
    spec = good_spec()
    spec["slug"] = slug
    spec["configs"] = [c for c in spec["configs"] if c["model"].startswith("toy-")]
    return spec


def test_malformed_prompt_files_are_refused_and_nothing_is_stored(conn, cli_env, slug, tmp_path, monkeypatch, capsys):
    _patched_repo(monkeypatch, tmp_path, prompts_a="item_id,prompt,schema\na1,Which ticket?,zz\na1,,ticket\n")
    path = tmp_path / "spec.yaml"
    path.write_text(yaml.safe_dump(_offline_spec(slug)), encoding="utf-8")
    code, out = _main(capsys, ["run", "--spec", str(path), "--sample", "tuning-2"])
    assert code == 2 and out["refused"] == str(path)
    assert any("no file schemas/zz.json" in p for p in out["problems"]) and any("line 3" in p for p in out["problems"])
    assert conn.execute("SELECT count(*) AS n FROM experiments WHERE slug = %s", (slug,)).fetchone()["n"] == 0


def test_a_guard_that_is_not_a_claims_experiment_is_refused(conn, cli_env, slug, tmp_path, monkeypatch, capsys):
    _patched_repo(monkeypatch, tmp_path)
    spec = _offline_spec(slug)
    spec["params"]["guard"] = {"experiment": "a-toy", "metric": "usable_per_doc"}
    path = tmp_path / "spec.yaml"
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    code, out = _main(capsys, ["run", "--spec", str(path), "--sample", "tuning-2"])
    assert code == 2 and any("belongs to an experiment of the kind 'claims'" in p for p in out["problems"])
    assert conn.execute("SELECT count(*) AS n FROM experiments WHERE slug = %s", (slug,)).fetchone()["n"] == 0


def test_a_prompt_file_or_schema_changed_after_the_sample_was_stored_is_refused(conn, slug, tmp_path, monkeypatch):
    root = _patched_repo(monkeypatch, tmp_path)
    spec = _offline_spec(slug)
    specs.setup(conn, spec)
    specs.setup(conn, spec)  # the same members: idempotent
    (root / "lab/corpora/c1/prompts-a.csv").write_text(
        "item_id,prompt,schema,grammar\na1,Classify: a different prompt.,ticket,g1\na2,Tags for this.,tags,\n", encoding="utf-8")
    with pytest.raises(ex.SampleMismatch):
        specs.setup(conn, spec)
    (root / "lab/corpora/c1/prompts-a.csv").write_text(
        "item_id,prompt,schema,grammar\na1,Classify: double charge.,ticket,g1\na2,Tags for this.,tags,\n", encoding="utf-8")
    specs.setup(conn, spec)
    schema_path = root / "lab/corpora/c1/schemas/ticket.json"
    schema_path.write_text(json.dumps({**json.loads(schema_path.read_text()), "required": ["category"]}), encoding="utf-8")
    with pytest.raises(ex.SampleMismatch):  # the schema is part of what the item stands for
        specs.setup(conn, spec)


def test_failed_jobs_and_empty_replies_are_counted_and_the_answers_still_give_their_share(
        conn, slug, tmp_path, monkeypatch, tenant):
    root = _patched_repo(monkeypatch, tmp_path)
    spec = _offline_spec(slug)
    spec["configs"].append({"name": "sparse", "model": "toy-sparse", "provider": "none", "params": {"format": "free"}})
    ids = specs.setup(conn, spec)
    conn.execute("UPDATE exp_sample_items SET payload = jsonb_set(payload, '{prompt}', '\"tampered\"') "
                 "WHERE sample_id = %s AND item_id = 'a2'", (ids["samples"]["tuning-2"],))
    run = ex.create_run(conn, ids["experiment"], "run-2026-09-30-1", ids["samples"]["tuning-2"])
    assert ex.enqueue(conn, run, list(ids["configs"].values())) == 6  # 2 items x 3 configurations
    summary = ex.work(conn, {F.KIND: F.make_runner(conn, tenant, root=root)}, owner="test", run_uuid=run)
    assert (summary.done, summary.failed) == (3, 6)  # a2 fails twice per configuration: 2 attempts
    assert ex.finish_run(conn, run) == {"done": 3, "error": 3}
    assert conn.execute("SELECT status FROM exp_runs WHERE id = %s", (run,)).fetchone()["status"] == "failed"
    stored = F.compute_metrics(conn, run)
    assert F.compute_metrics(conn, run) == stored  # idempotent
    row = conn.execute("SELECT n, details FROM exp_metrics WHERE result_id = %s",
                       (f"{slug}/run-2026-09-30-1/free/conforming_share",)).fetchone()
    assert row["n"] == 1 and row["details"]["failed_jobs"] == 1 and row["details"]["no_answer"] == 0
    diff = conn.execute("SELECT n, value FROM exp_metrics WHERE result_id = %s",
                        (f"{slug}/run-2026-09-30-1/diff/forced_minus_free/conforming_share",)).fetchone()
    assert diff["n"] == 1  # only the item both answered
    guard = conn.execute("SELECT value, n, method FROM exp_metrics WHERE result_id = %s",
                         (f"{slug}/run-2026-09-30-1/guard/a-claims/usable_per_doc",)).fetchone()
    assert (guard["value"], guard["n"], guard["method"]) == (None, 0, "reference")


def test_an_empty_reply_is_stored_as_a_result_that_is_not_ok_and_counted_as_no_answer(
        conn, slug, tmp_path, monkeypatch, tenant):
    root = _patched_repo(monkeypatch, tmp_path)
    prompts = "item_id,prompt,schema\n" + "".join(f"p{i:02d},Classify ticket number {i}.,ticket\n" for i in range(40))
    (root / "lab/corpora/c1/prompts-a.csv").write_text(prompts, encoding="utf-8")
    spec = _offline_spec(slug)
    spec["configs"] = [{"name": "sparse", "model": "toy-sparse", "provider": "none", "params": {"format": "free"}}]
    spec["params"].pop("baseline")
    ids = specs.setup(conn, spec)
    run = ex.create_run(conn, ids["experiment"], "run-2026-09-30-1", ids["samples"]["tuning-2"])
    ex.enqueue(conn, run, list(ids["configs"].values()))
    summary = ex.work(conn, {F.KIND: F.make_runner(conn, tenant, root=root)}, owner="test", run_uuid=run)
    assert summary.failed == 0 and summary.done == 40
    silent = conn.execute("SELECT count(*) AS n FROM exp_results WHERE run_id = %s AND NOT ok "
                          "AND error_reason = 'empty reply'", (run,)).fetchone()["n"]
    assert silent > 0
    assert ex.finish_run(conn, run) == {"done": 40}  # an empty reply is a finished job, not a failed one
    F.compute_metrics(conn, run)
    row = conn.execute("SELECT n, details FROM exp_metrics WHERE result_id = %s",
                       (f"{slug}/run-2026-09-30-1/sparse/conforming_share",)).fetchone()
    assert row["details"]["no_answer"] == silent and row["n"] == 40 - silent and row["details"]["failed_jobs"] == 0
