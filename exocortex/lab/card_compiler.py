# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Compiler of the reference project card (roadmap task F4.2): files only, no database, no model calls.

``compile_card(slug)`` reads what the lab published about one experiment:

- ``dowody/data/<slug>/``: metrics.csv, results.csv, runs.csv, configs.csv, samples.csv, datapackage.json;
- the hypothesis card in both languages (``dowody/<lang>/experiments/<slug>/hypothesis.md``) and the
  preregistration registry (``dowody/prereg.jsonl``);
- gate decision documents (``type: gate_decision`` in any ``dowody/<lang>/`` folder) naming the slug;
- the generated dossier, when the experiment has one, for the sentence about missing decisions;

and writes, for each language, three files:

- ``<slug>.card.<lang>.yaml``: the card in the format of F4.1 (lab/card-model.yaml, checked by
  ``exocortex lab card-check``);
- ``<slug>.card.<lang>.md``: the same sentences as Markdown, a link to a file or a data row of the repository
  next to every sentence;
- ``<slug>.sentences.<lang>.jsonl``: one record per sentence in the format of the honesty check (F4.3,
  ``exocortex lab honesty``).

Every sentence is a template of this module (Polish and English) filled with values from those files, or a
paragraph of the hypothesis card quoted word for word. The program writes nothing else. A section whose data
do not exist says so ("no results yet") and cites the file that shows it.

Two rules hold by construction:

- The project status is the decision of the last applied gate decision for the card's current version, never
  higher; without one it is ``frozen`` (the card is registered and unchanged) or ``draft``, never a decision
  (``project_status``).
- A number that is not a recorded result (a threshold, a seed, a sample size) is printed in code format, as
  the honesty check allows for identifiers and parameters, so the card shows a parameter next to a result
  without presenting it as one. ``compile_card`` runs ``card-check`` and the honesty check on its own output.

Nothing is published anywhere: the output goes to ``out`` (a temporary folder by default).
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
import tempfile
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from exocortex.lab import card_model, honesty, prereg
from exocortex.lab import docs as docs_mod

LANGS = card_model.LANGS
DEFAULT_BASE_URL = "https://github.com/hretheum/exocortex-public/blob/main/"
STATES = ("draft", "frozen", "GO", "NO-GO", "PIVOT", "NOT-NOW", "CLOSED")
DECISIONS = STATES[2:]
GATES = ("G0", "G1", "G2")
AGREE = ("hypothesis", "hypothesis_version", "gate", "decision", "date", "result_ids", "return_condition")
ROLE_WORDS = {"pl": {"tuning": "strojenie", "control": "kontrola", "blind": "ślepa próba", "test": "test"}}


class CompileError(ValueError):
    """The experiment cannot be compiled; the message says why and what is missing."""


