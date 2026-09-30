# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Independent recomputation of the numbers of a format conformity experiment (roadmap task F5.9).

Uses only the standard library and none of the lab's code: not the validator (exocortex/lab/format_conformity.py),
not the metrics (exocortex/lab/format_conformity_metrics.py), not the Wilson interval (exocortex/lab/stats.py),
not the ``jsonschema`` package. From the schema files of the corpus folder and the raw answers in results.csv it
judges every answer again with its own small validator (the JSON Schema subset the lab documents: type,
properties, required, additionalProperties, enum, const, items, minItems, maxItems, minLength, maxLength,
pattern, minimum, maximum, exclusiveMinimum, exclusiveMaximum), and checks that the verdict and the set of reason
codes stored with each answer are the ones it finds. Then it computes, from its own verdicts, the share of
conforming answers per configuration with the Wilson score interval, the paired difference of every pair the
experiment compares with the Newcombe (1998, method 10) interval, the counts and reason counts in the details,
and compares every value of metrics.csv with them. Equality is exact, not "close". The guard rows (references to
a claims experiment's metric, without a value) are checked against the guard in datapackage.json.

    python lab/independent_format_check.py dowody/data/toy-format lab/corpora/toy-format

The one number it cannot recompute is ``failed_jobs`` in the details: a job that ended in an error has no
result, so results.csv has no row for it. Exit code 0 when every published number is reproduced exactly.
"""

from __future__ import annotations

import csv
import json
import math
import re
import sys
from pathlib import Path

Z = 1.959963984540054  # the 97.5th percentile of the standard normal distribution, to double precision
MAX_REASONS = 50
FENCE = re.compile(r"```[A-Za-z0-9_-]*[ \t]*\r?\n?(.*?)\r?\n?[ \t]*```", re.DOTALL)


# -- the answers ---------------------------------------------------------------

class NonFinite(ValueError):
    pass


def no_constants(name):
    raise NonFinite(name)


def finite(text):
    value = float(text)
    if math.isinf(value) or math.isnan(value):
        raise NonFinite(text)
    return value


def parse(text):
    """(value, repeated keys); raises ValueError when the text is not exactly one JSON value."""
    repeated = []

    def pairs(items):
        keys = [k for k, _ in items]
        repeated.extend(sorted({k for k in keys if keys.count(k) > 1}))
        return dict(items)

    return json.loads(text, object_pairs_hook=pairs, parse_constant=no_constants, parse_float=finite), repeated


def json_stage_code(text, finish_reason, nonfinite):
    """The code for an answer that is not one JSON value, by the rules the lab documents."""
    if nonfinite:
        return "non_finite_number"
    if finish_reason == "length":
        return "truncated"
    fenced = FENCE.fullmatch(text.strip())
    if fenced:
        try:
            json.loads(fenced.group(1))
            return "code_fence"
        except (ValueError, RecursionError):
            pass
    decoder = json.JSONDecoder()
    for match in list(re.finditer(r"[{\[]", text))[:200]:
        try:
            decoder.raw_decode(text, match.start())
            return "text_around_json"
        except (ValueError, RecursionError):
            pass
    return "not_json"


def same(a, b):
    """JSON equality: true is not 1, and 1 is 1.0."""
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    return type(a) is type(b) and a == b


def has_type(value, name):
    if name == "null":
        return value is None
    if name == "boolean":
        return isinstance(value, bool)
    if name == "integer":
        return (isinstance(value, int) and not isinstance(value, bool)) or (isinstance(value, float) and value.is_integer())
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "string":
        return isinstance(value, str)
    if name == "array":
        return isinstance(value, list)
    return isinstance(value, dict) if name == "object" else False


def reason_codes(value, schema, found):
    """Add to ``found`` the reason code of every violation of the schema, keyword by keyword."""
    wanted = schema.get("type")
    if wanted is not None and not any(has_type(value, t) for t in ([wanted] if isinstance(wanted, str) else wanted)):
        found.add("wrong_type")
    if "enum" in schema and not any(same(value, option) for option in schema["enum"]):
        found.add("bad_value")
    if "const" in schema and not same(value, schema["const"]):
        found.add("bad_value")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            found.add("out_of_range")
        if "maximum" in schema and value > schema["maximum"]:
            found.add("out_of_range")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            found.add("out_of_range")
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            found.add("out_of_range")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            found.add("bad_length")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            found.add("bad_length")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            found.add("bad_pattern")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            found.add("bad_length")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            found.add("bad_length")
        if isinstance(schema.get("items"), dict):
            for element in value:
                reason_codes(element, schema["items"], found)
    if isinstance(value, dict):
        if any(name not in value for name in schema.get("required", [])):
            found.add("missing_field")
        properties = schema.get("properties", {})
        for name, sub in properties.items():
            if name in value:
                reason_codes(value[name], sub, found)
        extra = schema.get("additionalProperties")
        for name in value:
            if name not in properties:
                if extra is False:
                    found.add("extra_field")
                elif isinstance(extra, dict):
                    reason_codes(value[name], extra, found)


def judge(text, schema, finish_reason):
    """(verdict, reason codes, whether the answer was one JSON value) of one answer."""
    try:
        value, repeated = parse(text)
    except (ValueError, RecursionError) as exc:
        return "non_conforming", {json_stage_code(text, finish_reason, isinstance(exc, NonFinite))}, False
    codes = {"duplicate_key"} if repeated else set()
    reason_codes(value, schema, codes)
    return ("non_conforming" if codes else "conforming"), codes, True


# -- the numbers ---------------------------------------------------------------

def wilson(successes, n):
    p = successes / n
    denom = 1 + Z * Z / n
    centre = (p + Z * Z / (2 * n)) / denom
    half = Z / denom * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n))
    low = 0.0 if successes == 0 else max(0.0, centre - half)
    high = 1.0 if successes == n else min(1.0, centre + half)
    return p, low, high


def newcombe(a, b):
    """(share of b - share of a, low, high) on the items both answered; ``a`` and ``b`` map item to conforming."""
    items = sorted(set(a) & set(b))
    both = sum(1 for i in items if a[i] and b[i])
    only_a = sum(1 for i in items if a[i] and not b[i])
    only_b = sum(1 for i in items if b[i] and not a[i])
    neither = len(items) - both - only_a - only_b
    n = len(items)
    if n == 0:
        return None, None, None, 0, {"both": 0, "only_a": 0, "only_b": 0, "neither": 0}
    p_b, low_b, high_b = wilson(both + only_b, n)
    p_a, low_a, high_a = wilson(both + only_a, n)
    marginals = (both + only_b) * (only_a + neither) * (both + only_a) * (only_b + neither)
    cross = both * neither - only_b * only_a
    if marginals == 0:
        phi = 0.0
    else:
        if cross > n / 2:
            adjusted = cross - n / 2
        elif cross >= 0:
            adjusted = 0.0
        else:
            adjusted = float(cross)
        phi = adjusted / math.sqrt(marginals)
    delta = p_b - p_a
    lo_b, lo_a = p_b - low_b, high_a - p_a
    hi_b, hi_a = high_b - p_b, p_a - low_a
    low = delta - math.sqrt(max(0.0, lo_b * lo_b + lo_a * lo_a - 2 * phi * lo_b * lo_a))
    high = delta + math.sqrt(max(0.0, hi_b * hi_b + hi_a * hi_a - 2 * phi * hi_b * hi_a))
    table = {"both": both, "only_a": only_a, "only_b": only_b, "neither": neither}
    return delta, max(-1.0, low), min(1.0, high), n, table


def recompute(data: Path, corpus: Path):
    """({result id: (value, low, high, n, details)}, problems) from results.csv, the schemas and the params."""
    package = json.loads((data / "datapackage.json").read_text(encoding="utf-8"))
    params = package["exocortex"]["params"]
    baseline, guard = params.get("baseline"), params.get("guard")
    schemas = {p.stem: json.loads(p.read_text(encoding="utf-8-sig")) for p in (corpus / "schemas").glob("*.json")}
    problems: list[str] = []
    per_run: dict[str, dict[str, dict]] = {}
    with (data / "results.csv").open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            where = f"{row['run_id']}/{row['config']}/{row['item_id']}"
            cfg = per_run.setdefault(row["run_id"], {}).setdefault(
                row["config"], {"answers": {}, "no_answer": 0, "reasons": {}})
            if row["ok"] != "true":
                cfg["no_answer"] += 1
                continue
            out = json.loads(row["output"])
            if out["schema"] not in schemas:
                problems.append(f"{where}: no schema file {out['schema']}")
                continue
            verdict, codes, parsed = judge(out["answer"], schemas[out["schema"]], out.get("finish_reason"))
            if verdict != out["verdict"]:
                problems.append(f"{where}: stored verdict {out['verdict']}, recomputed {verdict}")
            stored = {r["code"] for r in out["reasons"]}
            if len(out["reasons"]) < MAX_REASONS and stored != codes:
                problems.append(f"{where}: stored reasons {sorted(stored)}, recomputed {sorted(codes)}")
            if verdict == "non_conforming" and not parsed and len(stored) != 1:
                problems.append(f"{where}: an answer that is not JSON has exactly one reason")
            cfg["answers"][row["item_id"]] = verdict == "conforming"
            for code in sorted(stored):
                cfg["reasons"][code] = cfg["reasons"].get(code, 0) + 1
    slug = data.name
    found: dict[str, tuple] = {}
    for run, configs in per_run.items():
        names = sorted(configs)
        for name in names:
            answers = configs[name]["answers"]
            conforming = sum(answers.values())
            value, low, high = wilson(conforming, len(answers)) if answers else (None, None, None)
            found[f"{slug}/{run}/{name}/conforming_share"] = (value, low, high, len(answers), {
                "conforming": conforming, "non_conforming": len(answers) - conforming,
                "no_answer": configs[name]["no_answer"], "reasons": dict(sorted(configs[name]["reasons"].items()))})
        pairs = ([(baseline, b) for b in names if b != baseline] if baseline
                 else [(a, b) for i, a in enumerate(names) for b in names[i + 1:]])
        for a, b in pairs:
            d, low, high, n, table = newcombe(configs[a]["answers"], configs[b]["answers"])
            found[f"{slug}/{run}/diff/{b}_minus_{a}/conforming_share"] = (
                d, low, high, n, {"a": a, "b": b, "difference": "b - a", **table})
        if guard:
            ref = f"{guard['experiment']}/{guard['metric']}"
            found[f"{slug}/{run}/guard/{ref}"] = (None, None, None, 0, {
                "guard": {"experiment": guard["experiment"], "metric": guard["metric"]}, "computed_here": False})
    return found, problems


def number(text):
    return None if text == "" else float(text)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print(__doc__.split("\n\n")[2].strip())
        return 2
    data, corpus = Path(args[0]), Path(args[1])
    found, problems = recompute(data, corpus)
    with (data / "metrics.csv").open(encoding="utf-8", newline="") as fh:
        published = list(csv.DictReader(fh))
    wrong = 0
    for row in published:
        mine = found.get(row["result_id"])
        if mine is None:
            print(f"missing   {row['result_id']}")
            wrong += 1
            continue
        theirs = (number(row["value"]), number(row["ci_low"]), number(row["ci_high"]), int(row["n"]))
        details = {k: v for k, v in json.loads(row["details"]).items() if k != "failed_jobs"}
        status = "ok" if theirs == mine[:4] and details == mine[4] else "DIFFERENT"
        wrong += status != "ok"
        print(f"{status:9} {row['result_id']}"
              + ("" if status == "ok" else f"  published {theirs} {details}, recomputed {mine}"))
    for problem in problems:
        print(f"PROBLEM   {problem}")
    ok = not wrong and not problems and bool(published) and {r["result_id"] for r in published} == set(found)
    print(f"{len(published)} published number(s); " + ("all reproduced exactly" if ok else "NOT all reproduced"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
