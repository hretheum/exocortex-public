# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""The public graph package (roadmap task F8.2) without a database: format,
determinism, and what verify catches."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("graph_package", ROOT / "lab" / "graph_package.py")
gp = importlib.util.module_from_spec(_spec)
sys.modules["graph_package"] = gp  # dataclasses look their module up while the class is built
_spec.loader.exec_module(gp)

RAW = "We show that retrieval “helps” — sometimes.  Large   models fail on long inputs, as Table 2 shows."
PAPER = "arxiv:2609.00001v1"
DOC = f"c1/{PAPER}/abstract"


def _package(extra_claim_doc: str | None = None, vector=(0.1, -0.2, 0.05, 0.0)) -> gp.Package:
    text = gp.collapse(RAW)
    doc = {"document_id": DOC, "corpus": "c1", "source": "arxiv-abstracts", "paper": PAPER, "kind": "abstract",
           "lang": "en", "uri": "https://arxiv.org/abs/2609.00001v1", "sha256": gp.sha256_text(text),
           "chars": len(text)}
    start, end = gp.locate('retrieval "helps" - sometimes', text)
    cid = "e1/run-2026-09-29-1/cfg/2609.00001/1"
    claim = {"claim_id": cid, "document_id": DOC, "experiment": "e1", "run_id": "run-2026-09-29-1", "config": "cfg",
             "model": "m", "variant": "baseline", "mode": "", "text": "Retrieval sometimes helps.",
             "proposition": True, "redundant": False, "usable": True}
    claims = [claim]
    quotes = [{"quote_id": cid + "/q", "claim_id": cid, "document_id": DOC, "start": start, "end": end,
               "text": text[start:end]}]
    edges = [{"source": cid, "target": DOC, "type": "derived_from", "weight": "1"}]
    if extra_claim_doc:
        claims.append({**claim, "claim_id": cid + "0", "document_id": extra_claim_doc})
    scale, pixels = gp.quantize(list(vector))
    return gp.Package(documents=[doc], claims=claims, quotes=quotes, edges=edges,
                      vectors=[{"document_id": DOC, "scale": scale, "pixels": pixels}],
                      corpora=[{"name": "c1", "path": "lab/corpora/c1/", "documents": 1}],
                      sources=[{"id": "arxiv-abstracts", "redistribution": {"corpus_abstract": "CC0 1.0"}}],
                      dimensions=len(vector))


def _corpora(tmp_path: Path, abstract: str = RAW) -> Path:
    folder = tmp_path / "corpora" / "c1"
    folder.mkdir(parents=True)
    (folder / "corpus.jsonl").write_text(json.dumps({"arxiv_id": "2609.00001", "version": 1, "abstract": abstract,
                                                     "summary_pl": "Streszczenie.", "findings_pl": ""}) + "\n")
    (folder / "manifest.csv").write_text("arxiv_id\n2609.00001\n")
    return tmp_path / "corpora"


# -- quotes ----------------------------------------------------------------------------

def test_locate_finds_the_span_the_extractor_matched():
    text = gp.collapse(RAW)
    start, end = gp.locate('RETRIEVAL "helps" - sometimes', text)
    assert text[start:end] == "retrieval “helps” — sometimes"
    start, end = gp.locate("large models fail", text)
    assert text[start:end] == "Large models fail"
    assert gp.locate("not in the text", text) is None
    assert gp.locate("   ", text) is None


def test_locate_maps_offsets_back_through_collapsed_whitespace():
    raw = "Alpha  beta  gamma."
    start, end = gp.locate("beta gamma", raw)
    assert raw[start:end] == "beta  gamma"


# -- vectors ---------------------------------------------------------------------------

def test_quantize_uses_the_full_range_and_is_reversible():
    vec = [0.03, -0.12, 0.0, 0.06]
    scale, pixels = gp.quantize(vec)
    assert [p - 128 for p in pixels] == [32, -127, 0, 64] and 0 not in pixels
    assert all(abs(a - b) <= float(scale) / 2 + 1e-15 for a, b in zip(gp.dequantize(scale, pixels), vec))
    assert gp.quantize(vec) == (scale, pixels)
    with pytest.raises(ValueError):
        gp.quantize([0.0, 0.0])


def test_parse_vector_reads_both_database_forms():
    assert gp.parse_vector("[0.5,-1,2e-3]") == [0.5, -1.0, 0.002]
    assert gp.parse_vector("{0.5,-1}") == [0.5, -1.0]


