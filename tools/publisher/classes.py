"""Publication classes (roadmap task F1.11).

Every path the publisher handles gets a class from the list below. The list
lives in the gate image and changes only through a commit that passes CI:
nothing in the vault, in the lab's output folder or in a file header can
change the class of a file. Classification reads the path relative to the
documents folder and the file size, never the content.

| Class      | Paths                                                                 |
|------------|-----------------------------------------------------------------------|
| docs       | pl/ and en/: DOCS_FILES, roadmap/**, templates/**, img/**             |
| experiment | pl/ and en/: experiments/<slug>/**; data/<slug>/**; prereg.jsonl      |
| generated  | pl/ and en/: generated/**                                             |
| unknown    | anything else                                                         |

The design (dowody/*/05-publication-design.md) lists the documents 01 to 05;
06-interactive-lab-design.md was written later and is listed here as well.

Fail-closed: a path that matches no rule exactly, a documentation path with
an extension other than .md or .svg, a documentation file over
DOCS_MAX_BYTES or of unknown size, and any error while classifying all give
the strictest class, ``unknown``. The folders experiments/, data/,
generated/ and the registry are never documentation.

Each class has a set of checks (roadmap task F1.13, CHECKS below).
Documentation skips the semantic comparison, the review page and paragraph
approvals. It keeps the literal scanner at the blocking level, and scanner
warnings only go to the run log. It also keeps the machine translation
rule, parity, the header schemas and the language check. Every other class
gets every check.
"""

from __future__ import annotations

from pathlib import Path

DOCS, EXPERIMENT, GENERATED, UNKNOWN = "docs", "experiment", "generated", "unknown"
CLASSES = (DOCS, EXPERIMENT, GENERATED, UNKNOWN)

LANGS = ("pl", "en")
REGISTRY = "prereg.jsonl"
DOCS_FILES = frozenset({"01-cycle.md", "02-roadmap.md", "03-progress.md", "04-how-it-works.md",
                        "05-publication-design.md", "06-interactive-lab-design.md"})
DOCS_DIRS = frozenset({"roadmap", "templates", "img"})
DOCS_EXTENSIONS = (".md", ".svg")
DOCS_MAX_BYTES = 128 * 1024  # a larger file is not held for its size; it gets the checks of the unknown class


def _parts(rel: str) -> list[str] | None:
    """The parts of a clean relative path, or None for anything unusual."""
    if not rel or rel.startswith("/") or "\\" in rel:
        return None
    parts = rel.split("/")
    if any(not p or p in (".", "..") or p.startswith(".") for p in parts):
        return None
    return parts


def _classify(rel: str, size: int | None) -> str:
    parts = _parts(rel)
    if parts is None:
        return UNKNOWN
    if parts == [REGISTRY]:
        return EXPERIMENT
    if parts[0] == "data":
        return EXPERIMENT if len(parts) >= 3 else UNKNOWN  # data/<slug>/<file>
    if parts[0] not in LANGS or len(parts) < 2:
        return UNKNOWN
    rest = parts[1:]
    if rest[0] == "experiments":
        return EXPERIMENT if len(rest) >= 3 else UNKNOWN   # experiments/<slug>/<file>
    if rest[0] == "generated":
        return GENERATED if len(rest) >= 2 else UNKNOWN
    listed = (len(rest) == 1 and rest[0] in DOCS_FILES) or (len(rest) >= 2 and rest[0] in DOCS_DIRS)
    if not listed or not rest[-1].endswith(DOCS_EXTENSIONS):
        return UNKNOWN
    if type(size) is not int or not 0 <= size <= DOCS_MAX_BYTES:
        return UNKNOWN
    return DOCS


# Checks a class can have.
LITERAL_BLOCK = "literal-block"   # leakgate findings of the blocking tier hold the file
LITERAL_WARN = "literal-warn"     # leakgate warnings hold it too; without this they only go to the run log
TRANSLATION = "translation"       # a file marked `translation: machine` waits for a person
SEMANTIC = "semantic"             # simcheck, the review page and paragraph approvals
PARITY = "parity"                 # the pl/en parity check
SCHEMA = "schema"                 # the header schemas
LANGUAGE = "language"             # the language check (humanlint)
ALL_CHECKS = frozenset({LITERAL_BLOCK, LITERAL_WARN, TRANSLATION, SEMANTIC, PARITY, SCHEMA, LANGUAGE})

# Owner's decision (2026-09-29): documentation drops only the semantic comparison and
# scanner warnings. To exempt it from every check, replace its line with
# `DOCS: frozenset(),`. Read the risk in deploy/gate/README.md first.
CHECKS: dict[str, frozenset[str]] = {
    DOCS: frozenset({LITERAL_BLOCK, TRANSLATION, PARITY, SCHEMA, LANGUAGE}),
    EXPERIMENT: ALL_CHECKS,
    GENERATED: ALL_CHECKS,
    UNKNOWN: ALL_CHECKS,
}


def checks_for(cls: str) -> frozenset[str]:
    """The checks of a class; a class missing from the table gets every check."""
    return CHECKS.get(cls, ALL_CHECKS)


def classify(rel: str, size: int | None) -> str:
    """Class of the file at ``rel`` (relative to the documents folder) with ``size`` bytes (None: unknown)."""
    try:
        return _classify(rel, size)
    except Exception:  # noqa: BLE001 - any doubt means the strictest class
        return UNKNOWN


def experiment_slug(rel: str) -> str | None:
    """The experiment a path belongs to: ``<slug>`` of pl|en/experiments/<slug>/** or data/<slug>/**."""
    parts = _parts(rel) if isinstance(rel, str) else None
    if parts and parts[0] == "data" and len(parts) >= 3:
        return parts[1]
    if parts and parts[0] in LANGS and len(parts) >= 4 and parts[1] == "experiments":
        return parts[2]
    return None


def classify_file(rel: str, path: Path) -> str:
    """Class of ``rel``, sized from the file at ``path`` (a missing file has unknown size)."""
    try:
        size = path.stat().st_size if path.is_file() else None
    except OSError:
        size = None
    return classify(rel, size)
