---
id: progress
lang: en
counterpart: ../pl/03-progress.md
provenance: ai_authored
provenance_metadata:
  agent: Claude Opus 5.5 (Cowork)
  date: 2026-09-28
  human_validated: false
---

# Progress

A log of what has been done under the [roadmap](02-roadmap.md), newest entries first. The state of each task is in the header of its file. Here we record what changed, what is left and what came up along the way.

## 2026-09-28

The F0 and F1 work was done overnight by the agent, without the owner. Everything it did is waiting for review. The `human_validated` fields stay `false`.

### F0. The gate

The `leakgate` scanner checks text, files with metadata (photos, PDF, office documents), archives, Python packages, container images and commit metadata. The denylist has 11,613 HMAC hashes. In container images the scanner checks the configuration and the files that come from the repository. Executables and compiled Python code in an image are allowed, but their strings are checked too. The self-test plants 73 cases and all of them are caught.

The private corpus comparison (`simcheck`) has a calibrated literal similarity threshold (0.40). The semantic part needs an embedding model on the server and is not calibrated yet. That is why F0.6 has the status `doing`.

The nightly self-test is ready, but the nights do not count yet: they start after the first run on the server and in CI. The old package release on PyPI is waiting to be deleted by the owner.

### F1. The repository

A private working repository has been created. The engine code went through the export with an allowlist of paths, and the example configuration was written again with fictional data. The `code_en` tool found 604 fragments with Polish text in comments, docstrings and messages. 341 of them were changed. The rest were in English and had been flagged by a detector that was too sensitive and was fixed afterwards. Along the way, references to private task notes were removed.

Known debt: some user-facing strings (wiki headings, bot replies) are still in Polish, because they are program behaviour, not comments. Moving them to English needs language support in the engine and will be a separate task. The second debt is lint: `ruff` reports several hundred findings, so in CI that job reports but does not block.

The image and the package are built from an explicit list of paths. Package 0.2.0 passes the gate locally. CI on GitHub will run after the repository is first pushed and the gate key is added as a secret.

Documents have the `paritycheck` tool (PL and EN versions match) and `humanlint` (language model habits), plus a glossary of terms. The `humanlint` thresholds were set from texts written by people. The publisher and the systemd units for the server are ready and tested against a local repository. The first publication moved the documents into the working repository. Pushing to GitHub and starting it on the server are for the owner.

### F2. The first task

Task F2.3 does not need the server, so it was done right after F1. The headers of hypothesis cards, run notes, gate decisions and task files have JSON Schemas. The `docschema` script checks them in CI and in the publisher, and an error names the file, the field and the reason. A run note template was added, and the README describes the layout of experiment folders.

### Next

The owner's steps: delete the PyPI release, add the gate key to GitHub secrets, push the repository, start the publisher and the index on the server, review the code and the documents. Then seven nights of the self-test and the switch to public according to the conditions in the roadmap.
