"""Index building and similarity queries."""

from __future__ import annotations

import json
import math
import os
import pickle
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from datasketch import MinHash, MinHashLSHEnsemble

from tools.leakgate.normalize import fold

NUM_PERM = 128
CHAR_K = 5  # chosen on calibration data: character 5-grams survive removed names and dropped words
ENSEMBLE_THRESHOLD = 0.1
# Paragraphs with fewer distinct shingles carry too little text to judge
# (decorative comment rulers, short headings); containment of a tiny set is
# high by chance.
MIN_SHINGLES = 50
MIN_PARAGRAPH = 160
WINDOW = 1200
TEXT_SUFFIXES = {".md", ".txt", ".html", ".csv", ".json", ".yaml", ".yml", ".py", ".sql"}


FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.S)


def paragraphs(text: str) -> Iterator[str]:
    """Split into paragraphs; long ones into overlapping windows.

    YAML front matter is dropped first: it is boilerplate shared by many
    documents and says nothing about their content.
    """
    text = FRONTMATTER_RE.sub("", text)
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if len(block) < MIN_PARAGRAPH:
            continue
        if len(block) <= WINDOW:
            yield block
            continue
        step = WINDOW // 2
        for start in range(0, len(block) - step, step):
            yield block[start : start + WINDOW]


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", fold(text))


def shingles(text: str) -> set[bytes]:
    joined = "".join(_words(text))
    return {joined[i : i + CHAR_K].encode() for i in range(max(1, len(joined) - CHAR_K + 1))}


def hashed(sh: set[bytes]):
    """Shingles as a sorted array of 32-bit hashes, for exact containment."""
    import numpy as np
    import zlib

    return np.unique(np.fromiter((zlib.crc32(x) for x in sh), dtype=np.uint32, count=len(sh)))


def minhash(sh: set[bytes]) -> MinHash:
    m = MinHash(num_perm=NUM_PERM)
    m.update_batch(list(sh))
    return m


def containment(q: MinHash, q_size: int, c: MinHash, c_size: int) -> float:
    """Estimated share of the query's shingles present in the candidate."""
    j = q.jaccard(c)
    inter = j * (q_size + c_size) / (1 + j)
    return min(1.0, inter / max(1, q_size))


def iter_dir_texts(roots: Iterable[Path], exclude: Iterable[str] = ()) -> Iterator[tuple[str, str]]:
    """Text files under the roots. ``exclude`` holds glob patterns matched
    against the path relative to its root (for example ``*/dowody/*``, so the
    published documents are not part of the private corpus)."""
    import fnmatch

    patterns = list(exclude)
    for root in roots:
        for path in sorted(Path(root).rglob("*")):
            rel = path.relative_to(root).as_posix()
            if any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch("/" + rel, pat) for pat in patterns):
                continue
            if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES and ".git" not in path.parts:
                try:
                    yield str(path), path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue


def iter_postgres_texts(dsn: str, query: str) -> Iterator[tuple[str, str]]:
    import psycopg

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(query)
        for row in cur:
            yield str(row[0]), row[1] or ""


