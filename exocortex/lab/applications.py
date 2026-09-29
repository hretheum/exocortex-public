# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Business applications section of a hypothesis page (roadmap task F8.1).

``draft`` composes ``{pl,en}/experiments/<slug>/applications.md`` from three
inputs: the dossier (question, method, results, gate decisions,
limitations), the catalogue of general kinds of applications
(lab/applications-catalogue.yaml) and, for a hypothesis without a result,
both outcomes. The model writes only text, through the lab's model gateway
and only with a model listed in lab/models.yaml. The strength of evidence
comes from a rule (exocortex/lab/evidence.py) and is written into the file
by this code, as is the checksum of the sources.

A draft has ``publish: false`` and ``human_validated: false`` in its header,
so the publisher leaves it in the vault. The owner approves it by setting
``publish: true`` and ``human_validated: true`` in both language versions;
this code never does. Both fields stay in the header: ``check`` requires
them, and an approved file with ``publish: false`` is a problem. A changed
result changes ``source_hash``, and the site then shows "being updated"
instead of the section until a new draft is approved.

``check`` rejects a draft when a table row has no reference to a result of
the dossier, the label is not the computed one, the text has a number that
is not among the dossier's results, a name from the gate's denylist, an
amount, a currency or a promise of profit, the Polish and English versions
are not a pair, or the text fails the language check (tools/humanlint) or
the header checks (tools/docschema and the fields below). Messages name
the rule and the line, never the matched text of a name.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from exocortex.lab import evidence
from exocortex.lab.evidence import LANGS, Evidence

FILE = "applications.md"
TYPE = "applications"
RESULTS_ANCHOR = "overview.md#s-results"
HEADER_FIELDS = ("id", "lang", "counterpart", "type", "slug", "label", "source_hash", "publish", "human_validated")
SECTION_LIMIT = 3000  # characters of one dossier section given to the model

T = {
    "pl": {"title": "Zastosowania biznesowe", "applications": "Zastosowania",
           "cols": ("Zastosowanie", "Kto korzysta", "Wynik, na którym się opiera", "Siła dowodu", "Warunki i granice"),
           "scenarios": "Jeśli potwierdzimy, jeśli obalimy", "if_confirmed": "Jeśli potwierdzimy",
           "if_refuted": "Jeśli obalimy", "limits": "Czego z tego nie wolno wyciągać", "next": "Co sprawdzić dalej",
           "results": "wyniki w dossier"},
    "en": {"title": "Business applications", "applications": "Applications",
           "cols": ("Application", "Who uses it", "Result it rests on", "Strength of evidence", "Conditions and limits"),
           "scenarios": "If we confirm, if we refute", "if_confirmed": "If we confirm",
           "if_refuted": "If we refute", "limits": "What not to conclude from this", "next": "What to check next",
           "results": "results in the dossier"},
}

# Words that name money or promise gain. Both lists apply to both languages:
# a draft must not carry either, whatever language it is in.
MONEY = {
    "currency": [r"[$€£¥]", r"\b(?:PLN|USD|EUR|GBP|CHF|JPY)\b", r"\bzł\b", r"\bzłot(?:y|ych|e|ówek|ówki)\b",
                 r"\bgrosz(?:y|e)?\b", r"\bdolar(?:a|ów|y|ach)?\b", r"\bdollars?\b", r"\beuro\b",
                 r"\bpounds? sterling\b"],
    "amount": [r"\d+(?:[.,]\d+)?\s?(?:k|tys\.?|mln|mld|thousand|million|billion|bn)(?!\w)"],
    "profit": [r"\bzysk\w*", r"\bzarob\w*", r"\bzaoszczędz\w*", r"\bprzych(?:ód|od\w*)", r"\brentown\w*",
               r"\bmarż\w*", r"\bzwrot\w* z inwestycji", r"\bROI\b", r"\bgwarantowan\w*", r"\bprofit\w*",
               r"\brevenue\w*", r"\bearn(?:s|ed|ing|ings)?\b", r"\breturn on investment\b", r"\bguaranteed\b",
               r"\bcost savings?\b", r"\bsave(?:s)? (?:you|your|money)\b", r"\bboost\w* (?:sales|revenue)\b"],
}
_MONEY = {rule: [re.compile(p, re.IGNORECASE) for p in patterns] for rule, patterns in MONEY.items()}

