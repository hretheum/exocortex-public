# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Experiment kind ``format_conformity``: does the model's answer match a schema (roadmap task F5.9).

An item of the experiment is a prompt and a reference to a JSON Schema. A configuration names the model and
says whether the answer format is forced by the model server (``json_schema`` or ``grammar``) or free. The
runner sends the prompt through the lab gateway (exocortex/lab/llm.py: the only way out), stores the raw
answer, and a strict mechanical validator decides, with no human rating: conforming, non conforming (with the
reasons), or no answer. The share of conforming answers per configuration comes with a Wilson interval and
the difference between configurations with a paired Newcombe interval (format_conformity_metrics.py).
results.csv keeps every raw answer with its verdict and reasons, so every number can be recomputed
(lab/recompute.py, ``lab/independent_format_check.py``).

Input files
-----------

Everything the experiment reads is in its corpus folder, ``lab/corpora/<corpus>/``:

- ``schemas/<name>.json``: one JSON Schema per file, a name is lower-case letters, digits and ``-``;
- one prompt file per sample, named by the ``items:`` of the spec (no item may be in two samples).

A prompt file is ``*.csv`` with the header ``item_id,prompt,schema`` and optionally ``grammar`` (any order)::

    item_id,prompt,schema,grammar
    t01,"Classify this ticket: the invoice shows a double charge.",ticket,ticket-gbnf

or ``*.jsonl``, one object per line with the same keys. Files are read strictly: the whole file is checked,
every problem is reported with its line, and an experiment whose files have any problem does not run.

- ``item_id``: letters, digits, ``.``, ``_`` and ``-``, at most 64, unique in the file and across the samples;
- ``prompt``: text, at most 20000 characters, line breaks allowed, other control characters not;
- ``schema``: the name of a file in ``schemas/``;
- ``grammar``: optional label of a GBNF grammar (the same character set as an item id). It is a label only: it
  is stored with the item and its answer, and nothing is sent to the model because of it.

Schemas are JSON Schema draft 2020-12, checked against its meta-schema and then against the supported
subset, which is what the validator and the independent calculation both implement: ``type``, ``properties``,
``required``, ``additionalProperties``, ``enum``, ``const``, ``items``, ``minItems``, ``maxItems``,
``minLength``, ``maxLength``, ``pattern``, ``minimum``, ``maximum``, ``exclusiveMinimum``,
``exclusiveMaximum``, and the annotations ``title``, ``description``, ``$comment``. Any other keyword is an
error, not silently ignored (a misspelt ``requird`` would otherwise make every answer conform). Formats are
not asserted, and there are no ``$ref``s, so the validator never reads anything but the schema.

Validator
---------

Strict, in two stages. The whole answer (leading and trailing white space aside) must be one JSON value.
Otherwise it does not conform, and the reason says how: ``code_fence`` (the JSON is inside a Markdown fence),
``text_around_json`` (there is JSON, with text before or after it), ``truncated`` (the model stopped at its
token limit), ``non_finite_number`` (NaN, Infinity or a number too large for a double), ``not_json`` (prose
instead of JSON). A repeated key in an object is ``duplicate_key``. A JSON value is then checked against the
schema, and each violation is a reason: ``wrong_type``, ``missing_field``, ``extra_field``, ``bad_value``
(``enum``, ``const``), ``out_of_range`` (``minimum``, ``maximum``, ``exclusiveMinimum``, ``exclusiveMaximum``),
``bad_length`` (``minLength``, ``maxLength``, ``minItems``, ``maxItems``), ``bad_pattern``. A reason has the
code, the JSON pointer of the place and a short detail; an answer can have several. An empty reply is ``no
answer``: the result is stored with ``ok`` false. A model call that fails before any reply arrives (gateway
down, HTTP error) raises, and the queue retries it and then marks the job as an error: a failed job, counted
in the details of the metrics.

Configurations
--------------

``model`` is a chat model from lab/models.yaml, through the lab gateway, or a model named ``toy-*`` below,
which is computed in the process with no network (the toy experiment uses them; they say nothing about real
models). Params of a configuration:

- ``format`` (required): ``free`` (the answer is not constrained), ``json_schema`` (the OpenAI-style
  ``response_format`` with the schema, which the local model server compiles to a grammar) or ``grammar``
  (the server's native ``json_schema`` request field, sampled through a grammar; see the PR notes for the
  open question whether raw GBNF text should be sent instead);
- ``show_schema`` (default true): whether the system prompt shows the schema to the model, in every format,
  so that the formats differ in forcing and not in what the model was told;
- ``max_tokens`` (default 1024), ``temperature`` (default 0.0), ``seed`` (default none).

Guard metric
------------

``params.guard`` links the experiment to the claims kind::

    guard: {experiment: <slug of a claims experiment>, metric: <metric name>}

It names the metric of a claims experiment that guards this one (claim quality: forcing a format must not
make the claims worse). It is checked when the spec is loaded (the slug must have a spec in
``lab/experiments/`` of the kind ``claims``; the metric is a name such as ``usable_per_document``), stored
with the experiment's params (datapackage.json), and every run stores a reference row
``<experiment>/<run>/guard/<claims experiment>/<metric>`` with the metric ``guard:<claims experiment>/<metric>``,
no value and the method ``reference``, so pages and metrics.csv carry the link. The number is computed by the
claims kind, not here.

