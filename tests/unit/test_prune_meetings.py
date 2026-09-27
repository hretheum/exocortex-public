# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Unit tests for orphan pruning in the work domain (meeting pages).

Meetings needed their own path, and a guard recipes never did.

A meeting page is named `{date}--{title-slug}--{shortid}`, so a title change
renames it and strands the old file — that is how the 2026-08-03 diacritics
fix left 21 stale meeting pages. But meeting pages also carry state the
database does not have: action items the user ticks off by hand, which the
compiler merges forward from the existing file on every rebuild. After a
rename the ticks stay in the orphan, making it the ONLY copy — 18 pages held
47 such ticks when this was written. Deleting one blind would destroy them,
so a page with ticks is reported for a human instead of pruned.
"""
from __future__ import annotations

from pathlib import Path

from exocortex.wiki.util.prune import has_user_state


def _page(tmp_path: Path, name: str, *, ticked: bool = False) -> Path:
    box = "- [x] zrobione ✅ 2026-02-25" if ticked else "- [ ] do zrobienia"
    p = tmp_path / name
    p.write_text(f"---\ntitle: X\ntype: meeting\n---\n\n## Zadania\n\n{box}\n",
                 encoding="utf-8")
    return p


# ── has_user_state ─────────────────────────────────────────────────────────

def test_ticked_item_counts_as_user_state(tmp_path):
    assert has_user_state(_page(tmp_path, "a.md", ticked=True)) is True


def test_unticked_item_is_not_user_state(tmp_path):
    assert has_user_state(_page(tmp_path, "b.md", ticked=False)) is False


def test_uppercase_x_counts(tmp_path):
    p = tmp_path / "c.md"
    p.write_text("- [X] zrobione\n", encoding="utf-8")
    assert has_user_state(p) is True


def test_indented_item_counts(tmp_path):
    p = tmp_path / "d.md"
    p.write_text("  - [x] zagniezdzone\n", encoding="utf-8")
    assert has_user_state(p) is True


def test_unreadable_file_is_treated_as_having_state(tmp_path):
    """Cannot read means do-not-touch, never 'safe to delete'."""
    assert has_user_state(tmp_path / "nie-ma-mnie.md") is True


# ── WorkDomain.prune_orphans ───────────────────────────────────────────────

def _setup(tmp_path, monkeypatch, files, db_rows, *, dry_run=False):
    """Lay out wiki/work/meetings/src and stub the DB behind it."""
    from exocortex.wiki.core import _state
    src = tmp_path / "work" / "meetings" / "src"
    src.mkdir(parents=True)
    for name, ticked in files.items():
        _page(src, name, ticked=ticked)
    import exocortex.wiki.domains.work as w
    monkeypatch.setattr("exocortex.wiki.core.io._get_wiki_root", lambda: tmp_path)
    # Stubbed at the compiler's own loader, not at the DB: pruning must judge a
    # page against the exact slug the compiler would write, never a second,
    # drifting reimplementation of it.
    monkeypatch.setattr(w, "_load_work_meetings", lambda *a, **k: db_rows)
    monkeypatch.setattr(_state, "DRY_RUN", dry_run)
    return src


def _row(tid, date, title):
    from exocortex.wiki.util.classification import _meeting_slug
    return {"thought_id": tid, "slug": _meeting_slug(date, title, tid)}


def _prune(tmp_path):
    from exocortex.wiki.domains.work import WorkDomain
    from exocortex.wiki.core.context import RunContext
    return WorkDomain().prune_orphans(RunContext(tenant_id="t"))


def test_renamed_meeting_leaves_old_page_as_orphan(tmp_path, monkeypatch):
    """Exactly the diacritics rename: same meeting, degraded old slug."""
    src = _setup(
        tmp_path, monkeypatch,
        files={"2026-06-19--om-wienie-toolboxa--f523b230.md": False,
               "2026-06-19--omowienie-toolboxa--f523b230.md": False},
        db_rows=[_row("f523b230-adce-4b80-aa8f-e6a92d406149",
                      "2026-06-19", "Omowienie toolboxa")])
    assert _prune(tmp_path) == 1
    assert {f.name for f in src.glob("*.md")} == {
        "2026-06-19--omowienie-toolboxa--f523b230.md"}


def test_orphan_with_ticked_items_is_never_deleted(tmp_path, monkeypatch):
    """The ticks exist nowhere else — report, do not destroy."""
    src = _setup(
        tmp_path, monkeypatch,
        files={"2026-06-19--om-wienie-toolboxa--f523b230.md": True,
               "2026-06-19--omowienie-toolboxa--f523b230.md": False},
        db_rows=[_row("f523b230-adce-4b80-aa8f-e6a92d406149",
                      "2026-06-19", "Omowienie toolboxa")])
    assert _prune(tmp_path) == 0
    assert len(list(src.glob("*.md"))) == 2


def test_file_without_parseable_id_is_left_alone(tmp_path, monkeypatch):
    """A page from an older naming scheme cannot be matched to a meeting,
    so it is not ours to delete."""
    src = _setup(
        tmp_path, monkeypatch,
        files={"2026-05-26--e2e-smoke-test--actions-queue.md": False},
        db_rows=[])
    assert _prune(tmp_path) == 0
    assert len(list(src.glob("*.md"))) == 1


def test_current_page_is_kept(tmp_path, monkeypatch):
    src = _setup(
        tmp_path, monkeypatch,
        files={"2026-06-19--omowienie-toolboxa--f523b230.md": False},
        db_rows=[_row("f523b230-adce-4b80-aa8f-e6a92d406149",
                      "2026-06-19", "Omowienie toolboxa")])
    assert _prune(tmp_path) == 0
    assert len(list(src.glob("*.md"))) == 1


def test_replacement_must_exist_before_deleting(tmp_path, monkeypatch):
    """Incremental compile may not have written the new name yet."""
    src = _setup(
        tmp_path, monkeypatch,
        files={"2026-06-19--stara-nazwa--f523b230.md": False},
        db_rows=[_row("f523b230-adce-4b80-aa8f-e6a92d406149",
                      "2026-06-19", "Zupelnie nowa nazwa")])
    assert _prune(tmp_path) == 0
    assert len(list(src.glob("*.md"))) == 1


def test_dry_run_deletes_nothing(tmp_path, monkeypatch):
    src = _setup(
        tmp_path, monkeypatch,
        files={"2026-06-19--om-wienie-toolboxa--f523b230.md": False,
               "2026-06-19--omowienie-toolboxa--f523b230.md": False},
        db_rows=[_row("f523b230-adce-4b80-aa8f-e6a92d406149",
                      "2026-06-19", "Omowienie toolboxa")], dry_run=True)
    assert _prune(tmp_path) == 1
    assert len(list(src.glob("*.md"))) == 2


def test_missing_directory_returns_zero_without_db(tmp_path, monkeypatch):
    from exocortex.wiki.domains.work import WorkDomain
    from exocortex.wiki.core.context import RunContext

    monkeypatch.setattr("exocortex.wiki.core.io._get_wiki_root", lambda: tmp_path)

    import exocortex.wiki.domains.work as w

    def _boom(*a, **k):
        raise AssertionError("nie wolno pytac bazy, gdy katalogu nie ma")
    monkeypatch.setattr(w, "_load_work_meetings", _boom)
    assert WorkDomain().prune_orphans(RunContext(tenant_id="t")) == 0


def test_incremental_compile_does_not_prune(tmp_path, monkeypatch):
    """The dangerous case: with `since` set the meetings list is only the
    recent slice, so pruning against it would delete every older page."""
    import exocortex.wiki.domains.work as w
    from datetime import datetime

    src = _setup(
        tmp_path, monkeypatch,
        files={"2026-06-19--stara--f523b230.md": False,
               "2026-06-19--nowa--f523b230.md": False},
        db_rows=[_row("f523b230-adce-4b80-aa8f-e6a92d406149", "2026-06-19", "Nowa")])
    pruned = []
    monkeypatch.setattr(w, "_prune_meeting_orphans",
                        lambda *a, **k: pruned.append(1) or 0)
    monkeypatch.setattr(w, "_write_meeting_pages", lambda *a, **k: None)
    monkeypatch.setattr(w, "_load_active_syntheses", lambda *a, **k: {})
    monkeypatch.setattr(w, "_load_edges_index", lambda *a, **k: {})
    monkeypatch.setattr(w, "_safe",
                        lambda fn, *a, **k: fn(*a, **k))
    try:
        w.compile_work_module("t", datetime(2026, 8, 1))
    except Exception:
        pass  # later stages need far more scaffolding; the prune call is the point
    assert pruned == [], "kompilacja przyrostowa nie moze sprzatac"


def test_page_whose_meeting_is_gone_is_never_deleted(tmp_path, monkeypatch):
    """Meeting pages outlive their thoughts: everything before ~May 2026 has
    no row left in the database, so 'no matching record' means the page is the
    last copy of a real meeting — not that it is stale."""
    src = _setup(
        tmp_path, monkeypatch,
        files={"2026-02-11--adamn--a734f910.md": False},
        db_rows=[])
    assert _prune(tmp_path) == 0
    assert len(list(src.glob("*.md"))) == 1


def test_rename_is_still_pruned_when_meeting_is_live(tmp_path, monkeypatch):
    """The narrower rule must not disable the case it was built for."""
    src = _setup(
        tmp_path, monkeypatch,
        files={"2026-06-19--om-wienie--f523b230.md": False,
               "2026-06-19--omowienie--f523b230.md": False},
        db_rows=[_row("f523b230-adce-4b80-aa8f-e6a92d406149",
                      "2026-06-19", "Omowienie")])
    assert _prune(tmp_path) == 1
    assert {f.name for f in src.glob("*.md")} == {"2026-06-19--omowienie--f523b230.md"}