# Polish terms that carry the English term in brackets at their first use in a document
# (dowody/glossary.md, row "osadzenia / embeddings"). Every inflected form counts.
GLOSSES = {"osadzenia": (r"osadze(?:nie|nia|niu|niem|ń|niom|niami|niach)", "embeddings")}
_GLOSS_TERMS = {term: re.compile(rf"(?<!\w){forms}(?!\w)", re.IGNORECASE) for term, (forms, _) in GLOSSES.items()}
_FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_CODE = re.compile(r"`[^`\n]*`")
_LINK = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)\s]+)\)")
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_LIST_MARK = re.compile(r"^(\s*)\d+[.)](?=\s)", re.MULTILINE)
_NUMBER = re.compile(r"(?<![\w@.,/-])(\d+(?:[.,]\d+)?)(\s?%)?(?![\w@])")
_H2 = re.compile(r"^## (.+?)\s*$", re.MULTILINE)


# ------------------------------------------------------------------ inputs ----
def catalogue(path: Path | None = None) -> list[dict]:
    from exocortex.lab.claims import repo_path

    path = path or repo_path("lab/applications-catalogue.yaml")
    return yaml.safe_load(path.read_text(encoding="utf-8"))["kinds"]


def allowed_models(path: Path | None = None) -> set[str]:
    from exocortex.lab.claims import repo_path

    path = path or repo_path("lab/models.yaml")
    return {m["id"] for m in yaml.safe_load(path.read_text(encoding="utf-8"))["models"]}


def references(inputs: dict) -> dict[str, dict[str, str]]:
    """Every dossier item a row may rest on: {ref id: {lang: Markdown for the table cell}}."""
    out = {"results-section": {lang: f"[{T[lang]['results']}]({RESULTS_ANCHOR})" for lang in LANGS}}
    for kind, items in (("gate", inputs["gates"]), ("run", inputs["runs"])):
        for name, by_lang in items.items():
            if all(by_lang.get(lang) for lang in LANGS):
                out[f"{kind}:{name}"] = {lang: f"[{name.removesuffix('.md')}]({name})" for lang in LANGS}
    for row in evidence.metric_rows(inputs):
        rid = row.get("result_id")
        if rid:
            out[f"result:{rid}"] = {lang: f"`{rid}`" for lang in LANGS}
    return out


def _sections(text: str | None) -> tuple[str, str, list[str]]:
    """(title, tagline, sections in order) of an overview."""
    if not text:
        return "", "", []
    front, body = evidence.split_front(text + "\n")
    m = re.search(r"^# (.+)$", body, re.MULTILINE)
    parts = _H2.split(body)
    return (m.group(1).strip() if m else "", str(front.get("tagline", "")),
            [parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)])


def dossier_brief(docs: Path, slug: str, inputs: dict, ev: Evidence) -> dict:
    """What the model sees of the dossier: short texts in both languages, results, decisions, the label."""
    brief: dict = {"slug": slug, "status": evidence.status(inputs),
                   "strength_of_evidence": {lang: ev.label(lang) for lang in LANGS}}
    for lang in LANGS:
        path = docs / lang / "experiments" / slug / "overview.md"
        title, tagline, secs = _sections(path.read_text(encoding="utf-8") if path.is_file() else None)
        pick = {"question": 1, "method": 4, "results": 6, "limitations": 10}
        brief[lang] = {"title": title, "tagline": tagline,
                       **{k: (secs[i][:SECTION_LIMIT] if i < len(secs) else "") for k, i in pick.items()}}
    brief["gate_decisions"] = []
    for name, by in inputs["gates"].items():
        front = evidence.split_front((by.get("pl") or "") + "\n")[0]
        brief["gate_decisions"].append({"file": name, "gate": front.get("gate"), "decision": front.get("decision"),
                                        "approved": front.get("human_validated") is True})
    brief["results"] = [{k: r.get(k) for k in ("result_id", "metric", "value", "ci_low", "ci_high", "n")}
                        for r in evidence.metric_rows(inputs)]
    return brief


