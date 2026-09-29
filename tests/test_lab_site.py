# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Build the lab site from a minimal documents tree and check its structure."""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FRONT = "---\nid: {id}\nlang: {lang}\ncounterpart: ../../../{other}/experiments/toy/overview.md\nstatus: preparation\nroadmap: F9\nstage: 1\ntier: S\ntagline: \"{tag}\"\nupdated: 2026-09-28\n---\n"
SECTIONS = ["Abstract", "Question", "Preregistration", "Data", "Method", "Runs", "Results", "Gates", "Changes",
            "Reproduce", "Limits", "Refs"]


def _write_docs(docs: Path, corpora: Path) -> None:
    for lang, other in (("en", "pl"), ("pl", "en")):
        d = docs / lang / "experiments" / "toy"
        d.mkdir(parents=True)
        body = FRONT.format(id=f"toy-{lang}", lang=lang, other=other, tag="A toy question.") + f"\n# Toy {lang}\n\n"
        for s in SECTIONS:
            body += f"## {s}\n\n"
            body += ("| Date | Version | Change |\n|---|---|---|\n| 2026-09-28 | 0.1 | Created |\n\n" if s == "Changes"
                     else "Text with a [link](../../roadmap/F1-x.md) and a [site](https://example.org).\n\n")
        (d / "overview.md").write_text(body, encoding="utf-8")
        (docs / lang / "roadmap").mkdir(parents=True, exist_ok=True)
        (docs / lang / "roadmap" / "F9-toy.md").write_text(
            "---\nid: F9\nlang: en\n---\n\n# F9. Toy phase\n\n## Goal\n\nA goal.\n\n### F9.1. First task\n\nText.\n", encoding="utf-8")
        (docs / lang / "04-how-it-works.md").write_text(
            "---\nid: how\nlang: en\n---\n\n# How\n\nIntro.\n\n## One\n\nText.\n\n## FAQ\n\n### For data teams: how it is built\n\nDetails.\n\n### A question\n\nAn answer.\n", encoding="utf-8")
    (corpora / "toy").mkdir(parents=True)
    (corpora / "toy" / "manifest.csv").write_text("id,x\n1,a\n2,b\n", encoding="utf-8")


def _build(tmp_path: Path) -> Path:
    docs, corpora, out = tmp_path / "dowody", tmp_path / "corpora", tmp_path / "dist"
    _write_docs(docs, corpora)
    subprocess.run([sys.executable, str(ROOT / "lab-site" / "build.py"), "--docs", str(docs), "--corpora", str(corpora),
                    "--out", str(out), "--asof", "2026-09-28"], check=True)
    return out


def test_pages_redirect_and_data(tmp_path):
    out = _build(tmp_path)
    for lang in ("en", "pl"):
        for page in ("", "how-it-works/", "hypotheses/", "status/", "hypotheses/toy/"):
            assert (out / lang / page / "index.html").exists(), (lang, page)
    root = (out / "index.html").read_text(encoding="utf-8")
    assert "location.replace('en/')" in root and 'content="0; url=en/"' in root
    sums = (out / "data" / "toy" / "SHA256SUMS").read_text(encoding="utf-8")
    assert re.match(r"^[0-9a-f]{64}  manifest.csv$", sums.strip())
    index = json.loads((out / "hypotheses.json").read_text(encoding="utf-8"))
    assert index["hypotheses"][0]["slug"] == "toy" and index["hypotheses"][0]["files"][0]["records"] == 2
    assert "lab.exocortex.zone" in (out / "sitemap.xml").read_text(encoding="utf-8")


def test_every_page_says_we_are_not_affiliated_with_model_vendors(tmp_path):
    out = _build(tmp_path)
    for lang, phrase in (("en", "not affiliated with OpenAI"), ("pl", "Nie mamy powiązania z OpenAI")):
        for page in ("", "how-it-works/", "hypotheses/", "status/", "hypotheses/toy/"):
            html = (out / lang / page / "index.html").read_text(encoding="utf-8")
            assert phrase in html, (lang, page)


def test_internal_links_resolve_and_nothing_third_party(tmp_path):
    out = _build(tmp_path)
    for page in out.rglob("*.html"):
        if page.name == "404.html":
            continue
        html = page.read_text(encoding="utf-8")
        for m in re.finditer(r'(?:href|src)="([^"#]*)"', html):
            url = m.group(1)
            if not url or url.startswith(("http:", "https:", "data:")):
                continue
            target = (page.parent / url).resolve()
            if target.is_dir():
                target = target / "index.html"
            assert target.exists(), (page.name, url)
        assert "fonts.googleapis.com" not in html  # fonts are served locally by default


