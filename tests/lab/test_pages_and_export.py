# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Result pages (F2.7) and raw data export with recomputation (F2.8)."""
from __future__ import annotations

import json
import subprocess
import sys
import uuid

import pytest

from exocortex.lab import experiments as ex
from tests.lab.conftest import ROOT, needs_engine
from tests.lab.test_graph_and_toy import _docs

pytestmark = needs_engine


def _task(root, lang, phase, n, status, deps):
    other = "en" if lang == "pl" else "pl"
    path = root / lang / "roadmap" / phase / f"{phase}.{n}-t.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nid: {phase}.{n}\nphase: {phase}\nlang: {lang}\ncounterpart: ../../../{other}/roadmap/{phase}/"
                    f"{phase}.{n}-t.md\nstatus: {status}\ndepends_on: {json.dumps(deps)}\nestimate: 4h\nowner: agent\n"
                    f"provenance: ai_authored\nprovenance_metadata: {{date: 2026-09-29, human_validated: false}}\n---\n\n"
                    f"# {phase}.{n}. {'Zadanie' if lang == 'pl' else 'Task'} {n}\n")


def _phase(root, lang, phase, body=""):
    other = "en" if lang == "pl" else "pl"
    path = root / lang / "roadmap" / f"{phase}-x.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nid: {phase}\nlang: {lang}\ncounterpart: ../../{other}/roadmap/{phase}-x.md\nstatus: todo\n---\n\n"
                    f"# {phase}. {'Faza' if lang == 'pl' else 'Phase'}\n\n{body}")


@pytest.fixture()
def lab_docs(conn, tenant, tmp_path, monkeypatch):
    """A documents tree with two phases, as the only documents of a fresh tenant."""
    from exocortex.lab.docsync import sync_documents

    monkeypatch.delenv("EXOCORTEX_SOURCE_ALLOWLIST", raising=False)
    t = str(uuid.uuid4())
    monkeypatch.setenv("TENANT_ID", t)
    root = tmp_path / "dowody"
    for lang in ("pl", "en"):
        _phase(root, lang, "F8")
        _task(root, lang, "F8", 1, "done", [])
        _task(root, lang, "F8", 2, "doing", ["F8.1"])
        _task(root, lang, "F8", 3, "todo", ["F8.2", "F9"])
        serial = root / lang / "roadmap" / "F8" / "F8.4-s.md"
        serial.write_text((root / lang / "roadmap" / "F8" / "F8.3-t.md").read_text().replace("id: F8.3", "id: F8.4")
                          .replace("phase: F8", "phase: F8\ntype: serial").replace("F8.3-t.md", "F8.4-s.md")
                          .replace("# F8.3.", "# F8.4."))
        _phase(root, lang, "F9", ("### F9.1. " + ("Pierwsze" if lang == "pl" else "First") +
                                  "\n\nTekst. " + ("Zależy od F8." if lang == "pl" else "Depends on F8.") + "\n"))
    sync_documents(conn, t, root, base_uri=f"file:///vault/_source/dowody/{uuid.uuid4().hex[:8]}/")
    return t, tmp_path


def test_roadmap_page_shows_every_task_with_what_it_waits_for(conn, lab_docs):
    from exocortex.lab.docsync import current_documents
    from exocortex.lab.pages import roadmap_page

    tenant, _ = lab_docs
    pl = roadmap_page(current_documents(conn, tenant), "pl")
    assert "| [F8.3](../roadmap/F8/F8.3-t.md) | Zadanie 3 | do zrobienia | F8.2, F9 | F8.2, F9 |" in pl
    assert "| [F8.2](../roadmap/F8/F8.2-t.md) | Zadanie 2 | w toku | F8.1 | — |" in pl
    assert "| [F9.1](../roadmap/F9-x.md) | Pierwsze | do zrobienia (opis w dokumencie fazy) | F8 | F8 |" in pl
    assert "| [F8](../roadmap/F8-x.md) | 4 | 1 | 1 | 2 |" in pl  # the serial task F8.4 counts too
    assert "| [F8.1](../roadmap/F8/F8.1-t.md) | Zadanie 1 | zrobione | — | — |" in pl
    en = roadmap_page(current_documents(conn, tenant), "en")
    assert "| [F8.3](../roadmap/F8/F8.3-t.md) | Task 3 | to do | F8.2, F9 | F8.2, F9 |" in en


