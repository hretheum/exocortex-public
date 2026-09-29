# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Approval of drafts on the review desk.

A draft of the business applications of a hypothesis (``{pl,en}/experiments/<slug>/applications.md``)
has ``publish: false`` and ``human_validated: false`` in both language versions. It waits in one of two
places: in the vault (a draft put there by hand), or in the lab's drafts folder, where the lab's draft job
writes it and which the desk and ``apply`` mount read-only (origin ``lab``). The owner reads it on the desk
and approves it. The desk never writes into the vault: it records the decision (with the checksums of the
two texts the owner saw) in the state folder. When the owner presses "Publish now", ``apply`` runs first, in
a container that may write to the vault. For a draft in the vault it changes exactly two header lines in
each version to ``true``; for a draft from the lab it writes both versions into the vault with those two
lines set to ``true``, replacing the section there. Either way only if both texts are still the ones that
were approved. Then the publisher runs and applies every gate as usual. A text written by a model reaches
the vault only this way.

Only text of the vault reaches this module; nothing is sent anywhere.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

LANGS = ("pl", "en")
ORIGINS = ("vault", "lab")
NAME = "applications.md"
FOLDER = "approvals"
LOG = "log.jsonl"
SLUG = re.compile(r"[a-z0-9][a-z0-9-]*")
MAX_TEXT = 200_000
_FRONT = re.compile(r"\A---\n(.*?\n)---\n", re.DOTALL)
_FLAG = {"publish": re.compile(r"^publish:[ \t]*(true|false)[ \t]*$", re.MULTILINE),
         "human_validated": re.compile(r"^human_validated:[ \t]*(true|false)[ \t]*$", re.MULTILINE)}


class ApprovalError(Exception):
    pass


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def path_of(docs: Path, lang: str, slug: str) -> Path:
    return docs / lang / "experiments" / slug / NAME


def flags(text: str) -> dict[str, bool] | None:
    """The top-level ``publish`` and ``human_validated`` of the header, or None if either is missing or repeated."""
    m = _FRONT.match(text)
    if not m:
        return None
    out = {}
    for name, rx in _FLAG.items():
        found = rx.findall(m.group(1))
        if len(found) != 1:
            return None
        out[name] = found[0] == "true"
    return out


def flip(text: str) -> str:
    """The text with ``publish: true`` and ``human_validated: true`` in the header; nothing else changes."""
    m = _FRONT.match(text)
    if not m or flags(text) is None:
        raise ApprovalError("the header has no single publish and human_validated field")
    head = m.group(1)
    for name, rx in _FLAG.items():
        head = rx.sub(f"{name}: true", head, count=1)
    return "---\n" + head + "---\n" + text[m.end():]


