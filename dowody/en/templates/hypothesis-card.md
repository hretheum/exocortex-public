---
type: hypothesis_card
lang: en
counterpart: ../../pl/templates/hypothesis-card.md
slug: "<slug>"
version: 1
supersedes: null
tier_target: S          # S | M | L
data_class: public      # the only allowed value in the lab
sources: []             # links to the signals the idea came from
prereg_hash: null       # filled in by the processor on approval, do not edit
human_validated: false
---

# Hypothesis: <what we are testing, in one sentence>

## Problem

What the question is about, who it matters to, what is known about it today and from where.

## Hypothesis

- H1: ... (what result refutes it?)
- H0: ...

## Metrics

| Role | Metric | Definition | Threshold | Baseline | How computed |
|---|---|---|---|---|---|
| deciding | | | | | |
| supporting | | | | | |
| guard | | | no worse than ... | | |

Confidence intervals: the Wilson method for proportions, bootstrap over units for continuous values.

## Samples

| Sample | Size | Sampling method | Seed | Checksum |
|---|---|---|---|---|
| tuning | | | | |
| control (opened once) | | | | |
| blind (scale M) | | | | |

## Configurations

| Name | Model | Variant | Parameters |
|---|---|---|---|
| baseline | | | |

## The assumption everything depends on

One assumption the experiment should measure instead of taking for granted.

## Gate criteria

- G1 (S to M): ...
- G2 (M to L): ...

## Stopping condition

When we stop early.

## What this method will not detect

At least one thing.

## Related work

The closest known approaches and how we differ from them.
