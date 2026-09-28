"""Validate the YAML front matter of evidence documents against JSON Schemas.

Which schema applies:
- a ``type`` field naming a schema in ``schemas/`` (hypothesis_card,
  run_note, gate_decision),
- files under ``roadmap/F<n>/`` are roadmap tasks.
Other files (the cycle, the roadmap, phase documents, templates of types
without a schema) are not validated here.

Messages name the file, the field and what is wrong, in plain words.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

SCHEMAS = Path(__file__).parent / "schemas"
FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.S)
TASK_PATH = re.compile(r"(^|/)roadmap/F\d+/F\d+\.\d+-[^/]+\.md$")


@dataclass
class Error:
    path: str
    field: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.field}: {self.message}"


def _plain(value):
    """YAML turns 2026-09-28 into a date object; schemas expect ISO strings."""
    import datetime as dt

    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def _validators() -> dict[str, Draft202012Validator]:
    return {
        p.name.removesuffix(".schema.json"): Draft202012Validator(json.loads(p.read_text(encoding="utf-8")))
        for p in SCHEMAS.glob("*.schema.json")
    }


def schema_for(rel: str, front: dict, validators: dict) -> str | None:
    t = front.get("type")
    if isinstance(t, str) and t in validators:
        return t
    if TASK_PATH.search(rel):
        return "roadmap_task"
    return None


def _readable(err) -> tuple[str, str]:
    field = ".".join(str(p) for p in err.absolute_path) or "(header)"
    if err.validator == "required":
        missing = err.message.split("'")[1] if "'" in err.message else err.message
        return missing, "required field is missing"
    if err.validator == "additionalProperties":
        extra = re.findall(r"'([^']+)'", err.message)
        return ", ".join(extra) or field, "unknown field (check the spelling; unknown fields are not allowed)"
    if err.validator in ("enum", "const"):
        allowed = err.validator_value if err.validator == "enum" else [err.validator_value]
        return field, f"value {err.instance!r} is not allowed; use one of: {', '.join(map(str, allowed))}"
    if err.validator == "pattern":
        return field, f"value {err.instance!r} does not have the expected form ({err.validator_value})"
    if err.validator == "type":
        return field, f"expected {err.validator_value}, got {type(err.instance).__name__}"
    return field, err.message


def validate_text(rel: str, text: str, validators: dict | None = None) -> list[Error]:
    validators = validators or _validators()
    m = FRONT.match(text)
    if not m:
        return [Error(rel, "(header)", "no front matter")] if TASK_PATH.search(rel) else []
    try:
        front = _plain(yaml.safe_load(m.group(1)) or {})
    except yaml.YAMLError as e:
        return [Error(rel, "(header)", f"YAML error: {type(e).__name__}")]
    name = schema_for(rel, front, validators)
    if name is None:
        return []
    out = []
    for err in sorted(validators[name].iter_errors(front), key=lambda e: list(e.absolute_path)):
        field, msg = _readable(err)
        out.append(Error(rel, field, msg))
    return out


def validate_tree(root: Path) -> tuple[int, list[Error]]:
    validators = _validators()
    checked, errors = 0, []
    for f in sorted(root.rglob("*.md")):
        rel = f.relative_to(root).as_posix()
        text = f.read_text(encoding="utf-8")
        m = FRONT.match(text)
        front = (yaml.safe_load(m.group(1)) or {}) if m else {}
        if schema_for(rel, front if isinstance(front, dict) else {}, validators):
            checked += 1
        errors.extend(validate_text(rel, text, validators))
    return checked, errors
