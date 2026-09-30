import json
import subprocess
from pathlib import Path

import pytest

from tools.leakgate.denylist import build
from tools.publisher.core import Settings, publish

DOC = """---
id: {id}
lang: {lang}
counterpart: {other}/{name}
status: todo
---

# {title}

{body}
"""


def pair(root: Path, name: str, pl_body: str, en_body: str) -> None:
    up = "../" * (name.count("/") + 1)
    for lang, other, title, body in (("pl", "en", "Tytuł", pl_body), ("en", "pl", "Title", en_body)):
        p = root / lang / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(DOC.format(id=name[:-3], lang=lang, other=up + other, name=name, title=title, body=body),
                     encoding="utf-8")


def card(root: Path, slug: str, pl_body: str = "Hipoteza: próg 3.", en_body: str = "Hypothesis: threshold 3.") -> None:
    pair(root, f"experiments/{slug}/hypothesis.md", pl_body, en_body)


def line(slug: str, version: int = 1) -> str:
    """A registry line as the lab writes it (exocortex/lab/hypotheses.py)."""
    return json.dumps({"slug": slug, "version": version, "sha256": "0" * 64, "algorithm": "prereg-v1",
                       "files": {lang: f"{lang}/experiments/{slug}/hypothesis.md" for lang in ("pl", "en")}},
                      sort_keys=True)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


@pytest.fixture()
def env(tmp_path, key):
    deny = tmp_path / "deny.yaml"
    deny.write_text('version: 1\nentries:\n  - {term: "Vexalor", tier: block}\n  - {term: "Quorvanne", tier: warn}\n',
                    encoding="utf-8")
    hashes = tmp_path / "hashes.json"
    hashes.write_text(json.dumps(build(deny, key)), encoding="utf-8")
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    repo = tmp_path / "repo"
    subprocess.run(["git", "clone", "-q", str(remote), str(repo)], check=True, capture_output=True)
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "t")
    (repo / "README.md").write_text("repo\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "init")
    git(repo, "push", "-q", "origin", "HEAD:main")
    src = tmp_path / "vault" / "dowody"
    src.mkdir(parents=True)
    s = Settings(source=src, repo=repo, lock_file=tmp_path / "gate.lock", hashes=hashes, push=True,
                 author="Publisher <publisher@example.com>")
    return s, remote


def test_clean_pair_is_published_and_pushed(env):
    s, remote = env
    pair(s.source, "note.md", "Próg to 3.", "The threshold is 3.")
    res = publish(s)
    assert res.status == "ok" and sorted(res.published) == ["en/note.md", "pl/note.md"] and res.pushed
    assert "Publish 2 document files" in git(remote, "log", "-1", "--format=%s")
    assert publish(s).status == "nothing"


def test_canary_holds_file_and_its_pair(env):
    s, _ = env
    pair(s.source, "ok.md", "Próg to 3.", "The threshold is 3.")
    pair(s.source, "bad.md", "Klient Vexalor.", "Client Vexalor.")
    res = publish(s)
    assert sorted(res.published) == ["en/ok.md", "pl/ok.md"]
    assert set(res.held) == {"pl/bad.md", "en/bad.md"}
    assert any(r.startswith("leakgate:") for r in res.held["pl/bad.md"])
    assert not (s.repo / "dowody" / "pl" / "bad.md").exists()


def test_parity_mismatch_is_held(env):
    s, _ = env
    pair(s.source, "n.md", "Próg to 3.", "The threshold is 4.")
    res = publish(s)
    assert res.status == "held-only"
    assert "paritycheck:numbers" in res.held["pl/n.md"]


def test_nothing_is_published_while_locked(env):
    s, _ = env
    pair(s.source, "note.md", "Próg to 3.", "The threshold is 3.")
    s.lock_file.write_text("locked by leakgate selftest")
    assert publish(s).status == "locked"
    assert not (s.repo / "dowody").exists()


def test_machine_translation_is_held(env):
    s, _ = env
    pair(s.source, "m.md", "Próg to 3.", "The threshold is 3.")
    p = s.source / "en" / "m.md"
    p.write_text(p.read_text().replace("status: todo", "status: todo\ntranslation: machine"))
    res = publish(s)
    assert "machine translation not reviewed" in res.held["en/m.md"]
    assert "pair partner held: en/m.md" in res.held["pl/m.md"]


def test_sparse_checkout_holds_only_the_documents(tmp_path, key):
    from tools.publisher.core import ensure_checkout

    work = tmp_path / "work"
    subprocess.run(["git", "init", "-q", "-b", "main", str(work)], check=True)
    git(work, "config", "user.email", "t@example.com")
    git(work, "config", "user.name", "t")
    (work / "engine").mkdir()
    (work / "engine" / "core.py").write_text("print('source code')\n")
    (work / "pyproject.toml").write_text("[project]\n")
    (work / "dowody" / "pl").mkdir(parents=True)
    (work / "dowody" / "pl" / "a.md").write_text("tekst\n")
    git(work, "add", "-A")
    git(work, "commit", "-qm", "init")
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(work), str(remote)], check=True)
    git(remote, "config", "uploadpack.allowFilter", "true")
    git(remote, "config", "uploadpack.allowAnySHA1InWant", "true")

    repo = tmp_path / "checkout"
    ensure_checkout(repo, remote.as_uri(), "main", "dowody")
    files = sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*") if p.is_file() and ".git" not in p.parts)
    assert files == ["dowody/pl/a.md"]
    # the engine file's content was never downloaded
    blob = git(work, "rev-parse", "HEAD:engine/core.py").strip()
    missing = subprocess.run(["git", "-C", str(repo), "cat-file", "-e", blob], capture_output=True,
                             env={"GIT_NO_LAZY_FETCH": "1", "PATH": "/usr/bin:/bin"})
    assert missing.returncode != 0
    # a second call resets to the remote without cloning again
    ensure_checkout(repo, remote.as_uri(), "main", "dowody")


