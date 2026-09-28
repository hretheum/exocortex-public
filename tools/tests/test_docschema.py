from pathlib import Path

import pytest

from tools.docschema.core import validate_text, validate_tree

TASK = """---
id: F9.1
phase: F9
lang: en
counterpart: ../../../pl/roadmap/F9/F9.1-x.md
status: todo
depends_on: [F8]
estimate: 4h
owner: agent
provenance: ai_authored
provenance_metadata: {agent: "x", date: 2026-09-28, human_validated: false}
---

# F9.1
"""

GATE = """---
type: gate_decision
lang: en
counterpart: ../../pl/experiments/demo/gate-g1.md
hypothesis: demo
hypothesis_version: 1
gate: G1
decision: GO
date: 2026-09-28
approved_by: [owner]
return_condition: null
result_ids: [r1]
human_validated: true
---
"""

REL_TASK = "en/roadmap/F9/F9.1-x.md"
REL_GATE = "en/experiments/demo/gate-g1.md"


def test_valid_files_pass():
    assert validate_text(REL_TASK, TASK) == []
    assert validate_text(REL_GATE, GATE) == []


def test_missing_field():
    [err] = validate_text(REL_TASK, TASK.replace("status: todo\n", ""))
    assert err.field == "status" and "missing" in err.message


def test_wrong_value():
    [err] = validate_text(REL_GATE, GATE.replace("decision: GO", "decision: MAYBE"))
    assert err.field == "decision" and "GO" in err.message and "MAYBE" in err.message


def test_unknown_field():
    [err] = validate_text(REL_GATE, GATE.replace("gate: G1", "gate: G1\ngtae: G2"))
    assert "gtae" in err.field and "unknown field" in err.message


def test_files_without_schema_are_skipped():
    assert validate_text("en/01-cycle.md", "---\nid: cycle\n---\n") == []


def test_repository_documents_pass():
    root = Path(__file__).resolve().parents[2] / "dowody"
    if not root.is_dir():
        pytest.skip("dowody/ not present in this checkout")
    checked, errors = validate_tree(root)
    assert checked > 0 and not errors, [str(e) for e in errors]