def test_dossier_sections_in_order(tmp_path):
    out = _build(tmp_path)
    html = (out / "en" / "hypotheses" / "toy" / "index.html").read_text(encoding="utf-8")
    ids = re.findall(r'<section id="s-([a-z]+)"', html)
    assert ids == ["applications", "abstract", "question", "prereg", "data", "method", "runs", "results", "gates",
                   "reproduce", "limits", "refs", "changes", "cite"]
    assert "Not frozen yet" in html and "SHA-256" in html


def test_build_survives_missing_project_documents(tmp_path):
    """Project documents can be held by the gate; the site still builds and shows a notice instead."""
    docs, corpora, out = tmp_path / "dowody", tmp_path / "corpora", tmp_path / "dist"
    _write_docs(docs, corpora)
    for lang in ("en", "pl"):
        (docs / lang / "04-how-it-works.md").unlink()
    subprocess.run([sys.executable, str(ROOT / "lab-site" / "build.py"), "--docs", str(docs), "--corpora", str(corpora),
                    "--out", str(out), "--asof", "2026-09-28"], check=True)
    html = (out / "en" / "how-it-works" / "index.html").read_text(encoding="utf-8")
    assert "being published" in html and html.count("<figure") == 8
    assert (out / "en" / "hypotheses" / "toy" / "index.html").exists()


def test_how_page_labelled_blocks_are_folded_and_questions_get_a_mark(tmp_path):
    """A "Label: subject" heading is shown as written and folded; a plain heading is a question and the first is open."""
    out = _build(tmp_path)
    html = (out / "en" / "how-it-works" / "index.html").read_text(encoding="utf-8")
    assert '<details class="faqi"><summary>For data teams: how it is built</summary>' in html
    assert '<details class="faqi" open><summary>A question?</summary>' in html
    assert "built?</summary>" not in html


def test_build_with_no_documents_at_all(tmp_path):
    out, docs = tmp_path / "dist", tmp_path / "empty"
    docs.mkdir()
    subprocess.run([sys.executable, str(ROOT / "lab-site" / "build.py"), "--docs", str(docs), "--out", str(out),
                    "--asof", "2026-09-28"], check=True)
    assert (out / "en" / "index.html").exists() and (out / "hypotheses.json").exists()


def test_status_page_is_computed_from_task_states(tmp_path):
    """No static picture, phase labels follow the tasks (a state file is ignored), inline tasks read task_status."""
    docs, corpora, out = tmp_path / "dowody", tmp_path / "corpora", tmp_path / "dist"
    _write_docs(docs, corpora)
    for lang in ("en", "pl"):
        (docs / lang / "roadmap" / "F9-toy.md").write_text(
            "---\nid: F9\nlang: en\ntask_status: {F9.1: done, F9.2: doing}\n---\n\n# F9. Toy phase\n\n## Goal\n\nA goal.\n\n"
            "### F9.1. First task\n\nText.\n\n### F9.2. Second task\n\nText.\n\n### F9.3. Third task\n\nText.\n", encoding="utf-8")
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"F9": "working"}), encoding="utf-8")
    subprocess.run([sys.executable, str(ROOT / "lab-site" / "build.py"), "--docs", str(docs), "--corpora", str(corpora),
                    "--out", str(out), "--state", str(state), "--asof", "2026-09-28"], check=True)
    html = (out / "en" / "status" / "index.html").read_text(encoding="utf-8")
    assert "<figure" not in html
    assert "1/3" in html and "In progress" in html and "Working" not in html


# ------------------------------------------------------------ business applications (F8.1) ----
def _applications(docs: Path, approve: bool = True) -> None:
    """A draft from the stand-in model, then what the owner does to approve it."""
    from exocortex.lab import applications as ap
    from tests.lab.applications_tree import model_output
    from tests.lab.test_applications import MODELS, FakeLLM

    kinds = ap.catalogue(ROOT / "lab" / "applications-catalogue.yaml")
    result = ap.draft(docs, "toy", FakeLLM(model_output()), kinds=kinds, models=MODELS)
    assert "written" in result, result
    if approve:
        for lang in ("pl", "en"):
            p = docs / lang / "experiments" / "toy" / "applications.md"
            p.write_text(p.read_text(encoding="utf-8").replace("publish: false", "publish: true")
                         .replace("human_validated: false", "human_validated: true"), encoding="utf-8")


