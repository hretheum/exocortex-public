# Exocortex lab on the self-hosted server (rootless Podman, Quadlet)

The lab runs on the same server as the private Exocortex instance, so the
separation has to hold even when someone makes a mistake (roadmap task F2.1).

| File | What it does |
|---|---|
| `exocortex-lab.network` | Internal network: no route to the host, the LAN or the internet. |
| `exocortex-lab-db.container` + `.volume` | Lab database (the `exocortex-db` image) with its own container, password and volume. No published port. |
| `exocortex-lab-migrate.container` | Schema migrations from the public engine image. On demand and before the API starts. |
| `exocortex-lab-api.container` | Lab Capture API, on the lab network only. Sees only the published documents folder of the vault, read-only. |
| `exocortex-lab-llm.container` + `.volume` | Gateway to the local model server. Not on the lab network: its own network namespace forwards only the model server's port on the host loopback (`pasta -T 8080`). Lab processes talk to it through a Unix socket in the volume. Three calls (`/v1/models`, `/v1/chat/completions`, `/v1/embeddings`) for the models in `lab/models.yaml`; everything else is refused. |
| `exocortex-lab-fetch.container` + `.volume` | Gateway for downloads from allowed sources. Not on the lab network: its own network namespace reaches the internet only (no host ports). Lab jobs talk to it through a Unix socket in the volume. |
| `exocortex-lab-sync.container` + `.timer` | Every 15 minutes: documents, hypothesis cards and gate decisions into the lab, data export and result pages into the `exocortex-lab-out` volume, which the publisher reads. |
| `exocortex-lab-radar.container` + `.timer` | Sunday 22:30: radar channels into the lab graph, the week's radar page and the first scoring of its candidates by three model families (F5.1 to F5.3). |
| `exocortex-lab-applications-draft@.container` + `exocortex-lab-drafts.volume` | On demand, one experiment per instance: the draft of the business applications section (F8.1) into the `exocortex-lab-drafts` volume, never into the vault. |
| `exocortex-lab-graph-package.container` | On demand: the public graph package (F8.2) from the lab database into `data/graph/` of the `exocortex-lab-out` volume, which the publisher reads. |
| `exocortex-lab-run@.container` | On demand, one run per instance: one sample of one experiment through the lab queue (F2.9). |
| `exocortex-lab-work.container` + `.timer` | Drains the queue of every experiment, grouped by model, and marks finished runs (F2.9). On demand; the nightly timer (00:30) ships disabled. |
| `exocortex-lab-blind@.container` + `blind.env.example` | On demand, one step of blind rating per instance: draw a sample, import the rated page, summary, publish (F2.9, F2.10). |
| `exocortex-lab-isolation.container` + `.timer` | 03:40 every night: from inside the lab, every known address of the private database and of the outside world must refuse a TCP connection, no private vault folder may be visible, the lab database must answer, and the model gateway must refuse other paths, other models and absolute-form targets. |

The units come from the engine image (`/opt/exocortex/deploy/lab/`); the
server gets no source code.

## Install

```sh
tmp=$(mktemp -d)
podman run --rm --entrypoint sh -v "$tmp:/out:Z" ghcr.io/hretheum/exocortex-public:main \
  -c 'cp -r /opt/exocortex/deploy/lab/. /out/'
mkdir -p ~/.config/containers/systemd/exocortex-lab ~/.config/systemd/user ~/.config/exocortex-lab
cp "$tmp"/quadlet/* ~/.config/containers/systemd/exocortex-lab/
cp "$tmp"/systemd/* ~/.config/systemd/user/
cp -n "$tmp"/lab.env.example ~/.config/exocortex-lab/lab.env && chmod 600 ~/.config/exocortex-lab/lab.env
cp -n "$tmp"/blind.env.example ~/.config/exocortex-lab/blind.env
rm -rf "$tmp"

pw=$(openssl rand -hex 24)
printf %s "$pw" | podman secret create lab_db_password -
printf %s "postgresql://exocortex:$pw@exocortex-lab-db:5432/exocortex" | podman secret create lab_database_url -
openssl rand -hex 24 | tr -d '\n' | podman secret create lab_capture_token -
unset pw

systemctl --user daemon-reload
systemctl --user start exocortex-lab-db exocortex-lab-migrate exocortex-lab-api exocortex-lab-llm
systemctl --user start exocortex-lab-isolation     # expect "status": "pass"
systemctl --user enable --now exocortex-lab-isolation.timer
```

Add the server's LAN addresses to `LAB_PRIVATE_DB_TARGETS` in `lab.env`.

## Running on demand

