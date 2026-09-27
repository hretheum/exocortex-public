# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31.4.2 — graph_fact_check tool: claim extraction + verdict pipeline."""
from __future__ import annotations

import os
import sys
import types
from uuid import uuid4

import pytest

os.environ.setdefault("TENANT_ID", "test-tenant")
os.environ.setdefault("EXOCORTEX_VAULT_PATH", "/tmp/test-vault")


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _install_llm_router(monkeypatch, claims):
    """Install a fake `llm_router` module returning a fixed claim list."""
    fake = types.ModuleType("llm_router")

    class _FakeUsage:
        provider = "fake"
        model = "fake"
        input_tokens = 0
        output_tokens = 0
        cache_creation_input_tokens = 0
        cache_read_input_tokens = 0
        cost_usd = 0.0
        latency_ms = 0
        use_case = "test"
        fallback_chain: list[str] = []

    def _call_tool(**kwargs):
        return {"claims": list(claims)}, _FakeUsage()

    fake.call_tool = _call_tool  # type: ignore[attr-defined]

    fake_exc = types.ModuleType("llm_router.exceptions")
    fake_exc.ProviderError = type("ProviderError", (Exception,), {})  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "llm_router", fake)
    monkeypatch.setitem(sys.modules, "llm_router.exceptions", fake_exc)


def _install_llm_router_raises(monkeypatch, exc):
    fake = types.ModuleType("llm_router")

    def _call_tool(**kwargs):
        raise exc

    fake.call_tool = _call_tool  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "llm_router", fake)


@pytest.fixture
def gfc(monkeypatch):
    """Fresh exocortex.graph_fact_check module per test, with patched deps."""
    # No-op llm_routing.initialize to avoid touching real config/.env.
    fake_routing = types.ModuleType("exocortex.llm_routing")
    fake_routing.initialize = lambda *a, **kw: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "exocortex.llm_routing", fake_routing)

    sys.modules.pop("exocortex.graph_fact_check", None)
    from exocortex import graph_fact_check as mod

    monkeypatch.setattr(mod, "get_tenant_id", lambda: "test-tenant")
    monkeypatch.setattr(mod, "get_embedding", lambda text: [0.0] * 1536)
    return mod


# ---------------------------------------------------------------------------
# Claim extraction edge cases
# ---------------------------------------------------------------------------

def test_empty_text_returns_empty_list(gfc, monkeypatch):
    monkeypatch.setattr(gfc, "query", lambda *a, **kw: [])
    assert gfc.graph_fact_check("") == []
    assert gfc.graph_fact_check("   ") == []


def test_llm_parse_failure_returns_empty(gfc, monkeypatch):
    _install_llm_router_raises(monkeypatch, RuntimeError("boom"))
    monkeypatch.setattr(gfc, "query", lambda *a, **kw: [])
    assert gfc.graph_fact_check("Some text") == []


def test_llm_returns_non_dict_returns_empty(gfc, monkeypatch):
    fake = types.ModuleType("llm_router")

    class _U:
        provider = model = use_case = ""
        input_tokens = output_tokens = 0
        cache_creation_input_tokens = cache_read_input_tokens = 0
        cost_usd = 0.0
        latency_ms = 0
        fallback_chain: list[str] = []

    fake.call_tool = lambda **kw: ("not a dict", _U())  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "llm_router", fake)
    monkeypatch.setattr(gfc, "query", lambda *a, **kw: [])
    assert gfc.graph_fact_check("hello") == []


def test_no_claims_extracted_returns_empty(gfc, monkeypatch):
    _install_llm_router(monkeypatch, [])
    monkeypatch.setattr(gfc, "query", lambda *a, **kw: [])
    assert gfc.graph_fact_check("Just an opinion, nothing factual.") == []


