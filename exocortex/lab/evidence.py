# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Strength of evidence of a hypothesis and the checksum of its sources (roadmap task F8.1).

Used by two programs: the lab processor that drafts the applications
section (exocortex/lab/applications.py) and the lab site generator
(lab-site/build.py), which loads this file by its path. So it depends on
nothing but the standard library and PyYAML, and imports nothing from the
package.

Everything is read from the documents tree (``<docs>/{pl,en}/experiments/<slug>/``)
and the exported data (``<data>/<slug>/metrics.csv``):

- ``overview.md``: header fields ``status`` and ``stage``, and the text of
  the results section (the 7th H2 section, as in lab-site/model.py);
- ``hypothesis.md``: the card, if there is one;
- ``gate-*.md``: gate decisions; ``run-*.md``: run notes;
- ``metrics.csv``: result ids with their sample size ``n``.

The label comes from a rule, never from a model:

- no approved gate decision and no results: ``none``;
- results (a metric row or a run note with result ids) but no approved
  decision: ``preliminary``;
- the latest approved decision (``human_validated: true`` in both
  languages, the same decision in both) is GO and every criterion in its
  criteria table is met: ``confirmed`` on a sample of N;
- it is NO-GO and at least one criterion is not met: ``refuted`` on N;
- anything else (PIVOT, NOT-NOW, CLOSED, a decision against its own
  numbers, no criteria table): ``inconclusive``.

N is the smallest ``n`` among the results the decision names: a label
never claims more than the weakest result behind it. A named result
without ``n`` is a problem, and a draft is not made while there are
problems.

``source_hash`` is SHA-256 over a canonical JSON of every input above.
A change of a result, a decision, the card or those header fields changes
it, and the site then hides an approved section until a new draft is
approved.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ALGORITHM = "applications-v1"
LANGS = ("pl", "en")
# Position of the results section among the H2 sections of overview.md
# (lab-site/model.py SECTION_KEYS: abstract, question, prereg, data, method, runs, results, ...).
RESULTS_POSITION = 6
DECISIONS = ("GO", "NO-GO", "PIVOT", "NOT-NOW", "CLOSED")
CRITERIA_HEADINGS = ("kryteria z karty hipotezy (bez zmian)", "criteria from the hypothesis card (unchanged)")
MET_COLUMNS = ("spełnione", "met")
YES = ("tak", "yes", "true")
NO = ("nie", "no", "false")

KEYS = ("none", "preliminary", "confirmed", "refuted", "inconclusive")
LABELS = {
    "pl": {"none": "hipoteza, bez dowodu", "preliminary": "wstępne", "confirmed": "potwierdzone na próbie {n}",
           "refuted": "obalone na próbie {n}", "inconclusive": "nierozstrzygnięte"},
    "en": {"none": "hypothesis, no evidence", "preliminary": "preliminary", "confirmed": "confirmed on a sample of {n}",
           "refuted": "refuted on a sample of {n}", "inconclusive": "inconclusive"},
}

_FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_H2 = re.compile(r"^## (.+)$", re.MULTILINE)
_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)


def canonical(text: str) -> str:
    """Unicode NFC, ``\\n`` line ends, no trailing spaces, no blank lines at either end."""
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip(" \t") for line in text.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def split_front(text: str) -> tuple[dict, str]:
    m = _FRONT.match(text)
    if not m:
        return {}, text
    try:
        front = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}, text[m.end():]
    return (front if isinstance(front, dict) else {}), text[m.end():]


def results_section(body: str) -> str:
    parts = _H2.split(body)
    sections = [parts[i + 1] for i in range(1, len(parts) - 1, 2)]
    return canonical(sections[RESULTS_POSITION]) if len(sections) > RESULTS_POSITION else ""


def _read(path: Path) -> str | None:
    return canonical(path.read_text(encoding="utf-8")) if path.is_file() else None


def _pairs(docs: Path, slug: str, pattern: str) -> dict[str, dict[str, str | None]]:
    names = sorted({p.name for lang in LANGS for p in (docs / lang / "experiments" / slug).glob(pattern)})
    return {n: {lang: _read(docs / lang / "experiments" / slug / n) for lang in LANGS} for n in names}


def collect(docs: Path, slug: str, data: Path | None = None) -> dict:
    """Every input of the label and the checksum, as plain JSON-able data."""
    data = data if data is not None else docs / "data"
    overview: dict[str, dict[str, str] | None] = {}
    for lang in LANGS:
        text = _read(docs / lang / "experiments" / slug / "overview.md")
        if text is None:
            overview[lang] = None
            continue
        front, body = split_front(text + "\n")
        overview[lang] = {"status": str(front.get("status", "")), "stage": str(front.get("stage", "")),
                          "results": results_section(body)}
    metrics = data / slug / "metrics.csv"
    return {
        "algorithm": ALGORITHM,
        "slug": slug,
        "overview": overview,
        "card": {lang: _read(docs / lang / "experiments" / slug / "hypothesis.md") for lang in LANGS},
        "gates": _pairs(docs, slug, "gate-*.md"),
        "runs": _pairs(docs, slug, "run-*.md"),
        "metrics": _read(metrics) or "",
    }