# ------------------------------------------------------------------ text ----
# One template per sentence and language. Placeholders are filled with values from the repository's files.
T: dict[str, dict[str, Any]] = {
    "en": {
        "title": "Reference card: {slug}",
        "card_lists": "The card lists among its sources: “{title}” ({path}).",
        "missing_problem": "The hypothesis card has no Problem section.",
        "version_first": "Version {v} is the first version of the hypothesis card.",
        "version_next": "Version {v} of the hypothesis card replaces version {old}.",
        "state_draft": "As of {date}, version {v} of the card is a draft: it is {approved} and has no entry in the "
                       "preregistration registry.",
        "state_frozen": "As of {date}, version {v} of the card is frozen: it was registered on {registered} and its "
                        "checksum {sha} still matches the registry.",
        "state_changed": "As of {date}, version {v} of the card was registered on {registered}, but its text no "
                         "longer matches the registered checksum, so it is treated as a draft.",
        "approved_yes": "approved in both languages",
        "approved_no": "not approved in both languages",
        "quote_state": "As of {date}, the card says: {text}",
        "config": "Configuration {name}: model {model}, provider {provider}, variant {variant}.",
        "run": "Run {run} measured sample {sample} with card version {v}, code commit {commit}, status {status}.",
        "run_counts": " {total} results were recorded for it, {failed} of them failed.",
        "run_no_results": " No result rows are recorded for it.",
        "no_runs": "As of {date}, no run is recorded for this experiment.",
        "no_configs": "As of {date}, no configuration is recorded for this experiment.",
        "metric_card": "The card defines the metric {metric} (role: {role}): {definition}.",
        "metric_threshold": " Threshold: {threshold}.",
        "metric_baseline": " Baseline: {baseline}.",
        "metric_how": " Computed by: {how}.",
        "sample": "Sample {name} (role: {role}) has size {size} and seed {seed}; sampling method: “{method}”.",
        "sample_sha": " The checksum of its members starts with {sha}.",
        "stat_method": "The metric {metric} is computed with the method {method}.",
        "no_samples": "As of {date}, no sample is recorded for this experiment.",
        "result": "In run {run} on sample {sample}{role}, the metric {metric} {scope} was {value}{details}.",
        "result_no_value": "In run {run}, the metric {metric} {scope} is recorded without a value.",
        "scope_config": "for configuration {config}",
        "scope_pair": "comparing {b} with {a}",
        "scope_all": "across configurations",
        "role": " (role: {role})",
        "details": " (confidence interval {lo} to {hi}, n = {n}, method {method})",
        "details_n": " (n = {n}, method {method})",
        "no_metrics_run": "Run {run} is recorded, but no metric for it has been published as of {date}.",
        "no_results": "As of {date}, no result of this experiment has been published: there is no run and no metric yet.",
        "status_rule": "The project status follows from the last approved gate decision and is never higher than it.",
        "status": "As of {date}, the project status is {state}.",
        "state_draft_word": "draft: the hypothesis card is not frozen",
        "state_frozen_word": "frozen: the card is registered and no gate has decided yet",
        "state_decided": "{decision} at gate {gate}",
        "decision": "The last approved gate decision, {gate} on {date}, for version {v} of the card is {decision}.",
        "decision_results": "It rests on the results {ids}.",
        "return_condition": "Return condition: {text}",
        "no_decision": "As of {date}, no gate decision has been approved for this experiment.",
        "decision_not_applied": "The gate decision document {path} is not applied: {reason}.",
        "gate_rule": "A gate decision is accepted only for a card version that is approved in both languages, "
                     "registered and unchanged since.",
        "criterion_prefix": "Gate criterion of the card: {text}",
        "quote_card": "{text}",
        "quote_stop": "Stopping condition of the card: {text}",
        "quote_assumption": "The assumption everything depends on, according to the card: {text}",
        "quote_blind": "What the method will not detect, according to the card: {text}",
        "quote_related": "Related work, according to the card: {text}",
        "no_related": "The hypothesis card has no section on related work.",
        "no_risks": "The hypothesis card has no section on assumptions or limits, so none are stated here.",
        "guard": "The card sets the guard metric {metric} with the limit {threshold}.",
        "failed_items": "In run {run}, configuration {config}: {failed} of {total} items gave no result; the first, "
                        "{item}, failed with: “{reason}”.",
        "failed_items_noreason": "In run {run}, configuration {config}: {failed} of {total} items gave no result; "
                                 "the first one is {item}.",
        "recompute": "The command {command} recomputes every published number of this experiment from its CSV files.",
        "no_datapackage": "This experiment has no data package, so lab/recompute.py has no description of its "
                          "data to work from.",
        "commit": "The code commit {commit} was used by {runs}.",
        "verify_prereg": "The script lab/verify_prereg.py recomputes the checksum of every registered card and "
                         "checks that it was registered before the first run of its experiment.",
        "registered_at": "Version {v} of the card is registered in dowody/prereg.jsonl under the checksum {sha}.",
        "reason": {
            "missing_language": "only one language version exists",
            "header_invalid": "its header does not pass the document schema",
            "not_validated": "it is not approved by a person in both languages",
            "languages_disagree": "the two language versions disagree on {fields}",
            "bad_value": "its decision or gate is not one of the allowed values",
            "other_version": "it decides version {v} of the card, not the current version {cur}",
            "card_not_frozen": "the card version it decides is not registered and unchanged",
            "unknown_result": "it names a result id that is not in metrics.csv",
            "no_results": "it names no result id",
            "no_return_condition": "NOT-NOW needs a return condition",
        },
    },
    "pl": {
        "title": "Karta projektu referencyjnego: {slug}",
        "card_lists": "Karta wymienia wśród źródeł: „{title}” ({path}).",
        "missing_problem": "Karta hipotezy nie ma sekcji Problem.",
        "version_first": "Wersja {v} jest pierwszą wersją karty hipotezy.",
        "version_next": "Wersja {v} karty hipotezy zastępuje wersję {old}.",
        "state_draft": "Stan na {date}: wersja {v} karty jest szkicem: {approved} i nie ma wpisu w rejestrze "
                       "prerejestracji.",
        "state_frozen": "Stan na {date}: wersja {v} karty jest zamrożona, zarejestrowano ją {registered}, a jej suma "
                        "kontrolna {sha} nadal zgadza się z rejestrem.",
        "state_changed": "Stan na {date}: wersję {v} karty zarejestrowano {registered}, ale jej tekst nie zgadza się "
                         "już z zapisaną sumą kontrolną, więc traktujemy ją jak szkic.",
        "approved_yes": "jest zatwierdzona w obu językach",
        "approved_no": "nie jest zatwierdzona w obu językach",
        "quote_state": "Stan na {date}: karta stwierdza: {text}",
        "config": "Konfiguracja {name}: model {model}, dostawca {provider}, wariant {variant}.",
        "run": "Przebieg {run} zmierzył próbę {sample} według wersji karty {v}, commit kodu {commit}, "
               "status {status}.",
        "run_counts": " Zapisano dla niego wyników: {total}, w tym nieudanych: {failed}.",
        "run_no_results": " Nie ma dla niego zapisanych wierszy wyników.",
        "no_runs": "Stan na {date}: dla tego eksperymentu nie zapisano żadnego przebiegu.",
        "no_configs": "Stan na {date}: dla tego eksperymentu nie zapisano żadnej konfiguracji.",
        "metric_card": "Karta definiuje metrykę {metric} (rola: {role}): {definition}.",
        "metric_threshold": " Próg: {threshold}.",
        "metric_baseline": " Linia bazowa: {baseline}.",
        "metric_how": " Sposób liczenia: {how}.",
        "sample": "Próba {name} (rola: {role}) ma rozmiar {size} i ziarno {seed}; sposób losowania: „{method}”.",
        "sample_sha": " Suma kontrolna jej elementów zaczyna się od {sha}.",
        "stat_method": "Metryka {metric} jest liczona metodą {method}.",
        "no_samples": "Stan na {date}: dla tego eksperymentu nie zapisano żadnej próby.",
        "result": "W przebiegu {run} na próbie {sample}{role} metryka {metric} {scope} wyniosła {value}{details}.",
        "result_no_value": "W przebiegu {run} metryka {metric} {scope} jest zapisana bez wartości.",
        "scope_config": "dla konfiguracji {config}",
        "scope_pair": "w porównaniu {b} z {a}",
        "scope_all": "między konfiguracjami",
        "role": " (rola: {role})",
        "details": " (przedział ufności od {lo} do {hi}, n = {n}, metoda {method})",
        "details_n": " (n = {n}, metoda {method})",
        "no_metrics_run": "Przebieg {run} jest zapisany, ale stan na {date} nie opublikowano dla niego żadnej "
                          "metryki.",
        "no_results": "Stan na {date}: nie opublikowano jeszcze żadnego wyniku tego eksperymentu: nie ma przebiegu "
                      "ani metryki.",
        "status_rule": "Status projektu wynika z ostatniej zatwierdzonej decyzji bramki i nigdy nie jest od niej "
                       "wyższy.",
        "status": "Stan na {date}: status projektu to {state}.",
        "state_draft_word": "szkic: karta hipotezy nie jest zamrożona",
        "state_frozen_word": "zamrożona: karta jest zarejestrowana, a żadna bramka jeszcze nie zdecydowała",
        "state_decided": "{decision} na bramce {gate}",
        "decision": "Ostatnia zatwierdzona decyzja bramki, {gate} z dnia {date}, dla wersji {v} karty brzmi: "
                    "{decision}.",
        "decision_results": "Opiera się na wynikach {ids}.",
        "return_condition": "Warunek powrotu: {text}",
        "no_decision": "Stan na {date}: dla tego eksperymentu nie zatwierdzono żadnej decyzji bramki.",
        "decision_not_applied": "Dokument decyzji bramki {path} nie jest zastosowany: {reason}.",
        "gate_rule": "Decyzja bramki jest przyjmowana tylko dla wersji karty zatwierdzonej w obu językach, "
                     "zarejestrowanej i niezmienionej od rejestracji.",
        "criterion_prefix": "Kryterium bramki z karty: {text}",
        "quote_card": "{text}",
        "quote_stop": "Warunek przerwania z karty: {text}",
        "quote_assumption": "Założenie, od którego wszystko zależy, według karty: {text}",
        "quote_blind": "Czego metoda nie wykryje, według karty: {text}",
        "quote_related": "Prace pokrewne, według karty: {text}",
        "no_related": "Karta hipotezy nie ma sekcji o pracach pokrewnych.",
        "no_risks": "Karta hipotezy nie ma sekcji o założeniach ani ograniczeniach, więc nie podajemy ich tutaj.",
        "guard": "Karta ustala metrykę ochronną {metric} z granicą {threshold}.",
        "failed_items": "W przebiegu {run}, konfiguracja {config}: elementów bez wyniku {failed} z {total}; pierwszy, "
                        "{item}, zakończył się błędem: „{reason}”.",
        "failed_items_noreason": "W przebiegu {run}, konfiguracja {config}: elementów bez wyniku {failed} z "
                                 "{total}; pierwszy to {item}.",
        "recompute": "Polecenie {command} przelicza z plików CSV każdą opublikowaną liczbę tego eksperymentu.",
        "no_datapackage": "Ten eksperyment nie ma pakietu danych, więc lab/recompute.py nie ma opisu jego danych, "
                          "z którego mógłby korzystać.",
        "commit": "Commit kodu {commit} zastosowano w: {runs}.",
        "verify_prereg": "Skrypt lab/verify_prereg.py przelicza sumę kontrolną każdej zarejestrowanej karty i "
                         "sprawdza, że zarejestrowano ją przed pierwszym przebiegiem jej eksperymentu.",
        "registered_at": "Wersja {v} karty jest zapisana w dowody/prereg.jsonl pod sumą kontrolną {sha}.",
        "reason": {
            "missing_language": "istnieje tylko jedna wersja językowa",
            "header_invalid": "jego nagłówek nie przechodzi schematu dokumentów",
            "not_validated": "nie zatwierdził go człowiek w obu językach",
            "languages_disagree": "obie wersje językowe różnią się w polach: {fields}",
            "bad_value": "decyzja lub bramka nie jest jedną z dozwolonych wartości",
            "other_version": "dotyczy wersji {v} karty, a nie bieżącej wersji {cur}",
            "card_not_frozen": "wersja karty, której dotyczy, nie jest zarejestrowana i niezmieniona",
            "unknown_result": "wskazuje identyfikator wyniku, którego nie ma w metrics.csv",
            "no_results": "nie wskazuje żadnego identyfikatora wyniku",
            "no_return_condition": "NOT-NOW wymaga warunku powrotu",
        },
    },
}