def test_claim_cap_max_10(gfc, monkeypatch):
    _install_llm_router(monkeypatch, [f"claim {i}" for i in range(25)])

    candidates_calls: list[tuple] = []

    def _vector_search(tenant_id, embedding, top_k):
        candidates_calls.append((tenant_id, top_k))
        return []

    monkeypatch.setattr(gfc, "vector_search", _vector_search)
    out = gfc.graph_fact_check("text")
    assert len(out) == 10
    # 10 vector searches (one per claim) + 0 edge lookups (no candidates)
    assert len(candidates_calls) == 10


# ---------------------------------------------------------------------------
# Verdict logic — 5 claims fixture
# ---------------------------------------------------------------------------

def _mk_thought(title: str) -> dict:
    return {
        "id": str(uuid4()),
        "metadata": {"title": title},
        "score": 0.9,
    }


def test_five_claims_mixed_verdicts(gfc, monkeypatch):
    # 2 supported, 2 contradicts, 1 no_evidence
    claims = [
        "supported claim A",
        "supported claim B",
        "contradicting claim C",
        "contradicting claim D",
        "isolated claim E",
    ]
    _install_llm_router(monkeypatch, claims)

    # Pre-allocate candidate UUIDs per claim so edge fixtures can target them.
    candidates_per_claim = {c: [_mk_thought(f"t-{c}-{i}") for i in range(3)] for c in claims}
    edges_per_candidate_id: dict[str, list[dict]] = {}

    def _add_edge(claim: str, edge_type: str, src_idx: int, dst_idx: int):
        src = candidates_per_claim[claim][src_idx]["id"]
        dst = candidates_per_claim[claim][dst_idx]["id"]
        e = {"src_id": src, "dst_id": dst, "edge_type": edge_type}
        edges_per_candidate_id.setdefault(src, []).append(e)
        edges_per_candidate_id.setdefault(dst, []).append(e)

    # Supported = ≥2 supports/decided_in edges (distinct node pairs)
    _add_edge("supported claim A", "supports", 0, 1)
    _add_edge("supported claim A", "decided_in", 0, 2)
    _add_edge("supported claim B", "supports", 0, 1)
    _add_edge("supported claim B", "supports", 1, 2)
    # Contradicts = at least one contradicts edge
    _add_edge("contradicting claim C", "contradicts", 0, 1)
    _add_edge("contradicting claim D", "contradicts", 0, 1)
    # "isolated claim E" gets candidates but no edges.

    # Map claim → candidates by tracking which call we are on.
    call_state = {"i": 0}

    def _vector_search(tenant_id, embedding, top_k):
        claim = claims[call_state["i"]]
        call_state["i"] += 1
        return candidates_per_claim[claim]

    monkeypatch.setattr(gfc, "vector_search", _vector_search)

    def _query(sql, *params):
        if "FROM edges" in sql:
            # params: tenant_id, edge_types_list, ids_list, ids_list
            ids = params[2]
            out: list[dict] = []
            seen: set[tuple] = set()
            for tid in ids:
                for e in edges_per_candidate_id.get(tid, []):
                    key = (e["src_id"], e["dst_id"], e["edge_type"])
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(e)
            return out
        return []

    monkeypatch.setattr(gfc, "query", _query)

    results = gfc.graph_fact_check("any text — claims come from mock")
    assert len(results) == 5
    verdicts = {r["claim"]: r["verdict"] for r in results}
    assert verdicts["supported claim A"] == "supported"
    assert verdicts["supported claim B"] == "supported"
    assert verdicts["contradicting claim C"] == "contradicts"
    assert verdicts["contradicting claim D"] == "contradicts"
    assert verdicts["isolated claim E"] == "no_evidence"

    # Sources on supported claims must be non-empty and titled.
    for r in results:
        if r["verdict"] == "supported":
            assert r["sources"]
            assert all("thought_id" in s and "title" in s for s in r["sources"])
        if r["verdict"] == "contradicts":
            assert r["sources"]
        if r["verdict"] == "no_evidence":
            assert r["evidence_edges"] == []
            assert r["sources"] == []


