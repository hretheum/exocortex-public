# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Honesty check for the text of a reference project card (roadmap task F4.3).

The card compiler (F4.2) writes a card as a list of sentence records, one
per sentence, in the order they appear in the card (format: ``Sentence``).
This module checks that list with three rules and returns every
violation; nothing is fixed or dropped silently.

1. ``fact-source``: a sentence that reads as a fact must rest on a source
   in fact mode. "Reads as a fact" is decided by an injected mode
   classifier (``ModeClassifier``: the F3 classifier of fact, plan,
   requirement and hypothesis) or by the compiler's own label; either one
   saying "fact" is enough. A plan written in the present tense therefore
   fails even when the compiler labelled it a plan.
2. ``recorded-number``: every number in the text (digits or words, in
   English or Polish) must be a recorded result, within the rounding
   tolerance below. Recorded results are the published experiment files
   ``dowody/data/<slug>/metrics.csv`` and ``results.csv``.
3. ``dated-state``: a sentence about the current state ("works",
   "currently", "działa", "obecnie", ...) must carry a date: the record's
   ``date`` field or an explicit date in the text itself.

Rounding tolerance (rule 2). A number written with ``d`` decimals is an
honest rounding of a recorded value ``r`` when both hold:

* ``|r - t| <= 0.5 * 10**-d`` (``ROUNDING``): ``t`` is ``r`` rounded to the
  digits shown, half a unit of the last digit either way;
* ``|r - t| <= REL_TOLERANCE * |r|`` (5 %): coarse rounding cannot pass a
  different number, so "1" does not stand for 0.75 and "10%" does not
  stand for 0.0833.

A value equal to ``r`` (to ``EPS``) always passes. A number followed by
"%", "percent", "procent", "pp", "percentage points" or "punktów
procentowych" is compared both as written and divided by 100, because the
lab records shares as fractions (0.0833 is written "8.3%").

Not counted as numbers: digits glued to a letter (F3, G1, v1, qwen3.6),
anything inside backticks, a URL or a Markdown link target, paths and run
labels (``run-2026-09-29-1``), dates (ISO, "30 September 2026", "września
2026", "in 2026"), and the word "one"/"jeden" on its own (it is far more
often a pronoun than a count). Every other number counts, including small
ones such as "two models": a count on a card must be a recorded count.

    exocortex lab honesty card.jsonl --data dowody/data/intent-vs-fact

The record format, how the compiler should fill it, and the full rule
reference: docs/guides/card-honesty-check.md.

Exit code 0 when the card has no violations, 1 when it has some, 2 when
the input is invalid.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from exocortex.lab.extractor import MODES

RULE_FACT_SOURCE = "fact-source"
RULE_RECORDED_NUMBER = "recorded-number"
RULE_DATED_STATE = "dated-state"
RULES = (RULE_FACT_SOURCE, RULE_RECORDED_NUMBER, RULE_DATED_STATE)

ROUNDING = 0.5  # half a unit of the last digit shown
REL_TOLERANCE = 0.05  # and at most 5 % away from the recorded value
EPS = 1e-9


# -- records ------------------------------------------------------------------------

@dataclass(frozen=True)
class Sentence:
    """One sentence of a card, as the card compiler (F4.2) writes it.

    text         the sentence exactly as it appears on the card
    mode         the mode the compiler meant: fact, plan, requirement or
                 hypothesis (``extractor.MODES``)
    source_ref   where the sentence comes from: a repository path, with
                 ``#<result_id>`` when it rests on one recorded result
                 (``dowody/data/toy-length/metrics.csv#toy-length/run-1/a/mean_chars``);
                 empty only for sentences that state nothing checkable
    source_mode  the mode of the source itself: a measured result, a
                 frozen hypothesis card and a gate decision are "fact",
                 "hypothesis" and "fact"; a plan in a phase document is
                 "plan"; None when there is no source
    numbers      the recorded values the compiler put into the text,
                 unrounded, in the order they appear (may be empty)
    date         ISO date (YYYY-MM-DD) the sentence is true as of, or None
    """

    text: str
    mode: str
    source_ref: str | None = None
    source_mode: str | None = None
    numbers: tuple[float, ...] = ()
    date: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("text must be a non-empty string")
        if self.mode not in MODES:
            raise ValueError(f"mode must be one of {', '.join(MODES)}, not {self.mode!r}")
        if self.source_mode is not None and self.source_mode not in MODES:
            raise ValueError(f"source_mode must be one of {', '.join(MODES)} or null, not {self.source_mode!r}")
        if self.source_mode is not None and not self.source_ref:
            raise ValueError("source_mode is set but source_ref is empty")
        nums = tuple(self.numbers)
        for n in nums:
            if isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n):
                raise ValueError(f"numbers must be finite numbers, not {n!r}")
        object.__setattr__(self, "numbers", tuple(float(n) for n in nums))
        if self.date is not None:
            try:
                dt.date.fromisoformat(self.date)
            except (TypeError, ValueError):
                raise ValueError(f"date must be an ISO date (YYYY-MM-DD), not {self.date!r}") from None

    @classmethod
    def from_dict(cls, d: Mapping) -> Sentence:
        unknown = set(d) - {"text", "mode", "source_ref", "source_mode", "numbers", "date"}
        if unknown:
            raise ValueError(f"unknown fields: {', '.join(sorted(unknown))}")
        return cls(text=d.get("text", ""), mode=d.get("mode", ""), source_ref=d.get("source_ref") or None,
                   source_mode=d.get("source_mode"), numbers=tuple(d.get("numbers") or ()), date=d.get("date"))


