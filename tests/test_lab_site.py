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
            "---\nid: how\nlang: en\n---\n\n# How\n\nIntro.\n\n## One\n\nText.\n\n## FAQ\n\n### A question\n\nAn answer.\n", encoding="utf-8")
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
    assert ids == ["abstract", "question", "prereg", "data", "method", "runs", "results", "gates", "changes",
                   "reproduce", "limits", "refs", "cite"]
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