# Headings of the hypothesis card sections, by language (templates/hypothesis-card.md in both languages).
CARD_HEADINGS = {
    "problem": ("Problem",),
    "hypothesis": ("Hipoteza", "Hypothesis"),
    "metrics": ("Metryki", "Metrics"),
    "assumption": ("Założenie, od którego wszystko zależy", "The assumption everything depends on"),
    "gate": ("Kryteria bramek", "Gate criteria"),
    "stop": ("Warunek przerwania", "Stopping condition"),
    "blind": ("Czego ta metoda nie wykryje", "What this method will not detect"),
    "related": ("Prace pokrewne", "Related work"),
}
DOSSIER_GATES = ("Decyzje z bramek", "Gate decisions")
METRIC_COLUMNS = {
    "role": ("rola", "role"), "metric": ("metryka", "metric"), "definition": ("definicja", "definition"),
    "threshold": ("próg", "threshold"), "baseline": ("linia bazowa", "baseline"),
    "how": ("jak liczona", "how computed"),
}


# --------------------------------------------------------------- records ----
@dataclass(frozen=True)
class Source:
    """What a sentence cites: a file (optionally a Markdown heading) or one data row."""

    path: str
    heading: str | None = None
    row: tuple[tuple[str, str], ...] | None = None  # column values picking exactly one row of a data file
    line: int | None = None  # line of that row in the file, for the link
    ref_id: str | None = None  # the recorded result id the sentence rests on (honesty check, source_ref)

    @property
    def is_data(self) -> bool:
        return self.row is not None

    def card_source(self) -> dict:
        if self.row is not None:
            return {"data": self.path, "row": dict(self.row)}
        out: dict = {"file": self.path}
        if self.heading:
            out["heading"] = self.heading
        return out

    @property
    def source_ref(self) -> str:
        return f"{self.path}#{self.ref_id}" if self.ref_id else self.path


@dataclass
class Statement:
    text: str
    mode: str
    source: Source
    source_mode: str = "fact"
    current_state: bool = False
    numbers: tuple[float, ...] = ()
    key: str = ""  # what the statement is, e.g. "status"; not printed


@dataclass
class Card:
    lang: str
    title: str
    sections: list[tuple[str, list[Statement]]] = field(default_factory=list)

    def statements(self) -> list[Statement]:
        return [s for _, sts in self.sections for s in sts]


@dataclass
class Compiled:
    slug: str
    as_of: str
    status: str  # project status: draft, frozen or a decision (project_status)
    version: int
    cards: dict[str, Card]
    files: dict[str, str] = field(default_factory=dict)  # name -> path written
    checks: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not any(self.checks.values())


# --------------------------------------------------------------- helpers ----
def project_status(card_state: str, decision: str | None) -> str:
    """The project status: the last applied gate decision, never higher; without one, frozen or draft.

    ``card_state`` is ``frozen`` for a registered, unchanged card and ``draft`` for anything else. A card
    without an applied decision can never be reported as GO, NO-GO or any other decision.
    """
    if decision is not None:
        if decision not in DECISIONS:
            raise ValueError(f"{decision!r} is not a gate decision")
        return decision
    return "frozen" if card_state == "frozen" else "draft"


def github_anchor(heading: str) -> str:
    """The fragment GitHub gives a Markdown heading."""
    text = re.sub(r"[`*_]", "", heading.strip().lower())
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def code(value: Any) -> str:
    return f"`{value}`"


@dataclass
class Table:
    """Rows of a data file with the line each one starts on."""

    path: str
    rows: list[dict[str, str]]
    lines: list[int]

    def find(self, **want: str) -> tuple[dict[str, str], int]:
        hits = [(r, n) for r, n in zip(self.rows, self.lines, strict=True)
                if all(r.get(k) == str(v) for k, v in want.items())]
        if len(hits) != 1:
            raise CompileError(f"{self.path}: {want} matches {len(hits)} rows, expected exactly one")
        return hits[0]

    def source(self, ref_id: str | None = None, **want: str) -> Source:
        _, line = self.find(**want)
        return Source(self.path, row=tuple((k, str(v)) for k, v in want.items()), line=line, ref_id=ref_id)


