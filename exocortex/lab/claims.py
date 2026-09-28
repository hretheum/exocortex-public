# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Queue runner for claim extraction on a corpus (experiment kind ``claims``).

An item is a paper of a corpus in the lab graph (exocortex/lab/corpus_graph).
The configuration says which of its two texts to use (``text``: abstract or
summary), the model, the schema variant and the extractor settings. Before
running, the runner checks the text against the checksum stored with the
sample item, so a run always uses the text the sample was drawn with.
"""

from __future__ import annotations

from pathlib import Path

from exocortex.lab import extractor
from exocortex.lab.abbreviations import load as load_dictionary
from exocortex.lab.corpus_graph import sha256
from exocortex.lab.llm import LabLLM

KIND = "claims"
NODE = {"abstract": "corpus_abstract", "summary": "corpus_summary"}


def repo_path(rel: str) -> Path:
    """A path shipped with the code: the checkout in development, /opt/exocortex in the image."""
    for root in (Path(__file__).resolve().parents[2], Path("/opt/exocortex")):
        if (root / rel).exists():
            return root / rel
    raise FileNotFoundError(rel)


def make_runner(conn, tenant: str, llm: LabLLM | None = None):
    llm = llm or LabLLM()
    dictionaries: dict[str, dict[str, str]] = {}

    def run(job: dict, item: dict) -> dict:
        cfg = job["config"]
        params = cfg.get("params") or {}
        text = params.get("text", "abstract")
        corpus = job["experiment"]["params"].get("corpus")
        row = conn.execute(
            """SELECT body, metadata FROM thoughts WHERE tenant_id = %s AND thought_type = %s
                 AND metadata->>'corpus' = %s AND metadata->>'arxiv_id' = %s""",
            (tenant, NODE[text], corpus, item["item_id"]),
        ).fetchone()
        expected = (item.get("payload") or {}).get(f"{text}_sha256")
        base = {"model": cfg["model"], "provider": cfg.get("provider") or "local", "base_url": llm.url}
        # A missing or changed text is a broken setup, not a measurement: the job fails and the run with it.
        if row is None:
            raise RuntimeError(f"no {text} node for {item['item_id']} in corpus {corpus}")
        # whitespace-normalised checksum, the same as in manifest.csv for both texts
        if expected and sha256(row["body"]) != expected:
            raise RuntimeError(f"the {text} of {item['item_id']} changed since the sample was drawn")
        glossary = {}
        if params.get("abbreviations"):
            path = params["abbreviations"]
            if path not in dictionaries:
                dictionaries[path] = load_dictionary(repo_path(path))
            glossary = extractor.glossary_for(row["body"], dictionaries[path])
        settings = extractor.Settings.from_config(cfg)
        result = extractor.extract(llm, row["body"], settings, glossary=glossary,
                                   embed=lambda texts: llm.embed(settings.embed_model, texts))
        result["glossary"] = glossary
        result["text"] = text
        return {**base, "ok": result["ok"], "error_reason": result["error_reason"], "output": result,
                "input_tokens": result["input_tokens"], "output_tokens": result["output_tokens"],
                "latency_ms": result["latency_ms"]}

    return run