@dataclass(frozen=True)
class Violation:
    sentence: int  # 1-based position in the card
    rule: str
    message: str


class ModeClassifier(Protocol):
    """Reads one sentence and says in which mode it presents its statement."""

    def classify(self, text: str) -> str:
        """One of ``extractor.MODES``."""
        ...


@dataclass
class ModeTable:
    """A classifier whose answers were computed beforehand (text -> mode).

    The CLI uses it with the output of a separate run of the F3 classifier;
    sentences missing from the table fall back to ``default``.
    """

    modes: dict[str, str] = field(default_factory=dict)
    default: dict[str, str] = field(default_factory=dict)

    def classify(self, text: str) -> str:
        return self.modes.get(text) or self.default.get(text) or "fact"


# -- recorded results ---------------------------------------------------------------

@dataclass
class Recorded:
    """Numbers of the published experiment files, by result id and all together."""

    by_result: dict[str, list[float]] = field(default_factory=dict)

    def add(self, result_id: str, values: Iterable[float]) -> None:
        self.by_result.setdefault(result_id, []).extend(values)

    def all_values(self) -> list[float]:
        return [v for vs in self.by_result.values() for v in vs]

    def scope(self, source_ref: str | None) -> tuple[list[float] | None, str | None]:
        """Values a sentence may use: those of its result, else every recorded value.

        Returns (values, problem); values is None when the reference names a
        result that is not recorded.
        """
        if source_ref and "#" in source_ref:
            rid = source_ref.split("#", 1)[1]
            if rid in self.by_result:
                return self.by_result[rid], None
            return None, f"the source names result {rid!r}, which is not in the recorded results"
        return self.all_values(), None


def _num(s: str | None) -> float | None:
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def _detail_numbers(raw: str) -> list[float]:
    try:
        doc = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return []
    out: list[float] = []
    stack = [doc]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            stack.extend(x.values())
        elif isinstance(x, list):
            stack.extend(x)
        elif isinstance(x, (int, float)) and not isinstance(x, bool):
            out.append(float(x))
    return out


def load_recorded(paths: Iterable[Path]) -> Recorded:
    """Read metrics.csv and results.csv of experiment folders.

    Each path is an experiment folder (``dowody/data/<slug>``) or a folder of
    them (``dowody/data``). Recorded per metric row (``result_id``): value,
    ci_low, ci_high, n and every number in ``details``. Recorded per run
    (``<slug>/<run_id>``) and per run and configuration
    (``<slug>/<run_id>/<config>``) of results.csv: the number of results,
    of successful ones and of failed ones.
    """
    rec = Recorded()
    folders: list[Path] = []
    for p in paths:
        p = Path(p)
        if (p / "metrics.csv").exists() or (p / "results.csv").exists():
            folders.append(p)
        elif p.is_dir():
            folders.extend(sorted(q for q in p.iterdir() if (q / "metrics.csv").exists() or (q / "results.csv").exists()))
        else:
            raise FileNotFoundError(f"{p}: no metrics.csv or results.csv")
    for folder in folders:
        slug = folder.name
        if (folder / "metrics.csv").exists():
            with (folder / "metrics.csv").open(encoding="utf-8", newline="") as fh:
                for row in csv.DictReader(fh):
                    vals = [v for v in (_num(row.get(k)) for k in ("value", "ci_low", "ci_high", "n")) if v is not None]
                    rec.add(row["result_id"], vals + _detail_numbers(row.get("details", "")))
        if (folder / "results.csv").exists():
            counts: dict[str, list[int]] = {}
            with (folder / "results.csv").open(encoding="utf-8", newline="") as fh:
                for row in csv.DictReader(fh):
                    ok = (row.get("ok") or "").strip().lower() == "true"
                    for key in (f"{slug}/{row['run_id']}", f"{slug}/{row['run_id']}/{row['config']}"):
                        c = counts.setdefault(key, [0, 0])
                        c[0] += 1
                        c[1] += ok
            for key, (total, good) in counts.items():
                rec.add(key, [float(total), float(good), float(total - good)])
    return rec