def read_table(root: Path, rel: str) -> Table | None:
    path = root / rel
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    rows: list[dict[str, str]] = []
    lines: list[int] = []
    if path.suffix == ".jsonl":
        for n, raw in enumerate(text.split("\n"), start=1):
            if raw.strip():
                obj = json.loads(raw)
                rows.append({k: v if isinstance(v, str) else json.dumps(v, sort_keys=True) for k, v in obj.items()})
                lines.append(n)
        return Table(rel, rows, lines)
    reader = csv.reader(io.StringIO(text, newline=""))
    header = next(reader, None)
    if header is None:
        return Table(rel, [], [])
    start = reader.line_num + 1
    for cells in reader:
        rows.append(dict(zip(header, cells, strict=False)))
        lines.append(start)
        start = reader.line_num + 1
    return Table(rel, rows, lines)


def table_rows(table: list[list[str]], columns: Mapping[str, Sequence[str]]) -> list[dict[str, str]]:
    """Rows of a Markdown table keyed by our column names, matched on header text in either language.

    The same reading as exocortex/lab/hypotheses.py, repeated here because that module needs a database driver.
    """
    if not table:
        return []
    header = [h.strip().lower() for h in table[0]]
    index = {name: next((i for i, h in enumerate(header) if h in aliases), None) for name, aliases in columns.items()}
    rows = []
    for cells in table[1:]:
        row = {name: (cells[i].strip() if i is not None and i < len(cells) else "") for name, i in index.items()}
        if any(row.values()):
            rows.append(row)
    return rows


def items_under(body: str, heading: str) -> list[str]:
    """Bullets and paragraphs under a Markdown heading, as plain one-line text; tables and code are left out."""
    text = docs_mod.sections(body).get(heading, "")
    text = re.sub(r"^```.*?^```", "", text, flags=re.MULTILINE | re.DOTALL)
    out: list[str] = []
    block: list[str] = []

    def flush() -> None:
        if block:
            out.append(" ".join(block))
            block.clear()

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("|"):
            flush()
        elif re.match(r"^([-*+]|\d+\.)\s+", stripped):
            flush()
            block.append(re.sub(r"^([-*+]|\d+\.)\s+", "", stripped))
        elif stripped.startswith("#"):
            flush()
        else:
            block.append(stripped)
    flush()
    cleaned = []
    for item in out:
        item = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", item)  # links keep their text
        item = item.replace("**", "").replace("  ", " ").strip()
        if item:
            cleaned.append(item)
    return cleaned


def _wrap_first(text: str, shown: str) -> str | None:
    """Put the first free occurrence of ``shown`` in code format; None when there is none."""
    for m in re.finditer(re.escape(shown), text):
        before, after = text[:m.start()], text[m.end():]
        if before.count("`") % 2 == 1:
            continue  # already inside code
        if re.search(r"[\w.,]$", before) or re.match(r"[\w]", after):
            continue
        return f"{before}`{shown}`{after}"
    return None


# ----------------------------------------------------------------- inputs ----
@dataclass
class Gate:
    """One gate decision document pair and what was decided about it."""

    key: str
    paths: dict[str, str]  # lang -> repository path
    header: dict
    applied: bool
    reasons: list[tuple[str, dict]]  # (code, format arguments)


class Inputs:
    """Everything the compiler reads for one experiment, read once."""

    def __init__(self, root: Path, slug: str) -> None:
        self.root = root
        self.slug = slug
        self.dowody = root / "dowody"
        self.data_dir = f"dowody/data/{slug}"
        self.cards: dict[str, docs_mod.Doc] = {}
        for lang in LANGS:
            path = self.dowody / lang / "experiments" / slug / "hypothesis.md"
            if not path.is_file():
                raise CompileError(f"no hypothesis card for {slug}: dowody/{lang}/experiments/{slug}/hypothesis.md "
                                   "does not exist")
            self.cards[lang] = docs_mod.read_doc(self.dowody, path)
        fronts = [d.front for d in self.cards.values()]
        version = fronts[0].get("version")
        if not isinstance(version, int) or any(f.get("version") != version for f in fronts):
            raise CompileError(f"the two language versions of the card of {slug} do not agree on the version")
        self.version: int = version
        self.supersedes = fronts[0].get("supersedes")
        self.approved = all(f.get("human_validated") is True for f in fronts)
        self.registry = prereg.read_registry(self.dowody / "prereg.jsonl")
        self.entry = prereg.find(self.registry, slug, version)
        self.entry_ok = False
        if self.entry is not None:
            verdict = prereg.verify(self.dowody, [self.entry])[0]
            self.entry_ok = verdict["status"] == "ok"
        self.card_state = "frozen" if self.entry_ok else "draft"
        self.prereg_table = read_table(root, "dowody/prereg.jsonl")
        self.metrics = read_table(root, f"{self.data_dir}/metrics.csv")
        self.results = read_table(root, f"{self.data_dir}/results.csv")
        self.runs = read_table(root, f"{self.data_dir}/runs.csv")
        self.configs = read_table(root, f"{self.data_dir}/configs.csv")
        self.samples = read_table(root, f"{self.data_dir}/samples.csv")
        self.has_datapackage = (root / self.data_dir / "datapackage.json").is_file()
        self.recorded = honesty.load_recorded([root / self.data_dir]) if (root / self.data_dir).is_dir() \
            else honesty.Recorded()
        self.gates = self._gates()

    # -- gate decisions
    def _gates(self) -> list[Gate]:
        pairs: dict[str, dict[str, docs_mod.Doc]] = {}
        for lang in LANGS:
            base = self.dowody / lang
            if not base.is_dir():
                continue
            for path in sorted(base.rglob("*.md")):
                doc = docs_mod.read_doc(self.dowody, path)
                if doc.front.get("type") == "gate_decision" and not doc.key.startswith("templates/"):
                    pairs.setdefault(doc.key, {})[lang] = doc
        out = []
        for key, pair in sorted(pairs.items()):
            if not any(d.front.get("hypothesis") == self.slug for d in pair.values()):
                continue
            out.append(self._check_gate(key, pair))
        return out

    def _check_gate(self, key: str, pair: dict[str, docs_mod.Doc]) -> Gate:
        from exocortex.lab import headers

        reasons: list[tuple[str, dict]] = []
        paths = {lang: f"dowody/{d.rel}" for lang, d in pair.items()}
        front = next(iter(pair.values())).front
        if set(pair) != set(LANGS):
            reasons.append(("missing_language", {}))
        elif any(headers.validate(d.rel, d.text) for d in pair.values()):
            reasons.append(("header_invalid", {}))
        else:
            diff = [f for f in AGREE if pair["pl"].front.get(f) != pair["en"].front.get(f)]
            if diff:
                reasons.append(("languages_disagree", {"fields": ", ".join(diff)}))
        if not all(d.front.get("human_validated") is True for d in pair.values()) or set(pair) != set(LANGS):
            reasons.append(("not_validated", {}))
        if front.get("decision") not in DECISIONS or front.get("gate") not in GATES:
            reasons.append(("bad_value", {}))
        if front.get("hypothesis_version") != self.version:
            reasons.append(("other_version", {"v": front.get("hypothesis_version"), "cur": self.version}))
        elif self.card_state != "frozen":
            reasons.append(("card_not_frozen", {}))
        ids = front.get("result_ids") or []
        known = {r["result_id"] for r in self.metrics.rows} if self.metrics else set()
        if not ids:
            reasons.append(("no_results", {}))
        elif any(i not in known for i in ids):
            reasons.append(("unknown_result", {}))
        if front.get("decision") == "NOT-NOW" and not front.get("return_condition"):
            reasons.append(("no_return_condition", {}))
        return Gate(key, paths, front, not reasons, reasons)

    def last_decision(self) -> Gate | None:
        applied = [g for g in self.gates if g.applied]
        if not applied:
            return None
        return max(applied, key=lambda g: (str(g.header.get("date")), GATES.index(g.header["gate"])))


