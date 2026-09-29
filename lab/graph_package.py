#!/usr/bin/env python3
# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Public graph package of the lab (roadmap task F8.2).

    python lab/graph_package.py build --out dowody/data/graph   # from the lab database
    python lab/graph_package.py verify dowody/data/graph/v1-...  # from the package files alone

A package is a folder named ``v1-`` plus the first 12 hex digits of its hash:

- documents.csv: documents of the public corpora (``lab/corpora/<name>/``)
  whose source records a basis for redistribution in ``lab/sources.yaml``.
  Their texts and titles are not repeated: they are in the corpus file of
  the repository, matched by id and SHA-256 (over the text with runs of
  whitespace collapsed to one space, as in the corpus manifest);
- claims.csv: claims the lab's experiments extracted from those documents,
  only those with a verbatim quote;
- quotes.csv: the quote of every claim, exactly as it appears in the
  document, with its position (start and end offsets in characters, end
  exclusive, into the collapsed text);
- edges.csv: relations between documents and claims, with a type and a weight;
- vectors-0001.png, vectors-0002.png, ...: the embeddings of the documents,
  one row of pixels per document in an 8-bit grayscale image, pixel =
  integer + 128, with one scale per vector; vectors.csv says which image
  and row belongs to which document. The images are stored uncompressed,
  so the same numbers always give the same bytes;
- no file is larger than MAX_PART_BYTES; a larger table is stored in parts,
  quotes-0001.csv, quotes-0002.csv and so on (only quotes and edges, which
  no other table refers to);
- datapackage.json: Frictionless Data descriptor, with keys and references;
- manifest.json: SHA-256 of every file and of the whole package.

The package hash is the SHA-256 of the lines ``<sha256>  <file>`` of all
files but the manifest, sorted by file name: the output of ``sha256sum`` on
those files. Beside the version folders, ``latest.json`` names the current
version and ``README.md`` / ``README.pl.md`` describe the package.

The build is byte-deterministic: the same data give the same bytes and so
the same hash. ``verify`` needs only Python 3.10+ and nothing installed. It
checks the checksums, that every reference points to a row of the package
and that the folder name matches the hash. With ``--corpora`` it also checks
every quote against the text of the corpus.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import shutil
import struct
import sys
import tempfile
import unicodedata
import zlib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORMAT = "exocortex-lab-graph/1"
PREFIX = "v1-"
MANIFEST, DATAPACKAGE, LATEST = "manifest.json", "datapackage.json", "latest.json"
EMBEDDING_MODEL = "bge-m3"  # the default of `exocortex lab corpus-graph`, which embeds the corpus nodes
NODE_KIND = {"corpus_abstract": "abstract", "corpus_summary": "summary"}

TABLES: dict[str, list[tuple[str, str, str]]] = {
    "documents": [
        ("document_id", "string", "<corpus>/<paper>/<kind>"),
        ("corpus", "string", "corpus folder in lab/corpora/"),
        ("source", "string", "source id in lab/sources.yaml"),
        ("paper", "string", "the source record, e.g. arxiv:2607.26722v2"),
        ("kind", "string", "abstract or summary"),
        ("lang", "string", "language of the text"),
        ("uri", "string", "address of the paper"),
        ("sha256", "string", "SHA-256 of the text with whitespace collapsed; the corpus manifest has the same"),
        ("chars", "integer", "length of that text in characters"),
    ],
    "claims": [
        ("claim_id", "string", "<experiment>/<run>/<configuration>/<item>/<position in the model's answer>"),
        ("document_id", "string", "document the claim was extracted from"),
        ("experiment", "string", "experiment slug"),
        ("run_id", "string", "run of the experiment"),
        ("config", "string", "configuration of the run"),
        ("model", "string", "model that extracted the claim"),
        ("variant", "string", "schema variant"),
        ("mode", "string", "mode the model gave, for the variant that asks for it"),
        ("text", "string", "the claim"),
        ("proposition", "boolean", "judged a claim by the lab's judge"),
        ("redundant", "boolean", "near duplicate of another claim of the same answer"),
        ("usable", "boolean", "counted as a claim by the experiment"),
    ],
    "quotes": [
        ("quote_id", "string", "<claim_id>/q"),
        ("claim_id", "string", "claim the quote supports"),
        ("document_id", "string", "document the quote is taken from"),
        ("start", "integer", "offset of the first character in the document text"),
        ("end", "integer", "offset after the last character (exclusive)"),
        ("text", "string", "the quote, exactly as it appears in the document"),
    ],
    "edges": [
        ("source", "string", "id of a document or a claim"),
        ("target", "string", "id of a document or a claim"),
        ("type", "string", "relation, e.g. derived_from"),
        ("weight", "number", "strength of the relation; 1 for structural relations"),
    ],
    "vectors": [
        ("document_id", "string", "document the embedding belongs to"),
        ("image", "string", "file of the image, e.g. vectors-0001.png"),
        ("row", "integer", "row of pixels in that image, from 0"),
        ("scale", "number", "value of one step: embedding ≈ scale × (pixel − 128)"),
    ],
}
KEYS = {"documents": "document_id", "claims": "claim_id", "quotes": "quote_id", "vectors": "document_id"}
# The gate's semantic check takes at most 5 MiB per file, as JSON; a part stays well below that.
MAX_PART_BYTES = 2 * 1024 * 1024
SPLITTABLE = {"quotes", "edges"}  # tables no other table refers to
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
IMAGE = re.compile(r"vectors-\d{4}\.png")
REFERENCES = [("claims", "document_id", "documents"), ("quotes", "claim_id", "claims"),
              ("quotes", "document_id", "documents"), ("vectors", "document_id", "documents")]


# -- text -----------------------------------------------------------------------------

