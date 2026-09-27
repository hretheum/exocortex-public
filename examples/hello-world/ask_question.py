#!/usr/bin/env python3
# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31.9.4 — Ask a natural-language question against the hello-world note.

Calls the in-process GraphRAG orchestrator (same engine the MCP ``ask`` tool
uses).  Prints the answer paragraph plus a list of cited sources so a new
user can see retrieval, reasoning and provenance in one shot.

Usage::

    python examples/hello-world/ask_question.py "what did I learn about Cypher"
"""
from __future__ import annotations

import argparse
import sys

from exocortex.graph_rag import GraphRAGOrchestrator
from exocortex.settings import get_tenant_id


def _fmt_source(idx: int, src) -> str:
    title = src.title or "(untitled)"
    excerpt = (src.body_excerpt or "").strip().replace("\n", " ")
    if len(excerpt) > 140:
        excerpt = excerpt[:137] + "..."
    return (
        f"  [{idx}] {title}\n"
        f"      thought_id={src.thought_id}  score={src.score:.3f}  "
        f"provenance={src.provenance}\n"
        f"      “{excerpt}”"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Hello-world Exocortex query")
    parser.add_argument("question", help="natural-language question (in quotes)")
    args = parser.parse_args()

    orchestrator = GraphRAGOrchestrator(tenant_id=get_tenant_id())
    answer = orchestrator.answer(args.question, query_source="hello_world_example")

    if not answer.sources:
        print("No sources found. Did you run `python ingest_one_note.py` first?",
              file=sys.stderr)
        print(f"\nAnswer: {answer.response}")
        return 1

    print(f"Q: {args.question}\n")
    print("A:", answer.response, "\n")
    print(f"Sources ({len(answer.sources)}):")
    for i, src in enumerate(answer.sources, start=1):
        print(_fmt_source(i, src))
    print(f"\nLatency: {answer.latency_ms} ms · cost: ${answer.cost_usd:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