# ---------------------------------------------------------------- context ----
@dataclass
class Ctx:
    inp: Inputs
    lang: str
    as_of: str
    t: dict[str, Any] = field(init=False)

    def __post_init__(self) -> None:
        self.t = T[self.lang]

    @property
    def card(self) -> docs_mod.Doc:
        return self.inp.cards[self.lang]

    @property
    def card_path(self) -> str:
        return f"dowody/{self.card.rel}"

    def card_file(self, heading_key: str | None = None) -> Source:
        heading = self.heading(heading_key) if heading_key else None
        return Source(self.card_path, heading=heading)

    def heading(self, key: str) -> str | None:
        have = set(docs_mod.sections(self.card.body))
        return next((h for h in CARD_HEADINGS[key] if h in have), None)

    def items(self, key: str) -> list[str]:
        h = self.heading(key)
        return items_under(self.card.body, h) if h else []

    def role_of(self, sample: str) -> str | None:
        if self.inp.samples is None:
            return None
        for row in self.inp.samples.rows:
            if row["name"] == sample:
                return row.get("role") or None
        return None

    def role_word(self, role: str) -> str:
        return ROLE_WORDS.get(self.lang, {}).get(role, role)

    def num(self, value: float) -> str:
        """A recorded number the way a reader sees it: enough digits to be an honest rounding."""
        for digits in range(3, 13):
            shown = f"{value:.{digits}f}"
            if honesty.matches(float(shown), digits, value):
                break
        return shown.replace(".", ",") if self.lang == "pl" else shown

    def fallback(self) -> Source:
        return self.card_file()


