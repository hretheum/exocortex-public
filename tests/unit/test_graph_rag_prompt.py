# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31.8.2 — GraphRAG system prompt loader (Jinja2 + YAML config)."""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest

# graph_rag.py reads TENANT_ID at import time.
os.environ.setdefault("TENANT_ID", "test-tenant")


# ---------------------------------------------------------------------------
# Fixture: every test gets a fresh module + a fake `yaml` providing safe_load.
# ---------------------------------------------------------------------------

def _install_yaml(monkeypatch, payload: dict | None):
    fake_yaml = types.ModuleType("yaml")
    fake_yaml.safe_load = lambda text: payload  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "yaml", fake_yaml)


@pytest.fixture
def grprompt(monkeypatch):
    """Import a fresh exocortex.graph_rag_prompt module per-test.

    Resets caches/warnings so tests do not bleed into each other.
    """
    # Drop the cached module so each test re-executes top-level state.
    sys.modules.pop("exocortex.graph_rag_prompt", None)
    from exocortex import graph_rag_prompt as mod
    mod.reset()
    return mod


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------

def test_template_file_exists():
    """The Jinja2 template ships inside the package."""
    path = (
        Path(__file__).resolve().parent.parent.parent
        / "exocortex" / "prompts" / "graph_rag" / "system_prompt.md.j2"
    )
    assert path.exists(), f"Expected template at {path}"
    text = path.read_text(encoding="utf-8")
    assert "{{ user_role }}" in text
    assert "{{ language }}" in text


def _point_config_at(monkeypatch, grprompt, tmp_path):
    """Create a real (empty) config file so the loader's exists()-check passes;
    the YAML payload is supplied via the fake `yaml.safe_load` from the caller."""
    cfg = tmp_path / "graph_rag.yaml"
    cfg.write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(grprompt, "_CONFIG_PATH", cfg)
    monkeypatch.setattr(
        grprompt, "_EXAMPLE_PATH", tmp_path / "graph_rag.example.yaml"
    )


def test_renders_user_role_into_prompt(grprompt, monkeypatch, tmp_path):
    _install_yaml(monkeypatch, {
        "user_role": "principal engineer",
        "clients": [],
        "language": "English",
        "citation_style": "[[slug]]",
    })
    _point_config_at(monkeypatch, grprompt, tmp_path)

    out = grprompt.build_system_prompt()
    assert "principal engineer" in out
    assert "English" in out
    # No client clause because clients == []
    assert "clients:" not in out.lower()


def test_renders_explicit_clients_list(grprompt, monkeypatch, tmp_path):
    _install_yaml(monkeypatch, {
        "user_role": "operator",
        "clients": ["Acme", "Globex", "Initech"],
        "language": "Polish",
        "citation_style": "wikilinks",
    })
    _point_config_at(monkeypatch, grprompt, tmp_path)

    out = grprompt.build_system_prompt()
    assert "Acme, Globex, Initech" in out
    assert "Polish" in out


def test_auto_clients_resolves_against_db(grprompt, monkeypatch, tmp_path):
    _install_yaml(monkeypatch, {
        "user_role": "operator",
        "clients": "auto",
        "clients_auto_top_n": 3,
        "language": "English",
        "citation_style": "[[slug]]",
    })
    _point_config_at(monkeypatch, grprompt, tmp_path)

    fake_db = types.ModuleType("exocortex.db")
    fake_db.query = lambda sql, top_n: [  # type: ignore[attr-defined]
        {"name": "Acme", "n": 30},
        {"name": "Globex", "n": 12},
        {"name": "Initech", "n": 5},
    ][:top_n]
    monkeypatch.setitem(sys.modules, "exocortex.db", fake_db)

    out = grprompt.build_system_prompt()
    assert "Acme, Globex, Initech" in out


def test_auto_clients_swallows_db_errors(grprompt, monkeypatch, tmp_path):
    _install_yaml(monkeypatch, {
        "user_role": "operator",
        "clients": "auto",
        "language": "English",
        "citation_style": "[[slug]]",
    })
    _point_config_at(monkeypatch, grprompt, tmp_path)

    fake_db = types.ModuleType("exocortex.db")
    def _boom(sql, top_n):
        raise RuntimeError("graph offline")
    fake_db.query = _boom  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "exocortex.db", fake_db)

    out = grprompt.build_system_prompt()
    # Prompt rendered without a client clause despite the DB failure.
    assert "operator" in out
    assert "Acme" not in out


def test_falls_back_to_example_when_yaml_missing(grprompt, monkeypatch, tmp_path):
    # No user config; example exists with a custom user_role.
    example = tmp_path / "graph_rag.example.yaml"
    example.write_text("noop", encoding="utf-8")
    _install_yaml(monkeypatch, {
        "user_role": "demo-user",
        "clients": [],
        "language": "English",
        "citation_style": "[[slug]]",
    })
    monkeypatch.setattr(grprompt, "_CONFIG_PATH", tmp_path / "graph_rag.yaml")
    monkeypatch.setattr(grprompt, "_EXAMPLE_PATH", example)

    out = grprompt.build_system_prompt()
    assert "demo-user" in out


