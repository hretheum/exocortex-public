# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# config/models.py — Pydantic models for YAML config validation.

from __future__ import annotations


from pydantic import BaseModel, Field


class TagItem(BaseModel):
    """Single entry in tag_taxonomy.yaml (client, project, activity, topic, status)."""

    tag: str
    display_name: str
    description: str
    aliases: list[str] = Field(default_factory=list)
    domain: str = 'work'


class TagTaxonomy(BaseModel):
    """Root model for config/tag_taxonomy.yaml."""

    client: list[TagItem] = Field(default_factory=list)
    project: list[TagItem] = Field(default_factory=list)
    activity: list[TagItem] = Field(default_factory=list)
    topic: list[TagItem] = Field(default_factory=list)
    status: list[TagItem] = Field(default_factory=list)

    @classmethod
    def from_yaml(cls, data: dict) -> 'TagTaxonomy':
        """Validate raw dict loaded from yaml.safe_load."""
        return cls(**data)
