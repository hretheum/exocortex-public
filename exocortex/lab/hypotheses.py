# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Processor ``hypothesis_card``: cards into the lab graph, preregistration (F2.4).

Reads both language versions of every card among the published documents
(nodes written by docsync), validates their headers against the gate's
schemas and keeps one row per card version in ``lab_hypotheses`` with a
node in the graph.

When both versions say ``human_validated: true`` and the card version is
not registered yet, the processor computes its checksum
(exocortex/lab/prereg.py) and appends an entry to ``prereg.jsonl`` in the
lab's output folder. The publisher sends that file to the repository; the
commit is the timestamp. From then on the checksum is fixed: any change of
content without a new version marks the card as violated, pages show it,
and the gate processor refuses decisions for it. A new version names the
old one in ``supersedes``; both stay.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from psycopg.types.json import Jsonb

from exocortex.lab import headers, prereg
from exocortex.lab.db import insert_edge, upsert_thought
from exocortex.lab.docs import first_table_under

METRICS_HEADINGS = ("Metryki", "Metrics")
_COLUMNS = {
    "role": ("rola", "role"),
    "metric": ("metryka", "metric"),
    "threshold": ("próg", "threshold"),
    "baseline": ("linia bazowa", "baseline"),
}


def table_rows(table: list[list[str]], columns: dict[str, tuple[str, ...]]) -> list[dict]:
    """Rows of a Markdown table as dicts keyed by our column names (matched on header text)."""
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


def card_metrics(body: str) -> list[dict]:
    return table_rows(first_table_under(body, METRICS_HEADINGS), _COLUMNS)


def norm_value(text: str) -> str:
    """Threshold text for comparison: case, spaces and decimal commas do not count."""
    text = text.lower().replace(" ", " ").replace(",", ".")
    return re.sub(r"\s+", " ", text).strip()


def _card_docs(docs: list[dict]) -> dict[tuple, dict[str, dict]]:
    out: dict[tuple, dict[str, dict]] = {}
    for d in docs:
        if d.get("kind") != "hypothesis_card" or d.get("lang") not in ("pl", "en"):
            continue
        if d["key"].startswith("templates/"):
            continue
        front = d.get("front") or {}
        out.setdefault((front.get("slug"), front.get("version")), {})[d["lang"]] = d
    return out


def process(conn, tenant: str, docs: list[dict], registry_path: Path, now: dt.datetime | None = None) -> dict:
    """Bring ``lab_hypotheses``, the graph and the registry up to date; returns counts."""
    now = now or dt.datetime.now(dt.UTC)
    registry = prereg.read_registry(registry_path)
    counts = {"cards": 0, "registered": 0, "frozen": 0, "violated": 0, "with_problems": 0}
    for (slug, version), by_lang in sorted(_card_docs(docs).items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        counts["cards"] += 1
        problems: list[str] = []
        for lang, d in sorted(by_lang.items()):
            problems += [f"{d['rel']}: {p}" for p in headers.validate(d["rel"], d["body"])]
        missing = {"pl", "en"} - set(by_lang)
        if missing or not isinstance(slug, str) or not isinstance(version, int):
            problems.append(f"missing language version: {', '.join(sorted(missing))}" if missing
                            else "slug or version missing")
            counts["with_problems"] += 1
            continue  # nothing reliable to store: the header does not identify a card
        pl, en = by_lang["pl"], by_lang["en"]
        for field in ("slug", "version", "supersedes", "tier_target", "data_class"):
            if pl["front"].get(field) != en["front"].get(field):
                problems.append(f"{field} differs between the Polish and English versions")
        content = prereg.card_hash(pl["body"], en["body"])
        approved = pl["front"].get("human_validated") is True and en["front"].get("human_validated") is True
        entry = prereg.find(registry, slug, version)
        if approved and entry is None:
            if problems:
                problems.append("approved but not registered: fix the problems above first")
            else:
                entry = {"slug": slug, "version": version, "sha256": content, "algorithm": prereg.ALGORITHM,
                         "registered_at": now.isoformat(timespec="seconds"),
                         "files": {"pl": pl["rel"], "en": en["rel"]}}
                prereg.append(registry_path, entry)
                registry.append(entry)
                counts["registered"] += 1
        violated = entry is not None and entry["sha256"] != content
        for lang, d in (("pl", pl), ("en", en)):
            stated = d["front"].get("prereg_hash")
            if stated and entry is not None and stated != entry["sha256"]:
                problems.append(f"{d['rel']}: prereg_hash differs from the registered checksum")
            if stated and entry is None:
                problems.append(f"{d['rel']}: prereg_hash is set but the card is not registered")
        # gate decisions are applied afterwards (gates.process) and set the decided states again
        state = "frozen" if entry else "draft"
        counts["frozen"] += entry is not None
        counts["violated"] += violated
        counts["with_problems"] += bool(problems)
        metrics = {"pl": card_metrics(pl["body"]), "en": card_metrics(en["body"])}
        meta = {"domain": "lab", "slug": slug, "version": version, "state": state, "violated": violated,
                "approved": approved, "content_sha256": content,
                "prereg_sha256": entry["sha256"] if entry else None, "files": {"pl": pl["rel"], "en": en["rel"]}}
        tid, _ = upsert_thought(conn, tenant, source_id=None, thought_type="hypothesis_card", key=f"{slug}/v{version}",
                                body=pl["body"], metadata=meta)
        for d in (pl, en):
            insert_edge(conn, tenant, tid, "thought", d["id"], "thought", "derived_from")
        supersedes = pl["front"].get("supersedes")
        if isinstance(supersedes, int):
            old = conn.execute("SELECT thought_id FROM lab_hypotheses WHERE slug = %s AND version = %s",
                               (slug, supersedes)).fetchone()
            if old and old["thought_id"]:
                insert_edge(conn, tenant, tid, "thought", str(old["thought_id"]), "thought", "supersedes")
            else:
                problems.append(f"supersedes version {supersedes}, which is not among the cards")
        conn.execute(
            """INSERT INTO lab_hypotheses (slug, version, supersedes, title, files, content_sha256, approved,
                                           prereg_sha256, prereg_at, violated, state, metrics, problems, thought_id,
                                           updated_at)
               VALUES (%(slug)s, %(version)s, %(supersedes)s, %(title)s, %(files)s, %(content)s, %(approved)s,
                       %(prereg)s, %(prereg_at)s, %(violated)s, %(state)s, %(metrics)s, %(problems)s, %(tid)s, NOW())
               ON CONFLICT (slug, version) DO UPDATE SET supersedes = EXCLUDED.supersedes, title = EXCLUDED.title,
                   files = EXCLUDED.files, content_sha256 = EXCLUDED.content_sha256, approved = EXCLUDED.approved,
                   prereg_sha256 = EXCLUDED.prereg_sha256, prereg_at = EXCLUDED.prereg_at,
                   violated = EXCLUDED.violated, state = EXCLUDED.state, return_condition = NULL,
                   metrics = EXCLUDED.metrics,
                   problems = EXCLUDED.problems, thought_id = EXCLUDED.thought_id, updated_at = NOW()""",
            {"slug": slug, "version": version, "supersedes": supersedes if isinstance(supersedes, int) else None,
             "title": _title(pl["body"]), "files": Jsonb(meta["files"]), "content": content, "approved": approved,
             "prereg": entry["sha256"] if entry else None, "prereg_at": entry["registered_at"] if entry else None,
             "violated": violated, "state": state, "metrics": Jsonb(metrics), "problems": Jsonb(problems), "tid": tid},
        )
    return counts


def _title(text: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return m.group(1).strip() if m else ""
