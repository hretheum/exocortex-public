# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Abbreviation dictionary built from a lab corpus (roadmap task F3.3).

The extractor tells the model what an abbreviation stands for when a
document uses it without defining it. The dictionary comes only from the
corpus itself: every "long form (SHORT)" definition in the abstracts
(Schwartz & Hearst, 2003), kept when at least ``min_docs`` documents
define the abbreviation and one long form covers at least ``min_share`` of
those definitions. Nothing is carried over from earlier, non-public work.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from exocortex.lab.extractor import definitions


def build(texts: list[str], min_docs: int = 3, min_share: float = 0.6) -> list[dict]:
    forms: dict[str, Counter] = defaultdict(Counter)
    for text in texts:
        for short, long_form in definitions(text).items():
            forms[short][" ".join(long_form.lower().split())] += 1
    rows = []
    for short, counter in sorted(forms.items()):
        total = sum(counter.values())
        long_form, n = counter.most_common(1)[0]
        if total >= min_docs and n / total >= min_share:
            rows.append({"abbreviation": short, "long_form": long_form, "documents": total,
                         "share": round(n / total, 3)})
    return rows


def build_from_corpus(corpus: Path, out: Path, **kw) -> int:
    texts = [json.loads(line)["abstract"] for line in corpus.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = build(texts, **kw)
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["abbreviation", "long_form", "documents", "share"])
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def load(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8") as fh:
        return {row["abbreviation"]: row["long_form"] for row in csv.DictReader(fh)}
