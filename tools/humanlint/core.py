"""Heuristic check for habits of machine-written prose.

Works on Markdown. Front matter, code blocks, inline code, tables and link
targets are ignored. The result is per file: pattern matches with line
numbers, the measured rates, and which thresholds were crossed.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import yaml

HERE = Path(__file__).parent
FRONT = re.compile(r"\A---\n.*?\n---\n", re.S)
FENCE = re.compile(r"^```.*?^```", re.S | re.M)
INLINE_CODE = re.compile(r"`[^`\n]*`")
LINK_TARGET = re.compile(r"\]\([^)]*\)")
WORD = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*", re.U)
BOLD = re.compile(r"\*\*[^*\n]+\*\*|__[^_\n]+__")
DASH = re.compile(r"\s[—–]\s")
HEADING = re.compile(r"^#{1,6}\s+(.*)$")
EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F02F\U0001F0A0-\U0001F0FF\U0001F100-\U0001F1FF]"
)
# Articles, pronouns and one-letter prepositions start many ordinary sentences;
# they are not counted as a repeated opening.
NEUTRAL_STARTS = {"the", "a", "an", "it", "this", "we", "i", "in", "w", "z", "i", "a", "to", "na", "do", "nie"}
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ\"„])")


@dataclass
class Pattern:
    lang: str
    regex: re.Pattern
    reason: str


@dataclass
class Hit:
    line: int
    rule: str
    detail: str


@dataclass
class FileReport:
    path: str
    words: int = 0
    hits: list[Hit] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    exempt: str | None = None

    @property
    def ok(self) -> bool:
        return not self.failures or self.exempt is not None


def load_patterns(path: Path = HERE / "patterns.yaml") -> list[Pattern]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Pattern(p["lang"], re.compile(p["pattern"], re.I | re.M), p["reason"]) for p in raw]


def load_config(path: Path = HERE / "config.yaml") -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def detect_lang(path: Path, text: str) -> str:
    parts = set(path.parts)
    if "pl" in parts:
        return "pl"
    if "en" in parts:
        return "en"
    m = re.search(r"^lang:\s*(\w+)", text, re.M)
    if m:
        return m.group(1)
    return "pl" if re.search(r"[ąćęłńśźż]", text) else "en"


def prose_lines(text: str) -> list[tuple[int, str]]:
    """(line number, text) for lines that are running prose or headings."""
    m = FRONT.match(text)
    offset = text[: m.end()].count("\n") if m else 0
    body = text[m.end():] if m else text
    body = FENCE.sub(lambda mm: "\n" * mm.group(0).count("\n"), body)
    out = []
    for i, line in enumerate(body.split("\n"), start=offset + 1):
        if line.lstrip().startswith("|"):
            continue
        line = INLINE_CODE.sub(" ", line)
        line = LINK_TARGET.sub("]", line)
        out.append((i, line))
    return out


def analyse(path: Path, text: str, patterns: list[Pattern], cfg: dict) -> FileReport:
    rep = FileReport(str(path))
    lang = detect_lang(path, text)
    lines = prose_lines(text)
    prose = "\n".join(line for _, line in lines if not HEADING.match(line))
    words = WORD.findall(prose)
    rep.words = len(words)

    for no, line in lines:
        for p in patterns:
            if p.lang not in (lang, "any"):
                continue
            for mm in p.regex.finditer(line):
                rep.hits.append(Hit(no, "pattern", f"{mm.group(0).strip()!r}: {p.reason}"))
        h = HEADING.match(line)
        if h and h.group(1).rstrip().endswith("?"):
            rep.hits.append(Hit(no, "question_heading", "heading phrased as a question"))
        for e in EMOJI.findall(line):
            rep.hits.append(Hit(no, "emoji", f"U+{ord(e):04X}"))

    bold_mid = 0
    for _, line in lines:
        stripped = re.sub(r"^\s*(?:[-*+]|\d+[.)])?\s*", "", line)
        for mm in BOLD.finditer(stripped):
            if mm.start() > 0:  # a bold lead-in at the start of a line or list item is fine
                bold_mid += 1
    dashes = sum(len(DASH.findall(line)) for _, line in lines)
    sentences = [s for s in SENTENCE_SPLIT.split(re.sub(r"\s+", " ", prose)) if len(WORD.findall(s)) >= 3]
    starts = Counter(WORD.findall(s)[0].lower() for s in sentences if WORD.findall(s))
    for w in NEUTRAL_STARTS:
        starts.pop(w, None)
    per_k = 1000 / max(rep.words, 1)
    pattern_hits = sum(1 for h in rep.hits if h.rule == "pattern")
    rep.metrics = {
        "hits_per_1000": round(pattern_hits * per_k, 2),
        "bold_mid_per_1000": round(bold_mid * per_k, 2),
        "dash_per_1000": round(dashes * per_k, 2),
        "same_start_share": round(max(starts.values()) / len(sentences), 3) if sentences and starts else 0.0,
        "sentences": len(sentences),
        "emoji": sum(1 for h in rep.hits if h.rule == "emoji"),
        "question_headings": sum(1 for h in rep.hits if h.rule == "question_heading"),
    }
    m = rep.metrics
    if m["emoji"] > cfg["max_emoji"]:
        rep.failures.append(f"emoji: {m['emoji']} > {cfg['max_emoji']}")
    if m["question_headings"] > cfg["max_question_headings"]:
        rep.failures.append(f"question headings: {m['question_headings']} > {cfg['max_question_headings']}")
    if rep.words >= cfg["min_words"]:
        for key in ("hits_per_1000", "bold_mid_per_1000", "dash_per_1000"):
            if m[key] > cfg[f"max_{key}"]:
                rep.failures.append(f"{key}: {m[key]} > {cfg[f'max_{key}']}")
        if m["sentences"] >= cfg["min_sentences_for_share"] and m["same_start_share"] > cfg["max_same_start_share"]:
            rep.failures.append(f"same_start_share: {m['same_start_share']} > {cfg['max_same_start_share']}")
    return rep


def load_exceptions(root: Path) -> dict[str, str]:
    """``humanlint-exceptions.yaml`` in the scanned root: {relative path: reason}."""
    f = root / "humanlint-exceptions.yaml"
    if not f.exists():
        return {}
    data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    return {k: str(v) for k, v in data.items() if v}


def run(paths: list[Path], cfg: dict | None = None, patterns: list[Pattern] | None = None) -> list[FileReport]:
    cfg = cfg or load_config()
    patterns = patterns or load_patterns()
    reports = []
    for base in paths:
        root = base if base.is_dir() else base.parent
        exceptions = load_exceptions(root)
        files = sorted(base.rglob("*.md")) if base.is_dir() else [base]
        for f in files:
            rep = analyse(f, f.read_text(encoding="utf-8"), patterns, cfg)
            rel = f.relative_to(root).as_posix()
            rep.path = str(f)
            rep.exempt = exceptions.get(rel)
            reports.append(rep)
    return reports