Spec example (see lab/experiments/toy-format.yaml)::

    slug: toy-format
    kind: format_conformity
    title: "Toy experiment: answer format conformity"
    hypothesis: null
    params:
      corpus: toy-format
      baseline: free                # differences to this one; default every pair
      guard: {experiment: intent-vs-fact, metric: usable_per_document}
    configs:
      - {name: free, model: toy-answerer, provider: none, variant: free, params: {format: free}}
      - {name: schema-forced, model: toy-answerer, provider: none, variant: json_schema,
         params: {format: json_schema}}
    samples:
      - {name: test-36, role: test, seed: 0, method: "written by hand",
         items: lab/corpora/toy-format/prompts-test.csv}

Metrics: see format_conformity_metrics.py.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from exocortex.lab import experiments as ex
from exocortex.lab import format_conformity_metrics as fm
from exocortex.lab.claims import repo_path

KIND = "format_conformity"
NAME = re.compile(r"[a-z0-9][a-z0-9-]*")  # experiment, sample, configuration and schema names
ITEM_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
LABEL = ITEM_ID
GUARD_METRIC = re.compile(r"[a-z][a-z0-9_]*")
ITEM_FIELDS = ("item_id", "prompt", "schema", "grammar")
REQUIRED_FIELDS = ("item_id", "prompt", "schema")
MAX_PROMPT_CHARS = 20000
MAX_REASONS = 50
MAX_DETAIL_CHARS = 200
ROLES = ("tuning", "control", "pilot", "test", "blind")
FORMATS = ("free", "json_schema", "grammar")
EXPERIMENT_PARAMS = {"corpus", "baseline", "guard"}
CONFIG_KEYS = {"name", "model", "provider", "variant", "params"}
CONFIG_PARAMS = {"format", "max_tokens", "temperature", "seed", "show_schema"}
DEFAULT_MAX_TOKENS = 1024
DRAFT = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_KEYWORDS = frozenset((
    "$schema", "$comment", "title", "description", "type", "properties", "required", "additionalProperties",
    "enum", "const", "items", "minItems", "maxItems", "minLength", "maxLength", "pattern", "minimum", "maximum",
    "exclusiveMinimum", "exclusiveMaximum"))
MAX_REPORTED = 20
SYSTEM = "Reply with one JSON value and nothing else: no explanation and no Markdown code fence."
SYSTEM_WITH_SCHEMA = SYSTEM + "\nThe JSON value must match this JSON Schema:\n{schema}"

REASON_OF_KEYWORD = {
    "type": "wrong_type", "required": "missing_field", "additionalProperties": "extra_field", "enum": "bad_value",
    "const": "bad_value", "minimum": "out_of_range", "maximum": "out_of_range",
    "exclusiveMinimum": "out_of_range", "exclusiveMaximum": "out_of_range", "minLength": "bad_length",
    "maxLength": "bad_length", "minItems": "bad_length", "maxItems": "bad_length", "pattern": "bad_pattern"}
JSON_STAGE_CODES = ("code_fence", "text_around_json", "truncated", "non_finite_number", "not_json")


class FormatInputError(ValueError):
    """A prompt file, schema file or spec that does not pass the checks; ``problems`` lists every one."""

    def __init__(self, source: str, problems: Sequence[str]):
        self.source, self.problems = source, list(problems)
        shown = self.problems[:MAX_REPORTED]
        more = f"\n- ... and {len(self.problems) - MAX_REPORTED} more" if len(self.problems) > MAX_REPORTED else ""
        super().__init__(f"{source}: {len(self.problems)} problem(s)\n" + "\n".join(f"- {p}" for p in shown) + more)


def _resolve(rel: str, root: Path | None) -> Path:
    return root / rel if root is not None else repo_path(rel)


# -- strict JSON ---------------------------------------------------------------

class _NonFinite(ValueError):
    """NaN, Infinity or a number that does not fit a double: JSON has none of these."""


def _reject_constant(name: str):
    raise _NonFinite(name)


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise _NonFinite(text)
    return value


