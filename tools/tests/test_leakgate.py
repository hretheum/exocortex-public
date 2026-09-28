import argparse
import csv
import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

from tools.leakgate import normalize, selftest
from tools.leakgate.__main__ import main
from tools.leakgate.artifacts import scan_image
from tools.leakgate.denylist import Denylist, KeyError_, build, key_id
from tools.leakgate.pii import detect
from tools.leakgate.scan import Config, Scanner, exit_code

TERMS = ["Vexalor", "Kwarnel Dostry", "Żółmirka"]


@pytest.fixture()
def scanner(tmp_path, key):
    src = tmp_path / "deny.yaml"
    src.write_text(
        "version: 1\nentries:\n" + "".join(f"  - {{term: \"{t}\", tier: block}}\n" for t in TERMS),
        encoding="utf-8",
    )
    data = build(src, key)
    return Scanner(Denylist(data["hashes"], key), Config.load(), tmp_path)


def rules(findings):
    return {(f.rule, f.tier) for f in findings}


def test_fold_handles_case_diacritics_zero_width_and_homoglyphs():
    assert normalize.tokens("ŻÓŁ​mirka") == ["zolmirka"]
    assert normalize.tokens("Vеxаlor") == ["vexalor"]  # Cyrillic е and а


def test_term_forms_mark_generated_inflections():
    forms = normalize.term_forms("Vexalor")
    assert forms["vexalor"] is False
    assert forms["vexalorowi"] is True


@pytest.mark.parametrize(
    "text",
    [
        "Vexalor",
        "VEXALOR-owi",
        "vexalorem",
        "v3xal0r",
        "vexalor2026",
        "Kwarnel\nDostry",
        "kwarneldostry",
        "zolmirka",
        "%C5%BC%C3%B3%C5%82mirka",
        '{"a": "\\u017c\\u00f3\\u0142mirka"}',
    ],
)
def test_denylist_catches_variants(scanner, text):
    found = scanner.scan_text("t.md", text)
    assert any(f.rule == "denylist" and f.tier == "block" for f in found), text


def test_clean_text_passes(scanner):
    assert scanner.scan_text("t.md", "Retrieval quality improved on the tuning sample.\n") == []


def test_report_never_contains_matched_text(scanner, tmp_path, capsys, monkeypatch, key):
    f = tmp_path / "leak.md"
    f.write_text("owner: Vexalor\n", encoding="utf-8")
    hashes = tmp_path / "h.json"
    src = tmp_path / "deny.yaml"
    hashes.write_text(json.dumps(build(src, key)), encoding="utf-8")
    code = main(["--hashes", str(hashes), "--json", str(tmp_path / "r.json"), "scan", str(f)])
    out = capsys.readouterr()
    assert code == 1
    assert "vexalor" not in (out.out + out.err + (tmp_path / "r.json").read_text()).lower()


def test_key_mismatch_fails_closed(tmp_path, key):
    src = tmp_path / "deny.yaml"
    src.write_text("version: 1\nentries: []\n", encoding="utf-8")
    data = build(src, key)
    data["key_id"] = "000000000000"
    p = tmp_path / "h.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(KeyError_):
        Denylist.load(p, key)


def test_missing_key_exit_code(tmp_path, monkeypatch):
    monkeypatch.delenv("LEAKGATE_HMAC_KEY", raising=False)
    monkeypatch.delenv("LEAKGATE_HMAC_KEY_FILE", raising=False)
    assert main(["scan", str(tmp_path)]) == 2


def test_pii_detectors():
    import random

    cases = selftest.synthetic_pii(random.Random(1))
    text = "\n".join(cases.values()) + "\nJan Kowalski\n"
    found = {r for _, r, _, _ in detect(text, ["*@example.com"], [])}
    assert {"pii.email", "pii.phone", "pii.pesel", "pii.iban", "pii.person_name"} <= found


def test_pii_ignores_hex_and_allowlisted():
    text = "hash 0a1b2c44051401359dd\nauthor eof@offline.pl\nEryk Orłowski\n"
    found = detect(text, ["eof@offline.pl"], ["Eryk Orłowski"])
    assert found == []


def test_metadata_in_files(scanner):
    jpg = selftest._jpeg_with_exif("Vexalor")
    found = scanner.scan_bytes("a.jpg", jpg)
    assert ("meta.image_exif", "block") in rules(found)
    assert any(f.rule == "denylist" for f in found)
    pdf = selftest._pdf_with_author("Vexalor")
    assert ("meta.pdf_info", "block") in rules(scanner.scan_bytes("a.pdf", pdf))
    docx = selftest._docx_with_comment("Vexalor")
    found = scanner.scan_bytes("a.docx", docx)
    assert ("meta.office_comments", "block") in rules(found)
    assert any(f.rule == "denylist" for f in found)