# -- the lab's output folder ------------------------------------------------------

@pytest.fixture()
def lab_env(env, tmp_path):
    s, remote = env
    s.lab_source = tmp_path / "lab-out"
    s.lab_source.mkdir()
    return s, remote


def test_lab_owned_files_come_from_the_lab_folder_only(lab_env):
    s, _ = lab_env
    pair(s.lab_source, "generated/status.md", "Zadań: 3.", "Tasks: 3.")
    (s.lab_source / "prereg.jsonl").write_text(line("toy") + "\n")
    (s.lab_source / "data" / "toy").mkdir(parents=True)
    (s.lab_source / "data" / "toy" / "results.csv").write_text("item,value\na,1\n")
    card(s.source, "toy")
    pair(s.source, "generated/status.md", "Stara kopia 9.", "Old copy 9.")  # ignored: the lab owns the path
    (s.lab_source / "stray.md").write_text("not a lab path\n")              # ignored: not a lab path
    res = publish(s)
    assert sorted(res.published) == ["data/toy/results.csv", "en/experiments/toy/hypothesis.md",
                                     "en/generated/status.md", "pl/experiments/toy/hypothesis.md",
                                     "pl/generated/status.md", "prereg.jsonl"]
    assert "Zadań: 3." in (s.repo / "dowody/pl/generated/status.md").read_text()
    assert not (s.repo / "dowody/stray.md").exists()


