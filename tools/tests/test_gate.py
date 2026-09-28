import json
import os
from pathlib import Path

from tools.gate import __main__ as gate
from tools.simcheck.core import Index
from tools.simcheck.server import IndexHolder

PRIVATE = " ".join(f"Private paragraph about the gearbox of machine {i} and its oil pressure readings." for i in range(12))


def test_build_index_swaps_link_and_keeps_thresholds(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    (corpus / "_source" / "dowody").mkdir(parents=True)
    (corpus / "notes").mkdir()
    (corpus / "notes" / "a.md").write_text(PRIVATE)
    (corpus / "_source" / "dowody" / "public.md").write_text("Published document that must not be in the index. " * 20)
    monkeypatch.setenv("GATE_INDEX", str(tmp_path / "index"))
    monkeypatch.setenv("SIMCHECK_CORPUS_DIR", str(corpus))
    monkeypatch.setenv("SIMCHECK_PG_DSN", "none")
    monkeypatch.delenv("SIMCHECK_EMBED_URL", raising=False)
    assert gate.main(["build-index"]) == 0
    link = tmp_path / "index" / "current"
    first = link.resolve()
    holder = IndexHolder(link)
    assert holder.refresh().check(PRIVATE).similar
    assert not holder.refresh().check("Published document that must not be in the index. " * 20).similar

    idx = Index.load(first)
    idx.thresholds["literal"] = 0.33
    idx.save(first)
    assert holder.refresh().thresholds["literal"] == 0.33  # reload after calibration

    os.utime(corpus / "notes" / "a.md")
    assert gate.main(["build-index"]) == 0
    assert link.resolve() != first
    assert holder.refresh().thresholds["literal"] == 0.33  # carried over to the new build


def test_export_copies_deployment_files(tmp_path, monkeypatch):
    src = Path(__file__).resolve().parents[2] / "deploy" / "gate"
    monkeypatch.setattr(gate, "DEPLOY_DIR", src)
    assert gate.main(["export", str(tmp_path / "out")]) == 0
    assert (tmp_path / "out" / "quadlet" / "exocortex-gate.pod").exists()
    assert (tmp_path / "out" / "systemd" / "exocortex-gate-publisher.timer").exists()


def test_quadlet_units_are_consistent():
    root = Path(__file__).resolve().parents[2] / "deploy" / "gate"
    containers = {p.stem: p.read_text() for p in (root / "quadlet").glob("*.container")}
    commands = {"publish", "simcheck", "build-index", "calibrate", "selftest"}
    for name, text in containers.items():
        assert "Pod=exocortex-gate.pod" in text, name
        assert "Image=ghcr.io/hretheum/exocortex-gate:main" in text, name
        assert "AutoUpdate" not in text, name  # updates are scoped to the gate timer
        exec_line = [line for line in text.splitlines() if line.startswith("Exec=")]
        assert exec_line and exec_line[0].split("=", 1)[1] in commands, name
    services = {p.stem for p in (root / "systemd").glob("*.service")}
    for timer in (root / "systemd").glob("*.timer"):
        assert timer.stem in containers or timer.stem in services, f"{timer.name} has nothing to start"
    for vol in ("state", "repo", "index"):
        assert (root / "quadlet" / f"exocortex-gate-{vol}.volume").exists()


def test_publish_requires_repo_url(monkeypatch, capsys):
    monkeypatch.delenv("GATE_REPO_URL", raising=False)
    assert gate.main(["publish"]) == 2