def collapse(text: str) -> str:
    """Runs of whitespace as one space, no space at the ends: the text the corpus checksums cover."""
    return " ".join(text.split())


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_QUOTES = str.maketrans({"‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
                         "“": '"', "”": '"', "„": '"', "‟": '"', "«": '"', "»": '"',
                         "–": "-", "—": "-", "−": "-", "‐": "-", "‑": "-",
                         "\u00ad": None, "\u200b": None})


def normalise(text: str) -> str:
    """The extractor's comparison form (exocortex/lab/extractor.py): a quote counts if it matches in this form."""
    return " ".join(unicodedata.normalize("NFKC", text).translate(_QUOTES).casefold().split())


def locate(quote: str, text: str) -> tuple[int, int] | None:
    """The span of ``text`` the extractor matched ``quote`` to, or None.

    The first place where the normalised quote occurs in the normalised text,
    mapped back to offsets of ``text``; the span, normalised, must equal the
    normalised quote.
    """
    target = normalise(quote)
    if not target:
        return None
    chars: list[str] = []
    origin: list[int] = []
    space = True  # drop leading whitespace, fold every run into one space
    for i, ch in enumerate(text):
        for piece in unicodedata.normalize("NFKC", ch).translate(_QUOTES).casefold():
            if piece.isspace():
                if not space:
                    chars.append(" ")
                    origin.append(i)
                space = True
            else:
                chars.append(piece)
                origin.append(i)
                space = False
    at = "".join(chars).find(target)
    if at < 0:
        return None
    start, end = origin[at], origin[at + len(target) - 1] + 1
    return (start, end) if normalise(text[start:end]) == target else None


# -- vectors ----------------------------------------------------------------------------

def parse_vector(text: str) -> list[float]:
    """An embedding as the database prints it: [0.1,0.2] (pgvector) or {0.1,0.2} (an array)."""
    inner = text.strip()[1:-1]
    return [float(x) for x in inner.split(",")] if inner.strip() else []


def quantize(vector: list[float]) -> tuple[str, bytes]:
    """(scale, pixels) with one scale per vector: q = round(127 × v / max|v|), pixel = q + 128.

    Plain Python floats (IEEE 754 doubles) and round-half-to-even, so every
    machine gives the same bytes. The scale is printed with repr, the
    shortest text that reads back as the same double. A pixel is never 0.
    """
    top = max((abs(x) for x in vector), default=0.0)
    if not top:
        raise ValueError("zero vector")
    return repr(top / 127.0), bytes(round(127.0 * x / top) + 128 for x in vector)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = (sum(x * x for x in a) * sum(y * y for y in b)) ** 0.5
    return dot / norm if norm else 0.0


def dequantize(scale: str, pixels: bytes) -> list[float]:
    s = float(scale)
    return [s * (p - 128) for p in pixels]