def test_the_registry_may_only_grow(lab_env):
    s, _ = lab_env
    reg = s.lab_source / "prereg.jsonl"
    card(s.source, "a")
    card(s.source, "b")
    reg.write_text(line("a") + "\n")
    assert "prereg.jsonl" in publish(s).published
    reg.write_text(line("a") + "\n" + line("b") + "\n")
    assert publish(s).published == ["prereg.jsonl"]
    reg.write_text(line("a").replace("0" * 64, "1" * 64) + "\n" + line("b") + "\n")
    res = publish(s)
    assert res.status == "held-only" and "registry: published lines changed or removed" in res.held["prereg.jsonl"]
    reg.unlink()
    pair(s.lab_source, "generated/x.md", "Jeden 1.", "One 1.")  # the folder is not empty, so deletions count
    res = publish(s)
    assert "registry: may not be removed" in res.held["prereg.jsonl"]
    assert (s.repo / "dowody/prereg.jsonl").exists()


def test_an_empty_or_missing_lab_folder_deletes_nothing(lab_env):
    s, _ = lab_env
    pair(s.lab_source, "generated/status.md", "Zadań: 3.", "Tasks: 3.")
    publish(s)
    for rel in ("pl/generated/status.md", "en/generated/status.md"):
        (s.lab_source / rel).unlink()
    assert publish(s).status == "nothing"  # empty folder: probably not mounted
    s.lab_source = None
    assert publish(s).status == "nothing"
    assert (s.repo / "dowody/pl/generated/status.md").exists()


def test_a_page_the_lab_dropped_is_removed_while_the_folder_is_present(lab_env):
    s, _ = lab_env
    pair(s.lab_source, "generated/a.md", "A 1.", "A 1.")
    pair(s.lab_source, "generated/b.md", "B 2.", "B 2.")
    publish(s)
    for lang in ("pl", "en"):
        (s.lab_source / lang / "generated" / "b.md").unlink()
    res = publish(s)
    assert sorted(res.deleted) == ["en/generated/b.md", "pl/generated/b.md"]


def test_generated_pages_go_through_the_same_checks(lab_env):
    s, _ = lab_env
    pair(s.lab_source, "generated/bad.md", "Klient Vexalor.", "Client Vexalor.")
    res = publish(s)
    assert res.status == "held-only" and any(r.startswith("leakgate:") for r in res.held["pl/generated/bad.md"])


def test_a_page_marked_publish_false_stays_in_the_vault(env):
    s, _ = env
    pair(s.source, "note.md", "Próg to 3.", "The threshold is 3.")
    work = s.source / "pl" / "experiments" / "x" / "ocena-1.md"
    work.parent.mkdir(parents=True)
    work.write_text("---\ntype: blind_rating\nlang: pl\npublish: false\n---\n\n# Ocena\n\n- [ ] poprawne\n")
    res = publish(s)
    assert sorted(res.published) == ["en/note.md", "pl/note.md"] and not res.held
    work.write_text(work.read_text().replace("publish: false", "publish: true"))
    assert "pl/experiments/x/ocena-1.md" in publish(s).held  # now it is a document like any other: no pair



def test_an_applications_section_is_published_only_with_publish_true(env):
    """F8.1: a draft (publish: false) stays in the vault; the owner's publish: true releases the pair."""
    s, _ = env
    rel = "experiments/x/applications.md"
    for lang, other, text in (("pl", "en", "Próg to 3."), ("en", "pl", "The threshold is 3.")):
        path = s.source / lang / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"---\nid: x-applications\nlang: {lang}\ncounterpart: ../../../{other}/{rel}\n"
                        f"type: applications\npublish: false\nhuman_validated: false\n---\n\n# X\n\n{text}\n")
    res = publish(s)
    assert not any(p.endswith("applications.md") for p in res.published) and not res.held
    for lang in ("pl", "en"):
        path = s.source / lang / rel
        path.write_text(path.read_text().replace("publish: false", "publish: true")
                        .replace("human_validated: false", "human_validated: true"))
    res = publish(s)
    assert sorted(res.published) == ["en/" + rel, "pl/" + rel], (res.published, res.held)

# -- publication classes (F1.11) --------------------------------------------------