def _decimal(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def _date(value: Any) -> str:
    return str(value)[:10]


# --------------------------------------------------------------- sections ----
def quote(ctx: Ctx, text: str, key: str, mode: str, source_mode: str, template: str = "quote_card") -> Statement:
    return Statement(ctx.t[template].format(text=text), mode, ctx.card_file(key), source_mode)


def goal_and_context(ctx: Ctx) -> list[Statement]:
    out = [quote(ctx, t, "problem", "fact", "fact") for t in ctx.items("problem")]
    if not out:
        out.append(Statement(ctx.t["missing_problem"], "fact", ctx.card_file()))
    for rel in ctx.card.front.get("sources") or []:
        target = (ctx.inp.dowody / ctx.card.rel).parent / str(rel)
        try:
            resolved = target.resolve().relative_to(ctx.inp.root.resolve())
        except ValueError:
            continue
        if target.is_file():
            title = docs_mod.read_doc(ctx.inp.dowody, target.resolve()).title if target.suffix == ".md" else resolved.name
            out.append(Statement(ctx.t["card_lists"].format(title=title, path=code(resolved.as_posix())), "fact",
                                 ctx.card_file()))
    return out


def hypothesis(ctx: Ctx) -> list[Statement]:
    inp, date = ctx.inp, ctx.as_of
    out = [quote(ctx, t, "hypothesis", "hypothesis", "hypothesis") for t in ctx.items("hypothesis")]
    v = f"v{inp.version}"
    if isinstance(inp.supersedes, int):
        out.append(Statement(ctx.t["version_next"].format(v=v, old=f"v{inp.supersedes}"), "fact", ctx.card_file()))
    else:
        out.append(Statement(ctx.t["version_first"].format(v=v), "fact", ctx.card_file()))
    if inp.entry is None:
        approved = ctx.t["approved_yes" if inp.approved else "approved_no"]
        out.append(Statement(ctx.t["state_draft"].format(date=date, v=v, approved=approved), "fact", ctx.card_file(),
                             current_state=True, key="card_state"))
    else:
        assert inp.prereg_table is not None
        src = inp.prereg_table.source(slug=inp.slug, version=str(inp.version))
        registered = _date(inp.entry.get("registered_at"))
        if inp.entry_ok:
            text = ctx.t["state_frozen"].format(date=date, v=v, registered=registered,
                                                sha=code(str(inp.entry["sha256"])[:16]))
        else:
            text = ctx.t["state_changed"].format(date=date, v=v, registered=registered)
        out.append(Statement(text, "fact", src, current_state=True, key="card_state"))
    return out


def _failed_by_run_config(inp: Inputs) -> dict[tuple[str, str], list[dict[str, str]]]:
    out: dict[tuple[str, str], list[dict[str, str]]] = {}
    for r in (inp.results.rows if inp.results else []):
        out.setdefault((r["run_id"], r["config"]), []).append(r)
    return out


def experiments_and_iterations(ctx: Ctx) -> list[Statement]:
    inp, date = ctx.inp, ctx.as_of
    out: list[Statement] = []
    if inp.runs is None or not inp.runs.rows:
        out.append(Statement(ctx.t["no_runs"].format(date=date), "fact", ctx.card_file(), current_state=True))
    else:
        totals: Counter[str] = Counter()
        failed: Counter[str] = Counter()
        for r in (inp.results.rows if inp.results else []):
            totals[r["run_id"]] += 1
            failed[r["run_id"]] += (r.get("ok") or "").strip().lower() != "true"
        for r in inp.runs.rows:
            rid = r["run_id"]
            text = ctx.t["run"].format(run=code(rid), sample=code(r["sample"]), v=f"v{r['hypothesis_version']}",
                                       commit=code(r["code_commit"][:12]), status=code(r["status"]))
            ref = None
            if totals[rid]:
                text += ctx.t["run_counts"].format(total=totals[rid], failed=failed[rid])
                ref = f"{inp.slug}/{rid}"
            else:
                text += ctx.t["run_no_results"]
            out.append(Statement(text, "fact", inp.runs.source(ref_id=ref, run_id=rid),
                                 numbers=(float(totals[rid]), float(failed[rid])) if ref else ()))
    if inp.configs is None or not inp.configs.rows:
        out.append(Statement(ctx.t["no_configs"].format(date=date), "fact", ctx.card_file(), current_state=True))
    else:
        for r in inp.configs.rows:
            out.append(Statement(ctx.t["config"].format(name=code(r["name"]), model=code(r["model"]),
                                                        provider=code(r["provider"]), variant=code(r["variant"])),
                                 "fact", inp.configs.source(name=r["name"])))
    return out


def validation_method(ctx: Ctx) -> list[Statement]:
    inp, date = ctx.inp, ctx.as_of
    out: list[Statement] = []
    heading = ctx.heading("metrics")
    rows = table_rows(docs_mod.first_table_under(ctx.card.body, CARD_HEADINGS["metrics"]), METRIC_COLUMNS) \
        if heading else []
    for r in rows:
        text = ctx.t["metric_card"].format(metric=code(r["metric"]), role=r["role"] or "-",
                                           definition=r["definition"].rstrip("."))
        for cell, key in (("threshold", "metric_threshold"), ("baseline", "metric_baseline"), ("how", "metric_how")):
            if r[cell]:
                text += ctx.t[key].format(**{cell: r[cell].rstrip(".")})
        out.append(Statement(text, "fact", ctx.card_file("metrics")))
    for t in ctx.items("gate"):
        out.append(Statement(ctx.t["criterion_prefix"].format(text=t), "requirement", ctx.card_file("gate"),
                             "requirement"))
    if inp.samples is None or not inp.samples.rows:
        out.append(Statement(ctx.t["no_samples"].format(date=date), "fact", ctx.card_file(), current_state=True))
    else:
        for r in inp.samples.rows:
            text = ctx.t["sample"].format(name=code(r["name"]), role=ctx.role_word(r["role"]), size=code(r["size"]),
                                          seed=code(r["seed"]), method=r["method"])
            if r.get("members_sha256"):
                text += ctx.t["sample_sha"].format(sha=code(r["members_sha256"][:12]))
            out.append(Statement(text, "fact", inp.samples.source(name=r["name"])))
    seen: set[tuple[str, str]] = set()
    for r in (inp.metrics.rows if inp.metrics else []):
        pair = (r["metric"], r["method"])
        if r["method"] and pair not in seen:
            seen.add(pair)
            assert inp.metrics is not None
            out.append(Statement(ctx.t["stat_method"].format(metric=code(r["metric"]), method=code(r["method"])),
                                 "fact", inp.metrics.source(result_id=r["result_id"])))
    return out


def _details(raw: str) -> dict:
    try:
        d = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {}
    return d if isinstance(d, dict) else {}


def results(ctx: Ctx) -> list[Statement]:
    inp, date = ctx.inp, ctx.as_of
    out: list[Statement] = []
    rows = inp.metrics.rows if inp.metrics else []
    for r in rows:
        assert inp.metrics is not None
        src = inp.metrics.source(ref_id=r["result_id"], result_id=r["result_id"])
        run = next((x for x in (inp.runs.rows if inp.runs else []) if x["run_id"] == r["run_id"]), None)
        sample = run["sample"] if run else None
        role = ctx.role_of(sample) if sample else None
        details = _details(r.get("details", ""))
        if r["config"]:
            scope = ctx.t["scope_config"].format(config=code(r["config"]))
        elif "a" in details and "b" in details:
            scope = ctx.t["scope_pair"].format(a=code(details["a"]), b=code(details["b"]))
        else:
            scope = ctx.t["scope_all"]
        value = _decimal(r["value"])
        if value is None:
            out.append(Statement(ctx.t["result_no_value"].format(run=code(r["run_id"]), metric=code(r["metric"]),
                                                                scope=scope), "fact", src))
            continue
        nums = [value]
        lo, hi, n = _decimal(r["ci_low"]), _decimal(r["ci_high"]), _decimal(r["n"])
        tail = ""
        if lo is not None and hi is not None and n is not None:
            tail = ctx.t["details"].format(lo=ctx.num(lo), hi=ctx.num(hi), n=int(n),
                                           method=code(r["method"]))
            nums += [lo, hi, n]
        elif n is not None:
            tail = ctx.t["details_n"].format(n=int(n), method=code(r["method"]))
            nums.append(n)
        text = ctx.t["result"].format(
            run=code(r["run_id"]), sample=code(sample) if sample else code("-"),
            role=ctx.t["role"].format(role=ctx.role_word(role)) if role else "",
            metric=code(r["metric"]), scope=scope, value=ctx.num(value), details=tail)
        out.append(Statement(text, "fact", src, numbers=tuple(nums)))
    metric_runs = {r["run_id"] for r in rows}
    for r in (inp.runs.rows if inp.runs else []):
        if r["run_id"] not in metric_runs:
            assert inp.runs is not None
            out.append(Statement(ctx.t["no_metrics_run"].format(run=code(r["run_id"]), date=date), "fact",
                                 inp.runs.source(run_id=r["run_id"]), current_state=True))
    if not out:
        out.append(Statement(ctx.t["no_results"].format(date=date), "fact", _first_data_row(inp),
                             current_state=True))
    return out


def _first_data_row(inp: Inputs) -> Source:
    """A data row to cite for "no results yet": the results section accepts data sources only (F4.1)."""
    for table, col in ((inp.runs, "run_id"), (inp.configs, "name"), (inp.samples, "name")):
        if table is not None and table.rows:
            return table.source(**{col: table.rows[0][col]})
    if inp.prereg_table is not None and inp.entry is not None:
        return inp.prereg_table.source(slug=inp.slug, version=str(inp.version))
    raise CompileError(
        f"{inp.slug}: nothing to cite for the results section: no run, configuration, sample or registry row "
        "exists, and the card model accepts only data rows there (open decision for the card model)")


def status_state_word(ctx: Ctx, status: str, gate: Gate | None) -> str:
    if status == "draft":
        return ctx.t["state_draft_word"]
    if status == "frozen":
        return ctx.t["state_frozen_word"]
    assert gate is not None
    return ctx.t["state_decided"].format(decision=status, gate=gate.header["gate"])


def next_steps(ctx: Ctx) -> list[Statement]:
    inp, date = ctx.inp, ctx.as_of
    gate = inp.last_decision()
    status = project_status(inp.card_state, gate.header["decision"] if gate else None)
    out: list[Statement] = []
    if gate is not None:
        status_src = Source(gate.paths[ctx.lang])
    elif inp.entry_ok and inp.prereg_table is not None:
        status_src = inp.prereg_table.source(slug=inp.slug, version=str(inp.version))
    else:
        status_src = ctx.card_file()
    out.append(Statement(ctx.t["status"].format(date=date, state=status_state_word(ctx, status, gate)), "fact",
                         status_src, current_state=True, key="status"))
    out.append(Statement(ctx.t["status_rule"], "requirement", Source("exocortex/lab/card_compiler.py"),
                         "requirement"))
    if gate is not None:
        h = gate.header
        out.append(Statement(ctx.t["decision"].format(gate=h["gate"], date=_date(h["date"]),
                                                      v=f"v{h['hypothesis_version']}", decision=h["decision"]),
                             "fact", Source(gate.paths[ctx.lang])))
        ids = ", ".join(code(i) for i in h["result_ids"])
        out.append(Statement(ctx.t["decision_results"].format(ids=ids), "fact", Source(gate.paths[ctx.lang])))
        if h.get("return_condition"):
            out.append(Statement(ctx.t["return_condition"].format(text=h["return_condition"]), "requirement",
                                 Source(gate.paths[ctx.lang]), "requirement"))
    else:
        dossier = f"dowody/{ctx.lang}/generated/experiments/{inp.slug}.md"
        src = ctx.card_file()
        if (inp.root / dossier).is_file():
            doc = docs_mod.read_doc(inp.dowody, inp.root / dossier)
            heading = next((h for h in DOSSIER_GATES if h in docs_mod.sections(doc.body)), None)
            src = Source(dossier, heading=heading)
        out.append(Statement(ctx.t["no_decision"].format(date=date), "fact", src, current_state=True))
    for g in inp.gates:
        if g.applied:
            continue
        path = g.paths.get(ctx.lang) or next(iter(g.paths.values()))
        for reason, args in g.reasons:
            out.append(Statement(ctx.t["decision_not_applied"].format(path=code(path),
                                                                      reason=ctx.t["reason"][reason].format(**args)),
                                 "fact", Source(path)))
    out.append(Statement(ctx.t["gate_rule"], "requirement", Source("exocortex/lab/gates.py"), "requirement"))
    for t in ctx.items("stop"):
        out.append(quote(ctx, t, "stop", "plan", "plan", "quote_stop"))
    return out


def novelty(ctx: Ctx) -> list[Statement]:
    out = [quote(ctx, t, "related", "fact", "fact", "quote_related") for t in ctx.items("related")]
    return out or [Statement(ctx.t["no_related"], "fact", ctx.card_file())]


def risks_and_limitations(ctx: Ctx) -> list[Statement]:
    inp = ctx.inp
    out = [quote(ctx, t, key, "fact", "fact", f"quote_{key}") for key in ("assumption", "blind")
           for t in ctx.items(key)]
    heading = ctx.heading("metrics")
    rows = table_rows(docs_mod.first_table_under(ctx.card.body, CARD_HEADINGS["metrics"]), METRIC_COLUMNS) \
        if heading else []
    guard_roles = {"guard", "ochronna"}
    for r in rows:
        if r["role"].lower() in guard_roles and r["threshold"]:
            out.append(Statement(ctx.t["guard"].format(metric=code(r["metric"]), threshold=r["threshold"]), "fact",
                                 ctx.card_file("metrics")))
    for (run, cfg), rs in sorted(_failed_by_run_config(inp).items()):
        bad = [r for r in rs if (r.get("ok") or "").strip().lower() != "true"]
        if not bad:
            continue
        first = bad[0]
        assert inp.results is not None
        src = inp.results.source(ref_id=f"{inp.slug}/{run}/{cfg}", run_id=run, config=cfg, item_id=first["item_id"])
        args = {"run": code(run), "config": code(cfg), "failed": len(bad), "total": len(rs),
                "item": code(first["item_id"]), "reason": first.get("error_reason", "")}
        key = "failed_items" if args["reason"] else "failed_items_noreason"
        out.append(Statement(ctx.t[key].format(**args), "fact", src, numbers=(float(len(bad)), float(len(rs)))))
    return out or [Statement(ctx.t["no_risks"], "fact", ctx.card_file())]


def how_to_verify(ctx: Ctx) -> list[Statement]:
    inp = ctx.inp
    out: list[Statement] = []
    package = inp.root / inp.data_dir / "datapackage.json"
    if package.is_file():
        command = json.loads(package.read_text(encoding="utf-8")).get("exocortex", {}).get("recompute")
    else:
        command = None
    if command:
        out.append(Statement(ctx.t["recompute"].format(command=code(command)), "fact",
                             Source(f"{inp.data_dir}/datapackage.json")))
    else:
        out.append(Statement(ctx.t["no_datapackage"], "fact", Source("lab/recompute.py")))
    by_commit: dict[str, list[str]] = {}
    for r in (inp.runs.rows if inp.runs else []):
        by_commit.setdefault(r["code_commit"], []).append(r["run_id"])
    for commit, runs in by_commit.items():
        assert inp.runs is not None
        out.append(Statement(ctx.t["commit"].format(commit=code(commit[:12]), runs=", ".join(code(r) for r in runs)),
                             "fact", inp.runs.source(run_id=runs[0])))
    if inp.entry is not None and inp.prereg_table is not None:
        out.append(Statement(ctx.t["registered_at"].format(v=f"v{inp.version}", sha=code(inp.entry["sha256"])),
                             "fact", inp.prereg_table.source(slug=inp.slug, version=str(inp.version))))
    out.append(Statement(ctx.t["verify_prereg"], "fact", Source("lab/verify_prereg.py")))
    return out


BUILDERS: dict[str, Callable[[Ctx], list[Statement]]] = {
    "goal_and_context": goal_and_context,
    "hypothesis": hypothesis,
    "experiments_and_iterations": experiments_and_iterations,
    "validation_method": validation_method,
    "results": results,
    "next_steps": next_steps,
    "novelty": novelty,
    "risks_and_limitations": risks_and_limitations,
    "how_to_verify": how_to_verify,
}


# --------------------------------------------------------- honest wording ----
def finalize(ctx: Ctx, st: Statement) -> Statement:
    """Make a statement pass the honesty check by construction.

    - a sentence that speaks about the current state gets the date it is true as of (a quoted card sentence
      with a word like "works" is attributed to the card as of that date);
    - a number that is not a recorded result of the sentence's own source (a threshold, a seed, a size) is
      printed in code format.
    """
    text = st.text
    if not st.current_state and honesty.state_words(text) and not honesty.has_date(text):
        st = Statement(ctx.t["quote_state"].format(date=ctx.as_of, text=text), st.mode, st.source, st.source_mode,
                       True, st.numbers, st.key)
        text = st.text
    # only a sentence resting on one recorded result may show its numbers unmarked; any other number is a
    # parameter or an identifier, even when it happens to equal a recorded value
    pool = ctx.inp.recorded.by_result.get(st.source.ref_id or "", [])
    for _ in range(200):
        bad = [n for n in honesty.numbers_in(text) if not honesty.number_matches(n, pool)]
        if not bad:
            break
        wrapped = _wrap_first(text, bad[0].shown)
        if wrapped is None:
            raise CompileError(f"cannot mark the number {bad[0].shown!r} in: {text}")
        text = wrapped
    st.text = text
    return st


def build_card(inp: Inputs, lang: str, as_of: str) -> Card:
    ctx = Ctx(inp, lang, as_of)
    model = card_model.load_model(root=inp.root)
    card = Card(lang, ctx.t["title"].format(slug=inp.slug))
    for section in model["sections"]:
        statements = [finalize(ctx, s) for s in BUILDERS[section["id"]](ctx)]
        card.sections.append((section["id"], statements))
    return card


# ---------------------------------------------------------------- output ----
def link_url(source: Source, base_url: str) -> str:
    url = base_url + source.path
    if source.is_data:
        return f"{url}?plain=1#L{source.line}"
    if source.heading:
        return f"{url}#{github_anchor(source.heading)}"
    return url


def link_label(source: Source) -> str:
    name = Path(source.path).name
    if source.is_data:
        return f"{name}#L{source.line}"
    return f"{name} § {source.heading}" if source.heading else name


def to_yaml(compiled: Compiled, lang: str) -> str:
    card = compiled.cards[lang]
    model = card_model.load_model()
    sections = []
    for sid, sts in card.sections:
        statements = []
        for st in sts:
            item: dict[str, Any] = {"text": st.text, "mode": st.mode, "source": st.source.card_source(),
                                    "current_state": st.current_state}
            if st.current_state:
                item["as_of"] = compiled.as_of
            statements.append(item)
        sections.append({"id": sid, "statements": statements})
    doc = {"card_model": model["version"], "experiment": compiled.slug,
           "hypothesis": {"slug": compiled.slug, "version": compiled.version}, "lang": lang, "title": card.title,
           "sections": sections}
    header = (f"# Generated by `exocortex lab card-compile {compiled.slug}` (F4.2) from the files cited in the\n"
              f"# statements; do not edit by hand. Format: lab/card-model.yaml. Compiled as of {compiled.as_of}.\n")
    return header + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=10_000)


