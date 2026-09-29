# Publishing gate on a home server (rootless Podman, Quadlet)

The gate runs from one image, `ghcr.io/hretheum/exocortex-gate`, built and
scanned in CI. The server gets the image and a few configuration files;
no source code from the repository is copied to it. The publisher keeps a
partial, sparse clone that contains only the published documents folder.

## Units

| File | What it does |
|---|---|
| `exocortex-gate.pod` | Rootless pod on the host network. Services bind to 127.0.0.1. |
| `exocortex-gate-{state,repo,index}.volume` | Lock file and run log; the documents checkout; the similarity index. |
| `exocortex-gate-simcheck.container` | Serves the index on 127.0.0.1:8099 and reloads it after rebuilds. |
| `exocortex-gate-publisher.container` + `.timer` | Every 15 minutes: sync the checkout, diff with the synced vault folder, run the checks of each file's publication class (leakgate, simcheck, paritycheck, docschema, humanlint; see below), commit and push what passed, notify about held files. |
| `exocortex-gate-index.container` + `.timer` | 02:40 every night: rebuild the index from the vault (read-only, published documents excluded) and optionally the Exocortex database; calibrated thresholds carry over. |
| `exocortex-gate-selftest.container` + `.timer` | 03:30 every night: planted canaries, also in every publication class. A miss creates the lock file and the publisher stops. |
| `exocortex-gate-calibrate.container` | By hand: calibrate and apply simcheck thresholds; the numeric report goes to the state volume. |
| `exocortex-gate-update.timer` / `.service` | 02:20 every night: pull the latest gate image and restart simcheck. |

Quadlet reads `.pod`, `.volume` and `.container` files from
`~/.config/containers/systemd/`; timers are ordinary systemd units and go to
`~/.config/systemd/user/`.

## Install

1. Log in to GHCR so rootless Podman can pull private images, with the
   credentials stored persistently:
   `podman login ghcr.io --authfile ~/.config/containers/auth.json`
2. Take the deployment files out of the image:

   ```sh
   tmp=$(mktemp -d)
   podman run --rm -v "$tmp:/out:Z" ghcr.io/hretheum/exocortex-gate:main export /out
   mkdir -p ~/.config/containers/systemd/exocortex-gate ~/.config/systemd/user ~/.config/exocortex-gate
   cp "$tmp"/quadlet/* ~/.config/containers/systemd/exocortex-gate/
   cp "$tmp"/systemd/* ~/.config/systemd/user/
   cp -n "$tmp"/gate.env.example ~/.config/exocortex-gate/gate.env && chmod 600 ~/.config/exocortex-gate/gate.env
   ```

3. Secrets (values never go into files in the repository or into `gate.env`):

   ```sh
   podman secret create leakgate_hmac_key /path/to/hmac.key      # the gate's private HMAC key
   ssh-keygen -t ed25519 -N '' -C exocortex-gate -f "$tmp/deploy_key"
   podman secret create gate_deploy_key "$tmp/deploy_key"        # add deploy_key.pub to the repo with write access
   printf %s "$TELEGRAM_BOT_TOKEN" | podman secret create gate_telegram_token -   # or: printf none | ...
   printf %s "$PG_DSN" | podman secret create simcheck_pg_dsn -  # or: printf none | ...
   rm -rf "$tmp"
   ```

4. Fill in `~/.config/exocortex-gate/gate.env`. If the synced documents
   folder or the vault is not at `~/vault/_source/dowody` / `~/vault`, add
   drop-ins, e.g. `~/.config/containers/systemd/exocortex-gate-publisher.container.d/source.conf`
   with `[Container]` and a replacement `Volume=` line.
5. Start:

   ```sh
   systemctl --user daemon-reload
   systemctl --user start exocortex-gate-pod exocortex-gate-index   # first index build
   systemctl --user start exocortex-gate-simcheck exocortex-gate-calibrate
   systemctl --user enable --now exocortex-gate-publisher.timer exocortex-gate-index.timer \
       exocortex-gate-selftest.timer exocortex-gate-update.timer
   loginctl enable-linger "$USER"
   ```

`exocortex-gate-update.timer` pulls the latest image from `main` (which
passed the gate in CI) every night and restarts the simcheck service. It is
scoped to the gate: `podman-auto-update.timer` would also update every other
container on the host that has an AutoUpdate label.

## Running on demand

Every job can run at any time; the timers only set the default rhythm.

| What | Command |
|---|---|
| Publish now | `systemctl --user start exocortex-gate-publisher` |
| Rebuild the index | `systemctl --user start exocortex-gate-index` (then restart simcheck: `systemctl --user restart exocortex-gate-simcheck`) |
| Self-test | `systemctl --user start exocortex-gate-selftest` |
| Calibrate | `systemctl --user start exocortex-gate-calibrate` |
| Pull the newest image | `systemctl --user start exocortex-gate-update` |
| Review page for close paragraphs | `systemctl --user start exocortex-gate-review` |
| Release paragraphs marked "keep" | `systemctl --user start exocortex-gate-approve` |

Add `--no-block` to return at once and follow with
`journalctl --user -fu <unit>`. In GitHub, every workflow has a "Run
workflow" button (workflow_dispatch), including the nightly self-test.

## Calibration

Positives are private paragraphs, edited mechanically (literal layer) or
rewritten by the local model (semantic layer). Negatives are public texts on
similar topics: the published documents and the folders in
`SIMCHECK_CALIBRATION_PUBLIC` (on the home server: the arXiv paper summaries
the engine compiles, which are kept out of the private corpus for this
reason). A negative that is a copy of a corpus paragraph is counted as
`negatives_in_corpus` and left out.