def test_a_dry_run_lists_the_class_of_every_file(lab_env):
    s, _ = lab_env
    pair(s.source, "roadmap/F9-toy.md", "Próg to 3.", "The threshold is 3.")
    pair(s.source, "experiments/x/overview.md", "Próg to 3.", "The threshold is 3.")
    pair(s.source, "misc/note.md", "Próg to 3.", "The threshold is 3.")
    pair(s.lab_source, "generated/status.md", "Zadań: 3.", "Tasks: 3.")
    (s.lab_source / "data" / "x").mkdir(parents=True)
    (s.lab_source / "data" / "x" / "results.csv").write_text("item,value\na,1\n")
    s.dry_run = True
    res = publish(s)
    both = lambda rel, cls: {f"pl/{rel}": cls, f"en/{rel}": cls}
    assert res.classes == {**both("roadmap/F9-toy.md", "docs"), **both("experiments/x/overview.md", "experiment"),
                           **both("misc/note.md", "unknown"), **both("generated/status.md", "generated"),
                           "data/x/results.csv": "open-data"}
    assert not (s.repo / "dowody").exists()
    # a dry run with nothing to publish still lists every file
    s.dry_run = False
    publish(s)
    s.dry_run = True
    res = publish(s)
    assert res.status == "nothing" and len(res.classes) == 9


def test_the_run_log_records_the_class_of_touched_files(env, tmp_path):
    from tools.publisher.core import log

    s, _ = env
    pair(s.source, "roadmap/F9-toy.md", "Próg to 3.", "The threshold is 3.")
    res = publish(s)
    log(res, tmp_path / "runs.jsonl")
    pair(s.source, "misc/note.md", "Próg to 3.", "The threshold is 3.")
    res = publish(s)
    log(res, tmp_path / "runs.jsonl")
    first, second = [json.loads(line) for line in (tmp_path / "runs.jsonl").read_text().splitlines()]
    assert first["classes"] == {"pl/roadmap/F9-toy.md": "docs", "en/roadmap/F9-toy.md": "docs"}
    assert second["classes"] == {"pl/misc/note.md": "unknown", "en/misc/note.md": "unknown"}


def test_a_file_of_the_unknown_class_raises_an_alarm(env, monkeypatch):
    import httpx

    from tools.publisher.core import notify

    sent = []
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    monkeypatch.setattr(httpx, "post", lambda url, json, timeout: sent.append(json["text"]))
    s, _ = env
    pair(s.source, "roadmap/F9-toy.md", "Próg to 3.", "The threshold is 3.")
    res = publish(s)
    assert not res.held and notify(res) is None and not sent  # documentation alone: nothing to report
    pair(s.source, "misc/note.md", "Próg to 3.", "The threshold is 3.")
    res = publish(s)
    assert sorted(res.published) == ["en/misc/note.md", "pl/misc/note.md"] and not res.held
    assert notify(res) == "telegram"
    assert "Alarm: 2 file(s) of the unknown publication class" in sent[0] and "- pl/misc/note.md" in sent[0]


# -- checks per class (F1.13) --------------------------------------------------------

