# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Compile domain ``dowody``: result pages built from the lab graph (roadmap task F2.7).

Pages, each in Polish and English from one pass:

- ``generated/roadmap-status.md``: every task of the roadmap with its status,
  dependencies and what it still waits for, from the task files' headers
  (and, for phases without task files, from the task sections of the phase
  document);
- ``generated/experiments.md``: every experiment with the state of its card;
- ``generated/experiments/<slug>.md``: the dossier of one experiment: card
  versions and preregistration, configurations, runs, results with
  confidence intervals, gate decisions, and links to the raw data.

Fixed text comes from the templates below; names and numbers come from the
lab database. Pages carry no timestamp of their own, so a page changes only
when its data does. They are written to the lab's output folder
(``$LAB_OUT/{pl,en}/generated``); the publisher sends them through the same
checks as every other document.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from exocortex.lab.docsync import current_documents

T: dict[str, dict[str, Any]] = {
    "pl": {
        "status": {"todo": "do zrobienia", "doing": "w toku", "done": "zrobione"},
        "roadmap_title": "Stan roadmapy",
        "roadmap_intro": ("Strona powstaje automatycznie w laboratorium z nagłówków plików zadań (zadanie "
                          "[F2.7]({f27})). Nie edytuje się jej ręcznie: stan zmienia się w pliku zadania."),
        "phase_cols": "| Faza | Zadań | Zrobione | W toku | Do zrobienia |",
        "task_cols": "| Id | Zadanie | Stan | Zależy od | Czeka na |",
        "from_phase_doc": "opis w dokumencie fazy",
        "exp_title": "Eksperymenty",
        "exp_intro": ("Lista eksperymentów laboratorium ze stanem ich kart hipotez. Strona powstaje automatycznie "
                      "z grafu laboratorium."),
        "exp_cols": "| Eksperyment | Karta | Stan | Prerejestracja | Przebiegi | Dossier |",
        "states": {"draft": "projekt", "frozen": "zamrożona", "GO": "GO", "NO-GO": "NO-GO", "PIVOT": "PIVOT",
                   "NOT-NOW": "NOT-NOW", "CLOSED": "CLOSED"},
        "violated": r"$\color{red}{\textsf{naruszona}}$",
        "none": "brak",
        "no_card": "bez karty",
        "dossier_title": "Dossier",
        "dossier_intro": ("Dossier eksperymentu {slug}, złożone automatycznie z grafu laboratorium. Karta, "
                          "konfiguracje i próby są opisane w dokumentach eksperymentu, a surowe dane w katalogu "
                          "danych."),
        "card": "Karta hipotezy",
        "card_cols": "| Wersja | Stan | Zatwierdzona | Suma kontrolna treści | Zarejestrowana | Suma w rejestrze |",
        "configs": "Konfiguracje",
        "config_cols": "| Nazwa | Model | Dostawca | Wariant |",
        "runs": "Przebiegi",
        "run_cols": "| Przebieg | Próba | Rola próby | Stan | Zadania | Commit kodu | Suma z prerejestracji |",
        "results": "Wyniki",
        "result_cols": "| Id wyniku | Metryka | Wartość | Przedział ufności | n | Metoda |",
        "gates": "Decyzje z bramek",
        "gate_cols": "| Plik | Bramka | Decyzja | Stan | Powody |",
        "gate_status": {"applied": "przyjęta", "rejected": "odrzucona", "ignored": "niezatwierdzona"},
        "data": "Surowe dane",
        "data_text": "Pliki CSV z opisem kolumn: [datapackage.json]({link}). Przeliczenie: `python lab/recompute.py {slug}`.",
        "no_data": "Brak wyeksportowanych danych.",
        "yes": "tak", "no": "nie", "dash": "—",
        "problems": "Problemy w karcie",
    },
    "en": {
        "status": {"todo": "to do", "doing": "in progress", "done": "done"},
        "roadmap_title": "Roadmap status",
        "roadmap_intro": ("This page is built automatically in the lab from the headers of the task files (task "
                          "[F2.7]({f27})). It is not edited by hand: the status changes in the task file."),
        "phase_cols": "| Phase | Tasks | Done | In progress | To do |",
        "task_cols": "| Id | Task | Status | Depends on | Waits for |",
        "from_phase_doc": "described in the phase document",
        "exp_title": "Experiments",
        "exp_intro": ("The lab's experiments with the state of their hypothesis cards. This page is built "
                      "automatically from the lab graph."),
        "exp_cols": "| Experiment | Card | State | Preregistration | Runs | Dossier |",
        "states": {"draft": "draft", "frozen": "frozen", "GO": "GO", "NO-GO": "NO-GO", "PIVOT": "PIVOT",
                   "NOT-NOW": "NOT-NOW", "CLOSED": "CLOSED"},
        "violated": r"$\color{red}{\textsf{violated}}$",
        "none": "none",
        "no_card": "no card",
        "dossier_title": "Dossier",
        "dossier_intro": ("Dossier of the experiment {slug}, compiled automatically from the lab graph. The card, "
                          "configurations and samples are described in the experiment's documents, and the raw "
                          "data in the data folder."),
        "card": "Hypothesis card",
        "card_cols": "| Version | State | Approved | Content checksum | Registered | Registered checksum |",
        "configs": "Configurations",
        "config_cols": "| Name | Model | Provider | Variant |",
        "runs": "Runs",
        "run_cols": "| Run | Sample | Sample role | Status | Jobs | Code commit | Preregistration checksum |",
        "results": "Results",
        "result_cols": "| Result id | Metric | Value | Confidence interval | n | Method |",
        "gates": "Gate decisions",
        "gate_cols": "| File | Gate | Decision | Status | Reasons |",
        "gate_status": {"applied": "applied", "rejected": "rejected", "ignored": "not approved"},
        "data": "Raw data",
        "data_text": "CSV files with a description of the columns: [datapackage.json]({link}). Recompute: `python lab/recompute.py {slug}`.",
        "no_data": "No exported data yet.",
        "yes": "yes", "no": "no", "dash": "—",
        "problems": "Problems in the card",
    },
}
_TASK_SECTION = re.compile(r"^### (F\d+\.\d+)\. (.+)$", re.MULTILINE)
_DEPENDS = re.compile(r"(?:Zależy od|Depends on) ([^.]+)\.")
_ID = re.compile(r"F\d+(?:\.\d+)?")