def rows_per_image(dimensions: int) -> int:
    return max(1, (MAX_PART_BYTES - 1024) // (dimensions + 1))


def write_png(rows: list[bytes], width: int) -> bytes:
    """An 8-bit grayscale PNG with one image row per item, unfiltered and uncompressed.

    The zlib stream is written here as stored deflate blocks, so the bytes do
    not depend on the zlib library a machine has.
    """
    raw = b"".join(b"\x00" + r for r in rows)
    blocks = []
    for i in range(0, len(raw), 65535):
        part = raw[i:i + 65535]
        blocks.append(bytes([1 if i + 65535 >= len(raw) else 0]) + len(part).to_bytes(2, "little")
                      + (len(part) ^ 0xFFFF).to_bytes(2, "little") + part)
    stream = b"\x78\x01" + b"".join(blocks) + zlib.adler32(raw).to_bytes(4, "big")

    def chunk(kind: bytes, body: bytes) -> bytes:
        return len(body).to_bytes(4, "big") + kind + body + zlib.crc32(kind + body).to_bytes(4, "big")

    header = struct.pack(">IIBBBBB", width, len(rows), 8, 0, 0, 0, 0)
    return PNG_SIGNATURE + chunk(b"IHDR", header) + chunk(b"IDAT", stream) + chunk(b"IEND", b"")


def read_png(data: bytes) -> tuple[int, list[bytes]]:
    """(width, rows of pixels) of an image written by write_png; ValueError otherwise."""
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("not a PNG image")
    i, kinds, idat, width, height = 8, [], [], 0, 0
    while i + 12 <= len(data):
        length = int.from_bytes(data[i:i + 4], "big")
        kind, body = data[i + 4:i + 8], data[i + 8:i + 8 + length]
        if zlib.crc32(kind + body) != int.from_bytes(data[i + 8 + length:i + 12 + length], "big"):
            raise ValueError(f"the CRC of a {kind.decode('latin-1')} chunk is wrong")
        kinds.append(kind)
        if kind == b"IHDR":
            width, height, *rest = struct.unpack(">IIBBBBB", body)
            if rest != [8, 0, 0, 0, 0]:
                raise ValueError("not an 8-bit grayscale image without interlacing")
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
        i += 12 + length
    if kinds[:1] != [b"IHDR"] or kinds[-1:] != [b"IEND"] or set(kinds) - {b"IHDR", b"IDAT", b"IEND"}:
        raise ValueError("chunks other than IHDR, IDAT and IEND")
    try:
        raw = zlib.decompress(b"".join(idat))
    except zlib.error as exc:
        raise ValueError("pixel data cannot be read") from exc
    if len(raw) != height * (width + 1) or any(raw[r * (width + 1)] for r in range(height)):
        raise ValueError("pixel data of the wrong size, or rows with a filter")
    return width, [raw[r * (width + 1) + 1:(r + 1) * (width + 1)] for r in range(height)]


# -- writing ------------------------------------------------------------------------------

def _line(values: list) -> bytes:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerow(values)
    return buf.getvalue().encode("utf-8")


def _csv_parts(table: str, rows: list[dict]) -> list[bytes]:
    """The table as CSV, cut into parts of at most MAX_PART_BYTES, each with the header."""
    columns = [c for c, _, _ in TABLES[table]]
    header = _line(columns)
    parts, current, size = [], [header], len(header)
    for r in rows:
        line = _line(["" if r.get(c) is None else str(r[c]).lower() if isinstance(r[c], bool) else r[c]
                      for c in columns])
        if size + len(line) > MAX_PART_BYTES and len(current) > 1:
            parts.append(b"".join(current))
            current, size = [header], len(header)
        current.append(line)
        size += len(line)
    parts.append(b"".join(current))
    return parts


def part_names(table: str, n: int) -> list[str]:
    return [f"{table}.csv"] if n == 1 else [f"{table}-{i:04d}.csv" for i in range(1, n + 1)]


def _json(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def package_hash(files: dict[str, str]) -> str:
    """SHA-256 of the sha256sum listing of the files (name -> SHA-256), sorted by name."""
    return sha256_text("".join(f"{files[name]}  {name}\n" for name in sorted(files)))


@dataclass
class Package:
    documents: list[dict] = field(default_factory=list)
    claims: list[dict] = field(default_factory=list)
    quotes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    vectors: list[dict] = field(default_factory=list)
    corpora: list[dict] = field(default_factory=list)   # name, path and number of documents of each corpus
    sources: list[dict] = field(default_factory=list)   # id and the recorded basis for each kind taken from it
    dimensions: int = 0
    embedding_model: str = EMBEDDING_MODEL


def descriptor(pkg: Package, tables: dict[str, list[str]], images: list[str]) -> dict:
    """datapackage.json: Frictionless Data, with the keys and references verify checks.

    Every file is a resource; the parts of a split table share its schema,
    ``exocortex.tables`` lists the files of each table and
    ``exocortex.images`` the images of the embeddings.
    """
    resources = []
    for table, columns in TABLES.items():
        schema: dict = {"fields": [{"name": n, "type": t, "description": d} for n, t, d in columns]}
        if table in KEYS:
            schema["primaryKey"] = [KEYS[table]]
        refs = [{"fields": [col], "reference": {"resource": ref, "fields": [KEYS[ref]]}}
                for tab, col, ref in REFERENCES if tab == table]
        if refs:
            schema["foreignKeys"] = refs
        for name in tables[table]:
            resources.append({"name": name[:-4], "path": name, "profile": "tabular-data-resource",
                              "format": "csv", "mediatype": "text/csv", "encoding": "utf-8", "schema": schema})
    for name in images:
        resources.append({"name": name[:-4], "path": name, "format": "png", "mediatype": "image/png",
                          "description": "embeddings of the documents: one row of pixels per document, as listed "
                                         "in vectors.csv; 8-bit grayscale, embedding ≈ scale × (pixel − 128)"})
    return {
        "profile": "tabular-data-package",
        "name": "exocortex-lab-graph",
        "title": "Public graph package of the Exocortex lab",
        "description": ("Claims the lab extracted from public corpora, their verbatim quotes with positions, "
                        "relations and embeddings of the documents. The texts are in the corpus files of the "
                        "repository (lab/corpora/), matched by id and SHA-256."),
        "licenses": [{"name": "CC0-1.0", "path": "https://creativecommons.org/publicdomain/zero/1.0/",
                      "title": "arXiv metadata and abstracts are CC0; the claims, relations and vectors are the lab's"}],
        "exocortex": {
            "format": FORMAT,
            "corpora": pkg.corpora,
            "sources": pkg.sources,
            "counts": {t: len(getattr(pkg, t)) for t in TABLES},
            "embedding": {"model": pkg.embedding_model, "dimensions": pkg.dimensions,
                          "encoding": ("8 bits, one scale per vector: q = round(127 * v / max|v|), pixel = q + 128, "
                                       "v ≈ scale * (pixel - 128); PNG, 8-bit grayscale, unfiltered, uncompressed")},
            "hash": "SHA-256 of the lines '<sha256>  <file>' of every file but manifest.json, sorted by name",
            "tables": tables,
            "images": images,
        },
        "resources": resources,
    }


def render(pkg: Package) -> dict[str, bytes]:
    """File name -> bytes of one package, manifest included."""
    order = {"documents": "document_id", "claims": "claim_id", "quotes": "quote_id", "vectors": "document_id"}
    files: dict[str, bytes] = {}
    tables: dict[str, list[str]] = {}
    images: list[str] = []
    index: list[dict] = []
    vectors = sorted(pkg.vectors, key=lambda r: r["document_id"])
    per = rows_per_image(pkg.dimensions)
    for n, start in enumerate(range(0, len(vectors), per), start=1):
        chunk = vectors[start:start + per]
        name = f"vectors-{n:04d}.png"
        files[name] = write_png([r["pixels"] for r in chunk], pkg.dimensions)
        images.append(name)
        index += [{"document_id": r["document_id"], "image": name, "row": i, "scale": r["scale"]}
                  for i, r in enumerate(chunk)]
    for table in TABLES:
        rows = index if table == "vectors" else getattr(pkg, table)
        key = (lambda r: (r["source"], r["target"], r["type"])) if table == "edges" else (lambda r, k=order[table]: r[k])
        parts = _csv_parts(table, sorted(rows, key=key))
        if len(parts) > 1 and table not in SPLITTABLE:
            raise ValueError(f"{table} takes {sum(map(len, parts))} bytes, more than one file of {MAX_PART_BYTES}; "
                             "other tables refer to it, so the format has to change before it can be split")
        tables[table] = part_names(table, len(parts))
        files.update(zip(tables[table], parts))
    files[DATAPACKAGE] = _json(descriptor(pkg, tables, images))
    sums = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    digest = package_hash(sums)
    files[MANIFEST] = _json({"format": FORMAT, "package_sha256": digest,
                             "files": [{"path": n, "bytes": len(files[n]), "sha256": sums[n]} for n in sorted(sums)]})
    return files


def version_of(files: dict[str, bytes]) -> tuple[str, str]:
    digest = json.loads(files[MANIFEST])["package_sha256"]
    return PREFIX + digest[:12], digest


README = {
    "README.md": """# Public graph package of the Exocortex lab

Each folder `v1-<hash>` holds one version of the package: the claims the lab extracted from public corpora,
the verbatim quote of every claim with its position in the source document, the relations between documents
and claims, and the embeddings of the documents. `latest.json` names the current version. Older versions stay
in the history of the repository.

| File | What it holds |
|---|---|
| `documents.csv` | the documents: paper, kind of text (abstract or summary), address, SHA-256 and length of the text |
| `claims.csv` | claims with the experiment, run and model that extracted them |
| `quotes.csv` | the quote of every claim, exactly as in the document, with its start and end offsets |
| `edges.csv` | relations with a type and a weight, for example a claim `derived_from` a document |
| `vectors-0001.png`, … | the embeddings: every document is one row of pixels in an 8-bit grayscale image |
| `vectors.csv` | which image and row belongs to which document, and the scale of each vector |
| `datapackage.json` | description of the columns, keys and references (Frictionless Data) |
| `manifest.json` | SHA-256 of every file and the hash of the whole package |

An embedding is read from its row of pixels as `scale × (pixel − 128)` for every pixel of the row. The
images are stored uncompressed, so any PNG reader opens them and the same numbers always give the same bytes.
No file is larger than 2 MiB: a larger table of quotes or relations is stored in parts with the same
columns (`quotes-0001.csv`, `quotes-0002.csv`), and `datapackage.json` lists every file.

The texts and titles of the documents are not repeated here. They are in `lab/corpora/<corpus>/corpus.jsonl`
of this repository, with the same SHA-256, computed over the text with runs of whitespace collapsed to one space.
Offsets count characters of that text. Only corpora whose source records a basis for redistribution in
`lab/sources.yaml` are included.

## How to check the hash

The hash of a package is the SHA-256 of the output of `sha256sum` on its files other than `manifest.json`,
listed by name. Its first 12 characters are in the name of the folder:

    cd v1-<hash>
    LC_ALL=C ls | grep -vx manifest.json | xargs sha256sum | sha256sum

The full check needs only Python 3.10 or newer, run from the root of the repository. It checks every
checksum and every reference between the files, and with `--corpora` also every quote against the text
of its document:

    python lab/graph_package.py verify dowody/data/graph/v1-<hash> --corpora lab/corpora

The lab builds the package from its database with `python lab/graph_package.py build`. The same data always
give the same bytes, so a rebuild gives the same hash.
""",
    "README.pl.md": """# Publiczny pakiet grafu laboratorium Exocortex

Każdy folder `v1-<skrót>` to jedna wersja pakietu. Są w nim twierdzenia, które laboratorium wyciągnęło
z publicznych korpusów, dosłowny cytat każdego twierdzenia z pozycją w dokumencie źródłowym, powiązania
między dokumentami i twierdzeniami oraz osadzenia (ang. embeddings) dokumentów. Plik `latest.json` wskazuje
bieżącą wersję. Starsze wersje zostają w historii repozytorium.

| Plik | Zawartość |
|---|---|
| `documents.csv` | dokumenty: artykuł, rodzaj tekstu (abstrakt albo streszczenie), adres, SHA-256 i długość tekstu |
| `claims.csv` | twierdzenia z eksperymentem, przebiegiem i modelem, który je wyciągnął |
| `quotes.csv` | cytat każdego twierdzenia, dokładnie jak w dokumencie, z pozycją początku i końca |
| `edges.csv` | powiązania z typem i wagą, na przykład twierdzenie `derived_from` dokument |
| `vectors-0001.png`, … | osadzenia: każdy dokument to jeden wiersz pikseli w 8-bitowym obrazie w skali szarości |
| `vectors.csv` | który obraz i wiersz należy do którego dokumentu oraz skala każdego wektora |
| `datapackage.json` | opis kolumn, kluczy i odwołań (Frictionless Data) |
| `manifest.json` | SHA-256 każdego pliku i skrót całego pakietu |

Osadzenie odczytuje się z wiersza pikseli jako `skala × (piksel − 128)` dla każdego piksela wiersza. Obrazy
są zapisane bez kompresji, więc otworzy je każdy czytnik PNG, a te same liczby dają zawsze te same bajty.
Żaden plik nie jest większy niż 2 MiB: większa tabela cytatów albo powiązań jest zapisana w częściach o tych
samych kolumnach (`quotes-0001.csv`, `quotes-0002.csv`), a `datapackage.json` wymienia wszystkie pliki.

Teksty i tytuły dokumentów nie są tu powtórzone. Leżą w `lab/corpora/<korpus>/corpus.jsonl` tego
repozytorium, z tym samym SHA-256, liczonym po zastąpieniu każdego ciągu białych znaków jedną spacją. Pozycje liczą znaki tego
tekstu. Pakiet obejmuje tylko korpusy, których źródło ma w `lab/sources.yaml` zapisaną podstawę do dalszego
udostępniania.

## Jak sprawdzić skrót

Skrót pakietu to SHA-256 wyniku `sha256sum` dla jego plików poza `manifest.json`, wymienionych według nazwy.
Pierwsze 12 znaków skrótu jest w nazwie folderu:

    cd v1-<skrót>
    LC_ALL=C ls | grep -vx manifest.json | xargs sha256sum | sha256sum

Pełne sprawdzenie wymaga tylko Pythona 3.10 lub nowszego, uruchomionego w katalogu głównym repozytorium.
Sprawdza każdą sumę kontrolną i każde odwołanie między plikami, a z `--corpora` także każdy cytat
z tekstem jego dokumentu:

    python lab/graph_package.py verify dowody/data/graph/v1-<skrót> --corpora lab/corpora

Laboratorium buduje pakiet ze swojej bazy poleceniem `python lab/graph_package.py build`. Te same dane dają
zawsze te same bajty, więc ponowna budowa daje ten sam skrót.
""",
}


def _atomic_write(path: Path, data: bytes) -> bool:
    if path.exists() and path.read_bytes() == data:
        return False
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    return True


def place(files: dict[str, bytes], out: Path, staging: Path | None = None) -> dict:
    """Write one package into ``out``: its version folder, latest.json and the READMEs.

    With ``staging`` on the same file system as ``out`` (and outside what the
    publisher reads), a version folder appears and disappears at once: it is
    written there and renamed into place, and old versions are renamed out
    before they are deleted. Without it the manifest is written last, so a
    folder without one is incomplete. A sound folder of the same version is
    left as it is.
    """
    version, digest = version_of(files)
    out.mkdir(parents=True, exist_ok=True)
    if staging is not None:
        staging.mkdir(parents=True, exist_ok=True)
    atomic = staging is not None and _same_device(staging, out)
    target = out / version
    unchanged = target.is_dir() and not verify(target)
    if not unchanged:
        if target.exists():
            _remove(target, staging if atomic else None)
        if atomic:
            work = Path(tempfile.mkdtemp(prefix="new-", dir=staging))
            _write_files(work / version, files)
            os.replace(work / version, target)
            shutil.rmtree(work, ignore_errors=True)
        else:
            _write_files(target, files)
    _atomic_write(out / LATEST, _json({"format": FORMAT, "version": version, "package_sha256": digest}))
    for name, text in README.items():
        _atomic_write(out / name, text.encode("utf-8"))
    removed = []
    for old in sorted(p for p in out.iterdir() if p.is_dir() and p.name.startswith(PREFIX) and p.name != version):
        try:
            ours = json.loads((old / MANIFEST).read_text(encoding="utf-8")).get("format") == FORMAT
        except (OSError, ValueError):
            ours = False
        if ours:
            _remove(old, staging if atomic else None)
            removed.append(old.name)
    return {"version": version, "package_sha256": digest, "unchanged": unchanged, "removed": removed}


def _write_files(folder: Path, files: dict[str, bytes]) -> None:
    folder.mkdir(parents=True)
    for name in sorted(files, key=lambda n: (n == MANIFEST, n)):  # the manifest last
        (folder / name).write_bytes(files[name])


def _remove(folder: Path, staging: Path | None) -> None:
    """Delete a version folder; with ``staging`` it first leaves ``out`` in one rename."""
    if staging is not None:
        work = Path(tempfile.mkdtemp(prefix="old-", dir=staging))
        os.replace(folder, work / folder.name)
        folder = work
    shutil.rmtree(folder, ignore_errors=True)


def _same_device(a: Path, b: Path) -> bool:
    try:
        return a.stat().st_dev == b.stat().st_dev
    except OSError:
        return False


# -- verification (standard library only) -----------------------------------------------

def _rows(data: bytes) -> tuple[list[str], list[dict]]:
    reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""))
    return list(reader.fieldnames or []), list(reader)