def _similar_to_everything(monkeypatch):
    """simcheck stand-in that calls every text similar and records what it was asked about."""
    import httpx

    asked = []

    def post(url, json, timeout):
        asked.append(json["text"])
        return httpx.Response(200, json={"similar": True}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    return asked


def test_documentation_skips_the_semantic_comparison(env, monkeypatch):
    asked = _similar_to_everything(monkeypatch)
    s, _ = env
    s.simcheck_url = "http://simcheck.invalid"
    pair(s.source, "roadmap/F9-toy.md", "Dokumentacja: próg to 3.", "Documentation: the threshold is 3.")
    pair(s.source, "experiments/x/overview.md", "Eksperyment: próg to 3.", "Experiment: the threshold is 3.")
    res = publish(s)
    assert sorted(res.published) == ["en/roadmap/F9-toy.md", "pl/roadmap/F9-toy.md"]
    assert res.held["pl/experiments/x/overview.md"][0] == "simcheck:similar to private corpus"
    assert len(asked) == 2 and not any("Documentation" in t or "Dokumentacja" in t for t in asked)


@pytest.mark.parametrize("name, lab", [("roadmap/F9-toy.md", False), ("img/figure.md", False),
                                       ("experiments/x/overview.md", False), ("generated/status.md", True),
                                       ("misc/note.md", False)])
def test_a_canary_in_every_class_is_held(lab_env, name, lab):
    """Synthetic personal data from the self-test's generator, planted in each class."""
    import random

    from tools.leakgate.selftest import synthetic_pii
    from tools.publisher.classes import CHECKS, LITERAL_BLOCK, classify

    s, _ = lab_env
    cls = classify(f"pl/{name}", 100)
    if LITERAL_BLOCK not in CHECKS[cls]:
        pytest.skip(f"class {cls} is exempt from the literal scanner in tools/publisher/classes.py")
    pii = synthetic_pii(random.Random(7))
    pair(s.lab_source if lab else s.source, name, f"Kontakt: {pii['email']}, {pii['pesel']}.",
         f"Contact: {pii['email']}, {pii['pesel']}.")
    res = publish(s)
    assert res.status == "held-only"
    assert {"leakgate:pii.email", "leakgate:pii.pesel"} <= set(res.held[f"pl/{name}"])
    assert not (s.repo / "dowody" / "pl" / name).exists()


def test_scanner_warnings_hold_experiments_but_only_go_to_the_log_for_documentation(env, tmp_path):
    from tools.publisher.classes import CHECKS, DOCS, LITERAL_BLOCK
    from tools.publisher.core import log

    s, _ = env
    pair(s.source, "roadmap/F9-toy.md", "Rozmowa z Quorvanne, próg 3.", "A talk with Quorvanne, threshold 3.")
    pair(s.source, "experiments/x/overview.md", "Rozmowa z Quorvanne, próg 3.", "A talk with Quorvanne, threshold 3.")
    res = publish(s)
    assert sorted(res.published) == ["en/roadmap/F9-toy.md", "pl/roadmap/F9-toy.md"]
    assert res.held["pl/experiments/x/overview.md"][0] == "leakgate:denylist"
    if LITERAL_BLOCK not in CHECKS[DOCS]:
        assert not res.warnings  # documentation switched off from the scanner: nothing is scanned
        return
    assert res.warnings["pl/roadmap/F9-toy.md"] == ["leakgate:denylist"]
    log(res, tmp_path / "runs.jsonl")
    line = (tmp_path / "runs.jsonl").read_text()
    assert '"warnings": {"en/roadmap/F9-toy.md": ["leakgate:denylist"]' in line and "Quorvanne" not in line


def test_documentation_keeps_parity_schemas_language_and_the_translation_rule(env):
    from tools.publisher.classes import (
        CHECKS,
        DOCS,
        LANGUAGE,
        PARITY,
        SCHEMA,
        TRANSLATION,
    )
    from tools.tests.test_humanlint import MACHINE_EN

    s, _ = env
    pair(s.source, "roadmap/F9-parity.md", "Próg to 3.", "The threshold is 4.")
    pair(s.source, "roadmap/F9/F9.1-task.md", "Zadanie.", "A task.")  # a task file without the task fields
    pair(s.source, "roadmap/F9-machine.md", "Próg to 3.", "The threshold is 3.")
    p = s.source / "en" / "roadmap" / "F9-machine.md"
    p.write_text(p.read_text().replace("status: todo", "status: todo\ntranslation: machine"))
    pair(s.source, "templates/lint.md", "Szablon.", "A template.")
    (s.source / "en" / "templates" / "lint.md").write_text(MACHINE_EN.replace("lang: en", "lang: en\ncounterpart: "
                                                                                "../../pl/templates/lint.md"))
    res = publish(s)
    expected = {PARITY: ("pl/roadmap/F9-parity.md", "paritycheck:numbers"),
                SCHEMA: ("pl/roadmap/F9/F9.1-task.md", "docschema:"),
                TRANSLATION: ("en/roadmap/F9-machine.md", "machine translation not reviewed"),
                LANGUAGE: ("en/templates/lint.md", "humanlint:")}
    for check, (rel, reason) in expected.items():
        found = any(r.startswith(reason) for r in res.held.get(rel, []))
        assert found == (check in CHECKS[DOCS]), (check, rel, res.held.get(rel))


# -- units of publication (F1.12) ---------------------------------------------------

def _experiment(s, slug: str, card_pl: str = "Hipoteza: próg 3.", card_en: str = "Hypothesis: threshold 3.") -> None:
    """A whole experiment: dossier and card in the vault, data and a registry line from the lab."""
    pair(s.source, f"experiments/{slug}/overview.md", "Opis: próg 3.", "Overview: threshold 3.")
    for lang in ("pl", "en"):  # a dossier has a dossier status (lab-site/model.py)
        p = s.source / lang / "experiments" / slug / "overview.md"
        p.write_text(p.read_text().replace("status: todo", "status: planned"))
    card(s.source, slug, card_pl, card_en)
    (s.lab_source / "data" / slug).mkdir(parents=True, exist_ok=True)
    (s.lab_source / "data" / slug / "results.csv").write_text("item,value\na,1\n")
    with (s.lab_source / "prereg.jsonl").open("a") as fh:
        fh.write(line(slug) + "\n")


def _public(s) -> list[str]:
    root = s.repo / "dowody"
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()) if root.is_dir() else []


