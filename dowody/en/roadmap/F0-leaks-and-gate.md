---
id: F0
lang: en
counterpart: ../../pl/roadmap/F0-leaks-and-gate.md
status: doing
provenance: ai_authored
provenance_metadata: {agent: "Claude Opus 5.5 (Cowork)", date: 2026-09-27, human_validated: false}
---

# F0. Stopping leaks and the publishing gate

[← Roadmap](../02-roadmap.md)

## Goal

Before anything new becomes public, we check what is public already and build a mechanism that lets nothing from client material through. The project rules were written later than some Exocortex artifacts (a container image, a Python package), so those artifacts have to be checked against the rules and whatever does not meet them has to be withdrawn.

The gate has three layers. The text and file scanner looks for forbidden names, personal data and metadata. The build artifact scanner unpacks packages and container images before they are pushed. The comparison with the private corpus catches fragments reworded so that they no longer contain any name. The whole gate is tested every night on cases with deliberately planted leaks.

## The phase is done when

- no previously published artifact breaks the rules, or it has been withdrawn,
- the scanner runs locally before each commit and in CI before every publication,
- the nightly gate test passes in full for at least seven days in a row.

## Tasks

| Id | Task | Depends on | Estimate |
|---|---|---|---|
| [F0.1](F0/F0.1-close-leaking-channels.md) | Turn off public access to artifacts made before the rules and stop publishing them automatically | | 1 h |
| [F0.2](F0/F0.2-exposure-audit.md) | List every place where something from the project is public and check each one | F0.1 | 4 h |
| [F0.3](F0/F0.3-denylist.md) | Build the private list of forbidden names and its hashed version | F0.2 | 4 h |
| [F0.4](F0/F0.4-scanner-text-and-files.md) | Write the text and file scanner | F0.3 | 1 day |
| [F0.5](F0/F0.5-scanner-build-artifacts.md) | Extend the scanner to packages and container images | F0.4 | 4 h |
| [F0.6](F0/F0.6-similarity-check.md) | Build the comparison with the private corpus on K12 | F0.4 | 1 day |
| [F0.7](F0/F0.7-gate-self-test.md) | Gate test suite run every night | F0.4, F0.5, F0.6 | 1 day |

## Two design decisions

The list of forbidden names cannot live in the public repository, because it would be a leak in itself. The repository only gets HMAC hashes made with a secret key. Plain hashes are not enough: a short company name can be guessed by hashing a dictionary of names.

The scanner never prints the text it found. CI logs of a public repository are public, so the report gives only the file, the line, the rule id and a hash of the match.
