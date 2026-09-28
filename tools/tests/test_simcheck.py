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