# -- determinism and the hash ----------------------------------------------------------

def test_two_builds_from_the_same_data_give_the_same_bytes(tmp_path):
    a, b = gp.render(_package()), gp.render(_package())
    assert a == b
    first = gp.place(a, tmp_path / "one")
    second = gp.place(b, tmp_path / "two")
    assert first["package_sha256"] == second["package_sha256"]
    for name in a:
        assert (tmp_path / "one" / first["version"] / name).read_bytes() == \
               (tmp_path / "two" / second["version"] / name).read_bytes()


def test_the_hash_is_sha256sum_of_the_files_and_names_the_folder(tmp_path):
    files = gp.render(_package())
    placed = gp.place(files, tmp_path / "out")
    folder = tmp_path / "out" / placed["version"]
    listing = "".join(f"{hashlib.sha256((folder / n).read_bytes()).hexdigest()}  {n}\n"
                      for n in sorted(files) if n != gp.MANIFEST)
    digest = hashlib.sha256(listing.encode()).hexdigest()
    assert digest == placed["package_sha256"] == json.loads((folder / gp.MANIFEST).read_text())["package_sha256"]
    assert placed["version"] == "v1-" + digest[:12]
    assert json.loads((tmp_path / "out" / "latest.json").read_text()) == {
        "format": gp.FORMAT, "version": placed["version"], "package_sha256": digest}
    assert gp.verify(folder) == []


def test_a_new_version_replaces_the_old_one_and_a_rebuild_changes_nothing(tmp_path):
    out, staging = tmp_path / "out", tmp_path / "staging"
    old = gp.place(gp.render(_package()), out, staging)
    new = gp.place(gp.render(_package(vector=(0.2, 0.1, -0.3, 0.4))), out, staging)
    assert new["removed"] == [old["version"]] and not (out / old["version"]).exists()
    assert sorted(p.name for p in out.iterdir()) == sorted(["README.md", "README.pl.md", "latest.json",
                                                            new["version"]])
    again = gp.place(gp.render(_package(vector=(0.2, 0.1, -0.3, 0.4))), out, staging)
    assert again["unchanged"] and again["package_sha256"] == new["package_sha256"]
    assert list(staging.iterdir()) == []


# -- what verify catches ---------------------------------------------------------------

def test_a_corrupted_file_is_detected(tmp_path):
    placed = gp.place(gp.render(_package()), tmp_path / "out")
    folder = tmp_path / "out" / placed["version"]
    data = bytearray((folder / "quotes.csv").read_bytes())
    data[-3] = ord("0") if data[-3] != ord("0") else ord("1")
    (folder / "quotes.csv").write_bytes(bytes(data))
    assert "quotes.csv: SHA-256 differs from manifest.json" in gp.verify(folder)


def test_a_corrupted_image_is_detected(tmp_path):
    placed = gp.place(gp.render(_package()), tmp_path / "out")
    folder = tmp_path / "out" / placed["version"]
    data = bytearray((folder / "vectors-0001.png").read_bytes())
    data[60] ^= 0x01  # a pixel inside the only IDAT chunk
    (folder / "vectors-0001.png").write_bytes(bytes(data))
    problems = gp.verify(folder)
    assert "vectors-0001.png: SHA-256 differs from manifest.json" in problems
    assert "vectors-0001.png: the CRC of a IDAT chunk is wrong" in problems


def test_the_images_are_plain_png_any_reader_opens(tmp_path):
    rows = [bytes([1, 2, 255, 128]), bytes([128, 129, 7, 200]), bytes([90, 91, 92, 93])]
    data = gp.write_png(rows, 4)
    assert gp.read_png(data) == (4, rows) and gp.write_png(rows, 4) == data
    image = pytest.importorskip("PIL.Image")
    if not isinstance(getattr(image, "__file__", None), str):  # tests/unit/conftest.py stubs missing modules
        pytest.skip("Pillow is not installed")
    (tmp_path / "v.png").write_bytes(data)
    with image.open(tmp_path / "v.png") as img:
        assert img.mode == "L" and img.size == (4, 3) and img.tobytes() == b"".join(rows)


def test_a_reference_to_a_missing_document_is_detected(tmp_path):
    placed = gp.place(gp.render(_package(extra_claim_doc="c1/arxiv:2609.99999v1/abstract")), tmp_path / "out")
    problems = gp.verify(tmp_path / "out" / placed["version"])
    assert problems == ["claims.csv: document_id c1/arxiv:2609.99999v1/abstract is not in documents.csv"]