class Embedder:
    """OpenAI-compatible embeddings endpoint (for example llama-swap with bge-m3)."""

    def __init__(self, base_url: str, model: str, api_key: str = "unused"):
        import httpx

        self.client = httpx.Client(base_url=base_url.rstrip("/"), timeout=120, headers={"Authorization": f"Bearer {api_key}"})
        self.model = model

    def _post(self, batch: list[str]) -> list[list[float]]:
        resp = self.client.post("/embeddings", json={"model": self.model, "input": batch})
        resp.raise_for_status()
        return [d["embedding"] for d in resp.json()["data"]]

    def _one(self, text: str) -> list[float]:
        """Embed one text; if the server rejects it as too long (llama.cpp's
        physical batch limit), embed a shorter prefix instead."""
        import httpx

        for _ in range(6):
            try:
                return self._post([text])[0]
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 500 or len(text) < 200:
                    raise
                text = text[: len(text) // 2]
        return self._post([text[:200]])[0]

    def embed(self, texts: list[str], progress_every: int = 2000) -> list[list[float]]:
        import httpx

        out: list[list[float]] = []
        for i in range(0, len(texts), 32):
            batch = texts[i : i + 32]
            try:
                out.extend(self._post(batch))
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 500:
                    raise
                out.extend(self._one(t) for t in batch)
            if progress_every and (i // 32) % max(1, progress_every // 32) == 0:
                print(f"embedded {min(i + 32, len(texts))}/{len(texts)}", flush=True)
        return out


def _normalise(vec: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / n for x in vec]


@dataclass
class Result:
    similar: bool
    score_literal: float
    score_semantic: float
    rule: str

    def to_dict(self) -> dict:
        return {"similar": self.similar, "score_literal": round(self.score_literal, 4),
                "score_semantic": round(self.score_semantic, 4), "rule": self.rule}


class Index:
    def __init__(self, ensemble: MinHashLSHEnsemble, sigs: dict, vectors=None, thresholds=None, embed_cfg=None):
        self.ensemble = ensemble
        self.sigs = sigs  # key -> (MinHash, size, sorted uint32 shingle hashes)
        self.vectors = vectors  # numpy array (n, d) normalised, or None
        self.thresholds = thresholds or {"literal": 0.40, "semantic": 0.90}
        self.embed_cfg = embed_cfg
        self._embedder = None

    # -- build ----------------------------------------------------------------
    @classmethod
    def build(cls, texts: Iterable[tuple[str, str]], embedder: Embedder | None = None) -> "Index":
        sigs: dict[str, tuple[MinHash, int]] = {}
        paras: list[str] = []
        n = 0
        for _src, text in texts:
            for para in paragraphs(text):
                sh = shingles(para)
                sigs[f"p{n}"] = (minhash(sh), len(sh), hashed(sh))
                paras.append(para)
                n += 1
        ensemble = MinHashLSHEnsemble(threshold=ENSEMBLE_THRESHOLD, num_perm=NUM_PERM, num_part=32)
        ensemble.index((k, m, size) for k, (m, size, _h) in sigs.items())
        vectors = None
        embed_cfg = None
        if embedder is not None and paras:
            import numpy as np

            vectors = np.array([_normalise(v) for v in embedder.embed(paras)], dtype="float32")
            embed_cfg = {"base_url": str(embedder.client.base_url), "model": embedder.model}
        return cls(ensemble, sigs, vectors, None, embed_cfg)

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        with (directory / "index.pkl").open("wb") as fh:
            pickle.dump({"ensemble": self.ensemble, "sigs": self.sigs,
                         "thresholds": self.thresholds, "embed_cfg": self.embed_cfg}, fh)
        if self.vectors is not None:
            import numpy as np

            np.save(directory / "vectors.npy", self.vectors)
        (directory / "meta.json").write_text(json.dumps({"paragraphs": len(self.sigs), "thresholds": self.thresholds,
                                                          "semantic": self.vectors is not None}, indent=2))

    @classmethod
    def load(cls, directory: Path) -> "Index":
        with (directory / "index.pkl").open("rb") as fh:
            d = pickle.load(fh)
        vectors = None
        if (directory / "vectors.npy").exists():
            import numpy as np

            vectors = np.load(directory / "vectors.npy")
        return cls(d["ensemble"], d["sigs"], vectors, d["thresholds"], d.get("embed_cfg"))

    # -- query ----------------------------------------------------------------
    def literal_score(self, para: str) -> float:
        """Highest exact share of the paragraph's shingles found in one corpus paragraph."""
        import numpy as np

        sh = shingles(para)
        if len(sh) < MIN_SHINGLES:
            return 0.0
        q = minhash(sh)
        qh = hashed(sh)
        best = 0.0
        for key in self.ensemble.query(q, len(sh)):
            ch = self.sigs[key][2]
            best = max(best, len(np.intersect1d(qh, ch, assume_unique=True)) / max(1, len(qh)))
        return best

    def semantic_scores(self, paras: list[str]) -> list[float]:
        if self.vectors is None or not paras:
            return [0.0] * len(paras)
        if self._embedder is None:
            self._embedder = Embedder(self.embed_cfg["base_url"], self.embed_cfg["model"], os.environ.get("SIMCHECK_EMBED_KEY", "unused"))
        import numpy as np

        q = np.array([_normalise(v) for v in self._embedder.embed(paras)], dtype="float32")
        return [float(x) for x in (q @ self.vectors.T).max(axis=1)]

    def check(self, text: str) -> Result:
        paras = list(paragraphs(text)) or ([text] if len(text) >= 40 else [])
        if not paras:
            return Result(False, 0.0, 0.0, "none")
        lit = max(self.literal_score(p) for p in paras)
        sem = max(self.semantic_scores(paras)) if self.vectors is not None else 0.0
        if lit >= self.thresholds["literal"]:
            return Result(True, lit, sem, "literal")
        if self.vectors is not None and sem >= self.thresholds["semantic"]:
            return Result(True, lit, sem, "semantic")
        return Result(False, lit, sem, "none")