def corpus_texts(corpora: Path) -> dict[str, str]:
    """document_id -> collapsed text, from the corpus files of the repository."""
    out = {}
    for path in sorted(corpora.glob("*/corpus.jsonl")):
        name = path.parent.name
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                paper = f"arxiv:{r['arxiv_id']}v{r['version']}"
                out[f"{name}/{paper}/abstract"] = collapse(r.get("abstract") or "")
                summary = collapse((r.get("summary_pl") or "") + "\n" + (r.get("findings_pl") or ""))
                out[f"{name}/{paper}/summary"] = summary
    return out


def verify(folder: Path, corpora: Path | None = None) -> list[str]:
    """Problems of one package folder; an empty list means it is sound."""
    problems: list[str] = []
    try:
        manifest = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"{MANIFEST}: cannot be read ({type(exc).__name__})"]
    if manifest.get("format") != FORMAT:
        problems.append(f"{MANIFEST}: format {manifest.get('format')!r}, expected {FORMAT!r}")
    listed = {f["path"]: f for f in manifest.get("files", []) if isinstance(f, dict) and isinstance(f.get("path"), str)}
    for name in sorted(listed):
        if name != Path(name).name or name.startswith("."):
            problems.append(f"{MANIFEST}: {name!r} is not a plain file name")
            listed.pop(name)
    table_files: dict[str, list[str]] = {}
    for table in TABLES:
        parts = sorted(n for n in listed if re.fullmatch(rf"{table}-\d{{4}}\.csv", n))
        if f"{table}.csv" in listed and parts:
            problems.append(f"{MANIFEST}: {table} is listed both whole and in parts")
        names = [f"{table}.csv"] if f"{table}.csv" in listed else parts
        if not names:
            problems.append(f"{MANIFEST}: {table}.csv is not listed")
        elif parts and parts != part_names(table, len(parts)):
            problems.append(f"{MANIFEST}: the parts of {table} are not numbered 0001 onwards")
        elif len(names) > 1 and table not in SPLITTABLE:
            problems.append(f"{MANIFEST}: {table} may not be split, other tables refer to it")
        table_files[table] = names
    images = sorted(n for n in listed if IMAGE.fullmatch(n))
    if images != [f"vectors-{i:04d}.png" for i in range(1, len(images) + 1)]:
        problems.append(f"{MANIFEST}: the images are not numbered 0001 onwards")
    expected = {n for names in table_files.values() for n in names} | set(images) | {DATAPACKAGE}
    if DATAPACKAGE not in listed:
        problems.append(f"{MANIFEST}: {DATAPACKAGE} is not listed")
    for name in sorted(set(listed) - expected):
        problems.append(f"{MANIFEST}: {name} is not a file of the package")
    present = {p.name for p in folder.iterdir() if p.is_file() and not p.name.startswith(".")} - {MANIFEST}
    for name in sorted(present - set(listed)):
        problems.append(f"{name}: not listed in {MANIFEST}")
    data: dict[str, bytes] = {}
    for name, entry in sorted(listed.items()):
        path = folder / name
        if not path.is_file():
            problems.append(f"{name}: missing")
            continue
        data[name] = path.read_bytes()
        if name != DATAPACKAGE and len(data[name]) > MAX_PART_BYTES:
            problems.append(f"{name}: {len(data[name])} bytes, over the limit of {MAX_PART_BYTES} for one file")
        if len(data[name]) != entry.get("bytes"):
            problems.append(f"{name}: {len(data[name])} bytes, {entry.get('bytes')} in {MANIFEST}")
        if hashlib.sha256(data[name]).hexdigest() != entry.get("sha256"):
            problems.append(f"{name}: SHA-256 differs from {MANIFEST}")
    digest = package_hash({n: e.get("sha256", "") for n, e in listed.items()})
    if digest != manifest.get("package_sha256"):
        problems.append(f"{MANIFEST}: package_sha256 is not the hash of the listed files")
    if folder.name != PREFIX + digest[:12]:
        problems.append(f"folder name {folder.name} does not match the package hash ({PREFIX}{digest[:12]})")

    tables: dict[str, list[dict]] = {}
    for table, columns in TABLES.items():
        for name in table_files[table]:
            if name not in data:
                continue
            header, rows = _rows(data[name])
            if header != [c for c, _, _ in columns]:
                problems.append(f"{name}: columns {header}, expected {[c for c, _, _ in columns]}")
                continue
            tables.setdefault(table, []).extend(rows)
    for table, key in KEYS.items():
        seen: set[str] = set()
        for r in tables.get(table, []):
            if r[key] in seen:
                problems.append(f"{table}.csv: {key} {r[key]} appears twice")
            seen.add(r[key])
    ids = {t: {r[KEYS[t]] for r in tables.get(t, [])} for t in KEYS}
    for table, column, ref in REFERENCES:
        for r in tables.get(table, []):
            if r[column] not in ids[ref]:
                problems.append(f"{table}.csv: {column} {r[column]} is not in {ref}.csv")
    nodes = ids["documents"] | ids["claims"]
    for r in tables.get("edges", []):
        for end in ("source", "target"):
            if r[end] not in nodes:
                problems.append(f"edges.csv: {end} {r[end]} is not a document or a claim")
        try:
            float(r["weight"])
        except ValueError:
            problems.append(f"edges.csv: weight {r['weight']!r} is not a number")
    claims = {r["claim_id"]: r for r in tables.get("claims", [])}
    documents = {r["document_id"]: r for r in tables.get("documents", [])}
    for r in tables.get("quotes", []):
        doc = documents.get(r["document_id"])
        claim = claims.get(r["claim_id"])
        if claim is not None and claim["document_id"] != r["document_id"]:
            problems.append(f"quotes.csv: {r['quote_id']} and its claim name different documents")
        try:
            start, end = int(r["start"]), int(r["end"])
        except ValueError:
            problems.append(f"quotes.csv: {r['quote_id']} has offsets that are not integers")
            continue
        if (doc is not None and not 0 <= start < end <= int(doc["chars"])) or end - start != len(r["text"]):
            problems.append(f"quotes.csv: {r['quote_id']} has offsets outside its document or its text")
    pixels: dict[str, list[bytes]] = {}
    dims = set()
    for name in images:
        if name in data:
            try:
                width, rows = read_png(data[name])
            except ValueError as exc:
                problems.append(f"{name}: {exc}")
                continue
            pixels[name] = rows
            dims.add(width)
    used: set[tuple[str, int]] = set()
    for r in tables.get("vectors", []):
        try:
            row = int(r["row"])
            float(r["scale"])
        except ValueError:
            problems.append(f"vectors.csv: {r['document_id']} has a row or scale that is not a number")
            continue
        if r["image"] not in pixels:
            problems.append(f"vectors.csv: {r['document_id']} names {r['image']}, not a readable image of the package")
        elif not 0 <= row < len(pixels[r["image"]]) or (r["image"], row) in used:
            problems.append(f"vectors.csv: {r['document_id']} names a row outside {r['image']} or used twice")
        else:
            used.add((r["image"], row))
            if 0 in pixels[r["image"]][row]:
                problems.append(f"{r['image']}: row {row} has a pixel 0, which no integer is written as")
    if sum(len(rows) for rows in pixels.values()) != len(used) and not any("vectors.csv" in p for p in problems):
        problems.append("vectors.csv: some rows of the images belong to no document")
    if len(dims) > 1:
        problems.append(f"images of different widths {sorted(dims)}")
    try:
        described = json.loads(data.get(DATAPACKAGE, b"{}")).get("exocortex", {})
    except ValueError:
        described = {}
        problems.append(f"{DATAPACKAGE}: not JSON")
    if described.get("tables") != table_files or described.get("images") != images:
        problems.append(f"{DATAPACKAGE}: the files of the tables differ from {MANIFEST}")
    if dims and described.get("embedding", {}).get("dimensions") not in dims:
        problems.append(f"{DATAPACKAGE}: dimensions differ from vectors.csv")
    for table in TABLES:
        if described.get("counts", {}).get(table) != len(tables.get(table, [])):
            problems.append(f"{DATAPACKAGE}: count of {table} differs from {table}.csv")

    if corpora is not None:
        texts = corpus_texts(corpora)
        for doc_id, doc in documents.items():
            text = texts.get(doc_id)
            if text is None:
                problems.append(f"documents.csv: {doc_id} is not in the corpus files")
            elif sha256_text(text) != doc["sha256"] or len(text) != int(doc["chars"]):
                problems.append(f"documents.csv: {doc_id} differs from its corpus text")
        for r in tables.get("quotes", []):
            text = texts.get(r["document_id"])
            if text is not None and text[int(r["start"]):int(r["end"])] != r["text"]:
                problems.append(f"quotes.csv: {r['quote_id']} is not at its position in the corpus text")
    return problems


