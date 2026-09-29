import json

import pytest

from tools.publisher import approvals as ap

HEAD = """---
id: x-applications
lang: {lang}
type: applications
slug: {slug}
label: hypothesis, no evidence
source_hash: abc
publish: {flag}
human_validated: {flag}
provenance: ai_authored
provenance_metadata:
  agent: some agent
  human_validated: false
---

# Business applications: {slug}

One sentence.

## Applications

| a | b |
|---|---|
| publish: false | in a table |
"""


def write(docs, slug, flag="false", langs=("pl", "en")):
    for lang in langs:
        p = ap.path_of(docs, lang, slug)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(HEAD.format(lang=lang, slug=slug, flag=flag), encoding="utf-8")


@pytest.fixture()
def world(tmp_path):
    docs, state = tmp_path / "docs", tmp_path / "state"
    state.mkdir()
    write(docs, "alpha")
    return docs, state


def test_flip_changes_only_the_two_header_lines():
    text = HEAD.format(lang="pl", slug="a", flag="false")
    new = ap.flip(text)
    assert ap.flags(new) == {"publish": True, "human_validated": True}
    assert new.count("human_validated: false") == 1 and "| publish: false | in a table |" in new  # nested field and body stay
    assert new.replace("publish: true", "publish: false").replace("human_validated: true", "human_validated: false") == text


def test_flip_refuses_a_header_it_does_not_understand():
    for bad in ("no header", "---\nid: a\n---\nbody\n", HEAD.format(lang="pl", slug="a", flag="false").replace("publish: false\n", "")):
        with pytest.raises(ap.ApprovalError):
            ap.flip(bad)


def test_drafts_are_listed_with_their_state(world):
    docs, state = world
    write(docs, "beta", "true")
    write(docs, "gamma", langs=("pl",))
    ap.path_of(docs, "en", "beta").write_text(HEAD.format(lang="en", slug="beta", flag="false"), encoding="utf-8")  # mixed
    by = {d["slug"]: d for d in ap.list_drafts(docs, state)}
    assert by["alpha"]["state"] == "draft" and by["alpha"]["approval"] == "none"
    assert by["beta"]["state"] == "broken" and by["gamma"]["state"] == "broken"
    assert by["alpha"]["title"]["pl"] == "Business applications: alpha" and set(by["alpha"]["sha"]) == {"pl", "en"}


def test_approval_needs_the_texts_the_owner_saw(world):
    docs, state = world
    draft = ap.list_drafts(docs, state)[0]
    with pytest.raises(ap.ApprovalError):
        ap.approve(docs, state, "alpha", {"pl": draft["sha"]["pl"], "en": "0" * 64}, "owner")
    with pytest.raises(ap.ApprovalError):
        ap.approve(docs, state, "../x", draft["sha"], "owner")
    with pytest.raises(ap.ApprovalError):
        ap.approve(docs, state, "nope", draft["sha"], "owner")
    ap.approve(docs, state, "alpha", draft["sha"], "owner")
    assert ap.list_drafts(docs, state)[0]["approval"] == "waiting"
    assert ap.withdraw(state, "alpha") is True and ap.withdraw(state, "alpha") is False
    assert ap.list_drafts(docs, state)[0]["approval"] == "none"


def test_nothing_changes_in_the_vault_until_apply(world):
    docs, state = world
    before = {lang: ap.path_of(docs, lang, "alpha").read_bytes() for lang in ap.LANGS}
    ap.approve(docs, state, "alpha", ap.list_drafts(docs, state)[0]["sha"], "owner")
    assert before == {lang: ap.path_of(docs, lang, "alpha").read_bytes() for lang in ap.LANGS}


