"""Threshold calibration on private positives and public negatives.

Positives are paragraphs from the private corpus changed in two ways: a
mechanical edit (names and some words removed, sentences shuffled) for the
literal layer, and a rewrite by a language model for the semantic layer.
Negatives are public texts on similar topics (the published documents and,
on the server, arXiv paper summaries, which are kept out of the private
corpus). Results stay private; only the chosen thresholds are written into
the index.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

from .core import ENSEMBLE_THRESHOLD as ENSEMBLE_FLOOR
from .core import Index, _words, iter_dir_texts, paragraphs

REWRITE_PROMPT = (
    "Rewrite the following paragraph in your own words, in the same language. "
    "Remove all proper names. Keep the meaning. Return only the rewritten text.\n\n"
)


def mechanical_edit(text: str, rng: random.Random) -> str:
    text = re.sub(r"\b[A-ZŁŚŻŹĆŃÓ][\w-]+\b", "", text)  # drop capitalised words (names)
    words = text.split()
    kept = [w for w in words if rng.random() > 0.10]
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(kept))
    rng.shuffle(sentences)
    return " ".join(sentences)


def rewrite(texts: list[str], base_url: str, model: str) -> list[str]:
    import httpx

    client = httpx.Client(base_url=base_url.rstrip("/"), timeout=300)
    out = []
    for t in texts:
        # No reasoning and a bounded answer: a rewrite is about as long as its
        # input, and thinking models otherwise spend minutes per paragraph.
        resp = client.post("/chat/completions", json={"model": model, "temperature": 0.7, "max_tokens": 1024,
                                                      "chat_template_kwargs": {"enable_thinking": False},
                                                      "reasoning_effort": "low",
                                                      "messages": [{"role": "user", "content": REWRITE_PROMPT + t}]})
        resp.raise_for_status()
        out.append(resp.json()["choices"][0]["message"]["content"])
    return out


# A negative this close to a corpus paragraph is not a public text on a
# similar topic but a copy of a corpus paragraph; it is counted and left out.
IN_CORPUS_LITERAL = 0.95
# Rewrites shorter than this (refusals, fragments) do not test anything.
MIN_REWRITE_WORDS = 25


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def _rate(values: list[float], pred) -> float:
    return sum(1 for v in values if pred(v)) / max(1, len(values))


def pick_threshold(pos: list[float], neg: list[float], fa_budget: float, floor: float = 0.0) -> dict:
    """Threshold policy shared by both layers.

    If the two sets are separated, the threshold sits halfway between them.
    Otherwise zero misses on the positives comes first. If that would hold
    more than ``fa_budget`` of the negatives, the threshold rises until the
    false alarm rate fits the budget, and the miss rate it costs is reported.
    """
    pos_min, neg_max = min(pos, default=floor), max(neg, default=0.0)
    if pos and pos_min > neg_max:
        return _report(max(floor, (pos_min + neg_max) / 2), "separated", pos, neg)
    t = max(floor, pos_min - 0.01)
    policy = "zero-miss"
    if neg and _rate(neg, lambda v: v >= t) > fa_budget:
        # smallest threshold that keeps false alarms within the budget
        t = max(t, _pct(neg, 1.0 - fa_budget) + 1e-4)
        policy = "fa-budget"
    return _report(t, policy, pos, neg)


def _report(t: float, policy: str, pos: list[float], neg: list[float]) -> dict:
    return {"threshold": round(t, 4), "policy": policy,
            "false_alarm_rate": round(_rate(neg, lambda v: v >= t), 4),
            "miss_rate": round(_rate(pos, lambda v: v < t), 4),
            "positives": {"n": len(pos), "min": round(min(pos, default=0), 4),
                          "p05": round(_pct(pos, 0.05), 4), "p50": round(_pct(pos, 0.5), 4)},
            "negatives": {"n": len(neg), "p50": round(_pct(neg, 0.5), 4),
                          "p95": round(_pct(neg, 0.95), 4), "max": round(max(neg, default=0), 4)}}


def calibrate(index: Index, private_dirs: list[Path], public_dirs: list[Path], sample: int, seed: int,
              rewriter: tuple[str, str] | None, exclude: list[str] | None = None,
              fa_budget: float = 0.05) -> dict:
    rng = random.Random(seed)
    private = [p for _, t in iter_dir_texts(private_dirs, exclude or ()) for p in paragraphs(t)]
    public = [p for _, t in iter_dir_texts(public_dirs) for p in paragraphs(t) if len(_words(p)) >= 25]
    pos = rng.sample(private, min(sample, len(private)))
    rng.shuffle(public)
    neg: list[str] = []
    lit_neg: list[float] = []
    in_corpus = 0
    for para in public:
        if len(neg) >= sample:
            break
        score = index.literal_score(para)
        if score >= IN_CORPUS_LITERAL:
            in_corpus += 1
            continue
        neg.append(para)
        lit_neg.append(score)
    # Only edits that still carry substance count as leaks worth catching.
    mech = [m for m in (mechanical_edit(p, rng) for p in pos) if len(_words(m)) >= 25]
    lit_mech = [index.literal_score(p) for p in mech]
    res = {"sample": len(pos), "negatives": len(neg), "negatives_in_corpus": in_corpus, "seed": seed,
           "fa_budget": fa_budget}
    res["literal"] = pick_threshold(lit_mech, lit_neg, fa_budget, floor=ENSEMBLE_FLOOR)
    if rewriter and index.vectors is not None:
        rewritten = [r for r in rewrite(pos, *rewriter) if len(_words(r)) >= MIN_REWRITE_WORDS]
        sem_pos = index.semantic_scores(rewritten)
        sem_neg = index.semantic_scores(neg)
        res["semantic"] = pick_threshold(sem_pos, sem_neg, fa_budget)
    return res


def apply(index_dir: Path, result: dict) -> None:
    index = Index.load(index_dir)
    index.thresholds["literal"] = result["literal"]["threshold"]
    if "semantic" in result:
        index.thresholds["semantic"] = result["semantic"]["threshold"]
    index.save(index_dir)
    (index_dir / "calibration.json").write_text(json.dumps(result, indent=2))
