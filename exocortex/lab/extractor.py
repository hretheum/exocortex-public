# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Claim extractor of the lab (roadmap task F3.3), written for public data.

Three passes over one document:

1. Extraction. One call returns claims, each with a verbatim quote from the
   document. Two variants of the output schema differ in one field only:
   ``baseline`` has quote and claim; ``mode`` adds the mode in which the
   document presents the statement: fact, plan, requirement or
   hypothesis. The instructions differ only by the rule that defines that
   field. Both ask for the quote first.
2. Grounding and judgement. A claim counts only if its quote is a
   verbatim substring of the document after normalisation (Unicode form,
   case, quotation marks, dashes, whitespace). A second, separate call
   decides for every grounded claim whether it is a claim at all: a
   self-contained statement that can be true or false.
3. Duplicates. Among the remaining claims, one whose embedding is at
   least ``dedupe_threshold`` similar to an earlier one is marked
   redundant.

Nothing is dropped silently: every candidate stays in the output with the
reason it was rejected. Works for English and Polish text; prompts are in
English.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

import jsonschema

from exocortex.lab.llm import Call, LabLLM

MODES = ("fact", "plan", "requirement", "hypothesis")
MAX_CLAIMS = 20
MIN_QUOTE_CHARS = 12

_RULES = """You extract claims from a text. A claim is one statement the text makes: about the world, about \
the work it describes, or about that work's results.

Rules:
1. For every claim, first copy the quote from the text that supports it, exactly as it appears: one \
contiguous span, character for character, with no ellipsis, no paraphrase and nothing added. Use the \
shortest span that supports the claim.
2. Then write the claim as one self-contained sentence in the language of the text. Replace pronouns and \
abbreviations with what they stand for, so the sentence can be understood without the text.
3. Add nothing that the text does not say.
4. Give every distinct claim, at most {max_claims}."""

_MODE_RULE = """
5. For every claim, give the mode in which the text presents it:
   - fact: reported as done, observed, measured or true;
   - plan: something the authors intend to do or will do;
   - requirement: something that must, should or needs to hold;
   - hypothesis: something proposed, expected, assumed, suggested or considered possible, but not \
reported as established."""

JUDGE_SYSTEM = """You check a numbered list of sentences. For each one, decide whether it is a claim: a \
declarative statement that is either true or false and can be understood on its own, without the text it \
came from. Questions, headings, fragments, and sentences that cannot be understood without their context \
are not claims. Answer for every number."""


def system_prompt(variant: str) -> str:
    base = _RULES.format(max_claims=MAX_CLAIMS)
    return base + _MODE_RULE if variant == "mode" else base


def output_schema(variant: str) -> dict:
    props: dict = {"quote": {"type": "string"}}
    required = ["quote", "claim"]
    if variant == "mode":
        props["mode"] = {"type": "string", "enum": list(MODES)}
        required = ["quote", "mode", "claim"]
    props["claim"] = {"type": "string"}
    return {"type": "object", "additionalProperties": False, "required": ["claims"],
            "properties": {"claims": {"type": "array", "maxItems": MAX_CLAIMS,
                                      "items": {"type": "object", "additionalProperties": False,
                                                "required": required, "properties": props}}}}


JUDGE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["verdicts"],
                "properties": {"verdicts": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False, "required": ["n", "claim"],
                    "properties": {"n": {"type": "integer"}, "claim": {"type": "boolean"}}}}}}

_QUOTES = str.maketrans({"‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
                         "“": '"', "”": '"', "„": '"', "‟": '"', "«": '"', "»": '"',
                         "–": "-", "—": "-", "−": "-", "‐": "-", "‑": "-",
                         "­": None, "\u200b": None})


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_QUOTES).casefold()
    return " ".join(text.split())


def grounded(quote: str, document: str) -> tuple[bool, str | None]:
    """(is the quote a verbatim part of the document after normalisation, reason if not)."""
    q = normalise(quote)
    if len(q) < MIN_QUOTE_CHARS:
        return False, "quote_too_short"
    return (True, None) if q in normalise(document) else (False, "not_grounded")


def user_prompt(text: str, glossary: dict[str, str] | None = None) -> str:
    out = f"Text:\n\n{text}"
    if glossary:
        lines = "\n".join(f"- {k}: {v}" for k, v in sorted(glossary.items()))
        out += f"\n\nAbbreviations the text uses without defining them:\n{lines}"
    return out


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


@dataclass
class Settings:
    model: str
    variant: str = "baseline"          # baseline | mode
    call_mode: str = "json_schema"     # json_schema | tools (the model server's structured-output route)
    judge_model: str | None = None     # default: the extraction model
    embed_model: str = "bge-m3"
    dedupe_threshold: float = 0.92
    temperature: float = 0.0
    seed: int = 0
    max_tokens: int = 3072
    judge_max_tokens: int = 1024

    @classmethod
    def from_config(cls, config: dict) -> Settings:
        params = dict(config.get("params") or {})
        allowed = {f for f in cls.__dataclass_fields__} - {"model", "variant"}
        return cls(model=config["model"], variant=config.get("variant") or "baseline",
                   **{k: v for k, v in params.items() if k in allowed})


def _usage(calls: list[Call]) -> dict:
    return {"input_tokens": sum(c.prompt_tokens for c in calls),
            "output_tokens": sum(c.completion_tokens for c in calls),
            "latency_ms": sum(c.latency_ms for c in calls)}


