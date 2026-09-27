---
type: gate_decision
lang: en
counterpart: ../../pl/templates/gate-decision.md
hypothesis: "<slug>"
hypothesis_version: 1
gate: G1                # G0 | G1 | G2
decision: null          # GO | NO-GO | PIVOT | NOT-NOW | CLOSED
date: "<YYYY-MM-DD>"
approved_by: []
return_condition: null  # required for NOT-NOW
result_ids: []          # ids of the results the decision rests on
human_validated: false  # without true the processor ignores the decision
---

# Gate <G?>: <hypothesis>

## Criteria from the hypothesis card (unchanged)

| Criterion | Threshold | Result | Confidence interval | Result id | Met |
|---|---|---|---|---|---|

## Guard metrics

| Metric | Limit | Result | Met |
|---|---|---|---|

## Errors

Main error classes with counts. Can they be removed by changing the prompt, the schema or a filter, or do they come from the approach itself.

## Decision

The decision and its reasons in a few sentences. If the decision goes against the numbers, say so plainly and why.

## What next

On GO, the scope of the next scale. On PIVOT, what the new card version changes. On NO-GO, what we learned.