# -- numbers in text ----------------------------------------------------------------

@dataclass(frozen=True)
class Number:
    shown: str  # as written
    candidates: tuple[tuple[float, int], ...]  # (value, digits after the decimal mark) per reading
    percent: bool  # followed by %, "percent", "pp", ...

    def readings(self) -> list[tuple[float, int]]:
        """Every value the text may mean; a percentage also as a fraction (8.3% -> 0.083)."""
        out = list(self.candidates)
        if self.percent:
            out += [(v / 100.0, d + 2) for v, d in self.candidates]
        return out


_MONTHS = [
    "january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
    "november", "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    "styczeń", "stycznia", "luty", "lutego", "marzec", "marca", "kwiecień", "kwietnia", "maj", "maja",
    "czerwiec", "czerwca", "lipiec", "lipca", "sierpień", "sierpnia", "wrzesień", "września",
    "październik", "października", "listopad", "listopada", "grudzień", "grudnia",
]
_MONTH = r"(?:" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\.?"
_FULL_DATES = [  # a date a reader can check: day or month, and the year
    r"\b\d{4}-\d{2}-\d{2}\b",
    r"\b\d{1,2}\.\d{1,2}\.\d{4}\b",
    rf"\b\d{{1,2}}\s+{_MONTH}\s+\d{{4}}\b",
    rf"\b{_MONTH}\s+\d{{1,2}},?\s+\d{{4}}\b",
    rf"\b{_MONTH}\s+\d{{4}}\b",
]
_DATE_PATTERNS = _FULL_DATES + [  # also not numbers: a bare year in a time phrase
    r"\b(?:in|since|by|until|w|od|do)\s+(?:19|20)\d{2}\b",
    r"\b(?:19|20)\d{2}\s*(?:r\.|roku)",
]
_DATE_RE = re.compile("|".join(_DATE_PATTERNS), re.IGNORECASE)
_STRIP_RE = re.compile(
    r"`[^`]*`"  # code
    r"|\]\([^)]*\)"  # Markdown link target
    r"|https?://\S+"  # URL
    r"|\S*[/_]\S*"  # paths, ids with underscores
    r"|\S*[A-Za-zÀ-ž]-\d\S*",  # run-2026-09-29-1
)
_PERCENT = r"(?:\s?%|\s?pp\b|\s?p\.\s?p\.|\s+(?:percent|per\s+cent|percentage\s+points?|procent\w*|punkt\w*\s+procentow\w*))"
_DIGITS_RE = re.compile(
    r"(?<![\w.,])(?P<sign>[-−–]?)(?P<num>\d{1,3}(?:[\u00a0\u202f]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
    rf"(?P<pct>{_PERCENT})?(?![\w])",
    re.IGNORECASE,
)

_RANGE_PCT_RE = re.compile(r"\s?[-–]\s?\d+(?:[.,]\d+)?" + _PERCENT, re.IGNORECASE)

_WORDS = {
    # English
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
    "thousand": 1000, "half": 0.5,
    # Polish, with the inflected forms a card is likely to use
    "jeden": 1, "jedna": 1, "jedno": 1, "jednego": 1,
    "dwa": 2, "dwie": 2, "dwóch": 2, "dwoma": 2, "dwu": 2, "dwoje": 2,
    "trzy": 3, "trzech": 3, "trzema": 3, "cztery": 4, "czterech": 4, "czterema": 4,
    "pięć": 5, "pięciu": 5, "sześć": 6, "sześciu": 6, "siedem": 7, "siedmiu": 7, "osiem": 8, "ośmiu": 8,
    "dziewięć": 9, "dziewięciu": 9, "dziesięć": 10, "dziesięciu": 10,
    "jedenaście": 11, "jedenastu": 11, "dwanaście": 12, "dwunastu": 12, "trzynaście": 13, "trzynastu": 13,
    "czternaście": 14, "czternastu": 14, "piętnaście": 15, "piętnastu": 15, "szesnaście": 16,
    "szesnastu": 16, "siedemnaście": 17, "siedemnastu": 17, "osiemnaście": 18, "osiemnastu": 18,
    "dziewiętnaście": 19, "dziewiętnastu": 19, "dwadzieścia": 20, "dwudziestu": 20,
    "trzydzieści": 30, "trzydziestu": 30, "czterdzieści": 40, "czterdziestu": 40,
    "pięćdziesiąt": 50, "pięćdziesięciu": 50, "sześćdziesiąt": 60, "sześćdziesięciu": 60,
    "siedemdziesiąt": 70, "siedemdziesięciu": 70, "osiemdziesiąt": 80, "osiemdziesięciu": 80,
    "dziewięćdziesiąt": 90, "dziewięćdziesięciu": 90, "sto": 100, "stu": 100,
    "tysiąc": 1000, "tysiące": 1000, "tysięcy": 1000,
    "połowa": 0.5, "połowę": 0.5, "połowy": 0.5, "połowie": 0.5,
}
_ALONE_IGNORED = {"one", "jeden", "jedna", "jedno", "jednego"}  # mostly pronouns or articles
_WORD_RE = re.compile(
    r"(?<!\w)(?P<words>(?:" + "|".join(sorted(_WORDS, key=len, reverse=True)) + r")"
    r"(?:(?:\s+|-)(?:" + "|".join(sorted(_WORDS, key=len, reverse=True)) + r"))*)"
    rf"(?P<pct>{_PERCENT})?(?!\w)",
    re.IGNORECASE,
)


