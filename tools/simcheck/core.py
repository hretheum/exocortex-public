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
# Neighbourhood size for the margin and csls semantic measures.
SEMANTIC_K = 10
# Private paragraphs shown to the judge for each candidate.
JUDGE_NEIGHBOURS = 3
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


JUDGE_PROMPT = (
    "You check whether a text about to be published reveals the content of a private note.\n"
    "Answer YES if text A restates specific content of any private note below: the same particular "
    "facts, figures, decisions, names, events or plans, even in other words or another language. "
    "Answer NO if they only share a general topic, vocabulary or document structure.\n"
    "Answer with one word: YES or NO.\n\n"
)


class Judge:
    """Second stage of the semantic check: a local chat model decides whether
    a candidate paragraph restates one of its nearest private paragraphs.
    OpenAI-compatible endpoint; thinking disabled, one-word answer."""

    def __init__(self, base_url: str, model: str, api_key: str = "unused", client=None):
        import httpx

        self.model = model
        self.client = client or httpx.Client(base_url=base_url.rstrip("/"), timeout=300,
                                             headers={"Authorization": f"Bearer {api_key}"})
        self.calls = 0

    @classmethod
    def from_env(cls) -> "Judge | None":
        url, model = os.environ.get("SIMCHECK_JUDGE_URL", "").strip(), os.environ.get("SIMCHECK_JUDGE_MODEL", "").strip()
        if not url or not model or url.lower() == "none":
            return None
        return cls(url, model, os.environ.get("SIMCHECK_JUDGE_KEY", "unused"))

    def is_restatement(self, candidate: str, private: list[str]) -> bool:
        notes = "\n\n".join(f"Private note {i + 1}:\n{p[:WINDOW]}" for i, p in enumerate(private))
        content = f"{JUDGE_PROMPT}Text A:\n{candidate[:WINDOW]}\n\n{notes}\n\nAnswer:"
        resp = self.client.post("/chat/completions", json={
            "model": self.model, "temperature": 0, "max_tokens": 8,
            "chat_template_kwargs": {"enable_thinking": False}, "reasoning_effort": "low",
            "messages": [{"role": "user", "content": content}]})
        resp.raise_for_status()
        self.calls += 1
        answer = (resp.json()["choices"][0]["message"].get("content") or "").strip().upper()
        return answer.startswith("YES")


@dataclass
class Result:
    similar: bool
    score_literal: float
    score_semantic: float
    rule: str
    judged: int = 0

    def to_dict(self) -> dict:
        return {"similar": self.similar, "score_literal": round(self.score_literal, 4),
                "score_semantic": round(self.score_semantic, 4), "rule": self.rule, "judged": self.judged}


