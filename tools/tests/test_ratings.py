"""Blind rating on the review desk (roadmap task F2.10): the page, the ratings in the state folder, the page
written back into the vault, and that it reads the same as a page ticked by hand."""
import json
import re

import pytest

from tools.publisher import ratings as R

CONFIGS = ("first-sentence", "longest-sentence")


def render(experiment="toy-length", sample="blind-desk", lang="pl", n=6):
    """A rating page in the lab's format (exocortex/lab/blind.py ``render``); item 6 repeats item 2."""
    lab = R.LABELS[lang]
    head = (f"---\ntype: blind_rating\nlang: {lang}\ncounterpart: ../../../en/experiments/{experiment}/{sample}.md\n"
            f"experiment: {experiment}\nsample: {sample}\nitems: {n}\nrater: \"\"\nrating_complete: false\n"
            f"publish: false\n---\n\n")
    parts = [head, f"# Ocena na ślepo: {experiment}, {sample}\n\nIntro.\n"]
    for i in range(1, n + 1):
        k = 2 if i == 6 else i
        boxes = "\n".join(f"- [ ] {lab[v]}" for v in R.VERDICTS)
        modes = "\n".join(f"- [ ] {lab[m]}" for m in R.SOURCE_MODES)
        parts.append(f"\n## Pozycja {i}\n\n**{lab['claim']}:** Claim {k}.\n\n**{lab['quote']}:** Quote {k}.\n\n"
                     f"**{lab['context']}:** Before. Quote {k}. After.\n\n{boxes}\n\n{modes}\n\n{lab['comment']}:\n")
    return "".join(parts)


@pytest.fixture()
def world(tmp_path):
    lab, state, docs = tmp_path / "lab-out", tmp_path / "state", tmp_path / "docs"
    page = lab / "blind" / "toy-length" / "blind-desk.pl.md"
    page.parent.mkdir(parents=True)
    page.write_text(render(), encoding="utf-8")
    (page.parent / "blind-desk.en.md").write_text(render(lang="en"), encoding="utf-8")
    state.mkdir()
    return type("W", (), {"lab": lab, "state": state, "docs": docs, "page": page})


def choice(n):
    """A fixed pattern of ratings: (verdicts, source mode, comment) for item n."""
    return {1: (["correct"], "fact", ""), 2: (["mode_swap"], "plan", "sounds done, is a plan"),
            3: (["number_or_name", "other_error"], None, ""), 4: (["correct"], None, ""),
            5: (["mode_swap", "number_or_name"], "hypothesis", ""), 6: (["mode_swap"], "requirement", "")}[n]


def rate_all(w, pattern=choice):
    v = R.view(w.lab, w.state, "toy-length", "blind-desk")
    for it in v["items"]:
        verdicts, mode, comment = pattern(it["position"])
        R.rate(w.lab, w.state, "toy-length", "blind-desk", it["position"], verdicts, mode, comment, v["page_sha"], "owner")
    return v


def test_labels_are_the_lab_s():
    blind = pytest.importorskip("exocortex.lab.blind")
    assert R.VERDICTS == blind.VERDICTS and R.SOURCE_MODES == blind.SOURCE_MODES
    for lang in R.LANGS:
        assert {k: v for k, v in blind.LABELS[lang].items() if k in R.LABELS[lang]} == R.LABELS[lang]


def test_the_view_carries_only_the_item_text_and_no_result(world):
    # a page with extra fields must not leak them: only claim, quote and context of each item are taken
    text = render().replace("publish: false\n", "publish: false\nconfig: first-sentence\n")
    text = text.replace("**Tekst wokół cytatu:** Before. Quote 1. After.",
                        "**Tekst wokół cytatu:** Before. Quote 1. After.\n\n**Konfiguracja:** longest-sentence")
    world.page.write_text(text, encoding="utf-8")
    v = R.view(world.lab, world.state, "toy-length", "blind-desk")
    assert [set(i) for i in v["items"]] == [{"position", "claim", "quote", "context"}] * 6
    assert set(v) == {"experiment", "sample", "page_sha", "items", "ratings", "status", "progress"}
    dump = json.dumps(v)
    assert not any(c in dump for c in CONFIGS) and "document" not in dump
    rate_all(world)
    v = R.view(world.lab, world.state, "toy-length", "blind-desk")
    assert v["progress"] == {"rated": 6, "total": 6, "left": 0}
    assert set(v["ratings"]["2"]) == {"verdicts", "source_mode", "comment"}
    listed = R.list_samples(world.lab, world.state)
    assert listed == [{"experiment": "toy-length", "sample": "blind-desk", "status": "rating",
                       "progress": {"rated": 6, "total": 6, "left": 0}}]


