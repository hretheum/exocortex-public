from tools.simcheck.core import Index, paragraphs

PRIVATE = (
    "Spotkanie zespołu dotyczyło migracji systemu rozliczeń do nowej architektury, harmonogramu wdrożenia "
    "w trzech falach oraz ryzyka opóźnień wynikających z zależności od dostawcy zewnętrznego i braku testów."
)
PUBLIC = (
    "The lab publishes every hypothesis card before measuring anything, so that the commit date shows the "
    "method was not fitted to the result, and the control set is opened only once at the very end."
)


def test_paragraphs_drop_front_matter():
    text = "---\ntitle: x\nprovenance: ai_authored\n---\n\n" + PRIVATE
    assert list(paragraphs(text)) == [PRIVATE]


def test_literal_layer_separates(tmp_path):
    index = Index.build([("a", PRIVATE + "\n\n" + PRIVATE.replace("zespołu", "grupy"))])
    index.save(tmp_path / "idx")
    index = Index.load(tmp_path / "idx")
    edited = PRIVATE.replace("Spotkanie", "").replace("trzech", "")
    assert index.check(edited).similar
    assert not index.check(PUBLIC).similar


def test_embedder_shortens_texts_the_server_rejects(monkeypatch):
    import httpx

    from tools.simcheck.core import Embedder

    def handler(request):
        import json as _json

        inputs = _json.loads(request.content)["input"]
        if any(len(t) > 500 for t in inputs):
            return httpx.Response(500, json={"error": {"message": "input is too large to process"}})
        return httpx.Response(200, json={"data": [{"embedding": [float(len(t)), 1.0]} for t in inputs]})

    e = Embedder("http://test/v1", "m")
    e.client = httpx.Client(base_url="http://test/v1", transport=httpx.MockTransport(handler))
    vecs = e.embed(["short", "x" * 2000, "also short"], progress_every=0)
    assert len(vecs) == 3
    assert vecs[0][0] == 5.0 and vecs[1][0] <= 500 and vecs[2][0] == 10.0


def test_threshold_halfway_when_separated():
    from tools.simcheck.calibrate import pick_threshold

    r = pick_threshold([0.8, 0.9], [0.1, 0.4], fa_budget=0.05)
    assert r["policy"] == "separated" and r["threshold"] == 0.6
    assert r["miss_rate"] == 0 and r["false_alarm_rate"] == 0


def test_threshold_respects_false_alarm_budget():
    from tools.simcheck.calibrate import pick_threshold

    pos = [0.5] + [0.9] * 99  # one weak positive would drag the zero-miss threshold down
    neg = [0.1] * 90 + [0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.82, 0.84, 0.86, 0.88]
    r = pick_threshold(pos, neg, fa_budget=0.05)
    assert r["policy"] == "fa-budget"
    assert r["false_alarm_rate"] <= 0.05
    assert r["miss_rate"] == 0.01


def test_calibration_drops_negatives_copied_from_the_corpus(tmp_path):
    from tools.simcheck.calibrate import calibrate

    priv = tmp_path / "priv"
    pub = tmp_path / "pub"
    priv.mkdir()
    pub.mkdir()
    (priv / "a.md").write_text(PRIVATE)
    (pub / "copy.md").write_text(PRIVATE)  # a "public" text that is really a corpus copy
    (pub / "fresh.md").write_text(PUBLIC)
    index = Index.build([("a", PRIVATE)])
    res = calibrate(index, [priv], [pub], sample=10, seed=1, rewriter=None)
    assert res["negatives_in_corpus"] == 1
    assert res["negatives"] == 1