def test_pages_come_in_pairs_that_pass_the_parity_check(conn, lab_docs):
    from exocortex.lab.pages import compile_pages
    from tools.paritycheck.core import check

    tenant, tmp = lab_docs
    out = tmp / "out"
    first = compile_pages(conn, tenant, out)
    assert "pl/generated/roadmap-status.md" in first["written"] and "en/generated/experiments.md" in first["written"]
    assert compile_pages(conn, tenant, out)["written"] == []  # nothing changes without new data
    result = check(out)
    assert result.ok, [str(p) for p in result.problems]


def test_export_and_recompute_give_the_same_numbers(conn, tenant, tmp_path, monkeypatch):
    from exocortex.lab import export, toy
    from exocortex.lab.cli import runners
    from exocortex.lab.docsync import sync_documents
    from exocortex.lab.pages import dossier_page

    monkeypatch.delenv("EXOCORTEX_SOURCE_ALLOWLIST", raising=False)
    slug = "toy-" + uuid.uuid4().hex[:8]
    monkeypatch.setattr(toy, "SLUG", slug)
    folder = "e-" + uuid.uuid4().hex[:8]
    _docs(tmp_path / "docs", n=10, folder=folder)
    sync_documents(conn, tenant, tmp_path / "docs", base_uri=f"file:///vault/_source/dowody/{uuid.uuid4().hex[:8]}/")
    ids = toy.setup(conn, tenant, tuning=8, control=4,
                    items=[i for i in toy.frame(conn, tenant) if f"/{folder}/" in i["item_id"]])
    run = ex.create_run(conn, ids["experiment"], "run-2026-09-30-1", ids["samples"]["tuning"], hypothesis_version=1)
    ex.enqueue(conn, run, list(ids["configs"].values()))
    ex.work(conn, runners(conn, tenant), owner="test", run_uuid=run)
    result_ids = toy.compute_metrics(conn, run)
    out = tmp_path / "out"
    exp = conn.execute("SELECT id, slug, kind, params FROM experiments WHERE slug = %s", (slug,)).fetchone()
    changed = export.export_experiment(conn, dict(exp), out)
    assert f"data/{slug}/results.csv" in changed and f"data/{slug}/datapackage.json" in changed
    assert export.export_experiment(conn, dict(exp), out) == []
    results = (out / "data" / slug / "results.csv").read_text()
    assert "unit_chars" in results and "context" not in results  # toy data carries lengths, not text
    package = json.loads((out / "data" / slug / "datapackage.json").read_text())
    assert package["exocortex"]["kind"] == "toy" and {r["name"] for r in package["resources"]} >= {"results", "metrics"}
    proc = subprocess.run([sys.executable, str(ROOT / "lab" / "recompute.py"), slug, "--data", str(out / "data")],
                          capture_output=True, text=True, cwd=tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert f"{len(result_ids)} published number(s); all reproduced exactly" in proc.stdout
    page = dossier_page(conn, slug, "en", True)
    for rid in result_ids:
        assert f"`{rid}`" in page
    assert f"../../../data/{slug}/datapackage.json" in page


def test_recompute_notices_a_changed_number(conn, tenant, tmp_path, monkeypatch):
    out = tmp_path / "data" / "x"
    out.mkdir(parents=True)
    (out / "datapackage.json").write_text(json.dumps({"exocortex": {"kind": "toy", "params": {}}}))
    (out / "results.csv").write_text("result_uuid,run_id,config,item_id,ok,output\n"
                                     'a,run-1,c1,d1,true,"{""chars"": 10, ""unit_chars"": []}"\n')
    (out / "metrics.csv").write_text("result_id,run_id,config,metric,value,ci_low,ci_high,n,method,details\n"
                                     "x/run-1/c1/mean_chars,run-1,c1,mean_chars,11.0,10.0,10.0,1,x,{}\n"
                                     "x/run-1/c1/long_unit_share,run-1,c1,long_unit_share,0.0,0.0,0.7934,1,wilson,{}\n")
    proc = subprocess.run([sys.executable, str(ROOT / "lab" / "recompute.py"), "x", "--data", str(tmp_path / "data")],
                          capture_output=True, text=True)
    assert proc.returncode == 1 and "DIFFERENT x/run-1/c1/mean_chars" in proc.stdout
