# Reference card compiler

Roadmap task F4.2. Code: `exocortex/lab/card_compiler.py`. Tests: `tests/lab/test_card_compiler.py`.

The compiler turns the files the lab has published about one experiment into a reference project card, in
Polish and in English, with a link next to every sentence to the file or data row it comes from. It reads
files only: no database, no model calls, no network.

```
exocortex lab card-compile toy-length
exocortex lab card-compile toy-length --out build/cards --as-of 2026-10-01
python -m exocortex.lab card-compile intent-vs-fact --base-url ""
```

| option | meaning |
|---|---|
| `slug` | the experiment, as in `dowody/data/<slug>/` |
| `--out` | output folder; default is a new temporary folder (the command prints the file names) |
| `--as-of` | date of the sentences about the current state, `YYYY-MM-DD`; default is today (UTC) |
| `--root` | repository root; default is this checkout |
| `--base-url` | prefix of the links; default is the public repository's `blob/main/` address; an empty value gives paths relative to the repository root |

Exit code 0 when both checks below pass, 1 when one of them reports something, 2 when the experiment cannot be
compiled (for example, it has no hypothesis card in both languages).

Nothing is published. The compiler writes only to `--out`; it does not touch the vault or the
`{pl,en}/generated/` folders. Connecting its output to publication is a separate decision.

## What it reads

| input | used for |
|---|---|
| `dowody/<lang>/experiments/<slug>/hypothesis.md` | the card: problem, hypothesis, metrics, gate criteria, stopping condition, assumption, limits, related work, version, approval |
| `dowody/prereg.jsonl` | whether the card version is frozen (registered, and its checksum still matches) |
| `dowody/data/<slug>/` | `metrics.csv`, `results.csv`, `runs.csv`, `configs.csv`, `samples.csv`, `datapackage.json` |
| gate decision documents (`type: gate_decision`, `hypothesis: <slug>`) | the last approved gate decision, hence the project status |
| `dowody/<lang>/generated/experiments/<slug>.md` | only to cite where the dossier says that no gate decision exists |

## What it writes

For each language `<lang>` (`pl`, `en`), in `--out`:

| file | content |
|---|---|
| `<slug>.card.<lang>.yaml` | the card in the format of the card model (F4.1): per sentence the text, mode, source and, for the current state, the date. Checked by `exocortex lab card-check` |
| `<slug>.card.<lang>.md` | the same sentences as Markdown, one bullet per sentence, ending with one link |
| `<slug>.sentences.<lang>.jsonl` | one record per sentence for the honesty check (F4.3): text, mode, `source_ref`, `source_mode`, `numbers`, `date`. Checked by `exocortex lab honesty` |

`compile_card` runs `card-check` and the honesty check on its own output and prints the result under `checks`.

## How sentences are made

Every sentence is one of two kinds, and nothing else is ever written:

1. A template of the module, in Polish or English, filled with values from the files: a run and its code
   commit, a configuration, a sample, a metric value with its confidence interval and n, a count of results.
2. A bullet or paragraph of the hypothesis card, quoted word for word from the card of that language
   (the problem, the hypotheses, the gate criteria, the stopping condition, the assumption, the limits, the
   related work).

Sections follow the card model:

| section | built from |
|---|---|
| goal and context | card "Problem"; the documents the card header lists as sources |
| hypothesis | card "Hypothesis"; the card version, what it replaces; its state as of the date (draft, frozen, changed since registration) |
| experiments and iterations | one sentence per run (sample, card version, code commit, status, count of results and of failures) and per configuration |
| validation method | the card's metrics table and gate criteria; one sentence per sample; the statistical method of each metric |
| results | one sentence per row of `metrics.csv`, with the sample role; for a run without metrics, a sentence saying so |
| next steps | project status; last approved gate decision, its result ids, its return condition; gate decisions that are not applied and why; the card's stopping condition |
| novelty | card "Related work" |
| risks and limitations | card "The assumption everything depends on" and "What this method will not detect"; guard metrics; failed items with the first reason |
| how to verify | the recompute command of the data package; the code commit of each run; the registered checksum; the preregistration check |

