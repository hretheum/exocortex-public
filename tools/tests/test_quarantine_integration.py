"""Synthetic index end to end: intake, decisions, simcheck reading approvals and exclusions, the desk card."""
import http.client
import json
import re
import threading
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from tools.gate.desk import IndexProvider
from tools.publisher.quarantine import Store, paragraph_key
from tools.simcheck.core import Index
from tools.simcheck.intake import sync
from tools.simcheck.server import StoreHolder, make_handler

ROOT = "/corpus"
DIM = 256


def para(prefix: str, ids, suffix: str = "x") -> str:
    return " ".join(f"{prefix}{i}{suffix}" for i in ids)


class FakeEmbedder:
    """Deterministic embeddings: the word ``<prefix><n><letter>`` is concept n, whatever its prefix."""

    def __init__(self):
        self.client = SimpleNamespace(base_url="http://embedder.invalid/v1")
        self.model = "synthetic"

    def embed(self, texts, progress_every=0):
        out = []
        for t in texts:
            v = [0.0] * DIM
            for w in t.split():
                m = re.fullmatch(r"[a-z]+(\d+)[a-z]", w)
                if m:
                    v[int(m.group(1)) % DIM] += 1.0
            out.append(v)
        return out


PRIV_A = para("alpha", range(0, 30))      # note in a folder of client material
PRIV_B = para("delta", range(60, 90))     # a public-ish note
SEM = para("beta", range(0, 30), "y")     # same concepts as PRIV_A, other words: semantic only
LIT = PRIV_A.replace("alpha3x", "omega3z").replace("alpha9x", "omega9z")  # near copy: literal
CLEAN = para("gamma", range(120, 150), "z")
SEM_B = para("epsilon", range(60, 90), "w")  # same concepts as PRIV_B


@pytest.fixture()
def world(tmp_path):
    index = Index.build([(f"{ROOT}/client-a/plan.md", PRIV_A), (f"{ROOT}/open-notes/tips.md", PRIV_B)], FakeEmbedder())
    index.thresholds = {"literal": 0.4, "semantic": 0.9}
    index._embedder = FakeEmbedder()
    docs = tmp_path / "docs"
    (docs / "en/experiments/exp-a").mkdir(parents=True)
    (docs / "pl/experiments/exp-a").mkdir(parents=True)
    (docs / "en/experiments/exp-a/card.md").write_text(f"{SEM}\n\n{CLEAN}\n\n{SEM_B}\n")
    (docs / "en/experiments/exp-a/lit.md").write_text(f"{LIT}\n")
    (docs / "pl/experiments/exp-a/card.md").write_text(f"{CLEAN}\n")
    (docs / "en/experiments/exp-b").mkdir(parents=True)
    (docs / "en/experiments/exp-b/notes.md").write_text(f"{CLEAN}\n")
    hard = tmp_path / "hard.txt"
    hard.write_text("client-a/\n")
    store = Store(tmp_path / "q.sqlite3", never_exclude_file=hard)
    return SimpleNamespace(index=index, docs=docs, store=store, db=tmp_path / "q.sqlite3", tmp=tmp_path)


def findings(store):
    [unit] = [u for u in store.list_units() if u["key"] == "exp-a"]
    return unit, {(f["path"].rsplit("/", 1)[1], f["rule"]): f for f in store.findings(unit["id"])}


def test_intake_makes_one_unit_per_experiment_with_typed_findings(world):
    counts = sync(world.store, world.index, world.docs)
    assert counts["units"] == 2 and counts["new"] == 3  # two units scanned; the clean one gets no record
    assert [u["key"] for u in world.store.list_units()] == ["exp-a"]
    unit, fs = findings(world.store)
    assert unit["cls"] == "experiment" and len(unit["files"]) == 3
    assert set(fs) == {("card.md", "semantic"), ("lit.md", "literal")}
    assert sum(1 for f in world.store.findings(unit["id"]) if f["rule"] == "semantic") == 2
    assert fs[("lit.md", "literal")]["literal"] is True
    hashes = {f["para_hash"] for f in world.store.findings(unit["id"])}
    assert paragraph_key(SEM) in hashes and paragraph_key(SEM_B) in hashes and paragraph_key(CLEAN) not in hashes
    assert b"beta0y" not in world.db.read_bytes()  # no paragraph text in the database


