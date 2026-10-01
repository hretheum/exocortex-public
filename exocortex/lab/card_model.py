# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""General model of a reference project card and its validator (roadmap task F4.1).

The model (lab/card-model.yaml) lists nine sections in a fixed order, what
each one answers, the sentence modes it may contain, the kinds of source it
may cite and which parts of the lab graph its content comes from. Its
``inventory`` names only node types, edge types, tables and files that the
lab code and migrations already define.

A card is a YAML file with a header and one entry per section, in the
model's order. Each section holds statements; every statement has the three
fields the honesty check (F4.3) reads:

- ``mode``: fact, plan, requirement or hypothesis (the modes of the F3
  extractor), and one of the modes the model allows in that section;
- ``source``: a file in the repository (``file``, optionally a Markdown
  ``heading`` in it) or one data row (``data``, a CSV or JSONL file, and
  ``row``, column values that match exactly one row);
- ``current_state`` and ``as_of``: a statement about the current state
  carries the date it was true on; any other statement has no date.

Example:

    card_model: 1
    experiment: toy-length
    hypothesis: {slug: toy-length, version: 1}
    lang: en
    title: "Toy experiment: document length"
    sections:
      - id: goal_and_context
        statements:
          - text: "..."
            mode: fact
            source: {file: dowody/en/experiments/toy-length/hypothesis.md, heading: Problem}
            current_state: false

Messages name the field by its path with list positions, for example
``sections[4].statements[0].source``, and say what is wrong in plain words.
Sources are checked against the repository: the file must exist, the
heading must be in it, the row must match exactly one row.

    python -m exocortex.lab.card_model lab/cards/toy-length.en.yaml
    exocortex lab card-check lab/cards/toy-length.en.yaml
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from exocortex.lab.extractor import MODES

ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = "lab/card-model.yaml"
LANGS = ("pl", "en")
SOURCE_KINDS = ("file", "data")
INVENTORY_KINDS = ("nodes", "sources", "edges", "tables", "files")
GRAPH_KINDS = {"nodes": "nodes", "edges": "edges", "tables": "tables", "files": "files"}
CARD_FIELDS = {"card_model", "experiment", "hypothesis", "lang", "title", "sections"}
SECTION_FIELDS = {"id", "statements"}
STATEMENT_FIELDS = {"text", "mode", "source", "current_state", "as_of"}
FILE_SOURCE_FIELDS = {"file", "heading"}
DATA_SOURCE_FIELDS = {"data", "row"}
DATA_SUFFIXES = (".csv", ".jsonl")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SECTION_ID = re.compile(r"^[a-z][a-z_]*$")
DECISION_ID = re.compile(r"^OD-\d+$")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class Problem:
    field: str
    message: str

    def __str__(self) -> str:
        return f"{self.field}: {self.message}"


class CardModelError(ValueError):
    """The model file itself is broken; carries every problem."""

    def __init__(self, path: str, problems: list[Problem]):
        self.problems = problems
        super().__init__(f"{path}: " + "; ".join(map(str, problems)))


# ------------------------------------------------------------------ model ----
def load_model(path: Path | None = None, root: Path | None = None) -> dict:
    """The card model, checked; raises CardModelError when it is broken."""
    path = path or (root or ROOT) / MODEL_PATH
    model = yaml.safe_load(path.read_text(encoding="utf-8"))
    problems = check_model(model)
    if problems:
        raise CardModelError(str(path), problems)
    return model


