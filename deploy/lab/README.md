# Exocortex lab on the home server (rootless Podman, Quadlet)

The lab runs on the same server as the private Exocortex instance, so the
separation has to hold even when someone makes a mistake (roadmap task F2.1).

| File | What it does |
|---|---|
| `exocortex-lab.network` | Internal network: no route to the host, the LAN or the internet. |
| `exocortex-lab-db.container` + `.volume` | Lab database (the `exocortex-db` image) with its own role, password and volume. No published port. |
| `exocortex-lab-migrate.container` | Schema migrations from the public engine image. On demand and before the API starts. |
| `exocortex-lab-api.container` | Lab Capture API, on the lab network only. Sees only the published documents folder of the vault, read-only. |
| `exocortex-lab-isolation.container` + `.timer` | 03:40 every night: from inside the lab, every known address of the private database must refuse a TCP connection, no private vault folder may be visible, and the lab database must answer. |

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
rm -rf "$tmp"

pw=$(openssl rand -hex 24)
printf %s "$pw" | podman secret create lab_db_password -
printf %s "postgresql://lab:$pw@exocortex-lab-db:5432/lab" | podman secret create lab_database_url -
openssl rand -hex 24 | tr -d '\n' | podman secret create lab_capture_token -
unset pw

systemctl --user daemon-reload
systemctl --user start exocortex-lab-db exocortex-lab-migrate exocortex-lab-api
systemctl --user start exocortex-lab-isolation     # expect "status": "pass"
systemctl --user enable --now exocortex-lab-isolation.timer
```

Add the server's LAN addresses to `LAB_PRIVATE_DB_TARGETS` in `lab.env`.

## Not yet

The internal network also cuts the lab off from the local model server and
from the internet. Both come back through explicit, allowlisted paths:
source downloads in F2.2 and F3.2, model access when the lab starts
extracting (F3.3).