def _num(value: float | None, lang: str, digits: int = 3) -> str:
    if value is None:
        return "—"
    text = f"{value:.{digits}f}"
    return text.replace(".", ",") if lang == "pl" else text


def _cell(text) -> str:
    return str(text).replace("|", "/").replace("\n", " ").strip() or "—"


def _head(page_id: str, lang: str, counterpart: str) -> str:
    return f"---\nid: {page_id}\nlang: {lang}\ncounterpart: {counterpart}\ngenerated: true\n---\n"


def _task_title(body: str, task_id: str) -> str:
    m = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    title = m.group(1).strip() if m else task_id
    return re.sub(rf"^{re.escape(task_id)}\.?\s*", "", title)


def roadmap_tasks(docs: list[dict], lang: str) -> list[dict]:
    """Phases with their tasks: from task files, or from sections of the phase document."""
    mine = [d for d in docs if d.get("lang") == lang]
    phases = {d["front"].get("id"): d for d in mine if d.get("kind") == "roadmap_phase" and d["front"].get("id")}
    tasks = [d for d in mine if d.get("kind") == "roadmap_task"]
    out = []
    for pid in sorted(phases, key=lambda p: int(p[1:])):
        phase = phases[pid]
        rows = []
        for t in sorted((t for t in tasks if t["front"].get("phase") == pid),
                        key=lambda t: int(t["front"]["id"].split(".")[1])):
            rows.append({"id": t["front"]["id"], "title": _task_title(t["body"], t["front"]["id"]),
                         "status": t["front"].get("status", "todo"), "depends_on": t["front"].get("depends_on") or [],
                         "rel": t["rel"], "from_phase_doc": False})
        if not rows:  # phases whose tasks are sections of the phase document (F4 to F7)
            # their status, if any, is a map in the phase header: task_status: {F5.2: done}
            known = phase["front"].get("task_status") or {}
            sections = list(_TASK_SECTION.finditer(phase["body"]))
            for i, m in enumerate(sections):
                text = phase["body"][m.end(): sections[i + 1].start() if i + 1 < len(sections) else len(phase["body"])]
                dep = _DEPENDS.search(text)
                rows.append({"id": m.group(1), "title": m.group(2).strip(),
                             "status": known.get(m.group(1), "todo") if isinstance(known, dict) else "todo",
                             "depends_on": _ID.findall(dep.group(1)) if dep else [], "rel": phase["rel"],
                             "from_phase_doc": True})
        out.append({"id": pid, "title": _task_title(phase["body"], pid), "rel": phase["rel"],
                    "status": phase["front"].get("status", "todo"), "tasks": rows})
    return out


