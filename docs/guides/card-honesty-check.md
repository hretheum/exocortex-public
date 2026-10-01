# Honesty check for the reference card text

Roadmap task F4.3. Code: `exocortex/lab/honesty.py`. Tests: `tests/lab/test_honesty.py`
with the prepared sentences in `tests/lab/data/honesty/`.

The reference project card (F4) is assembled by the card compiler (F4.2)
from the lab's recorded results. Before a card reaches a buyer, this check
reads it sentence by sentence and reports every sentence that sounds more
certain than its evidence. It changes nothing; it only lists violations.

## Input: sentence records

The compiler writes the card as a list of records, one per sentence, in
card order, as JSON Lines (one object per line) or one JSON list:

| field | type | meaning |
|---|---|---|
| `text` | string, required | the sentence exactly as printed on the card |
| `mode` | `fact`, `plan`, `requirement` or `hypothesis`, required | what the compiler meant the sentence to be |
| `source_ref` | string or null | repository path of the source; `path#<result_id>` when the sentence rests on one recorded result |
| `source_mode` | one of the four modes, or null | the mode of the source itself; needs `source_ref` |
| `numbers` | list of numbers | the recorded values the compiler put into the text, unrounded |
| `date` | `YYYY-MM-DD` or null | the date the sentence is true as of |

Records are validated when read (`Sentence` dataclass): an unknown field,
an unknown mode, a `source_mode` without `source_ref`, a non-finite number
or a date that is not ISO is an input error (exit code 2).

How the compiler should produce them:

* One record per printed sentence, in order, with `text` identical to the
  printed text (the check reports violations by 1-based sentence number).
* `mode` follows from the card section and graph node the sentence comes
  from: results and gate decisions are `fact`, the frozen hypothesis is
  `hypothesis`, next steps are `plan`.
* `source_ref` is the link printed next to the sentence. For a number from
  an experiment, point at the metric row:
  `dowody/data/<slug>/metrics.csv#<result_id>`, or at a run's result count:
  `dowody/data/<slug>/results.csv#<slug>/<run_id>[/<config>]`.
* `source_mode` is the mode of that source node (a measured result is
  `fact`; a phase document's task description is `plan`).
* `numbers` lists the raw recorded values the compiler rounded into the
  text, so the check can confirm both that they are recorded and that the
  text shows them.
* `date` is set for every sentence about the current state (see rule 3);
  the compiler should also print it.

## The three rules

1. **`fact-source`**: a sentence that reads as a fact must rest on a source
   in fact mode. Whether it reads as a fact is decided by a mode classifier
   (the F3 classifier of fact, plan, requirement and hypothesis), injected
   as the `ModeClassifier` protocol: `classify(text) -> mode`. If either the
   classifier or the compiler's label says `fact`, `source_mode` must be
   `fact`. A plan written in the present tense ("The generator fills in
   buyer forms.") therefore fails even when the compiler labelled it a plan.
2. **`recorded-number`**: every number in the text must be a recorded
   result, within the rounding tolerance below. When `source_ref` names a
   result (`#<result_id>`), only that result's numbers count; a result id
   that is not recorded is itself a violation. Without a result id, any
   recorded number counts. Every value in `numbers` must be recorded and
   must appear (rounded) in the text.
3. **`dated-state`**: a sentence about the current state must carry a date,
   in `date` or in the text itself ("As of 30 September 2026", "stan na
   30 września 2026", "2026-09-30"; a month with a year also counts, a
   month alone does not). Quotation marks do not exempt a word: `the
   pipeline "works"` still needs a date.

Recorded results are the published experiment files `metrics.csv` and
`results.csv` under `dowody/data/<slug>/`:

* per metric row (`result_id`): `value`, `ci_low`, `ci_high`, `n` and every
  number in `details`;
* per run (`<slug>/<run_id>`) and per run and configuration
  (`<slug>/<run_id>/<config>`) of `results.csv`: the number of results, of
  successful ones and of failed ones.

### Numbers in the text

Digits with a decimal point or a Polish decimal comma (`8.3`, `8,3`),
thousands separated by a no-break space (`2 521,5`), a comma with exactly
three digits after it read both ways (`1,000` is 1.0 or 1000), a sign
(`−0.2`), and numbers written in words in English and Polish, including
compounds and common inflected forms (`seventy-five`, `dwunastu`,
`sto dwadzieścia`, `half`, `połowa`).

A number followed by `%`, `percent`, `procent`, `pp`, `percentage points`
or `punktów procentowych` is compared both as written and divided by 100,
because the lab records shares as fractions. In a range such as
`1.5–35.4%` the sign covers both ends.

Not counted as numbers: digits glued to a letter (`F3`, `G1`, `v1`,
`qwen3.6`), anything in backticks, URLs and Markdown link targets, paths
and run labels (`run-2026-09-29-1`), dates, a year after `in`/`since`/`w`/
`od` or before `r.`/`roku`, and `one`/`jeden` on its own (more often a
pronoun or article than a count). Every other number counts, including
small counts such as "two models".

### Rounding tolerance

A number shown with `d` digits after the decimal mark is an honest
rounding of a recorded value `r` when both hold:

* `|r − shown| ≤ 0.5 × 10^−d`: it is `r` rounded to the digits shown
  (`ROUNDING` in the code);
* `|r − shown| ≤ 5 % of |r|`: coarse rounding cannot stand in for a
  different number (`REL_TOLERANCE`).

An exact match always passes. Examples against the published toy
experiment: 0.0833 may be written `8.3%` or `8%` but not `10%`; 2521.5 may
be written `2521.5` or `2522` but not `2500`; 0.75 may not be written `0.7`
(within half a unit, but 6.7 % away).

### Current-state words

English: works, working, currently, at present, presently, right now,
as of now, nowadays, is/are running, in production, is live, is/are
deployed, today. Polish: działa (and działają, działający, ...), obecnie,
aktualnie, teraz, w tej chwili, na dziś, dziś, dzisiaj, jest/są wdrożony,
na produkcji. "related works", "prior works" and similar are not state.

## Running it

```
exocortex lab honesty card.jsonl --data dowody/data/intent-vs-fact
python -m exocortex.lab honesty card.jsonl --data dowody/data --modes modes.jsonl
```

`--data` is repeatable and takes an experiment folder or a folder of them
(default `dowody/data`). `--modes` is the classifier's output computed
beforehand, JSON Lines `{"text": ..., "mode": ...}`; without it the check
uses the compiler's labels only, which still catches a fact label on a
non-fact source but not a plan written as a fact. The command makes no
model calls.

The command prints one JSON document, like every lab command:

```json
{
  "command": "honesty",
  "card": "card.jsonl",
  "sentences": 15,
  "classifier": "precomputed",
  "recorded_results": 32,
  "violations": [
    {"sentence": 4, "rule": "dated-state",
     "message": "'works' describes the current state, but the sentence has no date"}
  ]
}
```

Exit code 0 with no violations, 1 with violations, 2 when the input is
invalid.
