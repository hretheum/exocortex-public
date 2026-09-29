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


def test_relative_measures_discount_dense_regions():
    import numpy as np

    from tools.simcheck.core import SEMANTIC_K

    rng = np.random.default_rng(0)
    d = 64
    centre = rng.normal(size=d)
    cluster = [centre + 0.25 * rng.normal(size=d) for _ in range(SEMANTIC_K + 5)]  # a "topic" with many notes
    lone = rng.normal(size=d)  # one private note on its own
    corpus = np.array([v / np.linalg.norm(v) for v in cluster + [lone]], dtype="float32")
    index = Index.build([("a", PRIVATE)])
    index.vectors = corpus
    on_topic = centre + 0.3 * rng.normal(size=d)
    paraphrase = lone + 0.45 * rng.normal(size=d)
    q = np.array([v / np.linalg.norm(v) for v in (on_topic, paraphrase)], dtype="float32")
    v = index.semantic_variants(["x", "y"], q=q)
    # raw similarity cannot tell them apart well; the relative measures can
    assert v["margin"][1] > v["margin"][0]
    assert v["csls"][1] > v["csls"][0]


def test_apply_records_the_measure(tmp_path):
    from tools.simcheck.calibrate import apply

    Index.build([("a", PRIVATE)]).save(tmp_path / "idx")
    apply(tmp_path / "idx", {"literal": {"threshold": 0.4}, "semantic": {"threshold": 0.1, "measure": "margin"}})
    assert Index.load(tmp_path / "idx").thresholds["semantic_score"] == "margin"


def _two_stage_index(answer):
    import numpy as np

    index = Index.build([("a", PRIVATE + "\n\n" + PUBLIC)])
    index.vectors = np.array([[1.0, 0.0], [0.0, 1.0]], dtype="float32")
    index.texts = ["private note", "other note"]
    index.thresholds.update({"semantic": 0.99, "semantic_candidate": 0.8})
    seen = []

    class StubJudge:
        calls = 0

        def is_restatement(self, candidate, private):
            seen.append(private)
            return answer

    index._judge = StubJudge()
    index._embed_queries = lambda paras: np.array([[0.9, 0.1]] * len(paras), dtype="float32")
    return index, seen


def test_two_stage_holds_only_when_the_judge_says_so():
    text = "Zupełnie inny akapit o planowaniu prac zespołu, wdrożeniu nowej wersji i harmonogramie testów w kolejnych tygodniach."
    index, seen = _two_stage_index(True)
    r = index.check(text)
    assert r.similar and r.rule == "semantic-judged" and r.judged == 1
    assert seen[0][0] == "private note"  # nearest private paragraph first
    index, _ = _two_stage_index(False)
    r = index.check(text)
    assert not r.similar and r.judged == 1


def test_judge_reads_a_one_word_answer():
    import httpx

    from tools.simcheck.core import Judge

    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": " yes."}}]})

    j = Judge("http://t/v1", "m", client=httpx.Client(base_url="http://t/v1", transport=httpx.MockTransport(handler)))
    assert j.is_restatement("a", ["b"]) and j.calls == 1


def test_approved_paragraph_is_not_held():
    import numpy as np

    from tools.simcheck.core import paragraph_hash

    index = Index.build([("a", PRIVATE)])
    index.vectors = np.array([[1.0, 0.0]], dtype="float32")
    index.texts = [PRIVATE]
    index.thresholds.update({"semantic": 0.5})
    index._embed_queries = lambda paras: np.array([[1.0, 0.0]] * len(paras), dtype="float32")
    assert index.check(PUBLIC).rule == "semantic"
    r = index.check(PUBLIC, approved={paragraph_hash(PUBLIC)})
    assert not r.similar and r.rule == "approved"