def _done(ids: list[str], status: dict[str, str]) -> bool:
    return all(status.get(i) == "done" for i in ids)


def roadmap_page(docs: list[dict], lang: str) -> str:
    t = T[lang]
    phases = roadmap_tasks(docs, lang)
    status = {task["id"]: task["status"] for p in phases for task in p["tasks"]}
    status.update({p["id"]: ("done" if p["tasks"] and all(x["status"] == "done" for x in p["tasks"]) else p["status"])
                   for p in phases})
    other = "en" if lang == "pl" else "pl"
    lines = [_head("generated-roadmap-status", lang, f"../../{other}/generated/roadmap-status.md"),
             f"# {t['roadmap_title']}\n", t["roadmap_intro"].format(f27="../roadmap/F2/F2.7-compile-domain.md") + "\n",
             t["phase_cols"], "|---|---|---|---|---|"]
    for p in phases:
        counts = {s: sum(1 for x in p["tasks"] if x["status"] == s) for s in ("done", "doing", "todo")}
        link = "../" + p["rel"].split("/", 1)[1]
        lines.append(f"| [{p['id']}]({link}) | {len(p['tasks'])} | {counts['done']} | {counts['doing']} | {counts['todo']} |")
    for p in phases:
        lines += ["", f"## {p['id']}. {p['title']}", "", t["task_cols"], "|---|---|---|---|---|"]
        for x in p["tasks"]:
            link = "../" + x["rel"].split("/", 1)[1]
            label = t["status"].get(x["status"], x["status"])
            if x["from_phase_doc"]:
                label += f" ({t['from_phase_doc']})"
            waits = [] if x["status"] == "done" else [d for d in x["depends_on"] if status.get(d) != "done"]
            lines.append(f"| [{x['id']}]({link}) | {_cell(x['title'])} | {label} | "
                         f"{', '.join(x['depends_on']) or t['dash']} | {', '.join(waits) or t['dash']} |")
    return "\n".join(lines) + "\n"


def _experiments(conn) -> list[dict]:
    """One row per slug with the latest card version, if any, and the run count."""
    cards = conn.execute("""SELECT DISTINCT ON (slug) * FROM lab_hypotheses ORDER BY slug, version DESC""").fetchall()
    exps = conn.execute(
        """SELECT e.slug, e.hypothesis_slug, count(r.id) AS runs FROM experiments e
           LEFT JOIN exp_runs r ON r.experiment_id = e.id GROUP BY e.slug, e.hypothesis_slug ORDER BY e.slug""").fetchall()
    by_slug: dict[str, dict] = {c["slug"]: {"slug": c["slug"], "card": dict(c), "runs": 0} for c in cards}
    for e in exps:
        row = by_slug.setdefault(e["slug"], {"slug": e["slug"], "card": None, "runs": 0})
        row["runs"] += e["runs"]
    return [by_slug[k] for k in sorted(by_slug)]