def loads_strict(text: str) -> tuple[Any, list[str]]:
    """(value, repeated keys) of a JSON text; ValueError (or RecursionError) when it is not JSON.

    Stricter than ``json.loads``: NaN, Infinity and numbers beyond a double raise ``_NonFinite``.
    """
    repeated: list[str] = []

    def pairs(items: list[tuple[str, Any]]) -> dict:
        seen: set[str] = set()
        for key, _ in items:
            if key in seen:
                repeated.append(key)
            seen.add(key)
        return dict(items)

    value = json.loads(text, object_pairs_hook=pairs, parse_constant=_reject_constant, parse_float=_finite_float)
    return value, repeated


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_of(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _pointer(parts: Sequence[Any]) -> str:
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


# -- schemas -------------------------------------------------------------------

def _subset_problems(node: Any, where: str, problems: list[str], root: bool = True) -> None:
    here = where or "(root)"
    if not isinstance(node, dict):
        problems.append(f"{here}: a schema must be an object")
        return
    for key in node:
        if key not in SCHEMA_KEYWORDS:
            problems.append(f"{here}: keyword {key!r} is not supported; supported: {', '.join(sorted(SCHEMA_KEYWORDS))}")
    if "$schema" in node and (not root or node["$schema"] != DRAFT):
        problems.append(f"{here}: $schema may only be {DRAFT!r}, at the root")
    if isinstance(node.get("pattern"), str):
        try:
            re.compile(node["pattern"])
        except re.error as exc:
            problems.append(f"{here}: pattern does not compile ({exc})")
    if isinstance(node.get("properties"), dict):
        for name, sub in node["properties"].items():
            _subset_problems(sub, f"{where}/properties/{name}", problems, root=False)
    for key in ("items", "additionalProperties"):
        if isinstance(node.get(key), dict):
            _subset_problems(node[key], f"{where}/{key}", problems, root=False)


def parse_schema(text: str, source: str = "schema.json") -> dict:
    """A schema from its file's text, checked: JSON (no repeated keys), meta-schema, supported subset."""
    try:
        schema, repeated = loads_strict(text)
    except json.JSONDecodeError as exc:
        raise FormatInputError(source, [f"line {exc.lineno}: not valid JSON ({exc.msg})"]) from exc
    except (ValueError, RecursionError) as exc:
        raise FormatInputError(source, [f"not valid JSON ({exc})"]) from exc
    problems: list[str] = []
    if repeated:
        problems.append(f"a key is repeated: {', '.join(sorted(set(repeated)))}")
    if not isinstance(schema, dict):
        raise FormatInputError(source, [*problems, "the schema must be a JSON object"])
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        problems.append(f"not a valid JSON Schema ({exc.message[:MAX_DETAIL_CHARS]} at {_pointer(exc.absolute_path) or '(root)'})")
    else:
        _subset_problems(schema, "", problems)
    if problems:
        raise FormatInputError(source, problems)
    return schema


def schema_files(corpus: str, root: Path | None = None) -> dict[str, Path]:
    """Schema files of a corpus folder by name."""
    folder = _resolve(f"lab/corpora/{corpus}/schemas", root)
    return {p.stem: p for p in sorted(folder.glob("*.json"))}


def load_schema(corpus: str, name: str, root: Path | None = None) -> tuple[dict, str]:
    """(schema, SHA-256 of its canonical JSON) of ``schemas/<name>.json`` in the corpus folder."""
    path = schema_files(corpus, root).get(name)
    if path is None:
        raise FormatInputError(f"lab/corpora/{corpus}/schemas", [f"no schema {name!r}"])
    try:
        schema = parse_schema(path.read_text(encoding="utf-8-sig"), f"lab/corpora/{corpus}/schemas/{name}.json")
    except UnicodeDecodeError as exc:
        raise FormatInputError(str(path), [f"not UTF-8 text ({exc.reason})"]) from exc
    return schema, sha256_of(schema)


def load_schemas(corpus: str, root: Path | None = None) -> tuple[dict[str, tuple[dict, str]], list[str]]:
    """Every schema of the corpus folder that loads, and the problems of those that do not."""
    found: dict[str, tuple[dict, str]] = {}
    problems: list[str] = []
    for name in schema_files(corpus, root):
        if not NAME.fullmatch(name):
            problems.append(f"schemas/{name}.json: the name must be lower-case letters, digits and '-'")
            continue
        try:
            found[name] = load_schema(corpus, name, root)
        except FormatInputError as exc:
            problems += [f"schemas/{name}.json: {p}" for p in exc.problems]
    return found, problems


# -- prompt files --------------------------------------------------------------

@dataclass(frozen=True)
class Item:
    id: str
    prompt: str
    schema: str
    grammar: str | None = None


def content_sha256(item: Item, schema_sha256: str) -> str:
    """Checksum of an item with the schema it is judged against: what a sample member stands for."""
    return sha256_of({"prompt": item.prompt, "schema": item.schema, "schema_sha256": schema_sha256,
                      "grammar": item.grammar})


def _item(fields: Mapping[str, Any], where: str, seen: set[str], known_schemas: set[str] | None,
          problems: list[str]) -> Item | None:
    start = len(problems)
    item_id, prompt, schema, grammar = (fields.get(k) for k in ITEM_FIELDS)
    if not isinstance(item_id, str) or not ITEM_ID.fullmatch(item_id):
        problems.append(f"{where}: item_id must be letters, digits, '.', '_' or '-' (at most 64), got {item_id!r}")
    elif item_id in seen:
        problems.append(f"{where}: item_id {item_id!r} is used twice")
    if not isinstance(prompt, str) or not prompt.strip():
        problems.append(f"{where}: the prompt is empty")
    else:
        prompt = prompt.strip()
        if not all(c.isprintable() or c in "\n\t" for c in prompt):
            problems.append(f"{where}: the prompt has a control character other than a line break or a tab")
        if len(prompt) > MAX_PROMPT_CHARS:
            problems.append(f"{where}: the prompt is longer than {MAX_PROMPT_CHARS} characters")
    if not isinstance(schema, str) or not NAME.fullmatch(schema):
        problems.append(f"{where}: schema must be a schema name (lower-case letters, digits, '-'), got {schema!r}")
    elif known_schemas is not None and schema not in known_schemas:
        problems.append(f"{where}: schema {schema!r} has no file schemas/{schema}.json")
    if grammar in ("", None):
        grammar = None
    elif not isinstance(grammar, str) or not LABEL.fullmatch(grammar):
        problems.append(f"{where}: grammar must be a label of letters, digits, '.', '_' or '-', got {grammar!r}")
    if len(problems) != start:
        return None
    seen.add(str(item_id))
    return Item(str(item_id), str(prompt), str(schema), grammar)


def parse_items_csv(text: str, known_schemas: set[str] | None = None, source: str = "prompts.csv") -> list[Item]:
    problems: list[str] = []
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    items: list[Item] = []
    seen: set[str] = set()
    header: list[str] | None = None
    previous = 0
    try:
        for row in reader:
            start, end = previous + 1, reader.line_num
            previous = end
            where = f"line {start}" if start == end else f"lines {start}-{end}"
            if header is None:
                header = [h.strip() for h in row]
                bad = (sorted(set(header) - set(ITEM_FIELDS)), sorted(set(REQUIRED_FIELDS) - set(header)),
                       sorted({h for h in header if header.count(h) > 1}))
                if any(bad):
                    problems.append(f"{where}: the header needs {','.join(REQUIRED_FIELDS)} and may add grammar "
                                    f"(any order); got {','.join(header)}")
                    break
                continue
            if not any(cell.strip() for cell in row):
                continue
            if len(row) != len(header):
                problems.append(f"{where}: {len(row)} field(s), the header has {len(header)} "
                                "(a comma in a prompt needs quotes)")
                continue
            fields = dict(zip(header, row))
            fields["item_id"] = fields["item_id"].strip()
            fields["schema"] = fields["schema"].strip()
            if "grammar" in fields:
                fields["grammar"] = fields["grammar"].strip()
            item = _item(fields, where, seen, known_schemas, problems)
            if item:
                items.append(item)
    except csv.Error as exc:
        problems.append(f"line {reader.line_num}: not valid CSV ({exc})")
    if header is None:
        problems.append("the file is empty")
    elif not problems and not items:
        problems.append("the file has no item")
    if problems:
        raise FormatInputError(source, problems)
    return items


def parse_items_jsonl(text: str, known_schemas: set[str] | None = None, source: str = "prompts.jsonl") -> list[Item]:
    problems: list[str] = []
    items: list[Item] = []
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
        if not isinstance(doc, dict) or not set(REQUIRED_FIELDS) <= set(doc) <= set(ITEM_FIELDS):
            got = sorted(doc) if isinstance(doc, dict) else type(doc).__name__
            problems.append(f"{where}: an object with the keys {', '.join(REQUIRED_FIELDS)} and optionally grammar "
                            f"is needed, got {got}")
            continue
        item = _item(doc, where, seen, known_schemas, problems)
        if item:
            items.append(item)
    if not problems and not items:
        problems.append("the file has no item")
    if problems:
        raise FormatInputError(source, problems)
    return items


def load_items(path: Path, known_schemas: set[str] | None = None) -> list[Item]:
    """Items of a prompt file (CSV or JSONL by extension), checked strictly; FormatInputError on any problem."""
    parse = {".csv": parse_items_csv, ".jsonl": parse_items_jsonl}.get(path.suffix)
    if parse is None:
        raise FormatInputError(str(path), [f"the extension must be .csv or .jsonl, got {path.suffix!r}"])
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FormatInputError(str(path), [f"not UTF-8 text ({exc.reason})"]) from exc
    except FileNotFoundError as exc:
        raise FormatInputError(str(path), ["the file does not exist"]) from exc
    return parse(text, known_schemas, str(path))


# -- the validator -------------------------------------------------------------

_FENCE = re.compile(r"```[A-Za-z0-9_-]*[ \t]*\r?\n?(.*?)\r?\n?[ \t]*```", re.DOTALL)
_MAX_SCAN = 200


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object" if isinstance(value, dict) else type(value).__name__


def _reason(code: str, path: str, detail: str) -> dict:
    return {"code": code, "path": path, "detail": detail[:MAX_DETAIL_CHARS]}


def _schema_reasons(value: Any, schema: dict, validator: Draft202012Validator | None = None) -> list[dict]:
    validator = validator or Draft202012Validator(schema)
    found: dict[tuple[str, str, str], dict] = {}
    for error in validator.iter_errors(value):
        code = REASON_OF_KEYWORD.get(str(error.validator), "other_constraint")
        parts = list(error.absolute_path)
        if error.validator == "required":
            missing = [name for name in error.validator_value if name not in error.instance]
            detail = "missing " + ", ".join(repr(m) for m in missing)
        elif error.validator == "additionalProperties":
            allowed = (error.schema.get("properties") or {})
            detail = "unexpected " + ", ".join(repr(k) for k in sorted(k for k in error.instance if k not in allowed))
        elif error.validator == "type":
            wanted = error.validator_value if isinstance(error.validator_value, str) else "/".join(error.validator_value)
            detail = f"expected {wanted}, got {_json_type(error.instance)}"
        elif error.validator in ("enum", "const"):
            detail = "not one of the allowed values" if error.validator == "enum" else "not the required value"
        else:
            detail = f"{error.validator} {canonical(error.validator_value)}"
        path = _pointer(parts)
        found[code, path, detail] = _reason(code, path, detail)
    return [found[k] for k in sorted(found)]


def _why_not_json(text: str, finish_reason: str | None, nonfinite: bool) -> dict:
    """The one reason an answer that is not a single JSON value does not conform."""
    if nonfinite:
        return _reason("non_finite_number", "", "NaN, Infinity or a number beyond a double")
    if finish_reason == "length":
        return _reason("truncated", "", "the model stopped at its token limit")
    fenced = _FENCE.fullmatch(text.strip())
    if fenced:
        try:
            json.loads(fenced.group(1))
            return _reason("code_fence", "", "the JSON is inside a Markdown code fence")
        except (ValueError, RecursionError):
            pass
    decoder = json.JSONDecoder()
    starts = [m.start() for m in re.finditer(r"[{\[]", text)][:_MAX_SCAN]
    for start in starts:
        try:
            decoder.raw_decode(text, start)
        except (ValueError, RecursionError):
            continue
        return _reason("text_around_json", "", "there is JSON, with other text before or after it")
    return _reason("not_json", "", "the answer has no JSON in it")


def judge(text: str, schema: dict, finish_reason: str | None = None,
          validator: Draft202012Validator | None = None) -> tuple[str, list[dict]]:
    """(verdict, reasons) for one answer: ``no_answer`` for an empty reply, else ``conforming`` (no reasons) or
    ``non_conforming``. See the module docstring for the reasons."""
    if not text.strip():
        return fm.NO_ANSWER, []
    try:
        value, repeated = loads_strict(text)
    except (ValueError, RecursionError) as exc:
        return fm.NON_CONFORMING, [_why_not_json(text, finish_reason, isinstance(exc, _NonFinite))]
    reasons = [_reason("duplicate_key", "", "a key is repeated: " + ", ".join(repr(k) for k in sorted(set(repeated))))
               ] if repeated else []
    reasons += _schema_reasons(value, schema, validator)
    reasons = sorted(reasons, key=lambda r: (r["path"], r["code"], r["detail"]))[:MAX_REASONS]
    return (fm.NON_CONFORMING if reasons else fm.CONFORMING), reasons


# -- toy models ----------------------------------------------------------------

@dataclass(frozen=True)
class Reply:
    text: str
    finish_reason: str = "stop"


def _pick(seed: str, n: int, salt: str) -> int:
    digest = hashlib.blake2b(f"{seed}\0{salt}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") % n


def example(schema: dict, seed: str, where: str = "") -> Any:
    """A value that matches ``schema``, chosen from ``seed`` (for the toy models; the supported subset only)."""
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][_pick(seed, len(schema["enum"]), where)]
    kind = schema.get("type", "string")
    kind = kind[0] if isinstance(kind, list) else kind
    if kind == "object":
        props = schema.get("properties") or {}
        required = set(schema.get("required") or ())
        return {k: example(v, seed, f"{where}/{k}") for k, v in props.items()
                if k in required or _pick(seed, 2, f"{where}/{k}?")}
    if kind == "array":
        low = schema.get("minItems", 1)
        high = max(low, schema.get("maxItems", low + 2))
        return [example(schema.get("items") or {}, seed, f"{where}/{i}")
                for i in range(low + _pick(seed, high - low + 1, f"{where}#"))]
    if kind == "string":
        words = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot"]
        text = " ".join(words[_pick(seed, len(words), f"{where}/w{i}")] for i in range(3))
        return text[:schema.get("maxLength", len(text))].ljust(schema.get("minLength", 0), "x")
    if kind in ("integer", "number"):
        low = schema.get("minimum", 0)
        high = schema.get("maximum", low + 9)
        if kind == "integer":
            return int(low) + _pick(seed, int(high) - int(low) + 1, where)
        return round(low + (high - low) * _pick(seed, 1001, where) / 1000, 3)
    if kind == "boolean":
        return bool(_pick(seed, 2, where))
    return None


