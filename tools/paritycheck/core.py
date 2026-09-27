"""Structural comparison of Polish and English document pairs.

Layout: ``<root>/pl/<path>`` and ``<root>/en/<path>`` with identical file
names. Files directly in ``<root>`` (the bilingual README, the glossary) are
not paired. Only Markdown files are compared.

For each pair the check compares what a translation must not change:
front matter keys ``id``, ``status`` and ``depends_on``; the sequence of
heading levels; the set of numbers in the body; the set of link targets;
the shape of every table. It does not judge the quality of the translation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import yaml

LANGS = ("pl", "en")
FRONT_KEYS = ("id", "status", "depends_on")

FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.S)
HEADING = re.compile(r"^(#{1,6})\s+\S", re.M)
FENCE = re.compile(r"^```.*?^```", re.S | re.M)
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
IMAGE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")
# 11 613 (Polish thousands), 0,40 / 0.40, 2026-09-27, F1.7
NUMBER = re.compile(r"\d{1,3}(?:[   ]\d{3})+(?![\d])|\d+(?:[.,]\d+)*")
WIKILINK = re.compile(r"\[\[[^\]]+\]\]")


@dataclass
class Doc:
    front: dict
    headings: list[int]
    numbers: set[str]
    links: set[str]
    tables: list[tuple[int, int]]
    wikilinks: int


@dataclass
class Problem:
    path: str
    check: str
    detail: str

    def __str__(self) -> str:
        return f"{self.path}: {self.check}: {self.detail}"


@dataclass
class Result:
    pairs: int = 0
    problems: list[Problem] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def held(self) -> set[str]:
        """Relative paths (without language prefix) that must not be published."""
        return {p.path for p in self.problems}


def _strip_code(text: str) -> str:
    text = FENCE.sub("", text)
    return re.sub(r"`[^`\n]*`", "", text)


def _canonical_number(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    return digits.lstrip("0") or "0"


def _tables(body: str) -> list[tuple[int, int]]:
    shapes = []
    rows: list[str] = []
    for line in body.splitlines() + [""]:
        if line.lstrip().startswith("|"):
            rows.append(line)
            continue
        if rows:
            data = [r for r in rows if not re.fullmatch(r"\s*\|?[\s:|-]+\|?\s*", r)]
            cols = rows[0].strip().strip("|").count("|") + 1
            shapes.append((len(data), cols))
            rows = []
    return shapes


def parse(text: str) -> Doc:
    front: dict = {}
    m = FRONT.match(text)
    body = text
    if m:
        front = yaml.safe_load(m.group(1)) or {}
        body = text[m.end():]
    plain = _strip_code(body)
    links = {t.split("#", 1)[0] for t in LINK.findall(plain)} | set(IMAGE.findall(plain))
    links.discard("")
    return Doc(
        front=front,
        headings=[len(h) for h in HEADING.findall(plain)],
        numbers={_canonical_number(n) for n in NUMBER.findall(LINK.sub(" ", plain))},
        links=links,
        tables=_tables(plain),
        wikilinks=len(WIKILINK.findall(plain)),
    )


def compare(rel: str, pl: Doc, en: Doc, pl_name: str, en_name: str) -> list[Problem]:
    out: list[Problem] = []
    for key in FRONT_KEYS:
        if pl.front.get(key) != en.front.get(key):
            out.append(Problem(rel, "front matter", f"{key} differs"))
    for doc, lang in ((pl, "pl"), (en, "en")):
        if doc.front.get("lang") != lang:
            out.append(Problem(rel, "front matter", f"{lang} version has lang={doc.front.get('lang')!r}"))
        if doc.wikilinks:
            out.append(Problem(rel, "links", f"{lang} version uses {doc.wikilinks} wiki link(s); use markdown links"))
    expected = {"pl": f"../{'../' * (rel.count('/'))}en/{rel}", "en": f"../{'../' * (rel.count('/'))}pl/{rel}"}
    for doc, lang in ((pl, "pl"), (en, "en")):
        cp = doc.front.get("counterpart")
        if cp is None or str(PurePosixPath(cp)) != str(PurePosixPath(expected[lang])):
            out.append(Problem(rel, "front matter", f"{lang} counterpart should be {expected[lang]}"))
    if pl.headings != en.headings:
        out.append(Problem(rel, "headings", f"levels pl={pl.headings} en={en.headings}"))
    if pl.numbers != en.numbers:
        only_pl = sorted(pl.numbers - en.numbers)
        only_en = sorted(en.numbers - pl.numbers)
        out.append(Problem(rel, "numbers", f"only in pl: {only_pl}; only in en: {only_en}"))
    if pl.links != en.links:
        out.append(
            Problem(rel, "links", f"only in pl: {sorted(pl.links - en.links)}; only in en: {sorted(en.links - pl.links)}")
        )
    if pl.tables != en.tables:
        out.append(Problem(rel, "tables", f"shapes pl={pl.tables} en={en.tables}"))
    return out


def check(root: Path) -> Result:
    res = Result()
    files = {lang: {p.relative_to(root / lang).as_posix() for p in (root / lang).rglob("*.md")} for lang in LANGS if (root / lang).is_dir()}
    pl_files = files.get("pl", set())
    en_files = files.get("en", set())
    for rel in sorted(pl_files - en_files):
        res.problems.append(Problem(rel, "pair", "missing en version"))
    for rel in sorted(en_files - pl_files):
        res.problems.append(Problem(rel, "pair", "missing pl version"))
    for rel in sorted(pl_files & en_files):
        res.pairs += 1
        pl_path, en_path = root / "pl" / rel, root / "en" / rel
        try:
            pl = parse(pl_path.read_text(encoding="utf-8"))
            en = parse(en_path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, UnicodeDecodeError) as e:
            res.problems.append(Problem(rel, "parse", type(e).__name__))
            continue
        res.problems.extend(compare(rel, pl, en, str(pl_path), str(en_path)))
    return res
