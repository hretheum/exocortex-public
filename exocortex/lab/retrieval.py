# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Experiment kind ``retrieval``: how well a configuration finds the right documents (roadmap task F5.8).

An item of the experiment is a question with hand-made gold answers. A
configuration says which embedding model ranks the documents of a corpus
for the question, and whether the ranking is then expanded along edges of
the graph. The runner stores each ranking with the gold answers it was
measured against, so results.csv alone is enough to recompute every number
(lab/recompute.py, ``lab/independent_retrieval_check.py``).

Question sets
-------------

A question set is a file in the experiment's corpus folder
(``lab/corpora/<corpus>/``) that a person prepares by hand; every sample of
the spec names one (``items:``), and no question may be in two samples.
Two formats, by file extension. Both are read strictly: the whole file is
checked, every problem is reported with its line, and an experiment whose
question sets have any problem does not run.

``*.csv`` with the header ``question_id,question,gold`` (any order)::

    question_id,question,gold
    q01,Which unit measures the pressure of a gas?,d004;d005:2;d011:0

``*.jsonl``, one object per line with the same three keys::

    {"question_id": "q01", "question": "Which unit ...?", "gold": ["d004", {"doc": "d005", "grade": 2}]}
    {"question_id": "q02", "question": "...", "gold": {"d004": 1, "d005": 2}}

- ``question_id``: letters, digits, ``.``, ``_`` and ``-``, at most 64,
  unique in the file (and across the samples of the spec).
- ``question``: one line of printable text, at most 2000 characters.
- ``gold``: the relevant documents. In CSV, entries separated by ``;``,
  each ``doc_id`` or ``doc_id:grade``; in JSONL a list of ids and
  ``{"doc", "grade"}`` objects, or an object from id to grade. A grade is an
  integer from 0 to 3, default 1; 0 marks a document judged not relevant
  (it is stored and has no effect on the metrics). A question needs at least
  one document with a grade above 0, no document may be listed twice, and
  every id must be a document of the corpus.
- A document id is letters, digits, ``.``, ``_``, ``-`` and ``/``, starting
  with a letter or digit.

Corpora
-------

``params.index`` picks where the documents come from:

- ``files`` (small corpora, the toy experiment): ``documents.jsonl`` in the
  corpus folder, one ``{"id", "text"}`` object per line, and optionally
  ``edges.csv`` with the header ``src,dst,type`` (directed edges between
  document ids; a type is lower-case letters, digits and ``_``);
- ``graph`` (default; the corpus in the lab graph, exocortex/lab/corpus_graph):
  the nodes of one text per paper (``text: abstract`` or ``summary``), the
  embedding stored in the graph for bge-m3 (otherwise the documents are
  embedded through the lab gateway), and the edges of the graph between two
  papers of the corpus. ``manifest.csv`` of the corpus folder names the
  documents, so gold ids can be checked before anything runs.

Configurations
--------------

The ``model`` of a configuration is the embedding model, from
lab/models.yaml, through the lab gateway (exocortex/lab/llm.py: the only
way out; the queue groups jobs by this model). Models named ``toy-hash-*``
are computed in the process from the words of the text, with no network: the
toy experiment uses them, and they say nothing about real embeddings. Params
of a configuration:

- ``text``: ``abstract`` (default) or ``summary``, graph corpora only;
- ``depth``: length of the stored ranking, default 100; the metrics see
  nothing beyond it;
- ``expansion``: absent or null for embeddings alone, otherwise a mapping:
  ``seed_k`` (the best documents by embedding that are expanded, default 5),
  ``hops`` (1 to 3, default 1), ``decay`` (score factor per hop, above 0
  and up to 1, default 0.5), ``direction`` (``out``, ``in`` or ``both``,
  default ``both``) and ``edge_types`` (a list; absent means every type).

A document reached by expansion gets ``decay`` times the score of the
document it was reached from (a score below 0 counts as 0) and keeps
the higher of that and its own embedding score. Ranks are by score, equal
scores by document id. An expansion along a type that the corpus has no
edge of is an error, not a silent no-op.

Spec example (see lab/experiments/toy-retrieval.yaml)::

    slug: toy-retrieval
    kind: retrieval
    title: "Toy experiment: retrieval"
    hypothesis: null
    params:
      corpus: toy-retrieval
      index: files
      recall_k: [5, 10]         # default 10
      bootstrap_seed: 20260929  # default the lab's; the value the card declares
      baseline: embeddings      # differences to this one; default every pair
    configs:
      - {name: embeddings, model: toy-hash-64, provider: none, variant: embeddings}
      - name: graph-cites
        model: toy-hash-64
        provider: none
        variant: graph
        params: {expansion: {seed_k: 3, edge_types: [cites]}}
    samples:
      - {name: test-12, role: test, seed: 0, method: "written by hand",
         items: lab/corpora/toy-retrieval/questions-test.csv}

Metrics: see retrieval_metrics.py.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path, PurePosixPath

from exocortex.lab import experiments as ex
from exocortex.lab import retrieval_metrics as rm
from exocortex.lab.claims import NODE, repo_path

