"""Threshold calibration on private positives and public negatives.

Positives are paragraphs from the private corpus changed in two ways: a
mechanical edit (names and some words removed, sentences shuffled) for the
literal layer, and a rewrite by a language model for the semantic layer.
Negatives are public texts on similar topics. Results stay private; only the
chosen thresholds are written into the index.
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


def calibrate(index: Index, private_dirs: list[Path], public_dirs: list[Path], sample: int, seed: int,
              rewriter: tuple[str, str] | None, exclude: list[str] | None = None) -> dict:
    rng = random.Random(seed)
    private = [p for _, t in iter_dir_texts(private_dirs, exclude or ()) for p in paragraphs(t)]
    public = [p for _, t in iter_dir_texts(public_dirs) for p in paragraphs(t)]
    pos = rng.sample(private, min(sample, len(private)))
    neg = rng.sample(public, min(sample, len(public)))
    # Only edits that still carry substance count as leaks worth catching.
    mech = [m for m in (mechanical_edit(p, rng) for p in pos) if len(_words(m)) >= 25]
    res = {"sample": len(pos), "negatives": len(neg), "seed": seed}
    lit_mech = [index.literal_score(p) for p in mech]
    lit_neg = [index.literal_score(p) for p in neg]
    res["literal"] = {"positives_used": len(mech), "mechanical_min": min(lit_mech, default=0), "mechanical_p05": sorted(lit_mech)[len(lit_mech) // 20] if lit_mech else 0,
                      "negatives_max": max(lit_neg, default=0)}
    # Zero misses on the calibration positives comes first; the false alarm
    # rate at that threshold is reported so a person can judge it.
    pos_min, neg_max = min(lit_mech, default=0.4), max(lit_neg, default=0.0)
    t_lit = (pos_min + neg_max) / 2 if pos_min > neg_max else pos_min * 0.95
    t_lit = max(ENSEMBLE_FLOOR, t_lit)
    res["literal"]["threshold"] = round(t_lit, 4)
    res["literal"]["false_alarm_rate"] = sum(s >= t_lit for s in lit_neg) / max(1, len(lit_neg))
    res["literal"]["miss_rate"] = sum(s < t_lit for s in lit_mech) / max(1, len(lit_mech))
    if rewriter and index.vectors is not None:
        rewritten = rewrite(pos, *rewriter)
        sem_pos = index.semantic_scores(rewritten)
        sem_neg = index.semantic_scores(neg)
        t_sem = min(sem_pos, default=0.9) - 0.01
        res["semantic"] = {"rewritten_min": min(sem_pos, default=0), "negatives_max": max(sem_neg, default=0),
                           "threshold": round(t_sem, 4),
                           "false_alarm_rate": sum(s >= t_sem for s in sem_neg) / max(1, len(sem_neg)),
                           "miss_rate": sum(s < t_sem for s in sem_pos) / max(1, len(sem_pos))}
    return res


def apply(index_dir: Path, result: dict) -> None:
    index = Index.load(index_dir)
    index.thresholds["literal"] = result["literal"]["threshold"]
    if "semantic" in result:
        index.thresholds["semantic"] = result["semantic"]["threshold"]
    index.save(index_dir)
    (index_dir / "calibration.json").write_text(json.dumps(result, indent=2))
