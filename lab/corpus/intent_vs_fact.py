# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Build the corpus of the "intent or fact" experiment (roadmap task F3.2).

Input: the paper pages the engine compiles (one Markdown file per arXiv
paper, with the Polish summary and key findings). For every paper the
abstract is downloaded again from the arXiv API, so the corpus does not
depend on what the engine stored.

Output (in --out):
  corpus.jsonl   one record per paper: id and version, abstract, summary,
                 findings, relevance score, stratum, dates, checksums
  manifest.csv   id, source address, download date, SHA-256 of the
                 normalised abstract and summary, character counts, basis
  excluded.csv   papers left out and why

Checksums are taken over whitespace-normalised text, so a second run on
another machine gives the same values unless arXiv changed an abstract.

    python lab/corpus/intent_vs_fact.py --papers <wiki/papers/papers> --out <dir>
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from pathlib import Path

API = "https://export.arxiv.org/api/query"
BATCH = 100
PAUSE_S = 3.0  # arXiv API terms: at most one request every three seconds
MIN_ABSTRACT_WORDS = 50
BASIS_ABSTRACT = "arXiv metadata, CC0 1.0 (https://info.arxiv.org/help/api/tou.html)"
BASIS_SUMMARY = "Exocortex engine output, published by the lab"
ATOM = {"a": "http://www.w3.org/2005/Atom"}
USER_AGENT = "exocortex-lab/0.1 (research corpus; https://github.com/hretheum)"


def normalise(text: str) -> str:
    return " ".join(text.split())


def sha256(text: str) -> str:
    return hashlib.sha256(normalise(text).encode("utf-8")).hexdigest()


def stratum(score: int | None) -> str:
    if score is None:
        return "unknown"
    return "low" if score <= 4 else "middle" if score <= 7 else "high"


# -- engine pages ---------------------------------------------------------------

_FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def _section(body: str, name: str) -> str:
    m = re.search(rf"^## {re.escape(name)}\n(.*?)(?=^## |\Z)", body, re.DOTALL | re.MULTILINE)
    return m.group(1).strip() if m else ""