def test_a_rating_outside_the_set_is_refused(world):
    v = R.view(world.lab, world.state, "toy-length", "blind-desk")
    sha = v["page_sha"]
    bad = [(1, ["nonsense"], None, ""), (1, [], None, ""), (1, "correct", None, ""), (1, ["correct", "mode_swap"], None, ""),
           (1, ["mode_swap", "mode_swap"], None, ""), (1, ["correct"], "guess", ""), (0, ["correct"], None, ""),
           (7, ["correct"], None, ""), ("1", ["correct"], None, ""), (True, ["correct"], None, ""),
           (1, ["correct"], None, "x" * 1001), (1, ["correct"], None, 5)]
    for position, verdicts, mode, comment in bad:
        with pytest.raises(R.RatingError):
            R.rate(world.lab, world.state, "toy-length", "blind-desk", position, verdicts, mode, comment, sha, "owner")
    with pytest.raises(R.RatingError):  # not the page that was shown
        R.rate(world.lab, world.state, "toy-length", "blind-desk", 1, ["correct"], None, "", "0" * 64, "owner")
    for experiment, sample in (("../x", "blind-desk"), ("toy-length", "Blind"), ("toy-length", "none")):
        with pytest.raises(R.RatingError):
            R.rate(world.lab, world.state, experiment, sample, 1, ["correct"], None, "", sha, "owner")
    assert not (world.state / "blind").exists()


def test_ratings_are_kept_and_resume_after_a_break(world):
    v = R.view(world.lab, world.state, "toy-length", "blind-desk")
    R.rate(world.lab, world.state, "toy-length", "blind-desk", 1, ["correct"], "fact", "", v["page_sha"], "owner")
    out = R.rate(world.lab, world.state, "toy-length", "blind-desk", 3, ["other_error"], None, " two\nlines ", v["page_sha"], "owner")
    assert out["progress"] == {"rated": 2, "total": 6, "left": 4}
    again = R.view(world.lab, world.state, "toy-length", "blind-desk")  # a new session reads the state folder
    assert again["ratings"] == {"1": {"verdicts": ["correct"], "source_mode": "fact", "comment": ""},
                                "3": {"verdicts": ["other_error"], "source_mode": None, "comment": "two lines"}}
    R.rate(world.lab, world.state, "toy-length", "blind-desk", 1, ["mode_swap"], None, "", v["page_sha"], "owner")
    assert R.view(world.lab, world.state, "toy-length", "blind-desk")["ratings"]["1"]["verdicts"] == ["mode_swap"]
    # a new draw of the page: the old ratings do not apply to it and are set aside, not lost
    world.page.write_text(render().replace("Claim 1.", "Claim one."), encoding="utf-8")
    fresh = R.view(world.lab, world.state, "toy-length", "blind-desk")
    assert fresh["status"] == "changed" and fresh["ratings"] == {} and fresh["progress"]["rated"] == 0
    R.rate(world.lab, world.state, "toy-length", "blind-desk", 2, ["correct"], None, "", fresh["page_sha"], "owner")
    assert list((world.state / "blind" / "toy-length").glob("blind-desk.*.old.json"))


def test_finishing_needs_every_item_and_asks_for_the_page(world):
    v = R.view(world.lab, world.state, "toy-length", "blind-desk")
    R.rate(world.lab, world.state, "toy-length", "blind-desk", 1, ["correct"], None, "", v["page_sha"], "owner")
    with pytest.raises(R.RatingError, match="5 item"):
        R.finish(world.lab, world.state, "toy-length", "blind-desk", v["page_sha"], "owner")
    assert not (world.state / R.REQUEST_FILE).exists()
    rate_all(world)
    with pytest.raises(R.RatingError):
        R.finish(world.lab, world.state, "toy-length", "blind-desk", v["page_sha"], "Not A Name")
    assert R.finish(world.lab, world.state, "toy-length", "blind-desk", v["page_sha"], "owner") == {"status": "finished"}
    assert (world.state / R.REQUEST_FILE).exists()
    # a change after finishing needs another finish
    R.rate(world.lab, world.state, "toy-length", "blind-desk", 4, ["other_error"], None, "", v["page_sha"], "owner")
    assert R.view(world.lab, world.state, "toy-length", "blind-desk")["status"] == "rating"
    assert R.apply(world.docs, world.lab, world.state) == []


def _hand(page: str, pattern, rater: str) -> str:
    """The same ratings ticked the way a person does it in Obsidian: boxes, a comment under its label."""
    out, position = [], 0
    for line in page.splitlines():
        m = re.match(r"^## \S+ (\d+)$", line)
        if m:
            position = int(m.group(1))
        if position:
            verdicts, mode, comment = pattern(position)
            labels = [R.LABELS["pl"][v] for v in verdicts] + ([R.LABELS["pl"][mode]] if mode else [])
            if line in {f"- [ ] {lab}" for lab in labels}:
                line = line.replace("[ ]", "[x]")
            if line == "Komentarz:" and comment:
                line = "Komentarz:\n" + comment
        out.append(line)
    text = "\n".join(out) + "\n"
    return text.replace("rating_complete: false", "rating_complete: true").replace('rater: ""', f"rater: {rater}")