# -- building from the lab database -------------------------------------------------------

def _personal_data(text: str) -> bool:
    """Whether the gate would find personal data in ``text`` (its own rules, shipped with the lab)."""
    from exocortex.lab.headers import personal_data

    return bool(personal_data(text))


def redistribution(sources_file: Path) -> dict[str, dict[str, str]]:
    """source id -> {node type: basis} from the ``redistribution`` field of lab/sources.yaml."""
    import yaml

    data = yaml.safe_load(sources_file.read_text(encoding="utf-8")) or {}
    out = {}
    for s in data.get("sources") or []:
        basis = s.get("redistribution")
        if isinstance(basis, dict):
            out[str(s["id"])] = {str(k): str(v) for k, v in basis.items() if isinstance(v, str) and v.strip()}
    return out


def collect(conn, tenant: str, corpora: list[str], sources_file: Path,
            embedding_model: str = EMBEDDING_MODEL) -> tuple[Package, dict]:
    """The package from the lab database, and a report of what was left out and why."""
    from exocortex.source_allowlist import Allowlist

    allow = Allowlist.load(sources_file)
    basis = redistribution(sources_file)
    pkg = Package(embedding_model=embedding_model)
    report: dict = {"left_out": {}, "claims_left_out": {}, "not_a_corpus": {}}

    def leave(bucket: str, key: str, n: int = 1) -> None:
        report[bucket][key] = report[bucket].get(key, 0) + n

    rows = conn.execute(
        """SELECT t.id::text AS id, t.thought_type, t.body, t.metadata, t.embedding::text AS embedding,
                  s.source_type, s.uri AS source_uri
           FROM thoughts t JOIN raw_sources s ON s.id = t.source_id
           WHERE t.tenant_id = %s AND t.thought_type = ANY(%s) AND s.deleted_at IS NULL
             AND t.metadata->>'corpus' = ANY(%s)
           ORDER BY t.id""",
        (tenant, list(NODE_KIND), corpora),
    ).fetchall()
    by_node: dict[str, str] = {}             # thought id -> document id
    by_paper: dict[tuple, list[dict]] = {}   # (corpus, arxiv id, kind) -> documents (one per version)
    used_sources: dict[str, set] = {}
    for r in rows:
        meta = r["metadata"] or {}
        kind = NODE_KIND[r["thought_type"]]
        source = next((s for s in allow.sources
                       if s.source_type == r["source_type"] and s.matches_uri(r["source_uri"])), None)
        if source is None:
            leave("left_out", f"{kind} of corpus {meta.get('corpus')}: source not on lab/sources.yaml")
            continue
        if r["thought_type"] not in basis.get(source.id, {}):
            leave("left_out", f"{kind} of corpus {meta.get('corpus')}: no basis for redistribution of "
                              f"{r['thought_type']} under {source.id} in lab/sources.yaml")
            continue
        text = collapse(r["body"] or "")
        if _personal_data(text):
            leave("left_out", f"{kind} of corpus {meta.get('corpus')}: personal data the gate would hold")
            continue
        paper = f"arxiv:{meta.get('arxiv_id')}v{meta.get('version')}"
        doc = {"document_id": f"{meta.get('corpus')}/{paper}/{kind}", "corpus": meta.get("corpus"),
               "source": source.id, "paper": paper, "kind": kind, "lang": meta.get("lang") or "",
               "uri": meta.get("uri") or r["source_uri"], "sha256": sha256_text(text),
               "chars": len(text), "_text": text}
        pkg.documents.append(doc)
        by_node[r["id"]] = doc["document_id"]
        by_paper.setdefault((meta.get("corpus"), str(meta.get("arxiv_id")), kind), []).append(doc)
        used_sources.setdefault(source.id, set()).add(r["thought_type"])
        if not r["embedding"]:
            leave("left_out", "vector: document without an embedding")
            continue
        vec = parse_vector(r["embedding"])
        if pkg.dimensions and len(vec) != pkg.dimensions:
            raise ValueError(f"embeddings of different lengths ({pkg.dimensions} and {len(vec)})")
        pkg.dimensions = len(vec)
        scale, pixels = quantize(vec)
        pkg.vectors.append({"document_id": doc["document_id"], "scale": scale, "pixels": pixels})
        loss = 1.0 - _cosine(vec, dequantize(scale, pixels))
        report["quantization_max_cosine_loss"] = max(report.get("quantization_max_cosine_loss", 0.0), loss)

    results = conn.execute(
        """SELECT e.slug, e.params AS eparams, r.run_id, c.name AS config, c.variant, c.params AS cparams,
                  res.model, res.item_id, res.output, si.payload
           FROM exp_results res
           JOIN exp_runs r ON r.id = res.run_id
           JOIN experiments e ON e.id = r.experiment_id
           JOIN exp_configs c ON c.id = res.config_id
           LEFT JOIN exp_sample_items si ON si.sample_id = r.sample_id AND si.item_id = res.item_id
           WHERE e.kind = 'claims' AND r.status = 'done' AND res.ok AND e.params->>'corpus' = ANY(%s)
           ORDER BY e.slug, r.run_id, c.name, res.item_id""",
        (corpora,),
    ).fetchall()
    for res in results:
        kind = ((res["cparams"] or {}).get("text") or "abstract")
        docs = by_paper.get(((res["eparams"] or {}).get("corpus"), str(res["item_id"]), kind), [])
        claims = [c for c in (res["output"] or {}).get("claims") or [] if c.get("grounded")]
        if not docs:
            leave("claims_left_out", "their document is not in the package", len(claims))
            continue
        # the text the run used: the sample recorded its checksum (exocortex/lab/specs.py)
        expected = (res["payload"] or {}).get(f"{kind}_sha256")
        doc = next((d for d in docs if d["sha256"] == expected), None) if expected else (docs[0] if len(docs) == 1 else None)
        if doc is None:
            leave("claims_left_out", "their document changed after the run", len(claims))
            continue
        for c in claims:
            span = locate(c.get("quote") or "", doc["_text"])
            if span is None:
                leave("claims_left_out", "quote not found in the document")
                continue
            quote = doc["_text"][span[0]:span[1]]
            if _personal_data(c.get("claim") or "") or _personal_data(quote):
                leave("claims_left_out", "personal data the gate would hold")
                continue
            cid = f"{res['slug']}/{res['run_id']}/{res['config']}/{res['item_id']}/{c.get('i')}"
            pkg.claims.append({"claim_id": cid, "document_id": doc["document_id"], "experiment": res["slug"],
                               "run_id": res["run_id"], "config": res["config"], "model": res["model"] or "",
                               "variant": res["variant"] or "", "mode": c.get("mode") or "",
                               "text": collapse(c.get("claim") or ""), "proposition": c.get("proposition"),
                               "redundant": c.get("redundant"), "usable": c.get("usable")})
            pkg.quotes.append({"quote_id": f"{cid}/q", "claim_id": cid, "document_id": doc["document_id"],
                               "start": span[0], "end": span[1], "text": quote})
            pkg.edges.append({"source": cid, "target": doc["document_id"], "type": "derived_from", "weight": "1"})

    if by_node:
        ids = sorted(by_node)
        for e in conn.execute(
                """SELECT src_id::text AS src, dst_id::text AS dst, type::text AS type, confidence FROM edges
                   WHERE tenant_id = %s AND src_id::text = ANY(%s) AND dst_id::text = ANY(%s)""",
                (tenant, ids, ids)).fetchall():
            weight = format(float(e["confidence"]), ".6g") if e["confidence"] is not None else "1"
            pkg.edges.append({"source": by_node[e["src"]], "target": by_node[e["dst"]], "type": e["type"],
                              "weight": weight})
    for r in conn.execute(
            """SELECT thought_type, count(*) AS n FROM thoughts WHERE tenant_id = %s AND NOT (thought_type = ANY(%s))
               AND (metadata->>'domain') = 'lab' GROUP BY thought_type ORDER BY thought_type""",
            (tenant, list(NODE_KIND))).fetchall():
        report["not_a_corpus"][r["thought_type"]] = r["n"]
    pkg.corpora = [{"name": c, "path": f"lab/corpora/{c}/",
                    "documents": sum(1 for d in pkg.documents if d["corpus"] == c)} for c in sorted(corpora)]
    pkg.sources = [{"id": sid, "redistribution": {t: basis[sid][t] for t in sorted(types)}}
                   for sid, types in sorted(used_sources.items())]
    for d in pkg.documents:
        d.pop("_text")
    return pkg, report


