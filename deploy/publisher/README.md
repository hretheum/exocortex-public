# Publisher on a home server

The publisher is the only way documents get from the vault into this
repository. It runs every 15 minutes as a systemd user unit, checks every
changed file with the publishing gate and pushes what passed. Everything here
assumes a Linux server with systemd, git and Python 3.12; the author's setup
is a home server that already runs the Exocortex instance.

## Pieces

| Unit | What it does |
|---|---|
| `exocortex-publisher.timer` / `.service` | One run every 15 minutes: pull tools, diff the synced folder against the repository, run leakgate, simcheck, paritycheck and humanlint, commit and push what passed. |
| `exocortex-simcheck.service` | Serves the similarity index on 127.0.0.1:8099. Request bodies are never logged. |
| `exocortex-simcheck-index.timer` / `.service` | Rebuilds the index from the private corpus every night at 02:40. |
| `exocortex-gate-selftest.timer` / `.service` | Plants canaries every night at 03:30. If one slips through, it creates the lock file and the publisher stops until a person looks into it. |

## Install

1. Syncthing: share only the `dowody` folder from the laptop, as "Send Only"
   on the laptop and "Receive Only" on the server. The private folder next to
   it is never shared.
2. Create a deploy key with write access to this repository only and clone
   the repository into `~/exocortex-publisher/repo` with it.
3. `python3.12 -m venv ~/exocortex-publisher/venv && ~/exocortex-publisher/venv/bin/pip install -r ~/exocortex-publisher/repo/tools/requirements.txt`
4. Put the private HMAC key in `~/.config/exocortex-publisher/hmac.key`
   (`chmod 600`). Optionally add the private self-test cases file.
5. Copy `publisher.env.example` to `~/.config/exocortex-publisher/publisher.env`,
   fill in absolute paths and the notification settings, `chmod 600`.
6. Build the first index by hand:
   `systemctl --user start exocortex-simcheck-index.service`
7. Install and start the units:

   ```sh
   mkdir -p ~/.config/systemd/user ~/.local/state/exocortex-publisher
   cp ~/exocortex-publisher/repo/deploy/publisher/*.service ~/exocortex-publisher/repo/deploy/publisher/*.timer ~/.config/systemd/user/
   systemctl --user daemon-reload
   systemctl --user enable --now exocortex-simcheck.service exocortex-simcheck-index.timer \
       exocortex-gate-selftest.timer exocortex-publisher.timer
   loginctl enable-linger "$USER"   # keep user units running without a login session
   ```

8. Test: `systemctl --user start exocortex-publisher.service`, then
   `journalctl --user -u exocortex-publisher -n 50` and the last line of
   `runs.jsonl`.

## What a run records

`runs.jsonl` gets one JSON line per run: time, status (`ok`, `nothing`,
`held-only`, `locked`, `error`), published and removed paths, held paths with
the names of the rules that held them, and the commit hash. It never contains
the text that matched.

## When the lock file exists

The nightly self-test missed a planted canary. Nothing is published until the
cause is found, fixed, and the self-test passes again (it removes the lock
file itself when it passes).