def test_apply_sets_both_flags_and_keeps_a_log(world):
    docs, state = world
    ap.approve(docs, state, "alpha", ap.list_drafts(docs, state)[0]["sha"], "owner")
    [res] = ap.apply(docs, state)
    assert res["result"] == "applied" and res["who"] == "owner"
    for lang in ap.LANGS:
        assert ap.flags(ap.path_of(docs, lang, "alpha").read_text(encoding="utf-8")) == {"publish": True, "human_validated": True}
    assert ap.list_drafts(docs, state)[0]["state"] == "live"
    assert not (state / "approvals" / "alpha.json").exists()
    assert json.loads((state / "approvals" / "log.jsonl").read_text().splitlines()[-1])["result"] == "applied"
    assert ap.apply(docs, state) == []  # nothing left to do


def test_a_text_changed_after_the_approval_is_not_applied(world):
    docs, state = world
    ap.approve(docs, state, "alpha", ap.list_drafts(docs, state)[0]["sha"], "owner")
    p = ap.path_of(docs, "en", "alpha")
    p.write_text(p.read_text(encoding="utf-8") + "\nAn added sentence.\n", encoding="utf-8")
    assert ap.list_drafts(docs, state)[0]["approval"] == "changed"
    [res] = ap.apply(docs, state)
    assert res["result"] == "skipped: changed after the approval"
    for lang in ap.LANGS:
        assert ap.flags(ap.path_of(docs, lang, "alpha").read_text(encoding="utf-8")) == {"publish": False, "human_validated": False}


def test_a_half_written_pair_is_put_back(world, monkeypatch):
    docs, state = world
    ap.approve(docs, state, "alpha", ap.list_drafts(docs, state)[0]["sha"], "owner")
    real, calls = ap._atomic, []

    def flaky(path, text):
        calls.append(path)
        if len(calls) == 2:
            raise OSError("disk")
        real(path, text)
    monkeypatch.setattr(ap, "_atomic", flaky)
    [res] = ap.apply(docs, state)
    assert res["result"].startswith("failed")
    monkeypatch.setattr(ap, "_atomic", real)
    assert all(ap.flags(ap.path_of(docs, lang, "alpha").read_text(encoding="utf-8")) == {"publish": False, "human_validated": False}
               for lang in ap.LANGS)
    assert (state / "approvals" / "alpha.json").exists()  # kept for the next try


# -- drafts from the lab's drafts folder (F8.1) ---------------------------------------------------

@pytest.fixture()
def lab_world(tmp_path):
    docs, state, drafts = tmp_path / "docs", tmp_path / "state", tmp_path / "drafts"
    state.mkdir()
    write(docs, "alpha", flag="true")       # the section live in the vault
    write(drafts, "alpha")                  # a new draft written by the lab
    for lang in ap.LANGS:                   # its text differs from the live one
        p = ap.path_of(drafts, lang, "alpha")
        p.write_text(p.read_text(encoding="utf-8").replace("One sentence.", "A new sentence from the model."), encoding="utf-8")
    return docs, state, drafts


def _lab(docs, state, drafts):
    return [d for d in ap.list_drafts(docs, state, drafts) if d["origin"] == "lab"]


def test_a_lab_draft_is_offered_next_to_the_live_section(lab_world):
    docs, state, drafts = lab_world
    listed = ap.list_drafts(docs, state, drafts)
    assert [(d["origin"], d["state"]) for d in listed] == [("vault", "live"), ("lab", "draft")]
    [d] = _lab(docs, state, drafts)
    assert d["replaces"] == "live" and "A new sentence from the model." in d["text"]["pl"]
    assert ap.list_drafts(docs, state) == listed[:1]  # without the drafts folder nothing from the lab