def corpus_names(corpora_dir: Path) -> list[str]:
    """The public corpora: folders of lab/corpora with a manifest."""
    return sorted(p.parent.name for p in corpora_dir.glob("*/manifest.csv"))


def cmd_build(args) -> int:
    sys.path.insert(0, str(ROOT))  # the gate's personal-data rules ship as tools/leakgate/pii.py
    from exocortex.lab.db import connect, tenant_id

    conn = connect(args.database_url)
    try:
        pkg, report = collect(conn, tenant_id(), corpus_names(args.corpora), args.sources, args.embedding_model)
    finally:
        conn.close()
    if not pkg.documents:
        print(json.dumps({"error": "nothing to publish: no document of a public corpus has a basis for "
                                   "redistribution", **report}, indent=2, ensure_ascii=False))
        return 1
    files = render(pkg)
    version, digest = version_of(files)
    with tempfile.TemporaryDirectory() as tmp:
        check = Path(tmp) / version
        check.mkdir()
        for name, data in files.items():
            (check / name).write_bytes(data)
        problems = verify(check, args.corpora)
    if problems:
        print(json.dumps({"error": "the built package does not verify", "problems": problems[:50]}, indent=2))
        return 1
    placed = {"version": version, "package_sha256": digest, "unchanged": None, "removed": []}
    if not args.dry_run:
        placed = place(files, args.out, args.staging)
    print(json.dumps({**placed, "bytes": sum(len(d) for d in files.values()),
                      "files": {n: len(d) for n, d in sorted(files.items())},
                      "counts": {t: len(getattr(pkg, t)) for t in TABLES}, "dimensions": pkg.dimensions,
                      **report}, indent=2, ensure_ascii=False))
    return 0