class Index:
    def __init__(self, ensemble: MinHashLSHEnsemble, sigs: dict, vectors=None, thresholds=None, embed_cfg=None,
                 texts: list[str] | None = None):
        self.ensemble = ensemble
        # Private paragraph texts, for the judge only; never returned by the service.
        self.texts = texts
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
        return cls(ensemble, sigs, vectors, None, embed_cfg, paras)

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        with (directory / "index.pkl").open("wb") as fh:
            pickle.dump({"ensemble": self.ensemble, "sigs": self.sigs, "thresholds": self.thresholds,
                         "embed_cfg": self.embed_cfg, "texts": self.texts}, fh)
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
        return cls(d["ensemble"], d["sigs"], vectors, d["thresholds"], d.get("embed_cfg"), d.get("texts"))

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

    def _embed_queries(self, paras: list[str]):
        if self._embedder is None:
            self._embedder = Embedder(self.embed_cfg["base_url"], self.embed_cfg["model"], os.environ.get("SIMCHECK_EMBED_KEY", "unused"))
        import numpy as np

        return np.array([_normalise(v) for v in self._embedder.embed(paras)], dtype="float32")

    def _corpus_hubness(self, idx: int) -> float:
        """Mean similarity of corpus paragraph ``idx`` to its nearest corpus
        neighbours (itself excluded); cached, computed on demand."""
        import numpy as np

        cache = self.__dict__.setdefault("_hub_cache", {})
        if idx not in cache:
            sims = self.vectors @ self.vectors[idx]
            top = np.partition(sims, -(SEMANTIC_K + 1))[-(SEMANTIC_K + 1):]
            cache[idx] = float((top.sum() - sims[idx]) / SEMANTIC_K)
        return cache[idx]

    def semantic_variants(self, paras: list[str], q=None) -> dict[str, list[float]]:
        """Three scores per paragraph against the corpus embeddings.

        raw    highest cosine similarity (the original measure);
        margin highest similarity minus the mean of the next SEMANTIC_K: a
               paraphrase stands out against one private paragraph, a text
               that is merely on the same topic is close to many;
        csls   cross-domain similarity local scaling: 2*cos(q, p) minus the
               mean neighbourhood similarity of the query and of p, which
               discounts dense regions of the corpus ("hubs").
        """
        import numpy as np

        if self.vectors is None or not paras:
            zero = [0.0] * len(paras)
            return {"raw": zero, "margin": zero, "csls": zero}
        if q is None:
            q = self._embed_queries(paras)
        sims = q @ self.vectors.T
        k = min(SEMANTIC_K + 1, sims.shape[1])
        top_idx = np.argpartition(sims, -k, axis=1)[:, -k:]
        top = np.take_along_axis(sims, top_idx, axis=1)
        order = np.argsort(-top, axis=1)
        top = np.take_along_axis(top, order, axis=1)
        top_idx = np.take_along_axis(top_idx, order, axis=1)
        raw = top[:, 0]
        rest = top[:, 1:].mean(axis=1) if top.shape[1] > 1 else np.zeros_like(raw)
        margin = raw - rest
        r_q = top[:, :SEMANTIC_K].mean(axis=1)
        r_p = np.array([self._corpus_hubness(int(i)) for i in top_idx[:, 0]], dtype="float32")
        csls = 2 * raw - r_q - r_p
        return {"raw": [float(x) for x in raw], "margin": [float(x) for x in margin],
                "csls": [float(x) for x in csls]}

    def semantic_neighbours(self, paras: list[str], k: int = 3, q=None) -> tuple[list[float], list[list[int]]]:
        """Highest similarity per paragraph and the corpus indices of its k nearest paragraphs."""
        import numpy as np

        if q is None:
            q = self._embed_queries(paras)
        sims = q @ self.vectors.T
        k = min(k, sims.shape[1])
        idx = np.argpartition(sims, -k, axis=1)[:, -k:]
        top = np.take_along_axis(sims, idx, axis=1)
        order = np.argsort(-top, axis=1)
        idx = np.take_along_axis(idx, order, axis=1)
        top = np.take_along_axis(top, order, axis=1)
        return [float(x) for x in top[:, 0]], [[int(i) for i in row] for row in idx]

    def judge(self) -> "Judge | None":
        if "_judge" not in self.__dict__:
            self._judge = Judge.from_env()
        return self._judge

    def two_stage(self) -> bool:
        return (self.vectors is not None and self.texts is not None
                and self.thresholds.get("semantic_candidate") is not None and self.judge() is not None)

    def semantic_scores(self, paras: list[str]) -> list[float]:
        """Scores under the measure named in thresholds["semantic_score"]."""
        if self.vectors is None or not paras:
            return [0.0] * len(paras)
        measure = self.thresholds.get("semantic_score", "raw")
        return self.semantic_variants(paras)[measure]

    def check(self, text: str) -> Result:
        paras = list(paragraphs(text)) or ([text] if len(text) >= 40 else [])
        if not paras:
            return Result(False, 0.0, 0.0, "none")
        lit = max(self.literal_score(p) for p in paras)
        if self.two_stage():
            # Stage one: similarity only picks candidates. Stage two: the judge
            # decides. A judge error propagates, so the caller holds the file.
            raw, idx = self.semantic_neighbours(paras, JUDGE_NEIGHBOURS)
            sem = max(raw)
            if lit >= self.thresholds["literal"]:
                return Result(True, lit, sem, "literal")
            cand = self.thresholds["semantic_candidate"]
            judged = 0
            for para, score, ids in sorted(zip(paras, raw, idx), key=lambda t: -t[1]):
                if score < cand:
                    break
                judged += 1
                if self.judge().is_restatement(para, [self.texts[i] for i in ids]):
                    return Result(True, lit, sem, "semantic-judged", judged)
            return Result(False, lit, sem, "none", judged)
        sem = max(self.semantic_scores(paras)) if self.vectors is not None else 0.0
        if lit >= self.thresholds["literal"]:
            return Result(True, lit, sem, "literal")
        if self.vectors is not None and sem >= self.thresholds["semantic"]:
            return Result(True, lit, sem, "semantic")
        return Result(False, lit, sem, "none")
