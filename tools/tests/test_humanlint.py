from pathlib import Path

import pytest

from tools.humanlint.core import load_config, load_patterns, run

PLAIN_EN = """---
lang: en
---

# Nightly run

The job starts at three in the morning and reads every note changed since the
previous run. Notes that fail to parse are moved to a quarantine folder and
listed in the log. After that the worker builds embeddings in batches of
sixty-four and writes them to Postgres. If the database is down, the run stops
and tries again an hour later; nothing is lost because the queue lives on disk.
""" + " ".join(
    f"{w} step writes a log line with the number of items it handled and how long it took."
    for w in ("Each", "Every", "One", "Another", "Any", "Some", "Our", "That", "Such", "Its") * 3
)

MACHINE_EN = """---
lang: en
---

# Why does this matter?

Here's the thing: it's worth noting that this robust, seamless pipeline doesn't
just move data, it's a testament to what we can unlock. Let's dive into the
landscape. Furthermore, the comprehensive design is crucial and pivotal —
moreover it will empower every team to elevate their work — in conclusion, a
true game-changer. 🚀
""" + " ".join(["It is a tapestry of seamless, robust ideas that delve deep."] * 20)


@pytest.fixture
def cfg():
    return load_config()


def write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / "en" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_plain_text_passes(tmp_path, cfg):
    [rep] = run([write(tmp_path, "plain.md", PLAIN_EN)], cfg, load_patterns())
    assert rep.ok, rep.failures


def test_machine_text_fails(tmp_path, cfg):
    [rep] = run([write(tmp_path, "machine.md", MACHINE_EN)], cfg, load_patterns())
    assert not rep.ok
    rules = " ".join(rep.failures)
    assert "hits_per_1000" in rules and "emoji" in rules and "question headings" in rules
    assert any(h.line == 5 for h in rep.hits)  # line numbers point into the file


def test_exception_needs_a_reason(tmp_path, cfg):
    text = MACHINE_EN.replace("lang: en", "lang: en\nhumanlint_exception: quotes the patterns as examples")
    write(tmp_path, "machine.md", text)
    [rep] = run([tmp_path], cfg, load_patterns())
    assert rep.failures and rep.ok and rep.exempt


def test_code_and_link_targets_are_ignored(tmp_path, cfg):
    text = PLAIN_EN + "\n```\nrobust seamless delve leverage\n```\nSee [notes](robust-seamless.md).\n"
    [rep] = run([write(tmp_path, "code.md", text)], cfg, load_patterns())
    assert not [h for h in rep.hits if h.rule == "pattern"]


def test_repository_documents_pass():
    root = Path(__file__).resolve().parents[2] / "dowody"
    if not root.is_dir():
        pytest.skip("dowody/ not present in this checkout")
    bad = [r.path for r in run([root]) if not r.ok]
    assert not bad