def test_resync_is_idempotent_and_keeps_decisions(world):
    sync(world.store, world.index, world.docs)
    unit, fs = findings(world.store)
    sem = next(f for f in world.store.findings(unit["id"]) if f["para_hash"] == paragraph_key(SEM))
    world.store.decide(sem["id"], "keep", "me")
    counts = sync(world.store, world.index, world.docs, mask=None)
    assert counts["new"] == 0
    assert world.store.finding(sem["id"])["state"] == "kept"


def serve_simcheck(world):
    holder = StoreHolder(world.db, ROOT)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(world.index, holder))
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def check(text, exhaustive=False):
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
        conn.request("POST", "/check", json.dumps({"text": text, "exhaustive": exhaustive}), {"Content-Type": "application/json"})
        body = json.loads(conn.getresponse().read())
        conn.close()
        return body

    return server, check


def test_check_returns_paragraphs_and_scores(world):
    server, check = serve_simcheck(world)
    try:
        r = check(f"{SEM}\n\n{CLEAN}")
        assert r["similar"] is True and r["rule"] == "semantic"
        by_hash = {p["hash"]: p for p in r["paragraphs"]}
        assert by_hash[paragraph_key(SEM)]["flagged"] and by_hash[paragraph_key(SEM)]["score_semantic"] >= 0.9
        assert not by_hash[paragraph_key(CLEAN)]["flagged"]
        assert all(set(p) >= {"hash", "score_literal", "score_semantic", "approved", "flagged"} for p in r["paragraphs"])
        assert "beta0y" not in json.dumps(r)  # hashes and scores only
    finally:
        server.shutdown()


def test_simcheck_reads_approvals_from_the_store_and_literal_ignores_them(world):
    sync(world.store, world.index, world.docs)
    unit, _ = findings(world.store)
    server, check = serve_simcheck(world)
    try:
        assert check(SEM)["similar"] is True
        sem = next(f for f in world.store.findings(unit["id"]) if f["para_hash"] == paragraph_key(SEM))
        world.store.decide(sem["id"], "keep", "me")
        assert check(SEM)["similar"] is False  # approved in the database, read by the service
        assert check(SEM)["paragraphs"][0]["approved"] is True
        assert check(LIT)["similar"] is True  # the literal layer ignores approvals
        world.store.undo_last("me")
        assert check(SEM)["similar"] is True
    finally:
        server.shutdown()


def test_simcheck_skips_excluded_sources(world):
    server, check = serve_simcheck(world)
    try:
        assert check(SEM_B)["similar"] is True
        world.store.add_exclusion("open-notes/", "public tips", "me", folder=True)
        r = check(SEM_B)
        assert r["similar"] is False and r["paragraphs"][0]["score_semantic"] < 0.9
        assert check(SEM)["similar"] is True  # other sources still protect
        e = world.store.exclusions()[0]
        world.store.revoke_exclusion(e["id"], "me")
        assert check(SEM_B)["similar"] is True
    finally:
        server.shutdown()


def test_excluded_sources_do_not_count_for_the_literal_layer_either(world):
    lit_b = PRIV_B.replace("delta61x", "omega61z")
    assert world.index.check(lit_b).similar
    mask = world.index.exclusion_mask(["open-notes/tips.md"], ROOT)
    assert not world.index.check(lit_b, excluded=mask).similar
    assert world.index.exclusion_mask(["OPEN-NOTES/"], ROOT) is not None  # case-insensitive
    assert world.index.exclusion_mask(["open-notes/"], "/elsewhere") is None  # a source outside the root is never excluded


