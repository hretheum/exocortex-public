# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Reading the evidence documents (``dowody/``): headers, sections, tables.

Every document exists as ``pl/<path>`` and ``en/<path>``. Headers are YAML
front matter; the body is Markdown. Nothing here writes anything.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.S)
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$", re.M)
LANGS = ("pl", "en")


def plain(value):
    """YAML dates as ISO strings, recursively, so headers serialise as JSON."""
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v) for v in value]
    return value


def split_front(text: str) -> tuple[dict, str]:
    """(header, body). A missing or broken header gives ({}, text)."""
    m = FRONT.match(text)
    if not m:
        return {}, text
    try:
        front = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}, text
    return (plain(front) if isinstance(front, dict) else {}), text[m.end():]


@dataclass
class Doc:
    rel: str            # path relative to the documents root, e.g. pl/roadmap/F2/F2.4-....md
    lang: str | None    # pl, en or None for files outside the language folders
    key: str            # rel without the language folder: the pair's shared name
    text: str
    front: dict
    body: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    @property
    def title(self) -> str:
        m = HEADING.search(self.body)
        return m.group(2) if m else self.key


def read_doc(root: Path, path: Path) -> Doc:
    rel = path.relative_to(root).as_posix()
    head, _, rest = rel.partition("/")
    lang = head if head in LANGS and rest else None
    text = path.read_text(encoding="utf-8")
    front, body = split_front(text)
    return Doc(rel=rel, lang=lang, key=rest if lang else rel, text=text, front=front, body=body)


def iter_docs(root: Path) -> list[Doc]:
    """All Markdown documents under ``root``, sorted, skipping hidden folders."""
    out = []
    for path in sorted(root.rglob("*.md")):
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        out.append(read_doc(root, path))
    return out


def pairs(docs: list[Doc]) -> dict[str, dict[str, Doc]]:
    """{key: {"pl": doc, "en": doc}} for documents in the language folders."""
    out: dict[str, dict[str, Doc]] = {}
    for d in docs:
        if d.lang:
            out.setdefault(d.key, {})[d.lang] = d
    return out


def sections(body: str) -> dict[str, str]:
    """Text under each heading (any level), keyed by the heading text."""
    out: dict[str, str] = {}
    marks = list(HEADING.finditer(body))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        out[m.group(2)] = body[m.end():end].strip()
    return out


def _cells(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def tables(text: str) -> list[list[list[str]]]:
    """Every Markdown table in ``text`` as rows of cells; the header row first, the rule row dropped."""
    out, current = [], []
    for line in text.splitlines():
        if line.strip().startswith("|"):
            cells = _cells(line)
            if all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c):
                continue
            current.append(cells)
        elif current:
            out.append(current)
            current = []
    if current:
        out.append(current)
    return out


def first_table_under(body: str, headings: tuple[str, ...]) -> list[list[str]]:
    """First table in the section whose heading is one of ``headings`` (case-insensitive)."""
    wanted = {h.lower() for h in headings}
    for name, text in sections(body).items():
        if name.lower() in wanted:
            found = tables(text)
            if found:
                return found[0]
    return []