def _site(tmp_path: Path, change=None) -> dict[str, str]:
    docs, corpora, out = tmp_path / "dowody", tmp_path / "corpora", tmp_path / "dist"
    if not docs.exists():
        _write_docs(docs, corpora)
    if change:
        change(docs)
    subprocess.run([sys.executable, str(ROOT / "lab-site" / "build.py"), "--docs", str(docs), "--corpora", str(corpora),
                    "--out", str(out), "--asof", "2026-09-28"], check=True)
    return {lang: (out / lang / "hypotheses" / "toy" / "index.html").read_text(encoding="utf-8") for lang in ("en", "pl")}


def test_without_applications_the_section_is_still_first_with_a_notice(tmp_path):
    html = _site(tmp_path)
    for lang in ("en", "pl"):
        ids = re.findall(r'<section id="s-([a-z]+)"', html[lang])
        assert ids[0] == "applications" and len(ids) == 14
    assert "being prepared" in html["en"] and "w przygotowaniu" in html["pl"]
    assert "being updated" not in html["en"]


def test_approved_current_applications_come_first_on_the_page(tmp_path):
    html = _site(tmp_path, _applications)
    ids = re.findall(r'<section id="s-([a-z]+)"', html["en"])
    assert ids[0] == "applications" and len(ids) == 14
    assert "<h3>If we confirm, if we refute</h3>" in html["en"] and "being updated" not in html["en"]
    for lang in ("en", "pl"):  # the table shows application, who uses it, conditions: not the result link, not the strength
        sec = re.search(r'<section id="s-applications".*?</section>', html[lang], re.DOTALL).group(0)
        assert len(re.findall(r"<th[ >]", sec)) == 3 and 'href="#s-results"' not in sec
        assert "hypothesis, no evidence" not in sec and "hipoteza, bez dowodu" not in sec
    assert re.search(r'<span class="n" aria-hidden="true">1</span>Business applications', html["en"])
    for lang, head in (("en", "For the technically minded"), ("pl", "Dla dociekliwych")):
        sec = re.search(r'<section id="s-applications".*?</section>', html[lang], re.DOTALL).group(0)
        box = re.search(r'<aside class="nerd">(.*?)</aside>', sec, re.DOTALL).group(1)
        assert head in box and sec.index('<aside class="nerd">') > sec.index("</table>")  # below the plain text
        assert "nDCG" not in sec[: sec.index('<aside class="nerd">')]


def test_unapproved_applications_show_only_a_notice(tmp_path):
    html = _site(tmp_path, lambda docs: _applications(docs, approve=False))
    assert "being updated" in html["en"] and "aktualizowana" in html["pl"]
    assert "hypothesis, no evidence" not in html["en"]


def test_a_changed_result_hides_the_approved_section(tmp_path):
    def change(docs):
        _applications(docs)
        (docs / "data" / "toy").mkdir(parents=True)
        (docs / "data" / "toy" / "metrics.csv").write_text(
            "result_id,run_id,config,metric,value,ci_low,ci_high,n,method,details\n"
            "toy/run-1/a/acc,run-1,a,accuracy,0.7,0.6,0.8,30,wilson,{}\n", encoding="utf-8")
    html = _site(tmp_path, change)
    assert "being updated" in html["en"] and "hypothesis, no evidence" not in html["en"]


def test_applications_in_one_language_only_show_a_notice(tmp_path):
    def change(docs):
        _applications(docs)
        (docs / "en" / "experiments" / "toy" / "applications.md").unlink()
    html = _site(tmp_path, change)
    assert "being updated" in html["en"] and "aktualizowana" in html["pl"]


def test_deviations_and_history_come_after_the_sources_and_before_how_to_cite(tmp_path):
    html = _site(tmp_path, _applications)
    ids = re.findall(r'<section id="s-([a-z]+)"', html["en"])
    assert ids[-3:] == ["refs", "changes", "cite"] and ids.index("changes") == len(ids) - 2
    nums = re.findall(r'<span class="n" aria-hidden="true">(\d+)</span>', html["en"])
    assert nums == [str(i) for i in range(1, len(nums) + 1)]  # headings stay numbered in reading order