# ------------------------------------------------------------------ model -----
SYSTEM = """You write the section "business applications" of a hypothesis page of a public research lab, \
in Polish and in English with the same meaning. The readers decide about tools and products in \
organisations; they are not researchers.

Rules:
- Use only what the dossier says. Never guess a result.
- Numbers: only those that appear in the dossier's results. If there are no results, write no numbers at all.
- No amounts of money, no currencies, no budgets, no promises of profit, revenue, savings or return. \
No names of companies, clients or people.
- The strength of evidence is fixed by the lab and given in the dossier. Never describe the evidence as \
stronger than that.
- A negative result is useful: say plainly what it tells an organisation not to invest in.
- If the hypothesis has no result yet, say what to do if it is confirmed and what to do if it is refuted, \
without guessing which will happen.
- Every application names one kind from the catalogue and the dossier item it rests on.
- Plain, short sentences. No marketing language, no bold text, no dashes as punctuation, no emoji.
- In the Polish text, put "(ang. embeddings)" right after the first form of the word "osadzenia" \
(any inflected form, for example osadzeń), counting the fields in this order: sentence, rows, \
scenarios, limits, next. Later uses need no gloss. The English text needs no gloss.
- Every text field has a Polish ("pl") and an English ("en") version that say the same thing."""


def _both() -> dict:
    return {"type": "object", "additionalProperties": False, "required": ["pl", "en"],
            "properties": {"pl": {"type": "string", "minLength": 1}, "en": {"type": "string", "minLength": 1}}}


def output_schema(kinds: list[str], refs: list[str], scenarios: bool) -> dict:
    props = {
        "sentence": _both(),
        "rows": {"type": "array", "minItems": 1, "maxItems": 5, "items": {
            "type": "object", "additionalProperties": False,
            "required": ["kind", "result", "application", "who", "conditions"],
            "properties": {"kind": {"type": "string", "enum": kinds}, "result": {"type": "string", "enum": refs},
                           "application": _both(), "who": _both(), "conditions": _both()}}},
        "limits": {"type": "array", "minItems": 1, "maxItems": 4, "items": _both()},
        "next": {"type": "array", "minItems": 1, "maxItems": 3, "items": _both()},
    }
    if scenarios:
        props["scenarios"] = {"type": "object", "additionalProperties": False,
                              "required": ["if_confirmed", "if_refuted"],
                              "properties": {"if_confirmed": _both(), "if_refuted": _both()}}
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


def prompt(brief: dict, kinds: list[dict], refs: dict[str, dict[str, str]], scenarios: bool,
           feedback: list[str] | None = None) -> str:
    parts = [
        "Dossier (JSON):", json.dumps(brief, ensure_ascii=False, indent=1),
        "Catalogue of kinds of applications (field \"kind\" is the id):",
        json.dumps([{"id": k["id"], "pl": k["pl"], "en": k["en"]} for k in kinds], ensure_ascii=False, indent=1),
        "Dossier items a row may rest on (field \"result\"): " + ", ".join(refs),
        "Write:",
        "- sentence: one sentence on what this hypothesis changes for an organisation;",
        "- rows: one to five applications, each with who uses it and its conditions and limits;",
        "- limits: what must not be concluded from this, in plain words;",
        "- next: what to check next.",
    ]
    if scenarios:
        parts.append("- scenarios: what to do if the hypothesis is confirmed and what to do if it is refuted.")
    if feedback:
        parts += ["The previous draft was rejected for these reasons; avoid them:", *[f"- {f}" for f in feedback]]
    return "\n".join(parts)


# ------------------------------------------------------------------ render ----
def _cell(text: str) -> str:
    return " ".join(str(text).replace("|", "/").split()) or "—"


