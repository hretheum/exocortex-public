import datetime as dt
import sqlite3

import pytest

from tools.publisher import quarantine as q
from tools.publisher.quarantine import Store

H1, H2, H3 = (c * 64 for c in "abc")


class Clock:
    def __init__(self):
        self.t = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)

    def __call__(self):
        return self.t

    def advance(self, **kw):
        self.t += dt.timedelta(**kw)


@pytest.fixture()
def clock():
    return Clock()


@pytest.fixture()
def hard(tmp_path):
    f = tmp_path / "hard.txt"
    f.write_text("# synthetic\nprotected-area/\nprivate/notes.md\n")
    return f


@pytest.fixture()
def store(tmp_path, clock, hard):
    return Store(tmp_path / "q.sqlite3", clock=clock, never_exclude_file=hard)


def sem(path, h, score=0.95, rule="semantic"):
    return {"rule": rule, "path": path, "para_hash": h, "score": score}


def sync(store, findings, source="s1", key="exp-a", cls="experiment", files=None):
    return store.sync_unit(cls, key, files or sorted({f["path"] for f in findings}), source, findings)


def test_new_findings_are_open_and_unit_is_open(store):
    sync(store, [sem("en/experiments/exp-a/a.md", H1), sem("en/experiments/exp-a/b.md", H2)])
    [unit] = store.list_units()
    assert unit["state"] == "open" and unit["counts"]["open"] == 2 and unit["findings"] == 2
    assert {f["state"] for f in store.findings(unit["id"])} == {"open"}


def test_keep_and_to_edit_lifecycle_and_release(store):
    sync(store, [sem("en/a.md", H1), sem("en/b.md", H2)], key="doc", cls="unknown")
    uid = store.list_units()[0]["id"]
    f1, f2 = store.findings(uid)
    store.decide(f1["id"], "keep", "me")
    assert H1 in store.approved_hashes()
    assert store.get_unit(uid)["state"] == "open"
    store.decide(f2["id"], "to_edit", "me", note="rewrite the second sentence")
    assert store.get_unit(uid)["state"] == "open"  # to_edit still holds the unit
    assert store.finding(f2["id"])["note"] == "rewrite the second sentence"
    assert H2 not in store.approved_hashes()
    # the edit happened: the paragraph is gone, the unit is released
    sync(store, [sem("en/a.md", H1)], source="s2", key="doc", cls="unknown")
    unit = store.get_unit(uid)
    assert unit["state"] == "released"
    assert unit["counts"]["outdated"] == 1 and unit["counts"]["kept"] == 1


def test_source_change_returns_only_changed_paragraphs(store):
    sync(store, [sem("en/a.md", H1), sem("en/a.md", H2)], key="doc", cls="unknown")
    uid = store.list_units()[0]["id"]
    for f in store.findings(uid):
        store.decide(f["id"], "keep", "me")
    assert store.get_unit(uid)["state"] == "released"
    # H2 was edited into H3 and is still close to the corpus; H1 did not change
    c = sync(store, [sem("en/a.md", H1), sem("en/a.md", H3)], source="s2", key="doc", cls="unknown")
    assert c == {"new": 1, "kept": 1, "outdated": 1}
    by_hash = {f["para_hash"]: f["state"] for f in store.findings(uid)}
    assert by_hash == {H1: "kept", H2: "outdated", H3: "open"}
    assert store.get_unit(uid)["state"] == "open"
    assert H2 not in store.approved_hashes() and H1 in store.approved_hashes()
    assert store.get_unit(uid)["source_hash"] == "s2"


def test_outdated_finding_cannot_be_decided(store):
    sync(store, [sem("en/a.md", H1)], key="doc", cls="unknown")
    fid = store.findings(store.list_units()[0]["id"])[0]["id"]
    sync(store, [], source="s2", key="doc", cls="unknown")
    with pytest.raises(q.InvalidState):
        store.decide(fid, "keep", "me")


