"""Quarantine database of the publishing gate (SQLite, one file on the state volume).

A held unit of publication (a publication class plus a key: the experiment
slug, or the path of a document) has findings. A finding is a rule name, a
path and the SHA-256 of a paragraph, with a similarity score; the database
never stores paragraph text. The only free text in it is a person's own
short note ("to edit") and the reasons given for waivers, and the history
records who decided what and when, without any text.

Finding states
    open      waits for a decision
    kept      a person approved the paragraph (its hash is in ``approvals``)
    to_edit   the paragraph has to be rewritten; the note says what
    outdated  the source changed and the paragraph is gone or different

A unit is ``released`` when it has no open and no to_edit findings.

Literal findings (personal data, names, a list of names, near copies) can
never be kept, only marked to_edit. A rule is approvable only if it is in
``APPROVABLE_RULES``; every unknown rule counts as literal (fail-closed).

Also kept here: the approvals themselves (imported once from the older text
file, which is only read), the list of protected sources switched off from
protection (with a hard list of paths that can never be switched off) and
standing rules "always keep this folder".
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Callable, Iterable

OPEN, KEPT, TO_EDIT, RELEASED, OUTDATED = "open", "kept", "to_edit", "released", "outdated"
FINDING_STATES = (OPEN, KEPT, TO_EDIT, OUTDATED)
UNIT_STATES = (OPEN, RELEASED)

# Rules of the semantic layer: a person may judge them. Everything else is literal.
APPROVABLE_RULES = frozenset({"semantic", "semantic-judged"})

MAX_NOTE = 500
MAX_REASON = 300
DEFAULT_RULE_DAYS = 90
MAX_RULE_DAYS = 365
UNDOABLE = ("keep", "to_edit", "bulk_keep")


class QuarantineError(Exception):
    """Base of every error raised on purpose; the message never holds text of a paragraph."""


class NotFound(QuarantineError):
    pass


class InvalidState(QuarantineError):
    pass


class InvalidInput(QuarantineError):
    pass


class LiteralNotApprovable(QuarantineError):
    pass


class HardListUnavailable(QuarantineError):
    pass


class HardListViolation(QuarantineError):
    pass


class StaleConfirmation(QuarantineError):
    pass


def is_literal_rule(rule: str) -> bool:
    return rule not in APPROVABLE_RULES


def paragraph_key(text: str) -> str:
    """Same identity as simcheck's paragraph_hash (kept here so this module needs no numpy)."""
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()


def clean_path(path: str, folder: bool = False) -> str:
    """A clean relative path; a folder ends with one slash. Raises InvalidInput for anything unusual."""
    if not isinstance(path, str):
        raise InvalidInput("path must be a string")
    p = path.strip()
    is_folder = folder or p.endswith("/")
    parts = p.strip("/").split("/")
    if (not p or p.startswith("/") or "\\" in p or "\0" in p or len(p) > 512
            or any(not s or s in (".", "..") for s in parts)):
        raise InvalidInput("unusable path")
    return "/".join(parts) + ("/" if is_folder else "")


def covers(prefix: str, path: str) -> bool:
    """``prefix`` is the path itself or a folder (with or without the trailing slash) that holds it."""
    a, b = prefix.casefold().rstrip("/"), path.casefold().rstrip("/")
    return b == a or b.startswith(a + "/")


def load_hard_list(path: Path | str | None) -> list[str]:
    """Paths that may never be switched off, one per line, ``#`` starts a comment.

    Raises HardListUnavailable when the file is not configured or unreadable:
    without the list nothing may be switched off.
    """
    if not path:
        raise HardListUnavailable("the hard list of protected paths is not configured")
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise HardListUnavailable("the hard list of protected paths cannot be read") from exc
    out = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(clean_path(line))
    return out


def _iso(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(s: str) -> dt.datetime:
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)


