import json
import subprocess
from pathlib import Path

import pytest

from tools.leakgate.denylist import build
from tools.publisher.core import Settings, publish

DOC = """---
id: {id}
lang: {lang}
counterpart: ../{other}/{name}
status: todo
---

# {title}

{body}
"""


def pair(root: Path, name: str, pl_body: str, en_body: str) -> None:
    for lang, other, title, body in (("pl", "en", "Tytuł", pl_body), ("en", "pl", "Title", en_body)):
        p = root / lang / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(DOC.format(id=name[:-3], lang=lang, other=other, name=name, title=title, body=body), encoding="utf-8")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


@pytest.fixture()
def env(tmp_path, key):
    deny = tmp_path / "deny.yaml"
    deny.write_text('version: 1\nentries:\n  - {term: "Vexalor", tier: block}\n', encoding="utf-8")
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
