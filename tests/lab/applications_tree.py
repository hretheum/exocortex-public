# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""A minimal synthetic documents tree for the applications section (F8.1), shared by lab and site tests."""

from __future__ import annotations

from pathlib import Path

SECTIONS = {
    "pl": ["Streszczenie", "Pytanie i hipoteza", "Prerejestracja", "Dane", "Metoda", "Przebiegi", "Wyniki",
           "Decyzje z bramek", "Odstępstwa i historia zmian", "Jak powtórzyć", "Ograniczenia", "Źródła"],
    "en": ["Abstract", "Question and hypothesis", "Preregistration", "Data", "Method", "Runs", "Results",
           "Gate decisions", "Deviations and change log", "How to reproduce", "Limitations", "References"],
}
RESULTS = {"pl": "Brak wyników.", "en": "No results yet."}
METRICS_HEAD = "result_id,run_id,config,metric,value,ci_low,ci_high,n,method,details\n"


def overview(lang: str, slug: str, status: str = "planned", stage: int = 0, results: str | None = None,
             abstract: str = "") -> str:
    other = "en" if lang == "pl" else "pl"
    text = (f"---\nid: {slug}-overview\nlang: {lang}\ncounterpart: ../../../{other}/experiments/{slug}/overview.md\n"
            f"status: {status}\nroadmap: F9.1\nstage: {stage}\ntier: S\ntagline: \"A toy question.\"\n"
            f"updated: 2026-09-28\n---\n\n# Toy {lang}\n\n")
    for i, heading in enumerate(SECTIONS[lang]):
        body = (results or RESULTS[lang]) if i == 6 else (abstract or "Text.") if i == 0 else "Text."
        if heading.startswith(("Odstępstwa", "Deviations")):
            body = "| Date | Version | Change |\n|---|---|---|\n| 2026-09-28 | 0.1 | Created |"
        text += f"## {heading}\n\n{body}\n\n"
    return text


def gate(lang: str, slug: str, decision: str, met: list[str], result_ids: list[str], approved: bool = True,
         date: str = "2026-10-01", gate_name: str = "G1") -> str:
    head = ("Kryterium | Próg | Wynik | Przedział ufności | Id wyniku | Spełnione" if lang == "pl"
            else "Criterion | Threshold | Result | Confidence interval | Result id | Met")
    heading = "Kryteria z karty hipotezy (bez zmian)" if lang == "pl" else "Criteria from the hypothesis card (unchanged)"
    rows = "".join(f"| c{i} | ≥ 0.5 | 0.6 | 0.5 – 0.7 | `{result_ids[0] if result_ids else ''}` | {m} |\n"
                   for i, m in enumerate(met))
    return (f"---\ntype: gate_decision\nlang: {lang}\nhypothesis: \"{slug}\"\nhypothesis_version: 1\n"
            f"gate: {gate_name}\ndecision: {decision}\ndate: \"{date}\"\napproved_by: [owner]\n"
            f"return_condition: null\nresult_ids: {result_ids}\nhuman_validated: {'true' if approved else 'false'}\n"
            f"---\n\n# Gate\n\n## {heading}\n\n| {head} |\n|---|---|---|---|---|---|\n{rows}\n## Decision\n\nText.\n")


def run_note(lang: str, slug: str, result_ids: list[str]) -> str:
    return (f"---\ntype: run_note\nlang: {lang}\nhypothesis: \"{slug}\"\nhypothesis_version: 1\n"
            f"run_id: \"run-2026-10-01-1\"\ndate: \"2026-10-01\"\nsample: tuning\nconfiguration: baseline\n"
            f"result_ids: {result_ids}\nhuman_validated: false\n---\n\n# Run\n\nText.\n")


def make(docs: Path, slug: str = "toy", status: str = "planned", stage: int = 0, metrics: str | None = None,
         gates: dict[str, tuple] | None = None, runs: dict[str, list[str]] | None = None,
         results: dict[str, str] | None = None) -> Path:
    """Write a dossier; ``gates`` maps a file name to gate() arguments after lang and slug."""
    for lang in ("pl", "en"):
        folder = docs / lang / "experiments" / slug
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "overview.md").write_text(
            overview(lang, slug, status, stage, (results or {}).get(lang)), encoding="utf-8")
        for name, args in (gates or {}).items():
            (folder / name).write_text(gate(lang, slug, *args), encoding="utf-8")
        for name, ids in (runs or {}).items():
            (folder / name).write_text(run_note(lang, slug, ids), encoding="utf-8")
    if metrics is not None:
        (docs / "data" / slug).mkdir(parents=True, exist_ok=True)
        (docs / "data" / slug / "metrics.csv").write_text(METRICS_HEAD + metrics, encoding="utf-8")
    return docs


def model_output(scenarios: bool = True, result: str = "results-section", number: str = "") -> dict:
    """A reply of the stand-in model: text only, no label, no numbers unless ``number`` is given."""
    out = {
        "sentence": {"pl": f"Hipoteza mówi, czy prostsze wyszukiwanie wystarcza w zespole{number}.",
                     "en": f"The hypothesis tells whether simpler search is enough for a team{number}."},
        "rows": [{"kind": "tool-choice", "result": result,
                  "application": {"pl": "wybór sposobu wyszukiwania w bazie dokumentów",
                                  "en": "choosing how to search a document base"},
                  "who": {"pl": "zespoły produktowe", "en": "product teams"},
                  "conditions": {"pl": "jeden korpus publiczny, jeden zbiór pytań",
                                 "en": "one public corpus, one set of questions"}}],
        "limits": [{"pl": "Wynik dotyczy jednego korpusu i nie mówi nic o innych danych.",
                    "en": "The result concerns one corpus and says nothing about other data."}],
        "next": [{"pl": "Powtórzenie na innym korpusie.", "en": "A repetition on another corpus."}],
    }
    if scenarios:
        out["scenarios"] = {
            "if_confirmed": {"pl": "warto dodać powiązania do wyszukiwania i mierzyć je dalej.",
                             "en": "it is worth adding links to search and keep measuring them."},
            "if_refuted": {"pl": "nie warto inwestować w rozbudowę grafu dla wyszukiwania.",
                           "en": "it is not worth investing in a larger graph for search."}}
    return out
