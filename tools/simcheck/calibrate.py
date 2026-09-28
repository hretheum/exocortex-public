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
import os
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


def _split(values: list, rng: random.Random) -> tuple[list[int], list[int]]:
    idx = list(range(len(values)))
    rng.shuffle(idx)
    half = len(idx) // 2
    return idx[:half], idx[half:]


def _holdout(pos: list[float], neg: list[float], split_pos, split_neg, fa_budget: float, floor: float = 0.0) -> dict:
    """Pick the threshold on one half of each set and measure it on the other."""
    tune = pick_threshold([pos[i] for i in split_pos[0]], [neg[i] for i in split_neg[0]], fa_budget, floor)
    t = tune["threshold"]
    held_pos = [pos[i] for i in split_pos[1]]
    held_neg = [neg[i] for i in split_neg[1]]
    return {"threshold_tuned": t,
            "false_alarm_rate": round(_rate(held_neg, lambda v: v >= t), 4),
            "miss_rate": round(_rate(held_pos, lambda v: v < t), 4)}


def _published(index: Index, files_dir: Path | None) -> list[tuple[list[str], object]] | None:
    """Paragraphs of every published file with their embeddings."""
    if files_dir is None or not files_dir.is_dir():
        return None
    out = []
    for _src, text in iter_dir_texts([files_dir]):
        paras = list(paragraphs(text))
        if paras:
            out.append((paras, index._embed_queries(paras)))
    return out


def _published_scores(index: Index, published) -> list[dict[str, list[float]]] | None:
    if published is None:
        return None
    return [index.semantic_variants(paras, q=q) for paras, q in published]


def _two_stage(index: Index, judge, pos: list[str], pos_q, neg: list[str], neg_q, published,
               stage1_miss: float) -> dict:
    """Stage one keeps paragraphs whose plain similarity reaches the candidate
    threshold (set so that at most ``stage1_miss`` of the positives fall below
    it); stage two asks the judge. Rates are over all positives / negatives."""
    from tools.simcheck.core import JUDGE_NEIGHBOURS

    pos_raw, pos_idx = index.semantic_neighbours(pos, JUDGE_NEIGHBOURS, q=pos_q)
    neg_raw, neg_idx = index.semantic_neighbours(neg, JUDGE_NEIGHBOURS, q=neg_q)
    cand = round(_pct(pos_raw, stage1_miss) - 1e-4, 4)

    def judged(texts, raw, idx):
        yes = asked = 0
        for t, r, ids in zip(texts, raw, idx):
            if r >= cand:
                asked += 1
                yes += judge.is_restatement(t, [index.texts[i] for i in ids])
        return yes, asked

    pos_yes, pos_asked = judged(pos, pos_raw, pos_idx)
    neg_yes, neg_asked = judged(neg, neg_raw, neg_idx)
    res = {"candidate_threshold": cand, "stage1_miss_target": stage1_miss,
           "positives": {"n": len(pos), "candidates": pos_asked, "judged_yes": pos_yes},
           "negatives": {"n": len(neg), "candidates": neg_asked, "judged_yes": neg_yes},
           "miss_rate": round(1 - pos_yes / max(1, len(pos)), 4),
           "false_alarm_rate": round(neg_yes / max(1, len(neg)), 4)}
    if published is not None:
        held = asked_total = 0
        for paras, q in published:
            raw, idx = index.semantic_neighbours(paras, JUDGE_NEIGHBOURS, q=q)
            for t, r, ids in sorted(zip(paras, raw, idx), key=lambda x: -x[1]):
                if r < cand:
                    break
                asked_total += 1
                if judge.is_restatement(t, [index.texts[i] for i in ids]):
                    held += 1
                    break
        res["published_files_held"] = {"files": len(published), "held": held, "judged": asked_total}
    res["judge_calls"] = judge.calls
    return res


def _files_held(scores: list[dict[str, list[float]]] | None, measure: str, threshold: float) -> dict | None:
    """How many published files a threshold would hold (any paragraph over it)."""
    if scores is None:
        return None
    return {"files": len(scores), "held": sum(any(v >= threshold for v in f[measure]) for f in scores)}


def calibrate(index: Index, private_dirs: list[Path], public_dirs: list[Path], sample: int, seed: int,
              rewriter: tuple[str, str] | None, exclude: list[str] | None = None,
              fa_budget: float = 0.05, rewrites_cache: Path | None = None,
              published_dir: Path | None = None, judge=None, stage1_miss: float = 0.02) -> dict:
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
        rewritten = None
        import hashlib

        digest = hashlib.sha256("\x00".join(pos).encode("utf-8")).hexdigest()
        key = {"seed": seed, "sample": sample, "model": rewriter[1], "positives_sha256": digest}
        if rewrites_cache is not None and rewrites_cache.exists():
            cached = json.loads(rewrites_cache.read_text(encoding="utf-8"))
            if cached.get("key") == key:
                rewritten = cached["rewrites"]
        if rewritten is None:
            rewritten = rewrite(pos, *rewriter)
            if rewrites_cache is not None:
                # private text: the cache lives next to the private reports
                rewrites_cache.write_text(json.dumps({"key": key, "rewrites": rewritten}, ensure_ascii=False),
                                          encoding="utf-8")
                os.chmod(rewrites_cache, 0o600)
        rewritten = [r for r in rewritten if len(_words(r)) >= MIN_REWRITE_WORDS]
        pos_q = index._embed_queries(rewritten)
        neg_q = index._embed_queries(neg)
        pos_v = index.semantic_variants(rewritten, q=pos_q)
        neg_v = index.semantic_variants(neg, q=neg_q)
        split_rng = random.Random(seed + 1)
        split_pos, split_neg = _split(rewritten, split_rng), _split(neg, split_rng)
        published = _published(index, published_dir)
        published_scores = _published_scores(index, published)
        variants = {}
        for measure in ("raw", "margin", "csls"):
            v = pick_threshold(pos_v[measure], neg_v[measure], fa_budget)
            v["holdout"] = _holdout(pos_v[measure], neg_v[measure], split_pos, split_neg, fa_budget)
            v["published_files_held"] = _files_held(published_scores, measure, v["threshold"])
            variants[measure] = v
        # Lowest miss rate within the false alarm budget wins; ties go to fewer false alarms.
        best = min(variants, key=lambda m: (variants[m]["miss_rate"], variants[m]["false_alarm_rate"]))
        res["semantic"] = {**variants[best], "measure": best}
        res["semantic_variants"] = variants
        if judge is not None and index.texts is not None:
            res["two_stage"] = _two_stage(index, judge, rewritten, pos_q, neg, neg_q, published, stage1_miss)
    return res


def apply(index_dir: Path, result: dict) -> None:
    index = Index.load(index_dir)
    index.thresholds["literal"] = result["literal"]["threshold"]
    if "semantic" in result:
        index.thresholds["semantic"] = result["semantic"]["threshold"]
        index.thresholds["semantic_score"] = result["semantic"].get("measure", "raw")
    if "two_stage" in result:
        index.thresholds["semantic_candidate"] = result["two_stage"]["candidate_threshold"]
    else:
        index.thresholds.pop("semantic_candidate", None)
    index.save(index_dir)
    (index_dir / "calibration.json").write_text(json.dumps(result, indent=2))