def test_single_support_edge_is_not_enough(gfc, monkeypatch):
    """One supports edge alone → no_evidence (threshold is 2)."""
    claim = "claim with one support"
    _install_llm_router(monkeypatch, [claim])
    cands = [_mk_thought("t1"), _mk_thought("t2")]
    edge = {"src_id": cands[0]["id"], "dst_id": cands[1]["id"], "edge_type": "supports"}

    monkeypatch.setattr(gfc, "vector_search", lambda tenant_id, embedding, top_k: cands)

    def _query(sql, *params):
        if "FROM edges" in sql:
            return [edge]
        return []

    monkeypatch.setattr(gfc, "query", _query)
    out = gfc.graph_fact_check("text")
    assert len(out) == 1
    assert out[0]["verdict"] == "no_evidence"


def test_contradicts_wins_over_supports(gfc, monkeypatch):
    """A single contradicts edge yields 'contradicts' even with many supports."""
    claim = "mixed evidence claim"
    _install_llm_router(monkeypatch, [claim])
    cands = [_mk_thought("t1"), _mk_thought("t2"), _mk_thought("t3")]
    edges = [
        {"src_id": cands[0]["id"], "dst_id": cands[1]["id"], "edge_type": "supports"},
        {"src_id": cands[0]["id"], "dst_id": cands[2]["id"], "edge_type": "supports"},
        {"src_id": cands[1]["id"], "dst_id": cands[2]["id"], "edge_type": "contradicts"},
    ]

    monkeypatch.setattr(gfc, "vector_search", lambda tenant_id, embedding, top_k: cands)
    monkeypatch.setattr(gfc, "query", lambda sql, *params: edges if "FROM edges" in sql else [])
    out = gfc.graph_fact_check("text")
    assert out[0]["verdict"] == "contradicts"


def test_no_candidates_returns_no_evidence(gfc, monkeypatch):
    """If the vector search yields nothing, verdict is no_evidence."""
    _install_llm_router(monkeypatch, ["lonely claim"])
    monkeypatch.setattr(gfc, "vector_search", lambda tenant_id, embedding, top_k: [])
    out = gfc.graph_fact_check("text")
    assert out[0]["verdict"] == "no_evidence"
    assert out[0]["sources"] == []


def test_embedding_failure_yields_no_evidence(gfc, monkeypatch):
    _install_llm_router(monkeypatch, ["claim"])
    monkeypatch.setattr(gfc, "get_embedding", lambda text: None)
    monkeypatch.setattr(gfc, "vector_search", lambda tenant_id, embedding, top_k: [])
    out = gfc.graph_fact_check("text")
    assert out == [{"claim": "claim", "verdict": "no_evidence",
                    "evidence_edges": [], "sources": []}]


def test_title_fallback_when_missing(gfc, monkeypatch):
    claim = "claim"
    _install_llm_router(monkeypatch, [claim])
    cands = [
        {"id": str(uuid4()), "metadata": None, "score": 0.9},
        {"id": str(uuid4()), "metadata": {}, "score": 0.9},
    ]
    edge = {"src_id": cands[0]["id"], "dst_id": cands[1]["id"],
            "edge_type": "contradicts"}

    monkeypatch.setattr(gfc, "vector_search", lambda tenant_id, embedding, top_k: cands)
    monkeypatch.setattr(gfc, "query", lambda sql, *params: [edge] if "FROM edges" in sql else [])
    out = gfc.graph_fact_check("text")
    assert out[0]["verdict"] == "contradicts"
    # Title falls back to first 8 chars of UUID when metadata is missing.
    assert len(out[0]["sources"][0]["title"]) >= 4


# Performance / cost expectation (informational only):
#   - Mocked end-to-end here runs in <100 ms; real Qwen on DeepInfra is
#     ~2-4 s for 5 claims at ~$0.001-0.003 per fact_check call. Not asserted.