KIND = "retrieval"
NAME = re.compile(r"[a-z0-9][a-z0-9-]*")  # experiment, sample and configuration names, as the run unit takes them
QUESTION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
DOC_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")
EDGE_TYPE = re.compile(r"[a-z][a-z0-9_]*")
MAX_GRADE = 3
MAX_QUESTION_CHARS = 2000
QUESTION_FIELDS = ("question_id", "question", "gold")
ROLES = ("tuning", "control", "pilot", "test", "blind")
DIRECTIONS = ("out", "in", "both")
INDEXES = ("files", "graph")
EXPERIMENT_PARAMS = {"corpus", "index", "text", "recall_k", "bootstrap_seed", "baseline"}
CONFIG_KEYS = {"name", "model", "provider", "variant", "params"}
CONFIG_PARAMS = {"text", "depth", "expansion"}
EXPANSION_PARAMS = {"seed_k", "hops", "decay", "direction", "edge_types"}
DEFAULT_DEPTH = 100
STORED_MODEL = "bge-m3"  # the embeddings the lab graph keeps (schema/31_embeddings_bge_m3_1024.sql)
MAX_REPORTED = 20


class RetrievalInputError(ValueError):
    """A question set, corpus file or spec that does not pass the checks; ``problems`` lists every one."""

    def __init__(self, source: str, problems: Sequence[str]):
        self.source, self.problems = source, list(problems)
        shown = self.problems[:MAX_REPORTED]
        more = f"\n- ... and {len(self.problems) - MAX_REPORTED} more" if len(self.problems) > MAX_REPORTED else ""
        super().__init__(f"{source}: {len(self.problems)} problem(s)\n" + "\n".join(f"- {p}" for p in shown) + more)


# -- question sets -------------------------------------------------------------

@dataclass(frozen=True)
class Question:
    id: str
    text: str
    gold: dict[str, int]


def content_sha256(question: Question) -> str:
    """Checksum of a question with its gold answers: what a sample member stands for."""
    doc = {"question": question.text, "gold": dict(sorted(question.gold.items()))}
    return hashlib.sha256(json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()


def _grade(value, where: str, problems: list[str]) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        problems.append(f"{where}: grade must be an integer, got {value!r}")
    elif not 0 <= value <= MAX_GRADE:
        problems.append(f"{where}: grade {value} is outside 0 to {MAX_GRADE}")
    else:
        return value
    return None


def _gold_from_cell(cell: str, where: str, problems: list[str]) -> list[tuple[str, int | None]]:
    entries = []
    for part in cell.split(";"):
        part = part.strip()
        if not part:
            problems.append(f"{where}: empty entry in gold (a stray ';')")
            continue
        doc, sep, grade = part.partition(":")
        doc, grade = doc.strip(), grade.strip()
        if sep:
            value = int(grade) if re.fullmatch(r"[0-9]+", grade) else grade
            entries.append((doc, _grade(value, f"{where}: {part!r}", problems)))
        else:
            entries.append((doc, 1))
    return entries


def _gold_from_json(raw, where: str, problems: list[str]) -> list[tuple[str, int | None]]:
    entries: list[tuple[str, int | None]] = []
    if isinstance(raw, dict):
        for doc, grade in raw.items():
            entries.append((doc, _grade(grade, f"{where}: {doc!r}", problems)))
    elif isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, str):
                entries.append((entry, 1))
            elif isinstance(entry, dict) and set(entry) <= {"doc", "grade"} and isinstance(entry.get("doc"), str):
                grade = entry.get("grade", 1)
                entries.append((entry["doc"], _grade(grade, f"{where}: {entry['doc']!r}", problems)))
            else:
                problems.append(f"{where}: a gold entry is a document id or an object with \"doc\" and optional "
                                f"\"grade\", got {entry!r}")
    else:
        problems.append(f"{where}: gold must be a list or an object, got {type(raw).__name__}")
    return entries


def _question(qid, text, entries, where: str, seen: set[str], known_docs: set[str] | None,
              problems: list[str], start: int) -> Question | None:
    """The question if nothing was reported for it since ``start`` (the length of ``problems`` before its gold was read)."""
    if not isinstance(qid, str) or not QUESTION_ID.fullmatch(qid):
        problems.append(f"{where}: question_id must be letters, digits, '.', '_' or '-' (at most 64), got {qid!r}")
    elif qid in seen:
        problems.append(f"{where}: question_id {qid!r} is used twice")
    if not isinstance(text, str) or not text.strip():
        problems.append(f"{where}: the question is empty")
    else:
        text = text.strip()
        if not text.isprintable():
            problems.append(f"{where}: the question has a control character or a line break")
        if len(text) > MAX_QUESTION_CHARS:
            problems.append(f"{where}: the question is longer than {MAX_QUESTION_CHARS} characters")
    gold: dict[str, int] = {}
    listed: set = set()
    if not entries:
        problems.append(f"{where}: gold lists no document")
    for doc, grade in entries:
        if not isinstance(doc, str) or not DOC_ID.fullmatch(doc):
            problems.append(f"{where}: {doc!r} is not a document id (letters, digits, '.', '_', '-', '/')")
            continue
        if doc in listed:
            problems.append(f"{where}: document {doc!r} is listed twice in gold")
            continue
        listed.add(doc)
        if known_docs is not None and doc not in known_docs:
            problems.append(f"{where}: document {doc!r} is not in the corpus")
        if grade is not None:
            gold[doc] = grade
    if entries and not any(g > 0 for g in gold.values()) and len(problems) == start:
        problems.append(f"{where}: no gold document has a grade above 0")
    if len(problems) != start:
        return None
    seen.add(qid)
    return Question(qid, text, gold)


