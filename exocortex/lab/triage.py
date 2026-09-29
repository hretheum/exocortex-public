# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""First scoring of radar candidates by models of three families (roadmap task F5.3).

Each candidate (a hypothesis or plan found by the radar) goes to three local
models of different families, each asked on its own, with the rules of the
triage template (dowody/*/templates/triage.md): five knock-out questions and
seven dimensions scored 1 to 5 with fixed weights. A "no" from any model on
a knock-out question, or a spread of at least two points in any dimension,
marks the candidate for discussion; scores are then not averaged. The page
lists everything for a person, who decides at gate G0. Nothing here decides.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from exocortex.lab.pages import _cell, _head, _write

MODELS = (("qwen3.6-35b-a3b", "json_schema"), ("gemma-4-26b-a4b", "json_schema"), ("gpt-oss-20b", "tools"))
KNOCKOUTS = ("why", "data", "legal", "measurable", "needs_ai")
DIMENSIONS = (("value", 25), ("feasibility", 15), ("effort", 15), ("data", 15), ("risk", 10), ("evidence", 10),
              ("gap", 10))

SYSTEM = """You help a small public AI lab choose its next experiments. The lab runs local open-weight models \
on one home server (one 24 GB GPU), uses only public data, publishes every hypothesis, result and dataset, and \
measures claims extraction and retrieval over its own knowledge graph. Current experiments: whether a mode field \
keeps plans and hypotheses from turning into facts in claim extraction; planned: graph expansion versus plain \
embedding search, local versus cloud embeddings, and grammar-constrained answers.

You get one candidate: a statement from a new paper. Judge whether testing it would make a good experiment for \
this lab. Answer the knock-out questions with true or false:
- why: we know why the lab would do it (the result would matter to someone);
- data: suitable public data exists;
- legal: it can be done lawfully with public data;
- measurable: it can be measured with a number decided in advance;
- needs_ai: it cannot be done more simply without AI.
Then score each dimension from 1 to 5, higher is better:
- value: 1 a curiosity, 3 useful, 5 changes decisions;
- feasibility: 1 no tools or compute, 3 to be built, 5 ready;
- effort (reversed): 1 over a month to the first gate, 3 a week, 5 a day;
- data: 1 none, 3 needs work, 5 ready;
- risk (reversed): 1 high legal, privacy or reputation risk, 3 medium, 5 low;
- evidence: 1 the result cannot be published and checked, 3 partly, 5 fully;
- gap: 1 does not fill anything missing from the lab's record, 3 partly, 5 directly.
Give one short sentence of reasons."""

SCHEMA = {"type": "object", "additionalProperties": False,
          "required": ["knockouts", "scores", "reason"],
          "properties": {
              "knockouts": {"type": "object", "additionalProperties": False, "required": list(KNOCKOUTS),
                            "properties": {k: {"type": "boolean"} for k in KNOCKOUTS}},
              "scores": {"type": "object", "additionalProperties": False, "required": [d for d, _ in DIMENSIONS],
                         "properties": {d: {"type": "integer", "minimum": 1, "maximum": 5} for d, _ in DIMENSIONS}},
              "reason": {"type": "string"}}}


def weighted(scores: dict) -> float:
    return sum(scores[d] * w for d, w in DIMENSIONS) / 100


def assess(candidates: list[dict], llm) -> list[dict]:
    """Every candidate scored by every model; calls grouped by model so the server swaps models twice."""
    import jsonschema

    results = {i: {} for i in range(len(candidates))}
    for model, mode in MODELS:
        for i, c in enumerate(candidates):
            # reasoning models spend part of the budget before answering: 4000 leaves room (measured 700 to 1300)
            call = llm.structured(model=model, system=SYSTEM, name="triage", mode=mode, max_tokens=4000,
                                  user=f"Candidate: {c['claim']}\nSource: {c.get('title') or c['uri']}", schema=SCHEMA)
            ok = call.ok
            if ok:
                try:
                    jsonschema.validate(call.output, SCHEMA)
                except jsonschema.ValidationError:
                    ok = False
            results[i][model] = call.output if ok else {"error": call.error or "answer does not match the schema"}
    out = []
    for i, c in enumerate(candidates):
        answers = results[i]
        valid = {m: a for m, a in answers.items() if "error" not in a}
        knocked = sorted({k for a in valid.values() for k, v in a["knockouts"].items() if v is False})
        spread = {d: max(a["scores"][d] for a in valid.values()) - min(a["scores"][d] for a in valid.values())
                  for d, _ in DIMENSIONS} if valid else {}
        discuss = sorted(d for d, s in spread.items() if s >= 2)
        out.append({**c, "answers": answers, "knocked_out_by": knocked, "discuss": discuss,
                    "weighted": {m: weighted(a["scores"]) for m, a in valid.items()},
                    "complete": len(valid) == len(MODELS)})
    return out


T = {
    "pl": {"title": "Wybór kandydatów: pierwsza ocena modeli", "intro": (
        "Kandydaci z radaru ({radar}) ocenieni osobno przez modele trzech rodzin według szablonu wyboru "
        "kandydatów (zadanie [F5.3]({f53})). To tylko pierwsza ocena: decyzję podejmuje człowiek na bramce G0."),
        "cols": "| Nr | Kandydat | Odpada na pytaniu | Do dyskusji (rozrzut ≥ 2) | Wynik ważony (qwen / gemma / gpt-oss) |",
        "detail": "Szczegóły ocen", "detail_cols": "| Nr | Model | Pytania odrzucające | Wartość | Wykonalność | Nakład | Dane | Ryzyko | Dowodowa | Luka | Uzasadnienie |",
        "yes_no": {True: "tak", False: "nie"}, "error": "brak poprawnej odpowiedzi", "none": "—"},
    "en": {"title": "Selecting candidates: first scoring by models", "intro": (
        "Candidates from the radar ({radar}) scored separately by models of three families with the candidate "
        "selection template (task [F5.3]({f53})). This is only a first scoring: a person decides at gate G0."),
        "cols": "| No. | Candidate | Knocked out on | To discuss (spread ≥ 2) | Weighted score (qwen / gemma / gpt-oss) |",
        "detail": "Scores in detail", "detail_cols": "| No. | Model | Knock-out questions | Value | Feasibility | Effort | Data | Risk | Evidence | Gap | Reason |",
        "yes_no": {True: "yes", False: "no"}, "error": "no valid answer", "none": "—"},
}


def page(week: str, lang: str, assessed: list[dict]) -> str:
    t = T[lang]
    other = "en" if lang == "pl" else "pl"
    fmt = (lambda x: f"{x:.2f}".replace(".", ",")) if lang == "pl" else (lambda x: f"{x:.2f}")
    lines = [_head(f"generated-triage-{week}", lang, f"../../../{other}/generated/triage/{week}.md"),
             f"# {t['title']}: {week}\n",
             t["intro"].format(radar=f"[{week}](../radar/{week}.md)", f53="../../roadmap/F5-radar-and-experiments.md") + "\n",
             t["cols"], "|---|---|---|---|---|"]
    for n, a in enumerate(assessed, 1):
        scores = " / ".join(fmt(a["weighted"][m]) if m in a["weighted"] else t["none"] for m, _ in MODELS)
        lines.append(f"| {n} | [{_cell(a['claim'])}]({a['uri']}) | {', '.join(a['knocked_out_by']) or t['none']} | "
                     f"{', '.join(a['discuss']) or t['none']} | {scores} |")
    lines += ["", f"## {t['detail']}", "", t["detail_cols"], "|---|---|---|---|---|---|---|---|---|---|---|"]
    for n, a in enumerate(assessed, 1):
        for m, _ in MODELS:
            ans = a["answers"].get(m, {"error": "missing"})
            if "error" in ans:
                lines.append(f"| {n} | {m} | {t['error']} |" + " |" * 8)
                continue
            ko = ", ".join(f"{k}: {t['yes_no'][v]}" for k, v in ans["knockouts"].items())
            sc = " | ".join(str(ans["scores"][d]) for d, _ in DIMENSIONS)
            lines.append(f"| {n} | {m} | {ko} | {sc} | {_cell(ans['reason'])} |")
    return "\n".join(lines) + "\n"


def run(conn, tenant: str, llm, out: Path, day: dt.date | None = None, limit: int = 10) -> dict:
    from exocortex.lab import radar

    week, monday, sunday = radar.week_of(day or dt.date.today())
    reserved = radar.corpus_ids()
    papers = [p for p in radar._signals(conn, tenant, monday, sunday, "arxiv") if p["meta"].get("arxiv_id") not in reserved]
    from exocortex.lab.headers import personal_data

    everything = radar.candidates(papers, lambda texts: llm.embed("bge-m3", texts))
    found = [c for c in everything if not personal_data(f"{c['claim']} {c.get('title') or ''}")][:limit]
    for c in found:
        c.pop("vec", None)
    assessed = assess(found, llm)
    written = []
    for lang in ("pl", "en"):
        if _write(out / lang / "generated" / "triage" / f"{week}.md", page(week, lang, assessed)):
            written.append(f"{lang}/generated/triage/{week}.md")
    return {"week": week, "candidates": len(assessed), "complete": sum(a["complete"] for a in assessed),
            "left_out_personal_data": sum(1 for c in everything if personal_data(f"{c['claim']} {c.get('title') or ''}")),
            "to_discuss": sum(bool(a["discuss"]) for a in assessed),
            "knocked_out": sum(bool(a["knocked_out_by"]) for a in assessed), "written": written,
            "summary": json.dumps([{"claim": a["claim"][:80], "weighted": a["weighted"]} for a in assessed])[:2000]}