def test_a_lab_draft_reaches_the_vault_only_after_approval_and_apply(lab_world):
    docs, state, drafts = lab_world
    before = {lang: ap.path_of(docs, lang, "alpha").read_text(encoding="utf-8") for lang in ap.LANGS}
    assert ap.apply(docs, state, drafts) == []  # nothing approved: nothing written
    [d] = _lab(docs, state, drafts)
    with pytest.raises(ap.ApprovalError):  # the vault's version is not the draft that was shown
        ap.approve(docs, state, "alpha", d["sha"], "owner")
    ap.approve(docs, state, "alpha", d["sha"], "owner", origin="lab", drafts=drafts)
    assert {lang: ap.path_of(docs, lang, "alpha").read_text(encoding="utf-8") for lang in ap.LANGS} == before
    [res] = ap.apply(docs, state, drafts)
    assert res["result"] == "applied" and res["origin"] == "lab"
    for lang in ap.LANGS:
        text = ap.path_of(docs, lang, "alpha").read_text(encoding="utf-8")
        assert "A new sentence from the model." in text
        assert ap.flags(text) == {"publish": True, "human_validated": True}
        assert text == ap.flip(ap.path_of(drafts, lang, "alpha").read_text(encoding="utf-8"))
        assert ap.flags(ap.path_of(drafts, lang, "alpha").read_text(encoding="utf-8"))["publish"] is False  # never touched
    assert _lab(docs, state, drafts) == []  # in the vault now, so no longer offered
    assert ap.apply(docs, state, drafts) == []


def test_a_lab_draft_changed_after_approval_is_not_written(lab_world):
    docs, state, drafts = lab_world
    [d] = _lab(docs, state, drafts)
    ap.approve(docs, state, "alpha", d["sha"], "owner", origin="lab", drafts=drafts)
    p = ap.path_of(drafts, "en", "alpha")
    p.write_text(p.read_text(encoding="utf-8") + "\nRedrafted.\n", encoding="utf-8")
    assert _lab(docs, state, drafts)[0]["approval"] == "changed"
    [res] = ap.apply(docs, state, drafts)
    assert res["result"] == "skipped: changed after the approval"
    assert "A new sentence" not in ap.path_of(docs, "pl", "alpha").read_text(encoding="utf-8")


def test_a_lab_draft_is_not_written_without_the_drafts_folder(lab_world):
    docs, state, drafts = lab_world
    [d] = _lab(docs, state, drafts)
    ap.approve(docs, state, "alpha", d["sha"], "owner", origin="lab", drafts=drafts)
    [res] = ap.apply(docs, state)  # apply-approvals without the lab's drafts mounted
    assert res["result"] == "skipped: not a draft any more"
    assert "A new sentence" not in ap.path_of(docs, "pl", "alpha").read_text(encoding="utf-8")


def test_only_a_draft_in_both_languages_is_offered_from_the_lab(lab_world):
    docs, state, drafts = lab_world
    ap.path_of(drafts, "en", "alpha").write_text(HEAD.format(lang="en", slug="alpha", flag="true"), encoding="utf-8")
    assert _lab(docs, state, drafts) == []
    ap.path_of(drafts, "en", "alpha").unlink()
    assert _lab(docs, state, drafts) == []
    with pytest.raises(ap.ApprovalError):
        ap.approve(docs, state, "alpha", {"pl": "x", "en": "y"}, "owner", origin="elsewhere", drafts=drafts)


def test_a_new_section_from_the_lab_creates_the_pair_and_a_failure_removes_it(tmp_path, monkeypatch):
    docs, state, drafts = tmp_path / "docs", tmp_path / "state", tmp_path / "drafts"
    state.mkdir()
    write(drafts, "beta")
    [d] = _lab(docs, state, drafts)
    assert d["replaces"] is None
    ap.approve(docs, state, "beta", d["sha"], "owner", origin="lab", drafts=drafts)
    real, calls = ap._atomic, []

    def flaky(path, text):
        calls.append(path)
        if len(calls) == 2:
            raise OSError("disk")
        real(path, text)
    monkeypatch.setattr(ap, "_atomic", flaky)
    [res] = ap.apply(docs, state, drafts)
    assert res["result"].startswith("failed")
    assert not any(ap.path_of(docs, lang, "beta").exists() for lang in ap.LANGS)
    monkeypatch.setattr(ap, "_atomic", real)
    [res] = ap.apply(docs, state, drafts)
    assert res["result"] == "applied" and all(ap.path_of(docs, lang, "beta").exists() for lang in ap.LANGS)