def _registry(s) -> list[str]:
    reg = s.repo / "dowody" / "prereg.jsonl"
    return reg.read_text().splitlines() if reg.exists() else []


def test_an_experiment_goes_out_whole_or_not_at_all(lab_env):
    """The data of one experiment pass and its card is held, so none of it goes out; another goes out."""
    s, remote = lab_env
    _experiment(s, "a", "Hipoteza od Vexalor.", "Hypothesis from Vexalor.")
    _experiment(s, "b")
    before = git(remote, "rev-list", "--count", "main")
    res = publish(s)
    assert res.status == "ok"
    assert sorted(res.published) == ["data/b/results.csv", "en/experiments/b/hypothesis.md",
                                     "en/experiments/b/overview.md", "pl/experiments/b/hypothesis.md",
                                     "pl/experiments/b/overview.md", "prereg.jsonl"]
    assert int(git(remote, "rev-list", "--count", "main")) == int(before) + 1  # one commit
    assert "leakgate:denylist" in res.held["pl/experiments/a/hypothesis.md"]
    assert res.held["data/a/results.csv"] == ["unit held: experiment a"]
    assert res.held["pl/experiments/a/overview.md"] == ["unit held: experiment a"]
    assert "line of a held with its experiment" in res.held["prereg.jsonl"]
    assert not [p for p in _public(s) if "/a/" in p]
    assert _registry(s) == [line("b")]


def test_the_registry_lists_lines_in_the_order_of_publication(lab_env):
    s, _ = lab_env
    _experiment(s, "a", "Hipoteza od Vexalor.", "Hypothesis from Vexalor.")
    _experiment(s, "b")
    publish(s)
    assert _registry(s) == [line("b")]
    card(s.source, "a")  # the card is fixed
    _experiment(s, "c")
    res = publish(s)
    assert not res.held and "prereg.jsonl" in res.published
    assert _registry(s) == [line("b"), line("a"), line("c")]
    source = set((s.lab_source / "prereg.jsonl").read_text().splitlines())
    assert all(ln in source for ln in _registry(s))  # every public line is in the source, unchanged
    assert publish(s).status == "nothing"  # a different order in the source is not a change


