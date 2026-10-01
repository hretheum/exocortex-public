---
id: card-compiler
lang: en
counterpart: ../pl/08-card-compiler.md
provenance: ai_authored
provenance_metadata:
  agent: Claude Code (cloud session)
  date: 2026-10-01
  human_validated: false
---

# The reference card compiler

A reference card describes a completed project for a bid or a tender. This document explains the program that writes such cards from the lab's records: what it reads, what it writes, and why the card it produces can be trusted. It is task F4.2 of phase [F4](roadmap/F4-reference-card.md). The shape of the card is described in [General model of a reference card](07-card-model.md).

## Why

A card written by hand drifts away from the facts. A number is remembered wrongly, a plan is written as if it were done, a project is called a success before anyone decided that. The buyer cannot check. The compiler removes the hand from the process: it takes the card only from files that the lab has already published, and next to every sentence it puts a link to the file or the row of data where the sentence comes from. A reader can open each link and see the source.

## How it works

The program is called `exocortex lab card-compile`, and it is given the name of an experiment. It reads the hypothesis card (in Polish and English), the table of runs, samples, configurations and metrics, the preregistration registry and the gate decisions, if there are any. It then writes the card twice, in Polish and in English, in nine sections that always come in the same order.

Every sentence is made in one of two ways. Either it is a sentence pattern filled with values from the data, for example "In run X on sample Y the metric Z was 0.083, with a confidence interval from 0.015 to 0.354." Or it is a passage of the hypothesis card copied word for word. The program does not call a language model and does not write anything of its own.

If something is missing, the card says so. For an experiment that has been run but not yet measured, the Results section holds one sentence per run: "no metric for it has been published as of this date". It never fills the gap with a guess.

## The project status

The status on the card comes from the last gate decision that a person has approved, and it is never higher. If no gate has decided, the status is "frozen" (the hypothesis card is registered and has not changed since) or "draft". A card without a decision cannot say GO. The tests check this directly.

A gate decision counts only if both language versions exist and agree, a person has approved both, it concerns the current version of the card, and the results it names exist in the data. Otherwise the card lists the document and says why it was not applied.

## Honest numbers

A number that is a measured result is shown as it was recorded, rounded sensibly. A number that is only a setting, for example a threshold, a random seed or a sample size, is shown in code format, so it cannot be taken for a result. A sentence about the present state always carries the date.

After writing, the program runs two checks on its own output: whether the card follows the model, and whether any sentence sounds more certain than its evidence. Both must find nothing.

## An example

For the toy experiment, the one that tests the lab's machinery, the program writes 60 sentences in each language. The status line reads: "As of 2026-10-01, the project status is draft: the hypothesis card is not frozen." One of the results reads: "In run `run-2026-09-29-1` on sample `tuning-12` (role: tuning), the metric `long_unit_share` for configuration `longest-sentence` was 0.833 (confidence interval 0.552 to 0.953, n = 12, method `wilson`)." Next to it is a link to the exact line of the file with the metrics.

## What it does not do yet

- The first real experiment has no results yet, so there is no card for it. When the results come, the same command produces it.
- The program does not publish anything. The cards go to a folder of your choice. Deciding where they are published, and when they are refreshed, is left open.
- The Results section shows every recorded metric. Whether it should show only the results a gate decision rests on is an open question in the card model.
