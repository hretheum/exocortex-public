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
