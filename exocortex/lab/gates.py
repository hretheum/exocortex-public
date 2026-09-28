# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Processor ``gate_decision``: decisions at the gates (roadmap task F2.5).

A decision is where a criterion can quietly change, so the processor
accepts a decision only if:

- both language versions exist, their headers are valid and agree;
- both say ``human_validated: true`` (otherwise it is recorded as ignored:
  it changes nothing and later compilers do not see it);
- the hypothesis version it decides is registered (frozen) and not
  violated;
- every criterion and guard metric it quotes has the same threshold as the
  frozen card, unless the decision is PIVOT and a newer card version that
  supersedes this one exists;
- it names result ids, and each one exists in the experiment tables;
- NOT-NOW comes with a return condition.

An accepted decision moves the hypothesis to the decided state (GO, NO-GO,
PIVOT, NOT-NOW or CLOSED) and gets a node in the graph with a ``decides``
edge to the card version.
"""

from __future__ import annotations

import hashlib

from psycopg.types.json import Jsonb

from exocortex.lab import headers
from exocortex.lab.db import insert_edge, upsert_thought
from exocortex.lab.docs import first_table_under
from exocortex.lab.hypotheses import norm_value, table_rows

CRITERIA_HEADINGS = ("Kryteria z karty hipotezy (bez zmian)", "Criteria from the hypothesis card (unchanged)")
GUARD_HEADINGS = ("Metryki ochronne", "Guard metrics")
_CRITERIA_COLUMNS = {"metric": ("kryterium", "criterion"), "threshold": ("próg", "threshold"),
                     "result_id": ("id wyniku", "result id")}
_GUARD_COLUMNS = {"metric": ("metryka", "metric"), "threshold": ("granica", "limit")}
AGREE = ("hypothesis", "hypothesis_version", "gate", "decision", "date", "result_ids", "return_condition")


def _decision_docs(docs: list[dict]) -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    for d in docs:
        if d.get("kind") == "gate_decision" and d.get("lang") in ("pl", "en") and not d["key"].startswith("templates/"):
            out.setdefault(d["key"], {})[d["lang"]] = d
    return out


def quoted_thresholds(body: str) -> list[dict]:
    rows = table_rows(first_table_under(body, CRITERIA_HEADINGS), _CRITERIA_COLUMNS)
    rows += [{**r, "result_id": ""} for r in table_rows(first_table_under(body, GUARD_HEADINGS), _GUARD_COLUMNS)]
    return [r for r in rows if r["metric"]]


def threshold_mismatches(quoted: list[dict], card_rows: list[dict]) -> list[str]:
    """Criteria of a decision whose threshold is not the card's, or that the card does not have."""
    card = {norm_value(r["metric"]): norm_value(r["threshold"]) for r in card_rows if r.get("metric")}
    out = []
    for r in quoted:
        name = norm_value(r["metric"])
        if name not in card:
            out.append(f"criterion {r['metric']!r} is not in the frozen card")
        elif norm_value(r["threshold"]) != card[name]:
            out.append(f"threshold of {r['metric']!r} is {r['threshold']!r}, the frozen card says a different value")
    return out


def check(conn, pair: dict[str, dict]) -> tuple[str, list[str], dict, bool]:
    """(status, reasons, header, approved) for one decision; status is applied, rejected or ignored."""
    reasons: list[str] = []
    for lang, d in sorted(pair.items()):
        reasons += [f"{d['rel']}: {p}" for p in headers.validate(d["rel"], d["body"])]
    missing = {"pl", "en"} - set(pair)
    if missing:
        only = next(iter(pair.values()))
        return ("rejected", reasons + [f"missing language version: {', '.join(sorted(missing))}"],
                only["front"], False)
    pl, en = pair["pl"], pair["en"]
    front = pl["front"]
    for field in AGREE:
        if pl["front"].get(field) != en["front"].get(field):
            reasons.append(f"{field} differs between the Polish and English versions")
    approved = pl["front"].get("human_validated") is True and en["front"].get("human_validated") is True
    if not approved:
        return "ignored", reasons + ["not approved (human_validated is not true in both versions)"], front, False
    slug, version, decision = front.get("hypothesis"), front.get("hypothesis_version"), front.get("decision")
    card = conn.execute("SELECT * FROM lab_hypotheses WHERE slug = %s AND version = %s", (slug, version)).fetchone()
    if card is None:
        reasons.append(f"hypothesis {slug} v{version} is not among the cards")
    elif card["prereg_sha256"] is None:
        reasons.append(f"hypothesis {slug} v{version} is not frozen (no preregistration entry)")
    elif card["violated"]:
        reasons.append(f"hypothesis {slug} v{version} changed after it was frozen: its gates are blocked")
    if decision is None:
        reasons.append("no decision")
    if decision == "NOT-NOW" and not front.get("return_condition"):
        reasons.append("NOT-NOW needs a return condition")
    if card is not None:
        mismatches = []
        for lang, d in (("pl", pl), ("en", en)):
            mismatches += [f"{lang}: {m}" for m in threshold_mismatches(quoted_thresholds(d["body"]),
                                                                        card["metrics"].get(lang, []))]
        if mismatches and decision == "PIVOT":
            newer = conn.execute("SELECT 1 FROM lab_hypotheses WHERE slug = %s AND supersedes = %s",
                                 (slug, version)).fetchone()
            if newer is None:
                reasons.append("PIVOT with changed criteria needs a new card version that supersedes this one")
        elif mismatches:
            reasons += mismatches
    result_ids = front.get("result_ids") or []
    if not result_ids:
        reasons.append("the decision names no result ids")
    for rid in result_ids:
        found = conn.execute("SELECT 1 FROM exp_metrics WHERE result_id = %s", (rid,)).fetchone()
        if found is None:
            reasons.append(f"result id {rid!r} is not in the experiment tables")
    return ("rejected" if reasons else "applied"), reasons, front, True


