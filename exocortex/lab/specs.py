# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Experiments described as files in the repository (lab/experiments/*.yaml).

A spec names the experiment, its kind, its configurations and its samples;
sample members are listed in CSV files next to the corpus, so the drawn
samples are public before anything runs. Setting up is idempotent and
refuses to change an existing configuration or sample.

A run of an experiment that tests a hypothesis needs the card version to
be frozen (registered) and not violated; the run records the registered
checksum. Machinery tests (no hypothesis) run without one.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import yaml

from exocortex.lab import experiments as ex
from exocortex.lab.claims import repo_path


class NotPreregistered(Exception):
    """The hypothesis card of the experiment is not frozen, or was changed after freezing."""


def load(path: Path) -> dict:
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    for key in ("slug", "kind", "title", "configs", "samples"):
        if key not in spec:
            raise ValueError(f"{path}: missing {key}")
    if spec["kind"] == "retrieval":  # its corpus and question sets are checked before anything is stored or run
        from exocortex.lab import retrieval

        problems = retrieval.check_spec(spec)
        if problems:
            raise retrieval.RetrievalInputError(str(path), problems)
    if spec["kind"] == "format_conformity":  # likewise its schemas, prompt files and guard reference
        from exocortex.lab import format_conformity

        problems = format_conformity.check_spec(spec)
        if problems:
            raise format_conformity.FormatInputError(str(path), problems)
    return spec


def corpus_checksums(corpus: str) -> dict[str, dict]:
    with repo_path(f"lab/corpora/{corpus}/manifest.csv").open(encoding="utf-8") as fh:
        return {row["arxiv_id"]: row for row in csv.DictReader(fh)}


def sample_items(spec: dict, sample: dict) -> list[dict]:
    """Members of a sample from its CSV, with the corpus checksums of both texts."""
    manifest = corpus_checksums(spec["params"]["corpus"])
    items = []
    with repo_path(sample["items"]).open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            m = manifest[row["arxiv_id"]]
            both = f"{m['abstract_sha256']} {m['summary_sha256']}"
            items.append({"item_id": row["arxiv_id"], "stratum": m["stratum"],
                          "content_sha256": hashlib.sha256(both.encode()).hexdigest(),
                          "payload": {"abstract_sha256": m["abstract_sha256"],
                                      "summary_sha256": m["summary_sha256"]}})
    return items


def sample_members(spec: dict, sample: dict) -> list[dict]:
    """Members of a sample: corpus papers for most kinds, questions with gold answers for ``retrieval``, prompts
    with their schemas for ``format_conformity``."""
    if spec["kind"] == "retrieval":
        from exocortex.lab import retrieval

        return retrieval.sample_items(spec, sample)
    if spec["kind"] == "format_conformity":
        from exocortex.lab import format_conformity

        return format_conformity.sample_items(spec, sample)
    return sample_items(spec, sample)


def setup(conn, spec: dict) -> dict:
    hyp = spec.get("hypothesis") or {}
    exp = ex.ensure_experiment(conn, spec["slug"], spec["kind"], spec["title"], hypothesis_slug=hyp.get("slug"),
                               params=spec.get("params") or {})
    configs = {c["name"]: ex.ensure_config(conn, exp, c["name"], model=c.get("model"),
                                           provider=c.get("provider", "local"), variant=c.get("variant", ""),
                                           params=c.get("params") or {})
               for c in spec["configs"]}
    samples = {s["name"]: ex.create_sample(conn, exp, s["name"], s["role"], int(s["seed"]), s["method"],
                                           sample_members(spec, s))
               for s in spec["samples"]}
    return {"experiment": exp, "configs": configs, "samples": samples}


def preregistration(conn, spec: dict) -> tuple[int | None, str | None]:
    """(hypothesis version, registered checksum) for a run; raises NotPreregistered."""
    hyp = spec.get("hypothesis")
    if not hyp:
        return None, None
    row = conn.execute("SELECT prereg_sha256, violated FROM lab_hypotheses WHERE slug = %s AND version = %s",
                       (hyp["slug"], hyp["version"])).fetchone()
    if row is None or row["prereg_sha256"] is None:
        raise NotPreregistered(f"{hyp['slug']} v{hyp['version']} is not frozen: no run before preregistration")
    if row["violated"]:
        raise NotPreregistered(f"{hyp['slug']} v{hyp['version']} changed after it was frozen")
    return int(hyp["version"]), row["prereg_sha256"]
