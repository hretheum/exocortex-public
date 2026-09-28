---
type: run_note
lang: en
counterpart: ../../pl/templates/run-note.md
hypothesis: "<slug>"
hypothesis_version: 1
run_id: "<run-id>"        # run-<date>-<n>, unique within the hypothesis
date: "<YYYY-MM-DD>"
sample: tuning            # tuning | control | blind
configuration: baseline   # a name from the Configurations table of the card
code_commit: null         # commit of the lab code the run used
prereg_hash: null         # copied from the approved card
result_ids: []            # filled in by the processor
human_validated: false
---

# Run <run-id>: <configuration> on <sample>

## What was run

Model, variant, parameters, and anything that differs from the card. If nothing differs, say so.

## Result

| Metric | Value | Confidence interval | Result id |
|---|---|---|---|

## What went wrong or looked odd

Errors, restarts, items skipped and why. An empty section means nothing happened, not that nobody looked.
