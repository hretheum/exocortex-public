"""Testy klasyfikatora typu dokumentu (zadanie-9). Progi/wzorce/routing
z config/doctype_routing.yaml — testy pilnują semantyki reguł i tego, że
routing jest daną (zmiana przypisania bez zmiany kodu)."""
from __future__ import annotations

import copy

from scripts.doctype_classifier import classify, load_config

CFG = load_config()

PROSE = ("To jest zdanie prozy wystarczająco długie, żeby przekroczyć próg "
         "sześćdziesięciu znaków wymagany przez regułę.")


def _long_body(n_lines=10):
    return "\n".join([PROSE] * n_lines)


def test_template_marker_wins():
    c = classify("# Szablon {{title}}\n" + _long_body(), "work/globex/x.md", CFG)
    assert c.doc_type == "jalowy" and c.extraction_config is None


def test_short_doc_is_skeleton():
    c = classify("## X\nTBD", "work/globex/x.md", CFG)
    assert c.doc_type == "jalowy"


def test_short_with_tbd_is_skeleton():
    body = "## Plan\nTBD\n" + PROSE  # ~150-250 znaków, z TBD
    assert classify(body, "work/globex/x.md", CFG).doc_type == "jalowy"


def test_link_hub_without_prose_is_skeleton():
    body = "## Spis\n- [[A]]\n- [[B]]\n- [[C]]\n\n## Related\n- [[D]]\n" * 5
    assert len(body) < 1000
    c = classify(body, "work/globex/x.md", CFG)
    assert c.doc_type == "jalowy"
    assert "bez prozy" in c.reason


def test_long_doc_with_tbd_is_not_skeleton():
    body = _long_body(20) + "\nTBD"
    assert len(body) > 900
    assert classify(body, "work/globex/x.md", CFG).doc_type == "tezowy"


def test_howto_path_is_technical():
    c = classify(_long_body(), "_source/work/howto/x.md", CFG)
    assert c.doc_type == "techniczny"
    assert c.extraction_config == "terse-qwen36-chunk"


def test_archive_path_is_technical():
    assert classify(_long_body(), "a/_archiwum-2026-05/x.md", CFG).doc_type == "techniczny"


def test_default_is_thesis_routed_remote():
    c = classify(_long_body(), "_source/work/globex/CoE/01_STRATEGY/x.md", CFG)
    assert c.doc_type == "tezowy"
    assert c.extraction_config == "terse-gemini36flash-doc"


def test_routing_is_data_not_code():
    cfg = copy.deepcopy(CFG)
    cfg["routing"]["techniczny"] = "inny-config"
    c = classify(_long_body(), "_source/work/howto/x.md", cfg)
    assert c.doc_type == "techniczny"
    assert c.extraction_config == "inny-config"