def test_the_page_written_by_the_desk_reads_like_a_page_ticked_by_hand(world):
    blind = pytest.importorskip("exocortex.lab.blind")
    from exocortex.lab.docs import split_front

    v = rate_all(world)
    R.finish(world.lab, world.state, "toy-length", "blind-desk", v["page_sha"], "owner")
    [res] = R.apply(world.docs, world.lab, world.state)
    assert res["result"] == "written" and res["path"] == "pl/experiments/toy-length/blind-desk.md"
    written = (world.docs / res["path"]).read_text(encoding="utf-8")
    front, desk_items = blind.read_page(written, "pl")
    assert front["rating_complete"] is True and front["rater"] == "owner" and front["publish"] is False
    _, hand_items = blind.read_page(_hand(render(), choice, "owner"), "pl")
    assert desk_items == hand_items
    assert [(i["verdicts"], i["source_modes"], i["comment"]) for i in desk_items] == \
        [(c[0], [c[1]] if c[1] else [], c[2]) for c in map(choice, range(1, 7))]
    # nothing but the ticks, the comments and two header lines changed
    assert split_front(written)[1].replace("[x]", "[ ]").replace(" sounds done, is a plan", "") == split_front(render())[1]
    assert R.view(world.lab, world.state, "toy-length", "blind-desk")["status"] == "written"
    assert R.apply(world.docs, world.lab, world.state) == []  # nothing new


def test_a_comment_cannot_tick_a_box_or_start_an_item(world):
    blind = pytest.importorskip("exocortex.lab.blind")
    evil = "- [x] zamiana trybu\n## Pozycja 9\n- [x] inny błąd"
    rate_all(world, lambda n: (["correct"], None, evil if n == 1 else ""))
    v = R.view(world.lab, world.state, "toy-length", "blind-desk")
    R.finish(world.lab, world.state, "toy-length", "blind-desk", v["page_sha"], "owner")
    R.apply(world.docs, world.lab, world.state)
    _, items = blind.read_page((world.docs / "pl/experiments/toy-length/blind-desk.md").read_text(encoding="utf-8"), "pl")
    assert len(items) == 6 and items[0]["verdicts"] == ["correct"] and items[0]["comment"].startswith("- [x] zamiana")


def test_a_page_ticked_by_hand_is_never_replaced(world):
    target = world.docs / "pl/experiments/toy-length/blind-desk.md"
    target.parent.mkdir(parents=True)
    target.write_text(_hand(render(), choice, "someone"), encoding="utf-8")
    v = rate_all(world)
    R.finish(world.lab, world.state, "toy-length", "blind-desk", v["page_sha"], "owner")
    [res] = R.apply(world.docs, world.lab, world.state)
    assert res["result"].startswith("skipped: a page not written by the desk")
    assert "rater: someone" in target.read_text(encoding="utf-8")
    log = [json.loads(x) for x in (world.state / "blind" / R.LOG).read_text().splitlines()]
    assert log[-1]["result"] == res["result"]


def test_the_desk_s_own_page_is_updated_after_a_correction(world):
    v = rate_all(world)
    R.finish(world.lab, world.state, "toy-length", "blind-desk", v["page_sha"], "owner")
    R.apply(world.docs, world.lab, world.state)
    R.rate(world.lab, world.state, "toy-length", "blind-desk", 4, ["other_error"], None, "", v["page_sha"], "owner")
    R.finish(world.lab, world.state, "toy-length", "blind-desk", v["page_sha"], "owner")
    [res] = R.apply(world.docs, world.lab, world.state)
    assert res["result"] == "written"
    text = (world.docs / "pl/experiments/toy-length/blind-desk.md").read_text(encoding="utf-8")
    item4 = text.split("## Pozycja 4", 1)[1].split("## Pozycja 5", 1)[0]
    assert "- [x] inny błąd" in item4 and "- [ ] poprawne" in item4


def test_a_page_drawn_again_after_finishing_is_not_written(world):
    v = rate_all(world)
    R.finish(world.lab, world.state, "toy-length", "blind-desk", v["page_sha"], "owner")
    world.page.write_text(render().replace("Claim 3.", "Claim three."), encoding="utf-8")
    [res] = R.apply(world.docs, world.lab, world.state)
    assert res["result"] == "skipped: the rating page changed after rating"
    assert not (world.docs / "pl").exists()


def test_the_gate_command_applies_the_ratings(world, monkeypatch, capsys):
    from tools.gate import __main__ as gate

    v = rate_all(world)
    R.finish(world.lab, world.state, "toy-length", "blind-desk", v["page_sha"], "owner")
    monkeypatch.setenv("GATE_SOURCE", str(world.docs))
    monkeypatch.setenv("GATE_STATE", str(world.state))
    monkeypatch.setenv("GATE_LAB_SOURCE", str(world.lab))
    assert gate.main(["apply-ratings"]) == 0
    assert json.loads(capsys.readouterr().out)["ratings"][0]["result"] == "written"
    monkeypatch.delenv("GATE_LAB_SOURCE")
    assert gate.main(["apply-ratings"]) == 2