def extract(llm: LabLLM, text: str, settings: Settings, glossary: dict[str, str] | None = None,
            embed: Callable[[list[str]], list[list[float]]] | None = None) -> dict:
    """Run the three passes on one document; the result is stored as JSON as is."""
    if settings.variant not in ("baseline", "mode"):
        raise ValueError(f"unknown variant {settings.variant!r}")
    schema = output_schema(settings.variant)
    call = llm.structured(model=settings.model, system=system_prompt(settings.variant),
                          user=user_prompt(text, glossary), schema=schema, name="extract_claims",
                          mode=settings.call_mode, max_tokens=settings.max_tokens,
                          temperature=settings.temperature, seed=settings.seed)
    calls = [call]
    trace = [{"stage": "extract", "ok": call.ok, "error": call.error, "finish_reason": call.finish_reason,
              "prompt_tokens": call.prompt_tokens, "completion_tokens": call.completion_tokens,
              "latency_ms": call.latency_ms}]
    out = {"variant": settings.variant, "model": settings.model, "claims": [], "calls": trace}
    if call.ok:
        try:
            jsonschema.validate(call.output, schema)
        except jsonschema.ValidationError as exc:
            call.error = f"schema: {exc.validator} at {'/'.join(map(str, exc.absolute_path)) or '(root)'}"
    if not call.ok:
        trace[0]["error"] = call.error
        return {**out, "ok": False, "error_reason": call.error, "counts": _counts([]), **_usage(calls)}

    claims = []
    for i, raw in enumerate(call.output["claims"]):
        c = {"i": i, "quote": raw["quote"], "claim": raw["claim"], "mode": raw.get("mode"),
             "grounded": False, "proposition": None, "redundant": None, "usable": False, "rejection": None}
        c["grounded"], c["rejection"] = grounded(raw["quote"], text)
        claims.append(c)

    candidates = [c for c in claims if c["grounded"]]
    if candidates:
        listing = "\n".join(f"{n}. {c['claim']}" for n, c in enumerate(candidates, 1))
        judge = llm.structured(model=settings.judge_model or settings.model, system=JUDGE_SYSTEM, user=listing,
                               schema=JUDGE_SCHEMA, name="judge_claims", mode=settings.call_mode,
                               max_tokens=settings.judge_max_tokens, temperature=settings.temperature,
                               seed=settings.seed)
        calls.append(judge)
        trace.append({"stage": "judge", "ok": judge.ok, "error": judge.error, "finish_reason": judge.finish_reason,
                      "prompt_tokens": judge.prompt_tokens, "completion_tokens": judge.completion_tokens,
                      "latency_ms": judge.latency_ms})
        verdicts = {}
        if judge.ok:
            for v in judge.output.get("verdicts") or []:
                if isinstance(v, dict) and isinstance(v.get("n"), int) and isinstance(v.get("claim"), bool):
                    verdicts.setdefault(v["n"], v["claim"])
        for n, c in enumerate(candidates, 1):
            c["proposition"] = verdicts.get(n)
            if c["proposition"] is None:
                c["rejection"] = "judge_failed" if not judge.ok else "judge_missing"
            elif not c["proposition"]:
                c["rejection"] = "not_proposition"

    kept = [c for c in candidates if c["proposition"]]
    if kept and embed is not None:
        vectors = embed([c["claim"] for c in kept])
        accepted: list[list[float]] = []
        for c, vec in zip(kept, vectors):
            c["redundant"] = any(cosine(vec, prev) >= settings.dedupe_threshold for prev in accepted)
            if c["redundant"]:
                c["rejection"] = "redundant"
            else:
                accepted.append(vec)
    for c in kept:
        c["usable"] = c["redundant"] is False or (embed is None and c["redundant"] is None)
    return {**out, "ok": True, "error_reason": None, "claims": claims, "counts": _counts(claims),
            "dedupe": "embeddings" if embed is not None else "off", **_usage(calls)}


def _counts(claims: list[dict]) -> dict:
    return {"extracted": len(claims), "grounded": sum(c["grounded"] for c in claims),
            "proposition": sum(bool(c["proposition"]) for c in claims),
            "redundant": sum(bool(c["redundant"]) for c in claims), "usable": sum(c["usable"] for c in claims)}


# -- abbreviations ------------------------------------------------------------

_DEF = re.compile(r"([A-Za-z][\w\-' ]{2,120}?)\s*\(\s*([A-Z][A-Za-z0-9\-]{1,9}s?)\s*\)")


def definitions(text: str) -> dict[str, str]:
    """Abbreviations defined in ``text`` as "long form (SHORT)" (Schwartz & Hearst, 2003).

    The long form is the shortest run of words before the parenthesis whose
    first word starts with the abbreviation's first letter and which
    contains the abbreviation's letters in order.
    """
    out: dict[str, str] = {}
    for m in _DEF.finditer(text):
        short = m.group(2)
        words = m.group(1).split()
        letters = [ch.lower() for ch in short if ch.isalnum()]
        if short.endswith("s") and len(letters) > 2:
            letters = letters[:-1]
        for start in range(len(words) - 1, max(-1, len(words) - len(letters) - 5), -1):
            candidate = words[start:]
            if not candidate[0][:1].lower() == letters[0]:
                continue
            if _letters_in_order(" ".join(candidate).lower(), letters) and len(candidate) <= len(letters) + 4:
                out.setdefault(short.rstrip("s") if short.endswith("s") and len(short) > 2 else short,
                               " ".join(candidate))
                break
    return out


def _letters_in_order(long_form: str, letters: list[str]) -> bool:
    pos = 0
    for ch in letters:
        pos = long_form.find(ch, pos)
        if pos < 0:
            return False
        pos += 1
    return True


def glossary_for(text: str, dictionary: dict[str, str]) -> dict[str, str]:
    """Entries of ``dictionary`` whose abbreviation the text uses but does not define."""
    defined = definitions(text)
    used = set(re.findall(r"\b([A-Z][A-Za-z0-9\-]{1,9})s?\b", text))
    return {k: v for k, v in dictionary.items() if k in used and k not in defined}