def _order(item: tuple[str, dict[str, dict]]) -> tuple:
    front = next(iter(item[1].values()))["front"]
    return str(front.get("date") or ""), str(front.get("gate") or ""), item[0]


def process(conn, tenant: str, docs: list[dict]) -> dict:
    """Check every decision, oldest first, so the latest applied one sets the hypothesis state.

    Run after hypotheses.process, which resets every card to frozen or draft.
    """
    counts = {"decisions": 0, "applied": 0, "rejected": 0, "ignored": 0}
    for key, pair in sorted(_decision_docs(docs).items(), key=_order):
        counts["decisions"] += 1
        status, reasons, front, approved = check(conn, pair)
        counts[status] += 1
        digest = hashlib.sha256("".join(pair[lang]["body"] for lang in sorted(pair)).encode()).hexdigest()
        slug, version = front.get("hypothesis"), front.get("hypothesis_version")
        tid = None
        if status == "applied":
            meta = {"domain": "lab", "hypothesis": slug, "hypothesis_version": version, "gate": front.get("gate"),
                    "decision": front.get("decision"), "result_ids": front.get("result_ids"), "key": key}
            tid, _ = upsert_thought(conn, tenant, source_id=None, thought_type="gate_decision", key=key,
                                    body=pair["pl"]["body"], metadata=meta)
            card = conn.execute("SELECT thought_id FROM lab_hypotheses WHERE slug = %s AND version = %s",
                                (slug, version)).fetchone()
            if card and card["thought_id"]:
                insert_edge(conn, tenant, tid, "thought", str(card["thought_id"]), "thought", "decides")
            conn.execute("""UPDATE lab_hypotheses SET state = %s, return_condition = %s, updated_at = NOW()
                            WHERE slug = %s AND version = %s""",
                         (front["decision"], front.get("return_condition"), slug, version))
        date = front.get("date") if isinstance(front.get("date"), str) and front.get("date", "")[:1].isdigit() else None
        conn.execute(
            """INSERT INTO lab_gate_decisions (key, slug, hypothesis_version, gate, decision, decided_on, approved,
                                               status, reasons, result_ids, content_sha256, thought_id, processed_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
               ON CONFLICT (key) DO UPDATE SET slug = EXCLUDED.slug, hypothesis_version = EXCLUDED.hypothesis_version,
                   gate = EXCLUDED.gate, decision = EXCLUDED.decision, decided_on = EXCLUDED.decided_on,
                   approved = EXCLUDED.approved, status = EXCLUDED.status, reasons = EXCLUDED.reasons,
                   result_ids = EXCLUDED.result_ids, content_sha256 = EXCLUDED.content_sha256,
                   thought_id = COALESCE(EXCLUDED.thought_id, lab_gate_decisions.thought_id), processed_at = NOW()""",
            (key, slug if isinstance(slug, str) else None, version if isinstance(version, int) else None,
             front.get("gate") if front.get("gate") in ("G0", "G1", "G2") else None,
             front.get("decision") if front.get("decision") in ("GO", "NO-GO", "PIVOT", "NOT-NOW", "CLOSED") else None,
             date, approved, status, Jsonb(reasons), [str(r) for r in front.get("result_ids") or []], digest, tid),
        )
    return counts
