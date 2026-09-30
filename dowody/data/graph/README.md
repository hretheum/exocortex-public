# Public graph package of the Exocortex lab

Each folder `v1-<hash>` holds one version of the package: the claims the lab extracted from public corpora,
the verbatim quote of every claim with its position in the source document, the relations between documents
and claims, and the embeddings of the documents. `latest.json` names the current version. Older versions stay
in the history of the repository.

| File | What it holds |
|---|---|
| `documents.csv` | the documents: paper, kind of text (abstract or summary), address, SHA-256 and length of the text |
| `claims.csv` | claims with the experiment, run and model that extracted them |
| `quotes.csv` | the quote of every claim, exactly as in the document, with its start and end offsets |
| `edges.csv` | relations with a type and a weight, for example a claim `derived_from` a document |
| `vectors-0001.png`, … | the embeddings: every document is one row of pixels in an 8-bit grayscale image |
| `vectors.csv` | which image and row belongs to which document, and the scale of each vector |
| `datapackage.json` | description of the columns, keys and references (Frictionless Data) |
| `manifest.json` | SHA-256 of every file and the hash of the whole package |

An embedding is read from its row of pixels as `scale × (pixel − 128)` for every pixel of the row. The
images are stored uncompressed, so any PNG reader opens them and the same numbers always give the same bytes.
No file is larger than 2 MiB: a larger table of quotes or relations is stored in parts with the same
columns (`quotes-0001.csv`, `quotes-0002.csv`), and `datapackage.json` lists every file.

The texts and titles of the documents are not repeated here. They are in `lab/corpora/<corpus>/corpus.jsonl`
of this repository, with the same SHA-256, computed over the text with runs of whitespace collapsed to one space.
Offsets count characters of that text. Only corpora whose source records a basis for redistribution in
`lab/sources.yaml` are included.

## How to check the hash

The hash of a package is the SHA-256 of the output of `sha256sum` on its files other than `manifest.json`,
listed by name. Its first 12 characters are in the name of the folder:

    cd v1-<hash>
    LC_ALL=C ls | grep -vx manifest.json | xargs sha256sum | sha256sum

The full check needs only Python 3.10 or newer, run from the root of the repository. It checks every
checksum and every reference between the files, and with `--corpora` also every quote against the text
of its document:

    python lab/graph_package.py verify dowody/data/graph/v1-<hash> --corpora lab/corpora

The lab builds the package from its database with `python lab/graph_package.py build`. The same data always
give the same bytes, so a rebuild gives the same hash.
