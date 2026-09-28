# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F2.2: only listed sources get in, and every refusal is logged."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from exocortex import source_allowlist as sa

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def lab_list(tmp_path, monkeypatch):
    p = tmp_path / "sources.yaml"
    p.write_text(
        "sources:\n"
        "  - id: docs\n    source_type: vault-note\n    uri_prefixes: ['file:///vault/_source/dowody/']\n"
        "    basis: own\n    added_by: owner\n    reason: test\n"
        "  - id: arxiv\n    source_type: arxiv\n    domains: [arxiv.org]\n"
        "    basis: CC0 metadata\n    added_by: owner\n    reason: test\n"
    )
    monkeypatch.setenv("EXOCORTEX_SOURCE_ALLOWLIST", str(p))
    return p


def test_listed_sources_pass(lab_list):
    sa.require_capture("vault-note", "file:///vault/_source/dowody/pl/02-roadmap.md")
    sa.require_capture("arxiv", "https://arxiv.org/abs/2608.11050v1")
    sa.require_capture("arxiv", "https://export.arxiv.org/abs/2608.11050v1")
    sa.require_url("https://export.arxiv.org/api/query?id_list=2608.11050")


def test_unlisted_type_and_address_are_refused_and_logged(lab_list, caplog):
    caplog.set_level(logging.WARNING, logger="exocortex.source_allowlist")
    with pytest.raises(sa.SourceNotAllowed):
        sa.require_capture("gmail-thread", "gmail-thread://abc")
    with pytest.raises(sa.SourceNotAllowed):
        sa.require_capture("vault-note", "file:///vault/_source/work/notes.md")
    with pytest.raises(sa.SourceNotAllowed):
        sa.require_capture("arxiv", "https://evil-arxiv.org.example.com/abs/1")
    with pytest.raises(sa.SourceNotAllowed):
        sa.require_url("https://example.com/feed.xml")
    refusals = [r for r in caplog.records if "source_refused" in r.getMessage()]
    assert len(refusals) == 4


def test_no_allowlist_means_no_restriction(monkeypatch):
    monkeypatch.delenv("EXOCORTEX_SOURCE_ALLOWLIST", raising=False)
    sa.require_capture("gmail-thread", "gmail-thread://abc")
    sa.require_url("https://example.com/feed.xml")


def test_configured_but_missing_file_is_an_error(monkeypatch, tmp_path):
    monkeypatch.setenv("EXOCORTEX_SOURCE_ALLOWLIST", str(tmp_path / "nope.yaml"))
    with pytest.raises(FileNotFoundError):
        sa.require_url("https://arxiv.org/abs/1")


def test_entries_need_basis_and_reason(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text("sources:\n  - id: x\n    source_type: arxiv\n    domains: [arxiv.org]\n")
    with pytest.raises(ValueError):
        sa.Allowlist.load(p)


def test_repository_allowlist_is_valid():
    allow = sa.Allowlist.load(REPO / "lab" / "sources.yaml")
    assert allow.check("vault-note", "file:///vault/_source/dowody/pl/03-progress.md")[0]
    assert not allow.check("vault-note", "file:///vault/_source/work/x.md")[0]


def test_capture_api_refuses_with_403(lab_list, monkeypatch):
    fastapi = pytest.importorskip("fastapi")
    monkeypatch.setenv("CAPTURE_API_TOKEN", "t")
    monkeypatch.setenv("EXOCORTEX_VAULT_PATH", "/tmp")
    from exocortex import capture_api

    req = capture_api.CaptureRequest(source_type="vault-note", uri="file:///vault/_source/work/x.md")
    with pytest.raises(fastapi.HTTPException) as exc:
        capture_api._do_capture(None, req)  # refused before the connection is used
    assert exc.value.status_code == 403