@pytest.mark.parametrize("rule", ["literal", "leakgate:person-name", "something-new"])
def test_literal_findings_cannot_be_kept(store, rule):
    sync(store, [sem("en/a.md", H1, rule=rule)], key="doc", cls="unknown")
    uid = store.list_units()[0]["id"]
    f = store.findings(uid)[0]
    assert f["literal"]
    with pytest.raises(q.LiteralNotApprovable):
        store.decide(f["id"], "keep", "me")
    assert store.approved_hashes() == set()
    store.decide(f["id"], "to_edit", "me", note="remove the name")
    assert store.finding(f["id"])["state"] == "to_edit"


def test_file_level_finding_is_literal(store):
    sync(store, [{"rule": "semantic", "path": "en/a.md", "para_hash": "", "score": 1.0}], key="doc", cls="unknown")
    f = store.findings(store.list_units()[0]["id"])[0]
    assert f["literal"]


def test_approved_hash_makes_new_semantic_finding_kept(store):
    sync(store, [sem("en/a.md", H1)], key="d1", cls="unknown")
    store.decide(store.findings(store.list_units()[0]["id"])[0]["id"], "keep", "me")
    sync(store, [sem("en/z.md", H1)], key="d2", cls="unknown")
    assert store.findings(store.list_units()[0]["id"])[0]["state"] == "kept"


def test_undo_restores_state_and_approval(store):
    sync(store, [sem("en/a.md", H1)], key="doc", cls="unknown")
    uid = store.list_units()[0]["id"]
    fid = store.findings(uid)[0]["id"]
    store.decide(fid, "keep", "me")
    assert store.undo_last("me")["findings"] == [fid]
    assert store.finding(fid)["state"] == "open"
    assert store.approved_hashes() == set()
    assert store.get_unit(uid)["state"] == "open"
    assert store.undo_last("me") is None  # nothing left to undo
    hist = store.history()
    assert [h["decision"] for h in hist[:3]] == ["undo", "keep", "new"] and hist[1]["undone"]


def test_reopen_puts_a_decided_finding_back_and_takes_its_approval_with_it(store):
    sync(store, [sem("en/a.md", H1), sem("en/b.md", H2)], key="doc", cls="unknown")
    uid = store.list_units()[0]["id"]
    f1, f2 = store.findings(uid)
    store.decide(f1["id"], "keep", "me")
    store.decide(f2["id"], "to_edit", "me", "reword")
    assert store.get_unit(uid)["state"] == "open"
    assert store.reopen(f1["id"], "me")["state"] == "open"
    assert store.approved_hashes() == set()
    assert store.reopen(f2["id"], "me")["state"] == "open"
    assert store.finding(f2["id"])["note"] is None
    assert [h["decision"] for h in store.history()[:2]] == ["reopen", "reopen"]
    with pytest.raises(q.InvalidState):
        store.reopen(f1["id"], "me")  # already open
    with pytest.raises(q.NotFound):
        store.reopen(999, "me")


def test_reopen_after_release_makes_the_unit_open_again(store):
    sync(store, [sem("en/a.md", H1)], key="doc", cls="unknown")
    uid = store.list_units()[0]["id"]
    fid = store.findings(uid)[0]["id"]
    store.decide(fid, "keep", "me")
    assert store.get_unit(uid)["state"] == "released"
    store.reopen(fid, "me")
    assert store.get_unit(uid)["state"] == "open"


def test_undo_never_removes_an_imported_approval(store, tmp_path):
    f = tmp_path / "old.txt"
    f.write_text(f"{H1}  # a note 2026-01-01\n")
    store.import_approved_file(f)
    sync(store, [sem("en/a.md", H1, rule="semantic")], key="doc", cls="unknown")
    uid = store.list_units()[0]["id"]
    assert store.findings(uid)[0]["state"] == "kept"  # already approved
    fid = store.findings(uid)[0]["id"]
    store.decide(fid, "to_edit", "me")
    store.undo_last("me")
    assert H1 in store.approved_hashes()


def test_import_reads_old_file_only(store, tmp_path):
    f = tmp_path / "approved-paragraphs.txt"
    body = f"# header\n{H1}  # note 2026\n\nnot-a-hash\n{H2}\n{H1}\n"
    f.write_text(body)
    assert store.import_approved_file(f) == {"seen": 2, "added": 2}
    assert store.import_approved_file(f) == {"seen": 2, "added": 0}
    assert store.approved_hashes() == {H1, H2}
    assert f.read_text() == body
    assert store.import_approved_file(tmp_path / "missing.txt") == {"seen": 0, "added": 0}