def check_model(model: Any) -> list[Problem]:
    """Every problem of the model file, empty when it is usable."""
    if not isinstance(model, dict):
        return [Problem("(model)", "expected a mapping")]
    out: list[Problem] = []
    unknown = set(model) - {"version", "modes", "inventory", "sections", "open_decisions"}
    if unknown:
        out.append(Problem(", ".join(sorted(unknown)), "unknown field"))
    if not isinstance(model.get("version"), int) or isinstance(model.get("version"), bool):
        out.append(Problem("version", "expected an integer"))
    if model.get("modes") != list(MODES):
        out.append(Problem("modes", f"must be exactly {list(MODES)}, the modes of exocortex/lab/extractor.py"))
    inventory = model.get("inventory")
    names: dict[str, set[str]] = {kind: set() for kind in INVENTORY_KINDS}
    if not isinstance(inventory, dict):
        out.append(Problem("inventory", "expected a mapping"))
    else:
        for kind in INVENTORY_KINDS:
            entries = inventory.get(kind)
            if not isinstance(entries, dict) or not entries:
                out.append(Problem(f"inventory.{kind}", "expected a non-empty mapping"))
                continue
            names[kind] = set(entries)
            for name, entry in entries.items():
                where = f"inventory.{kind}.{name}"
                if not isinstance(entry, dict) or set(entry) != {"defined_in", "what"}:
                    out.append(Problem(where, "expected exactly the fields defined_in and what"))
                elif not all(isinstance(entry[k], str) and entry[k].strip() for k in ("defined_in", "what")):
                    out.append(Problem(where, "defined_in and what must be non-empty text"))
        extra = set(inventory) - set(INVENTORY_KINDS)
        if extra:
            out.append(Problem(f"inventory.{', '.join(sorted(extra))}", "unknown field"))
    decisions = model.get("open_decisions")
    decision_ids: set[str] = set()
    if not isinstance(decisions, list):
        out.append(Problem("open_decisions", "expected a list"))
    else:
        for i, d in enumerate(decisions):
            where = f"open_decisions[{i}]"
            if not isinstance(d, dict) or set(d) != {"id", "question", "now", "options"}:
                out.append(Problem(where, "expected exactly the fields id, question, now and options"))
                continue
            if not isinstance(d["id"], str) or not DECISION_ID.fullmatch(d["id"]):
                out.append(Problem(f"{where}.id", f"expected OD-<number>, got {d['id']!r}"))
            elif d["id"] in decision_ids:
                out.append(Problem(f"{where}.id", f"{d['id']} appears twice"))
            else:
                decision_ids.add(d["id"])
            if not isinstance(d["options"], list) or len(d["options"]) < 2:
                out.append(Problem(f"{where}.options", "a decision needs at least two options"))
    sections = model.get("sections")
    if not isinstance(sections, list) or not sections:
        return out + [Problem("sections", "expected a non-empty list")]
    seen: set[str] = set()
    used_decisions: set[str] = set()
    fields = {"id", "title", "answers", "modes", "source_kinds", "graph", "content", "open_decisions"}
    for i, s in enumerate(sections):
        where = f"sections[{i}]"
        if not isinstance(s, dict):
            out.append(Problem(where, "expected a mapping"))
            continue
        if set(s) != fields:
            missing, extra = fields - set(s), set(s) - fields
            if missing:
                out.append(Problem(where, f"missing {', '.join(sorted(missing))}"))
            if extra:
                out.append(Problem(where, f"unknown {', '.join(sorted(extra))}"))
            continue
        if not isinstance(s["id"], str) or not SECTION_ID.fullmatch(s["id"]):
            out.append(Problem(f"{where}.id", f"expected lower-case letters and '_', got {s['id']!r}"))
        elif s["id"] in seen:
            out.append(Problem(f"{where}.id", f"{s['id']} appears twice"))
        seen.add(str(s["id"]))
        if not isinstance(s["title"], dict) or set(s["title"]) != set(LANGS) \
                or not all(isinstance(v, str) and v for v in s["title"].values()):
            out.append(Problem(f"{where}.title", "expected a non-empty title in pl and en"))
        if not isinstance(s["modes"], list) or not s["modes"] or not set(s["modes"]) <= set(MODES):
            out.append(Problem(f"{where}.modes", f"expected a non-empty list of {', '.join(MODES)}"))
        if not isinstance(s["source_kinds"], list) or not s["source_kinds"] \
                or not set(s["source_kinds"]) <= set(SOURCE_KINDS):
            out.append(Problem(f"{where}.source_kinds", f"expected a non-empty list of {', '.join(SOURCE_KINDS)}"))
        graph = s["graph"]
        if not isinstance(graph, dict) or set(graph) != set(GRAPH_KINDS):
            out.append(Problem(f"{where}.graph", f"expected exactly the fields {', '.join(GRAPH_KINDS)}"))
        else:
            for key, kind in GRAPH_KINDS.items():
                refs = graph[key]
                if not isinstance(refs, list):
                    out.append(Problem(f"{where}.graph.{key}", "expected a list"))
                    continue
                for j, ref in enumerate(refs):
                    if ref not in names[kind]:
                        out.append(Problem(f"{where}.graph.{key}[{j}]", f"{ref!r} is not in inventory.{kind}"))
            if not any(graph[k] for k in GRAPH_KINDS if isinstance(graph[k], list)):
                out.append(Problem(f"{where}.graph", "a section must come from at least one part of the graph"))
        for j, ref in enumerate(s["open_decisions"] if isinstance(s["open_decisions"], list) else []):
            if ref not in decision_ids:
                out.append(Problem(f"{where}.open_decisions[{j}]", f"{ref!r} is not among open_decisions"))
            used_decisions.add(ref)
    for unused in sorted(decision_ids - used_decisions):
        out.append(Problem("open_decisions", f"{unused} is not referred to by any section"))
    return out


# ------------------------------------------------------------------- card ----
def _date(value: Any) -> bool:
    if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
        return True
    if isinstance(value, str) and DATE.fullmatch(value):
        try:
            dt.date.fromisoformat(value)
            return True
        except ValueError:
            return False
    return False