def render(slug: str, lang: str, out: dict, kinds: list[dict], refs: dict[str, dict[str, str]], ev: Evidence,
           digest: str, title: str, agent: str, today: dt.date) -> str:
    t = T[lang]
    other = "en" if lang == "pl" else "pl"
    names = {k["id"]: k[lang]["name"] for k in kinds}
    front = {"id": f"{slug}-applications", "lang": lang,
             "counterpart": f"../../../{other}/experiments/{slug}/{FILE}", "type": TYPE, "slug": slug,
             "label": ev.label(lang), "source_hash": digest, "publish": False, "human_validated": False,
             "provenance": "ai_authored", "provenance_metadata": {"agent": agent, "date": today.isoformat()}}
    head = yaml.safe_dump(front, allow_unicode=True, sort_keys=False, width=1000)
    lines = [f"---\n{head}---", "", f"# {t['title']}: {gloss_first(title) if lang == 'pl' else title}" if title else f"# {t['title']}", "",
             out["sentence"][lang].strip(), "", f"## {t['applications']}", "",
             "| " + " | ".join(t["cols"]) + " |", "|---|---|---|---|---|"]
    for r in out["rows"]:
        name = names.get(r["kind"], r["kind"])
        lines.append(f"| {_cell(name.capitalize() + ': ' + r['application'][lang])} | {_cell(r['who'][lang])} | "
                     f"{refs[r['result']][lang]} | {ev.label(lang)} | {_cell(r['conditions'][lang])} |")
    if "scenarios" in out:
        s = out["scenarios"]
        lines += ["", f"## {t['scenarios']}", "", f"- {t['if_confirmed']}: {s['if_confirmed'][lang].strip()}",
                  f"- {t['if_refuted']}: {s['if_refuted'][lang].strip()}"]
    lines += ["", f"## {t['limits']}", ""] + [f"- {x[lang].strip()}" for x in out["limits"]]
    lines += ["", f"## {t['next']}", ""] + [f"- {x[lang].strip()}" for x in out["next"]]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ check -----
@dataclass
class Report:
    problems: list[str] = field(default_factory=list)
    not_run: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def _front(text: str) -> tuple[dict, str]:
    m = _FRONT.match(text)
    if not m:
        return {}, text
    try:
        front = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}, text[m.end():]
    return (front if isinstance(front, dict) else {}), text[m.end():]


def _plain(body: str) -> str:
    """Body text where numbers are counted: no code spans, link targets, dates or list markers."""
    body = _CODE.sub(" ", body)
    body = _LINK.sub(lambda m: m.group(1), body)
    body = _DATE.sub(" ", body)
    return _LIST_MARK.sub(r"\1", body)


def numbers_in(text: str) -> list[tuple[str, bool]]:
    """(number as written, followed by %) for every stand-alone number in ``text``."""
    return [(m.group(1), bool(m.group(2))) for m in _NUMBER.finditer(text)]


def allowed_numbers(inputs: dict, ev: Evidence) -> list[float]:
    """Numbers of the dossier's results: metrics.csv, the results sections, gate decisions and run notes."""
    out: list[float] = []
    for r in evidence.metric_rows(inputs):
        for k in ("value", "ci_low", "ci_high", "n"):
            try:
                out.append(float(r.get(k) or ""))
            except ValueError:
                pass
    texts = [o["results"] for o in inputs["overview"].values() if o]
    texts += [t for items in (inputs["gates"], inputs["runs"]) for by in items.values() for t in by.values() if t]
    for text in texts:
        out += [float(n.replace(",", ".")) for n, _ in numbers_in(_plain(evidence.split_front(text + "\n")[1]))]
    if ev.n is not None:
        out.append(float(ev.n))
    return out


def number_allowed(written: str, percent: bool, allowed: list[float]) -> bool:
    value = float(written.replace(",", "."))
    decimals = len(re.split(r"[.,]", written)[1]) if re.search(r"[.,]", written) else 0
    for a in allowed:
        for c in ((a, a * 100) if percent else (a,)):
            if decimals == 0 and not percent and abs(c - round(c)) > 1e-9:
                continue  # an integer in the text does not stand for a rounded fraction
            if abs(round(c, decimals) - value) < 1e-9:
                return True
    return False


def _lines(body: str, offset: int) -> list[tuple[int, str]]:
    return [(offset + i, line) for i, line in enumerate(body.split("\n"), start=1)]


def _table_rows(body: str, lang: str) -> tuple[list[list[str]] | None, list[str]]:
    """Data rows of the applications table (None if there is no such table), and problems of its header."""
    t = T[lang]
    m = re.search(rf"^## {re.escape(t['applications'])}\s*$", body, re.MULTILINE)
    if not m:
        return None, []
    rest = body[m.end():]
    nxt = re.search(r"^## ", rest, re.MULTILINE)
    rows = [[c.strip() for c in line.strip().strip("|").split("|")]
            for line in (rest[:nxt.start()] if nxt else rest).splitlines() if line.strip().startswith("|")]
    rows = [r for r in rows if not all(re.fullmatch(r":?-{3,}:?", c) for c in r if c)]
    if not rows:
        return None, []
    problems = [] if tuple(rows[0]) == t["cols"] else [f"{lang}: the table columns are not: {' | '.join(t['cols'])}"]
    return rows[1:], problems