Policy for each layer: if positives and negatives separate, the threshold
sits halfway between them; otherwise no missed positive comes first, unless
that holds more than `SIMCHECK_FA_BUDGET` (default 5%) of the negatives, in
which case the threshold rises to fit the budget and the report shows the
miss rate it costs. Every run compares three
semantic measures (plain similarity, margin over the next neighbours,
CSLS) and checks each on a held-out half.

With `SIMCHECK_JUDGE_URL` and `SIMCHECK_JUDGE_MODEL` set, calibration also
measures a two-stage check: plain similarity only picks candidates (the
candidate threshold lets at most `SIMCHECK_STAGE1_MISS` of the positives
through), and a local chat model decides for each candidate whether it
restates one of its three nearest private paragraphs. Once such a report is
applied, simcheck works this way; if the model is unreachable the check
fails and the publisher holds the file. For this the index keeps the
private paragraph texts; the service never returns them.

The report (numbers only) goes to the state volume. With
`SIMCHECK_CALIBRATION_APPLY=0` nothing is applied; apply a report later with
`SIMCHECK_CALIBRATION_FROM=/state/<report>.json` in a drop-in or with
`podman run`.

## Publication classes and checks

The publisher gives every path in the documents folder a class
(`tools/publisher/classes.py`, roadmap tasks F1.11 and F1.13). The list is
part of the image, so it changes only through a commit that passes CI.
Nothing in the vault or in a file header can change a class.

| Class | Paths (under `pl/` and `en/` unless noted) | Checks |
|---|---|---|
| Project documentation | `01-cycle.md` to `06-interactive-lab-design.md`, `roadmap/**`, `templates/**`, `img/**`; only `.md` and `.svg` files up to 128 KiB | leakgate at the blocking tier (warnings only go to the run log), the machine translation rule, paritycheck, docschema, humanlint |
| Experiment | `experiments/<slug>/**`; `data/<slug>/**` and `prereg.jsonl` (no language folder) | every check, including simcheck and leakgate warnings |
| Generated page | `generated/**` | every check |
| Unknown | any other path; a documentation path with another extension; a documentation file over 128 KiB; any error while classifying | every check, and an alarm in the notification |

What follows from the table:

- Documentation is never sent to simcheck. It does not appear on the review
  page and gets no paragraph approvals: `approve` counts such ticks as
  `no_semantic_check` and records nothing.
- The run log has two more fields. `classes` gives the class of every file
  the run touched (a dry run lists every file). `warnings` lists the
  leakgate findings that did not hold a documentation file, as rule names.
- The nightly self-test also plants canaries in every class (the
  `publication-classes` suite in `selftest.json`). In every class,
  synthetic personal data and a blocking canary must be held, and clean
  files must pass. A warning canary must be held outside documentation and
  logged in it. A miss sets the lock, as before.

### Switching every check off for documentation

This is one line in `tools/publisher/classes.py`: replace the `DOCS:`
entry of `CHECKS` with `DOCS: frozenset(),`, commit it and let CI build the
image. It is not enabled.

The risk: documentation is written largely by agents. With every check off,
nothing stops a document that names a client, a private machine or a
person, or carries personal data, from going public within 15 minutes. The
literal scanner is deterministic and almost never raises a false alarm on
documentation: every documentation hold before F1.13 was semantic.
Switching it off gains almost nothing and removes the last safeguard.

After the switch, CI skips the documentation canary tests and gives the
reason. The nightly self-test lists the class under `exempt` in
`selftest.json` and in its output instead of locking the publisher.

## Units of publication

An experiment goes to the repository as a whole or not at all (roadmap task
F1.12). Its unit is `pl/` and `en/experiments/<slug>/**`,
`data/<slug>/**` and the lines of `prereg.jsonl` with its slug. Every
other file is a unit together with its language pair. If any part of an
experiment is held, the publisher copies, deletes and appends none of it.
The public version stays as it was, every path gets a reason (for example
`unit held: experiment <slug>`), and the other units go out in the same
commit. An experiment is also held, with a reason that starts with
`incomplete`, when:

- a file lacks its version in the other language;
- a registry line lacks its card in both languages;
- it is removed from the vault while the lab folder is not mounted, so its
  data could not be removed with it.

A registered experiment therefore cannot lose its card.

The public registry is built from lines. The lines of experiments that
passed are appended at the end, so the order in the file is the order of
publication. The source may list lines in another order, but it must keep
every public line unchanged. If it loses or changes one, nothing is
appended. Each new line goes through leakgate on its own, and the registry
as it would be published is scanned once more.

## Held paragraphs: review and release

A semantic hold is not a verdict; it asks a person to look. The review job
writes a page to the private working folder of the vault
(`_source/dowody-prywatne/robocze/<date>-przeglad-semantyczny.md`, or
`-semantic-review.md` with `GATE_REVIEW_LANG=en`). For every paragraph at or
above the semantic threshold, and every candidate the judge says repeats a
note, the page shows the public paragraph, the three nearest protected
paragraphs with links into the vault, the model's verdict and two boxes:
keep or rewrite. Project documentation is not on the page, because it
skips the semantic comparison. After ticking, the approve job records the
hashes of the paragraphs marked keep in `approved-paragraphs.txt` next to
the index; simcheck skips them from then on. An edited paragraph gets a new
hash and is checked again. Approvals never apply to the literal layer.

## Checking

- `journalctl --user -u exocortex-gate-publisher -n 50`
- last run: `podman run --rm -v exocortex-gate-state:/state:ro --entrypoint tail ghcr.io/hretheum/exocortex-gate:main -n 1 /state/runs.jsonl`
- lock file present means the self-test failed; nothing is published until it passes again.

The run log records paths and rule names only, never matched text.