def _repo_file(rel: Any, root: Path) -> tuple[Path | None, str | None]:
    """(path, None) for a repository-relative file that exists, else (None, reason)."""
    if not isinstance(rel, str) or not rel:
        return None, "expected a path relative to the repository root"
    if rel.startswith("/") or "\\" in rel or ".." in Path(rel).parts:
        return None, f"{rel!r} must be relative to the repository root, without '..'"
    path = root / rel
    if not path.is_file():
        return None, f"{rel} does not exist in the repository"
    return path, None


def headings(text: str) -> list[str]:
    """Text of every Markdown heading, outside fenced code."""
    text = re.sub(r"^```.*?^```", "", text, flags=re.MULTILINE | re.DOTALL)
    return [m.group(1).strip() for m in HEADING.finditer(text)]


def data_rows(path: Path) -> list[dict[str, str]]:
    """Rows of a CSV file, or the objects of a JSONL file with values as text."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".csv":
        return list(csv.DictReader(text.splitlines()))
    rows = []
    for line in text.splitlines():
        if line.strip():
            obj = json.loads(line)
            rows.append({k: v if isinstance(v, str) else json.dumps(v, sort_keys=True) for k, v in obj.items()})
    return rows


def _check_source(source: Any, where: str, kinds: list[str], root: Path,
                  cache: dict[Path, list[dict[str, str]]]) -> list[Problem]:
    if source is None:
        return [Problem(where, "required field is missing: every statement needs a file or a data row")]
    if not isinstance(source, dict):
        return [Problem(where, "expected a mapping with file (and heading) or data and row")]
    if "file" in source and "data" in source:
        return [Problem(where, "give either file or data, not both")]
    kind = "file" if "file" in source else "data" if "data" in source else None
    if kind is None:
        return [Problem(where, "expected file (and heading) or data and row")]
    if kind not in kinds:
        return [Problem(where, f"this section accepts sources of kind {', '.join(kinds)}, not {kind}")]
    allowed = FILE_SOURCE_FIELDS if kind == "file" else DATA_SOURCE_FIELDS
    extra = set(source) - allowed
    if extra:
        return [Problem(f"{where}.{min(extra)}", f"unknown field; a {kind} source has {', '.join(sorted(allowed))}")]
    path, reason = _repo_file(source[kind], root)
    if path is None:
        return [Problem(f"{where}.{kind}", str(reason))]
    if kind == "file":
        if "heading" not in source:
            return []
        heading = source["heading"]
        if path.suffix != ".md":
            return [Problem(f"{where}.heading", "a heading can be given only for a Markdown file")]
        if not isinstance(heading, str) or heading not in headings(path.read_text(encoding="utf-8")):
            return [Problem(f"{where}.heading", f"{heading!r} is not a heading of {source['file']}")]
        return []
    if path.suffix not in DATA_SUFFIXES:
        return [Problem(f"{where}.data", f"a data source must be a {' or '.join(DATA_SUFFIXES)} file")]
    row = source.get("row")
    if not isinstance(row, dict) or not row:
        return [Problem(f"{where}.row", "required: column values that pick exactly one row")]
    if path not in cache:
        cache[path] = data_rows(path)
    rows = cache[path]
    columns = set(rows[0]) if rows else set()
    unknown = sorted(set(row) - columns)
    if unknown:
        return [Problem(f"{where}.row.{unknown[0]}", f"{source['data']} has no column {unknown[0]!r}")]
    want = {k: str(v) for k, v in row.items()}
    hits = sum(all(r.get(k) == v for k, v in want.items()) for r in rows)
    if hits != 1:
        return [Problem(f"{where}.row", f"matches {hits} rows of {source['data']}, expected exactly one")]
    return []


def _check_statement(st: Any, where: str, section: dict, root: Path,
                     cache: dict[Path, list[dict[str, str]]]) -> list[Problem]:
    if not isinstance(st, dict):
        return [Problem(where, "expected a mapping")]
    out = [Problem(f"{where}.{k}", "unknown field") for k in sorted(set(st) - STATEMENT_FIELDS)]
    if not isinstance(st.get("text"), str) or not st["text"].strip():
        out.append(Problem(f"{where}.text", "required: the sentence as it appears on the card"))
    mode = st.get("mode")
    if mode is None:
        out.append(Problem(f"{where}.mode", f"required field is missing; use one of: {', '.join(MODES)}"))
    elif mode not in MODES:
        out.append(Problem(f"{where}.mode", f"value {mode!r} is not allowed; use one of: {', '.join(MODES)}"))
    elif mode not in section["modes"]:
        out.append(Problem(f"{where}.mode", f"mode {mode!r} is not allowed in section {section['id']}; "
                                            f"use one of: {', '.join(section['modes'])}"))
    out += _check_source(st.get("source"), f"{where}.source", section["source_kinds"], root, cache)
    current = st.get("current_state")
    if not isinstance(current, bool):
        out.append(Problem(f"{where}.current_state", "required: true for a statement about the current state, "
                                                     "else false"))
    elif current and not _date(st.get("as_of")):
        out.append(Problem(f"{where}.as_of", "a statement about the current state needs the date it was true on "
                                             "(YYYY-MM-DD)"))
    elif not current and "as_of" in st:
        out.append(Problem(f"{where}.as_of", "only a statement about the current state carries a date"))
    return out


def check_card(card: Any, model: dict | None = None, root: Path | None = None) -> list[Problem]:
    """Every problem of a card, empty when it follows the model and every source resolves."""
    root = root or ROOT
    model = model or load_model(root=root)
    if not isinstance(card, dict):
        return [Problem("(card)", "expected a mapping")]
    out = [Problem(k, "unknown field") for k in sorted(set(card) - CARD_FIELDS)]
    out += [Problem(k, "required field is missing") for k in sorted(CARD_FIELDS - set(card))]
    if "card_model" in card and card["card_model"] != model["version"]:
        out.append(Problem("card_model", f"expected {model['version']}, the version of {MODEL_PATH}"))
    if "experiment" in card and (not isinstance(card["experiment"], str) or not SLUG.fullmatch(card["experiment"])):
        out.append(Problem("experiment", f"expected an experiment slug, got {card['experiment']!r}"))
    hyp = card.get("hypothesis")
    if hyp is not None and (
            not isinstance(hyp, dict) or set(hyp) != {"slug", "version"} or not isinstance(hyp.get("slug"), str)
            or not SLUG.fullmatch(hyp["slug"]) or not isinstance(hyp.get("version"), int)
            or isinstance(hyp.get("version"), bool) or hyp["version"] < 1):
        out.append(Problem("hypothesis", "expected null or {slug, version} with a version of 1 or more"))
    if "lang" in card and card["lang"] not in LANGS:
        out.append(Problem("lang", f"value {card['lang']!r} is not allowed; use one of: {', '.join(LANGS)}"))
    if "title" in card and (not isinstance(card["title"], str) or not card["title"].strip()):
        out.append(Problem("title", "expected non-empty text"))
    sections = card.get("sections")
    if "sections" not in card:
        return out
    if not isinstance(sections, list):
        return out + [Problem("sections", "expected a list")]
    expected = [s["id"] for s in model["sections"]]
    by_id = {s["id"]: s for s in model["sections"]}
    given = [s.get("id") if isinstance(s, dict) else None for s in sections]
    for pos, sid in enumerate(expected):
        if sid not in given:
            out.append(Problem("sections", f"missing section {sid!r} (position {pos} of the model)"))
    cache: dict[Path, list[dict[str, str]]] = {}
    present = [sid for sid in given if sid in by_id]
    if present != [sid for sid in expected if sid in present]:
        out.append(Problem("sections", f"sections must follow the order of the model: {', '.join(expected)}"))
    for i, sec in enumerate(sections):
        where = f"sections[{i}]"
        if not isinstance(sec, dict):
            out.append(Problem(where, "expected a mapping"))
            continue
        out += [Problem(f"{where}.{k}", "unknown field") for k in sorted(set(sec) - SECTION_FIELDS)]
        sid = sec.get("id")
        if sid not in by_id:
            out.append(Problem(f"{where}.id", f"{sid!r} is not a section of the model; use one of: "
                                               f"{', '.join(expected)}"))
            continue
        if given.count(sid) > 1 and given.index(sid) != i:
            out.append(Problem(f"{where}.id", f"section {sid!r} appears twice"))
        statements = sec.get("statements")
        if not isinstance(statements, list) or not statements:
            out.append(Problem(f"{where}.statements", "a section needs at least one statement"))
            continue
        for j, st in enumerate(statements):
            out += _check_statement(st, f"{where}.statements[{j}]", by_id[sid], root, cache)
    return out


def check_file(path: Path, root: Path | None = None) -> list[Problem]:
    try:
        card = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return [Problem("(card)", f"YAML error: {type(exc).__name__}")]
    return check_card(card, root=root)


def main(argv: Sequence[str] | None = None) -> int:
    paths = list(argv if argv is not None else sys.argv[1:])
    if not paths:
        print("usage: python -m exocortex.lab.card_model CARD.yaml...", file=sys.stderr)
        return 2
    failed = 0
    for p in paths:
        problems = check_file(Path(p))
        for problem in problems:
            print(f"{p}: {problem}")
        if not problems:
            print(f"{p}: ok")
        failed += bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
