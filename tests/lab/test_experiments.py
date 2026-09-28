# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Experiment tables, queue and control sample lock (roadmap task F2.6)."""
from __future__ import annotations

import psycopg
import pytest

from exocortex.lab import experiments as ex


def _items(n: int, strata=("a", "b")) -> list[dict]:
    return [{"item_id": f"doc-{i:03d}", "content_sha256": f"{i:064x}", "stratum": strata[i % len(strata)]}
            for i in range(n)]


# -- pure ----------------------------------------------------------------------

def test_stratified_draw_is_deterministic_disjoint_and_proportional():
    frame = _items(40, strata=("a", "a", "a", "b"))  # 30 a, 10 b
    one = ex.draw_stratified(frame, {"tuning": 8, "control": 4}, seed=7)
    two = ex.draw_stratified(list(reversed(frame)), {"tuning": 8, "control": 4}, seed=7)
    assert one == two
    ids = [i["item_id"] for s in one.values() for i in s]
    assert len(ids) == len(set(ids)) == 12
    assert sum(i["stratum"] == "b" for i in one["tuning"]) == 2  # 8 * 10/40
    assert ex.draw_stratified(frame, {"tuning": 8}, seed=8) != ex.draw_stratified(frame, {"tuning": 8}, seed=7)


def test_stratified_draw_respects_exclusions_and_size():
    frame = _items(10)
    drawn = ex.draw_stratified(frame, {"tuning": 5}, seed=1, exclude={"doc-000", "doc-001"})
    assert not {"doc-000", "doc-001"} & {i["item_id"] for i in drawn["tuning"]}
    with pytest.raises(ValueError):
        ex.draw_stratified(frame, {"tuning": 9}, seed=1, exclude={"doc-000", "doc-001"})


def test_members_checksum_ignores_order():
    a = [("x", "1"), ("y", "2")]
    assert ex.members_sha256(a) == ex.members_sha256(reversed(a))
    assert ex.members_sha256(a) != ex.members_sha256([("x", "1"), ("y", "3")])


# -- database ------------------------------------------------------------------

def _setup(conn, slug, n_items=6, role="tuning"):
    exp = ex.ensure_experiment(conn, slug, "count", "test")
    cfg_a = ex.ensure_config(conn, exp, "a", model="model-a", provider="local")
    cfg_b = ex.ensure_config(conn, exp, "b", model="model-b", provider="local")
    sample = ex.create_sample(conn, exp, f"{role}-{n_items}", role, 1, "test", _items(n_items))
    return exp, cfg_a, cfg_b, sample


def _count_runner(job, item):
    return {"ok": True, "output": {"len": len(item["item_id"])}, "model": job["config"]["model"],
            "provider": "local", "input_tokens": 3, "output_tokens": 1, "latency_ms": 5}


def test_toy_path_runs_through_the_queue_and_stores_results(conn, slug):
    exp, a, b, sample = _setup(conn, slug)
    run = ex.create_run(conn, exp, "run-2026-09-29-1", sample)
    assert ex.enqueue(conn, run, [a, b]) == 12
    assert ex.enqueue(conn, run, [a, b]) == 0  # enqueueing again adds nothing
    summary = ex.work(conn, {"count": _count_runner}, owner="test", run_uuid=run)
    assert summary.done == 12 and summary.failed == 0
    counts = ex.finish_run(conn, run)
    assert counts == {"done": 12}
    rows = conn.execute("SELECT count(*) AS n, sum(input_tokens) AS t FROM exp_results WHERE run_id = %s",
                        (run,)).fetchone()
    assert rows["n"] == 12 and rows["t"] == 36
    assert conn.execute("SELECT status FROM exp_runs WHERE id = %s", (run,)).fetchone()["status"] == "done"


def test_jobs_for_two_models_run_in_two_blocks(conn, slug):
    exp, a, b, sample = _setup(conn, slug, n_items=8)
    run = ex.create_run(conn, exp, "run-2026-09-29-1", sample)
    ex.enqueue(conn, run, [a, b])  # created interleaved: item 0 for a, item 0 for b, item 1 for a, ...
    created = [r["model"] for r in conn.execute(
        "SELECT model FROM exp_jobs WHERE run_id = %s ORDER BY created_at, id", (run,)).fetchall()]
    assert sum(1 for x, y in zip(created, created[1:]) if x != y) > 1  # the queue itself alternates
    summary = ex.work(conn, {"count": _count_runner}, owner="test", run_uuid=run)
    assert summary.done == 16
    assert summary.switches() == 1, summary.models
    assert summary.models[:8] == [summary.models[0]] * 8