def test_a_client_folder_on_the_hard_list_cannot_be_excluded(world):
    from tools.publisher.quarantine import HardListViolation

    with pytest.raises(HardListViolation):
        world.store.add_exclusion("client-a/plan.md", "not allowed", "me")
    server, check = serve_simcheck(world)
    try:
        assert check(SEM)["similar"] is True
    finally:
        server.shutdown()


def test_missing_database_approves_and_excludes_nothing(world, tmp_path):
    holder = StoreHolder(tmp_path / "absent.sqlite3", ROOT)
    assert holder.get() == set() and holder.mask(world.index) is None


def test_source_change_reopens_only_the_changed_paragraph(world):
    sync(world.store, world.index, world.docs)
    unit, _ = findings(world.store)
    for f in world.store.findings(unit["id"]):
        if not f["literal"]:
            world.store.decide(f["id"], "keep", "me")
    card = world.docs / "en/experiments/exp-a/card.md"
    edited = para("beta", range(0, 30), "y").replace("beta0y", "beta1y")  # still close in meaning
    card.write_text(f"{edited}\n\n{CLEAN}\n\n{SEM_B}\n")
    counts = sync(world.store, world.index, world.docs)
    assert counts["new"] == 1 and counts["outdated"] == 1
    states = {f["para_hash"]: f["state"] for f in world.store.findings(unit["id"])}
    assert states[paragraph_key(SEM)] == "outdated"
    assert states[paragraph_key(SEM_B)] == "kept"
    assert states[paragraph_key(edited)] == "open"


def test_a_removed_literal_finding_releases_the_unit(world):
    sync(world.store, world.index, world.docs)
    unit, _ = findings(world.store)
    for f in world.store.findings(unit["id"]):
        world.store.decide(f["id"], "keep" if not f["literal"] else "to_edit", "me")
    assert world.store.get_unit(unit["id"])["state"] == "open"  # the literal one waits for its edit
    (world.docs / "en/experiments/exp-a/lit.md").write_text(f"{CLEAN}\n")
    sync(world.store, world.index, world.docs)
    assert world.store.get_unit(unit["id"])["state"] == "released"


def test_desk_card_shows_nearest_protected_paragraphs_from_the_index(world):
    sync(world.store, world.index, world.docs)
    unit, _ = findings(world.store)
    provider = IndexProvider(world.index, world.docs, ROOT, world.store)
    sem = next(f for f in world.store.findings(unit["id"]) if f["para_hash"] == paragraph_key(SEM))
    card = provider.card(sem)
    assert card["public"] == SEM
    top = card["neighbours"][0]
    assert top["text"] == PRIV_A and top["note_path"] == "client-a/plan.md" and top["folder_path"] == "client-a/"
    assert top["score"] > 0.99 and len(card["neighbours"]) <= 3
    lit = next(f for f in world.store.findings(unit["id"]) if f["literal"])
    lit_card = provider.card(lit)
    assert lit_card["neighbours"][0]["text"] == PRIV_A and "cannot be kept" in lit_card["hint"]
    # an excluded source no longer shows up as a neighbour
    world.store.add_exclusion("open-notes/", "public tips", "me", folder=True)
    other = next(f for f in world.store.findings(unit["id"]) if f["para_hash"] == paragraph_key(SEM_B))
    assert all(n["note_path"] != "open-notes/tips.md" for n in provider.card(other)["neighbours"])


def test_desk_card_for_a_paragraph_that_left_the_source(world):
    sync(world.store, world.index, world.docs)
    unit, _ = findings(world.store)
    sem = next(f for f in world.store.findings(unit["id"]) if f["para_hash"] == paragraph_key(SEM))
    (world.docs / "en/experiments/exp-a/card.md").write_text(f"{CLEAN}\n")
    card = IndexProvider(world.index, world.docs, ROOT, world.store).card(sem)
    assert card["public"] is None and card["neighbours"] == []


def test_desk_card_never_reads_outside_the_documents(world):
    provider = IndexProvider(world.index, world.docs, ROOT, world.store)
    (world.tmp / "secret.md").write_text(SEM)
    assert provider._read("../secret.md") is None
    assert provider._read("/etc/passwd") is None