def parse_questions_csv(text: str, known_docs: set[str] | None = None, source: str = "questions.csv") -> list[Question]:
    problems: list[str] = []
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    questions: list[Question] = []
    seen: set[str] = set()
    header: list[str] | None = None
    try:
        for row in reader:
            line = reader.line_num
            if header is None:
                header = [h.strip() for h in row]
                if sorted(header) != sorted(QUESTION_FIELDS):
                    problems.append(f"line {line}: the header must be exactly {','.join(QUESTION_FIELDS)} "
                                    f"(in any order), got {','.join(header)}")
                    break
                continue
            if not any(cell.strip() for cell in row):
                continue
            where = f"line {line}"
            if len(row) != len(header):
                problems.append(f"{where}: {len(row)} field(s), the header has {len(header)} "
                                "(a comma in a question needs quotes)")
                continue
            fields = dict(zip(header, row))
            start = len(problems)
            entries = _gold_from_cell(fields["gold"], where, problems)
            q = _question(fields["question_id"].strip(), fields["question"], entries, where, seen, known_docs,
                          problems, start)
            if q:
                questions.append(q)
    except csv.Error as exc:
        problems.append(f"line {reader.line_num}: not valid CSV ({exc})")
    if header is None:
        problems.append("the file is empty")
    elif not problems and not questions:
        problems.append("the file has no question")
    if problems:
        raise RetrievalInputError(source, problems)
    return questions


def parse_questions_jsonl(text: str, known_docs: set[str] | None = None,
                          source: str = "questions.jsonl") -> list[Question]:
    problems: list[str] = []
    questions: list[Question] = []
    seen: set[str] = set()
    for line, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        where = f"line {line}"
        try:
            doc = json.loads(raw)
        except ValueError as exc:
            problems.append(f"{where}: not valid JSON ({exc})")
            continue
        if not isinstance(doc, dict) or set(doc) != set(QUESTION_FIELDS):
            got = sorted(doc) if isinstance(doc, dict) else type(doc).__name__
            problems.append(f"{where}: an object with exactly the keys {', '.join(QUESTION_FIELDS)} is needed, got {got}")
            continue
        start = len(problems)
        entries = _gold_from_json(doc["gold"], where, problems)
        q = _question(doc["question_id"], doc["question"], entries, where, seen, known_docs, problems, start)
        if q:
            questions.append(q)
    if not problems and not questions:
        problems.append("the file has no question")
    if problems:
        raise RetrievalInputError(source, problems)
    return questions


def load_questions(path: Path, known_docs: set[str] | None = None) -> list[Question]:
    """Questions of a file (CSV or JSONL by extension), checked strictly; RetrievalInputError on any problem."""
    parse = {".csv": parse_questions_csv, ".jsonl": parse_questions_jsonl}.get(path.suffix)
    if parse is None:
        raise RetrievalInputError(str(path), [f"the extension must be .csv or .jsonl, got {path.suffix!r}"])
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise RetrievalInputError(str(path), [f"not UTF-8 text ({exc.reason})"]) from exc
    except FileNotFoundError as exc:
        raise RetrievalInputError(str(path), ["the file does not exist"]) from exc
    return parse(text, known_docs, str(path))


# -- corpora -------------------------------------------------------------------

