# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Load a corpus built by lab/corpus/*.py into the lab through its Capture API.

Each record becomes one `arxiv` source: the abstract is the payload, the
engine's summary, findings and checksums go into metadata. Re-running is
safe: the Capture API ignores unchanged items.

    python lab/corpus/load.py --corpus corpus.jsonl --api http://exocortex-lab-api:8000
Token: CAPTURE_API_TOKEN in the environment.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

CHUNK = 200


def item(rec: dict, corpus_name: str) -> dict:
    return {
        "source_type": "arxiv",
        "uri": f"https://arxiv.org/abs/{rec['arxiv_id']}v{rec['version']}",
        "title": rec["title"],
        "published_at": rec.get("published") or None,
        "source_name": "arXiv",
        "raw_payload": rec["abstract"],
        "metadata": {
            "corpus": corpus_name, "arxiv_id": rec["arxiv_id"], "version": rec["version"],
            "abstract_sha256": rec["abstract_sha256"], "summary_sha256": rec["summary_sha256"],
            "summary_pl": rec["summary_pl"], "findings_pl": rec["findings_pl"],
            "summary_date": rec.get("summary_date"), "relevance": rec.get("relevance"),
            "stratum": rec.get("stratum"),
        },
    }


def post(api: str, token: str, items: list[dict]) -> dict:
    body = json.dumps({"items": items}).encode("utf-8")
    req = urllib.request.Request(api.rstrip("/") + "/capture/batch", data=body, method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--api", default=os.environ.get("LAB_CAPTURE_API", "http://exocortex-lab-api:8000"))
    ap.add_argument("--name", default=None, help="corpus name stored in metadata (default: folder name)")
    args = ap.parse_args(argv)
    token = os.environ["CAPTURE_API_TOKEN"]
    name = args.name or args.corpus.parent.name
    records = [json.loads(line) for line in args.corpus.read_text(encoding="utf-8").splitlines() if line.strip()]
    created = errors = 0
    for i in range(0, len(records), CHUNK):
        res = post(args.api, token, [item(r, name) for r in records[i:i + CHUNK]])
        created += res["created_count"]
        errs = [x for x in res["results"] if "error" in x]
        errors += len(errs)
        for e in errs[:3]:
            print(f"error: {e['uri']}: {e['error']}", file=sys.stderr)
    print(json.dumps({"records": len(records), "created": created, "errors": errors}))
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
