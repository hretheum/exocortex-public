---
type: triage
lang: en
counterpart: ../../pl/templates/triage.md
date: "<YYYY-MM-DD>"
human_validated: false
---

# Selecting candidates

## Knock-out questions

A single "no" means the candidate is set aside with a recorded reason and a condition for coming back.

| Candidate | Do we know why? | Is there data? | Legal? | Can it be measured? | No simpler way without AI? | Passes |
|---|---|---|---|---|---|---|

## Scoring

Scale from 1 to 5, a higher score is better. Weights are set before scoring.

| Dimension | Criterion | Weight | 1 | 3 | 5 |
|---|---|---|---|---|---|
| Value | will the result change anything for anyone | 25% | a curiosity | useful | changes decisions |
| Feasibility | do we have the tools and compute | 15% | none | to be built | ready |
| Effort (reversed) | time to the first gate | 15% | over a month | a week | a day |
| Data | is public data available and good | 15% | none | needs work | ready |
| Risk (reversed) | law, privacy, reputation | 10% | high | medium | low |
| Evidence value | can the result be published and checked | 10% | no | partly | fully |
| Portfolio gap | does it fill what our track record lacks | 10% | no | partly | directly |

Evidence value and portfolio gap help set the order. They cannot push through a candidate that failed the knock-out questions.

## Scores

| Candidate | Rater | Value | Feasibility | Effort | Data | Risk | Evidence | Gap | Total |
|---|---|---|---|---|---|---|---|---|---|

Raters are people or models from different families, each scoring independently. A difference of at least two points in any dimension means the candidate needs a discussion. Scores are not averaged in that case.

## Decision

| To a quick test | Set aside (with a condition for coming back) | Rejected (with a reason) |
|---|---|---|
