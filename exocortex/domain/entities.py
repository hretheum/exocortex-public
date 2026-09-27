# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# domain/entities.py — Domain entities (no infrastructure dependencies).
#
# F31-CLN-04: First step toward Clean Architecture — extract domain objects
# from infrastructure modules into a dependency-free domain layer.
#
# These are pure dataclasses: no ORM, no DB imports, no LLM SDK. The repository
# and use-case layers (future tickets) will depend on these.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Thought:
    """A typed, addressable unit of ingested content stored in the knowledge graph."""
    id: str
    body: str
    thought_type: str
    metadata: dict[str, Any] = field(default_factory=dict)
    extracted_tags: dict[str, Any] = field(default_factory=dict)
    embedding: Optional[list[float]] = None
    created_at: str = ""


@dataclass
class SynthesisResult:
    """Result of an LLM synthesis pass over a set of thoughts."""
    perspective_type: str
    perspective_key: str
    status: str  # 'ok' | 'skipped' | 'below-threshold' | 'no-thoughts' | 'error'
    reason: str = ""
    content: Optional[dict[str, Any]] = None
    source_thought_ids: list[str] = field(default_factory=list)
    input_hash: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0
    synthesis_id: Optional[str] = None
    superseded_id: Optional[str] = None


@dataclass
class Source:
    """A ranked thought fragment returned by GraphRAG retrieval."""
    thought_id: str
    title: str
    body_excerpt: str
    score: float
    rank_vector: Optional[int] = None
    rank_graph: Optional[int] = None
    edge_path: list[str] = field(default_factory=list)
    provenance: str = "human"


@dataclass
class Answer:
    """A synthesized response to a user question with cited sources."""
    question: str
    response: str
    sources: list[Source]
    cost_usd: float
    latency_ms: int
    usage: dict[str, int] = field(default_factory=dict)
    cache_hit: bool = False


@dataclass
class Classification:
    """Result of classifying a thought into client/project/person."""
    source_slug: str
    clients: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    person_slug: Optional[str] = None
    confidence: float = 1.0
    matched_by: str = ""  # e.g. 'slug', 'alias', 'body_match'