def source_hash(inputs: dict) -> str:
    payload = json.dumps(inputs, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def metric_rows(inputs: dict) -> list[dict]:
    text = inputs.get("metrics") or ""
    return list(csv.DictReader(io.StringIO(text))) if text else []


def _criteria_met(body: str) -> list[bool | None]:
    """The 'met' column of the criteria table: True, False or None (unreadable) per row."""
    marks = list(_HEADING.finditer(body))
    for i, m in enumerate(marks):
        if m.group(1).strip().lower() not in CRITERIA_HEADINGS:
            continue
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        rows = [[c.strip() for c in line.strip().strip("|").split("|")]
                for line in body[m.end():end].splitlines() if line.strip().startswith("|")]
        rows = [r for r in rows if not all(re.fullmatch(r":?-{3,}:?", c) for c in r if c)]
        if not rows:
            return []
        header = [h.lower() for h in rows[0]]
        col = next((i for i, h in enumerate(header) if h in MET_COLUMNS), None)
        if col is None:
            return [None for _ in rows[1:]]
        out = []
        for r in rows[1:]:
            value = r[col].strip().lower() if col < len(r) else ""
            out.append(True if value in YES else False if value in NO else None)
        return out
    return []


@dataclass
class Evidence:
    key: str
    n: int | None = None
    decision: dict | None = None
    problems: list[str] = field(default_factory=list)

    def label(self, lang: str) -> str:
        return LABELS[lang][self.key].format(n=self.n)


def _approved_decisions(inputs: dict) -> tuple[list[dict], list[str]]:
    out, problems = [], []
    for name, by_lang in sorted(inputs["gates"].items()):
        fronts = {}
        for lang in LANGS:
            if by_lang.get(lang) is None:
                continue
            fronts[lang] = split_front(by_lang[lang] + "\n")
        if set(fronts) != set(LANGS):
            continue  # one language only: not a decision anybody approved in both
        pl, en = fronts["pl"][0], fronts["en"][0]
        if not (pl.get("human_validated") is True and en.get("human_validated") is True):
            continue
        if pl.get("decision") != en.get("decision") or pl.get("decision") not in DECISIONS:
            problems.append(f"{name}: the decision differs between languages or is not one of {', '.join(DECISIONS)}")
            continue
        met = {lang: _criteria_met(fronts[lang][1]) for lang in LANGS}
        if met["pl"] != met["en"]:
            problems.append(f"{name}: the criteria tables differ between languages")
        out.append({"file": name, "gate": str(pl.get("gate") or ""), "decision": pl["decision"],
                    "date": str(pl.get("date") or ""), "result_ids": [str(r) for r in pl.get("result_ids") or []],
                    "met": met["pl"]})
    out.sort(key=lambda d: (d["date"], d["gate"], d["file"]))
    return out, problems


def _has_results(inputs: dict) -> bool:
    if metric_rows(inputs):
        return True
    for by_lang in inputs["runs"].values():
        for text in by_lang.values():
            if text and split_front(text + "\n")[0].get("result_ids"):
                return True
    return False


def evidence(inputs: dict) -> Evidence:
    """The label of a hypothesis from its inputs (see the module docstring)."""
    decisions, problems = _approved_decisions(inputs)
    if not decisions:
        return Evidence("preliminary" if _has_results(inputs) else "none", problems=problems)
    last = decisions[-1]
    met = last["met"]
    if last["decision"] == "GO" and met and all(m is True for m in met):
        key = "confirmed"
    elif last["decision"] == "NO-GO" and any(m is False for m in met):
        key = "refuted"
    else:
        key = "inconclusive"
    n = None
    if key in ("confirmed", "refuted"):
        sizes = {r.get("result_id"): r.get("n") for r in metric_rows(inputs)}
        found = []
        if not last["result_ids"]:
            problems.append(f"{last['file']}: the decision names no result ids, so the sample size is unknown")
        for rid in last["result_ids"]:
            raw = (sizes.get(rid) or "").strip()
            if rid not in sizes:
                problems.append(f"{last['file']}: result id {rid!r} is not in metrics.csv")
            elif not raw.isdigit():
                problems.append(f"{last['file']}: result id {rid!r} has no sample size n")
            else:
                found.append(int(raw))
        n = min(found) if found else None
        if n is None:
            key = "inconclusive"
    return Evidence(key, n, last, problems)


def status(inputs: dict) -> str:
    """The dossier status (planned, preparation, running, decided), from the Polish or English header."""
    for lang in LANGS:
        if inputs["overview"].get(lang):
            return inputs["overview"][lang]["status"]
    return ""


def needs_scenarios(inputs: dict, ev: Evidence) -> bool:
    """'If we confirm, if we refute' belongs to planned and prepared hypotheses, and to any without evidence."""
    return status(inputs) in ("planned", "preparation") or ev.key == "none"


def assess(docs: Path, slug: str, data: Path | None = None) -> tuple[dict, str, Evidence]:
    """(inputs, source_hash, evidence) of one dossier."""
    inputs = collect(docs, slug, data)
    return inputs, source_hash(inputs), evidence(inputs)
