# Lab corpora

Data sets used by lab experiments. Each folder is built by a script in
`lab/corpus/` and described (sources, basis for use, sampling frame) in the
experiment's documents under `dowody/{pl,en}/experiments/<slug>/`.

| Folder | Built by | Records |
|---|---|---|
| `intent-vs-fact/` | `lab/corpus/intent_vs_fact.py` | arXiv abstracts (CC0 metadata) with the engine's Polish summaries |

Each folder holds `corpus.jsonl`, `manifest.csv` (checksums over
whitespace-normalised text) and `excluded.csv` (what was left out and why).
Papers the publishing gate holds because they contain a name from its
private list are left out through a private file and appear only as
"(withheld)", since their ids would point at the names.

Rebuilding on another machine should give the same checksums, except where
arXiv has since published a new version of a paper.
