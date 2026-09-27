---
id: F4
lang: en
counterpart: ../../pl/roadmap/F4-reference-card.md
status: todo
provenance: ai_authored
provenance_metadata: {agent: "Claude Opus 5.5 (Cowork)", date: 2026-09-27, human_validated: false}
---

# F4. Reference project card from the graph

[← Roadmap](../02-roadmap.md)

## Goal

The reference project card is no longer written by hand. A compiler assembles it from the lab graph: the hypothesis from the frozen card, the validation method from the experiment description, results from the tables, next steps from gate decisions. Every sentence links to its source in the public repository, and the text goes through a check that catches numbers without a source and plans described as facts.

The tasks are described here, without separate files. Details will be settled after F3.

## The phase is done when

The card for the F3 experiment is generated in both languages, every number has a link, the honesty check passes, and the same card fills in a sample tender form.

## Tasks

### F4.1. General card model

Card sections as a neutral schema, independent of any particular form: goal and context, hypothesis, experiments and iterations, validation method, results, next steps, what is new compared with related work, risks and limitations, how to verify. For each section: which graph nodes its content comes from. Done when the schema is published in both languages. Depends on F2.

### F4.2. Card compiler

Generates the card in markdown, in Polish and in English, with a link next to every sentence to a file or data row in the repository. Project status follows from the last approved gate and is never higher. Done when the card for F3 is generated and every link works. Depends on F4.1 and F3.

### F4.3. Honesty check for the card text

Three rules: a sentence in fact mode must have a source in fact mode (the mode classifier from F3), a number in the card must appear in a recorded result, a sentence about current state ("works", "currently") must have a date. Done when the check stops a set of prepared bad sentences and passes the F4.2 card. Depends on F4.2.

### F4.4. Filling in tender forms

The generator code that moves card sections into the fields of a particular form (for example an xlsx sheet) is public and general. The mapping from sections to the fields of a specific form is private and lives outside the repository, because the form belongs to the contracting party. Done when the generator fills in a sample form prepared by us. Depends on F4.2.