Rule: every recurring lab job has an on-demand start with one command, and every
one-off job is a unit too. A timer only sets the default rhythm. A test in the
repository (`tests/unit/test_lab_units.py`) checks that every timer here
starts a unit that can be started by hand and that the unit is listed below.

| What | Command |
|---|---|
| Documents, cards, gate decisions, pages (every 15 minutes) | `systemctl --user start exocortex-lab-sync` |
| Weekly radar (Sunday 22:30) | `systemctl --user start exocortex-lab-radar` |
| Isolation check (03:40 every night) | `systemctl --user start exocortex-lab-isolation` |
| Drain the queue (timer ships disabled) | `systemctl --user start exocortex-lab-work` |
| One run of one sample | `systemctl --user start exocortex-lab-run@<experiment>_<sample>` |
| Blind rating: draw, import, summary, publish | `systemctl --user start exocortex-lab-blind@<action>_<experiment>_<sample>` |
| Applications section draft | `systemctl --user start exocortex-lab-applications-draft@<slug>` |
| Public graph package | `systemctl --user start exocortex-lab-graph-package` |

Add `--no-block` to return at once, and read the result with
`journalctl --user -u <unit> -o cat`. Every job prints one JSON document.

### Runs and the queue (F2.9)

The instance name of a run is `<experiment>_<sample>`, optionally followed by
`_<config>.<config>` (default: every configuration of the spec) and by
`_queue`. Unit names cannot carry spaces or commas, and container names cannot
carry colons, so the parts are joined with underscores and the configurations
with dots. The spec comes from `lab/experiments/<experiment>.yaml` in the
image; the toy experiment `toy-length` has none and runs `tuning` or `control`
with both of its configurations.

```sh
systemctl --user start exocortex-lab-run@toy-length_tuning                   # run and work through it
systemctl --user start exocortex-lab-run@intent-vs-fact_tuning_qwen36-baseline.qwen36-mode
systemctl --user start exocortex-lab-run@toy-length_tuning_queue             # enqueue only
systemctl --user start exocortex-lab-work                                    # drain the queue
```

Experiments of the kind `retrieval` (F5.8) need no unit of their own: `exocortex-lab-run@<experiment>_<sample>` and
`exocortex-lab-work` run them like the others, `work` stores their nDCG@10, recall@k and MRR when a run finishes,
and the pages and the data export pick them up in the next `exocortex-lab-sync`. The toy experiment is
`systemctl --user start exocortex-lab-run@toy-retrieval_test-12`. A question set that is malformed, or names
a document that is not in the corpus, refuses the run before anything is stored.

A run of an experiment with a hypothesis is refused until its card is frozen,
and a control sample can be read once per card version; the lab enforces both.
`_queue` leaves the jobs for `exocortex-lab-work`, which takes every pending job
of every experiment grouped by model, so each model loads once, and then marks
the runs whose jobs are all finished. To let the queue drain every night:
`systemctl --user enable --now exocortex-lab-work.timer`. It is not enabled by
the install steps.

### Blind rating (F2.9, F2.10)

The instance name is `<action>_<experiment>_<sample>`, with an optional last
part that belongs to the action:

| Action | What it does | Optional last part |
|---|---|---|
| `draw` | Draws the blind sample from the results of the newest finished run and writes the rating page to `blind/<experiment>/<sample>.{pl,en}.md` in `exocortex-lab-out`. Size, repeated items and seed come from `~/.config/exocortex-lab/blind.env`. | run ids, joined with dots |
| `import` | Reads the rated page `{pl,en}/experiments/<experiment>/<sample>.md` from the vault (read-only) and stores the ratings in `exp_judgments`, then prints the summary. | the page name, if it differs from the sample |
| `summary` | Shares per configuration with Wilson intervals, differences between configurations with a bootstrap by document. | the rater, when the sample has more than one |
| `publish` | The results page with the configuration of every item, into `generated/` for the publisher. | the rater |

```sh
systemctl --user start exocortex-lab-blind@draw_toy-length_blind-desk
systemctl --user start exocortex-lab-blind@import_toy-length_blind-desk
```

The owner rates on the review desk (screen "Ocena na ślepo"), which reads the
page from `exocortex-lab-out` and never reaches the lab database. The gate job
`apply-ratings` writes the ticks into the page in the vault, and `import` reads
it with the same code and the same checks as a page filled by hand in
Obsidian, which stays the fallback. See `deploy/gate/README.md`.

## Paths out of the lab

The lab network is internal. Every path out is explicit and checked every
night by the isolation check:

