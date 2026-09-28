# Exocortex on rootless Podman (Quadlet)

This directory runs the Exocortex engine on a single home server with
rootless Podman. Every unit is a Quadlet file. Nothing on the host runs
source code: all work happens inside the published images.

## Files

Long-running services (`Restart=always` / `on-failure`):

- `exocortex-db.container` - Postgres 16 with pgvector and Apache AGE.
- `exocortex-api.container` - Capture API; runs migrations, then uvicorn.
- `exocortex-scorer.container` - scorer daemon (LISTEN `content_acquired`).
- `exocortex-vault-watcher.container` - watches the vault and posts to the Capture API.
- `exocortex-notify-listener.container` - `pg_notify` to Telegram push.
- `exocortex-telegram.container` - Telegram bot (long polling).
- `exocortex-syncthing.container` - vault sync with your other machines.

One-shot jobs (`Type=oneshot`), each started by the `.timer` of the same name:

- `exocortex-ingest` - vault reconciliation, scorer backfill, compile of the work domain.
- `exocortex-compile` - daily compile of the whole wiki.
- `exocortex-gmail` - Gmail adapter; on success starts `exocortex-gmail-compile`.
- `exocortex-rss` - RSS adapter; on success starts `exocortex-rss-compile`.
- `exocortex-synth` - nightly synthesis.
- `exocortex-gap-radar` - weekly gap radar.
- `exocortex-night-shift` - night shift briefing.
- `exocortex-live-sections` - live sections processor.

`exocortex-migrate.container` is a one-shot without a timer: it runs at
startup and can be started by hand.

Quadlet generates `<name>.service` from `<name>.container`, so a timer
called `<name>.timer` starts the matching container.

## Install

Put your settings in `~/.config/exocortex/` (`exocortex.env`,
`llm_routing.local.yaml`, `sources.yaml`). The vault lives in `~/vault`,
database and Syncthing data in `~/exocortex/`. Adjust the `Volume=`
lines if your paths differ (`%h` is your home directory).

```sh
# take the unit files from the engine image, no checkout of the repository needed
tmp=$(mktemp -d)
podman run --rm --entrypoint sh -v "$tmp:/out:Z" ghcr.io/hretheum/exocortex:main \
  -c 'cp /opt/exocortex/deploy/quadlet/* /out/'
mkdir -p ~/.config/containers/systemd/exocortex ~/.config/systemd/user
cp "$tmp"/*.container ~/.config/containers/systemd/exocortex/
cp "$tmp"/*.timer ~/.config/systemd/user/     # timers are plain systemd units
rm -rf "$tmp"
systemctl --user daemon-reload
systemctl --user start exocortex-db exocortex-api exocortex-scorer \
  exocortex-vault-watcher exocortex-notify-listener exocortex-telegram exocortex-syncthing
systemctl --user enable --now exocortex-ingest.timer exocortex-compile.timer \
  exocortex-gmail.timer exocortex-rss.timer exocortex-synth.timer \
  exocortex-gap-radar.timer exocortex-night-shift.timer exocortex-live-sections.timer
loginctl enable-linger "$USER"
```

Quadlet units are generated, so `systemctl --user enable` does not apply to
the `.container` files; their `[Install]` section starts them at boot.
`loginctl enable-linger` keeps your user services running without a login
session.

## Network

All services use `Network=host` or publish ports on `127.0.0.1` only:
Postgres 5432, Capture API 8000, Syncthing GUI 8384. The one exception is
the Syncthing transport port 22000 (TCP and UDP), which must be reachable
from the LAN for sync to work.

## Site-specific extra steps

To run something after a job (for example a check after `exocortex-compile`),
add a drop-in instead of editing these files:

```ini
# ~/.config/containers/systemd/exocortex-compile.container.d/50-extra.conf
[Unit]
OnSuccess=my-extra-step.service
```

and put `my-extra-step.container` next to the other units. Extra steps must
themselves be containers: do not add `ExecStartPost=` lines that run
scripts from the host filesystem. Run `systemctl --user daemon-reload`
after adding or changing drop-ins.

## Note on the author's deployment

The author's own deployment used to run a host script after ingest,
compile, gmail and rss as a language check on the generated wiki pages.
That step was removed because it ran source code on the host. It has to
be packaged as a container image before it can come back, as a drop-in
like the one above.