def _unit(vec: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm else list(vec)


@dataclass
class Corpus:
    """Documents (id to text), directed edges (src, dst, type) between them, and the embeddings the graph keeps."""

    name: str
    texts: dict[str, str]
    edges: list[tuple[str, str, str]]
    stored: dict[str, list[float]] | None = None
    stored_model: str | None = None

    def __post_init__(self):
        self._out: dict[str, list[tuple[str, str]]] = {}
        self._in: dict[str, list[tuple[str, str]]] = {}
        for src, dst, kind in self.edges:
            self._out.setdefault(src, []).append((dst, kind))
            self._in.setdefault(dst, []).append((src, kind))

    def edge_types(self) -> set[str]:
        return {kind for _, _, kind in self.edges}

    def neighbours(self, doc: str, types: Iterable[str] | None = None, direction: str = "both") -> list[tuple[str, str]]:
        """(document, edge type) reachable in one step, sorted; every type when ``types`` is None."""
        wanted = None if types is None else set(types)
        found = []
        if direction in ("out", "both"):
            found += self._out.get(doc, [])
        if direction in ("in", "both"):
            found += self._in.get(doc, [])
        return sorted((d, t) for d, t in found if wanted is None or t in wanted)


def parse_documents(text: str, source: str = "documents.jsonl") -> dict[str, str]:
    problems: list[str] = []
    docs: dict[str, str] = {}
    for line, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            doc = json.loads(raw)
        except ValueError as exc:
            problems.append(f"line {line}: not valid JSON ({exc})")
            continue
        if not isinstance(doc, dict) or set(doc) != {"id", "text"}:
            problems.append(f"line {line}: an object with exactly the keys id and text is needed")
        elif not isinstance(doc["id"], str) or not DOC_ID.fullmatch(doc["id"]):
            problems.append(f"line {line}: {doc['id']!r} is not a document id")
        elif doc["id"] in docs:
            problems.append(f"line {line}: document {doc['id']!r} appears twice")
        elif not isinstance(doc["text"], str) or not doc["text"].strip():
            problems.append(f"line {line}: document {doc['id']!r} has no text")
        else:
            docs[doc["id"]] = doc["text"].strip()
    if not problems and not docs:
        problems.append("the file has no document")
    if problems:
        raise RetrievalInputError(source, problems)
    return docs


def parse_edges(text: str, docs: Iterable[str], source: str = "edges.csv") -> list[tuple[str, str, str]]:
    known = set(docs)
    problems: list[str] = []
    edges: list[tuple[str, str, str]] = []
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    header = None
    try:
        for row in reader:
            line = reader.line_num
            if header is None:
                header = [h.strip() for h in row]
                if header != ["src", "dst", "type"]:
                    problems.append(f"line {line}: the header must be exactly src,dst,type")
                    break
                continue
            if not any(cell.strip() for cell in row):
                continue
            if len(row) != 3:
                problems.append(f"line {line}: {len(row)} field(s), 3 are needed")
                continue
            src, dst, kind = (cell.strip() for cell in row)
            if src not in known or dst not in known:
                problems.append(f"line {line}: edge {src!r} -> {dst!r} names a document that is not in the corpus")
            elif src == dst:
                problems.append(f"line {line}: {src!r} is joined to itself")
            elif not EDGE_TYPE.fullmatch(kind):
                problems.append(f"line {line}: {kind!r} is not an edge type (lower-case letters, digits, '_')")
            elif (src, dst, kind) in edges:
                problems.append(f"line {line}: edge {src!r} -> {dst!r} of type {kind!r} appears twice")
            else:
                edges.append((src, dst, kind))
    except csv.Error as exc:
        problems.append(f"line {reader.line_num}: not valid CSV ({exc})")
    if problems:
        raise RetrievalInputError(source, problems)
    return edges


def _resolve(rel: str, root: Path | None) -> Path:
    return root / rel if root is not None else repo_path(rel)


def load_file_corpus(name: str, root: Path | None = None) -> Corpus:
    """Corpus of a folder with documents.jsonl (and edges.csv, if it has one)."""
    folder = f"lab/corpora/{name}"
    docs = parse_documents(_resolve(f"{folder}/documents.jsonl", root).read_text(encoding="utf-8-sig"),
                           f"{folder}/documents.jsonl")
    try:
        edges_text = _resolve(f"{folder}/edges.csv", root).read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        edges = []
    else:
        edges = parse_edges(edges_text, docs, f"{folder}/edges.csv")
    return Corpus(name, docs, edges)


def _vector(text: str | None) -> list[float] | None:
    return _unit([float(x) for x in text.strip("[]").split(",")]) if text else None


def load_graph_corpus(conn, tenant: str, corpus: str, text: str = "abstract") -> Corpus:
    """Papers of a corpus in the lab graph: the chosen text of each, the edges between papers, stored embeddings."""
    if text not in NODE:
        raise ValueError(f"text must be one of {', '.join(NODE)}, got {text!r}")
    rows = conn.execute(
        """SELECT metadata->>'arxiv_id' AS doc, body, embedding::text AS embedding FROM thoughts
           WHERE tenant_id = %s AND thought_type = %s AND metadata->>'corpus' = %s
           ORDER BY metadata->>'arxiv_id'""", (tenant, NODE[text], corpus)).fetchall()
    if not rows:
        raise RuntimeError(f"no {text} nodes for corpus {corpus!r} in the lab graph (exocortex lab corpus-graph)")
    texts = {r["doc"]: r["body"] for r in rows}
    nodes = {r["id"]: r["doc"] for r in conn.execute(
        """SELECT id::text AS id, metadata->>'arxiv_id' AS doc FROM thoughts WHERE tenant_id = %s
             AND thought_type = ANY(%s) AND metadata->>'corpus' = %s""",
        (tenant, list(NODE.values()), corpus)).fetchall()}
    edges = set()
    ids = list(nodes)
    for r in conn.execute(
            """SELECT src_id::text AS src, dst_id::text AS dst, type::text AS type FROM edges
               WHERE tenant_id = %s AND src_type = 'thought' AND dst_type = 'thought'
                 AND src_id = ANY(%s::uuid[]) AND dst_id = ANY(%s::uuid[])""", (tenant, ids, ids)).fetchall():
        a, b = nodes[r["src"]], nodes[r["dst"]]
        if a != b and a in texts and b in texts:  # abstract and summary of one paper are one document
            edges.add((a, b, r["type"]))
    stored = {r["doc"]: vec for r in rows if (vec := _vector(r["embedding"])) is not None}
    return Corpus(corpus, texts, sorted(edges), stored, STORED_MODEL)


def corpus_doc_ids(corpus: str, index: str, root: Path | None = None) -> set[str]:
    """Document ids that gold answers may name: from documents.jsonl (files) or manifest.csv (graph)."""
    if index == "files":
        return set(load_file_corpus(corpus, root).texts)
    with _resolve(f"lab/corpora/{corpus}/manifest.csv", root).open(encoding="utf-8-sig", newline="") as fh:
        return {row["arxiv_id"] for row in csv.DictReader(fh)}


# -- embeddings ----------------------------------------------------------------

_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset((
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "does", "do", "for", "from", "how", "in", "into", "is",
    "it", "its", "of", "on", "or", "that", "the", "this", "to", "was", "were", "what", "when", "which", "who", "why",
    "with"))


def hash_embed(texts: list[str], dim: int) -> list[list[float]]:
    """Unit vectors of hashed word counts, common words left out: deterministic, offline, and only a stand-in
    for real embeddings (words that hash to the same place count as the same word)."""
    out = []
    for text in texts:
        vec = [0.0] * dim
        for token in _TOKEN.findall(text.lower()):
            if token in _STOPWORDS:
                continue
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            vec[int.from_bytes(digest, "big") % dim] += 1.0
        out.append(_unit(vec))
    return out


OFFLINE_EMBEDDERS: dict[str, Callable[[list[str]], list[list[float]]]] = {
    "toy-hash-64": partial(hash_embed, dim=64),
    "toy-hash-16": partial(hash_embed, dim=16),
}


# -- configurations and the ranking --------------------------------------------

@dataclass(frozen=True)
class Expansion:
    seed_k: int = 5
    hops: int = 1
    decay: float = 0.5
    direction: str = "both"
    edge_types: tuple[str, ...] | None = None


@dataclass(frozen=True)
class Settings:
    text: str
    depth: int
    expansion: Expansion | None


def _int(value, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{name} must be an integer from {low} to {high}, got {value!r}")
    return value


def config_settings(params: Mapping | None, experiment_params: Mapping | None = None) -> Settings:
    """Settings of a configuration from its params (ValueError on anything unknown or out of range)."""
    params, experiment_params = params or {}, experiment_params or {}
    unknown = set(params) - CONFIG_PARAMS
    if unknown:
        raise ValueError(f"unknown params {', '.join(sorted(unknown))}; known: {', '.join(sorted(CONFIG_PARAMS))}")
    text = params.get("text", experiment_params.get("text", "abstract"))
    if text not in NODE:
        raise ValueError(f"text must be one of {', '.join(NODE)}, got {text!r}")
    depth = _int(params.get("depth", DEFAULT_DEPTH), "depth", rm.NDCG_K, 1000)
    raw = params.get("expansion")
    if raw is None:
        return Settings(text, depth, None)
    if not isinstance(raw, dict):
        raise ValueError("expansion must be a mapping or null")  # noqa: TRY004 - one error type for every bad param
    unknown = set(raw) - EXPANSION_PARAMS
    if unknown:
        raise ValueError(f"unknown expansion params {', '.join(sorted(unknown))}; "
                         f"known: {', '.join(sorted(EXPANSION_PARAMS))}")
    decay = raw.get("decay", Expansion.decay)
    if isinstance(decay, bool) or not isinstance(decay, (int, float)) or not 0 < decay <= 1:
        raise ValueError(f"decay must be a number above 0 and at most 1, got {decay!r}")
    direction = raw.get("direction", Expansion.direction)
    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be one of {', '.join(DIRECTIONS)}, got {direction!r}")
    types = raw.get("edge_types")
    if types is not None:
        if (not isinstance(types, list) or not types or len(set(types)) != len(types)
                or not all(isinstance(t, str) and EDGE_TYPE.fullmatch(t) for t in types)):
            raise ValueError(f"edge_types must be a non-empty list of distinct edge type names, got {types!r}")
        types = tuple(types)
    seed_k = _int(raw.get("seed_k", Expansion.seed_k), "seed_k", 1, depth)
    return Settings(text, depth, Expansion(seed_k, _int(raw.get("hops", Expansion.hops), "hops", 1, 3),
                                           float(decay), direction, types))


def retrieve(corpus: Corpus, vectors: Mapping[str, Sequence[float]], question: Sequence[float],
             expansion: Expansion | None = None, depth: int = DEFAULT_DEPTH) -> list[dict]:
    """The ranking for one question: [{"doc", "score", "via"}], best first, at most ``depth`` long.

    Scores are dot products of unit vectors. See the module docstring for the expansion.
    """
    direct = {}
    for doc, vec in vectors.items():
        if len(vec) != len(question):
            raise ValueError(f"embedding of {doc!r} has {len(vec)} dimensions, the question has {len(question)}")
        direct[doc] = sum(a * b for a, b in zip(question, vec))
    final = dict(direct)
    via = {doc: "embedding" for doc in direct}
    if expansion is not None:
        frontier = {doc: max(direct[doc], 0.0) for doc in rm.rank_by_score(direct)[:expansion.seed_k]}
        for _ in range(expansion.hops):
            reached: dict[str, tuple[float, str]] = {}
            for doc in sorted(frontier):
                for neighbour, kind in corpus.neighbours(doc, expansion.edge_types, expansion.direction):
                    score = frontier[doc] * expansion.decay
                    known = reached.get(neighbour)
                    if known is None or score > known[0] or (score == known[0] and kind < known[1]):
                        reached[neighbour] = (score, kind)
            for neighbour, (score, kind) in sorted(reached.items()):
                if score > final[neighbour]:
                    final[neighbour], via[neighbour] = score, f"expansion:{kind}"
            frontier = {doc: score for doc, (score, _) in reached.items()}
    return [{"doc": doc, "score": final[doc], "via": via[doc]} for doc in rm.rank_by_score(final)[:depth]]


# -- spec ----------------------------------------------------------------------

def _models(models: dict | None) -> dict:
    if models is not None:
        return models
    from exocortex.lab.llm_gateway import load_models

    return load_models(repo_path("lab/models.yaml"))


def check_spec(spec: dict, *, root: Path | None = None, models: dict | None = None) -> list[str]:
    """Every problem of a retrieval spec, empty when it can run.

    Checks the keys, the configurations (names as the run unit takes them, models from lab/models.yaml or
    the offline toy models, params), the metric settings, and, in the corpus folder, the corpus and every
    question set (strictly, gold ids against the corpus, no question in two samples).
    """
    problems: list[str] = []
    if spec.get("kind") != KIND:
        problems.append(f"kind must be {KIND!r}, got {spec.get('kind')!r}")
    params = spec.get("params") or {}
    if not isinstance(params, dict):
        return problems + ["params must be a mapping"]
    unknown = set(params) - EXPERIMENT_PARAMS
    if unknown:
        problems.append(f"params: unknown {', '.join(sorted(unknown))}; known: {', '.join(sorted(EXPERIMENT_PARAMS))}")
    slug = spec.get("slug")
    if not isinstance(slug, str) or not NAME.fullmatch(slug):
        problems.append(f"slug must be lower-case letters, digits and '-', got {slug!r}")
    corpus, index = params.get("corpus"), params.get("index", "graph")
    if not isinstance(corpus, str) or not NAME.fullmatch(corpus):
        problems.append(f"params.corpus must name a folder of lab/corpora/, got {corpus!r}")
        corpus = None
    if index not in INDEXES:
        problems.append(f"params.index must be one of {', '.join(INDEXES)}, got {index!r}")
        index = None
    known_docs, edge_types = None, None
    if corpus and index:
        try:
            if index == "files":
                loaded = load_file_corpus(corpus, root)
                known_docs, edge_types = set(loaded.texts), loaded.edge_types()
            else:
                known_docs = corpus_doc_ids(corpus, index, root)
        except RetrievalInputError as exc:
            problems += [f"corpus {corpus}: {p}" for p in exc.problems]
        except (OSError, KeyError) as exc:
            problems.append(f"corpus {corpus}: cannot read its documents ({type(exc).__name__}: {exc})")
    ks: list[int] = list(rm.DEFAULT_RECALL_K)
    baseline = None
    try:
        ks, _, baseline = rm.settings(params)
    except (ValueError, TypeError) as exc:
        problems.append(f"params: {exc}")
    problems += _check_configs(spec, params, ks, baseline, edge_types, models, slug)
    problems += _check_samples(spec, corpus, known_docs, root)
    return problems


def _check_configs(spec: dict, params: dict, ks: list[int], baseline, edge_types, models, slug) -> list[str]:
    problems: list[str] = []
    configs = spec.get("configs")
    if not isinstance(configs, list) or not configs:
        return problems + ["configs: at least one configuration is needed"]
    try:
        registry = _models(models)
    except (OSError, ValueError) as exc:
        registry = {}
        problems.append(f"lab/models.yaml cannot be loaded ({exc})")
    names: list[str] = []
    for i, cfg in enumerate(configs):
        name = cfg.get("name") if isinstance(cfg, dict) else None
        where = f"config {name if isinstance(name, str) else f'#{i + 1}'}"
        if not isinstance(cfg, dict):
            problems.append(f"{where}: must be a mapping")
            continue
        if extra := set(cfg) - CONFIG_KEYS:
            problems.append(f"{where}: unknown keys {', '.join(sorted(extra))}")
        if not isinstance(name, str) or not NAME.fullmatch(name):
            problems.append(f"{where}: name must be lower-case letters, digits and '-' (the run unit's instance "
                            "name allows nothing else)")
        elif name in names:
            problems.append(f"{where}: the name is used twice")
        else:
            names.append(name)
        problems += [f"{where}: {p}" for p in _check_model(cfg, registry, slug)]
        try:
            settings = config_settings(cfg.get("params"), params)
        except ValueError as exc:
            problems.append(f"{where}: {exc}")
            continue
        if settings.depth < max(ks):
            problems.append(f"{where}: depth {settings.depth} is below the recall cutoff {max(ks)}")
        if settings.expansion and settings.expansion.edge_types and edge_types is not None:
            absent = sorted(set(settings.expansion.edge_types) - edge_types)
            if absent:
                problems.append(f"{where}: the corpus has no edge of type {', '.join(absent)}; "
                                f"it has {', '.join(sorted(edge_types)) or 'no edges'}")
    if baseline is not None and baseline not in names:
        problems.append(f"params.baseline {baseline!r} is not a configuration")
    return problems


def _check_model(cfg: dict, registry: dict, slug) -> list[str]:
    from exocortex.lab.llm_gateway import LOCAL, ModelNotAllowed, authorize

    model, provider = cfg.get("model"), cfg.get("provider", "local")
    if not isinstance(model, str) or not model:
        return ["model (the embedding model) is required"]
    if model in OFFLINE_EMBEDDERS:
        return [] if provider == "none" else [f"{model} is computed in the process: provider must be 'none'"]
    try:
        entry = authorize(registry, model, "public", slug)
    except ModelNotAllowed as exc:
        return [str(exc)]
    expected = "local" if entry.get("provider", LOCAL) == LOCAL else "remote"
    return [] if provider == expected else [f"{model} is {expected} in lab/models.yaml: provider must be {expected!r}"]


def _sample_path(sample: dict, corpus: str | None) -> tuple[str | None, str | None]:
    items = sample.get("items")
    if not isinstance(items, str) or not items:
        return None, "items: the question set file is required"
    parts = PurePosixPath(items).parts
    if corpus and (len(parts) != 4 or parts[:3] != ("lab", "corpora", corpus) or ".." in parts):
        return None, f"items: the question set must be a file directly in lab/corpora/{corpus}/, got {items!r}"
    return items, None


def _check_samples(spec: dict, corpus: str | None, known_docs: set[str] | None, root: Path | None) -> list[str]:
    problems: list[str] = []
    samples = spec.get("samples")
    if not isinstance(samples, list) or not samples:
        return ["samples: at least one sample is needed"]
    names: list[str] = []
    owner: dict[str, str] = {}
    for i, sample in enumerate(samples):
        name = sample.get("name") if isinstance(sample, dict) else None
        where = f"sample {name if isinstance(name, str) else f'#{i + 1}'}"
        if not isinstance(sample, dict):
            problems.append(f"{where}: must be a mapping")
            continue
        if not isinstance(name, str) or not NAME.fullmatch(name):
            problems.append(f"{where}: name must be lower-case letters, digits and '-'")
        elif name in names:
            problems.append(f"{where}: the name is used twice")
        else:
            names.append(name)
        if sample.get("role") not in ROLES:
            problems.append(f"{where}: role must be one of {', '.join(ROLES)}")
        elif sample["role"] == "control" and not spec.get("hypothesis"):
            problems.append(f"{where}: a control sample belongs to a hypothesis, and the spec has none")
        if isinstance(sample.get("seed"), bool) or not isinstance(sample.get("seed"), int):
            problems.append(f"{where}: seed must be an integer")
        if not isinstance(sample.get("method"), str) or not sample["method"].strip():
            problems.append(f"{where}: method (how the questions were chosen) is required")
        rel, problem = _sample_path(sample, corpus)
        if problem or rel is None:
            problems.append(f"{where}: {problem}")
            continue
        try:
            questions = load_questions(_resolve(rel, root), known_docs)
        except RetrievalInputError as exc:
            problems += [f"{where}, {rel}: {p}" for p in exc.problems]
            continue
        except OSError as exc:
            problems.append(f"{where}: cannot read {rel} ({exc})")
            continue
        for q in questions:
            if q.id in owner:
                problems.append(f"{where}: question {q.id!r} is also in sample {owner[q.id]}")
            owner.setdefault(q.id, str(name))
    return problems


def sample_items(spec: dict, sample: dict, root: Path | None = None) -> list[dict]:
    """Members of a sample for exocortex.lab.experiments.create_sample: the questions of its file, in file order.

    The member's checksum covers the question and its gold answers, so changing either after the sample was
    stored is refused (SampleMismatch). The payload keeps both for the runner.
    """
    params = spec.get("params") or {}
    known = corpus_doc_ids(params["corpus"], params.get("index", "graph"), root)
    rel, problem = _sample_path(sample, params.get("corpus"))
    if problem or rel is None:
        raise RetrievalInputError(sample.get("name", "sample"), [problem or "items: the question set file is required"])
    return [{"item_id": q.id, "stratum": None, "content_sha256": content_sha256(q),
             "payload": {"question": q.text, "gold": q.gold}}
            for q in load_questions(_resolve(rel, root), known)]


# -- runner --------------------------------------------------------------------

def _payload_question(item: dict) -> Question:
    payload = item.get("payload") or {}
    question = Question(item["item_id"], payload.get("question", ""), dict(payload.get("gold") or {}))
    if content_sha256(question) != item["content_sha256"]:
        raise RuntimeError(f"question {item['item_id']} does not match the checksum stored with the sample")
    return question


def make_runner(conn, tenant: str, llm=None, root: Path | None = None):
    """Queue runner of the kind: one job ranks the corpus for one question with one configuration.

    Corpora and document embeddings are kept per process, so the jobs of one embedding model, which the queue
    hands out together, embed each document once. Anything that stops a valid ranking (a corpus that cannot be
    loaded, a changed question, a failed embedding call) raises: the queue retries and then marks the job as
    an error, and the run as failed. Nothing is guessed.
    """
    corpora: dict[tuple, Corpus] = {}
    vectors: dict[tuple, dict[str, list[float]]] = {}
    clients: list = [llm]

    def embedder(model: str) -> Callable[[list[str]], list[list[float]]]:
        if model in OFFLINE_EMBEDDERS:
            return OFFLINE_EMBEDDERS[model]
        if clients[0] is None:
            from exocortex.lab.llm import LabLLM

            clients[0] = LabLLM()
        return lambda texts: clients[0].embed(model, texts)

    def corpus_for(params: dict, text: str) -> tuple[tuple, Corpus]:
        name, index = str(params.get("corpus")), params.get("index", "graph")
        key = (name, index, text if index == "graph" else "")
        if key not in corpora:
            corpora[key] = load_file_corpus(name, root) if index == "files" else load_graph_corpus(conn, tenant, name, text)
        return key, corpora[key]

    def vectors_for(key: tuple, corpus: Corpus, model: str) -> dict[str, list[float]]:
        if (key, model) not in vectors:
            if corpus.stored and model == corpus.stored_model and set(corpus.stored) == set(corpus.texts):
                vectors[key, model] = corpus.stored
            else:
                docs = sorted(corpus.texts)
                vectors[key, model] = dict(zip(docs, (_unit(v) for v in embedder(model)([corpus.texts[d] for d in docs]))))
        return vectors[key, model]

    def run(job: dict, item: dict) -> dict:
        started = time.monotonic()
        cfg, params = job["config"], job["experiment"]["params"] or {}
        settings = config_settings(cfg.get("params"), params)
        question = _payload_question(item)
        key, corpus = corpus_for(params, settings.text)
        if missing := sorted(set(question.gold) - set(corpus.texts)):
            raise RuntimeError(f"gold documents of {question.id} are not in corpus {key[0]}: {', '.join(missing)}")
        wanted = settings.expansion.edge_types if settings.expansion else None
        if wanted and (absent := sorted(set(wanted) - corpus.edge_types())):
            raise RuntimeError(f"corpus {key[0]} has no edge of type {', '.join(absent)}")
        model = cfg["model"]
        docs = vectors_for(key, corpus, model)
        qvec = _unit(embedder(model)([question.text])[0])
        ranking = retrieve(corpus, docs, qvec, settings.expansion, settings.depth)
        offline = model in OFFLINE_EMBEDDERS
        output = {"question": question.id, "ranking": ranking, "gold": question.gold, "depth": settings.depth,
                  "documents": len(corpus.texts),
                  "expansion": None if settings.expansion is None else {
                      "seed_k": settings.expansion.seed_k, "hops": settings.expansion.hops,
                      "decay": settings.expansion.decay, "direction": settings.expansion.direction,
                      "edge_types": list(settings.expansion.edge_types) if settings.expansion.edge_types else None}}
        return {"ok": True, "output": output, "model": model, "provider": cfg.get("provider") or "local",
                "base_url": None if offline or clients[0] is None else clients[0].url,
                "latency_ms": round((time.monotonic() - started) * 1000)}

    return run


# -- metrics and summary -------------------------------------------------------

def compute_metrics(conn, run_uuid: str) -> list[str]:
    """Store the retrieval metrics of a run; returns their result ids (exocortex/lab/metrics.py conventions).

    A job that ended in an error has no result; it counts as a failed item in the details of each metric.
    """
    run = conn.execute("SELECT r.run_id, e.slug, e.params FROM exp_runs r JOIN experiments e ON e.id = r.experiment_id "
                       "WHERE r.id = %s", (run_uuid,)).fetchone()
    rows = conn.execute(
        """SELECT c.id AS config_id, c.name, j.item_id, res.ok, res.output FROM exp_jobs j
           JOIN exp_configs c ON c.id = j.config_id LEFT JOIN exp_results res ON res.job_id = j.id
           WHERE j.run_id = %s ORDER BY c.name, j.item_id""", (run_uuid,)).fetchall()
    config_ids = {r["name"]: str(r["config_id"]) for r in rows}
    plain = [{"config": r["name"], "item_id": r["item_id"], "ok": bool(r["ok"]),
              "ranking": [e["doc"] for e in (r["output"] or {}).get("ranking") or []],
              "gold": (r["output"] or {}).get("gold") or {}} for r in rows]
    ks, seed, baseline = rm.settings(run["params"])
    ids = []
    for m in rm.retrieval_metrics(plain, f"{run['slug']}/{run['run_id']}", ks, seed, baseline):
        ex.record_metric(conn, m["result_id"], run_uuid, config_ids.get(m["config"]), m["metric"], m["value"],
                         m["ci_low"], m["ci_high"], m["n"], m["method"], m["details"])
        ids.append(m["result_id"])
    return ids


def summary(conn, slug: str, run_id: str | None = None) -> dict:
    """The metrics of a run (default: the newest one that is finished), per configuration and as differences.

    Computes and stores them first when the run is finished and has none yet.
    """
    exp = conn.execute("SELECT id, kind FROM experiments WHERE slug = %s", (slug,)).fetchone()
    if exp is None or exp["kind"] != KIND:
        raise LookupError(f"no experiment of kind {KIND} named {slug!r}")
    run = conn.execute(
        """SELECT id, run_id, status FROM exp_runs WHERE experiment_id = %s
             AND ((%s::text IS NULL AND status IN ('done', 'failed')) OR run_id = %s)
           ORDER BY created_at DESC LIMIT 1""", (exp["id"], run_id, run_id)).fetchone()
    if run is None:
        raise LookupError(f"no {'run ' + run_id if run_id else 'finished run'} of {slug}")
    have = conn.execute("SELECT count(*) AS n FROM exp_metrics WHERE run_id = %s", (run["id"],)).fetchone()["n"]
    if not have and run["status"] in ("done", "failed"):
        compute_metrics(conn, str(run["id"]))
    jobs = {r["status"]: r["n"] for r in conn.execute(
        "SELECT status, count(*) AS n FROM exp_jobs WHERE run_id = %s GROUP BY status", (run["id"],)).fetchall()}
    configs: dict[str, dict] = {}
    differences = []
    for m in conn.execute(
            """SELECT m.result_id, c.name AS config, m.metric, m.value, m.ci_low, m.ci_high, m.n, m.details
               FROM exp_metrics m LEFT JOIN exp_configs c ON c.id = m.config_id WHERE m.run_id = %s
               ORDER BY m.result_id""", (run["id"],)).fetchall():
        entry = {"value": m["value"], "ci_low": m["ci_low"], "ci_high": m["ci_high"], "n": m["n"],
                 "result_id": m["result_id"]}
        if m["config"] is None:
            differences.append({"metric": m["metric"], "a": m["details"].get("a"), "b": m["details"].get("b"), **entry})
        else:
            configs.setdefault(m["config"], {})[m["metric"]] = entry
    return {"experiment": slug, "run": run["run_id"], "status": run["status"], "jobs": jobs, "configs": configs,
            "differences": differences}