def row_reference(cell: str, lang: str, refs: dict[str, dict[str, str]]) -> str | None:
    """The reference id a result cell names, if it names exactly a dossier item."""
    for rid, by_lang in refs.items():
        if cell.strip() == by_lang[lang]:
            return rid
    return None


def _unglossed(text: str, term: str, en: str):
    """The first use of ``term`` in ``text`` (code spans skipped) if no "(ang. <en>)" follows it, else None."""
    m = _GLOSS_TERMS[term].search(_CODE.sub(lambda c: " " * len(c.group(0)), text))
    if m and not re.match(rf"\s*\(ang\.\s*{re.escape(en)}\)", text[m.end():]):
        return m
    return None


def missing_glosses(body: str) -> list[tuple[str, str]]:
    """(term, English term) for every glossed term whose first use in ``body`` has no "(ang. ...)" after it."""
    return [(term, en) for term, (_, en) in GLOSSES.items() if _unglossed(body, term, en)]


def gloss_first(text: str) -> str:
    """``text`` with "(ang. ...)" after the first use of each glossed term that lacks it."""
    for term, (_, en) in GLOSSES.items():
        if m := _unglossed(text, term, en):
            text = f"{text[:m.end()]} (ang. {en}){text[m.end():]}"
    return text


def check_money(body: str, offset: int) -> list[str]:
    out = []
    for no, line in _lines(_CODE.sub(" ", body), offset):
        for rule, patterns in _MONEY.items():
            if any(p.search(line) for p in patterns):
                out.append(f"line {no}: {rule}")
    return out


def name_scanner():
    """The gate's literal scanner with its denylist (needs the HMAC key), or (None, reason)."""
    from exocortex.lab.headers import _import_tools, _tools_root

    try:
        _import_tools("leakgate/scan.py")
        from tools.leakgate.denylist import Denylist, load_key
        from tools.leakgate.scan import Config, Scanner

        key = load_key()
        deny = Denylist.load(_tools_root("leakgate/scan.py") / "tools/leakgate/data/denylist.hmac.json", key)
        return Scanner(deny, Config.load()), None
    except Exception as exc:  # noqa: BLE001 - any failure means the names were not checked
        return None, f"names: not checked ({type(exc).__name__}: the gate's scanner or its HMAC key is missing)"