def _break(value: Any, schema: dict, defect: str) -> tuple[Any, bool]:
    """``value`` with one defect in it, and whether the defect could be made for this schema."""
    if not isinstance(value, dict):
        return value, False
    value = dict(value)
    props = schema.get("properties") or {}
    if defect == "missing_field":
        required = [k for k in schema.get("required") or () if k in value]
        if required:
            del value[required[-1]]
            return value, True
    elif defect == "wrong_type":
        for key, item in value.items():
            if isinstance(item, str):
                value[key] = 7
                return value, True
            if isinstance(item, (int, float)) and not isinstance(item, bool):
                value[key] = str(item)
                return value, True
    elif defect == "extra_field":
        value["x-extra"] = "extra"
        return value, True
    elif defect == "out_of_range":
        for key, item in value.items():
            bounds = props.get(key) or {}
            if "maximum" in bounds and isinstance(item, (int, float)):
                value[key] = bounds["maximum"] + 1
                return value, True
    return value, False


def _toy_reply(format_: str, schema: dict, prompt: str, silent: bool) -> Reply:
    seed = prompt + "\0" + canonical(schema)
    if silent and _pick(seed, 8, "silent") == 0:
        return Reply("")
    value = example(schema, seed)
    text = json.dumps(value, ensure_ascii=False)
    roll = _pick(seed, 16, f"roll-{format_}")
    if format_ == "free":
        defects = {9: "prose", 10: "prose_then_json", 11: "fenced", 12: "missing_field", 13: "wrong_type",
                   14: "extra_field", 15: "truncated"}
    elif format_ == "json_schema":
        defects = {0: "out_of_range", 1: "out_of_range"}  # a forced format that does not enforce numeric bounds
    else:
        defects = {}
    defect = defects.get(roll)
    if defect == "prose":
        return Reply("Sure, here is my assessment: the request looks fine and I see nothing unusual in it.")
    if defect == "prose_then_json":
        return Reply(f"Here is the answer:\n{text}")
    if defect == "fenced":
        return Reply(f"```json\n{text}\n```")
    if defect == "truncated":
        return Reply(text[:max(1, len(text) * 6 // 10)], "length")
    if defect:
        broken, made = _break(value, schema, defect)
        if made:
            return Reply(json.dumps(broken, ensure_ascii=False))
    return Reply(text)


def toy_answerer(format_: str, schema: dict, system: str, prompt: str) -> Reply:
    """A model that does what the format says: free answers go wrong in several ways, a forced format mostly
    holds (``json_schema`` does not enforce numeric bounds, ``grammar`` enforces everything)."""
    return _toy_reply(format_, schema, prompt, silent=False)


def toy_sparse(format_: str, schema: dict, system: str, prompt: str) -> Reply:
    """Like ``toy-answerer``, but one item in eight gets an empty reply."""
    return _toy_reply(format_, schema, prompt, silent=True)


OFFLINE_MODELS: dict[str, Callable[[str, dict, str, str], Reply]] = {
    "toy-answerer": toy_answerer,
    "toy-sparse": toy_sparse,
}


# -- configurations ------------------------------------------------------------

@dataclass(frozen=True)
class Settings:
    format: str
    max_tokens: int
    temperature: float
    seed: int | None
    show_schema: bool


def config_settings(params: Mapping | None) -> Settings:
    """Settings of a configuration from its params (ValueError on anything unknown or out of range)."""
    params = params or {}
    unknown = set(params) - CONFIG_PARAMS
    if unknown:
        raise ValueError(f"unknown params {', '.join(sorted(unknown))}; known: {', '.join(sorted(CONFIG_PARAMS))}")
    format_ = params.get("format")
    if format_ not in FORMATS:
        raise ValueError(f"format is required and must be one of {', '.join(FORMATS)}, got {format_!r}")
    max_tokens = params.get("max_tokens", DEFAULT_MAX_TOKENS)
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or not 16 <= max_tokens <= 8192:
        raise ValueError(f"max_tokens must be an integer from 16 to 8192, got {max_tokens!r}")
    temperature = params.get("temperature", 0.0)
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)) or not 0 <= temperature <= 2:
        raise ValueError(f"temperature must be a number from 0 to 2, got {temperature!r}")
    seed = params.get("seed")
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
        raise ValueError(f"seed must be an integer, got {seed!r}")
    show = params.get("show_schema", True)
    if not isinstance(show, bool):
        raise ValueError(f"show_schema must be true or false, got {show!r}")  # noqa: TRY004 - one error type for every bad param
    return Settings(format_, max_tokens, float(temperature), seed, show)


def system_prompt(schema: dict, show_schema: bool) -> str:
    return SYSTEM_WITH_SCHEMA.format(schema=canonical(schema)) if show_schema else SYSTEM


def request_format(format_: str, schema: dict, schema_name: str) -> tuple[dict | None, dict | None]:
    """(``response_format``, extra body fields) that force ``format_`` on the model server."""
    if format_ == "json_schema":
        return {"type": "json_schema", "json_schema": {"name": schema_name, "schema": schema, "strict": True}}, None
    if format_ == "grammar":
        return None, {"json_schema": schema}
    return None, None


# -- spec ----------------------------------------------------------------------

def _models(models: dict | None) -> dict:
    if models is not None:
        return models
    from exocortex.lab.llm_gateway import load_models

    return load_models(repo_path("lab/models.yaml"))


def _check_model(cfg: dict, registry: dict, slug) -> list[str]:
    from exocortex.lab.llm_gateway import LOCAL, ModelNotAllowed, authorize

    model, provider = cfg.get("model"), cfg.get("provider", "local")
    if not isinstance(model, str) or not model:
        return ["model is required"]
    if model in OFFLINE_MODELS:
        return [] if provider == "none" else [f"{model} is computed in the process: provider must be 'none'"]
    try:
        entry = authorize(registry, model, "public", slug)
    except ModelNotAllowed as exc:
        return [str(exc)]
    expected = "local" if entry.get("provider", LOCAL) == LOCAL else "remote"
    return [] if provider == expected else [f"{model} is {expected} in lab/models.yaml: provider must be {expected!r}"]


def _check_configs(spec: dict, params: dict, models, slug) -> list[str]:
    problems: list[str] = []
    configs = spec.get("configs")
    if not isinstance(configs, list) or not configs:
        return ["configs: at least one configuration is needed"]
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
            config_settings(cfg.get("params"))
        except ValueError as exc:
            problems.append(f"{where}: {exc}")
    baseline = params.get("baseline")
    if baseline is not None and baseline not in names:
        problems.append(f"params.baseline {baseline!r} is not a configuration")
    return problems


def _check_guard(params: dict, slug, root: Path | None) -> list[str]:
    guard = params.get("guard")
    if guard is None:
        return []
    if not isinstance(guard, dict) or set(guard) != {"experiment", "metric"}:
        return ["params.guard must be a mapping with exactly the keys experiment and metric"]
    experiment, metric = guard["experiment"], guard["metric"]
    problems: list[str] = []
    if not isinstance(metric, str) or not GUARD_METRIC.fullmatch(metric):
        problems.append(f"params.guard.metric must be a metric name (lower-case letters, digits, '_'), got {metric!r}")
    if not isinstance(experiment, str) or not NAME.fullmatch(experiment):
        return problems + [f"params.guard.experiment must be the slug of a claims experiment, got {experiment!r}"]
    if experiment == slug:
        return problems + ["params.guard.experiment must be another experiment, the guard is claim quality"]
    try:
        other = yaml.safe_load(_resolve(f"lab/experiments/{experiment}.yaml", root).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return problems + [f"params.guard.experiment {experiment!r} has no readable spec lab/experiments/{experiment}.yaml"]
    kind = other.get("kind") if isinstance(other, dict) else None
    if kind != "claims":
        problems.append(f"params.guard.experiment {experiment!r} is of the kind {kind!r}; the guard metric "
                        "(claim quality) belongs to an experiment of the kind 'claims'")
    elif other.get("slug") != experiment:
        problems.append(f"lab/experiments/{experiment}.yaml has the slug {other.get('slug')!r}")
    return problems


def _sample_path(sample: dict, corpus: str | None) -> tuple[str | None, str | None]:
    items = sample.get("items")
    if not isinstance(items, str) or not items:
        return None, "items: the prompt file is required"
    parts = PurePosixPath(items).parts
    if corpus and (len(parts) != 4 or parts[:3] != ("lab", "corpora", corpus) or ".." in parts):
        return None, f"items: the prompt file must be a file directly in lab/corpora/{corpus}/, got {items!r}"
    return items, None


def _check_samples(spec: dict, corpus: str | None, schemas: set[str] | None, root: Path | None) -> list[str]:
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
            problems.append(f"{where}: method (how the prompts were chosen) is required")
        rel, problem = _sample_path(sample, corpus)
        if problem or rel is None:
            problems.append(f"{where}: {problem}")
            continue
        try:
            items = load_items(_resolve(rel, root), schemas)
        except FormatInputError as exc:
            problems += [f"{where}, {rel}: {p}" for p in exc.problems]
            continue
        except OSError as exc:
            problems.append(f"{where}: cannot read {rel} ({exc})")
            continue
        for it in items:
            if it.id in owner:
                problems.append(f"{where}: item {it.id!r} is also in sample {owner[it.id]}")
            owner.setdefault(it.id, str(name))
    return problems


def check_spec(spec: dict, *, root: Path | None = None, models: dict | None = None) -> list[str]:
    """Every problem of a format conformity spec, empty when it can run.

    Checks the keys, the configurations (names as the run unit takes them, models from lab/models.yaml or the
    toy models, params), the guard reference, and, in the corpus folder, every schema and every prompt file
    (strictly, each schema reference against the schema files, no item in two samples).
    """
    problems: list[str] = []
    if spec.get("kind") != KIND:
        problems.append(f"kind must be {KIND!r}, got {spec.get('kind')!r}")
    params = spec.get("params") or {}
    if not isinstance(params, dict):
        return problems + ["params must be a mapping"]
    if unknown := set(params) - EXPERIMENT_PARAMS:
        problems.append(f"params: unknown {', '.join(sorted(unknown))}; known: {', '.join(sorted(EXPERIMENT_PARAMS))}")
    slug = spec.get("slug")
    if not isinstance(slug, str) or not NAME.fullmatch(slug):
        problems.append(f"slug must be lower-case letters, digits and '-', got {slug!r}")
    corpus = params.get("corpus")
    schemas: set[str] | None = None
    if not isinstance(corpus, str) or not NAME.fullmatch(corpus):
        problems.append(f"params.corpus must name a folder of lab/corpora/, got {corpus!r}")
        corpus = None
    else:
        try:
            _, schema_problems = load_schemas(corpus, root)
        except OSError as exc:
            problems.append(f"corpus {corpus}: cannot read its schemas ({type(exc).__name__}: {exc})")
        else:
            problems += [f"corpus {corpus}: {p}" for p in schema_problems]
            schemas = set(schema_files(corpus, root))  # a broken schema is reported above, once
            if not schemas:
                problems.append(f"corpus {corpus}: the folder schemas/ has no schema")
    try:
        fm.settings(params)
    except ValueError as exc:
        problems.append(f"params: {exc}")
    problems += _check_configs(spec, params, models, slug)
    problems += _check_guard(params, slug, root)
    problems += _check_samples(spec, corpus, schemas, root)
    return problems


def sample_items(spec: dict, sample: dict, root: Path | None = None) -> list[dict]:
    """Members of a sample for exocortex.lab.experiments.create_sample: the items of its file, in file order.

    The member's checksum covers the prompt, the schema name and the schema's content, so changing any of them
    after the sample was stored is refused (SampleMismatch). The payload keeps what the runner needs.
    """
    params = spec.get("params") or {}
    rel, problem = _sample_path(sample, params.get("corpus"))
    if problem or rel is None:
        raise FormatInputError(sample.get("name", "sample"), [problem or "items: the prompt file is required"])
    schemas, schema_problems = load_schemas(params["corpus"], root)
    if schema_problems:
        raise FormatInputError(f"lab/corpora/{params['corpus']}/schemas", schema_problems)
    members = []
    for item in load_items(_resolve(rel, root), set(schemas)):
        digest = schemas[item.schema][1]
        members.append({"item_id": item.id, "stratum": item.schema, "content_sha256": content_sha256(item, digest),
                        "payload": {"prompt": item.prompt, "schema": item.schema, "schema_sha256": digest,
                                    "grammar": item.grammar}})
    return members


# -- runner --------------------------------------------------------------------

def _payload_item(item: dict) -> tuple[Item, str]:
    payload = item.get("payload") or {}
    it = Item(item["item_id"], payload.get("prompt", ""), payload.get("schema", ""), payload.get("grammar"))
    digest = str(payload.get("schema_sha256", ""))
    if content_sha256(it, digest) != item["content_sha256"]:
        raise RuntimeError(f"item {item['item_id']} does not match the checksum stored with the sample")
    return it, digest


def make_runner(conn, tenant: str, llm=None, root: Path | None = None):
    """Queue runner of the kind: one job sends one prompt to one configuration and judges the answer.

    The schema is read from the corpus folder and must be the one the sample was stored with. Anything that
    stops a valid measurement (a changed item or schema, a failed model call) raises: the queue retries and
    then marks the job as an error. A model that answers badly is a measurement and is stored as one.
    """
    schemas: dict[tuple[str, str], tuple[dict, str, Draft202012Validator]] = {}
    clients: list = [llm]

    def schema_for(corpus: str, name: str) -> tuple[dict, str, Draft202012Validator]:
        if (corpus, name) not in schemas:
            schema, digest = load_schema(corpus, name, root)
            schemas[corpus, name] = (schema, digest, Draft202012Validator(schema))
        return schemas[corpus, name]

    def run(job: dict, item: dict) -> dict:
        started = time.monotonic()
        cfg, params = job["config"], job["experiment"]["params"] or {}
        settings = config_settings(cfg.get("params"))
        it, stored_digest = _payload_item(item)
        schema, digest, validator = schema_for(str(params.get("corpus")), it.schema)
        if digest != stored_digest:
            raise RuntimeError(f"schema {it.schema} changed since the sample of {it.id} was stored")
        model = cfg["model"]
        system = system_prompt(schema, settings.show_schema)
        offline = model in OFFLINE_MODELS
        input_tokens = output_tokens = 0
        if offline:
            reply = OFFLINE_MODELS[model](settings.format, schema, system, it.prompt)
            input_tokens, output_tokens = len((system + " " + it.prompt).split()), len(reply.text.split())
        else:
            if clients[0] is None:
                from exocortex.lab.llm import LabLLM

                clients[0] = LabLLM()
            response_format, extra = request_format(settings.format, schema, it.schema)
            call = clients[0].chat(model=model, system=system, user=it.prompt, response_format=response_format,
                                   max_tokens=settings.max_tokens, temperature=settings.temperature,
                                   seed=settings.seed, extra=extra)
            if call.error:
                raise RuntimeError(f"no reply from {model}: {call.error}")
            reply = Reply(call.raw, call.finish_reason or "")
            input_tokens, output_tokens = call.prompt_tokens, call.completion_tokens
        text = reply.text.replace("\x00", "\ufffd")  # JSONB cannot hold a NUL; the verdict is of what is stored
        verdict, reasons = judge(text, schema, reply.finish_reason, validator)
        output: dict[str, Any] = {"item": it.id, "schema": it.schema, "schema_sha256": digest, "grammar": it.grammar,
                  "format": settings.format, "answer": text, "finish_reason": reply.finish_reason,
                  "verdict": verdict, "reasons": reasons}
        if text != reply.text:
            output["nul_replaced"] = True
        answered = verdict != fm.NO_ANSWER
        return {"ok": answered, "error_reason": None if answered else "empty reply", "output": output,
                "model": model, "provider": cfg.get("provider") or "local",
                "base_url": None if offline or clients[0] is None else clients[0].url,
                "input_tokens": input_tokens, "output_tokens": output_tokens,
                "latency_ms": round((time.monotonic() - started) * 1000)}

    return run


# -- metrics and summary -------------------------------------------------------

def compute_metrics(conn, run_uuid: str) -> list[str]:
    """Store the format conformity metrics of a run; returns their result ids (exocortex/lab/metrics.py conventions).

    A job that ended in an error has no result; it counts as a failed job in the details of each metric.
    """
    run = conn.execute("SELECT r.run_id, e.slug, e.params FROM exp_runs r JOIN experiments e ON e.id = r.experiment_id "
                       "WHERE r.id = %s", (run_uuid,)).fetchone()
    rows = conn.execute(
        """SELECT c.id AS config_id, c.name, j.item_id, res.ok, res.output FROM exp_jobs j
           JOIN exp_configs c ON c.id = j.config_id LEFT JOIN exp_results res ON res.job_id = j.id
           WHERE j.run_id = %s ORDER BY c.name, j.item_id""", (run_uuid,)).fetchall()
    config_ids = {r["name"]: str(r["config_id"]) for r in rows}
    plain = [{"config": r["name"], "item_id": r["item_id"], "verdict": fm.row_verdict(r["ok"], r["output"]),
              "reasons": fm.reason_codes(r["output"])} for r in rows]
    baseline, guard = fm.settings(run["params"])
    ids = []
    for m in fm.format_metrics(plain, f"{run['slug']}/{run['run_id']}", baseline, guard):
        ex.record_metric(conn, m["result_id"], run_uuid, config_ids.get(m["config"]), m["metric"], m["value"],
                         m["ci_low"], m["ci_high"], m["n"], m["method"], m["details"])
        ids.append(m["result_id"])
    return ids


def summary(conn, slug: str, run_id: str | None = None) -> dict:
    """The metrics of a run (default: the newest one that is finished), per configuration and as differences.

    Computes and stores them first when the run is finished and has none yet. ``guard`` is the reference to the
    claims experiment's metric, if the experiment declares one; its number is not here.
    """
    exp = conn.execute("SELECT id, kind, params FROM experiments WHERE slug = %s", (slug,)).fetchone()
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
    guard = None
    for m in conn.execute(
            """SELECT m.result_id, c.name AS config, m.metric, m.value, m.ci_low, m.ci_high, m.n, m.method, m.details
               FROM exp_metrics m LEFT JOIN exp_configs c ON c.id = m.config_id WHERE m.run_id = %s
               ORDER BY m.result_id""", (run["id"],)).fetchall():
        entry = {"value": m["value"], "ci_low": m["ci_low"], "ci_high": m["ci_high"], "n": m["n"],
                 "method": m["method"], "details": m["details"], "result_id": m["result_id"]}
        if m["method"] == fm.GUARD_METHOD:
            guard = {**m["details"]["guard"], "result_id": m["result_id"], "computed_here": False}
        elif m["config"] is None:
            differences.append({"metric": m["metric"], "a": m["details"].get("a"), "b": m["details"].get("b"), **entry})
        else:
            configs.setdefault(m["config"], {})[m["metric"]] = entry
    return {"experiment": slug, "run": run["run_id"], "status": run["status"], "jobs": jobs, "configs": configs,
            "differences": differences, "guard": guard}
