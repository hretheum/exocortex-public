---
id: F6
lang: en
counterpart: ../../pl/roadmap/F6-scale-and-collaboration.md
status: doing
task_status: {F6.4: doing}
provenance: ai_authored
provenance_metadata: {agent: "Claude Opus 5.5 (Cowork)", date: 2026-09-27, human_validated: false}
---

# F6. Scale and collaboration

[← Roadmap](../02-roadmap.md)

> **Status: in progress** · as of 30 September 2026
>
> Task F6.4 (the lab website) is in progress, the other five are waiting, and no task is done yet (0 of 6). The site lab.exocortex.zone is published and refreshes every hour, but it does not yet update right after each publication, and the text "How Exocortex R&D works" will appear on it once the publishing gate releases the document. Tasks F6.2, F6.5 and F6.6 have no unmet dependencies and can start at any time, while F6.1 and F6.3 wait for the first experiment from F3.

## In short

This phase makes the lab stop being a one-person project on a single server. A second person who rates results joins, compute can be rented for large measurements, and there is a public site and permanent, citable releases.

## Why this phase

A result rated by one person is hard to trust, because nobody knows whether someone else would have rated it the same way. A second person makes it possible to compute the agreement between raters, which strengthens every result. A permanent DOI identifier lets one cite a specific release of the lab, for example in a bid, and be sure that in a year the same thing will be under that link. The site lab.exocortex.zone is the place to send someone who wants to see what the lab does and where its conclusions come from.

## Goal

The lab stops being a project of one person and one server. A second expert joins, rented compute becomes available for public data, scale L documents appear, and releases become permanent and citable.

The tasks are described here, without separate files.

## The phase is done when

The second expert has approved at least two gate decisions and rated at least one blind sample, at least one scale L document exists, and repository releases have DOIs.

## Tasks

### F6.1. Second expert

**Status: to do** — not started; waits for the first experiment (F3).

Why: the agreement between two raters shows how much a result depends on who did the rating.

Rules of collaboration (pull requests to the repository, approving gates, rating blind samples), read-only access to the lab through MCP (a protocol AI assistants use to read data from external tools) over HTTP with a token limited to the lab. A second rater makes it possible to compute agreement between raters, which strengthens every result. Done when the second person has rated one sample and agreement has been computed. Depends on F3.

### F6.2. Compute on demand

**Status: to do** — not started; its dependency (F2.6) is done, so the task can start at any time.

Why: large configuration matrices take long on a single server, and rented GPUs (graphics cards for model computation) speed them up; the data-class rule makes sure they get only public data.

Rented GPUs for large configuration matrices, allowed only for samples of class `public`. The rule "data class and allowed providers" is written in the model router configuration (the program that sends each call to the right model) and checked before every call. Done when one matrix has run on a rented GPU and a sample of another data class was refused. Depends on F2.6.

### F6.3. Scale L documents

**Status: to do** — not started; waits for F3.10 (the report of the first experiment), which has not started either.

Why: a large organisation asks not about the lab result but about what happens with thousands of users: cost, hardware needs. A scale L document answers with numbers computed from the pilot's measurements, with a formula next to each.

A generator for a document on deployment in a large organisation, from a template (`templates/runbook-l.md`), with numbers computed from pilot measurements and a formula next to each number. Done when a document exists for an experiment that passed G2. Depends on F3.10.

### F6.4. Lab website

**Status: in progress** — the site is published (a separate repository, GitHub Actions, custom domain, HTTPS) and refreshes every hour; still missing are a build triggered by each publication and the "How it works" text, which waits for the publishing gate to release it.

Why: without a site the results are scattered across files in the repository, and the site assembles them into readable hypothesis dossiers for someone who does not know the project.

The site lab.exocortex.zone in both languages (`/en` and `/pl`, the root address redirects to `/en`), generated from the repository: how the lab works, the list of hypotheses with their statuses, a dossier for every hypothesis (abstract, preregistration, data with checksums and files to download, runs, results, gate decisions, deviations, reproduction, limitations, how to cite) and the roadmap state. The site is static and runs on GitHub Pages in a separate, small repository, because exocortex.zone occupies the only Pages site of the main repository. The generator is in the `lab-site/` folder. Done when the site updates itself after every publication. Depends on F2.7.

### F6.5. Releases with DOIs

**Status: to do** — not started; the task has no dependencies.

Why: a DOI, a permanent identifier of an archived copy (like those of scientific publications), lets one cite a specific release and return to it years later.

Integrating the repository with Zenodo: every release gets a permanent identifier and an archived copy that can be cited in documents. Done when the first release has a DOI.

### F6.6. Kelter as the runner for agent experiments

**Status: to do** — not started; its dependency (F2.6) is done, so the task can start at any time.

Why: some research concerns models that plan and carry out successive steps with tools on their own (agents), and that needs a runner other than a single request to a model. Kelter is our open-source environment for running such agents.

Experiments in which a model carries out multi-step tasks with tools, run in Kelter. Done when one agent experiment has gone through the lab queue. Depends on F2.6.

## Progress

- 2026-09-29: F6.4. The site lab.exocortex.zone is published from the separate repository `lab-site-repo` through GitHub Actions, with a custom domain and HTTPS, and refreshes every hour. It shows three hypothesis dossiers, the roadmap status and the infographics. The text "How Exocortex R&D works" will appear once the gate releases that document; until then the site shows the infographics with a notice. The completion condition (an update after every publication) is met in the form of an hourly build; what remains is adding a build triggered by publication.
