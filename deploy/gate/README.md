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
| `exocortex-gate-publisher.container` + `.timer` | Every 15 minutes: sync the checkout, diff with the synced vault folder, run leakgate, simcheck, paritycheck, docschema and humanlint, commit and push what passed, notify about held files. |
| `exocortex-gate-index.container` + `.timer` | 02:40 every night: rebuild the index from the vault (read-only, published documents excluded) and optionally the Exocortex database; calibrated thresholds carry over. |
| `exocortex-gate-selftest.container` + `.timer` | 03:30 every night: planted canaries. A miss creates the lock file and the publisher stops. |
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

## Checking

- `journalctl --user -u exocortex-gate-publisher -n 50`
- last run: `podman run --rm -v exocortex-gate-state:/state:ro --entrypoint tail ghcr.io/hretheum/exocortex-gate:main -n 1 /state/runs.jsonl`
- lock file present means the self-test failed; nothing is published until it passes again.

The run log records paths and rule names only, never matched text.
