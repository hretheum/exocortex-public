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
from exocortex.lab import stats
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
_NOISE = re.compile(r"^```[\s\S]*?^```|^[ \t]*\|[^\n]*$|^#+ [^\n]*$|^[ \t]*[-*] |\[([^\]]*)\]\([^)]*\)", re.M)


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
    drawn = ex.draw_stratified(items if items is not None else frame(conn, tenant),
                               {"tuning": tuning, "control": control}, seed)
    samples = {}
    for role, items in drawn.items():
        name = f"{role}-{len(items)}"
        samples[role] = ex.create_sample(conn, exp_id, name, role, seed,
                                         f"stratified by language, seed {seed}", items)
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
    """Store the toy metrics of a run; returns their result ids."""
    run = conn.execute("SELECT r.run_id, e.slug FROM exp_runs r JOIN experiments e ON e.id = r.experiment_id "
                       "WHERE r.id = %s", (run_uuid,)).fetchone()
    rows = conn.execute(
        """SELECT c.id AS config_id, c.name, res.item_id, res.ok, res.output FROM exp_results res
           JOIN exp_configs c ON c.id = res.config_id WHERE res.run_id = %s ORDER BY c.name, res.item_id""",
        (run_uuid,),
    ).fetchall()
    by_config: dict[str, dict] = {}
    for r in rows:
        cfg = by_config.setdefault(r["name"], {"id": str(r["config_id"]), "chars": {}, "long": {}})
        if r["ok"]:
            units = r["output"].get("units") or []
            cfg["chars"][r["item_id"]] = float(r["output"]["chars"])
            cfg["long"][r["item_id"]] = (1.0 if units and len(units[0]["text"]) > LONG_UNIT else 0.0, 1.0)
    ids = []
    prefix = f"{run['slug']}/{run['run_id']}"
    for name, cfg in sorted(by_config.items()):
        mean, lo, hi = stats.bootstrap_mean(cfg["chars"])
        rid = f"{prefix}/{name}/mean_chars"
        ex.record_metric(conn, rid, run_uuid, cfg["id"], "mean_chars", mean, lo, hi, len(cfg["chars"]),
                         "bootstrap-by-item")
        ids.append(rid)
        k = int(sum(v[0] for v in cfg["long"].values()))
        p, lo, hi = stats.wilson(k, len(cfg["long"]))
        rid = f"{prefix}/{name}/long_unit_share"
        ex.record_metric(conn, rid, run_uuid, cfg["id"], "long_unit_share", p, lo, hi, len(cfg["long"]), "wilson",
                         {"successes": k})
        ids.append(rid)
    names = sorted(by_config)
    if len(names) == 2:
        a, b = by_config[names[0]]["long"], by_config[names[1]]["long"]
        d, lo, hi = stats.bootstrap_difference(a, b)
        rid = f"{prefix}/diff/long_unit_share"
        ex.record_metric(conn, rid, run_uuid, None, "long_unit_share_difference", d, lo, hi, len(set(a) & set(b)),
                         "bootstrap-by-item", {"a": names[0], "b": names[1], "difference": "b - a"})
        ids.append(rid)
    return ids
