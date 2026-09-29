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