def test_defaults_when_neither_file_exists(grprompt, monkeypatch, tmp_path):
    _install_yaml(monkeypatch, {})
    monkeypatch.setattr(grprompt, "_CONFIG_PATH", tmp_path / "missing.yaml")
    monkeypatch.setattr(grprompt, "_EXAMPLE_PATH", tmp_path / "missing.example.yaml")

    out = grprompt.build_system_prompt()
    # Built-in default ``user_role`` is "engineer".
    assert "engineer" in out


def test_build_system_prompt_is_cached(grprompt, monkeypatch, tmp_path):
    payload = {"user_role": "first", "clients": [], "language": "English",
               "citation_style": "[[slug]]"}
    _install_yaml(monkeypatch, payload)
    _point_config_at(monkeypatch, grprompt, tmp_path)

    a = grprompt.build_system_prompt()
    # Change the underlying yaml payload — without reset(), result should be cached.
    payload["user_role"] = "second"
    _install_yaml(monkeypatch, payload)
    b = grprompt.build_system_prompt()
    assert a == b
    assert "first" in a

    grprompt.reset()
    c = grprompt.build_system_prompt()
    assert "second" in c


def test_reset_clears_cache_and_warnings(grprompt):
    grprompt._warned_missing_config = True
    grprompt._cached_prompt = "stale"
    grprompt.reset()
    assert grprompt._cached_prompt is None
    assert grprompt._warned_missing_config is False


def test_unexpected_clients_value_coerces_to_empty(grprompt, monkeypatch, tmp_path):
    _install_yaml(monkeypatch, {
        "user_role": "operator",
        "clients": 12345,  # nonsense
        "language": "English",
        "citation_style": "[[slug]]",
    })
    _point_config_at(monkeypatch, grprompt, tmp_path)

    out = grprompt.build_system_prompt()
    assert "Acme" not in out  # no client clause rendered
    assert "operator" in out


def test_extra_instructions_appended(grprompt, monkeypatch, tmp_path):
    _install_yaml(monkeypatch, {
        "user_role": "operator",
        "clients": [],
        "language": "English",
        "citation_style": "[[slug]]",
        "extra_instructions": "Always include a one-line tl;dr first.",
    })
    _point_config_at(monkeypatch, grprompt, tmp_path)

    out = grprompt.build_system_prompt()
    assert "Always include a one-line tl;dr first." in out


# ---------------------------------------------------------------------------
# Integration with graph_rag module
# ---------------------------------------------------------------------------

def test_graph_rag_build_system_prompt_delegates(monkeypatch):
    """graph_rag.build_system_prompt() must defer to the loader."""
    # Patch the loader before importing graph_rag to avoid side-effects.
    fake = types.ModuleType("exocortex.graph_rag_prompt")
    fake.build_system_prompt = lambda: "stubbed-prompt"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "exocortex.graph_rag_prompt", fake)

    # graph_rag imports heavy deps (psycopg, dotenv) — stub via conftest auto-stub.
    sys.modules.pop("exocortex.graph_rag", None)
    from exocortex import graph_rag

    assert graph_rag.build_system_prompt() == "stubbed-prompt"


def test_graph_rag_no_hardcoded_pl_text():
    """The hardcoded Polish SYSTEM_PROMPT_TEXT was removed in F31.8.2."""
    src = (
        Path(__file__).resolve().parent.parent.parent
        / "exocortex" / "graph_rag.py"
    ).read_text(encoding="utf-8")
    assert "SYSTEM_PROMPT_TEXT" not in src, (
        "Hardcoded SYSTEM_PROMPT_TEXT must be replaced by the Jinja2 loader"
    )
    # Spot-check that the user-facing PL phrases are gone too.
    assert "Pisz po polsku" not in src
    assert "Pytanie użytkownika znajdziesz" not in src


def test_no_user_specific_names_in_prompt_pipeline():
    """Acceptance: no user-specific identifiers leak from graph_rag.py / template
    into the runtime prompt or its loader.

    The Apache 2.0 + Commons Clause license headers (F31.10.1) legitimately
    contain the copyright holder's name ("Eryk Orłowski") — those lines are
    metadata, never reach the LLM, and are stripped here before scanning.
    """
    root = Path(__file__).resolve().parent.parent.parent
    targets = [
        root / "exocortex" / "graph_rag.py",
        root / "exocortex" / "graph_rag_prompt.py",
        root / "exocortex" / "prompts" / "graph_rag" / "system_prompt.md.j2",
        root / "config" / "graph_rag.example.yaml",
    ]

    def _strip_license_header(src: str) -> str:
        # Drop the contiguous run of license-banner comment lines at the
        # top of the file before scanning, so the copyright holder's name
        # doesn't trip the "no user-specific names" rule.
        lines = src.splitlines(keepends=True)
        i = 0
        while i < len(lines) and lines[i].lstrip().startswith("#"):
            if (
                "Apache 2.0" in lines[i]
                or "Commons Clause" in lines[i]
                or "Eryk Orłowski" in lines[i]
                or "LICENSE for details" in lines[i]
            ):
                i += 1
                continue
            break
        return "".join(lines[i:])

    for p in targets:
        text = _strip_license_header(p.read_text(encoding="utf-8"))
        for forbidden in (
            "Alex",
            "Orłowski",
            "Orlowski",
            "example-corp",
            "prv-sync",
        ):
            assert forbidden not in text, f"{forbidden!r} leaked into {p}"
