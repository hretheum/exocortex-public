# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""The lab's on-demand jobs through the CLI the units call (roadmap task F2.9): a run enqueued for later,
the queue drained by ``work``, and blind rating driven by unit instance names."""
from __future__ import annotations

import json
import re
import uuid

import pytest

from exocortex.lab import blind
from tests.lab.conftest import needs_engine
from tests.lab.test_graph_and_toy import _docs

pytestmark = needs_engine


@pytest.fixture()
def toy(conn, tenant, tmp_path, monkeypatch, lab_url):
    from exocortex.lab import toy as toy_mod
    from exocortex.lab.docsync import sync_documents

    monkeypatch.setenv("DATABASE_URL", lab_url)
    monkeypatch.setenv("LAB_OUT", str(tmp_path / "out"))
    monkeypatch.delenv("EXOCORTEX_SOURCE_ALLOWLIST", raising=False)
    slug = "toy-" + uuid.uuid4().hex[:8]
    monkeypatch.setattr(toy_mod, "SLUG", slug)
    folder = "d-" + uuid.uuid4().hex[:8]
    _docs(tmp_path / "docs", n=10, folder=folder)
    sync_documents(conn, tenant, tmp_path / "docs", base_uri=f"file:///vault/_source/dowody/{uuid.uuid4().hex[:8]}/")
    items = [i for i in toy_mod.frame(conn, tenant) if f"/{folder}/" in i["item_id"]]
    real_setup = toy_mod.setup
    monkeypatch.setattr(toy_mod, "setup", lambda c, t, **kw: real_setup(c, t, tuning=6, control=3, items=items))
    return slug


def _run(capsys, argv) -> tuple[int, dict]:
    from exocortex.lab.cli import main

    code = main(argv)
    return code, json.loads(capsys.readouterr().out)


def test_a_queued_run_is_worked_off_and_finished_by_work(conn, toy, capsys):
    code, out = _run(capsys, ["run", "--instance", f"{toy}_tuning_queue"])
    assert code == 0 and out["queued"] is True and out["jobs"] == 12
    status = conn.execute("SELECT status FROM exp_runs r JOIN experiments e ON e.id = r.experiment_id "
                          "WHERE e.slug = %s", (toy,)).fetchone()["status"]
    assert status == "queued"
    code, out = _run(capsys, ["work"])
    assert code == 0 and out["done"] >= 12
    mine = [r for r in out["finished_runs"] if r["experiment"] == toy]
    assert len(mine) == 1 and mine[0]["status"] == "done" and len(mine[0]["result_ids"]) == 5
    row = conn.execute("SELECT r.status, r.finished_at FROM exp_runs r JOIN experiments e ON e.id = r.experiment_id "
                       "WHERE e.slug = %s", (toy,)).fetchone()
    assert row["status"] == "done" and row["finished_at"] is not None


def test_blind_steps_by_instance_name(conn, toy, capsys, tmp_path):
    assert _run(capsys, ["run", "--instance", f"{toy}_tuning"])[0] == 0
    code, out = _run(capsys, ["blind", "--instance", f"draw_{toy}_blind-u", "--repeats", "1"])
    assert code == 0 and out["candidates"] == 12
    page = (tmp_path / "out" / "blind" / toy / "blind-u.pl.md").read_text(encoding="utf-8")
    assert "first-sentence" not in page and "longest-sentence" not in page
    # no page in the documents tree yet: import is refused before it touches anything
    docs = tmp_path / "vault"
    code, out = _run(capsys, ["blind", "--instance", f"import_{toy}_blind-u", "--root", str(docs)])
    assert code == 2 and "no rated page" in out["refused"]
    rated = re.sub(r"- \[ \] poprawne", "- [x] poprawne", page)
    rated = rated.replace("rating_complete: false", "rating_complete: true").replace('rater: ""', "rater: tester")
    target = docs / "pl" / "experiments" / toy / "blind-u.md"
    target.parent.mkdir(parents=True)
    target.write_text(rated, encoding="utf-8")
    code, out = _run(capsys, ["blind", "--instance", f"import_{toy}_blind-u", "--root", str(docs)])
    assert code == 0 and out["stored"]["stored"] == 13 and out["summary"]["repeats"] == 1
    code, again = _run(capsys, ["blind", "--instance", f"summary_{toy}_blind-u"])  # the only rater
    assert code == 0 and again["rater"] == "tester" and again["summary"] == out["summary"]
    _, items = blind.read_page(rated, "pl")
    assert all(i["verdicts"] == ["correct"] for i in items)


def test_run_refuses_unknown_samples_and_configurations(conn, toy, capsys):
    code, out = _run(capsys, ["run", "--instance", f"{toy}_nonsense"])
    assert code == 2 and "refused" in out
    code, out = _run(capsys, ["run", "--instance", f"{toy}_tuning_first-sentence"])
    assert code == 2 and "refused" in out
