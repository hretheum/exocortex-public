# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Raw results of every experiment as CSV files (roadmap task F2.8).

``data/<slug>/`` in the lab's output folder, published by the publisher:

- configs.csv, samples.csv, sample_items.csv: what was run on what, with
  seeds and checksums;
- runs.csv: every run with its sample, hypothesis version, preregistration
  checksum and code commit;
- results.csv: one row per item and configuration, with tokens, time and
  the whole output as JSON;
- claims.csv (claim experiments): every candidate claim with its quote and
  the reason it was rejected, if it was;
- metrics.csv: the numbers the pages show, under their result ids;
- judgments.csv: blind ratings, raters under pseudonyms only;
- datapackage.json: a Frictionless Data Package describing all of it.

lab/recompute.py recomputes metrics.csv from these files alone. Files are
rewritten only when their content changes.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

FIELDS: dict[str, list[tuple[str, str, str]]] = {
    "configs": [("name", "string", "configuration name"), ("model", "string", "model id on the local server"),
                ("provider", "string", "local, remote or none"), ("variant", "string", "schema or rule variant"),
                ("params", "object", "settings as JSON")],
    "samples": [("name", "string", "sample name"), ("role", "string", "tuning, control, pilot, test or blind"),
                ("seed", "integer", "seed of the draw"), ("method", "string", "how members were drawn"),
                ("data_class", "string", "always public"), ("members_sha256", "string",
                                                            "SHA-256 over sorted 'item_id content_sha256' lines"),
                ("size", "integer", "number of members"), ("touched_at", "datetime",
                                                            "first read of a control sample")],
    "sample_items": [("sample", "string", "sample name"), ("position", "integer", "order of the draw"),
                     ("item_id", "string", "member id"), ("content_sha256", "string", "checksum of the member"),
                     ("stratum", "string", "stratum of the draw")],
    "runs": [("run_id", "string", "run id"), ("sample", "string", "sample name"),
             ("hypothesis_version", "integer", "card version the run measures"),
             ("prereg_hash", "string", "registered checksum of that card version"),
             ("code_commit", "string", "commit of the code that ran"), ("status", "string", "run status"),
             ("created_at", "datetime", "when the run was created (UTC)"),
             ("finished_at", "datetime", "when it finished (UTC)")],
    "results": [("result_uuid", "string", "result id"), ("run_id", "string", "run id"),
                ("config", "string", "configuration name"), ("item_id", "string", "item id"),
                ("ok", "boolean", "valid output"), ("error_reason", "string", "why not, if not"),
                ("model", "string", "model id"), ("provider", "string", "local, remote or none"),
                ("input_tokens", "integer", "prompt tokens, all calls"), ("output_tokens", "integer",
                                                                         "completion tokens, all calls"),
                ("cost_usd", "number", "cost in US dollars"), ("latency_ms", "integer", "time, all calls"),
                ("output", "object", "the whole output as JSON")],
    "claims": [("result_uuid", "string", "result id"), ("config", "string", "configuration name"),
               ("item_id", "string", "document id"), ("i", "integer", "position in the model's answer"),
               ("claim", "string", "claim text"), ("quote", "string", "quote given as support"),
               ("mode", "string", "mode field, if the variant has one"), ("grounded", "boolean",
                                                                          "quote found verbatim"),
               ("proposition", "boolean", "judged a claim"), ("redundant", "boolean", "near duplicate"),
               ("usable", "boolean", "counted as a claim"), ("rejection", "string", "why not usable")],
    "metrics": [("result_id", "string", "id cited by pages and gate decisions"), ("run_id", "string", "run id"),
                ("config", "string", "configuration, empty for a comparison"), ("metric", "string", "metric"),
                ("value", "number", "estimate"), ("ci_low", "number", "95% interval, lower bound"),
                ("ci_high", "number", "95% interval, upper bound"), ("n", "integer", "units counted"),
                ("method", "string", "wilson, bootstrap-by-item, ..."), ("details", "object", "extra fields as JSON")],
    "judgments": [("sample", "string", "blind sample"), ("item_id", "string", "rated unit"),
                  ("rater", "string", "pseudonym"), ("labels", "string", "verdicts, separated by ';'"),
                  ("source_mode", "string", "mode of the source according to the rater"),
                  ("comment", "string", "rater's comment")],
}


