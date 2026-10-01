# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Unit tests for F31.1.2 ``exocortex.pattern_detector``."""
from __future__ import annotations

import json
import math
from typing import Any
from unittest.mock import patch

import pytest

from exocortex import pattern_detector as pd

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tag_row(*values: str) -> dict[str, Any]:
    """Build a thought row in the spec shorthand shape: ``{tags: [...]}``."""
    return {"extracted_tags": {"tags": list(values)}}


def _axis_row(axis: str, *values: str) -> dict[str, Any]:
    """Build a thought row using the real axis shape."""
    return {
        "extracted_tags": {
            axis: [{"value": v, "confidence": 0.9, "source": "llm"} for v in values]
        }
    }


def _emb_row(vec: list[float]) -> dict[str, Any]:
    return {"embedding": "[" + ",".join(str(x) for x in vec) + "]"}


def _make_query_stub(window_rows: list[dict], baseline_rows: list[dict]):
    """Return a stub for ``exocortex.pattern_detector.query`` that returns
    ``window_rows`` for tag queries hitting the window, and ``baseline_rows``
    otherwise. Embedding queries return ``[]``.
    """
    def _stub(sql: str, *params: Any) -> list[dict]:
        is_emb = "embedding" in sql.lower() and "extracted_tags" not in sql.lower()
        if is_emb:
            return []
        # "INTERVAL '24 hours'" → window; "INTERVAL '720 hours'" (30d) → baseline.
        if "'24 hours'" in sql:
            return window_rows
        return baseline_rows
    return _stub


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_extract_terms_from_shorthand():
    assert pd._extract_terms({"tags": ["a", "b"]}) == ["a", "b"]


def test_extract_terms_from_axes():
    et = {
        "client": [{"value": "globex"}],
        "topic": [{"value": "ai"}, {"value": "ml"}],
    }
    out = pd._extract_terms(et)
    assert set(out) == {"globex", "ai", "ml"}


def test_extract_terms_handles_none_and_bad_shapes():
    assert pd._extract_terms(None) == []
    assert pd._extract_terms("not-a-dict") == []
    assert pd._extract_terms({"topic": "not-a-list"}) == []


def test_parse_vector_textual():
    assert pd._parse_vector("[1.0,2.0,3.0]") == [1.0, 2.0, 3.0]
    assert pd._parse_vector("[]") is None
    assert pd._parse_vector(None) is None
    assert pd._parse_vector("not-a-vector") is None