def _title(text: str) -> str:
    m = re.search(r"^# (.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _read(p: Path) -> str | None:
    try:
        if not p.is_file() or p.stat().st_size > MAX_TEXT:
            return None
        return p.read_text(encoding="utf-8")
    except OSError:
        return None


def _approval_file(state: Path, slug: str, origin: str = "vault") -> Path:
    return state / FOLDER / (f"{slug}.json" if origin == "vault" else f"{slug}.{origin}.json")


def _load(state: Path, slug: str, origin: str = "vault") -> dict | None:
    try:
        d = json.loads(_approval_file(state, slug, origin).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and isinstance(d.get("sha"), dict) else None


def _slugs(docs: Path) -> list[str]:
    found = set()
    for lang in LANGS:
        for p in (docs / lang / "experiments").glob(f"*/{NAME}"):
            if SLUG.fullmatch(p.parent.name):
                found.add(p.parent.name)
    return sorted(found)


def _pair_state(texts: dict[str, str | None]) -> str:
    """``draft`` (both versions unapproved), ``live`` (both approved) or ``broken`` (anything else)."""
    fl = {lang: flags(t) if t is not None else None for lang, t in texts.items()}
    if any(t is None for t in texts.values()) or any(f is None for f in fl.values()):
        return "broken"
    if all(not f["publish"] and not f["human_validated"] for f in fl.values()):
        return "draft"
    if all(f["publish"] and f["human_validated"] for f in fl.values()):
        return "live"
    return "broken"


def _entry(slug: str, origin: str, st: str, texts: dict, state: Path | None) -> dict:
    sha = {lang: _sha(t) for lang, t in texts.items() if t is not None}
    rec = _load(state, slug, origin) if state is not None else None
    approval = "none"
    if rec and st == "draft":
        approval = "waiting" if rec["sha"] == sha else "changed"
    return {"slug": slug, "origin": origin, "state": st, "approval": approval, "sha": sha,
            "title": {lang: _title(t or "") for lang, t in texts.items()},
            "text": {lang: t for lang, t in texts.items() if t is not None}}


def list_drafts(docs: Path, state: Path | None, drafts: Path | None = None) -> list[dict]:
    """Every applications pair in the vault, then every draft pair in the lab's drafts folder, with its state.

    ``state``: ``draft`` (both versions unapproved), ``live`` (both approved), ``broken`` (anything else, not
    approvable). ``approval``: ``none``, ``waiting`` (approved on the desk, applied at the next publish) or
    ``changed`` (a text changed after the approval, so it will not be applied). A draft from the lab is
    listed only while it is a draft in both languages and not yet in the vault; ``replaces`` gives the state
    of the section it would replace there (None when there is none).
    """
    out, vault = [], {}
    for slug in _slugs(docs):
        texts = {lang: _read(path_of(docs, lang, slug)) for lang in LANGS}
        vault[slug] = texts
        out.append(_entry(slug, "vault", _pair_state(texts), texts, state))
    for slug in _slugs(drafts) if drafts is not None and drafts.is_dir() else []:
        texts = {lang: _read(path_of(drafts, lang, slug)) for lang in LANGS}
        if _pair_state(texts) != "draft":
            continue  # the lab writes drafts only; anything else is not offered for approval
        live = vault.get(slug) or {}
        if all(live.get(lang) == flip(texts[lang]) for lang in LANGS):
            continue  # already switched on in the vault
        entry = _entry(slug, "lab", "draft", texts, state)
        entry["replaces"] = _pair_state(live) if slug in vault else None
        out.append(entry)
    return out


def _origin(origin) -> str:
    origin = origin or "vault"
    if origin not in ORIGINS:
        raise ApprovalError("unknown origin")
    return origin


def approve(docs: Path, state: Path, slug: str, sha: dict, who: str, origin: str | None = "vault",
            drafts: Path | None = None) -> dict:
    """Record the owner's approval of the two texts with these checksums."""
    if not SLUG.fullmatch(slug or ""):
        raise ApprovalError("bad name")
    origin = _origin(origin)
    draft = next((d for d in list_drafts(docs, state, drafts) if d["slug"] == slug and d["origin"] == origin), None)
    if draft is None:
        raise ApprovalError("no such draft")
    if draft["state"] != "draft":
        raise ApprovalError("only a draft with both versions unapproved can be approved")
    if not isinstance(sha, dict) or draft["sha"] != {k: sha.get(k) for k in LANGS}:
        raise ApprovalError("the text changed since it was shown; read it again")
    folder = state / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    rec = {"slug": slug, "origin": origin, "who": who,
           "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "sha": draft["sha"]}
    _atomic(_approval_file(state, slug, origin), json.dumps(rec))
    return rec


def withdraw(state: Path, slug: str, origin: str | None = "vault") -> bool:
    if not SLUG.fullmatch(slug or ""):
        raise ApprovalError("bad name")
    try:
        _approval_file(state, slug, _origin(origin)).unlink()
        return True
    except FileNotFoundError:
        return False


def _atomic(path: Path, text: str) -> None:
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


def apply(docs: Path, state: Path, drafts: Path | None = None) -> list[dict]:
    """Switch on every pair the owner approved whose texts are unchanged. One result per approval.

    A draft in the vault gets its two flags set; a draft from the lab's drafts folder is written into the
    vault with the two flags set. Nothing else is written.
    """
    results = []
    folder = state / FOLDER
    for f in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        slug, _, origin = f.stem.partition(".")
        origin = origin or "vault"
        rec = _load(state, slug, origin) if origin in ORIGINS else None
        res = {"slug": slug, "origin": origin, "who": (rec or {}).get("who"), "at": (rec or {}).get("at")}
        d = next((x for x in list_drafts(docs, state, drafts) if x["slug"] == slug and x["origin"] == origin), None)
        if rec is None or not SLUG.fullmatch(slug):
            res["result"] = "skipped: unreadable approval"
        elif d is None or d["state"] != "draft":
            res["result"] = "skipped: not a draft any more"
        elif d["sha"] != rec["sha"]:
            res["result"] = "skipped: changed after the approval"
        else:
            written = []
            try:
                for lang in LANGS:
                    p = path_of(docs, lang, slug)
                    old = _read(p) if origin == "lab" else d["text"][lang]
                    if origin == "lab":
                        p.parent.mkdir(parents=True, exist_ok=True)
                    _atomic(p, flip(d["text"][lang]))
                    written.append((p, old))
                res["result"] = "applied"
            except (OSError, ApprovalError) as exc:
                for p, old in written:  # put the first version back if the second could not be written
                    try:
                        if old is None:
                            p.unlink()
                        else:
                            _atomic(p, old)
                    except OSError:
                        pass
                res["result"] = f"failed: {type(exc).__name__}"
        if not res["result"].startswith("failed"):
            try:
                f.unlink()
            except OSError:
                pass
        res["done"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        with (folder / LOG).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(res) + "\n")
        results.append(res)
    return results