def _words_value(words: str) -> float | None:
    tokens = [t for t in re.split(r"\s+|-", words.lower()) if t]
    if len(tokens) == 1 and tokens[0] in _ALONE_IGNORED:
        return None
    total, current = 0.0, 0.0
    for t in tokens:
        v = _WORDS[t]
        if v in (100, 1000):
            current = (current or 1) * v
            if v == 1000:
                total, current = total + current, 0.0
        else:
            current += v
    return total + current


def _blank(text: str, pattern: re.Pattern[str]) -> str:
    return pattern.sub(lambda m: " " * len(m.group(0)), text)


def numbers_in(text: str) -> list[Number]:
    """Every number a reader would take from the sentence (see the module docstring)."""
    clean = _blank(_blank(text, _STRIP_RE), _DATE_RE)
    found: list[Number] = []
    for m in _DIGITS_RE.finditer(clean):
        raw = re.sub(r"[\u00a0\u202f]", "", m.group("num"))
        sign = -1.0 if m.group("sign") and (m.start() == 0 or clean[m.start() - 1] in " (\t") else 1.0
        if "," in raw and "." not in raw:
            whole, frac = raw.split(",")
            readings = [(float(f"{whole}.{frac}"), len(frac))]  # Polish decimal comma
            if len(frac) == 3:  # or an English thousands separator
                readings.append((float(whole + frac), 0))
        else:
            readings = [(float(raw), len(raw.split(".")[1]) if "." in raw else 0)]
        # "1.5–35.4%": the percent sign after a range covers its first number too
        pct = bool(m.group("pct")) or bool(_RANGE_PCT_RE.match(clean, m.end()))
        found.append(Number(m.group(0).strip(), tuple((sign * v, d) for v, d in readings), pct))
    for m in _WORD_RE.finditer(clean):
        v = _words_value(m.group("words"))
        if v is not None:
            found.append(Number(m.group(0).strip(), ((v, 0 if v == int(v) else 1),), bool(m.group("pct"))))
    return found


def matches(shown: float, decimals: int, recorded: float) -> bool:
    """Is ``shown`` (with ``decimals`` digits after the mark) an honest rounding of ``recorded``?"""
    diff = abs(recorded - shown)
    if diff <= EPS * max(1.0, abs(recorded)):
        return True
    return diff <= ROUNDING * 10.0 ** -decimals + EPS and diff <= REL_TOLERANCE * abs(recorded)


def number_matches(n: Number, recorded: Iterable[float]) -> bool:
    values = list(recorded)
    return any(matches(s, d, r) for s, d in n.readings() for r in values)


# -- current state ------------------------------------------------------------------

_STATE_WORDS = [
    # English
    r"works", r"working", r"currently", r"at present", r"presently", r"right now", r"as of now",
    r"nowadays", r"is running", r"are running", r"in production", r"is live", r"is deployed",
    r"are deployed", r"today",
    # Polish
    r"działa(?:ją|jący|jąca|jące)?", r"obecnie", r"aktualnie", r"teraz", r"w tej chwili", r"na dziś",
    r"dzisiaj", r"dziś", r"jest wdrożon\w*", r"są wdrożon\w*", r"na produkcji",
]
_NOT_STATE = re.compile(r"\b(?:related|prior|previous|earlier|these|those|cited|other)\s+works\b", re.IGNORECASE)
_STATE_RE = re.compile(r"(?<![\w-])(?:" + "|".join(_STATE_WORDS) + r")(?![\w-])", re.IGNORECASE)