def test_centroid_and_cosine_distance():
    c = pd._centroid([[1.0, 0.0], [0.0, 1.0]])
    assert c == [0.5, 0.5]
    # Opposite vectors → distance 2.0; identical → 0.0; orthogonal → 1.0.
    assert math.isclose(pd._cosine_distance([1.0, 0.0], [1.0, 0.0]), 0.0, abs_tol=1e-9)
    assert math.isclose(pd._cosine_distance([1.0, 0.0], [0.0, 1.0]), 1.0, abs_tol=1e-9)
    assert math.isclose(pd._cosine_distance([1.0, 0.0], [-1.0, 0.0]), 2.0, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# detect_patterns — DB mocked
# ---------------------------------------------------------------------------


def test_empty_window_returns_empty_list():
    with patch.object(pd, "query", return_value=[]):
        assert pd.detect_patterns(24, 30) == []


def test_spike_detected():
    window = [_tag_row("AI") for _ in range(10)]
    # Baseline: tag "AI" appears once in 30d → expected per-24h = 1/30 ≈ 0.033,
    # floored to 1.0; spike_ratio = 10/1 = 10 ≥ 3.0.
    baseline = [_tag_row("AI")]
    with patch.object(pd, "query", side_effect=_make_query_stub(window, baseline)):
        out = pd.detect_patterns(24, 30)
    spikes = [r for r in out if r["term"] == "AI"]
    assert len(spikes) == 1
    assert spikes[0]["frequency_now"] == 10
    assert spikes[0]["spike_ratio"] >= 3.0
    assert spikes[0]["drift_score"] == 0.0


def test_no_spike_below_threshold():
    # 2 occurrences in window, 1 in entire 30d baseline → expected floor = 1.0,
    # ratio = 2.0 < 3.0 → no emit.
    window = [_tag_row("AI"), _tag_row("AI")]
    baseline = [_tag_row("AI")]
    with patch.object(pd, "query", side_effect=_make_query_stub(window, baseline)):
        out = pd.detect_patterns(24, 30)
    assert [r for r in out if r["term"] == "AI"] == []


def test_axis_shape_also_detected():
    """Real schema shape (axes) must be recognised, not just shorthand."""
    window = [_axis_row("topic", "remediation") for _ in range(8)]
    baseline = [_axis_row("topic", "remediation")]
    with patch.object(pd, "query", side_effect=_make_query_stub(window, baseline)):
        out = pd.detect_patterns(24, 30)
    assert any(r["term"] == "remediation" and r["spike_ratio"] >= 3.0 for r in out)


def test_embedding_drift_detected():
    # Window centroid ~ [1, 0]; baseline centroid ~ [0, 1] → distance = 1.0.
    window_embs = [_emb_row([1.0, 0.0]) for _ in range(3)]
    baseline_embs = [_emb_row([0.0, 1.0]) for _ in range(3)]

    def _stub(sql: str, *params: Any) -> list[dict]:
        is_emb = "embedding" in sql.lower() and "extracted_tags" not in sql.lower()
        if not is_emb:
            return []  # no tags → no spikes
        if "'24 hours'" in sql:
            return window_embs
        return baseline_embs

    with patch.object(pd, "query", side_effect=_stub):
        out = pd.detect_patterns(24, 30)
    drift = [r for r in out if r["term"] == "_embedding_drift"]
    assert len(drift) == 1
    assert drift[0]["drift_score"] >= 0.3
    assert drift[0]["frequency_now"] == 3
    assert drift[0]["frequency_baseline"] == 3.0


def test_embedding_drift_skipped_when_no_embeddings():
    """Graceful: no embedding rows → no drift emit, no crash."""
    with patch.object(pd, "query", return_value=[]):
        out = pd.detect_patterns(24, 30)
    assert [r for r in out if r["term"] == "_embedding_drift"] == []


def test_no_drift_below_threshold():
    # Nearly identical centroids → distance ~ 0, below 0.3 → no emit.
    window_embs = [_emb_row([1.0, 0.0, 0.0])]
    baseline_embs = [_emb_row([0.999, 0.001, 0.0])]

    def _stub(sql: str, *params: Any) -> list[dict]:
        is_emb = "embedding" in sql.lower() and "extracted_tags" not in sql.lower()
        if not is_emb:
            return []
        if "'24 hours'" in sql:
            return window_embs
        return baseline_embs

    with patch.object(pd, "query", side_effect=_stub):
        out = pd.detect_patterns(24, 30)
    assert [r for r in out if r["term"] == "_embedding_drift"] == []


# ---------------------------------------------------------------------------
# CLI smoke
# ---------------------------------------------------------------------------


def test_cli_outputs_valid_json(capsys, monkeypatch):
    monkeypatch.setattr(pd, "detect_patterns", lambda window, baseline: [{"term": "x"}])
    monkeypatch.setattr("sys.argv", ["pattern_detector", "--window", "24", "--baseline", "30"])
    pd.main()
    captured = capsys.readouterr().out.strip()
    parsed = json.loads(captured)
    assert parsed == [{"term": "x"}]


def test_cli_defaults(monkeypatch, capsys):
    seen: dict[str, int] = {}

    def _fake(window: int, baseline: int) -> list[dict]:
        seen["window"] = window
        seen["baseline"] = baseline
        return []

    monkeypatch.setattr(pd, "detect_patterns", _fake)
    monkeypatch.setattr("sys.argv", ["pattern_detector"])
    pd.main()
    assert seen == {"window": 24, "baseline": 30}
    assert capsys.readouterr().out.strip() == "[]"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
