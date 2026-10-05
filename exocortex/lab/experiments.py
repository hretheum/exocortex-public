# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Experiments, samples, runs and the job queue of the lab (roadmap task F2.6).

The loop is ordinary code: no model decides what runs next. A run takes one
sample and a set of configurations and becomes one job per (configuration,
item). Workers lease jobs; a job whose lease expired goes back to the queue
until it runs out of attempts. Attempts cover crashes of the runner, not
invalid model output, which is a measured result and stored as such.

The queue hands out jobs grouped by model: a worker keeps taking jobs for
the model it used last and switches only when none are left, so the local
model server does not swap models between consecutive jobs.

A control sample is read once per hypothesis version. The database enforces
it (schema/43_lab_experiments.sql): the second run on the same control
sample and version fails, and create_run raises ControlSampleAlreadyOpened.
"""

from __future__ import annotations

import hashlib
import itertools
import random
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

import psycopg
from psycopg.types.json import Jsonb

Runner = Callable[[dict, dict], dict]  # (job with config, sample item) -> result fields


class ControlSampleAlreadyOpened(Exception):
    """A run asked for a control sample already read for this hypothesis version."""


class SampleMismatch(Exception):
    """A sample with this name exists with different members."""


def members_sha256(items: Iterable[tuple[str, str]]) -> str:
    """Checksum of a sample: SHA-256 over "item_id content_sha256" lines sorted by item id."""
    lines = sorted(f"{item_id} {content}" for item_id, content in items)
    return hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()


def draw_stratified(frame: list[dict], sizes: dict[str, int], seed: int,
                    exclude: Iterable[str] = ()) -> dict[str, list[dict]]:
    """Disjoint stratified samples from ``frame`` (dicts with item_id and stratum).

    Deterministic for a given frame, sizes and seed: items are sorted by id,
    shuffled within each stratum with ``random.Random(seed)``, and each sample
    in the order of ``sizes`` takes its share of every stratum (largest
    remainder) from the front of what is left. Items in ``exclude`` never
    enter any sample.
    """
    rng = random.Random(seed)
    excluded = set(exclude)
    strata: dict[str, list[dict]] = {}
    for item in sorted(frame, key=lambda x: x["item_id"]):
        if item["item_id"] not in excluded:
            strata.setdefault(item.get("stratum") or "", []).append(item)
    for name in sorted(strata):
        rng.shuffle(strata[name])
    total = sum(len(v) for v in strata.values())
    if sum(sizes.values()) > total:
        raise ValueError(f"samples need {sum(sizes.values())} items, the frame has {total}")
    out: dict[str, list[dict]] = {}
    for sample, n in sizes.items():
        remaining = {k: v for k, v in strata.items() if v}
        left = sum(len(v) for v in remaining.values())
        quotas = {k: n * len(v) / left for k, v in remaining.items()}
        take = {k: int(q) for k, q in quotas.items()}
        short = n - sum(take.values())
        for k in sorted(quotas, key=lambda k: (-(quotas[k] - take[k]), k))[:short]:
            take[k] += 1
        chosen = []
        for k in sorted(remaining):
            chosen.extend(strata[k][:take[k]])
            strata[k] = strata[k][take[k]:]
        out[sample] = chosen
    return out


def ensure_experiment(conn, slug: str, kind: str, title: str, hypothesis_slug: str | None = None,
                      params: dict | None = None) -> str:
    row = conn.execute(
        """INSERT INTO experiments (slug, kind, title, hypothesis_slug, params) VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (slug) DO UPDATE SET title = EXCLUDED.title RETURNING id""",
        (slug, kind, title, hypothesis_slug, Jsonb(params or {})),
    ).fetchone()
    return str(row["id"])


def ensure_config(conn, experiment_id: str, name: str, *, model: str | None = None, provider: str = "none",
                  variant: str = "", params: dict | None = None) -> str:
    """A configuration is data. Changing an existing one is refused: make a new name."""
    row = conn.execute("SELECT id, model, provider, variant, params FROM exp_configs WHERE experiment_id = %s AND name = %s",
                       (experiment_id, name)).fetchone()
    if row:
        if (row["model"], row["provider"], row["variant"], row["params"]) != (model, provider, variant, params or {}):
            raise ValueError(f"configuration {name!r} exists with different settings")
        return str(row["id"])
    row = conn.execute(
        """INSERT INTO exp_configs (experiment_id, name, model, provider, variant, params)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
        (experiment_id, name, model, provider, variant, Jsonb(params or {})),
    ).fetchone()
    return str(row["id"])