A section whose data do not exist says so instead of guessing. An experiment without runs gets "no run is
recorded", an experiment with runs but without `metrics.csv` rows gets one sentence per run saying that no
metric has been published, and so on. The results section accepts only data rows as sources in the card model,
so for "no results yet" the compiler cites the first run, configuration, sample or registry row that exists. If
none exists the compile stops with an error rather than citing something unrelated.

## Links

| source | link |
|---|---|
| a file | `<base>/<path>` |
| a Markdown heading | `<base>/<path>#<GitHub anchor of the heading>` |
| a data row | `<base>/<path>?plain=1#L<line the row starts on>` |

A data row is always one row: the card file names it by column values, and `card-check` refuses a source that
matches zero or several rows. The tests open every link of a compiled card: the file exists, the anchor is a
heading of it, the line starts exactly one row and that row is the one the card names.

## Project status

The status is the decision of the last applied gate decision for the card's current version, and never higher
(`project_status`). Without one it is `frozen` (the card is registered and its text still matches the
registered checksum) or `draft`. A card without a decision cannot say GO, NO-GO, PIVOT, NOT-NOW or CLOSED.

A gate decision document is applied when:

- both language versions exist, their headers pass the document schema and agree on hypothesis, version, gate,
  decision, date, result ids and return condition;
- both say `human_validated: true`;
- decision and gate are among the allowed values, and NOT-NOW has a return condition;
- it decides the current card version, and that version is frozen: registered and unchanged;
- it names result ids and each one is in `metrics.csv`.

This repeats the rules of the gate processor (`exocortex/lab/gates.py`) that can be checked from files. It does
not compare thresholds with the card; the processor does that against the database. A document that fails a
rule is not applied, and the card says which rule in a sentence that cites the document.

The wording of each state on the card is fixed in the templates (draft, frozen, and the five decisions).

## How the card stays honest

The honesty check accepts a number only when it is a recorded result. The compiler makes that true by
construction:

- A sentence that rests on one recorded result (a metric row, a run's counts) shows its numbers as they are,
  rounded to enough digits to be an honest rounding of the recorded value.
- Any other number (a threshold, a seed, a sample size, a year) is printed in code format, as the honesty
  check allows for parameters and identifiers. A threshold that happens to equal a recorded count is marked
  too. Number words in quoted card text ("zero", "three") are marked the same way, because the check reads
  them as numbers.
- A quoted card sentence with a word that speaks about the present ("works", "currently") is attributed to the
  card and dated: "As of 2026-10-01, the card says: ...".
- Statements about the current state carry `as_of` in the card and `date` in the sentence records, and the date
  is printed in the sentence.

The honesty check inside the compiler runs with the compiler's own mode labels. To also use a precomputed
output of the F3 mode classifier, run `exocortex lab honesty <slug>.sentences.<lang>.jsonl --modes <file>`
on the written records.

Modes and source modes: problem, limits, related work, metric definitions and recorded data are `fact`; the
hypothesis bullets are `hypothesis`; gate criteria and the rules of the compiler and gate processor are
`requirement`; the stopping condition is `plan`.

## Open decisions

These follow from the open decisions of the card model (`lab/card-model.yaml`) and are the owner's to settle.

- **OD-4**: results are all rows of `metrics.csv`, with the sample role stated. They are not restricted to
  the result ids of an applied gate decision.
- **OD-5**: states are shown with the fixed wordings in the templates; there is no wording table agreed with
  the owner.
- **No data at all**: the results section cannot cite a file in the card model, so an experiment with no data
  row of any kind cannot be compiled.
- **Data fields in English**: sample sampling methods and error reasons come from the data files and are quoted
  as they are, so a Polish card shows them in English.
- **Publication**: where compiled cards go, and when they are regenerated, is not decided.
