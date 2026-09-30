# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Blind rating on the review desk (roadmap task F2.10).

The lab draws a blind sample and writes its rating page to ``blind/<experiment>/<sample>.{pl,en}.md`` in its
output folder, which the desk mounts read-only. The page shows, for every item, the claim, its quote and the
text around the quote, never the configuration (``exocortex/lab/blind.py``). The desk has no way into the lab
database, so rating goes through files:

1. The desk shows one item at a time from the page and records each rating in the state folder
   (``blind/<experiment>/<sample>.json``), together with the checksum of the page it was made on. Only the
   item's own text leaves this module; nothing else of the page is passed on.
2. When every item is rated, the owner finishes the sample. The desk writes a request file; the gate job
   ``apply-ratings`` (the one container with the vault mounted writable for this) ticks the boxes on a copy of
   the page and writes it to ``{lang}/experiments/<experiment>/<sample>.md`` in the vault, with the rater and
   ``rating_complete: true``. It never replaces a page it did not write itself.
3. The lab reads that page with ``exocortex lab blind import``, the same code and checks as for a page ticked
   by hand in Obsidian, which stays the fallback.

The ratings are the owner's own input; no share, count per category or interval is computed here, so the
desk cannot show partial results.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import tempfile
import threading
from pathlib import Path

# The same keys and labels as exocortex/lab/blind.py (a test keeps them equal); the page is ticked by label.
VERDICTS = ("correct", "mode_swap", "number_or_name", "other_error")
SOURCE_MODES = ("fact", "plan", "requirement", "hypothesis")
LABELS = {
    "pl": {"correct": "poprawne", "mode_swap": "zamiana trybu", "number_or_name": "przekręcona liczba lub nazwa",
           "other_error": "inny błąd", "fact": "źródło: fakt", "plan": "źródło: plan", "requirement": "źródło: wymóg",
           "hypothesis": "źródło: hipoteza", "claim": "Twierdzenie", "quote": "Cytat", "context": "Tekst wokół cytatu",
           "comment": "Komentarz"},
    "en": {"correct": "correct", "mode_swap": "mode swap", "number_or_name": "distorted number or name",
           "other_error": "other error", "fact": "source: fact", "plan": "source: plan",
           "requirement": "source: requirement", "hypothesis": "source: hypothesis", "claim": "Claim",
           "quote": "Quote", "context": "Text around the quote", "comment": "Comment"},
}
LANGS = ("pl", "en")
FOLDER = "blind"
LOG = "log.jsonl"
REQUEST_FILE = "ratings-request"
NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
MAX_PAGE = 4 * 1024 * 1024
MAX_COMMENT = 1000
_FRONT = re.compile(r"\A---\n(.*?\n)---\n", re.DOTALL)
_ITEM = re.compile(r"^## \S+ (\d+)\s*$", re.M)
_LOCK = threading.Lock()


class RatingError(Exception):
    pass


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _front(text: str) -> dict[str, str] | None:
    """The flat ``key: value`` header of a rating page (values as written), or None."""
    m = _FRONT.match(text)
    if not m:
        return None
    out = {}
    for line in m.group(1).splitlines():
        k, sep, v = line.partition(":")
        if sep and k and not k.startswith(" "):
            out[k.strip()] = v.strip().strip('"')
    return out


def parse_page(text: str) -> dict | None:
    """The items of a rating page: position, claim, quote and text around the quote. None if it is not one.

    Only these four fields are taken from each item, whatever else a page might carry.
    """
    front = _front(text)
    if not front or front.get("type") != "blind_rating" or front.get("lang") not in LANGS:
        return None
    lab = LABELS[front["lang"]]
    body = text[_FRONT.match(text).end():]
    marks = list(_ITEM.finditer(body))
    items = []
    fields = (("claim", lab["claim"]), ("quote", lab["quote"]), ("context", lab["context"]))
    for i, m in enumerate(marks):
        chunk = body[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(body)]
        item = {"position": int(m.group(1))}
        for key, label in fields:  # each field is one paragraph that starts with its label
            start = chunk.find(f"\n**{label}:** ")
            if start < 0:
                return None
            start += len(label) + 7
            end = chunk.find("\n\n", start)
            item[key] = chunk[start: end if end >= 0 else len(chunk)].strip()
        items.append(item)
    if not items or [it["position"] for it in items] != list(range(1, len(items) + 1)):
        return None
    return {"lang": front["lang"], "experiment": front.get("experiment", ""), "sample": front.get("sample", ""),
            "items": items}