def _csv(fields: list[tuple[str, str, str]], rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow([f[0] for f in fields])
    for r in rows:
        w.writerow(["" if r.get(f) is None else
                    json.dumps(r[f], ensure_ascii=False, sort_keys=True) if t == "object" else
                    str(r[f]).lower() if t == "boolean" else
                    r[f].isoformat() if t == "datetime" and hasattr(r[f], "isoformat") else r[f]
                    for f, t, _ in fields])
    return buf.getvalue()


def _write(path: Path, text: str) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return True


def tables(conn, experiment_id: str) -> dict[str, list[dict]]:
    q = lambda sql: [dict(r) for r in conn.execute(sql, (experiment_id,)).fetchall()]  # noqa: E731
    out = {
        "configs": q("SELECT name, model, provider, variant, params FROM exp_configs WHERE experiment_id = %s "
                     "ORDER BY name"),
        "samples": q("SELECT name, role, seed, method, data_class, members_sha256, size, touched_at FROM exp_samples "
                     "WHERE experiment_id = %s ORDER BY name"),
        "sample_items": q("""SELECT s.name AS sample, i.position, i.item_id, i.content_sha256, i.stratum
                             FROM exp_sample_items i JOIN exp_samples s ON s.id = i.sample_id
                             WHERE s.experiment_id = %s ORDER BY s.name, i.position"""),
        "runs": q("""SELECT r.run_id, s.name AS sample, r.hypothesis_version, r.prereg_hash, r.code_commit, r.status,
                            r.created_at, r.finished_at
                     FROM exp_runs r JOIN exp_samples s ON s.id = r.sample_id WHERE r.experiment_id = %s
                     ORDER BY r.created_at"""),
        "results": q("""SELECT res.id::text AS result_uuid, r.run_id, c.name AS config, res.item_id, res.ok,
                               res.error_reason, res.model, res.provider, res.input_tokens, res.output_tokens,
                               res.cost_usd::float AS cost_usd, res.latency_ms, res.output
                        FROM exp_results res JOIN exp_runs r ON r.id = res.run_id JOIN exp_configs c ON c.id = res.config_id
                        WHERE r.experiment_id = %s ORDER BY r.created_at, c.name, res.item_id"""),
        "metrics": q("""SELECT m.result_id, r.run_id, c.name AS config, m.metric, m.value, m.ci_low, m.ci_high, m.n,
                               m.method, m.details
                        FROM exp_metrics m JOIN exp_runs r ON r.id = m.run_id LEFT JOIN exp_configs c ON c.id = m.config_id
                        WHERE r.experiment_id = %s ORDER BY m.result_id"""),
        "judgments": q("""SELECT s.name AS sample, j.item_id, j.rater, array_to_string(j.labels, ';') AS labels,
                                 j.source_mode, j.comment
                          FROM exp_judgments j JOIN exp_samples s ON s.id = j.sample_id
                          WHERE s.experiment_id = %s ORDER BY s.name, j.item_id, j.rater"""),
    }
    for row in out["results"]:
        row["output"] = row["output"] or {}
    claims = []
    for row in out["results"]:
        for c in row["output"].get("claims") or []:
            claims.append({"result_uuid": row["result_uuid"], "config": row["config"], "item_id": row["item_id"],
                           **{k: c.get(k) for k in ("i", "claim", "quote", "mode", "grounded", "proposition",
                                                     "redundant", "usable", "rejection")}})
    out["claims"] = claims
    return out


def datapackage(slug: str, kind: str, params: dict, present: list[str]) -> dict:
    return {
        "name": slug,
        "title": f"Raw results of the lab experiment {slug}",
        "profile": "tabular-data-package",
        "licenses": [{"name": "CC0-1.0", "path": "https://creativecommons.org/publicdomain/zero/1.0/",
                      "title": "arXiv abstracts are CC0; everything else here is produced by the lab"}],
        "exocortex": {"kind": kind, "params": params, "recompute": f"python lab/recompute.py {slug}"},
        "resources": [{"name": name, "path": f"{name}.csv", "profile": "tabular-data-resource", "format": "csv",
                       "encoding": "utf-8",
                       "schema": {"fields": [{"name": f, "type": t, "description": d} for f, t, d in FIELDS[name]]}}
                      for name in present],
    }


def export_experiment(conn, experiment: dict, out: Path) -> list[str]:
    data = tables(conn, str(experiment["id"]))
    folder = out / "data" / experiment["slug"]
    present = [n for n in FIELDS if data.get(n) or n in ("configs", "samples", "runs", "results", "metrics")]
    changed = []
    for name in present:
        if _write(folder / f"{name}.csv", _csv(FIELDS[name], data.get(name, []))):
            changed.append(f"data/{experiment['slug']}/{name}.csv")
    package = json.dumps(datapackage(experiment["slug"], experiment["kind"], experiment["params"], present),
                         indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if _write(folder / "datapackage.json", package):
        changed.append(f"data/{experiment['slug']}/datapackage.json")
    return changed


def export_all(conn, out: Path) -> dict:
    """Every experiment that has at least one run."""
    exps = conn.execute("""SELECT e.id, e.slug, e.kind, e.params FROM experiments e
                           WHERE EXISTS (SELECT 1 FROM exp_runs r WHERE r.experiment_id = e.id) ORDER BY e.slug""").fetchall()
    changed = []
    for e in exps:
        changed += export_experiment(conn, dict(e), out)
    return {"experiments": len(exps), "changed": changed}
