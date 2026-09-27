---
id: F6
lang: en
counterpart: ../../pl/roadmap/F6-scale-and-collaboration.md
status: todo
provenance: ai_authored
provenance_metadata: {agent: "Claude Opus 5.5 (Cowork)", date: 2026-09-27, human_validated: false}
---

# F6. Scale and collaboration

[← Roadmap](../02-roadmap.md)

## Goal

The lab stops being a project of one person and one server. A second expert joins, rented compute becomes available for public data, scale L documents appear, and releases become permanent and citable.

The tasks are described here, without separate files.

## The phase is done when

The second expert has approved at least two gate decisions and rated at least one blind sample, at least one scale L document exists, and repository releases have DOIs.

## Tasks

### F6.1. Second expert

Rules of collaboration (pull requests to the repository, approving gates, rating blind samples), read-only access to the lab through MCP over HTTP with a token limited to the lab. A second rater makes it possible to compute agreement between raters, which strengthens every result. Done when the second person has rated one sample and agreement has been computed. Depends on F3.

### F6.2. Compute on demand

Rented GPUs for large configuration matrices, allowed only for samples of class `public`. The rule "data class and allowed providers" is written in the model router configuration and checked before every call. Done when one matrix has run on a rented GPU and a sample of another data class was refused. Depends on F2.6.

### F6.3. Scale L documents

A generator for a document on deployment in a large organisation, from a template (`templates/runbook-l.md`), with numbers computed from pilot measurements and a formula next to each number. Done when a document exists for an experiment that passed G2. Depends on F3.10.

### F6.4. Lab website

A section on exocortex.zone in both languages, generated from the repository: list of experiments, roadmap state, reports. Done when the page updates itself after every publication. Depends on F2.7.

### F6.5. Releases with DOIs

Integrating the repository with Zenodo: every release gets a permanent identifier and an archived copy that can be cited in documents. Done when the first release has a DOI. Depends on F1.

### F6.6. Kelter as the runner for agent experiments

Experiments in which a model carries out multi-step tasks with tools, run in Kelter on K12. Done when one agent experiment has gone through the lab queue. Depends on F2.6.