def cmd_verify(args) -> int:
    problems = verify(args.folder, args.corpora)
    for p in problems:
        print(p)
    try:
        digest = json.loads((args.folder / MANIFEST).read_text(encoding="utf-8")).get("package_sha256")
    except (OSError, ValueError):
        digest = None
    print(f"{args.folder.name}: " + ("sound, package hash " + str(digest) if not problems
                                     else f"{len(problems)} problem(s)"))
    return 0 if not problems else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build the package from the lab database (DATABASE_URL, TENANT_ID)")
    b.add_argument("--out", type=Path, required=True, help="folder of the package versions, e.g. dowody/data/graph")
    b.add_argument("--staging", type=Path, default=None,
                   help="working folder on the same file system as --out that the publisher does not read")
    b.add_argument("--corpora", type=Path, default=ROOT / "lab" / "corpora")
    b.add_argument("--sources", type=Path, default=ROOT / "lab" / "sources.yaml")
    b.add_argument("--database-url", default=None)
    b.add_argument("--embedding-model", default=EMBEDDING_MODEL)
    b.add_argument("--dry-run", action="store_true", help="build and verify, write nothing")
    b.set_defaults(func=cmd_build)
    v = sub.add_parser("verify", help="check a package folder from its files alone")
    v.add_argument("folder", type=Path)
    v.add_argument("--corpora", type=Path, default=None, help="also check quotes against lab/corpora")
    v.set_defaults(func=cmd_verify)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
