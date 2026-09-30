# Lab corpora

Data sets used by lab experiments. Each folder is built by a script in
`lab/corpus/` and described (sources, basis for use, sampling frame) in the
experiment's documents under `dowody/{pl,en}/experiments/<slug>/`.

| Folder | Built by | Records |
|---|---|---|
| `intent-vs-fact/` | `lab/corpus/intent_vs_fact.py` | arXiv abstracts (CC0 metadata) with the engine's Polish summaries |
| `toy-format/` | written by hand | 42 synthetic prompts for three JSON Schemas for the toy answer format conformity experiment (F5.9) |
| `toy-retrieval/` | written by hand | 60 synthetic documents, their edges and hand-made questions for the toy retrieval experiment (F5.8) |

Each folder holds `corpus.jsonl`, `manifest.csv` (checksums over
whitespace-normalised text) and `excluded.csv` (what was left out and why).
Papers the publishing gate holds because they contain a name from its
private list are left out through a private file and appear only as
"(withheld)", since their ids would point at the names.

Rebuilding on another machine should give the same checksums, except where
arXiv has since published a new version of a paper.

## Retrieval question sets

Experiments of the kind `retrieval` (exocortex/lab/retrieval.py) need a question set with gold answers, prepared by
hand, as files in the corpus folder: one file per sample, named by the `items:` of the spec. `questions-*.csv` has
the header `question_id,question,gold`; `gold` lists document ids separated by `;`, each with an optional grade
from 0 to 3 after a colon (`d004;d005:2;d011:0`; no grade means 1, grade 0 marks a document judged not relevant).
The same can be written as JSON lines (`{"question_id": "q01", "question": "...", "gold": {"d004": 1, "d005": 2}}`).
Files are read strictly: any problem, with its line, stops the run, and gold ids must be documents of the corpus
(`documents.jsonl` for small corpora, `manifest.csv` for corpora in the lab graph). Check a spec and its files
without a database: `exocortex lab retrieval validate --experiment <slug>`.

## Format conformity prompts and schemas

Experiments of the kind `format_conformity` (exocortex/lab/format_conformity.py) read two things from the corpus folder:
`schemas/<name>.json`, one JSON Schema (draft 2020-12, the subset listed in the module's docstring) per file, and one
prompt file per sample, named by the `items:` of the spec. `prompts-*.csv` has the header `item_id,prompt,schema`
and optionally `grammar`; `schema` names a file in `schemas/`, and `grammar` is a label of a GBNF grammar, stored and
never sent. The same can be written as JSON lines with the same keys. A prompt may span lines (quoted in CSV).
Files are read strictly: any problem, with its line, stops the run, and every schema reference must name a schema
file that loads. Check a spec and its files without a database:
`exocortex lab format_conformity validate --experiment <slug>`.

The spec may link the experiment to the claims kind for the guard metric (claim quality):

    params:
      guard: {experiment: <slug of a claims experiment>, metric: <metric name>}

The slug must have a spec in `lab/experiments/` of the kind `claims`, and the metric is a name such as
`usable_per_document`. The link is stored with the experiment's params and carried into the results as a row with no
value (method `reference`); the number itself is computed by the claims kind, not by this kind.
