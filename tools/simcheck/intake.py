"""Fills the quarantine database from the documents to publish.

Each file of a publication class with the semantic comparison is checked
paragraph by paragraph (exhaustively, so every flagged paragraph is
reported). Findings are grouped into units of publication (an experiment
as a whole, every other file on its own) and synced into the database:
paragraphs that did not change keep their decision, changed ones start
over. Only paths, rule names, hashes and scores reach the database.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from tools.publisher.classes import SEMANTIC, checks_for, classify_file, experiment_slug
from tools.publisher.quarantine import Store, source_hash

from .core import Index, iter_dir_texts


def unit_of(rel: str, cls: str) -> str:
    """The key of the unit a file belongs to: the experiment slug, else the path without its language folder."""
    slug = experiment_slug(rel)
    if slug is not None:
        return slug
    parts = rel.split("/", 1)
    return parts[1] if len(parts) == 2 and parts[0] in ("pl", "en") else rel


def scan_units(index: Index, docs: Path, approved: set[str], mask=None, keep=None) -> dict[tuple[str, str], dict]:
    """(class, key) -> {"files": [...], "digests": [...], "findings": [...]} for the files under ``docs``."""
    units: dict[tuple[str, str], dict] = {}
    for src, text in iter_dir_texts([docs]):
        rel = Path(src).relative_to(docs).as_posix()
        cls = classify_file(rel, Path(src))
        if SEMANTIC not in checks_for(cls) or (keep is not None and not keep(rel)):
            continue
        u = units.setdefault((cls, unit_of(rel, cls)), {"files": [], "digests": [], "findings": []})
        u["files"].append(rel)
        u["digests"].append((rel, hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()))
        for p in index.check(text, approved, mask, exhaustive=True).paragraphs or []:
            if p["flagged"]:
                score = p["score_literal"] if p["rule"] == "literal" else p["score_semantic"]
                u["findings"].append({"rule": p["rule"], "path": rel, "para_hash": p["hash"], "score": score})
    return units


def sync(store: Store, index: Index, docs: Path, mask=None, keep=None, who: str = "intake",
         extra: list[tuple[Path, object]] | None = None) -> dict:
    """Check the documents and bring the database in line; returns counts.

    ``extra`` lists more roots with their own ``keep`` filter (the lab's output folder: generated pages and
    data that the publisher takes from there). Their paths are relative to their root, like the documents'.
    """
    total = {"units": 0, "new": 0, "kept": 0, "outdated": 0}
    seen = set()
    units = scan_units(index, docs, set(), mask, keep)
    for root, root_keep in extra or []:
        for k, u in scan_units(index, root, set(), mask, root_keep).items():
            if k in units:
                for field in ("files", "digests", "findings"):
                    units[k][field] += u[field]
            else:
                units[k] = u
    # Approvals are not passed on: an approved paragraph stays a finding (state kept) for as long as it
    # is in the source, so its approval is never dropped just because simcheck stopped flagging it.
    for (cls, key), u in units.items():
        seen.add((cls, key))
        c = store.sync_unit(cls, key, u["files"], source_hash(u["digests"]), u["findings"], who)
        total["units"] += 1
        for k in ("new", "kept", "outdated"):
            total[k] += c[k]
    for unit in store.list_units():  # a unit whose files are all gone or clean now
        if (unit["cls"], unit["key"]) not in seen and unit["state"] == "open":
            c = store.sync_unit(unit["cls"], unit["key"], [], "", [], who)
            total["outdated"] += c["outdated"]
    return total
