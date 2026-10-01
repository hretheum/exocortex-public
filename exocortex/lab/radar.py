# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Opportunity radar: a weekly list of experiment candidates (roadmap task F5.1).

From the lab graph, for one ISO week:

1. Hypotheses and plans in new papers: the claim extractor (variant with
   the mode field) runs on the week's new arXiv papers from the radar
   channels (never on an experiment's corpus); claims in the modes
   hypothesis and plan are candidates. Near-duplicates are removed by
   embedding similarity.
2. Possible contradictions: for the most similar pairs of those claims from
   different papers, the model is asked whether they contradict each
   other.
3. Dense topics without a synthesis: groups of at least three papers of the
   week whose embeddings are close to each other.
4. Sudden rises: arXiv categories whose count this week is at least twice
   their mean over the previous four weeks.

Also listed: the week's new models, data sets and tool releases. Every
candidate links to its source. The page is written in Polish and English to
``generated/radar/<week>.md`` with an index ``generated/radar.md``.
"""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from pathlib import Path

from exocortex.lab import extractor
from exocortex.lab.extractor import cosine
from exocortex.lab.headers import personal_data
from exocortex.lab.pages import _cell, _head, _write

CANDIDATE_MODES = ("hypothesis", "plan")
DUPLICATE = 0.90
TOPIC = 0.75
CONTRADICTION_PAIRS = 10
CONTRADICTION_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["contradict"],
                        "properties": {"contradict": {"type": "boolean"}}}
CONTRADICTION_SYSTEM = ("You compare two claims from two different scientific abstracts. Answer whether they "
                        "contradict each other: both cannot be true at the same time about the same thing. "
                        "Claims about different settings do not contradict.")

T = {
    "pl": {"title": "Radar okazji", "week": "tydzień", "intro": (
        "Zestawienie kandydatów na eksperymenty z tygodnia {week}, złożone automatycznie z grafu laboratorium "
        "(zadanie [F5.1]({f51})). Kandydat to sygnał do rozważenia, a nie wynik: wybór i ocena przychodzą w F5.3."),
        "hyp": "Hipotezy i plany w nowych pracach", "hyp_cols": "| Twierdzenie | Tryb | Praca |",
        "contra": "Możliwe sprzeczności", "contra_cols": "| Twierdzenie A | Twierdzenie B | Prace |",
        "topics": "Gęste tematy bez syntezy", "topics_cols": "| Temat (tytuły prac) | Prac |",
        "rises": "Nagłe wzrosty", "rises_cols": "| Kategoria arXiv | W tym tygodniu | Średnio wcześniej |",
        "new": "Nowe modele, dane i wydania", "new_cols": "| Kanał | Pozycja | Data | Licencja |",
        "none": "Brak w tym tygodniu.", "no_base": "Za mało tygodni wstecz, żeby porównać.",
        "omitted": "Pominięto pozycje, które mogły zawierać dane osobowe: {n}.",
        "channels": {"models": "modele", "open-data": "dane publiczne", "tools": "wydania narzędzi"},
        "modes": {"hypothesis": "hipoteza", "plan": "plan"}, "index_title": "Radar okazji: tygodnie",
        "index_intro": "Kolejne tygodnie radaru, od najnowszego."},
    "en": {"title": "Opportunity radar", "week": "week", "intro": (
        "Experiment candidates of the week {week}, compiled automatically from the lab graph (task "
        "[F5.1]({f51})). A candidate is a signal to consider, not a result: selection and scoring come in F5.3."),
        "hyp": "Hypotheses and plans in new papers", "hyp_cols": "| Claim | Mode | Paper |",
        "contra": "Possible contradictions", "contra_cols": "| Claim A | Claim B | Papers |",
        "topics": "Dense topics without a synthesis", "topics_cols": "| Topic (paper titles) | Papers |",
        "rises": "Sudden rises", "rises_cols": "| arXiv category | This week | Mean before |",
        "new": "New models, data sets and releases", "new_cols": "| Channel | Item | Date | License |",
        "none": "None this week.", "no_base": "Not enough earlier weeks to compare.",
        "omitted": "Items left out because they could contain personal data: {n}.",
        "channels": {"models": "models", "open-data": "public data", "tools": "tool releases"},
        "modes": {"hypothesis": "hypothesis", "plan": "plan"}, "index_title": "Opportunity radar: weeks",
        "index_intro": "The radar's weeks, newest first."},
}


def week_of(day: dt.date) -> tuple[str, dt.date, dt.date]:
    """(label like 2026-W40, Monday, Sunday) of the ISO week containing ``day``."""
    year, week, weekday = day.isocalendar()
    monday = day - dt.timedelta(days=weekday - 1)
    return f"{year}-W{week:02d}", monday, monday + dt.timedelta(days=6)


def _signals(conn, tenant: str, start: dt.date, end: dt.date, channel: str | None = None) -> list[dict]:
    rows = conn.execute(
        """SELECT id, body, metadata, embedding::text AS embedding FROM thoughts
           WHERE tenant_id = %s AND thought_type = 'signal' AND (metadata->>'published') BETWEEN %s AND %s
             AND (%s::text IS NULL OR metadata->>'channel' = %s)
           ORDER BY metadata->>'published', metadata->>'uri'""",
        (tenant, start.isoformat(), end.isoformat(), channel, channel),
    ).fetchall()
    out = []
    for r in rows:
        vec = json.loads(r["embedding"]) if r["embedding"] else None
        out.append({"id": str(r["id"]), "body": r["body"], "meta": r["metadata"], "vec": vec})
    return out


def extract_claims(conn, llm, papers: list[dict], model: str) -> int:
    """Run the extractor (mode variant) on papers not yet processed; keep the claims in the node."""
    done = 0
    settings = extractor.Settings(model=model, variant="mode")
    for p in papers:
        if "radar" in p["meta"]:
            continue
        result = extractor.extract(llm, p["body"], settings, embed=lambda t: llm.embed("bge-m3", t))
        claims = [{"claim": c["claim"], "quote": c["quote"], "mode": c["mode"]} for c in result["claims"] if c["usable"]]
        p["meta"]["radar"] = {"model": model, "ok": result["ok"], "claims": claims}
        conn.execute("UPDATE thoughts SET metadata = metadata || %s::jsonb WHERE id = %s",
                     (json.dumps({"radar": p["meta"]["radar"]}), p["id"]))
        done += 1
    return done


def candidates(papers: list[dict], embed) -> list[dict]:
    """Hypothesis and plan claims of the week, near-duplicates removed."""
    found = []
    for p in papers:
        for c in (p["meta"].get("radar") or {}).get("claims", []):
            if c["mode"] in CANDIDATE_MODES:
                found.append({**c, "uri": p["meta"]["uri"], "title": p["meta"].get("title"), "paper": p["meta"]["uri"]})
    if not found:
        return []
    vectors = embed([c["claim"] for c in found])
    kept, kept_vecs = [], []
    for c, v in zip(found, vectors):
        if any(cosine(v, k) >= DUPLICATE for k in kept_vecs):
            continue
        c["vec"] = v
        kept.append(c)
        kept_vecs.append(v)
    return kept


def contradictions(llm, claims: list[dict], model: str) -> list[tuple[dict, dict]]:
    pairs = []
    for i, a in enumerate(claims):
        for b in claims[i + 1:]:
            if a["paper"] != b["paper"]:
                pairs.append((cosine(a["vec"], b["vec"]), a, b))
    found = []
    for _, a, b in sorted(pairs, key=lambda x: -x[0])[:CONTRADICTION_PAIRS]:
        call = llm.structured(model=model, system=CONTRADICTION_SYSTEM, user=f"A: {a['claim']}\nB: {b['claim']}",
                              schema=CONTRADICTION_SCHEMA, name="contradiction", max_tokens=64)
        if call.ok and call.output.get("contradict") is True:
            found.append((a, b))
    return found


def topics(papers: list[dict], min_size: int = 3) -> list[list[dict]]:
    """Groups of papers whose embeddings are within TOPIC of the group's first paper (greedy)."""
    groups: list[list[dict]] = []
    for p in (p for p in papers if p["vec"]):
        for g in groups:
            if cosine(p["vec"], g[0]["vec"]) >= TOPIC:
                g.append(p)
                break
        else:
            groups.append([p])
    return [g for g in groups if len(g) >= min_size]


def rises(conn, tenant: str, monday: dt.date) -> tuple[list[tuple[str, int, float]], bool]:
    """(category, this week, mean of the four weeks before) for categories at least doubling; has baseline."""
    def count(start: dt.date) -> Counter:
        c: Counter = Counter()
        for p in _signals(conn, tenant, start, start + dt.timedelta(days=6), "arxiv"):
            c.update(p["meta"].get("categories") or [])
        return c

    now = count(monday)
    before = [count(monday - dt.timedelta(days=7 * k)) for k in range(1, 5)]
    if not any(before):
        return [], False
    out = []
    for cat, n in now.items():
        mean = sum(b.get(cat, 0) for b in before) / len(before)
        if n >= 3 and n >= 2 * max(mean, 0.5):
            out.append((cat, n, mean))
    return sorted(out, key=lambda x: -x[1]), True


def without_personal_data(found: dict) -> int:
    """Drop every item whose text the gate would hold as personal data; returns how many were dropped."""
    def clean(text: str) -> bool:
        return not personal_data(text)

    before = (len(found["claims"]) + len(found["contradictions"]) + sum(len(g) for g in found["topics"])
              + len(found["new"]))
    found["claims"] = [c for c in found["claims"] if clean(f"{c['claim']} {c.get('title') or ''}")]
    found["contradictions"] = [(a, b) for a, b in found["contradictions"]
                               if clean(f"{a['claim']} {b['claim']}")]
    found["topics"] = [g for g in ([p for p in g if clean(p["meta"].get("title") or "")] for g in found["topics"])
                       if len(g) >= 3]
    found["new"] = [p for p in found["new"] if clean(f"{p['meta'].get('title') or ''} {p['meta'].get('license') or ''}")]
    after = (len(found["claims"]) + len(found["contradictions"]) + sum(len(g) for g in found["topics"])
             + len(found["new"]))
    return before - after


def page(week: str, lang: str, found: dict) -> str:
    t = T[lang]
    other = "en" if lang == "pl" else "pl"
    num = (lambda x: f"{x:.1f}".replace(".", ",")) if lang == "pl" else (lambda x: f"{x:.1f}")
    lines = [_head(f"generated-radar-{week}", lang, f"../../../{other}/generated/radar/{week}.md"),
             f"# {t['title']}: {t['week']} {week}\n",
             t["intro"].format(week=week, f51="../../roadmap/F5-radar-and-experiments.md") + "\n"]
    if found.get("omitted"):
        lines.append(t["omitted"].format(n=found["omitted"]) + "\n")
    lines += [f"## {t['hyp']}", ""]
    if found["claims"]:
        lines += [t["hyp_cols"], "|---|---|---|"]
        lines += [f"| {_cell(c['claim'])} | {t['modes'][c['mode']]} | [{_cell(c['title'])}]({c['uri']}) |"
                  for c in found["claims"]]
    else:
        lines.append(t["none"])
    lines += ["", f"## {t['contra']}", ""]
    if found["contradictions"]:
        lines += [t["contra_cols"], "|---|---|---|"]
        lines += [f"| {_cell(a['claim'])} | {_cell(b['claim'])} | [A]({a['uri']}), [B]({b['uri']}) |"
                  for a, b in found["contradictions"]]
    else:
        lines.append(t["none"])
    lines += ["", f"## {t['topics']}", ""]
    if found["topics"]:
        lines += [t["topics_cols"], "|---|---|"]
        for g in found["topics"]:
            titles = "; ".join(f"[{_cell(p['meta'].get('title'))}]({p['meta']['uri']})" for p in g[:5])
            lines.append(f"| {titles} | {len(g)} |")
    else:
        lines.append(t["none"])
    lines += ["", f"## {t['rises']}", ""]
    if not found["has_baseline"]:
        lines.append(t["no_base"])
    elif found["rises"]:
        lines += [t["rises_cols"], "|---|---|---|"] + [f"| {c} | {n} | {num(m)} |" for c, n, m in found["rises"]]
    else:
        lines.append(t["none"])
    lines += ["", f"## {t['new']}", ""]
    if found["new"]:
        lines += [t["new_cols"], "|---|---|---|---|"]
        lines += [f"| {t['channels'][p['meta']['channel']]} | [{_cell(p['meta'].get('title'))}]({p['meta']['uri']}) | "
                  f"{p['meta'].get('published') or '—'} | {_cell(p['meta'].get('license') or '—')} |" for p in found["new"]]
    else:
        lines.append(t["none"])
    return "\n".join(lines) + "\n"


def corpus_ids() -> set[str]:
    """arXiv ids of every experiment corpus: the radar never runs the extractor on them."""
    import csv

    from exocortex.lab.claims import repo_path

    ids: set[str] = set()
    for manifest in repo_path("lab/corpora").glob("*/manifest.csv"):
        with manifest.open(encoding="utf-8") as fh:
            ids.update(row["arxiv_id"] for row in csv.DictReader(fh))
    return ids


def run(conn, tenant: str, llm, out: Path, day: dt.date | None = None, model: str = "qwen3.6-35b-a3b",
        extract: bool = True) -> dict:
    week, monday, sunday = week_of(day or dt.date.today())  # noqa: DTZ011 — local calendar date; an aware date would change behavior
    reserved = corpus_ids()
    papers = [p for p in _signals(conn, tenant, monday, sunday, "arxiv") if p["meta"].get("arxiv_id") not in reserved]
    processed = extract_claims(conn, llm, papers, model) if extract else 0
    found = {"claims": candidates(papers, lambda t: llm.embed("bge-m3", t))}
    found["contradictions"] = contradictions(llm, found["claims"], model) if found["claims"] else []
    found["topics"] = topics(papers)
    found["rises"], found["has_baseline"] = rises(conn, tenant, monday)
    found["new"] = [p for ch in ("models", "open-data", "tools") for p in _signals(conn, tenant, monday, sunday, ch)]
    found["omitted"] = without_personal_data(found)
    written = []
    for lang in ("pl", "en"):
        if _write(out / lang / "generated" / "radar" / f"{week}.md", page(week, lang, found)):
            written.append(f"{lang}/generated/radar/{week}.md")
        weeks = sorted((p.stem for p in (out / lang / "generated" / "radar").glob("*.md")), reverse=True)
        t = T[lang]
        other = "en" if lang == "pl" else "pl"
        index = [_head("generated-radar", lang, f"../../{other}/generated/radar.md"), f"# {t['index_title']}\n",
                 t["index_intro"] + "\n"] + [f"- [{w}](radar/{w}.md)" for w in weeks]
        if _write(out / lang / "generated" / "radar.md", "\n".join(index) + "\n"):
            written.append(f"{lang}/generated/radar.md")
    return {"week": week, "papers": len(papers), "extracted": processed, "candidates": len(found["claims"]),
            "contradictions": len(found["contradictions"]), "topics": len(found["topics"]),
            "rises": len(found["rises"]), "new_items": len(found["new"]), "left_out_personal_data": found["omitted"],
            "left_out_corpus_papers": len(
                [p for p in _signals(conn, tenant, monday, sunday, "arxiv") if p["meta"].get("arxiv_id") in reserved]),
            "written": written}