def check_texts(slug: str, texts: dict[str, str], inputs: dict, digest: str, ev: Evidence, *,
                scanner=None, scanner_missing: str | None = None, require_all: bool = True) -> Report:
    """Every rule of the module docstring on one Polish and English pair of texts."""
    rep = Report()
    rep.problems += [f"evidence: {p}" for p in ev.problems]
    refs = references(inputs)
    allowed = allowed_numbers(inputs, ev)
    fronts, bodies, row_refs = {}, {}, {}
    for lang in LANGS:
        text = texts.get(lang)
        if text is None:
            rep.problems.append(f"{lang}: missing")
            continue
        front, body = _front(text)
        fronts[lang], bodies[lang] = front, body
        offset = text[: len(text) - len(body)].count("\n")
        t = T[lang]
        for f in HEADER_FIELDS:
            if f not in front:
                rep.problems.append(f"{lang}: header field {f} is missing")
        if front.get("type") != TYPE or front.get("slug") != slug or front.get("lang") != lang:
            rep.problems.append(f"{lang}: header type, slug or lang is wrong")
        if front.get("label") != ev.label(lang):
            rep.problems.append(f"{lang}: label {front.get('label')!r} is not the computed {ev.label(lang)!r}")
        if front.get("source_hash") != digest:
            rep.problems.append(f"{lang}: source_hash is not the checksum of the current dossier (results changed)")
        if not isinstance(front.get("publish"), bool) or not isinstance(front.get("human_validated"), bool):
            rep.problems.append(f"{lang}: publish and human_validated must be true or false")
        elif front.get("human_validated") is not front.get("publish"):
            rep.problems.append(f"{lang}: approval needs both publish: true and human_validated: true")
        heads = [h.strip() for h in _H2.findall(body)]
        wanted = [t["applications"]] + ([t["scenarios"]] if evidence.needs_scenarios(inputs, ev) else []) + [
            t["limits"], t["next"]]
        if heads != wanted:
            rep.problems.append(f"{lang}: sections are {heads}, expected {wanted}")
        rows, problems = _table_rows(body, lang)
        rep.problems += problems
        if not rows:
            rep.problems.append(f"{lang}: the applications table has no rows")
        row_refs[lang] = []
        for i, row in enumerate(rows or [], start=1):
            if len(row) != 5:
                rep.problems.append(f"{lang}: row {i} has {len(row)} cells, expected 5")
                row_refs[lang].append(None)
                continue
            ref = row_reference(row[2], lang, refs)
            row_refs[lang].append(ref)
            if ref is None:
                rep.problems.append(f"{lang}: row {i} does not refer to a result of the dossier")
            if row[3] != ev.label(lang):
                rep.problems.append(f"{lang}: row {i} strength {row[3]!r} is not the computed {ev.label(lang)!r}")
        for no, line in _lines(_plain(body), offset):
            for written, pct in numbers_in(line):
                if not number_allowed(written, pct, allowed):
                    rep.problems.append(f"{lang}: line {no}: number {written}{'%' if pct else ''} "
                                        "is not among the dossier's results")
        rep.problems += [f"{lang}: {p}" for p in check_money(body, offset)]
        if lang == "pl":
            rep.problems += [f"pl: {term} bez glosy (ang. {en}) przy pierwszym użyciu" for term, en in missing_glosses(body)]
        rel = f"{lang}/experiments/{slug}/{FILE}"
        if scanner is not None:
            for f in scanner.scan_text(rel, text):
                if f.rule == "denylist" or f.tier == "block":
                    rep.problems.append(f"{lang}: line {f.line}: name or personal data (leakgate rule {f.rule})")
        rep.problems += _tool_checks(rel, text, rep, require_all)
    if scanner is None:
        missing = scanner_missing or "names: not checked (no scanner)"
        (rep.problems if require_all else rep.not_run).append(missing)
    if set(fronts) == set(LANGS):
        for f in ("slug", "source_hash", "id"):
            if fronts["pl"].get(f) != fronts["en"].get(f):
                rep.problems.append(f"pair: {f} differs between the Polish and English versions")
        if row_refs.get("pl") != row_refs.get("en"):
            rep.problems.append("pair: the rows do not rest on the same results in the same order")
        rep.problems += _parity(slug, texts, rep, require_all)
    rep.not_run = sorted(set(rep.not_run))
    return rep


def _tool_checks(rel: str, text: str, rep: Report, require_all: bool) -> list[str]:
    """Header schemas (tools/docschema) and the language check (tools/humanlint)."""
    from exocortex.lab.headers import _import_tools, _tools_root, validate

    out = [f"docschema: {p}" for p in validate(rel, text)]
    if _tools_root("humanlint/core.py") is None:
        (out if require_all else rep.not_run).append("humanlint: not run (tools/humanlint is not here)")
        return out
    _import_tools("humanlint/core.py")
    from tools.humanlint.core import (
        analyse,
        front_exception,
        load_config,
        load_patterns,
    )

    report = analyse(Path(rel), text, load_patterns(), load_config())
    if report.failures and not front_exception(text):
        out += [f"humanlint: {rel}: {f}" for f in report.failures]
    return out


def _parity(slug: str, texts: dict[str, str], rep: Report, require_all: bool) -> list[str]:
    """The gate's structural pair check (tools/paritycheck): headings, numbers, links, table shapes."""
    from exocortex.lab.headers import _import_tools, _tools_root

    if _tools_root("paritycheck/core.py") is None:
        (rep.problems if require_all else rep.not_run).append("pair: tools/paritycheck is not here")
        return []
    _import_tools("paritycheck/core.py")
    from tools.paritycheck.core import compare, parse

    rel = f"experiments/{slug}/{FILE}"
    return [f"pair: {p.check}: {p.detail}" for p in compare(rel, parse(texts["pl"]), parse(texts["en"]), "pl", "en")]


