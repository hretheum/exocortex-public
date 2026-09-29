# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Read the published documents (dowody/) and data files into plain Python structures.

Nothing here renders HTML. Everything the site shows about hypotheses, runs, gate
decisions, the roadmap and data files comes from these documents and files, so the
site can be rebuilt at any time from a clean clone of the repository.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

LANGS = ("en", "pl")
FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.S)
H2 = re.compile(r"^## (.+)$", re.M)

# The dossier skeleton (see dowody/<lang>/experiments/<slug>/overview.md). The order is the
# order of the H2 sections in every dossier; the site maps a section to its key by position.
SECTION_KEYS = ["abstract", "question", "prereg", "data", "method", "runs", "results", "gates",
                "changes", "reproduce", "limits", "refs"]
STAGES = ["candidate", "card", "test", "gate", "pilot", "report"]
# The one rule for the strength of evidence and the source checksum, shared with the lab
# (exocortex/lab/evidence.py). Loaded by path: it needs only the standard library and PyYAML.
EVIDENCE_PY = Path(__file__).resolve().parents[1] / "exocortex" / "lab" / "evidence.py"
APPLICATIONS = "applications.md"


def load_evidence(path: Path = EVIDENCE_PY):
    spec = importlib.util.spec_from_file_location("lab_evidence", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up while the class is built
    spec.loader.exec_module(module)
    return module


evidence = load_evidence()


def read_md(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    m = FRONT.match(text)
    front = yaml.safe_load(m.group(1)) if m else {}
    return (front or {}), text[m.end():] if m else text


def split_sections(body: str) -> tuple[str, list[tuple[str, str]]]:
    """(text before the first H2, [(heading, markdown)])."""
    parts = H2.split(body)
    head = parts[0]
    return head, [(parts[i].strip(), parts[i + 1].strip()) for i in range(1, len(parts) - 1, 2)]


def h1(body: str) -> str:
    m = re.search(r"^# (.+)$", body, re.M)
    return m.group(1).strip() if m else ""


def parse_table(md: str) -> list[list[str]]:
    rows = []
    for line in md.splitlines():
        line = line.strip()
        if line.startswith("|") and not re.match(r"^\|[\s:|-]+\|$", line):
            rows.append([c.strip() for c in line.strip("|").split("|")])
    return rows


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class DataFile:
    name: str
    path: Path
    size: int
    sha256: str
    records: int | None


@dataclass
class Item:
    """A run note, a gate decision or a hypothesis card of one language."""
    front: dict
    title: str
    body: str
    file: str  # repository path, for links


@dataclass
class Dossier:
    slug: str
    roadmap: str
    status: str
    stage: int
    tier: str
    updated: str
    by_lang: dict = field(default_factory=dict)  # lang -> dict(title, tagline, sections, changes)
    files: list = field(default_factory=list)
    prereg: list = field(default_factory=list)
    cards: dict = field(default_factory=dict)  # lang -> Item | None
    runs: dict = field(default_factory=dict)  # lang -> [Item]
    gates: dict = field(default_factory=dict)
    version: str = "0.1"
    # business applications (F8.1): "absent" (no file, the page is unchanged), "current" (approved and its
    # source checksum matches the dossier: shown) or "stale" (anything else: a short notice instead)
    applications_state: str = "absent"
    applications: dict = field(default_factory=dict)  # lang -> Item, only when current


def count_records(path: Path) -> int | None:
    if path.suffix == ".jsonl":
        with path.open("rb") as fh:
            return sum(1 for _ in fh)
    if path.suffix == ".csv":
        with path.open(encoding="utf-8", newline="") as fh:
            return max(0, sum(1 for _ in csv.reader(fh)) - 1)
    return None


def load_files(dirs: list[Path]) -> list[DataFile]:
    out = []
    for d in dirs:
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if p.is_file() and not p.name.startswith("."):
                out.append(DataFile(p.name, p, p.stat().st_size, sha256_file(p), count_records(p)))
    return out


def load_dossiers(docs: Path, corpora: Path | None) -> list[Dossier]:
    slugs = set()
    for lang in LANGS:
        for p in (docs / lang / "experiments").glob("*/overview.md"):
            slugs.add(p.parent.name)
    prereg_all = []
    pr = docs / "prereg.jsonl"
    if pr.exists():
        prereg_all = [json.loads(line) for line in pr.read_text(encoding="utf-8").splitlines() if line.strip()]
    out = []
    for slug in sorted(slugs):
        d = None
        for lang in LANGS:
            p = docs / lang / "experiments" / slug / "overview.md"
            if not p.exists():
                continue
            front, body = read_md(p)
            head, sections = split_sections(body)
            if d is None:
                d = Dossier(slug=slug, roadmap=str(front.get("roadmap", "")), status=str(front.get("status", "planned")),
                            stage=int(front.get("stage", 0)), tier=str(front.get("tier", "S")),
                            updated=str(front.get("updated", "")))
            changes = []
            for key, (heading, md) in zip(SECTION_KEYS, sections):
                if key == "changes":
                    changes = parse_table(md)[1:]
            d.by_lang[lang] = {"title": h1(body), "tagline": str(front.get("tagline", "")), "sections": sections,
                               "changes": changes}
            # dynamic items: card, runs, gates
            base = docs / lang / "experiments" / slug
            card = base / "hypothesis.md"
            d.cards[lang] = _item(card, docs.parent) if card.exists() else None
            d.runs[lang] = [_item(p2, docs.parent) for p2 in sorted(base.glob("run-*.md"))]
            d.gates[lang] = [_item(p2, docs.parent) for p2 in sorted(base.glob("gate-*.md"))]
        if d is None:
            continue
        chg = d.by_lang.get("en", {}).get("changes") or []
        if chg and len(chg[-1]) > 1:
            d.version = chg[-1][1]
        dirs = [docs / "data" / slug]
        if corpora is not None:
            dirs.append(corpora / slug)
        d.files = load_files(dirs)
        d.prereg = [e for e in prereg_all if e.get("hypothesis") == slug or e.get("slug") == slug]
        d.applications_state, d.applications = load_applications(docs, slug)
        out.append(d)
    order = {"running": 0, "preparation": 1, "planned": 2, "decided": 3}
    out.sort(key=lambda x: (order.get(x.status, 9), x.roadmap))
    return out


def load_applications(docs: Path, slug: str) -> tuple[str, dict]:
    """(state, {lang: Item}) of the applications section.

    Shown only when both language versions are approved (``publish: true`` and ``human_validated: true``)
    and their source checksum and label match the dossier.
    """
    paths = {lang: docs / lang / "experiments" / slug / APPLICATIONS for lang in LANGS}
    if not any(p.exists() for p in paths.values()):
        return "absent", {}
    if not all(p.exists() for p in paths.values()):
        return "stale", {}
    _, digest, ev = evidence.assess(docs, slug, docs / "data")
    items = {lang: _item(p, docs.parent) for lang, p in paths.items()}
    for lang, item in items.items():
        fr = item.front
        if (ev.problems or fr.get("human_validated") is not True or fr.get("publish") is not True
                or fr.get("source_hash") != digest or fr.get("label") != ev.label(lang)):
            return "stale", {}
    return "current", items


def _item(path: Path, root: Path) -> Item:
    front, body = read_md(path)
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        rel = path.name
    return Item(front, h1(body), body, rel)


# ------------------------------------------------------------------ roadmap ----
@dataclass
class Task:
    id: str
    title: str
    status: str
    estimate: str = ""
    depends: list = field(default_factory=list)


@dataclass
class Phase:
    id: str
    title: str
    goal: str
    tasks: list

    @property
    def done(self) -> int:
        return sum(1 for t in self.tasks if t.status == "done")

    @property
    def doing(self) -> int:
        return sum(1 for t in self.tasks if t.status == "doing")


def load_roadmap(docs: Path, lang: str) -> list[Phase]:
    phases = []
    rd = docs / lang / "roadmap"
    for pf in sorted(rd.glob("F[0-9]-*.md")):
        front, body = read_md(pf)
        title_full = h1(body)
        m = re.match(r"(F\d+)\.\s*(.*)", title_full)
        pid, title = (m.group(1), m.group(2)) if m else (front.get("id", pf.stem), title_full)
        goal = ""
        for heading, md in split_sections(body)[1]:
            if heading.lower() in ("cel", "goal"):
                goal = md.split("\n\n")[0].strip()
                break
        tasks = []
        tdir = rd / pid
        if tdir.is_dir() and any(tdir.glob("*.md")):
            for tf in sorted(tdir.glob(f"{pid}.*-*.md"), key=lambda p: int(re.match(rf"{pid}\.(\d+)", p.name).group(1))):
                tfront, tbody = read_md(tf)
                tt = h1(tbody)
                m2 = re.match(r"(F\d+\.\d+)\.\s*(.*)", tt)
                tasks.append(Task(id=m2.group(1) if m2 else str(tfront.get("id", "")), title=m2.group(2) if m2 else tt,
                                  status=str(tfront.get("status", "todo")), estimate=str(tfront.get("estimate", "")),
                                  depends=list(tfront.get("depends_on") or [])))
        else:
            ts = front.get("task_status") or {}
            for m3 in re.finditer(r"^### (F\d+\.\d+)\.\s*(.+)$", body, re.M):
                tasks.append(Task(id=m3.group(1), title=m3.group(2).strip(),
                                  status=str(ts.get(m3.group(1), "todo"))))
        phases.append(Phase(pid, title, goal, tasks))
    phases.sort(key=lambda p: int(p.id[1:]))
    return phases