def _page_path(lab: Path, experiment: str, sample: str) -> tuple[Path, str] | None:
    for lang in LANGS:  # the Polish page first: the desk speaks Polish
        p = lab / FOLDER / experiment / f"{sample}.{lang}.md"
        if p.is_file():
            return p, lang
    return None


def _read_page(lab: Path, experiment: str, sample: str) -> tuple[str, dict] | None:
    if not (NAME.fullmatch(experiment or "") and NAME.fullmatch(sample or "")):
        raise RatingError("bad name")
    found = _page_path(lab, experiment, sample)
    if found is None:
        return None
    try:
        if found[0].stat().st_size > MAX_PAGE:
            return None
        text = found[0].read_text(encoding="utf-8")
    except OSError:
        return None
    page = parse_page(text)
    if page is None or page["experiment"] != experiment or page["sample"] != sample:
        return None
    return text, page


def _state_file(state: Path, experiment: str, sample: str) -> Path:
    return state / FOLDER / experiment / f"{sample}.json"


def _load(state: Path, experiment: str, sample: str) -> dict | None:
    try:
        d = json.loads(_state_file(state, experiment, sample).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and isinstance(d.get("ratings"), dict) else None


def _atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(tmp, (path.stat().st_mode & 0o777) if path.exists() else 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _progress(total: int, rec: dict | None, sha: str) -> dict:
    rated = len(rec["ratings"]) if rec and rec.get("page_sha") == sha else 0
    return {"rated": rated, "total": total, "left": total - rated}


WAITING = ("new", "rating", "changed")  # statuses in which items still wait for the owner


def _rated_by_hand(docs: Path | None, lang: str, experiment: str, sample: str, rec: dict | None) -> bool:
    """A rated page for the sample is already in the vault and the desk did not write it (the fallback)."""
    if docs is None:
        return False
    try:
        text = target_of(docs, lang, experiment, sample).read_text(encoding="utf-8")
    except OSError:
        return False
    front = _front(text) or {}
    ours = {w.get("sha") for w in (rec or {}).get("history", [])}
    return front.get("rating_complete") == "true" and _sha(text) not in ours


def _status(rec: dict | None, sha: str) -> str:
    """``new``, ``rating``, ``finished`` (waiting for apply-ratings), ``written`` (page in the vault) or
    ``changed`` (the page was drawn again after rating started; the old ratings do not apply to it)."""
    if rec is None or not rec["ratings"]:
        return "new"
    if rec.get("page_sha") != sha:
        return "changed"
    if rec.get("written") and rec["written"].get("ratings_sha") == _ratings_sha(rec):
        return "written"
    return "finished" if rec.get("finished") else "rating"


def _ratings_sha(rec: dict) -> str:
    return _sha(json.dumps(rec["ratings"], sort_keys=True))


def list_samples(lab: Path | None, state: Path | None, docs: Path | None = None) -> list[dict]:
    """Every rating page in the lab's output folder, with the progress of its rating (never a result).

    With the documents folder, a sample whose rated page is already there and was not written by the desk
    (ticked by hand) gets the status ``by_hand`` and waits for nothing."""
    out = []
    root = lab / FOLDER if lab else None
    if root is None or not root.is_dir():
        return out
    for folder in sorted(p for p in root.iterdir() if p.is_dir() and NAME.fullmatch(p.name)):
        names = {f.name.rsplit(".", 2)[0] for f in folder.glob("*.md") if NAME.fullmatch(f.name.rsplit(".", 2)[0])}
        for sample in sorted(names):
            got = _read_page(lab, folder.name, sample)
            if got is None:
                continue
            text, page = got
            sha = _sha(text)
            rec = _load(state, folder.name, sample) if state else None
            status = _status(rec, sha)
            if status in WAITING and _rated_by_hand(docs, page["lang"], folder.name, sample, rec):
                status = "by_hand"
            out.append({"experiment": folder.name, "sample": sample, "status": status,
                        "progress": _progress(len(page["items"]), rec, sha)})
    return out


def waiting_items(lab: Path | None, state: Path | None, docs: Path | None = None) -> int:
    """Unrated items in every sample that still waits for the owner (the desk's menu counter)."""
    return sum(s["progress"]["left"] for s in list_samples(lab, state, docs) if s["status"] in WAITING)


def view(lab: Path, state: Path | None, experiment: str, sample: str) -> dict:
    """The items to rate (position, claim, quote, text around the quote) and the owner's own ratings."""
    got = _read_page(lab, experiment, sample)
    if got is None:
        raise RatingError("no such rating page")
    text, page = got
    sha = _sha(text)
    rec = _load(state, experiment, sample) if state else None
    ratings = rec["ratings"] if rec and rec.get("page_sha") == sha else {}
    items = [{k: it[k] for k in ("position", "claim", "quote", "context")} for it in page["items"]]
    return {"experiment": experiment, "sample": sample, "page_sha": sha, "items": items,
            "ratings": {k: _public_rating(v) for k, v in ratings.items()}, "status": _status(rec, sha),
            "progress": _progress(len(items), rec, sha)}


def _public_rating(r: dict) -> dict:
    return {k: r.get(k) for k in ("verdicts", "source_mode", "comment")}


def validate(verdicts, source_mode, comment) -> tuple[list[str], str | None, str]:
    """The same rules as ``exocortex lab blind import``: at least one verdict from the set, "correct" alone,
    at most one source mode from the set. A comment is one line of plain text."""
    if not isinstance(verdicts, list) or not verdicts or not all(isinstance(v, str) for v in verdicts):
        raise RatingError("choose at least one category")
    if any(v not in VERDICTS for v in verdicts) or len(set(verdicts)) != len(verdicts):
        raise RatingError("unknown category")
    if "correct" in verdicts and len(verdicts) > 1:
        raise RatingError("correct cannot go with an error")
    if source_mode is not None and source_mode not in SOURCE_MODES:
        raise RatingError("unknown source mode")
    if comment is None:
        comment = ""
    if not isinstance(comment, str) or len(comment) > MAX_COMMENT:
        raise RatingError(f"the comment must be text of at most {MAX_COMMENT} characters")
    comment = " ".join(comment.split())
    return [v for v in VERDICTS if v in verdicts], source_mode, comment


def rate(lab: Path, state: Path, experiment: str, sample: str, position, verdicts, source_mode, comment,
         page_sha, who: str) -> dict:
    """Record one rating; returns the progress. The page must be the one the owner was shown."""
    verdicts, source_mode, comment = validate(verdicts, source_mode, comment)
    with _LOCK:
        got = _read_page(lab, experiment, sample)
        if got is None:
            raise RatingError("no such rating page")
        text, page = got
        sha = _sha(text)
        if page_sha != sha:
            raise RatingError("the page changed since it was shown; open it again")
        if not isinstance(position, int) or isinstance(position, bool) or not 1 <= position <= len(page["items"]):
            raise RatingError("no such item")
        rec = _load(state, experiment, sample)
        if rec is None or rec.get("page_sha") != sha:
            if rec is not None and rec["ratings"]:
                _archive(state, experiment, sample)
            rec = {"experiment": experiment, "sample": sample, "lang": page["lang"], "page_sha": sha, "ratings": {}}
        rec["ratings"][str(position)] = {"verdicts": verdicts, "source_mode": source_mode, "comment": comment,
                                         "at": _now(), "who": who}
        rec.pop("finished", None)  # a change after finishing needs another finish
        _atomic(_state_file(state, experiment, sample), json.dumps(rec, ensure_ascii=False))
        return {"progress": _progress(len(page["items"]), rec, sha), "status": _status(rec, sha)}


def _archive(state: Path, experiment: str, sample: str) -> None:
    src = _state_file(state, experiment, sample)
    try:
        os.replace(src, src.with_name(f"{sample}.{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}.old.json"))
    except OSError:
        pass


def finish(lab: Path, state: Path, experiment: str, sample: str, page_sha, rater: str) -> dict:
    """Mark the sample as rated and ask for the page to be written (the request file for apply-ratings)."""
    if not NAME.fullmatch(rater or ""):
        raise RatingError("the rater's pseudonym must match [a-z0-9][a-z0-9-]*")
    with _LOCK:
        got = _read_page(lab, experiment, sample)
        if got is None:
            raise RatingError("no such rating page")
        text, page = got
        sha = _sha(text)
        rec = _load(state, experiment, sample)
        if page_sha != sha or rec is None or rec.get("page_sha") != sha:
            raise RatingError("the page changed since it was shown; open it again")
        missing = [n for n in range(1, len(page["items"]) + 1) if str(n) not in rec["ratings"]]
        if missing:
            raise RatingError(f"{len(missing)} item(s) not rated yet")
        rec["finished"] = {"at": _now(), "rater": rater}
        _atomic(_state_file(state, experiment, sample), json.dumps(rec, ensure_ascii=False))
    request(state, rater)
    return {"status": _status(rec, sha)}


def request(state: Path, who: str) -> bool:
    """Write the request file that starts apply-ratings; False when one is already waiting."""
    try:
        fd = os.open(state / REQUEST_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({"at": _now(), "who": who}, fh)
    return True


def fill(text: str, ratings: dict, rater: str) -> str:
    """The page with the boxes of every rating ticked, the comment after its label, the rater and
    ``rating_complete: true`` in the header. Everything else stays as it was."""
    front = _front(text)
    page = parse_page(text)
    if front is None or page is None:
        raise RatingError("not a rating page")
    lab = LABELS[page["lang"]]
    m = _FRONT.match(text)
    head = m.group(1)
    for key, value in (("rater", rater), ("rating_complete", "true")):
        head, n = re.subn(rf"^{key}:.*$", f"{key}: {value}", head, count=1, flags=re.M)
        if n != 1:
            raise RatingError(f"the header has no {key} field")
    body = text[m.end():]
    marks = list(_ITEM.finditer(body))
    parts = [body[: marks[0].start()]]
    for i, mk in enumerate(marks):
        chunk = body[mk.start(): marks[i + 1].start() if i + 1 < len(marks) else len(body)]
        r = ratings.get(mk.group(1))
        if r is None:
            raise RatingError(f"item {mk.group(1)} is not rated")
        ticked = {lab[v] for v in r["verdicts"]} | ({lab[r["source_mode"]]} if r.get("source_mode") else set())
        lines = []
        for line in chunk.split("\n"):
            box = re.fullmatch(r"- \[[ xX]\] (.+?)\s*", line)
            if box:
                line = f"- [{'x' if box.group(1) in ticked else ' '}] {box.group(1)}"
            elif line.startswith(f"{lab['comment']}:"):
                line = f"{lab['comment']}:" + (f" {r['comment']}" if r.get("comment") else "")
            lines.append(line)
        parts.append("\n".join(lines))
    return "---\n" + head + "---\n" + "".join(parts)


def target_of(docs: Path, lang: str, experiment: str, sample: str) -> Path:
    return docs / lang / "experiments" / experiment / f"{sample}.md"


def apply(docs: Path, lab: Path, state: Path) -> list[dict]:
    """Write the rated page of every finished sample into the vault. One result per finished sample.

    A page in the vault is replaced only when this job wrote it (its checksum is on record); a page filled
    by hand is left alone and reported.
    """
    results = []
    root = state / FOLDER
    for f in sorted(root.glob("*/*.json")) if root.is_dir() else []:
        if f.name.endswith(".old.json") or not NAME.fullmatch(f.parent.name) or not NAME.fullmatch(f.stem):
            continue
        experiment, sample = f.parent.name, f.stem
        with _LOCK:
            rec = _load(state, experiment, sample)
            if rec is None or not rec.get("finished"):
                continue
            res = {"experiment": experiment, "sample": sample, "rater": rec["finished"].get("rater")}
            got = _read_page(lab, experiment, sample)
            if rec.get("written") and rec["written"].get("ratings_sha") == _ratings_sha(rec):
                continue  # already in the vault
            if got is None or _sha(got[0]) != rec.get("page_sha"):
                res["result"] = "skipped: the rating page changed after rating"
            else:
                target = target_of(docs, rec.get("lang", "pl"), experiment, sample)
                try:
                    new = fill(got[0], rec["ratings"], rec["finished"]["rater"])
                    old = target.read_text(encoding="utf-8") if target.exists() else None
                    ours = {w.get("sha") for w in rec.get("history", [])} | {(rec.get("written") or {}).get("sha")}
                    if old is not None and old != new and _sha(old) not in ours:
                        res["result"] = "skipped: a page not written by the desk is already in the vault"
                    else:
                        if old != new:
                            _atomic(target, new)
                        rec["written"] = {"sha": _sha(new), "ratings_sha": _ratings_sha(rec), "at": _now(),
                                          "path": str(target.relative_to(docs))}
                        rec.setdefault("history", []).append({"sha": _sha(new), "at": rec["written"]["at"]})
                        _atomic(_state_file(state, experiment, sample), json.dumps(rec, ensure_ascii=False))
                        res["result"] = "written"
                        res["path"] = rec["written"]["path"]
                except (OSError, RatingError) as exc:
                    res["result"] = f"failed: {type(exc).__name__}"
            res["done"] = _now()
            with (root / LOG).open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(res) + "\n")
            results.append(res)
    return results