def test_extra_missing_and_unsafe_files_are_detected(tmp_path):
    placed = gp.place(gp.render(_package()), tmp_path / "out")
    folder = tmp_path / "out" / placed["version"]
    (folder / "extra.csv").write_text("x\n")
    (folder / "edges.csv").unlink()
    manifest = json.loads((folder / gp.MANIFEST).read_text())
    manifest["files"].append({"path": "../outside.csv", "bytes": 1, "sha256": "0" * 64})
    (folder / gp.MANIFEST).write_text(json.dumps(manifest))
    problems = gp.verify(folder)
    assert "extra.csv: not listed in manifest.json" in problems
    assert "edges.csv: missing" in problems
    assert "manifest.json: '../outside.csv' is not a plain file name" in problems


def test_quotes_are_checked_against_the_corpus_text(tmp_path):
    placed = gp.place(gp.render(_package()), tmp_path / "out")
    folder = tmp_path / "out" / placed["version"]
    assert gp.verify(folder, _corpora(tmp_path)) == []
    problems = gp.verify(folder, _corpora(tmp_path / "changed", RAW.replace("helps", "hurts")))
    assert f"documents.csv: {DOC} differs from its corpus text" in problems
    assert any(p.startswith("quotes.csv:") and "not at its position" in p for p in problems)