def create_sample(conn, experiment_id: str, name: str, role: str, seed: int, method: str,
                  items: list[dict]) -> str:
    """Store a sample and its items in draw order. Same name, same members: returns the existing id."""
    digest = members_sha256((i["item_id"], i["content_sha256"]) for i in items)
    row = conn.execute("SELECT id, members_sha256 FROM exp_samples WHERE experiment_id = %s AND name = %s",
                       (experiment_id, name)).fetchone()
    if row:
        if row["members_sha256"] != digest:
            raise SampleMismatch(f"sample {name!r} exists with other members")
        return str(row["id"])
    sid = str(conn.execute(
        """INSERT INTO exp_samples (experiment_id, name, role, seed, method, data_class, members_sha256, size)
           VALUES (%s, %s, %s, %s, %s, 'public', %s, %s) RETURNING id""",
        (experiment_id, name, role, seed, method, digest, len(items)),
    ).fetchone()["id"])
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO exp_sample_items (sample_id, item_id, content_sha256, stratum, position, payload)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            [(sid, i["item_id"], i["content_sha256"], i.get("stratum"), pos, Jsonb(i.get("payload") or {}))
             for pos, i in enumerate(items)],
        )
    return sid


def create_run(conn, experiment_id: str, run_id: str, sample_id: str, *, hypothesis_version: int | None = None,
               prereg_hash: str | None = None, code_commit: str | None = None, notes: str | None = None) -> str:
    try:
        row = conn.execute(
            """INSERT INTO exp_runs (experiment_id, run_id, sample_id, hypothesis_version, prereg_hash, code_commit, notes)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (experiment_id, run_id, sample_id, hypothesis_version, prereg_hash, code_commit, notes),
        ).fetchone()
    except psycopg.errors.UniqueViolation as exc:
        if "exp_control_openings" in str(exc):
            raise ControlSampleAlreadyOpened(
                f"control sample already read for hypothesis version {hypothesis_version}") from exc
        raise
    return str(row["id"])


def enqueue(conn, run_uuid: str, config_ids: list[str], max_attempts: int = 2) -> int:
    """One job per (configuration, sample item); returns how many were created."""
    before = conn.execute("SELECT count(*) AS n FROM exp_jobs WHERE run_id = %s", (run_uuid,)).fetchone()["n"]
    conn.execute(
        """INSERT INTO exp_jobs (run_id, config_id, item_id, model, max_attempts)
           SELECT r.id, c.id, i.item_id, c.model, %s
           FROM exp_runs r
           JOIN exp_sample_items i ON i.sample_id = r.sample_id
           JOIN exp_configs c ON c.id = ANY(%s::uuid[])
           WHERE r.id = %s
           ORDER BY i.position, c.name
           ON CONFLICT (run_id, config_id, item_id) DO NOTHING""",
        (max_attempts, config_ids, run_uuid),
    )
    after = conn.execute("SELECT count(*) AS n FROM exp_jobs WHERE run_id = %s", (run_uuid,)).fetchone()["n"]
    return after - before


_CLAIMABLE = """(j.status = 'pending'
                 OR (j.status = 'in_progress' AND j.lease_until < NOW() AND j.attempts < j.max_attempts))"""


def expire_leases(conn) -> int:
    """Jobs whose lease ran out with no attempts left become 'error'; returns how many."""
    return conn.execute(
        """UPDATE exp_jobs SET status = 'error', last_error = COALESCE(last_error, 'lease expired'),
                  finished_at = NOW(), lease_until = NULL
           WHERE status = 'in_progress' AND lease_until < NOW() AND attempts >= max_attempts""").rowcount


def next_model(conn, prefer: str | None, run_uuid: str | None = None) -> tuple[bool, str | None]:
    """(found, model) for the next claim: ``prefer`` while it has work, else the model with most."""
    expire_leases(conn)
    rows = conn.execute(
        f"""SELECT j.model, count(*) AS n FROM exp_jobs j
            WHERE {_CLAIMABLE} AND (%(run)s::uuid IS NULL OR j.run_id = %(run)s::uuid)
            GROUP BY j.model ORDER BY count(*) DESC, j.model NULLS FIRST""",
        {"run": run_uuid},
    ).fetchall()
    if not rows:
        return False, None
    models = [r["model"] for r in rows]
    return True, prefer if prefer in models else models[0]


def claim(conn, owner: str, model: str | None, run_uuid: str | None = None, lease_seconds: int = 900) -> dict | None:
    """Lease one claimable job for ``model`` (None matches jobs without a model)."""
    row = conn.execute(
        f"""WITH next AS (
                SELECT j.id FROM exp_jobs j
                WHERE {_CLAIMABLE} AND j.model IS NOT DISTINCT FROM %(model)s
                  AND (%(run)s::uuid IS NULL OR j.run_id = %(run)s::uuid)
                ORDER BY j.created_at, j.id
                LIMIT 1 FOR UPDATE SKIP LOCKED)
            UPDATE exp_jobs j SET status = 'in_progress', owner = %(owner)s, attempts = j.attempts + 1,
                   lease_until = NOW() + make_interval(secs => %(lease)s), claimed_at = NOW()
            FROM next WHERE j.id = next.id
            RETURNING j.*""",
        {"model": model, "run": run_uuid, "owner": owner, "lease": lease_seconds},
    ).fetchone()
    return dict(row) if row else None


RESULT_FIELDS = ("ok", "error_reason", "output", "model", "provider", "base_url", "input_tokens",
                 "output_tokens", "cost_usd", "latency_ms")


def complete(conn, job: dict, result: dict) -> str:
    """Store the result of a job and mark it done; returns the result id."""
    values = {k: result.get(k) for k in RESULT_FIELDS}
    values["ok"] = bool(values["ok"])
    values["output"] = Jsonb(values["output"] or {})
    for k in ("input_tokens", "output_tokens", "latency_ms"):
        values[k] = int(values[k] or 0)
    values["cost_usd"] = values["cost_usd"] or 0
    with conn.transaction():
        row = conn.execute(
            """INSERT INTO exp_results (job_id, run_id, config_id, item_id, ok, error_reason, output, model, provider,
                                        base_url, input_tokens, output_tokens, cost_usd, latency_ms)
               VALUES (%(job)s, %(run)s, %(config)s, %(item)s, %(ok)s, %(error_reason)s, %(output)s, %(model)s,
                       %(provider)s, %(base_url)s, %(input_tokens)s, %(output_tokens)s, %(cost_usd)s, %(latency_ms)s)
               ON CONFLICT (job_id) DO UPDATE SET ok = EXCLUDED.ok, error_reason = EXCLUDED.error_reason,
                   output = EXCLUDED.output, input_tokens = EXCLUDED.input_tokens,
                   output_tokens = EXCLUDED.output_tokens, latency_ms = EXCLUDED.latency_ms, created_at = NOW()
               RETURNING id""",
            {**values, "job": job["id"], "run": job["run_id"], "config": job["config_id"], "item": job["item_id"]},
        ).fetchone()
        conn.execute("UPDATE exp_jobs SET status = 'done', finished_at = NOW(), lease_until = NULL WHERE id = %s",
                     (job["id"],))
    return str(row["id"])


def fail(conn, job: dict, error: str) -> str:
    """The runner crashed: back to the queue while attempts remain, else 'error'. Returns the new status."""
    row = conn.execute(
        """UPDATE exp_jobs SET status = CASE WHEN attempts >= max_attempts THEN 'error' ELSE 'pending' END,
                  last_error = %s, lease_until = NULL, owner = NULL, finished_at = NOW()
           WHERE id = %s RETURNING status""",
        (error[:500], job["id"]),
    ).fetchone()
    return row["status"]


@dataclass
class WorkSummary:
    done: int = 0
    failed: int = 0
    models: list[str | None] = field(default_factory=list)  # model of every job in the order they ran

    def switches(self) -> int:
        seq = self.models or []
        return sum(1 for a, b in itertools.pairwise(seq) if a != b)


def job_context(conn, job: dict) -> tuple[dict, dict, dict]:
    """(experiment, config, sample item) for a leased job."""
    row = conn.execute(
        """SELECT e.slug, e.kind, e.params AS experiment_params, c.name AS config_name, c.model, c.provider,
                  c.variant, c.params AS config_params, i.item_id, i.content_sha256, i.stratum, i.payload
           FROM exp_jobs j
           JOIN exp_runs r ON r.id = j.run_id
           JOIN experiments e ON e.id = r.experiment_id
           JOIN exp_configs c ON c.id = j.config_id
           JOIN exp_sample_items i ON i.sample_id = r.sample_id AND i.item_id = j.item_id
           WHERE j.id = %s""",
        (job["id"],),
    ).fetchone()
    experiment = {"slug": row["slug"], "kind": row["kind"], "params": row["experiment_params"]}
    config = {"name": row["config_name"], "model": row["model"], "provider": row["provider"],
              "variant": row["variant"], "params": row["config_params"]}
    item = {"item_id": row["item_id"], "content_sha256": row["content_sha256"], "stratum": row["stratum"],
            "payload": row["payload"]}
    return experiment, config, item


def work(conn, runners: dict[str, Runner], owner: str, run_uuid: str | None = None,
         max_jobs: int | None = None, lease_seconds: int = 900) -> WorkSummary:
    """Process claimable jobs until none are left (or ``max_jobs``), grouped by model."""
    summary = WorkSummary(models=[])
    current: str | None = None
    while max_jobs is None or summary.done + summary.failed < max_jobs:
        found, model = next_model(conn, current, run_uuid)
        if not found:
            break
        job = claim(conn, owner, model, run_uuid, lease_seconds)
        if job is None:
            continue  # another worker took it; ask again
        current = model
        experiment, config, item = job_context(conn, job)
        try:
            result = runners[experiment["kind"]]({**job, "experiment": experiment, "config": config}, item)
        except Exception as exc:  # noqa: BLE001 - the queue records it and retries
            fail(conn, job, f"{type(exc).__name__}: {exc}")
            summary.failed += 1
            summary.models.append(model)
            continue
        complete(conn, job, result)
        summary.done += 1
        summary.models.append(model)
    return summary


def finish_run(conn, run_uuid: str) -> dict:
    """Mark a run done when no job is pending or leased; returns job counts by status."""
    counts = {r["status"]: r["n"] for r in conn.execute(
        "SELECT status, count(*) AS n FROM exp_jobs WHERE run_id = %s GROUP BY status", (run_uuid,)).fetchall()}
    if not counts.get("pending") and not counts.get("in_progress"):
        status = "failed" if counts.get("error") else "done"
        conn.execute("UPDATE exp_runs SET status = %s, finished_at = NOW() WHERE id = %s", (status, run_uuid))
    return counts


def finish_open_runs(conn) -> list[dict]:
    """Mark every queued run whose jobs are all finished; returns those runs (id, run_id, experiment, kind, status).

    ``exocortex lab work`` calls this after draining the queue, so runs enqueued without a worker of their
    own (``run ... --queue-only``) end up done or failed like the others.
    """
    rows = conn.execute(
        """SELECT r.id, r.run_id, e.slug, e.kind FROM exp_runs r JOIN experiments e ON e.id = r.experiment_id
           WHERE r.status IN ('queued', 'running')
             AND EXISTS (SELECT 1 FROM exp_jobs j WHERE j.run_id = r.id)
             AND NOT EXISTS (SELECT 1 FROM exp_jobs j WHERE j.run_id = r.id AND j.status IN ('pending', 'in_progress'))
           ORDER BY r.created_at""").fetchall()
    out = []
    for r in rows:
        counts = finish_run(conn, str(r["id"]))
        out.append({"id": str(r["id"]), "run_id": r["run_id"], "experiment": r["slug"], "kind": r["kind"],
                    "status": "failed" if counts.get("error") else "done"})
    return out


def record_metric(conn, result_id: str, run_uuid: str, config_id: str | None, metric: str, value: float | None,
                  ci_low: float | None = None, ci_high: float | None = None, n: int | None = None,
                  method: str | None = None, details: dict | None = None) -> None:
    conn.execute(
        """INSERT INTO exp_metrics (result_id, run_id, config_id, metric, value, ci_low, ci_high, n, method, details)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (result_id) DO UPDATE SET value = EXCLUDED.value, ci_low = EXCLUDED.ci_low,
               ci_high = EXCLUDED.ci_high, n = EXCLUDED.n, method = EXCLUDED.method, details = EXCLUDED.details,
               computed_at = NOW()""",
        (result_id, run_uuid, config_id, metric, value, ci_low, ci_high, n, method, Jsonb(details or {})),
    )
