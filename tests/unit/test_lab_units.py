# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Deployment units of the lab and the gate (roadmap task F2.9).

Rule: every recurring job has an on-demand start with one command. A timer
``X.timer`` starts ``X.service``, which comes from the Quadlet file
``X.container`` or from a plain ``X.service``; either can be started by hand
with ``systemctl --user start X``, and the deployment README lists that
command.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "deploy" / "lab"
GATE = ROOT / "deploy" / "gate"


def _conf(path: Path) -> list[tuple[str, str]]:
    return [tuple(line.split("=", 1)) for line in path.read_text(encoding="utf-8").splitlines()
            if "=" in line and not line.lstrip().startswith("#")]


def _timer_target(timer: Path) -> str:
    unit = dict(_conf(timer)).get("Unit")
    return unit.removesuffix(".service") if unit else timer.stem


@pytest.mark.parametrize("deploy", [LAB, GATE], ids=["lab", "gate"])
def test_every_timer_has_an_on_demand_counterpart(deploy):
    timers = sorted((deploy / "systemd").glob("*.timer"))
    assert timers
    readme = (deploy / "README.md").read_text(encoding="utf-8")
    for timer in timers:
        name = _timer_target(timer)
        container = deploy / "quadlet" / f"{name}.container"
        service = deploy / "systemd" / f"{name}.service"
        assert container.exists() or service.exists(), f"{timer.name} starts nothing that can be started by hand"
        if container.exists():  # a job, not a service that must stay up
            assert dict(_conf(container)).get("Type") == "oneshot", f"{name} is not a one-shot job"
        assert re.search(rf"systemctl --user start {re.escape(name)}(\.service)?\b", readme), \
            f"{name}: no on-demand command in {deploy.name}/README.md"


def test_every_lab_job_is_listed_with_its_command():
    readme = (LAB / "README.md").read_text(encoding="utf-8")
    for unit in (LAB / "quadlet").glob("*.container"):
        conf = dict(_conf(unit))
        if conf.get("Type") != "oneshot" or unit.stem == "exocortex-lab-migrate":
            continue  # services and the migration, which the other units start
        name = unit.stem
        pattern = re.escape(name[:-1]) + r"@\S+" if name.endswith("@") else re.escape(name) + r"\b"
        assert re.search(r"systemctl --user start " + pattern, readme), f"{name}: not in the on-demand table"


def _lab_units():
    return {p.stem: _conf(p) for p in (LAB / "quadlet").glob("*.container")}


def _values(conf, key):
    return [v for k, v in conf if k == key]


def test_new_jobs_stay_inside_the_radar_s_reach():
    units = _lab_units()
    radar = units["exocortex-lab-radar"]
    allowed_volumes = set(_values(radar, "Volume")) | {"%h/vault/_source/dowody:/vault/_source/dowody:ro,z"}
    for name in ("exocortex-lab-run@", "exocortex-lab-work", "exocortex-lab-blind@"):
        conf = units[name]
        assert dict(conf)["Image"] == "ghcr.io/hretheum/exocortex-public:main", name
        assert _values(conf, "Network") == ["exocortex-lab.network"], name
        assert _values(conf, "Secret") == _values(radar, "Secret"), name
        assert set(_values(conf, "Volume")) <= allowed_volumes, name
        assert "exocortex-lab-fetch.volume:/run/lab-fetch:z" not in _values(conf, "Volume"), name  # no downloads
        assert not any(k in ("PublishPort", "AddCapability", "PodmanArgs") for k, _ in conf), name
    assert not any("vault" in v and "ro" not in v.split(":")[-1] for v in _values(units["exocortex-lab-blind@"], "Volume"))


def test_instance_units_pass_the_instance_to_the_cli():
    from exocortex.lab.cli import build_parser, parse_blind_instance, parse_run_instance

    units = _lab_units()
    assert dict(units["exocortex-lab-run@"])["Exec"] == "exocortex lab run --instance %i"
    assert dict(units["exocortex-lab-blind@"])["Exec"] == "exocortex lab blind --instance %i"
    assert dict(units["exocortex-lab-work"])["Exec"] == "exocortex lab work"
    for name in ("exocortex-lab-run@", "exocortex-lab-blind@"):
        container = dict(units[name])["ContainerName"]
        assert container.endswith("-%i")
    readme = (LAB / "README.md").read_text(encoding="utf-8")
    runs = re.findall(r"exocortex-lab-run@([a-z0-9][\w.-]*)", readme)
    blinds = re.findall(r"exocortex-lab-blind@([a-z0-9][\w.-]*)", readme)
    assert runs and blinds
    for inst in runs:
        parse_run_instance(inst)
        # a container name allows letters, digits, "_", "." and "-" only
        assert re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", f"exocortex-lab-run-{inst}")
    for inst in blinds:
        parse_blind_instance(inst)
    args = build_parser().parse_args(["run", "--instance", "toy-length_tuning_queue"])
    assert args.instance == "toy-length_tuning_queue"


def test_run_instance_names():
    from exocortex.lab.cli import parse_run_instance as parse

    assert parse("toy-length_tuning") == {"experiment": "toy-length", "sample": "tuning", "configs": None,
                                          "queue_only": False}
    assert parse("intent-vs-fact_tuning_qwen36-baseline.qwen36-mode_queue") == {
        "experiment": "intent-vs-fact", "sample": "tuning", "configs": ["qwen36-baseline", "qwen36-mode"],
        "queue_only": True}
    for bad in ("toy-length", "toy-length:tuning", "a_b_c_d_e", "Toy_tuning", "x_y_bad!", "_tuning"):
        with pytest.raises(ValueError):
            parse(bad)


def test_blind_instance_names():
    from exocortex.lab.cli import parse_blind_instance as parse

    assert parse("draw_toy-length_blind-desk") == {"action": "draw", "experiment": "toy-length", "name": "blind-desk"}
    assert parse("draw_x_s_run-2026-09-30-1.run-2026-09-30-2")["runs"] == "run-2026-09-30-1,run-2026-09-30-2"
    assert parse("import_x_s_page-by-hand")["page_name"] == "page-by-hand"
    assert parse("summary_x_s_owner")["rater"] == "owner"
    for bad in ("rate_x_s", "draw_x", "draw_x_s_a_b", "import_x_s_../up"):
        with pytest.raises(ValueError):
            parse(bad)


def test_the_nightly_queue_timer_ships_disabled():
    timer = LAB / "systemd" / "exocortex-lab-work.timer"
    assert timer.exists()
    readme = (LAB / "README.md").read_text(encoding="utf-8")
    install = readme.split("## Install", 1)[1].split("\n## ", 1)[0]
    assert "exocortex-lab-work.timer" not in install
    assert (LAB / "blind.env.example").exists() and "blind.env" in install


def test_blind_import_finds_the_page_in_the_documents_tree(tmp_path):
    from exocortex.lab.cli import _blind_page

    assert _blind_page(tmp_path, "toy-length", "blind-desk") is None
    en = tmp_path / "en" / "experiments" / "toy-length" / "blind-desk.md"
    en.parent.mkdir(parents=True)
    en.write_text("x", encoding="utf-8")
    assert _blind_page(tmp_path, "toy-length", "blind-desk") == en
    pl = tmp_path / "pl" / "experiments" / "toy-length" / "blind-desk.md"
    pl.parent.mkdir(parents=True)
    pl.write_text("x", encoding="utf-8")
    assert _blind_page(tmp_path, "toy-length", "blind-desk") == pl