def test_verify_needs_only_the_standard_library(tmp_path):
    placed = gp.place(gp.render(_package()), tmp_path / "out")
    # -S: no site-packages at all, so any third-party import would fail
    proc = subprocess.run([sys.executable, "-S", str(ROOT / "lab" / "graph_package.py"), "verify",
                           str(tmp_path / "out" / placed["version"]), "--corpora", str(_corpora(tmp_path))],
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert f"sound, package hash {placed['package_sha256']}" in proc.stdout


# -- parts ------------------------------------------------------------------------------

def _many(n: int, dims: int, edges: int = 0) -> gp.Package:
    """n documents with vectors of ``dims`` numbers, and ``edges`` relations between them."""
    docs, vectors, rel = [], [], []
    for i in range(n):
        doc_id = f"c1/arxiv:2609.{10000 + i}v1/abstract"
        docs.append({"document_id": doc_id, "corpus": "c1", "source": "arxiv-abstracts",
                     "paper": f"arxiv:2609.{10000 + i}v1", "kind": "abstract", "lang": "en",
                     "uri": f"https://arxiv.org/abs/2609.{10000 + i}v1", "sha256": "0" * 64, "chars": 100})
        scale, pixels = gp.quantize([((i + 1) * (j + 3)) % 17 - 8 + 0.5 for j in range(dims)])
        vectors.append({"document_id": doc_id, "scale": scale, "pixels": pixels})
    for k in range(edges):
        rel.append({"source": docs[k % n]["document_id"], "target": docs[(k + 1) % n]["document_id"],
                    "type": f"related_{k:03d}", "weight": "0.5"})
    return gp.Package(documents=docs, vectors=vectors, edges=rel, dimensions=dims,
                      corpora=[{"name": "c1", "path": "lab/corpora/c1/", "documents": n}])


def test_a_large_table_is_stored_in_parts_and_images_are_split_by_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(gp, "MAX_PART_BYTES", 1200)
    files = gp.render(_many(4, 200, edges=30))
    parts = sorted(n for n in files if n.startswith("edges"))
    assert len(parts) > 1 and parts == [f"edges-{i:04d}.csv" for i in range(1, len(parts) + 1)]
    assert all(len(files[n]) <= 1200 and files[n].startswith(b"source,target,type,weight\n") for n in parts)
    images = sorted(n for n in files if n.endswith(".png"))
    assert images == ["vectors-0001.png", "vectors-0002.png", "vectors-0003.png", "vectors-0004.png"]  # 4 rows of 201 bytes
    described = json.loads(files[gp.DATAPACKAGE])["exocortex"]
    assert described["tables"]["edges"] == parts and described["images"] == images
    placed = gp.place(files, tmp_path / "out")
    assert gp.verify(tmp_path / "out" / placed["version"]) == []
    assert gp.render(_many(4, 200, edges=30)) == files


def test_a_table_other_tables_refer_to_is_never_split(monkeypatch):
    monkeypatch.setattr(gp, "MAX_PART_BYTES", 400)
    with pytest.raises(ValueError, match="documents takes"):
        gp.render(_many(4, 8))


def test_a_missing_part_is_detected(tmp_path, monkeypatch):
    monkeypatch.setattr(gp, "MAX_PART_BYTES", 1200)
    placed = gp.place(gp.render(_many(4, 200, edges=30)), tmp_path / "out")
    folder = tmp_path / "out" / placed["version"]
    manifest = json.loads((folder / gp.MANIFEST).read_text())
    manifest["files"] = [f for f in manifest["files"] if f["path"] not in ("edges-0002.csv", "vectors-0002.png")]
    (folder / gp.MANIFEST).write_text(json.dumps(manifest))
    (folder / "edges-0002.csv").unlink()
    (folder / "vectors-0002.png").unlink()
    problems = gp.verify(folder)
    assert "manifest.json: the parts of edges are not numbered 0001 onwards" in problems
    assert "manifest.json: the images are not numbered 0001 onwards" in problems
    assert "datapackage.json: the files of the tables differ from manifest.json" in problems


def test_the_limit_leaves_room_under_the_gate(tmp_path):
    """The gate's semantic check refuses more than 5 MiB of JSON per file; a part is well below."""
    assert gp.MAX_PART_BYTES * 2 < 5 * 1024 * 1024


# -- what goes in ------------------------------------------------------------------------

def test_only_kinds_with_a_recorded_basis_count(tmp_path):
    sources = tmp_path / "sources.yaml"
    sources.write_text(
        "sources:\n"
        "  - {id: a, source_type: arxiv, domains: [arxiv.org], basis: b, added_by: o, reason: r,\n"
        "     redistribution: {corpus_abstract: 'CC0 1.0', corpus_summary: '  '}}\n"
        "  - {id: h, source_type: hf-model, domains: [huggingface.co], basis: b, added_by: o, reason: r}\n")
    assert gp.redistribution(sources) == {"a": {"corpus_abstract": "CC0 1.0"}}


def test_the_repository_records_a_basis_only_for_the_arxiv_corpus_texts():
    basis = gp.redistribution(ROOT / "lab" / "sources.yaml")
    assert set(basis) == {"arxiv-abstracts"}
    assert set(basis["arxiv-abstracts"]) == {"corpus_abstract", "corpus_summary"}


def test_the_readmes_pass_the_language_check(tmp_path):
    from tools.humanlint.core import run

    for name, text in gp.README.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    reports = run([tmp_path / name for name in gp.README])
    assert all(r.ok for r in reports), [(r.path, r.failures) for r in reports]


# -- the on-demand unit --------------------------------------------------------------------

def test_the_quadlet_unit_builds_on_demand_into_what_the_publisher_reads():
    from tools.publisher.classes import OPEN_DATA, classify, experiment_slug
    from tools.publisher.core import lab_owned

    quadlet = ROOT / "deploy" / "lab" / "quadlet"
    unit = (quadlet / "exocortex-lab-graph-package.container").read_text(encoding="utf-8")
    keys = [line.split("=", 1) for line in unit.splitlines() if "=" in line and not line.startswith("#")]
    conf = dict(keys)
    assert conf["Exec"] == ("python lab/graph_package.py build --out /lab-out/data/graph "
                            "--staging /lab-out/.graph-staging")
    assert conf["Image"] == "ghcr.io/hretheum/exocortex-public:main"
    assert conf["Type"] == "oneshot" and conf["Network"] == "exocortex-lab.network"
    assert [v for k, v in keys if k == "Secret"] == ["lab_database_url,type=env,target=DATABASE_URL"]
    assert [v for k, v in keys if k == "Volume"] == ["exocortex-lab-out.volume:/lab-out:z"]  # no vault, no models
    assert (quadlet / "exocortex-lab-out.volume").exists()
    assert not (ROOT / "deploy" / "lab" / "systemd" / "exocortex-lab-graph-package.timer").exists()
    # the publisher takes data/graph/ as one unit of publication and never reads the staging folder
    assert lab_owned("data/graph/v1-0123456789ab/documents.csv") and lab_owned("data/graph/latest.json")
    assert not lab_owned(".graph-staging/new-x/v1-0123456789ab/documents.csv")
    for rel in ("data/graph/v1-0123456789ab/vectors.csv", "data/graph/latest.json", "data/graph/README.pl.md"):
        assert classify(rel, 10) == OPEN_DATA and experiment_slug(rel) == "graph"
    readme = (ROOT / "deploy" / "lab" / "README.md").read_text(encoding="utf-8")
    assert "systemctl --user start exocortex-lab-graph-package.service" in readme