def read_pair(docs: Path, slug: str) -> dict[str, str]:
    return {lang: p.read_text(encoding="utf-8") for lang in LANGS
            if (p := docs / lang / "experiments" / slug / FILE).is_file()}


def check(docs: Path, slug: str, data: Path | None = None, scanner=None, scanner_missing: str | None = None,
          require_all: bool = True) -> Report:
    inputs, digest, ev = evidence.assess(docs, slug, data)
    return check_texts(slug, read_pair(docs, slug), inputs, digest, ev, scanner=scanner,
                       scanner_missing=scanner_missing, require_all=require_all)


# ------------------------------------------------------------------ draft -----
def draft(docs: Path, slug: str, llm, *, data: Path | None = None, out: Path | None = None,
          model: str = "qwen3.6-35b-a3b", attempts: int = 2, force: bool = False, scanner=None,
          scanner_missing: str | None = None, kinds: list[dict] | None = None, models: set[str] | None = None,
          today: dt.date | None = None) -> dict:
    """Draft the pair for ``slug`` and write it under ``out`` (default: ``docs``) if it passes the checks."""
    out = out or docs
    report: dict = {"slug": slug, "model": model}
    if model not in (models if models is not None else allowed_models()):
        return {**report, "refused": f"model {model!r} is not in lab/models.yaml"}
    if not all((docs / lang / "experiments" / slug / "overview.md").is_file() for lang in LANGS):
        return {**report, "refused": "the dossier needs overview.md in both languages"}
    inputs, digest, ev = evidence.assess(docs, slug, data)
    report.update(source_hash=digest, label={lang: ev.label(lang) for lang in LANGS})
    if ev.problems:
        return {**report, "refused": "the label cannot be computed", "problems": ev.problems}
    current = read_pair(out, slug)
    if current and not force:
        front = _front(current.get("pl", ""))[0]
        if front.get("source_hash") == digest:
            state = "approved" if front.get("human_validated") is True else "draft"
            return {**report, "skipped": f"the {state} section is current"}
    kinds = kinds if kinds is not None else catalogue()
    refs = references(inputs)
    scenarios = evidence.needs_scenarios(inputs, ev)
    schema = output_schema([k["id"] for k in kinds], list(refs), scenarios)
    brief = dossier_brief(docs, slug, inputs, ev)
    titles = {lang: brief[lang]["title"] for lang in LANGS}
    today = today or dt.datetime.now(dt.UTC).date()
    feedback: list[str] = []
    for attempt in range(1, attempts + 1):
        call = llm.structured(model=model, system=SYSTEM, user=prompt(brief, kinds, refs, scenarios, feedback),
                              schema=schema, name="applications", max_tokens=4096)
        report["attempts"] = attempt
        if not call.ok:
            feedback = [f"the reply was not valid: {call.error}"]
            report["problems"] = feedback
            continue
        shape = _shape_problems(call.output, schema)
        if shape:
            feedback, report["problems"] = shape, shape
            continue
        agent = f"{model} (lab model gateway), exocortex lab applications"
        texts = {lang: render(slug, lang, call.output, kinds, refs, ev, digest, titles[lang], agent, today)
                 for lang in LANGS}
        rep = check_texts(slug, texts, inputs, digest, ev, scanner=scanner, scanner_missing=scanner_missing,
                          require_all=False)
        report["problems"], report["not_run"] = rep.problems, rep.not_run
        if rep.ok:
            written = []
            for lang in LANGS:
                path = out / lang / "experiments" / slug / FILE
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(texts[lang], encoding="utf-8")
                written.append(str(path.relative_to(out)))
            return {**report, "written": written}
        feedback = rep.problems
    return {**report, "refused": "no draft passed the checks"}


def _shape_problems(obj: dict, schema: dict) -> list[str]:
    """The model's object against the schema, in case the server did not enforce it."""
    from jsonschema import Draft202012Validator

    return [f"reply: {'.'.join(map(str, e.absolute_path)) or '(object)'}: {e.message}"
            for e in Draft202012Validator(schema).iter_errors(obj)][:10]