SCHEMA = """
CREATE TABLE IF NOT EXISTS units(
  id INTEGER PRIMARY KEY, cls TEXT NOT NULL, key TEXT NOT NULL, source_hash TEXT NOT NULL,
  state TEXT NOT NULL, created_at TEXT NOT NULL, opened_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(cls, key));
CREATE TABLE IF NOT EXISTS unit_files(unit_id INTEGER NOT NULL, path TEXT NOT NULL, PRIMARY KEY(unit_id, path));
CREATE TABLE IF NOT EXISTS findings(
  id INTEGER PRIMARY KEY, unit_id INTEGER NOT NULL, rule TEXT NOT NULL, path TEXT NOT NULL,
  para_hash TEXT NOT NULL, score REAL NOT NULL, literal INTEGER NOT NULL, state TEXT NOT NULL,
  kept_via TEXT, note TEXT, source_hash TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS findings_unit ON findings(unit_id, state);
CREATE INDEX IF NOT EXISTS findings_hash ON findings(para_hash);
CREATE TABLE IF NOT EXISTS approvals(para_hash TEXT PRIMARY KEY, origin TEXT NOT NULL, who TEXT NOT NULL, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS decisions(
  id INTEGER PRIMARY KEY, batch_id INTEGER NOT NULL, unit_id INTEGER, finding_id INTEGER, who TEXT NOT NULL,
  at TEXT NOT NULL, decision TEXT NOT NULL, prev_state TEXT, new_state TEXT, detail TEXT, undone INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS exclusions(
  id INTEGER PRIMARY KEY, path TEXT NOT NULL, reason TEXT NOT NULL, expires_at TEXT, who TEXT NOT NULL,
  at TEXT NOT NULL, revoked_at TEXT, revoked_by TEXT);
CREATE TABLE IF NOT EXISTS standing_rules(
  id INTEGER PRIMARY KEY, folder TEXT NOT NULL, reason TEXT NOT NULL, expires_at TEXT NOT NULL, who TEXT NOT NULL,
  at TEXT NOT NULL, revoked_at TEXT, revoked_by TEXT);
"""


