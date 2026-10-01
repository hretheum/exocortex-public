# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Blind samples and human rating (roadmap task F3.5).

1. ``draw``: units (claims, or the toy experiment's sentences) from the
   results of one or more runs become a blind sample: shuffled with a
   recorded seed, optionally stratified by configuration and document
   length, with a few items repeated to measure the rater's consistency.
   The configuration stays in the database; the page never shows it, nor
   the mode label of a claim.
2. ``render``: a rating page for Obsidian, one item per section: the
   claim, its quote and the text around the quote, then boxes for the
   verdict (correct, mode swap, distorted number or name, other error),
   the mode of the source, and a comment. The page has ``publish: false``,
   so the publisher never sends the working page out.
3. ``read_page`` and ``store``: after rating, the page is parsed, the
   verdicts are joined with configurations and stored in
   ``exp_judgments`` under the rater's pseudonym.
4. ``summary``: shares per configuration with Wilson intervals and paired
   differences between configurations with a bootstrap by document
   (exocortex/lab/stats.py).
"""

from __future__ import annotations

import random
import re
from collections import defaultdict

from exocortex.lab import experiments as ex
from exocortex.lab import stats
from exocortex.lab.extractor import normalise

VERDICTS = ("correct", "mode_swap", "number_or_name", "other_error")
SOURCE_MODES = ("fact", "plan", "requirement", "hypothesis")
LABELS = {
    "pl": {"correct": "poprawne", "mode_swap": "zamiana trybu", "number_or_name": "przekręcona liczba lub nazwa",
           "other_error": "inny błąd", "fact": "źródło: fakt", "plan": "źródło: plan", "requirement": "źródło: wymóg",
           "hypothesis": "źródło: hipoteza", "claim": "Twierdzenie", "quote": "Cytat", "context": "Tekst wokół cytatu",
           "comment": "Komentarz", "item": "Pozycja",
           "intro": ("Oceń każdą pozycję: zaznacz werdykt, tryb, w jakim źródło przedstawia treść cytatu, i dopisz "
                     "komentarz, jeśli coś jest niejasne. Strona nie pokazuje, z której konfiguracji pochodzi "
                     "twierdzenie. Po skończeniu ustaw w nagłówku `rating_complete: true` i swój pseudonim w polu "
                     "`rater`.")},
    "en": {"correct": "correct", "mode_swap": "mode swap", "number_or_name": "distorted number or name",
           "other_error": "other error", "fact": "source: fact", "plan": "source: plan",
           "requirement": "source: requirement", "hypothesis": "source: hypothesis", "claim": "Claim",
           "quote": "Quote", "context": "Text around the quote", "comment": "Comment", "item": "Item",
           "intro": ("Rate every item: tick the verdict and the mode in which the source presents the quoted "
                     "content, and add a comment if something is unclear. The page does not show which "
                     "configuration a claim comes from. When done, set `rating_complete: true` in the header and "
                     "your pseudonym in `rater`.")},
}


def context_around(document: str, quote: str, width: int = 300) -> str:
    """The quote with up to ``width`` characters on each side, located after normalisation."""
    doc = " ".join(document.split())
    q = " ".join(quote.split())
    at = doc.lower().find(q.lower())
    if at < 0:
        norm_doc = normalise(doc)
        at = norm_doc.find(normalise(q))
        if at < 0:
            return doc[: 2 * width]
    start, end = max(0, at - width), min(len(doc), at + len(q) + width)
    return ("…" if start else "") + doc[start:end] + ("…" if end < len(doc) else "")


def units(conn, run_uuids: list[str], document_text) -> list[dict]:
    """Usable units of the given runs: claims (kind claims) or chosen sentences (kind toy).

    ``document_text(item_id, output)`` returns the text a result was computed on.
    """
    rows = conn.execute(
        """SELECT r.id, r.item_id, r.output, c.name AS config, c.variant FROM exp_results r
           JOIN exp_configs c ON c.id = r.config_id WHERE r.run_id = ANY(%s::uuid[]) AND r.ok
           ORDER BY r.item_id, c.name""",
        (run_uuids,),
    ).fetchall()
    out = []
    texts: dict[tuple, str] = {}
    for r in rows:
        key = (r["item_id"], r["output"].get("text"))
        if key not in texts:
            texts[key] = document_text(r["item_id"], r["output"]) or ""
        claims = r["output"].get("claims")
        if claims is not None:
            for c in claims:
                if c.get("usable"):
                    out.append({"item_id": f"{r['id']}:{c['i']}", "result_id": str(r["id"]), "document": r["item_id"],
                                "config": r["config"], "claim": c["claim"], "quote": c["quote"], "mode": c.get("mode"),
                                "text": texts[key]})
        else:
            for i, u in enumerate(r["output"].get("units") or []):
                out.append({"item_id": f"{r['id']}:{i}", "result_id": str(r["id"]), "document": r["item_id"],
                            "config": r["config"], "claim": u["text"], "quote": u["quote"], "mode": None,
                            "text": texts[key]})
    for u in out:
        doc = u.pop("text")
        u["context"] = context_around(doc, u["quote"]) if doc else ""
        u["doc_chars"] = len(doc)
    return out


def _length_band(chars: int, cuts: tuple[int, int]) -> str:
    return "short" if chars <= cuts[0] else "medium" if chars <= cuts[1] else "long"


def draw(conn, experiment_id: str, name: str, candidates: list[dict], seed: int, size: int | None = None,
         repeats: int = 0) -> str:
    """Store a blind sample of ``candidates`` (all of them when ``size`` is None)."""
    rng = random.Random(seed)
    pool = sorted(candidates, key=lambda u: u["item_id"])
    if size is not None and size < len(pool):
        lengths = sorted(u["doc_chars"] for u in pool)
        cuts = (lengths[len(lengths) // 3], lengths[2 * len(lengths) // 3])
        strata: dict[tuple, list[dict]] = defaultdict(list)
        for u in pool:
            strata[(u["config"], _length_band(u["doc_chars"], cuts))].append(u)
        frame = [{"item_id": u["item_id"], "stratum": "|".join(k), "u": u} for k, v in strata.items() for u in v]
        chosen = ex.draw_stratified(frame, {"blind": size}, seed)["blind"]
        pool = [c["u"] for c in chosen]
    rng.shuffle(pool)
    repeated = rng.sample(pool, min(repeats, len(pool))) if repeats else []
    items = list(pool)
    for u in repeated:
        items.insert(rng.randrange(len(items) + 1), {**u, "item_id": u["item_id"] + "#repeat"})
    rows = [{"item_id": u["item_id"], "stratum": u["config"],
             "content_sha256": _payload_sha(u),
             "payload": {"claim": u["claim"], "quote": u["quote"], "context": u["context"],
                         "document": u["document"]}}
            for u in items]
    method = ("all usable units, shuffled" if size is None else "stratified by configuration and document length")
    method += f"; {len(repeated)} repeated for rater consistency" if repeated else ""
    return ex.create_sample(conn, experiment_id, name, "blind", seed, method, rows)


def _payload_sha(u: dict) -> str:
    import hashlib

    return hashlib.sha256("\n".join((u["claim"], u["quote"], u["context"])).encode("utf-8")).hexdigest()


def render(conn, sample_id: str, lang: str, experiment: str, counterpart: str) -> str:
    """The rating page (Markdown with tick boxes); the position is the item number."""
    lab = LABELS[lang]
    sample = conn.execute("SELECT name FROM exp_samples WHERE id = %s", (sample_id,)).fetchone()
    rows = conn.execute("SELECT item_id, payload FROM exp_sample_items WHERE sample_id = %s ORDER BY position",
                        (sample_id,)).fetchall()
    head = (f"---\ntype: blind_rating\nlang: {lang}\ncounterpart: {counterpart}\nexperiment: {experiment}\n"
            f"sample: {sample['name']}\nitems: {len(rows)}\nrater: \"\"\nrating_complete: false\npublish: false\n---\n\n")
    title = "Ocena na ślepo" if lang == "pl" else "Blind rating"
    parts = [head, f"# {title}: {experiment}, {sample['name']}\n\n{lab['intro']}\n"]
    for n, r in enumerate(rows, 1):
        p = r["payload"]
        boxes = "\n".join(f"- [ ] {lab[v]}" for v in VERDICTS)
        modes = "\n".join(f"- [ ] {lab[m]}" for m in SOURCE_MODES)
        parts.append(f"\n## {lab['item']} {n}\n\n**{lab['claim']}:** {p['claim']}\n\n**{lab['quote']}:** {p['quote']}\n\n"
                     f"**{lab['context']}:** {p['context']}\n\n{boxes}\n\n{modes}\n\n{lab['comment']}:\n")
    return "".join(parts)


_ITEM = re.compile(r"^## \S+ (\d+)\s*$", re.MULTILINE)
_BOX = re.compile(r"^- \[([ xX])\] (.+?)\s*$", re.MULTILINE)


def read_page(text: str, lang: str) -> tuple[dict, list[dict]]:
    """(header, one dict per item: position, verdicts, source_mode, comment) from a rated page."""
    from exocortex.lab.docs import split_front

    front, body = split_front(text)
    by_label = {v: k for k, v in LABELS[lang].items() if k in VERDICTS + SOURCE_MODES}
    marks = list(_ITEM.finditer(body))
    items = []
    for i, m in enumerate(marks):
        chunk = body[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(body)]
        ticked = [by_label[b.group(2)] for b in _BOX.finditer(chunk) if b.group(1) in "xX" and b.group(2) in by_label]
        comment = chunk.split(f"{LABELS[lang]['comment']}:", 1)[1].strip() if f"{LABELS[lang]['comment']}:" in chunk else ""
        items.append({"position": int(m.group(1)), "verdicts": [t for t in ticked if t in VERDICTS],
                      "source_modes": [t for t in ticked if t in SOURCE_MODES], "comment": comment})
    return front, items


def store(conn, sample_id: str, rater: str, items: list[dict]) -> dict:
    """Write judgments; items without a verdict are reported, not stored."""
    rows = conn.execute("SELECT item_id FROM exp_sample_items WHERE sample_id = %s ORDER BY position",
                        (sample_id,)).fetchall()
    by_position = {n: r["item_id"] for n, r in enumerate(rows, 1)}
    stored, missing, conflicting = 0, [], []
    for it in items:
        item_id = by_position.get(it["position"])
        if item_id is None:
            continue
        if not it["verdicts"]:
            missing.append(it["position"])
            continue
        if "correct" in it["verdicts"] and len(it["verdicts"]) > 1:
            conflicting.append(it["position"])
            continue
        mode = it["source_modes"][0] if len(it["source_modes"]) == 1 else None
        conn.execute(
            """INSERT INTO exp_judgments (sample_id, item_id, rater, labels, source_mode, comment)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (sample_id, item_id, rater) DO UPDATE SET labels = EXCLUDED.labels,
                   source_mode = EXCLUDED.source_mode, comment = EXCLUDED.comment, created_at = NOW()""",
            (sample_id, item_id, rater, it["verdicts"], mode, it["comment"] or None),
        )
        stored += 1
    return {"stored": stored, "without_verdict": missing, "correct_with_errors": conflicting,
            "items": len(by_position)}


def judged(conn, sample_id: str, rater: str) -> list[dict]:
    """Judgments joined with their configuration, document and, for claims, the mode label."""
    rows = conn.execute(
        """SELECT j.item_id, j.labels, j.source_mode, i.payload->>'document' AS document, c.name AS config,
                  c.variant, r.output
           FROM exp_judgments j
           JOIN exp_sample_items i ON i.sample_id = j.sample_id AND i.item_id = j.item_id
           JOIN exp_results r ON r.id = split_part(split_part(j.item_id, '#', 1), ':', 1)::uuid
           JOIN exp_configs c ON c.id = r.config_id
           WHERE j.sample_id = %s AND j.rater = %s ORDER BY j.item_id""",
        (sample_id, rater),
    ).fetchall()
    out = []
    for r in rows:
        base_id = r["item_id"].split("#", 1)[0]
        index = int(base_id.rsplit(":", 1)[1])
        claims = r["output"].get("claims") or []
        label = claims[index].get("mode") if index < len(claims) else None
        out.append({"item_id": r["item_id"], "repeat": r["item_id"].endswith("#repeat"), "labels": r["labels"],
                    "source_mode": r["source_mode"], "document": r["document"], "config": r["config"],
                    "variant": r["variant"], "mode_label": label})
    return out


def effective_swap(j: dict) -> bool:
    """A mode swap counts unless the claim carries a non-fact mode label (see the hypothesis card)."""
    if "mode_swap" not in j["labels"]:
        return False
    return not (j["mode_label"] and j["mode_label"] != "fact")


def summary(conn, sample_id: str, rater: str) -> dict:
    """Shares per configuration (Wilson) and paired differences between configurations (bootstrap by document)."""
    rows = judged(conn, sample_id, rater)
    first = [r for r in rows if not r["repeat"]]
    repeats = {r["item_id"].split("#", 1)[0]: r for r in rows if r["repeat"]}
    originals = {r["item_id"]: r for r in first}
    agree = [set(originals[k]["labels"]) == set(v["labels"]) for k, v in repeats.items() if k in originals]
    per_config: dict[str, dict] = {}
    clusters: dict[str, dict[str, dict[str, tuple[float, float]]]] = defaultdict(lambda: defaultdict(dict))
    for metric, test in (("swap_rate", effective_swap), ("correct_share", lambda j: j["labels"] == ["correct"]),
                         ("other_errors", lambda j: bool({"number_or_name", "other_error"} & set(j["labels"])))):
        for config in sorted({r["config"] for r in first}):
            mine = [r for r in first if r["config"] == config]
            k = sum(test(r) for r in mine)
            p, lo, hi = stats.wilson(k, len(mine))
            per_config.setdefault(config, {})[metric] = {"value": p, "ci_low": lo, "ci_high": hi, "k": k,
                                                         "n": len(mine), "method": "wilson"}
            for r in mine:
                num, den = clusters[metric][config].get(r["document"], (0.0, 0.0))
                clusters[metric][config][r["document"]] = (num + test(r), den + 1)
    labelled = [r for r in first if r["mode_label"] and r["source_mode"]]
    acc_k = sum(r["mode_label"] == r["source_mode"] for r in labelled)
    label_accuracy = dict(zip(("value", "ci_low", "ci_high"), stats.wilson(acc_k, len(labelled))),
                          k=acc_k, n=len(labelled), method="wilson")
    differences = {}
    configs = sorted(per_config)
    for i, a in enumerate(configs):
        for b in configs[i + 1:]:
            for metric in ("swap_rate", "other_errors"):
                d, lo, hi = stats.bootstrap_difference(clusters[metric][a], clusters[metric][b])
                differences[f"{b} - {a}/{metric}"] = {"value": d, "ci_low": lo, "ci_high": hi,
                                                      "method": "bootstrap-by-document"}
    return {"items": len(first), "repeats": len(agree),
            "self_agreement": (sum(agree) / len(agree)) if agree else None,
            "per_config": per_config, "label_accuracy": label_accuracy, "differences": differences}


def rated_page(conn, sample_id: str, rater: str, lang: str, experiment: str, counterpart: str) -> str:
    """The rating page after rating, for publication: every item with its configuration and verdict."""
    lab = LABELS[lang]
    sample = conn.execute("SELECT name, seed, method FROM exp_samples WHERE id = %s", (sample_id,)).fetchone()
    rows = {r["item_id"]: r for r in judged(conn, sample_id, rater)}
    items = conn.execute("SELECT item_id, payload FROM exp_sample_items WHERE sample_id = %s ORDER BY position",
                         (sample_id,)).fetchall()
    pl = lang == "pl"
    head = (f"---\ntype: blind_rating_result\nlang: {lang}\ncounterpart: {counterpart}\nexperiment: {experiment}\n"
            f"sample: {sample['name']}\nrater: {rater}\n---\n\n")
    title = "Ocena na ślepo, wyniki" if pl else "Blind rating, results"
    intro = (f"Strona oceny próby {sample['name']} po zakończeniu oceniania, z konfiguracją każdej pozycji. "
             f"Losowanie: {sample['method']}, ziarno {sample['seed']}. Oceniał: {rater}." if pl else
             f"The rating page of sample {sample['name']} after rating, with the configuration of every item. "
             f"Draw: {sample['method']}, seed {sample['seed']}. Rated by: {rater}.")
    cols = ("| Nr | Konfiguracja | Werdykt | Tryb w źródle | Pole trybu | Twierdzenie | Cytat |" if pl else
            "| No. | Configuration | Verdict | Source mode | Mode field | Claim | Quote |")
    lines = [head, f"# {title}: {experiment}, {sample['name']}\n\n{intro}\n\n{cols}\n|---|---|---|---|---|---|---|"]
    for n, it in enumerate(items, 1):
        j = rows.get(it["item_id"])
        verdict = ", ".join(lab[v] for v in j["labels"]) if j else "—"
        source = lab[j["source_mode"]].split(": ")[-1] if j and j["source_mode"] else "—"
        field = (j or {}).get("mode_label") or "—"
        cell = lambda t: t.replace("|", "/").replace("\n", " ")
        lines.append(f"| {n} | {j['config'] if j else '—'} | {verdict} | {source} | {field} | "
                     f"{cell(it['payload']['claim'])} | {cell(it['payload']['quote'])} |")
    return "\n".join(lines) + "\n"