def test_an_incomplete_experiment_is_held(lab_env):
    s, _ = lab_env
    pair(s.source, "experiments/x/overview.md", "Opis 1.", "Overview 1.")
    (s.source / "en" / "experiments" / "x" / "overview.md").unlink()  # no English version
    (s.lab_source / "data" / "x").mkdir(parents=True)
    (s.lab_source / "data" / "x" / "results.csv").write_text("item,value\na,1\n")
    (s.lab_source / "data" / "y").mkdir(parents=True)
    (s.lab_source / "data" / "y" / "results.csv").write_text("item,value\na,1\n")
    (s.lab_source / "prereg.jsonl").write_text(line("y") + "\n")  # a registry line without its card
    res = publish(s)
    assert res.status == "held-only"
    assert "incomplete: en/experiments/x/overview.md missing" in res.held["data/x/results.csv"]
    assert "incomplete: en/experiments/x/overview.md missing" in res.held["pl/experiments/x/overview.md"]
    assert "incomplete: registry line of y v1 without its card (pl)" in res.held["data/y/results.csv"]
    assert "line of y held with its experiment" in res.held["prereg.jsonl"]
    assert _public(s) == []


def test_an_experiment_is_removed_as_a_whole(lab_env):
    s, _ = lab_env
    pair(s.source, "experiments/r/overview.md", "Opis 1.", "Overview 1.")
    (s.lab_source / "data" / "r").mkdir(parents=True)
    (s.lab_source / "data" / "r" / "results.csv").write_text("item,value\na,1\n")
    pair(s.lab_source, "generated/status.md", "Zadań: 3.", "Tasks: 3.")  # keeps the lab folder non-empty
    publish(s)
    for lang in ("pl", "en"):
        (s.source / lang / "experiments" / "r" / "overview.md").unlink()
    lab = s.lab_source
    s.lab_source = None  # the lab folder is not mounted: its data cannot be removed with the dossier
    res = publish(s)
    assert res.status == "held-only" and not res.deleted
    assert res.held["pl/experiments/r/overview.md"] == [
        "incomplete: removed from the vault while its data wait for the lab folder"]
    s.lab_source = lab
    (lab / "data" / "r" / "results.csv").unlink()
    res = publish(s)
    assert sorted(res.deleted) == ["data/r/results.csv", "en/experiments/r/overview.md",
                                   "pl/experiments/r/overview.md"]
    assert not [p for p in _public(s) if "/r/" in p]


def test_a_registered_experiment_cannot_lose_its_card(lab_env):
    s, _ = lab_env
    _experiment(s, "k")
    publish(s)
    for lang in ("pl", "en"):
        (s.source / lang / "experiments" / "k" / "hypothesis.md").unlink()
    res = publish(s)
    assert res.status == "held-only" and not res.deleted
    assert "incomplete: registry line of k v1 without its card (pl)" in res.held["pl/experiments/k/hypothesis.md"]
    assert (s.repo / "dowody/pl/experiments/k/hypothesis.md").exists()


def test_the_lab_site_builds_from_every_intermediate_state(lab_env, tmp_path):
    """The lab site reads only public files, so it has to build after every run."""
    import sys

    pytest.importorskip("markdown")
    root = Path(__file__).resolve().parents[2]
    s, _ = lab_env

    def build(n: int) -> None:
        docs = s.repo / "dowody"
        docs.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, str(root / "lab-site" / "build.py"), "--docs", str(docs),
                        "--out", str(tmp_path / f"site-{n}"), "--asof", "2026-09-29"],
                       check=True, capture_output=True, text=True)

    build(0)  # nothing published yet
    _experiment(s, "a", "Hipoteza od Vexalor.", "Hypothesis from Vexalor.")
    _experiment(s, "b")
    publish(s)
    build(1)  # one experiment whole, the other absent
    card(s.source, "a")
    publish(s)
    build(2)  # both
    for lang in ("pl", "en"):
        (s.source / lang / "experiments" / "b" / "overview.md").unlink()
    publish(s)
    build(3)  # a dossier removed while the card and the registry line stay
    assert (tmp_path / "site-3" / "en" / "hypotheses" / "a" / "index.html").exists()