class Store:
    """The quarantine database. Thread-safe (one connection, one lock).

    ``never_exclude_file`` is the hard list; ``clock`` returns the current UTC time (tests inject it).
    ``read_only`` opens an existing file without any write (for services that only read approvals).
    """

    def __init__(self, path: Path | str, *, never_exclude_file: Path | str | None = None,
                 clock: Callable[[], dt.datetime] | None = None, read_only: bool = False):
        self.path = Path(path)
        self.never_exclude_file = never_exclude_file
        self.clock = clock or (lambda: dt.datetime.now(dt.timezone.utc))
        self.read_only = read_only
        self.lock = threading.RLock()
        if read_only:
            self.db = sqlite3.connect(f"{self.path.resolve().as_uri()}?mode=ro", uri=True, check_same_thread=False,
                                      isolation_level=None, timeout=5)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fresh = not self.path.exists()
            self.db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None, timeout=5)
            if fresh:
                os.chmod(self.path, 0o600)
            self.db.executescript(SCHEMA)
        self.db.row_factory = sqlite3.Row

    # -- plumbing ---------------------------------------------------------------
    def close(self) -> None:
        self.db.close()

    def now(self) -> str:
        return _iso(self.clock())

    def revision(self) -> int:
        """Changes whenever another connection commits; services use it to reload approvals cheaply."""
        with self.lock:
            return self.db.execute("PRAGMA data_version").fetchone()[0]

    def _tx(self):
        store = self

        class Tx:
            def __enter__(self_):
                store.lock.acquire()
                if store.read_only:
                    store.lock.release()
                    raise QuarantineError("the database is open read-only")
                store.db.execute("BEGIN IMMEDIATE")
                return store.db

            def __exit__(self_, exc_type, exc, tb):
                try:
                    store.db.execute("ROLLBACK" if exc_type else "COMMIT")
                finally:
                    store.lock.release()
                return False

        return Tx()

    def _q(self, sql: str, args: Iterable = ()) -> list[sqlite3.Row]:
        with self.lock:
            return self.db.execute(sql, tuple(args)).fetchall()

    def _record(self, db, batch: int, decision: str, who: str, *, unit_id=None, finding_id=None,
                prev=None, new=None, detail=None) -> int:
        cur = db.execute("INSERT INTO decisions(batch_id, unit_id, finding_id, who, at, decision, prev_state, new_state, detail)"
                         " VALUES(?,?,?,?,?,?,?,?,?)",
                         (batch, unit_id, finding_id, who, self.now(), decision, prev, new, detail))
        return cur.lastrowid

    @staticmethod
    def _batch(db) -> int:
        return db.execute("SELECT COALESCE(MAX(batch_id), 0) + 1 FROM decisions").fetchone()[0]

    # -- approvals --------------------------------------------------------------
    def approved_hashes(self) -> set[str]:
        return {r[0] for r in self._q("SELECT para_hash FROM approvals")}

    def import_approved_file(self, path: Path | str, who: str = "import") -> dict:
        """Import approvals from the older text file (one hash per line, ``#`` starts a comment).

        The file is only read. Hashes already present are left as they are.
        """
        p = Path(path)
        seen = added = 0
        hashes = []
        if p.is_file():
            for line in p.read_text(encoding="utf-8").splitlines():
                h = line.split("#", 1)[0].strip().lower()
                if len(h) == 64 and all(c in "0123456789abcdef" for c in h):
                    hashes.append(h)
        with self._tx() as db:
            batch = self._batch(db)
            for h in dict.fromkeys(hashes):
                seen += 1
                cur = db.execute("INSERT OR IGNORE INTO approvals(para_hash, origin, who, at) VALUES(?,?,?,?)",
                                 (h, "import", who, self.now()))
                added += cur.rowcount
            self._record(db, batch, "import", who, detail=f"{added} of {seen}")
        return {"seen": seen, "added": added}

    def _prune_approvals(self, db, hashes: Iterable[str]) -> None:
        """Drop approvals whose last supporting finding is gone; imported ones stay."""
        for h in set(hashes):
            still = db.execute("SELECT 1 FROM findings WHERE para_hash=? AND state=? LIMIT 1", (h, KEPT)).fetchone()
            if not still:
                db.execute("DELETE FROM approvals WHERE para_hash=? AND origin<>'import'", (h,))

    def _approve(self, db, h: str, origin: str, who: str) -> None:
        db.execute("INSERT OR IGNORE INTO approvals(para_hash, origin, who, at) VALUES(?,?,?,?)",
                   (h, origin, who, self.now()))

    # -- units ------------------------------------------------------------------
    def sync_unit(self, cls: str, key: str, files: Iterable[str], source_hash: str,
                  findings: Iterable[dict], who: str = "intake") -> dict:
        """Bring a unit in line with the current source.

        ``findings`` are dicts with rule, path, para_hash (empty for a whole
        file) and score. A finding that is still present keeps its state; one
        that is gone or whose paragraph changed becomes outdated; a new one
        is open. Standing rules are applied to new non-literal findings.
        """
        files = sorted(set(files))
        wanted: dict[tuple, dict] = {}
        for f in findings:
            item = (str(f["rule"]), clean_path(f["path"]), str(f.get("para_hash", "")))
            if item[2] and len(item[2]) != 64:
                raise InvalidInput("para_hash must be a SHA-256 hex digest")
            prev = wanted.get(item)
            wanted[item] = {"score": max(float(f.get("score", 0.0)), prev["score"] if prev else 0.0)}
        now = self.now()
        counts = {"new": 0, "kept": 0, "outdated": 0}
        with self._tx() as db:
            row = db.execute("SELECT * FROM units WHERE cls=? AND key=?", (cls, key)).fetchone()
            if row is None:
                if not wanted:
                    return counts
                uid = db.execute("INSERT INTO units(cls,key,source_hash,state,created_at,opened_at,updated_at)"
                                 " VALUES(?,?,?,?,?,?,?)", (cls, key, source_hash, OPEN, now, now, now)).lastrowid
            else:
                uid = row["id"]
                db.execute("UPDATE units SET source_hash=?, updated_at=? WHERE id=?", (source_hash, now, uid))
            db.execute("DELETE FROM unit_files WHERE unit_id=?", (uid,))
            db.executemany("INSERT INTO unit_files(unit_id, path) VALUES(?,?)", [(uid, p) for p in files])
            batch = self._batch(db)
            pruned = []
            current = db.execute("SELECT * FROM findings WHERE unit_id=? AND state<>?", (uid, OUTDATED)).fetchall()
            present = set()
            for r in current:
                ident = (r["rule"], r["path"], r["para_hash"])
                if ident in wanted:
                    present.add(ident)
                    db.execute("UPDATE findings SET source_hash=?, score=?, updated_at=? WHERE id=?",
                               (source_hash, wanted[ident]["score"], now, r["id"]))
                    counts["kept"] += 1
                else:
                    db.execute("UPDATE findings SET state=?, updated_at=? WHERE id=?", (OUTDATED, now, r["id"]))
                    self._record(db, batch, "outdated", who, unit_id=uid, finding_id=r["id"], prev=r["state"], new=OUTDATED)
                    counts["outdated"] += 1
                    if r["state"] == KEPT:
                        pruned.append(r["para_hash"])
            approved = {r[0] for r in db.execute("SELECT para_hash FROM approvals")}
            for ident, val in wanted.items():
                if ident in present:
                    continue
                rule, path, h = ident
                literal = is_literal_rule(rule) or not h
                state, via = OPEN, None
                if not literal and h in approved:
                    state, via = KEPT, "approved"
                cur = db.execute("INSERT INTO findings(unit_id,rule,path,para_hash,score,literal,state,kept_via,source_hash,"
                                 "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                                 (uid, rule, path, h, val["score"], int(literal), state, via, source_hash, now, now))
                self._record(db, batch, "new", who, unit_id=uid, finding_id=cur.lastrowid, new=state)
                counts["new"] += 1
            self._prune_approvals(db, pruned)
            self._expire_rules(db)
            self._apply_standing(db, uid)
            self._refresh_unit(db, uid)
        return counts

    def _refresh_unit(self, db, uid: int) -> str:
        n = db.execute("SELECT COUNT(*) FROM findings WHERE unit_id=? AND state IN (?,?)", (uid, OPEN, TO_EDIT)).fetchone()[0]
        state = OPEN if n else RELEASED
        old = db.execute("SELECT state FROM units WHERE id=?", (uid,)).fetchone()[0]
        now = self.now()
        if state == OPEN and old != OPEN:
            db.execute("UPDATE units SET state=?, opened_at=?, updated_at=? WHERE id=?", (state, now, now, uid))
        else:
            db.execute("UPDATE units SET state=?, updated_at=? WHERE id=?", (state, now, uid))
        return state

    def _unit_row(self, r: sqlite3.Row) -> dict:
        counts = {s: 0 for s in FINDING_STATES}
        for s, n in self._q("SELECT state, COUNT(*) FROM findings WHERE unit_id=? GROUP BY state", (r["id"],)):
            counts[s] = n
        active = counts[OPEN] + counts[KEPT] + counts[TO_EDIT]
        age = max(0, (self.clock() - _parse(r["opened_at"])).days) if r["state"] == OPEN else 0
        return {"id": r["id"], "cls": r["cls"], "key": r["key"], "state": r["state"], "source_hash": r["source_hash"],
                "counts": counts, "findings": active, "age_days": age, "opened_at": r["opened_at"],
                "files": [x[0] for x in self._q("SELECT path FROM unit_files WHERE unit_id=? ORDER BY path", (r["id"],))]}

    def list_units(self) -> list[dict]:
        rows = self._q("SELECT * FROM units ORDER BY (state='open') DESC, opened_at, cls, key")
        return [self._unit_row(r) for r in rows]

    def count_waiting_units(self) -> int:
        """Units with at least one open finding: what the queue lists as waiting for a decision."""
        return self._q(f"SELECT COUNT(DISTINCT unit_id) FROM findings WHERE state='{OPEN}'")[0][0]

    def get_unit(self, uid: int) -> dict:
        rows = self._q("SELECT * FROM units WHERE id=?", (uid,))
        if not rows:
            raise NotFound("unit")
        return self._unit_row(rows[0])

    def progress(self, uid: int) -> dict:
        c = self.get_unit(uid)["counts"]
        total = c[OPEN] + c[KEPT] + c[TO_EDIT]
        return {"total": total, "decided": c[KEPT] + c[TO_EDIT], "to_edit": c[TO_EDIT], "open": c[OPEN]}

    @staticmethod
    def _finding(r: sqlite3.Row) -> dict:
        return {"id": r["id"], "unit_id": r["unit_id"], "rule": r["rule"], "path": r["path"], "para_hash": r["para_hash"],
                "score": r["score"], "literal": bool(r["literal"]), "state": r["state"], "kept_via": r["kept_via"],
                "note": r["note"], "updated_at": r["updated_at"]}

    def findings(self, uid: int, states: Iterable[str] | None = None) -> list[dict]:
        self.get_unit(uid)
        rows = self._q("SELECT * FROM findings WHERE unit_id=? ORDER BY path, id", (uid,))
        return [self._finding(r) for r in rows if states is None or r["state"] in states]

    def finding(self, fid: int) -> dict:
        rows = self._q("SELECT * FROM findings WHERE id=?", (fid,))
        if not rows:
            raise NotFound("finding")
        return self._finding(rows[0])

    # -- decisions --------------------------------------------------------------
    def decide(self, fid: int, decision: str, who: str, note: str | None = None) -> dict:
        """``keep`` or ``to_edit`` for one finding. A literal finding can only be to_edit."""
        if decision not in ("keep", "to_edit"):
            raise InvalidInput("decision must be keep or to_edit")
        if note is not None and (not isinstance(note, str) or len(note) > MAX_NOTE):
            raise InvalidInput("note too long")
        with self._tx() as db:
            r = db.execute("SELECT * FROM findings WHERE id=?", (fid,)).fetchone()
            if r is None:
                raise NotFound("finding")
            if r["state"] == OUTDATED:
                raise InvalidState("the finding is outdated")
            if decision == "keep" and (r["literal"] or is_literal_rule(r["rule"]) or not r["para_hash"]):
                raise LiteralNotApprovable("a literal finding cannot be kept; mark it to edit")
            new = KEPT if decision == "keep" else TO_EDIT
            batch = self._batch(db)
            db.execute("UPDATE findings SET state=?, kept_via=?, note=?, updated_at=? WHERE id=?",
                       (new, "manual" if new == KEPT else None, (note or None) if new == TO_EDIT else None, self.now(), fid))
            if new == KEPT:
                self._approve(db, r["para_hash"], "decision", who)
            self._record(db, batch, decision, who, unit_id=r["unit_id"], finding_id=fid, prev=r["state"], new=new)
            if r["state"] == KEPT and new != KEPT:
                self._prune_approvals(db, [r["para_hash"]])
            self._refresh_unit(db, r["unit_id"])
        return self.finding(fid)

    def reopen(self, fid: int, who: str) -> dict:
        """Put a decided finding back in the queue: one marked to edit, or kept by hand.
        A finding kept by an approval or a standing rule is not the person's decision to take back here."""
        with self._tx() as db:
            r = db.execute("SELECT * FROM findings WHERE id=?", (fid,)).fetchone()
            if r is None:
                raise NotFound("finding")
            if not (r["state"] == TO_EDIT or (r["state"] == KEPT and r["kept_via"] == "manual")):
                raise InvalidState("only a finding kept by hand or marked to edit can be reopened")
            db.execute("UPDATE findings SET state=?, kept_via=NULL, note=NULL, updated_at=? WHERE id=?", (OPEN, self.now(), fid))
            self._record(db, self._batch(db), "reopen", who, unit_id=r["unit_id"], finding_id=fid, prev=r["state"], new=OPEN)
            if r["state"] == KEPT:
                self._prune_approvals(db, [r["para_hash"]])
            self._refresh_unit(db, r["unit_id"])
        return self.finding(fid)

    def undo_last(self, who: str) -> dict | None:
        """Undo the newest decision (a whole bulk decision counts as one). Returns what was undone, or None."""
        with self._tx() as db:
            last = db.execute("SELECT batch_id FROM decisions WHERE undone=0 AND decision IN (?,?,?) "
                              "ORDER BY id DESC LIMIT 1", UNDOABLE).fetchone()
            if last is None:
                return None
            rows = db.execute("SELECT * FROM decisions WHERE batch_id=? AND undone=0 AND decision IN (?,?,?) ORDER BY id DESC",
                              (last[0], *UNDOABLE)).fetchall()
            hashes, units, restored = [], set(), []
            for d in rows:
                f = db.execute("SELECT * FROM findings WHERE id=?", (d["finding_id"],)).fetchone()
                if f is not None and f["state"] == d["new_state"]:
                    db.execute("UPDATE findings SET state=?, kept_via=NULL, note=NULL, updated_at=? WHERE id=?",
                               (d["prev_state"], self.now(), f["id"]))
                    hashes.append(f["para_hash"])
                    restored.append(f["id"])
                    if d["prev_state"] == KEPT:  # re-decided earlier: the earlier keep comes back with its approval
                        db.execute("UPDATE findings SET kept_via='manual' WHERE id=?", (f["id"],))
                        self._approve(db, f["para_hash"], "decision", who)
                units.add(d["unit_id"])
                db.execute("UPDATE decisions SET undone=1 WHERE id=?", (d["id"],))
            self._prune_approvals(db, hashes)
            for uid in units:
                self._refresh_unit(db, uid)
            self._record(db, self._batch(db), "undo", who, unit_id=next(iter(units), None), detail=f"batch {last[0]}")
        return {"batch": last[0], "findings": sorted(restored), "unit_id": next(iter(units), None)}

    # -- bulk -------------------------------------------------------------------
    def bulk_preview(self, uid: int, folder: str | None = None) -> dict:
        """What "keep the whole unit" (or a folder of it) would do, and whether it is allowed."""
        self.get_unit(uid)
        prefix = clean_path(folder, folder=True) if folder else None
        rows = [f for f in self.findings(uid, (OPEN, TO_EDIT))
                if prefix is None or covers(prefix, f["path"])]
        literal = [f for f in rows if f["literal"] or is_literal_rule(f["rule"]) or not f["para_hash"]]
        todo = [f for f in rows if f["state"] == OPEN]
        reason = None
        if literal:
            reason = f"{len(literal)} literal finding(s) in scope; literal findings can only be edited"
        elif not todo:
            reason = "nothing open in scope"
        digest = hashlib.sha256(json.dumps([[f["id"], f["state"], f["para_hash"]] for f in rows]).encode()).hexdigest()[:24]
        return {"unit_id": uid, "folder": prefix, "files": len({f["path"] for f in todo}), "paragraphs": len(todo),
                "max_score": max((f["score"] for f in todo), default=0.0), "literal": len(literal),
                "disabled": reason is not None, "reason": reason, "digest": digest, "ids": [f["id"] for f in todo]}

    def bulk_keep(self, uid: int, folder: str | None, digest: str, who: str) -> dict:
        """Keep every open finding in scope. ``digest`` is the one the preview showed: the person's confirmation."""
        with self.lock:
            pv = self.bulk_preview(uid, folder)
            if pv["disabled"]:
                raise LiteralNotApprovable(pv["reason"])
            if digest != pv["digest"]:
                raise StaleConfirmation("the findings changed since the summary was shown")
            with self._tx() as db:
                batch = self._batch(db)
                for fid in pv["ids"]:
                    db.execute("UPDATE findings SET state=?, kept_via='bulk', updated_at=? WHERE id=?", (KEPT, self.now(), fid))
                    h = db.execute("SELECT para_hash FROM findings WHERE id=?", (fid,)).fetchone()[0]
                    self._approve(db, h, "decision", who)
                    self._record(db, batch, "bulk_keep", who, unit_id=uid, finding_id=fid, prev=OPEN, new=KEPT,
                                 detail=pv["folder"] or "unit")
                self._refresh_unit(db, uid)
        return {k: pv[k] for k in ("files", "paragraphs", "max_score")}

    # -- standing rules ---------------------------------------------------------
    def add_standing_rule(self, folder: str, reason: str, who: str, days: int | None = None) -> dict:
        prefix = clean_path(folder, folder=True)
        reason = self._reason(reason)
        days = DEFAULT_RULE_DAYS if days is None else days
        if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= MAX_RULE_DAYS:
            raise InvalidInput(f"days must be between 1 and {MAX_RULE_DAYS}")
        expires = _iso(self.clock() + dt.timedelta(days=days))
        with self._tx() as db:
            rid = db.execute("INSERT INTO standing_rules(folder,reason,expires_at,who,at) VALUES(?,?,?,?,?)",
                             (prefix, reason, expires, who, self.now())).lastrowid
            self._record(db, self._batch(db), "standing_add", who, detail=f"rule:{rid} {prefix}")
            applied = 0
            for u in db.execute("SELECT id FROM units").fetchall():
                applied += self._apply_standing(db, u[0])
        return {"id": rid, "folder": prefix, "expires_at": expires, "applied": applied}

    def revoke_standing_rule(self, rid: int, who: str) -> None:
        with self._tx() as db:
            r = db.execute("SELECT * FROM standing_rules WHERE id=? AND revoked_at IS NULL", (rid,)).fetchone()
            if r is None:
                raise NotFound("rule")
            db.execute("UPDATE standing_rules SET revoked_at=?, revoked_by=? WHERE id=?", (self.now(), who, rid))
            self._record(db, self._batch(db), "standing_revoke", who, detail=f"rule:{rid}")
            self._release_rule(db, rid, "rule_revoked", who)

    def _release_rule(self, db, rid: int, decision: str, who: str) -> None:
        """Findings kept by a rule go back to open and lose the approval the rule gave them."""
        rows = db.execute("SELECT * FROM findings WHERE kept_via=? AND state=?", (f"rule:{rid}", KEPT)).fetchall()
        batch = self._batch(db)
        for f in rows:
            db.execute("UPDATE findings SET state=?, kept_via=NULL, updated_at=? WHERE id=?", (OPEN, self.now(), f["id"]))
            self._record(db, batch, decision, who, unit_id=f["unit_id"], finding_id=f["id"], prev=KEPT, new=OPEN,
                         detail=f"rule:{rid}")
        self._prune_approvals(db, [f["para_hash"] for f in rows])
        for uid in {f["unit_id"] for f in rows}:
            self._refresh_unit(db, uid)

    def _expire_rules(self, db) -> None:
        now = self.now()
        for r in db.execute("SELECT id FROM standing_rules WHERE revoked_at IS NULL AND expires_at<=?", (now,)).fetchall():
            db.execute("UPDATE standing_rules SET revoked_at=?, revoked_by=? WHERE id=?", (now, "expiry", r[0]))
            self._release_rule(db, r[0], "rule_expired", "expiry")

    def expire(self) -> None:
        """Retire expired standing rules now (also done on every sync)."""
        with self._tx() as db:
            self._expire_rules(db)

    def _apply_standing(self, db, uid: int) -> int:
        """Keep open non-literal findings under an active standing rule; every use goes to the history."""
        rules = db.execute("SELECT id, folder FROM standing_rules WHERE revoked_at IS NULL AND expires_at>?",
                           (self.now(),)).fetchall()
        if not rules:
            return 0
        batch, used = self._batch(db), 0
        for f in db.execute("SELECT * FROM findings WHERE unit_id=? AND state=? AND literal=0", (uid, OPEN)).fetchall():
            if is_literal_rule(f["rule"]) or not f["para_hash"]:
                continue
            rule = next((r for r in rules if covers(r["folder"], f["path"])), None)
            if rule is None:
                continue
            db.execute("UPDATE findings SET state=?, kept_via=?, updated_at=? WHERE id=?",
                       (KEPT, f"rule:{rule['id']}", self.now(), f["id"]))
            self._approve(db, f["para_hash"], f"rule:{rule['id']}", "rule")
            self._record(db, batch, "auto_keep", "rule", unit_id=uid, finding_id=f["id"], prev=OPEN, new=KEPT,
                         detail=f"rule:{rule['id']}")
            used += 1
        if used:
            self._refresh_unit(db, uid)
        return used

    def standing_rules(self, active_only: bool = False) -> list[dict]:
        now = self.now()
        out = []
        for r in self._q("SELECT * FROM standing_rules ORDER BY id DESC"):
            active = r["revoked_at"] is None and r["expires_at"] > now
            if active or not active_only:
                out.append({"id": r["id"], "folder": r["folder"], "reason": r["reason"], "expires_at": r["expires_at"],
                            "who": r["who"], "at": r["at"], "active": active, "revoked_at": r["revoked_at"]})
        return out

    # -- exclusions of protected sources ----------------------------------------
    @staticmethod
    def _reason(reason: str) -> str:
        if not isinstance(reason, str) or len(reason.strip()) < 3:
            raise InvalidInput("a reason is required")
        if len(reason) > MAX_REASON:
            raise InvalidInput("reason too long")
        return reason.strip()

    def add_exclusion(self, path: str, reason: str, who: str, expires_days: int | None = None,
                      folder: bool = False) -> dict:
        """Switch a protected source (a note, or a folder with ``folder=True`` or a trailing slash) off from protection.

        Refused when the hard list is missing or unreadable (fail-closed) and
        when the path is on the hard list or holds a path from it.
        """
        hard = load_hard_list(self.never_exclude_file)
        entry = clean_path(path, folder=folder)
        reason = self._reason(reason)
        for h in hard:
            if covers(entry, h) or covers(h, entry):
                raise HardListViolation("this path is on the hard list and cannot be switched off")
        expires = None
        if expires_days is not None:
            if not isinstance(expires_days, int) or isinstance(expires_days, bool) or not 1 <= expires_days <= 3650:
                raise InvalidInput("expires_days out of range")
            expires = _iso(self.clock() + dt.timedelta(days=expires_days))
        with self._tx() as db:
            eid = db.execute("INSERT INTO exclusions(path,reason,expires_at,who,at) VALUES(?,?,?,?,?)",
                             (entry, reason, expires, who, self.now())).lastrowid
            self._record(db, self._batch(db), "exclude", who, detail=f"{'folder' if entry.endswith('/') else 'note'}:{entry}")
        return {"id": eid, "path": entry, "expires_at": expires}

    def revoke_exclusion(self, eid: int, who: str) -> None:
        with self._tx() as db:
            r = db.execute("SELECT path FROM exclusions WHERE id=? AND revoked_at IS NULL", (eid,)).fetchone()
            if r is None:
                raise NotFound("exclusion")
            db.execute("UPDATE exclusions SET revoked_at=?, revoked_by=? WHERE id=?", (self.now(), who, eid))
            self._record(db, self._batch(db), "unexclude", who, detail=r[0])

    def exclusions(self, active_only: bool = False) -> list[dict]:
        now = self.now()
        out = []
        for r in self._q("SELECT * FROM exclusions ORDER BY id DESC"):
            active = r["revoked_at"] is None and (r["expires_at"] is None or r["expires_at"] > now)
            if active or not active_only:
                out.append({"id": r["id"], "path": r["path"], "reason": r["reason"], "expires_at": r["expires_at"],
                            "who": r["who"], "at": r["at"], "active": active, "revoked_at": r["revoked_at"]})
        return out

    def active_exclusion_paths(self) -> list[str]:
        return [e["path"] for e in self.exclusions(active_only=True)]

    def hard_list_status(self) -> dict:
        try:
            return {"available": True, "entries": len(load_hard_list(self.never_exclude_file))}
        except QuarantineError:
            return {"available": False, "entries": 0}

    # -- history ----------------------------------------------------------------
    def history(self, limit: int = 200, unit_id: int | None = None) -> list[dict]:
        sql = ("SELECT d.*, u.cls AS cls, u.key AS ukey, f.path AS fpath FROM decisions d "
               "LEFT JOIN units u ON u.id=d.unit_id LEFT JOIN findings f ON f.id=d.finding_id ")
        args: list = []
        if unit_id is not None:
            sql += "WHERE d.unit_id=? "
            args.append(unit_id)
        rows = self._q(sql + "ORDER BY d.id DESC LIMIT ?", (*args, max(1, min(int(limit), 1000))))
        return [{"id": r["id"], "batch": r["batch_id"], "who": r["who"], "at": r["at"], "decision": r["decision"],
                 "unit": f"{r['cls']}:{r['ukey']}" if r["cls"] else None, "path": r["fpath"], "from": r["prev_state"],
                 "to": r["new_state"], "detail": r["detail"], "undone": bool(r["undone"])} for r in rows]


def source_hash(items: Iterable[tuple[str, str]]) -> str:
    """Hash of a unit's source: (relative path, content hash) pairs."""
    h = hashlib.sha256()
    for rel, digest in sorted(items):
        h.update(f"{rel}\0{digest}\n".encode())
    return h.hexdigest()