def test_review_page_round_trip(tmp_path):
    from tools.simcheck.core import load_approved, paragraph_hash
    from tools.simcheck.review import approve, render

    docs = tmp_path / "docs"
    (docs / "pl").mkdir(parents=True)
    (docs / "pl" / "a.md").write_text(PUBLIC + "\n\nDrugi akapit, który zostanie przepisany przez właściciela, bo powtarza konkret z notatki prywatnej.\n")
    other = "Drugi akapit, który zostanie przepisany przez właściciela, bo powtarza konkret z notatki prywatnej."
    items = [{"para": PUBLIC, "score": 0.9, "judge": True,
              "neighbours": [{"score": 0.9, "text": PRIVATE, "source": {"vault": "_source/work/x.md"}}]},
             {"para": other, "score": 0.88, "judge": False,
              "neighbours": [{"score": 0.88, "text": PRIVATE, "source": {"db": "claude_session", "ref": "id"}}]}]
    page = render([{"file": "pl/a.md", "max": 0.9, "items": items}], "_source/dowody", "pl", "2026-09-28")
    assert "[[_source/dowody/pl/a|a]]" in page and "[[_source/work/x|x]]" in page
    # tick "keep" for the first paragraph, "rewrite" for the second
    first = page.index("- [ ] zostawiam")
    page = page[:first] + "- [x] zostawiam" + page[first + len("- [ ] zostawiam"):]
    second = page.index("- [ ] do przepisania", page.index("### 1.2."))
    page = page[:second] + "- [x] do przepisania" + page[second + len("- [ ] do przepisania"):]
    (tmp_path / "review.md").write_text(page)
    res = approve(tmp_path / "review.md", docs, tmp_path / "approved.txt")
    assert res["approved_added"] == 1 and res["rewrite"] == 1 and res["changed_since_review"] == 0
    assert load_approved(tmp_path / "approved.txt") == {paragraph_hash(PUBLIC)}
    # a second run adds nothing
    assert approve(tmp_path / "review.md", docs, tmp_path / "approved.txt")["approved_added"] == 0
    # paths listed with the documents folder in front still resolve
    (tmp_path / "review2.md").write_text(page.replace("## 1. pl/a.md", "## 1. dowody/pl/a.md"))
    assert approve(tmp_path / "review2.md", docs, tmp_path / "approved2.txt")["approved_added"] == 1


def test_review_covers_the_lab_output_folder(tmp_path):
    from tools.simcheck.core import load_approved, paragraph_hash
    from tools.simcheck.review import approve, render

    lab = tmp_path / "lab-out"
    (lab / "data" / "x").mkdir(parents=True)
    (lab / "data" / "x" / "results.csv").write_text(PUBLIC + "\n")
    items = [{"para": PUBLIC, "score": 0.9, "judge": False,
              "neighbours": [{"score": 0.9, "text": PRIVATE, "source": {"vault": "_source/work/x.md"}}]}]
    page = render([{"file": "lab-out/data/x/results.csv", "max": 0.9, "items": items}], "_source/dowody", "pl",
                  "2026-09-29")
    assert "`lab-out/data/x/results.csv`" in page and "[[_source/dowody/lab-out" not in page
    first = page.index("- [ ] zostawiam")
    page = page[:first] + "- [x] zostawiam" + page[first + len("- [ ] zostawiam"):]
    (tmp_path / "review.md").write_text(page)
    res = approve(tmp_path / "review.md", tmp_path / "docs", tmp_path / "approved.txt", lab)
    assert res["approved_added"] == 1 and load_approved(tmp_path / "approved.txt") == {paragraph_hash(PUBLIC)}


def _index_similar_to_everything():
    import numpy as np

    index = Index.build([("a", PRIVATE)])
    index.vectors = np.array([[1.0, 0.0]], dtype="float32")
    index.texts = [PRIVATE]
    index.thresholds.update({"semantic": 0.5})
    index._embed_queries = lambda paras: np.array([[1.0, 0.0]] * len(paras), dtype="float32")
    return index


def test_review_page_leaves_out_project_documentation(tmp_path):
    from tools.simcheck.review import collect

    docs = tmp_path / "docs"
    for rel in ("pl/roadmap/F9-toy.md", "pl/04-how-it-works.md", "pl/experiments/x/overview.md", "pl/misc/a.md"):
        (docs / rel).parent.mkdir(parents=True, exist_ok=True)
        (docs / rel).write_text(PUBLIC + "\n")
    files = collect(_index_similar_to_everything(), docs, {})
    assert sorted(f["file"] for f in files) == ["pl/experiments/x/overview.md", "pl/misc/a.md"]


def test_approvals_skip_project_documentation(tmp_path):
    from tools.simcheck.core import load_approved
    from tools.simcheck.review import approve, render

    docs = tmp_path / "docs"
    (docs / "pl" / "roadmap").mkdir(parents=True)
    (docs / "pl" / "roadmap" / "F9-toy.md").write_text(PUBLIC + "\n")
    items = [{"para": PUBLIC, "score": 0.9, "judge": False,
              "neighbours": [{"score": 0.9, "text": PRIVATE, "source": {"vault": "_source/work/x.md"}}]}]
    page = render([{"file": "pl/roadmap/F9-toy.md", "max": 0.9, "items": items}], "_source/dowody", "en", "2026-09-29")
    page = page.replace("- [ ] keep", "- [x] keep", 1)
    (tmp_path / "review.md").write_text(page)
    res = approve(tmp_path / "review.md", docs, tmp_path / "approved.txt")
    assert res["keep"] == 1 and res["approved_added"] == 0 and res["no_semantic_check"] == 1
    assert load_approved(tmp_path / "approved.txt") == set()