def test_database_holds_no_paragraph_text(store, tmp_path):
    secret = "Confidential sentence that must never be stored anywhere."
    sync(store, [sem("en/a.md", q.paragraph_key(secret))], key="doc", cls="unknown")
    store.decide(store.findings(store.list_units()[0]["id"])[0]["id"], "keep", "me")
    store.close()
    assert secret.encode() not in (tmp_path / "q.sqlite3").read_bytes()


# -- bulk ---------------------------------------------------------------------------------------

def test_bulk_keep_needs_matching_digest_and_is_one_undo(store):
    sync(store, [sem("en/experiments/exp-a/a.md", H1, 0.91), sem("en/experiments/exp-a/sub/b.md", H2, 0.97)])
    uid = store.list_units()[0]["id"]
    pv = store.bulk_preview(uid)
    assert (pv["files"], pv["paragraphs"], pv["max_score"], pv["disabled"]) == (2, 2, 0.97, False)
    with pytest.raises(q.StaleConfirmation):
        store.bulk_keep(uid, None, "0" * 24, "me")
    store.bulk_keep(uid, None, pv["digest"], "me")
    assert store.get_unit(uid)["state"] == "released" and store.approved_hashes() == {H1, H2}
    store.undo_last("me")
    assert store.get_unit(uid)["counts"]["open"] == 2 and store.approved_hashes() == set()


def test_bulk_folder_scope(store):
    sync(store, [sem("en/experiments/exp-a/a.md", H1), sem("en/experiments/exp-a/sub/b.md", H2)])
    uid = store.list_units()[0]["id"]
    pv = store.bulk_preview(uid, "en/experiments/exp-a/sub/")
    assert pv["paragraphs"] == 1
    store.bulk_keep(uid, "en/experiments/exp-a/sub/", pv["digest"], "me")
    assert store.approved_hashes() == {H2}


def test_bulk_is_disabled_with_a_literal_finding(store):
    sync(store, [sem("en/experiments/exp-a/a.md", H1), sem("en/experiments/exp-a/b.md", H2, rule="literal")])
    uid = store.list_units()[0]["id"]
    pv = store.bulk_preview(uid)
    assert pv["disabled"] and "literal" in pv["reason"]
    with pytest.raises(q.LiteralNotApprovable):
        store.bulk_keep(uid, None, pv["digest"], "me")
    assert store.approved_hashes() == set()


def test_bulk_folder_without_literal_finding_stays_allowed(store):
    sync(store, [sem("en/experiments/exp-a/a/x.md", H1), sem("en/experiments/exp-a/sub/y.md", H2, rule="literal")])
    uid = store.list_units()[0]["id"]
    assert not store.bulk_preview(uid, "en/experiments/exp-a/a/")["disabled"]
    assert store.bulk_preview(uid, "en/experiments/exp-a/sub/")["disabled"]


# -- standing rules -----------------------------------------------------------------------------

def test_standing_rule_keeps_semantic_only_logs_use_and_expires(store, clock):
    sync(store, [sem("en/experiments/exp-a/a.md", H1), sem("en/experiments/exp-a/b.md", H2, rule="literal"),
                 sem("en/other/c.md", H3)])
    uid = store.list_units()[0]["id"]
    rule = store.add_standing_rule("en/experiments/exp-a", "reviewed as a whole", "me")
    assert rule["applied"] == 1 and rule["folder"] == "en/experiments/exp-a/"
    assert (dt.datetime.strptime(rule["expires_at"], "%Y-%m-%dT%H:%M:%SZ") - dt.datetime(2026, 1, 1)).days == 90
    states = {f["para_hash"]: f["state"] for f in store.findings(uid)}
    assert states == {H1: "kept", H2: "open", H3: "open"}  # the literal one and the other folder stay
    uses = [h for h in store.history() if h["decision"] == "auto_keep"]
    assert len(uses) == 1 and uses[0]["detail"] == f"rule:{rule['id']}"
    clock.advance(days=91)
    store.expire()
    assert {f["para_hash"]: f["state"] for f in store.findings(uid)}[H1] == "open"
    assert H1 not in store.approved_hashes()
    assert not store.standing_rules()[0]["active"]