def to_markdown(compiled: Compiled, lang: str, base_url: str) -> str:
    card = compiled.cards[lang]
    model = card_model.load_model()
    titles = {s["id"]: s["title"][lang] for s in model["sections"]}
    note = (f"<!-- Generated by `exocortex lab card-compile {compiled.slug}` (F4.2); every sentence links to the "
            f"file or data row it comes from. Do not edit by hand. -->")
    lines = [note, "", f"# {card.title}", ""]
    for sid, sts in card.sections:
        lines += [f"## {titles[sid]}", ""]
        for st in sts:
            lines.append(f"- {st.text} [{link_label(st.source)}]({link_url(st.source, base_url)})")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def to_records(compiled: Compiled, lang: str) -> str:
    """Honesty-check records (exocortex/lab/honesty.py: Sentence), one JSON object per line."""
    out = []
    for st in compiled.cards[lang].statements():
        out.append(json.dumps({
            "text": st.text, "mode": st.mode, "source_ref": st.source.source_ref, "source_mode": st.source_mode,
            "numbers": list(st.numbers), "date": compiled.as_of if st.current_state else None,
        }, ensure_ascii=False))
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ entry ----
def compile_card(slug: str, out: Path | None = None, root: Path | None = None, as_of: str | None = None,
                 base_url: str = DEFAULT_BASE_URL) -> Compiled:
    """Compile the card of ``slug`` into ``out`` and run the F4.1 and F4.3 checks on the result."""
    root = root or card_model.ROOT
    if not card_model.SLUG.fullmatch(slug):
        raise CompileError(f"{slug!r} is not an experiment slug")
    as_of = as_of or dt.datetime.now(dt.UTC).date().isoformat()
    try:
        dt.date.fromisoformat(as_of)
    except ValueError:
        raise CompileError(f"as-of date must be YYYY-MM-DD, not {as_of!r}") from None
    if not base_url.endswith("/") and base_url:
        base_url += "/"
    inp = Inputs(root, slug)
    gate = inp.last_decision()
    status = project_status(inp.card_state, gate.header["decision"] if gate else None)
    compiled = Compiled(slug, as_of, status, inp.version, {lang: build_card(inp, lang, as_of) for lang in LANGS})
    out = Path(out) if out else Path(tempfile.mkdtemp(prefix=f"card-{slug}-"))
    out.mkdir(parents=True, exist_ok=True)
    for lang in LANGS:
        files = {
            f"{slug}.card.{lang}.yaml": to_yaml(compiled, lang),
            f"{slug}.card.{lang}.md": to_markdown(compiled, lang, base_url),
            f"{slug}.sentences.{lang}.jsonl": to_records(compiled, lang),
        }
        for name, text in files.items():
            (out / name).write_text(text, encoding="utf-8")
            compiled.files[name] = str(out / name)
    checks: dict[str, Any] = {}
    for lang in LANGS:
        problems = [str(p) for p in card_model.check_file(out / f"{slug}.card.{lang}.yaml", root=root)]
        checks[f"card-check {lang}"] = problems
        report, _ = honesty.run(out / f"{slug}.sentences.{lang}.jsonl", [root / inp.data_dir]
                                if (root / inp.data_dir).is_dir() else [])
        checks[f"honesty {lang}"] = report.get("violations", []) or ([report["error"]] if "error" in report else [])
    compiled.checks = checks
    return compiled


def report(compiled: Compiled) -> dict:
    return {
        "command": "card-compile", "experiment": compiled.slug, "as_of": compiled.as_of,
        "card_version": compiled.version, "project_status": compiled.status,
        "sentences": {lang: len(c.statements()) for lang, c in compiled.cards.items()},
        "files": compiled.files, "checks": {k: v for k, v in compiled.checks.items()},
        "ok": compiled.ok,
    }


def read_links(markdown: str) -> Iterable[tuple[str, str]]:
    """(label, url) of every link in a compiled card, in order."""
    return re.findall(r"\[([^\]]+)\]\((https?://[^)]+|[^)]+)\)", markdown)
