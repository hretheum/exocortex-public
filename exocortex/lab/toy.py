# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Toy experiment: the whole path of the experiment machinery (roadmap F2.6).

Items are the lab's own published documents, in both languages. Two
configurations measure each document without any model: length in
characters, words and sentences, and one sentence chosen by a fixed rule
(the first, or the longest), which stands in for a claim when the blind
sample tool is tested (F3.5). The configurations carry placeholder model
names, so the queue test can show that jobs run grouped by model.

Metrics per run: mean length in characters (bootstrap by document), the
share of documents whose chosen sentence is longer than 120 characters
(Wilson), and the difference in that share between the configurations
(paired bootstrap by document).
"""

from __future__ import annotations

import re
import time

from exocortex.lab import experiments as ex
from exocortex.lab import metrics
from exocortex.lab.docs import split_front
from exocortex.lab.docsync import current_documents

SLUG = "toy-length"
KIND = "toy"
TITLE = "Toy experiment: document length"
CONFIGS = {
    "first-sentence": {"model": "toy-model-a", "params": {"unit": "first"}},
    "longest-sentence": {"model": "toy-model-b", "params": {"unit": "longest"}},
}
LONG_UNIT = 120
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ\"„(])")
_NOISE = re.compile(r"^```[\s\S]*?^```|^[ \t]*\|[^\n]*$|^#+ [^\n]*$|^[ \t]*[-*] |\[([^\]]*)\]\([^)]*\)", re.MULTILINE)


def prose(text: str) -> str:
    """Body text without header, code, tables and headings; link text kept."""
    _, body = split_front(text)
    body = _NOISE.sub(lambda m: m.group(1) or "", body)
    return " ".join(body.split())


def measure(text: str, unit: str) -> dict:
    body = prose(text)
    sentences = [s for s in _SENTENCE.split(body) if s.strip()]
    chosen = ""
    if sentences:
        chosen = sentences[0] if unit == "first" else max(sentences, key=len)
    start = body.find(chosen)
    context = body[max(0, start - 200): start + len(chosen) + 200] if chosen else ""
    return {"chars": len(body), "words": len(body.split()), "sentences": len(sentences),
            "units": [{"text": chosen, "quote": chosen, "context": context}] if chosen else []}


def frame(conn, tenant: str) -> list[dict]:
    """Every published document in pl/ or en/ except templates, stratified by language."""
    return [{"item_id": d["rel"], "content_sha256": d["sha256"], "stratum": d["lang"]}
            for d in current_documents(conn, tenant)
            if d.get("lang") in ("pl", "en") and d.get("kind") != "template"]


def setup(conn, tenant: str, seed: int = 20260929, tuning: int = 12, control: int = 6,
          items: list[dict] | None = None) -> dict:
    """Experiment, configurations and two disjoint samples (tuning, control) from ``items`` or the frame."""
    exp_id = ex.ensure_experiment(conn, SLUG, KIND, TITLE, hypothesis_slug=SLUG,
                                  params={"long_unit_chars": LONG_UNIT})
    configs = {name: ex.ensure_config(conn, exp_id, name, model=c["model"], provider="none",
                                      variant=c["params"]["unit"], params=c["params"])
               for name, c in CONFIGS.items()}
    # The samples are drawn once and kept: the published documents keep changing, and a new draw from
    # them would no longer match the stored members.
    kept = {r["role"]: str(r["id"]) for r in conn.execute(
        """SELECT DISTINCT ON (role) id, role FROM exp_samples WHERE experiment_id = %s
           AND role IN ('tuning', 'control') ORDER BY role, created_at, id""", (exp_id,)).fetchall()}
    if items is None and set(kept) == {"tuning", "control"}:
        return {"experiment": exp_id, "configs": configs, "samples": kept}
    drawn = ex.draw_stratified(items if items is not None else frame(conn, tenant),
                               {"tuning": tuning, "control": control}, seed)
    samples = {}
    for role, role_items in drawn.items():
        name = f"{role}-{len(role_items)}"
        samples[role] = ex.create_sample(conn, exp_id, name, role, seed,
                                         f"stratified by language, seed {seed}", role_items)
    return {"experiment": exp_id, "configs": configs, "samples": samples}


def make_runner(conn, tenant: str):
    texts = {d["rel"]: d for d in current_documents(conn, tenant)}

    def run(job: dict, item: dict) -> dict:
        started = time.monotonic()
        doc = texts.get(item["item_id"])
        if doc is None or doc["sha256"] != item["content_sha256"]:
            return {"ok": False, "error_reason": "document changed since the sample was drawn",
                    "model": job["config"]["model"], "provider": "none"}
        out = measure(doc["body"], job["config"]["params"]["unit"])
        return {"ok": True, "output": out, "model": job["config"]["model"], "provider": "none",
                "latency_ms": round((time.monotonic() - started) * 1000)}

    return run


def compute_metrics(conn, run_uuid: str) -> list[str]:
    """Store the toy metrics of a run; returns their result ids (exocortex/lab/metrics.py)."""
    run = conn.execute("SELECT r.run_id, e.slug FROM exp_runs r JOIN experiments e ON e.id = r.experiment_id "
                       "WHERE r.id = %s", (run_uuid,)).fetchone()
    rows = conn.execute(
        """SELECT c.id AS config_id, c.name, res.item_id, res.ok, res.output FROM exp_results res
           JOIN exp_configs c ON c.id = res.config_id WHERE res.run_id = %s ORDER BY c.name, res.item_id""",
        (run_uuid,),
    ).fetchall()
    config_ids = {r["name"]: str(r["config_id"]) for r in rows}
    plain = [{"config": r["name"], "item_id": r["item_id"], "ok": r["ok"], "chars": (r["output"] or {}).get("chars"),
              "unit_chars": unit_chars(r["output"])} for r in rows]
    ids = []
    for m in metrics.toy_metrics(plain, f"{run['slug']}/{run['run_id']}", LONG_UNIT):
        ex.record_metric(conn, m["result_id"], run_uuid, config_ids.get(m["config"]), m["metric"], m["value"],
                         m["ci_low"], m["ci_high"], m["n"], m["method"], m["details"])
        ids.append(m["result_id"])
    return ids


def unit_chars(output: dict | None) -> int | None:
    units = (output or {}).get("units") or []
    return len(units[0]["text"]) if units else None