def experiments_page(conn, lang: str) -> str:
    t = T[lang]
    other = "en" if lang == "pl" else "pl"
    lines = [_head("generated-experiments", lang, f"../../{other}/generated/experiments.md"),
             f"# {t['exp_title']}\n", t["exp_intro"] + "\n", t["exp_cols"], "|---|---|---|---|---|---|"]
    for e in _experiments(conn):
        c = e["card"]
        if c:
            state = t["states"][c["state"]] + (f", {t['violated']}" if c["violated"] else "")
            card = f"v{c['version']}"
            prereg = str(c["prereg_at"])[:10] if c["prereg_at"] else t["none"]
        else:
            state, card, prereg = t["dash"], t["no_card"], t["dash"]
        lines.append(f"| {e['slug']} | {card} | {state} | {prereg} | {e['runs']} | "
                     f"[{t['dossier_title']}](experiments/{e['slug']}.md) |")
    return "\n".join(lines) + "\n"


def dossier_page(conn, slug: str, lang: str, data_exists: bool) -> str:
    t = T[lang]
    other = "en" if lang == "pl" else "pl"
    lines = [_head(f"generated-dossier-{slug}", lang, f"../../../{other}/generated/experiments/{slug}.md"),
             f"# {t['dossier_title']}: {slug}\n", t["dossier_intro"].format(slug=slug) + "\n"]
    cards = conn.execute("SELECT * FROM lab_hypotheses WHERE slug = %s ORDER BY version", (slug,)).fetchall()
    lines += [f"## {t['card']}", ""]
    if cards:
        lines += [t["card_cols"], "|---|---|---|---|---|---|"]
        for c in cards:
            state = t["states"][c["state"]] + (f", {t['violated']}" if c["violated"] else "")
            lines.append(f"| {c['version']} | {state} | {t['yes'] if c['approved'] else t['no']} | "
                         f"`{c['content_sha256'][:16]}` | {str(c['prereg_at'])[:10] if c['prereg_at'] else t['dash']} | "
                         f"{'`' + c['prereg_sha256'][:16] + '`' if c['prereg_sha256'] else t['dash']} |")
        problems = [p for c in cards for p in (c["problems"] or [])]
        if problems:
            lines += ["", f"{t['problems']}:", ""] + [f"- {_cell(p)}" for p in problems]
    else:
        lines.append(t["no_card"] + ".")
    exp = conn.execute("SELECT id FROM experiments WHERE slug = %s", (slug,)).fetchone()
    if exp:
        configs = conn.execute("SELECT name, model, provider, variant FROM exp_configs WHERE experiment_id = %s "
                               "ORDER BY name", (exp["id"],)).fetchall()
        lines += ["", f"## {t['configs']}", "", t["config_cols"], "|---|---|---|---|"]
        lines += [f"| {c['name']} | {c['model'] or t['dash']} | {c['provider']} | {c['variant'] or t['dash']} |"
                  for c in configs]
        runs = conn.execute(
            """SELECT r.id, r.run_id, s.name AS sample, s.role, r.status, r.code_commit, r.prereg_hash,
                      (SELECT count(*) FROM exp_jobs j WHERE j.run_id = r.id) AS jobs
               FROM exp_runs r JOIN exp_samples s ON s.id = r.sample_id WHERE r.experiment_id = %s
               ORDER BY r.created_at""", (exp["id"],)).fetchall()
        lines += ["", f"## {t['runs']}", "", t["run_cols"], "|---|---|---|---|---|---|---|"]
        lines += [f"| {r['run_id']} | {r['sample']} | {r['role']} | {r['status']} | {r['jobs']} | "
                  f"{'`' + r['code_commit'][:8] + '`' if r['code_commit'] and r['code_commit'] != 'unknown' else t['dash']} | "
                  f"{'`' + r['prereg_hash'][:16] + '`' if r['prereg_hash'] else t['dash']} |" for r in runs]
        metrics = conn.execute(
            """SELECT m.* FROM exp_metrics m JOIN exp_runs r ON r.id = m.run_id WHERE r.experiment_id = %s
               ORDER BY m.result_id""", (exp["id"],)).fetchall()
        lines += ["", f"## {t['results']}", "", t["result_cols"], "|---|---|---|---|---|---|"]
        for m in metrics:
            ci = f"{_num(m['ci_low'], lang)} – {_num(m['ci_high'], lang)}" if m["ci_low"] is not None else t["dash"]
            lines.append(f"| `{m['result_id']}` | {m['metric']} | {_num(m['value'], lang)} | {ci} | "
                         f"{m['n'] if m['n'] is not None else t['dash']} | {m['method'] or t['dash']} |")
    decisions = conn.execute("SELECT * FROM lab_gate_decisions WHERE slug = %s ORDER BY key", (slug,)).fetchall()
    lines += ["", f"## {t['gates']}", ""]
    if decisions:
        lines += [t["gate_cols"], "|---|---|---|---|---|"]
        for d in decisions:
            reasons = "; ".join(_cell(r) for r in (d["reasons"] or [])) or t["dash"]
            lines.append(f"| {d['key'].rsplit('/', 1)[-1]} | {d['gate'] or t['dash']} | {d['decision'] or t['dash']} | "
                         f"{t['gate_status'][d['status']]} | {reasons} |")
    else:
        lines.append(t["none"].capitalize() + ".")
    lines += ["", f"## {t['data']}", ""]
    lines.append(t["data_text"].format(link=f"../../../data/{slug}/datapackage.json", slug=slug) if data_exists
                 else t["no_data"])
    return "\n".join(lines) + "\n"