def state_words(text: str) -> list[str]:
    """Words saying the sentence is about the current state (quotation marks do not exempt them)."""
    return [m.group(0) for m in _STATE_RE.finditer(_blank(text, _NOT_STATE))]


_FULL_DATE_RE = re.compile("|".join(_FULL_DATES), re.IGNORECASE)


def has_date(text: str) -> bool:
    return bool(_FULL_DATE_RE.search(text))


# -- the check ----------------------------------------------------------------------

def check(card: Sequence[Sentence], classifier: ModeClassifier, recorded: Recorded) -> list[Violation]:
    """Every violation of the three rules, in card order."""
    out: list[Violation] = []
    for i, s in enumerate(card, start=1):
        # 1. fact-source
        read_as = classifier.classify(s.text)
        if read_as not in MODES:
            raise ValueError(f"sentence {i}: the classifier returned {read_as!r}, not one of {', '.join(MODES)}")
        if "fact" in (read_as, s.mode) and s.source_mode != "fact":
            why = "reads as a fact" if read_as == "fact" else "is labelled a fact"
            if s.mode != "fact" and read_as == "fact":
                why += f" although the compiler labelled it {s.mode}"
            src = f"its source is in {s.source_mode} mode" if s.source_mode else "it has no source"
            out.append(Violation(i, RULE_FACT_SOURCE, f"the sentence {why}, but {src}"))

        # 2. recorded-number
        shown = numbers_in(s.text)
        if shown or s.numbers:
            pool, problem = recorded.scope(s.source_ref)
            if pool is None:
                out.append(Violation(i, RULE_RECORDED_NUMBER, problem or "unknown source"))
            else:
                for n in shown:
                    if not number_matches(n, pool):
                        out.append(Violation(i, RULE_RECORDED_NUMBER,
                                             f"{n.shown!r} does not match any recorded result"
                                             + (f" of {s.source_ref}" if s.source_ref and "#" in s.source_ref else "")))
                for v in s.numbers:
                    if not any(matches(v, 12, r) for r in pool):
                        out.append(Violation(i, RULE_RECORDED_NUMBER, f"declared number {v!r} is not a recorded value"))
                    elif not any(number_matches(n, [v]) for n in shown):
                        out.append(Violation(i, RULE_RECORDED_NUMBER, f"declared number {v!r} does not appear in the text"))

        # 3. dated-state
        words = state_words(s.text)
        if words and not s.date and not has_date(s.text):
            out.append(Violation(i, RULE_DATED_STATE,
                                 f"{words[0]!r} describes the current state, but the sentence has no date"))
    return out


# -- files and command line ---------------------------------------------------------

def read_card(path: Path) -> list[Sentence]:
    """A card as JSON Lines (one record per line) or as one JSON list."""
    text = Path(path).read_text(encoding="utf-8")
    if text.lstrip().startswith("["):
        raw = json.loads(text)
    else:
        raw = [json.loads(line) for line in text.splitlines() if line.strip()]
    card = []
    for i, d in enumerate(raw, start=1):
        try:
            card.append(Sentence.from_dict(d))
        except (ValueError, TypeError, AttributeError) as e:
            raise ValueError(f"sentence {i}: {e}") from None
    return card


def read_modes(path: Path) -> dict[str, str]:
    """Classifier output as JSON Lines: {"text": ..., "mode": ...} per sentence."""
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            if d.get("mode") not in MODES:
                raise ValueError(f"{path}: mode {d.get('mode')!r} is not one of {', '.join(MODES)}")
            out[d["text"]] = d["mode"]
    return out


def run(card_path: Path, data: Sequence[Path], modes_path: Path | None = None) -> tuple[dict, int]:
    """The ``exocortex lab honesty`` command: (report, exit code)."""
    try:
        card = read_card(card_path)
        modes = read_modes(modes_path) if modes_path else {}
        recorded = load_recorded(data)
    except (OSError, ValueError) as e:
        return {"command": "honesty", "card": str(card_path), "error": str(e)}, 2
    classifier = ModeTable(modes, {s.text: s.mode for s in card})
    violations = check(card, classifier, recorded)
    report = {
        "command": "honesty",
        "card": str(card_path),
        "sentences": len(card),
        "classifier": "precomputed" if modes_path else "compiler labels only",
        "recorded_results": len(recorded.by_result),
        "violations": [{"sentence": v.sentence, "rule": v.rule, "message": v.message} for v in violations],
    }
    return report, 1 if violations else 0