| Path | How | What it allows |
|---|---|---|
| Local models | `exocortex-lab-llm`, Unix socket in the `exocortex-lab-llm` volume | the three calls above, for models listed in `lab/models.yaml` with their license |
| Public sources | `exocortex-lab-fetch`, Unix socket in the `exocortex-lab-fetch` volume | `GET /fetch?url=` for https URLs on `lab/sources.yaml`, keeping each source's pause between requests; redirects only to allowed URLs |

Adding a model is a commit to `lab/models.yaml` with the license and where
it was checked. The gateway itself holds no credentials, takes no target
from a request, follows no redirects and logs one line per request without
prompts or answers.

## Lab jobs

Every job runs from the engine image on the lab network, prints one JSON
document and exits. For example:

```sh
lab() {
  podman run --rm --network exocortex-lab --env-file ~/.config/exocortex-lab/lab.env \
    --secret lab_database_url,type=env,target=DATABASE_URL \
    -v ~/vault/_source/dowody:/vault/_source/dowody:ro,z \
    -v exocortex-lab-llm:/run/lab-llm:z \
    ghcr.io/hretheum/exocortex-public:main exocortex lab "$@"
}
lab docs-sync                                   # published documents -> lab graph
lab corpus-graph --corpus intent-vs-fact --embed  # corpus papers -> lab graph (F3.2)
lab toy run --sample tuning                     # toy experiment through the queue (F2.6)
lab work                                        # drain the queue, grouped by model
lab signals --embed                             # radar channels through the fetch gateway (F5.2)
```

Jobs that download mount the fetch volume as well:
`-v exocortex-lab-fetch:/run/lab-fetch:z`.

## Applications section drafts (F8.1)

The draft of the business applications section runs on demand, one
experiment per unit instance. The instance name is the experiment's folder
under `experiments/`:

```sh
systemctl --user daemon-reload                  # once, after installing the units
systemctl --user start exocortex-lab-applications-draft@<slug>.service
journalctl --user -u exocortex-lab-applications-draft@<slug>.service -o cat
```

Each run reads the published documents folder of the vault and the exported
data (`exocortex-lab-out`), both read-only, calls a model from
`lab/models.yaml` through the model gateway and prints one JSON document.
`written` lists the files it wrote, `skipped` means the section in the vault
or the waiting draft is already current, and `refused` gives the reason no
draft was written, with `problems`. `not_run` lists the checks the engine
image cannot run (the gate's name scanner and the language check); run
`exocortex lab applications check <slug>` on a checkout with the gate tools
and the HMAC key before approving.

Drafts land in the `exocortex-lab-drafts` volume, never in the vault,
with `publish: false` and `human_validated: false`. To read it:

```sh
podman run --rm -v exocortex-lab-drafts:/drafts:ro,z --entrypoint cat ghcr.io/hretheum/exocortex-public:main \
  /drafts/pl/experiments/<slug>/applications.md /drafts/en/experiments/<slug>/applications.md
```

The review desk reads the volume read-only and lists the draft under
"Szkice do zatwierdzenia", marked as a draft from the lab. The owner reads it
there and approves it; "Publish now" then writes it into the vault with
`publish: true` and `human_validated: true`, only if both texts are still the
ones that were approved (`deploy/gate/README.md`). Nobody copies a draft into
the vault by hand, and the unit never sets either flag.

## Public graph package (F8.2)

The package holds the claims the lab extracted from public corpora, their
verbatim quotes with positions, the relations between documents and claims
and the embeddings of the documents (format: `lab/graph_package.py` and the
README it writes next to the versions). It is built on demand:

```sh
systemctl --user daemon-reload                  # once, after installing the units
systemctl --user start exocortex-lab-graph-package.service
journalctl --user -u exocortex-lab-graph-package.service -o cat
```

The job reads the lab database only and prints one JSON document:

- `version` and `package_sha256` name the package;
- `unchanged` says whether a package with the same content was already in
  place;
- `counts` and `bytes` give its size;
- `left_out` and `claims_left_out` say what did not go in and why: a kind of
  text without a basis for redistribution in `lab/sources.yaml`, personal
  data the gate would hold, a claim whose quote is not in its document or
  whose document changed after the run;
- `not_a_corpus` counts the lab's other nodes (documents, cards, radar
  signals), which are never in the package.

The new version goes to `data/graph/v1-<hash>/` in `exocortex-lab-out`, with
`latest.json` and the README beside it. The previous version is removed in
the same step. The publisher takes it from there: the whole `data/graph/`
folder is one unit of publication, so it goes out whole or waits on the
review desk. The same data give the same bytes, so a second run prints the
same hash and `unchanged: true`.

Anyone can check a published version from a clone with Python only:

```sh
python lab/graph_package.py verify dowody/data/graph/v1-<hash> --corpora lab/corpora
```