def _write(path: Path, text: str) -> bool:
    """Write only when the content changed; True if it did."""
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return True


def compile_pages(conn, tenant: str, out: Path) -> dict:
    docs = current_documents(conn, tenant)
    written: list[str] = []
    kept: list[str] = []
    slugs = [e["slug"] for e in _experiments(conn)]
    for lang in ("pl", "en"):
        base = out / lang / "generated"
        pages = {base / "roadmap-status.md": roadmap_page(docs, lang),
                 base / "experiments.md": experiments_page(conn, lang)}
        for slug in slugs:
            pages[base / "experiments" / f"{slug}.md"] = dossier_page(
                conn, slug, lang, (out / "data" / slug / "datapackage.json").exists())
        for path, text in pages.items():
            (written if _write(path, text) else kept).append(str(path.relative_to(out)))
        expected = {p.resolve() for p in pages}
        for stale in sorted((base / "experiments").glob("*.md")) if (base / "experiments").is_dir() else []:
            if stale.resolve() not in expected and not stale.name.startswith("blind-"):
                stale.unlink()
                written.append(f"removed {stale.relative_to(out)}")
    return {"written": written, "unchanged": len(kept)}


def compile_module(tenant_id: str, since=None) -> None:
    """Entry for wiki_compiler.compile_all (domain 'dowody'); a no-op outside the lab (no LAB_OUT)."""
    out = os.environ.get("LAB_OUT", "").strip()
    if not out:
        print("[wiki_compiler] dowody: LAB_OUT is not set, not a lab deployment; skipped")
        return
    from exocortex.lab.db import connect

    with connect() as conn:
        result = compile_pages(conn, tenant_id, Path(out))
    print(f"[wiki_compiler] dowody: {len(result['written'])} page(s) changed, {result['unchanged']} unchanged")