def test_standing_rule_applies_to_findings_that_arrive_later_and_can_be_revoked(store):
    rule = store.add_standing_rule("en/experiments/exp-a/", "trusted", "me", days=30)
    sync(store, [sem("en/experiments/exp-a/a.md", H1), sem("en/experiments/exp-a/b.md", H2, rule="leakgate:name")])
    uid = store.list_units()[0]["id"]
    assert {f["para_hash"]: f["state"] for f in store.findings(uid)} == {H1: "kept", H2: "open"}
    store.revoke_standing_rule(rule["id"], "me")
    assert store.findings(uid)[0]["state"] == "open" and store.approved_hashes() == set()


@pytest.mark.parametrize("bad", [dict(folder="", reason="x reason"), dict(folder="en/a/", reason=""),
                                 dict(folder="../x/", reason="reason"), dict(folder="/abs/", reason="reason"),
                                 dict(folder="en/a/", reason="reason", days=0), dict(folder="en/a/", reason="reason", days=9999)])
def test_standing_rule_needs_folder_reason_and_bounded_days(store, bad):
    with pytest.raises(q.InvalidInput):
        store.add_standing_rule(bad["folder"], bad["reason"], "me", bad.get("days"))


# -- exclusions ---------------------------------------------------------------------------------

def test_exclusion_lifecycle(store, clock):
    e = store.add_exclusion("notes/public-note.md", "published elsewhere", "me", expires_days=10)
    assert store.active_exclusion_paths() == ["notes/public-note.md"]
    clock.advance(days=11)
    assert store.active_exclusion_paths() == []  # expired
    e2 = store.add_exclusion("open-notes", "a folder of public texts", "me", folder=True)
    assert e2["path"] == "open-notes/" and store.active_exclusion_paths() == ["open-notes/"]
    store.revoke_exclusion(e2["id"], "me")
    assert store.active_exclusion_paths() == []
    assert [x["active"] for x in store.exclusions()] == [False, False]
    assert {"exclude", "unexclude"} <= {h["decision"] for h in store.history()}
    assert e["id"] != e2["id"]


@pytest.mark.parametrize("path,folder", [("protected-area/x.md", False), ("protected-area", True), ("private/notes.md", False),
                                         ("private/", True), ("PROTECTED-AREA/y.md", False)])
def test_hard_list_paths_cannot_be_switched_off(store, path, folder):
    with pytest.raises(q.HardListViolation):
        store.add_exclusion(path, "reason here", "me", folder=folder)
    assert store.active_exclusion_paths() == []


def test_hard_list_missing_is_fail_closed(tmp_path, clock):
    for hard in (None, tmp_path / "missing.txt"):
        s = Store(tmp_path / f"{hard is None}.sqlite3", clock=clock, never_exclude_file=hard)
        with pytest.raises(q.HardListUnavailable):
            s.add_exclusion("notes/a.md", "reason here", "me")
        assert s.active_exclusion_paths() == [] and s.hard_list_status()["available"] is False


def test_exclusion_needs_reason_and_clean_path(store):
    with pytest.raises(q.InvalidInput):
        store.add_exclusion("notes/a.md", "  ", "me")
    for bad in ("", "/etc/x", "a/../b", "a\\b", "a//b"):
        with pytest.raises(q.InvalidInput):
            store.add_exclusion(bad, "reason here", "me")


def test_read_only_connection_reads_and_cannot_write(tmp_path, store):
    sync(store, [sem("en/a.md", H1)], key="doc", cls="unknown")
    store.decide(store.findings(store.list_units()[0]["id"])[0]["id"], "keep", "me")
    ro = Store(tmp_path / "q.sqlite3", read_only=True)
    assert ro.approved_hashes() == {H1}
    with pytest.raises(q.QuarantineError):
        ro.add_standing_rule("en/a/", "reason here", "me")
    with pytest.raises(sqlite3.OperationalError):
        ro.db.execute("DELETE FROM approvals")
    before = ro.revision()
    store.import_approved_file(tmp_path / "none.txt")
    assert ro.revision() != before  # another connection committed