def test_second_read_of_a_control_sample_raises(conn, slug):
    exp, a, b, sample = _setup(conn, slug, role="control")
    ex.create_run(conn, exp, "run-2026-09-29-1", sample, hypothesis_version=1)
    touched = conn.execute("SELECT touched_at FROM exp_samples WHERE id = %s", (sample,)).fetchone()["touched_at"]
    assert touched is not None
    with pytest.raises(ex.ControlSampleAlreadyOpened):
        ex.create_run(conn, exp, "run-2026-09-29-2", sample, hypothesis_version=1)
    # a new version of the hypothesis is a new question and may read it once
    ex.create_run(conn, exp, "run-2026-09-29-3", sample, hypothesis_version=2)
    with pytest.raises(ex.ControlSampleAlreadyOpened):
        ex.create_run(conn, exp, "run-2026-09-29-4", sample, hypothesis_version=2)
    with pytest.raises(psycopg.errors.CheckViolation):
        ex.create_run(conn, exp, "run-2026-09-29-5", sample)  # no version: refused


def test_tuning_samples_can_be_read_many_times(conn, slug):
    exp, a, b, sample = _setup(conn, slug)
    ex.create_run(conn, exp, "run-2026-09-29-1", sample, hypothesis_version=1)
    ex.create_run(conn, exp, "run-2026-09-29-2", sample, hypothesis_version=1)


def test_a_crashing_runner_is_retried_then_marked_error(conn, slug):
    exp, a, b, sample = _setup(conn, slug, n_items=1)
    run = ex.create_run(conn, exp, "run-2026-09-29-1", sample)
    ex.enqueue(conn, run, [a])

    def boom(job, item):
        raise RuntimeError("runner crashed")

    summary = ex.work(conn, {"count": boom}, owner="test", run_uuid=run)
    assert summary.failed == 2 and summary.done == 0
    job = conn.execute("SELECT status, attempts, last_error FROM exp_jobs WHERE run_id = %s", (run,)).fetchone()
    assert job["status"] == "error" and job["attempts"] == 2 and "crashed" in job["last_error"]
    assert ex.finish_run(conn, run) == {"error": 1}


def test_an_expired_lease_goes_back_to_the_queue(conn, slug):
    exp, a, b, sample = _setup(conn, slug, n_items=1)
    run = ex.create_run(conn, exp, "run-2026-09-29-1", sample)
    ex.enqueue(conn, run, [a])
    first = ex.claim(conn, "worker-1", "model-a", run, lease_seconds=0)  # the worker dies with the lease
    assert first is not None
    second = ex.claim(conn, "worker-2", "model-a", run)
    assert second["id"] == first["id"] and second["attempts"] == 2 and second["owner"] == "worker-2"


def test_invalid_output_is_a_result_not_a_retry(conn, slug):
    exp, a, b, sample = _setup(conn, slug, n_items=2)
    run = ex.create_run(conn, exp, "run-2026-09-29-1", sample)
    ex.enqueue(conn, run, [a])
    summary = ex.work(conn, {"count": lambda job, item: {"ok": False, "error_reason": "no JSON object"}},
                      owner="test", run_uuid=run)
    assert summary.done == 2
    assert conn.execute("SELECT count(*) AS n FROM exp_results WHERE run_id = %s AND NOT ok",
                        (run,)).fetchone()["n"] == 2


def test_configurations_and_samples_are_immutable(conn, slug):
    exp, a, b, sample = _setup(conn, slug)
    with pytest.raises(ValueError):
        ex.ensure_config(conn, exp, "a", model="another-model", provider="local")
    with pytest.raises(ex.SampleMismatch):
        ex.create_sample(conn, exp, "tuning-6", "tuning", 1, "test", _items(5))
    assert ex.create_sample(conn, exp, "tuning-6", "tuning", 1, "test", _items(6)) == sample


def test_only_public_data_is_allowed(conn, slug):
    exp = ex.ensure_experiment(conn, slug, "count", "test")
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("""INSERT INTO exp_samples (experiment_id, name, role, seed, method, data_class, members_sha256, size)
                        VALUES (%s, 's', 'tuning', 1, 'x', 'client', 'x', 0)""", (exp,))


def test_metrics_are_recorded_under_readable_ids(conn, slug):
    exp, a, b, sample = _setup(conn, slug)
    run = ex.create_run(conn, exp, "run-2026-09-29-1", sample)
    ex.record_metric(conn, f"{slug}/run-2026-09-29-1/a/rate", run, a, "rate", 0.5, 0.2, 0.8, 10, "wilson")
    ex.record_metric(conn, f"{slug}/run-2026-09-29-1/a/rate", run, a, "rate", 0.6, 0.3, 0.8, 10, "wilson")
    row = conn.execute("SELECT value FROM exp_metrics WHERE result_id = %s",
                       (f"{slug}/run-2026-09-29-1/a/rate",)).fetchone()
    assert row["value"] == 0.6