def test_unknown_binary_is_rejected(scanner):
    found = scanner.scan_bytes("blob.bin", b"\x00\x01\x02\x03binary\x00")
    assert ("file.unknown_binary", "block") in rules(found)


def test_nested_archives(scanner):
    found = scanner.scan_bytes("pkg.tar.gz", selftest._targz_with("Vexalor"))
    assert any(f.rule == "denylist" for f in found)
    found = scanner.scan_bytes("pkg.whl", selftest._wheel_with("Kwarnel Dostry"))
    assert any(f.rule == "denylist" for f in found)


def test_image_layers_and_config(scanner, tmp_path):
    img = tmp_path / "img.tar"
    img.write_bytes(selftest._docker_archive("Vexalor", None))
    assert any(f.rule == "denylist" for f in scan_image(scanner, img))
    img.write_bytes(selftest._docker_archive(None, "Vexalor"))
    assert any(f.rule == "denylist" and f.path.endswith("#config") for f in scan_image(scanner, img))
    img.write_bytes(selftest._docker_archive(None, None))
    assert scan_image(scanner, img) == []


def test_image_include_prefix_limits_layer_scan(scanner, tmp_path):
    img = tmp_path / "img.tar"
    img.write_bytes(selftest._docker_archive("Vexalor", None))
    assert any(f.rule == "denylist" for f in scan_image(scanner, img, ("opt/app",)))
    assert scan_image(scanner, img, ("opt/other",)) == []
    img.write_bytes(selftest._docker_archive(None, "Vexalor"))
    assert any(f.path.endswith("#config") for f in scan_image(scanner, img, ("opt/other",)))


def test_compiled_files_accepted_only_in_images(scanner):
    elf = b"\x7fELF\x02\x01\x01" + b"\x00" * 40 + b"Vexalor\x00"
    assert ("file.unknown_binary", "block") in rules(scanner.scan_bytes("lib.so", elf))
    found = scanner.scan_bytes("lib.so", elf, compiled_ok=True)
    assert ("file.unknown_binary", "block") not in rules(found)
    assert any(f.rule == "denylist" for f in found)


def test_corpus_exemption_needs_manifest(scanner, tmp_path):
    corpus = tmp_path / "dowody" / "corpus" / "demo"
    (corpus / "texts").mkdir(parents=True)
    doc = corpus / "texts" / "doc1.md"
    doc.write_text("Strategia wspomina Vexalor jako spółkę skarbu państwa.\n", encoding="utf-8")
    assert exit_code(scanner.scan_path(doc)) == 1
    with (corpus / "manifest.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "sha256_file"])
        w.writerow(["doc1", hashlib.sha256(doc.read_bytes()).hexdigest()])
    assert exit_code(scanner.scan_path(doc)) == 0
    doc.write_text("Strategia wspomina Vexalor, zmieniony tekst.\n", encoding="utf-8")
    assert exit_code(scanner.scan_path(doc)) == 1


def _selftest_args(tmp_path):
    return argparse.Namespace(allowlist=None, lock_file=str(tmp_path / "LOCK"), results=str(tmp_path / "st.json"),
                              private_cases=None, hashes=None)


def test_selftest_passes(tmp_path):
    assert selftest.run_selftest(_selftest_args(tmp_path)) == 0
    report = json.loads((tmp_path / "st.json").read_text())
    assert report["total_cases"] >= 50 and report["missed"] == 0
    assert not (tmp_path / "LOCK").exists()


def test_selftest_fails_and_locks_when_normalisation_breaks(tmp_path, monkeypatch):
    import tools.leakgate.normalize as n

    monkeypatch.setattr(n, "fold", lambda text: text.lower())
    monkeypatch.setattr(n, "tokens", lambda text: n._TOKEN_RE.findall(text.lower()))
    import tools.leakgate.scan as s

    monkeypatch.setattr(s, "tokens", lambda text: n._TOKEN_RE.findall(text.lower()))
    assert selftest.run_selftest(_selftest_args(tmp_path)) == 1
    assert (tmp_path / "LOCK").exists()


def test_pyc_constants_are_scanned_not_raw_bytes(scanner, tmp_path):
    import py_compile

    src = tmp_path / "m.py"
    src.write_text('"""Docstring about Vexalor."""\nX = 1\n')
    pyc = tmp_path / "m.pyc"
    py_compile.compile(str(src), cfile=str(pyc))
    found = scanner.scan_bytes("m.pyc", pyc.read_bytes(), compiled_ok=True)
    assert any(f.rule == "denylist" for f in found)
    src.write_text('"""Nothing to see."""\nX = 1\n')
    py_compile.compile(str(src), cfile=str(pyc))
    assert scanner.scan_bytes("m.pyc", pyc.read_bytes(), compiled_ok=True) == []