def read_page(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    fm = _FRONT.match(text)
    if not fm:
        return None
    meta = {}
    for line in fm.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip("'\"")
    m = re.match(r"https?://arxiv\.org/abs/(.+?)(v\d+)?$", meta.get("url", ""))
    if not m:
        return None
    body = text[fm.end():]
    score = meta.get("relevance_score")
    return {
        "arxiv_id": m.group(1),
        "page_version": (m.group(2) or "")[1:] or None,
        "page": path.name,
        "relevance": int(score) if score and score.isdigit() else None,
        "summary_date": meta.get("created_at", "")[:10] or None,
        "summary_pl": _section(body, "Streszczenie"),
        "findings_pl": _section(body, "Key findings"),
    }


def read_pages(folder: Path) -> tuple[dict[str, dict], list[tuple[str, str]]]:
    """One entry per arXiv id (the newest page version wins); excluded pages."""
    papers: dict[str, dict] = {}
    excluded: list[tuple[str, str]] = []
    for path in sorted(folder.glob("*.md")):
        page = read_page(path)
        if page is None:
            excluded.append((path.name, "no arXiv id"))
            continue
        old = papers.get(page["arxiv_id"])
        if old is not None:
            keep, drop = (page, old) if int(page["page_version"] or 0) > int(old["page_version"] or 0) else (old, page)
            excluded.append((drop["page"], "duplicate of " + keep["page"]))
            page = keep
        papers[page["arxiv_id"]] = page
    return papers, excluded


# -- arXiv ----------------------------------------------------------------------

def http_get(url: str) -> bytes:
    from exocortex.source_allowlist import (
        require_url,  # no-op unless an allowlist is configured
    )

    require_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def parse_feed(xml: bytes) -> dict[str, dict]:
    out = {}
    root = ET.fromstring(xml)
    for e in root.findall("a:entry", ATOM):
        full = e.findtext("a:id", default="", namespaces=ATOM).rsplit("/abs/", 1)[-1]
        m = re.match(r"(.+?)v(\d+)$", full)
        if not m:
            continue
        out[m.group(1)] = {
            "version": int(m.group(2)),
            "title": normalise(e.findtext("a:title", default="", namespaces=ATOM)),
            "abstract": normalise(e.findtext("a:summary", default="", namespaces=ATOM)),
            "published": e.findtext("a:published", default="", namespaces=ATOM)[:10],
            "updated": e.findtext("a:updated", default="", namespaces=ATOM)[:10],
        }
    return out


def fetch_abstracts(ids: Iterable[str], get: Callable[[str], bytes] = http_get,
                    pause: float = PAUSE_S) -> dict[str, dict]:
    ids = list(ids)
    found: dict[str, dict] = {}
    for i in range(0, len(ids), BATCH):
        chunk = ids[i:i + BATCH]
        url = f"{API}?id_list={','.join(chunk)}&max_results={len(chunk)}"
        found.update(parse_feed(get(url)))
        if i + BATCH < len(ids) and pause:
            time.sleep(pause)
    return found


# -- build ----------------------------------------------------------------------

def build(papers: dict[str, dict], abstracts: dict[str, dict], fetched_at: str,
          excluded: list[tuple[str, str]]) -> list[dict]:
    corpus = []
    for aid in sorted(papers):
        p, a = papers[aid], abstracts.get(aid)
        if a is None:
            excluded.append((aid, "no abstract from the arXiv API"))
            continue
        if re.search(r"\bwithdrawn\b", a["abstract"], re.IGNORECASE) and len(a["abstract"].split()) < 80:
            excluded.append((aid, "withdrawn"))
            continue
        if len(a["abstract"].split()) < MIN_ABSTRACT_WORDS:
            excluded.append((aid, f"abstract shorter than {MIN_ABSTRACT_WORDS} words"))
            continue
        if not p["summary_pl"]:
            excluded.append((aid, "no summary in the engine"))
            continue
        corpus.append({
            "arxiv_id": aid, "version": a["version"], "title": a["title"],
            "abstract": a["abstract"], "abstract_sha256": sha256(a["abstract"]),
            "published": a["published"], "updated": a["updated"], "fetched_at": fetched_at,
            "summary_pl": normalise(p["summary_pl"]), "findings_pl": p["findings_pl"].strip(),
            "summary_sha256": sha256(p["summary_pl"] + "\n" + p["findings_pl"]),
            "summary_date": p["summary_date"], "summary_model": None,  # the engine did not record it
            "relevance": p["relevance"], "stratum": stratum(p["relevance"]),
        })
    return corpus


def write(out: Path, corpus: list[dict], excluded: list[tuple[str, str]]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with (out / "corpus.jsonl").open("w", encoding="utf-8") as fh:
        for rec in corpus:
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    with (out / "manifest.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["arxiv_id", "version", "source_url", "fetched_at", "abstract_sha256", "abstract_chars",
                    "summary_sha256", "summary_chars", "stratum", "basis_abstract", "basis_summary"])
        for r in corpus:
            w.writerow([r["arxiv_id"], r["version"], f"https://arxiv.org/abs/{r['arxiv_id']}v{r['version']}",
                        r["fetched_at"], r["abstract_sha256"], len(r["abstract"]), r["summary_sha256"],
                        len(r["summary_pl"]) + len(r["findings_pl"]), r["stratum"], BASIS_ABSTRACT, BASIS_SUMMARY])
    with (out / "excluded.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["item", "reason"])
        w.writerows(sorted(excluded))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--papers", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)
    papers, excluded = read_pages(args.papers)
    fetched_at = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d")
    abstracts = fetch_abstracts(sorted(papers))
    corpus = build(papers, abstracts, fetched_at, excluded)
    write(args.out, corpus, excluded)
    strata = {s: sum(1 for r in corpus if r["stratum"] == s) for s in ("low", "middle", "high", "unknown")}
    print(json.dumps({"pages": len(papers) + sum(1 for e in excluded if e[1].startswith("duplicate")),
                      "corpus": len(corpus), "excluded": len(excluded), "strata": strata}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
